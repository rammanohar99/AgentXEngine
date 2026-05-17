"""
Reranker tests — mock LLM, deterministic scoring.
"""

import asyncio

import pytest
from packages.rag.reranker import Reranker
from packages.rag.schemas import DocumentMetadata, RetrievalResult


def _make_result(text: str, score: float) -> RetrievalResult:
    return RetrievalResult(
        chunk_id="c1",
        document_id="d1",
        text=text,
        score=score,
        metadata=DocumentMetadata(source="test.md"),
    )


class MockLLM:
    """Returns scores in sequence."""

    def __init__(self, scores: list[float]) -> None:
        self._scores = scores
        self._index = 0

    async def complete(self, messages, temperature=0.0, **kwargs):
        score = self._scores[min(self._index, len(self._scores) - 1)]
        self._index += 1
        return type("R", (), {"text": str(score)})()


@pytest.mark.asyncio
async def test_reranker_reorders_by_score() -> None:
    # Original order: low score first, high score second
    results = [
        _make_result("Less relevant text", 0.7),
        _make_result("Highly relevant text", 0.6),
    ]
    # LLM scores: first gets 0.4, second gets 0.9
    reranker = Reranker(llm_provider=MockLLM(scores=[0.4, 0.9]))
    reranked = await reranker.rerank("relevant query", results)

    assert len(reranked) == 2
    # Higher LLM score should come first
    assert reranked[0].text == "Highly relevant text"
    assert reranked[0].score == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_reranker_empty_results() -> None:
    reranker = Reranker(llm_provider=MockLLM(scores=[]))
    reranked = await reranker.rerank("query", [])
    assert reranked == []


@pytest.mark.asyncio
async def test_reranker_top_k_limits_output() -> None:
    results = [_make_result(f"Result {i}", 0.8) for i in range(5)]
    reranker = Reranker(llm_provider=MockLLM(scores=[0.9, 0.8, 0.7, 0.6, 0.5]))
    reranked = await reranker.rerank("query", results, top_k=3)
    assert len(reranked) == 3


@pytest.mark.asyncio
async def test_reranker_falls_back_on_llm_failure() -> None:
    class FailingLLM:
        async def complete(self, messages, **kwargs):
            raise RuntimeError("LLM down")

    results = [_make_result("Some text", 0.8)]
    reranker = Reranker(llm_provider=FailingLLM())
    reranked = await reranker.rerank("query", results)

    # Should still return results (with neutral 0.5 score)
    assert len(reranked) == 1
    assert reranked[0].score == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_reranker_clamps_scores() -> None:
    """LLM returning out-of-range scores should be clamped."""
    results = [_make_result("Text", 0.5)]
    reranker = Reranker(llm_provider=MockLLM(scores=[1.5]))  # Over 1.0
    reranked = await reranker.rerank("query", results)
    assert reranked[0].score <= 1.0


@pytest.mark.asyncio
async def test_reranker_timeout() -> None:
    class SlowLLM:
        async def complete(self, messages, **kwargs):
            await asyncio.sleep(0.5)
            return type("R", (), {"text": "0.9"})()

    results = [_make_result("Text", 0.8)]
    reranker = Reranker(llm_provider=SlowLLM(), timeout_seconds=0.1)
    reranked = await reranker.rerank("query", results)

    # Should time out and return neutral 0.5 score
    assert len(reranked) == 1
    assert reranked[0].score == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_reranker_bounded_concurrency() -> None:
    class TrackingLLM:
        def __init__(self):
            self.concurrent_calls = 0
            self.max_concurrent_calls = 0

        async def complete(self, messages, **kwargs):
            self.concurrent_calls += 1
            self.max_concurrent_calls = max(self.max_concurrent_calls, self.concurrent_calls)
            await asyncio.sleep(0.1)
            self.concurrent_calls -= 1
            return type("R", (), {"text": "0.8"})()

    llm = TrackingLLM()
    # 5 items to score, max_concurrent=2
    results = [_make_result(f"Text {i}", 0.8) for i in range(5)]
    reranker = Reranker(llm_provider=llm, max_concurrent=2)

    await reranker.rerank("query", results)

    # Should never exceed 2 concurrent calls
    assert llm.max_concurrent_calls <= 2


@pytest.mark.asyncio
async def test_reranker_observability_logging() -> None:
    import structlog

    results = [_make_result("Text", 0.8)]
    reranker = Reranker(llm_provider=MockLLM(scores=[0.9]))

    with structlog.testing.capture_logs() as cap_logs:
        await reranker.rerank("query", results)

    # Ensure the metric event is emitted
    assert any(log.get("event") == "metric.rag_reranker" for log in cap_logs)
