---
title: "Phase 7: Production State Management"
domain: roadmap
doc_type: roadmap
status: planned
owner: platform-engineering
last_reviewed: 2026-05-18
stability: experimental
retrieval_priority: medium
tags: [roadmap, phase-7, redis, sessions, distributed, circuit-breaker, state]
---

# Phase 7: Production State Management

**Status:** 🔲 Next
**Related:** [Architecture Overview](../architecture/overview.md) · [Memory Systems](../architecture/memory-systems.md) · [Reliability Principles](../reliability/principles.md)

---

## Objective

Replace all in-process state with distributed, persistent equivalents.
After Phase 7, the system can run multiple replicas without state divergence,
and sessions survive pod restarts.

---

## Work Items

### 7.1 Redis-Backed Session Store

**Problem:** `_sessions: dict[str, list[ChatMessage]]` in `AgentService` is in-process.
Sessions are lost on restart. Not shared across replicas. Unbounded growth.

**Solution:**
```
Key:   session:{session_id}
Value: JSON-serialized list[ChatMessage]
TTL:   24h (configurable via SESSION_TTL_SECONDS)
```

Migration: lazy — old sessions expire naturally. New sessions use Redis.

**Files:** `apps/backend/app/services/agent.py`, new `app/core/session_store.py`

---

### 7.2 Redis-Backed Vector Memory

**Problem:** `VectorMemory._store: dict` is in-process. Lost on restart. Not shared.

**Solution:** Persist vector memory entries to pgvector:
```sql
CREATE TABLE vector_memory_entries (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL,
    role        VARCHAR(20) NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(768),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON vector_memory_entries (session_id, created_at);
```

**Files:** `packages/memory/vector_memory.py`, new Alembic migration

---

### 7.3 Distributed Circuit Breaker

**Problem:** Circuit breaker state is in-process. In a 3-replica deployment,
each replica has independent state. A degraded LLM opens the breaker on one
replica but not others — two-thirds of replicas continue hammering the service.

**Solution:** Back circuit breaker state with Redis:
```python
redis.incr(f"circuit:{name}:failures")
redis.set(f"circuit:{name}:state", "open", ex=recovery_seconds)
```

**Files:** `packages/agents/resilience.py`

---

### 7.4 Retire ChatService

**Problem:** `ChatService` is a Phase 1 artifact. Both `AgentService` and `ChatService`
maintain independent session stores — two sources of truth.

**Solution:** Route all `/chat` requests through `AgentService`. Delete `ChatService`.

**Files:** `apps/backend/app/services/chat.py`, `apps/backend/app/api/chat.py`

---

### 7.5 Langfuse + OTel Trace Correlation

**Problem:** Langfuse traces and OTel spans are independent. A single agent run
generates both but they share no common ID.

**Solution:** Inject Langfuse trace ID as an OTel span attribute.
Inject OTel trace ID into Langfuse metadata.

**Files:** `packages/observability/tracer.py`, `packages/observability/otel.py`

---

### 7.6 Token-Aware Memory Injection

**Problem:** Memory context is injected without checking the token budget.
A large memory context can consume most of the budget before the conversation starts.

**Solution:** Estimate memory token cost before injection. Truncate if needed.
Priority: recent turns > summary > long-term facts > oldest turns.

**Files:** `packages/memory/manager.py`, `packages/agents/context_manager.py`

---

## Definition of Done

- [ ] Sessions survive backend restart
- [ ] Two backend replicas share session state
- [ ] Circuit breaker state shared across replicas
- [ ] `ChatService` deleted, all routes through `AgentService`
- [ ] Langfuse trace ID appears in OTel spans
- [ ] Memory injection respects token budget
- [ ] All existing tests pass
- [ ] New integration tests for Redis session store
