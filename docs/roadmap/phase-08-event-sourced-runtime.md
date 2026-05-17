---
title: "Phase 8: Event-Sourced Runtime"
domain: roadmap
doc_type: roadmap
status: planned
owner: platform-engineering
last_reviewed: 2026-05-18
stability: experimental
retrieval_priority: medium
tags: [roadmap, phase-8, event-sourcing, replay, execution-journal, replayability]
---

# Phase 8: Event-Sourced Runtime

**Status:** 🔲 Planned
**Related:** [Agent Runtime](../architecture/agent-runtime.md) · [Observability Overview](../observability/overview.md)

---

## Objective

Every `AgentEvent` emitted during a run is persisted to an append-only execution
journal. Runs become replayable, resumable, and auditable.

---

## The Problem

Currently, if an agent run produces a bad response, there is no way to inspect
what happened. The exact context sent to the LLM at each step, the tool call
inputs and outputs, and the reasoning chain are all ephemeral. They exist only
in memory during the run and are lost when it completes.

This makes debugging production quality issues extremely difficult.

---

## Execution Journal Schema

```sql
CREATE TABLE agent_run_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      UUID NOT NULL,
    session_id  UUID NOT NULL,
    step        INTEGER NOT NULL,
    event_type  VARCHAR(50) NOT NULL,   -- REASONING, TOOL_CALL, TOOL_RESULT, TEXT, DONE, ERROR
    content     TEXT,
    metadata    JSONB DEFAULT '{}',     -- model, tokens, latency_ms, tool_name, etc.
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON agent_run_events (run_id, step);
CREATE INDEX ON agent_run_events (session_id, created_at);
```

---

## Capabilities Unlocked

**Replay:** Re-execute any past run step-by-step in the UI.
**Debug:** Inspect the exact context sent to the LLM at each step.
**Resume:** Continue a run after interruption (pod restart, timeout).
**Audit:** Complete audit trail for governance and compliance.
**Evaluation:** Trajectory analysis on real production runs.

---

## API

```
GET /api/v1/runs/{run_id}/events          — full event stream for a run
GET /api/v1/runs/{run_id}/events/{step}   — single step detail
GET /api/v1/sessions/{session_id}/runs    — all runs for a session
POST /api/v1/runs/{run_id}/replay         — replay a run (future)
```

---

## Work Items

- [ ] Alembic migration: `agent_run_events` table
- [ ] `AgentRuntime` persists each `AgentEvent` to the journal
- [ ] `AgentService` generates and tracks `run_id` per run
- [ ] API endpoints for run event retrieval
- [ ] Retention policy: archive runs older than 90 days
- [ ] UI: run event timeline viewer (Phase 12)
