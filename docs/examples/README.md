---
title: Execution Examples Index
domain: example
doc_type: reference
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: operational
retrieval_priority: medium
tags: [examples, traces, execution, debugging, runtime]
---

# Execution Examples

Real execution traces, event flows, and annotated examples for debugging
and understanding runtime behavior.

**Related:** [Agent Runtime](../architecture/agent-runtime.md) · [Observability Overview](../observability/overview.md) · [Runbooks](../runbooks/incident-response.md)

---

## Index

| Example | Description |
|---|---|
| [Successful Agent Run](successful-agent-run.md) | Full ReAct loop trace: 3 steps, 2 tool calls, final answer |
| [Circuit Breaker Trip](circuit-breaker-trip.md) | LLM degradation → circuit opens → requests rejected → recovery |
| [Memory Retrieval Flow](memory-retrieval-flow.md) | Short-term + summary + vector memory assembled into context |
| [RAG Query Flow](rag-query-flow.md) | Embed → retrieve → rerank → inject → LLM response |
| [Graceful Degradation](graceful-degradation.md) | Redis down → in-process fallback → agent run succeeds |
| [Concurrent Reranker Trace](concurrent-reranker-trace.md) | Log trace showing parallel LLM scoring with bounded concurrency |
| [Retry Amplification Trace](retry-amplification-trace.md) | Contrast between localized provider retries and nested runtime retries |
| [Non-Blocking Evaluation](evaluation-trace.md) | Log trace showing asynchronous LLM-as-a-judge execution post-response |
| [Distributed Trace Correlation](distributed-trace.md) | End-to-end linkage across structlog, OpenTelemetry, and Langfuse |

---

## How to Read These Examples

Each example contains:
- **Setup:** the initial conditions
- **Event stream:** the sequence of `AgentEvent` objects emitted
- **Annotated log:** structured log output with explanations
- **Latency breakdown:** where time was spent
- **Key observations:** what to notice and why it matters

These examples are derived from real runs. Sensitive data has been replaced
with representative placeholders.
