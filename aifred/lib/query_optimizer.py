"""
Query Optimizer - Search Query Optimization with LLM

Optimizes user queries for better web search results:
- Extracts key search terms
- Adds temporal context (current year)
- Handles follow-up questions with history
"""

import re
from datetime import datetime
from typing import Optional, Tuple, List, Dict
from .logging_utils import log_message
from .prompt_loader import get_query_optimization_prompt
from .message_builder import build_messages_from_history
from .config import AUTOMATIK_LLM_NUM_CTX


# Compiled Regex Pattern
THINK_TAG_PATTERN = re.compile(r'<think>(.*?)</think>', re.DOTALL)


async def optimize_search_query(
    user_text: str,
    automatik_model: str,
    history: Optional[List],
    llm_client,
    automatik_llm_context_limit: int,
    llm_options: Optional[Dict] = None,
    vision_json_context: Optional[Dict] = None
) -> Tuple[List[str], Optional[str]]:
    """
    Extract optimized search terms from user question

    Args:
        user_text: Full user question (can be long)
        automatik_model: Automatik-LLM for query optimization
        history: Chat history (for context on follow-up questions)
        llm_client: LLMClient instance
        automatik_llm_context_limit: Context limit for automatik LLM
        llm_options: Optional Dict with enable_thinking toggle
        vision_json_context: Optional Vision JSON from image extraction (for query context)

    Returns:
        tuple: (list_of_optimized_queries, reasoning_content)
               Multiple queries for distribution across search APIs
    """
    # Language detection for user input
    from .prompt_loader import detect_language
    detected_user_language = detect_language(user_text)
    log_message(f"🌐 Language detection: User input is probably '{detected_user_language.upper()}' (for prompt selection)")

    prompt = get_query_optimization_prompt(
        user_text=user_text,
        lang=detected_user_language,
        vision_json=vision_json_context
    )

    # DEBUG: Show Query Optimization Prompt
    log_message("=" * 60)
    log_message("📋 QUERY OPTIMIZATION PROMPT:")
    log_message("-" * 60)
    log_message(prompt)
    log_message("-" * 60)
    log_message(f"Prompt length: {len(prompt)} chars, ~{len(prompt.split())} words")
    log_message("=" * 60)

    try:
        log_message(f"🔍 Query optimization with {automatik_model}")
        log_message("🔧 Query optimization starting")

        # Build messages with history (last 2-3 turns for context on follow-up questions)
        messages = build_messages_from_history(history, prompt, max_turns=3)

        # DEBUG: Show complete Messages array
        log_message("=" * 60)
        log_message(f"📨 MESSAGES to {automatik_model} (Query-Opt):")
        log_message("-" * 60)
        for i, msg in enumerate(messages):
            log_message(f"Message {i+1} - Role: {msg['role']}")
            log_message(f"Content: {msg['content']}")
            log_message("-" * 60)

        # Build options (temperature + thinking control)
        options = {
            'temperature': 0.3,  # Slightly creative for keywords, but stable
            'num_ctx': AUTOMATIK_LLM_NUM_CTX,  # Explicit 4K context (prevents 262K default!)
            'num_predict': 128,  # Keywords: "weather London tomorrow 2025" = ~30 tokens (4x buffer)
            'enable_thinking': False  # Default: Fast keyword extraction without reasoning
        }

        # Automatik tasks: Thinking is ALWAYS off (independent of user toggle)
        # User toggle only applies to Main-LLM, not query optimization
        log_message("🧠 Query-Opt enable_thinking: False (Automatik-Task)")

        log_message(f"Total Messages: {len(messages)}, Temperature: 0.3")
        log_message("=" * 60)

        # Async LLM call
        response = await llm_client.chat(
            model=automatik_model,
            messages=messages,
            options=options
        )
        raw_response = response.text.strip()

        # DEBUG: Log raw response BEFORE any processing
        log_message("=" * 60)
        log_message("📝 RAW LLM RESPONSE (Query-Opt):")
        log_message("-" * 60)
        log_message(raw_response)
        log_message("-" * 60)
        log_message(f"Response length: {len(raw_response)} chars")
        log_message("=" * 60)

        # Extract <think> content BEFORE removing it (for debug output)
        think_match = THINK_TAG_PATTERN.search(raw_response)
        think_content = think_match.group(1).strip() if think_match else None

        # Clean: Remove <think> tags and their content
        optimized_query = THINK_TAG_PATTERN.sub('', raw_response)

        # CRITICAL: Also remove incomplete or orphaned tags
        # Remove opening tags (incomplete): everything from "<think" to end of string
        optimized_query = re.sub(r'<think.*', '', optimized_query, flags=re.DOTALL)
        # Remove closing tags (orphaned): </think>
        optimized_query = re.sub(r'</think>', '', optimized_query, flags=re.IGNORECASE)

        # ============================================================
        # MULTI-QUERY: Parse all lines (prompt returns 1-3 queries)
        # ============================================================
        query_lines = [line.strip() for line in optimized_query.split('\n') if line.strip()]

        # Clean each query: remove quotes and normalize whitespace
        cleaned_queries = []
        for query in query_lines:
            query = re.sub(r'["\']', '', query)
            query = ' '.join(query.split())  # Normalize whitespace
            if query:  # Only add non-empty queries
                cleaned_queries.append(query)

        # ============================================================
        # FALLBACK: Empty Query List (Thinking Models fail to produce keywords)
        # ============================================================
        if not cleaned_queries:
            log_message("⚠️ Query optimization returned empty list (Thinking model?)")
            log_message("   → Fallback to original query")
            cleaned_queries = [user_text]  # Use full user question as-is

        # ============================================================
        # POST-PROCESSING: Temporal context detection (for ALL queries)
        # ============================================================
        # Guarantees current year for time-relevant queries, even if LLM forgets it

        # Dynamic year (not hardcoded!)
        current_year = str(datetime.now().year)

        temporal_keywords = [
            'neu', 'neue', 'neuer', 'neues', 'neueste', 'neuester', 'neuestes',
            'aktuell', 'aktuelle', 'aktueller', 'aktuelles',
            'latest', 'recent', 'new', 'newest',
            'beste', 'bester', 'bestes', 'best',
            'top', 'current'
        ]

        comparison_keywords = [
            'vs', 'versus', 'vergleich', 'compare', 'comparison',
            'oder', 'or', 'vs.', 'gegen', 'statt', 'instead'
        ]

        # Apply temporal post-processing to each query
        processed_queries = []
        for query in cleaned_queries:
            query_lower = query.lower()

            # Rule 1: "best/latest X" → + current year (if not already present)
            if any(kw in query_lower for kw in temporal_keywords) and current_year not in query:
                query += f" {current_year}"
                log_message(f"   ⏰ Temporal context added: {current_year}")

            # Rule 2: "X vs Y" → + current year (if not already present)
            elif any(kw in query_lower for kw in comparison_keywords) and current_year not in query:
                query += f" {current_year}"
                log_message(f"   ⚖️ Comparison context added: {current_year}")

            processed_queries.append(query)

        log_message("🔍 Query optimization:")
        log_message(f"   Original: {user_text[:80]}{'...' if len(user_text) > 80 else ''}")
        log_message(f"   📋 {len(processed_queries)} queries generated:")
        for i, q in enumerate(processed_queries, 1):
            log_message(f"      {i}. {q}")

        # Return: Tuple (list_of_queries, reasoning)
        return (processed_queries, think_content)

    except Exception as e:
        log_message(f"⚠️ Error during query optimization: {e}")
        log_message("   Fallback to original query")
        return ([user_text], None)  # Return as list for consistency
