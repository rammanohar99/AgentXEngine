"""
Celery tasks for async memory operations.

Task: summarize_session_memory
  Triggered when a session's short-term memory approaches its limit.
  Compresses older turns into a summary stored in Redis.
  This offloads the LLM summarization call from the hot request path.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="memory.summarize_session",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    acks_late=True,
)
def summarize_session_memory(
    self,
    session_id: str,
    turns: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Summarize a session's conversation history asynchronously.

    Called when short-term memory hits the summarization threshold.
    Stores the summary in Redis for the next request to pick up.
    """
    try:
        result = asyncio.run(_summarize_async(session_id, turns))
        logger.info(
            "session_summarized",
            extra={"session_id": session_id, "task_id": self.request.id},
        )
        return result
    except Exception as exc:
        logger.error(
            "summarize_failed",
            extra={"session_id": session_id, "error": str(exc)},
        )
        raise self.retry(exc=exc) from exc


async def _summarize_async(session_id: str, turns: list[dict[str, Any]]) -> dict[str, Any]:
    """Async implementation of memory summarization."""
    from packages.memory.schemas import ConversationTurn
    from packages.memory.summarizer import MemorySummarizer

    from app.core.redis import get_redis_client
    from app.services.vertex_ai import VertexAIService

    llm = VertexAIService()
    summarizer = MemorySummarizer(llm_provider=llm)

    conversation_turns = [
        ConversationTurn(role=turn["role"], content=turn["content"]) for turn in turns
    ]

    summary = await summarizer.summarize(session_id, conversation_turns)

    # Store in Redis
    redis = get_redis_client()
    key = f"memory:summary:{session_id}"
    await redis.set(key, summary, ex=7 * 24 * 60 * 60)

    return {"session_id": session_id, "summary": summary, "status": "complete"}
