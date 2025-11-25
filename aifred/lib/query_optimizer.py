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


# Compiled Regex Pattern
THINK_TAG_PATTERN = re.compile(r'<think>(.*?)</think>', re.DOTALL)


async def optimize_search_query(
    user_text: str,
    automatik_model: str,
    history: Optional[List],
    llm_client,
    automatik_llm_context_limit: int,
    llm_options: Optional[Dict] = None
) -> Tuple[str, Optional[str]]:
    """
    Extrahiert optimierte Suchbegriffe aus User-Frage

    Args:
        user_text: Volle User-Frage (kann lang sein)
        automatik_model: Automatik-LLM für Query-Optimierung
        history: Chat History (für Kontext bei Nachfragen)
        llm_client: LLMClient instance
        automatik_llm_context_limit: Context limit for automatik LLM
        llm_options: Optional Dict mit enable_thinking toggle

    Returns:
        tuple: (optimized_query, reasoning_content)
    """
    # Spracherkennung für Nutzereingabe
    from .prompt_loader import detect_language
    detected_user_language = detect_language(user_text)
    log_message(f"🌐 Spracherkennung: Nutzereingabe ist wahrscheinlich '{detected_user_language.upper()}' (für Prompt-Auswahl)")

    prompt = get_query_optimization_prompt(user_text=user_text, lang=detected_user_language)

    # DEBUG: Zeige Query Optimization Prompt
    log_message("=" * 60)
    log_message("📋 QUERY OPTIMIZATION PROMPT:")
    log_message("-" * 60)
    log_message(prompt)
    log_message("-" * 60)
    log_message(f"Prompt-Länge: {len(prompt)} Zeichen, ~{len(prompt.split())} Wörter")
    log_message("=" * 60)

    try:
        log_message(f"🔍 Query-Optimierung mit {automatik_model}")
        log_message("🔧 Query-Optimierung startet")

        # Baue Messages mit History (letzte 2-3 Turns für Kontext bei Nachfragen)
        messages = build_messages_from_history(history, prompt, max_turns=3)

        # DEBUG: Zeige Messages-Array vollständig
        log_message("=" * 60)
        log_message(f"📨 MESSAGES an {automatik_model} (Query-Opt):")
        log_message("-" * 60)
        for i, msg in enumerate(messages):
            log_message(f"Message {i+1} - Role: {msg['role']}")
            log_message(f"Content: {msg['content']}")
            log_message("-" * 60)

        # Build options (temperature + thinking control)
        options = {
            'temperature': 0.3,  # Leicht kreativ für Keywords, aber stabil
            'num_predict': 128,  # Keywords: "weather London tomorrow 2025" = ~30 tokens (4x buffer)
            'enable_thinking': False  # Default: Fast keyword extraction without reasoning
        }

        # Use user's enable_thinking toggle if explicitly set
        if llm_options and 'enable_thinking' in llm_options:
            options['enable_thinking'] = llm_options['enable_thinking']
            log_message(f"🧠 Query-Opt enable_thinking: {llm_options['enable_thinking']} (from user toggle)")
        else:
            log_message(f"🧠 Query-Opt enable_thinking: False (default - fast keyword mode)")

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

        # Extrahiere <think> Inhalt BEVOR wir ihn entfernen (für Debug-Output)
        think_match = THINK_TAG_PATTERN.search(raw_response)
        think_content = think_match.group(1).strip() if think_match else None

        # Säubern: Entferne <think> Tags und deren Inhalt
        optimized_query = THINK_TAG_PATTERN.sub('', raw_response)

        # CRITICAL: Also remove incomplete or orphaned tags
        # Remove opening tags (incomplete): everything from "<think" to end of string
        optimized_query = re.sub(r'<think.*', '', optimized_query, flags=re.DOTALL)
        # Remove closing tags (orphaned): </think>
        optimized_query = re.sub(r'</think>', '', optimized_query, flags=re.IGNORECASE)

        # Entferne Anführungszeichen und Sonderzeichen
        optimized_query = re.sub(r'["\'\n\r]', '', optimized_query)
        optimized_query = ' '.join(optimized_query.split())  # Normalize whitespace

        # ============================================================
        # FALLBACK: Empty Query (Thinking Models fail to produce keywords)
        # ============================================================
        if not optimized_query or len(optimized_query.strip()) == 0:
            log_message("⚠️ Query-Optimierung ergab leeren String (Thinking-Model?)")
            log_message("   → Fallback zu Original-Query")
            optimized_query = user_text  # Use full user question as-is

        # ============================================================
        # POST-PROCESSING: Temporale Kontext-Erkennung
        # ============================================================
        # Garantiert aktuelles Jahr bei zeitlich relevanten Queries, auch wenn LLM es vergisst

        # Dynamisches Jahr (nicht hardcoded!)
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

        query_lower = optimized_query.lower()

        # Regel 1: "beste/neueste X" → + aktuelles Jahr (falls nicht schon vorhanden)
        if any(kw in query_lower for kw in temporal_keywords) and current_year not in optimized_query:
            optimized_query += f" {current_year}"
            log_message(f"   ⏰ Temporaler Kontext ergänzt: {current_year}")

        # Regel 2: "X vs Y" → + aktuelles Jahr (falls nicht schon vorhanden)
        elif any(kw in query_lower for kw in comparison_keywords) and current_year not in optimized_query:
            optimized_query += f" {current_year}"
            log_message(f"   ⚖️ Vergleichs-Kontext ergänzt: {current_year}")

        log_message("🔍 Query-Optimierung:")
        log_message(f"   Original: {user_text[:80]}{'...' if len(user_text) > 80 else ''}")
        log_message(f"   Optimiert: {optimized_query}")

        # Return: Tuple (optimized_query, reasoning)
        return (optimized_query, think_content)

    except Exception as e:
        log_message(f"⚠️ Fehler bei Query-Optimierung: {e}")
        log_message("   Fallback zu Original-Query")
        return (user_text, None)
