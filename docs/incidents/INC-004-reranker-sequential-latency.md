---
title: "INC-004: Sequential Reranker Adding 5-10s to RAG Queries"
domain: incident
doc_type: incident
status: active
owner: rag-pipeline
last_reviewed: 2026-05-18
stability: historical
retrieval_priority: medium
tags: [incident, rag, reranker, latency, performance, sequential, concurrent]
related_adrs: [ADR-004]
---

# INC-004: Sequential Reranker Adding 5-10s to RAG Queries

> **Immutable record.** This postmortem is not modified after publication.

**Severity:** Medium
**Phase:** 6 (identified during performance analysis)
**Status:** Resolved (fix defined; implementation tracked in Phase 11)
**ADR Created:** [ADR-004](../adr/004-concurrent-reranker.md)

---

## Summary

The LLM-based reranker executed scoring calls sequentially — one LLM call per
retrieved chunk, each taking 1-2 seconds. For `top_k=5`, this added 5-10 seconds
to every RAG query. The scoring calls are completely independent and could be
executed concurrently with no change to the result. The fix — using `asyncio.gather`
— reduces reranking latency from O(N) to O(1) with no change in cost or quality.

---

## Timeline

| Event | Description |
|---|---|
| Phase 6 analysis | Performance profiling of the RAG pipeline |
| Discovery | Reranker loop found executing sequential `await` calls |
| Measurement | 5 × 1-2s = 5-10s added to every RAG query with top_k=5 |
| Fix defined | `asyncio.gather` identified as the solution |
| ADR | ADR-004 written |
| Status | Fix tracked for Phase 11 implementation |

---

## Impact

- **User impact:** Every RAG query with reranking enabled takes 5-10 seconds longer
  than necessary. For a system where LLM calls already dominate latency, this is
  a significant additional delay.
- **System impact:** The reranker is the highest-latency component in the RAG pipeline,
  exceeding even the primary LLM call in worst cases.
- **Blast radius:** All RAG queries with `top_k > 1` and reranking enabled.

---

## Root Cause

```python
# WRONG — as found in the codebase
async def rerank(self, query: str, results: list[RetrievalResult]) -> list[RetrievalResult]:
    scored = []
    for result in results:
        score = await self._score_chunk(query, result.text)  # Sequential
        scored.append((score, result))
    return [r for _, r in sorted(scored, reverse=True)]
```

Each `_score_chunk()` call makes an independent LLM API call. The calls have no
dependency on each other — each scores one chunk against the query independently.
There is no reason to execute them sequentially.

Sequential execution means total latency = sum of all call latencies.
For `top_k=5` with 1-2s per call: 5-10 seconds.

---

## Contributing Factors

- Sequential iteration is the natural Python pattern — `asyncio.gather` requires
  explicit awareness of concurrency
- No performance benchmark for the reranker at the time of development
- The latency is invisible in unit tests (mocked LLM calls are instant)
- No p95/p99 latency tracking to surface the tail latency impact

---

## Detection

Identified during a manual performance analysis of the RAG pipeline in Phase 6.

**Observability gap:** No benchmark for reranker latency in the benchmark suite.
`metric.rag_retrieval` tracks total retrieval latency but does not break out
reranking time separately.

---

## Resolution

```python
# CORRECT — concurrent execution
async def rerank(self, query: str, results: list[RetrievalResult]) -> list[RetrievalResult]:
    scores = await asyncio.gather(*[
        self._score_chunk(query, result.text) for result in results
    ])
    scored = list(zip(scores, results))
    return [r for _, r in sorted(scored, reverse=True)]
```

Total latency is now bounded by the slowest single call, not the sum of all calls.
For `top_k=5`: ~1-2s regardless of N.

---

## Prevention

- [x] ADR created: [ADR-004](../adr/004-concurrent-reranker.md) — "Concurrent Reranker Scoring"
- [ ] Implementation: `asyncio.gather` in `packages/rag/reranker.py` (Phase 11)
- [ ] Benchmark added: reranker latency in `tests/test_benchmarks.py`
- [ ] Metric added: `reranking_latency_ms` in `metric.rag_retrieval`

---

## Lessons Learned

**Independent async operations should always be concurrent.** The question to ask
before any `for result in results: await ...` loop: "Are these calls independent?"
If yes, use `asyncio.gather`. The latency improvement is always N× with zero cost increase.

**Benchmarks must cover the full pipeline.** The benchmark suite covered chunking
and embedding but not reranking. A benchmark that covers only part of the pipeline
gives a false sense of performance.

**The most fixable performance problem is often the most obvious one.** Sequential
execution of independent async calls is a common pattern that is easy to spot in
code review and easy to fix. It should be caught before it reaches production.

---

## Related

- **ADR:** [ADR-004 — Concurrent Reranker Scoring](../adr/004-concurrent-reranker.md)
- **Architecture:** [RAG Pipeline — Reranking](../architecture/rag-pipeline.md#reranking)
- **Performance:** [Performance Overview — The Reranker Bottleneck](../performance/overview.md#the-reranker-bottleneck)
