---
title: "Example: Graceful Degradation (Redis Unavailable)"
domain: example
doc_type: example
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: operational
retrieval_priority: medium
tags: [example, graceful-degradation, redis, fallback, reliability, trace]
related_adrs: [ADR-003]
---

# Example: Graceful Degradation (Redis Unavailable)

A trace showing the system degrading gracefully when Redis goes down —
falling back to in-process state while agent runs continue uninterrupted.

**Related:** [Reliability Principles](../reliability/principles.md) · [Memory Systems](../architecture/memory-systems.md) · [Runbooks — Redis Unavailable](../runbooks/incident-response.md#redis-unavailable)

---

## Setup

- **Redis status:** Unavailable (connection refused)
- **Affected subsystems:** long-term memory, rate limiting, session store
- **Expected behavior:** all subsystems fall back to in-process equivalents

---

## Event Flow

```
[T+0ms]    Request arrives
           → CorrelationIDMiddleware injects correlation_id=corr_ghi

[T+1ms]    RATE LIMIT CHECK
           → redis.incr("rate:sess_abc:minute") → ConnectionError
           → FALLBACK: in-process counter
           → logger.warning("redis_unavailable_rate_limit_fallback")
           → rate limit check passes (in-process counter)

[T+2ms]    MemoryManager.get_context()
           → FETCH short-term memory (in-process) → OK, 4 turns
           → FETCH summary from Redis → ConnectionError
           → FALLBACK: no summary (treat as empty)
           → logger.warning("redis_unavailable_summary_fetch_failed")
           → FETCH long-term facts from Redis → ConnectionError
           → FALLBACK: empty facts dict
           → logger.warning("redis_unavailable_facts_fetch_failed")
           → RETURN: short-term turns only (no summary, no facts)

[T+3ms]    AgentRuntime.run() proceeds normally
           → context assembled from short-term memory only
           → LLM call, tool calls, final answer — all normal

[T+5,200ms] Run completes
           → metric.agent_run: success=true, latency_ms=5200

[T+5,201ms] MemoryManager.record_turn()
           → short-term memory updated (in-process) → OK
           → long-term facts write to Redis → ConnectionError
           → FALLBACK: write to in-process dict
           → logger.warning("redis_unavailable_facts_write_fallback")

[T+5,202ms] Summarization check
           → 4 turns < threshold (16), no summarization triggered
```

---

## What the User Experiences

The user receives a normal response. There is no error. The response may be
slightly lower quality (no long-term facts injected) but the run succeeds.

---

## What Operators See

```json
{"level": "warning", "event": "redis_unavailable_rate_limit_fallback", "correlation_id": "corr_ghi"}
{"level": "warning", "event": "redis_unavailable_summary_fetch_failed", "correlation_id": "corr_ghi"}
{"level": "warning", "event": "redis_unavailable_facts_fetch_failed", "correlation_id": "corr_ghi"}
{"level": "warning", "event": "redis_unavailable_facts_write_fallback", "correlation_id": "corr_ghi"}
{"event": "metric.agent_run", "success": true, "latency_ms": 5200}
```

Warnings, not errors. The run succeeds. The `correlation_id` links all warnings
to the same request for easy diagnosis.

---

## Degradation Summary

| Subsystem | Normal | Redis Down |
|---|---|---|
| Rate limiting | Redis sliding window | In-process counter (per-replica) |
| Long-term memory read | Redis | Empty (no facts injected) |
| Long-term memory write | Redis | In-process dict (lost on restart) |
| Summary read | Redis | Empty (no summary injected) |
| Session store | Redis | In-process dict (lost on restart) |
| Agent run | Normal | Normal (slightly reduced context quality) |

---

## What This Demonstrates

- Every Redis-dependent subsystem has an in-process fallback
- Fallbacks are logged as warnings, not errors
- Agent runs never fail due to Redis unavailability
- The `correlation_id` links all fallback warnings to the same request
- This is the correct behavior defined in [Reliability Principles](../reliability/principles.md#graceful-degradation)
