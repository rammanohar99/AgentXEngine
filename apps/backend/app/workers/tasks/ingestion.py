"""
Celery tasks for async document ingestion.

Why async ingestion via Celery?
- Embedding large documents takes 5-30 seconds
- We don't want HTTP requests to block that long
- The API accepts the document, queues the task, returns immediately
- The worker processes it in the background
- Status can be polled via task ID

Task: ingest_document
  Input:  content (str), metadata (dict)
  Output: {"document_id": str, "chunk_count": int, "status": "complete"}
  Errors: Retried up to 3 times with exponential backoff
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import Task

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(  # type: ignore
    name="ingestion.ingest_document",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def ingest_document(
    self: Task,
    content: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """
    Ingest a document into the RAG pipeline asynchronously.

    This task:
    1. Chunks the document
    2. Generates embeddings via Vertex AI
    3. Stores chunks in pgvector
    4. Returns the document ID and chunk count

    Retries on transient failures (network, API rate limits).
    """
    try:
        result = asyncio.run(_ingest_document_async(content, metadata))
        logger.info(
            "ingest_document_complete",
            extra={
                "document_id": result["document_id"],
                "chunk_count": result["chunk_count"],
                "task_id": self.request.id,
            },
        )
        return result
    except Exception as exc:
        logger.error(
            "ingest_document_failed",
            extra={"error": str(exc), "task_id": self.request.id},
        )
        raise self.retry(exc=exc, countdown=2**self.request.retries * 10) from exc


async def _ingest_document_async(content: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """Async implementation of document ingestion."""
    from packages.rag.embeddings import EmbeddingService
    from packages.rag.schemas import DocumentMetadata, IngestRequest

    from app.core.config import get_settings
    from app.core.database import get_session_factory
    from app.services.rag import RAGService

    settings = get_settings()
    embedding_service = EmbeddingService(
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
    )

    doc_metadata = DocumentMetadata(
        source=metadata.get("source", ""),
        source_type=metadata.get("source_type", ""),
        title=metadata.get("title", ""),
        language=metadata.get("language", ""),
        extra=metadata.get("extra", {}),
    )

    async with get_session_factory()() as session:
        rag_service = RAGService(session=session, embedding_service=embedding_service)
        response = await rag_service.ingest(IngestRequest(content=content, metadata=doc_metadata))
        await session.commit()

    return {
        "document_id": response.document_id,
        "chunk_count": response.chunk_count,
        "source": response.source,
        "status": "complete",
    }
