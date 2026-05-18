"""
Google Gen AI service — unified LLM provider using the google-genai SDK.

Migrated from the deprecated vertexai SDK to google-genai (v1.66+).
The google-genai SDK supports both:
  - Vertex AI backend (ADC + project ID) — production
  - Gemini Developer API (API key) — development

Config via environment variables:
  GOOGLE_CLOUD_PROJECT    — GCP project ID (Vertex AI mode)
  GOOGLE_CLOUD_LOCATION   — region, default "us-central1"
  GEMINI_API_KEY          — API key (Developer API mode, optional)

If GEMINI_API_KEY is set, it takes priority (Developer API).
Otherwise, uses ADC + GOOGLE_CLOUD_PROJECT (Vertex AI).

Models available on Agent Platform (k8s-terraform-lab):
  gemini-2.0-flash        — fast, cost-efficient
  gemini-2.0-flash-lite   — cheapest
  gemini-3.1-flash-lite   — latest lite
  gemini-3.1-pro-preview  — most capable
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from typing import Any, cast

from google import genai
from google.genai import types
from packages.agents.resilience import RetryPolicy
from packages.observability.metrics import get_metrics

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
metrics = get_metrics()

_FALLBACK_TRIGGER_PATTERNS = ("quota", "rate limit", "resource exhausted", "429", "503")


def _should_try_fallback(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(p in msg for p in _FALLBACK_TRIGGER_PATTERNS)


def _build_client(settings: Settings) -> genai.Client:
    """
    Build a google-genai client.

    Priority:
    1. GEMINI_API_KEY set → Developer API (no GCP project needed)
    2. GOOGLE_CLOUD_PROJECT set → Vertex AI via ADC
    """
    api_key = getattr(settings, "gemini_api_key", "") or ""
    if api_key:
        logger.info("genai_client_mode", mode="developer_api")
        return genai.Client(api_key=api_key)

    project = settings.google_cloud_project
    location = settings.google_cloud_location
    logger.info("genai_client_mode", mode="vertex_ai", project=project, location=location)
    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
    )


class VertexAIService:
    """
    LLM service using the google-genai SDK.

    Supports both Vertex AI (ADC) and Gemini Developer API (API key).
    Maintains the same interface as the previous vertexai-based service
    so the rest of the codebase is unaffected.
    """

    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.vertex_ai_model
        self._fallback_model_name = settings.vertex_ai_fallback_model
        self._settings = settings
        self._client: genai.Client | None = None
        self._retry_policy = RetryPolicy(max_attempts=3, base_delay=2.0, max_delay=30.0)

    def _get_client(self) -> genai.Client:
        """Lazy-initialize the client."""
        if self._client is None:
            self._client = _build_client(self._settings)
        return self._client

    async def complete(
        self,
        messages: list[Any],
        temperature: float = 0.2,
        max_output_tokens: int = 8192,
        response_schema: Any | None = None,
        correlation_id: str = "",
        **kwargs: Any,
    ) -> Any:
        """
        Non-streaming completion. Returns a response object with a .text attribute.
        Tries primary model, falls back on quota/rate-limit errors.
        """
        try:
            return await self._complete_with_model(
                model_name=self._model_name,
                messages=messages,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                correlation_id=correlation_id,
            )
        except Exception as primary_exc:
            if _should_try_fallback(primary_exc) and self._fallback_model_name != self._model_name:
                logger.warning(
                    "genai_fallback_triggered",
                    primary_model=self._model_name,
                    fallback_model=self._fallback_model_name,
                    error=str(primary_exc)[:200],
                    correlation_id=correlation_id,
                )
                return await self._complete_with_model(
                    model_name=self._fallback_model_name,
                    messages=messages,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    correlation_id=correlation_id,
                )
            raise

    async def _complete_with_model(
        self,
        model_name: str,
        messages: list[Any],
        temperature: float,
        max_output_tokens: int,
        correlation_id: str,
    ) -> Any:
        """Execute a completion with retry policy."""

        async def _attempt() -> Any:
            start = time.perf_counter()
            client = self._get_client()

            contents, system_instruction = _convert_messages(messages)

            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                system_instruction=system_instruction,
            )

            response = await client.aio.models.generate_content(
                model=model_name,
                contents=cast(Any, contents),
                config=config,
            )

            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

            logger.info(
                "genai_completion",
                model=model_name,
                duration_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                correlation_id=correlation_id,
            )
            metrics.record_llm_call(
                model=model_name,
                latency_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                success=True,
                correlation_id=correlation_id,
            )
            return response

        return await self._retry_policy.execute(
            operation=_attempt,
            operation_name=f"genai_complete_{model_name}",
            correlation_id=correlation_id,
        )

    async def stream(
        self,
        messages: list[Any],
        temperature: float = 0.2,
        max_output_tokens: int = 8192,
        correlation_id: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        Streaming completion — yields text chunks.

        Emits metric.llm_first_token with time_to_first_token_ms.
        First-token latency is the primary UX metric for streaming responses —
        users perceive a system as fast if they see the first word quickly.
        """
        client = self._get_client()
        contents, system_instruction = _convert_messages(messages)

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            system_instruction=system_instruction,
        )

        start = time.perf_counter()
        first_token_emitted = False
        total_output_tokens = 0

        try:
            async for chunk in await client.aio.models.generate_content_stream(
                model=self._model_name,
                contents=cast(Any, contents),
                config=config,
            ):
                if chunk.text:
                    # Record first-token latency on the very first chunk with text
                    if not first_token_emitted:
                        first_token_ms = round((time.perf_counter() - start) * 1000, 2)
                        first_token_emitted = True
                        logger.info(
                            "metric.llm_first_token",
                            model=self._model_name,
                            time_to_first_token_ms=first_token_ms,
                            correlation_id=correlation_id,
                        )
                    yield chunk.text
                if chunk.usage_metadata:
                    total_output_tokens = (
                        getattr(chunk.usage_metadata, "candidates_token_count", 0) or 0
                    )

            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "genai_stream_complete",
                model=self._model_name,
                duration_ms=duration_ms,
                output_tokens=total_output_tokens,
                correlation_id=correlation_id,
            )
            metrics.record_llm_call(
                model=self._model_name,
                latency_ms=duration_ms,
                output_tokens=total_output_tokens,
                success=True,
                correlation_id=correlation_id,
            )

        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                "genai_stream_error",
                model=self._model_name,
                duration_ms=duration_ms,
                error=str(exc)[:200],
                correlation_id=correlation_id,
            )
            metrics.record_llm_call(
                model=self._model_name,
                latency_ms=duration_ms,
                success=False,
                error_type=type(exc).__name__,
                correlation_id=correlation_id,
            )
            raise


def _convert_messages(messages: list[Any]) -> tuple[list[types.Content], str | None]:
    """
    Convert our internal message list to google-genai Content objects.

    Returns (contents, system_instruction).
    System messages are extracted and passed as system_instruction.
    """
    system_parts: list[str] = []
    contents: list[types.Content] = []

    for message in messages:
        role_str = message.role if isinstance(message.role, str) else message.role.value

        if role_str == "system":
            system_parts.append(message.content)
            continue

        # google-genai uses "user" and "model" roles
        genai_role = "model" if role_str == "assistant" else "user"
        contents.append(
            types.Content(
                role=genai_role,
                parts=[types.Part(text=message.content)],
            )
        )

    system_instruction = "\n\n".join(system_parts) if system_parts else None
    return contents, system_instruction
