"""
Executor — runs a ToolCall and returns a ToolResult.

Responsibilities:
- Look up the tool in the registry
- Delegate execution to the tool's execute() method
- Emit structured logs for every tool execution (name, duration, success)

The executor does NOT catch errors from tools — BaseTool.execute() already
wraps all exceptions into ToolResult(success=False). The executor's job is
orchestration and observability, not error handling.
"""

from __future__ import annotations

import structlog

from packages.agents.schemas import ToolCall, ToolResult
from packages.agents.tool_registry import ToolRegistry

logger = structlog.get_logger(__name__)


class ExecutorError(Exception):
    """Raised when the executor cannot find the requested tool."""

    pass


class Executor:
    """
    Executes tool calls by delegating to the tool registry.

    Injected with a ToolRegistry at construction time.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        """
        Execute a tool call and return the result.

        Logs the execution with timing and outcome.
        Returns ToolResult(success=False) if the tool is not found.
        """
        tool = self._registry.get(tool_call.tool_name)

        if tool is None:
            logger.warning(
                "tool_not_found",
                tool_name=tool_call.tool_name,
                call_id=tool_call.call_id,
            )
            return ToolResult(
                tool_name=tool_call.tool_name,
                call_id=tool_call.call_id,
                success=False,
                output=None,
                error=f"Tool '{tool_call.tool_name}' is not registered.",
            )

        logger.info(
            "tool_execution_start",
            tool_name=tool_call.tool_name,
            call_id=tool_call.call_id,
            arguments=tool_call.arguments,
        )

        result = await tool.execute(tool_call)

        logger.info(
            "tool_execution_complete",
            tool_name=tool_call.tool_name,
            call_id=tool_call.call_id,
            success=result.success,
            duration_ms=result.duration_ms,
            error=result.error,
        )

        return result
