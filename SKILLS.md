# SKILLS.md — AI Systems Engineering Knowledge Base

> **Navigation note:** This file is the original knowledge base that seeded the
> documentation system. Its content has been migrated into the structured docs
> hierarchy. For current, authoritative documentation use the links below.
>
> | Topic | Authoritative Location |
> |---|---|
> | Agent runtime, ReAct loop | [docs/architecture/agent-runtime.md](docs/architecture/agent-runtime.md) |
> | Reliability, retry, circuit breaker | [docs/reliability/principles.md](docs/reliability/principles.md) |
> | Performance, latency hierarchy | [docs/performance/overview.md](docs/performance/overview.md) |
> | Observability, metrics, tracing | [docs/observability/overview.md](docs/observability/overview.md) |
> | Context engineering, token budget | [docs/architecture/context-engineering.md](docs/architecture/context-engineering.md) |
> | Evaluation, LLM-as-judge | [docs/evaluation/overview.md](docs/evaluation/overview.md) |
> | Distributed systems learnings | [docs/incidents/README.md](docs/incidents/README.md) |
> | RAG pipeline | [docs/architecture/rag-pipeline.md](docs/architecture/rag-pipeline.md) |
> | Memory systems | [docs/architecture/memory-systems.md](docs/architecture/memory-systems.md) |
> | Tool system | [docs/tools/reference.md](docs/tools/reference.md) |
> | Infrastructure, deployment | [docs/infrastructure/overview.md](docs/infrastructure/overview.md) |
> | ADRs | [docs/adr/README.md](docs/adr/README.md) |
>
> This file is preserved as the historical source. It is not actively maintained.

---

This repository is both a production AI platform and a learning operating system.
This document is the **original engineering knowledge base** — it encodes every
major concept, architectural decision, and operational learning discovered during
the development and auditing of this system.

---

# 1. AI RUNTIME ENGINEERING

## The ReAct Loop

ReAct (Reasoning + Acting) is the core execution pattern for autonomous agents.
The agent alternates between reasoning about what to do and taking actions.

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

**Implementation:** `packages/agents/runtime.py`

## Runtime Execution Lifecycle

```
Request arrives
    ↓
Check circuit breaker (reject if OPEN)
    ↓
Build system prompt + inject history + memory context
    ↓
Apply token budget (truncate if over limit)
    ↓
Call LLM with timeout
    ↓
Parse response → AgentDecision (Planner)
    ↓
TOOL_CALL?                    FINAL_ANSWER?
    ↓                              ↓
Execute tool with timeout     Stream TEXT events
    ↓                              ↓
Truncate output               Emit DONE event
    ↓                              ↓
Inject observation            Record metrics
    ↓
Loop back to token budget step
```

## The Planner

The planner is the boundary between unstructured LLM text and typed execution.
It parses raw LLM output into an `AgentDecision` — either a `ToolCall` or a `FinalAnswer`.

Parsing strategy (in priority order):
1. Look for `Final Answer:` → `DecisionType.FINAL_ANSWER`
2. Look for `Action:` + `Action Input:` → `DecisionType.TOOL_CALL`
3. Validate the tool exists in the registry
4. Parse `Action Input` as JSON (with Python dict fallback)
5. If nothing matches → treat entire output as final answer (graceful fallback)

The planner is intentionally simple text parsing — no regex complexity, no LLM calls.
Parse failures are observable (logged as metrics) and degrade gracefully.

**Implementation:** `packages/agents/planner.py`

## The Executor

The executor dispatches `ToolCall` objects to the correct tool implementation.
It does not handle errors — `BaseTool.execute()` wraps all exceptions into
`ToolResult(success=False)`. The executor's job is orchestration and observability.

**Implementation:** `packages/agents/executor.py`

## Tool Registry

The tool registry is the single source of truth for available tools.
It serves two purposes:
1. **Prompt generation:** renders tool descriptions for the system prompt
2. **Dispatch:** looks up tool instances by name for execution

Adding a tool = implement `BaseTool` + call `registry.register(tool)`.

**Implementation:** `packages/agents/tool_registry.py`

## Multi-Agent Orchestration

One strong orchestrator is preferred over many weak agents.

The orchestrator receives the user request and decides:
- Answer directly (simple queries)
- Delegate to a specialist (complex, domain-specific tasks)

Specialists are: planner, coding, retrieval, debugging, devops.
Each specialist has a filtered tool registry and specialized system prompt.
Delegation is via the `delegate_to_agent` tool. Max depth: 1 (no recursive delegation).

**Key insight:** Specialists share the same `AgentRuntime` implementation.
Only the system prompt and allowed tools differ. Data, not classes.

**Implementation:** `packages/agents/orchestrator.py`, `packages/agents/agent_types.py`


---

# 2. RELIABILITY ENGINEERING

## The Retry Amplification Problem — A Real Case Study

During the Phase 6 audit of this codebase, a critical reliability bug was discovered:

**The setup:**
- `AgentRuntime._call_llm_with_resilience()` wrapped LLM calls with `RetryPolicy(max_attempts=3)`
- `VertexAIService._complete_with_model()` also wrapped LLM calls with `RetryPolicy(max_attempts=3)`
- These two retry layers were independent and nested

**The math:**
```
1 logical LLM call
  → AgentRuntime retry layer: up to 3 attempts
    → Each attempt: VertexAIService retry layer: up to 3 attempts
      = up to 9 actual API calls per logical LLM call
```

**The failure mode under load:**
1. Vertex AI becomes rate-limited (429 responses)
2. Both retry layers kick in simultaneously
3. 9× the expected API call volume hits the already-degraded service
4. Rate limiting worsens, more retries trigger, more rate limiting
5. Circuit breaker opens — but only after the damage is done

**The fix:**
Remove the retry layer from `AgentRuntime`. The provider layer (`VertexAIService`)
owns all retry logic. The runtime layer owns circuit breaker and timeout only.

**The principle:**
**Only one layer in the call stack may own retry logic for a given operation.**

This is one of the most common reliability mistakes in distributed systems.
It appears in microservices (service A retries → service B retries → database retries),
in HTTP clients (application retry + SDK retry + load balancer retry), and in
AI systems (runtime retry + provider retry).

## Circuit Breaker

The circuit breaker prevents cascading failures when an external service is degraded.

```
CLOSED → normal operation
  ↓ (N consecutive failures)
OPEN → reject all requests immediately
  ↓ (recovery_seconds elapsed)
HALF_OPEN → allow one probe request
  ↓ success          ↓ failure
CLOSED              OPEN (reopen)
```

**Why it matters:** Without a circuit breaker, every request to a degraded service
waits for the full timeout (60s) before failing. Under load, this exhausts the
thread/connection pool and brings down the entire service — not just the LLM feature.

**Critical lifecycle rule:** Circuit breaker instances MUST be long-lived.
A circuit breaker recreated per request resets to CLOSED on every call.
Its entire value is the accumulated failure state across multiple requests.

**Implementation:** `packages/agents/resilience.py`

## Differentiated Retry Policy

Not all errors should be retried. Retrying permanent errors wastes time and
can make the situation worse (e.g., retrying an auth failure generates more
auth failure logs and may trigger account lockout).

```
Transient (retry with exponential backoff + jitter):
  - Network errors, connection resets
  - Rate limit (429)
  - Service unavailable (503)
  - Internal server error (500)

Permanent (fail immediately, zero retries):
  - Authentication failure (401, 403)
  - Invalid request (400)
  - Model not found (404)
  - Quota exhausted (billing)
  - Context length exceeded
```

**Jitter:** Add random variation to backoff delays to prevent thundering herd.
Without jitter, all retrying clients wake up at the same time and hammer the service.

## Timeout Ownership

Every external call must have a timeout. Timeouts prevent hung connections
from accumulating and exhausting resources.

```
LLM calls:        60s (configurable)
Tool execution:   30s (configurable)
Complete run:     300s (configurable)
```

Timeouts must surface as ERROR events to the user — never as hung connections.
`asyncio.wait_for` is the correct mechanism in async Python.

## Graceful Degradation

Every subsystem must degrade gracefully when its dependencies fail.

**Memory summarization example:**
```python
# WRONG — summarization failure crashes the agent run
await self._maybe_summarize(session_id)

# CORRECT — summarization failure is logged and skipped
try:
    await self._maybe_summarize(session_id)
except Exception as exc:
    logger.warning("summarization_failed_degrading", error=str(exc))
    # Continue with raw turns — better than failing the run
```

**The principle:** A subsystem failure should degrade the feature, not crash the system.

## Fallback Model Strategy

On quota or rate-limit errors, try a cheaper/faster model before giving up.

```
Primary:  gemini-2.0-flash
Fallback: gemini-2.0-flash-lite
```

The fallback is transparent to the caller. The response quality may be slightly
lower but the user gets an answer instead of an error.


---

# 3. PERFORMANCE ENGINEERING

## CPU-Bound vs Network-Bound Systems

Understanding which operations are CPU-bound vs network-bound is the foundation
of performance engineering. Optimizing the wrong thing wastes engineering time.

**CPU-bound:** computation is the bottleneck (parsing, encoding, hashing)
**Network-bound:** waiting for external services is the bottleneck (API calls, DB queries)

This system is **network-bound**. The LLM API is the dominant latency source.

### Measured Latency Hierarchy

```
LLM call (Gemini Flash):     1,000 – 8,000ms   ← BOTTLENECK
LLM call (Gemini Pro):       2,000 – 30,000ms  ← BOTTLENECK
Embedding call (batch):      100 – 500ms        ← Significant
Reranking (5 sequential):    5,000 – 15,000ms  ← BOTTLENECK (fixable)
Reranking (5 concurrent):    1,000 – 3,000ms   ← After fix
pgvector search:             10 – 100ms         ← Acceptable
Redis operation:             1 – 5ms            ← Negligible
Chunker (large doc):         50 – 200ms         ← Negligible vs LLM
Planner parse:               < 0.1ms            ← Negligible
Token estimation:            < 0.01ms           ← Negligible
```

**Implication:** Optimizing the planner parser saves < 0.1ms per request.
Reducing one LLM step saves 1,000 – 8,000ms. Focus on the right things.

## Latency Distribution Thinking

Always think in distributions, not averages.

```
p50 (median):  typical user experience
p95:           what 1 in 20 users experiences
p99:           what 1 in 100 users experiences
```

A system with p50=2s and p99=30s is not a "2-second system."
It is a system that occasionally takes 30 seconds.

**Why p99 matters:** In a system with 1,000 requests/minute, p99 latency
affects 10 users per minute. At scale, tail latency is not rare — it's constant.

## The Reranker Bottleneck

The LLM-based reranker is the most fixable performance problem in this system.

**Current:** N sequential LLM calls (one per retrieved chunk)
```python
for result in results:
    score = await self._score_chunk(query, result.text)  # 1-2s each
# Total: N × 1-2s = 5-10s for top_k=5
```

**Fixed:** N concurrent LLM calls
```python
scores = await asyncio.gather(*[
    self._score_chunk(query, result.text) for result in results
])
# Total: ~1-2s regardless of N (limited by slowest call)
```

Same cost. N× lower latency. This is the highest-ROI performance fix in the system.

## Orchestration Overhead

Multi-agent orchestration adds latency at every delegation boundary.

```
User request
  → Orchestrator LLM call (1-8s)
  → Delegation decision
  → Specialist LLM call (1-8s)
  → Specialist tool calls (variable)
  → Specialist final answer
  → Orchestrator synthesis LLM call (1-8s)
  → Response
```

A 3-step orchestrated workflow can take 10-30 seconds minimum.
This is the cost of multi-agent coordination. Design workflows to minimize
unnecessary delegation.

## First-Token Latency

For streaming responses, **first-token latency** is the primary UX metric.
Users perceive a system as "fast" if they see the first word quickly,
even if the total response takes longer.

Measure and optimize:
- Time from request receipt to first token yielded
- Emit as `metric.llm_first_token` with `time_to_first_token_ms`

## Throughput vs Latency

These are often in tension:
- **Batching** improves throughput but increases latency (wait for batch to fill)
- **Streaming** reduces first-token latency but increases per-token overhead
- **Caching** reduces latency but requires cache invalidation logic

For this system: prioritize latency over throughput. Users are waiting for responses.


---

# 4. OBSERVABILITY ENGINEERING

## The Four Pillars

A production system is only as observable as its instrumentation.

```
Logs    → what happened (structured JSON, correlation IDs)
Traces  → how it happened (distributed spans, timing)
Metrics → how often and how fast (aggregated numbers)
Events  → what changed (execution journal, state transitions)
```

All four are required. Missing any one creates blind spots.

## Structured Logging

Logs must be structured JSON — not free-form strings.

```python
# WRONG — unstructured, unsearchable
logger.info(f"Agent run completed in {latency}ms with {steps} steps")

# CORRECT — structured, filterable, aggregatable
logger.info(
    "agent_run_complete",
    session_id=session_id,
    run_id=run_id,
    latency_ms=latency_ms,
    steps=steps,
    success=True,
)
```

**Why:** Structured logs can be queried, aggregated, and alerted on.
Free-form strings require regex parsing and are fragile.

## Correlation IDs

Every request gets a unique `correlation_id` that flows through all logs,
traces, and metrics for that request.

```
HTTP request → CorrelationIDMiddleware injects X-Correlation-ID
  → All logs for this request include correlation_id
  → All Langfuse spans include correlation_id
  → All metric events include correlation_id
  → All retry logs include correlation_id
```

Without correlation IDs, debugging a distributed failure requires
manually correlating timestamps across multiple log streams. With them,
a single grep finds every log entry for a specific request.

## Distributed Tracing

This system uses two tracing systems:
- **Langfuse:** agent-level tracing (runs, steps, tool calls, memory)
- **OpenTelemetry:** infrastructure-level tracing (HTTP requests, DB queries)

**Known gap:** These two systems are currently independent. A single agent run
generates both a Langfuse trace and OTel spans, but they share no common ID.
Debugging requires searching two systems separately.

**Fix:** Inject Langfuse trace ID as an OTel span attribute. Inject OTel trace ID
into Langfuse metadata. Single correlation ID links both systems.

## The metric.* Pattern

All key operations emit `metric.*` log events with consistent schemas.
These can be consumed by any log aggregator (Datadog, CloudWatch, etc.)
to build dashboards and alerts without a separate metrics infrastructure.

```python
logger.info(
    "metric.agent_run",
    session_id=session_id,
    run_id=run_id,
    latency_ms=450.2,
    steps_taken=3,
    tool_calls=2,
    success=True,
)
```

The `metric.` prefix makes these events filterable from operational logs.

## Execution Replayability

A production AI system must be replayable. Every agent run should be
reproducible for debugging, auditing, and evaluation.

**What replayability requires:**
1. Every `AgentEvent` persisted to an execution journal
2. The exact context sent to the LLM at each step (not just the response)
3. Tool call inputs and outputs
4. Memory state at the start of the run
5. Timestamps for every step

**Current state:** Runs are not persisted. If a run produces a bad response,
there is no way to inspect what happened.

**Roadmap:** Append-only execution journal in PostgreSQL.
Replay API: `GET /api/v1/runs/{run_id}/events`

## Runtime Introspection

Operators need visibility into the runtime state without reading logs.

Required introspection endpoints:
- `GET /api/v1/debug/runtime` — circuit breaker states, active sessions, error rates
- `GET /api/v1/debug/sessions/{session_id}/memory` — memory state for a session
- `GET /api/v1/runs/{run_id}/events` — execution journal for a run

These endpoints must be protected by admin authentication.


---

# 5. CONTEXT ENGINEERING

## The Token Budget Problem

LLMs have a finite context window. As conversations grow, tool outputs accumulate,
and memory is injected, the context can exceed the model's limit.

Without a token budget:
- Silent truncation by the model (unpredictable behavior)
- Degraded reasoning quality (model loses track of earlier context)
- Higher costs (more tokens = more money)
- Higher latency (more tokens = slower response)

With a token budget:
- Predictable truncation (oldest history first)
- Controlled costs
- Consistent reasoning quality

## Token Estimation

Exact token counting requires a tokenizer call (expensive).
Approximate counting uses a character heuristic (fast, good enough).

```python
# Heuristic: 4 characters ≈ 1 token (English prose)
def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
```

**Limitations:**
- Underestimates for code (dense tokens)
- Overestimates for some non-English languages
- Does not account for special tokens or role markers

**Roadmap:** Integrate Vertex AI tokenize API for exact counts.
Fall back to heuristic if tokenize call fails.

## Truncation Priority

When context exceeds budget, truncate in this order:

```
1. Oldest conversation turns (least relevant)
2. Verbose tool outputs (truncate to max_tool_output_chars)
3. Long-term memory facts (least recently accessed)
4. Summary (compress further if possible)

NEVER truncate:
- System messages (contain instructions and tool descriptions)
- Most recent user message
- Most recent assistant response
```

## Tool Output Truncation

A single `read_file` call on a large file can return 50,000+ characters.
Injecting this directly into the LLM context would consume most of the token budget.

```python
# Truncate tool output before injection
truncated = output[:max_tool_output_chars]
notice = f"\n\n[Output truncated at {max_tool_output_chars} chars]"
return truncated + notice
```

The truncation notice tells the LLM that the output was cut — preventing it from
assuming the file ended at the truncation point.

## Memory Context Injection

Memory context (short-term turns, summary, long-term facts) is injected as a
system message before the conversation. This must be token-aware.

**Problem:** A large memory context can consume a significant portion of the
token budget before the conversation even starts.

**Solution:** Estimate memory token cost before injection. If memory + conversation
would exceed budget, prioritize: recent turns > summary > long-term facts > oldest turns.

## Prompt Caching (Roadmap)

The system prompt and tool descriptions are static across all requests.
Vertex AI supports cached content for static prefixes.

**How it works:**
1. Upload the static system prompt + tool descriptions as cached content
2. Reference the cache key in every LLM call
3. Vertex AI skips re-processing the cached prefix

**Estimated savings:** 30-40% reduction in input token costs.

## Dynamic Tool Selection (Roadmap)

Currently, all tool descriptions are included in every LLM call.
For a registry with 6+ tools, this is 500-1000 tokens per step.

**Future approach:**
1. At each ReAct step, score available tools for relevance to the current task
2. Include only the top-K most relevant tool descriptions
3. Reduces system prompt size by 50-70% for large registries

## Retrieval Prioritization

Position RAG context immediately before the user message, not at the top
of the system prompt. Transformer attention is strongest near the end of
the context window (recency bias). The most relevant context should be
closest to the query.


---

# 6. EVALUATION ENGINEERING

## Evaluation Is a First-Class Production System

Evaluation is not a testing afterthought. It is a production system that runs
continuously alongside the agent runtime, measuring quality on every response.

**The mistake:** Building an evaluator as a library that is never called.
This is what happened in this codebase — `AgentEvaluator` existed and worked
correctly but was never wired into `AgentService`. Quality metrics were not
being collected in production.

**The fix:** Call `AgentEvaluator.evaluate_response()` at the end of every
agent run. Store results in PostgreSQL. Build dashboards on top.

## LLM-as-Judge

LLM-as-judge uses a separate LLM call to evaluate the quality of a response.

```python
prompt = """
Evaluate this response on three dimensions (0.0 to 1.0):
Query: {query}
Response: {response}

relevance: <score>      # Does it address the query?
completeness: <score>   # Does it cover key aspects?
accuracy: <score>       # Is the information correct?
"""
```

**Strengths:** Flexible, no ground truth required, scales to any domain.
**Weaknesses:** Self-referential (LLM judging LLM), expensive (extra LLM call),
not deterministic (scores vary between runs).

**Mitigation:** Use a different model for evaluation than for generation.
Use temperature=0 for deterministic scoring. Average scores over multiple runs.

## Trajectory Evaluation

Response quality alone is insufficient. A good final answer reached via 8
unnecessary tool calls is not the same as one reached in 2 steps.

Trajectory evaluation measures:
- **Step efficiency:** did the agent reach the answer in minimum steps?
- **Tool selection accuracy:** did the agent use the right tools?
- **Reasoning coherence:** was the thought process logical?
- **Unnecessary tool calls:** did the agent call tools it didn't need?

**Implementation:** Record the full (thought, action, observation) sequence
per run. Score each step independently. Aggregate into a trajectory score.

## Hallucination Detection

For RAG responses, the final answer must be grounded in the retrieved context.

```python
grounding_prompt = """
Is this answer supported by the following context?
Answer: {answer}
Context: {retrieved_chunks}

Respond: GROUNDED / PARTIALLY_GROUNDED / NOT_GROUNDED
Explanation: <brief explanation>
"""
```

This is a separate LLM call after the main response. It must be:
- Non-blocking (async, does not delay the response to the user)
- Protected by circuit breaker
- Stored with the evaluation record

## Regression Benchmarks

A curated dataset of (query, expected_answer, expected_tools) tuples must be
maintained and run against every PR.

```json
{
  "id": "bench-001",
  "query": "What does the create_app function do?",
  "expected_tools": ["read_file", "search_files"],
  "expected_answer_contains": ["FastAPI", "middleware", "router"],
  "max_steps": 4
}
```

**Quality gates:** Block merge if:
- Quality score regression > 5% on benchmark dataset
- Step efficiency regression > 20% (agent taking more steps than baseline)
- Any benchmark query produces a NOT_GROUNDED hallucination

## Evaluation Data Pipeline

```
Agent run completes
    ↓
AgentEvaluator.evaluate_response() (async, non-blocking)
    ↓
Store EvaluationResult in PostgreSQL
    ↓
Aggregate into session-level and system-level metrics
    ↓
Langfuse scores (optional — for Langfuse dashboard)
    ↓
Alert if quality drops below threshold
```


---

# 7. DISTRIBUTED SYSTEMS LEARNINGS

## In-Memory State Does Not Scale

Any state stored in a Python dict inside a running process has these properties:
- Lost on process restart
- Not shared across replicas
- Unbounded growth (no eviction unless explicitly coded)
- Not visible to operators

This is acceptable for local development. It is not acceptable for production.

**In this codebase, the following are in-process and must be migrated:**

| State | Current | Target |
|---|---|---|
| Session history | `_sessions: dict` | Redis with TTL |
| Vector memory | `_store: dict` | pgvector table |
| Circuit breaker state | In-process | Redis-backed |
| Memory summaries | Redis (correct) | ✅ Already correct |

## Redis as Coordination Layer

Redis serves multiple roles in this system:

1. **Session state:** store conversation history across replicas
2. **Rate limiting:** sliding window counters shared across replicas
3. **Circuit breaker:** shared failure state across replicas (roadmap)
4. **Task queue:** Celery broker for background workers
5. **Memory cache:** summaries and long-term facts

**Key design principle:** Redis is the coordination layer for distributed state.
Anything that needs to be shared across replicas goes through Redis.

## Distributed Circuit Breaker

**The problem:** In a 3-replica deployment, each replica has its own circuit breaker.
If Vertex AI becomes degraded:
- Replica 1: opens circuit after 5 failures
- Replica 2: still CLOSED, continues sending requests
- Replica 3: still CLOSED, continues sending requests

Two-thirds of replicas continue hammering the degraded service.

**The solution:** Back circuit breaker state with Redis.
All replicas read and write the same failure counter and state.
When the circuit opens on one replica, it opens on all replicas.

```python
# Redis-backed circuit breaker state
redis.incr(f"circuit:{name}:failures")
redis.set(f"circuit:{name}:state", "open", ex=recovery_seconds)
```

## Workflow Execution and Dependency Management

The `WorkflowExecutor` implements a simple topological sort to execute tasks
in dependency order. This is correct for sequential execution.

**The gap:** Tasks with no dependencies could run concurrently.
The current implementation runs them sequentially.

**The fix:** Identify tasks with all dependencies met, execute them concurrently
via `asyncio.gather`, then check for newly unblocked tasks.

```python
# Find all tasks ready to run (dependencies met)
ready = [t for t in remaining if all(d in completed for d in t.depends_on)]

# Execute ready tasks concurrently
results = await asyncio.gather(*[run_task(t) for t in ready])
```

## Execution Persistence and Resumability

Long-running workflows are vulnerable to infrastructure events (pod restarts,
network partitions, quota exhaustion). Without persistence, a workflow that
fails at step 8 of 10 must restart from step 1.

**The solution:** Checkpoint completed task results to Redis or PostgreSQL.
On restart, load the checkpoint and resume from the last completed task.

```python
# After each task completes
await redis.set(f"workflow:{run_id}:task:{task_id}", result, ex=3600)

# On startup/resume
completed = await redis.keys(f"workflow:{run_id}:task:*")
```

## The Event Sourcing Pattern

Event sourcing stores state as a sequence of events rather than a current snapshot.

```
Traditional: store current state → "session has 5 messages"
Event sourced: store events → "message added", "message added", ... (5 times)
```

**Benefits for AI systems:**
- **Replayability:** re-execute any past run by replaying its events
- **Auditability:** complete history of every state change
- **Debugging:** inspect the exact state at any point in time
- **Recovery:** rebuild state from events after a failure

**Implementation for this system:**
```sql
CREATE TABLE agent_run_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      UUID NOT NULL,
    session_id  UUID NOT NULL,
    step        INTEGER NOT NULL,
    event_type  VARCHAR(50) NOT NULL,
    content     TEXT,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON agent_run_events (run_id, step);
CREATE INDEX ON agent_run_events (session_id, created_at);
```


---

# 8. RAG PIPELINE ENGINEERING

## The Full Pipeline

```
Document arrives (text, PDF, CSV, Excel, markdown)
    ↓
Extract text (packages/rag/extractor.py)
    ↓
Chunk into overlapping segments (packages/rag/chunker.py)
    ↓
Embed chunks in batches (packages/rag/embeddings.py)
    ↓
Store chunks + embeddings in pgvector (app/repositories/document.py)
    ↓
Query arrives
    ↓
Embed query (single vector)
    ↓
Cosine similarity search (pgvector IVFFlat index)
    ↓
Rerank results (packages/rag/reranker.py) ← MUST BE CONCURRENT
    ↓
Inject top-K chunks into LLM context
```

## Chunking Strategy

Documents are split on paragraph boundaries (double newlines) with configurable overlap.
Oversized paragraphs are split on sentence boundaries.
Overlap preserves context across chunk boundaries.

```
max_chunk_size=800 chars ≈ 200 tokens (well within embedding limits)
overlap=100 chars ≈ 25 tokens (enough context continuity)
```

**Why overlap matters:** Without overlap, a sentence split across two chunks
loses context. The end of chunk N and the start of chunk N+1 may be
semantically disconnected. Overlap ensures continuity.

## Embedding Batching

Embedding API calls are batched to minimize round trips.
Token-aware batching ensures no batch exceeds the API's token limit.

```python
# Build batches respecting token limits
batches = _build_token_aware_batches(texts, max_tokens_per_batch=20_000)
for batch in batches:
    embeddings = await client.embed_content(batch)
```

## pgvector and IVFFlat

pgvector stores embeddings as `vector(768)` columns.
IVFFlat (Inverted File with Flat quantization) enables approximate nearest-neighbor search.

```sql
CREATE INDEX ON document_chunks USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

`lists` parameter: sqrt(number_of_rows) is a good starting point.
More lists = faster search, less accurate. Fewer lists = slower, more accurate.

## Reranking

Vector similarity is a good first pass but not always the best relevance signal.
The reranker applies a cross-encoder style scoring to re-rank the top-K results.

**Current implementation:** LLM-as-judge (one LLM call per chunk)
**Performance issue:** Sequential calls add 5-10s for top_k=5
**Fix:** Concurrent calls via `asyncio.gather`
**Future:** Dedicated cross-encoder model (Cohere Rerank, sentence-transformers)

---

# 9. MEMORY SYSTEMS ENGINEERING

## Memory Type Hierarchy

```
Short-term memory:  sliding window of recent turns (in-process)
Long-term memory:   explicit facts per session (Redis)
Summarized memory:  LLM-compressed older turns (Redis)
Vector memory:      embedding-based episodic recall (in-process → pgvector)
```

## Summarization Trigger

When short-term memory reaches the threshold (16 turns), older turns are
compressed into a summary via LLM. The summary replaces the raw turns.

```
Before: [turn 1, turn 2, ..., turn 16]
After:  summary="User asked about X, Y, Z. Agent explained..."
        + [turn 11, turn 12, ..., turn 16]  (6 most recent kept)
```

**Why keep recent turns:** The most recent context is most relevant.
The summary captures the gist of older turns without the verbosity.

## Memory Failure Isolation

Memory operations must never fail agent runs:

```python
# WRONG — summarization failure crashes the run
await self._maybe_summarize(session_id)

# CORRECT — summarization failure is logged and skipped
try:
    await self._maybe_summarize(session_id)
except Exception as exc:
    logger.warning("summarization_skipped", error=str(exc))
    # Continue — raw turns are still available
```

## Vector Memory for Episodic Recall

Vector memory enables "remember when we discussed X?" even if X was many
turns ago and has been pruned from short-term memory.

Each turn is embedded and stored. Retrieval uses cosine similarity against
the current query to find semantically relevant past exchanges.

**Current limitation:** In-process storage. Lost on restart.
**Target:** pgvector table with session_id index.

---

# 10. TOOL SYSTEM ENGINEERING

## The BaseTool Contract

Every tool must implement:
```python
class BaseTool:
    name: str                    # Unique identifier
    description: str             # Human-readable description for LLM
    parameters_schema: dict      # JSON Schema for input validation

    async def _run(self, **kwargs) -> Any:
        """Tool-specific implementation."""
        ...

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        """Wraps _run() with timing, logging, and exception handling."""
        # BaseTool.execute() catches ALL exceptions
        # Tools NEVER crash the runtime
        ...
```

The base class wraps all exceptions into `ToolResult(success=False)`.
This is the contract: tools return results, they do not raise exceptions.

## Security Boundaries

Each tool category has explicit security boundaries:

**Filesystem:** Sandboxed to workspace root. Path traversal blocked.
```python
resolved = (workspace_root / path).resolve()
if not resolved.is_relative_to(workspace_root):
    raise SecurityError("Path traversal detected")
```

**Terminal:** Explicit allowlist. Dangerous commands blocked.
```python
ALLOWED_COMMANDS = {"git", "python", "pytest", "ruff", "black", "mypy", "echo"}
BLOCKED_GIT_SUBCOMMANDS = {"push", "commit", "reset", "force", "delete"}
```

**Database:** SELECT only. DML/DDL blocked.
```python
BLOCKED_KEYWORDS = {"INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "EXEC"}
```

**Web search:** Rate limited. No credential exposure in results.


---

# 11. INFRASTRUCTURE AND DEPLOYMENT

## Docker Compose (Local Development)

All 5 services run locally via Docker Compose:
- `postgres` (pgvector/pgvector:pg16) — vector database
- `redis` (redis:7.4-alpine) — cache, queue, session state
- `backend` (FastAPI + uvicorn, hot-reload) — API server
- `frontend` (Vite dev server) — React UI
- `worker` (Celery) — background task processor

## Celery Workers

Background tasks for:
- Document ingestion (chunking + embedding) — avoids blocking the API
- Memory summarization — triggered when short-term memory fills

Tasks retry on transient failures with exponential backoff.
**Known gap:** No dead letter queue for permanently failed tasks.

## Alembic Migrations

All schema changes via Alembic. Never modify the database schema directly.

```bash
# Create a new migration
alembic revision --autogenerate -m "add vector_memory_entries table"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## Cloud Run Deployment

Production deployment via Google Cloud Run:
- Secrets via Google Secret Manager (never in environment variables in production)
- Database via Cloud SQL (managed PostgreSQL)
- Health probes: liveness (`/health`) and readiness (`/health`)
- Auto-scaling based on request concurrency

## CI/CD Pipeline

GitHub Actions runs on every push to main/develop and every PR:
1. Backend: ruff lint → black format check → mypy type check → pytest
2. Frontend: eslint → typecheck → build
3. Docker: build backend + frontend images (main branch only)

**Rule:** Never merge a broken build.

---

# 12. ARCHITECTURAL DECISION RECORDS

## ADR-001: Provider Layer Owns Retries

**Decision:** `VertexAIService` owns all retry logic for LLM calls.
`AgentRuntime` owns circuit breaker and timeout only.

**Context:** Discovered retry amplification bug where nested retry layers
could trigger up to 9 API calls per logical LLM call.

**Consequences:** All retry configuration lives in `VertexAIService`.
The runtime layer is simpler and cannot accidentally amplify retries.

## ADR-002: Long-Lived Runtime Objects

**Decision:** `AgentRuntime`, `MemoryManager`, and `AgentTracer` are
module-level singletons, lazy-initialized on first use.

**Context:** Circuit breaker state must persist across requests.
Creating a new runtime per request resets the circuit breaker to CLOSED.

**Consequences:** These objects are shared across all requests.
They must be thread-safe (they are — asyncio is single-threaded).

## ADR-003: Graceful Memory Degradation

**Decision:** Memory subsystem failures must not fail agent runs.
All memory operations are wrapped in try/except with graceful fallback.

**Context:** Memory summarization makes an LLM call. If this call fails
and the exception propagates, it fails the entire agent run — not just
the summarization. This is disproportionate impact.

**Consequences:** Memory failures are logged as warnings, not errors.
The agent run continues with whatever memory state is available.

## ADR-004: Concurrent Reranker Scoring

**Decision:** Reranker scoring must use `asyncio.gather` for concurrent execution.

**Context:** Sequential reranking for top_k=5 adds 5-10 seconds to every
RAG query. This is the single largest fixable latency in the system.

**Consequences:** All N scoring calls execute concurrently. Total latency
is bounded by the slowest single call, not the sum of all calls.

## ADR-005: Evaluation in the Hot Path

**Decision:** `AgentEvaluator.evaluate_response()` is called at the end
of every agent run, asynchronously, without blocking the response.

**Context:** Evaluation was built as a library but never wired into the
agent service. Quality metrics were not being collected in production.

**Consequences:** Every agent run generates an evaluation record.
Quality trends are visible over time. Regressions can be detected.

