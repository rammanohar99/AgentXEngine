"""
Tool Registry — central catalog of all available tools.

Design:
- Tools are registered by name at startup
- The registry is the single source of truth for tool lookup
- The runtime asks the registry for tool descriptions (for prompts)
  and for tool instances (for execution)
- Adding a new tool = implement BaseTool + call registry.register()

The registry is a plain class, not a singleton — it's instantiated
once in the runtime and injected where needed.
"""

from __future__ import annotations

from packages.agents.tools.base import BaseTool
from packages.agents.tools.filesystem import (
    ListDirectoryTool,
    ReadFileTool,
    SearchFilesTool,
)


class ToolRegistry:
    """
    Holds all registered tools and provides lookup + description generation.

    Usage:
        registry = ToolRegistry.with_defaults()
        tool = registry.get("read_file")
        descriptions = registry.get_prompt_descriptions()
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool. Raises if a tool with the same name already exists."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Look up a tool by name. Returns None if not found."""
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())

    def get_prompt_descriptions(self) -> str:
        """
        Render all tools as a formatted block for injection into the system prompt.

        Example output:
            Tool: read_file
            Description: Read the contents of a file...
            Parameters:
              - path (string, required): ...

            Tool: list_directory
            ...
        """
        if not self._tools:
            return "No tools available."
        return "\n\n".join(tool.to_prompt_description() for tool in self._tools.values())

    @classmethod
    def with_defaults(cls) -> "ToolRegistry":
        """
        Create a registry pre-loaded with the full default tool set.

        Filesystem tools: read_file, list_directory, search_files
        Search tools: web_search, github_search
        Terminal: terminal (allowlisted commands only)
        """
        from packages.agents.tools.github_search import GitHubSearchTool
        from packages.agents.tools.terminal import TerminalTool
        from packages.agents.tools.web_search import WebSearchTool

        registry = cls()
        registry.register(ReadFileTool())
        registry.register(ListDirectoryTool())
        registry.register(SearchFilesTool())
        registry.register(WebSearchTool())
        registry.register(GitHubSearchTool())
        registry.register(TerminalTool())
        return registry

    @classmethod
    def with_database(cls, database_url: str) -> "ToolRegistry":
        """
        Create a registry that includes the database query tool.

        Used when the agent needs to inspect application data.
        """
        from packages.agents.tools.database_query import DatabaseQueryTool

        registry = cls.with_defaults()
        registry.register(DatabaseQueryTool(database_url=database_url))
        return registry
