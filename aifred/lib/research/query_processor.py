"""
Query Processor - Query optimization and web search

Handles:
- Direct URL detection and scraping
- Query optimization using Automatik-LLM
- Web search with fallback (Brave → Tavily → SearXNG)
- URL extraction from search results
"""

import re
import time
from typing import Dict, List, AsyncIterator
from urllib.parse import urlparse

from ..query_optimizer import optimize_search_query
from ..agent_tools import search_web
from ..logging_utils import log_message
from ..formatting import format_number
from ..tools.url_utils import deduplicate_urls


# ============================================================
# URL DETECTION & INTENT ANALYSIS
# ============================================================

# Compiled Regex for URL detection (performance optimization)
URL_PATTERN = re.compile(
    r'https?://[^\s]+|'  # https://... or http://...
    r'www\.[^\s]+|'  # www....
    r'\b[a-zA-Z][-a-zA-Z0-9]*\.(?:com|de|org|net|io|co|gov|ai|tech|dev|app|info|me)(?:/[^\s]*)?',  # domain.tld/path (starts with letter, not digit)
    re.IGNORECASE
)

# Search intent keywords (multilingual)
SEARCH_INTENT_KEYWORDS = [
    # German
    'finde', 'find heraus', 'suche', 'such', 'ähnliche', 'vergleiche', 'vergleich',
    'alternative', 'alternativen', 'gibt es',
    # English
    'find', 'search', 'similar', 'compare', 'comparison', 'alternative', 'alternatives',
    'are there', 'is there'
]


def detect_urls_in_text(text: str, max_urls: int = 7) -> List[str]:
    """
    Detects URLs in user text using regex

    Args:
        text: User input text
        max_urls: Maximum number of URLs to return (default: 7 for Deep-Modus)

    Returns:
        List of validated and normalized URLs (up to max_urls)
    """
    matches = URL_PATTERN.findall(text)
    validated_urls = []

    for match in matches:
        # Extract URL string from tuple (regex with groups returns tuples)
        url = match[0] if isinstance(match, tuple) else match

        # Normalize: Add https:// if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # Validate with urlparse
        try:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                validated_urls.append(url)
        except Exception:
            continue  # Skip invalid URLs

        # Limit to max_urls
        if len(validated_urls) >= max_urls:
            break

    # Deduplicate URLs (using existing utility)
    return deduplicate_urls(validated_urls)


def detect_search_intent(text: str) -> bool:
    """
    Detects if user wants additional web search beyond URL scraping

    Keywords: finde, suche, ähnliche, vergleiche, alternative, etc.

    Args:
        text: User input text

    Returns:
        True if search intent detected, False otherwise
    """
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in SEARCH_INTENT_KEYWORDS)


def remove_urls_from_text(text: str, urls: List[str]) -> str:
    """
    Removes detected URLs from user text for query optimization

    Args:
        text: Original user text
        urls: List of URLs to remove

    Returns:
        Text with URLs removed and whitespace normalized
    """
    result = text

    for url in urls:
        # Remove original URL (may not have https://)
        result = result.replace(url, '')

        # Also remove normalized version (with https://)
        if url.startswith('https://'):
            result = result.replace(url.replace('https://', ''), '')

    # Normalize whitespace
    result = ' '.join(result.split())

    return result.strip()


async def process_query_and_search(
    user_text: str,
    history: List[tuple],
    automatik_model: str,
    automatik_llm_client
) -> AsyncIterator[Dict]:
    """
    Process query optimization and perform web search

    Args:
        user_text: User's question
        history: Chat history for context
        automatik_model: Automatik LLM model name
        automatik_llm_client: Automatik LLM client

    Yields:
        Dict: Debug messages and search results

    Returns (via last yield):
        Tuple[str, str, float, List[str], List[Dict]]:
        (optimized_query, query_reasoning, query_opt_time, related_urls, tool_results)
    """
    tool_results = []

    # ============================================================
    # STEP 0: URL DETECTION & INTENT ANALYSIS
    # ============================================================
    detected_urls = detect_urls_in_text(user_text, max_urls=7)
    has_search_intent = detect_search_intent(user_text)

    # Determine processing mode
    if detected_urls and not has_search_intent:
        # MODE A: Direct-URL-Modus (keine Web-Search)
        mode = "direct"
    elif detected_urls and has_search_intent:
        # MODE B: Hybrid-Modus (URL + Web-Search)
        mode = "hybrid"
    else:
        # MODE C: Normal-Modus (nur Web-Search)
        mode = "normal"

    # ============================================================
    # MODE A: DIRECT-URL-MODUS (Skip Query-Opt & Search)
    # ============================================================
    if mode == "direct":
        log_message("=" * 60)
        log_message("⚡ Direct-Scraping-Modus aktiviert")
        log_message("=" * 60)

        yield {"type": "debug", "message": f"🔗 {len(detected_urls)} URL(s) erkannt → Direct-Scraping"}
        for i, url in enumerate(detected_urls, 1):
            yield {"type": "debug", "message": f"   {i}. {url}"}

        yield {"type": "debug", "message": "⚡ Direct-Scraping-Modus (Skip Query-Opt & Search)"}

        # Set results directly
        optimized_query = detected_urls[0] if len(detected_urls) == 1 else f"{len(detected_urls)} URLs"
        query_reasoning = "Direct URL detected - skipped optimization and search"
        query_opt_time = 0.0
        related_urls = detected_urls

        # Return results
        yield {"type": "query_result", "data": (optimized_query, query_reasoning, query_opt_time, related_urls, tool_results)}
        return

    # ============================================================
    # MODE B: HYBRID-MODUS (URL + Web-Search)
    # ============================================================
    elif mode == "hybrid":
        log_message("=" * 60)
        log_message("🔀 Hybrid-Modus aktiviert (URL + Web-Search)")
        log_message("=" * 60)

        yield {"type": "debug", "message": f"🔗 {len(detected_urls)} URL(s) erkannt"}
        for i, url in enumerate(detected_urls, 1):
            yield {"type": "debug", "message": f"   {i}. {url}"}
        yield {"type": "debug", "message": "🔍 Such-Intent erkannt → Hybrid-Modus"}

        # Remove URLs from text for query optimization
        text_without_urls = remove_urls_from_text(user_text, detected_urls)

        if not text_without_urls:
            # Edge case: Only URLs in text, no search keywords
            log_message("⚠️ Kein Text nach URL-Entfernung, fallback zu Direct-Modus")
            yield {"type": "debug", "message": "⚠️ Nur URLs im Text, fallback zu Direct-Scraping"}

            optimized_query = detected_urls[0] if len(detected_urls) == 1 else f"{len(detected_urls)} URLs"
            query_reasoning = "Only URLs in text, no additional search terms"
            query_opt_time = 0.0
            related_urls = detected_urls

            yield {"type": "query_result", "data": (optimized_query, query_reasoning, query_opt_time, related_urls, tool_results)}
            return

        # Query Optimization for text without URLs
        yield {"type": "debug", "message": "🔍 Query-Optimierung (für Such-Keywords)..."}

        query_opt_start = time.time()
        automatik_limit, _ = await automatik_llm_client.get_model_context_limit(automatik_model)

        optimized_query, query_reasoning = await optimize_search_query(
            user_text=text_without_urls,
            automatik_model=automatik_model,
            history=history,
            llm_client=automatik_llm_client,
            automatik_llm_context_limit=automatik_limit
        )
        query_opt_time = time.time() - query_opt_start

        yield {"type": "debug", "message": f"✅ Query-Optimierung fertig ({format_number(query_opt_time, 1)}s)"}
        yield {"type": "debug", "message": f"🔎 Optimierte Query: {optimized_query}"}

        # Web-Suche mit optimierter Query
        log_message("=" * 60)
        log_message("🔍 Web-Suche mit optimierter Query (Hybrid)")
        log_message("=" * 60)

        search_result = search_web(optimized_query)
        tool_results.append(search_result)

        # Console Log: Welche API wurde benutzt?
        api_source = search_result.get('source', 'Unbekannt')
        stats = search_result.get('stats', {})
        apis_used = search_result.get('apis_used', [])

        if stats and apis_used:
            total_urls = stats.get('total_urls', 0)
            unique_urls = stats.get('unique_urls', 0)
            duplicates = stats.get('duplicates_removed', 0)

            yield {"type": "debug", "message": f"🌐 Web-Suche: {', '.join(apis_used)} ({len(apis_used)} APIs)"}
            if duplicates > 0:
                yield {"type": "debug", "message": f"🔄 Deduplizierung: {total_urls} URLs → {unique_urls} unique ({duplicates} Duplikate)"}
        else:
            yield {"type": "debug", "message": f"🌐 Web-Suche mit: {api_source}"}

        # Combine detected URLs with search results
        search_urls = search_result.get('related_urls', [])
        related_urls = detected_urls + search_urls

        # Deduplicate combined list
        related_urls = deduplicate_urls(related_urls)

        yield {"type": "debug", "message": f"🔀 Gesamt: {len(related_urls)} URLs (direkt + Search)"}

        # Return results
        yield {"type": "query_result", "data": (optimized_query, query_reasoning, query_opt_time, related_urls, tool_results)}
        return

    # ============================================================
    # MODE C: NORMAL-MODUS (nur Web-Search, wie bisher)
    # ============================================================
    else:  # mode == "normal"
        # 1. Query Optimization
        yield {"type": "debug", "message": "🔍 Query-Optimierung läuft..."}

        query_opt_start = time.time()

        # Query Automatik-Model Context Limit (silent - already shown in decision phase)
        automatik_limit, _ = await automatik_llm_client.get_model_context_limit(automatik_model)

        optimized_query, query_reasoning = await optimize_search_query(
            user_text=user_text,
            automatik_model=automatik_model,
            history=history,
            llm_client=automatik_llm_client,
            automatik_llm_context_limit=automatik_limit
        )
        query_opt_time = time.time() - query_opt_start

        # Show query optimization completion AND optimized query
        yield {"type": "debug", "message": f"✅ Query-Optimierung fertig ({format_number(query_opt_time, 1)}s)"}
        yield {"type": "debug", "message": f"🔎 Optimierte Query: {optimized_query}"}

        # 2. Web-Suche
        log_message("=" * 60)
        log_message("🔍 Web-Suche mit optimierter Query")
        log_message("=" * 60)

        search_result = search_web(optimized_query)
        tool_results.append(search_result)

    # Console Log: Welche API wurde benutzt?
    api_source = search_result.get('source', 'Unbekannt')
    stats = search_result.get('stats', {})
    apis_used = search_result.get('apis_used', [])

    if stats and apis_used:
        # Multi-API Search mit Stats
        total_urls = stats.get('total_urls', 0)
        unique_urls = stats.get('unique_urls', 0)
        duplicates = stats.get('duplicates_removed', 0)

        yield {"type": "debug", "message": f"🌐 Web-Suche: {', '.join(apis_used)} ({len(apis_used)} APIs)"}
        if duplicates > 0:
            yield {"type": "debug", "message": f"🔄 Deduplizierung: {total_urls} URLs → {unique_urls} unique ({duplicates} Duplikate)"}
    else:
        yield {"type": "debug", "message": f"🌐 Web-Suche mit: {api_source}"}

    # Extract URLs
    related_urls = search_result.get('related_urls', [])

    # Return results as last yield (includes query_reasoning for debug accordion)
    yield {"type": "query_result", "data": (optimized_query, query_reasoning, query_opt_time, related_urls, tool_results)}
