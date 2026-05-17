---
title: Observability Overview
domain: observability
doc_type: architecture
status: active
owner: observability
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [observability, logging, tracing, metrics, correlation-id, langfuse, opentelemetry, structured-logs]
related_incidents: [INC-005]
---

# Observability Overview

**Related:** [Architecture Overview](../architecture/overview.md) · [Reliability Principles](../reliability/principles.md) · [Evaluation Overview](../evaluation/overview.md) · [Phase 8 Roadmap](../roadmap/phase-08-event-sourced-runtime.md)

---

## The Four Pillars

Every production operation must be covered by all four:

| Pillar | Tool | Purpose |
|---|---|---|
| Logs | structlog (structured JSON) | What happened, with context |
| Traces | Langfuse + OpenTelemetry | How it happened, timing, spans |
| Metrics | `metric.*` log events | How often and how fast |
| Events | Execution journal (roadmap) | What changed, for replay and audit |

Missing any one creates blind spots.

**Implementation:** `packages/observability/`

---

## Structured Logging

Logs must be structured JSON — not free-form strings.

```python
# WRONG — unstructured, unsearchable
logger.info(f"Agent run completed in {latency}ms with {steps} steps")

# CORRECT — structured, filterable, aggregatable
logger.info(
    "agent_run_complete",
    session_id=session_id,
    run_id=run_id,
    latency_ms=latency_ms,
    steps=steps,
    success=True,
)
```

Structured logs can be queried, aggregated, and alerted on.
Free-form strings require regex parsing and are fragile.

---

## Correlation IDs

Every request gets a unique `correlation_id` injected by `CorrelationIDMiddleware`.
This ID MUST flow through:
- All log entries for the request
- All Langfuse trace metadata
- All OTel span attributes
- All metric events
- All retry log entries

Without correlation IDs, debugging a distributed failure requires manually
correlating timestamps across multiple log streams. With them, a single grep
finds every log entry for a specific request.

**Implementation:** `apps/backend/app/core/middleware.py`

---

## Distributed Tracing

This system uses two tracing systems:

| System | Scope | Tool |
|---|---|---|
| Langfuse | Agent-level: runs, steps, tool calls, memory | `packages/observability/tracer.py` |
| OpenTelemetry | Infrastructure-level: HTTP requests, DB queries | `packages/observability/otel.py` |

**Integration (Implemented in Phase 3):** These two systems are fully linked.
`CorrelationIDMiddleware` extracts the OpenTelemetry `trace_id` and binds it to `structlog` alongside the HTTP request `correlation_id`.
`AgentTracer` injects both the `correlation_id` and `otel_trace_id` into Langfuse trace tags and metadata.
A single `correlation_id` or `trace_id` links logs, metrics, OpenTelemetry spans, and Langfuse traces end-to-end.

---

## Required Metric Events

All key operations MUST emit `metric.*` log events with consistent schemas.
These can be consumed by any log aggregator (Datadog, CloudWatch, etc.)
to build dashboards and alerts without a separate metrics infrastructure.

The `metric.` prefix makes these events filterable from operational logs.

| Event | Required Fields |
|---|---|
| `metric.agent_run` | session_id, run_id, latency_ms, steps, tool_calls, tokens, success, error_type |
| `metric.llm_call` | model, latency_ms, input_tokens, output_tokens, retry_count, success, error_type |
| `metric.llm_first_token` | model, time_to_first_token_ms, correlation_id |
| `metric.tool_execution` | tool_name, latency_ms, success, error_type, output_chars |
| `metric.circuit_breaker` | breaker_name, event, failure_count |
| `metric.context_budget` | estimated_tokens, max_tokens, utilization_pct, truncated |
| `metric.memory_operation` | operation, session_id, latency_ms, success |
| `metric.rag_retrieval` | query_length, results_count, avg_score, latency_ms, reranked |
| `metric.evaluation` | session_id, run_id, relevance, completeness, accuracy, overall |

---

## First-Token Latency

For streaming responses, **first-token latency** is the primary UX metric.
Users perceive a system as "fast" if they see the first word quickly,
even if the total response takes longer.

`VertexAIService.stream()` records and emits `metric.llm_first_token` with:
- `time_to_first_token_ms`
- `model`
- `correlation_id`

---

## Memory Operation Tracing

Memory operations (`record_turn`, `get_context`, `summarize`) are not currently
traced in Langfuse. They must be wrapped in Langfuse spans to make memory
retrieval latency visible in traces. This is tracked for Phase 7.

---

## Runtime Introspection (Roadmap — Phase 12)

`GET /api/v1/debug/runtime` will return:
- Active session count
- Circuit breaker states (all breakers)
- Memory usage per session (turn count, summary presence)
- Recent error rates (last 5 minutes)
- Queue depths (Celery)

Protected by admin authentication. Never exposed publicly.

---

## Execution Replayability (Roadmap — Phase 8)

Every `AgentEvent` emitted during a run will be persisted to an execution journal.

```sql
CREATE TABLE agent_run_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      UUID NOT NULL,
    session_id  UUID NOT NULL,
    step        INTEGER NOT NULL,
    event_type  VARCHAR(50) NOT NULL,
    content     TEXT,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON agent_run_events (run_id, step);
CREATE INDEX ON agent_run_events (session_id, created_at);
```

This enables:
- **Replay:** re-execute any past run step-by-step in the UI
- **Debug:** inspect the exact context sent to the LLM at each step
- **Audit:** complete audit trail for governance and compliance
- **Evaluation:** trajectory analysis on real production runs

Replay API: `GET /api/v1/runs/{run_id}/events`
