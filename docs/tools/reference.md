---
title: Tool Reference
domain: tools
doc_type: reference
status: active
owner: agent-runtime
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [tools, filesystem, web-search, database, delegation, security, basetool]
---

# Tool Reference

**Related:** [Agent Runtime](../architecture/agent-runtime.md) · [Architecture Overview](../architecture/overview.md) · [Invariants](../architecture/invariants.md)

All tools implement `BaseTool` from `packages/agents/tools/base.py`.

---

## BaseTool Contract

Every tool must implement:

```python
class BaseTool:
    name: str                    # Unique identifier used in LLM prompts
    description: str             # Human-readable description for LLM
    parameters_schema: dict      # JSON Schema for input validation

    async def _run(self, **kwargs) -> Any:
        """Tool-specific implementation."""
        ...

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        """Wraps _run() with timing, logging, and exception handling.
        BaseTool.execute() catches ALL exceptions.
        Tools NEVER crash the runtime.
        """
        ...
```

The base class wraps all exceptions into `ToolResult(success=False)`.
This is the contract: tools return results, they do not raise exceptions.

---

## Filesystem Tools

### read_file

Read the contents of a file within the workspace.

| Parameter | Type | Required | Description |
|---|---|---|---|
| path | string | yes | File path relative to workspace root |
| start_line | integer | no | First line to read (1-indexed) |
| end_line | integer | no | Last line to read (1-indexed) |

### list_directory

List files and directories at a path.

| Parameter | Type | Required | Description |
|---|---|---|---|
| path | string | yes | Directory path relative to workspace root |
| depth | integer | no | Recursion depth (1-5, default 1) |

### search_files

Search for text patterns across files.

| Parameter | Type | Required | Description |
|---|---|---|---|
| pattern | string | yes | Text to search for (case-insensitive) |
| directory | string | no | Directory to search in (default: `.`) |
| file_pattern | string | no | Glob filter e.g. `*.py` (default: `*`) |

**Security:** All filesystem tools are sandboxed to the workspace root.
Path traversal is blocked at the tool level.

```python
resolved = (workspace_root / path).resolve()
if not resolved.is_relative_to(workspace_root):
    raise SecurityError("Path traversal detected")
```

---

## Search Tools

### web_search

Search the web using DuckDuckGo.

| Parameter | Type | Required | Description |
|---|---|---|---|
| query | string | yes | Search query |
| max_results | integer | no | Results to return (1-5, default 3) |

**Security:** Rate limited. No credential exposure in results.

### github_search

Search GitHub repositories, code, and issues.

| Parameter | Type | Required | Description |
|---|---|---|---|
| query | string | yes | Search query |
| search_type | string | no | `repositories`, `code`, or `issues` (default: `repositories`) |
| max_results | integer | no | Results to return (1-5, default 3) |

Set `GITHUB_TOKEN` env variable for higher rate limits (5,000/hour vs 60/hour).

---

## Knowledge Base Tools

### retrieve_documents

Semantic search over ingested documents.

| Parameter | Type | Required | Description |
|---|---|---|---|
| query | string | yes | Search query |
| top_k | integer | no | Results to return (1-10, default 5) |

### database_query

Read-only SQL queries against the application database.

| Parameter | Type | Required | Description |
|---|---|---|---|
| sql | string | yes | SELECT query to execute |

**Security:** Only SELECT statements are permitted. Results limited to 50 rows.
DML/DDL is blocked:

```python
BLOCKED_KEYWORDS = {"INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "EXEC"}
```

---

## Multi-Agent Tools

### delegate_to_agent

Delegate a task to a specialist agent. Available to the orchestrator only.

| Parameter | Type | Required | Description |
|---|---|---|---|
| agent | string | yes | Specialist: `planner`, `coding`, `retrieval`, `debugging`, `devops` |
| task | string | yes | Task description for the specialist |

**Constraint:** Max delegation depth is 1. Specialists cannot delegate further.
This prevents infinite delegation loops.

---

## Security Boundaries Summary

| Tool Category | Restriction |
|---|---|
| Filesystem | Sandboxed to workspace root, path traversal blocked |
| Terminal | Explicit allowlist only, dangerous commands blocked |
| Database | SELECT only, DML/DDL blocked, 50-row limit |
| Web search | Rate limited, no credential exposure |

Terminal allowlist:
```python
ALLOWED_COMMANDS = {"git", "python", "pytest", "ruff", "black", "mypy", "echo"}
BLOCKED_GIT_SUBCOMMANDS = {"push", "commit", "reset", "force", "delete"}
```

---

## Adding a New Tool

1. Create `packages/agents/tools/my_tool.py`
2. Subclass `BaseTool`
3. Implement `name`, `description`, `parameters_schema`, `_run()`
4. Register in `ToolRegistry.with_defaults()` or inject at runtime
5. Add tests in `apps/backend/tests/test_tools.py`
6. Document here

**Checklist for new tools:**
- [ ] No shared mutable state
- [ ] Typed input schema (Pydantic or JSON Schema)
- [ ] All exceptions caught in `_run()` or handled by `BaseTool.execute()`
- [ ] Returns structured `ToolResult` with `success`, `output`, `metadata`
- [ ] Output is machine-readable
- [ ] Security boundaries enforced (sandboxing, allowlists, rate limits)
- [ ] `duration_ms` included in metadata
