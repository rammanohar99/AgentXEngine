---
title: Documentation Lifecycle Management
domain: governance
doc_type: standard
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [governance, lifecycle, deprecation, archival, stale-docs]
---

# Documentation Lifecycle Management

Every document in this system has a lifecycle. Understanding that lifecycle
prevents stale documentation from misleading engineers and AI agents.

**Related:** [Documentation Standards](documentation-standards.md) · [Ownership Model](ownership-model.md) · [Retrieval Strategy](retrieval-strategy.md)

---

## Document Lifecycle Classes

Documents are classified into seven lifecycle classes. The class determines
how the document evolves, who owns it, and when it expires.

### 1. Evergreen Architecture

**Definition:** Describes how the system fundamentally works. Changes only when
the architecture changes.

**Examples:** `docs/architecture/agent-runtime.md`, `docs/architecture/rag-pipeline.md`,
`docs/architecture/invariants.md`

**Review cadence:** When the described system changes, or quarterly audit.
**Expiry:** Never expires — superseded by a new version when architecture changes.
**Owner:** The team that owns the described system.

### 2. Operational Knowledge

**Definition:** Describes how to operate the system — runbooks, incident response,
deployment procedures.

**Examples:** `docs/runbooks/`, `docs/infrastructure/overview.md`

**Review cadence:** After every incident that reveals a gap. Quarterly otherwise.
**Expiry:** When the operational procedure changes or the system it describes is retired.
**Owner:** Platform engineering / whoever is on-call.

### 3. Incident Learnings

**Definition:** Postmortems and root cause analyses for specific production incidents.

**Examples:** `docs/incidents/INC-001-retry-amplification.md`

**Review cadence:** Never revised after publication (immutable record).
**Expiry:** Never expires — historical record. Move to `docs/archive/incidents/` after 2 years.
**Owner:** The engineer who wrote the postmortem.

### 4. Architectural Decision Records

**Definition:** Records of significant architectural decisions — context, decision, consequences.

**Examples:** `docs/adr/001-provider-layer-owns-retries.md`

**Review cadence:** Never revised after acceptance (immutable record).
**Expiry:** Superseded (not deleted) when the decision is reversed. Status changes to `deprecated`.
**Owner:** The engineer who proposed the ADR.

### 5. Experimental Systems

**Definition:** Documents systems that are in active development or not yet production-ready.

**Examples:** Kubernetes manifests docs, Terraform docs (currently in-progress).

**Review cadence:** Every sprint or milestone.
**Expiry:** Graduates to Evergreen Architecture when the system reaches production.
Archived if the experiment is abandoned.
**Owner:** The team building the system.

### 6. Roadmap

**Definition:** Describes planned future systems and capabilities.

**Examples:** `docs/roadmap/`

**Review cadence:** Every phase boundary. Quarterly otherwise.
**Expiry:** Roadmap items graduate to architecture docs when implemented.
Archived if the plan is abandoned.
**Owner:** Platform engineering / CTO.

### 7. Onboarding Material

**Definition:** Guides for new engineers and AI agents to get oriented.

**Examples:** `docs/onboarding/getting-started.md`, `docs/onboarding/engineering-principles.md`

**Review cadence:** When the system changes significantly. Quarterly otherwise.
**Expiry:** Never expires — updated in place.
**Owner:** Platform engineering.

---

## Staleness Detection

A document is considered stale when any of the following are true:

- `last_reviewed` date is more than 6 months ago (for operational docs)
- `last_reviewed` date is more than 12 months ago (for architecture docs)
- The code it describes has changed significantly since `last_reviewed`
- It references a phase that has been completed but the doc still says "planned"
- It contains a "Known Limitation" that has been fixed but not updated

**Stale document handling:**
1. Add a `> ⚠️ This document may be outdated. Last reviewed: YYYY-MM-DD` banner
2. Open a tracking issue to update it
3. Do not delete — stale docs are better than no docs until updated

---

## Deprecation Policy

When a document is superseded:

1. Update the frontmatter: `status: deprecated`, add `superseded_by: path/to/new.md`
2. Add a banner at the top:
   ```
   > ⚠️ Deprecated. This document has been superseded by [New Document](path/to/new.md).
   ```
3. Move to `docs/archive/` after 90 days
4. Update all inbound links to point to the new document

**Never delete documents.** Deletion breaks links and loses historical context.
Archive instead.

---

## ADR Supersession Rules

When an architectural decision is reversed:

1. Create a new ADR (e.g., ADR-006) that supersedes the old one
2. Update the old ADR's status: `status: deprecated`, `superseded_by: ADR-006`
3. Add a banner to the old ADR linking to the new one
4. Do not modify the old ADR's content — it is an immutable historical record

The old ADR remains in `docs/adr/` (not archived) because it explains the history
of the decision, which is valuable context for understanding the new decision.

---

## Roadmap Lifecycle

Roadmap items follow this lifecycle:

```
Proposed → Planned → In Progress → Implemented → Archived
```

When a roadmap item is implemented:
1. Create or update the architecture doc describing the new system
2. Create an ADR if a significant decision was made
3. Update the roadmap item status to `implemented` and link to the architecture doc
4. Remove the item from active roadmap docs (keep in archive)

When a roadmap item is abandoned:
1. Update status to `abandoned` with a brief explanation
2. Move to `docs/archive/roadmap/`

---

## Incident Retention Policy

Incident postmortems are immutable records. They are never modified after publication.

- Active incidents: `docs/incidents/`
- Incidents older than 2 years: move to `docs/archive/incidents/`
- Never delete incident records

The archive preserves organizational memory. An incident from 3 years ago may
explain why a current architectural constraint exists.

---

## Review Cadence Summary

| Lifecycle Class | Review Trigger | Maximum Age Without Review |
|---|---|---|
| Evergreen Architecture | System change | 12 months |
| Operational Knowledge | Incident or procedure change | 6 months |
| Incident Learnings | Never (immutable) | N/A |
| ADRs | Never (immutable) | N/A |
| Experimental Systems | Sprint/milestone | 3 months |
| Roadmap | Phase boundary | 3 months |
| Onboarding Material | System change | 6 months |
