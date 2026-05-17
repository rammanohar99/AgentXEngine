---
title: Context Engineering
domain: architecture
doc_type: architecture
status: active
owner: agent-runtime
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [context, token-budget, truncation, memory-injection, prompt-caching, tool-selection]
---

# Context Engineering

**Related:** [Agent Runtime](agent-runtime.md) · [Memory Systems](memory-systems.md) · [Performance Overview](../performance/overview.md) · [Phase 13 Roadmap](../roadmap/phase-13-context-engineering.md)

Context engineering is the discipline of managing what goes into the LLM's context window —
what to include, what to truncate, and in what order — to maximize response quality
while controlling cost and latency.

---

## The Token Budget Problem

LLMs have a finite context window. As conversations grow, tool outputs accumulate,
and memory is injected, the context can exceed the model's limit.

**Without a token budget:**
- Silent truncation by the model (unpredictable behavior)
- Degraded reasoning quality (model loses track of earlier context)
- Higher costs (more tokens = more money)
- Higher latency (more tokens = slower response)

**With a token budget:**
- Predictable truncation (oldest history first)
- Controlled costs
- Consistent reasoning quality

Every LLM call MUST be gated by a token budget check before sending.

**Implementation:** `packages/agents/context_manager.py`

---

## Token Estimation

Exact token counting requires a tokenizer call (expensive).
Approximate counting uses a character heuristic (fast, good enough for most cases).

```python
# Heuristic: 4 characters ≈ 1 token (English prose)
def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
```

**Known limitations:**
- Underestimates for code (dense tokens — more tokens per character)
- Overestimates for some non-English languages
- Does not account for special tokens, role markers, or formatting overhead

**Roadmap (Phase 13):** Integrate Vertex AI tokenize API for exact counts.
Fall back to character heuristic if the tokenize call fails.

---

## Truncation Priority

When context exceeds budget, truncate in this order:

```
1. Oldest conversation turns        (least relevant to current query)
2. Verbose tool outputs             (truncate to max_tool_output_chars)
3. Long-term memory facts           (least recently accessed first)
4. Summary                          (compress further if possible)
```

**Never truncate:**
- System messages (contain tool descriptions and instructions)
- The most recent user message
- The most recent assistant response

---

## Tool Output Truncation

A single `read_file` call on a large file can return 50,000+ characters.
Injecting this directly into the LLM context would consume most of the token budget.

```python
truncated = output[:max_tool_output_chars]
notice = f"\n\n[Output truncated at {max_tool_output_chars} chars]"
return truncated + notice
```

The truncation notice tells the LLM that the output was cut — preventing it from
assuming the file ended at the truncation point.

---

## Retrieval Positioning

RAG context should be positioned immediately before the user message,
not at the top of the system prompt.

**Why:** Transformer attention is strongest near the end of the context window
(recency bias). The most relevant context should be closest to the query.

---

## Budget Metric

Every LLM call emits a `metric.context_budget` event:

```python
logger.info(
    "metric.context_budget",
    estimated_tokens=estimated,
    max_tokens=max_tokens,
    utilization_pct=round(estimated / max_tokens * 100, 1),
    truncated=was_truncated,
)
```

---

## Roadmap

### Phase 11: Prompt Caching

The system prompt and tool descriptions are static across all requests.
Vertex AI supports cached content for static prefixes.

**How it works:**
1. Upload the static system prompt + tool descriptions as cached content
2. Reference the cache key in every LLM call
3. Vertex AI skips re-processing the cached prefix

**Estimated savings:** 30-40% reduction in input token costs.

### Phase 13: Dynamic Tool Selection

Currently, all tool descriptions are included in every LLM call.
For a registry with 6+ tools, this is 500-1000 tokens per step.

**Approach:**
1. At each ReAct step, score available tools for relevance to the current task
2. Include only the top-K most relevant tool descriptions
3. Reduces system prompt size by 50-70% for large registries

### Phase 13: Exact Token Counting

Replace the character heuristic with the Vertex AI tokenize API.
Fall back to heuristic if the tokenize call fails.
