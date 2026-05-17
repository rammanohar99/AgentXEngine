---
title: Architectural Decision Records Index
domain: adr
doc_type: reference
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [adr, decisions, architecture, index]
---

# Architectural Decision Records

ADRs capture significant architectural decisions — the context, the options
considered, the decision made, and the consequences. They are the authoritative
record of *why* the system is designed the way it is.

Read them before proposing changes to the areas they cover.

**Related:** [Architecture Overview](../architecture/overview.md) · [Invariants](../architecture/invariants.md) · [Incidents Index](../incidents/README.md)

---

## Index

| ADR | Title | Status | Incident |
|---|---|---|---|
| [ADR-001](001-provider-layer-owns-retries.md) | Provider Layer Owns Retries | Accepted | [INC-001](../incidents/INC-001-retry-amplification.md) |
| [ADR-002](002-long-lived-runtime-objects.md) | Long-Lived Runtime Objects | Accepted | [INC-002](../incidents/INC-002-circuit-breaker-lifecycle.md) |
| [ADR-003](003-graceful-memory-degradation.md) | Graceful Memory Degradation | Accepted | [INC-003](../incidents/INC-003-memory-summarization-cascade.md) |
| [ADR-004](004-concurrent-reranker.md) | Concurrent Reranker Scoring | Accepted | [INC-004](../incidents/INC-004-reranker-sequential-latency.md) |
| [ADR-005](005-evaluation-in-hot-path.md) | Evaluation in the Hot Path | Accepted | [INC-005](../incidents/INC-005-evaluator-not-wired.md) |

---

## ADR Format

```markdown
# ADR-NNN: Title

**Status:** Proposed | Accepted | Deprecated | Superseded by ADR-NNN
**Date:** YYYY-MM-DD
**Phase:** N

## Context
## Decision
## Consequences
## Alternatives Considered
```

ADRs are **immutable** after acceptance. To reverse a decision, write a new ADR
that supersedes the old one. Update the old ADR's status field only.

See [Contribution Guidelines](../governance/contribution-guidelines.md#writing-an-adr).
