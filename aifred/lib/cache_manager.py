"""
Cache Manager - Research Cache Management with Thread Safety

Handles caching of research results including:
- Thread-safe cache operations
- Session-based cache lookups
"""

import time  # Keep for timestamp (time.time() for data, not duration)
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
