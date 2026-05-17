"""
Memory system unit tests.

All tests are deterministic — no Redis, no LLM calls needed.
Long-term memory uses a mock Redis client.
Summarizer uses a mock LLM provider.
"""

from __future__ import annotations

import pytest

from packages.memory.manager import MemoryManager
from packages.memory.schemas import ConversationTurn
from packages.memory.short_term import ShortTermMemory
from packages.memory.summarizer import MemorySummarizer


# ── Short-term memory tests ───────────────────────────────────────────────────


def test_short_term_stores_turns() -> None:
    memory = ShortTermMemory(window_size=10)
    memory.add_turn("s1", role="user", content="Hello")
    memory.add_turn("s1", role="assistant", content="Hi there")
    turns = memory.get_turns("s1")
    assert len(turns) == 2
    assert turns[0].role == "user"
    assert turns[1].role == "assistant"


def test_short_term_window_prunes_oldest() -> None:
    memory = ShortTermMemory(window_size=3)
    for i in range(5):
        memory.add_turn("s1", role="user", content=f"Message {i}")
    turns = memory.get_turns("s1")
    assert len(turns) == 3
    assert turns[0].content == "Message 2"  # Oldest kept
    assert turns[-1].content == "Message 4"  # Most recent


def test_short_term_get_recent_turns() -> None:
    memory = ShortTermMemory(window_size=10)
    for i in range(6):
        memory.add_turn("s1", role="user", content=f"Msg {i}")
    recent = memory.get_recent_turns("s1", count=3)
    assert len(recent) == 3
    assert recent[-1].content == "Msg 5"


def test_short_term_clear() -> None:
    memory = ShortTermMemory(window_size=10)
    memory.add_turn("s1", role="user", content="Hello")
    memory.clear("s1")
    assert memory.get_turns("s1") == []


def test_short_term_isolates_sessions() -> None:
    memory = ShortTermMemory(window_size=10)
    memory.add_turn("s1", role="user", content="Session 1")
    memory.add_turn("s2", role="user", content="Session 2")
    assert len(memory.get_turns("s1")) == 1
    assert len(memory.get_turns("s2")) == 1
    assert memory.get_turns("s1")[0].content == "Session 1"


def test_short_term_invalid_window_raises() -> None:
    with pytest.raises(ValueError):
        ShortTermMemory(window_size=0)


def test_short_term_turn_count() -> None:
    memory = ShortTermMemory(window_size=10)
    assert memory.turn_count("s1") == 0
    memory.add_turn("s1", role="user", content="Hi")
    assert memory.turn_count("s1") == 1


# ── Long-term memory tests ────────────────────────────────────────────────────


class MockRedis:
    """In-memory Redis mock for testing."""

    def __init__(self) -> None:
        self._store: dict[str, list[str]] = {}
        self._strings: dict[str, str] = {}

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        items = self._store.get(key, [])
        if end == -1:
            return list(items[start:])
        return list(items[start : end + 1])

    async def rpush(self, key: str, value: str) -> int:
        if key not in self._store:
            self._store[key] = []
        self._store[key].append(value)
        return len(self._store[key])

    async def expire(self, key: str, ttl: int) -> int:
        return 1

    async def llen(self, key: str) -> int:
        return len(self._store.get(key, []))

    async def ltrim(self, key: str, start: int, end: int) -> str:
        items = self._store.get(key, [])
        if end == -1:
            self._store[key] = items[start:]
        else:
            self._store[key] = items[start : end + 1]
        return "OK"

    async def delete(self, key: str) -> int:
        removed = 1 if key in self._store else 0
        self._store.pop(key, None)
        self._strings.pop(key, None)
        return removed

    async def get(self, key: str) -> str | None:
        return self._strings.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> str:
        self._strings[key] = value
        return "OK"


@pytest.mark.asyncio
async def test_long_term_stores_and_retrieves_facts() -> None:
    from packages.memory.long_term import LongTermMemory

    memory = LongTermMemory(redis_client=MockRedis())
    await memory.store_fact("s1", "User prefers Python")
    await memory.store_fact("s1", "Project uses FastAPI")
    facts = await memory.get_facts("s1")
    assert "User prefers Python" in facts
    assert "Project uses FastAPI" in facts


@pytest.mark.asyncio
async def test_long_term_deduplicates_facts() -> None:
    from packages.memory.long_term import LongTermMemory

    memory = LongTermMemory(redis_client=MockRedis())
    await memory.store_fact("s1", "Same fact")
    await memory.store_fact("s1", "Same fact")
    facts = await memory.get_facts("s1")
    assert facts.count("Same fact") == 1


@pytest.mark.asyncio
async def test_long_term_clear() -> None:
    from packages.memory.long_term import LongTermMemory

    memory = LongTermMemory(redis_client=MockRedis())
    await memory.store_fact("s1", "A fact")
    await memory.clear("s1")
    facts = await memory.get_facts("s1")
    assert facts == []


@pytest.mark.asyncio
async def test_long_term_isolates_sessions() -> None:
    from packages.memory.long_term import LongTermMemory

    memory = LongTermMemory(redis_client=MockRedis())
    await memory.store_fact("s1", "Fact for session 1")
    await memory.store_fact("s2", "Fact for session 2")
    s1_facts = await memory.get_facts("s1")
    s2_facts = await memory.get_facts("s2")
    assert "Fact for session 1" in s1_facts
    assert "Fact for session 2" not in s1_facts
    assert "Fact for session 2" in s2_facts


# ── Summarizer tests ──────────────────────────────────────────────────────────


class MockLLM:
    """Mock LLM that returns a fixed summary."""

    async def complete(self, messages, temperature=0.1, **kwargs):
        response = type("R", (), {"text": "This is a test summary."})()
        return response


@pytest.mark.asyncio
async def test_summarizer_produces_summary() -> None:
    summarizer = MemorySummarizer(llm_provider=MockLLM())
    turns = [
        ConversationTurn(role="user", content="What is FastAPI?"),
        ConversationTurn(role="assistant", content="FastAPI is a Python web framework."),
    ]
    summary = await summarizer.summarize("s1", turns)
    assert summary == "This is a test summary."


@pytest.mark.asyncio
async def test_summarizer_empty_turns_returns_empty() -> None:
    summarizer = MemorySummarizer(llm_provider=MockLLM())
    summary = await summarizer.summarize("s1", [])
    assert summary == ""


# ── Memory manager tests ──────────────────────────────────────────────────────


def _make_manager(window_size: int = 20) -> MemoryManager:
    from packages.memory.long_term import LongTermMemory

    short_term = ShortTermMemory(window_size=window_size)
    long_term = LongTermMemory(redis_client=MockRedis())
    summarizer = MemorySummarizer(llm_provider=MockLLM())
    redis = MockRedis()
    return MemoryManager(
        short_term=short_term,
        long_term=long_term,
        summarizer=summarizer,
        redis_client=redis,
    )


@pytest.mark.asyncio
async def test_manager_records_turns() -> None:
    manager = _make_manager()
    await manager.record_turn("s1", role="user", content="Hello")
    await manager.record_turn("s1", role="assistant", content="Hi")
    context = await manager.get_context("s1")
    assert len(context.short_term) == 2


@pytest.mark.asyncio
async def test_manager_context_is_empty_for_new_session() -> None:
    manager = _make_manager()
    context = await manager.get_context("new-session")
    assert context.is_empty()


@pytest.mark.asyncio
async def test_manager_stores_long_term_facts() -> None:
    manager = _make_manager()
    await manager.store_fact("s1", "User prefers dark mode")
    context = await manager.get_context("s1")
    assert "User prefers dark mode" in context.long_term_facts


@pytest.mark.asyncio
async def test_manager_triggers_summarization_at_threshold() -> None:
    """When turns exceed the threshold, older turns should be summarized."""
    manager = _make_manager(window_size=30)

    # Add enough turns to trigger summarization (threshold is 16)
    for i in range(18):
        role = "user" if i % 2 == 0 else "assistant"
        await manager.record_turn("s1", role=role, content=f"Message {i}")

    context = await manager.get_context("s1")
    # After summarization, short-term should have fewer turns
    assert len(context.short_term) < 18
    # And there should be a summary
    assert context.summary is not None


@pytest.mark.asyncio
async def test_manager_clear_session() -> None:
    manager = _make_manager()
    await manager.record_turn("s1", role="user", content="Hello")
    await manager.store_fact("s1", "A fact")
    await manager.clear_session("s1")
    context = await manager.get_context("s1")
    assert context.is_empty()


@pytest.mark.asyncio
async def test_memory_context_prompt_section() -> None:
    from packages.memory.schemas import ConversationTurn, MemoryContext

    context = MemoryContext(
        session_id="s1",
        short_term=[
            ConversationTurn(role="user", content="What is Python?"),
            ConversationTurn(role="assistant", content="Python is a programming language."),
        ],
        summary="User asked about Python basics.",
        long_term_facts=["User is a beginner"],
    )
    section = context.to_prompt_section()
    assert "Memory Context" in section
    assert "Python" in section
    assert "User is a beginner" in section
    assert "User asked about Python basics" in section
