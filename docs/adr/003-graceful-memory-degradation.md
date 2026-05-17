---
title: "ADR-003: Graceful Memory Degradation"
domain: adr
doc_type: adr
status: active
owner: memory-systems
last_reviewed: 2026-05-18
stability: historical
retrieval_priority: high
tags: [adr, reliability, memory, graceful-degradation, summarization, cascade]
related_incidents: [INC-003]
---

# ADR-003: Graceful Memory Degradation

**Status:** Accepted
**Date:** Phase 6.1
**Phase:** 6.1

---

## Context

Memory summarization makes an LLM call. If this call fails and the exception
propagates, it fails the entire agent run — not just the summarization.

This is disproportionate impact. The user asked a question. The agent was about
to answer it. The summarization step is a background optimization — it compresses
old conversation turns to save context space. If it fails, the agent can still
answer the question using the raw turns. There is no reason to fail the entire run.

The same principle applies to other memory operations: long-term memory writes,
vector memory storage, and Redis operations.

---

## Decision

Memory subsystem failures MUST NOT fail agent runs.
All memory operations are wrapped in try/except with graceful fallback.

```python
# WRONG — summarization failure crashes the agent run
await self._maybe_summarize(session_id)

# CORRECT — summarization failure is logged and skipped
try:
    await self._maybe_summarize(session_id)
except Exception as exc:
    logger.warning(
        "summarization_skipped",
        session_id=session_id,
        error=str(exc),
    )
    # Continue — raw turns are still available
```

Degradation table:

| Failure | Behavior |
|---|---|
| Summarization LLM call fails | Skip summarization, keep raw turns, continue |
| Redis unavailable | Fall back to in-process dict for long-term memory |
| Vector embedding fails | Skip vector storage, log warning, continue |

---

## Consequences

**Positive:**
- Memory failures are contained — they do not cascade into agent run failures
- Users get answers even when memory subsystems are degraded
- Memory failures are visible in logs (warnings, not errors)

**Negative:**
- Memory state may be inconsistent after a failure (e.g., turns not summarized)
- Long-term memory may be unavailable if Redis is down
- Vector memory may be incomplete if embedding fails

These are acceptable tradeoffs. Degraded memory is better than no answer.

---

## Alternatives Considered

**Fail the agent run on memory failure:** Rejected. The memory subsystem is
a supporting component, not the primary function. Failing the run for a
summarization error is disproportionate.

**Retry memory operations:** Rejected for the same reason as ADR-001 — retry
ownership must be clear. Memory operations that fail transiently will be retried
on the next turn. Retrying synchronously in the hot path adds latency.
