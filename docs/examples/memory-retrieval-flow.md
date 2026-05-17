---
title: "Example: Memory Retrieval and Context Assembly"
domain: example
doc_type: example
status: active
owner: memory-systems
last_reviewed: 2026-05-18
stability: operational
retrieval_priority: medium
tags: [example, memory, context, summarization, vector-memory, trace]
related_adrs: [ADR-003]
related_incidents: [INC-003]
---

# Example: Memory Retrieval and Context Assembly

A trace showing how all four memory types are assembled into the LLM context
for a session with 20 prior turns (past the summarization threshold).

**Related:** [Memory Systems](../architecture/memory-systems.md) · [Context Engineering](../architecture/context-engineering.md) · [INC-003](../incidents/INC-003-memory-summarization-cascade.md)

---

## Setup

- **Session:** `sess_def456`
- **Prior turns:** 20 (threshold is 16 — summarization has run)
- **Summary:** present (covers turns 1–14)
- **Short-term:** turns 15–20 (6 most recent kept verbatim)
- **Long-term facts:** 3 Redis entries
- **Vector memory:** 20 embeddings stored

---

## Memory Assembly Flow

```
[T+0ms]    MemoryManager.get_context(session_id="sess_def456")

[T+1ms]    FETCH short-term memory
           → 6 turns (turns 15–20)
           → 847 chars, ~212 tokens

[T+2ms]    FETCH summary from Redis
           → key: session:sess_def456:summary
           → "User is building a FastAPI backend. They asked about RAG pipeline
              setup, chunking strategies, and embedding batching. Agent explained
              the IVFFlat index configuration and overlap importance."
           → 312 chars, ~78 tokens

[T+3ms]    FETCH long-term facts from Redis
           → key: session:sess_def456:facts
           → ["User prefers Python 3.12", "Project uses Vertex AI", "top_k=5"]
           → 89 chars, ~22 tokens

[T+4ms]    VECTOR MEMORY SEARCH
           → embed current query: "How do I configure the reranker?"
           → cosine similarity against 20 stored turn embeddings
           → top 2 relevant past exchanges retrieved:
             - "User asked about reranker performance" (score: 0.87)
             - "Agent explained LLM-as-judge scoring" (score: 0.81)
           → 423 chars, ~106 tokens

[T+47ms]   ESTIMATE total memory token cost
           → short-term: 212 tokens
           → summary: 78 tokens
           → long-term facts: 22 tokens
           → vector memory: 106 tokens
           → total: 418 tokens

[T+48ms]   CHECK token budget
           → conversation budget: 32,000 tokens
           → system prompt: 847 tokens
           → memory: 418 tokens
           → remaining for conversation: 30,735 tokens
           → no truncation needed

[T+49ms]   ASSEMBLE memory context message
           → role: system
           → content:
             "## Memory Context
              ### Summary of prior conversation
              User is building a FastAPI backend...

              ### Recent conversation
              [turn 15] User: How does embedding batching work?
              [turn 15] Assistant: Batching groups texts...
              ...

              ### Key facts
              - User prefers Python 3.12
              - Project uses Vertex AI
              - top_k=5

              ### Relevant past exchanges
              [recalled] User asked about reranker performance..."

[T+50ms]   RETURN context to AgentRuntime
           → metric.memory_operation: operation=get_context,
             session_id=sess_def456, latency_ms=50, success=true
```

---

## What Happens When Summarization Fails

```
[During record_turn, after turn 16]
  _maybe_summarize() called
  LLM call for summarization → 503 Service Unavailable

  # CORRECT behavior (INV-003)
  except Exception as exc:
      logger.warning("summarization_skipped", error="503 Service Unavailable")
      # Continue — raw turns 1–16 remain in short-term memory
      # Agent run is NOT failed

  metric.memory_operation: operation=summarize, success=false
  # Agent run continues normally with raw turns
```

The agent run succeeds. The user gets their answer. The memory is slightly
larger than optimal (raw turns instead of summary) but fully functional.
See [INC-003](../incidents/INC-003-memory-summarization-cascade.md).

---

## Structured Log Output

```json
{"event": "metric.memory_operation", "operation": "get_context", "session_id": "sess_def456", "latency_ms": 50, "success": true}
{"event": "metric.context_budget", "estimated_tokens": 1265, "max_tokens": 32000, "utilization_pct": 3.95, "truncated": false}
```
