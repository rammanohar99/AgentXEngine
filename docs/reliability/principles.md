---
title: Reliability Principles
domain: reliability
doc_type: architecture
status: active
owner: agent-runtime
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [reliability, retry, circuit-breaker, timeout, graceful-degradation, fallback]
related_adrs: [ADR-001, ADR-002, ADR-003]
related_incidents: [INC-001, INC-002, INC-003]
---

# Reliability Principles

**Related:** [Agent Runtime](../architecture/agent-runtime.md) · [Invariants](../architecture/invariants.md) · [ADR-001](../adr/001-provider-layer-owns-retries.md) · [ADR-002](../adr/002-long-lived-runtime-objects.md) · [ADR-003](../adr/003-graceful-memory-degradation.md) · [INC-001](../incidents/INC-001-retry-amplification.md)

---

## The Fundamental Rule: One Layer Owns Retries

**ONLY ONE LAYER in the call stack may own retry logic for a given operation.**

This is the most critical reliability rule in this system.

### The Retry Amplification Problem

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

**The fix:** Remove the retry layer from `AgentRuntime`. The provider layer
(`VertexAIService`) owns all retry logic. The runtime layer owns circuit breaker
and timeout only.

This pattern appears everywhere in distributed systems: microservices (service A
retries → service B retries → database retries), HTTP clients (application retry +
SDK retry + load balancer retry), and AI systems (runtime retry + provider retry).

### Retry Ownership Rules

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

See [ADR-001](../adr/001-provider-layer-owns-retries.md).

---

## Transient vs Permanent Error Classification

Not all errors should be retried. Retrying permanent errors wastes time and
can make the situation worse (e.g., retrying an auth failure may trigger account lockout).

**Transient — retry with exponential backoff + jitter:**
- Network errors, connection resets
- Rate limit exceeded (429)
- Service unavailable (503)
- Internal server error (500) — sometimes transient

**Permanent — fail immediately, zero retries:**
- Authentication failure (401, 403)
- Invalid request (400)
- Model not found (404)
- Quota exhausted (billing issue)
- Context length exceeded

**Jitter:** Add random variation to backoff delays to prevent thundering herd.
Without jitter, all retrying clients wake up at the same time and hammer the service.

Every retry MUST emit a structured log with:
- `correlation_id`
- `attempt` number
- `error_type`
- `backoff_seconds`
- `is_transient`

---

## Circuit Breaker

The circuit breaker prevents cascading failures when an external service is degraded.

**Without a circuit breaker:** Every request to a degraded service waits for the
full timeout (60s) before failing. Under load, this exhausts the connection pool
and brings down the entire service — not just the LLM feature.

### States

```
CLOSED    → normal operation, failures increment counter
OPEN      → rejecting all requests immediately
HALF_OPEN → one probe request allowed through
```

### Transitions

```
CLOSED → OPEN:      failure_count >= threshold (default: 5)
OPEN → HALF_OPEN:   recovery_seconds elapsed (default: 60s)
HALF_OPEN → CLOSED: probe request succeeds
HALF_OPEN → OPEN:   probe request fails (reopen immediately)
```

### Lifecycle Rule

**Circuit breaker instances MUST be long-lived.**

A circuit breaker recreated per request resets to CLOSED on every call.
Its entire value is the accumulated failure state across multiple requests.

```python
# WRONG — circuit breaker state is thrown away after every request
async def run(self, ...):
    runtime = AgentRuntime(...)  # New circuit breaker, zero protection
    async for event in runtime.run(...):
        yield event

# CORRECT — circuit breaker persists across requests
def __init__(self, ...):
    self._runtime = AgentRuntime(...)  # Created once, reused
```

See [ADR-002](../adr/002-long-lived-runtime-objects.md).

### Distributed Circuit Breaker (Phase 7)

Current circuit breakers are in-process. In a multi-replica deployment:
- Each pod has independent breaker state
- A degraded LLM opens the breaker on some pods but not others
- Pods without open breakers continue hammering the degraded service

**Fix:** Back circuit breaker state with Redis so all replicas share state.

```python
# Redis-backed circuit breaker state
redis.incr(f"circuit:{name}:failures")
redis.set(f"circuit:{name}:state", "open", ex=recovery_seconds)
```

**Implementation:** `packages/agents/resilience.py`

---

## Timeout Ownership

Every external call MUST have a timeout. Timeouts prevent hung connections
from accumulating and exhausting resources.

| Operation | Default Timeout | Owner |
|---|---|---|
| LLM call | 60s | `AgentRuntime` via `with_timeout()` |
| Tool execution | 30s | `AgentRuntime` via `with_timeout()` |
| Complete agent run | 300s | `AgentService` (future) |
| Embedding call | 30s | `EmbeddingService` |

Timeouts MUST surface as ERROR events to the user — never as hung connections.
`asyncio.wait_for` is the correct mechanism in async Python.

---

## Graceful Degradation

Every subsystem MUST degrade gracefully when its dependencies are unavailable.

| Subsystem | Dependency | Degradation |
|---|---|---|
| Memory summarization | LLM | Skip summarization, keep raw turns |
| Long-term memory | Redis | Fall back to in-process dict |
| Rate limiting | Redis | Fall back to in-process counter |
| Langfuse tracing | Langfuse | Fall back to NoOpTracer |
| Retrieval tool | pgvector | Skip tool registration, log warning |

**The principle:** A subsystem failure should degrade the feature, not crash the system.

```python
# WRONG — summarization failure crashes the agent run
await self._maybe_summarize(session_id)

# CORRECT — summarization failure is logged and skipped
try:
    await self._maybe_summarize(session_id)
except Exception as exc:
    logger.warning("summarization_skipped", error=str(exc))
    # Continue — raw turns are still available
```

See [ADR-003](../adr/003-graceful-memory-degradation.md).

---

## Fallback Model Strategy

On quota or rate-limit errors, the system tries a fallback model before giving up.

```
Primary:  gemini-2.0-flash       (fast, cost-efficient)
Fallback: gemini-2.0-flash-lite  (cheapest, fastest)
```

Fallback is triggered by: `quota`, `rate limit`, `resource exhausted`, `429`, `503`
Fallback is NOT triggered by: auth failures, invalid requests, model not found

The fallback is transparent to the caller. Response quality may be slightly lower
but the user gets an answer instead of an error.

---

## Reliability Checklist

Before merging any change that touches the agent runtime or LLM call path:

- [ ] No new retry layer added above `VertexAIService`
- [ ] No runtime objects created per-request that should be long-lived
- [ ] All new external calls have timeouts
- [ ] All new subsystem failures degrade gracefully (try/except + log + continue)
- [ ] All new operations emit `metric.*` events on both success and failure paths
- [ ] Circuit breaker state is not reset by the change
