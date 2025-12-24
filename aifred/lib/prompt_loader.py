"""
Prompt Loader Module with i18n Support

Loads prompts from language-specific directories (de/ or en/).
Supports automatic language detection.
No fallbacks - prompts must exist in both languages.
"""

from pathlib import Path
from typing import Optional
import re

# Base directory for prompts (relative to project root)
PROMPTS_DIR = Path(__file__).parent.parent.parent / 'prompts'

# Global language setting (can be overridden)
_current_language = "auto"  # "auto", "de", "en"


def detect_language(text: str) -> str:
    """
    Simple language detection based on keywords

    Args:
        text: Text to analyze

    Returns:
        "en" or "de"
    """
    # Common English indicators
    english_patterns = [
        r'\b(the|is|are|what|where|when|how|why|can|could|would|should)\b',
        r'\b(weather|today|tomorrow|please|thanks|hello)\b',
        r'\b(I|you|he|she|it|we|they|my|your)\b'
    ]

    # Common German indicators
    german_patterns = [
        r'\b(der|die|das|ein|eine|ist|sind|was|wo|wann|wie|warum)\b',
        r'\b(wetter|heute|morgen|bitte|danke|hallo)\b',
        r'\b(ich|du|er|sie|es|wir|ihr|mein|dein)\b',
        r'\b(können|könntest|würde|sollte)\b'
    ]

    text_lower = text.lower()

    # Count matches
    en_score = sum(1 for pattern in english_patterns if re.search(pattern, text_lower, re.IGNORECASE))
    de_score = sum(1 for pattern in german_patterns if re.search(pattern, text_lower, re.IGNORECASE))

    # Default to German if unclear (since AIfred is primarily German)
    return "en" if en_score > de_score else "de"


def set_language(lang: str):
    """
    Set the global language for prompts

    Args:
        lang: "auto", "de", or "en"
    """
    global _current_language
    if lang in ["auto", "de", "en"]:
        _current_language = lang
    else:
        raise ValueError(f"Unsupported language: {lang}. Use 'auto', 'de', or 'en'")


def get_language() -> str:
    """Get the current language setting"""
    return _current_language


def load_prompt(prompt_name: str, lang: Optional[str] = None, user_text: str = None, **kwargs) -> str:
    """
    Load a prompt from a file with language support

    Automatically injects current date/time at the beginning of every prompt.

    Args:
        prompt_name: Name of the prompt file (without .txt extension)
        lang: Language override ("de", "en", or None for current setting)
        user_text: User text for auto-detection (if lang="auto")
        **kwargs: Keyword arguments for string formatting

    Returns:
        Formatted prompt string with timestamp prefix

    Raises:
        FileNotFoundError: If prompt file doesn't exist
        KeyError: If required placeholders are missing
    """
    from datetime import datetime

    # Determine language
    if lang is None:
        lang = _current_language

    if lang == "auto":
        # Need user_text for auto-detection
        if user_text:
            lang = detect_language(user_text)
        elif 'user_text' in kwargs:
            lang = detect_language(kwargs['user_text'])
        else:
            # Default to German if no text to analyze
            lang = "de"

    # Load from language-specific directory only (no fallback)
    prompt_file = PROMPTS_DIR / lang / f"{prompt_name}.txt"

    if not prompt_file.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_file}\n"
            f"Expected language: {lang}\n"
            f"Available prompts: {list_available_prompts()}"
        )

    # Load prompt file
    with open(prompt_file, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    # ============================================================
    # INJECT CURRENT DATE/TIME (always, for all prompts)
    # ============================================================
    now = datetime.now()

    if lang == "de":
        # German weekday translation
        weekday_map = {
            "Monday": "Montag", "Tuesday": "Dienstag", "Wednesday": "Mittwoch",
            "Thursday": "Donnerstag", "Friday": "Freitag",
            "Saturday": "Samstag", "Sunday": "Sonntag"
        }
        weekday_de = weekday_map.get(now.strftime("%A"), now.strftime("%A"))

        timestamp_prefix = f"""AKTUELLES DATUM UND UHRZEIT:
- Datum: {weekday_de}, {now.strftime('%d.%m.%Y')}
- Uhrzeit: {now.strftime('%H:%M:%S')} Uhr

"""
    else:  # English
        timestamp_prefix = f"""CURRENT DATE AND TIME:
- Date: {now.strftime('%A')}, {now.strftime('%Y-%m-%d')}
- Time: {now.strftime('%H:%M:%S')}

"""

    # Prepend timestamp to prompt
    prompt_template = timestamp_prefix + prompt_template

    # Format with kwargs if provided
    if kwargs or user_text:
        try:
            # Merge user_text into kwargs if not already there
            if user_text and 'user_text' not in kwargs:
                kwargs['user_text'] = user_text
            return prompt_template.format(**kwargs)
        except KeyError as e:
            raise KeyError(
                f"Missing placeholder in prompt '{prompt_name}': {e}\n"
                f"Provided kwargs: {list(kwargs.keys())}"
            )

    return prompt_template


def list_available_prompts() -> list:
    """
    List all available prompts across all languages

    Returns:
        List of all available prompt names (without .txt)
    """
    if not PROMPTS_DIR.exists():
        return []

    prompts = set()

    # Check language directories only (no root directory)
    for lang_dir in ['de', 'en']:
        lang_path = PROMPTS_DIR / lang_dir
        if lang_path.exists():
            prompts.update(p.stem for p in lang_path.glob('*.txt'))

    return sorted(list(prompts))


# ============================================================
# Convenience functions for frequently used prompts
# ============================================================

def get_query_optimization_prompt(
    user_text: str,
    lang: Optional[str] = None,
    vision_json: Optional[dict] = None
) -> str:
    """Load query optimization prompt with optional Vision JSON context"""
    # Build Vision JSON context string (same pattern as decision_making_prompt)
    if vision_json:
        import json
        vision_json_context = f"""

STRUKTURIERTE DATEN AUS BILD:
```json
{json.dumps(vision_json, ensure_ascii=False, indent=2)}
```

Diese Daten wurden automatisch aus einem Bild extrahiert."""
    else:
        vision_json_context = ""

    return load_prompt(
        'query_optimization',
        lang=lang,
        user_text=user_text,
        vision_json_context=vision_json_context
    )


def get_decision_making_prompt(
    user_text: str,
    has_images: bool = False,
    vision_json: Optional[dict] = None,
    lang: Optional[str] = None
) -> str:
    """
    Load decision-making prompt with optional image and Vision JSON context

    Args:
        user_text: User query text
        has_images: Whether the message includes image(s)
        vision_json: Structured data extracted from images by Vision-LLM
        lang: Language override

    Returns:
        Formatted decision prompt with timestamp, image context, and Vision JSON context
    """
    # Build image context string
    if has_images:
        if lang == "en":
            image_context = "\n\n⚠️ USER ATTACHED IMAGE(S) - This is an image analysis task!"
        else:  # German (default)
            image_context = "\n\n⚠️ BENUTZER HAT BILD(ER) ANGEHÄNGT - Dies ist eine Bildanalyse-Aufgabe!"
    else:
        image_context = ""

    # Build Vision JSON context string
    if vision_json:
        import json
        vision_json_context = f"""

STRUKTURIERTE DATEN AUS BILD:
```json
{json.dumps(vision_json, ensure_ascii=False, indent=2)}
```

Diese Daten wurden automatisch aus dem Bild extrahiert."""
    else:
        vision_json_context = ""

    return load_prompt(
        'decision_making',
        lang=lang,
        user_text=user_text,
        image_context=image_context,
        vision_json_context=vision_json_context
    )


# Cache decision addon removed - will be replaced with Vector DB semantic search


def get_intent_detection_prompt(user_query: str, lang: Optional[str] = None) -> str:
    """Load intent detection prompt"""
    return load_prompt('intent_detection', lang=lang, user_query=user_query)


def get_followup_intent_prompt(original_query: str, followup_query: str, lang: Optional[str] = None) -> str:
    """Load followup intent detection prompt"""
    return load_prompt(
        'followup_intent_detection',
        lang=lang,
        original_query=original_query,
        followup_query=followup_query
    )


def get_system_rag_prompt(context: str, user_text: str = "", lang: Optional[str] = None) -> str:
    """Load system RAG prompt (timestamp injected automatically by load_prompt)"""
    return load_prompt(
        'system_rag',
        lang=lang,
        user_text=user_text,
        context=context
    )


# Cache metadata prompt removed - will be replaced with Vector DB embeddings


def get_vision_ocr_prompt(lang: Optional[str] = None) -> str:
    """Load Vision-LLM OCR prompt (timestamp injected automatically by load_prompt)"""
    return load_prompt('vision_ocr', lang=lang)


def get_vision_templateless_ocr_prompt(lang: Optional[str] = None) -> str:
    """
    Load Vision-LLM OCR prompt for template-less models (DeepSeek-OCR, etc.)

    Note: No timestamp injection for template-less models (keeps prompt minimal)
    """
    if lang is None:
        lang = _current_language
    if lang == "auto":
        lang = "de"  # Default to German

    prompt_file = PROMPTS_DIR / lang / "vision_templateless_ocr.txt"
    with open(prompt_file, 'r', encoding='utf-8') as f:
        return f.read().strip()


def get_vision_templateless_default_prompt(lang: Optional[str] = None) -> str:
    """
    Load default Vision prompt for template-less models

    Note: No timestamp injection for template-less models (keeps prompt minimal)
    """
    if lang is None:
        lang = _current_language
    if lang == "auto":
        lang = "de"  # Default to German

    prompt_file = PROMPTS_DIR / lang / "vision_templateless_default.txt"
    with open(prompt_file, 'r', encoding='utf-8') as f:
        return f.read().strip()


def get_cache_metadata_prompt(sources_preview: str, lang: Optional[str] = None) -> str:
    """
    Load cache metadata generation prompt.

    Used to generate a concise summary of cached research sources
    for later cache hit decisions.

    Args:
        sources_preview: Preview text of research sources
        lang: Language code (de/en), defaults to current language

    Returns:
        Formatted prompt with sources inserted
    """
    if lang is None:
        lang = _current_language
    if lang == "auto":
        lang = "en"  # Cache metadata is always English for consistency

    prompt_file = PROMPTS_DIR / lang / "cache_metadata.txt"
    with open(prompt_file, 'r', encoding='utf-8') as f:
        template = f.read().strip()

    return template.format(sources_preview=sources_preview)


# ============================================================
# Sokrates Multi-Agent Prompts
# ============================================================

def get_sokrates_critic_prompt(lang: Optional[str] = None) -> str:
    """
    Load Sokrates Critic prompt for User-as-Judge and Auto-Consensus modes.

    Args:
        lang: Language code (de/en), defaults to current language

    Returns:
        Sokrates critic system prompt
    """
    if lang is None:
        lang = _current_language
    if lang == "auto":
        lang = "de"

    prompt_file = PROMPTS_DIR / lang / "sokrates" / "critic.txt"
    with open(prompt_file, 'r', encoding='utf-8') as f:
        return f.read().strip()


def get_sokrates_devils_advocate_prompt(lang: Optional[str] = None) -> str:
    """
    Load Sokrates Devil's Advocate prompt for Pro/Contra analysis.

    Args:
        lang: Language code (de/en), defaults to current language

    Returns:
        Sokrates devil's advocate system prompt
    """
    if lang is None:
        lang = _current_language
    if lang == "auto":
        lang = "de"

    prompt_file = PROMPTS_DIR / lang / "sokrates" / "devils_advocate.txt"
    with open(prompt_file, 'r', encoding='utf-8') as f:
        return f.read().strip()


def get_sokrates_refinement_prompt(
    critique: str,
    user_interjection: str = "",
    lang: Optional[str] = None
) -> str:
    """
    Load AIfred Refinement prompt (when responding to Sokrates' critique).

    Args:
        critique: Sokrates' critique text
        user_interjection: Optional user interjection during debate
        lang: Language code (de/en), defaults to current language

    Returns:
        Formatted refinement prompt with critique inserted
    """
    if lang is None:
        lang = _current_language
    if lang == "auto":
        lang = "de"

    prompt_file = PROMPTS_DIR / lang / "sokrates" / "refinement.txt"
    with open(prompt_file, 'r', encoding='utf-8') as f:
        template = f.read().strip()

    return template.format(
        critique=critique,
        user_interjection=user_interjection
    )