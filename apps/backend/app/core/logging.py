"""
Structured JSON logging configuration using structlog.

All log entries include:
- timestamp
- log level
- correlation_id (when available)
- service name
- environment

Usage:
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("event_name", key="value")
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

from app.core.config import get_settings

_logging_configured = False


def add_service_context(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Inject service-level metadata into every log entry."""
    settings = get_settings()
    event_dict["service"] = settings.app_name
    event_dict["version"] = settings.app_version
    event_dict["environment"] = settings.environment
    return event_dict


def add_logger_name_from_context(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Add the logger name to the event dict.

    Works with both stdlib Logger and structlog PrintLogger.
    structlog.stdlib.add_logger_name only works with stdlib loggers;
    this version reads the name from the bound context instead.
    """
    # structlog passes the name as a positional arg when get_logger(name) is called
    name = getattr(logger, "name", None)
    if name is None:
        # PrintLogger stores the name in _name (set via get_logger binding)
        name = event_dict.pop("_logger_name", None)
    if name:
        event_dict["logger"] = name
    return event_dict


def configure_logging() -> None:
    """
    Configure structlog for structured JSON output in production,
    and pretty console output in development.

    Idempotent — safe to call multiple times (e.g. during tests).
    """
    global _logging_configured
    if _logging_configured:
        return

    settings = get_settings()

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        add_service_context,
    ]

    if settings.is_production:
        # JSON output for log aggregation (Datadog, CloudWatch, etc.)
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Human-readable output for local development
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,  # Allow reconfiguration in tests
    )

    # Also configure stdlib logging to route through structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.getLevelName(settings.log_level.upper()),
    )

    _logging_configured = True


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a named structured logger."""
    return structlog.get_logger(name)
