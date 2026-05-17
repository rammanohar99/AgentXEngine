"""
Database query tool — safe read-only SQL queries against the application database.

Security model:
- SELECT queries only — no INSERT, UPDATE, DELETE, DROP, etc.
- Query is validated before execution
- Results are truncated to prevent huge outputs
- Uses the existing async database session

AGENTS.md: "database tool" listed as an initial tool.
Never allow unsafe unrestricted execution.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from packages.agents.tools.base import BaseTool

logger = structlog.get_logger(__name__)

_MAX_ROWS = 50
_BLOCKED_KEYWORDS = frozenset([
    "insert", "update", "delete", "drop", "truncate", "alter",
    "create", "grant", "revoke", "exec", "execute", "call",
])


def _is_safe_query(sql: str) -> tuple[bool, str]:
    """
    Validate that a SQL query is safe to execute.

    Returns (is_safe, reason).
    Only SELECT statements are allowed.
    """
    normalized = sql.strip().lower()

    if not normalized.startswith("select"):
        return False, "Only SELECT queries are allowed."

    for keyword in _BLOCKED_KEYWORDS:
        # Check for keyword as a whole word
        if re.search(rf"\b{keyword}\b", normalized):
            return False, f"Blocked keyword detected: '{keyword}'"

    return True, ""


class DatabaseQueryTool(BaseTool):
    """
    Execute read-only SQL queries against the application database.

    Only SELECT statements are permitted.
    Results are limited to 50 rows.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    @property
    def name(self) -> str:
        return "database_query"

    @property
    def description(self) -> str:
        return (
            "Execute a read-only SQL SELECT query against the application database. "
            "Use this to inspect data, check document counts, or query stored information. "
            "Only SELECT statements are allowed. Results are limited to 50 rows."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A SQL SELECT query to execute. Must start with SELECT.",
                },
            },
            "required": ["sql"],
        }

    async def _run(self, arguments: dict[str, Any]) -> str:
        sql: str = arguments["sql"].strip()

        # Validate before executing
        is_safe, reason = _is_safe_query(sql)
        if not is_safe:
            raise ValueError(f"Query rejected: {reason}")

        try:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine

            engine = create_async_engine(self._database_url, echo=False)

            async with engine.connect() as conn:
                result = await conn.execute(text(sql))
                rows = result.fetchmany(_MAX_ROWS)
                columns = list(result.keys())

            await engine.dispose()

            if not rows:
                return f"Query returned no rows.\nSQL: {sql}"

            # Format as a simple table
            lines = [f"# Query results ({len(rows)} rows)\n"]
            lines.append("| " + " | ".join(columns) + " |")
            lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
            for row in rows:
                row_values = [str(v)[:50] if v is not None else "NULL" for v in row]
                lines.append("| " + " | ".join(row_values) + " |")

            if len(rows) == _MAX_ROWS:
                lines.append(f"\n_(Results truncated at {_MAX_ROWS} rows)_")

            return "\n".join(lines)

        except Exception as exc:
            raise RuntimeError(f"Query failed: {exc}") from exc
