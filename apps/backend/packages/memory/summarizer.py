"""
Memory summarizer — compresses conversation history into a concise summary.

When short-term memory approaches its window limit, the summarizer
condenses older turns into a single summary string. This preserves
context without overloading the prompt with raw history.

Design:
- Accepts an LLM provider (same LLMProvider protocol as the runtime)
- Produces a single paragraph summary of the conversation so far
- The summary replaces the oldest turns in the context
- Summaries are stored in Redis with a TTL

Usage:
    summarizer = MemorySummarizer(llm_provider)
    summary = await summarizer.summarize(session_id, turns)
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import structlog

from packages.memory.schemas import ConversationTurn

logger = structlog.get_logger(__name__)

SUMMARIZE_PROMPT = """\
Summarize the following conversation in 2-3 sentences. Focus on:
- The main topics discussed
- Key decisions or conclusions reached
- Important context for future messages

Be concise. Do not include greetings or filler.

Conversation:
{conversation}

Summary:"""


@runtime_checkable
class SummarizerLLM(Protocol):
    """Minimal LLM interface needed for summarization."""

    async def complete(
        self, messages: list[Any], temperature: float = 0.1, **kwargs: Any
    ) -> Any: ...


class MemorySummarizer:
    """
    Compresses conversation turns into a summary using an LLM.

    Injected with an LLM provider — no direct Vertex AI dependency.
    """

    def __init__(self, llm_provider: SummarizerLLM) -> None:
        self._llm = llm_provider

    async def summarize(self, session_id: str, turns: list[ConversationTurn]) -> str:
        """
        Summarize a list of conversation turns.

        Returns a plain text summary string.
        Falls back to a simple concatenation if the LLM call fails.
        """
        if not turns:
            return ""

        conversation_text = self._format_turns(turns)

        try:
            from packages.agents.runtime import Message

            prompt = SUMMARIZE_PROMPT.format(conversation=conversation_text)
            messages = [Message(role="user", content=prompt)]
            response = await self._llm.complete(messages=messages, temperature=0.1)
            summary = str(response.text).strip()

            logger.info(
                "memory_summarized",
                session_id=session_id,
                turns_count=len(turns),
                summary_length=len(summary),
            )
            return summary

        except Exception as exc:
            logger.warning("memory_summarize_failed", session_id=session_id, error=str(exc))
            # Fallback: return a truncated version of the conversation
            if len(conversation_text) > 500:
                return conversation_text[:500] + "..."
            return conversation_text

    def _format_turns(self, turns: list[ConversationTurn]) -> str:
        """Format turns as a readable conversation string."""
        lines = []
        for turn in turns:
            role_label = "User" if turn.role == "user" else "Assistant"
            content = turn.content[:300] + "..." if len(turn.content) > 300 else turn.content
            lines.append(f"{role_label}: {content}")
        return "\n".join(lines)
