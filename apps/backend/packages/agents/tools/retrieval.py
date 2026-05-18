"""
Retrieval tool — gives the agent access to the RAG knowledge base.

The agent calls this tool when it needs to look up information from
ingested documents, repositories, or documentation.

Design:
- The tool accepts a callable retriever (injected at construction time)
- This keeps the tool decoupled from the database and embedding service
- The retriever is provided by the backend's RAGService
- Tests can inject a mock retriever

Tool contract:
  Input:  { "query": "...", "top_k": 5 }
  Output: Formatted string of ranked document excerpts with sources
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from packages.agents.tools.base import BaseTool

# Type alias for the retriever callable
# Takes (query: str, top_k: int) → list of result dicts
RetrieverFn = Callable[[str, int], Awaitable[list[dict[str, Any]]]]


class RetrieveDocumentsTool(BaseTool):
    """
    Semantic search over the RAG knowledge base.

    Injected with a retriever callable so it stays decoupled from
    the database and embedding infrastructure.
    """

    def __init__(self, retriever: RetrieverFn) -> None:
        self._retriever = retriever

    @property
    def name(self) -> str:
        return "retrieve_documents"

    @property
    def description(self) -> str:
        return (
            "Search the knowledge base for relevant documents, code, or documentation. "
            "Use this when you need to look up information from ingested repositories, "
            "files, or documentation. Returns ranked excerpts with source references."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query. Be specific and descriptive.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (1-10). Default is 5.",
                },
            },
            "required": ["query"],
        }

    async def _run(self, arguments: dict[str, Any]) -> str:
        # Handle the case where the LLM wraps arguments as a JSON string
        # inside an "input" key: {"input": "{'query': '...', 'top_k': 5}"}
        if "input" in arguments and "query" not in arguments:
            import json

            raw = arguments["input"]
            try:
                # Try JSON parse first, then Python literal eval as fallback
                arguments = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                try:
                    import ast

                    arguments = ast.literal_eval(str(raw))
                except Exception:
                    return f'Invalid tool arguments. Expected {{"query": "..."}}, got: {raw}'

        query: str = arguments["query"]
        top_k: int = int(arguments.get("top_k", 5))
        top_k = max(1, min(top_k, 10))  # Clamp to safe range

        results = await self._retriever(query, top_k)

        if not results:
            return f"No relevant documents found for query: '{query}'"

        lines = [f"# Search results for: '{query}'\n"]
        for index, result in enumerate(results, start=1):
            source = result.get("source") or result.get("document_id", "unknown")
            score = result.get("score", 0.0)
            text = result.get("text", "")
            lines.append(f"## Result {index} — {source} (score: {score:.3f})")
            lines.append(text)
            lines.append("")

        return "\n".join(lines)
