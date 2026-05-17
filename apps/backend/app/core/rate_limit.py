"""
Rate limiting middleware — protects the API from abuse.

Strategy: sliding window rate limit per IP address, stored in Redis.
Falls back to in-process limiting if Redis is unavailable.

AGENTS.md security rules: "apply rate limiting"

Limits (configurable via env):
- Default: 60 requests per minute per IP
- Chat endpoints: 20 requests per minute per IP (LLM calls are expensive)

Usage (registered in main.py):
    app.add_middleware(RateLimitMiddleware, requests_per_minute=60)
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.logging import get_logger

logger = get_logger(__name__)

# In-process fallback store: {ip: [(timestamp, count)]}
_in_process_store: dict[str, list[float]] = {}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiter.

    Tracks request counts per IP in Redis (with in-process fallback).
    Returns 429 Too Many Requests when the limit is exceeded.
    """

    def __init__(
        self,
        app: Any,
        requests_per_minute: int = 60,
        chat_requests_per_minute: int = 20,
    ) -> None:
        super().__init__(app)
        self._default_limit = requests_per_minute
        self._chat_limit = chat_requests_per_minute
        self._window_seconds = 60

    def _get_limit_for_path(self, path: str) -> int:
        """Return the appropriate rate limit for a given path."""
        if "/chat" in path:
            return self._chat_limit
        return self._default_limit

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP, respecting X-Forwarded-For for proxied requests."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def _check_rate_limit_redis(self, key: str, limit: int) -> tuple[bool, int]:
        """
        Check rate limit using Redis sliding window.
        Returns (is_allowed, remaining_requests).
        """
        try:
            from app.core.redis import get_redis_client

            redis = get_redis_client()
            now = time.time()
            window_start = now - self._window_seconds

            # Remove old entries outside the window
            await redis.zremrangebyscore(key, 0, window_start)
            # Count current requests in window
            count = await redis.zcard(key)

            if count >= limit:
                return False, 0

            # Add current request
            await redis.zadd(key, {str(now): now})
            await redis.expire(key, self._window_seconds * 2)

            return True, limit - count - 1

        except Exception:
            # Redis unavailable — fall back to in-process
            return self._check_rate_limit_in_process(key, limit)

    def _check_rate_limit_in_process(self, key: str, limit: int) -> tuple[bool, int]:
        """In-process fallback rate limiter."""
        now = time.time()
        window_start = now - self._window_seconds

        if key not in _in_process_store:
            _in_process_store[key] = []

        # Prune old timestamps
        _in_process_store[key] = [t for t in _in_process_store[key] if t > window_start]

        count = len(_in_process_store[key])
        if count >= limit:
            return False, 0

        _in_process_store[key].append(now)
        return True, limit - count - 1

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in ("/api/v1/health", "/api/v1/health/ready"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        limit = self._get_limit_for_path(request.url.path)

        path_parts = request.url.path.split("/")
        category = path_parts[3] if len(path_parts) > 3 else "default"
        key = f"ratelimit:{client_ip}:{category}"

        is_allowed, remaining = await self._check_rate_limit_redis(key, limit)

        if not is_allowed:
            logger.warning(
                "rate_limit_exceeded",
                client_ip=client_ip,
                path=request.url.path,
                limit=limit,
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"error": "Rate limit exceeded. Please slow down."},
                headers={"Retry-After": str(self._window_seconds)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(limit)
        return response
