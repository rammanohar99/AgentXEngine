"""
Agent Runtime — production-grade ReAct loop.

Phase 6 reliability additions:
- LLM calls wrapped with timeout + circuit breaker
- Tool execution wrapped with per-tool timeout
- Context manager enforces token budget before every LLM call
- Tool outputs truncated before injection into context
- All failures emit structured metrics
- Planner parse failures are observable (not silently swallowed)
- Step limit forces final answer with one additional LLM call

Phase 6.1 reliability fixes:
- REMOVED runtime-level retry policy (ADR-001: retry amplification fix)
  VertexAIService owns all retry logic. The runtime owns circuit breaker
  and timeout only. Having both layers retry independently caused up to
  9 API calls per logical LLM call under failure conditions.

Execution flow:
1. Build context (system prompt + history)
2. Apply context budget (truncate if over limit)
3. Check circuit breaker — reject if OPEN
4. Call LLM with timeout (VertexAIService handles retries internally)
5. Record circuit breaker success/failure
6. Planner parses → AgentDecision
7. If TOOL_CALL:
   a. Execute tool with timeout
   b. Truncate output to budget
   c. Inject observation
   d. Loop
8. If FINAL_ANSWER: stream text + DONE
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import structlog

from packages.agents.context_manager import ContextManager
from packages.agents.executor import Executor
from packages.agents.planner import Planner
from packages.agents.prompt_manager import PromptManager
from packages.agents.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    get_llm_circuit_breaker,
    with_timeout,
)
from packages.agents.schemas import (
    AgentDecision,
    AgentEvent,
    AgentEventType,
    DecisionType,
    RunState,
)
from packages.agents.tool_registry import ToolRegistry
from packages.observability.metrics import get_metrics

logger = structlog.get_logger(__name__)

# Default reliability settings — overridden by AgentRuntime constructor
_DEFAULT_LLM_TIMEOUT = 60.0
_DEFAULT_TOOL_TIMEOUT = 30.0
_DEFAULT_MAX_TOKENS = 100_000
_DEFAULT_MAX_TOOL_OUTPUT_CHARS = 8_000


@dataclass
class Message:
    """
    A single conversation message passed to the runtime.

    The AgentService converts Pydantic ChatMessage → Message at the boundary.
    This keeps the runtime fully decoupled from the web framework.
    """

    role: str  # "user" | "assistant" | "system"
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    """
    Minimal protocol the runtime requires from an LLM service.

    VertexAIService satisfies this protocol structurally.
    Tests can pass any object with a matching complete() method.
    """

    async def complete(self, messages: list[Any], temperature: float = 0.1, **kwargs: Any) -> Any:
        """Return an object with a .text attribute."""
        ...


class AgentRuntime:
    """
    Production-grade ReAct agent runtime.

    Stateless — holds no per-request state.
    All mutable state lives in RunState, created fresh per run() call.

    Reliability features:
    - LLM timeout: configurable per-call timeout
    - Circuit breaker: rejects requests when LLM is degraded
    - Retry policy: transient errors retry, permanent errors fail fast
    - Context budget: truncates context before LLM calls
    - Tool timeout: per-tool execution timeout
    - Metrics: all operations emit structured metrics
    """

    def __init__(
        self,
        vertex_service: LLMProvider,
        registry: ToolRegistry,
        max_steps: int = 10,
        llm_timeout_seconds: float = _DEFAULT_LLM_TIMEOUT,
        tool_timeout_seconds: float = _DEFAULT_TOOL_TIMEOUT,
        max_context_tokens: int = _DEFAULT_MAX_TOKENS,
        max_tool_output_chars: int = _DEFAULT_MAX_TOOL_OUTPUT_CHARS,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._llm = vertex_service
        self._registry = registry
        self._planner = Planner(registry)
        self._executor = Executor(registry)
        self._prompt_manager = PromptManager(registry)
        self._max_steps = max_steps
        self._llm_timeout = llm_timeout_seconds
        self._tool_timeout = tool_timeout_seconds
        self._context_manager = ContextManager(
            max_tokens=max_context_tokens,
            max_tool_output_chars=max_tool_output_chars,
        )
        self._circuit_breaker = circuit_breaker or get_llm_circuit_breaker()
        # NOTE: No RetryPolicy here — VertexAIService owns all retry logic.
        # ADR-001: Only one layer may own retries for a given operation.
        # Adding a retry layer here would cause retry amplification:
        # runtime retries × provider retries = multiplicative API call storms.
        self._metrics = get_metrics()

    async def run(
        self,
        session_id: str,
        history: list[Message],
        user_message: str,
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Execute the ReAct loop for a single user message.
        Yields AgentEvent objects as the run progresses.
        """
        run_id = str(uuid.uuid4())
        run_start = time.perf_counter()
        state = RunState(
            session_id=session_id,
            run_id=run_id,
            user_message=user_message,
            max_steps=self._max_steps,
        )

        logger.info(
            "agent_run_start",
            session_id=session_id,
            run_id=run_id,
            message_length=len(user_message),
        )

        system_prompt = self._prompt_manager.build_system_prompt()
        working_messages: list[Message] = [
            Message(role="system", content=system_prompt),
            *history,
        ]

        # Check circuit breaker before starting the loop
        # (avoids the async generator exception propagation complexity)
        if self._circuit_breaker.is_open():
            self._metrics.record_circuit_breaker_event(
                breaker_name=self._circuit_breaker._name,
                event="rejected",
            )
            yield AgentEvent(
                type=AgentEventType.ERROR,
                content="The AI service is temporarily unavailable. Please try again in a moment.",
                metadata={"run_id": run_id, "error_type": "circuit_open"},
            )
            return

        run_success = True
        run_error_type: str | None = None

        try:
            async for event in self._react_loop(state, working_messages):
                yield event
        except CircuitOpenError as exc:
            run_success = False
            run_error_type = "circuit_open"
            logger.error("agent_run_circuit_open", run_id=run_id, error=str(exc))
            yield AgentEvent(
                type=AgentEventType.ERROR,
                content="The AI service is temporarily unavailable. Please try again in a moment.",
                metadata={"run_id": run_id, "error_type": "circuit_open"},
            )
        except asyncio.TimeoutError as exc:
            run_success = False
            run_error_type = "timeout"
            logger.error("agent_run_timeout", run_id=run_id, error=str(exc))
            yield AgentEvent(
                type=AgentEventType.ERROR,
                content="The request timed out. Please try a simpler query.",
                metadata={"run_id": run_id, "error_type": "timeout"},
            )
        except Exception as exc:
            run_success = False
            run_error_type = type(exc).__name__
            logger.error("agent_run_error", run_id=run_id, error=str(exc), error_type=run_error_type)
            yield AgentEvent(
                type=AgentEventType.ERROR,
                content=f"An unexpected error occurred: {exc}",
                metadata={"run_id": run_id, "error_type": run_error_type},
            )
        finally:
            latency_ms = round((time.perf_counter() - run_start) * 1000, 2)
            self._metrics.record_agent_run(
                session_id=session_id,
                run_id=run_id,
                latency_ms=latency_ms,
                steps_taken=state.step,
                tool_calls=len(state.tool_calls_made),
                success=run_success,
                error_type=run_error_type,
            )
            logger.info(
                "agent_run_complete",
                session_id=session_id,
                run_id=run_id,
                steps=state.step,
                tool_calls=len(state.tool_calls_made),
                latency_ms=latency_ms,
                success=run_success,
            )

    async def _react_loop(
        self,
        state: RunState,
        working_messages: list[Message],
    ) -> AsyncGenerator[AgentEvent, None]:
        """Core ReAct loop — runs until final answer, step limit, or error."""
        while not state.is_complete:
            state.increment_step()

            if state.is_at_limit():
                limit_msg = self._prompt_manager.format_step_limit_message(state.max_steps)
                working_messages.append(Message(role="user", content=limit_msg))

            # Apply context budget before every LLM call
            prepared_messages = self._context_manager.prepare_messages(
                working_messages, correlation_id=state.run_id
            )

            llm_response_text = await self._call_llm_with_resilience(
                prepared_messages, state.run_id
            )
            decision = self._planner.parse(llm_response_text)

            # Log parse result — distinguishes "answered" from "parse fallback"
            logger.info(
                "agent_decision",
                run_id=state.run_id,
                step=state.step,
                decision_type=decision.decision_type,
                tool_name=decision.tool_call.tool_name if decision.tool_call else None,
                has_reasoning=bool(decision.reasoning),
            )

            if decision.decision_type == DecisionType.TOOL_CALL:
                async for event in self._handle_tool_call(state, decision, working_messages):
                    yield event
            else:
                async for event in self._handle_final_answer(state, decision):
                    yield event

    async def _call_llm_with_resilience(
        self, messages: list[Message], run_id: str
    ) -> str:
        """
        Call the LLM with timeout and circuit breaker protection.

        ADR-001 — Retry Ownership:
        This method does NOT retry. VertexAIService owns all retry logic.
        Adding retries here would create retry amplification:
          runtime (3 attempts) × provider (3 attempts) = 9 API calls per step.

        This method owns:
        - Circuit breaker check (reject if OPEN)
        - Timeout enforcement (asyncio.wait_for)
        - Circuit breaker state update (record success/failure)
        - Metrics emission

        Raises CircuitOpenError if circuit is open.
        Raises asyncio.TimeoutError if call exceeds timeout.
        Raises provider exception if the call fails after provider retries.
        """
        if self._circuit_breaker.is_open():
            self._metrics.record_circuit_breaker_event(
                breaker_name=self._circuit_breaker._name,
                event="rejected",
            )
            raise CircuitOpenError(
                f"Circuit breaker '{self._circuit_breaker._name}' is OPEN."
            )

        call_start = time.perf_counter()

        try:
            # with_timeout wraps the provider call — provider handles retries internally
            response = await with_timeout(
                self._llm.complete(messages=messages, temperature=0.1),
                timeout_seconds=self._llm_timeout,
                operation_name="llm_complete",
                correlation_id=run_id,
            )
            result = str(response.text)

            self._circuit_breaker.record_success()
            latency_ms = round((time.perf_counter() - call_start) * 1000, 2)
            self._metrics.record_llm_call(
                model=getattr(self._llm, "_model_name", "unknown"),
                latency_ms=latency_ms,
                success=True,
                correlation_id=run_id,
            )
            return result

        except Exception as exc:
            self._circuit_breaker.record_failure(exc)
            latency_ms = round((time.perf_counter() - call_start) * 1000, 2)
            self._metrics.record_llm_call(
                model=getattr(self._llm, "_model_name", "unknown"),
                latency_ms=latency_ms,
                success=False,
                error_type=type(exc).__name__,
                correlation_id=run_id,
            )
            raise

    async def _handle_tool_call(
        self,
        state: RunState,
        decision: AgentDecision,
        working_messages: list[Message],
    ) -> AsyncGenerator[AgentEvent, None]:
        """Execute a tool call with timeout, emit events, inject observation."""
        tool_call = decision.tool_call
        assert tool_call is not None

        if decision.reasoning:
            yield AgentEvent(
                type=AgentEventType.REASONING,
                content=decision.reasoning,
                metadata={"step": state.step, "run_id": state.run_id},
            )

        yield AgentEvent(
            type=AgentEventType.TOOL_CALL,
            content=f"Calling {tool_call.tool_name}",
            metadata={
                "tool_name": tool_call.tool_name,
                "arguments": tool_call.arguments,
                "call_id": tool_call.call_id,
                "step": state.step,
            },
        )

        # Execute with timeout
        tool_start = time.perf_counter()
        try:
            result = await with_timeout(
                self._executor.execute(tool_call),
                timeout_seconds=self._tool_timeout,
                operation_name=f"tool_{tool_call.tool_name}",
                correlation_id=state.run_id,
            )
        except asyncio.TimeoutError:
            from packages.agents.schemas import ToolResult
            result = ToolResult(
                tool_name=tool_call.tool_name,
                call_id=tool_call.call_id,
                success=False,
                output=None,
                error=f"Tool '{tool_call.tool_name}' timed out after {self._tool_timeout}s",
                duration_ms=self._tool_timeout * 1000,
            )

        tool_latency_ms = round((time.perf_counter() - tool_start) * 1000, 2)
        self._metrics.record_tool_execution(
            tool_name=tool_call.tool_name,
            latency_ms=tool_latency_ms,
            success=result.success,
            error_type="timeout" if not result.success and "timed out" in (result.error or "") else None,
            output_chars=len(str(result.output or "")),
            correlation_id=state.run_id,
        )

        state.tool_calls_made.append(tool_call)

        # Truncate tool output before injecting into context
        observation = result.to_observation()
        truncated_observation = self._context_manager.truncate_tool_output(
            observation, tool_name=tool_call.tool_name
        )

        yield AgentEvent(
            type=AgentEventType.TOOL_RESULT,
            content=truncated_observation,
            metadata={
                "tool_name": result.tool_name,
                "call_id": result.call_id,
                "success": result.success,
                "duration_ms": result.duration_ms,
                "step": state.step,
                "truncated": len(observation) != len(truncated_observation),
            },
        )

        observation_text = (
            f"Thought: {decision.reasoning}\n"
            f"Action: {tool_call.tool_name}\n"
            f"Action Input: {tool_call.arguments}\n"
            f"Observation: {truncated_observation}"
        )
        working_messages.append(Message(role="assistant", content=observation_text))
        state.observations.append(truncated_observation)

    async def _handle_final_answer(
        self,
        state: RunState,
        decision: AgentDecision,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Stream the final answer and mark the run complete."""
        if decision.reasoning:
            yield AgentEvent(
                type=AgentEventType.REASONING,
                content=decision.reasoning,
                metadata={"step": state.step, "run_id": state.run_id},
            )

        final_text = decision.final_answer or ""
        state.final_answer = final_text
        state.is_complete = True

        chunk_size = 50
        for start_idx in range(0, len(final_text), chunk_size):
            yield AgentEvent(
                type=AgentEventType.TEXT,
                content=final_text[start_idx : start_idx + chunk_size],
                metadata={"run_id": state.run_id},
            )

        yield AgentEvent(
            type=AgentEventType.DONE,
            metadata={
                "run_id": state.run_id,
                "session_id": state.session_id,
                "steps": state.step,
                "tool_calls": len(state.tool_calls_made),
            },
        )
