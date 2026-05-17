---
title: "INC-005: Evaluator Built but Never Called"
domain: incident
doc_type: incident
status: active
owner: observability
last_reviewed: 2026-05-18
stability: historical
retrieval_priority: low
tags: [incident, evaluation, observability, quality, wiring]
related_adrs: [ADR-005]
---

# INC-005: Evaluator Built but Never Called

> **Immutable record.** This postmortem is not modified after publication.

**Severity:** Low (no user-facing impact; quality metrics not collected)
**Phase:** 6.1 (discovered during Phase 6 reliability audit)
**Status:** Resolved
**ADR Created:** [ADR-005](../adr/005-evaluation-in-hot-path.md)

---

## Summary

`AgentEvaluator` was built in Phase 5 and worked correctly in isolation. However,
it was never wired into `AgentService`. The evaluator existed as a library that
was never called. As a result, quality metrics were not being collected in production
for the entire duration of Phase 5 and Phase 6. There was no visibility into response
quality trends, no way to detect regressions, and no data to drive quality improvements.

---

## Timeline

| Event | Description |
|---|---|
| Phase 5 | `AgentEvaluator` implemented and unit tested |
| Phase 5 | `AgentEvaluator` never wired into `AgentService` |
| Phase 6 audit | Code audit reveals evaluator is never called |
| Fix | `AgentService.stream_chat()` updated to call `AgentEvaluator.evaluate_response()` |
| ADR | ADR-005 written |

---

## Impact

- **User impact:** None directly. Users received correct responses.
- **System impact:** Zero quality metrics collected during Phase 5 and Phase 6.
  No visibility into response quality trends. No ability to detect quality regressions.
- **Blast radius:** All agent runs during Phase 5 and Phase 6 — no evaluation data.

---

## Root Cause

The evaluator was built as a standalone library component without a clear integration
point. The `AgentService` was not updated to call it. There was no test that verified
evaluation was being called as part of the agent run pipeline.

This is a "last mile" integration failure — the component works correctly in isolation
but is never connected to the system it is meant to serve.

---

## Contributing Factors

- No integration test that verifies evaluation is called after each agent run
- No metric that would reveal "zero evaluations in the last hour" as an anomaly
- The evaluator was built in a separate phase from the agent service integration
- No explicit "wire this in" task in the phase completion checklist

---

## Detection

Discovered during a manual code audit of the agent service in Phase 6.

**Observability gap:** No `metric.evaluation` events in the logs would have been
a clear signal that evaluation was not running. But there was no alert for
"zero evaluation events in the last N hours."

---

## Resolution

`AgentService.stream_chat()` now calls `AgentEvaluator.evaluate_response()` at
the end of every agent run, asynchronously, without blocking the response:

```python
# After run completes — non-blocking evaluation
asyncio.create_task(
    self._evaluator.evaluate_response(
        session_id=session_id,
        run_id=run_id,
        query=query,
        response=final_response,
    )
)
```

---

## Prevention

- [x] Code change: Evaluator wired into `AgentService.stream_chat()`
- [x] ADR created: [ADR-005](../adr/005-evaluation-in-hot-path.md) — "Evaluation in the Hot Path"
- [ ] Alert added: "Zero `metric.evaluation` events in the last hour" → warning
- [ ] Integration test: verify `AgentEvaluator.evaluate_response()` is called after each run

---

## Lessons Learned

**A component that is never called is not a component — it is dead code.**
Building a system component without wiring it into the pipeline is equivalent
to not building it. The integration is as important as the implementation.

**"Last mile" integration failures are common and hard to detect.** The evaluator
worked correctly in unit tests. The agent service worked correctly in integration
tests. Only a test that verified the full pipeline — agent run → evaluation call —
would have caught this.

**Observability gaps compound.** The absence of `metric.evaluation` events should
have been an alert. "Zero events of type X in the last hour" is a valid and
important alert class. Monitoring for the absence of expected events is as
important as monitoring for the presence of error events.

---

## Related

- **ADR:** [ADR-005 — Evaluation in the Hot Path](../adr/005-evaluation-in-hot-path.md)
- **Architecture:** [Evaluation Overview](../evaluation/overview.md)
- **Observability:** [Required Metric Events](../observability/overview.md#required-metric-events)
