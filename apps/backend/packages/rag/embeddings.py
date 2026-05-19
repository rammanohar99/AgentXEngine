"""
Embeddings service — wraps Vertex AI text embeddings via google-genai SDK.

Design:
- Isolated from the rest of the RAG pipeline
- Token-aware batching: estimates tokens per chunk and splits batches
  so no single request exceeds the model's token limit
- Retries only transient errors (5xx, network); fails fast on 400
- Emits structured logs for every embedding call

Vertex AI text-embedding-004 limits:
- Max tokens per request: 20,000
- Max texts per request: 250
- Max tokens per single text: 2,048
- Output dimensions: 768

Token estimation: 1 token ≈ 4 characters (conservative estimate)
"""

from __future__ import annotations

import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768

# Hard limits from the Gemini embedding API
_MAX_TEXTS_PER_BATCH = 250
_MAX_TOKENS_PER_BATCH = 18_000  # Stay under 20k with a safety margin
_MAX_TOKENS_PER_TEXT = 2_048
_CHARS_PER_TOKEN = 4  # Conservative estimate: 4 chars ≈ 1 token


def _estimate_tokens(text: str) -> int:
    """Estimate token count from character count."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _is_transient_error(exc: Exception) -> bool:
    """Return True for errors worth retrying (network, 5xx, rate limit)."""
    msg = str(exc).lower()
    # Never retry token limit / invalid argument errors
    if "invalid_argument" in msg or "400" in msg:
        return False
    if "token count" in msg or "input token" in msg:
        return False
    # Retry on rate limit, service unavailable, network errors
    return any(k in msg for k in ("429", "503", "500", "rate limit", "unavailable", "timeout"))


def _build_token_aware_batches(texts: list[str]) -> list[list[str]]:
    """
    Split texts into batches that respect both the text count limit
    and the total token limit per request.
    """
    batches: list[list[str]] = []
    current_batch: list[str] = []
    current_tokens = 0

    for text in texts:
        # Truncate individual texts that exceed the per-text token limit
        max_chars = _MAX_TOKENS_PER_TEXT * _CHARS_PER_TOKEN
        if len(text) > max_chars:
            text = text[:max_chars]
            logger.warning(
                "chunk_truncated_for_embedding",
                original_len=len(text),
                max_chars=max_chars,
            )

        text_tokens = _estimate_tokens(text)

        # Start a new batch if adding this text would exceed limits
        would_exceed_tokens = current_tokens + text_tokens > _MAX_TOKENS_PER_BATCH
        would_exceed_count = len(current_batch) >= _MAX_TEXTS_PER_BATCH

        if current_batch and (would_exceed_tokens or would_exceed_count):
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0

        current_batch.append(text)
        current_tokens += text_tokens

    if current_batch:
        batches.append(current_batch)

    return batches


class EmbeddingService:
    """
    Generates text embeddings using the google-genai SDK.

    Supports both:
    - Gemini Developer API (GEMINI_API_KEY) — development
    - Vertex AI (ADC + project) — production

    If api_key is provided, it takes priority over project/location.
    """

    def __init__(
        self,
        project: str = "",
        location: str = "us-central1",
        api_key: str = "",
    ) -> None:
        self._project = project
        self._location = location
        self._api_key = api_key
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-initialize the google-genai client."""
        if self._client is None:
            from google import genai

            if self._api_key:
                logger.info("embedding_client_mode", mode="developer_api")
                self._client = genai.Client(api_key=self._api_key)
            else:
                logger.info(
                    "embedding_client_mode",
                    mode="vertex_ai",
                    project=self._project,
                    location=self._location,
                )
                self._client = genai.Client(
                    vertexai=True,
                    project=self._project,
                    location=self._location,
                )
        return self._client

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of texts. Returns a list of float vectors in input order.

        Uses token-aware batching to stay within the 20k token/request limit.
        Retries transient errors; fails fast on permanent errors (400).
        """
        if not texts:
            return []

        start = time.perf_counter()
        batches = _build_token_aware_batches(texts)
        all_embeddings: list[list[float]] = []

        logger.info(
            "embedding_batches_planned",
            total_texts=len(texts),
            batch_count=len(batches),
            batch_sizes=[len(b) for b in batches],
        )

        for batch_idx, batch in enumerate(batches):
            batch_embeddings = await self._embed_batch_with_retry(
                batch,
                task_type="RETRIEVAL_DOCUMENT",
                batch_idx=batch_idx,
                total_batches=len(batches),
            )
            all_embeddings.extend(batch_embeddings)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "embeddings_generated",
            count=len(texts),
            batches=len(batches),
            model=EMBEDDING_MODEL,
            duration_ms=duration_ms,
        )

        return all_embeddings

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query string using RETRIEVAL_QUERY task type."""
        result = await self._embed_batch_with_retry(
            [query], task_type="RETRIEVAL_QUERY", batch_idx=0, total_batches=1
        )
        return result[0]

    async def _embed_batch_with_retry(
        self,
        texts: list[str],
        task_type: str,
        batch_idx: int,
        total_batches: int,
        max_attempts: int = 3,
    ) -> list[list[float]]:
        """
        Embed a single batch with retry logic.

        Retries transient errors (5xx, rate limit) with exponential backoff.
        Fails immediately on permanent errors (400 invalid argument, token limit).
        """
        import asyncio

        last_exc: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                result = await self._embed_batch(texts, task_type)
                if attempt > 1:
                    logger.info(
                        "embedding_retry_succeeded",
                        batch_idx=batch_idx,
                        attempt=attempt,
                    )
                return result
            except Exception as exc:
                last_exc = exc

                if not _is_transient_error(exc):
                    # Permanent error — fail immediately, no retry
                    logger.error(
                        "embedding_permanent_error",
                        batch_idx=batch_idx,
                        total_batches=total_batches,
                        error=str(exc)[:300],
                    )
                    raise

                if attempt < max_attempts:
                    delay = 2.0**attempt  # 2s, 4s
                    logger.warning(
                        "embedding_transient_error_retry",
                        batch_idx=batch_idx,
                        attempt=attempt,
                        delay_s=delay,
                        error=str(exc)[:200],
                    )
                    await asyncio.sleep(delay)

        raise last_exc  # type: ignore[misc]

    async def _embed_batch(self, texts: list[str], task_type: str) -> list[list[float]]:
        """Make a single embed_content API call."""
        from google.genai import types

        client = self._get_client()

        if self._api_key:
            # Developer API mode — pass output_dimensionality to truncate to 768
            response = await client.aio.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=EMBEDDING_DIMENSIONS,
                ),
            )
        else:
            response = await client.aio.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=EMBEDDING_DIMENSIONS,
                ),
            )

        return [list(embedding.values) for embedding in response.embeddings]
