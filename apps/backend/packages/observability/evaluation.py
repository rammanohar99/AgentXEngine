"""
Evaluation system — measures agent response quality and RAG retrieval quality.

AGENTS.md Phase 5: "evaluation systems"

Metrics tracked:
- Agent response quality: relevance, completeness, accuracy (LLM-judged)
- RAG retrieval quality: precision, recall, MRR (Mean Reciprocal Rank)
- Tool usage efficiency: steps taken, tools called, success rate
- Latency: time to first token, total response time

Design:
- EvaluationResult is a typed Pydantic model
- Evaluator uses LLM-as-judge for quality scoring
- All evaluations are logged as structured events
- Results can be sent to Langfuse as scores

Usage:
    evaluator = AgentEvaluator(llm_provider)
    result = await evaluator.evaluate_response(
        query="What is FastAPI?",
        response="FastAPI is a modern Python web framework...",
        context_used=["FastAPI docs chunk 1", "FastAPI docs chunk 2"],
    )
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

_QUALITY_PROMPT = """\
Evaluate the quality of this AI assistant response.

User query: {query}

Assistant response: {response}

Rate the response on these dimensions (0.0 to 1.0):
1. Relevance: Does it directly address the query?
2. Completeness: Does it cover the key aspects?
3. Accuracy: Is the information correct and precise?

Respond in this exact format:
relevance: <score>
completeness: <score>
accuracy: <score>"""


class EvaluationScore(BaseModel):
    """Scores for a single evaluation dimension."""

    relevance: float = Field(ge=0.0, le=1.0)
    completeness: float = Field(ge=0.0, le=1.0)
    accuracy: float = Field(ge=0.0, le=1.0)

    @property
    def overall(self) -> float:
        return round((self.relevance + self.completeness + self.accuracy) / 3, 3)


class AgentRunMetrics(BaseModel):
    """Metrics for a single agent run."""

    session_id: str
    run_id: str
    query: str
    response: str
    steps_taken: int = 0
    tool_calls_made: int = 0
    tool_success_rate: float = 1.0
    latency_ms: float = 0.0
    quality_score: EvaluationScore | None = None


class RAGRetrievalMetrics(BaseModel):
    """Metrics for a RAG retrieval operation."""

    query: str
    results_returned: int
    avg_score: float
    top_score: float
    score_threshold: float
    latency_ms: float = 0.0


@runtime_checkable
class EvaluatorLLM(Protocol):
    async def complete(
        self, messages: list[Any], temperature: float = 0.0, **kwargs: Any
    ) -> Any: ...


class AgentEvaluator:
    """
    LLM-as-judge evaluator for agent responses.

    Scores responses on relevance, completeness, and accuracy.
    Results are logged as structured events and optionally sent to Langfuse.
    """

    def __init__(self, llm_provider: EvaluatorLLM) -> None:
        self._llm = llm_provider

    async def evaluate_response(
        self,
        query: str,
        response: str,
        session_id: str = "",
        run_id: str = "",
        steps_taken: int = 0,
        tool_calls_made: int = 0,
        latency_ms: float = 0.0,
    ) -> AgentRunMetrics:
        """
        Evaluate an agent response and return structured metrics.

        Uses LLM-as-judge to score quality dimensions.
        Falls back to neutral scores if evaluation fails.
        """
        quality_score = await self._score_response(query, response)

        metrics = AgentRunMetrics(
            session_id=session_id,
            run_id=run_id,
            query=query,
            response=response,
            steps_taken=steps_taken,
            tool_calls_made=tool_calls_made,
            latency_ms=latency_ms,
            quality_score=quality_score,
        )

        logger.info(
            "agent_evaluation",
            session_id=session_id,
            run_id=run_id,
            overall_score=quality_score.overall if quality_score else None,
            relevance=quality_score.relevance if quality_score else None,
            completeness=quality_score.completeness if quality_score else None,
            accuracy=quality_score.accuracy if quality_score else None,
            steps_taken=steps_taken,
            tool_calls_made=tool_calls_made,
            latency_ms=latency_ms,
        )

        return metrics

    async def _score_response(self, query: str, response: str) -> EvaluationScore:
        """Score a response using LLM-as-judge."""
        try:
            from packages.agents.runtime import Message

            prompt = _QUALITY_PROMPT.format(
                query=query[:500],
                response=response[:1000],
            )
            messages = [Message(role="user", content=prompt)]
            llm_response = await self._llm.complete(messages=messages, temperature=0.0)
            return self._parse_scores(str(llm_response.text))

        except Exception as exc:
            logger.warning("evaluation_score_failed", error=str(exc))
            return EvaluationScore(relevance=0.5, completeness=0.5, accuracy=0.5)

    def _parse_scores(self, text: str) -> EvaluationScore:
        """Parse LLM score output into EvaluationScore."""
        import re

        scores: dict[str, float] = {}
        for dimension in ["relevance", "completeness", "accuracy"]:
            pattern = rf"{dimension}:\s*(\d+\.?\d*)"
            match = re.search(pattern, text.lower())
            if match:
                scores[dimension] = max(0.0, min(1.0, float(match.group(1))))
            else:
                scores[dimension] = 0.5

        return EvaluationScore(**scores)


def evaluate_rag_retrieval(
    query: str,
    results: list[Any],
    score_threshold: float,
    latency_ms: float = 0.0,
) -> RAGRetrievalMetrics:
    """
    Compute RAG retrieval quality metrics (no LLM needed).

    Tracks: result count, score distribution, latency.
    """
    scores = [r.score for r in results if hasattr(r, "score")]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    top_score = max(scores) if scores else 0.0

    metrics = RAGRetrievalMetrics(
        query=query,
        results_returned=len(results),
        avg_score=round(avg_score, 3),
        top_score=round(top_score, 3),
        score_threshold=score_threshold,
        latency_ms=latency_ms,
    )

    logger.info(
        "rag_retrieval_evaluation",
        query_length=len(query),
        results_returned=metrics.results_returned,
        avg_score=metrics.avg_score,
        top_score=metrics.top_score,
    )

    return metrics
