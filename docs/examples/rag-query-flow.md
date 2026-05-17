---
title: "Example: RAG Query Flow"
domain: example
doc_type: example
status: active
owner: rag-pipeline
last_reviewed: 2026-05-18
stability: operational
retrieval_priority: medium
tags: [example, rag, retrieval, embedding, reranking, trace, latency]
related_adrs: [ADR-004]
related_incidents: [INC-004]
---

# Example: RAG Query Flow

A complete trace of a `retrieve_documents` tool call — from query embedding
through vector search, reranking, and context injection.

**Related:** [RAG Pipeline](../architecture/rag-pipeline.md) · [Performance Overview](../performance/overview.md) · [INC-004](../incidents/INC-004-reranker-sequential-latency.md)

---

## Setup

- **Query:** "How does the chunker handle oversized paragraphs?"
- **top_k:** 5
- **Reranking:** enabled (concurrent via `asyncio.gather`)
- **Documents indexed:** 47 chunks across 8 documents

---

## Event Flow

```
[T+0ms]    TOOL CALL: retrieve_documents
           → query="How does the chunker handle oversized paragraphs?"
           → top_k=5

[T+1ms]    EMBED query
           → POST text-embedding-004 (single vector)

[T+187ms]  EMBEDDING received
           → vector: 768 dimensions
           → latency: 186ms

[T+188ms]  VECTOR SEARCH (pgvector IVFFlat cosine similarity)
           → SELECT ... ORDER BY embedding <=> $1 LIMIT 15
           → (retrieve 3× top_k for reranker to work with)

[T+201ms]  SEARCH RESULTS: 15 chunks returned
           → latency: 13ms
           → scores: [0.91, 0.88, 0.85, 0.83, 0.81, 0.79, ...]

[T+202ms]  RERANK: asyncio.gather (5 concurrent LLM calls)
           → scoring chunk 1: "Chunker splits on paragraph boundaries..."
           → scoring chunk 2: "Oversized paragraphs are split on sentence..."
           → scoring chunk 3: "The overlap parameter ensures context..."
           → scoring chunk 4: "max_chunk_size=800 chars..."
           → scoring chunk 5: "Text extraction handles PDF, CSV..."
           (all 5 calls fire simultaneously)

[T+1,489ms] ALL RERANKER SCORES received
           → concurrent latency: 1,287ms (bounded by slowest call)
           → reranked scores: [0.95, 0.92, 0.88, 0.71, 0.43]
           → top 5 selected

[T+1,490ms] ASSEMBLE context
           → 5 chunks, total 2,847 chars
           → metric.rag_retrieval: results_count=5, avg_score=0.778,
             latency_ms=1490, reranked=true

[T+1,491ms] TRUNCATE if needed
           → 2,847 chars < max_tool_output_chars (4,000)
           → no truncation needed

[T+1,492ms] RETURN to agent
           → ToolResult(success=true, output=<5 chunks>, metadata={...})
           → metric.tool_execution: tool=retrieve_documents, latency_ms=1492, success=true
```

---

## Latency Breakdown

| Phase | Duration |
|---|---|
| Query embedding | 186ms |
| pgvector search | 13ms |
| Reranking (5 concurrent) | 1,287ms |
| Assembly + truncation | 2ms |
| **Total** | **1,490ms** |

**Key observation:** Reranking is 86% of total RAG latency even with concurrent execution.
Sequential reranking would have been 5-10s. Concurrent execution reduced it to 1.3s.
See [INC-004](../incidents/INC-004-reranker-sequential-latency.md) for the full story.

---

## Structured Log Output

```json
{"event": "metric.rag_retrieval", "query_length": 52, "results_count": 5, "avg_score": 0.778, "latency_ms": 1490, "reranked": true}
{"event": "metric.tool_execution", "tool_name": "retrieve_documents", "latency_ms": 1492, "success": true, "output_chars": 2847}
```

---

## What Happens Without Concurrent Reranking

For comparison — the sequential version of the same query:

```
Reranking chunk 1: 1,102ms
Reranking chunk 2: 987ms
Reranking chunk 3: 1,234ms
Reranking chunk 4: 1,089ms
Reranking chunk 5: 1,156ms
Total reranking: 5,568ms   ← vs 1,287ms concurrent
Total RAG latency: 5,780ms ← vs 1,490ms concurrent
```

Same cost. 3.9× higher latency. This is why ADR-004 is an invariant (INV-004).
