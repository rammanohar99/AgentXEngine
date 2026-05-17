---
title: "Phase 9: Execution DAG Engine"
domain: roadmap
doc_type: roadmap
status: planned
owner: platform-engineering
last_reviewed: 2026-05-18
stability: experimental
retrieval_priority: low
tags: [roadmap, phase-9, dag, workflow, parallel, execution, checkpointing]
---

# Phase 9: Execution DAG Engine

**Status:** 🔲 Planned
**Related:** [Architecture Overview](../architecture/overview.md) · [RAG Pipeline — Reranking](../architecture/rag-pipeline.md#reranking)

---

## Objective

Upgrade the `WorkflowExecutor` from sequential topological execution to a true
DAG engine that executes independent tasks concurrently and checkpoints progress.

---

## The Problem

The current `WorkflowExecutor` implements topological sort and executes tasks
in dependency order — but sequentially. Tasks with no dependencies on each other
run one at a time. A 5-task workflow where tasks 2, 3, and 4 are all independent
takes 5× the time it needs to.

Additionally, if a workflow fails at step 8 of 10, it must restart from step 1.
There is no checkpointing.

---

## Concurrent Execution

```python
# Current — sequential even when tasks are independent
for task in topological_order:
    result = await run_task(task)
    completed[task.id] = result

# Target — concurrent execution of independent tasks
while remaining:
    ready = [t for t in remaining if all(d in completed for d in t.depends_on)]
    results = await asyncio.gather(*[run_task(t) for t in ready])
    for task, result in zip(ready, results):
        completed[task.id] = result
        remaining.remove(task)
```

---

## Checkpointing

After each task completes, checkpoint to Redis:
```python
await redis.set(f"workflow:{run_id}:task:{task_id}", result_json, ex=3600)
```

On restart, load completed tasks from Redis and resume from the last checkpoint.

---

## Work Items

- [ ] Refactor `WorkflowExecutor` to identify ready tasks at each step
- [ ] Execute ready tasks via `asyncio.gather`
- [ ] Checkpoint completed task results to Redis
- [ ] Resume workflow from checkpoint on restart
- [ ] Workflow status API: `GET /api/v1/workflows/{run_id}`
- [ ] Concurrent reranker scoring (also tracked here — same pattern)
