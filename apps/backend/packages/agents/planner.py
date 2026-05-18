"""
Planner — parses raw LLM output into a typed AgentDecision.

The planner is the bridge between the LLM's text output and the runtime's
typed decision system. It does one thing: parse a ReAct-formatted response
and return either a ToolCall decision or a FinalAnswer decision.

Parsing strategy:
- Look for "Final Answer:" → DecisionType.FINAL_ANSWER
- Look for "Action:" + "Action Input:" → DecisionType.TOOL_CALL
- Extract "Thought:" as the reasoning field
- If neither is found, treat the full text as a final answer (graceful fallback)

This is intentionally simple text parsing — no regex complexity, no LLM calls.
The format is enforced by the system prompt in prompt_manager.py.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from packages.agents.schemas import AgentDecision, DecisionType, ToolCall
from packages.agents.tool_registry import ToolRegistry


class PlannerError(Exception):
    """Raised when the planner cannot parse the LLM output."""

    pass


class Planner:
    """
    Parses a single LLM response into an AgentDecision.

    Injected with the ToolRegistry to validate that the requested tool exists.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def parse(self, llm_output: str) -> AgentDecision:
        """
        Parse raw LLM text into a typed AgentDecision.

        Handles:
        - Clean ReAct format (Thought / Action / Action Input)
        - Final Answer format (Thought / Final Answer)
        - Graceful fallback when format is not followed
        """
        text = llm_output.strip()

        reasoning = self._extract_section(text, "Thought:")
        final_answer_text = self._extract_section(text, "Final Answer:")
        action_name = self._extract_section(text, "Action:")
        action_input_text = self._extract_section(text, "Action Input:")

        # Final Answer takes priority
        if final_answer_text:
            return AgentDecision(
                decision_type=DecisionType.FINAL_ANSWER,
                reasoning=reasoning,
                final_answer=final_answer_text,
            )

        # Tool call path
        if action_name:
            tool_name = action_name.strip()

            # Validate the tool exists
            if self._registry.get(tool_name) is None:
                # Unknown tool — treat as final answer with an error note
                return AgentDecision(
                    decision_type=DecisionType.FINAL_ANSWER,
                    reasoning=reasoning,
                    final_answer=(
                        f"I attempted to use tool '{tool_name}' which is not available. "
                        f"Here is what I know based on the context so far:\n\n{reasoning}"
                    ),
                )

            arguments = self._parse_action_input(action_input_text)

            return AgentDecision(
                decision_type=DecisionType.TOOL_CALL,
                reasoning=reasoning,
                tool_call=ToolCall(
                    tool_name=tool_name,
                    arguments=arguments,
                    call_id=str(uuid.uuid4()),
                ),
            )

        # Fallback: no recognizable format — treat entire output as final answer
        return AgentDecision(
            decision_type=DecisionType.FINAL_ANSWER,
            reasoning="",
            final_answer=text,
        )

    def _extract_section(self, text: str, marker: str) -> str:
        """
        Extract the content after a marker up to the next known marker.

        Example:
            text = "Thought: I need to read the file\nAction: read_file\n..."
            _extract_section(text, "Thought:") → "I need to read the file"
        """
        known_markers = ["Thought:", "Action:", "Action Input:", "Final Answer:", "Observation:"]

        lower_text = text.lower()
        marker_lower = marker.lower()

        start_idx = lower_text.find(marker_lower)
        if start_idx == -1:
            return ""

        content_start = start_idx + len(marker)

        # Find the next marker after this one
        end_idx = len(text)
        for other_marker in known_markers:
            if other_marker.lower() == marker_lower:
                continue
            next_pos = lower_text.find(other_marker.lower(), content_start)
            if next_pos != -1 and next_pos < end_idx:
                end_idx = next_pos

        return text[content_start:end_idx].strip()

    def _parse_action_input(self, raw_input: str) -> dict[str, Any]:
        """
        Parse the Action Input section as JSON.

        Handles:
        - Valid JSON objects
        - Python dict literals (single quotes) that the LLM sometimes emits
        - Graceful fallback to {"input": raw} if nothing else works
        """
        if not raw_input:
            return {}

        # Strip markdown code fences if present
        cleaned = raw_input.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        cleaned = cleaned.strip()

        # 1. Try standard JSON first
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
            return {"input": parsed}
        except json.JSONDecodeError:
            pass

        # 2. Try converting Python dict literal → JSON (single quotes → double quotes)
        # The LLM sometimes outputs {'key': 'value'} instead of {"key": "value"}
        try:
            import ast

            parsed = ast.literal_eval(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, SyntaxError):
            pass

        # 3. Last resort: return the raw string as a single argument
        return {"input": cleaned}
