---
title: Documentation Standards
domain: governance
doc_type: standard
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [governance, standards, documentation, ai-retrieval]
---

# Documentation Standards

This document defines the standards every file in this documentation system must follow.
It exists so that documentation remains useful as the system scales — for human engineers,
AI coding agents, and RAG retrieval pipelines equally.

**Related:** [Lifecycle Management](lifecycle-management.md) · [Metadata Standards](metadata-standards.md) · [Retrieval Strategy](retrieval-strategy.md) · [Contribution Guidelines](contribution-guidelines.md)

---

## Why Standards Matter Here

Documentation in this repository is not decorative. It is part of the runtime
architecture — it is the substrate that AI agents use to navigate the codebase,
the onboarding system for new engineers, and the organizational memory that
prevents known failure modes from recurring.

A document that is too long, semantically mixed, or missing metadata degrades
retrieval quality for every agent that reads it. A document that is stale
actively misleads. Standards prevent both.

---

## Document Size Limits

| Document Type | Target Size | Hard Limit |
|---|---|---|
| Architecture doc | 150–250 lines | 300 lines |
| ADR | 60–100 lines | 150 lines |
| Runbook | 100–200 lines | 250 lines |
| Incident postmortem | 80–150 lines | 200 lines |
| Onboarding guide | 100–200 lines | 250 lines |
| Governance doc | 100–200 lines | 300 lines |
| Roadmap item | 50–100 lines | 150 lines |
| Example/trace | 50–150 lines | 200 lines |

**Why size limits matter for AI retrieval:** A 1,200-line file returned by a
semantic search query forces the agent to process 10× more tokens than necessary.
Smaller, semantically isolated documents produce higher-precision retrieval.

When a document approaches its limit, split it — do not compress it.
Compression loses information. Splitting improves retrieval.

---

## One Concept Per Document

Every document must have a single, clearly bounded topic.

**Good:** `docs/reliability/principles.md` — reliability principles only
**Bad:** A file that covers reliability, performance, AND observability

If you find yourself writing "and also..." in a document, that is a signal to split.

The test: can you describe the document's topic in 10 words or fewer?
If not, it covers too much.

---

## Required Frontmatter

Every document must begin with YAML frontmatter:

```yaml
---
title: Human-readable title
domain: architecture | reliability | observability | evaluation | performance | rag | memory | tools | infrastructure | governance | onboarding | adr | incident | roadmap | example | archive
doc_type: architecture | adr | runbook | incident | standard | guide | reference | example | roadmap | invariant
status: active | draft | deprecated | archived
owner: platform-engineering | agent-runtime | rag-pipeline | memory-systems | observability | infrastructure
last_reviewed: YYYY-MM-DD
stability: evergreen | operational | experimental | historical
retrieval_priority: high | medium | low
tags: [comma, separated, tags]
related_adrs: [ADR-001, ADR-002]   # optional
related_incidents: [INC-001]        # optional
superseded_by: path/to/new.md       # optional, for deprecated docs
---
```

See [Metadata Standards](metadata-standards.md) for field definitions and allowed values.

---

## Required Sections

### All Documents

Every document must have:
1. Frontmatter (YAML, as above)
2. A `# Title` H1 heading matching the frontmatter `title`
3. A **Related:** line immediately after the title, linking to related documents
4. A brief purpose statement (1–3 sentences) before the first section

### Architecture Documents

Must include:
- Purpose statement
- Implementation pointer (`**Implementation:** path/to/file.py`)
- Related ADRs
- Known limitations (if any)

### ADRs

Must follow the standard ADR format defined in [docs/adr/README.md](../adr/README.md):
- Context
- Decision
- Consequences (positive and negative)
- Alternatives Considered

### Runbooks

Must include:
- Symptoms (how to recognize the situation)
- Diagnosis steps (how to confirm)
- Resolution steps (what to do)
- Do not / avoid section
- Related ADRs and incidents

### Incident Postmortems

Must follow the template in [docs/incidents/TEMPLATE.md](../incidents/TEMPLATE.md).

---

## Heading Conventions

```
# H1  — Document title only (one per document)
## H2 — Major sections
### H3 — Subsections
#### H4 — Use sparingly, only for deeply nested reference material
```

Do not use bold text as a substitute for headings.
Do not skip heading levels.

---

## Code Block Standards

All code blocks must specify a language:

```python
# Python example
```

```sql
-- SQL example
```

```bash
# Shell commands
```

```
# Diagrams, flow charts, ASCII art — no language tag
```

---

## Cross-Reference Standards

Use relative paths for all internal links:

```markdown
# Good — relative path
[Reliability Principles](../reliability/principles.md)

# Bad — absolute path
[Reliability Principles](/docs/reliability/principles.md)
```

Every document must link to its related documents in the **Related:** line.
Every ADR reference must use the format `[ADR-NNN](../adr/NNN-title.md)`.
Every incident reference must use the format `[INC-NNN](../incidents/NNN-title.md)`.

---

## Language and Tone

- Write in present tense for current state, future tense for roadmap items
- Use active voice
- Be direct — no filler phrases ("it is worth noting that...")
- Prefer tables over prose for structured comparisons
- Prefer code blocks over prose for technical specifications
- Use **bold** for critical warnings and invariants
- Use `code formatting` for all identifiers, file paths, and commands

---

## What Belongs Where

| Content Type | Location |
|---|---|
| How the system works today | `docs/architecture/` |
| Why a decision was made | `docs/adr/` |
| What to do when something breaks | `docs/runbooks/` |
| What went wrong and what we learned | `docs/incidents/` |
| What we plan to build | `docs/roadmap/` |
| How to get started | `docs/onboarding/` |
| Rules and standards | `docs/governance/` |
| Real execution traces | `docs/examples/` |
| Non-negotiable boundaries | `docs/architecture/invariants.md` |
| Deprecated/superseded content | `docs/archive/` |

When in doubt: if it describes current behavior, it's architecture.
If it explains a past decision, it's an ADR. If it describes a future plan, it's roadmap.
