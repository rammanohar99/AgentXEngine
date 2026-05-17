---
title: Archive Index
domain: archive
doc_type: reference
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: historical
retrieval_priority: low
tags: [archive, deprecated, historical, superseded]
---

# Archive

This directory contains deprecated, superseded, and historical documentation.

**These documents are preserved for historical context. They do not reflect
the current state of the system. Do not use them as a reference for current behavior.**

**Related:** [Lifecycle Management](../governance/lifecycle-management.md#deprecation-policy)

---

## What Belongs Here

- Documents superseded by newer versions
- Roadmap items that were abandoned
- Incident postmortems older than 2 years
- Architecture docs for systems that have been retired
- ADRs that have been superseded (note: superseded ADRs stay in `docs/adr/`
  with updated status — they are not moved here)

---

## Archive Structure

```
docs/archive/
  incidents/     — incident postmortems older than 2 years
  roadmap/       — abandoned roadmap items
  architecture/  — retired system documentation
```

---

## Current Archive

No documents archived yet. The system is in active development.

---

## Archival Process

1. Update the document's frontmatter: `status: archived`
2. Add the archival banner at the top of the document
3. Move the file to the appropriate subdirectory here
4. Update all inbound links to note the document is archived
5. Update the index in this README

See [Lifecycle Management](../governance/lifecycle-management.md) for full policy.
