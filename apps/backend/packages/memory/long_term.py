"""
Long-term memory — Redis-backed persistent facts per session.

Design:
- Facts are stored as a Redis list per session (key: memory:lt:{session_id})
- Each fact is a plain string (e.g. "User prefers Python over JavaScript")
- Facts are deduplicated on write
- TTL of 30 days prevents unbounded growth
- Falls back gracefully if Redis is unavailable

Long-term memory is for facts that should persist across sessions:
- User preferences
- Project context
- Established decisions
- Recurring patterns

Usage:
    memory = LongTermMemory(redis_client)
    await memory.store_fact(session_id, "User prefers async Python")
    facts = await memory.get_facts(session_id)
    await memory.clear(session_id)
"""

from __future__ import annotations

from typing import Any, cast

import structlog

logger = structlog.get_logger(__name__)

# Redis key prefix and TTL
_KEY_PREFIX = "memory:lt:"
_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days
_MAX_FACTS = 50  # Cap per session to prevent unbounded growth


class LongTermMemory:
    """
    Redis-backed persistent fact storage.

    Injected with a Redis client — no global state.
    Degrades gracefully if Redis is unavailable.
    """

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    def _key(self, session_id: str) -> str:
        return f"{_KEY_PREFIX}{session_id}"

    async def store_fact(self, session_id: str, fact: str) -> None:
        """
        Store a fact for a session.

        Deduplicates: if the fact already exists, it is not added again.
        Prunes oldest facts if the cap is exceeded.
        """
        key = self._key(session_id)
        try:
            # Check for duplicate
            existing = await self._redis.lrange(key, 0, -1)
            if fact in existing:
                return

            await self._redis.rpush(key, fact)
            await self._redis.expire(key, _TTL_SECONDS)

            # Prune if over cap — remove oldest (leftmost) entries
            current_length = await self._redis.llen(key)
            if current_length > _MAX_FACTS:
                await self._redis.ltrim(key, current_length - _MAX_FACTS, -1)

            logger.info("long_term_fact_stored", session_id=session_id)
        except Exception as exc:
            logger.warning("long_term_store_failed", session_id=session_id, error=str(exc))

    async def get_facts(self, session_id: str) -> list[str]:
        """Return all stored facts for a session."""
        key = self._key(session_id)
        try:
            facts = await self._redis.lrange(key, 0, -1)
            return [f for f in facts if f]
        except Exception as exc:
            logger.warning("long_term_get_failed", session_id=session_id, error=str(exc))
            return []

    async def clear(self, session_id: str) -> None:
        """Delete all facts for a session."""
        try:
            await self._redis.delete(self._key(session_id))
        except Exception as exc:
            logger.warning("long_term_clear_failed", session_id=session_id, error=str(exc))

    async def fact_count(self, session_id: str) -> int:
        """Return the number of stored facts."""
        try:
            return cast(int, await self._redis.llen(self._key(session_id)))
        except Exception:
            return 0
