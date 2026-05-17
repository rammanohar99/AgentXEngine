---
title: "Phase 13: Context Engineering System"
domain: roadmap
doc_type: roadmap
status: planned
owner: agent-runtime
last_reviewed: 2026-05-18
stability: experimental
retrieval_priority: low
tags: [roadmap, phase-13, context, tokens, compression, semantic, tool-selection]
---

# Phase 13: Context Engineering System

**Status:** 🔲 Planned
**Related:** [Context Engineering](../architecture/context-engineering.md) · [Performance Overview](../performance/overview.md)

---

## Objective

Replace the character-based token heuristic with exact counting, implement
semantic compression of verbose tool outputs, and add adaptive memory injection.

---

## Work Items

### 13.1 Exact Token Counting

Replace `len(text) // 4` heuristic with Vertex AI tokenize API.

```python
async def count_tokens(self, text: str) -> int:
    try:
        response = await self._client.count_tokens(text)
        return response.total_tokens
    except Exception:
        return max(1, len(text) // 4)  # Fallback to heuristic
```

Impact: accurate budget enforcement, especially for code-heavy contexts.

---

### 13.2 Semantic Tool Output Compression

When a tool output is too large for the token budget, compress it semantically
rather than truncating at a character boundary.

```python
# Current — dumb truncation
truncated = output[:max_chars]

# Target — semantic compression
summary = await llm.summarize(output, max_tokens=budget_remaining)
```

Only invoke compression when the output exceeds the budget. Truncation remains
the fallback if the compression LLM call fails.

---

### 13.3 Adaptive Memory Injection

Prioritize memory injection based on semantic relevance to the current query,
not just recency.

```python
# Score each memory entry against the current query
scores = await asyncio.gather(*[
    embed_similarity(query, entry.content) for entry in memory_entries
])
# Inject highest-scoring entries first, within token budget
```

---

### 13.4 Retrieval Positioning

Enforce that RAG context is always positioned immediately before the user message,
not at the top of the system prompt. Recency bias in transformer attention means
the most relevant context should be closest to the query.

---

## Definition of Done

- [ ] Exact token counting via Vertex AI tokenize API
- [ ] Heuristic fallback when tokenize call fails
- [ ] Semantic compression for oversized tool outputs
- [ ] Adaptive memory injection by relevance score
- [ ] RAG context positioning enforced
- [ ] Token budget accuracy measured before/after
