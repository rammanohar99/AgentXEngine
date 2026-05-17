"""
Session service — authoritative runtime state consolidation.

Provides a single authoritative in-memory session layer, eliminating
fragmented runtime ownership between ChatService and AgentService.
Establishes a lifecycle-safe state access pattern and persistence
migration path for Phase 7 (Redis).
"""

import uuid

from app.schemas.chat import ChatMessage

# Single source of truth for runtime session state
_sessions: dict[str, list[ChatMessage]] = {}


class SessionManager:
    """
    Centralized session coordination.
    """

    @classmethod
    def get_or_create(cls, session_id: str | None) -> tuple[str, list[ChatMessage]]:
        """Return existing session history or create a new one."""
        sid = session_id or str(uuid.uuid4())
        if sid not in _sessions:
            _sessions[sid] = []
        return sid, _sessions[sid]

    @classmethod
    def append_message(cls, session_id: str, message: ChatMessage) -> None:
        """Append a message to the session history."""
        if session_id in _sessions:
            _sessions[session_id].append(message)

    @classmethod
    def get_history(cls, session_id: str) -> list[ChatMessage]:
        """Get the current history for a session."""
        return _sessions.get(session_id, [])

    @classmethod
    def clear(cls, session_id: str) -> None:
        """Clear a session."""
        if session_id in _sessions:
            del _sessions[session_id]
