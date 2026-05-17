---
title: "INC-002: Circuit Breaker Reset on Every Request"
domain: incident
doc_type: incident
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: historical
retrieval_priority: high
tags: [incident, reliability, circuit-breaker, orchestrator, lifecycle]
related_adrs: [ADR-002]
---

# INC-002: Circuit Breaker Reset on Every Request

> **Immutable record.** This postmortem is not modified after publication.

**Severity:** High
**Phase:** 6.1 (discovered during Phase 6 reliability audit)
**Status:** Resolved
**ADR Created:** [ADR-002](../adr/002-long-lived-runtime-objects.md)

---

## Summary

The `Orchestrator` was creating a new `AgentRuntime` instance on every `run()` call.
`AgentRuntime` contains a `CircuitBreaker`. Because the runtime was recreated per
request, the circuit breaker was also recreated per request — resetting to CLOSED
on every call. The circuit breaker provided zero protection against a degraded LLM
service because it could never accumulate failure state across requests.

---

## Timeline

| Event | Description |
|---|---|
| Phase 6 audit | Reliability audit of the orchestrator lifecycle |
| Discovery | `AgentRuntime(...)` found inside `Orchestrator.run()` method |
| Analysis | Circuit breaker resets to CLOSED on every request — zero protection |
| Fix | `AgentRuntime` moved to `Orchestrator.__init__()` |
| ADR | ADR-002 written to prevent recurrence |

---

## Impact

- **User impact:** During a Vertex AI degradation event, the circuit breaker would
  never open. Every request would wait for the full LLM timeout (60s) before failing,
  rather than being rejected immediately after the threshold was reached.
- **System impact:** Without a functioning circuit breaker, the system could not
  protect itself from cascading failures. All requests would pile up waiting for
  timeouts, exhausting connection pools.
- **Blast radius:** All orchestrated agent runs during any LLM degradation event.

---

## Root Cause

```python
# WRONG — as found in the codebase
class Orchestrator:
    async def run(self, session_id, query, ...):
        runtime = AgentRuntime(...)  # New circuit breaker created here
        async for event in runtime.run(...):
            yield event
        # runtime goes out of scope — circuit breaker state lost
```

The `AgentRuntime` was instantiated inside the `run()` method, making it
request-scoped. The circuit breaker inside it was also request-scoped.
A circuit breaker that is recreated per request can never accumulate failures
and can never open.

The circuit breaker's entire value is the accumulated failure state across
multiple requests. Recreating it per request is equivalent to having no
circuit breaker at all.

---

## Contributing Factors

- No documented rule about object lifecycle at the time of development
- The bug is invisible in normal operation — the circuit breaker "works" (it just never opens)
- No test that verifies the circuit breaker opens after N failures across multiple requests
- The pattern of creating objects inside methods is common and not obviously wrong

---

## Detection

Discovered during a manual code audit of the orchestrator lifecycle in Phase 6.
Not detected by monitoring — the bug is invisible when the LLM service is healthy.

**Observability gap:** No metric tracked circuit breaker state across requests.
`metric.circuit_breaker` events would have shown the breaker always in CLOSED state,
which is a signal that it is never accumulating failures.

---

## Mitigation

Moved `AgentRuntime` instantiation from `Orchestrator.run()` to `Orchestrator.__init__()`.

```python
# CORRECT — as fixed
class Orchestrator:
    def __init__(self, ...):
        self._runtime = AgentRuntime(...)  # Circuit breaker persists

    async def run(self, session_id, query, ...):
        async for event in self._runtime.run(...):
            yield event
```

---

## Resolution

`AgentRuntime` is now a long-lived object, created once in `__init__` and reused
across all requests. The circuit breaker accumulates failure state correctly.

Specialist runtimes are cached by role name in `self._specialist_runtimes: dict[str, AgentRuntime]`.

---

## Prevention

- [x] Code change: `AgentRuntime` moved to `Orchestrator.__init__()`
- [x] ADR created: [ADR-002](../adr/002-long-lived-runtime-objects.md) — "Long-Lived Runtime Objects"
- [x] Reliability checklist updated: "No runtime objects created per-request that should be long-lived"
- [ ] Test added: circuit breaker opens after N failures across multiple requests

---

## Lessons Learned

**Object lifecycle is a reliability concern, not just a performance concern.**
A circuit breaker that is recreated per request is not just inefficient — it is
completely non-functional. The bug is invisible in normal operation and only
manifests during the exact conditions when the circuit breaker is most needed.

**Long-lived objects must be explicitly identified and protected.** Without a
documented list of which objects must be long-lived and why, they will be
recreated per-request by engineers who don't know the constraint.

**The test that would catch this is non-obvious.** Unit tests of the circuit breaker
in isolation pass. Integration tests of a single request pass. Only a test that
sends N requests and verifies the circuit opens would catch this — and that test
is not commonly written.

---

## Related

- **ADR:** [ADR-002 — Long-Lived Runtime Objects](../adr/002-long-lived-runtime-objects.md)
- **Runbook:** [LLM Service Degraded](../runbooks/incident-response.md#llm-service-degraded-429--503)
- **Architecture:** [Agent Runtime — Object Lifecycle Rules](../architecture/agent-runtime.md#object-lifecycle-rules)
