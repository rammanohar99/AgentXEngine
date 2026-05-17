"""
Vector memory tests — uses a mock embedder, no Vertex AI needed.
"""

import pytest
from packages.memory.vector_memory import VectorMemory, _cosine_similarity


class MockEmbedder:
    """Returns deterministic embeddings based on content hash."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, query: str) -> list[float]:
        return self._embed(query)

    def _embed(self, text: str) -> list[float]:
        # Simple deterministic embedding: use char codes mod 1.0
        # Similar texts will have similar embeddings
        vec = [0.0] * 8
        for i, char in enumerate(text[:8]):
            vec[i] = ord(char) / 128.0
        return vec


def test_cosine_similarity_identical_vectors() -> None:
    vec = [1.0, 0.0, 0.0]
    assert _cosine_similarity(vec, vec) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors() -> None:
    vec_a = [1.0, 0.0]
    vec_b = [0.0, 1.0]
    assert _cosine_similarity(vec_a, vec_b) == pytest.approx(0.0)


def test_cosine_similarity_empty_vectors() -> None:
    assert _cosine_similarity([], []) == 0.0


@pytest.mark.asyncio
async def test_vector_memory_stores_and_retrieves() -> None:
    memory = VectorMemory(embedder=MockEmbedder())
    await memory.store("s1", role="user", content="FastAPI async patterns")
    await memory.store("s1", role="assistant", content="FastAPI uses async/await natively")

    assert memory.entry_count("s1") == 2


@pytest.mark.asyncio
async def test_vector_memory_retrieve_returns_relevant() -> None:
    memory = VectorMemory(embedder=MockEmbedder(), max_entries_per_session=100)
    await memory.store("s1", role="user", content="FastAPI routing")
    await memory.store("s1", role="user", content="Python basics")

    # Retrieve with a low threshold to get results from mock embedder
    results = await memory.retrieve("s1", query="FastAPI", top_k=5, score_threshold=0.0)
    assert len(results) > 0
    for result in results:
        assert "role" in result
        assert "content" in result
        assert "score" in result


@pytest.mark.asyncio
async def test_vector_memory_clear() -> None:
    memory = VectorMemory(embedder=MockEmbedder())
    await memory.store("s1", role="user", content="Hello")
    memory.clear("s1")
    assert memory.entry_count("s1") == 0


@pytest.mark.asyncio
async def test_vector_memory_isolates_sessions() -> None:
    memory = VectorMemory(embedder=MockEmbedder())
    await memory.store("s1", role="user", content="Session 1 content")
    await memory.store("s2", role="user", content="Session 2 content")

    assert memory.entry_count("s1") == 1
    assert memory.entry_count("s2") == 1


@pytest.mark.asyncio
async def test_vector_memory_prunes_old_entries() -> None:
    memory = VectorMemory(embedder=MockEmbedder(), max_entries_per_session=3)
    for i in range(5):
        await memory.store("s1", role="user", content=f"Message {i}")

    assert memory.entry_count("s1") == 3


@pytest.mark.asyncio
async def test_vector_memory_empty_content_not_stored() -> None:
    memory = VectorMemory(embedder=MockEmbedder())
    await memory.store("s1", role="user", content="   ")
    assert memory.entry_count("s1") == 0


@pytest.mark.asyncio
async def test_vector_memory_retrieve_empty_session() -> None:
    memory = VectorMemory(embedder=MockEmbedder())
    results = await memory.retrieve("nonexistent", query="anything")
    assert results == []
