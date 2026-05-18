"""
Prompt Manager — builds the system prompt for the ReAct agent.

Responsibilities:
- Compose the system instruction from static template + dynamic tool list
- Format the ReAct output structure the LLM must follow
- Build the observation injection message after a tool call

ReAct format used:
    Thought: <reasoning about what to do next>
    Action: <tool_name>
    Action Input: <json arguments>

    --- or, when done ---

    Thought: <reasoning>
    Final Answer: <response to the user>

This format is explicit and parseable without regex magic.
The planner.py module parses this structure.
"""

from __future__ import annotations

from packages.agents.tool_registry import ToolRegistry

REACT_SYSTEM_TEMPLATE = """\
You are a document question-answering assistant. You answer questions STRICTLY based on \
documents retrieved from the knowledge base using the retrieve_documents tool.

You reason step by step using the ReAct format. For each step, you MUST output exactly one of:

FORMAT A — when you need to use a tool:
Thought: <your reasoning about what to do>
Action: <tool_name>
Action Input: <valid JSON object with the tool arguments>

FORMAT B — when you have enough information to answer:
Thought: <your reasoning>
Final Answer: <your complete response to the user>

STRICT RULES — you MUST follow these without exception:
1. ALWAYS call retrieve_documents first for ANY question about document content.
2. Answer ONLY from the retrieved chunks. Never use your own training knowledge.
3. ALWAYS cite the source document for every fact you state. \
   Format: "According to [source filename], ..."
4. If multiple documents contain CONFLICTING information about the same fact, \
   you MUST report ALL values and their sources. Never pick one silently. \
   Example: "doc_a.pdf states 22 cars sold, while doc_b.pdf states 28 cars sold. \
   These documents may cover different time periods or regions."
5. If retrieved chunks do not contain enough information to answer, respond ONLY with: \
   "I could not find information about that in the uploaded documents." \
   Do NOT guess. Do NOT use your own knowledge.
6. For codebase questions (reading files, searching code), use the filesystem tools.

Available tools:
{tool_descriptions}
"""

OBSERVATION_TEMPLATE = """\
Observation: {observation}
"""


class PromptManager:
    """
    Builds prompts for the ReAct runtime.

    Injected into the runtime at construction time.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def build_system_prompt(self) -> str:
        """Build the full system prompt with current tool descriptions."""
        tool_descriptions = self._registry.get_prompt_descriptions()
        return REACT_SYSTEM_TEMPLATE.format(tool_descriptions=tool_descriptions)

    def format_observation(self, observation: str) -> str:
        """Wrap a tool result as an observation message for the LLM."""
        return OBSERVATION_TEMPLATE.format(observation=observation)

    def format_step_limit_message(self, max_steps: int) -> str:
        """Message injected when the agent hits the step limit."""
        return (
            f"You have reached the maximum of {max_steps} reasoning steps. "
            "Provide your best Final Answer now based on what you have gathered so far."
        )
