---
title: Incident Postmortems Index
domain: incident
doc_type: reference
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: operational
retrieval_priority: medium
tags: [incidents, postmortems, reliability, learnings]
---

# Incident Postmortems

This directory contains postmortems for production incidents and significant
bug discoveries. Each postmortem is an immutable record — it is never modified
after publication.

**Related:** [Reliability Principles](../reliability/principles.md) · [Runbooks](../runbooks/incident-response.md) · [ADR Index](../adr/README.md)

---

## Index

| Incident | Title | Phase | Severity | ADR Created |
|---|---|---|---|---|
| [INC-001](INC-001-retry-amplification.md) | Retry Amplification in LLM Call Stack | 6.1 | High | ADR-001 |
| [INC-002](INC-002-circuit-breaker-lifecycle.md) | Circuit Breaker Reset on Every Request | 6.1 | High | ADR-002 |
| [INC-003](INC-003-memory-summarization-cascade.md) | Memory Summarization Failure Cascading to Agent Run | 6.1 | Medium | ADR-003 |
| [INC-004](INC-004-reranker-sequential-latency.md) | Sequential Reranker Adding 5-10s to RAG Queries | 6 | Medium | ADR-004 |
| [INC-005](INC-005-evaluator-not-wired.md) | Evaluator Built but Never Called | 6.1 | Low | ADR-005 |

---

## Severity Definitions

| Severity | Definition |
|---|---|
| Critical | Complete service outage or data loss |
| High | Significant degradation affecting all users, or a reliability failure that could cause an outage under load |
| Medium | Degraded performance or quality affecting some users |
| Low | Correctness issue with no immediate user impact |

---

## Postmortem Template

Use `docs/incidents/TEMPLATE.md` for all new postmortems.

---

## Retention Policy

- Active incidents: this directory
- Incidents older than 2 years: `docs/archive/incidents/`
- Never deleted

See [Lifecycle Management](../governance/lifecycle-management.md#incident-retention-policy).
