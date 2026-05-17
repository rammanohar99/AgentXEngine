---
title: "Phase 11: Performance Observatory"
domain: roadmap
doc_type: roadmap
status: planned
owner: platform-engineering
last_reviewed: 2026-05-18
stability: experimental
retrieval_priority: medium
tags: [roadmap, phase-11, performance, p99, latency, prompt-caching, reranker, token-optimization]
---

# Phase 11: Performance Observatory

**Status:** 🔲 Planned
**Related:** [Performance Overview](../performance/overview.md) · [RAG Pipeline](../architecture/rag-pipeline.md) · [ADR-004](../adr/004-concurrent-reranker.md)

---

## Objective

Instrument the system for p50/p95/p99 latency visibility, implement concurrent
reranking, add prompt caching, and reduce token costs through dynamic tool selection.

---

## Work Items

### 11.1 Concurrent Reranker Scoring

The highest-ROI performance fix in the system. Defined in [ADR-004](../adr/004-concurrent-reranker.md).

```python
# Replace sequential loop with concurrent gather
scores = await asyncio.gather(*[
    self._score_chunk(query, result.text) for result in results
])
```

Impact: 5-10s → 1-2s per RAG query with `top_k=5`.

**File:** `packages/rag/reranker.py`

---

### 11.2 p50/p95/p99 Latency Tracking

Add a rolling percentile tracker to all critical paths.

Emit per-request:
```python
logger.info("metric.latency_percentiles",
    operation="agent_run",
    p50_ms=..., p95_ms=..., p99_ms=...)
```

Track: agent run, LLM call, tool execution, RAG retrieval, reranking.

---

### 11.3 Prompt Caching

The system prompt and tool descriptions are static across all requests.
Vertex AI supports cached content for static prefixes.

Steps:
1. Upload static system prompt + tool descriptions as cached content
2. Reference cache key in every LLM call
3. Vertex AI skips re-processing the cached prefix

**Estimated savings:** 30-40% reduction in input token costs.

---

### 11.4 Dynamic Tool Selection

Currently all tool descriptions are included in every LLM call (~500-1000 tokens).

Approach:
1. At each ReAct step, score available tools for relevance to the current task
2. Include only the top-K most relevant tool descriptions
3. Reduces system prompt size by 50-70% for large registries

---

### 11.5 Token Usage Aggregation

Aggregate token usage at the run level:
- Total input tokens per run
- Total output tokens per run
- Cost estimate per run
- Emit as `metric.token_usage` at run completion

---

## Definition of Done

- [ ] Concurrent reranker implemented and benchmarked
- [ ] p50/p95/p99 tracked for all critical paths
- [ ] Prompt caching implemented and cost reduction measured
- [ ] Dynamic tool selection implemented
- [ ] Token usage aggregated per run
- [ ] Benchmark suite updated to cover reranker latency
