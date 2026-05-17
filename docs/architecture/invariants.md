---
title: Architectural Invariants
domain: architecture
doc_type: invariant
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [invariants, architecture, constraints, safety, non-negotiable]
related_adrs: [ADR-001, ADR-002, ADR-003, ADR-004, ADR-005]
---

# Architectural Invariants

These are non-negotiable boundaries. They encode the lessons from production
failures and reliability audits. Violating any of them introduces a known
failure mode that has already been discovered and fixed once.

**Read this document before making any architectural change.**

**Related:** [Reliability Principles](../reliability/principles.md) · [Agent Runtime](agent-runtime.md) · [ADR Index](../adr/README.md)

---

## Runtime Invariants

### INV-001: Provider Layer Owns Retries

`VertexAIService` is the only layer that may own retry logic for LLM API calls.
No layer above it may add its own retry loop.

**Why:** Nested retry layers create multiplicative amplification. 3×3 = 9 actual
API calls per logical call. Under load this accelerates service degradation.

**Violation looks like:** Any `RetryPolicy` or retry loop in `AgentRuntime`,
`AgentService`, `Orchestrator`, or any caller of `VertexAIService`.

**Source:** [INC-001](../incidents/INC-001-retry-amplification.md) · [ADR-001](../adr/001-provider-layer-owns-retries.md)

---

### INV-002: Circuit Breakers Are Long-Lived

`AgentRuntime` instances — and the `CircuitBreaker` they contain — MUST be
module-level singletons. They MUST NOT be created per-request.

**Why:** A circuit breaker recreated per request resets to CLOSED on every call.
It can never accumulate failure state and provides zero protection.

**Violation looks like:** `AgentRuntime(...)` inside any method that is called
per-request (e.g., inside `run()`, `stream_chat()`, or a FastAPI route handler).

**Source:** [INC-002](../incidents/INC-002-circuit-breaker-lifecycle.md) · [ADR-002](../adr/002-long-lived-runtime-objects.md)

---

### INV-003: Memory Failures Do Not Fail Agent Runs

All memory subsystem operations (`record_turn`, `_maybe_summarize`, vector storage)
MUST be wrapped in try/except. Failures MUST be logged as warnings and execution
MUST continue.

**Why:** Memory summarization makes an LLM call. If it fails and the exception
propagates, it fails the entire agent run — not just the summarization. This is
disproportionate impact.

**Violation looks like:** Any `await memory_manager.*()` call in the agent run
hot path without exception handling.

**Source:** [INC-003](../incidents/INC-003-memory-summarization-cascade.md) · [ADR-003](../adr/003-graceful-memory-degradation.md)

---

### INV-004: Reranker Scoring Is Concurrent

The reranker MUST use `asyncio.gather` to execute all scoring calls concurrently.
Sequential scoring is not permitted.

**Why:** Sequential reranking for `top_k=5` adds 5-10 seconds to every RAG query.
The calls are independent — there is no reason to execute them sequentially.

**Violation looks like:** `for result in results: score = await self._score_chunk(...)`

**Source:** [INC-004](../incidents/INC-004-reranker-sequential-latency.md) · [ADR-004](../adr/004-concurrent-reranker.md)

---

### INV-005: Evaluation Never Blocks the User Response

`AgentEvaluator.evaluate_response()` MUST be called after every agent run.
It MUST be called asynchronously (via `asyncio.create_task`) and MUST NOT
block or delay the response stream.

**Why:** Evaluation is a production quality system, not a testing afterthought.
It must run on every request. But it must not add latency to the user response.

**Violation looks like:** Evaluation called with `await` in the response path,
or evaluation not called at all.

**Source:** [INC-005](../incidents/INC-005-evaluator-not-wired.md) · [ADR-005](../adr/005-evaluation-in-hot-path.md)

---

## Observability Invariants

### INV-006: All Runtime Actions Emit Telemetry

Every operation in the agent runtime MUST emit structured log events.
Failure paths MUST emit metrics — not just success paths.

**Why:** A metric that is only emitted on success is useless for debugging failures.
Observability gaps are discovered during incidents, not before them.

**Required events:** See [Observability — Required Metric Events](../observability/overview.md#required-metric-events).

**Violation looks like:** A new operation with no corresponding `metric.*` log event,
or a `metric.*` event only in the success branch of a try/except.

---

### INV-007: Correlation IDs Flow Through All Operations

Every request's `correlation_id` MUST appear in all log entries, Langfuse spans,
OTel attributes, and metric events for that request.

**Why:** Without correlation IDs, debugging a distributed failure requires manually
correlating timestamps across multiple log streams.

**Violation looks like:** A new service or middleware that does not propagate
`correlation_id` from the request context.

---

## State Management Invariants

### INV-008: Single Authoritative Runtime Session Layer

All runtime services (`AgentService`, `ChatService`) MUST use `SessionManager` as the single authoritative source of truth for runtime session state. Local `_sessions` dicts are forbidden.

**Why:** Fragmented runtime ownership creates invisible session boundaries where an agent run does not see earlier chat history and vice versa. It also complicates the persistence migration.

**Violation looks like:** A local `_sessions: dict` initialized inside a service.

**Exception:** Explicitly temporary caches with bounded size and documented
eviction policy are acceptable for non-session state. Document the limitation.

---

## Security Invariants

### INV-009: Filesystem Tools Are Sandboxed

All filesystem tool operations MUST resolve paths relative to the workspace root
and MUST reject paths that escape the sandbox via traversal.

**Why:** Path traversal allows agents to read or write arbitrary files on the host.

**Violation looks like:** Any filesystem tool that does not call `.resolve()` and
verify the result is relative to `workspace_root`.

---

### INV-010: Database Tools Are Read-Only

The `database_query` tool MUST only permit SELECT statements.
DML and DDL (INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER) MUST be blocked.

**Why:** An agent with write access to the database can corrupt or destroy data.

**Violation looks like:** Removing or weakening the `BLOCKED_KEYWORDS` check in
the database tool.

---

## Invariant Checklist

Before merging any change, verify:

- [ ] No new retry layer above `VertexAIService` (INV-001)
- [ ] No `AgentRuntime` created per-request (INV-002)
- [ ] All memory operations wrapped in try/except (INV-003)
- [ ] No sequential reranker scoring loop (INV-004)
- [ ] Evaluation still called after every agent run (INV-005)
- [ ] All new operations emit `metric.*` events on success AND failure (INV-006)
- [ ] `correlation_id` propagated through new services (INV-007)
- [ ] No new unbounded in-memory state (INV-008)
- [ ] Filesystem tools still sandboxed (INV-009)
- [ ] Database tool still read-only (INV-010)
