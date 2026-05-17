---
title: Metadata Standards
domain: governance
doc_type: standard
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [governance, metadata, frontmatter, ai-retrieval, rag]
---

# Metadata Standards

Every document in this system carries structured YAML frontmatter.
This metadata serves three audiences simultaneously: human engineers navigating
the docs, AI agents retrieving context, and RAG pipelines indexing content.

**Related:** [Documentation Standards](documentation-standards.md) · [Retrieval Strategy](retrieval-strategy.md)

---

## Why Metadata Matters for AI Retrieval

When an AI agent or RAG pipeline retrieves a document, it receives the full text.
Without metadata, the agent must infer the document's purpose, freshness, and
authority from the content alone — which is slow and error-prone.

With metadata, the retrieval system can:
- Filter by `domain` to narrow results to the relevant subsystem
- Filter by `status: active` to exclude deprecated content
- Rank by `retrieval_priority` to surface the most important docs first
- Filter by `stability: evergreen` to exclude experimental content
- Use `tags` for semantic clustering
- Use `related_adrs` to automatically surface decision context

---

## Required Fields

Every document must include all required fields.

### `title`
Human-readable document title. Must match the H1 heading.

```yaml
title: Agent Runtime Architecture
```

### `domain`
The primary system domain this document belongs to.

Allowed values:
```
architecture | reliability | observability | evaluation | performance |
rag | memory | tools | infrastructure | governance | onboarding |
adr | incident | roadmap | example | archive
```

### `doc_type`
The type of document, which determines its lifecycle class and review cadence.

Allowed values:
```
architecture    — describes how a system works
adr             — architectural decision record
runbook         — operational procedure
incident        — postmortem / root cause analysis
standard        — governance rule or standard
guide           — onboarding or how-to guide
reference       — reference material (tool params, API, config)
example         — execution trace or worked example
roadmap         — planned future capability
invariant       — non-negotiable architectural boundary
```

### `status`
Current lifecycle status of the document.

Allowed values:
```
active      — current, accurate, maintained
draft       — work in progress, not yet authoritative
deprecated  — superseded by another document
archived    — historical record, no longer actively maintained
```

### `owner`
The team responsible for maintaining this document.

Allowed values:
```
platform-engineering | agent-runtime | rag-pipeline |
memory-systems | observability | infrastructure
```

### `last_reviewed`
ISO 8601 date of the last review. Updated whenever the document is reviewed
or significantly updated.

```yaml
last_reviewed: 2026-05-18
```

### `stability`
How stable the content is. Used by retrieval systems to weight results.

Allowed values:
```
evergreen     — stable, changes only with architecture changes
operational   — changes with operational procedures and incidents
experimental  — actively changing, may be inaccurate
historical    — immutable historical record
```

### `retrieval_priority`
How important this document is for AI agent retrieval. High-priority documents
are surfaced first when multiple documents match a query.

Allowed values:
```
high    — critical path documents (architecture, reliability, ADRs)
medium  — supporting documents (runbooks, onboarding, governance)
low     — reference material, examples, archive
```

### `tags`
Semantic tags for clustering and retrieval. Use lowercase, hyphenated.

```yaml
tags: [agent-runtime, react-loop, circuit-breaker, reliability]
```

---

## Optional Fields

### `related_adrs`
List of ADR identifiers that are directly relevant to this document.

```yaml
related_adrs: [ADR-001, ADR-002, ADR-003]
```

### `related_incidents`
List of incident identifiers that are directly relevant to this document.

```yaml
related_incidents: [INC-001, INC-002]
```

### `superseded_by`
Path to the document that supersedes this one. Only present on deprecated docs.

```yaml
superseded_by: docs/architecture/new-runtime.md
```

### `implements_adr`
For architecture docs that implement a specific ADR decision.

```yaml
implements_adr: ADR-004
```

---

## Complete Example

```yaml
---
title: Agent Runtime Architecture
domain: architecture
doc_type: architecture
status: active
owner: agent-runtime
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [agent-runtime, react-loop, planner, executor, orchestrator, circuit-breaker]
related_adrs: [ADR-001, ADR-002, ADR-003]
related_incidents: [INC-001, INC-002]
---
```

---

## Metadata for RAG Chunking

When this documentation is ingested into a RAG pipeline, the frontmatter
should be treated as document-level metadata, not as a retrievable chunk.

Recommended chunking strategy:
- Split on `## H2` headings — each section becomes a chunk
- Prepend the document `title` and `domain` to each chunk for context
- Include `tags` in chunk metadata for filtering
- Use `retrieval_priority` to weight chunk scores
- Exclude `status: deprecated` and `status: archived` documents from active indexes

See [Retrieval Strategy](retrieval-strategy.md) for the full RAG optimization guide.
