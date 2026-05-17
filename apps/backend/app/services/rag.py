"""
RAG service — orchestrates ingestion and retrieval.

Responsibilities:
- Ingest: chunk document → embed chunks → store in pgvector
- Retrieve: embed query → similarity search → return ranked results

This service is the only place that knows about both the embedding
service and the database. The API layer and agent tools call this.

Design:
- Accepts an AsyncSession via dependency injection (no global state)
- EmbeddingService is injected (mockable in tests)
- All operations are async
- Structured logging for every operation
"""

from __future__ import annotations

from typing import Any

from packages.rag.chunker import Chunker
from packages.rag.schemas import (
    Document,
    DocumentMetadata,
    IngestRequest,
    IngestResponse,
    RetrievalResult,
    SearchRequest,
    SearchResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.repositories.document import DocumentRepository

logger = get_logger(__name__)


class RAGService:
    """
    Ingestion and retrieval service.

    Usage:
        service = RAGService(session, embedding_service)
        response = await service.ingest(request)
        results = await service.search(request)
    """

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: Any,  # EmbeddingService — typed loosely to avoid import chain
        chunker: Chunker | None = None,
    ) -> None:
        self._session = session
        self._embeddings = embedding_service
        self._chunker = chunker or Chunker(max_chunk_size=800, overlap=100)
        self._repo = DocumentRepository(session)

    async def list_documents(self) -> list[dict[str, Any]]:
        """Return all ingested documents with chunk counts."""
        return await self._repo.list_documents()

    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and all its chunks. Returns True if deleted."""
        import uuid as _uuid

        return await self._repo.delete_document(_uuid.UUID(document_id))

    async def ingest(self, request: IngestRequest) -> IngestResponse:
        """
        Ingest a document into the RAG pipeline.

        Steps:
        1. Create document record
        2. Chunk the content
        3. Embed all chunks (batched)
        4. Store chunks with embeddings
        """
        logger.info(
            "rag_ingest_start",
            source=request.metadata.source,
            content_length=len(request.content),
        )

        # 1. Create document record
        doc_model = await self._repo.create_document(
            content=request.content,
            source=request.metadata.source,
            source_type=request.metadata.source_type,
            title=request.metadata.title,
            language=request.metadata.language,
            extra_metadata=request.metadata.extra,
        )

        # 2. Chunk the content
        document = Document(
            id=str(doc_model.id),
            content=request.content,
            metadata=request.metadata,
        )
        chunks = self._chunker.chunk(document)

        # 3. Embed all chunks in one batched call
        chunk_texts = [chunk.text for chunk in chunks]
        embeddings = await self._embeddings.embed_texts(chunk_texts)

        # 4. Store chunks with embeddings
        chunk_data = [
            {
                "text": chunk.text,
                "chunk_index": chunk.chunk_index,
                "embedding": embedding,
            }
            for chunk, embedding in zip(chunks, embeddings, strict=False)
        ]
        await self._repo.create_chunks(doc_model.id, chunk_data)

        logger.info(
            "rag_ingest_complete",
            document_id=str(doc_model.id),
            chunk_count=len(chunks),
            source=request.metadata.source,
        )

        return IngestResponse(
            document_id=str(doc_model.id),
            chunk_count=len(chunks),
            source=request.metadata.source,
        )

    async def search(self, request: SearchRequest) -> SearchResponse:
        """
        Search the knowledge base using semantic similarity.

        Steps:
        1. Embed the query
        2. Run similarity search against chunk embeddings
        3. Return ranked results above the score threshold
        """
        logger.info(
            "rag_search_start",
            query_length=len(request.query),
            top_k=request.top_k,
        )

        # 1. Embed the query
        query_embedding = await self._embeddings.embed_query(request.query)

        # 2. Similarity search
        raw_results = await self._repo.similarity_search(
            query_embedding=query_embedding,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
        )

        # 3. Map to typed results
        results = [
            RetrievalResult(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                text=row["text"],
                score=row["score"],
                metadata=DocumentMetadata(
                    source=row["source"],
                    source_type=row["source_type"],
                    title=row["title"],
                    language=row["language"],
                    extra=row["extra_metadata"] or {},
                ),
            )
            for row in raw_results
        ]

        logger.info(
            "rag_search_complete",
            query_length=len(request.query),
            results_found=len(results),
        )

        return SearchResponse(
            query=request.query,
            results=results,
            total_found=len(results),
        )
