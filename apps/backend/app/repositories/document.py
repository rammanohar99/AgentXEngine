"""
Document repository — all database access for documents and chunks.

Follows the repository pattern: no business logic here, only typed
database operations. The RAG service calls this layer.

All methods are async and use the injected AsyncSession.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.document import ChunkModel, DocumentModel

logger = get_logger(__name__)


class DocumentRepository:
    """
    Typed database access for documents and chunks.

    Usage:
        repo = DocumentRepository(session)
        doc = await repo.create_document(content="...", metadata={...})
        chunks = await repo.create_chunks(doc.id, chunk_data)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_document(
        self,
        content: str,
        source: str = "",
        source_type: str = "",
        title: str = "",
        language: str = "",
        extra_metadata: dict[str, Any] | None = None,
    ) -> DocumentModel:
        """Insert a new document and return the persisted model."""
        document = DocumentModel(
            content=content,
            source=source,
            source_type=source_type,
            title=title,
            language=language,
            extra_metadata=extra_metadata or {},
        )
        self._session.add(document)
        await self._session.flush()  # Get the generated ID without committing
        logger.info("document_created", document_id=str(document.id), source=source)
        return document

    async def create_chunks(
        self,
        document_id: uuid.UUID,
        chunks: list[dict[str, Any]],
    ) -> list[ChunkModel]:
        """
        Bulk-insert chunks for a document.

        Each dict in chunks must have: text, chunk_index, embedding (optional).
        """
        models = [
            ChunkModel(
                document_id=document_id,
                text=chunk["text"],
                chunk_index=chunk["chunk_index"],
                embedding=chunk.get("embedding"),
            )
            for chunk in chunks
        ]
        self._session.add_all(models)
        await self._session.flush()
        logger.info(
            "chunks_created",
            document_id=str(document_id),
            count=len(models),
        )
        return models

    async def similarity_search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        score_threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """
        Find the top-k most similar chunks using cosine similarity.

        Uses raw SQL with pgvector's <=> operator to avoid SQLAlchemy ORM
        parameter binding issues when the same vector is referenced multiple times.
        Cosine similarity = 1 - cosine_distance.
        """
        # Convert to a pgvector-compatible string literal: '[0.1, 0.2, ...]'
        vector_str = "[" + ",".join(str(float(v)) for v in query_embedding) + "]"

        sql = text(
            """
            SELECT
                c.id            AS chunk_id,
                c.document_id   AS document_id,
                c.text          AS text,
                d.source        AS source,
                d.source_type   AS source_type,
                d.title         AS title,
                d.language      AS language,
                d.extra_metadata AS extra_metadata,
                1 - (c.embedding <=> CAST(:vec AS vector)) AS similarity
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.embedding IS NOT NULL
            ORDER BY c.embedding <=> CAST(:vec AS vector)
            LIMIT :top_k
        """
        )

        result = await self._session.execute(
            sql,
            {"vec": vector_str, "top_k": top_k},
        )
        rows = result.mappings().all()

        return [
            {
                "chunk_id": str(row["chunk_id"]),
                "document_id": str(row["document_id"]),
                "text": row["text"],
                "score": float(row["similarity"]),
                "source": row["source"],
                "source_type": row["source_type"],
                "title": row["title"],
                "language": row["language"],
                "extra_metadata": row["extra_metadata"],
            }
            for row in rows
            if float(row["similarity"]) >= score_threshold
        ]

    async def list_documents(self) -> list[dict[str, Any]]:
        """
        Return all documents with their chunk counts, ordered by most recent first.
        """
        stmt = (
            select(
                DocumentModel.id,
                DocumentModel.source,
                DocumentModel.source_type,
                DocumentModel.title,
                DocumentModel.created_at,
                func.count(ChunkModel.id).label("chunk_count"),
            )
            .outerjoin(ChunkModel, ChunkModel.document_id == DocumentModel.id)
            .group_by(DocumentModel.id)
            .order_by(DocumentModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        rows = result.all()
        return [
            {
                "document_id": str(row.id),
                "source": row.source,
                "source_type": row.source_type,
                "title": row.title,
                "created_at": row.created_at.isoformat(),
                "chunk_count": row.chunk_count,
            }
            for row in rows
        ]

    async def delete_document(self, document_id: uuid.UUID) -> bool:
        """
        Delete a document and all its chunks (CASCADE handles chunks).
        Returns True if a document was deleted, False if not found.
        """
        result = await self._session.execute(
            delete(DocumentModel).where(DocumentModel.id == document_id)
        )
        deleted = result.rowcount > 0
        if deleted:
            logger.info("document_deleted", document_id=str(document_id))
        return deleted

    async def get_document(self, document_id: uuid.UUID) -> DocumentModel | None:
        """Fetch a document by ID."""
        result = await self._session.execute(
            select(DocumentModel).where(DocumentModel.id == document_id)
        )
        return result.scalar_one_or_none()

    async def count_chunks(self, document_id: uuid.UUID) -> int:
        """Count chunks for a document."""
        result = await self._session.execute(
            select(func.count()).where(ChunkModel.document_id == document_id)
        )
        return result.scalar_one() or 0
