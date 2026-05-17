"""
Tracer unit tests — verifies NoOpTracer and span lifecycle.

No Langfuse credentials needed — tests use NoOpTracer only.
"""

import pytest

from packages.observability.tracer import AgentTracer, NoOpTracer


def test_noop_tracer_is_disabled() -> None:
    tracer = NoOpTracer()
    assert tracer.is_enabled is False


def test_noop_tracer_trace_run_context_manager() -> None:
    tracer = NoOpTracer()
    with tracer.trace_run("s1", "run-1", "Hello") as trace:
        assert trace is not None
        span = trace.span_tool_call("read_file", {"path": "test.py"})
        span.end(output="file contents")


def test_noop_tracer_span_end_with_error() -> None:
    tracer = NoOpTracer()
    with tracer.trace_run("s1", "run-1", "Hello") as trace:
        span = trace.span_tool_call("read_file", {})
        span.end(error="File not found")  # Should not raise


def test_noop_tracer_llm_span() -> None:
    tracer = NoOpTracer()
    with tracer.trace_run("s1", "run-1", "Hello") as trace:
        span = trace.span_llm_call("gemini-1.5-pro", prompt_tokens=100)
        span.end(output="The answer is 42")


def test_noop_tracer_memory_span() -> None:
    tracer = NoOpTracer()
    with tracer.trace_run("s1", "run-1", "Hello") as trace:
        span = trace.span_memory_retrieval("s1")
        span.end()


def test_agent_tracer_from_settings_returns_noop_when_unconfigured() -> None:
    """When Langfuse keys are empty, from_settings returns NoOpTracer."""

    class FakeSettings:
        langfuse_public_key = ""
        langfuse_secret_key = ""
        langfuse_host = "https://cloud.langfuse.com"

    tracer = AgentTracer.from_settings(FakeSettings())
    assert isinstance(tracer, NoOpTracer)


def test_agent_tracer_from_settings_returns_agent_tracer_when_configured() -> None:
    """When Langfuse keys are present, from_settings returns AgentTracer."""

    class FakeSettings:
        langfuse_public_key = "pk-test"
        langfuse_secret_key = "sk-test"
        langfuse_host = "https://cloud.langfuse.com"

    tracer = AgentTracer.from_settings(FakeSettings())
    assert isinstance(tracer, AgentTracer)
    assert tracer.is_enabled is True
