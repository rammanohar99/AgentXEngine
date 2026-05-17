---
title: Engineering Principles
domain: onboarding
doc_type: guide
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [principles, engineering, coding-standards, reliability, observability, state-management]
related_adrs: [ADR-001, ADR-002, ADR-003, ADR-004]
---

# Engineering Principles

**Related:** [Getting Started](getting-started.md) · [Reliability Principles](../reliability/principles.md) · [Invariants](../architecture/invariants.md) · [ADR Index](../adr/README.md)

They are not suggestions. They are the rules that prevent known failure modes
from recurring.

---

## Core Principles

### Always

- Write modular code — prefer composition over inheritance
- Keep business logic isolated from routes/controllers
- Use typed interfaces and Pydantic schemas everywhere
- Use dependency injection patterns
- Use async IO — never block the event loop
- Write observable systems — every operation emits logs and metrics
- Keep functions small and focused
- Prefer explicit code over magic abstractions
- Read existing code before writing new code

### Never

- Place business logic inside routes/controllers
- Tightly couple infrastructure with domain logic
- Use giant files
- Duplicate logic across services
- Introduce unnecessary frameworks
- Hardcode secrets
- Use blocking IO in async paths
- Swallow exceptions silently
- Retry permanent errors
- Nest retry loops (retry amplification)
- Grow context unboundedly
- Deploy without health checks
- Merge without passing tests
- Create runtime objects per-request when they must be long-lived
- Use in-memory state in production multi-replica deployments

---

## Reliability Rules

### One Layer Owns Retries

Only one layer in the call stack may own retry logic for a given operation.
`VertexAIService` owns LLM retries. `AgentRuntime` owns circuit breaker and timeout only.

Nested retry layers create retry amplification. A 3×3 nested retry = 9 actual API calls
per logical call. Under load, this accelerates service degradation.

See [ADR-001](../adr/001-provider-layer-owns-retries.md).

### Circuit Breakers Must Be Long-Lived

A circuit breaker recreated per request provides zero protection.
Its value is the accumulated failure state across multiple requests.

See [ADR-002](../adr/002-long-lived-runtime-objects.md).

### Subsystem Failures Must Not Cascade

Memory failures, tracing failures, and evaluation failures must not fail agent runs.
Wrap subsystem operations in try/except. Log warnings. Continue.

See [ADR-003](../adr/003-graceful-memory-degradation.md).

### Every External Call Has a Timeout

Timeouts prevent hung connections from accumulating and exhausting resources.
`asyncio.wait_for` is the correct mechanism. Timeouts surface as ERROR events,
never as hung connections.

---

## Performance Rules

### Optimize the Right Things

This is a network-bound system. LLM calls dominate latency.

- Optimizing the planner parser saves < 0.1ms
- Reducing one LLM step saves 1,000 – 8,000ms

Focus on LLM call count, reranker parallelism, and context size.
Do not optimize CPU-bound operations that are not bottlenecks.

### Concurrent Over Sequential for Independent Operations

When N operations are independent, execute them concurrently via `asyncio.gather`.
The reranker is the canonical example: N sequential LLM calls → N concurrent calls.
Same cost. N× lower latency.

See [ADR-004](../adr/004-concurrent-reranker.md).

---

## Observability Rules

### Structured Logs Only

All logs must be structured JSON with consistent field names.
Free-form strings cannot be queried, aggregated, or alerted on.

### Correlation IDs Flow Everywhere

Every request gets a `correlation_id` that flows through all logs, traces, and metrics.
Without correlation IDs, distributed debugging is impossible.

### Metrics on Every Operation

All key operations emit `metric.*` log events. Even failure paths.
A metric that is only emitted on success is useless for debugging failures.

---

## State Management Rules

### In-Memory State Does Not Scale

Any state stored in a Python dict inside a running process is:
- Lost on process restart
- Not shared across replicas
- Unbounded (no eviction unless explicitly coded)

This is acceptable for local development. It is not acceptable for production.

### Redis Is the Coordination Layer

Anything that needs to be shared across replicas goes through Redis:
session state, rate limiting counters, circuit breaker state, task queues.

---

## Coding Style

### Python

- Ruff (linting), Black (formatting)
- Type hints required on all functions
- Pydantic schemas for all data contracts
- structlog for all logging (structured JSON)
- async/await everywhere — no blocking IO

### TypeScript

- ESLint + Prettier
- Strict mode enabled
- No `any` types

### Naming

- Descriptive names — no abbreviations
- No single-letter variables
- Functions: single responsibility, small and composable

---

## The Operational Constitution

Every engineering decision must optimize for:

1. **Correctness** — the system does what it says it does
2. **Observability** — every failure is visible and traceable
3. **Reliability** — failures are contained, not cascading
4. **Recoverability** — the system recovers from transient failures automatically
5. **Debuggability** — every run can be traced, replayed, and inspected
6. **Governance** — all operations are auditable and controllable
