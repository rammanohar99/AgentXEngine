"""
Filesystem tools — safe, sandboxed file operations.

Tools provided:
- read_file      — read file contents with optional line range
- list_directory — list files/dirs at a path with depth control
- search_files   — grep-style text search across files

Security model:
- All paths are resolved and validated against an allowed root
- Symlinks that escape the root are rejected
- Binary files are detected and rejected
- File size is capped to prevent memory exhaustion
- No write operations — read-only in Phase 2

The allowed root defaults to the current working directory.
It can be overridden via the AGENT_WORKSPACE_ROOT env variable.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any

from packages.agents.tools.base import BaseTool

# Max file size to read (2 MB) — prevents accidental huge file ingestion
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024

# Max directory entries to return
MAX_DIR_ENTRIES = 200

# Max search results
MAX_SEARCH_RESULTS = 50


def _get_workspace_root() -> pathlib.Path:
    """Return the sandboxed workspace root. Defaults to cwd."""
    root = os.environ.get("AGENT_WORKSPACE_ROOT", os.getcwd())
    return pathlib.Path(root).resolve()


def _safe_resolve(raw_path: str) -> pathlib.Path:
    """
    Resolve a path and verify it stays within the workspace root.
    Raises ValueError if the path escapes the sandbox.
    """
    workspace_root = _get_workspace_root()
    resolved = (workspace_root / raw_path).resolve()

    try:
        resolved.relative_to(workspace_root)
    except ValueError:
        raise ValueError(
            f"Path '{raw_path}' resolves outside the workspace root '{workspace_root}'. "
            "Access denied."
        ) from None

    return resolved


def _is_binary(file_path: pathlib.Path) -> bool:
    """Heuristic binary detection — read first 8KB and check for null bytes."""
    try:
        with open(file_path, "rb") as file_handle:
            chunk = file_handle.read(8192)
        return b"\x00" in chunk
    except OSError:
        return False


# ── read_file ─────────────────────────────────────────────────────────────────


class ReadFileTool(BaseTool):
    """Read the contents of a file within the workspace."""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read the contents of a file. Optionally specify start_line and end_line "
            "to read a specific range. Returns the file content as a string."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file, relative to the workspace root.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "First line to read (1-indexed, inclusive). Defaults to 1.",
                },
                "end_line": {
                    "type": "integer",
                    "description": (
                        "Last line to read (1-indexed, inclusive). Defaults to end of file."
                    ),
                },
            },
            "required": ["path"],
        }

    async def _run(self, arguments: dict[str, Any]) -> str:
        raw_path: str = arguments["path"]
        start_line: int = int(arguments.get("start_line", 1))
        end_line: int | None = arguments.get("end_line")

        resolved = _safe_resolve(raw_path)

        if not resolved.exists():
            raise FileNotFoundError(f"File not found: {raw_path}")
        if not resolved.is_file():
            raise ValueError(f"Path is not a file: {raw_path}")
        if resolved.stat().st_size > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"File '{raw_path}' exceeds the {MAX_FILE_SIZE_BYTES // 1024}KB size limit."
            )
        if _is_binary(resolved):
            raise ValueError(
                f"File '{raw_path}' appears to be binary. Only text files are supported."
            )

        content = resolved.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines(keepends=True)

        # Apply line range (convert to 0-indexed)
        start_idx = max(0, start_line - 1)
        end_idx = end_line if end_line is None else min(end_line, len(lines))
        selected_lines = lines[start_idx:end_idx]

        result = "".join(selected_lines)
        if start_line > 1 or end_line:
            line_info = f"lines {start_line}-{end_line or len(lines)}"
        else:
            line_info = f"{len(lines)} lines"
        return f"# {raw_path} ({line_info})\n\n{result}"


# ── list_directory ────────────────────────────────────────────────────────────


class ListDirectoryTool(BaseTool):
    """List files and directories at a given path."""

    @property
    def name(self) -> str:
        return "list_directory"

    @property
    def description(self) -> str:
        return (
            "List the contents of a directory. Returns file names, types, and sizes. "
            "Use depth to control recursion (default 1 = immediate children only)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to workspace root. Use '.' for root.",
                },
                "depth": {
                    "type": "integer",
                    "description": "How many levels deep to recurse. Default is 1.",
                },
            },
            "required": ["path"],
        }

    async def _run(self, arguments: dict[str, Any]) -> str:
        raw_path: str = arguments.get("path", ".")
        depth: int = int(arguments.get("depth", 1))
        depth = max(1, min(depth, 5))  # Cap at 5 to prevent huge outputs

        resolved = _safe_resolve(raw_path)

        if not resolved.exists():
            raise FileNotFoundError(f"Directory not found: {raw_path}")
        if not resolved.is_dir():
            raise ValueError(f"Path is not a directory: {raw_path}")

        entries: list[str] = []
        self._collect_entries(resolved, resolved, depth, 0, entries)

        if not entries:
            return f"Directory '{raw_path}' is empty."

        header = f"# {raw_path}/ ({len(entries)} entries)\n\n"
        return header + "\n".join(entries[:MAX_DIR_ENTRIES])

    def _collect_entries(
        self,
        base: pathlib.Path,
        current: pathlib.Path,
        max_depth: int,
        current_depth: int,
        entries: list[str],
    ) -> None:
        if current_depth >= max_depth:
            return
        try:
            items = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return

        for item in items:
            if item.name.startswith(".") and current_depth > 0:
                continue  # Skip hidden files in subdirectories
            relative = item.relative_to(base)
            indent = "  " * current_depth
            if item.is_dir():
                entries.append(f"{indent}{relative}/")
                self._collect_entries(base, item, max_depth, current_depth + 1, entries)
            elif item.is_file():
                size_kb = round(item.stat().st_size / 1024, 1)
                entries.append(f"{indent}{relative} ({size_kb}KB)")


# ── search_files ──────────────────────────────────────────────────────────────


class SearchFilesTool(BaseTool):
    """Search for text patterns across files in the workspace."""

    @property
    def name(self) -> str:
        return "search_files"

    @property
    def description(self) -> str:
        return (
            "Search for a text pattern across files in the workspace. "
            "Returns matching lines with file paths and line numbers. "
            "Use file_pattern to restrict search to specific file types (e.g. '*.py')."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Text string to search for (case-insensitive substring match).",
                },
                "directory": {
                    "type": "string",
                    "description": (
                        "Directory to search in, relative to workspace root. Default is '.'."
                    ),
                },
                "file_pattern": {
                    "type": "string",
                    "description": (
                        "Glob pattern to filter files (e.g. '*.py', '*.ts'). Default is '*'."
                    ),
                },
            },
            "required": ["pattern"],
        }

    async def _run(self, arguments: dict[str, Any]) -> str:
        pattern: str = arguments["pattern"]
        raw_dir: str = arguments.get("directory", ".")
        file_glob: str = arguments.get("file_pattern", "*")

        resolved_dir = _safe_resolve(raw_dir)

        if not resolved_dir.is_dir():
            raise ValueError(f"Search directory not found: {raw_dir}")

        matches: list[str] = []
        search_lower = pattern.lower()

        for file_path in sorted(resolved_dir.rglob(file_glob)):
            if not file_path.is_file():
                continue
            if file_path.stat().st_size > MAX_FILE_SIZE_BYTES:
                continue
            if _is_binary(file_path):
                continue

            try:
                relative = file_path.relative_to(_get_workspace_root())
                lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
                for line_number, line in enumerate(lines, start=1):
                    if search_lower in line.lower():
                        matches.append(f"{relative}:{line_number}: {line.rstrip()}")
                        if len(matches) >= MAX_SEARCH_RESULTS:
                            break
            except OSError:
                continue

            if len(matches) >= MAX_SEARCH_RESULTS:
                break

        if not matches:
            return f"No matches found for '{pattern}' in {raw_dir}."

        header = f"# Search results for '{pattern}' ({len(matches)} matches)\n\n"
        return header + "\n".join(matches)
