---
title: Concurrent Reranker Trace
domain: examples
doc_type: example
status: active
owner: rag-pipeline
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: medium
tags: [trace, rag, reranker, concurrency, performance]
---

# Concurrent Reranker Trace

**Related:** [ADR-004](../adr/004-concurrent-reranker.md) · [Performance Overview](../performance/overview.md)

This trace demonstrates the behavior of the concurrent reranker (`packages/rag/reranker.py`),
which uses `asyncio.gather` and an `asyncio.Semaphore` to score all retrieved chunks
simultaneously, rather than sequentially.

## The Trace

```json
{"event": "http_request", "method": "POST", "path": "/api/v1/chat", "correlation_id": "f5e9d2...a1b"}
{"event": "agent_stream_start", "session_id": "sess_123", "run_id": "run_456", "correlation_id": "f5e9d2...a1b", "otel_trace_id": "032x..."}
{"event": "tool_execution_start", "tool_name": "retrieve_documents", "call_id": "call_789"}
{"event": "pgvector_search_complete", "results_found": 15, "latency_ms": 120.5}

// Concurrent reranking begins. The LLM provider is invoked multiple times in parallel.
// Notice that the start times are identical (or within milliseconds), 
// and the completion times depend on the LLM provider's response latency, not a sequence.
{"event": "metric.llm_call", "model": "gemini-1.5-flash", "latency_ms": 1100.2, "correlation_id": "f5e9d2...a1b"}
{"event": "metric.llm_call", "model": "gemini-1.5-flash", "latency_ms": 1150.8, "correlation_id": "f5e9d2...a1b"}
{"event": "metric.llm_call", "model": "gemini-1.5-flash", "latency_ms": 1200.1, "correlation_id": "f5e9d2...a1b"}
{"event": "metric.llm_call", "model": "gemini-1.5-flash", "latency_ms": 1120.4, "correlation_id": "f5e9d2...a1b"}
{"event": "metric.llm_call", "model": "gemini-1.5-flash", "latency_ms": 1180.7, "correlation_id": "f5e9d2...a1b"}

// The total latency of the reranker operation matches the *longest* individual LLM call,
// plus a few milliseconds of overhead, rather than the *sum* of all calls.
{"event": "metric.rag_reranker", "query_length": 45, "input_count": 15, "output_count": 5, "latency_ms": 1202.3, "correlation_id": "f5e9d2...a1b"}

{"event": "tool_execution_complete", "tool_name": "retrieve_documents", "success": true, "duration_ms": 1325.0}
{"event": "metric.rag_retrieval", "query_length": 45, "results_count": 5, "latency_ms": 1325.0, "reranked": true, "correlation_id": "f5e9d2...a1b"}
```

## Key Observations

1. **Concurrent LLM Calls:** Multiple `metric.llm_call` events are generated, but the total `metric.rag_reranker` latency (1202.3ms) is slightly higher than the longest individual LLM call (1200.1ms), not the sum (~5700ms).
2. **Correlation ID propagation:** The `correlation_id` matches across the HTTP request, the agent stream start, the LLM calls, and the final metrics.
3. **Semaphore Bound:** The concurrency is bounded by `max_concurrent` (default 5). If `top_k=15` and `max_concurrent=5`, you would see them complete in 3 distinct "waves" or batches, resulting in ~3.6s total latency instead of 18s.
