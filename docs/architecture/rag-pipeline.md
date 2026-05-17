---
title: RAG Pipeline Architecture
domain: architecture
doc_type: architecture
status: active
owner: rag-pipeline
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [rag, chunking, embedding, retrieval, reranking, pgvector, pipeline]
related_adrs: [ADR-004]
related_incidents: [INC-004]
---

# RAG Pipeline Architecture

**Related:** [Architecture Overview](overview.md) · [Performance Overview](../performance/overview.md) · [ADR-004](../adr/004-concurrent-reranker.md) · [INC-004](../incidents/INC-004-reranker-sequential-latency.md)

---

## Pipeline Overview

```
Document arrives (text, PDF, CSV, Excel, markdown)
    ↓
1. Extract text          packages/rag/extractor.py
    ↓
2. Chunk                 packages/rag/chunker.py
    ↓
3. Embed (batched)       packages/rag/embeddings.py
    ↓
4. Store                 app/repositories/document.py → pgvector
    ↓
    ─────────── query time ───────────
    ↓
5. Embed query           packages/rag/embeddings.py
    ↓
6. Retrieve              pgvector cosine similarity search
    ↓
7. Rerank (concurrent)   packages/rag/reranker.py
    ↓
8. Assemble              inject top-K chunks into LLM context
```

---

## Chunking

Documents are split on paragraph boundaries (double newlines) with configurable overlap.
Oversized paragraphs are split on sentence boundaries.

```
max_chunk_size = 800 chars  ≈ 200 tokens
overlap        = 100 chars  ≈ 25 tokens
```

**Why overlap matters:** Without overlap, a sentence split across two chunks loses
context. The end of chunk N and the start of chunk N+1 may be semantically disconnected.
Overlap ensures continuity at boundaries.

**Implementation:** `packages/rag/chunker.py`

---

## Embedding

Embeddings use Vertex AI `text-embedding-004` (768-dimensional vectors).
API calls are batched to minimize round trips, with token-aware batch sizing.

```python
# Token-aware batching — no batch exceeds the API's token limit
batches = _build_token_aware_batches(texts, max_tokens_per_batch=20_000)
for batch in batches:
    embeddings = await client.embed_content(batch)
```

Batch size: up to 250 texts per call.

**Implementation:** `packages/rag/embeddings.py`

---

## Storage (pgvector)

Chunks and embeddings are stored in PostgreSQL with the pgvector extension.

```sql
-- Vector column
embedding vector(768)

-- IVFFlat index for approximate nearest-neighbor search
CREATE INDEX ON document_chunks
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
```

`lists` parameter: `sqrt(row_count)` is a good starting point.
More lists = faster search, lower recall. Fewer lists = slower, higher recall.

---

## Retrieval

Retrieval uses cosine similarity search against the IVFFlat index.
Returns the top-K most similar chunks by vector distance.

---

## Reranking

Vector similarity is a good first pass but not always the best relevance signal.
The reranker applies cross-encoder style scoring to re-order the top-K results.

**Current implementation:** LLM-as-judge (one LLM call per chunk)

### Critical Performance Rule

**The reranker MUST execute scoring concurrently, not sequentially.**

```python
# WRONG — sequential, O(N) latency
for result in results:
    score = await self._score_chunk(query, result.text)
# For top_k=5: 5 × 1-2s = 5-10 seconds per query

# CORRECT — concurrent, O(1) latency
scores = await asyncio.gather(*[
    self._score_chunk(query, result.text) for result in results
])
# For top_k=5: ~1-2s regardless of N (bounded by slowest call)
```

Same cost. N× lower latency. See [ADR-004](../adr/004-concurrent-reranker.md).

**Future:** Replace LLM-based reranker with a dedicated cross-encoder model
(Cohere Rerank API, or a local sentence-transformers cross-encoder) to eliminate
the LLM dependency and reduce latency further.

**Implementation:** `packages/rag/reranker.py`

---

## Context Assembly

Retrieved chunks are injected into the LLM context immediately before the user message.
This positioning is intentional — transformer attention is strongest near the end of
the context window (recency bias). The most relevant context should be closest to the query.

Tool output is truncated before injection to respect the token budget:

```python
truncated = output[:max_tool_output_chars]
notice = f"\n\n[Output truncated at {max_tool_output_chars} chars]"
return truncated + notice
```

The truncation notice tells the LLM that the output was cut, preventing it from
assuming the document ended at the truncation point.

---

## Ingestion Worker

Document ingestion runs as a Celery background task to avoid blocking the API.

```
POST /documents/ingest
  → Create document record (status: PENDING)
  → Enqueue Celery task
  → Return 202 Accepted

Celery worker:
  → Extract text
  → Chunk
  → Embed (batched)
  → Store chunks + embeddings
  → Update document status: COMPLETE
```

**Implementation:** `apps/backend/app/workers/tasks/ingestion.py`

---

## Performance Characteristics

| Operation | Typical Latency |
|---|---|
| Chunker (small doc, ~3KB) | 1 – 5ms |
| Chunker (large doc, ~300KB) | 50 – 200ms |
| Embedding call (batch of 50) | 100 – 500ms |
| pgvector similarity search | 10 – 100ms |
| Reranking (5 sequential LLM calls) | 5,000 – 15,000ms |
| Reranking (5 concurrent LLM calls) | 1,000 – 3,000ms |

The reranker is the dominant latency source in the RAG pipeline.
Concurrent execution is not optional — it is required.
