"""
Agent runtime schemas — typed contracts for all runtime events and state.

These are the core data structures that flow through the entire ReAct loop.
Every component speaks in these types — no raw dicts, no stringly-typed events.

Design:
- AgentEvent is the streaming unit — the API serializes these as SSE chunks
- RunState holds the mutable loop state (history, step count, tool calls made)
- ToolCall / ToolResult are the tool execution contract
- AgentDecision is what the planner produces after parsing LLM output
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ── Event types ───────────────────────────────────────────────────────────────


class AgentEventType(str, Enum):
    """All possible event types emitted by the runtime during a run."""

    REASONING = "reasoning"  # Intermediate thought text from the LLM
    TOOL_CALL = "tool_call"  # Agent decided to call a tool
    TOOL_RESULT = "tool_result"  # Tool execution completed
    TEXT = "text"  # Final answer text chunk (streaming)
    DONE = "done"  # Run complete
    ERROR = "error"  # Unrecoverable error


class AgentEvent(BaseModel):
    """
    A single streaming event emitted by the runtime.

    The API serializes these directly as SSE data payloads.
    The frontend uses `type` to decide how to render each event.
    """

    type: AgentEventType
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )


# ── Tool schemas ──────────────────────────────────────────────────────────────


class ToolCall(BaseModel):
    """A parsed tool invocation from the LLM output."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str = Field(default="")  # Set by executor for tracing


class ToolResult(BaseModel):
    """The structured output of a tool execution."""

    tool_name: str
    call_id: str
    success: bool
    output: Any  # Machine-readable result — type depends on the tool
    error: str | None = None
    duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_observation(self) -> str:
        """
        Format the result as a text observation for injection into the LLM context.
        This is what the model sees after a tool call.
        """
        if not self.success:
            return f"Tool '{self.tool_name}' failed: {self.error}"
        return f"Tool '{self.tool_name}' result:\n{self.output}"


# ── Planner decision ──────────────────────────────────────────────────────────


class DecisionType(str, Enum):
    TOOL_CALL = "tool_call"
    FINAL_ANSWER = "final_answer"


class AgentDecision(BaseModel):
    """
    What the planner produces after parsing a single LLM response.

    Either the agent wants to call a tool, or it has a final answer.
    The reasoning field captures the thought process before the decision.
    """

    decision_type: DecisionType
    reasoning: str = ""  # The "Thought:" section from ReAct output
    tool_call: ToolCall | None = None
    final_answer: str | None = None


# ── Run state ─────────────────────────────────────────────────────────────────


class RunState(BaseModel):
    """
    Mutable state for a single agent run (one user message → one response).

    Passed through the ReAct loop and updated at each step.
    Not persisted in Phase 2 — Phase 4 will add Redis-backed state.
    """

    session_id: str
    run_id: str
    user_message: str
    step: int = 0
    max_steps: int = 10
    tool_calls_made: list[ToolCall] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    final_answer: str | None = None
    is_complete: bool = False

    def increment_step(self) -> None:
        self.step += 1

    def is_at_limit(self) -> bool:
        return self.step >= self.max_steps
