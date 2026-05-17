"""
Evaluation system tests — deterministic, no real LLM calls.
"""

import pytest
from packages.observability.evaluation import (
    AgentEvaluator,
    AgentRunMetrics,
    EvaluationScore,
    RAGRetrievalMetrics,
    evaluate_rag_retrieval,
)


class MockLLM:
    """Returns a fixed evaluation response."""

    async def complete(self, messages, temperature=0.0, **kwargs):
        text = "relevance: 0.9\ncompleteness: 0.8\naccuracy: 0.85"
        return type("R", (), {"text": text})()


class FailingLLM:
    async def complete(self, messages, **kwargs):
        raise RuntimeError("LLM unavailable")


@pytest.mark.asyncio
async def test_evaluator_scores_response() -> None:
    evaluator = AgentEvaluator(llm_provider=MockLLM())
    metrics = await evaluator.evaluate_response(
        query="What is FastAPI?",
        response="FastAPI is a modern Python web framework for building APIs.",
        session_id="s1",
        run_id="r1",
    )
    assert isinstance(metrics, AgentRunMetrics)
    assert metrics.quality_score is not None
    assert metrics.quality_score.relevance == 0.9
    assert metrics.quality_score.completeness == 0.8
    assert metrics.quality_score.accuracy == 0.85
    assert 0.0 <= metrics.quality_score.overall <= 1.0


@pytest.mark.asyncio
async def test_evaluator_falls_back_on_llm_failure() -> None:
    evaluator = AgentEvaluator(llm_provider=FailingLLM())
    metrics = await evaluator.evaluate_response(
        query="What is Python?",
        response="Python is a programming language.",
    )
    assert metrics.quality_score is not None
    assert metrics.quality_score.overall == 0.5  # Neutral fallback


def test_evaluation_score_overall() -> None:
    score = EvaluationScore(relevance=1.0, completeness=0.8, accuracy=0.6)
    assert score.overall == pytest.approx(0.8, abs=0.01)


def test_evaluate_rag_retrieval_with_results() -> None:
    from packages.rag.schemas import DocumentMetadata, RetrievalResult

    results = [
        RetrievalResult(
            chunk_id="c1", document_id="d1", text="FastAPI docs",
            score=0.92, metadata=DocumentMetadata()
        ),
        RetrievalResult(
            chunk_id="c2", document_id="d1", text="More FastAPI",
            score=0.85, metadata=DocumentMetadata()
        ),
    ]
    metrics = evaluate_rag_retrieval(
        query="FastAPI async",
        results=results,
        score_threshold=0.3,
        latency_ms=45.0,
    )
    assert isinstance(metrics, RAGRetrievalMetrics)
    assert metrics.results_returned == 2
    assert metrics.top_score == 0.92
    assert metrics.avg_score == pytest.approx(0.885, abs=0.01)


def test_evaluate_rag_retrieval_empty() -> None:
    metrics = evaluate_rag_retrieval(
        query="nothing",
        results=[],
        score_threshold=0.3,
    )
    assert metrics.results_returned == 0
    assert metrics.avg_score == 0.0
    assert metrics.top_score == 0.0


@pytest.mark.asyncio
async def test_evaluator_parses_scores_correctly() -> None:
    evaluator = AgentEvaluator(llm_provider=MockLLM())
    score = evaluator._parse_scores("relevance: 0.7\ncompleteness: 0.6\naccuracy: 0.8")
    assert score.relevance == 0.7
    assert score.completeness == 0.6
    assert score.accuracy == 0.8


@pytest.mark.asyncio
async def test_evaluator_clamps_scores_to_valid_range() -> None:
    evaluator = AgentEvaluator(llm_provider=MockLLM())
    # 1.5 gets clamped to 1.0; -0.2 can't be parsed by regex (no negative match) → fallback 0.5
    score = evaluator._parse_scores("relevance: 1.5\ncompleteness: -0.2\naccuracy: 0.5")
    assert score.relevance == 1.0   # Clamped from 1.5
    assert score.completeness == 0.5  # Fallback — regex doesn't match negative numbers
    assert score.accuracy == 0.5
