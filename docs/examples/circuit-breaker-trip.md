---
title: "Example: Circuit Breaker Trip and Recovery"
domain: example
doc_type: example
status: active
owner: agent-runtime
last_reviewed: 2026-05-18
stability: operational
retrieval_priority: medium
tags: [example, circuit-breaker, reliability, degradation, recovery, trace]
related_adrs: [ADR-001, ADR-002]
related_incidents: [INC-001, INC-002]
---

# Example: Circuit Breaker Trip and Recovery

A trace showing Vertex AI rate limiting → retry exhaustion → circuit breaker
opening → requests rejected immediately → recovery after 60s.

**Related:** [Reliability Principles](../reliability/principles.md) · [Runbooks — LLM Degraded](../runbooks/incident-response.md#llm-service-degraded-429--503) · [INC-001](../incidents/INC-001-retry-amplification.md)

---

## Setup

- **Vertex AI status:** Rate limited (429 responses)
- **Circuit breaker threshold:** 5 failures
- **Recovery period:** 60s
- **Retry policy:** 3 attempts, exponential backoff (owned by `VertexAIService`)

---

## Phase 1: Failures Accumulate (Requests 1–5)

```
[Request 1]
  CHECK circuit breaker → CLOSED (failures=0)
  LLM CALL attempt 1 → 429 Rate Limited
  LLM CALL attempt 2 (backoff 1s) → 429 Rate Limited
  LLM CALL attempt 3 (backoff 2s) → 429 Rate Limited
  FALLBACK to gemini-2.0-flash-lite
  LLM CALL attempt 1 (fallback) → 429 Rate Limited
  LLM CALL attempt 2 (fallback, backoff 1s) → 429 Rate Limited
  LLM CALL attempt 3 (fallback, backoff 2s) → 429 Rate Limited
  ALL retries exhausted → raise LLMError
  circuit_breaker.record_failure() → failures=1
  EMIT AgentEvent(ERROR): "LLM service unavailable"
  metric.llm_call: success=false, retry_count=3, error_type=rate_limit
  metric.agent_run: success=false, error_type=rate_limit

[Requests 2–4]  (same pattern)
  circuit_breaker.failures → 2, 3, 4

[Request 5]
  circuit_breaker.record_failure() → failures=5 >= threshold(5)
  CIRCUIT BREAKER OPENS
  metric.circuit_breaker: event=opened, failure_count=5
```

---

## Phase 2: Circuit Open — Requests Rejected Immediately

```
[Requests 6–N, during 60s recovery window]
  CHECK circuit breaker → OPEN
  REJECT immediately (no LLM call made)
  EMIT AgentEvent(ERROR): "Service temporarily unavailable. Please try again shortly."
  metric.circuit_breaker: event=rejected, state=open
  metric.agent_run: success=false, error_type=circuit_open, latency_ms=1
```

**Key observation:** Requests fail in ~1ms instead of waiting 60s+ for retries.
The circuit breaker protects the system from exhausting connection pools.

---

## Phase 3: Half-Open Probe

```
[T+60s after opening]
  CIRCUIT BREAKER → HALF_OPEN
  metric.circuit_breaker: event=half_open

[Next request]
  CHECK circuit breaker → HALF_OPEN, allow probe
  LLM CALL → 200 OK (Vertex AI recovered)
  circuit_breaker.record_success()
  CIRCUIT BREAKER → CLOSED
  metric.circuit_breaker: event=closed, failure_count=0
  Run completes normally
```

---

## Structured Log Sequence

```json
{"event": "metric.llm_call", "success": false, "retry_count": 3, "error_type": "rate_limit", "model": "gemini-2.0-flash"}
{"event": "metric.llm_call", "success": false, "retry_count": 3, "error_type": "rate_limit", "model": "gemini-2.0-flash-lite"}
{"event": "metric.circuit_breaker", "breaker_name": "vertex_ai", "event": "opened", "failure_count": 5}
{"event": "metric.circuit_breaker", "breaker_name": "vertex_ai", "event": "rejected", "state": "open"}
{"event": "metric.circuit_breaker", "breaker_name": "vertex_ai", "event": "half_open"}
{"event": "metric.circuit_breaker", "breaker_name": "vertex_ai", "event": "closed", "failure_count": 0}
```

---

## What This Demonstrates

- `VertexAIService` owns all retries — `AgentRuntime` does not add its own (INV-001)
- Fallback model is tried before giving up
- Circuit breaker is long-lived — it accumulates failures across requests (INV-002)
- Rejected requests fail in ~1ms — no timeout wait
- Recovery is automatic — no manual intervention needed
- All state transitions emit `metric.circuit_breaker` events
