"""
Orchestrator and multi-agent tests.

LLM is mocked — tests verify delegation routing, specialist selection,
and workflow execution without real API calls.
"""

from __future__ import annotations

import pytest

from packages.agents.agent_types import AgentRole, get_agent_config
from packages.agents.orchestrator import Orchestrator
from packages.agents.runtime import Message
from packages.agents.schemas import AgentEventType
from packages.agents.tool_registry import ToolRegistry


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_vertex_mock(responses: list[str]):
    """Mock LLM that returns responses in sequence."""
    call_count = 0

    class MockLLM:
        async def complete(self, messages, temperature=0.1, **kwargs):
            nonlocal call_count
            text = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            response = type("R", (), {"text": text})()
            return response

    return MockLLM()


async def _collect_events(orchestrator: Orchestrator, message: str) -> list:
    events = []
    async for event in orchestrator.run(
        session_id="test-session",
        history=[],
        user_message=message,
    ):
        events.append(event)
    return events


# ── Agent type config tests ───────────────────────────────────────────────────


def test_all_agent_roles_have_configs() -> None:
    for role in AgentRole:
        config = get_agent_config(role)
        assert config.role == role
        assert config.name
        assert config.system_prompt
        assert config.max_steps > 0


def test_specialist_configs_have_allowed_tools() -> None:
    """Specialists (not orchestrator) should have restricted tool sets."""
    for role in [AgentRole.PLANNER, AgentRole.CODING, AgentRole.RETRIEVAL]:
        config = get_agent_config(role)
        assert len(config.allowed_tools) > 0


def test_orchestrator_config_has_no_tool_restriction() -> None:
    config = get_agent_config(AgentRole.ORCHESTRATOR)
    assert config.allowed_tools == []  # Empty = all tools allowed


# ── Orchestrator runtime tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_direct_answer() -> None:
    """Orchestrator answers directly without delegation."""
    llm = _make_vertex_mock(["Thought: I can answer this.\nFinal Answer: Python is great."])
    registry = ToolRegistry.with_defaults()
    orchestrator = Orchestrator(llm_provider=llm, base_registry=registry)

    events = await _collect_events(orchestrator, "What is Python?")
    event_types = [e.type for e in events]

    assert AgentEventType.TEXT in event_types
    assert AgentEventType.DONE in event_types

    full_text = "".join(e.content or "" for e in events if e.type == AgentEventType.TEXT)
    assert "Python" in full_text


@pytest.mark.asyncio
async def test_orchestrator_has_delegation_tool() -> None:
    """Orchestrator registry should include the delegate_to_agent tool."""
    llm = _make_vertex_mock(["Thought: Done.\nFinal Answer: OK."])
    registry = ToolRegistry.with_defaults()
    orchestrator = Orchestrator(llm_provider=llm, base_registry=registry)

    # Build the orchestrator registry and verify delegation tool is present
    orch_registry = orchestrator._build_orchestrator_registry()
    assert orch_registry.get("delegate_to_agent") is not None


@pytest.mark.asyncio
async def test_orchestrator_specialist_registry_is_filtered() -> None:
    """Specialist registries should only contain their allowed tools."""
    llm = _make_vertex_mock(["Final Answer: Done."])
    registry = ToolRegistry.with_defaults()
    orchestrator = Orchestrator(llm_provider=llm, base_registry=registry)

    # Retrieval agent only allows retrieve_documents and search_files
    config = get_agent_config(AgentRole.RETRIEVAL)
    specialist_registry = orchestrator._build_specialist_registry(config.allowed_tools)

    # Should have search_files (it's in base registry and allowed)
    assert specialist_registry.get("search_files") is not None
    # Should NOT have read_file (not in retrieval agent's allowed tools)
    assert specialist_registry.get("read_file") is None


@pytest.mark.asyncio
async def test_orchestrator_delegation_tool_call(tmp_path, monkeypatch) -> None:
    """
    When orchestrator calls delegate_to_agent, the specialist runs
    and its result is injected as an observation.
    """
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "info.txt").write_text("The answer is 42.\n")

    # First call: orchestrator decides to delegate
    # Second call: specialist (coding agent) answers
    # Third call: orchestrator synthesizes
    responses = [
        "Thought: I should delegate this to the coding agent.\nAction: delegate_to_agent\nAction Input: {\"agent\": \"coding\", \"task\": \"What is in info.txt?\"}",
        "Thought: Let me read the file.\nFinal Answer: The file contains: The answer is 42.",
        "Thought: I have the result.\nFinal Answer: According to the coding agent, the answer is 42.",
    ]

    llm = _make_vertex_mock(responses)
    registry = ToolRegistry.with_defaults()
    orchestrator = Orchestrator(llm_provider=llm, base_registry=registry)

    events = await _collect_events(orchestrator, "What is in info.txt?")
    event_types = [e.type for e in events]

    assert AgentEventType.TOOL_CALL in event_types
    assert AgentEventType.TOOL_RESULT in event_types
    assert AgentEventType.DONE in event_types

    # Verify delegation tool was called
    tool_call_events = [e for e in events if e.type == AgentEventType.TOOL_CALL]
    assert any(e.metadata.get("tool_name") == "delegate_to_agent" for e in tool_call_events)


# ── Workflow executor tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_workflow_executor_runs_tasks() -> None:
    """Workflow executor should run all tasks and collect results."""
    import uuid
    from packages.workflows.executor import WorkflowExecutor
    from packages.workflows.schemas import AgentTask, WorkflowRun, WorkflowStatus

    llm = _make_vertex_mock(["Final Answer: Task complete."] * 5)
    registry = ToolRegistry.with_defaults()
    orchestrator = Orchestrator(llm_provider=llm, base_registry=registry)
    executor = WorkflowExecutor(orchestrator=orchestrator)

    run = WorkflowRun(
        run_id=str(uuid.uuid4()),
        workflow_id="test-workflow",
        session_id="test-session",
        tasks=[
            AgentTask(
                task_id="task-1",
                agent_role="coding",
                instruction="Describe the project structure.",
            ),
            AgentTask(
                task_id="task-2",
                agent_role="planner",
                instruction="Plan the next steps.",
                depends_on=["task-1"],
            ),
        ],
    )

    result = await executor.execute(run)

    assert result.status == WorkflowStatus.COMPLETE
    assert result.final_output is not None
    assert all(t.status.value == "complete" for t in result.tasks)


@pytest.mark.asyncio
async def test_workflow_executor_handles_task_failure() -> None:
    """
    A failing LLM causes the runtime to emit an ERROR event.
    The workflow task completes with empty output (not a crash).
    The workflow itself completes — individual task errors are surfaced
    via the task result content, not by crashing the workflow.
    """
    import uuid
    from packages.workflows.executor import WorkflowExecutor
    from packages.workflows.schemas import AgentTask, WorkflowRun, WorkflowStatus

    class FailingLLM:
        _model_name = "failing-model"

        async def complete(self, messages, **kwargs):
            raise Exception("invalid api key")  # Permanent error — fails fast

    registry = ToolRegistry.with_defaults()
    orchestrator = Orchestrator(llm_provider=FailingLLM(), base_registry=registry)
    executor = WorkflowExecutor(orchestrator=orchestrator)

    run = WorkflowRun(
        run_id=str(uuid.uuid4()),
        workflow_id="test-workflow",
        session_id="test-session",
        tasks=[
            AgentTask(
                task_id="task-1",
                agent_role="coding",
                instruction="This will fail.",
            ),
        ],
    )

    result = await executor.execute(run)
    # With the reliability layer, the runtime catches errors and emits ERROR events
    # rather than raising. The workflow completes but the task result is empty/error.
    # This is the correct production behavior — workflows don't crash on LLM errors.
    assert result.status in (WorkflowStatus.COMPLETE, WorkflowStatus.FAILED)


# ── Phase 6.1 regression tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_adr002_orchestrator_runtime_is_long_lived() -> None:
    """
    ADR-002: Orchestrator must use a long-lived runtime (created in __init__).

    Regression test: verify that the same runtime instance is used across
    multiple run() calls. If a new runtime were created per call, the
    circuit breaker would reset to CLOSED on every request.
    """
    llm = _make_vertex_mock(["Final Answer: OK."] * 3)
    registry = ToolRegistry.with_defaults()
    orchestrator = Orchestrator(llm_provider=llm, base_registry=registry)

    # The orchestrator must have a pre-built runtime in __init__
    assert hasattr(orchestrator, "_orchestrator_runtime"), (
        "Orchestrator must have _orchestrator_runtime attribute. "
        "ADR-002: runtime must be created in __init__, not per request."
    )

    runtime_id_first = id(orchestrator._orchestrator_runtime)

    # Run twice — must use the same runtime instance
    await _collect_events(orchestrator, "first query")
    await _collect_events(orchestrator, "second query")

    runtime_id_second = id(orchestrator._orchestrator_runtime)
    assert runtime_id_first == runtime_id_second, (
        "Orchestrator created a new runtime between calls. "
        "ADR-002 violation: circuit breaker state would be lost."
    )


@pytest.mark.asyncio
async def test_adr004_workflow_task_marked_failed_on_error_event() -> None:
    """
    Phase 6.1 fix: Workflow tasks that produce ERROR events must be FAILED.

    Regression test: verify that when the runtime emits an ERROR event
    (e.g., circuit open, LLM failure), the task status is FAILED — not COMPLETE.
    """
    import uuid
    from packages.workflows.executor import WorkflowExecutor
    from packages.workflows.schemas import AgentTask, WorkflowRun, WorkflowStatus, TaskStatus

    class PermanentFailLLM:
        _model_name = "fail-model"

        async def complete(self, messages, **kwargs):
            raise Exception("invalid api key")  # Permanent — no retries

    registry = ToolRegistry.with_defaults()
    orchestrator = Orchestrator(llm_provider=PermanentFailLLM(), base_registry=registry)
    executor = WorkflowExecutor(orchestrator=orchestrator)

    run = WorkflowRun(
        run_id=str(uuid.uuid4()),
        workflow_id="test-workflow",
        session_id="test-session",
        tasks=[
            AgentTask(
                task_id="task-fail",
                agent_role="coding",
                instruction="This will produce an ERROR event.",
            ),
        ],
    )

    result = await executor.execute(run)

    # The task must be FAILED — not COMPLETE with empty output
    failed_task = next(t for t in result.tasks if t.task_id == "task-fail")
    assert failed_task.status == TaskStatus.FAILED, (
        f"Task status was {failed_task.status}, expected FAILED. "
        "Phase 6.1 regression: ERROR events must mark tasks as FAILED."
    )
    assert failed_task.error is not None
    assert result.status == WorkflowStatus.FAILED


@pytest.mark.asyncio
async def test_adr003_memory_summarization_failure_does_not_crash_run() -> None:
    """
    ADR-003: Memory summarization failure must not fail the agent run.

    Regression test: verify that when the summarizer raises an exception,
    the agent run continues and produces a response.
    """
    from packages.memory.manager import MemoryManager, _SUMMARIZE_THRESHOLD
    from packages.memory.short_term import ShortTermMemory
    from packages.memory.long_term import LongTermMemory

    class ExplodingSummarizer:
        """Summarizer that always raises — simulates LLM failure during summarization."""
        async def summarize(self, session_id, turns):
            raise RuntimeError("Summarization LLM call failed")

    class MockRedis:
        async def lrange(self, *a, **k): return []
        async def rpush(self, *a, **k): return 0
        async def expire(self, *a, **k): return 0
        async def llen(self, *a, **k): return 0
        async def ltrim(self, *a, **k): return 0
        async def delete(self, *a, **k): return 0
        async def get(self, *a, **k): return None
        async def set(self, *a, **k): return None

    short_term = ShortTermMemory(window_size=50)
    long_term = LongTermMemory(redis_client=MockRedis())
    manager = MemoryManager(
        short_term=short_term,
        long_term=long_term,
        summarizer=ExplodingSummarizer(),
        redis_client=MockRedis(),
    )

    session_id = "test-summarize-fail"

    # Add enough turns to trigger summarization threshold
    for i in range(_SUMMARIZE_THRESHOLD + 2):
        role = "user" if i % 2 == 0 else "assistant"
        # Must NOT raise — summarization failure must be caught and logged
        await manager.record_turn(session_id, role=role, content=f"Message {i}")

    # Context must still be retrievable after summarization failure
    context = await manager.get_context(session_id)
    # Short-term turns are still available (summarization was skipped, not crashed)
    assert len(context.short_term) > 0, (
        "Short-term memory was cleared despite summarization failure. "
        "ADR-003 regression: summarization failure must degrade gracefully."
    )
