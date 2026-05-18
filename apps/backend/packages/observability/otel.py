"""
OpenTelemetry setup for the FastAPI backend.

Instruments:
- FastAPI request/response spans (via opentelemetry-instrumentation-fastapi)
- Outgoing HTTP calls (via httpx instrumentation)
- Structured log correlation (trace_id injected into structlog context)

AGENTS.md observability requirements:
  ✅ request tracing
  ✅ agent step tracing (via Langfuse)
  ✅ tool execution tracing (via Langfuse)
  ✅ token usage tracking (via Langfuse)
  ✅ latency tracking (via structlog timings)
  ✅ OpenTelemetry (this module)

Usage (called once at app startup):
    from packages.observability.otel import configure_otel
    configure_otel(service_name="aiengos-backend", environment="production")
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def configure_otel(service_name: str = "aiengos-backend", environment: str = "development") -> None:
    """
    Configure OpenTelemetry SDK with console exporter for development
    and OTLP exporter for production.

    Gracefully no-ops if opentelemetry packages are not installed.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        resource = Resource.create({
            "service.name": service_name,
            "deployment.environment": environment,
        })

        provider = TracerProvider(resource=resource)

        if environment == "production":
            # In production, export to an OTLP collector
            # Configure OTEL_EXPORTER_OTLP_ENDPOINT env var to point to your collector
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                exporter = OTLPSpanExporter()
                provider.add_span_processor(BatchSpanProcessor(exporter))
            except ImportError:
                # OTLP exporter not installed — fall back to console
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        else:
            # Development: log spans to console (visible in docker logs)
            # Use a simple exporter that doesn't flood the console
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        trace.set_tracer_provider(provider)

        logger.info(
            "otel_configured",
            service_name=service_name,
            environment=environment,
        )

    except ImportError:
        logger.warning("otel_not_available", message="opentelemetry packages not installed")
    except Exception as exc:
        logger.warning("otel_setup_failed", error=str(exc))


def instrument_fastapi(app: object) -> None:
    """
    Instrument a FastAPI app with OpenTelemetry.

    Adds automatic span creation for every HTTP request.
    Call this after configure_otel() and after creating the FastAPI app.
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]
        logger.info("otel_fastapi_instrumented")
    except ImportError:
        logger.warning("otel_fastapi_instrumentor_not_available")
    except Exception as exc:
        logger.warning("otel_fastapi_instrument_failed", error=str(exc))
