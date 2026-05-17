"""
Short-term memory — sliding window of recent conversation turns.

Design:
- In-process storage (dict keyed by session_id)
- Configurable window size (default: last 20 turns)
- Automatically prunes oldest turns when window is exceeded
- Thread-safe for async use (no shared mutable state between requests)

Phase 4 will replace the in-process dict with Redis for multi-process
deployments. The interface stays the same.

Usage:
    memory = ShortTermMemory(window_size=20)
    memory.add_turn(session_id, role="user", content="Hello")
    turns = memory.get_turns(session_id)
    memory.clear(session_id)
"""

from __future__ import annotations

from packages.memory.schemas import ConversationTurn


class ShortTermMemory:
    """
    Sliding window conversation memory.

    Stores the last N turns per session. When the window is exceeded,
    the oldest turns are dropped. This prevents prompt bloat while
    keeping recent context available.
    """

    def __init__(self, window_size: int = 20) -> None:
        if window_size < 1:
            raise ValueError("window_size must be at least 1")
        self._window_size = window_size
        self._store: dict[str, list[ConversationTurn]] = {}

    def add_turn(self, session_id: str, role: str, content: str) -> None:
        """Add a conversation turn. Prunes oldest if window is exceeded."""
        if session_id not in self._store:
            self._store[session_id] = []

        self._store[session_id].append(ConversationTurn(role=role, content=content))

        # Prune to window size
        if len(self._store[session_id]) > self._window_size:
            self._store[session_id] = self._store[session_id][-self._window_size :]

    def get_turns(self, session_id: str) -> list[ConversationTurn]:
        """Return all turns in the current window for a session."""
        return list(self._store.get(session_id, []))

    def get_recent_turns(self, session_id: str, count: int) -> list[ConversationTurn]:
        """Return the most recent N turns."""
        turns = self._store.get(session_id, [])
        return list(turns[-count:])

    def clear(self, session_id: str) -> None:
        """Remove all turns for a session."""
        self._store.pop(session_id, None)

    def session_count(self) -> int:
        """Number of active sessions in memory."""
        return len(self._store)

    def turn_count(self, session_id: str) -> int:
        """Number of turns stored for a session."""
        return len(self._store.get(session_id, []))
