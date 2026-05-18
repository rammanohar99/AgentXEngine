"""
Agent service — the backend's interface to the agent runtime.

Responsibilities:
- Own the session store (message history per session_id)
- Instantiate and hold the AgentRuntime, MemoryManager, and Tracer
- Record conversation turns in memory after each exchange
- Inject memory context into the runtime's system prompt
- Emit Langfuse traces for every agent run
- Run evaluation after every completed agent run (ADR-005)
- Translate AgentEvent → StreamChunk for the existing API contract

Known limitation: _sessions is an in-memory dict. Sessions are lost on restart
and not shared across replicas. Phase 7 will replace with Redis-backed persistence.
See AGENTS.md — Session and State Management Rules.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any, cast

from redis.asyncio import Redis

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis_client
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse, MessageRole, StreamChunk
from app.services.session import SessionManager
from app.services.vertex_ai import VertexAIService
from packages.agents.runtime import AgentRuntime, Message
from packages.agents.schemas import AgentEventType
from packages.agents.tool_registry import ToolRegistry
from packages.memory.long_term import LongTermMemory
from packages.memory.manager import MemoryManager
from packages.memory.schemas import MemoryContext
from packages.memory.short_term import ShortTermMemory
from packages.memory.summarizer import MemorySummarizer
from packages.observability.evaluation import AgentEvaluator
from packages.observability.tracer import AgentTracer

logger = get_logger(__name__)

# ── Module-level singletons — lazy initialized ────────────────────────────────
# Initialized on first use, not at import time.
# This prevents startup failures when Vertex AI or Redis is unavailable.

_runtime: AgentRuntime | None = None
_memory_manager: MemoryManager | None = None
_tracer: Any = None
_evaluator: AgentEvaluator | None = None


def _get_runtime() -> AgentRuntime:
    global _runtime
    if _runtime is None:
        _runtime = _build_runtime()
    return _runtime


def _get_memory_manager() -> MemoryManager:
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = _build_memory_manager()
    return _memory_manager


def _get_tracer() -> Any:
    global _tracer
    if _tracer is None:
        _tracer = AgentTracer.from_settings(get_settings())
    return _tracer


def _get_evaluator() -> AgentEvaluator:
    """
    Lazy-initialize the evaluator.

    ADR-005: Evaluation is a first-class production system.
    The evaluator runs after every agent run to collect quality metrics.
    It uses a separate VertexAIService instance so evaluation LLM calls
    are independent of the main agent runtime.
    """
    global _evaluator
    if _evaluator is None:
        _evaluator = AgentEvaluator(llm_provider=VertexAIService())
    return _evaluator


def _build_runtime() -> AgentRuntime:
    settings = get_settings()
    vertex_service = VertexAIService()
    registry = ToolRegistry.with_defaults()

    # Wire up the RAG retrieval tool so the agent can query ingested documents
    _register_retrieval_tool(registry, settings, vertex_service)

    return AgentRuntime(
        vertex_service=vertex_service,
        registry=registry,
        max_steps=10,
        llm_timeout_seconds=settings.llm_timeout_seconds,
        tool_timeout_seconds=settings.tool_timeout_seconds,
        max_context_tokens=settings.max_context_tokens,
        max_tool_output_chars=settings.max_tool_output_chars,
    )


def _register_retrieval_tool(
    registry: ToolRegistry,
    settings: Settings,
    vertex_service: VertexAIService,
) -> None:
    """
    Build and register the RAG retrieval tool.

    Skipped gracefully if neither GCP project nor API key is configured.
    """
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        pass

    if not settings.google_cloud_project and not settings.gemini_api_key:
        logger.warning("retrieval_tool_skipped", reason="No GCP project or API key configured")
        return

    try:
        from app.core.database import get_session_factory
        from app.repositories.document import DocumentRepository
        from packages.agents.tools.retrieval import RetrieveDocumentsTool
        from packages.rag.embeddings import EmbeddingService

        embedding_service = EmbeddingService(
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
            api_key=settings.gemini_api_key,  # Takes priority over project if set
        )

        async def retriever(query: str, top_k: int) -> list[dict[str, Any]]:
            """Retriever callable: embeds query and searches pgvector."""
            query_embedding = await embedding_service.embed_query(query)
            async with get_session_factory()() as session:
                repo = DocumentRepository(session)
                return await repo.similarity_search(
                    query_embedding=query_embedding,
                    top_k=top_k,
                    score_threshold=0.0,
                )

        registry.register(RetrieveDocumentsTool(retriever=retriever))
        logger.info("retrieval_tool_registered")
    except Exception as exc:
        logger.warning("retrieval_tool_registration_failed", error=str(exc))


def _build_memory_manager() -> MemoryManager:
    vertex_service = VertexAIService()
    short_term = ShortTermMemory(window_size=20)
    try:
        redis_client = get_redis_client()
        long_term = LongTermMemory(redis_client=redis_client)
    except Exception:
        # Fallback: no-op long-term memory if Redis is unavailable
        long_term = LongTermMemory(redis_client=cast(Redis, _NoOpRedis()))

    summarizer = MemorySummarizer(llm_provider=vertex_service)

    manager_redis_client: Redis | None = None
    try:
        manager_redis_client = get_redis_client()
    except Exception:
        manager_redis_client = None

    return MemoryManager(
        short_term=short_term,
        long_term=long_term,
        summarizer=summarizer,
        redis_client=manager_redis_client,
    )


class _NoOpRedis:
    """Minimal Redis stub used when Redis is unavailable."""

    async def lrange(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []

    async def rpush(self, *args: Any, **kwargs: Any) -> int:
        return 0

    async def expire(self, *args: Any, **kwargs: Any) -> bool:
        return False

    async def llen(self, *args: Any, **kwargs: Any) -> int:
        return 0

    async def ltrim(self, *args: Any, **kwargs: Any) -> bool:
        return False

    async def delete(self, *args: Any, **kwargs: Any) -> int:
        return 0

    async def get(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def set(self, *args: Any, **kwargs: Any) -> bool:
        return False


# ── Service ───────────────────────────────────────────────────────────────────


class AgentService:
    """
    Thin service layer wrapping the AgentRuntime with memory and tracing.
    """

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Non-streaming agent run — collects all events and returns final text."""
        session_id, history = SessionManager.get_or_create(request.session_id)
        user_message = ChatMessage(role=MessageRole.USER, content=request.message)
        SessionManager.append_message(session_id, user_message)

        full_response = ""
        async for chunk in self.stream_chat(request):
            if chunk.type == "text" and chunk.content:
                full_response += chunk.content

        assistant_message = ChatMessage(role=MessageRole.ASSISTANT, content=full_response)
        SessionManager.append_message(session_id, assistant_message)

        return ChatResponse(session_id=session_id, message=assistant_message)

    async def stream_chat(self, request: ChatRequest) -> AsyncGenerator[StreamChunk, None]:
        """
        Streaming agent run with memory context, Langfuse tracing, and evaluation.

        Flow:
        1. Record user turn in memory
        2. Retrieve memory context (short-term + summary + long-term facts)
        3. Inject memory context into the first system message
        4. Run the agent with Langfuse tracing
        5. Record assistant response in memory
        6. Run evaluation asynchronously (non-blocking, ADR-005)
        """
        session_id, history = SessionManager.get_or_create(request.session_id)
        run_id = str(uuid.uuid4())
        run_start = time.perf_counter()

        user_message = ChatMessage(role=MessageRole.USER, content=request.message)
        SessionManager.append_message(session_id, user_message)

        # Record user turn in memory
        await _get_memory_manager().record_turn(session_id, role="user", content=request.message)

        # Retrieve memory context and build enriched history
        memory_context = await _get_memory_manager().get_context(session_id)
        enriched_history = self._build_history_with_memory(history, memory_context)

        logger.info(
            "agent_stream_start",
            session_id=session_id,
            run_id=run_id,
            message_length=len(request.message),
            has_memory=not memory_context.is_empty(),
        )

        full_response_text = ""
        steps_taken = 0
        tool_calls_made = 0

        tracer = _get_tracer()
        with tracer.trace_run(session_id, run_id, request.message) as trace:
            try:
                async for event in _get_runtime().run(
                    session_id=session_id,
                    history=enriched_history,
                    user_message=request.message,
                ):
                    if event.type == AgentEventType.TEXT and event.content:
                        full_response_text += event.content
                    elif event.type == AgentEventType.TOOL_CALL:
                        tool_calls_made += 1
                    elif event.type == AgentEventType.DONE:
                        steps_taken = event.metadata.get("steps", 0)

                    yield StreamChunk(
                        type=event.type.value,
                        content=event.content,
                        metadata={**event.metadata, "session_id": session_id},
                    )

            except Exception as exc:
                logger.error("agent_stream_error", session_id=session_id, error=str(exc))
                yield StreamChunk(
                    type="error",
                    content=f"Agent error: {exc}",
                    metadata={"session_id": session_id},
                )
                return

            # Record assistant response in memory
            if full_response_text:
                assistant_message = ChatMessage(
                    role=MessageRole.ASSISTANT, content=full_response_text
                )
                SessionManager.append_message(session_id, assistant_message)
                await _get_memory_manager().record_turn(
                    session_id, role="assistant", content=full_response_text
                )

            trace.end(output=full_response_text)

        # ADR-005: Run evaluation asynchronously after every completed run.
        # This is fire-and-forget — evaluation must never delay the response.
        # Evaluation failures are caught inside AgentEvaluator and logged as warnings.
        if full_response_text:
            latency_ms = round((time.perf_counter() - run_start) * 1000, 2)
            asyncio.ensure_future(
                _get_evaluator().evaluate_response(
                    query=request.message,
                    response=full_response_text,
                    session_id=session_id,
                    run_id=run_id,
                    steps_taken=steps_taken,
                    tool_calls_made=tool_calls_made,
                    latency_ms=latency_ms,
                )
            )

        logger.info("agent_stream_complete", session_id=session_id, run_id=run_id)

    def _build_history_with_memory(
        self,
        history: list[ChatMessage],
        memory_context: MemoryContext,
    ) -> list[Message]:
        """
        Build the message history for the runtime, prepending memory context
        as a system message if memory is non-empty.
        """
        messages: list[Message] = []

        # Inject memory context as a system message before the conversation
        memory_section = memory_context.to_prompt_section()
        if memory_section:
            messages.append(Message(role="system", content=memory_section))

        # Convert ChatMessage history to runtime Messages
        for msg in history:
            messages.append(Message(role=msg.role.value, content=msg.content))

        return messages
