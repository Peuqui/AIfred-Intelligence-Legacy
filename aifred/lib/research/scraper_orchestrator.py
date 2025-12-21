"""
Scraper Orchestrator - Parallel web scraping coordination

Handles:
- Scraping strategy based on mode (quick/deep)
- Parallel scraping with ThreadPoolExecutor
- Progress reporting
- LLM preloading during scraping
"""

import asyncio
from typing import Dict, List, AsyncIterator
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..agent_tools import scrape_webpage
from ..logging_utils import log_message


async def orchestrate_scraping(
    related_urls: List[str],
    mode: str,
    llm_client,
    model_choice: str
) -> AsyncIterator[Dict]:
    """
    Orchestrate parallel web scraping

    Args:
        related_urls: List of URLs to scrape
        mode: Scraping mode ('quick' or 'deep')
        llm_client: Main LLM client (for preloading)
        model_choice: Main LLM model name

    Yields:
        Dict: Progress updates, debug messages, scraping results

    Returns (via last yield):
        Tuple[List[Dict], List[Dict]]: (scraped_results, tool_results)
    """
    scraped_results: List[Dict] = []
    tool_results: List[Dict] = []

    if not related_urls:
        log_message("⚠️ No URLs found, only abstract")
        yield {"type": "scraping_result", "data": (scraped_results, tool_results)}
        return

    log_message(f"📋 {len(related_urls)} URLs found from search engine")

    # Determine scraping strategy
    if mode == "quick":
        target_sources = 3
        initial_scrape_count = 3
        log_message("⚡ Quick mode: Scrape top 3 URLs")
    elif mode == "deep":
        target_sources = 5
        initial_scrape_count = 7
        log_message(f"🔍 Deep mode: Scrape top {initial_scrape_count} URLs (target: {target_sources} successful)")
    else:
        target_sources = 3
        initial_scrape_count = 3

    scrape_limit = initial_scrape_count if mode == "deep" else target_sources
    urls_to_scrape = related_urls[:scrape_limit]

    yield {"type": "debug", "message": "🌐 Web scraping starting (parallel)"}

    # PERFORMANCE: Preload Main LLM during scraping (only for backends that need it)
    # vLLM, TabbyAPI and KoboldCPP keep models loaded in VRAM, so preloading is unnecessary
    needs_preload = llm_client.backend_type not in ["vllm", "tabbyapi", "koboldcpp"]
    preload_task = None
    preload_message_sent = False
    unloaded_models = []

    if needs_preload:
        # STEP 1: Unload all models (e.g., Automatik-LLM from decision) - parallel with scraping
        backend = llm_client._get_backend()

        async def unload_and_preload():
            """Preload main LLM (unload disabled - Ollama manages VRAM automatically)"""
            # unload_success, models = await backend.unload_all_models()  # DISABLED
            success, load_time = await backend.preload_model(model_choice)
            return (success, load_time, [])

        preload_task = asyncio.create_task(unload_and_preload())
        log_message(f"🚀 Main-LLM ({model_choice}) preloading in parallel...")
        yield {"type": "debug", "message": f"🚀 Main-LLM ({model_choice}) preloading..."}
    else:
        log_message(f"ℹ️ Main-LLM ({model_choice}) already loaded (Backend: {llm_client.backend_type})")
        yield {"type": "debug", "message": f"ℹ️ Main-LLM ({model_choice}) already loaded"}
        preload_message_sent = True  # Skip preload messages

    # Parallel Scraping
    log_message(f"🚀 Parallel Scraping: {len(urls_to_scrape)} URLs simultaneously")

    # Start scraping progress
    yield {"type": "progress", "phase": "scraping", "current": 0, "total": len(urls_to_scrape), "failed": 0}

    # Parallel execution
    with ThreadPoolExecutor(max_workers=min(5, len(urls_to_scrape))) as executor:
        future_to_url = {
            executor.submit(scrape_webpage, url): url
            for url in urls_to_scrape
        }

        # Collect results as they complete
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            url_short = url[:60] + '...' if len(url) > 60 else url

            try:
                scrape_result = future.result(timeout=10)

                if scrape_result['success']:
                    tool_results.append(scrape_result)
                    scraped_results.append(scrape_result)
                    log_message(f"  ✅ {url_short}: {scrape_result['word_count']} words")
                else:
                    log_message(f"  ❌ {url_short}: {scrape_result.get('error', 'Unknown')}")

            except Exception as e:
                log_message(f"  ❌ {url_short}: Exception: {e}")

            # Check if preload finished and send message immediately
            if not preload_message_sent and preload_task and preload_task.done():
                try:
                    success, load_time, unloaded_models = preload_task.result()

                    # Show unloaded models first
                    if unloaded_models:
                        models_str = ", ".join(unloaded_models)
                        yield {"type": "debug", "message": f"🗑️ Unloaded models: {models_str}"}
                        log_message(f"🗑️ Unloaded models: {models_str}")

                    # Then show preload result
                    if success:
                        log_message(f"✅ Main-LLM preloaded ({load_time:.1f}s)")
                        yield {"type": "debug", "message": f"✅ Main-LLM preloaded ({load_time:.1f}s)"}
                    else:
                        log_message(f"⚠️ Main-LLM preload failed ({load_time:.1f}s)")
                        yield {"type": "debug", "message": f"⚠️ Main-LLM preload failed ({load_time:.1f}s)"}
                    preload_message_sent = True
                except Exception as e:
                    log_message(f"⚠️ Main-LLM preload exception: {e}")
                    preload_message_sent = True

            # Update progress
            completed = len([f for f in future_to_url if f.done()])
            failed = completed - len(scraped_results)
            yield {"type": "progress", "phase": "scraping", "current": len(scraped_results), "total": len(urls_to_scrape), "failed": failed}

    log_message(f"✅ Parallel Scraping done: {len(scraped_results)}/{len(urls_to_scrape)} successful")

    # ============================================================
    # COLLECT FAILED URLs for UI Display
    # ============================================================
    failed_sources = []
    for future in future_to_url:
        url = future_to_url[future]
        try:
            result = future.result(timeout=0)  # Already completed
            if not result.get('success'):
                failed_sources.append({
                    'url': url,
                    'error': result.get('error', 'Unknown error'),
                    'method': result.get('method', 'unknown')
                })
        except Exception:
            pass  # Already handled above

    # Emit failed_sources for UI display (before AI response)
    if failed_sources:
        yield {"type": "failed_sources", "data": failed_sources}
        log_message(f"⚠️ {len(failed_sources)} URLs not scrapeable")

    # Wait for preload task to complete if not done yet
    if not preload_message_sent and preload_task:
        try:
            success, load_time, unloaded_models = await preload_task
            if unloaded_models:
                models_str = ", ".join(unloaded_models)
                log_message(f"🗑️ Unloaded models: {models_str}")
                yield {"type": "debug", "message": f"🗑️ Unloaded models: {models_str}"}

            if success:
                log_message(f"✅ Main-LLM preloaded ({load_time:.1f}s)")
                yield {"type": "debug", "message": f"✅ Main-LLM preloaded ({load_time:.1f}s)"}
            else:
                log_message(f"⚠️ Main-LLM preload failed ({load_time:.1f}s)")
                yield {"type": "debug", "message": f"⚠️ Main-LLM preload failed ({load_time:.1f}s)"}
        except Exception as e:
            log_message(f"⚠️ Main-LLM preload exception: {e}")

    # Return results
    yield {"type": "scraping_result", "data": (scraped_results, tool_results)}
