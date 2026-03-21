"""Research tools for LLM function calling.

Wraps the existing search/scrape infrastructure as OpenAI-compatible tools
that any agent can invoke autonomously via the ToolKit system.

Both the tool-call path (Automatik mode) and the forced path (quick/deep)
use the same underlying functions — no code duplication.
"""

import json
import logging

from .function_calling import Tool
from .tools.registry import search_web_multi, scrape_webpage

logger = logging.getLogger(__name__)


# ============================================================
# Tool Executor Functions
# ============================================================

async def _execute_web_search(queries: list[str]) -> str:
    """Execute web search using existing multi-API infrastructure.

    Wraps search_web_multi() which distributes queries across
    Tavily, Brave, and SearXNG in parallel.
    """
    if not queries:
        return json.dumps({"error": "No search queries provided"})

    # Limit to 3 queries (one per search API)
    queries = queries[:3]

    logger.info(f"🔧 web_search tool: {queries}")
    result = search_web_multi(queries)

    if not result.get("success"):
        return json.dumps({"error": "Search failed", "details": result.get("error", "unknown")})

    # Build concise response for the model
    urls = result.get("related_urls", [])
    titles = result.get("titles", [])
    snippets = result.get("snippets", [])

    search_results = []
    for i, url in enumerate(urls[:10]):  # Max 10 results
        entry: dict[str, str] = {"url": url}
        if i < len(titles) and titles[i]:
            entry["title"] = titles[i]
        if i < len(snippets) and snippets[i]:
            entry["snippet"] = snippets[i]
        search_results.append(entry)

    return json.dumps({
        "results": search_results,
        "total_urls": len(urls),
    }, ensure_ascii=False)


async def _execute_read_webpage(url: str) -> str:
    """Scrape a webpage using existing scraper infrastructure.

    Wraps scrape_webpage() which uses trafilatura + Playwright fallback.
    """
    if not url:
        return json.dumps({"error": "No URL provided"})

    logger.info(f"🔧 read_webpage tool: {url}")
    result = scrape_webpage(url)

    if not result.get("success"):
        return json.dumps({"error": f"Failed to scrape {url}", "details": result.get("error", "unknown")})

    content = result.get("content", "")

    # Truncate very long content to avoid context overflow
    max_chars = 15000
    if len(content) > max_chars:
        content = content[:max_chars] + "\n\n[... content truncated]"

    return json.dumps({
        "url": url,
        "title": result.get("title", ""),
        "content": content,
    }, ensure_ascii=False)


# ============================================================
# Tool Definitions
# ============================================================

WEB_SEARCH_TOOL = Tool(
    name="web_search",
    description=(
        "Search the web for current information. Use this when the user asks about "
        "recent events, facts you're unsure about, or anything that requires up-to-date "
        "information. Provide 1-3 search queries optimized for web search engines."
    ),
    parameters={
        "type": "object",
        "properties": {
            "queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "1-3 search queries (each sent to a different search engine)",
                "minItems": 1,
                "maxItems": 3,
            },
        },
        "required": ["queries"],
    },
    executor=_execute_web_search,
)

READ_WEBPAGE_TOOL = Tool(
    name="read_webpage",
    description=(
        "Read the full content of a webpage by URL. Use this after web_search to read "
        "specific pages from the search results, or when the user provides a URL directly."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to read",
            },
        },
        "required": ["url"],
    },
    executor=_execute_read_webpage,
)


def get_research_tools() -> list[Tool]:
    """Return the list of research tools for agent toolkits."""
    return [WEB_SEARCH_TOOL, READ_WEBPAGE_TOOL]
