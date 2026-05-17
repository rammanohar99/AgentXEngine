---
title: Performance Overview
domain: performance
doc_type: architecture
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [performance, latency, p99, network-bound, reranker, benchmarks, optimization]
related_adrs: [ADR-004]
related_incidents: [INC-004]
---

# Performance Overview

**Related:** [RAG Pipeline](../architecture/rag-pipeline.md) · [Agent Runtime](../architecture/agent-runtime.md) · [ADR-004](../adr/004-concurrent-reranker.md) · [Phase 11 Roadmap](../roadmap/phase-11-performance-observatory.md)

---

## The Fundamental Insight: This Is a Network-Bound System

The dominant latency sources are LLM calls, embedding calls, and reranking —
not CPU operations. This has profound implications for where to invest optimization effort.

**Do not optimize:**
- Planner parsing (sub-millisecond, not a bottleneck)
- Token estimation (character counting, negligible)
- Tool registry lookup (dict lookup, negligible)
- Context manager truncation (string slicing, negligible)

**Do optimize:**
- LLM call count (every extra step costs 1-8 seconds)
- Reranker parallelism (N sequential calls → N concurrent calls)
- Embedding batching (already implemented)
- Prompt caching (static system prompt + tool descriptions)
- Context size (fewer tokens = faster LLM response)

---

## Measured Latency Hierarchy

| Operation | Typical Latency | Bound |
|---|---|---|
| LLM call (Gemini Flash) | 1,000 – 8,000ms | Network |
| LLM call (Gemini Pro) | 2,000 – 30,000ms | Network |
| Embedding call (batch) | 100 – 500ms | Network |
| Reranking (5 sequential LLM calls) | 5,000 – 15,000ms | Network |
| Reranking (5 concurrent LLM calls) | 1,000 – 3,000ms | Network |
| pgvector similarity search | 10 – 100ms | IO |
| Redis operation | 1 – 5ms | IO |
| Chunker (large doc, ~300KB) | 50 – 200ms | CPU |
| Chunker (small doc, ~3KB) | 1 – 5ms | CPU |
| Planner parse | < 0.1ms | CPU |
| Token estimation | < 0.01ms | CPU |

These numbers come from the benchmark suite. Run to reproduce:
```bash
cd apps/backend
pytest tests/test_benchmarks.py --benchmark-only --benchmark-sort=mean
```

---

## ReAct Loop Latency

A 5-step ReAct run with 2s average LLM latency = **10 seconds minimum**.
This is irreducible with sequential execution.

**Optimization strategies:**
1. Reduce steps needed (better planning, better tools)
2. Use faster models for intermediate steps (Flash for reasoning, Pro for synthesis)
3. Parallelize independent tool calls within a single step (future)
4. Cache LLM responses for identical inputs (future)

**Key insight:** Optimizing the planner parser saves < 0.1ms per request.
Reducing one LLM step saves 1,000 – 8,000ms. Focus on the right things.

---

## The Reranker Bottleneck

The LLM-based reranker was previously a major bottleneck due to sequential execution.

```python
# PREVIOUS — sequential, O(N) latency
for result in results:
    score = await self._score_chunk(query, result.text)
# For top_k=5: 5 × 1-2s = 5-10 seconds per query

# CURRENT — concurrent, O(1) latency (Implemented per ADR-004)
scores = await asyncio.gather(*[
    self._score_chunk(query, result.text) for result in results
])
# For top_k=5: ~1-2s regardless of N
```

Same cost. N× lower latency. See [ADR-004](../adr/004-concurrent-reranker.md).

---

## Latency Distribution Thinking

Always think in distributions, not averages.

| Percentile | Meaning |
|---|---|
| p50 (median) | Typical user experience |
| p95 | What 1 in 20 users experiences |
| p99 | What 1 in 100 users experiences — often 5-10× the median |

A system with p50=2s and p99=30s is not a "2-second system."
It is a system that occasionally takes 30 seconds.

**Why p99 matters:** In a system with 1,000 requests/minute, p99 latency
affects 10 users per minute. At scale, tail latency is not rare — it's constant.

**Requirement (Phase 11):** All critical paths must track and emit p50/p95/p99 latency.

---

## First-Token Latency

For streaming responses, **first-token latency** is the primary UX metric.
Users perceive a system as "fast" if they see the first word quickly,
even if the total response takes longer.

`VertexAIService.stream()` records and emits `metric.llm_first_token` with:
- `time_to_first_token_ms`
- `model`
- `correlation_id`

---

## Multi-Agent Orchestration Overhead

Multi-agent orchestration adds latency at every delegation boundary.

```
User request
  → Orchestrator LLM call (1-8s)
  → Delegation decision
  → Specialist LLM call (1-8s)
  → Specialist tool calls (variable)
  → Specialist final answer
  → Orchestrator synthesis LLM call (1-8s)
  → Response
```

A 3-step orchestrated workflow can take 10-30 seconds minimum.
Design workflows to minimize unnecessary delegation.

---

## Performance Roadmap

| Phase | Optimization | Expected Impact |
|---|---|---|
| 11 | p50/p95/p99 latency tracking | Visibility into tail latency |
| 11 | Prompt caching (Vertex AI) | 30-40% reduction in input token costs |
| 11 | Dynamic tool selection | 50-70% reduction in system prompt size |
| 13 | Exact token counting (tokenize API) | More accurate budget enforcement |
| 13 | Semantic compression of tool outputs | Smaller context, faster responses |
