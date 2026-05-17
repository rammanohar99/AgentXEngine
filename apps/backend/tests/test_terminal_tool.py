"""
Terminal tool tests — validates the allowlist and command execution.
"""

import pytest
from packages.agents.schemas import ToolCall
from packages.agents.tools.terminal import TerminalTool, _is_permitted


def _make_call(**kwargs) -> ToolCall:
    return ToolCall(tool_name="terminal", arguments=kwargs, call_id="test")


# ── Allowlist tests ───────────────────────────────────────────────────────────


def test_permitted_git_status() -> None:
    is_ok, reason = _is_permitted("git status")
    assert is_ok is True


def test_permitted_echo() -> None:
    is_ok, _ = _is_permitted("echo hello")
    assert is_ok is True


def test_permitted_python() -> None:
    is_ok, _ = _is_permitted("python --version")
    assert is_ok is True


def test_permitted_pytest() -> None:
    is_ok, _ = _is_permitted("pytest --version")
    assert is_ok is True


def test_blocked_rm() -> None:
    is_ok, reason = _is_permitted("rm -rf /")
    assert is_ok is False
    assert "not permitted" in reason.lower()


def test_blocked_curl() -> None:
    is_ok, _ = _is_permitted("curl https://evil.com")
    assert is_ok is False


def test_blocked_git_push() -> None:
    is_ok, reason = _is_permitted("git push origin main")
    assert is_ok is False
    assert "not permitted" in reason.lower()


def test_blocked_git_commit() -> None:
    is_ok, _ = _is_permitted("git commit -m 'hack'")
    assert is_ok is False


def test_blocked_empty_command() -> None:
    is_ok, reason = _is_permitted("")
    assert is_ok is False
    assert "empty" in reason.lower()


# ── Execution tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_terminal_executes_echo() -> None:
    tool = TerminalTool()
    result = await tool.execute(_make_call(command="echo hello_world"))
    assert result.success is True
    assert "hello_world" in result.output


@pytest.mark.asyncio
async def test_terminal_rejects_blocked_command() -> None:
    tool = TerminalTool()
    result = await tool.execute(_make_call(command="rm -rf /"))
    assert result.success is False
    assert result.error is not None
    assert "not permitted" in result.error.lower()


@pytest.mark.asyncio
async def test_terminal_captures_exit_code() -> None:
    tool = TerminalTool()
    # python -c "exit(1)" should return exit code 1
    result = await tool.execute(_make_call(command='python -c "import sys; sys.exit(1)"'))
    assert result.success is True  # Tool succeeded (ran the command)
    assert "exit code: 1" in result.output


def test_terminal_prompt_description() -> None:
    tool = TerminalTool()
    desc = tool.to_prompt_description()
    assert "terminal" in desc
    assert "git" in desc.lower()


def test_registry_includes_terminal() -> None:
    from packages.agents.tool_registry import ToolRegistry

    registry = ToolRegistry.with_defaults()
    assert registry.get("terminal") is not None
