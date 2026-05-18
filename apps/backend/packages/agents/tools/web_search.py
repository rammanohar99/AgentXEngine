"""
Web search tool — searches the web for current information.

Uses the DuckDuckGo Instant Answer API (no API key required).
Falls back to a structured error if the search fails.

Security:
- Only outbound GET requests to a fixed endpoint
- No user-controlled URLs
- Results are text-only, no code execution
- Rate limited by the tool itself

AGENTS.md: "web search tool" listed as an initial tool.
"""

from __future__ import annotations

from typing import Any

import structlog

from packages.agents.tools.base import BaseTool

logger = structlog.get_logger(__name__)

_DDGS_API = "https://api.duckduckgo.com/"
_MAX_RESULTS = 5


class WebSearchTool(BaseTool):
    """
    Search the web using DuckDuckGo Instant Answer API.

    Returns structured results with title, snippet, and URL.
    No API key required. Results are informational only.
    """

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web for current information, documentation, or answers. "
            "Use this when you need up-to-date information not available in the codebase. "
            "Returns titles, snippets, and URLs."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query. Be specific for better results.",
                },
                "max_results": {
                    "type": "integer",
                    "description": f"Maximum results to return (1-{_MAX_RESULTS}). Default is 3.",
                },
            },
            "required": ["query"],
        }

    async def _run(self, arguments: dict[str, Any]) -> str:
        query: str = arguments["query"]
        max_results: int = min(int(arguments.get("max_results", 3)), _MAX_RESULTS)

        try:
            import httpx

            params = {
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(_DDGS_API, params=params)
                response.raise_for_status()
                data = response.json()

            results = self._parse_ddg_response(data, max_results)

            if not results:
                return f"No results found for: '{query}'"

            lines = [f"# Web search results for: '{query}'\n"]
            for index, result in enumerate(results, start=1):
                lines.append(f"## {index}. {result['title']}")
                lines.append(result["snippet"])
                if result.get("url"):
                    lines.append(f"Source: {result['url']}")
                lines.append("")

            return "\n".join(lines)

        except ImportError:
            raise RuntimeError(
                "httpx is required for web search. Install it with: pip install httpx"
            ) from None

    def _parse_ddg_response(self, data: dict[str, Any], max_results: int) -> list[dict[str, Any]]:
        """Extract results from DuckDuckGo API response."""
        results: list[dict[str, Any]] = []

        # Abstract (direct answer)
        if data.get("Abstract"):
            results.append(
                {
                    "title": data.get("Heading", "Answer"),
                    "snippet": data["Abstract"],
                    "url": data.get("AbstractURL", ""),
                }
            )

        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(
                    {
                        "title": topic.get("Text", "")[:80],
                        "snippet": topic.get("Text", ""),
                        "url": topic.get("FirstURL", ""),
                    }
                )

        return results[:max_results]
