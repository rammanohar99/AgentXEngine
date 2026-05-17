---
title: "ADR-001: Provider Layer Owns Retries"
domain: adr
doc_type: adr
status: active
owner: agent-runtime
last_reviewed: 2026-05-18
stability: historical
retrieval_priority: high
tags: [adr, reliability, retry, amplification, vertex-ai, provider-layer]
related_incidents: [INC-001]
---

# ADR-001: Provider Layer Owns Retries

**Status:** Accepted
**Date:** Phase 6.1
**Phase:** 6.1

---

## Context

During the Phase 6 reliability audit, a retry amplification bug was discovered:

- `AgentRuntime._call_llm_with_resilience()` wrapped LLM calls with `RetryPolicy(max_attempts=3)`
- `VertexAIService._complete_with_model()` also wrapped LLM calls with `RetryPolicy(max_attempts=3)`
- These two retry layers were independent and nested

**The math:**
```
1 logical LLM call
  → AgentRuntime retry layer: up to 3 attempts
    → Each attempt: VertexAIService retry layer: up to 3 attempts
      = up to 9 actual API calls per logical LLM call
```

**The failure mode under load:**
1. Vertex AI becomes rate-limited (429 responses)
2. Both retry layers kick in simultaneously
3. 9× the expected API call volume hits the already-degraded service
4. Rate limiting worsens → more retries → more rate limiting
5. Circuit breaker opens — but only after the damage is done

This is one of the most common reliability mistakes in distributed systems.
It appears in microservices (service A retries → service B retries → database retries),
in HTTP clients (application retry + SDK retry + load balancer retry), and in
AI systems (runtime retry + provider retry).

---

## Decision

**Only one layer in the call stack may own retry logic for a given operation.**

`VertexAIService` owns all retry logic for LLM calls.
`AgentRuntime` owns circuit breaker and timeout only.

```
Provider layer (VertexAIService):
  ✅ Owns retry logic for API calls
  ✅ Owns fallback model selection
  ✅ Owns transient vs permanent error classification

Runtime layer (AgentRuntime):
  ✅ Owns circuit breaker check
  ✅ Owns timeout enforcement
  ✅ Owns error event emission
  ❌ MUST NOT add its own retry loop over provider retries
```

---

## Consequences

**Positive:**
- Eliminates retry amplification — maximum 3 API calls per logical LLM call
- Simplifies `AgentRuntime` — no retry configuration to manage
- All retry configuration lives in one place (`VertexAIService`)
- Reduces pressure on degraded services under load

**Negative:**
- `AgentRuntime` cannot customize retry behavior per call site
- Retry policy is shared across all callers of `VertexAIService`

---

## Alternatives Considered

**Keep both retry layers, coordinate via shared state:** Too complex. Shared state
between layers creates coupling and is difficult to reason about.

**Remove retries from `VertexAIService`:** The provider layer is the right place
for retries because it has the most context about the error (HTTP status codes,
error messages, quota state). The runtime layer should not need to understand
provider-specific error codes.
