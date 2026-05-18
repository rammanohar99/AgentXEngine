"""
BaseTool — the abstract contract every tool must implement.

Design:
- Tools are isolated units with typed input schemas (Pydantic)
- Each tool declares its own name, description, and parameter schema
- The schema is used to generate the tool description injected into the LLM prompt
- execute() is always async — no blocking IO allowed
- Tools never raise exceptions to the runtime — they return ToolResult with success=False

Adding a new tool:
1. Subclass BaseTool
2. Define input_schema as a Pydantic model
3. Implement execute()
4. Register with ToolRegistry
"""

from __future__ import annotations

import abc
import time
import uuid
from typing import Any

from pydantic import BaseModel

from packages.agents.schemas import ToolCall, ToolResult


class BaseTool(abc.ABC):
    """Abstract base for all tools in the registry."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique tool identifier — used in LLM prompts and tool calls."""
        ...

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Human-readable description of what the tool does and when to use it."""
        ...

    @property
    @abc.abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """
        JSON Schema describing the tool's input parameters.
        Used to generate the tool description in the system prompt.
        """
        ...

    @abc.abstractmethod
    async def _run(self, arguments: dict[str, Any]) -> Any:
        """
        Core tool logic. Receives validated arguments, returns any serializable value.
        Raise exceptions freely here — the base class wraps them into ToolResult.
        """
        ...

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        """
        Public execution entry point.

        Validates arguments, runs the tool, wraps result in ToolResult.
        Never raises — errors are captured and returned as failed ToolResult.
        """
        call_id = tool_call.call_id or str(uuid.uuid4())
        start = time.perf_counter()

        try:
            output = await self._run(tool_call.arguments)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            return ToolResult(
                tool_name=self.name,
                call_id=call_id,
                success=True,
                output=output,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            return ToolResult(
                tool_name=self.name,
                call_id=call_id,
                success=False,
                output=None,
                error=str(exc),
                duration_ms=duration_ms,
            )

    def to_prompt_description(self) -> str:
        """
        Render the tool as a text block for injection into the system prompt.

        Format:
            Tool: read_file
            Description: Read the contents of a file at the given path.
            Parameters:
              - path (string, required): Absolute or relative file path to read.
        """
        lines = [
            f"Tool: {self.name}",
            f"Description: {self.description}",
            "Parameters:",
        ]
        schema = self.parameters_schema
        properties = schema.get("properties", {})
        required_fields = set(schema.get("required", []))

        for param_name, param_info in properties.items():
            param_type = param_info.get("type", "any")
            param_desc = param_info.get("description", "")
            required_marker = "required" if param_name in required_fields else "optional"
            lines.append(f"  - {param_name} ({param_type}, {required_marker}): {param_desc}")

        return "\n".join(lines)
