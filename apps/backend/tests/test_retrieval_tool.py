"""
Retrieval tool unit tests.

The retriever callable is mocked — no database or embedding service needed.
"""

import pytest

from packages.agents.schemas import ToolCall
from packages.agents.tools.retrieval import RetrieveDocumentsTool


def _make_call(tool_name: str, **kwargs) -> ToolCall:
    return ToolCall(tool_name=tool_name, arguments=kwargs, call_id="test-id")


def _make_mock_retriever(results: list[dict]) -> object:
    """Return an async callable that returns the given results."""

    async def retriever(query: str, top_k: int) -> list[dict]:
        return results[:top_k]

    return retriever


@pytest.mark.asyncio
async def test_retrieval_tool_formats_results() -> None:
    results = [
        {
            "chunk_id": "c1",
            "document_id": "d1",
            "text": "FastAPI is a modern web framework.",
            "score": 0.92,
            "source": "docs/fastapi.md",
        },
        {
            "chunk_id": "c2",
            "document_id": "d1",
            "text": "It supports async operations natively.",
            "score": 0.85,
            "source": "docs/fastapi.md",
        },
    ]
    tool = RetrieveDocumentsTool(retriever=_make_mock_retriever(results))
    result = await tool.execute(_make_call("retrieve_documents", query="FastAPI async"))

    assert result.success is True
    assert "FastAPI is a modern web framework" in result.output
    assert "docs/fastapi.md" in result.output
    assert "0.92" in result.output


@pytest.mark.asyncio
async def test_retrieval_tool_no_results() -> None:
    tool = RetrieveDocumentsTool(retriever=_make_mock_retriever([]))
    result = await tool.execute(_make_call("retrieve_documents", query="nothing here"))

    assert result.success is True
    assert "No relevant documents" in result.output


@pytest.mark.asyncio
async def test_retrieval_tool_respects_top_k() -> None:
    results = [{"chunk_id": f"c{i}", "document_id": "d1", "text": f"Result {i}", "score": 0.9, "source": "src"} for i in range(10)]
    captured_top_k: list[int] = []

    async def tracking_retriever(query: str, top_k: int) -> list[dict]:
        captured_top_k.append(top_k)
        return results[:top_k]

    tool = RetrieveDocumentsTool(retriever=tracking_retriever)
    await tool.execute(_make_call("retrieve_documents", query="test", top_k=3))

    assert captured_top_k[0] == 3


@pytest.mark.asyncio
async def test_retrieval_tool_clamps_top_k() -> None:
    """top_k should be clamped to [1, 10]."""
    captured: list[int] = []

    async def tracking_retriever(query: str, top_k: int) -> list[dict]:
        captured.append(top_k)
        return []

    tool = RetrieveDocumentsTool(retriever=tracking_retriever)
    await tool.execute(_make_call("retrieve_documents", query="test", top_k=999))
    assert captured[0] == 10

    captured.clear()
    await tool.execute(_make_call("retrieve_documents", query="test", top_k=0))
    assert captured[0] == 1


@pytest.mark.asyncio
async def test_retrieval_tool_default_top_k() -> None:
    captured: list[int] = []

    async def tracking_retriever(query: str, top_k: int) -> list[dict]:
        captured.append(top_k)
        return []

    tool = RetrieveDocumentsTool(retriever=tracking_retriever)
    await tool.execute(_make_call("retrieve_documents", query="test"))
    assert captured[0] == 5  # default


def test_retrieval_tool_prompt_description() -> None:
    tool = RetrieveDocumentsTool(retriever=_make_mock_retriever([]))
    description = tool.to_prompt_description()
    assert "retrieve_documents" in description
    assert "query" in description
    assert "knowledge base" in description.lower()
