"""
FastAPI application entrypoint.

Responsibilities:
- Create and configure the FastAPI app
- Register middleware (CORS, correlation ID, logging)
- Register all API routers
- Handle startup/shutdown lifecycle events
- Expose the ASGI app for uvicorn

This file should stay thin. Configuration lives in core/config.py,
middleware in core/middleware.py, routes in api/.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import CorrelationIDMiddleware
from app.core.rate_limit import RateLimitMiddleware
from app.core.redis import close_redis
from packages.observability.otel import configure_otel, instrument_fastapi

# Configure structured logging before anything else runs
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage application startup and shutdown.

    Startup:
    - Log configuration summary
    - (Future) run DB migrations check
    - (Future) warm up connection pools

    Shutdown:
    - Close Redis connections gracefully
    """
    settings = get_settings()
    logger.info(
        "application_startup",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        debug=settings.debug,
    )

    yield  # Application runs here

    logger.info("application_shutdown")
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()

    # Configure OpenTelemetry before creating the app
    configure_otel(service_name=settings.app_name, environment=settings.environment)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # CORS — allow frontend origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
    )

    # Correlation ID injection + request logging
    app.add_middleware(CorrelationIDMiddleware)

    # Rate limiting — protects LLM endpoints from abuse
    app.add_middleware(RateLimitMiddleware, requests_per_minute=60, chat_requests_per_minute=20)

    # Register all API routes under /api/v1
    app.include_router(api_router, prefix=settings.api_prefix)

    # Instrument FastAPI with OpenTelemetry (after routes are registered)
    instrument_fastapi(app)

    return app


app = create_app()
