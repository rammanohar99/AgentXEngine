"""
Workflows API — trigger and monitor multi-agent workflows.

Routes:
  POST /workflows/run    — trigger a workflow (async via Celery)
  GET  /workflows/{id}   — get workflow run status
  POST /workflows/ingest — async document ingestion (queued)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.logging import get_logger
from app.schemas.common import APIResponse
from packages.workflows.schemas import (
    WorkflowRequest,
    WorkflowResponse,
    WorkflowStatus,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("/ingest", response_model=APIResponse[dict])
async def queue_document_ingestion(
    content: str,
    source: str = "",
    source_type: str = "text",
    title: str = "",
) -> APIResponse[dict]:
    """
    Queue a document for async ingestion into the RAG pipeline.

    Returns immediately with a task ID.
    The actual ingestion (chunking + embedding + storage) runs in the background.
    Poll the task status via the task ID.
    """
    try:
        from app.workers.tasks.ingestion import ingest_document

        task = ingest_document.delay(
            content=content,
            metadata={
                "source": source,
                "source_type": source_type,
                "title": title,
            },
        )

        logger.info("ingestion_queued", task_id=task.id, source=source)

        return APIResponse(
            data={
                "task_id": task.id,
                "status": "queued",
                "message": "Document queued for ingestion. Poll task_id for status.",
            }
        )
    except Exception as exc:
        logger.error("ingestion_queue_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue ingestion: {exc}",
        ) from exc


@router.get("/tasks/{task_id}", response_model=APIResponse[dict])
async def get_task_status(task_id: str) -> APIResponse[dict]:
    """
    Get the status of a background task.

    Returns the task state and result if complete.
    """
    try:
        from app.workers.celery_app import celery_app
        from celery.result import AsyncResult

        result = AsyncResult(task_id, app=celery_app)

        response_data: dict = {
            "task_id": task_id,
            "status": result.status.lower(),
        }

        if result.ready():
            if result.successful():
                response_data["result"] = result.result
            else:
                response_data["error"] = str(result.result)

        return APIResponse(data=response_data)

    except Exception as exc:
        logger.error("task_status_failed", task_id=task_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get task status: {exc}",
        ) from exc
