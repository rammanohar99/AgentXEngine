---
title: Evaluation Overview
domain: evaluation
doc_type: architecture
status: active
owner: observability
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [evaluation, llm-as-judge, trajectory, hallucination, benchmarks, quality-gates]
related_adrs: [ADR-005]
related_incidents: [INC-005]
---

# Evaluation Overview

**Related:** [Observability Overview](../observability/overview.md) · [RAG Pipeline](../architecture/rag-pipeline.md) · [ADR-005](../adr/005-evaluation-in-hot-path.md) · [INC-005](../incidents/INC-005-evaluator-not-wired.md) · [Phase 10 Roadmap](../roadmap/phase-10-evaluation-platform.md)

---

## Evaluation Is a First-Class Production System

Evaluation is not a testing afterthought. It is a production system that runs
continuously alongside the agent runtime, measuring quality on every response.

**The mistake:** Building an evaluator as a library that is never called.
`AgentEvaluator` existed and worked correctly but was never wired into `AgentService`.
Quality metrics were not being collected in production.

**The fix:** `AgentService.stream_chat()` now calls `AgentEvaluator.evaluate_response()`
at the end of every agent run, asynchronously, without blocking the response.

See [ADR-005](../adr/005-evaluation-in-hot-path.md).

**Implementation:** `packages/observability/evaluation.py`

---

## What Gets Evaluated

### Response Quality (LLM-as-Judge)

```python
prompt = """
Evaluate this response on three dimensions (0.0 to 1.0):
Query: {query}
Response: {response}

relevance:    <score>   # Does it address the query?
completeness: <score>   # Does it cover key aspects?
accuracy:     <score>   # Is the information correct?
"""
```

**Strengths:** Flexible, no ground truth required, scales to any domain.

**Weaknesses:** Self-referential (LLM judging LLM), expensive (extra LLM call),
not deterministic (scores vary between runs).

**Mitigations:**
- Use a different model for evaluation than for generation
- Use temperature=0 for deterministic scoring
- Average scores over multiple runs for trend analysis

### Trajectory Quality (Phase 10)

Response quality alone is insufficient. A good final answer reached via 8
unnecessary tool calls is not the same as one reached in 2 steps.

Trajectory evaluation measures:
- **Step efficiency:** did the agent reach the answer in minimum steps?
- **Tool selection accuracy:** did the agent use the right tools?
- **Reasoning coherence:** was the thought process logical?
- **Unnecessary tool calls:** did the agent call tools it didn't need?

**Implementation:** Record the full (thought, action, observation) sequence per run.
Score each step independently. Aggregate into a trajectory score.

### Hallucination Detection (Phase 10)

For RAG responses, the final answer must be grounded in the retrieved context.

```python
grounding_prompt = """
Is this answer supported by the following context?
Answer: {answer}
Context: {retrieved_chunks}

Respond: GROUNDED / PARTIALLY_GROUNDED / NOT_GROUNDED
Explanation: <brief explanation>
"""
```

This is a separate LLM call after the main response. It must be:
- Non-blocking (async, does not delay the response to the user)
- Protected by circuit breaker
- Stored with the evaluation record

---

## Evaluation Data Pipeline

```
Agent run completes
    ↓
AgentEvaluator.evaluate_response()   [async, non-blocking]
    ↓
Store EvaluationResult in PostgreSQL
    ↓
Aggregate into session-level and system-level metrics
    ↓
Emit metric.evaluation log event
    ↓
Langfuse scores (optional — for Langfuse dashboard)
    ↓
Alert if quality drops below threshold
```

---

## Regression Benchmarks (Phase 10)

A curated dataset of `(query, expected_answer, expected_tools)` tuples must be
maintained and run against every PR.

```json
{
  "id": "bench-001",
  "query": "What does the create_app function do?",
  "expected_tools": ["read_file", "search_files"],
  "expected_answer_contains": ["FastAPI", "middleware", "router"],
  "max_steps": 4
}
```

Dataset location: `tests/evaluation/benchmark_dataset.json`

**Quality gates — block merge if:**
- Quality score regression > 5% on benchmark dataset
- Step efficiency regression > 20% (agent taking more steps than baseline)
- Any benchmark query produces a NOT_GROUNDED hallucination

---

## Quality Gates (CI)

Before merging to main:
- All unit tests pass
- All integration tests pass
- Benchmark suite shows no performance regression > 10%
- Evaluation scores on benchmark dataset show no quality regression > 5%
