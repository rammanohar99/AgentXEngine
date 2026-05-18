"""
Executor unit tests.

Tests tool dispatch, missing tool handling, and result structure.
Uses real filesystem tools with a temp workspace.
"""

import pathlib

import pytest

from packages.agents.executor import Executor
from packages.agents.schemas import ToolCall
from packages.agents.tool_registry import ToolRegistry


@pytest.fixture
def workspace(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "test.py").write_text("x = 1\n")
    return tmp_path


@pytest.fixture
def executor() -> Executor:
    return Executor(registry=ToolRegistry.with_defaults())


@pytest.mark.asyncio
async def test_executor_dispatches_to_correct_tool(
    workspace: pathlib.Path, executor: Executor
) -> None:
    call = ToolCall(tool_name="read_file", arguments={"path": "test.py"}, call_id="abc")
    result = await executor.execute(call)
    assert result.success is True
    assert result.tool_name == "read_file"
    assert result.call_id == "abc"
    assert "x = 1" in result.output


@pytest.mark.asyncio
async def test_executor_returns_failure_for_unknown_tool(executor: Executor) -> None:
    call = ToolCall(tool_name="does_not_exist", arguments={}, call_id="xyz")
    result = await executor.execute(call)
    assert result.success is False
    assert result.error is not None
    assert "not registered" in result.error


@pytest.mark.asyncio
async def test_executor_records_duration(workspace: pathlib.Path, executor: Executor) -> None:
    call = ToolCall(tool_name="list_directory", arguments={"path": "."}, call_id="dur")
    result = await executor.execute(call)
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_tool_result_to_observation_success(
    workspace: pathlib.Path, executor: Executor
) -> None:
    call = ToolCall(tool_name="read_file", arguments={"path": "test.py"}, call_id="obs")
    result = await executor.execute(call)
    observation = result.to_observation()
    assert "read_file" in observation
    assert "x = 1" in observation


@pytest.mark.asyncio
async def test_tool_result_to_observation_failure(executor: Executor) -> None:
    call = ToolCall(tool_name="missing_tool", arguments={}, call_id="fail")
    result = await executor.execute(call)
    observation = result.to_observation()
    assert "failed" in observation.lower()
    assert "missing_tool" in observation
