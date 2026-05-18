"""
Agent runtime integration tests.

The LLM (VertexAIService) is mocked — we control exactly what the model
returns so tests are deterministic and don't require GCP credentials.

Tests verify:
- A direct final answer (no tool calls) produces TEXT + DONE events
- A tool call followed by a final answer produces the full event sequence
- The step limit triggers a forced final answer
- Errors in tool execution are handled gracefully
"""

from __future__ import annotations

import pathlib
from typing import Any
from unittest.mock import MagicMock

import pytest

from packages.agents.runtime import AgentRuntime
from packages.agents.schemas import AgentEventType
from packages.agents.tool_registry import ToolRegistry

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_vertex_mock(responses: list[str]) -> MagicMock:
    """
    Build a mock VertexAIService that returns responses in sequence.
    Each call to complete() returns the next string in the list.
    """
    mock = MagicMock()
    call_count = 0

    async def fake_complete(messages: list[Any], **kwargs: Any) -> MagicMock:
        nonlocal call_count
        text = responses[min(call_count, len(responses) - 1)]
        call_count += 1
        response = MagicMock()
        response.text = text
        return response

    mock.complete = fake_complete
    return mock


async def _collect_events(runtime: AgentRuntime, message: str) -> list[Any]:
    """Run the runtime and collect all emitted events into a list."""
    events: list[Any] = []
    async for event in runtime.run(
        session_id="test-session",
        history=[],
        user_message=message,
    ):
        events.append(event)
    return events


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_direct_final_answer_emits_text_and_done() -> None:
    """When the LLM returns a Final Answer immediately, we get TEXT chunks + DONE."""
    llm_response = "Thought: I know the answer.\nFinal Answer: The capital of France is Paris."
    vertex_mock = _make_vertex_mock([llm_response])
    registry = ToolRegistry.with_defaults()
    runtime = AgentRuntime(vertex_service=vertex_mock, registry=registry)

    events = await _collect_events(runtime, "What is the capital of France?")

    event_types = [e.type for e in events]
    assert AgentEventType.REASONING in event_types
    assert AgentEventType.TEXT in event_types
    assert AgentEventType.DONE in event_types

    # Collect all text chunks
    full_text = "".join(e.content or "" for e in events if e.type == AgentEventType.TEXT)
    assert "Paris" in full_text

    # DONE must be the last event
    assert events[-1].type == AgentEventType.DONE


@pytest.mark.asyncio
async def test_tool_call_then_final_answer(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Simulate: LLM calls read_file → gets observation → produces Final Answer.
    Verifies the full REASONING → TOOL_CALL → TOOL_RESULT → TEXT → DONE sequence.
    """
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "answer.txt").write_text("42\n")

    tool_call_response = (
        "Thought: I need to read the file to find the answer.\n"
        "Action: read_file\n"
        'Action Input: {"path": "answer.txt"}'
    )
    final_answer_response = (
        "Thought: The file contains the answer.\n" "Final Answer: The answer is 42."
    )

    vertex_mock = _make_vertex_mock([tool_call_response, final_answer_response])
    registry = ToolRegistry.with_defaults()
    runtime = AgentRuntime(vertex_service=vertex_mock, registry=registry)

    events = await _collect_events(runtime, "What is in answer.txt?")
    event_types = [e.type for e in events]

    assert AgentEventType.REASONING in event_types
    assert AgentEventType.TOOL_CALL in event_types
    assert AgentEventType.TOOL_RESULT in event_types
    assert AgentEventType.TEXT in event_types
    assert AgentEventType.DONE in event_types

    # Verify tool call metadata
    tool_call_event = next(e for e in events if e.type == AgentEventType.TOOL_CALL)
    assert tool_call_event.metadata["tool_name"] == "read_file"

    # Verify tool result contains file content
    tool_result_event = next(e for e in events if e.type == AgentEventType.TOOL_RESULT)
    assert "42" in (tool_result_event.content or "")

    # Verify final answer
    full_text = "".join(e.content or "" for e in events if e.type == AgentEventType.TEXT)
    assert "42" in full_text

    # DONE carries run metadata
    done_event = events[-1]
    assert done_event.type == AgentEventType.DONE
    assert done_event.metadata.get("steps", 0) >= 1


@pytest.mark.asyncio
async def test_step_limit_forces_final_answer() -> None:
    """
    When the agent keeps calling tools and hits max_steps,
    it must produce a DONE event (not loop forever).
    """
    # Always return a tool call — never a final answer
    tool_call_response = (
        "Thought: I need more information.\n"
        "Action: list_directory\n"
        'Action Input: {"path": "."}'
    )
    # After step limit injection, return a final answer
    forced_final = "Thought: I must answer now.\nFinal Answer: I have reached my step limit."

    # First N calls return tool_call, last returns final answer
    vertex_mock = _make_vertex_mock([tool_call_response] * 3 + [forced_final])
    registry = ToolRegistry.with_defaults()
    runtime = AgentRuntime(vertex_service=vertex_mock, registry=registry, max_steps=3)

    events = await _collect_events(runtime, "Keep exploring forever.")
    event_types = [e.type for e in events]

    # Must terminate with DONE
    assert AgentEventType.DONE in event_types
    assert events[-1].type == AgentEventType.DONE

    # Should have made tool calls
    tool_call_events = [e for e in events if e.type == AgentEventType.TOOL_CALL]
    assert len(tool_call_events) >= 1


@pytest.mark.asyncio
async def test_failed_tool_still_continues(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A tool failure (file not found) should inject an error observation
    and allow the agent to continue to a final answer.
    """
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(tmp_path))

    tool_call_response = (
        "Thought: Let me read a file that doesn't exist.\n"
        "Action: read_file\n"
        'Action Input: {"path": "missing.txt"}'
    )
    final_after_error = (
        "Thought: The file was not found. I'll answer from what I know.\n"
        "Final Answer: The file does not exist."
    )

    vertex_mock = _make_vertex_mock([tool_call_response, final_after_error])
    registry = ToolRegistry.with_defaults()
    runtime = AgentRuntime(vertex_service=vertex_mock, registry=registry)

    events = await _collect_events(runtime, "Read missing.txt")
    event_types = [e.type for e in events]

    # Tool result should show failure
    tool_result_event = next(e for e in events if e.type == AgentEventType.TOOL_RESULT)
    assert tool_result_event.metadata.get("success") is False

    # But the run should still complete
    assert AgentEventType.DONE in event_types
    assert events[-1].type == AgentEventType.DONE


@pytest.mark.asyncio
async def test_done_event_contains_run_metadata() -> None:
    """DONE event must carry session_id, steps, and tool_calls count."""
    llm_response = "Thought: Simple.\nFinal Answer: Done."
    vertex_mock = _make_vertex_mock([llm_response])
    registry = ToolRegistry.with_defaults()
    runtime = AgentRuntime(vertex_service=vertex_mock, registry=registry)

    events = await _collect_events(runtime, "Simple question")
    done_event = events[-1]

    assert done_event.type == AgentEventType.DONE
    assert "session_id" in done_event.metadata
    assert "steps" in done_event.metadata
    assert "tool_calls" in done_event.metadata
