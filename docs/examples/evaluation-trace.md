---
title: Non-Blocking Evaluation Trace
domain: examples
doc_type: example
status: active
owner: observability
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: medium
tags: [trace, evaluation, non-blocking, performance]
---

# Non-Blocking Evaluation Trace

**Related:** [ADR-005](../adr/005-evaluation-in-hot-path.md) · [INV-005](../architecture/invariants.md#inv-005-evaluation-never-blocks-the-user-response)

This trace demonstrates how the `AgentEvaluator` executes concurrently after a run is complete, ensuring that the latency of the LLM-as-a-judge evaluation does not affect the end-user's response time.

## The Trace

```json
{"event": "agent_stream_start", "session_id": "sess_abc", "run_id": "run_xyz", "correlation_id": "b1c2d3...e4f"}
{"event": "tool_execution_start", "tool_name": "database_query"}
{"event": "tool_execution_complete", "tool_name": "database_query", "duration_ms": 150}
{"event": "metric.llm_call", "model": "gemini-1.5-pro", "latency_ms": 4200.5}

// The stream yields "done", the HTTP response concludes, and the agent run is complete.
{"event": "metric.agent_run", "latency_ms": 4350.5, "steps_taken": 2, "success": true, "correlation_id": "b1c2d3...e4f"}
{"event": "agent_stream_complete", "session_id": "sess_abc"}

// THE USER HAS ALREADY RECEIVED THE RESPONSE HERE

// The asyncio.ensure_future task kicks off the evaluation process.
// It inherits the same structlog context (correlation_id and trace_id).
{"event": "evaluation_started", "session_id": "sess_abc", "run_id": "run_xyz", "correlation_id": "b1c2d3...e4f"}

// A separate LLM call is made by the evaluator (LLM-as-a-judge).
// Note this call takes ~2.5 seconds, which would be terrible if it blocked the user!
{"event": "metric.llm_call", "model": "gemini-1.5-pro", "latency_ms": 2500.1, "correlation_id": "b1c2d3...e4f"}

// The evaluation metric is emitted.
{"event": "metric.evaluation", "session_id": "sess_abc", "run_id": "run_xyz", "relevance": 5, "completeness": 4, "accuracy": 5, "overall": 4.6, "correlation_id": "b1c2d3...e4f"}
```

## Key Observations

1. **User Experience:** The `metric.agent_run` and `agent_stream_complete` events occur immediately after the final answer is streamed.
2. **Context Persistence:** Because the evaluator task is created with `asyncio.ensure_future` or `asyncio.create_task`, Python 3.7+ contextvars are automatically inherited. The `correlation_id` and OpenTelemetry `trace_id` flow seamlessly into the evaluation logs.
3. **Isolation:** The evaluator uses its own instance of `VertexAIService` so that its token consumption and latency metrics are logged separately from the core agent tools, preventing pollution of the agent's internal state.