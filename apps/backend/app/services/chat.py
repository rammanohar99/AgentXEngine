"""
Chat service — orchestrates message handling between the API and the AI backend.

Responsibilities:
- Manage session context (short-term message history)
- Build prompts with system instructions
- Delegate to VertexAIService for completions
- Return streaming or non-streaming responses

This is intentionally simple for Phase 1.
The agent runtime (Phase 2) will replace the direct LLM call
with a full ReAct loop.
"""

from collections.abc import AsyncGenerator

from app.core.logging import get_logger
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse, MessageRole, StreamChunk
from app.services.session import SessionManager
from app.services.vertex_ai import VertexAIService

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are an AI engineering assistant built on the AI Engineering OS platform.

You help developers:
- Understand codebases and repositories
- Answer engineering questions
- Debug systems and errors
- Plan and architect solutions
- Explain technical concepts clearly

Be concise, precise, and technically accurate. Prefer code examples when relevant."""


class ChatService:
    def __init__(self) -> None:
        self._vertex = VertexAIService()

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Non-streaming chat completion."""
        session_id, history = SessionManager.get_or_create(request.session_id)

        user_message = ChatMessage(role=MessageRole.USER, content=request.message)
        SessionManager.append_message(session_id, user_message)

        logger.info("chat_request", session_id=session_id, message_length=len(request.message))

        # Dynamically inject system prompt
        messages = (
            [ChatMessage(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT)] + history + [user_message]
        )

        response = await self._vertex.complete(messages=messages)
        reply_text = response.text

        assistant_message = ChatMessage(role=MessageRole.ASSISTANT, content=reply_text)
        SessionManager.append_message(session_id, assistant_message)

        usage = {
            "input_tokens": response.usage_metadata.prompt_token_count,
            "output_tokens": response.usage_metadata.candidates_token_count,
        }

        logger.info("chat_response", session_id=session_id, usage=usage)

        return ChatResponse(
            session_id=session_id,
            message=assistant_message,
            usage=usage,
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncGenerator[StreamChunk, None]:
        """Streaming chat — yields StreamChunk objects."""
        session_id, history = SessionManager.get_or_create(request.session_id)

        user_message = ChatMessage(role=MessageRole.USER, content=request.message)
        SessionManager.append_message(session_id, user_message)

        logger.info("chat_stream_start", session_id=session_id, message_length=len(request.message))

        full_response = ""

        # Dynamically inject system prompt
        messages = (
            [ChatMessage(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT)] + history + [user_message]
        )

        async for text_chunk in self._vertex.stream(messages=messages):
            full_response += text_chunk
            yield StreamChunk(type="text", content=text_chunk, metadata={"session_id": session_id})

        # Persist the complete assistant response to session history
        assistant_message = ChatMessage(role=MessageRole.ASSISTANT, content=full_response)
        SessionManager.append_message(session_id, assistant_message)

        yield StreamChunk(type="done", metadata={"session_id": session_id})
        logger.info("chat_stream_complete", session_id=session_id)
