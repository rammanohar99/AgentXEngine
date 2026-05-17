---
title: "Phase 10: Advanced Evaluation Platform"
domain: roadmap
doc_type: roadmap
status: planned
owner: observability
last_reviewed: 2026-05-18
stability: experimental
retrieval_priority: medium
tags: [roadmap, phase-10, evaluation, trajectory, hallucination, benchmarks, quality-gates]
---

# Phase 10: Advanced Evaluation Platform

**Status:** 🔲 Planned
**Related:** [Evaluation Overview](../evaluation/overview.md) · [Observability Overview](../observability/overview.md)

---

## Objective

Extend the current LLM-as-judge response quality evaluation with trajectory
evaluation, hallucination detection, a regression benchmark dataset, and
automated quality gates in CI.

---

## Current State

Phase 6.1 wired `AgentEvaluator` into `AgentService`. Every run now produces
a quality score (relevance, completeness, accuracy). This is the foundation.

Phase 10 builds on it.

---

## Work Items

### 10.1 Trajectory Evaluation

Score the full reasoning chain, not just the final response.

Metrics:
- **Step efficiency:** did the agent reach the answer in minimum steps?
- **Tool selection accuracy:** did the agent use the right tools?
- **Unnecessary tool calls:** did the agent call tools it didn't need?
- **Reasoning coherence:** was the thought process logical?

Implementation: record the full `(thought, action, observation)` sequence per run.
Score each step. Aggregate into a trajectory score.

---

### 10.2 Hallucination Detection

For RAG responses, verify the answer is grounded in the retrieved context.

```python
grounding_prompt = """
Is this answer supported by the following context?
Answer: {answer}
Context: {retrieved_chunks}
Respond: GROUNDED / PARTIALLY_GROUNDED / NOT_GROUNDED
"""
```

Requirements:
- Async, non-blocking (does not delay user response)
- Protected by circuit breaker
- Stored with the evaluation record

---

### 10.3 Regression Benchmark Dataset

A curated dataset of `(query, expected_tools, expected_answer_contains, max_steps)` tuples.

Location: `tests/evaluation/benchmark_dataset.json`

```json
{
  "id": "bench-001",
  "query": "What does the create_app function do?",
  "expected_tools": ["read_file", "search_files"],
  "expected_answer_contains": ["FastAPI", "middleware", "router"],
  "max_steps": 4
}
```

---

### 10.4 Quality Gates in CI

Block merge if:
- Quality score regression > 5% on benchmark dataset
- Step efficiency regression > 20%
- Any benchmark query produces `NOT_GROUNDED`
- Performance regression > 10% on benchmark suite

---

## Definition of Done

- [ ] Trajectory scores stored per run
- [ ] Hallucination detection running async after every RAG response
- [ ] Benchmark dataset with ≥20 queries
- [ ] CI job runs benchmark suite on every PR
- [ ] Quality gate blocks merge on regression
