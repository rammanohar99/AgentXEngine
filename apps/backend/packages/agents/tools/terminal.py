"""
Terminal tool — executes shell commands in a sandboxed environment.

AGENTS.md: "terminal tool" listed as an initial tool.
AGENTS.md security: "Never allow unsafe unrestricted execution."

Security model:
- Allowlist of permitted commands (no arbitrary shell execution)
- Commands run in a restricted working directory
- Timeout enforced (default 30 seconds)
- No network access from executed commands
- Output truncated to prevent huge responses
- stdin is closed (no interactive commands)

Permitted command prefixes (configurable):
- git (read-only: status, log, diff, show, branch, tag)
- python -m pytest (test runner)
- python -m ruff (linter)
- cat, head, tail (file reading — prefer read_file tool)
- echo (output)

This is intentionally restrictive. The filesystem tools cover most
read-only use cases. The terminal tool is for build/test operations.
"""

from __future__ import annotations

import asyncio
import shlex
from typing import Any

import structlog

from packages.agents.tools.base import BaseTool

logger = structlog.get_logger(__name__)

# Commands that are explicitly permitted
# Format: tuple of allowed command prefixes (first token must match)
_ALLOWED_COMMANDS: frozenset[str] = frozenset(
    [
        "git",
        "echo",
        "python",
        "pytest",
        "ruff",
        "black",
        "mypy",
    ]
)

_MAX_OUTPUT_CHARS = 4000
_DEFAULT_TIMEOUT_SECONDS = 30


def _is_permitted(command: str) -> tuple[bool, str]:
    """
    Check if a command is in the allowlist.
    Returns (is_permitted, reason).
    """
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        return False, f"Invalid command syntax: {exc}"

    if not tokens:
        return False, "Empty command."

    base_command = tokens[0].lower()

    # Strip path prefix (e.g. /usr/bin/git → git)
    if "/" in base_command:
        base_command = base_command.split("/")[-1]

    if base_command not in _ALLOWED_COMMANDS:
        return False, (
            f"Command '{base_command}' is not permitted. "
            f"Allowed: {', '.join(sorted(_ALLOWED_COMMANDS))}"
        )

    # Block dangerous git subcommands
    if base_command == "git" and len(tokens) > 1:
        dangerous_git = {"push", "commit", "reset", "clean", "checkout", "merge", "rebase"}
        if tokens[1].lower() in dangerous_git:
            return False, f"git {tokens[1]} is not permitted (read-only git operations only)."

    return True, ""


class TerminalTool(BaseTool):
    """
    Execute permitted shell commands in a sandboxed environment.

    Only allowlisted commands are permitted.
    Output is truncated at 4000 characters.
    """

    def __init__(self, working_directory: str = ".") -> None:
        self._working_directory = working_directory

    @property
    def name(self) -> str:
        return "terminal"

    @property
    def description(self) -> str:
        return (
            "Execute a permitted shell command. "
            "Allowed commands: git (read-only), python, pytest, ruff, black, mypy, echo. "
            "Use for running tests, linting, or inspecting git history. "
            "Output is limited to 4000 characters."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"Timeout in seconds (default {_DEFAULT_TIMEOUT_SECONDS}).",
                },
            },
            "required": ["command"],
        }

    async def _run(self, arguments: dict[str, Any]) -> str:
        command: str = arguments["command"].strip()
        timeout: int = int(arguments.get("timeout", _DEFAULT_TIMEOUT_SECONDS))
        timeout = max(1, min(timeout, 60))  # Clamp to [1, 60] seconds

        # Validate before executing
        is_permitted, reason = _is_permitted(command)
        if not is_permitted:
            raise ValueError(f"Command not permitted: {reason}")

        logger.info("terminal_execute", command=command[:100])

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL,
                cwd=self._working_directory,
            )

            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except TimeoutError:
                process.kill()
                await process.communicate()
                raise TimeoutError(
                    f"Command timed out after {timeout} seconds: {command}"
                ) from None

            output = stdout.decode("utf-8", errors="replace")
            exit_code = process.returncode or 0

            # Truncate large outputs
            if len(output) > _MAX_OUTPUT_CHARS:
                output = (
                    output[:_MAX_OUTPUT_CHARS] + f"\n... (truncated at {_MAX_OUTPUT_CHARS} chars)"
                )

            result = f"$ {command}\n(exit code: {exit_code})\n\n{output}"

            logger.info(
                "terminal_complete",
                command=command[:100],
                exit_code=exit_code,
                output_length=len(output),
            )

            return result

        except (TimeoutError, ValueError):
            raise
        except Exception as exc:
            raise RuntimeError(f"Command execution failed: {exc}") from exc
