---
title: "INC-001: Retry Amplification in LLM Call Stack"
domain: incident
doc_type: incident
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: historical
retrieval_priority: high
tags: [incident, reliability, retry, amplification, llm, vertex-ai]
related_adrs: [ADR-001]
---

# INC-001: Retry Amplification in LLM Call Stack

> **Immutable record.** This postmortem is not modified after publication.

**Severity:** High
**Phase:** 6.1 (discovered during Phase 6 reliability audit)
**Status:** Resolved
**ADR Created:** [ADR-001](../adr/001-provider-layer-owns-retries.md)

---

## Summary

During the Phase 6 reliability audit, two independent retry layers were discovered
wrapping the same LLM call — one in `AgentRuntime` and one in `VertexAIService`.
Under load, a single logical LLM call could trigger up to 9 actual API calls before
failing. This created a retry storm pattern that amplified pressure on an already-degraded
service, accelerating circuit breaker opening and worsening outages.

---

## Timeline

| Event | Description |
|---|---|
| Phase 6 audit | Reliability audit of the agent runtime call stack |
| Discovery | Two `RetryPolicy(max_attempts=3)` instances found wrapping the same LLM call |
| Analysis | Math confirmed: 3 × 3 = 9 actual API calls per logical call |
| Fix | Retry layer removed from `AgentRuntime._call_llm_with_resilience()` |
| ADR | ADR-001 written to prevent recurrence |

---

## Impact

- **User impact:** Under load with a degraded Vertex AI service, users would experience
  extended timeouts (up to 9× the expected retry duration) before receiving an error.
- **System impact:** Retry amplification accelerated rate limiting on Vertex AI,
  causing the circuit breaker to open faster and affecting all users, not just those
  whose requests triggered the retries.
- **Blast radius:** All agent runs during a Vertex AI degradation event.

---

## Root Cause

Two independent `RetryPolicy(max_attempts=3)` instances were wrapping the same
LLM API call at different layers of the call stack:

```
AgentRuntime._call_llm_with_resilience()
  → RetryPolicy(max_attempts=3)          ← Layer 1
    → VertexAIService._complete_with_model()
      → RetryPolicy(max_attempts=3)      ← Layer 2
        → Vertex AI API
```

Each layer was unaware of the other. The layers were added independently during
different development phases without a clear ownership rule for retry logic.

**The math:**
```
1 logical LLM call
  → AgentRuntime: up to 3 attempts
    → Each attempt: VertexAIService: up to 3 attempts
      = up to 9 actual API calls
```

---

## Contributing Factors

- No documented rule about retry ownership at the time of development
- Retry logic was added to both layers independently, in different phases
- No integration test that would reveal the amplification under load
- The amplification is invisible in normal operation (only manifests under degradation)

---

## Detection

Discovered during a manual code audit of the reliability stack in Phase 6.
Not detected by monitoring — the amplification is invisible when the service is healthy.

**Observability gap:** No metric tracked the number of actual API calls per logical
LLM call. Adding `retry_count` to `metric.llm_call` events would have made this visible.

---

## Mitigation

Removed the `RetryPolicy` from `AgentRuntime._call_llm_with_resilience()`.
The runtime layer now delegates all retry logic to `VertexAIService`.

---

## Resolution

`AgentRuntime` now owns only circuit breaker state and timeout enforcement.
`VertexAIService` owns all retry logic, fallback model selection, and transient
vs permanent error classification.

---

## Prevention

- [x] Code change: Removed retry layer from `AgentRuntime`
- [x] ADR created: [ADR-001](../adr/001-provider-layer-owns-retries.md) — "Provider Layer Owns Retries"
- [x] Reliability checklist updated: "No new retry layer added above `VertexAIService`"
- [ ] Metric added: `retry_count` in `metric.llm_call` to make amplification visible

---

## Lessons Learned

**Retry ownership must be explicit and documented.** Without a clear rule, retry
logic accumulates at every layer independently. The result is multiplicative
amplification that is invisible in normal operation and catastrophic under load.

**This pattern is universal.** It appears in microservices (service A retries →
service B retries → database retries), HTTP clients (application retry + SDK retry
+ load balancer retry), and AI systems (runtime retry + provider retry). The fix
is always the same: designate one layer as the retry owner and enforce it.

**Audits find what tests miss.** This bug was invisible to unit tests and integration
tests because it only manifests under degradation. Manual reliability audits of the
call stack are a necessary complement to automated testing.

---

## Related

- **ADR:** [ADR-001 — Provider Layer Owns Retries](../adr/001-provider-layer-owns-retries.md)
- **Runbook:** [LLM Service Degraded](../runbooks/incident-response.md#llm-service-degraded-429--503)
- **Architecture:** [Reliability Principles](../reliability/principles.md)
