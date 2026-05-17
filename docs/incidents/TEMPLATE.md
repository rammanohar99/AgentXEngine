---
title: "INC-NNN: Short Title"
domain: incident
doc_type: incident
status: active
owner: <engineer-who-wrote-this>
last_reviewed: YYYY-MM-DD
stability: historical
retrieval_priority: medium
tags: [incident, <system>, <failure-type>]
related_adrs: []
---

# INC-NNN: Short Title

> **Immutable record.** This postmortem is not modified after publication.
> If new information emerges, write a follow-up incident or update the relevant ADR.

**Severity:** Critical | High | Medium | Low
**Phase:** N
**Status:** Resolved
**ADR Created:** ADR-NNN (if applicable)

---

## Summary

One paragraph. What happened, what was the impact, how was it resolved.

---

## Timeline

| Time | Event |
|---|---|
| T+0 | Incident begins |
| T+Xm | First symptom observed |
| T+Xm | Root cause identified |
| T+Xm | Fix applied |
| T+Xm | Incident resolved |

---

## Impact

- **User impact:** What did users experience?
- **System impact:** What systems were affected?
- **Duration:** How long did the incident last?
- **Blast radius:** How many requests/users were affected?

---

## Root Cause

Precise technical description of what caused the incident.

---

## Contributing Factors

What conditions made this incident possible or worse?

---

## Detection

How was the incident detected? Was it detected by monitoring, a user report,
or discovered during a code audit?

**Observability gap:** Was there a monitoring gap that delayed detection?

---

## Mitigation

What was done to stop the incident?

---

## Resolution

What was the permanent fix?

---

## Prevention

What changes prevent this class of incident from recurring?

- [ ] Code change: description
- [ ] ADR created: ADR-NNN
- [ ] Runbook updated: link
- [ ] Monitoring added: description

---

## Lessons Learned

What did we learn from this incident that applies beyond the immediate fix?

---

## Related

- **ADR:** [ADR-NNN](../adr/NNN-title.md)
- **Runbook:** [Incident Response](../runbooks/incident-response.md)
- **Architecture doc:** [Relevant Doc](../architecture/relevant.md)
