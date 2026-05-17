---
title: AI Retrieval Strategy
domain: governance
doc_type: standard
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [governance, ai-retrieval, rag, semantic-search, agent-navigation, context-optimization]
---

# AI Retrieval Strategy

This document defines how the documentation system is designed for AI agent
retrieval — including coding agents (Cursor, Gemini CLI, Codex), RAG pipelines,
and autonomous engineering agents operating within this codebase.

**Related:** [Metadata Standards](metadata-standards.md) · [Documentation Standards](documentation-standards.md) · [AGENTS.md](../../AGENTS.md)

---

## Retrieval Entrypoints

AI agents entering this codebase should follow this navigation hierarchy:

```
1. AGENTS.md                    — orientation layer, critical rules, doc map
2. docs/README.md               — full documentation index
3. docs/architecture/overview.md — system design, request flow
4. Domain-specific doc          — based on the task at hand
5. ADR                          — if a decision needs justification
6. Incident postmortem          — if a failure pattern needs context
```

**AGENTS.md is the primary entrypoint.** It is designed to be read in full
(~150 lines) and provides enough orientation to navigate to any other document.
It should never grow beyond 200 lines.

---

## Navigation Flow by Task Type

| Task | Primary Doc | Secondary Docs |
|---|---|---|
| Modify agent runtime | `architecture/agent-runtime.md` | `reliability/principles.md`, ADR-001, ADR-002 |
| Modify RAG pipeline | `architecture/rag-pipeline.md` | ADR-004, `performance/overview.md` |
| Modify memory systems | `architecture/memory-systems.md` | ADR-003, `architecture/context-engineering.md` |
| Add a new tool | `tools/reference.md` | `architecture/agent-runtime.md` |
| Debug a production issue | `runbooks/incident-response.md` | Relevant incident postmortem |
| Understand a design decision | `adr/README.md` | Specific ADR |
| Onboard to the codebase | `onboarding/getting-started.md` | `onboarding/engineering-principles.md` |
| Understand reliability rules | `reliability/principles.md` | ADR-001, ADR-002, ADR-003 |
| Understand observability | `observability/overview.md` | `evaluation/overview.md` |
| Plan future work | `roadmap/` | Relevant architecture doc |

---

## Semantic Isolation Principles

Each document is designed to be semantically isolated — it covers one topic
and one topic only. This is the most important property for retrieval precision.

**Why it matters:** A query about "circuit breaker" should return
`reliability/principles.md` and `adr/002-long-lived-runtime-objects.md` —
not a 1,200-line file that mentions circuit breakers in section 4 of 12.

**Enforcement:**
- One concept per document (see [Documentation Standards](documentation-standards.md))
- Size limits prevent topic sprawl
- Frontmatter `domain` and `tags` enable precise filtering

---

## RAG Indexing Recommendations

### Chunking Strategy

Split documents on `## H2` headings. Each H2 section becomes one chunk.

```
Document: docs/reliability/principles.md
Chunks:
  - "The Fundamental Rule: One Layer Owns Retries" (H2)
  - "Transient vs Permanent Error Classification" (H2)
  - "Circuit Breaker" (H2)
  - "Timeout Ownership" (H2)
  - "Graceful Degradation" (H2)
  - "Fallback Model Strategy" (H2)
  - "Reliability Checklist" (H2)
```

Each chunk is semantically coherent and retrievable independently.

### Chunk Metadata

Prepend to each chunk:
```
[Document: {title}] [Domain: {domain}] [Type: {doc_type}]
```

This ensures that even when a chunk is retrieved without its parent document,
the agent knows what system it belongs to.

### Filtering Rules

Exclude from active indexes:
- `status: deprecated`
- `status: archived`
- `stability: historical` (unless the query is explicitly historical)

Weight by:
- `retrieval_priority: high` → 1.5× score boost
- `retrieval_priority: medium` → 1.0× score
- `retrieval_priority: low` → 0.7× score

### Index Separation

Maintain separate indexes for:
- `active` documents (status: active, draft)
- `historical` documents (status: deprecated, archived, stability: historical)

Agents should query the active index by default. Historical index is for
explicit "why was this decided?" queries.

---

## Context Minimization Strategy

AI agents have finite context windows. The documentation system is designed
to minimize the tokens needed to answer any question.

**Principle:** An agent should be able to answer most questions by reading
2–3 documents totaling 400–600 lines, not by reading a 1,200-line monolith.

**How this is achieved:**
1. Small, focused documents (150–250 lines each)
2. Cross-links guide agents to related docs without duplicating content
3. AGENTS.md provides orientation in ~150 lines
4. ADRs provide decision context without repeating architecture content
5. Incidents provide failure context without polluting architecture docs

---

## Duplicate Content Prevention

Duplicate content is the primary enemy of retrieval precision. When the same
concept appears in 3 files, a query returns all 3 — forcing the agent to
deduplicate and reconcile, consuming tokens and introducing confusion.

**Rules:**
- Each concept has exactly one authoritative document
- Other documents reference it, they do not repeat it
- The retry amplification case study lives in `adr/001` and is referenced
  (not repeated) in `reliability/principles.md`
- Code examples live in one place and are linked from others

**Detecting duplicates:** If you find yourself writing content that already
exists in another document, stop. Add a cross-reference instead.

---

## AGENTS.md Design Constraints

`AGENTS.md` is the most-read document in the repository. It must be:

- **Complete enough** to orient any agent in < 200 lines
- **Sparse enough** to not duplicate architecture docs
- **Stable enough** to not require frequent updates
- **Structured** so agents can scan it quickly

It must contain:
- System identity (3–5 lines)
- Documentation map (links to all major docs)
- Critical rules summary (5–7 rules, each 2–3 lines with ADR link)
- Repository structure (directory tree)
- Phase status table

It must NOT contain:
- Full reliability principles (link to `reliability/principles.md`)
- Full architecture descriptions (link to `architecture/`)
- Code examples (link to `examples/`)
- Roadmap details (link to `roadmap/`)

---

## Naming Conventions

File names must be:
- Lowercase, hyphenated
- Descriptive of the single topic covered
- Prefixed with a number for ordered sequences (ADRs, incidents)

```
# Good
docs/reliability/principles.md
docs/adr/001-provider-layer-owns-retries.md
docs/incidents/INC-001-retry-amplification.md

# Bad
docs/reliability/RELIABILITY_PRINCIPLES.md
docs/adr/retry-decision.md
docs/incidents/retry-bug.md
```

---

## Codebase Copilot Integration

For AI coding assistants (Cursor, GitHub Copilot, Gemini CLI) operating in
this codebase:

1. The assistant should read `AGENTS.md` at session start
2. Before modifying `packages/agents/`, read `docs/architecture/agent-runtime.md`
3. Before modifying `packages/rag/`, read `docs/architecture/rag-pipeline.md`
4. Before any reliability-sensitive change, read `docs/reliability/principles.md`
5. Before any change to retry logic, read `docs/adr/001-provider-layer-owns-retries.md`
6. Before any change to object lifecycle, read `docs/adr/002-long-lived-runtime-objects.md`

The `docs/architecture/invariants.md` document contains non-negotiable boundaries
that must never be violated. Read it before any architectural change.
