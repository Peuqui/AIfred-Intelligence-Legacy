"""
Intent Detector - Query Intent Classification

Classifies user queries for adaptive temperature selection:
- FAKTISCH: Factual queries (low temperature)
- KREATIV: Creative queries (high temperature)
- GEMISCHT: Mixed queries (medium temperature)
"""

from typing import Optional, Dict
from .logging_utils import log_message
from .prompt_loader import get_intent_detection_prompt, get_followup_intent_prompt
from .config import AUTOMATIK_LLM_NUM_CTX


def parse_intent_from_response(intent_raw: str, context: str = "general") -> str:
    """
    Extract intent from LLM response (even if LLM writes more text)

    Args:
        intent_raw: Raw LLM response
        context: Context for logging ("general" or "cache_followup")

    Returns:
        str: "FAKTISCH", "KREATIV" or "GEMISCHT"
    """
    intent_upper = intent_raw.strip().upper()

    # Extract intent (prioritization)
    if "FAKTISCH" in intent_upper:
        return "FAKTISCH"
    elif "KREATIV" in intent_upper:
        return "KREATIV"
    elif "GEMISCHT" in intent_upper:
        return "GEMISCHT"
    else:
        # Fallback
        prefix = "Cache-Intent" if context == "cache_followup" else "Intent"
        log_message(f"⚠️ {prefix} unknown: '{intent_raw}' → Default: FAKTISCH")
        return "FAKTISCH"


async def detect_query_intent(
    user_query: str,
    automatik_model: str,
    llm_client,
    llm_options: Optional[Dict] = None
) -> str:
    """
    Detect intent of user query for adaptive temperature selection

    Args:
        user_query: User question
        automatik_model: LLM for intent detection
        llm_client: LLMClient instance
        llm_options: Optional Dict with enable_thinking toggle

    Returns:
        str: "FAKTISCH", "KREATIV" or "GEMISCHT"
    """
    # Language detection for user input
    from .prompt_loader import detect_language
    detected_user_language = detect_language(user_query)
    log_message(f"🌐 Language detection: User input is probably '{detected_user_language.upper()}' (for prompt selection)")

    prompt = get_intent_detection_prompt(user_query=user_query, lang=detected_user_language)

    try:
        log_message(f"🎯 Intent detection for query: {user_query[:60]}...")

        # Build options
        intent_options = {
            'temperature': 0.2,  # Low for consistent intent detection
            'num_ctx': AUTOMATIK_LLM_NUM_CTX,  # Explicit 4K context (prevents 262K default!)
            'num_predict': 32,  # Short: "FAKTISCH" / "KREATIV" = ~10 tokens (3x buffer)
            'enable_thinking': False  # Default: Fast intent detection without reasoning
        }

        # Automatik tasks: Thinking is ALWAYS off (independent of user toggle)
        log_message("🧠 Intent enable_thinking: False (Automatik-Task)")

        response = await llm_client.chat(
            model=automatik_model,
            messages=[{'role': 'user', 'content': prompt}],
            options=intent_options
        )
        intent_raw = response.text

        intent = parse_intent_from_response(intent_raw, context="general")
        log_message(f"✅ Intent detected: {intent}")
        return intent

    except Exception as e:
        log_message(f"❌ Intent detection error: {e} → Fallback: FAKTISCH")
        return "FAKTISCH"  # Safe Fallback


async def detect_cache_followup_intent(
    original_query: str,
    followup_query: str,
    automatik_model: str,
    llm_client,
    llm_options: Optional[Dict] = None
) -> str:
    """
    Detect intent of follow-up question to cached research

    Args:
        original_query: Original research question
        followup_query: User's follow-up question
        automatik_model: LLM for intent detection
        llm_client: LLMClient instance
        llm_options: Optional Dict with enable_thinking toggle

    Returns:
        str: "FAKTISCH", "KREATIV" or "GEMISCHT"
    """
    # Language detection for follow-up
    from .prompt_loader import detect_language
    detected_user_language = detect_language(followup_query)
    log_message(f"🌐 Language detection: Follow-up is probably '{detected_user_language.upper()}' (for prompt selection)")

    prompt = get_followup_intent_prompt(
        original_query=original_query,
        followup_query=followup_query,
        lang=detected_user_language
    )

    try:
        log_message(f"🎯 Cache-Followup Intent-Detection mit {automatik_model}: {followup_query[:60]}...")

        # Build options
        followup_intent_options = {
            'temperature': 0.2,
            'num_ctx': AUTOMATIK_LLM_NUM_CTX,  # Explicit 4K context (prevents 262K default!)
            'num_predict': 32,  # Short: "FAKTISCH" / "KREATIV" = ~10 tokens (3x buffer)
            'enable_thinking': False  # Default: Fast intent detection without reasoning
        }

        # Automatik tasks: Thinking is ALWAYS off (independent of user toggle)
        log_message("🧠 Followup Intent enable_thinking: False (Automatik-Task)")

        response = await llm_client.chat(
            model=automatik_model,
            messages=[{'role': 'user', 'content': prompt}],
            options=followup_intent_options
        )
        intent_raw = response.text

        intent = parse_intent_from_response(intent_raw, context="cache_followup")
        log_message(f"✅ Cache-Followup Intent ({automatik_model}): {intent}")
        return intent

    except Exception as e:
        log_message(f"❌ Cache-Followup Intent-Detection Error: {e} → Fallback: FAKTISCH")
        return "FAKTISCH"


def get_temperature_for_intent(intent: str) -> float:
    """
    Returns the appropriate temperature for an intent.

    Temperature values are defined in config.py:
    - INTENT_TEMPERATURE_FAKTISCH (0.2): precise, deterministic answers
    - INTENT_TEMPERATURE_GEMISCHT (0.5): general conversation
    - INTENT_TEMPERATURE_KREATIV (1.1): stories, poems, creative writing

    Args:
        intent: "FAKTISCH", "KREATIV" or "GEMISCHT"

    Returns:
        float: Temperature based on config.py constants
    """
    from .config import (
        INTENT_TEMPERATURE_FAKTISCH,
        INTENT_TEMPERATURE_GEMISCHT,
        INTENT_TEMPERATURE_KREATIV
    )

    temp_map = {
        "FAKTISCH": INTENT_TEMPERATURE_FAKTISCH,
        "KREATIV": INTENT_TEMPERATURE_KREATIV,
        "GEMISCHT": INTENT_TEMPERATURE_GEMISCHT
    }
    return temp_map.get(intent, INTENT_TEMPERATURE_FAKTISCH)  # Fallback: factual


def get_temperature_label(intent: str) -> str:
    """
    Returns the label for an intent (for UI display)

    Args:
        intent: "FAKTISCH", "KREATIV" or "GEMISCHT"

    Returns:
        str: "factual", "creative" or "mixed"
    """
    label_map = {
        "FAKTISCH": "factual",
        "KREATIV": "creative",
        "GEMISCHT": "mixed"
    }
    return label_map.get(intent, "factual")  # Fallback: factual


def detect_dialog_addressing(user_text: str) -> tuple[Optional[str], str]:
    """
    Detect if user is directly addressing Sokrates or AIfred.

    Handles various addressing patterns:
    - "Sokrates, warum..." / "sokrates:" / "@sokrates"
    - "AIfred, erkläre..." / "alfred," / "@alfred" / "Eifred," (STT variant)
    - "Warum, Sokrates, denkst du..."  (embedded addressing)

    Args:
        user_text: The user's message

    Returns:
        tuple: (addressed_to, cleaned_text)
            - addressed_to: "sokrates", "alfred", or None
            - cleaned_text: User text with addressing prefix removed
    """
    import re

    text = user_text.strip()
    text_lower = text.lower()

    # ============================================================
    # SOKRATES ADDRESSING PATTERNS
    # ============================================================
    sokrates_patterns = [
        # Start patterns: "Sokrates, ..." / "Sokrates: ..." / "@Sokrates ..."
        # IMPORTANT: Requires comma/colon after name to distinguish from "Sokrates hat gesagt"
        (r'^(?:@)?sokrates[,:]\s*', True),
        # "Hey Sokrates, ..."
        (r'^hey\s+sokrates[,:]\s*', True),
        # "An Sokrates: ..."
        (r'^an\s+sokrates[,:]\s*', True),
        # "Also Sokrates, ..." / "Aber Sokrates, ..." (word + Sokrates + comma/colon)
        # Does NOT match "Aber Sokrates hat gesagt" (no comma after Sokrates)
        (r'^\w+\s+sokrates[,:]\s*', True),
        # Embedded: "Warum, Sokrates, denkst du..." - keep text, just detect
        (r',\s*sokrates\s*,', False),
        # End of sentence: "..., Sokrates." / "..., Sokrates?" / "..., Sokrates!"
        (r',\s*sokrates\s*[.?!]?\s*$', False),
        # Standalone at end after period: "... motiviert. Sokrates." / "... Sokrates!"
        # Catches cases where Sokrates is addressed as a separate sentence/word
        (r'[.!?]\s*sokrates\s*[.!?]?\s*$', False),
        # Vocative phrases: "mein lieber Sokrates" / "lieber Sokrates" (anywhere in text)
        (r'\b(?:mein\s+)?liebe[rn]?\s+sokrates\b', False),
    ]

    for pattern, remove_prefix in sokrates_patterns:
        match = re.search(pattern, text_lower)
        if match:
            if remove_prefix:
                # Remove the addressing prefix from the text
                cleaned = text[match.end():].strip()
                # Capitalize first letter if needed
                if cleaned and cleaned[0].islower():
                    cleaned = cleaned[0].upper() + cleaned[1:]
                return ("sokrates", cleaned if cleaned else text)
            else:
                # Embedded addressing - keep original text
                return ("sokrates", text)

    # ============================================================
    # ALFRED ADDRESSING PATTERNS
    # ============================================================
    # Note: "AIfred" is often transcribed as "Eifred", "Alfred", "AI Fred" by STT
    alfred_patterns = [
        # Start patterns with various STT transcriptions
        (r'^(?:@)?(?:ai\s*fred|aifred|alfred|eifred)[,:\s!]+\s*', True),
        # "Hey AIfred, ..."
        (r'^hey\s+(?:ai\s*fred|aifred|alfred|eifred)[,:\s!]+\s*', True),
        # "An AIfred: ..."
        (r'^an\s+(?:ai\s*fred|aifred|alfred|eifred)[,:\s!]+\s*', True),
        # "Also AIfred, ..." / "Aber Alfred, ..." (word before AIfred)
        (r'^\w+\s+(?:ai\s*fred|aifred|alfred|eifred)[,:\s!]+\s*', True),
        # Embedded: "Warum, AIfred, denkst du..."
        (r',\s*(?:ai\s*fred|aifred|alfred|eifred)\s*,', False),
        # End of sentence: "..., Alfred?" / "Was sagst du, Alfred?" / "..., Alfred!"
        (r',\s*(?:ai\s*fred|aifred|alfred|eifred)\s*[.?!]?\s*$', False),
        # Standalone at end after period: "... machen. Alfred." / "... Alfred!"
        (r'[.!?]\s*(?:ai\s*fred|aifred|alfred|eifred)\s*[.!?]?\s*$', False),
        # Vocative phrases: "mein lieber Alfred" / "lieber Alfred" (anywhere in text)
        (r'\b(?:mein\s+)?liebe[rn]?\s+(?:ai\s*fred|aifred|alfred|eifred)\b', False),
    ]

    for pattern, remove_prefix in alfred_patterns:
        match = re.search(pattern, text_lower)
        if match:
            if remove_prefix:
                cleaned = text[match.end():].strip()
                if cleaned and cleaned[0].islower():
                    cleaned = cleaned[0].upper() + cleaned[1:]
                return ("alfred", cleaned if cleaned else text)
            else:
                return ("alfred", text)

    # No addressing detected
    return (None, text)
