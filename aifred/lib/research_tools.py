"""Research tools for LLM function calling.

Single research pipeline used by both:
- Forced path (keyword override): Automatik-LLM generates queries
- Tool call path (model decides): Model provides its own queries

Both paths run the same pipeline: Search → Ranking → Scraping → Context → Cache.
"""

import json
import logging
from typing import Any, AsyncGenerator, Optional, TYPE_CHECKING

from .function_calling import Tool

if TYPE_CHECKING:
    from ..state import AIState

logger = logging.getLogger(__name__)


# ============================================================
# Unified Research Pipeline (async generator for progress updates)
# ============================================================

async def execute_research(
    state: 'AIState',
    user_query: str,
    lang: str = "de",
    pre_generated_queries: Optional[list[str]] = None,
    skip_url_ranking: bool = False,
) -> AsyncGenerator[None, None]:
    """Execute the full research pipeline.

    Async generator — yields after state updates so Reflex can push
    progress (scraping progress bar, debug messages) to the browser.

    Single function for both forced path and tool-call path:
    1. Query generation (skipped if pre_generated_queries provided)
    2. Multi-API search (Tavily/Brave/SearXNG)
    3. URL ranking (LLM-based, skipped if skip_url_ranking=True)
    4. Parallel scraping
    5. Context building
    6. Vector cache write (with TTL volatility)

    Results stored in state._research_context and state._research_sources_html.
    """
    from .conversation_handler import generate_search_queries
    from .research.query_processor import process_query_and_search
    from .research.url_ranker import rank_urls_by_relevance
    from .research.scraper_orchestrator import orchestrate_scraping
    from .tools import build_context
    from .formatting import build_sources_collapsible
    from .llm_client import LLMClient
    from .research.context_utils import get_agent_num_ctx
    from .logging_utils import log_message

    # Automatik-LLM for query generation (if needed)
    automatik_model_id = state.automatik_model_id or state._effective_model_id("aifred")
    automatik_num_ctx, _ = get_agent_num_ctx("aifred", state, automatik_model_id)

    llm_client = LLMClient(backend_type=state.backend_type, base_url=state.backend_url)
    if state.backend_type == "ollama":
        automatik_llm_client = LLMClient(backend_type=state.backend_type, base_url=state.backend_url)
    else:
        automatik_llm_client = llm_client

    volatility = "WEEKLY"  # Default, overridden by query generation

    # Init result state
    state._research_context = ""  # type: ignore[attr-defined]
    state._research_sources_html = ""  # type: ignore[attr-defined]

    try:
        # ==============================================================
        # PHASE 0: Vector Cache Duplikat-Check
        # ==============================================================
        try:
            from .vector_cache import get_cache
            import datetime as _dt
            from .formatting import format_age
            cache = get_cache()
            cache_result = await cache.query(user_query, n_results=1)
            distance = cache_result.get('distance', 1.0)

            if cache_result['source'] == 'CACHE' and distance < 0.05:
                cache_time = _dt.datetime.fromisoformat(cache_result['metadata']['timestamp'])
                age_seconds = (_dt.datetime.now() - cache_time).total_seconds()
                age_formatted = format_age(age_seconds)
                state.add_debug(f"✅ Cache hit ({age_formatted} ago, d={distance:.4f})")
                state._research_context = cache_result['answer']  # type: ignore[attr-defined]
                yield
                return
        except Exception as e:
            log_message(f"⚠️ Vector cache check failed: {e}")

        # ==============================================================
        # PHASE 1: Query Generation (skipped if pre_generated_queries)
        # ==============================================================
        if not pre_generated_queries:
            state.add_debug("🔍 Generating search queries...")
            yield
            query_result = await generate_search_queries(
                user_text=user_query,
                automatik_llm_client=automatik_llm_client,
                automatik_model=automatik_model_id,
                detected_language=lang,
                llm_history=state._chat_sub().llm_history[:-1] if len(state._chat_sub().llm_history) > 1 else None,
                automatik_num_ctx=automatik_num_ctx,
            )
            pre_generated_queries = query_result["queries"]
            volatility = query_result.get("volatility", "WEEKLY")
            query_gen_time = query_result["generation_time"]
            state.add_debug(f"✅ {len(pre_generated_queries)} queries ({query_gen_time:.1f}s, TTL={volatility})")
            yield

        # ==============================================================
        # PHASE 2: Multi-API Web Search
        # (process_query_and_search logs the API-labeled queries)
        # ==============================================================
        related_urls: list[str] = []
        titles: list[str] = []
        snippets: list[str] = []
        tool_results: list[dict[str, Any]] = []

        async for item in process_query_and_search(
            user_text=user_query,
            llm_history=state._chat_sub().llm_history,
            automatik_model=automatik_model_id,
            automatik_llm_client=automatik_llm_client,
            llm_options={},
            vision_json_context=None,
            pre_generated_queries=pre_generated_queries,
        ):
            if item["type"] == "query_result":
                _, _, _, related_urls, titles, snippets, tool_results = item["data"]
            elif item["type"] == "debug":
                state.add_debug(item["message"])
                yield

        if not related_urls:
            state.add_debug("⚠️ No URLs found")
            yield
            return

        # ==============================================================
        # PHASE 3: LLM-based URL Ranking (skipped in tool-call path)
        # ==============================================================
        if skip_url_ranking:
            related_urls = related_urls[:7]
            state.add_debug(f"⏭️ URL ranking skipped, using top {len(related_urls)} URLs")
            yield
        elif related_urls and titles and snippets:
            top_n = 7
            state.add_debug(f"🎯 Ranking {len(related_urls)} URLs by relevance...")
            yield

            ranked_urls, _, debug_summary = await rank_urls_by_relevance(
                user_question=user_query,
                urls=related_urls,
                titles=titles,
                snippets=snippets,
                automatik_llm_client=automatik_llm_client,
                automatik_model=automatik_model_id,
                top_n=top_n,
                llm_options={},
                automatik_num_ctx=automatik_num_ctx,
            )
            if debug_summary:
                state.add_debug(f"📋 {debug_summary}")
            related_urls = ranked_urls
            yield

        # ==============================================================
        # PHASE 4: Parallel Web Scraping (with progress bar)
        # ==============================================================
        model_id = state._effective_model_id("aifred")
        failed_sources: list[dict[str, Any]] = []

        async for item in orchestrate_scraping(
            related_urls=related_urls,
            mode="deep",
            llm_client=llm_client,
            model_choice=model_id,
        ):
            if item["type"] == "scraping_result":
                _, scraping_tool_results = item["data"]
                tool_results.extend(scraping_tool_results)
            elif item["type"] == "debug":
                state.add_debug(item["message"])
                yield
            elif item["type"] == "progress":
                state.set_progress(
                    phase=item.get("phase", ""),
                    current=item.get("current", 0),
                    total=item.get("total", 0),
                    failed=item.get("failed", 0),
                )
                yield  # Push progress to browser
            elif item["type"] == "failed_sources":
                failed_sources.extend(item["data"])
                state.add_debug(f"⚠️ {len(item['data'])} source(s) failed")
                yield

        state.clear_progress()
        yield

        # ==============================================================
        # PHASE 5: Build context from scraped content
        # ==============================================================
        if not tool_results:
            state.add_debug("⚠️ No sources available")
            yield
            return

        context = build_context(user_query, tool_results)

        # Sources collapsible for UI
        scraped_only = [r for r in tool_results if r.get("success") and r.get("content")]
        used_sources = [
            {
                "url": src.get("url", ""),
                "word_count": src.get("word_count", 0),
                "rank_index": src.get("rank_index", idx),
                "success": True,
            }
            for idx, src in enumerate(scraped_only)
            if src.get("url")
        ]

        sources_html = build_sources_collapsible(
            used_sources=used_sources,
            failed_sources=failed_sources,
        )

        state.add_debug(f"✅ Research: {len(context)} chars, {len(used_sources)} sources")
        state._research_context = context  # type: ignore[attr-defined]
        state._research_sources_html = sources_html  # type: ignore[attr-defined]

        # ==============================================================
        # PHASE 6: Vector Cache Write (with TTL volatility)
        # ==============================================================
        try:
            from .vector_cache import get_cache
            cache = get_cache()
            await cache.add(
                query=user_query,
                answer=context,
                sources=scraped_only,
                failed_sources=failed_sources,
                metadata={"volatility": volatility},
            )
            state.add_debug(f"💾 Cached ({len(scraped_only)} sources, TTL={volatility})")
        except Exception as e:
            log_message(f"⚠️ Vector cache write failed: {e}")

        yield

    finally:
        await llm_client.close()
        if state.backend_type == "ollama":
            await automatik_llm_client.close()


# ============================================================
# Tool Definitions (for LLM function calling)
# ============================================================

def get_research_tools(state: Optional['AIState'] = None, lang: str = "de") -> list[Tool]:
    """Create research tools bound to a specific state instance.

    The web_search tool runs the full pipeline (search + scraping).
    """

    async def _execute_web_search(queries: list[str]) -> str:
        """Tool executor: runs full research pipeline with model-provided queries."""
        if not state:
            return json.dumps({"error": "No state available for research"})
        if not queries:
            return json.dumps({"error": "No search queries provided"})

        queries = queries[:3]

        # Run pipeline as generator, consume all yields (no Reflex push needed here)
        async for _ in execute_research(
            state=state,
            user_query=queries[0],  # First query as cache key
            lang=lang,
            pre_generated_queries=queries,
            skip_url_ranking=True,  # Avoid LLM recursion
        ):
            pass  # Consume yields (progress updates set on state directly)

        result = getattr(state, "_research_context", "")
        return result if result else json.dumps({"error": "No results found"})

    return [
        Tool(
            name="web_search",
            description=(
                "Search the web for current, verified information. You MUST use this tool when: "
                "(1) the user asks about specific products, software, models, versions, or releases, "
                "(2) the user asks about events, news, or anything time-sensitive, "
                "(3) the user asks about specific people, companies, or organizations, "
                "(4) you are not 100% certain your knowledge is accurate and up-to-date. "
                "Do NOT answer from memory when web search would give a better, verified answer. "
                "Provide 1-3 search queries optimized for web search engines."
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
        ),
    ]
