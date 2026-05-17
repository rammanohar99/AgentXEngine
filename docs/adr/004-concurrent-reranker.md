---
title: "ADR-004: Concurrent Reranker Scoring"
domain: adr
doc_type: adr
status: active
owner: rag-pipeline
last_reviewed: 2026-05-18
stability: historical
retrieval_priority: high
tags: [adr, performance, rag, reranker, concurrency, asyncio, latency]
related_incidents: [INC-004]
---

# ADR-004: Concurrent Reranker Scoring

**Status:** Accepted (Implemented, Drift Remediated)
**Date:** Phase 6
**Phase:** 6

---

## Context

The LLM-based reranker scores each retrieved chunk independently using a separate
LLM call. The original implementation executed these calls sequentially.

For `top_k=5`, this means 5 sequential LLM calls, each taking 1-2 seconds:
```
5 × 1-2s = 5-10 seconds added to every RAG query
```

This is the single largest fixable latency in the RAG pipeline. The scoring calls
are completely independent — each call scores one chunk against the query with no
dependency on the results of other calls. There is no reason to execute them sequentially.

---

## Decision

Reranker scoring MUST use `asyncio.gather` for concurrent execution.

```python
# WRONG — sequential, O(N) latency
for result in results:
    score = await self._score_chunk(query, result.text)

# CORRECT — concurrent, O(1) latency
scores = await asyncio.gather(*[
    self._score_chunk(query, result.text) for result in results
])
```

Total latency is now bounded by the slowest single call, not the sum of all calls.
For `top_k=5`: ~1-2s regardless of N.

---

## Consequences

**Positive:**
- 5-10s → 1-2s for every RAG query with `top_k=5`
- Same API cost — N calls are still made, just concurrently
- No change to the scoring logic or result quality

**Negative:**
- N concurrent LLM calls may increase instantaneous API quota consumption
- Under heavy load, concurrent reranking may trigger rate limiting sooner
  than sequential reranking would

The latency improvement far outweighs the quota risk for typical usage patterns.

---

## Alternatives Considered

**Replace LLM-based reranker with a cross-encoder model (Cohere Rerank, sentence-transformers):**
Better long-term solution — eliminates the LLM dependency and reduces latency further.
Tracked for Phase 11. Concurrent execution is the immediate fix.

**Reduce `top_k` to reduce reranking calls:** Reduces recall quality.
Not an acceptable tradeoff when the latency can be eliminated by concurrency.

**Cache reranking scores:** Queries are rarely identical. Cache hit rate would be low.
Not worth the complexity.
