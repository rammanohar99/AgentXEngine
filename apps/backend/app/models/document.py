"""
Document and Chunk ORM models.

Uses SQLAlchemy 2.0 mapped_column syntax with pgvector for the embedding column.

Schema:
  documents — one row per ingested source document
  chunks    — one row per text chunk, with a 768-dim embedding vector

The pgvector extension must be enabled before running migrations.
It is enabled in infrastructure/docker/postgres/init.sql.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

EMBEDDING_DIMENSIONS = 768  # text-embedding-004 output size


class DocumentModel(Base):
    """
    A source document ingested into the RAG pipeline.

    One document → many chunks.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, default="", index=True)
    source_type: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(Text, default="")
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship to chunks
    chunks: Mapped[list[ChunkModel]] = relationship(
        "ChunkModel", back_populates="document", cascade="all, delete-orphan"
    )


class ChunkModel(Base):
    """
    A text chunk from a document, with its embedding vector.

    The embedding column uses pgvector's VECTOR type.
    The ivfflat index enables approximate nearest-neighbor search.
    """

    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship back to document
    document: Mapped[DocumentModel] = relationship("DocumentModel", back_populates="chunks")

    # HNSW index for approximate nearest-neighbor search.
    # Works correctly at any dataset size (unlike IVFFlat which needs 300+ rows).
    # m=16 and ef_construction=64 are good defaults for most use cases.
    __table_args__ = (
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
    )
