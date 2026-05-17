---
title: Documentation Contribution Guidelines
domain: governance
doc_type: standard
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: medium
tags: [governance, contribution, process, quality]
---

# Documentation Contribution Guidelines

How to add, update, and review documentation in this repository.

**Related:** [Documentation Standards](documentation-standards.md) · [Lifecycle Management](lifecycle-management.md) · [Metadata Standards](metadata-standards.md)

---

## When to Write Documentation

Write documentation when:
- You add a new system or subsystem
- You make a significant architectural decision
- You discover a production failure mode
- You fix a bug that reveals a non-obvious constraint
- You complete a phase of the roadmap
- You write a runbook procedure that doesn't exist yet

Do not write documentation when:
- The code is self-explanatory
- You're documenting implementation details that belong in code comments
- You're duplicating content that already exists elsewhere

---

## Adding a New Document

1. **Choose the right location** using the table in [Documentation Standards](documentation-standards.md#what-belongs-where)

2. **Copy the appropriate template:**
   - Architecture doc: use the structure in `docs/architecture/overview.md` as a model
   - ADR: use the template in `docs/adr/README.md`
   - Incident: use `docs/incidents/TEMPLATE.md`
   - Runbook: use `docs/runbooks/incident-response.md` as a model

3. **Add frontmatter** following [Metadata Standards](metadata-standards.md)

4. **Write the document** following [Documentation Standards](documentation-standards.md)

5. **Add cross-references:**
   - Add a **Related:** line at the top of the new document
   - Add a link to the new document from related existing documents
   - Add the document to `docs/README.md`
   - If it's an ADR, add it to `docs/adr/README.md`
   - If it's an incident, add it to `docs/incidents/README.md`

6. **Update AGENTS.md** if the document is critical-path for agent navigation

---

## Updating an Existing Document

1. Update the content
2. Update `last_reviewed` in the frontmatter to today's date
3. If the change is significant, note it in a comment or PR description
4. Check that all cross-references are still accurate

---

## Writing an ADR

ADRs are written when a significant architectural decision is made.
"Significant" means: the decision has lasting consequences, affects multiple
components, or would be non-obvious to a future engineer.

ADR checklist:
- [ ] Assign the next sequential number
- [ ] Write the Context section — what problem motivated this?
- [ ] Write the Decision section — what was decided, precisely?
- [ ] Write the Consequences section — both positive and negative
- [ ] Write the Alternatives Considered section — what else was evaluated?
- [ ] Add the ADR to `docs/adr/README.md`
- [ ] Link the ADR from the relevant architecture doc
- [ ] Link the ADR from AGENTS.md critical rules if it's a safety-critical decision

ADRs are immutable after acceptance. Do not edit an accepted ADR.
If the decision changes, write a new ADR that supersedes the old one.

---

## Writing an Incident Postmortem

Postmortems are written after any production incident or significant bug discovery.

Postmortem checklist:
- [ ] Use `docs/incidents/TEMPLATE.md`
- [ ] Assign the next sequential INC number
- [ ] Complete all required sections (timeline, impact, root cause, etc.)
- [ ] Link to the relevant ADR if one was created as a result
- [ ] Add to `docs/incidents/README.md`
- [ ] Link from the relevant runbook
- [ ] Link from the relevant architecture doc if it changes the design

Postmortems are immutable after publication. Do not edit a published postmortem.

---

## Deprecating a Document

When a document is superseded:

1. Update frontmatter: `status: deprecated`, add `superseded_by`
2. Add the deprecation banner at the top of the document
3. Update all inbound links to point to the new document
4. Schedule archival after 90 days

---

## Review Checklist

Before merging any documentation change:

- [ ] Frontmatter is complete and valid
- [ ] Document size is within limits
- [ ] One concept per document (no topic sprawl)
- [ ] All cross-references are accurate and use relative paths
- [ ] No content is duplicated from another document
- [ ] `last_reviewed` is updated
- [ ] Document is added to the appropriate index (`docs/README.md`, `docs/adr/README.md`, etc.)
- [ ] AGENTS.md is updated if this is a critical-path document

---

## Documentation Debt

Documentation debt accumulates when:
- Code changes without documentation updates
- Roadmap items are completed without graduating to architecture docs
- Incidents occur without postmortems
- Architectural decisions are made without ADRs

Track documentation debt the same way you track technical debt.
It has the same compounding cost.
