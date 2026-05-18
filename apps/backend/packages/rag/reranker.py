"""
RAG reranker — re-scores retrieval results for better relevance ordering.

The initial vector search returns results by cosine similarity, which is
a good first pass but not always the best relevance signal. The reranker
applies a cross-encoder style scoring using the LLM to re-rank the top-k
results before assembling the final context.

Design:
- Takes the query + candidate chunks
- Scores each chunk for relevance to the query (0.0–1.0)
- Returns chunks sorted by reranked score
- Falls back to original order if reranking fails

This is a lightweight LLM-based reranker. Phase 5+ can replace it
with a dedicated cross-encoder model (e.g., Cohere Rerank API).

Usage:
    reranker = Reranker(llm_provider)
    reranked = await reranker.rerank(query, results, top_k=3)
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import structlog

from packages.rag.schemas import RetrievalResult

logger = structlog.get_logger(__name__)

_RERANK_PROMPT = """\
You are a relevance scoring system. \
Score how relevant the following document excerpt is to the query.

Query: {query}

Document excerpt:
{text}

Respond with ONLY a number between 0.0 and 1.0 where:
- 1.0 = perfectly relevant, directly answers the query
- 0.5 = somewhat relevant, related topic
- 0.0 = not relevant at all

Score:"""


@runtime_checkable
class RerankerLLM(Protocol):
    async def complete(
        self, messages: list[Any], temperature: float = 0.0, **kwargs: Any
    ) -> Any: ...


class Reranker:
    """
    LLM-based reranker for RAG retrieval results.

    Scores each candidate chunk against the query and re-sorts.
    Falls back to original order on any failure.
    """

    def __init__(
        self,
        llm_provider: RerankerLLM,
        max_concurrent: int = 5,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._llm = llm_provider
        self._max_concurrent = max_concurrent
        self._timeout_seconds = timeout_seconds

    async def rerank(
        self,
        query: str,
        results: list[RetrievalResult],
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        """
        Rerank retrieval results by LLM-scored relevance.

        Returns results sorted by reranked score (highest first).
        If top_k is set, returns only the top_k results.
        """
        if not results:
            return results

        import asyncio
        import time

        start_time = time.perf_counter()
        semaphore = asyncio.Semaphore(self._max_concurrent)

        async def _bounded_score(text: str) -> float:
            async with semaphore:
                try:
                    return await asyncio.wait_for(
                        self._score_chunk(query, text),
                        timeout=self._timeout_seconds,
                    )
                except TimeoutError:
                    logger.warning("rerank_score_timeout", timeout=self._timeout_seconds)
                    return 0.5
                except Exception as exc:
                    logger.warning("rerank_score_failed_outer", error=str(exc))
                    return 0.5

        # Score each result concurrently (ADR-004) with bounded concurrency
        scores = await asyncio.gather(*[_bounded_score(result.text) for result in results])

        # Combine results with scores
        scored = list(zip(results, scores, strict=False))

        # Sort by reranked score descending
        scored.sort(key=lambda pair: pair[1], reverse=True)

        # Update scores in the results
        reranked = []
        for result, new_score in scored:
            updated = result.model_copy(update={"score": new_score})
            reranked.append(updated)

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        logger.info(
            "metric.rag_reranker",
            query_length=len(query),
            input_count=len(results),
            output_count=len(reranked[:top_k] if top_k else reranked),
            latency_ms=latency_ms,
        )

        return reranked[:top_k] if top_k else reranked

    async def _score_chunk(self, query: str, text: str) -> float:
        """Score a single chunk for relevance to the query."""
        try:
            from packages.agents.runtime import Message

            prompt = _RERANK_PROMPT.format(query=query, text=text[:500])
            messages = [Message(role="user", content=prompt)]
            response = await self._llm.complete(messages=messages, temperature=0.0)
            raw = str(response.text).strip()

            # Parse the score — extract first float found
            import re

            match = re.search(r"\d+\.?\d*", raw)
            if match:
                score = float(match.group())
                return max(0.0, min(1.0, score))  # Clamp to [0, 1]
            return 0.5  # Default if parsing fails

        except Exception as exc:
            logger.warning("rerank_score_failed", error=str(exc))
            return 0.5  # Neutral score on failure
