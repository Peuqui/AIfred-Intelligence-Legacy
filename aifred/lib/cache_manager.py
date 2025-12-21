"""
Cache Manager - Research Cache Management with Thread Safety

Handles caching of research results including:
- Thread-safe cache operations
- Cache metadata generation
- Session-based cache lookups
"""

import time
import threading
from collections import OrderedDict
from typing import Dict, List, Optional
from .logging_utils import log_message


# ============================================================
# GLOBAL CACHE STATE (Dependency Injection)
# ============================================================
# IMPORTANT: Initialize cache directly at module import!
# This prevents "Cache not initialized" errors during hot-reloads.
#
# OrderedDict instead of Dict for LRU Cache (oldest entries are deleted first)
_research_cache: OrderedDict = OrderedDict()
_research_cache_lock: threading.Lock = threading.Lock()
MAX_CACHE_ENTRIES = 100  # Maximum number of sessions in RAM


def set_research_cache(cache_dict: Dict, lock: threading.Lock) -> None:
    """
    Sets the research cache and lock for dependency injection

    Args:
        cache_dict: Dictionary to store research results by session_id
        lock: threading.Lock() for thread-safe access
    """
    global _research_cache, _research_cache_lock
    _research_cache = cache_dict
    _research_cache_lock = lock


def get_cached_research(session_id: Optional[str]) -> Optional[Dict]:
    """
    Gets cached research for a session (thread-safe)

    Args:
        session_id: Session ID to lookup

    Returns:
        Cached research data or None if not found
    """
    # IMPORTANT: An empty dictionary {} is a valid (but empty) cache state!
    if not session_id:
        log_message("🔍 DEBUG Cache-Lookup: No session_id")
        return None

    with _research_cache_lock:
        # DEBUG: Show cache contents (keys) for diagnosis
        cache_keys = list(_research_cache.keys())
        log_message(f"🔍 DEBUG Cache-Lookup: Searching session_id = {session_id[:8]}...")
        log_message(f"   Cache contains {len(cache_keys)} entries: {[k[:8] + '...' for k in cache_keys]}")

        if session_id in _research_cache:
            cache_entry = _research_cache[session_id]
            log_message(f"   ✅ Cache-Hit! Entry found with {len(cache_entry.get('scraped_sources', []))} sources")
            return cache_entry.copy()
        else:
            log_message(f"   ❌ Cache-Miss! session_id '{session_id[:8]}...' not in cache")
    return None


def get_all_metadata_summaries(exclude_session_id: Optional[str] = None, max_entries: int = 10) -> List[Dict]:
    """
    Gets ALL metadata summaries from the cache (except the current session).

    This function is used to give the main LLM context from previous research,
    WITHOUT passing the full sources (saves context tokens).

    Args:
        exclude_session_id: Session ID that should NOT be returned (current research)
        max_entries: Maximum number of old research entries (default: 10)

    Returns:
        List of dicts with {session_id, user_text, metadata_summary, timestamp}
        Sorted by timestamp (newest first), max. max_entries entries
    """
    result = []
    with _research_cache_lock:
        for session_id, cache_entry in _research_cache.items():
            # Exclude current session
            if session_id == exclude_session_id:
                continue

            # Only entries WITH metadata summary
            metadata_summary = cache_entry.get('metadata_summary')
            if not metadata_summary:
                continue

            result.append({
                'session_id': session_id,
                'user_text': cache_entry.get('user_text', ''),
                'metadata_summary': metadata_summary,
                'timestamp': cache_entry.get('timestamp', 0)
            })

    # Sort by timestamp (newest first) and limit to max_entries
    result.sort(key=lambda x: x['timestamp'], reverse=True)
    return result[:max_entries]


def save_cached_research(
    session_id: Optional[str],
    user_text: str,
    scraped_sources: List[Dict],
    mode: str,
    metadata_summary: Optional[str] = None
) -> None:
    """
    Saves research to cache (thread-safe)

    Args:
        session_id: Session ID
        user_text: Original user question
        scraped_sources: List of scraped source dictionaries
        mode: Research mode used
        metadata_summary: Optional KI-generated semantic summary of sources
    """
    if not session_id:
        log_message("⚠️ DEBUG Cache save failed: No session_id")
        return

    with _research_cache_lock:
        _research_cache[session_id] = {
            'timestamp': time.time(),
            'user_text': user_text,
            'scraped_sources': scraped_sources,
            'mode': mode,
            'metadata_summary': metadata_summary
        }

        # LRU Eviction: If cache is full, delete oldest entry
        if len(_research_cache) > MAX_CACHE_ENTRIES:
            oldest_session = next(iter(_research_cache))  # First item = oldest
            evicted_entry = _research_cache.pop(oldest_session)
            log_message(
                f"🗑️ Research-Cache LRU evicted: Session {oldest_session[:8]}... "
                f"(Question: '{evicted_entry['user_text'][:50]}...')"
            )

        # DEBUG: Show cache status after saving
        cache_size = len(_research_cache)
        log_message(f"💾 Research-Cache saved for Session {session_id[:8]}...")
        log_message(f"   Cache now contains {cache_size}/{MAX_CACHE_ENTRIES} entries: {[k[:8] + '...' for k in list(_research_cache.keys())[-5:]]}")
        log_message(f"   Saved: {len(scraped_sources)} sources, user_text: '{user_text[:50]}...'")

        # DEBUG: Show COMPLETE cache contents
        log_message("=" * 80)
        log_message("📦 COMPLETE CACHE CONTENTS:")
        log_message("=" * 80)
        for cache_key, cache_value in _research_cache.items():
            source_urls = [s.get('url', 'N/A') for s in cache_value.get('scraped_sources', [])]
            log_message(f"Session: {cache_key}")
            log_message(f"  User-Text: {cache_value.get('user_text', 'N/A')}")
            log_message(f"  Timestamp: {cache_value.get('timestamp', 0)}")
            log_message(f"  Mode: {cache_value.get('mode', 'N/A')}")
            log_message(f"  Sources ({len(source_urls)}):")
            for i, url in enumerate(source_urls, 1):
                log_message(f"    {i}. {url[:80]}{'...' if len(url) > 80 else ''}")
            log_message("-" * 80)
        log_message("=" * 80)


def delete_cached_research(session_id: Optional[str]) -> None:
    """
    Deletes cached research for a session (thread-safe)

    Args:
        session_id: Session ID to delete
    """
    if not session_id:
        return

    with _research_cache_lock:
        if session_id in _research_cache:
            del _research_cache[session_id]
            log_message(f"🗑️ Cache deleted for Session {session_id[:8]}...")


async def generate_cache_metadata(
    session_id: Optional[str],
    metadata_model: str,
    llm_client,
    haupt_llm_context_limit: int
):
    """
    Generates AI-based metadata for cached research data (synchronous after main LLM).

    This function is called AFTER the main LLM response and yields messages
    for the debug console.

    Args:
        session_id: Session ID for cache lookup
        metadata_model: LLM model for metadata generation (e.g., automatik LLM)
        llm_client: LLMClient instance for inference
        haupt_llm_context_limit: Context limit for main LLM (for num_ctx calculation)

    Yields:
        Debug messages for UI
    """
    if not session_id:
        return

    try:
        # Get cache data
        cache_entry = get_cached_research(session_id)
        if not cache_entry:
            log_message("⚠️ Metadata generation: No cache found")
            return

        scraped_sources = cache_entry.get('scraped_sources', [])
        if not scraped_sources:
            log_message("⚠️ Metadata generation: No sources in cache")
            return

        # UI-Message: Start
        yield {"type": "debug", "message": "📝 Starting cache metadata generation..."}
        log_message("📝 Generating AI-based cache metadata...")
        log_message("📝 Creating cache summary...")

        # Build preview of sources (first 3 sources, 500 chars per source)
        sources_preview = "\n\n".join([
            f"Source {i+1}: {s.get('title', 'N/A')}\nURL: {s.get('url', 'N/A')}\nContent: {s.get('content', '')[:500]}..."
            for i, s in enumerate(scraped_sources[:3])  # First 3 sources for context
        ])

        # Load prompt from external file (prompts/cache_metadata.txt)
        from .prompt_loader import get_cache_metadata_prompt
        metadata_prompt = get_cache_metadata_prompt(sources_preview=sources_preview)

        # DEBUG: Show metadata generation prompt completely
        log_message("=" * 60)
        log_message("📋 METADATA GENERATION PROMPT:")
        log_message("-" * 60)
        log_message(metadata_prompt)
        log_message("-" * 60)
        log_message(f"Prompt length: {len(metadata_prompt)} chars, ~{len(metadata_prompt.split())} words")
        log_message("=" * 60)

        messages = [{'role': 'user', 'content': metadata_prompt}]

        # Dynamic num_ctx based on main LLM limit (50% for metadata, short output)
        metadata_num_ctx = min(2048, haupt_llm_context_limit // 2)  # Max 2048 or 50% of limit

        log_message(f"Total Messages: {len(messages)}, Temperature: 0.1, num_ctx: {metadata_num_ctx} (Main-LLM-Limit: {haupt_llm_context_limit}), num_predict: 100")
        log_message("=" * 60)

        metadata_start = time.time()

        log_message(f"🔧 Using metadata model: {metadata_model}")

        # Async LLM call
        response = await llm_client.chat(
            model=metadata_model,
            messages=messages,
            options={
                'temperature': 0.1,
                'num_ctx': metadata_num_ctx,
                'num_predict': 100,
                'enable_thinking': False  # Fast metadata generation, no reasoning needed
            }
        )

        metadata_summary = response.text.strip()
        metadata_time = time.time() - metadata_start

        # LLM follows the instructions in the prompt (max 60 words)
        # No hardcoded limit in code - the LLM controls the length itself

        # Update cache with metadata
        with _research_cache_lock:
            if session_id in _research_cache:
                _research_cache[session_id]['metadata_summary'] = metadata_summary

        tokens_per_second = response.tokens_per_second

        # UI-Message: Completion with tokens/sec
        yield {"type": "debug", "message": f"✅ Cache metadata done ({metadata_time:.1f}s, {tokens_per_second:.1f} t/s)"}

        # Log-File Messages (detailed)
        log_message(f"✅ Cache metadata generated ({metadata_time:.1f}s, {tokens_per_second:.1f} t/s): {metadata_summary}")
        log_message(f"✅ Summary created: {metadata_summary[:80]}{'...' if len(metadata_summary) > 80 else ''}")

    except Exception as e:
        log_message(f"⚠️ Error in metadata generation: {e}")
        log_message("⚠️ Metadata generation failed")
        yield {"type": "debug", "message": "⚠️ Cache metadata generation failed"}
