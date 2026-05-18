"""
Orchestrator — coordinates specialized agents for complex tasks.

The orchestrator is the top-level agent that:
1. Receives the user's request
2. Decides if it can answer directly or needs to delegate
3. Delegates to specialist agents via the DelegateToAgentTool
4. Synthesizes results into a final response

Architecture:
- One orchestrator runtime (with delegation tool) — long-lived, created in __init__
- N specialist runtimes (one per agent type, created lazily, cached)
- Specialists share the same tool registry (minus delegation)
- Communication is via structured task strings and result strings

Design decisions:
- Orchestrator runtime is created ONCE in __init__, not per request.
  ADR-002: The circuit breaker in AgentRuntime must persist across requests.
  Creating a new runtime per request resets the circuit breaker to CLOSED,
  providing zero protection against a degraded LLM.
- Specialists are created lazily (only when needed) and cached by role name.
- Each delegation is a fresh ReAct run (no shared state between agents)
- The orchestrator's context includes delegation results as observations
- Max delegation depth is 1 (no recursive delegation) to prevent loops

Usage:
    orchestrator = Orchestrator(llm_provider, registry)
    async for event in orchestrator.run(session_id, history, message):
        yield event
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import structlog

from packages.agents.agent_types import AgentRole, get_agent_config
from packages.agents.runtime import AgentRuntime, Message
from packages.agents.schemas import AgentEvent, AgentEventType
from packages.agents.tool_registry import ToolRegistry
from packages.agents.tools.delegation import DelegateToAgentTool

logger = structlog.get_logger(__name__)


class Orchestrator:
    """
    Multi-agent orchestrator.

    Runs the orchestrator agent with a delegation tool that can
    invoke specialist agents. Each specialist gets a filtered tool
    registry based on its allowed_tools configuration.

    Usage:
        orchestrator = Orchestrator(llm_provider, base_registry)
        async for event in orchestrator.run(session_id, history, message):
            yield event
    """

    def __init__(self, llm_provider: Any, base_registry: ToolRegistry) -> None:
        self._llm = llm_provider
        self._base_registry = base_registry
        # Cache specialist runtimes — created once per role, reused across requests
        self._specialist_runtimes: dict[str, AgentRuntime] = {}

        # Build the orchestrator runtime ONCE here, not per request.
        # ADR-002: AgentRuntime holds a CircuitBreaker. The circuit breaker's
        # value is its accumulated failure state across multiple requests.
        # Creating a new runtime per request resets the breaker to CLOSED
        # on every call — providing zero protection against a degraded LLM.
        orchestrator_config = get_agent_config(AgentRole.ORCHESTRATOR)
        orchestrator_registry = self._build_orchestrator_registry()
        self._orchestrator_runtime = AgentRuntime(
            vertex_service=self._llm,
            registry=orchestrator_registry,
            max_steps=orchestrator_config.max_steps,
        )
        self._orchestrator_system_prompt = orchestrator_config.system_prompt

    def _get_specialist_runtime(self, role_name: str) -> AgentRuntime:
        """Get or create a specialist runtime for the given role."""
        if role_name not in self._specialist_runtimes:
            try:
                role = AgentRole(role_name)
            except ValueError:
                role = AgentRole.CODING  # Fallback

            config = get_agent_config(role)

            # Build a filtered registry for this specialist
            specialist_registry = self._build_specialist_registry(config.allowed_tools)

            self._specialist_runtimes[role_name] = AgentRuntime(
                vertex_service=self._llm,
                registry=specialist_registry,
                max_steps=config.max_steps,
            )

        return self._specialist_runtimes[role_name]

    def _build_specialist_registry(self, allowed_tools: list[str]) -> ToolRegistry:
        """Build a registry containing only the allowed tools."""
        if not allowed_tools:
            return self._base_registry  # All tools allowed

        filtered = ToolRegistry()
        for tool_name in allowed_tools:
            tool = self._base_registry.get(tool_name)
            if tool is not None:
                filtered.register(tool)
        return filtered

    async def _delegate_to_specialist(self, role_name: str, task: str) -> str:
        """
        Run a specialist agent on a task and return its final answer.

        This is the callable injected into DelegateToAgentTool.
        """
        logger.info("delegation_start", role=role_name, task_length=len(task))

        specialist = self._get_specialist_runtime(role_name)
        role = (
            AgentRole(role_name) if role_name in AgentRole._value2member_map_ else AgentRole.CODING
        )
        config = get_agent_config(role)

        # Build specialist history with its specialized system prompt
        history = [Message(role="system", content=config.system_prompt)]

        final_answer = ""
        async for event in specialist.run(
            session_id=f"specialist-{role_name}-{uuid.uuid4().hex[:8]}",
            history=history,
            user_message=task,
        ):
            if event.type == AgentEventType.TEXT and event.content:
                final_answer += event.content

        logger.info("delegation_complete", role=role_name, answer_length=len(final_answer))
        return final_answer or f"[{role_name} agent produced no output]"

    def _build_orchestrator_registry(self) -> ToolRegistry:
        """Build the orchestrator's registry: base tools + delegation tool."""
        orchestrator_registry = ToolRegistry()

        # Add all base tools
        for tool_name in self._base_registry.list_names():
            tool = self._base_registry.get(tool_name)
            if tool is not None:
                orchestrator_registry.register(tool)

        # Add delegation tool
        orchestrator_registry.register(
            DelegateToAgentTool(delegate_fn=self._delegate_to_specialist)
        )

        return orchestrator_registry

    async def run(
        self,
        session_id: str,
        history: list[Message],
        user_message: str,
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Run the orchestrator for a user message.

        Uses the long-lived orchestrator runtime (created in __init__).
        The circuit breaker state persists across all requests through
        this runtime instance.

        The orchestrator can answer directly or delegate to specialists.
        Delegation results are injected as observations in the ReAct loop.
        """
        # Prepend orchestrator system prompt to history
        enriched_history = [
            Message(role="system", content=self._orchestrator_system_prompt),
            *history,
        ]

        logger.info(
            "orchestrator_run_start",
            session_id=session_id,
            message_length=len(user_message),
        )

        async for event in self._orchestrator_runtime.run(
            session_id=session_id,
            history=enriched_history,
            user_message=user_message,
        ):
            yield event

        logger.info("orchestrator_run_complete", session_id=session_id)
