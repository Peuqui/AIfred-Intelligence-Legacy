"""
Intent Detector - Query Intent Classification

Classifies user queries for adaptive temperature selection:
- FAKTISCH: Factual queries (low temperature)
- KREATIV: Creative queries (high temperature)
- GEMISCHT: Mixed queries (medium temperature)

Also detects dialog addressing (who is being spoken to):
- aifred: User is directly addressing AIfred
- sokrates: User is directly addressing Sokrates
- salomo: User is directly addressing Salomo
- None: No specific addressee
"""

from typing import Optional, Dict, Tuple
from .logging_utils import log_message
from .prompt_loader import get_intent_detection_prompt, get_followup_intent_prompt
from .config import AUTOMATIK_LLM_NUM_CTX


def parse_intent_addressee_language(
    response_raw: str,
    context: str = "general"
) -> Tuple[str, Optional[str], str]:
    """
    Extract intent, addressee, and language from LLM response.

    Expected format: "INTENT|ADDRESSEE|LANGUAGE" (e.g., "FAKTISCH|sokrates|DE", "KREATIV||EN")

    Args:
        response_raw: Raw LLM response
        context: Context for logging ("general" or "cache_followup")

    Returns:
        Tuple[str, Optional[str], str]: (intent, addressee, language)
            - intent: "FAKTISCH", "KREATIV" or "GEMISCHT"
            - addressee: "aifred", "sokrates", "salomo" or None
            - language: "de" or "en"
    """
    raw = response_raw.strip()

    # Parse pipe-separated format: INTENT|ADDRESSEE|LANGUAGE
    parts = raw.split("|") if "|" in raw else [raw]

    intent_part = parts[0].strip().upper() if len(parts) > 0 else ""
    addressee_part = parts[1].strip().lower() if len(parts) > 1 else ""
    language_part = parts[2].strip().upper() if len(parts) > 2 else ""

    # Parse intent (with English/German support)
    if "FAKTISCH" in intent_part or "FACTUAL" in intent_part:
        intent = "FAKTISCH"
    elif "KREATIV" in intent_part or "CREATIVE" in intent_part:
        intent = "KREATIV"
    elif "GEMISCHT" in intent_part or "MIXED" in intent_part:
        intent = "GEMISCHT"
    else:
        prefix = "Cache-Intent" if context == "cache_followup" else "Intent"
        log_message(f"⚠️ {prefix} unknown: '{response_raw}' → Default: FAKTISCH")
        intent = "FAKTISCH"

    # Parse addressee
    addressee: Optional[str] = None
    if addressee_part:
        # Normalize variations
        if addressee_part in ("aifred", "alfred", "eifred", "ai fred"):
            addressee = "aifred"
        elif addressee_part in ("sokrates", "socrates"):
            addressee = "sokrates"
        elif addressee_part in ("salomo", "solomon"):
            addressee = "salomo"
        # else: leave as None (unknown or empty)

    # Parse language (default to "en" for universal prompts)
    if language_part in ("DE", "DEUTSCH", "GERMAN"):
        language = "de"
    else:
        # EN, ENGLISH, or anything else → English (universal prompts)
        language = "en"

    return (intent, addressee, language)


def parse_intent_and_addressee(
    response_raw: str,
    context: str = "general"
) -> Tuple[str, Optional[str]]:
    """
    Extract intent and addressee from LLM response (legacy wrapper).

    For backwards compatibility. Use parse_intent_addressee_language() instead.

    Returns:
        Tuple[str, Optional[str]]: (intent, addressee)
    """
    intent, addressee, _ = parse_intent_addressee_language(response_raw, context)
    return (intent, addressee)


# Keep old function for backwards compatibility (used by cache_followup)
def parse_intent_from_response(intent_raw: str, context: str = "general") -> str:
    """
    Extract intent from LLM response (legacy wrapper).

    Args:
        intent_raw: Raw LLM response
        context: Context for logging ("general" or "cache_followup")

    Returns:
        str: "FAKTISCH", "KREATIV" or "GEMISCHT"
    """
    intent, _ = parse_intent_and_addressee(intent_raw, context)
    return intent


async def detect_query_intent_and_addressee(
    user_query: str,
    automatik_model: str,
    llm_client,
    llm_options: Optional[Dict] = None
) -> Tuple[str, Optional[str], str, str]:
    """
    Detect intent, addressee, and language of user query.

    Combines intent detection (for temperature selection), addressee
    detection (for dialog routing), and language detection (for prompt selection)
    in a single LLM call.

    Args:
        user_query: User question
        automatik_model: LLM for intent detection
        llm_client: LLMClient instance
        llm_options: Optional Dict with enable_thinking toggle

    Returns:
        Tuple[str, Optional[str], str, str]: (intent, addressee, detected_language, raw_response)
            - intent: "FAKTISCH", "KREATIV" or "GEMISCHT"
            - addressee: "aifred", "sokrates", "salomo" or None
            - detected_language: "de" or "en" (LLM-detected from user query)
            - raw_response: Raw LLM output for debugging
    """
    # Use English prompt for intent detection (universal, handles all languages)
    prompt = get_intent_detection_prompt(user_query=user_query, lang="en")

    try:
        log_message(f"🎯 Intent+Addressee+Language detection for query: {user_query[:60]}...")

        intent_options = {
            'temperature': 0.2,  # Low for consistent detection
            'num_ctx': AUTOMATIK_LLM_NUM_CTX,  # Explicit 4K context
            'num_predict': 32,  # Short: "FAKTISCH|sokrates|DE" = ~10 tokens
            'enable_thinking': False  # Fast detection without reasoning
        }

        log_message("🧠 Intent enable_thinking: False (Automatik-Task)")

        response = await llm_client.chat(
            model=automatik_model,
            messages=[{'role': 'user', 'content': prompt}],
            options=intent_options
        )
        response_raw = response.text

        intent, addressee, detected_language = parse_intent_addressee_language(response_raw, context="general")
        log_message(f"✅ Intent: {intent}, Addressee: {addressee or 'none'}, Language: {detected_language.upper()}, Raw: '{response_raw}'")
        return (intent, addressee, detected_language, response_raw)

    except Exception as e:
        log_message(f"❌ Intent detection error: {e} → Fallback: FAKTISCH, no addressee, EN")
        return ("FAKTISCH", None, "en", "")


async def detect_query_intent(
    user_query: str,
    automatik_model: str,
    llm_client,
    llm_options: Optional[Dict] = None
) -> str:
    """
    Detect intent of user query (legacy wrapper).

    For backwards compatibility. Use detect_query_intent_and_addressee() instead.

    Returns:
        str: "FAKTISCH", "KREATIV" or "GEMISCHT"
    """
    intent, _, _, _ = await detect_query_intent_and_addressee(
        user_query, automatik_model, llm_client, llm_options
    )
    return intent


async def detect_cache_followup_intent(
    original_query: str,
    followup_query: str,
    automatik_model: str,
    llm_client,
    llm_options: Optional[Dict] = None,
    detected_language: str = "de"
) -> str:
    """
    Detect intent of follow-up question to cached research

    Args:
        original_query: Original research question
        followup_query: User's follow-up question
        automatik_model: LLM for intent detection
        llm_client: LLMClient instance
        llm_options: Optional Dict with enable_thinking toggle
        detected_language: Language from Intent Detection ("de" or "en")

    Returns:
        str: "FAKTISCH", "KREATIV" or "GEMISCHT"
    """
    # Use detected_language from Intent Detection (passed from caller)
    detected_user_language = detected_language
    log_message(f"🌐 Cache Followup using language: {detected_user_language.upper()}")

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


