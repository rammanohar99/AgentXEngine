---
title: "ADR-005: Evaluation in the Hot Path"
domain: adr
doc_type: adr
status: active
owner: observability
last_reviewed: 2026-05-18
stability: historical
retrieval_priority: medium
tags: [adr, evaluation, quality, wiring, agent-service, async]
related_incidents: [INC-005]
---

# ADR-005: Evaluation in the Hot Path

**Status:** Accepted
**Date:** Phase 6.1
**Phase:** 6.1

---

## Context

`AgentEvaluator` was built in Phase 5 and worked correctly. However, it was never
wired into `AgentService`. It existed as a library that was never called.

As a result, quality metrics were not being collected in production. There was no
visibility into response quality trends, no way to detect regressions, and no data
to drive quality improvements.

Evaluation is not a testing afterthought. It is a production system that must run
continuously alongside the agent runtime to provide ongoing quality measurement.

---

## Decision

`AgentService.stream_chat()` calls `AgentEvaluator.evaluate_response()` at the end
of every agent run, asynchronously, without blocking the response to the user.

```python
async def stream_chat(self, ...):
    # ... run the agent, stream events to user ...

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

Evaluation results are stored in PostgreSQL and emitted as `metric.evaluation` events.

---

## Consequences

**Positive:**
- Quality metrics collected on every production run
- Quality trends visible over time
- Regressions detectable before they affect many users
- Foundation for regression benchmarks and quality gates (Phase 10)

**Negative:**
- Extra LLM call per agent run (evaluation uses LLM-as-judge)
- Evaluation failures must not fail the agent run (wrapped in try/except)
- Evaluation adds to API quota consumption

The quality visibility benefit outweighs the cost. Evaluation is async and
non-blocking — it does not affect response latency.

---

## Alternatives Considered

**Batch evaluation (run evaluation offline on stored responses):**
Delayed feedback. Quality regressions would not be detected until the batch runs.
Real-time evaluation provides faster feedback loops.

**Sample-based evaluation (evaluate 10% of runs):**
Reduces cost but reduces coverage. For the current scale, evaluating every run
is affordable. Sampling can be introduced later if costs become significant.
