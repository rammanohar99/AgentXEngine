"""
Memory Manager — unified interface to all memory systems.

This is the single entry point the agent runtime uses for memory.
It coordinates short-term, long-term, and summarized memory.

Responsibilities:
- Record each conversation turn in short-term memory
- Trigger summarization when short-term memory approaches its limit
- Store and retrieve long-term facts
- Assemble MemoryContext for prompt injection

Design:
- Injected with short-term, long-term, and summarizer instances
- Summarization is triggered automatically at a configurable threshold
- The runtime calls record_turn() after each exchange
- The runtime calls get_context() before each LLM call

Usage:
    manager = MemoryManager(short_term, long_term, summarizer)
    await manager.record_turn(session_id, "user", "Hello")
    context = await manager.get_context(session_id)
    prompt_section = context.to_prompt_section()
"""

from __future__ import annotations

import structlog

from packages.memory.long_term import LongTermMemory
from packages.memory.schemas import MemoryContext
from packages.memory.short_term import ShortTermMemory
from packages.memory.summarizer import MemorySummarizer

logger = structlog.get_logger(__name__)

# Trigger summarization when this many turns are in short-term memory
_SUMMARIZE_THRESHOLD = 16

# After summarization, keep this many recent turns (the rest become the summary)
_TURNS_TO_KEEP_AFTER_SUMMARY = 6

# Redis key for summaries
_SUMMARY_KEY_PREFIX = "memory:summary:"
_SUMMARY_TTL = 7 * 24 * 60 * 60  # 7 days


class MemoryManager:
    """
    Coordinates all memory systems for a session.

    The agent runtime holds one MemoryManager instance and calls it
    at the start and end of each reasoning step.
    """

    def __init__(
        self,
        short_term: ShortTermMemory,
        long_term: LongTermMemory,
        summarizer: MemorySummarizer,
        redis_client: object | None = None,
    ) -> None:
        self._short_term = short_term
        self._long_term = long_term
        self._summarizer = summarizer
        self._redis = redis_client
        # In-process summary cache (fallback when Redis is unavailable)
        self._summary_cache: dict[str, str] = {}

    async def record_turn(self, session_id: str, role: str, content: str) -> None:
        """
        Record a conversation turn and trigger summarization if needed.

        Called after every user message and assistant response.

        Summarization failure is caught and logged — it must never fail
        the agent run. The run continues with raw turns available.
        (ADR-003: Graceful Memory Degradation)
        """
        self._short_term.add_turn(session_id, role=role, content=content)

        # Check if we should summarize
        turn_count = self._short_term.turn_count(session_id)
        if turn_count >= _SUMMARIZE_THRESHOLD:
            try:
                await self._maybe_summarize(session_id)
            except Exception as exc:
                # Summarization failure must not fail the agent run.
                # The run continues with raw short-term turns available.
                # This is disproportionate impact: a summarization LLM call
                # failing should degrade memory quality, not crash the run.
                logger.warning(
                    "summarization_skipped_degrading",
                    session_id=session_id,
                    error=str(exc)[:200],
                    error_type=type(exc).__name__,
                    turn_count=turn_count,
                )

    async def get_context(self, session_id: str) -> MemoryContext:
        """
        Assemble the full memory context for a session.

        Returns a MemoryContext ready to be formatted into the prompt.
        """
        short_term_turns = self._short_term.get_turns(session_id)
        summary = await self._get_summary(session_id)
        long_term_facts = await self._long_term.get_facts(session_id)

        return MemoryContext(
            session_id=session_id,
            short_term=short_term_turns,
            summary=summary or None,
            long_term_facts=long_term_facts,
        )

    async def store_fact(self, session_id: str, fact: str) -> None:
        """Store a long-term fact for a session."""
        await self._long_term.store_fact(session_id, fact)

    async def clear_session(self, session_id: str) -> None:
        """Clear all memory for a session."""
        self._short_term.clear(session_id)
        await self._long_term.clear(session_id)
        await self._clear_summary(session_id)
        logger.info("memory_session_cleared", session_id=session_id)

    async def _maybe_summarize(self, session_id: str) -> None:
        """
        Summarize older turns and replace them with a summary.

        Keeps the most recent turns intact for immediate context.
        """
        all_turns = self._short_term.get_turns(session_id)
        turns_to_summarize = all_turns[:-_TURNS_TO_KEEP_AFTER_SUMMARY]
        turns_to_keep = all_turns[-_TURNS_TO_KEEP_AFTER_SUMMARY:]

        if not turns_to_summarize:
            return

        # Get existing summary to incorporate
        existing_summary = await self._get_summary(session_id)
        if existing_summary:
            # Prepend existing summary as context for the new summarization
            from packages.memory.schemas import ConversationTurn
            summary_turn = ConversationTurn(
                role="assistant",
                content=f"[Previous summary: {existing_summary}]",
            )
            turns_to_summarize = [summary_turn] + turns_to_summarize

        new_summary = await self._summarizer.summarize(session_id, turns_to_summarize)

        # Store the new summary
        await self._store_summary(session_id, new_summary)

        # Replace short-term memory with only the recent turns
        self._short_term.clear(session_id)
        for turn in turns_to_keep:
            self._short_term.add_turn(session_id, role=turn.role, content=turn.content)

        logger.info(
            "memory_summarized",
            session_id=session_id,
            summarized_turns=len(turns_to_summarize),
            kept_turns=len(turns_to_keep),
        )

    async def _get_summary(self, session_id: str) -> str:
        """Retrieve the current summary for a session."""
        key = f"{_SUMMARY_KEY_PREFIX}{session_id}"
        if self._redis is not None:
            try:
                summary = await self._redis.get(key)
                return summary or ""
            except Exception:
                pass
        return self._summary_cache.get(session_id, "")

    async def _store_summary(self, session_id: str, summary: str) -> None:
        """Persist a summary."""
        key = f"{_SUMMARY_KEY_PREFIX}{session_id}"
        self._summary_cache[session_id] = summary
        if self._redis is not None:
            try:
                await self._redis.set(key, summary, ex=_SUMMARY_TTL)
            except Exception as exc:
                logger.warning("summary_store_failed", session_id=session_id, error=str(exc))

    async def _clear_summary(self, session_id: str) -> None:
        """Delete the summary for a session."""
        self._summary_cache.pop(session_id, None)
        if self._redis is not None:
            try:
                await self._redis.delete(f"{_SUMMARY_KEY_PREFIX}{session_id}")
            except Exception:
                pass
