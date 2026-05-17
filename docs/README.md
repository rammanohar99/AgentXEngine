---
title: Documentation Index
domain: governance
doc_type: reference
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [index, navigation, documentation-map]
---

# Documentation Index

Complete map of all documentation in this repository.

**Start here:** [AGENTS.md](../AGENTS.md) — orientation for AI agents and new engineers.

---

## Architecture

| Document | Description | Owner |
|---|---|---|
| [Overview](architecture/overview.md) | System design, request flow, data flow, key decisions | platform-engineering |
| [Agent Runtime](architecture/agent-runtime.md) | ReAct loop, planner, executor, orchestrator, lifecycle rules | agent-runtime |
| [RAG Pipeline](architecture/rag-pipeline.md) | Ingestion, chunking, embedding, retrieval, reranking | rag-pipeline |
| [Memory Systems](architecture/memory-systems.md) | Memory types, summarization, failure isolation | memory-systems |
| [Context Engineering](architecture/context-engineering.md) | Token budget, truncation, memory injection | agent-runtime |
| [Invariants](architecture/invariants.md) | Non-negotiable architectural boundaries (read before any change) | platform-engineering |

## Reliability

| Document | Description | Owner |
|---|---|---|
| [Principles](reliability/principles.md) | Retry ownership, circuit breaker, timeouts, graceful degradation | agent-runtime |

## Observability

| Document | Description | Owner |
|---|---|---|
| [Overview](observability/overview.md) | Four pillars, structured logging, correlation IDs, metric events | observability |

## Evaluation

| Document | Description | Owner |
|---|---|---|
| [Overview](evaluation/overview.md) | LLM-as-judge, trajectory evaluation, hallucination detection | observability |

## Performance

| Document | Description | Owner |
|---|---|---|
| [Overview](performance/overview.md) | Latency hierarchy, benchmarks, optimization targets | platform-engineering |

## Tools

| Document | Description | Owner |
|---|---|---|
| [Reference](tools/reference.md) | All tools, parameters, security boundaries, adding new tools | agent-runtime |

## Infrastructure

| Document | Description | Owner |
|---|---|---|
| [Overview](infrastructure/overview.md) | Docker Compose, Alembic, Celery, Cloud Run, CI/CD | infrastructure |

## Architectural Decision Records

| ADR | Title | Incident |
|---|---|---|
| [ADR-001](adr/001-provider-layer-owns-retries.md) | Provider Layer Owns Retries | [INC-001](incidents/INC-001-retry-amplification.md) |
| [ADR-002](adr/002-long-lived-runtime-objects.md) | Long-Lived Runtime Objects | [INC-002](incidents/INC-002-circuit-breaker-lifecycle.md) |
| [ADR-003](adr/003-graceful-memory-degradation.md) | Graceful Memory Degradation | [INC-003](incidents/INC-003-memory-summarization-cascade.md) |
| [ADR-004](adr/004-concurrent-reranker.md) | Concurrent Reranker Scoring | [INC-004](incidents/INC-004-reranker-sequential-latency.md) |
| [ADR-005](adr/005-evaluation-in-hot-path.md) | Evaluation in the Hot Path | [INC-005](incidents/INC-005-evaluator-not-wired.md) |

## Incidents

| Incident | Title | Severity |
|---|---|---|
| [INC-001](incidents/INC-001-retry-amplification.md) | Retry Amplification in LLM Call Stack | High |
| [INC-002](incidents/INC-002-circuit-breaker-lifecycle.md) | Circuit Breaker Reset on Every Request | High |
| [INC-003](incidents/INC-003-memory-summarization-cascade.md) | Memory Summarization Failure Cascading to Agent Run | Medium |
| [INC-004](incidents/INC-004-reranker-sequential-latency.md) | Sequential Reranker Adding 5-10s to RAG Queries | Medium |
| [INC-005](incidents/INC-005-evaluator-not-wired.md) | Evaluator Built but Never Called | Low |

## Roadmap

| Document | Phase | Status |
|---|---|---|
| [Production State Management](roadmap/phase-07-production-state.md) | 7 | 🔲 Next |
| [Event-Sourced Runtime](roadmap/phase-08-event-sourced-runtime.md) | 8 | 🔲 Planned |
| [Execution DAG Engine](roadmap/phase-09-dag-engine.md) | 9 | 🔲 Planned |
| [Advanced Evaluation Platform](roadmap/phase-10-evaluation-platform.md) | 10 | 🔲 Planned |
| [Performance Observatory](roadmap/phase-11-performance-observatory.md) | 11 | 🔲 Planned |
| [Agent Replay and Debugging](roadmap/phase-12-replay-debugging.md) | 12 | 🔲 Planned |
| [Context Engineering System](roadmap/phase-13-context-engineering.md) | 13 | 🔲 Planned |
| [Browser and Sandbox Agents](roadmap/phase-14-browser-sandbox.md) | 14 | 🔲 Planned |
| [Policy and Governance Engine](roadmap/phase-15-governance-engine.md) | 15 | 🔲 Planned |

## Examples

| Document | Description |
|---|---|
| [Successful Agent Run](examples/successful-agent-run.md) | Full 3-step ReAct trace with latency breakdown |
| [Circuit Breaker Trip](examples/circuit-breaker-trip.md) | LLM degradation → circuit opens → recovery |
| [RAG Query Flow](examples/rag-query-flow.md) | Embed → retrieve → rerank → inject |
| [Memory Retrieval Flow](examples/memory-retrieval-flow.md) | All 4 memory types assembled into context |
| [Graceful Degradation](examples/graceful-degradation.md) | Redis down → fallbacks → run succeeds |

## Onboarding

| Document | Description |
|---|---|
| [Getting Started](onboarding/getting-started.md) | Setup, orientation, common tasks |
| [Engineering Principles](onboarding/engineering-principles.md) | Rules, coding standards, operational constitution |

## Runbooks

| Document | Description |
|---|---|
| [Incident Response](runbooks/incident-response.md) | LLM degradation, high latency, Redis failures, empty responses |

## Governance

| Document | Description |
|---|---|
| [Documentation Standards](governance/documentation-standards.md) | Size limits, required sections, heading conventions |
| [Lifecycle Management](governance/lifecycle-management.md) | Lifecycle classes, staleness, deprecation, archival |
| [Ownership Model](governance/ownership-model.md) | Who owns what and what that means |
| [Metadata Standards](governance/metadata-standards.md) | Frontmatter fields, allowed values, RAG chunking |
| [Retrieval Strategy](governance/retrieval-strategy.md) | AI agent navigation, RAG indexing, context minimization |
| [Contribution Guidelines](governance/contribution-guidelines.md) | How to add, update, and review documentation |

## Archive

| Document | Description |
|---|---|
| [Archive Index](archive/README.md) | Deprecated and historical documents |
