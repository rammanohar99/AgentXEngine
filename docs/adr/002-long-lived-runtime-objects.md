---
title: "ADR-002: Long-Lived Runtime Objects"
domain: adr
doc_type: adr
status: active
owner: agent-runtime
last_reviewed: 2026-05-18
stability: historical
retrieval_priority: high
tags: [adr, reliability, circuit-breaker, lifecycle, singleton, orchestrator]
related_incidents: [INC-002]
---

# ADR-002: Long-Lived Runtime Objects

**Status:** Accepted
**Date:** Phase 6.1
**Phase:** 6.1

---

## Context

The `Orchestrator` was creating a new `AgentRuntime` instance on every `run()` call.
`AgentRuntime` contains a `CircuitBreaker`. A circuit breaker recreated per request
resets to CLOSED on every call — providing zero protection against a degraded LLM.

The circuit breaker's entire value is the accumulated failure state across multiple
requests. If it is recreated per request, it can never accumulate failures and can
never open.

The same problem applies to `MemoryManager` (holds in-process session cache),
`AgentTracer` (holds Langfuse client connection), and `VertexAIService` (holds
google-genai client — expensive to create).

---

## Decision

`AgentRuntime`, `MemoryManager`, `AgentTracer`, and `VertexAIService` are
module-level singletons, lazy-initialized on first use.

```python
# Lazy initialization pattern
_runtime: AgentRuntime | None = None

def _get_runtime() -> AgentRuntime:
    global _runtime
    if _runtime is None:
        _runtime = _build_runtime()
    return _runtime
```

The `Orchestrator` MUST instantiate `AgentRuntime` in `__init__`, not in `run()`.

```python
# CORRECT
class Orchestrator:
    def __init__(self, ...):
        self._runtime = AgentRuntime(...)  # Circuit breaker persists

    async def run(self, ...):
        async for event in self._runtime.run(...):
            yield event
```

Specialist runtimes are cached by role name in `self._specialist_runtimes: dict[str, AgentRuntime]`.

---

## Consequences

**Positive:**
- Circuit breaker state persists across requests — provides actual protection
- `MemoryManager` session cache persists — no cache misses on every request
- `VertexAIService` client is created once — reduces startup overhead per request
- Simpler request handling — no object construction in the hot path

**Negative:**
- These objects are shared across all requests — they must be thread-safe
  (they are — asyncio is single-threaded per event loop)
- Startup failures in external services must be handled carefully
  (lazy initialization solves this — the module loads even if Vertex AI is down)

---

## Alternatives Considered

**Per-request object creation with explicit circuit breaker state store:**
Too complex. Requires externalizing circuit breaker state to Redis on every request.
This is the right long-term solution for distributed deployments (Phase 7) but
adds unnecessary complexity for the current single-process deployment.

**Dependency injection framework:** Adds framework complexity. The lazy singleton
pattern is explicit, simple, and sufficient.
