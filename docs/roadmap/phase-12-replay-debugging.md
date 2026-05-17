---
title: "Phase 12: Agent Replay and Debugging"
domain: roadmap
doc_type: roadmap
status: planned
owner: platform-engineering
last_reviewed: 2026-05-18
stability: experimental
retrieval_priority: low
tags: [roadmap, phase-12, replay, debugging, ui, trajectory-visualization, memory-inspector]
---

# Phase 12: Agent Replay and Debugging

**Status:** 🔲 Planned (requires Phase 8 execution journal)
**Related:** [Phase 8 — Event-Sourced Runtime](phase-08-event-sourced-runtime.md) · [Observability Overview](../observability/overview.md)

---

## Objective

Build a debugging UI that lets engineers step through any past agent run,
inspect the exact context sent to the LLM at each step, and visualize the
reasoning trajectory.

---

## Prerequisites

- Phase 8 execution journal must be implemented
- `GET /api/v1/runs/{run_id}/events` API must exist

---

## Work Items

### 12.1 Run Timeline Viewer

Frontend component that renders the event stream for a run as a timeline:
- REASONING events → thought bubbles
- TOOL_CALL events → tool call cards with inputs
- TOOL_RESULT events → result cards with outputs
- TEXT events → streamed response
- ERROR events → error cards with details

---

### 12.2 Context Inspector

For each step in the run, show the exact messages array sent to the LLM:
- System prompt
- Memory context
- Conversation history
- Tool outputs injected as observations
- Token count at each step

---

### 12.3 Memory Inspector

```
GET /api/v1/debug/sessions/{session_id}/memory
```

Returns:
- Short-term memory (recent turns)
- Summary (if present)
- Long-term facts
- Vector memory entry count

---

### 12.4 Runtime Introspection

```
GET /api/v1/debug/runtime
```

Returns:
- Active session count
- Circuit breaker states (all breakers: CLOSED/OPEN/HALF_OPEN)
- Recent error rates (last 5 minutes)
- Queue depths (Celery pending/active/reserved)

Protected by admin authentication.

---

## Definition of Done

- [ ] Run timeline viewer in frontend
- [ ] Context inspector shows exact LLM input per step
- [ ] Memory inspector API implemented
- [ ] Runtime introspection API implemented
- [ ] All debug endpoints protected by admin auth
