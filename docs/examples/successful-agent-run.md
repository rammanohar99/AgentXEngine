---
title: "Example: Successful Agent Run (3 Steps, 2 Tool Calls)"
domain: example
doc_type: example
status: active
owner: agent-runtime
last_reviewed: 2026-05-18
stability: operational
retrieval_priority: medium
tags: [example, agent-run, react-loop, tool-call, trace, debugging]
related_adrs: [ADR-001, ADR-002]
---

# Example: Successful Agent Run

A complete trace of a 3-step ReAct run with 2 tool calls and a final answer.
Use this as a reference when debugging agent behavior or verifying event emission.

**Related:** [Agent Runtime](../architecture/agent-runtime.md) · [Observability Overview](../observability/overview.md)

---

## Setup

- **Query:** "What does the `create_app` function do and where is it defined?"
- **Session:** `sess_abc123`
- **Run:** `run_xyz789`
- **Model:** `gemini-2.0-flash`
- **Circuit breaker:** CLOSED
- **Memory:** 4 prior turns (no summarization triggered)

---

## Event Stream

```
[T+0ms]    CHECK circuit breaker → CLOSED, proceed

[T+1ms]    BUILD system prompt
           → 847 tokens (tools: 312, instructions: 535)

[T+2ms]    INJECT memory context
           → 4 turns, 180 tokens
           → total context: 1,027 tokens (budget: 32,000)
           → metric.context_budget: utilization=3.2%, truncated=false

[T+45ms]   LLM CALL → gemini-2.0-flash
           → input_tokens: 1,027

[T+1,823ms] LLM RESPONSE received
           → first_token_latency: 312ms
           → metric.llm_first_token: time_to_first_token_ms=312

           Thought: I need to find where create_app is defined.
           Action: search_files
           Action Input: {"pattern": "def create_app", "file_pattern": "*.py"}

[T+1,824ms] EMIT AgentEvent(REASONING)
           → "I need to find where create_app is defined."

[T+1,825ms] EMIT AgentEvent(TOOL_CALL)
           → tool=search_files, inputs={"pattern": "def create_app", ...}

[T+1,826ms] EXECUTE search_files (timeout: 30s)

[T+1,891ms] TOOL RESULT received (65ms)
           → success=true, output_chars=142
           → "Found in apps/backend/app/main.py, line 52"
           → metric.tool_execution: tool=search_files, latency_ms=65, success=true

[T+1,892ms] EMIT AgentEvent(TOOL_RESULT)
           → truncated=false (142 chars < max_tool_output_chars)

[T+1,893ms] INJECT observation into working_messages

[T+1,894ms] APPLY token budget
           → context now: 1,169 tokens

[T+1,895ms] LLM CALL → gemini-2.0-flash
           → input_tokens: 1,169

[T+3,201ms] LLM RESPONSE received
           → first_token_latency: 287ms

           Thought: Found it. Now I need to read the file to understand what it does.
           Action: read_file
           Action Input: {"path": "apps/backend/app/main.py"}

[T+3,202ms] EMIT AgentEvent(REASONING)
[T+3,203ms] EMIT AgentEvent(TOOL_CALL)
           → tool=read_file, inputs={"path": "apps/backend/app/main.py"}

[T+3,204ms] EXECUTE read_file (timeout: 30s)

[T+3,289ms] TOOL RESULT received (85ms)
           → success=true, output_chars=4,821
           → metric.tool_execution: tool=read_file, latency_ms=85, success=true

[T+3,290ms] TRUNCATE tool output
           → 4,821 chars > max_tool_output_chars (4,000)
           → truncated to 4,000 chars + "[Output truncated at 4000 chars]"

[T+3,291ms] EMIT AgentEvent(TOOL_RESULT)
           → truncated=true

[T+3,292ms] INJECT observation into working_messages

[T+3,293ms] APPLY token budget
           → context now: 2,169 tokens

[T+3,294ms] LLM CALL → gemini-2.0-flash
           → input_tokens: 2,169

[T+5,102ms] LLM RESPONSE received
           → first_token_latency: 298ms

           Thought: I have the information I need.
           Final Answer: The `create_app` function is defined in
           `apps/backend/app/main.py` at line 52. It creates and configures
           the FastAPI application instance, registering all API routers,
           adding middleware (CORS, correlation ID, rate limiting), and
           configuring the lifespan context manager for startup/shutdown.

[T+5,103ms] EMIT AgentEvent(REASONING)
[T+5,104ms] STREAM AgentEvent(TEXT) chunks...
[T+5,847ms] EMIT AgentEvent(DONE)

[T+5,848ms] RECORD metrics
           → metric.agent_run: steps=3, tool_calls=2, latency_ms=5848,
             input_tokens_total=4365, success=true

[T+5,849ms] SCHEDULE evaluation (asyncio.create_task, non-blocking)
```

---

## Latency Breakdown

| Phase | Duration |
|---|---|
| Context build + memory inject | 2ms |
| LLM call 1 (search decision) | 1,778ms |
| Tool: search_files | 65ms |
| LLM call 2 (read decision) | 1,308ms |
| Tool: read_file | 85ms |
| LLM call 3 (final answer) | 1,808ms |
| Streaming final answer | 743ms |
| **Total** | **5,848ms** |

**Key observation:** 4,894ms (84%) of total latency is LLM calls.
Tool execution is 150ms (2.6%). This confirms the system is network-bound.
Optimizing tool execution has negligible impact. Reducing LLM steps has large impact.

---

## Structured Log Output (abbreviated)

```json
{"event": "metric.context_budget", "estimated_tokens": 1027, "max_tokens": 32000, "utilization_pct": 3.2, "truncated": false}
{"event": "metric.llm_first_token", "model": "gemini-2.0-flash", "time_to_first_token_ms": 312, "correlation_id": "corr_abc"}
{"event": "metric.tool_execution", "tool_name": "search_files", "latency_ms": 65, "success": true, "output_chars": 142}
{"event": "metric.tool_execution", "tool_name": "read_file", "latency_ms": 85, "success": true, "output_chars": 4821}
{"event": "metric.agent_run", "session_id": "sess_abc123", "run_id": "run_xyz789", "latency_ms": 5848, "steps": 3, "tool_calls": 2, "success": true}
```
