"""
Delegation tool — allows the orchestrator to delegate tasks to specialist agents.

When the orchestrator calls this tool, it:
1. Selects the appropriate specialist agent
2. Runs the specialist's ReAct loop with the delegated task
3. Returns the specialist's response as a tool result

This is the core of multi-agent coordination. The orchestrator
remains in control — it decides when and what to delegate.

Design:
- The tool accepts a delegate_fn callable (injected at construction)
- This keeps the tool decoupled from the runtime and LLM service
- The delegate_fn is provided by the OrchestratorService
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from packages.agents.tools.base import BaseTool

# Type: (agent_role: str, task: str) → result string
DelegateFn = Callable[[str, str], Awaitable[str]]


class DelegateToAgentTool(BaseTool):
    """
    Delegates a task to a specialized agent.

    The orchestrator uses this to hand off work to specialists.
    """

    def __init__(self, delegate_fn: DelegateFn) -> None:
        self._delegate = delegate_fn

    @property
    def name(self) -> str:
        return "delegate_to_agent"

    @property
    def description(self) -> str:
        return (
            "Delegate a task to a specialized agent. "
            "Use this when the task requires specialist expertise. "
            "Available agents: planner, coding, retrieval, debugging, devops."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": (
                        "The specialist agent to delegate to. "
                        "One of: planner, coding, retrieval, debugging, devops."
                    ),
                },
                "task": {
                    "type": "string",
                    "description": "The specific task for the specialist to complete.",
                },
            },
            "required": ["agent", "task"],
        }

    async def _run(self, arguments: dict[str, Any]) -> str:
        agent_role: str = arguments["agent"].lower().strip()
        task: str = arguments["task"]

        valid_roles = {"planner", "coding", "retrieval", "debugging", "devops"}
        if agent_role not in valid_roles:
            raise ValueError(
                f"Unknown agent role '{agent_role}'. Valid roles: {', '.join(sorted(valid_roles))}"
            )

        result = await self._delegate(agent_role, task)
        return f"[{agent_role.title()} Agent Result]\n{result}"
