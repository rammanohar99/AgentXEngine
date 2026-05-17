---
title: Roadmap Index
domain: roadmap
doc_type: roadmap
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: experimental
retrieval_priority: medium
tags: [roadmap, phases, planning, future-systems]
---

# Roadmap

This directory contains planned future capabilities for AI Engineering OS.
Roadmap documents describe what will be built, why, and the key design decisions
involved. They are not architecture docs — they describe intent, not current reality.

**Related:** [Architecture Overview](../architecture/overview.md) · [ADR Index](../adr/README.md)

> **Lifecycle note:** When a roadmap item is implemented, create the architecture doc,
> update the roadmap item status to `implemented`, and link to the new doc.
> See [Lifecycle Management](../governance/lifecycle-management.md#roadmap-lifecycle).

---

## Phase Status

| Phase | Status | Description |
|---|---|---|
| 1–6.1 | ✅ Complete | Full stack, agent runtime, RAG, memory, observability, reliability fixes |
| 7 | 🔲 Next | [Production State Management](phase-07-production-state.md) |
| 8 | 🔲 Planned | [Event-Sourced Runtime](phase-08-event-sourced-runtime.md) |
| 9 | 🔲 Planned | [Execution DAG Engine](phase-09-dag-engine.md) |
| 10 | 🔲 Planned | [Advanced Evaluation Platform](phase-10-evaluation-platform.md) |
| 11 | 🔲 Planned | [Performance Observatory](phase-11-performance-observatory.md) |
| 12 | 🔲 Planned | [Agent Replay and Debugging](phase-12-replay-debugging.md) |
| 13 | 🔲 Planned | [Context Engineering System](phase-13-context-engineering.md) |
| 14 | 🔲 Planned | [Browser and Sandbox Agents](phase-14-browser-sandbox.md) |
| 15 | 🔲 Planned | [Policy and Governance Engine](phase-15-governance-engine.md) |

---

## Current Known Limitations (Inputs to Roadmap)

These are documented limitations in the current system, each with a target phase.

| Limitation | Target Phase |
|---|---|
| In-memory session store — lost on restart, no horizontal scaling | Phase 7 |
| In-memory vector memory — lost on restart, not shared | Phase 7 |
| In-process circuit breakers — independent state per replica | Phase 7 |
| Langfuse and OTel traces not correlated | Phase 7 |
| Duplicate ChatService — two session stores | Phase 7 |
| No execution journal — runs cannot be replayed | Phase 8 |
| Sequential workflow tasks — independent tasks run one at a time | Phase 9 |
| Sequential reranking — 5-10s per RAG query | Phase 11 |
| No trajectory evaluation | Phase 10 |
| No hallucination detection | Phase 10 |
| No regression benchmark dataset | Phase 10 |
| Character-based token counting — inaccurate for code | Phase 13 |
| No prompt caching — static system prompt re-sent every call | Phase 11 |
| No p50/p95/p99 latency tracking | Phase 11 |
