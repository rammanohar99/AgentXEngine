"""
Vector memory — embedding-based episodic memory retrieval.

Unlike short-term memory (sliding window) and long-term memory (explicit facts),
vector memory stores conversation turns as embeddings and retrieves the most
semantically relevant past exchanges for the current context.

This enables contextual recall: "remember when we discussed X?" even if X
was many turns ago and has been pruned from short-term memory.

Design:
- Each turn is embedded and stored with its session_id
- Retrieval uses cosine similarity against the current query
- Results are formatted as memory context for the prompt
- Storage is in-process for Phase 4 (pgvector in Phase 5)

AGENTS.md memory types:
  ✅ short-term  — ShortTermMemory (sliding window)
  ✅ long-term   — LongTermMemory (Redis facts)
  ✅ summarized  — MemorySummarizer
  ✅ vector      — VectorMemory (this module)

Usage:
    vector_mem = VectorMemory(embedding_service)
    await vector_mem.store(session_id, "user", "How does FastAPI handle async?")
    results = await vector_mem.retrieve(session_id, "async patterns", top_k=3)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import structlog

logger = structlog.get_logger(__name__)


@runtime_checkable
class EmbedderProtocol(Protocol):
    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, query: str) -> list[float]: ...


@dataclass
class VectorMemoryEntry:
    """A stored memory turn with its embedding."""

    session_id: str
    role: str
    content: str
    embedding: list[float] = field(default_factory=list)


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class VectorMemory:
    """
    Embedding-based episodic memory.

    Stores conversation turns as vectors and retrieves the most
    semantically relevant past exchanges for a given query.

    In-process storage for Phase 4. Phase 5 will persist to pgvector.
    """

    def __init__(self, embedder: EmbedderProtocol, max_entries_per_session: int = 200) -> None:
        self._embedder = embedder
        self._max_entries = max_entries_per_session
        self._store: dict[str, list[VectorMemoryEntry]] = {}

    async def store(self, session_id: str, role: str, content: str) -> None:
        """Embed and store a conversation turn."""
        if not content.strip():
            return

        try:
            embeddings = await self._embedder.embed_texts([content])
            embedding = embeddings[0] if embeddings else []

            entry = VectorMemoryEntry(
                session_id=session_id,
                role=role,
                content=content,
                embedding=embedding,
            )

            if session_id not in self._store:
                self._store[session_id] = []

            self._store[session_id].append(entry)

            # Prune oldest entries if over limit
            if len(self._store[session_id]) > self._max_entries:
                self._store[session_id] = self._store[session_id][-self._max_entries :]

        except Exception as exc:
            logger.warning("vector_memory_store_failed", session_id=session_id, error=str(exc))

    async def retrieve(
        self,
        session_id: str,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.6,
    ) -> list[dict[str, Any]]:
        """
        Retrieve the most semantically relevant past turns for a query.

        Returns a list of dicts with role, content, and similarity score.
        """
        entries = self._store.get(session_id, [])
        if not entries:
            return []

        try:
            query_embedding = await self._embedder.embed_query(query)
        except Exception as exc:
            logger.warning("vector_memory_embed_failed", error=str(exc))
            return []

        # Score all entries
        scored = [
            (entry, _cosine_similarity(query_embedding, entry.embedding))
            for entry in entries
            if entry.embedding
        ]

        # Filter by threshold and sort by score
        relevant = [(entry, score) for entry, score in scored if score >= score_threshold]
        relevant.sort(key=lambda pair: pair[1], reverse=True)

        return [
            {"role": entry.role, "content": entry.content, "score": score}
            for entry, score in relevant[:top_k]
        ]

    def clear(self, session_id: str) -> None:
        """Remove all vector memory for a session."""
        self._store.pop(session_id, None)

    def entry_count(self, session_id: str) -> int:
        return len(self._store.get(session_id, []))
