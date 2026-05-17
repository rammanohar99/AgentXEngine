"""
Chat API routes.

Routes are thin — they validate input, call the service, and return typed responses.
Business logic lives in app.services.agent (AgentService → AgentRuntime).

Supports both:
- POST /chat        — non-streaming, returns full response
- POST /chat/stream — streaming, returns Server-Sent Events

The SSE stream emits JSON-encoded StreamChunk objects.
Chunk types: text | reasoning | tool_call | tool_result | done | error
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.logging import get_logger
from app.schemas.chat import ChatRequest, ChatResponse, StreamChunk
from app.schemas.common import APIResponse
from app.services.agent import AgentService

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


def get_agent_service() -> AgentService:
    """Dependency injection for AgentService."""
    return AgentService()


@router.post("", response_model=APIResponse[ChatResponse])
async def chat(
    request: ChatRequest,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> APIResponse[ChatResponse]:
    """Non-streaming agent chat completion."""
    try:
        response = await service.chat(request)
        return APIResponse(data=response)
    except Exception as exc:
        logger.error("chat_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent chat failed",
        ) from exc


@router.post("/stream")
async def stream_chat(
    request: ChatRequest,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> StreamingResponse:
    """
    Streaming agent chat via Server-Sent Events.

    Each SSE event carries a JSON-encoded StreamChunk.
    The stream ends with type="done".

    Chunk types the client should handle:
      text        — append to the current message bubble
      reasoning   — render as a collapsible thought block
      tool_call   — render as a tool invocation card
      tool_result — render as a tool output card
      done        — close the stream
      error       — display error, close stream
    """

    async def event_generator():
        try:
            async for chunk in service.stream_chat(request):
                yield f"data: {chunk.model_dump_json()}\n\n"
        except Exception as exc:
            logger.error("chat_stream_error", error=str(exc))
            error_chunk = StreamChunk(type="error", content=str(exc))
            yield f"data: {error_chunk.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
