"""
Agent tracer — Langfuse integration for agent run observability.

Traces:
- Agent runs (one trace per user message)
- LLM calls (one span per complete() call)
- Tool executions (one span per tool call)
- Memory operations (one span per retrieval)

Design:
- AgentTracer wraps Langfuse SDK behind a clean interface
- NoOpTracer is a drop-in replacement when Langfuse is not configured
- The runtime accepts either via duck typing
- All spans include correlation_id for cross-system tracing

Langfuse concepts:
- Trace: one complete agent run (user message → final answer)
- Span: a sub-operation within a trace (LLM call, tool call, etc.)
- Generation: specifically an LLM call (tracked for token usage)

Usage:
    tracer = AgentTracer.from_settings(settings)
    with tracer.trace_run(session_id, run_id, user_message) as trace:
        with trace.span_llm_call(model, input_tokens) as span:
            ...
        with trace.span_tool_call(tool_name, arguments) as span:
            ...
"""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ── No-op tracer (used when Langfuse is not configured) ───────────────────────


class NoOpSpan:
    """A span that does nothing — used when tracing is disabled."""

    def end(self, output: Any = None, error: str | None = None) -> None:
        pass

    def __enter__(self) -> NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class NoOpTrace:
    """A trace that does nothing."""

    def span_llm_call(self, model: str, prompt_tokens: int = 0) -> NoOpSpan:
        return NoOpSpan()

    def span_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> NoOpSpan:
        return NoOpSpan()

    def span_memory_retrieval(self, session_id: str) -> NoOpSpan:
        return NoOpSpan()

    def end(self, output: str | None = None) -> None:
        pass

    def __enter__(self) -> NoOpTrace:
        return self

    def __exit__(self, *args: Any) -> None:
        self.end()


class NoOpTracer:
    """Drop-in tracer when Langfuse is not configured."""

    @contextmanager
    def trace_run(
        self, session_id: str, run_id: str, user_message: str
    ) -> Generator[NoOpTrace, None, None]:
        yield NoOpTrace()

    @property
    def is_enabled(self) -> bool:
        return False


# ── Langfuse tracer ───────────────────────────────────────────────────────────


class LangfuseSpan:
    """Wraps a Langfuse span/generation with a clean interface."""

    def __init__(self, span: Any) -> None:
        self._span = span
        self._start = time.perf_counter()

    def end(self, output: Any = None, error: str | None = None) -> None:
        round((time.perf_counter() - self._start) * 1000, 2)
        try:
            kwargs: dict[str, Any] = {"end_time": None}
            if output is not None:
                kwargs["output"] = str(output)[:2000]  # Truncate large outputs
            if error:
                kwargs["level"] = "ERROR"
                kwargs["status_message"] = error
            self._span.end(**{k: v for k, v in kwargs.items() if v is not None})
        except Exception as exc:
            logger.warning("langfuse_span_end_failed", error=str(exc))

    def __enter__(self) -> LangfuseSpan:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        error = str(exc_val) if exc_val else None
        self.end(error=error)


class LangfuseTrace:
    """Wraps a Langfuse trace with span creation methods."""

    def __init__(self, trace: Any, client: Any) -> None:
        self._trace = trace
        self._client = client

    def span_llm_call(self, model: str, prompt_tokens: int = 0) -> LangfuseSpan:
        """Create a generation span for an LLM call."""
        try:
            generation = self._trace.generation(
                name="llm_call",
                model=model,
                usage={"input": prompt_tokens} if prompt_tokens else None,
            )
            return LangfuseSpan(generation)
        except Exception as exc:
            logger.warning("langfuse_generation_failed", error=str(exc))
            return LangfuseSpan(NoOpSpan())

    def span_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> LangfuseSpan:
        """Create a span for a tool execution."""
        try:
            span = self._trace.span(
                name=f"tool:{tool_name}",
                input=arguments,
            )
            return LangfuseSpan(span)
        except Exception as exc:
            logger.warning("langfuse_span_failed", error=str(exc))
            return LangfuseSpan(NoOpSpan())

    def span_memory_retrieval(self, session_id: str) -> LangfuseSpan:
        """Create a span for a memory retrieval operation."""
        try:
            span = self._trace.span(name="memory_retrieval", input={"session_id": session_id})
            return LangfuseSpan(span)
        except Exception as exc:
            logger.warning("langfuse_span_failed", error=str(exc))
            return LangfuseSpan(NoOpSpan())

    def end(self, output: str | None = None) -> None:
        try:
            if output:
                self._trace.update(output=output[:2000])
            self._client.flush()
        except Exception as exc:
            logger.warning("langfuse_trace_end_failed", error=str(exc))

    def __enter__(self) -> LangfuseTrace:
        return self

    def __exit__(self, *args: Any) -> None:
        self.end()


class AgentTracer:
    """
    Langfuse-backed tracer for agent runs.

    Usage:
        tracer = AgentTracer(public_key="...", secret_key="...", host="...")
        with tracer.trace_run(session_id, run_id, message) as trace:
            with trace.span_tool_call("read_file", {...}) as span:
                result = await tool.execute(...)
                span.end(output=result)
    """

    def __init__(self, public_key: str, secret_key: str, host: str) -> None:
        self._public_key = public_key
        self._secret_key = secret_key
        self._host = host
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-initialize the Langfuse client."""
        if self._client is None:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=self._public_key,
                secret_key=self._secret_key,
                host=self._host,
            )
        return self._client

    @contextmanager
    def trace_run(
        self, session_id: str, run_id: str, user_message: str
    ) -> Generator[LangfuseTrace, None, None]:
        """Create a trace for a complete agent run."""
        try:
            client = self._get_client()

            import structlog

            context_vars = structlog.contextvars.get_contextvars()
            correlation_id = context_vars.get("correlation_id", "")
            trace_id = context_vars.get("trace_id", "")

            metadata = {"run_id": run_id}
            tags = []
            if correlation_id:
                metadata["correlation_id"] = correlation_id
                tags.append(f"correlation_id:{correlation_id}")
            if trace_id:
                metadata["otel_trace_id"] = trace_id
                tags.append(f"otel_trace_id:{trace_id}")

            trace = client.trace(
                name="agent_run",
                session_id=session_id,
                id=run_id,
                input=user_message[:1000],
                metadata=metadata,
                tags=tags if tags else None,
            )
            langfuse_trace = LangfuseTrace(trace, client)
            yield langfuse_trace
            langfuse_trace.end()
        except Exception as exc:
            logger.warning("langfuse_trace_failed", error=str(exc))
            yield NoOpTrace()  # type: ignore[misc]

    @property
    def is_enabled(self) -> bool:
        return True

    @classmethod
    def from_settings(cls, settings: Any) -> AgentTracer | NoOpTracer:
        """
        Create an AgentTracer from app settings, or NoOpTracer if not configured.

        Usage:
            tracer = AgentTracer.from_settings(get_settings())
        """
        if settings.langfuse_public_key and settings.langfuse_secret_key:
            return cls(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
        logger.info("langfuse_not_configured", message="Using no-op tracer")
        return NoOpTracer()
