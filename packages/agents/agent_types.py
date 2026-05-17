"""
Specialized agent type definitions.

Each agent type has:
- A name and role description
- A specialized system prompt that focuses its behavior
- A set of tools it's allowed to use

The orchestrator selects which agent type to delegate to based on
the task at hand. Each specialized agent runs the same ReAct runtime
but with a different system prompt and tool set.

AGENTS.md specifies:
- planner agent
- coding agent
- retrieval agent
- debugging agent
- DevOps agent

Design: agent types are data, not classes. The runtime is reused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    PLANNER = "planner"
    CODING = "coding"
    RETRIEVAL = "retrieval"
    DEBUGGING = "debugging"
    DEVOPS = "devops"


@dataclass
class AgentTypeConfig:
    """Configuration for a specialized agent type."""

    role: AgentRole
    name: str
    description: str
    system_prompt: str
    allowed_tools: list[str] = field(default_factory=list)  # Empty = all tools allowed
    max_steps: int = 10


# ── Specialized system prompts ────────────────────────────────────────────────

_PLANNER_PROMPT = """\
You are a planning agent. Your job is to break down complex tasks into
clear, ordered subtasks that other specialized agents can execute.

When given a task:
1. Analyze what needs to be done
2. Identify dependencies between subtasks
3. Assign each subtask to the most appropriate agent type
4. Return a structured plan

Be specific. Vague plans are not useful.
Use read_file and list_directory to understand the codebase before planning."""

_CODING_PROMPT = """\
You are a coding agent specialized in reading, understanding, and analyzing code.

Your strengths:
- Reading and explaining code
- Identifying bugs and issues
- Suggesting improvements
- Understanding architecture and patterns

Use read_file to examine code before making claims about it.
Use search_files to find relevant implementations.
Always verify your understanding by reading the actual code."""

_RETRIEVAL_PROMPT = """\
You are a retrieval agent specialized in finding relevant information.

Your job:
- Search the knowledge base for relevant documents
- Find code examples and documentation
- Retrieve context needed to answer questions

Use retrieve_documents for semantic search over ingested content.
Use search_files for exact text search in the workspace.
Always cite your sources."""

_DEBUGGING_PROMPT = """\
You are a debugging agent specialized in diagnosing and fixing issues.

Your approach:
1. Read the error message carefully
2. Locate the relevant code with read_file and search_files
3. Trace the execution path
4. Identify the root cause
5. Propose a specific fix

Be systematic. Don't guess — verify by reading the code."""

_DEVOPS_PROMPT = """\
You are a DevOps agent specialized in infrastructure, deployment, and operations.

Your expertise:
- Docker and Docker Compose configuration
- CI/CD pipelines
- Environment configuration
- Database migrations
- Service health and monitoring

Use read_file to examine configuration files.
Use list_directory to understand project structure.
Always consider security implications."""

_ORCHESTRATOR_PROMPT = """\
You are the orchestrator agent. You coordinate specialized agents to complete complex tasks.

Your role:
1. Understand the user's request
2. Determine if the task needs delegation to a specialist
3. If simple: answer directly
4. If complex: delegate to the appropriate specialist

Available specialists:
- planner: breaks down complex tasks
- coding: reads and analyzes code
- retrieval: searches knowledge base
- debugging: diagnoses issues
- devops: handles infrastructure

When delegating, use the delegate_to_agent tool with the specialist name and task."""


# ── Agent type registry ───────────────────────────────────────────────────────

AGENT_CONFIGS: dict[AgentRole, AgentTypeConfig] = {
    AgentRole.ORCHESTRATOR: AgentTypeConfig(
        role=AgentRole.ORCHESTRATOR,
        name="Orchestrator",
        description="Coordinates specialized agents for complex tasks",
        system_prompt=_ORCHESTRATOR_PROMPT,
        max_steps=15,
    ),
    AgentRole.PLANNER: AgentTypeConfig(
        role=AgentRole.PLANNER,
        name="Planner",
        description="Breaks down complex tasks into ordered subtasks",
        system_prompt=_PLANNER_PROMPT,
        allowed_tools=["read_file", "list_directory", "search_files"],
        max_steps=8,
    ),
    AgentRole.CODING: AgentTypeConfig(
        role=AgentRole.CODING,
        name="Coding Agent",
        description="Reads, understands, and analyzes code",
        system_prompt=_CODING_PROMPT,
        allowed_tools=["read_file", "list_directory", "search_files"],
        max_steps=10,
    ),
    AgentRole.RETRIEVAL: AgentTypeConfig(
        role=AgentRole.RETRIEVAL,
        name="Retrieval Agent",
        description="Searches knowledge base and finds relevant information",
        system_prompt=_RETRIEVAL_PROMPT,
        allowed_tools=["retrieve_documents", "search_files"],
        max_steps=6,
    ),
    AgentRole.DEBUGGING: AgentTypeConfig(
        role=AgentRole.DEBUGGING,
        name="Debugging Agent",
        description="Diagnoses and fixes issues in code and systems",
        system_prompt=_DEBUGGING_PROMPT,
        allowed_tools=["read_file", "list_directory", "search_files"],
        max_steps=12,
    ),
    AgentRole.DEVOPS: AgentTypeConfig(
        role=AgentRole.DEVOPS,
        name="DevOps Agent",
        description="Handles infrastructure, deployment, and operations",
        system_prompt=_DEVOPS_PROMPT,
        allowed_tools=["read_file", "list_directory", "search_files"],
        max_steps=10,
    ),
}


def get_agent_config(role: AgentRole) -> AgentTypeConfig:
    """Get the configuration for a specific agent role."""
    config = AGENT_CONFIGS.get(role)
    if config is None:
        raise ValueError(f"Unknown agent role: {role}")
    return config
