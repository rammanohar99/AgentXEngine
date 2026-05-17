---
title: Documentation Ownership Model
domain: governance
doc_type: standard
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: medium
tags: [governance, ownership, responsibility, review]
---

# Documentation Ownership Model

Every document has an owner. Ownership means: you are responsible for keeping
the document accurate, reviewing it on schedule, and updating it when the
system it describes changes.

**Related:** [Lifecycle Management](lifecycle-management.md) · [Contribution Guidelines](contribution-guidelines.md)

---

## Owner Domains

| Owner | Responsible For |
|---|---|
| `platform-engineering` | Governance docs, onboarding, infrastructure, CI/CD |
| `agent-runtime` | Agent runtime, orchestration, planner, executor, tools |
| `rag-pipeline` | RAG pipeline, chunking, embedding, reranking, retrieval |
| `memory-systems` | All memory types, memory manager, summarization |
| `observability` | Logging, tracing, metrics, evaluation, Langfuse, OTel |
| `infrastructure` | Docker, Cloud Run, Kubernetes, Terraform, Alembic |

---

## Ownership by Document

### Architecture

| Document | Owner |
|---|---|
| `docs/architecture/overview.md` | platform-engineering |
| `docs/architecture/agent-runtime.md` | agent-runtime |
| `docs/architecture/rag-pipeline.md` | rag-pipeline |
| `docs/architecture/memory-systems.md` | memory-systems |
| `docs/architecture/context-engineering.md` | agent-runtime |
| `docs/architecture/invariants.md` | platform-engineering |

### Reliability

| Document | Owner |
|---|---|
| `docs/reliability/principles.md` | agent-runtime |

### Observability

| Document | Owner |
|---|---|
| `docs/observability/overview.md` | observability |

### Evaluation

| Document | Owner |
|---|---|
| `docs/evaluation/overview.md` | observability |

### Performance

| Document | Owner |
|---|---|
| `docs/performance/overview.md` | platform-engineering |

### Infrastructure

| Document | Owner |
|---|---|
| `docs/infrastructure/overview.md` | infrastructure |

### ADRs

ADRs are owned by the engineer who proposed them. Once accepted, they are
immutable — ownership is historical, not active.

### Incidents

Incidents are owned by the engineer who wrote the postmortem. Immutable after publication.

### Roadmap

| Document | Owner |
|---|---|
| All `docs/roadmap/` | platform-engineering |

### Governance

| Document | Owner |
|---|---|
| All `docs/governance/` | platform-engineering |

### Onboarding

| Document | Owner |
|---|---|
| All `docs/onboarding/` | platform-engineering |

---

## Ownership Responsibilities

As a document owner, you are responsible for:

1. **Accuracy:** The document reflects the current state of the system
2. **Review cadence:** Reviewing the document on the schedule defined in [Lifecycle Management](lifecycle-management.md)
3. **Update triggers:** Updating the document when the system it describes changes
4. **Staleness detection:** Adding the stale banner when the document is out of date
5. **Deprecation:** Following the deprecation policy when the document is superseded

---

## Transferring Ownership

When a team member leaves or ownership changes:

1. Update the `owner` field in the document's frontmatter
2. Update this ownership table
3. Notify the new owner of their responsibilities
4. Ensure the new owner has reviewed the document

---

## No-Owner Documents

Documents without a clear owner are a governance risk. They tend to become stale
because no one feels responsible for them.

If you find a document without an owner:
1. Assign yourself as owner if you know the system
2. Add the `owner` field to the frontmatter
3. Update this table

If no one can own a document, it should be archived.
