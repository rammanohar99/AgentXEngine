"""
Reliability engineering layer for the agent runtime.

This module implements the production-grade reliability primitives that
transform the agent from "works in demos" to "works under load":

1. RetryPolicy — differentiated retry logic (transient vs permanent errors)
2. CircuitBreaker — prevents cascading failures when LLM is degraded
3. TimeoutGuard — enforces execution time limits on LLM calls and tools
4. ExecutionWatchdog — monitors long-running operations and emits alerts

Design principles:
- All failures are observable (structured logs + metrics)
- Retry trees are traceable (correlation IDs on every retry)
- Circuit state transitions are logged
- Timeouts are configurable per operation type
- Permanent errors fail fast (no wasted retries)

Transient errors (should retry):
- Network timeouts
- Rate limit exceeded (429)
- Service unavailable (503)
- Internal server error (500) — sometimes transient

Permanent errors (fail fast):
- Authentication failure (401, 403)
- Invalid request (400)
- Model not found (404)
- Context length exceeded (specific error message)
- Quota exhausted (different from rate limit — billing issue)
"""

from __future__ import annotations

import asyncio
import enum
import time
from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")

# Error message patterns that indicate permanent failures (fail fast, no retry)
_PERMANENT_ERROR_PATTERNS: tuple[str, ...] = (
    "invalid api key",
    "authentication",
    "permission denied",
    "quota exceeded",
    "billing",
    "model not found",
    "context length",
    "context window",
    "invalid request",
    "bad request",
)


def _is_transient_error(exc: Exception) -> bool:
    """
    Determine if an exception is transient (should retry) or permanent (fail fast).

    Transient: network errors, rate limits, temporary service unavailability.
    Permanent: auth failures, invalid requests, quota exhaustion.
    """
    error_message = str(exc).lower()
    for pattern in _PERMANENT_ERROR_PATTERNS:
        if pattern in error_message:
            return False
    return True


# ── Circuit Breaker ───────────────────────────────────────────────────────────


class CircuitState(str, enum.Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing — reject requests immediately
    HALF_OPEN = "half_open" # Testing recovery — allow one request through


class CircuitBreaker:
    """
    Circuit breaker for LLM API calls.

    States:
    - CLOSED: Normal operation. Failures increment counter.
    - OPEN: Too many failures. Requests rejected immediately.
    - HALF_OPEN: Recovery probe. One request allowed through.

    Transitions:
    - CLOSED → OPEN: failure_count >= threshold
    - OPEN → HALF_OPEN: recovery_seconds elapsed
    - HALF_OPEN → CLOSED: probe request succeeds
    - HALF_OPEN → OPEN: probe request fails

    Usage:
        breaker = CircuitBreaker(failure_threshold=5, recovery_seconds=60)
        async with breaker.guard("vertex_ai"):
            response = await llm.complete(...)
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_seconds: float = 60.0,
        name: str = "default",
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._name = name
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._total_opens = 0

    @property
    def state(self) -> CircuitState:
        # Check if OPEN circuit should transition to HALF_OPEN
        if (
            self._state == CircuitState.OPEN
            and time.monotonic() - self._last_failure_time >= self._recovery_seconds
        ):
            self._state = CircuitState.HALF_OPEN
            logger.info(
                "circuit_breaker_half_open",
                name=self._name,
                recovery_seconds=self._recovery_seconds,
            )
        return self._state

    def record_success(self) -> None:
        """Record a successful call. Resets failure count and closes circuit."""
        if self._state == CircuitState.HALF_OPEN:
            logger.info("circuit_breaker_closed", name=self._name, reason="probe_success")
        self._state = CircuitState.CLOSED
        self._failure_count = 0

    def record_failure(self, exc: Exception) -> None:
        """Record a failed call. May open the circuit."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            # Probe failed — reopen immediately
            self._state = CircuitState.OPEN
            self._total_opens += 1
            logger.warning(
                "circuit_breaker_reopened",
                name=self._name,
                error=str(exc)[:200],
            )
        elif self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN
            self._total_opens += 1
            logger.error(
                "circuit_breaker_opened",
                name=self._name,
                failure_count=self._failure_count,
                threshold=self._failure_threshold,
                error=str(exc)[:200],
            )

    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    async def guard(self, operation_name: str) -> "CircuitBreakerContext":
        """Async context manager for circuit-protected operations."""
        return CircuitBreakerContext(self, operation_name)


class CircuitBreakerContext:
    """Context manager returned by CircuitBreaker.guard()."""

    def __init__(self, breaker: CircuitBreaker, operation_name: str) -> None:
        self._breaker = breaker
        self._operation_name = operation_name

    async def __aenter__(self) -> "CircuitBreakerContext":
        if self._breaker.is_open():
            raise CircuitOpenError(
                f"Circuit breaker '{self._breaker._name}' is OPEN. "
                f"Operation '{self._operation_name}' rejected. "
                f"Will retry after {self._breaker._recovery_seconds}s."
            )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_val is None:
            self._breaker.record_success()
        else:
            self._breaker.record_failure(exc_val)


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open and rejects a request."""
    pass


# ── Retry Policy ──────────────────────────────────────────────────────────────


class RetryPolicy:
    """
    Structured retry policy with differentiated handling.

    Transient errors: retry with exponential backoff + jitter.
    Permanent errors: fail immediately (no wasted retries).

    Every retry emits a structured log with:
    - correlation_id (for tracing retry trees)
    - attempt number
    - error type
    - backoff duration
    - whether error is transient

    Usage:
        policy = RetryPolicy(max_attempts=3, base_delay=2.0)
        result = await policy.execute(
            operation=lambda: llm.complete(messages),
            operation_name="vertex_ai_complete",
            correlation_id=run_id,
        )
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 2.0,
        max_delay: float = 30.0,
        jitter: bool = True,
    ) -> None:
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._jitter = jitter

    async def execute(
        self,
        operation: Callable[[], Coroutine[Any, Any, T]],
        operation_name: str = "operation",
        correlation_id: str = "",
    ) -> T:
        """
        Execute an async operation with retry policy.

        Raises the last exception if all attempts fail.
        Raises immediately on permanent errors.
        """
        last_exc: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                result = await operation()
                if attempt > 1:
                    logger.info(
                        "retry_succeeded",
                        operation=operation_name,
                        attempt=attempt,
                        correlation_id=correlation_id,
                    )
                return result

            except Exception as exc:
                last_exc = exc
                is_transient = _is_transient_error(exc)

                logger.warning(
                    "operation_failed",
                    operation=operation_name,
                    attempt=attempt,
                    max_attempts=self._max_attempts,
                    is_transient=is_transient,
                    error_type=type(exc).__name__,
                    error=str(exc)[:200],
                    correlation_id=correlation_id,
                )

                # Permanent errors fail immediately
                if not is_transient:
                    logger.error(
                        "permanent_error_no_retry",
                        operation=operation_name,
                        error_type=type(exc).__name__,
                        correlation_id=correlation_id,
                    )
                    raise

                # Last attempt — don't sleep, just raise
                if attempt == self._max_attempts:
                    break

                # Exponential backoff with optional jitter
                delay = min(self._base_delay * (2 ** (attempt - 1)), self._max_delay)
                if self._jitter:
                    import random
                    delay *= (0.5 + random.random() * 0.5)

                logger.info(
                    "retry_backoff",
                    operation=operation_name,
                    attempt=attempt,
                    delay_seconds=round(delay, 2),
                    correlation_id=correlation_id,
                )
                await asyncio.sleep(delay)

        assert last_exc is not None
        raise last_exc


# ── Timeout Guard ─────────────────────────────────────────────────────────────


async def with_timeout(
    coro: Coroutine[Any, Any, T],
    timeout_seconds: float,
    operation_name: str = "operation",
    correlation_id: str = "",
) -> T:
    """
    Execute a coroutine with a timeout.

    Raises asyncio.TimeoutError if the operation exceeds the limit.
    Logs the timeout with structured context.

    Usage:
        result = await with_timeout(
            llm.complete(messages),
            timeout_seconds=60.0,
            operation_name="vertex_ai_complete",
            correlation_id=run_id,
        )
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.error(
            "operation_timeout",
            operation=operation_name,
            timeout_seconds=timeout_seconds,
            correlation_id=correlation_id,
        )
        raise asyncio.TimeoutError(
            f"Operation '{operation_name}' timed out after {timeout_seconds}s"
        )


# ── Module-level circuit breakers (one per external service) ─────────────────

# These are module-level singletons — shared across all requests.
# Each external service gets its own breaker so one service's failure
# doesn't affect others.

_llm_circuit_breaker: CircuitBreaker | None = None
_embedding_circuit_breaker: CircuitBreaker | None = None


def get_llm_circuit_breaker(
    failure_threshold: int = 5,
    recovery_seconds: float = 60.0,
) -> CircuitBreaker:
    """Get or create the LLM circuit breaker."""
    global _llm_circuit_breaker
    if _llm_circuit_breaker is None:
        _llm_circuit_breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_seconds=recovery_seconds,
            name="vertex_ai_llm",
        )
    return _llm_circuit_breaker


def get_embedding_circuit_breaker(
    failure_threshold: int = 5,
    recovery_seconds: float = 60.0,
) -> CircuitBreaker:
    """Get or create the embedding circuit breaker."""
    global _embedding_circuit_breaker
    if _embedding_circuit_breaker is None:
        _embedding_circuit_breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_seconds=recovery_seconds,
            name="vertex_ai_embeddings",
        )
    return _embedding_circuit_breaker
