"""
Chat and agent interaction schemas.

These define the API contract for the chat endpoint —
what the frontend sends and what the backend returns.
"""

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
import datetime


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(..., min_length=1, max_length=32_000)
    stream: bool = True
    model: str | None = None  # Override default model if needed


class ChatResponse(BaseModel):
    session_id: str
    message: ChatMessage
    usage: dict[str, int] | None = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))


class StreamChunk(BaseModel):
    """A single chunk in a streaming response."""
    type: str  # "text" | "tool_call" | "tool_result" | "done" | "error"
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
