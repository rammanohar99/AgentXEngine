---
title: Agent Runtime Architecture
domain: architecture
doc_type: architecture
status: active
owner: agent-runtime
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [agent-runtime, react-loop, planner, executor, orchestrator, circuit-breaker, lifecycle]
related_adrs: [ADR-001, ADR-002, ADR-003, ADR-005]
related_incidents: [INC-001, INC-002, INC-003]
---

# Agent Runtime Architecture

**Related:** [Architecture Overview](overview.md) · [Reliability Principles](../reliability/principles.md) · [Context Engineering](context-engineering.md) · [Tool Reference](../tools/reference.md) · [Invariants](invariants.md)

The agent runtime is the most important component in the system. It implements the
ReAct (Reasoning + Acting) execution loop with full reliability enforcement.

**Implementation:** `packages/agents/runtime.py`

---

## The ReAct Loop

ReAct alternates between reasoning about what to do and taking actions.

```
Thought:      I need to find the function definition.
Action:       search_files
Action Input: {"pattern": "def create_app", "file_pattern": "*.py"}
Observation:  Found in apps/backend/app/main.py, line 52

Thought:      I found it. Let me read the file.
Action:       read_file
Action Input: {"path": "apps/backend/app/main.py"}
Observation:  [file contents]

Thought:      I now have enough information to answer.
Final Answer: The create_app function is in main.py and does X, Y, Z.
```

The loop continues until the agent produces a `Final Answer` or hits the step limit.

---

## Execution Flow

```
Request arrives
    ↓
1.  Check circuit breaker — reject immediately if OPEN
    ↓
2.  Build system prompt (PromptManager)
    ↓
3.  Prepend history + memory context
    ↓
4.  Apply token budget (ContextManager.prepare_messages)
    ↓
5.  Call LLM with timeout (with_timeout, default 60s)
    ↓
6.  Parse response → AgentDecision (Planner)
    ↓
    ├── TOOL_CALL ──────────────────────────────────────────────┐
    │   Emit REASONING event                                     │
    │   Emit TOOL_CALL event                                     │
    │   Execute tool with timeout (Executor.execute, 30s)        │
    │   Truncate output (ContextManager.truncate_tool_output)    │
    │   Emit TOOL_RESULT event                                   │
    │   Inject observation into working_messages                 │
    │   Loop back to step 4 ◄────────────────────────────────────┘
    │
    └── FINAL_ANSWER
        Emit REASONING event
        Stream TEXT events (chunked)
        Emit DONE event
        ↓
7.  Record metrics (MetricsCollector.record_agent_run)
8.  Run evaluation (AgentEvaluator, async, non-blocking)
```

---

## Runtime Components

| Component | File | Responsibility |
|---|---|---|
| `AgentRuntime` | `runtime.py` | ReAct loop orchestration, reliability enforcement |
| `Planner` | `planner.py` | Parse LLM output → typed `AgentDecision` |
| `Executor` | `executor.py` | Dispatch `ToolCall` → `ToolResult` |
| `ToolRegistry` | `tool_registry.py` | Tool catalog, prompt descriptions, dispatch |
| `ContextManager` | `context_manager.py` | Token budget enforcement, truncation |
| `PromptManager` | `prompt_manager.py` | System prompt assembly |
| `CircuitBreaker` | `resilience.py` | LLM failure isolation |
| `RetryPolicy` | `resilience.py` | Transient error recovery (provider layer only) |

---

## The Planner

The planner is the boundary between unstructured LLM text and typed execution.
It parses raw LLM output into an `AgentDecision` — either a `ToolCall` or a `FinalAnswer`.

**Parsing strategy (in priority order):**
1. Look for `Final Answer:` → `DecisionType.FINAL_ANSWER`
2. Look for `Action:` + `Action Input:` → `DecisionType.TOOL_CALL`
3. Validate the tool exists in the registry
4. Parse `Action Input` as JSON (with Python dict fallback)
5. If nothing matches → treat entire output as final answer (graceful fallback)

The planner is intentionally simple text parsing — no regex complexity, no LLM calls.
Parse failures are observable (logged as metrics) and degrade gracefully.

---

## The Executor

The executor dispatches `ToolCall` objects to the correct tool implementation.
It does not handle errors — `BaseTool.execute()` wraps all exceptions into
`ToolResult(success=False)`. The executor's job is orchestration and observability.

---

## Multi-Agent Orchestration

One strong orchestrator is preferred over many weak agents.

```
Orchestrator
├── Planner Agent    (read_file, list_directory, search_files)
├── Coding Agent     (read_file, list_directory, search_files)
├── Retrieval Agent  (retrieve_documents, search_files)
├── Debugging Agent  (read_file, list_directory, search_files)
└── DevOps Agent     (read_file, list_directory, search_files)
```

Delegation is via the `delegate_to_agent` tool. Max delegation depth: 1.
No recursive delegation — prevents infinite loops.

Each specialist has a filtered tool registry and specialized system prompt.
Specialists share the same `AgentRuntime` implementation — only config differs.
This is data, not classes.

**Implementation:** `packages/agents/orchestrator.py`, `packages/agents/agent_types.py`

---

## Object Lifecycle Rules

Understanding object lifecycle is critical for correctness and performance.

### Long-Lived Objects (module-level singletons)

These MUST be lazy-initialized on first use and reused across all requests:

| Object | Why Long-Lived |
|---|---|
| `AgentRuntime` | Holds circuit breaker state — must persist across requests |
| `MemoryManager` | Holds in-process session cache — must persist |
| `AgentTracer` | Holds Langfuse client connection |
| `VertexAIService` | Holds google-genai client — expensive to create |
| `ToolRegistry` | Static catalog — no reason to rebuild |
| `CircuitBreaker` | State is its entire value — must persist |

### Request-Scoped Objects (created fresh per request)

| Object | Why Request-Scoped |
|---|---|
| `RunState` | Mutable per-run state — must be isolated |
| `AsyncSession` (SQLAlchemy) | Database transaction scope |
| `RAGService` | Injected with session — request-scoped by design |

### Lazy Initialization Pattern

```python
_runtime: AgentRuntime | None = None

def _get_runtime() -> AgentRuntime:
    global _runtime
    if _runtime is None:
        _runtime = _build_runtime()
    return _runtime
```

Startup failures in external services must not prevent the module from loading.
The service should start and degrade gracefully.

### Orchestrator Lifecycle Rule

The `Orchestrator` MUST instantiate `AgentRuntime` in `__init__`, not in `run()`.

```python
# WRONG — circuit breaker resets to CLOSED on every request
class Orchestrator:
    async def run(self, ...):
        runtime = AgentRuntime(...)  # New circuit breaker, zero protection
        async for event in runtime.run(...):
            yield event

# CORRECT — circuit breaker persists across requests
class Orchestrator:
    def __init__(self, ...):
        self._runtime = AgentRuntime(...)  # Created once, reused

    async def run(self, ...):
        async for event in self._runtime.run(...):
            yield event
```

Specialist runtimes are cached by role name in `self._specialist_runtimes: dict[str, AgentRuntime]`.
Do not change this to per-request creation.

---

## Runtime Reliability Contract

The runtime MUST:
- Never crash on LLM failure — emit ERROR event instead
- Never crash on tool failure — `ToolResult(success=False)` is returned
- Never hang — all external calls have timeouts
- Never amplify retries — provider layer owns retry logic
- Always emit metrics — even on failure paths
- Always emit DONE or ERROR — never leave the stream open

---

## AgentEvent Types

| Event | When Emitted |
|---|---|
| `REASONING` | Before each tool call and before final answer |
| `TOOL_CALL` | When a tool is about to be executed |
| `TOOL_RESULT` | After a tool returns |
| `TEXT` | Streaming chunks of the final answer |
| `DONE` | Run completed successfully |
| `ERROR` | Run failed (LLM error, timeout, circuit open) |
