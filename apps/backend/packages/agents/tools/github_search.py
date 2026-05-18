"""
GitHub search tool — searches GitHub repositories, code, and issues.

Uses the GitHub REST API. Works without authentication for public repos
(60 requests/hour). With a GITHUB_TOKEN env variable, gets 5000/hour.

Security:
- Read-only API calls only
- No write operations
- Token loaded from environment, never hardcoded
- Results are text-only

AGENTS.md: "GitHub tool" listed as an initial tool.
"""

from __future__ import annotations

import os
from typing import Any

import structlog

from packages.agents.tools.base import BaseTool

logger = structlog.get_logger(__name__)

_GITHUB_API = "https://api.github.com"
_MAX_RESULTS = 5


class GitHubSearchTool(BaseTool):
    """
    Search GitHub for repositories, code, and issues.

    Supports:
    - Repository search: find repos by topic/language/name
    - Code search: find code snippets across GitHub
    - Issue search: find issues and PRs
    """

    @property
    def name(self) -> str:
        return "github_search"

    @property
    def description(self) -> str:
        return (
            "Search GitHub for repositories, code examples, or issues. "
            "Use this to find open-source implementations, examples, or related projects. "
            "Search types: 'repositories', 'code', 'issues'."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
                "search_type": {
                    "type": "string",
                    "description": "What to search: 'repositories', 'code', or 'issues'. Default is 'repositories'.",
                },
                "max_results": {
                    "type": "integer",
                    "description": f"Maximum results (1-{_MAX_RESULTS}). Default is 3.",
                },
            },
            "required": ["query"],
        }

    def _get_headers(self) -> dict[str, str]:
        """Build request headers, including auth token if available."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _run(self, arguments: dict[str, Any]) -> str:
        query: str = arguments["query"]
        search_type: str = arguments.get("search_type", "repositories").lower()
        max_results: int = min(int(arguments.get("max_results", 3)), _MAX_RESULTS)

        valid_types = {"repositories", "code", "issues"}
        if search_type not in valid_types:
            search_type = "repositories"

        try:
            import httpx

            url = f"{_GITHUB_API}/search/{search_type}"
            params = {"q": query, "per_page": max_results, "sort": "stars"}

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params, headers=self._get_headers())
                response.raise_for_status()
                data = response.json()

            items = data.get("items", [])
            if not items:
                return f"No GitHub {search_type} found for: '{query}'"

            return self._format_results(search_type, query, items[:max_results])

        except ImportError:
            raise RuntimeError("httpx is required for GitHub search.")

    def _format_results(
        self, search_type: str, query: str, items: list[dict[str, Any]]
    ) -> str:
        lines = [f"# GitHub {search_type} results for: '{query}'\n"]

        for index, item in enumerate(items, start=1):
            if search_type == "repositories":
                lines.append(f"## {index}. {item.get('full_name', 'Unknown')}")
                lines.append(item.get("description") or "No description")
                lines.append(f"Stars: {item.get('stargazers_count', 0)} | Language: {item.get('language', 'Unknown')}")
                lines.append(f"URL: {item.get('html_url', '')}")
            elif search_type == "code":
                lines.append(f"## {index}. {item.get('name', 'Unknown')} in {item.get('repository', {}).get('full_name', '')}")
                lines.append(f"Path: {item.get('path', '')}")
                lines.append(f"URL: {item.get('html_url', '')}")
            elif search_type == "issues":
                lines.append(f"## {index}. {item.get('title', 'Unknown')}")
                lines.append(f"State: {item.get('state', '')} | Comments: {item.get('comments', 0)}")
                lines.append(f"URL: {item.get('html_url', '')}")
            lines.append("")

        return "\n".join(lines)
