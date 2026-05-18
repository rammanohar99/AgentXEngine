"""
Structured metrics for the agent runtime.

AGENTS.md observability requirements:
- request tracing ✅ (Langfuse)
- agent step tracing ✅ (Langfuse)
- tool execution tracing ✅ (Langfuse)
- token usage tracking — this module
- latency tracking — this module
- error rate tracking — this module

Design:
- All metrics are emitted as structured log events
- Each metric event has a consistent schema
- Metrics can be consumed by log aggregators (Datadog, CloudWatch, etc.)
- No external metrics library dependency (avoids framework lock-in)
- Prometheus-compatible format available via /metrics endpoint (future)

Metric categories:
- agent_run: latency, steps, tool calls, token usage, success/failure
- llm_call: latency, tokens, model, retry count
- tool_execution: latency, success/failure, tool name
- memory_operation: latency, type, success/failure
- rag_retrieval: latency, result count, avg score
- circuit_breaker: state transitions, rejection count

Usage:
    from packages.observability.metrics import MetricsCollector
    metrics = MetricsCollector()
    metrics.record_agent_run(session_id, run_id, latency_ms=450, steps=3, ...)
"""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class MetricsCollector:
    """
    Emits structured metric events as log entries.

    All metric events use the prefix "metric." in the event name
    so they can be filtered and aggregated separately from operational logs.

    In production, configure your log aggregator to:
    - Parse metric.* events into a metrics store
    - Alert on error_rate > threshold
    - Dashboard latency percentiles
    - Track token usage for cost management
    """

    def record_agent_run(
        self,
        session_id: str,
        run_id: str,
        latency_ms: float,
        steps_taken: int,
        tool_calls: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        success: bool = True,
        error_type: str | None = None,
        context_tokens: int = 0,
    ) -> None:
        """Record metrics for a complete agent run."""
        logger.info(
            "metric.agent_run",
            session_id=session_id,
            run_id=run_id,
            latency_ms=round(latency_ms, 2),
            steps_taken=steps_taken,
            tool_calls=tool_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            context_tokens=context_tokens,
            success=success,
            error_type=error_type,
        )

    def record_llm_call(
        self,
        model: str,
        latency_ms: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
        retry_count: int = 0,
        success: bool = True,
        error_type: str | None = None,
        correlation_id: str = "",
    ) -> None:
        """Record metrics for a single LLM API call."""
        logger.info(
            "metric.llm_call",
            model=model,
            latency_ms=round(latency_ms, 2),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            retry_count=retry_count,
            success=success,
            error_type=error_type,
            correlation_id=correlation_id,
        )

    def record_tool_execution(
        self,
        tool_name: str,
        latency_ms: float,
        success: bool,
        error_type: str | None = None,
        output_chars: int = 0,
        correlation_id: str = "",
    ) -> None:
        """Record metrics for a tool execution."""
        logger.info(
            "metric.tool_execution",
            tool_name=tool_name,
            latency_ms=round(latency_ms, 2),
            success=success,
            error_type=error_type,
            output_chars=output_chars,
            correlation_id=correlation_id,
        )

    def record_circuit_breaker_event(
        self,
        breaker_name: str,
        event: str,  # "opened" | "closed" | "rejected" | "half_open"
        failure_count: int = 0,
    ) -> None:
        """Record a circuit breaker state transition."""
        logger.warning(
            "metric.circuit_breaker",
            breaker_name=breaker_name,
            cb_event=event,  # renamed: 'event' is reserved by structlog
            failure_count=failure_count,
        )

    def record_context_budget(
        self,
        estimated_tokens: int,
        max_tokens: int,
        truncated: bool,
        correlation_id: str = "",
    ) -> None:
        """Record context token budget usage."""
        logger.info(
            "metric.context_budget",
            estimated_tokens=estimated_tokens,
            max_tokens=max_tokens,
            utilization_pct=round(estimated_tokens / max_tokens * 100, 1),
            truncated=truncated,
            correlation_id=correlation_id,
        )

    def record_memory_operation(
        self,
        operation: str,  # "record_turn" | "get_context" | "summarize" | "store_fact"
        session_id: str,
        latency_ms: float,
        success: bool,
        error_type: str | None = None,
    ) -> None:
        """Record metrics for a memory operation."""
        logger.info(
            "metric.memory_operation",
            operation=operation,
            session_id=session_id,
            latency_ms=round(latency_ms, 2),
            success=success,
            error_type=error_type,
        )

    def record_rag_retrieval(
        self,
        query_length: int,
        results_count: int,
        avg_score: float,
        latency_ms: float,
        reranked: bool = False,
        correlation_id: str = "",
    ) -> None:
        """Record metrics for a RAG retrieval operation."""
        logger.info(
            "metric.rag_retrieval",
            query_length=query_length,
            results_count=results_count,
            avg_score=round(avg_score, 3),
            latency_ms=round(latency_ms, 2),
            reranked=reranked,
            correlation_id=correlation_id,
        )

    @contextmanager
    def timed(self, metric_name: str, **labels: Any) -> Generator[dict[str, Any], None, None]:
        """
        Context manager that measures execution time and emits a metric.

        Usage:
            with metrics.timed("tool_execution", tool_name="read_file") as ctx:
                result = await tool.execute(call)
                ctx["success"] = result.success
        """
        start = time.perf_counter()
        context: dict[str, Any] = {"success": True, **labels}
        try:
            yield context
        except Exception as exc:
            context["success"] = False
            context["error_type"] = type(exc).__name__
            raise
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                f"metric.{metric_name}",
                latency_ms=latency_ms,
                **context,
            )


# Module-level singleton
_metrics: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    """Get the module-level metrics collector."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics
