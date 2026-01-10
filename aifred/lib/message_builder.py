"""
Message Builder - Centralized LLM History to Messages Conversion

Converts llm_history (List[Dict]) to Ollama Messages format.
All LLM calls use llm_history exclusively (not chat_history).
"""

import re
from typing import List, Dict, Optional
from datetime import datetime

from .prompt_loader import get_user_name

# Multi-Agent Marker → Speaker Labels
# Used to identify which agent wrote a message in the chat history
AGENT_MARKERS = {
    "🏛️": "SOKRATES",
    "🎩": "AIFRED",
    # Extensible for additional agents
}

# ============================================================
# CENTRAL TIMING PATTERNS (Single Source of Truth)
# ============================================================
# Format: "*( Label: Time    tok/s    Source: ... )*" (italic, in parentheses)
# These patterns are stripped from LLM history to prevent imitation
TIMING_PATTERNS = (
    "*( STT:",           # Speech-to-Text time
    "*( Agent:",         # Agent Research time
    "*( Inference:",     # LLM Inference time
    "*( TTFT:",          # Time To First Token
    "*( Vision:",        # Vision-LLM time
    "*( TTS:",           # Text-to-Speech time
    "*( Decision:",      # Automatik Decision time
    "*( Cache-Hit:",     # Cache Hit time
)


def _clean_content(content: str, strip_img_markers: bool = True) -> str:
    """
    Central content cleaning function (Single Source of Truth).

    Removes all metadata and formatting that should not go to the LLM:
    - Multi-Agent markers → Speaker labels (🏛️[...] → [SOKRATES]: )
    - Raw thinking blocks (<think>...</think>)
    - Formatted thinking collapsibles (<details>...</details>)
    - Metadata spans (<span style="...">...</span>)
    - Timing patterns (*( Inference: ... )*)
    - [IMG:...] markers (optional)
    - Multiple blank lines → single blank line

    Args:
        content: Raw content string
        strip_img_markers: Whether to remove [IMG:...] markers (default: True)

    Returns:
        Cleaned content suitable for LLM context
    """
    if not content:
        return ""

    clean = content

    # 1. Transform Multi-Agent markers to speaker labels
    clean = re.sub(r'^🏛️\[[^\]]+\]', '[SOKRATES]: ', clean)
    clean = re.sub(r'^🎩\[[^\]]+\]', '[AIFRED]: ', clean)
    clean = re.sub(r'^👑\[[^\]]+\]', '[SALOMO]: ', clean)

    # 2. Remove thinking blocks - both raw <think> tags AND formatted <details>
    clean = re.sub(r'<think>.*?</think>', '', clean, flags=re.DOTALL)
    clean = re.sub(r'<details[^>]*>.*?</details>', '', clean, flags=re.DOTALL)

    # 3. Remove metadata spans (<span style="...">( Inference: ... )</span>)
    clean = re.sub(r'<span[^>]*>\s*\([^)]+\)\s*</span>', '', clean, flags=re.DOTALL)

    # 4. Remove text timing patterns (fallback if HTML missing)
    for pattern in TIMING_PATTERNS:
        if pattern in clean:
            clean = clean.split(pattern)[0]

    # 5. Remove [IMG:...] markers (optional)
    if strip_img_markers:
        clean = re.sub(r'\[IMG:[^\]]*\]', '', clean)

    # 6. Cleanup: Remove multiple blank lines and normalize whitespace
    clean = re.sub(r'\n\n+', '\n\n', clean.strip())

    return clean


def clean_content_for_llm(content: str) -> str:
    """
    Clean content for LLM history storage.

    This is a public wrapper around _clean_content() for external callers.
    Uses the central cleaning function to ensure consistency.

    Removes:
    - Thinking collapsibles (<details>...</details>)
    - Raw thinking blocks (<think>...</think>)
    - Metadata spans (<span style="...">...</span>)
    - Timing patterns (*( Inference: ... )*)
    - [IMG:...] markers
    - Multi-agent markers (transforms to speaker labels)

    Args:
        content: Raw content (may contain HTML, metadata, etc.)

    Returns:
        Cleaned content suitable for LLM context
    """
    return _clean_content(content, strip_img_markers=True)


def build_messages_from_llm_history(
    llm_history: List[Dict[str, str]],
    current_user_text: str = "",
    perspective: str = "aifred"  # REQUIRED: "sokrates", "aifred", "salomo", "observer"
) -> List[Dict[str, str]]:
    """
    Build LLM messages directly from llm_history (v2.13.0+).

    This is the ONLY function for building LLM messages.
    llm_history is already in the correct format - no parsing or cleaning needed!

    Advantages:
    - No regex parsing needed (llm_history is pre-cleaned)
    - No marker detection (speaker labels already applied)
    - Fast and reliable
    - Summaries already as system messages
    - All labels preserved for agent identification

    Args:
        llm_history: List of {"role": "user/assistant/system", "content": "..."}
        current_user_text: Current user message to append
        perspective: REQUIRED - Agent perspective for role transformation
            - "aifred": AIfred speaking - his messages as 'assistant', others as 'user'
            - "sokrates": Sokrates speaking - his messages as 'assistant', others as 'user'
            - "salomo": Salomo speaking - his messages as 'assistant', others as 'user'
            - "observer": Neutral observer - all as 'user' with labels

    Returns:
        list: Messages in Ollama format [{"role": "...", "content": "..."}, ...]

    Note:
        All agent labels ([AIFRED]:, [SOKRATES]:, [SALOMO]:) are preserved in the content.
        This allows agents to reference each other's statements.
    """
    if not llm_history:
        messages = []
    else:
        # Multi-Agent perspective transformation
        messages = []
        perspective_lower = perspective.lower()
        user_label = get_user_name() or "USER"

        for msg in llm_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                # System messages (summaries) stay as system
                messages.append({"role": "system", "content": content})
                continue

            # Detect speaker from content labels
            # ALL agent responses have labels: [AIFRED]:, [SOKRATES]:, [SALOMO]:
            is_sokrates = content.startswith("[SOKRATES]:")
            is_aifred = content.startswith("[AIFRED]:")
            is_salomo = content.startswith("[SALOMO]:")
            is_user = role == "user" and not (is_sokrates or is_aifred or is_salomo)

            if perspective_lower == "observer":
                # Observer sees everything as 'user' with labels
                if is_user:
                    messages.append({"role": "user", "content": f"[{user_label}]: {content}"})
                else:
                    # All agent messages as 'user' (keep their labels)
                    messages.append({"role": "user", "content": content})

            elif perspective_lower == "sokrates":
                if is_sokrates:
                    # Sokrates sees his own messages as 'assistant' (label preserved)
                    messages.append({"role": "assistant", "content": content})
                elif is_user:
                    messages.append({"role": "user", "content": f"[{user_label}]: {content}"})
                else:
                    # Others (AIfred, Salomo) as 'user' (keep their labels)
                    messages.append({"role": "user", "content": content})

            elif perspective_lower == "aifred":
                if is_aifred:
                    # AIfred sees his own messages as 'assistant' (label preserved)
                    messages.append({"role": "assistant", "content": content})
                elif is_user:
                    messages.append({"role": "user", "content": f"[{user_label}]: {content}"})
                else:
                    # Others (Sokrates, Salomo) as 'user' (keep their labels)
                    messages.append({"role": "user", "content": content})

            elif perspective_lower == "salomo":
                if is_salomo:
                    # Salomo sees his own messages as 'assistant' (label preserved)
                    messages.append({"role": "assistant", "content": content})
                elif is_user:
                    messages.append({"role": "user", "content": f"[{user_label}]: {content}"})
                else:
                    # Others (Sokrates, AIfred) as 'user' (keep their labels)
                    messages.append({"role": "user", "content": content})

            else:
                # Unknown perspective - use as-is
                messages.append(msg.copy())

    # Add current user message if provided
    if current_user_text:
        # Add personality reminder as prefix (v2.15.15+)
        # Reinforces agent's speech style in long conversations
        from .prompt_loader import load_personality_reminder, get_language

        # Determine agent name: perspective if set, otherwise "aifred" (default)
        agent_name = perspective.lower() if perspective else "aifred"
        if agent_name == "observer":
            agent_name = "salomo"  # Observer is Salomo's perspective

        reminder = load_personality_reminder(agent_name, lang=get_language())
        if reminder:
            current_user_text = f"{reminder}\n\n{current_user_text}"

        messages.append({"role": "user", "content": current_user_text})

    return messages


def build_system_prompt(language: str = "de") -> Dict[str, str]:
    """
    Build system prompt with current date and time

    This ensures the LLM knows the current date/time for temporal queries
    like "aktuelle Ereignisse", "neueste News", etc.

    Args:
        language: "de" or "en" (default: "de")

    Returns:
        dict: {'role': 'system', 'content': '...'}

    Examples:
        >>> prompt = build_system_prompt("de")
        >>> "Aktuelles Datum" in prompt['content']
        True
    """
    now = datetime.now()

    if language == "de":
        date_str = now.strftime("%d.%m.%Y")  # 15.11.2025
        time_str = now.strftime("%H:%M")     # 14:30
        weekday = now.strftime("%A")         # Monday

        # Translate weekday to German
        weekday_map = {
            "Monday": "Montag", "Tuesday": "Dienstag", "Wednesday": "Mittwoch",
            "Thursday": "Donnerstag", "Friday": "Freitag",
            "Saturday": "Samstag", "Sunday": "Sonntag"
        }
        weekday_de = weekday_map.get(weekday, weekday)

        content = f"""Du bist ein hilfreicher AI-Assistent.

WICHTIGE ZEITANGABEN:
- Aktuelles Datum: {weekday_de}, {date_str}
- Aktuelle Uhrzeit: {time_str} Uhr
- Jahr: {now.year}

Nutze diese Informationen für zeitbezogene Fragen (z.B. "Was ist heute?", "Welches Jahr haben wir?", "Aktuelle Ereignisse")."""

    else:  # English
        date_str = now.strftime("%Y-%m-%d")  # 2025-11-15
        time_str = now.strftime("%H:%M")     # 14:30
        weekday = now.strftime("%A")         # Monday

        content = f"""You are a helpful AI assistant.

IMPORTANT TIME INFORMATION:
- Current date: {weekday}, {date_str}
- Current time: {time_str}
- Year: {now.year}

Use this information for time-related queries (e.g., "What's today's date?", "What year is it?", "Current events")."""

    return {'role': 'system', 'content': content}


def inject_rag_context(
    messages: List[Dict[str, str]],
    rag_context: str,
    position: int = -1
) -> None:
    """
    Inject RAG context as system message into messages list.

    Modifies the list in-place by inserting a system message with
    previously researched context.

    Args:
        messages: List of message dicts to modify
        rag_context: The RAG context string to inject
        position: Where to insert (-1 = before last message, i.e., before user's question)

    Example:
        >>> messages = [{"role": "system", "content": "..."}, {"role": "user", "content": "Frage"}]
        >>> inject_rag_context(messages, "Recherche-Ergebnisse hier")
        >>> len(messages)
        3  # System message was inserted
    """
    rag_system_message = {
        'role': 'system',
        'content': f"""
ADDITIONAL CONTEXT FROM PREVIOUS RESEARCH:

{rag_context}

Use this information IN ADDITION to your training knowledge when relevant to the current question.
"""
    }
    messages.insert(position, rag_system_message)


def inject_vision_json_context(
    messages: List[Dict[str, str]],
    vision_json: dict,
    position: int = -1
) -> None:
    """
    Inject Vision JSON context as system message into messages list.

    Modifies the list in-place by inserting a system message with
    extracted image data.

    Args:
        messages: List of message dicts to modify
        vision_json: The extracted JSON from Vision-LLM
        position: Where to insert (-1 = before last message)

    Example:
        >>> messages = [{"role": "user", "content": "Was steht im Bild?"}]
        >>> inject_vision_json_context(messages, {"text": "Hello World"})
        >>> len(messages)
        2  # Vision context was inserted
    """
    import json

    vision_system_message = {
        'role': 'system',
        'content': f"""PREVIOUS IMAGE EXTRACTION (STRUCTURED DATA):

```json
{json.dumps(vision_json, ensure_ascii=False, indent=2)}
```

This data was extracted from an image. Use it for your answer."""
    }
    messages.insert(position, vision_system_message)
