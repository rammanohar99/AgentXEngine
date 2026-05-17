---
title: "INC-003: Memory Summarization Failure Cascading to Agent Run"
domain: incident
doc_type: incident
status: active
owner: memory-systems
last_reviewed: 2026-05-18
stability: historical
retrieval_priority: medium
tags: [incident, memory, summarization, graceful-degradation, cascade]
related_adrs: [ADR-003]
---

# INC-003: Memory Summarization Failure Cascading to Agent Run

> **Immutable record.** This postmortem is not modified after publication.

**Severity:** Medium
**Phase:** 6.1 (discovered during Phase 6 reliability audit)
**Status:** Resolved
**ADR Created:** [ADR-003](../adr/003-graceful-memory-degradation.md)

---

## Summary

Memory summarization makes an LLM call. When that LLM call failed (due to rate
limiting, timeout, or service degradation), the exception propagated up the call
stack and failed the entire agent run. A user asking a question would receive an
error not because the agent failed to answer, but because a background memory
optimization step failed. This is disproportionate impact — the summarization
failure should degrade the memory feature, not crash the agent run.

---

## Timeline

| Event | Description |
|---|---|
| Phase 6 audit | Reliability audit of the memory subsystem |
| Discovery | `_maybe_summarize()` called without try/except in the agent run hot path |
| Analysis | LLM failure in summarization propagates to agent run failure |
| Fix | `_maybe_summarize()` wrapped in try/except with graceful fallback |
| ADR | ADR-003 written to prevent recurrence |

---

## Impact

- **User impact:** During LLM degradation events, users with long conversation
  histories (>16 turns) would receive errors on their requests, even if the
  agent could have answered the question using the raw turns.
- **System impact:** Memory summarization failures amplified the impact of LLM
  degradation events — affecting users who would otherwise be unaffected.
- **Blast radius:** Users with sessions that had reached the summarization threshold
  (16 turns) during any LLM degradation event.

---

## Root Cause

```python
# WRONG — as found in the codebase
async def record_turn(self, session_id, role, content):
    self._short_term.add(session_id, role, content)
    await self._maybe_summarize(session_id)  # No exception handling
    # If _maybe_summarize raises, the entire record_turn call fails
    # Which propagates to the agent run
```

`_maybe_summarize()` makes an LLM call to compress old conversation turns.
This call was not wrapped in exception handling. When the LLM call failed,
the exception propagated through `record_turn()` into the agent run, causing
the entire run to fail.

The summarization step is a background optimization — it compresses old turns
to save context space. If it fails, the agent can still answer the question
using the raw turns. There is no reason to fail the entire run.

---

## Contributing Factors

- No documented rule about subsystem failure isolation at the time of development
- The failure mode is invisible in normal operation (only manifests during LLM degradation)
- The summarization step is in the hot path of every agent run for long sessions
- No test that verifies agent runs succeed when summarization fails

---

## Detection

Discovered during a manual code audit of the memory subsystem in Phase 6.

**Observability gap:** No metric distinguished between "agent run failed due to
LLM error" and "agent run failed due to memory summarization error." Both appeared
as generic agent run failures.

---

## Mitigation

Wrapped `_maybe_summarize()` in try/except with graceful fallback:

```python
# CORRECT — as fixed
async def record_turn(self, session_id, role, content):
    self._short_term.add(session_id, role, content)
    try:
        await self._maybe_summarize(session_id)
    except Exception as exc:
        logger.warning(
            "summarization_skipped",
            session_id=session_id,
            error=str(exc),
        )
        # Continue — raw turns are still available
```

---

## Resolution

All memory operations are now wrapped in try/except with graceful fallback.
Memory failures are logged as warnings, not errors. Agent runs continue with
whatever memory state is available.

---

## Prevention

- [x] Code change: `_maybe_summarize()` wrapped in try/except
- [x] ADR created: [ADR-003](../adr/003-graceful-memory-degradation.md) — "Graceful Memory Degradation"
- [x] Reliability checklist updated: "All new subsystem failures degrade gracefully"
- [ ] Test added: agent run succeeds when summarization raises an exception
- [ ] Metric added: `summarization_skipped` counter to track degradation frequency

---

## Lessons Learned

**Subsystem failures must be isolated.** A background optimization step should
never be able to crash the primary operation. The principle is: a subsystem
failure should degrade the feature, not crash the system.

**The hot path must be protected.** Any operation in the hot path of a user
request must be wrapped in exception handling if it can fail independently.
The question to ask: "If this step fails, should the user get an error?"
If the answer is no, wrap it.

**Disproportionate impact is a design smell.** When a minor background operation
can cause a major user-facing failure, the design is wrong. The fix is always
to isolate the failure at the subsystem boundary.

---

## Related

- **ADR:** [ADR-003 — Graceful Memory Degradation](../adr/003-graceful-memory-degradation.md)
- **Architecture:** [Memory Systems — Memory Failure Isolation](../architecture/memory-systems.md#memory-failure-isolation)
- **Runbook:** [Memory Summarization Failures](../runbooks/incident-response.md#memory-summarization-failures)
