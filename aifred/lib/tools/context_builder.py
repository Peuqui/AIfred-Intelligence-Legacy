"""
Context Builder - Build structured context for LLM

Extracted from agent_tools.py for better modularity.
"""

import logging
from typing import Dict, List

from ..config import MAX_RAG_CONTEXT_TOKENS, MAX_WORDS_PER_SOURCE, MAX_WORDS_SINGLE_SOURCE, CHARS_PER_TOKEN
from ..logging_utils import log_message

# Logging Setup
logger = logging.getLogger(__name__)

def build_context(user_text: str, tool_results: List[Dict], max_context_tokens: int = None) -> str:
    """
    Build structured context for AI from tool results

    INTELLIGENT CONTEXT MANAGEMENT:
    - Prioritizes SHORT, CURRENT sources
    - Limits LONG sources (Wikipedia) to MAX_WORDS_PER_SOURCE
    - Sorts: News articles > Wikipedia/Long articles

    Args:
        user_text: User question
        tool_results: List of research results
        max_context_tokens: Optional, if None uses MAX_RAG_CONTEXT_TOKENS from config.py
    """
    if max_context_tokens is None:
        max_context_tokens = MAX_RAG_CONTEXT_TOKENS
    context_header = f"# User Question\n{user_text}\n\n# Research Results\n\n"
    context_footer = ""  # No footer - system prompt already contains all instructions

    successful_results = [r for r in tool_results if r.get('success', False)]

    if not successful_results:
        context = context_header + "*No successful research results found.*\n\n" + context_footer
        return context

    # INTELLIGENT SORTING: News > Wikipedia
    def prioritize_source(result):
        url = result.get('url', '').lower()
        word_count = result.get('word_count', 0)

        # Wikipedia = low priority (large number = later)
        if 'wikipedia.org' in url:
            return 1000
        # Short articles (news) = high priority (small number = earlier)
        elif word_count < 5000:
            return word_count
        # Long articles = low priority
        else:
            return 500 + word_count

    successful_results.sort(key=prioritize_source)

    # Build context with intelligent limiting
    sources_text = []
    total_tokens = 0
    max_source_tokens = max_context_tokens - 1000  # Reserve for header/footer

    for i, result in enumerate(successful_results, 1):
        source = result.get('source', 'Unknown')
        content = result.get('content', result.get('abstract', ''))
        url = result.get('url', '')
        title = result.get('title', '')
        word_count = result.get('word_count', 0)

        # Determine word limit: Higher limit for single source (Direct URL)
        # e.g., scientific papers, PDFs with 4000-8000 words
        is_single_source = len(successful_results) == 1
        word_limit = MAX_WORDS_SINGLE_SOURCE if is_single_source else MAX_WORDS_PER_SOURCE

        # Limit LONG sources - value from config.py
        if word_count > word_limit:
            # Truncate content (roughly: 1 token = 0.75 words)
            words = content.split()
            content = ' '.join(words[:word_limit])
            log_message(f"⚠️ Source {i} ({url}) truncated: {word_count} → {word_limit} words")

        # Format source
        source_text = ""
        if title:
            source_text += f"## Source {i}: {title}\n"
        else:
            source_text += f"## Source {i}: {source}\n"

        if url:
            source_text += f"**🔗 URL:** {url}\n\n"

        if content:
            source_text += f"{content}\n\n"

        source_text += "---\n\n"

        # Token check - ratio from config.py
        source_tokens = len(source_text) // CHARS_PER_TOKEN
        if total_tokens + source_tokens > max_source_tokens:
            log_message(f"⚠️ Context limit reached at source {i}, stopping here")
            break

        sources_text.append(source_text)
        total_tokens += source_tokens

    context = context_header + ''.join(sources_text) + context_footer
    estimated_tokens = len(context) // CHARS_PER_TOKEN
    logger.info(f"Context built: {len(context)} chars (~{estimated_tokens} tokens), {len(sources_text)} sources")
    log_message(f"📦 Context built: {len(context)} chars (~{estimated_tokens} tokens), {len(sources_text)} sources")

    return context


# ============================================================
# TOOL REGISTRY
# ============================================================

