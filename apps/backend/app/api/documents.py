"""
Documents API — ingest and search endpoints.

Routes:
  POST /documents/upload  — upload any supported file and ingest into RAG
  POST /documents/ingest  — ingest pre-extracted text into the RAG pipeline
  POST /documents/search  — semantic search over the knowledge base

Supported upload formats:
  PDF   (.pdf)              — text extraction via pypdf
  Excel (.xlsx, .xls)       — openpyxl, all sheets as text tables
  CSV   (.csv)              — formatted as aligned text table
  Image (.png, .jpg, .jpeg,
         .webp, .tiff, .bmp) — Gemini Vision OCR
  Text  (everything else)   — UTF-8 decode

Routes are thin: validate input, call RAGService, return typed response.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from packages.rag.extractor import (
    extract_image_text,
    extract_text,
    get_source_type,
)
from packages.rag.schemas import (
    DocumentMetadata,
    IngestRequest,
    IngestResponse,
    SearchRequest,
    SearchResponse,
)
from packages.rag.schemas import (
    IngestRequest as RagIngestRequest,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.logging import get_logger
from app.schemas.common import APIResponse
from app.services.rag import RAGService

logger = get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

# 10 MB — generous enough for spreadsheets and multi-page scans
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def get_rag_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> RAGService:
    """
    Dependency injection for RAGService.

    Supports both Gemini Developer API (api_key) and Vertex AI (project).
    """
    settings = get_settings()
    if not settings.google_cloud_project and not settings.gemini_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Neither GOOGLE_CLOUD_PROJECT nor GEMINI_API_KEY is configured. "
                "RAG features are unavailable."
            ),
        )

    from packages.rag.embeddings import EmbeddingService

    embedding_service = EmbeddingService(
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
        api_key=settings.gemini_api_key,
    )
    return RAGService(session=session, embedding_service=embedding_service)


@router.get("/", response_model=APIResponse[list[dict[str, Any]]])
async def list_documents(
    service: Annotated[RAGService, Depends(get_rag_service)],
) -> APIResponse[list[dict[str, Any]]]:
    """
    List all ingested documents with metadata and chunk counts.
    Ordered by most recently ingested first.
    """
    try:
        docs = await service.list_documents()
        return APIResponse(data=docs)
    except Exception as exc:
        logger.error("list_documents_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list documents: {exc}",
        ) from exc


@router.delete("/{document_id}", response_model=APIResponse[dict[str, Any]])
async def delete_document(
    document_id: str,
    service: Annotated[RAGService, Depends(get_rag_service)],
) -> APIResponse[dict[str, Any]]:
    """
    Delete a document and all its chunks from the knowledge base.
    Returns 404 if the document does not exist.
    """
    try:
        deleted = await service.delete_document(document_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' not found.",
            )
        return APIResponse(data={"deleted": document_id})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("delete_document_error", document_id=document_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {exc}",
        ) from exc


@router.post("/upload", response_model=APIResponse[IngestResponse])
async def upload_document(
    file: Annotated[UploadFile, File(...)],
    service: Annotated[RAGService, Depends(get_rag_service)],
) -> APIResponse[IngestResponse]:
    """
    Upload a file and ingest it into the RAG knowledge base.

    Supported: PDF, Excel (.xlsx/.xls), CSV, images (PNG/JPG/JPEG/WEBP/TIFF/BMP), text files.
    Returns the document ID and number of chunks created.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided.",
        )

    filename = file.filename
    content_bytes = await file.read()

    if len(content_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    source_type = get_source_type(filename)

    try:
        if source_type == "image":
            # Use Gemini Vision for OCR — no Tesseract system dependency needed
            settings = get_settings()
            from google import genai as _genai

            if settings.gemini_api_key:
                gemini_client = _genai.Client(api_key=settings.gemini_api_key)
            else:
                gemini_client = _genai.Client(
                    vertexai=True,
                    project=settings.google_cloud_project,
                    location=settings.google_cloud_location,
                )
            content = await extract_image_text(
                content_bytes,
                filename,
                gemini_client=gemini_client,
                model=settings.vertex_ai_model,
            )
        else:
            content = extract_text(content_bytes, filename)

    except ValueError as exc:
        logger.warning("upload_extraction_warning", filename=filename, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("upload_parse_error", filename=filename, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse '{filename}': {exc}",
        ) from exc

    if not content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No text could be extracted from '{filename}'.",
        )

    logger.info(
        "upload_extracted",
        filename=filename,
        source_type=source_type,
        content_length=len(content),
    )

    request = RagIngestRequest(
        content=content,
        metadata=DocumentMetadata(
            source=filename,
            source_type=source_type,
            title=filename.rsplit(".", 1)[0],
        ),
    )

    try:
        response = await service.ingest(request)
        return APIResponse(data=response)
    except Exception as exc:
        logger.error("upload_ingest_error", filename=filename, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {exc}",
        ) from exc


@router.post("/ingest", response_model=APIResponse[IngestResponse])
async def ingest_document(
    request: IngestRequest,
    service: Annotated[RAGService, Depends(get_rag_service)],
) -> APIResponse[IngestResponse]:
    """
    Ingest pre-extracted text into the RAG knowledge base.

    The document is chunked, embedded, and stored in pgvector.
    Returns the document ID and number of chunks created.
    """
    try:
        response = await service.ingest(request)
        return APIResponse(data=response)
    except Exception as exc:
        logger.error("ingest_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {exc}",
        ) from exc


@router.post("/search", response_model=APIResponse[SearchResponse])
async def search_documents(
    request: SearchRequest,
    service: Annotated[RAGService, Depends(get_rag_service)],
) -> APIResponse[SearchResponse]:
    """
    Search the knowledge base using semantic similarity.

    Returns ranked chunks with similarity scores.
    """
    try:
        response = await service.search(request)
        return APIResponse(data=response)
    except Exception as exc:
        logger.error("search_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {exc}",
        ) from exc
