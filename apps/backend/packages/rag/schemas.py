"""
RAG pipeline schemas — typed contracts for documents, chunks, and retrieval.

These are pure Pydantic models with no database or framework dependencies.
The storage layer maps these to/from ORM models.
"""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    """Metadata attached to an ingested document."""

    source: str = ""  # File path, URL, or identifier
    source_type: str = ""  # "file" | "markdown" | "pdf" | "repository"
    title: str = ""
    language: str = ""  # Programming language or "markdown", "text"
    extra: dict[str, Any] = Field(default_factory=dict)


class Document(BaseModel):
    """A source document before chunking."""

    id: str = ""
    content: str
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )


class Chunk(BaseModel):
    """A single chunk of a document, ready for embedding and storage."""

    id: str = ""
    document_id: str
    text: str
    chunk_index: int
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    embedding: list[float] | None = None


class RetrievalResult(BaseModel):
    """A single result from a vector similarity search."""

    chunk_id: str
    document_id: str
    text: str
    score: float  # Cosine similarity score (0–1, higher = more similar)
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)

    def to_context_string(self) -> str:
        """Format for injection into the LLM context."""
        source = self.metadata.source or self.document_id
        return f"[Source: {source} | Score: {self.score:.3f}]\n{self.text}"


class IngestRequest(BaseModel):
    """Request to ingest a document into the RAG pipeline."""

    content: str = Field(..., min_length=1)
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)


class IngestResponse(BaseModel):
    """Response after successful document ingestion."""

    document_id: str
    chunk_count: int
    source: str


class SearchRequest(BaseModel):
    """Request to search the knowledge base."""

    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    score_threshold: float = Field(default=0.3, ge=0.0, le=1.0)


class SearchResponse(BaseModel):
    """Response from a knowledge base search."""

    query: str
    results: list[RetrievalResult]
    total_found: int
