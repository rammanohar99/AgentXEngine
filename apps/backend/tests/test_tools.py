"""
Filesystem tool unit tests.

All tests use a real temporary directory — no mocking of the filesystem.
This gives us confidence the sandbox logic actually works.
"""

import pathlib
from typing import Any

import pytest
from packages.agents.schemas import ToolCall
from packages.agents.tools.filesystem import (
    ListDirectoryTool,
    ReadFileTool,
    SearchFilesTool,
    _safe_resolve,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def workspace(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """
    Create a temporary workspace and point AGENT_WORKSPACE_ROOT at it.
    All tool tests run inside this sandbox.
    """
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(tmp_path))

    # Populate with some test files
    (tmp_path / "hello.py").write_text("def hello():\n    return 'world'\n")
    (tmp_path / "README.md").write_text("# Test Project\n\nThis is a test.\n")
    subdir = tmp_path / "src"
    subdir.mkdir()
    (subdir / "main.py").write_text(
        "from hello import hello\n\nif __name__ == '__main__':\n    print(hello())\n"
    )
    (subdir / "utils.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

    return tmp_path


def _make_call(tool_name: str, **kwargs: Any) -> ToolCall:
    return ToolCall(tool_name=tool_name, arguments=kwargs, call_id="test-call-id")


# ── read_file tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_file_returns_content(workspace: pathlib.Path) -> None:
    tool = ReadFileTool()
    result = await tool.execute(_make_call("read_file", path="hello.py"))
    assert result.success is True
    assert "def hello():" in result.output
    assert "hello.py" in result.output


@pytest.mark.asyncio
async def test_read_file_with_line_range(workspace: pathlib.Path) -> None:
    tool = ReadFileTool()
    result = await tool.execute(_make_call("read_file", path="hello.py", start_line=2, end_line=2))
    assert result.success is True
    assert "return 'world'" in result.output


@pytest.mark.asyncio
async def test_read_file_not_found(workspace: pathlib.Path) -> None:
    tool = ReadFileTool()
    result = await tool.execute(_make_call("read_file", path="nonexistent.py"))
    assert result.success is False
    assert result.error is not None
    assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_read_file_path_traversal_blocked(workspace: pathlib.Path) -> None:
    """Path traversal outside workspace root must be rejected."""
    tool = ReadFileTool()
    result = await tool.execute(_make_call("read_file", path="../../etc/passwd"))
    assert result.success is False
    assert result.error is not None
    assert "outside" in result.error.lower() or "denied" in result.error.lower()


# ── list_directory tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_directory_root(workspace: pathlib.Path) -> None:
    tool = ListDirectoryTool()
    result = await tool.execute(_make_call("list_directory", path="."))
    assert result.success is True
    assert "hello.py" in result.output
    assert "README.md" in result.output
    assert "src/" in result.output


@pytest.mark.asyncio
async def test_list_directory_with_depth(workspace: pathlib.Path) -> None:
    tool = ListDirectoryTool()
    result = await tool.execute(_make_call("list_directory", path=".", depth=2))
    assert result.success is True
    # Use os.sep-agnostic check — output uses platform path separators
    assert "main.py" in result.output
    assert "src" in result.output


@pytest.mark.asyncio
async def test_list_directory_not_found(workspace: pathlib.Path) -> None:
    tool = ListDirectoryTool()
    result = await tool.execute(_make_call("list_directory", path="nonexistent/"))
    assert result.success is False


@pytest.mark.asyncio
async def test_list_directory_path_traversal_blocked(workspace: pathlib.Path) -> None:
    tool = ListDirectoryTool()
    result = await tool.execute(_make_call("list_directory", path="../../"))
    assert result.success is False


# ── search_files tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_files_finds_pattern(workspace: pathlib.Path) -> None:
    tool = SearchFilesTool()
    result = await tool.execute(_make_call("search_files", pattern="def hello"))
    assert result.success is True
    assert "hello.py" in result.output
    assert "def hello" in result.output


@pytest.mark.asyncio
async def test_search_files_with_file_pattern(workspace: pathlib.Path) -> None:
    tool = SearchFilesTool()
    result = await tool.execute(_make_call("search_files", pattern="import", file_pattern="*.py"))
    assert result.success is True
    assert "main.py" in result.output


@pytest.mark.asyncio
async def test_search_files_no_matches(workspace: pathlib.Path) -> None:
    tool = SearchFilesTool()
    result = await tool.execute(_make_call("search_files", pattern="zzz_no_match_zzz"))
    assert result.success is True
    assert "No matches" in result.output


@pytest.mark.asyncio
async def test_search_files_case_insensitive(workspace: pathlib.Path) -> None:
    tool = SearchFilesTool()
    result = await tool.execute(_make_call("search_files", pattern="DEF HELLO"))
    assert result.success is True
    assert "hello.py" in result.output


# ── sandbox tests ─────────────────────────────────────────────────────────────


def test_safe_resolve_allows_valid_path(workspace: pathlib.Path) -> None:
    resolved = _safe_resolve("hello.py")
    assert resolved == workspace / "hello.py"


def test_safe_resolve_blocks_traversal(workspace: pathlib.Path) -> None:
    with pytest.raises(ValueError, match="outside"):
        _safe_resolve("../../etc/passwd")


def test_safe_resolve_allows_nested_path(workspace: pathlib.Path) -> None:
    resolved = _safe_resolve("src/main.py")
    assert resolved == workspace / "src" / "main.py"
