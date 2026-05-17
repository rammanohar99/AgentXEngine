---
title: AGENTS.md — Engineering Navigation Index
domain: governance
doc_type: guide
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [navigation, orientation, agents, entrypoint, critical-rules]
---

# AI Engineering OS — Agent Navigation Index

**This is the primary entrypoint for AI agents and new engineers.**

Read this file first. It orients you in ~150 lines, then links to the right
document for any task. Do not add deep implementation content here — link to it.

---

## System Identity

This is an **AI Operating System** — a production runtime infrastructure platform:
- Autonomous agent execution (ReAct loop with circuit breaker + retry + timeout)
- Multi-agent orchestration (1 orchestrator + 5 specialists)
- Retrieval-augmented generation (ingest → chunk → embed → retrieve → rerank → assemble)
- Persistent memory (short-term, long-term Redis, summarized, vector)
- Observable, replayable, recoverable workflows

---

## Before You Write Code

1. Read this file
2. Read [`docs/architecture/overview.md`](docs/architecture/overview.md)
3. Read [`docs/architecture/invariants.md`](docs/architecture/invariants.md) — non-negotiable boundaries
4. Read the domain doc for the area you're changing
5. Check for existing implementations before creating new ones

---

## Navigation by Task

| Task | Read First | Then Read |
|---|---|---|
| Modify agent runtime | [agent-runtime.md](docs/architecture/agent-runtime.md) | [reliability/principles.md](docs/reliability/principles.md), ADR-001, ADR-002 |
| Modify RAG pipeline | [rag-pipeline.md](docs/architecture/rag-pipeline.md) | ADR-004, [performance/overview.md](docs/performance/overview.md) |
| Modify memory systems | [memory-systems.md](docs/architecture/memory-systems.md) | ADR-003, [context-engineering.md](docs/architecture/context-engineering.md) |
| Add a tool | [tools/reference.md](docs/tools/reference.md) | [invariants.md](docs/architecture/invariants.md) |
| Debug a production issue | [runbooks/incident-response.md](docs/runbooks/incident-response.md) | Relevant incident postmortem |
| Understand a design decision | [adr/README.md](docs/adr/README.md) | Specific ADR |
| Onboard to the codebase | [onboarding/getting-started.md](docs/onboarding/getting-started.md) | [engineering-principles.md](docs/onboarding/engineering-principles.md) |
| Plan future work | [roadmap/README.md](docs/roadmap/README.md) | Relevant phase doc |

---

## Critical Rules

These encode production failures. Violating them reintroduces known failure modes.

**INV-001 — Provider layer owns retries**
`VertexAIService` is the only layer that may retry LLM calls. No layer above it
adds its own retry loop. Nested retries = 9 API calls per logical call under load.
→ [ADR-001](docs/adr/001-provider-layer-owns-retries.md) · [INC-001](docs/incidents/INC-001-retry-amplification.md)

**INV-002 — Circuit breakers are long-lived**
`AgentRuntime` is a module-level singleton. Never create it per-request.
A per-request circuit breaker resets to CLOSED on every call — zero protection.
→ [ADR-002](docs/adr/002-long-lived-runtime-objects.md) · [INC-002](docs/incidents/INC-002-circuit-breaker-lifecycle.md)

**INV-003 — Memory failures do not fail agent runs**
All memory operations are wrapped in try/except. Failures are logged as warnings.
Execution continues with whatever memory state is available.
→ [ADR-003](docs/adr/003-graceful-memory-degradation.md) · [INC-003](docs/incidents/INC-003-memory-summarization-cascade.md)

**INV-004 — Reranker scoring is concurrent**
Use `asyncio.gather` for all reranker scoring calls. Sequential scoring adds
5-10s per RAG query. The calls are independent — there is no reason to serialize.
→ [ADR-004](docs/adr/004-concurrent-reranker.md) · [INC-004](docs/incidents/INC-004-reranker-sequential-latency.md)

**INV-005 — Evaluation never blocks the user response**
`AgentEvaluator.evaluate_response()` is called via `asyncio.create_task` after
every agent run. It must not be awaited in the response path.
→ [ADR-005](docs/adr/005-evaluation-in-hot-path.md) · [INC-005](docs/incidents/INC-005-evaluator-not-wired.md)

**INV-006 — All runtime actions emit telemetry**
Every operation emits `metric.*` log events on both success AND failure paths.

**INV-007 — Correlation IDs flow through all operations**
`correlation_id` from `CorrelationIDMiddleware` appears in all logs, spans, and metrics.

**INV-008 — No new unbounded in-memory state in production paths**
New shared state uses Redis. In-process dicts are acceptable only with documented
eviction policy and explicit acknowledgment of the scaling limitation.

Full invariant list: [`docs/architecture/invariants.md`](docs/architecture/invariants.md)

---

## Repository Structure

```
apps/
  backend/          FastAPI — API layer, services, Celery workers
  frontend/         React + TypeScript — chat UI, streaming

packages/
  agents/           Runtime core: ReAct loop, planner, executor, orchestrator
  rag/              RAG pipeline: chunking, embedding, reranking, retrieval
  memory/           Short/long/summarized/vector memory systems
  observability/    Langfuse tracing, OpenTelemetry, evaluation, metrics
  workflows/        Multi-agent workflow engine (DAG executor)
  tools/            Tool implementations
  shared/           Shared types and utilities

infrastructure/
  docker/           Service init scripts
  k8s/              Kubernetes manifests
  terraform/        Infrastructure as code

docs/               Full documentation system (see docs/README.md)
```

---

## Documentation Map

| Section | Index |
|---|---|
| Architecture | [docs/architecture/](docs/architecture/overview.md) |
| Reliability | [docs/reliability/](docs/reliability/principles.md) |
| Observability | [docs/observability/](docs/observability/overview.md) |
| Evaluation | [docs/evaluation/](docs/evaluation/overview.md) |
| Performance | [docs/performance/](docs/performance/overview.md) |
| Tools | [docs/tools/](docs/tools/reference.md) |
| Infrastructure | [docs/infrastructure/](docs/infrastructure/overview.md) |
| ADRs | [docs/adr/](docs/adr/README.md) |
| Incidents | [docs/incidents/](docs/incidents/README.md) |
| Roadmap | [docs/roadmap/](docs/roadmap/README.md) |
| Examples | [docs/examples/](docs/examples/README.md) |
| Onboarding | [docs/onboarding/](docs/onboarding/getting-started.md) |
| Runbooks | [docs/runbooks/](docs/runbooks/incident-response.md) |
| Governance | [docs/governance/](docs/governance/documentation-standards.md) |
| Full index | [docs/README.md](docs/README.md) |

---

## Phase Status

| Phase | Status | Description |
|---|---|---|
| 1–6.1 | ✅ Complete | Full stack, agent runtime, RAG, memory, observability, reliability fixes |
| 7 | 🔲 Next | Redis sessions, distributed circuit breaker, trace correlation |
| 8 | 🔲 Planned | Event-sourced runtime, execution journal, replayability |
| 9 | 🔲 Planned | DAG workflow engine, parallel task execution |
| 10 | 🔲 Planned | Advanced evaluation: trajectory, hallucination, regression benchmarks |
| 11 | 🔲 Planned | Performance observatory: p99 tracking, concurrent reranker, prompt caching |
| 12 | 🔲 Planned | Agent replay UI, context inspector, memory inspector |
| 13 | 🔲 Planned | Context engineering: exact token counting, semantic compression |
| 14 | 🔲 Planned | Browser agents, Docker sandbox execution |
| 15 | 🔲 Planned | Policy and governance engine, approval workflows |
