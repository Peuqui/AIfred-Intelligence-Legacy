"""
Research Orchestrator - Top-Level Research Pipeline Coordination

This module contains the main research orchestration function that coordinates
all research pipeline modules (cache_handler, query_processor, scraper_orchestrator, context_builder).
"""

import time
from typing import Dict, List, Optional, AsyncIterator

from ..llm_client import LLMClient
from .cache_handler import handle_cache_hit
from .query_processor import process_query_and_search
from .scraper_orchestrator import orchestrate_scraping
from .context_builder import build_and_generate_response


async def perform_agent_research(
    user_text: str,
    stt_time: float,
    mode: str,
    model_choice: str,
    automatik_model: str,
    history: List,
    session_id: Optional[str] = None,
    temperature_mode: str = 'auto',
    temperature: float = 0.2,
    llm_options: Optional[Dict] = None,
    backend_type: str = "ollama",
    backend_url: Optional[str] = None,
    num_ctx_mode: str = "auto",
    num_ctx_manual: int = 16384,
    vision_json_context: Optional[dict] = None,
    user_name: Optional[str] = None,
    detected_intent: Optional[str] = None,
    detected_language: Optional[str] = None
) -> AsyncIterator[Dict]:
    """
    Agent research with query optimization and parallel web scraping

    REFACTORED: This function is now a lean orchestrator that delegates
    the actual work to specialized modules:
    - cache_handler: Cache hit handling
    - query_processor: Query optimization + web search
    - scraper_orchestrator: Parallel web scraping
    - context_builder: Context building + LLM inference

    Args:
        user_text: User question
        stt_time: STT time
        mode: "quick" or "deep"
        model_choice: Main LLM for final answer
        automatik_model: Automatik LLM for query optimization
        llm_options: Dict with Ollama options (num_ctx, etc.) - Optional
        history: Chat history
        session_id: Session ID for research cache (optional)
        temperature_mode: 'auto' (intent detection) or 'manual' (fixed value)
        temperature: Temperature value (0.0-2.0) - only for mode='manual'
        backend_type: LLM Backend ("ollama", "vllm", "tabbyapi")
        backend_url: Backend URL (optional, uses default if not provided)
        detected_intent: Pre-detected intent from state.py (FAKTISCH/KREATIV/GEMISCHT)
                        If provided, skips duplicate intent detection in context_builder
        detected_language: Pre-detected language from state.py ("de" or "en")
                          If provided, skips regex-based language detection

    Yields:
        Dict with: {"type": "debug"|"content"|"result", ...}
    """

    agent_start = time.time()

    # Initialize LLM clients with correct backend
    llm_client = LLMClient(backend_type=backend_type, base_url=backend_url)

    # Only Ollama supports model switching - other backends reuse same client
    if backend_type == 'ollama':
        automatik_llm_client = LLMClient(backend_type=backend_type, base_url=backend_url)
    else:
        # KoboldCPP, vLLM, TabbyAPI: Same model, same client (no model switching)
        automatik_llm_client = llm_client

    # ==============================================================
    # PHASE 1: Cache-Hit Check
    # ==============================================================
    cache_handled = False
    async for item in handle_cache_hit(
        session_id=session_id,
        user_text=user_text,
        history=history,
        model_choice=model_choice,
        automatik_model=automatik_model,
        llm_client=llm_client,
        automatik_llm_client=automatik_llm_client,
        llm_options=llm_options,
        temperature_mode=temperature_mode,
        temperature=temperature,
        agent_start=agent_start,
        num_ctx_mode=num_ctx_mode,
        num_ctx_manual=num_ctx_manual,
        user_name=user_name
    ):
        if item["type"] == "result":
            cache_handled = True
        yield item

    if cache_handled:
        # Cache hit handled everything - we're done
        await llm_client.close()
        # Only close automatik_llm_client if it's a separate instance (Ollama)
        if backend_type == 'ollama':
            await automatik_llm_client.close()
        return

    # ==============================================================
    # PHASE 2: Query Optimization + Web Search
    # ==============================================================
    optimized_query = None
    query_reasoning = None
    query_opt_time = 0.0
    related_urls = []
    tool_results = []

    async for item in process_query_and_search(
        user_text=user_text,
        history=history,
        automatik_model=automatik_model,
        automatik_llm_client=automatik_llm_client,
        llm_options=llm_options,
        vision_json_context=vision_json_context
    ):
        if item["type"] == "query_result":
            optimized_query, query_reasoning, query_opt_time, related_urls, tool_results = item["data"]
        else:
            yield item

    # ==============================================================
    # PHASE 3: Parallel Web Scraping
    # ==============================================================
    scraped_results = []
    failed_sources = []  # Collect failed URLs for cache storage

    async for item in orchestrate_scraping(
        related_urls=related_urls,
        mode=mode,
        llm_client=llm_client,
        model_choice=model_choice
    ):
        if item["type"] == "scraping_result":
            scraped_results, scraping_tool_results = item["data"]
            tool_results.extend(scraping_tool_results)
        elif item["type"] == "failed_sources":
            failed_sources.extend(item["data"])  # Collect failed sources
            yield item  # Still pass through to UI
        else:
            yield item

    # ==============================================================
    # PHASE 3.5: Fallback to Web-Search if Scraping Failed (0 Sources)
    # ==============================================================
    from ..agent_tools import search_web
    from ..logging_utils import log_message

    if len(scraped_results) == 0 and related_urls:
        # All scraping attempts failed (Cloudflare, 404, Timeout, etc.)
        # Fallback: Use optimized query for web search
        yield {"type": "debug", "message": "⚠️ Scraping failed (0 sources) → Fallback to web search"}
        log_message("=" * 60)
        log_message("⚠️ FALLBACK: Scraping failed (0 sources) → Web-Search")
        log_message("=" * 60)

        # Show optimized query being used for fallback
        yield {"type": "debug", "message": f"🔎 Fallback query: {optimized_query}"}
        log_message(f"🔎 Fallback query: {optimized_query}")

        # Use optimized query for fallback search
        fallback_search = search_web(optimized_query)
        tool_results.append(fallback_search)

        # Get new URLs from fallback search
        fallback_urls = fallback_search.get('related_urls', [])

        if fallback_urls:
            yield {"type": "debug", "message": f"🔄 {len(fallback_urls)} URLs found from fallback search"}
            log_message(f"🔄 Fallback search: {len(fallback_urls)} URLs found")

            # Retry scraping with new URLs
            async for item in orchestrate_scraping(
                related_urls=fallback_urls,
                mode=mode,
                llm_client=llm_client,
                model_choice=model_choice
            ):
                if item["type"] == "scraping_result":
                    scraped_results, scraping_tool_results = item["data"]
                    tool_results.extend(scraping_tool_results)
                elif item["type"] == "failed_sources":
                    failed_sources.extend(item["data"])  # Also collect from fallback
                    yield item
                else:
                    yield item

            if scraped_results:
                yield {"type": "debug", "message": f"✅ Fallback successful: {len(scraped_results)} sources"}
                log_message(f"✅ Fallback successful: {len(scraped_results)} sources scraped")
            else:
                yield {"type": "debug", "message": "⚠️ Fallback failed: No sources"}
                log_message("⚠️ Fallback also failed")
        else:
            yield {"type": "debug", "message": "⚠️ Fallback search: No URLs found"}
            log_message("⚠️ Fallback search: No URLs found")

    # ==============================================================
    # PHASE 4: Context Building + LLM Response Generation
    # ==============================================================
    async for item in build_and_generate_response(
        user_text=user_text,
        scraped_results=scraped_results,
        tool_results=tool_results,
        failed_sources=failed_sources,  # Pass failed URLs for cache storage
        history=history,
        session_id=session_id,
        mode=mode,
        model_choice=model_choice,
        automatik_model=automatik_model,
        query_reasoning=query_reasoning,
        query_opt_time=query_opt_time,
        llm_client=llm_client,
        automatik_llm_client=automatik_llm_client,
        llm_options=llm_options,
        temperature_mode=temperature_mode,
        temperature=temperature,
        agent_start=agent_start,
        stt_time=stt_time,
        num_ctx_mode=num_ctx_mode,
        num_ctx_manual=num_ctx_manual,
        user_name=user_name,
        detected_intent=detected_intent,
        detected_language=detected_language
    ):
        yield item

    # Cleanup
    await llm_client.close()
    # Only close automatik_llm_client if it's a separate instance (Ollama)
    if backend_type == 'ollama':
        await automatik_llm_client.close()
