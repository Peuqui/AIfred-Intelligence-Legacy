# Web Research Plugin

**File:** `aifred/plugins/tools/research.py`

Multi-API web search with automatic scraping and semantic caching.

## Tools

| Tool | Description | Tier |
|------|------------|------|
| `web_search` | Web search via configured search API | READONLY |
| `web_fetch` | Fetch URL and extract content | READONLY |

## Features

- **Multi-API:** Brave Search, Tavily, SearXNG — configurable per backend
- **Automatic scraping + ranking:** Search results are fetched and ranked by relevance
- **Semantic vector cache:** Results are cached in ChromaDB, repeated queries use the cache
- **Content extraction:** HTML is converted to readable text

## Configuration

- Search API configured via `.env` (API keys for Brave/Tavily)
- SearXNG as self-hosted alternative without API key
- ChromaDB collection `research_cache` for the vector cache
