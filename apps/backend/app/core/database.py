"""
Async SQLAlchemy database engine and session management.

Uses asyncpg driver for non-blocking PostgreSQL access.
Session lifecycle is managed per-request via FastAPI dependency injection.

Engine and session factory are lazy-initialized on first use so that
importing this module does not require asyncpg to be installed (e.g.
during test collection on machines without a live database).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


# Lazy singletons — not created at import time.
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _create_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url_str,
        echo=settings.debug,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # Detect stale connections
    )


def get_engine() -> AsyncEngine:
    """Return the shared engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = _create_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the shared session factory, creating it on first call."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a database session per request.
    Automatically commits on success, rolls back on exception.
    """
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_database_connection() -> bool:
    """Health check — verifies the database is reachable."""
    from sqlalchemy import text

    try:
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("database_connection_failed", error=str(exc))
        return False
