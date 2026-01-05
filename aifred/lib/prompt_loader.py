"""
Prompt Loader Module with i18n Support

Loads prompts from language-specific directories (de/ or en/).
Language is detected by LLM-based Intent Detection (see intent_detector.py).
No fallbacks - prompts must exist in both languages.

Personality System (v2.15.3+):
- Each agent has a personality.txt file with their speech style
- Personality can be toggled on/off per agent via settings
- When enabled, personality is appended after identity + task prompts
"""

from pathlib import Path
from typing import Optional

# Base directory for prompts (relative to project root)
PROMPTS_DIR = Path(__file__).parent.parent.parent / 'prompts'

# Global language setting (synced with UI language)
_current_language = "de"  # "de" or "en" (synced from ui_language)

# Global user name (set once when settings are loaded)
_current_user_name = ""

# Global user gender for salutation (male/female)
_current_user_gender = "male"

# Global personality toggle states (loaded from settings)
_personality_enabled = {
    "aifred": True,
    "sokrates": True,
    "salomo": True
}

# Cache for system prompt token counts (populated at startup)
# Format: {"aifred": {"de": tokens, "en": tokens}, "sokrates": {...}, ...}
_system_prompt_token_cache: dict[str, dict[str, int]] = {}


def set_user_name(name: str):
    """Set the global user name for prompts"""
    global _current_user_name
    _current_user_name = name.strip() if name else ""


def get_user_name() -> str:
    """Get the current user name"""
    return _current_user_name


def set_user_gender(gender: str):
    """Set the global user gender for salutation (male/female)"""
    global _current_user_gender
    _current_user_gender = gender if gender in ("male", "female") else "male"


def get_user_gender() -> str:
    """Get the current user gender"""
    return _current_user_gender


def get_salutation() -> str:
    """
    Get proper salutation based on user name and gender.

    Returns:
        - "Herr {name}" / "Mr. {name}" for male
        - "Frau {name}" / "Ms. {name}" for female
        - Empty string if no name set
    """
    if not _current_user_name:
        return ""

    if _current_language == "de":
        title = "Herr" if _current_user_gender == "male" else "Frau"
    else:
        title = "Mr." if _current_user_gender == "male" else "Ms."

    return f"{title} {_current_user_name}"


def set_personality_enabled(agent: str, enabled: bool):
    """
    Set personality toggle state for an agent.

    Args:
        agent: Agent name ("aifred", "sokrates", "salomo")
        enabled: True to enable personality style, False for factual responses
    """
    global _personality_enabled
    if agent in _personality_enabled:
        _personality_enabled[agent] = enabled


def get_personality_enabled(agent: str) -> bool:
    """
    Get personality toggle state for an agent.

    Args:
        agent: Agent name ("aifred", "sokrates", "salomo")

    Returns:
        True if personality is enabled, False otherwise
    """
    return _personality_enabled.get(agent, True)


def sync_personality_from_settings():
    """
    Sync personality toggle states from settings.json.

    Called at startup and when settings change.
    """
    global _personality_enabled
    from .settings import load_settings

    settings = load_settings() or {}
    _personality_enabled["aifred"] = settings.get("aifred_personality", True)
    _personality_enabled["sokrates"] = settings.get("sokrates_personality", True)
    _personality_enabled["salomo"] = settings.get("salomo_personality", True)


def load_identity(agent: str, lang: Optional[str] = None) -> str:
    """
    Load identity prompt for an agent (always loaded).

    Identity defines WHO the agent is - this is always included,
    regardless of personality toggle state.

    If user name and gender are set, appends proper salutation info.

    Args:
        agent: Agent name ("aifred", "sokrates", "salomo")
        lang: Language code, defaults to current language

    Returns:
        Identity prompt text, or empty string if not found
    """
    if lang is None:
        lang = _current_language

    identity_file = PROMPTS_DIR / lang / agent / "identity.txt"

    if not identity_file.exists():
        return ""

    with open(identity_file, 'r', encoding='utf-8') as f:
        identity = f.read().strip()

    return identity


def load_personality(agent: str, lang: Optional[str] = None) -> str:
    """
    Load personality prompt for an agent.

    Personality defines HOW the agent speaks (style) - this is optional
    and can be toggled on/off via settings.

    Args:
        agent: Agent name ("aifred", "sokrates", "salomo")
        lang: Language code, defaults to current language

    Returns:
        Personality prompt text, or empty string if not found/disabled
    """
    if not get_personality_enabled(agent):
        return ""

    if lang is None:
        lang = _current_language

    personality_file = PROMPTS_DIR / lang / agent / "personality.txt"

    if not personality_file.exists():
        return ""

    with open(personality_file, 'r', encoding='utf-8') as f:
        return f.read().strip()


def load_personality_reminder(agent: str, lang: Optional[str] = None) -> str:
    """
    Load short personality reminder for user-message prefix.

    Used to remind the LLM of the agent's speech style in long conversations,
    where the system prompt is far from the current question.

    Args:
        agent: Agent name ("aifred", "sokrates", "salomo")
        lang: Language code, defaults to current language

    Returns:
        Short reminder text (e.g., "[STIL: Britischer Butler]"), or empty string
    """
    if not get_personality_enabled(agent):
        return ""

    if lang is None:
        lang = _current_language

    reminder_file = PROMPTS_DIR / lang / agent / "reminder.txt"

    if not reminder_file.exists():
        return ""

    with open(reminder_file, 'r', encoding='utf-8') as f:
        return f.read().strip()


def set_language(lang: str):
    """
    Set the global language for prompts.

    This is synced with ui_language from state.py.

    Args:
        lang: "de" or "en"
    """
    global _current_language
    if lang in ["de", "en"]:
        _current_language = lang
    else:
        raise ValueError(f"Unsupported language: {lang}. Use 'de' or 'en'")


def get_language() -> str:
    """Get the current language setting"""
    return _current_language


def load_prompt(
    prompt_name: str,
    lang: Optional[str] = None,
    user_text: Optional[str] = None,
    **kwargs
) -> str:
    """
    Load a prompt from a file with language support.

    Provides automatic placeholder replacement for date/time values:
    - {current_year} → "2025"
    - {current_date} → "Montag, 02.01.2025" (DE) or "Monday, 2025-01-02" (EN)
    - {current_time} → "14:30:45"
    - {current_weekday} → "Montag" (DE) or "Monday" (EN)
    - {user_name} → User's configured name (if set)

    Args:
        prompt_name: Name of the prompt file (without .txt extension)
        lang: Language override ("de" or "en", or None for current setting)
        user_text: User text (passed through to kwargs for template formatting)
        **kwargs: Keyword arguments for string formatting

    Returns:
        Formatted prompt string with placeholders replaced

    Raises:
        FileNotFoundError: If prompt file doesn't exist
        KeyError: If required placeholders are missing
    """
    from datetime import datetime

    # Determine language
    if lang is None:
        lang = _current_language

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
    # BUILD STANDARD PLACEHOLDERS (date/time/user)
    # ============================================================
    now = datetime.now()

    # German weekday translation
    weekday_map = {
        "Monday": "Montag", "Tuesday": "Dienstag", "Wednesday": "Mittwoch",
        "Thursday": "Donnerstag", "Friday": "Freitag",
        "Saturday": "Samstag", "Sunday": "Sonntag"
    }

    if lang == "de":
        weekday = weekday_map.get(now.strftime("%A"), now.strftime("%A"))
        current_date = f"{weekday}, {now.strftime('%d.%m.%Y')}"
    else:
        weekday = now.strftime("%A")
        current_date = f"{weekday}, {now.strftime('%Y-%m-%d')}"

    # Standard placeholders - always available
    standard_placeholders = {
        'current_year': now.strftime('%Y'),
        'current_date': current_date,
        'current_time': now.strftime('%H:%M:%S'),
        'current_weekday': weekday,
        'user_name': _current_user_name if _current_user_name else "",
        'user_salutation': get_salutation(),  # "Herr Name" / "Frau Name" / ""
    }

    # Merge standard placeholders with kwargs (kwargs override standard)
    all_placeholders = {**standard_placeholders, **kwargs}

    # Merge user_text into placeholders if not already there
    if user_text and 'user_text' not in all_placeholders:
        all_placeholders['user_text'] = user_text

    # Format prompt with all placeholders
    try:
        return prompt_template.format(**all_placeholders)
    except KeyError as e:
        raise KeyError(
            f"Missing placeholder in prompt '{prompt_name}': {e}\n"
            f"Provided kwargs: {list(kwargs.keys())}\n"
            f"Standard placeholders: {list(standard_placeholders.keys())}"
        )


def list_available_prompts() -> list:
    """
    List all available prompts across all languages

    Returns:
        List of all available prompt names (without .txt)
    """
    if not PROMPTS_DIR.exists():
        return []

    prompts: set[str] = set()

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


def get_research_decision_prompt(
    user_text: str,
    has_images: bool = False,
    vision_json: Optional[dict] = None,
    lang: Optional[str] = None
) -> str:
    """
    Load combined research decision prompt (Decision-Making + Query-Optimization).

    This consolidates two LLM calls into one:
    1. Decides if web research is needed
    2. If yes, generates 3 optimized search queries

    Output format is JSON:
    - {"web": false} if no research needed
    - {"web": true, "queries": ["q1", "q2", "q3"]} if research needed

    Args:
        user_text: User query text
        has_images: Whether the message includes image(s)
        vision_json: Structured data extracted from images by Vision-LLM
        lang: Language override

    Returns:
        Formatted research decision prompt
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
        'research_decision',
        lang=lang,
        user_text=user_text,
        image_context=image_context,
        vision_json_context=vision_json_context
    )


def get_followup_intent_prompt(original_query: str, followup_query: str, lang: Optional[str] = None) -> str:
    """Load followup intent detection prompt"""
    return load_prompt(
        'followup_intent_detection',
        lang=lang,
        original_query=original_query,
        followup_query=followup_query
    )


def _merge_prompt_layers(agent: str, task_prompt: str, lang: Optional[str] = None) -> str:
    """
    Merge prompt layers in correct order: Identity + Personality + Task.

    This is the core 3-layer prompt system:
    1. Identity (WHO am I) - always loaded
    2. Personality (HOW do I speak) - toggleable via settings
    3. Task prompt (WHAT should I do) - situational

    Args:
        agent: Agent name ("aifred", "sokrates", "salomo")
        task_prompt: The task-specific prompt (already loaded with timestamp)
        lang: Language code (de/en), defaults to current language

    Returns:
        Merged prompt string with all applicable layers
    """
    parts = []

    # Layer 1: Identity (always)
    identity = load_identity(agent, lang)
    if identity:
        parts.append(identity)

    # Layer 2: Task prompt (always)
    parts.append(task_prompt)

    # Layer 3: Personality (if enabled) - LAST so LLM prioritizes it!
    # LLMs tend to follow instructions at the end more strongly.
    personality = load_personality(agent, lang)
    if personality:
        parts.append(personality)

    return "\n\n".join(parts)


def get_aifred_system_minimal(lang: Optional[str] = None) -> str:
    """
    Load AIfred minimal system prompt with 3-layer merging.

    Layers: Identity + Personality (if enabled) + Task prompt

    Args:
        lang: Language code (de/en), defaults to current language

    Returns:
        AIfred system prompt (identity + optional style + task instructions)
    """
    task_prompt = load_prompt('aifred/system_minimal', lang=lang)
    return _merge_prompt_layers("aifred", task_prompt, lang)


def get_system_rag_prompt(context: str, user_text: str = "", lang: Optional[str] = None) -> str:
    """
    Load system RAG prompt with 3-layer merging.

    Layers: Identity + Personality (if enabled) + RAG task prompt
    """
    task_prompt = load_prompt(
        'aifred/system_rag',
        lang=lang,
        user_text=user_text,
        context=context
    )
    return _merge_prompt_layers("aifred", task_prompt, lang)


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

    prompt_file = PROMPTS_DIR / lang / "cache_metadata.txt"
    with open(prompt_file, 'r', encoding='utf-8') as f:
        template = f.read().strip()

    return template.format(sources_preview=sources_preview)


# ============================================================
# Sokrates Multi-Agent Prompts
# ============================================================

def get_sokrates_system_minimal(lang: Optional[str] = None) -> str:
    """
    Load Sokrates minimal system prompt with 3-layer merging.

    Layers: Identity + Personality (if enabled) + Task prompt

    Args:
        lang: Language code (de/en), defaults to current language

    Returns:
        Sokrates system prompt (identity + optional style + task instructions)
    """
    task_prompt = load_prompt('sokrates/system_minimal', lang=lang)
    return _merge_prompt_layers("sokrates", task_prompt, lang)


def get_sokrates_critic_prompt(round_num: int = 1, lang: Optional[str] = None) -> str:
    """
    Load Sokrates Critic prompt for User-as-Judge and Auto-Consensus modes.

    Args:
        round_num: Current debate round (1, 2, 3, ...)
        lang: Language code (de/en), defaults to current language

    Returns:
        Sokrates critic system prompt with timestamp prefix and round number
    """
    return load_prompt('sokrates/critic', lang=lang, round_num=round_num)


def get_sokrates_devils_advocate_prompt(lang: Optional[str] = None) -> str:
    """
    Load Sokrates Devil's Advocate prompt for Pro/Contra analysis.

    Args:
        lang: Language code (de/en), defaults to current language

    Returns:
        Sokrates devil's advocate system prompt with timestamp prefix
    """
    return load_prompt('sokrates/devils_advocate', lang=lang)


def get_aifred_refinement_prompt(
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
        Formatted refinement prompt with critique and timestamp prefix
    """
    return load_prompt(
        'aifred/refinement',
        lang=lang,
        critique=critique,
        user_interjection=user_interjection
    )


# Backwards compatibility alias
get_sokrates_refinement_prompt = get_aifred_refinement_prompt


def get_sokrates_direct_prompt(lang: Optional[str] = None) -> str:
    """
    Load Sokrates Direct Response prompt with 3-layer merging.

    Layers: Identity + Personality (if enabled) + Direct task prompt

    Args:
        lang: Language code (de/en), defaults to current language

    Returns:
        Sokrates direct response system prompt (identity + optional style + task)
    """
    task_prompt = load_prompt('sokrates/direct', lang=lang)
    return _merge_prompt_layers("sokrates", task_prompt, lang)


def get_aifred_direct_prompt(lang: Optional[str] = None) -> str:
    """
    Load AIfred Direct Response prompt with 3-layer merging.

    Layers: Identity + Personality (if enabled) + Direct task prompt

    Args:
        lang: Language code (de/en), defaults to current language

    Returns:
        AIfred direct response system prompt (identity + optional style + task)
    """
    task_prompt = load_prompt('aifred/direct', lang=lang)
    return _merge_prompt_layers("aifred", task_prompt, lang)


# ============================================================
# Salomo Multi-Agent Prompts
# ============================================================

def get_salomo_direct_prompt(lang: Optional[str] = None) -> str:
    """
    Load Salomo Direct Response prompt with 3-layer merging.

    Layers: Identity + Personality (if enabled) + Direct task prompt

    Args:
        lang: Language code (de/en), defaults to current language

    Returns:
        Salomo direct response system prompt (identity + optional style + task)
    """
    task_prompt = load_prompt('salomo/direct', lang=lang)
    return _merge_prompt_layers("salomo", task_prompt, lang)


def get_salomo_system_minimal(lang: Optional[str] = None) -> str:
    """
    Load Salomo minimal system prompt with 3-layer merging.

    Layers: Identity + Personality (if enabled) + Task prompt

    Args:
        lang: Language code (de/en), defaults to current language

    Returns:
        Salomo system prompt (identity + optional style + task instructions)
    """
    task_prompt = load_prompt('salomo/system_minimal', lang=lang)
    return _merge_prompt_layers("salomo", task_prompt, lang)


def get_salomo_mediator_prompt(round_num: int = 1, lang: Optional[str] = None) -> str:
    """
    Load Salomo Mediator prompt for Auto-Consensus mode (Trialog).

    Salomo synthesizes AIfred's answer and Sokrates' critique,
    and decides whether to give LGTM.

    Args:
        round_num: Current debate round (1, 2, 3, ...)
        lang: Language code (de/en), defaults to current language

    Returns:
        Salomo mediator system prompt with round number
    """
    return load_prompt('salomo/mediator', lang=lang, round_num=round_num)


def get_salomo_judge_prompt(lang: Optional[str] = None) -> str:
    """
    Load Salomo Judge prompt for Tribunal mode.

    Salomo delivers a final verdict after AIfred and Sokrates have debated.

    Args:
        lang: Language code (de/en), defaults to current language

    Returns:
        Salomo judge system prompt
    """
    return load_prompt('salomo/judge', lang=lang)


# ============================================================
# System Prompt Token Cache (v2.14.0+)
# ============================================================

def _estimate_tokens(text: str) -> int:
    """Estimate tokens from text (3.5 chars/token for German/mixed)."""
    return int(len(text) / 3.5) if text else 0


def init_system_prompt_cache() -> dict[str, dict[str, int]]:
    """
    Initialize cache with all system prompt token counts.

    Called once at application startup to pre-calculate all prompt sizes.
    This avoids repeated file reads and token estimations during runtime.

    Returns:
        dict: The populated cache {agent: {lang: tokens}}
    """
    global _system_prompt_token_cache
    from .logging_utils import log_message

    _system_prompt_token_cache = {}

    for lang in ["de", "en"]:
        try:
            # AIfred system prompt (with personality for worst-case token count)
            aifred_prompt = get_aifred_system_minimal(lang=lang)
            if "aifred" not in _system_prompt_token_cache:
                _system_prompt_token_cache["aifred"] = {}
            _system_prompt_token_cache["aifred"][lang] = _estimate_tokens(aifred_prompt)

            # Sokrates system prompt (minimal + personality + critic as worst case)
            sokrates_minimal = get_sokrates_system_minimal(lang=lang)
            sokrates_critic = load_prompt('sokrates/critic', lang=lang, round_num=1)
            sokrates_combined = f"{sokrates_minimal}\n\n{sokrates_critic}"
            if "sokrates" not in _system_prompt_token_cache:
                _system_prompt_token_cache["sokrates"] = {}
            _system_prompt_token_cache["sokrates"][lang] = _estimate_tokens(sokrates_combined)

            # Salomo system prompt (minimal + personality + mediator as worst case)
            salomo_minimal = get_salomo_system_minimal(lang=lang)
            salomo_mediator = load_prompt('salomo/mediator', lang=lang, round_num=1)
            salomo_combined = f"{salomo_minimal}\n\n{salomo_mediator}"
            if "salomo" not in _system_prompt_token_cache:
                _system_prompt_token_cache["salomo"] = {}
            _system_prompt_token_cache["salomo"][lang] = _estimate_tokens(salomo_combined)

        except Exception as e:
            log_message(f"⚠️ Failed to cache prompts for {lang}: {e}")

    # Log cache summary
    for agent, langs in _system_prompt_token_cache.items():
        de_tokens = langs.get("de", 0)
        en_tokens = langs.get("en", 0)
        log_message(f"📊 Prompt cache: {agent} = {de_tokens} tok (de), {en_tokens} tok (en)")

    return _system_prompt_token_cache


def get_system_prompt_tokens(agent: str, lang: str = "de") -> int:
    """
    Get cached system prompt token count for an agent.

    Args:
        agent: Agent name ("aifred", "sokrates", "salomo")
        lang: Language code ("de" or "en")

    Returns:
        int: Cached token count, or 0 if not cached
    """
    if not _system_prompt_token_cache:
        # Cache not initialized - use fallback estimation
        return 0
    return _system_prompt_token_cache.get(agent, {}).get(lang, 0)


def get_max_system_prompt_tokens(multi_agent_mode: str = "standard", lang: str = "de") -> int:
    """
    Get the maximum system prompt tokens for the current mode.

    For compression checks, we need the worst-case (largest) prompt size
    across all agents that will be called.

    Args:
        multi_agent_mode: "standard", "critical_review", "auto_consensus", "tribunal", "devils_advocate"
        lang: Language code ("de" or "en")

    Returns:
        int: Maximum token count across relevant agents
    """
    if not _system_prompt_token_cache:
        return 0

    aifred_tokens = get_system_prompt_tokens("aifred", lang)

    if multi_agent_mode == "standard":
        return aifred_tokens

    sokrates_tokens = get_system_prompt_tokens("sokrates", lang)

    if multi_agent_mode in ["auto_consensus", "tribunal"]:
        salomo_tokens = get_system_prompt_tokens("salomo", lang)
        return max(aifred_tokens, sokrates_tokens, salomo_tokens)

    # critical_review, devils_advocate
    return max(aifred_tokens, sokrates_tokens)