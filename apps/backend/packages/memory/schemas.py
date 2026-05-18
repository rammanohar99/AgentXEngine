"""
Memory system schemas — typed contracts for all memory operations.

Memory types implemented:
- ShortTermMemory  — sliding window of recent messages (in-process)
- LongTermMemory   — Redis-backed persistent key/value facts
- SummarizedMemory — LLM-compressed conversation summaries

All memory types share a common MemoryEntry base so the context
builder can assemble them uniformly into the prompt.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    SUMMARY = "summary"
    VECTOR = "vector"


class MemoryEntry(BaseModel):
    """A single piece of memory — the atomic unit across all memory types."""

    id: str
    session_id: str
    memory_type: MemoryType
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    importance: float = 1.0  # 0.0–1.0, used for pruning decisions


class ConversationTurn(BaseModel):
    """A single user/assistant exchange stored in short-term memory."""

    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )


class MemoryContext(BaseModel):
    """
    Assembled memory context passed to the prompt builder.

    Contains all relevant memory entries for a given session,
    ready to be formatted into the system prompt.
    """

    session_id: str
    short_term: list[ConversationTurn] = Field(default_factory=list)
    summary: str | None = None
    long_term_facts: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.short_term and not self.summary and not self.long_term_facts

    def to_prompt_section(self) -> str:
        """Format memory context as a prompt section."""
        if self.is_empty():
            return ""

        sections: list[str] = ["## Memory Context\n"]

        if self.summary:
            sections.append(f"### Conversation Summary\n{self.summary}\n")

        if self.long_term_facts:
            facts_text = "\n".join(f"- {fact}" for fact in self.long_term_facts)
            sections.append(f"### Known Facts\n{facts_text}\n")

        if self.short_term:
            sections.append("### Recent Conversation")
            for turn in self.short_term:
                role_label = "User" if turn.role == "user" else "Assistant"
                # Truncate long turns to avoid prompt bloat
                content = turn.content[:500] + "..." if len(turn.content) > 500 else turn.content
                sections.append(f"{role_label}: {content}")

        return "\n".join(sections)
