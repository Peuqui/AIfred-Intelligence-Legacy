"""
Message Builder - Centralized History-to-Messages Conversion

Converts Gradio Chat History to Ollama Messages format and
removes timing information from displays.

Before: 6+ duplicated code locations with 10-15 lines each
After: 1 central function with robust pattern matching
"""

import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime


def build_messages_from_history(
    history: List[Tuple[str, str]],
    current_user_text: str,
    max_turns: Optional[int] = None,
    include_summaries: bool = True
) -> List[Dict[str, str]]:
    """
    Convert Gradio History to Ollama Messages format

    Removes timing info, HTML tags and metadata from User and AI messages:
    - Timing patterns: "(STT: 2.5s)", "(Inference: 1.3s)", "(Agent: 45.2s)"
    - HTML metadata: <span style="...">( Inference: ... )</span>
    - Thinking collapsibles: <details>...</details>

    Treats history summaries as system messages:
    - Summary format: ("", "[📊 Compressed: X Messages]\\n{summary}")
    - Becomes: {'role': 'system', 'content': summary}

    Args:
        history: Gradio Chat History [[user_msg, ai_msg], ...]
        current_user_text: Current user message
        max_turns: Optional - Only use last N turns (None = all)
        include_summaries: Include summaries as system messages (default: True)

    Returns:
        list: Ollama Messages format [{'role': 'user', 'content': '...'}, ...]

    Examples:
        >>> history = [
        ...     ["", "[📊 Compressed: 6 Messages]\\nUser asked about weather..."],
        ...     ["Hello (STT: 2.5s)", "Hi! (Inference: 1.3s)"],
        ...     ["What is 2+2? (Agent: 45.2s)", "4 (Inference: 0.8s)"]
        ... ]
        >>> msgs = build_messages_from_history(history, "Thanks!")
        >>> msgs[0]
        {'role': 'system', 'content': '[📊 Compressed: 6 Messages]\\nUser asked about weather...'}
    """
    messages = []

    # List of all known timing patterns (robust against new patterns)
    # Format: "*( Label: Time    tok/s    Source: ... )*" (italic, in parentheses)
    timing_patterns = [
        "*( STT:",           # Speech-to-Text time
        "*( Agent:",         # Agent Research time
        "*( Inference:",     # LLM Inference time
        "*( Vision:",        # Vision-LLM time
        "*( TTS:",           # Text-to-Speech time
        "*( Decision:",      # Automatik Decision time
        "*( Cache-Hit:",     # Cache Hit time
    ]

    # Limit history if desired (e.g., only last 3 turns)
    history_to_process = history[-max_turns:] if max_turns else history

    # Process history
    for user_turn, ai_turn in history_to_process:
        # Detect summary entries: ("", "[📊 Compressed: ...")
        is_summary = (user_turn == "" and
                     ai_turn.startswith("[📊 Compressed:") and
                     include_summaries)

        if is_summary:
            # Add summary as system message
            messages.append({'role': 'system', 'content': ai_turn})
            continue

        # Clean normal User/AI messages
        # Clean user message
        clean_user = user_turn
        for pattern in timing_patterns:
            if pattern in clean_user:
                # Cut everything from the first timing pattern
                clean_user = clean_user.split(pattern)[0]

        # Clean AI message (remove HTML tags AND text metadata)
        clean_ai = ai_turn

        # 1. Remove thinking collapsibles (<details>...</details>)
        clean_ai = re.sub(r'<details[^>]*>.*?</details>', '', clean_ai, flags=re.DOTALL)

        # 2. Remove metadata spans (<span style="...">( Inference: ... )</span>)
        clean_ai = re.sub(r'<span[^>]*>\s*\([^)]+\)\s*</span>', '', clean_ai, flags=re.DOTALL)

        # 3. Fallback: Remove remaining text metadata (if HTML tags missing)
        for pattern in timing_patterns:
            if pattern in clean_ai:
                # Cut everything from the first timing pattern
                clean_ai = clean_ai.split(pattern)[0]

        # 4. Cleanup: Remove multiple blank lines and whitespace
        clean_ai = re.sub(r'\n\n+', '\n\n', clean_ai.strip())

        # Add cleaned messages
        messages.extend([
            {'role': 'user', 'content': clean_user},
            {'role': 'assistant', 'content': clean_ai}
        ])

    # Add current user message
    messages.append({'role': 'user', 'content': current_user_text})

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
