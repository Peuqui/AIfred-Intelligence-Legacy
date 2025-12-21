"""
URL Utilities - Normalization and Deduplication

Extracted from agent_tools.py for better modularity.
"""

import logging
from typing import List
from urllib.parse import urlparse

# Logging Setup
logger = logging.getLogger(__name__)


# ============================================================
# URL DEDUPLICATION UTILITIES
# ============================================================

def normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication

    Handles:
    - www. vs non-www
    - http vs https
    - Trailing slashes
    - URL fragments (#)
    - Query parameters (?) [optional - currently NOT removed!]

    Args:
        url: URL to normalize

    Returns:
        Normalized URL
    """
    try:
        parsed = urlparse(url.lower().strip())

        # Normalize domain (remove www.)
        domain = parsed.netloc.replace('www.', '')

        # Normalize path (remove trailing slash)
        path = parsed.path.rstrip('/')

        # Keep query params (can be important, e.g., ?id=123)
        # Ignore fragments (# anchors)
        query = parsed.query

        # Build normalized URL
        normalized = f"{domain}{path}"
        if query:
            normalized += f"?{query}"

        return normalized

    except Exception as e:
        logger.warning(f"⚠️ URL normalization failed for {url}: {e}")
        return url  # Fallback: Original URL


def deduplicate_urls(urls: List[str]) -> List[str]:
    """
    Remove duplicate URLs from list

    Uses normalization to also detect similar URLs:
    - https://www.example.com/path/
    - https://example.com/path
    → Both count as equal!

    Args:
        urls: List of URL strings

    Returns:
        Deduplicated list (preserves order)
    """
    seen = set()
    unique = []

    for url in urls:
        normalized = normalize_url(url)

        if normalized not in seen:
            seen.add(normalized)
            unique.append(url)  # Keep original URL, not normalized!

    duplicates_removed = len(urls) - len(unique)
    if duplicates_removed > 0:
        logger.info(f"🔄 Deduplication: {len(urls)} URLs → {len(unique)} unique ({duplicates_removed} duplicates removed)")

    return unique
