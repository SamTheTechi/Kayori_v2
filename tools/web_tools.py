from __future__ import annotations

from typing import Any

import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import BaseTool, Tool
from pydantic import BaseModel

from shared_types.tool_schemas import WebExtractToolArgs, WebSearchToolArgs


_DDGS_AVAILABLE: bool = False
try:
    from ddgs import DDGS
    _DDGS_AVAILABLE = True
except ImportError:
    pass


def _ddgs_search(query: str, limit: int = 5) -> list[dict[str, str]]:
    if not _DDGS_AVAILABLE:
        return []
    try:
        with DDGS() as ddgs:
            results = []
            for r in ddgs.text(query, max_results=limit):
                results.append({
                    "title": str(r.get("title", "")),
                    "url": str(r.get("href", "")),
                    "snippet": str(r.get("body", "")),
                })
            return results
    except Exception:
        return []


async def _extract_text(url: str, timeout: float = 15.0) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
    except httpx.HTTPError as e:
        return f"Error fetching {url}: {e}"

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:200])


class WebSearchTool(BaseTool):
    name: str = "web_search"
    description: str = "Search the web and return relevant results."
    args_schema: type[BaseModel] = WebSearchToolArgs

    async def _arun(self, query: str, limit: int = 5, **kwargs: Any) -> str:
        results = _ddgs_search(query, limit)
        if not results:
            return 'Web search is unavailable (duckduckgo_search not installed).'
        lines = [f"{i+1}. [{r['title']}]({r['url']})\n   {r['snippet']}" for i, r in enumerate(results)]
        return "\n\n".join(lines)

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError("Use async execution for web_search.")


class WebExtractTool(BaseTool):
    name: str = "web_extract"
    description: str = "Extract clean text content from a URL."
    args_schema: type[BaseModel] = WebExtractToolArgs

    async def _arun(self, url: str, **kwargs: Any) -> str:
        text = await _extract_text(url)
        return text

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError("Use async execution for web_extract.")


from tools import registry  # noqa: E402

registry.register(
    "web_search",
    description="Search the web and return relevant results.",
    toolset="search",
    factory=lambda **kw: [WebSearchTool()] if _DDGS_AVAILABLE else [],
)

registry.register(
    "web_extract",
    description="Extract clean text content from a URL.",
    toolset="search",
    factory=lambda **kw: [WebExtractTool()],
)
