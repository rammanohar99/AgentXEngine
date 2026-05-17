"""
Redis client setup for caching, pub/sub, and Celery broker.

Uses redis-py async client for non-blocking operations.
"""

from typing import Any, cast

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    """Return the module-level Redis client (initialized at startup)."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = cast(
            Redis,
            aioredis.from_url(  # type: ignore[no-untyped-call]
                settings.redis_url_str,
                encoding="utf-8",
                decode_responses=True,
            ),
        )
    return _redis_client


async def check_redis_connection() -> bool:
    """Health check — verifies Redis is reachable."""
    try:
        client = get_redis_client()
        await cast(Any, client.ping())
        return True
    except Exception as exc:
        logger.error("redis_connection_failed", error=str(exc))
        return False


async def close_redis() -> None:
    """Gracefully close the Redis connection pool."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
