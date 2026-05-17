---
title: Retry Amplification Trace
domain: examples
doc_type: example
status: active
owner: reliability
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: medium
tags: [trace, reliability, retries, incidents, resilience]
---

# Retry Amplification Trace

**Related:** [INC-001](../incidents/INC-001-retry-amplification.md) · [ADR-001](../adr/001-provider-layer-owns-retries.md) · [INV-001](../architecture/invariants.md#inv-001-provider-layer-owns-retries)

This trace demonstrates the correct behavior of a single, localized retry loop in the Provider Layer (`VertexAIService`), contrasting with the failure mode of nested retries.

## The Trace (Correct Behavior)

When an LLM provider returns a 429 Too Many Requests, `VertexAIService` handles the retry transparently using `tenacity` with exponential backoff. The `AgentRuntime` sees a single, slightly slower call.

```json
{"event": "agent_stream_start", "session_id": "sess_456", "run_id": "run_789"}

// VertexAIService encounters a 429 and retries internally
{"event": "llm_retry_attempt", "attempt": 1, "error": "429 Too Many Requests", "delay_ms": 1000}
{"event": "llm_retry_attempt", "attempt": 2, "error": "429 Too Many Requests", "delay_ms": 2000}

// The 3rd attempt succeeds
{"event": "metric.llm_call", "model": "gemini-1.5-flash", "latency_ms": 3500.5, "retry_count": 2, "success": true}
```

## The Trace (Incorrect Behavior — Nested Retries)

If `AgentRuntime` (or `AgentService`) also implemented retries (e.g. 3 attempts), a single logical call failing would multiply: 3 runtime retries × 3 provider retries = 9 physical API calls.

```json
{"event": "agent_stream_start", "session_id": "sess_456", "run_id": "run_789"}

// Runtime Attempt 1
{"event": "llm_retry_attempt", "layer": "provider", "attempt": 1, "error": "429"}
{"event": "llm_retry_attempt", "layer": "provider", "attempt": 2, "error": "429"}
{"event": "llm_retry_attempt", "layer": "provider", "attempt": 3, "error": "429"}
{"event": "runtime_retry", "layer": "runtime", "attempt": 1, "error": "Provider failed after 3 attempts"}

// Runtime Attempt 2 (Amplification!)
{"event": "llm_retry_attempt", "layer": "provider", "attempt": 1, "error": "429"}
{"event": "llm_retry_attempt", "layer": "provider", "attempt": 2, "error": "429"}
{"event": "llm_retry_attempt", "layer": "provider", "attempt": 3, "error": "429"}
{"event": "runtime_retry", "layer": "runtime", "attempt": 2, "error": "Provider failed after 3 attempts"}

// Runtime Attempt 3 (Amplification!)
{"event": "llm_retry_attempt", "layer": "provider", "attempt": 1, "error": "429"}
{"event": "llm_retry_attempt", "layer": "provider", "attempt": 2, "error": "429"}
{"event": "llm_retry_attempt", "layer": "provider", "attempt": 3, "error": "429"}

{"event": "metric.agent_run", "success": false, "error_type": "MaxRetriesExceeded"}
```

## Key Observations

1. **Multiplicative Storm:** Nested retries rapidly exhaust quota and exacerbate system degradation.
2. **Single Owner:** `INV-001` dictates that ONLY the provider layer owns retries. 
3. **Trace Visibility:** By looking at `metric.llm_call`, we can see `retry_count=2` without the `AgentRuntime` being aware of the transient failures.