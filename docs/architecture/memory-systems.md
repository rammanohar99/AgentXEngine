---
title: Memory Systems Architecture
domain: architecture
doc_type: architecture
status: active
owner: memory-systems
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [memory, short-term, long-term, summarization, vector-memory, redis, session]
related_adrs: [ADR-003]
related_incidents: [INC-003]
---

# Memory Systems Architecture

**Related:** [Architecture Overview](overview.md) · [Agent Runtime](agent-runtime.md) · [Context Engineering](context-engineering.md) · [ADR-003](../adr/003-graceful-memory-degradation.md) · [INC-003](../incidents/INC-003-memory-summarization-cascade.md)

---

## Memory Type Hierarchy

| Type | Storage | Scope | TTL | Status |
|---|---|---|---|---|
| Short-term | In-process dict | Session | Evicted at window limit | ✅ Implemented |
| Long-term | Redis | Session | 30 days | ✅ Implemented |
| Summarized | Redis | Session | 7 days | ✅ Implemented |
| Vector | In-process dict | Session | Evicted at entry limit | ⚠️ Needs pgvector migration |

**Implementation:** `packages/memory/`

---

## Short-Term Memory

A sliding window of recent conversation turns, stored in-process.

- Window size: configurable (default: 16 turns)
- When the window fills, older turns are compressed into a summary
- The most recent N turns are always kept verbatim

---

## Long-Term Memory

Explicit facts extracted and stored per session in Redis.

- Keyed by `session:{session_id}:facts`
- TTL: 30 days
- Used for persistent user preferences, project context, and key facts

---

## Summarized Memory

When short-term memory reaches the threshold, older turns are compressed
into a summary via LLM call. The summary replaces the raw turns.

```
Before: [turn 1, turn 2, ..., turn 16]
After:  summary = "User asked about X, Y, Z. Agent explained..."
        + [turn 11, turn 12, ..., turn 16]  (6 most recent kept verbatim)
```

**Why keep recent turns:** The most recent context is most relevant.
The summary captures the gist of older turns without the verbosity.

**Implementation:** `packages/memory/summarizer.py`

---

## Vector Memory

Embedding-based episodic recall. Each turn is embedded and stored.
Retrieval uses cosine similarity against the current query to find
semantically relevant past exchanges.

Enables "remember when we discussed X?" even if X was many turns ago
and has been pruned from short-term memory.

**Current limitation:** In-process storage. Lost on restart. Not shared across replicas.

**Target (Phase 7):** Persist to pgvector table:
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

**Implementation:** `packages/memory/vector_memory.py`

---

## Memory Manager

The `MemoryManager` is the unified coordinator for all memory types.
It provides a single interface for recording turns and retrieving context.

```python
# Record a turn
await memory_manager.record_turn(session_id, role, content)

# Get context for injection into the prompt
context = await memory_manager.get_context(session_id)
# Returns: summary + recent turns + relevant vector memories
```

**Implementation:** `packages/memory/manager.py`

---

## Memory Failure Isolation

Memory subsystem failures MUST NOT fail agent runs.

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

**The principle:** A subsystem failure should degrade the feature, not crash the system.

Degradation table:

| Failure | Behavior |
|---|---|
| Summarization LLM call fails | Skip summarization, keep raw turns, continue |
| Redis unavailable | Fall back to in-process dict for long-term memory |
| Vector embedding fails | Skip vector storage, log warning, continue |

See [ADR-003](../adr/003-graceful-memory-degradation.md).

---

## Memory Context Injection

Memory context is injected as a system message before the conversation.
This must be token-aware — a large memory context can consume a significant
portion of the token budget before the conversation even starts.

```python
# WRONG — injects memory without checking budget
messages.append(Message(role="system", content=memory_section))

# CORRECT — estimates memory cost, truncates if needed
memory_tokens = estimate_tokens(memory_section)
if memory_tokens + conversation_tokens < max_tokens:
    messages.append(Message(role="system", content=memory_section))
else:
    truncated = truncate_memory_to_budget(memory_section, budget_remaining)
    messages.append(Message(role="system", content=truncated))
```

**Injection priority when budget is tight:**
1. Most recent conversation turns
2. Conversation summary
3. Most relevant long-term facts
4. Oldest turns (drop first)

---

## Known Limitations

| Limitation | Impact | Fix Phase |
|---|---|---|
| In-memory session store | Sessions lost on restart; no horizontal scaling | Phase 7 |
| In-memory vector memory | Vector memory lost on restart; not shared | Phase 7 |
| Memory operations not traced in Langfuse | Memory latency not visible in traces | Phase 7 |

---

## Production Target (Phase 7)

Replace in-process session store with Redis-backed `SessionStore`:

```
Key:   session:{session_id}
Value: JSON-serialized list[ChatMessage]
TTL:   24h (configurable)
```

Sessions survive pod restarts. Shared across all replicas.
Lazy migration: old sessions expire naturally.
