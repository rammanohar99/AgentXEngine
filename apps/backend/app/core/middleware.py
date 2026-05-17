"""
Request middleware for correlation ID injection and structured request logging.

Every request gets a unique correlation_id that flows through all logs,
making distributed tracing and debugging straightforward.
"""

import time
import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.logging import get_logger

logger = get_logger(__name__)

CORRELATION_ID_HEADER = "X-Correlation-ID"


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Injects a correlation ID into every request.
    - Reads from incoming header if present (for upstream propagation)
    - Generates a new UUID if not present
    - Binds to structlog context so all logs in the request include it
    - Returns the ID in the response header
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get(CORRELATION_ID_HEADER) or str(uuid.uuid4())

        # Bind to structlog context — all logs in this request will include it
        structlog.contextvars.clear_contextvars()

        context_vars = {"correlation_id": correlation_id}

        # Inject correlation_id into OTEL span, and grab trace_id for structlog
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span.is_recording():
                span.set_attribute("correlation_id", correlation_id)
                span_context = span.get_span_context()
                if span_context.is_valid:
                    context_vars["trace_id"] = format(span_context.trace_id, "032x")
                    context_vars["span_id"] = format(span_context.span_id, "016x")
        except ImportError:
            pass

        structlog.contextvars.bind_contextvars(**context_vars)

        start_time = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response
