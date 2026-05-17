---
title: Architecture Overview
domain: architecture
doc_type: architecture
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [architecture, overview, system-design, request-flow, data-flow]
related_adrs: [ADR-001, ADR-002]
---

# Architecture Overview

**Related:** [Agent Runtime](agent-runtime.md) · [RAG Pipeline](rag-pipeline.md) · [Memory Systems](memory-systems.md) · [Context Engineering](context-engineering.md) · [Invariants](invariants.md)

---

## System Identity

AI Engineering OS is a production runtime infrastructure platform, not a chatbot or RAG demo.

Core capabilities:
- Autonomous agent execution (ReAct loop)
- Multi-agent orchestration (orchestrator + specialists)
- Retrieval-augmented generation (full pipeline)
- Persistent memory management (4 memory types)
- Tool execution with governance and security boundaries
- Observable, replayable, recoverable workflows

---

## Repository Layout

```
apps/
  backend/          FastAPI application
    app/
      api/          Route handlers — thin, validation only
      core/         Infrastructure: database, config, logging, middleware, rate limiting
      models/       SQLAlchemy ORM models
      repositories/ Database access layer (repository pattern)
      schemas/      Pydantic request/response schemas
      services/     Business logic: agent, RAG, Vertex AI
      workers/      Celery tasks: ingestion, memory summarization
  frontend/         React + TypeScript + Tailwind CSS

packages/           Framework-independent domain packages
  agents/           Agent runtime (ReAct loop, planner, executor, orchestrator)
  rag/              RAG pipeline (chunker, embeddings, reranker, retrieval)
  memory/           Memory systems (short/long/summarized/vector)
  observability/    Tracing, evaluation, metrics
  workflows/        Multi-agent workflow engine
  tools/            Tool implementations
  shared/           Shared types and utilities

infrastructure/
  docker/           Service init scripts
  k8s/              Kubernetes manifests
  terraform/        Infrastructure as code
```

**Key design decision:** `packages/` are framework-independent. They have no FastAPI
dependency and use plain dataclasses and protocols. This makes them testable without
the full app stack and reusable in other contexts.

---

## Request Flow

```
User
  → Frontend (React SSE client)
  → FastAPI route handler (validation only)
  → AgentService
      → MemoryManager.get_context()
      → AgentRuntime.run() [ReAct loop]
          → Planner.parse()
          → Executor.execute()
          → ToolRegistry.dispatch()
      → AgentEvaluator.evaluate_response() [async, non-blocking]
  → Langfuse trace
  → SSE stream → Frontend
```

---

## Data Flow

**Document ingestion:**
```
POST /documents/ingest
  → RAGService
  → Chunker (paragraph-aware, overlapping)
  → EmbeddingService (batched, Vertex AI text-embedding-004)
  → pgvector (IVFFlat index)
```

**Semantic search:**
```
POST /documents/search
  → RAGService
  → EmbeddingService (query embedding)
  → pgvector (cosine similarity)
  → Reranker (concurrent LLM scoring)
  → Ranked chunks
```

**Agent retrieval:**
```
retrieve_documents tool
  → RAGService.search()
  → Ranked chunks
  → ContextManager.truncate_tool_output()
  → LLM context injection
```

---

## Key Design Decisions

### Dependency Injection Everywhere

Services receive their dependencies (LLM provider, database session, Redis client)
via constructor injection. No global singletons in business logic.

### Streaming-First

All agent responses stream via SSE. The frontend renders events as they arrive:
reasoning blocks → tool call cards → tool result cards → final answer.

### Graceful Degradation

Every subsystem degrades gracefully when dependencies are unavailable:

| Subsystem | Dependency | Degradation |
|---|---|---|
| Memory summarization | LLM | Skip summarization, keep raw turns |
| Long-term memory | Redis | Fall back to in-process dict |
| Rate limiting | Redis | Fall back to in-process counter |
| Langfuse tracing | Langfuse | Fall back to NoOpTracer |
| Retrieval tool | pgvector | Skip tool registration, log warning |

### One Layer Owns Retries

Only one layer in the call stack may own retry logic for a given operation.
`VertexAIService` owns LLM retries. `AgentRuntime` owns circuit breaker and timeout only.
See [Reliability Principles](../reliability/principles.md) for the full rule and the
retry amplification case study that motivated it.

### Long-Lived Runtime Objects

`AgentRuntime`, `MemoryManager`, and `AgentTracer` are module-level singletons,
lazy-initialized on first use. Circuit breaker state must persist across requests —
a runtime recreated per request provides zero protection.
See [ADR-002](../adr/002-long-lived-runtime-objects.md).

---

## Service Topology (Local)

```
┌─────────────┐     SSE      ┌─────────────┐
│   Frontend  │ ──────────── │   Backend   │
│  React/Vite │              │  FastAPI    │
│  :3000      │              │  :8000      │
└─────────────┘              └──────┬──────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
             ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
             │  PostgreSQL  │ │    Redis    │ │   Celery    │
             │  + pgvector  │ │  sessions  │ │   worker    │
             │  :5432       │ │  :6379     │ │             │
             └─────────────┘ └─────────────┘ └─────────────┘
```

---

## Known Limitations

These are documented, understood limitations — not bugs. Each has a planned fix.

| Limitation | Impact | Fix Phase |
|---|---|---|
| In-memory session store | Sessions lost on restart; no horizontal scaling | Phase 7 |
| In-memory vector memory | Vector memory lost on restart; not shared | Phase 7 |
| In-process circuit breakers | Each replica has independent breaker state | Phase 7 |
| Sequential reranking | 5-10s added to every RAG query with top_k=5 | Phase 11 |
| No execution journal | Runs cannot be replayed or resumed | Phase 8 |
| Sequential workflow tasks | Independent tasks run one at a time | Phase 9 |
| Character-based token counting | Inaccurate for code-heavy contexts | Phase 13 |
| No prompt caching | Static system prompt re-sent on every call | Phase 11 |
| Duplicate ChatService | Two session stores, two code paths | Phase 7 |
| No distributed trace correlation | Langfuse and OTel traces not linked | Phase 7 |
