"""
Planner unit tests.

Tests the ReAct output parser in isolation — no LLM calls, no tools needed.
All inputs are deterministic strings.
"""

import pytest
from packages.agents.planner import Planner
from packages.agents.schemas import DecisionType
from packages.agents.tool_registry import ToolRegistry


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry.with_defaults()


@pytest.fixture
def planner(registry: ToolRegistry) -> Planner:
    return Planner(registry)


def test_parses_final_answer(planner: Planner) -> None:
    output = """Thought: I have enough information to answer.
Final Answer: The answer is 42."""
    decision = planner.parse(output)
    assert decision.decision_type == DecisionType.FINAL_ANSWER
    assert decision.final_answer == "The answer is 42."
    assert "enough information" in decision.reasoning


def test_parses_tool_call(planner: Planner) -> None:
    output = """Thought: I need to read the file to understand the code.
Action: read_file
Action Input: {"path": "apps/backend/app/main.py"}"""
    decision = planner.parse(output)
    assert decision.decision_type == DecisionType.TOOL_CALL
    assert decision.tool_call is not None
    assert decision.tool_call.tool_name == "read_file"
    assert decision.tool_call.arguments == {"path": "apps/backend/app/main.py"}
    assert "read the file" in decision.reasoning


def test_parses_list_directory_call(planner: Planner) -> None:
    output = """Thought: Let me explore the directory structure.
Action: list_directory
Action Input: {"path": ".", "depth": 2}"""
    decision = planner.parse(output)
    assert decision.decision_type == DecisionType.TOOL_CALL
    assert decision.tool_call is not None
    assert decision.tool_call.tool_name == "list_directory"
    assert decision.tool_call.arguments["depth"] == 2


def test_parses_search_files_call(planner: Planner) -> None:
    output = """Thought: I should search for the function definition.
Action: search_files
Action Input: {"pattern": "def create_app", "file_pattern": "*.py"}"""
    decision = planner.parse(output)
    assert decision.decision_type == DecisionType.TOOL_CALL
    assert decision.tool_call is not None
    assert decision.tool_call.tool_name == "search_files"
    assert decision.tool_call.arguments["pattern"] == "def create_app"


def test_unknown_tool_falls_back_to_final_answer(planner: Planner) -> None:
    output = """Thought: I'll use a tool that doesn't exist.
Action: nonexistent_tool
Action Input: {"foo": "bar"}"""
    decision = planner.parse(output)
    assert decision.decision_type == DecisionType.FINAL_ANSWER
    assert "nonexistent_tool" in (decision.final_answer or "")


def test_fallback_when_no_format(planner: Planner) -> None:
    """Unformatted output should be treated as a final answer."""
    output = "Here is a plain response without any ReAct formatting."
    decision = planner.parse(output)
    assert decision.decision_type == DecisionType.FINAL_ANSWER
    assert decision.final_answer == output


def test_action_input_with_code_fence(planner: Planner) -> None:
    """Action Input wrapped in markdown code fences should still parse."""
    output = """Thought: Reading the config file.
Action: read_file
Action Input:
```json
{"path": "apps/backend/.env.example"}
```"""
    decision = planner.parse(output)
    assert decision.decision_type == DecisionType.TOOL_CALL
    assert decision.tool_call is not None
    assert decision.tool_call.arguments["path"] == "apps/backend/.env.example"


def test_tool_call_id_is_set(planner: Planner) -> None:
    """Every parsed tool call should have a unique call_id."""
    output = """Thought: Reading a file.
Action: read_file
Action Input: {"path": "README.md"}"""
    decision = planner.parse(output)
    assert decision.tool_call is not None
    assert decision.tool_call.call_id != ""
