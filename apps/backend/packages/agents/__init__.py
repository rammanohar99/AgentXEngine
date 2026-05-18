"""
packages.agents — ReAct agent runtime.

Lazy imports only — this package must be importable without
the full FastAPI app stack installed.

Public surface (import explicitly from submodules):
    from packages.agents.schemas import AgentEvent, AgentEventType, ...
    from packages.agents.runtime import AgentRuntime
    from packages.agents.tool_registry import ToolRegistry
"""
