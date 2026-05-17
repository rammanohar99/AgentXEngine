---
title: Distributed Trace Correlation
domain: examples
doc_type: example
status: active
owner: observability
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: medium
tags: [trace, distributed-tracing, opentelemetry, langfuse, structlog, correlation-id]
---

# Distributed Trace Correlation

**Related:** [Observability Overview](../observability/overview.md) · [INV-007](../architecture/invariants.md#inv-007-correlation-ids-flow-through-all-operations)

This trace demonstrates how the three observability pillars (Logs via structlog, App Tracing via Langfuse, and Infrastructure Tracing via OpenTelemetry) are linked together using a shared `correlation_id` and `otel_trace_id`.

## The Request Lifecycle

1. **Ingress:** The FastAPI middleware (`CorrelationIDMiddleware`) intercepts the request, reads `X-Correlation-ID` (or generates one), and binds it to `structlog.contextvars`.
2. **OTel Hook:** It also hooks into the active `FastAPIInstrumentor` OpenTelemetry span, injecting `correlation_id` as an attribute, and extracting the OpenTelemetry `trace_id` to bind it to `structlog.contextvars` as well.
3. **Agent Start:** When the `AgentService` starts, it creates a `LangfuseTrace`. The `AgentTracer` inspects the current `structlog.contextvars` and injects both IDs into the Langfuse Trace metadata and tags.
4. **Execution:** All subsequent operations (tools, LLMs, evaluation) inherit the `structlog` context automatically, ensuring every log and metric carries both IDs.

## The Trace

```json
// 1. The HTTP request is received. Middleware binds contextvars.
// OpenTelemetry generates trace_id: 5b8a9f...
// structlog logs the request completion later with those vars.

{"event": "agent_stream_start", "session_id": "sess_123", "correlation_id": "req-999", "trace_id": "5b8a9f..."}

// 2. Langfuse trace is opened. AgentTracer reads the contextvars.
// It sends a trace payload to Langfuse:
/* 
  POST /api/public/traces
  {
    "id": "run_456",
    "metadata": {
       "correlation_id": "req-999",
       "otel_trace_id": "5b8a9f..."
    },
    "tags": ["correlation_id:req-999", "otel_trace_id:5b8a9f..."]
  }
*/

// 3. Tool execution (part of Langfuse trace, logs also carry IDs)
{"event": "tool_execution_start", "tool_name": "read_file", "correlation_id": "req-999", "trace_id": "5b8a9f..."}
{"event": "metric.tool_execution", "tool_name": "read_file", "success": true, "correlation_id": "req-999", "trace_id": "5b8a9f..."}

// 4. LLM call (part of Langfuse trace generation, logs also carry IDs)
{"event": "metric.llm_call", "model": "gemini-1.5-flash", "latency_ms": 1200, "correlation_id": "req-999", "trace_id": "5b8a9f..."}

// 5. HTTP Response finishes
{"event": "http_request", "method": "POST", "path": "/api/v1/chat/stream", "status_code": 200, "duration_ms": 1350, "correlation_id": "req-999", "trace_id": "5b8a9f..."}
```

## Cross-System Linkage

- **From Logs to OTel:** Search your tracing backend (e.g., Jaeger, Datadog) for the `trace_id` found in the log.
- **From Logs to Langfuse:** Search Langfuse for the `correlation_id` found in the log using the global search or tags filter.
- **From Langfuse to OTel:** Look at the Langfuse trace's metadata pane to find the `otel_trace_id`, then paste it into your tracing backend.