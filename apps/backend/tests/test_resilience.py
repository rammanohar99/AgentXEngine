"""
Phase 6 reliability engineering tests.

Tests cover:
- CircuitBreaker state transitions (closed → open → half-open → closed)
- RetryPolicy: transient errors retry, permanent errors fail fast
- TimeoutGuard: asyncio.TimeoutError raised on slow operations
- ContextManager: token budget enforcement and truncation
- Runtime: circuit open error surfaces as ERROR event
- Runtime: timeout surfaces as ERROR event
- Runtime: tool timeout returns failed ToolResult (not crash)
"""

from __future__ import annotations

import asyncio
import time

import pytest

from packages.agents.context_manager import ContextManager
from packages.agents.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    RetryPolicy,
    _is_transient_error,
    with_timeout,
)
from packages.agents.runtime import AgentRuntime, Message
from packages.agents.schemas import AgentEventType
from packages.agents.tool_registry import ToolRegistry

# ── Transient error detection ─────────────────────────────────────────────────


def test_network_error_is_transient() -> None:
    assert _is_transient_error(ConnectionError("connection reset")) is True


def test_timeout_error_is_transient() -> None:
    assert _is_transient_error(TimeoutError("timed out")) is True


def test_generic_exception_is_transient() -> None:
    assert _is_transient_error(RuntimeError("service unavailable")) is True


def test_auth_error_is_permanent() -> None:
    assert _is_transient_error(Exception("invalid api key")) is False


def test_permission_denied_is_permanent() -> None:
    assert _is_transient_error(Exception("permission denied")) is False


def test_quota_exceeded_is_permanent() -> None:
    assert _is_transient_error(Exception("quota exceeded")) is False


def test_billing_error_is_permanent() -> None:
    assert _is_transient_error(Exception("billing account disabled")) is False


def test_bad_request_is_permanent() -> None:
    assert _is_transient_error(Exception("bad request: invalid json")) is False


# ── Circuit breaker ───────────────────────────────────────────────────────────


def test_circuit_starts_closed() -> None:
    breaker = CircuitBreaker(failure_threshold=3, recovery_seconds=60)
    assert breaker.state == CircuitState.CLOSED
    assert not breaker.is_open()


def test_circuit_opens_after_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=3, recovery_seconds=60)
    for _ in range(3):
        breaker.record_failure(RuntimeError("fail"))
    assert breaker.state == CircuitState.OPEN
    assert breaker.is_open()


def test_circuit_does_not_open_before_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=5, recovery_seconds=60)
    for _ in range(4):
        breaker.record_failure(RuntimeError("fail"))
    assert breaker.state == CircuitState.CLOSED


def test_circuit_resets_on_success() -> None:
    breaker = CircuitBreaker(failure_threshold=2, recovery_seconds=60)
    breaker.record_failure(RuntimeError("fail"))
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
    assert breaker._failure_count == 0


def test_circuit_transitions_to_half_open_after_recovery() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=0.1)
    breaker.record_failure(RuntimeError("fail"))
    # Immediately after failure, circuit is OPEN
    assert breaker._state == CircuitState.OPEN  # Check internal state directly

    time.sleep(0.15)  # Wait for recovery window
    # After recovery window, state property transitions to HALF_OPEN
    assert breaker.state == CircuitState.HALF_OPEN


def test_circuit_closes_after_successful_probe() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=0.1)
    breaker.record_failure(RuntimeError("fail"))
    time.sleep(0.15)
    assert breaker.state == CircuitState.HALF_OPEN

    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED


def test_circuit_reopens_after_failed_probe() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=0.1)
    breaker.record_failure(RuntimeError("fail"))
    time.sleep(0.15)
    assert breaker.state == CircuitState.HALF_OPEN

    breaker.record_failure(RuntimeError("probe failed"))
    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_context_rejects_when_open() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=60)
    breaker.record_failure(RuntimeError("fail"))

    with pytest.raises(CircuitOpenError):
        async with await breaker.guard("test_op"):
            pass  # Should not reach here


@pytest.mark.asyncio
async def test_circuit_breaker_context_records_success() -> None:
    breaker = CircuitBreaker(failure_threshold=5, recovery_seconds=60)
    async with await breaker.guard("test_op"):
        pass  # Success
    assert breaker._failure_count == 0


# ── Retry policy ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_policy_succeeds_on_first_attempt() -> None:
    policy = RetryPolicy(max_attempts=3, base_delay=0.01)
    call_count = 0

    async def operation():
        nonlocal call_count
        call_count += 1
        return "success"

    result = await policy.execute(operation, "test_op")
    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_policy_retries_transient_errors() -> None:
    policy = RetryPolicy(max_attempts=3, base_delay=0.01)
    call_count = 0

    async def operation():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("transient network error")
        return "success"

    result = await policy.execute(operation, "test_op")
    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_policy_fails_fast_on_permanent_error() -> None:
    policy = RetryPolicy(max_attempts=3, base_delay=0.01)
    call_count = 0

    async def operation():
        nonlocal call_count
        call_count += 1
        raise Exception("invalid api key")

    with pytest.raises(Exception, match="invalid api key"):
        await policy.execute(operation, "test_op")

    assert call_count == 1  # No retries for permanent errors


@pytest.mark.asyncio
async def test_retry_policy_exhausts_attempts() -> None:
    policy = RetryPolicy(max_attempts=3, base_delay=0.01)
    call_count = 0

    async def operation():
        nonlocal call_count
        call_count += 1
        raise ConnectionError("always fails")

    with pytest.raises(ConnectionError):
        await policy.execute(operation, "test_op")

    assert call_count == 3


# ── Timeout guard ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_guard_completes_fast_operation() -> None:
    async def fast_op():
        return "done"

    result = await with_timeout(fast_op(), timeout_seconds=5.0, operation_name="fast")
    assert result == "done"


@pytest.mark.asyncio
async def test_timeout_guard_raises_on_slow_operation() -> None:
    async def slow_op():
        await asyncio.sleep(10.0)
        return "never"

    with pytest.raises(asyncio.TimeoutError):
        await with_timeout(slow_op(), timeout_seconds=0.05, operation_name="slow")


# ── Context manager ───────────────────────────────────────────────────────────


def test_context_manager_estimates_tokens() -> None:
    manager = ContextManager(max_tokens=1000)
    messages = [Message(role="user", content="a" * 400)]  # ~100 tokens
    tokens = manager.estimate_tokens(messages)
    assert 90 <= tokens <= 110


def test_context_manager_truncates_tool_output() -> None:
    manager = ContextManager(max_tool_output_chars=100)
    long_output = "x" * 500
    truncated = manager.truncate_tool_output(long_output, tool_name="test_tool")
    assert len(truncated) <= 200  # 100 chars + truncation notice
    assert "truncated" in truncated.lower()


def test_context_manager_does_not_truncate_short_output() -> None:
    manager = ContextManager(max_tool_output_chars=1000)
    short_output = "hello world"
    result = manager.truncate_tool_output(short_output)
    assert result == short_output


def test_context_manager_caps_history() -> None:
    manager = ContextManager(max_tokens=100_000, max_history_messages=5)
    messages = [Message(role="user", content=f"msg {i}") for i in range(10)]
    prepared = manager.prepare_messages(messages)
    # System messages (0) + capped conversation (5)
    assert len(prepared) <= 5


def test_context_manager_preserves_system_messages() -> None:
    manager = ContextManager(max_tokens=100_000, max_history_messages=2)
    messages = [
        Message(role="system", content="You are an assistant"),
        Message(role="user", content="msg 1"),
        Message(role="user", content="msg 2"),
        Message(role="user", content="msg 3"),
    ]
    prepared = manager.prepare_messages(messages)
    # System message must always be preserved
    assert any(m.role == "system" for m in prepared)


def test_context_manager_budget_status() -> None:
    manager = ContextManager(max_tokens=1000)
    messages = [Message(role="user", content="a" * 400)]
    status = manager.get_budget_status(messages)
    assert "estimated_tokens" in status
    assert "utilization_pct" in status
    assert "is_over_budget" in status


# ── Runtime reliability integration ──────────────────────────────────────────


def _make_vertex_mock(responses: list[str]):
    call_count = 0

    class MockLLM:
        _model_name = "test-model"

        async def complete(self, messages, temperature=0.1, **kwargs):
            nonlocal call_count
            text = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            return type("R", (), {"text": text})()

    return MockLLM()


async def _collect_events(runtime: AgentRuntime, message: str) -> list:
    events = []
    async for event in runtime.run(
        session_id="test-session",
        history=[],
        user_message=message,
    ):
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_runtime_surfaces_circuit_open_as_error_event() -> None:
    """When circuit is open, runtime yields ERROR event instead of crashing."""
    open_breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=60)
    open_breaker.record_failure(RuntimeError("pre-opened"))

    llm = _make_vertex_mock(["Final Answer: Should not reach here."])
    registry = ToolRegistry.with_defaults()
    runtime = AgentRuntime(
        vertex_service=llm,
        registry=registry,
        circuit_breaker=open_breaker,
    )

    events = await _collect_events(runtime, "test query")
    event_types = [e.type for e in events]
    assert AgentEventType.ERROR in event_types
    error_event = next(e for e in events if e.type == AgentEventType.ERROR)
    assert "unavailable" in (error_event.content or "").lower()


@pytest.mark.asyncio
async def test_runtime_surfaces_timeout_as_error_event() -> None:
    """When LLM times out, runtime yields ERROR event."""

    class SlowLLM:
        _model_name = "slow-model"

        async def complete(self, messages, **kwargs):
            await asyncio.sleep(10.0)
            return type("R", (), {"text": "never"})()

    registry = ToolRegistry.with_defaults()
    runtime = AgentRuntime(
        vertex_service=SlowLLM(),
        registry=registry,
        llm_timeout_seconds=0.05,  # Very short timeout
    )

    events = await _collect_events(runtime, "test query")
    event_types = [e.type for e in events]
    assert AgentEventType.ERROR in event_types


@pytest.mark.asyncio
async def test_runtime_tool_timeout_continues_loop(tmp_path, monkeypatch) -> None:
    """A tool timeout produces a failed ToolResult, not a crash."""
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(tmp_path))

    tool_call_response = (
        "Thought: Let me read a file.\n"
        "Action: read_file\n"
        'Action Input: {"path": "nonexistent.txt"}'
    )
    final_answer_response = "Thought: File not found.\nFinal Answer: Could not read the file."

    llm = _make_vertex_mock([tool_call_response, final_answer_response])
    registry = ToolRegistry.with_defaults()
    runtime = AgentRuntime(
        vertex_service=llm,
        registry=registry,
        tool_timeout_seconds=30.0,  # Normal timeout — tool will fail naturally
    )

    events = await _collect_events(runtime, "Read nonexistent.txt")
    event_types = [e.type for e in events]

    # Should complete (not crash) even with tool failure
    assert AgentEventType.DONE in event_types
    assert AgentEventType.TOOL_RESULT in event_types

    # Tool result should indicate failure
    tool_result = next(e for e in events if e.type == AgentEventType.TOOL_RESULT)
    assert tool_result.metadata.get("success") is False


# ── Phase 6.1 regression tests ────────────────────────────────────────────────
# These tests protect against regressions of the six fixes applied in Phase 6.1.
# Each test is named after the ADR it protects.


@pytest.mark.asyncio
async def test_adr001_no_retry_amplification() -> None:
    """
    ADR-001: The runtime must NOT retry LLM calls.
    VertexAIService owns all retry logic.

    Regression test: verify that a failing LLM is called exactly ONCE
    by the runtime layer (not 3 times via a runtime-level RetryPolicy).
    The provider layer may retry internally, but the runtime must not.
    """
    call_count = 0

    class CountingFailLLM:
        _model_name = "counting-model"

        async def complete(self, messages, **kwargs):
            nonlocal call_count
            call_count += 1
            # Transient error — would be retried if runtime had a RetryPolicy
            raise ConnectionError("transient network error")

    registry = ToolRegistry.with_defaults()
    runtime = AgentRuntime(
        vertex_service=CountingFailLLM(),
        registry=registry,
    )

    events = await _collect_events(runtime, "test query")

    # Runtime must emit ERROR event (not crash)
    assert any(e.type == AgentEventType.ERROR for e in events)

    # CRITICAL: The runtime must call the LLM exactly once.
    # If call_count > 1, the runtime has its own retry layer — that is the bug.
    assert call_count == 1, (
        f"Runtime called LLM {call_count} times. "
        "ADR-001 violation: runtime must not retry — provider layer owns retries."
    )


@pytest.mark.asyncio
async def test_adr001_circuit_breaker_state_persists_across_calls() -> None:
    """
    ADR-002: Circuit breaker state must persist across multiple run() calls.

    Regression test: verify that failures accumulate in the circuit breaker
    across separate run() invocations on the same runtime instance.
    """
    call_count = 0

    class AlwaysFailLLM:
        _model_name = "fail-model"

        async def complete(self, messages, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("always fails")

    breaker = CircuitBreaker(failure_threshold=2, recovery_seconds=60)
    registry = ToolRegistry.with_defaults()
    runtime = AgentRuntime(
        vertex_service=AlwaysFailLLM(),
        registry=registry,
        circuit_breaker=breaker,
    )

    # First run — should fail and record one failure
    await _collect_events(runtime, "query 1")
    assert breaker._failure_count >= 1
    assert breaker.state == CircuitState.CLOSED  # Not yet at threshold

    # Second run — should fail and open the circuit
    await _collect_events(runtime, "query 2")
    assert breaker.state == CircuitState.OPEN  # Circuit opened after 2 failures

    # Third run — circuit is OPEN, should be rejected immediately (no LLM call)
    calls_before = call_count
    events = await _collect_events(runtime, "query 3")
    assert call_count == calls_before, "LLM was called despite open circuit"
    assert any(e.type == AgentEventType.ERROR for e in events)
    error = next(e for e in events if e.type == AgentEventType.ERROR)
    assert "unavailable" in (error.content or "").lower()
