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

from .prompt_loader import get_user_name

# Multi-Agent Marker → Speaker Labels
# Used to identify which agent wrote a message in the chat history
AGENT_MARKERS = {
    "🏛️": "SOKRATES",
    "🎩": "AIFRED",
    # Extensible for additional agents
}


def build_messages_from_history(
    history: List[Tuple[str, str]],
    current_user_text: str = "",
    max_turns: Optional[int] = None,
    include_summaries: bool = True,
    perspective: Optional[str] = None  # "sokrates", "aifred", "salomo", "observer", or None
) -> List[Dict[str, str]]:
    """
    Convert Gradio History to Ollama Messages format

    Removes timing info, HTML tags and metadata from User and AI messages:
    - Timing patterns: "(STT: 2.5s)", "(Inference: 1.3s)", "(Agent: 45.2s)"
    - HTML metadata: <span style="...">( Inference: ... )</span>
    - Thinking collapsibles: <details>...</details>

    Handles three types of history entries:
    1. Normal exchanges: (user_msg, ai_msg) → user + assistant messages
    2. Summaries: ("", "[📊 Compressed: ...]") → system message
    3. Multi-Agent: ("", "🏛️[...]...") or ("", "🎩[...]...") → system message with speaker label

    Speaker attribution (for multi-agent context):
    - Without perspective: Agent entries → system message with [SOKRATES]/[AIFRED] label
    - With perspective="sokrates": Sokrates sees his messages as 'assistant', others as 'user'
    - With perspective="aifred": AIfred sees his messages as 'assistant', others as 'user'

    Args:
        history: Gradio Chat History [[user_msg, ai_msg], ...]
        current_user_text: Current user message
        max_turns: Optional - Only use last N turns (None = all)
        include_summaries: Include summaries as system messages (default: True)
        perspective: Multi-Agent perspective ("sokrates", "aifred", or None)
            - None: Standard mode - all AI responses as 'assistant'
            - "sokrates": Sokrates is speaking - his responses are 'assistant',
                         AIfred's responses become 'user' with [AIFRED]: label
            - "aifred": AIfred is speaking - his responses are 'assistant',
                       Sokrates' responses become 'user' with [SOKRATES]: label

    Returns:
        list: Ollama Messages format [{'role': 'user', 'content': '...'}, ...]

    Examples:
        >>> history = [
        ...     ["", "[📊 Compressed: 6 Messages]\\nUser asked about weather..."],
        ...     ["Hello", "Hi!"],
        ...     ["", "🏛️[Kritische Prüfung] Deine Antwort ist zu kurz."],
        ...     ["", "🎩[Überarbeitung] Hier mehr Details..."]
        ... ]
        >>> msgs = build_messages_from_history(history, "Was denkst du?")
        >>> msgs[1]  # User message
        {'role': 'user', 'content': 'Hello'}
        >>> msgs[3]  # Sokrates critique as system
        {'role': 'system', 'content': '[MULTI-AGENT CONTEXT]\\n[SOKRATES]:  Deine Antwort ist zu kurz.'}
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

        # Detect Multi-Agent entries: ("", "🏛️[...]..." or "🎩[...]..." or "👑[...]...")
        # These are internal agent exchanges without user input
        is_agent_only = (user_turn == "" and
                        (ai_turn.startswith("🏛️") or ai_turn.startswith("🎩") or ai_turn.startswith("👑")))

        # Clean AI message (remove HTML tags AND text metadata)
        clean_ai = ai_turn

        # 1. Transform Multi-Agent markers to keep speaker attribution
        # Instead of removing, replace with clear speaker labels for LLM context
        # Sokrates: 🏛️[Mode] → "[SOKRATES]: "
        # AIfred: 🎩[Mode] → "[AIFRED]: "
        # Salomo: 👑[Mode] → "[SALOMO]: "
        clean_ai = re.sub(r'^🏛️\[[^\]]+\]', '[SOKRATES]: ', clean_ai)  # Sokrates marker
        clean_ai = re.sub(r'^🎩\[[^\]]+\]', '[AIFRED]: ', clean_ai)   # AIfred marker
        clean_ai = re.sub(r'^👑\[[^\]]+\]', '[SALOMO]: ', clean_ai)   # Salomo marker

        # 2. Remove thinking collapsibles (<details>...</details>)
        clean_ai = re.sub(r'<details[^>]*>.*?</details>', '', clean_ai, flags=re.DOTALL)

        # 3. Remove metadata spans (<span style="...">( Inference: ... )</span>)
        clean_ai = re.sub(r'<span[^>]*>\s*\([^)]+\)\s*</span>', '', clean_ai, flags=re.DOTALL)

        # 4. Fallback: Remove remaining text metadata (if HTML tags missing)
        for pattern in timing_patterns:
            if pattern in clean_ai:
                # Cut everything from the first timing pattern
                clean_ai = clean_ai.split(pattern)[0]

        # 5. Cleanup: Remove multiple blank lines and whitespace
        clean_ai = re.sub(r'\n\n+', '\n\n', clean_ai.strip())

        # Clean user message (needed for both modes)
        clean_user = user_turn
        if not is_agent_only:
            for pattern in timing_patterns:
                if pattern in clean_user:
                    clean_user = clean_user.split(pattern)[0]
            # Remove [IMG:...] markers from user messages
            clean_user = re.sub(r'\[IMG:[^\]]*\]', '', clean_user).strip()

        # === PERSPECTIVE-BASED ROLE ASSIGNMENT ===
        if perspective:
            # Multi-Agent mode: Assign roles based on who is currently speaking
            perspective_lower = perspective.lower()

            if is_agent_only:
                # Agent-only message (Sokrates, AIfred or Salomo internal exchange)
                is_sokrates_msg = ai_turn.startswith("🏛️")
                is_aifred_msg = ai_turn.startswith("🎩")
                is_salomo_msg = ai_turn.startswith("👑")

                if perspective_lower == "sokrates" and is_sokrates_msg:
                    # Sokrates sees his own earlier responses as 'assistant'
                    content = clean_ai.replace('[SOKRATES]: ', '').strip()
                    messages.append({'role': 'assistant', 'content': content})
                elif perspective_lower == "aifred" and is_aifred_msg:
                    # AIfred sees his own earlier responses as 'assistant'
                    content = clean_ai.replace('[AIFRED]: ', '').strip()
                    messages.append({'role': 'assistant', 'content': content})
                elif perspective_lower == "salomo" and is_salomo_msg:
                    # Salomo sees his own earlier responses as 'assistant'
                    content = clean_ai.replace('[SALOMO]: ', '').strip()
                    messages.append({'role': 'assistant', 'content': content})
                elif perspective_lower == "observer":
                    # Observer (Salomo as judge) sees ALL messages as 'user' with labels
                    messages.append({'role': 'user', 'content': clean_ai})
                else:
                    # Other agent's message → 'user' role with speaker label
                    messages.append({'role': 'user', 'content': clean_ai})
            else:
                # Normal user/AI exchange
                # Use actual username if set, otherwise fallback to [USER]
                user_label = get_user_name() or "USER"

                if perspective_lower == "sokrates":
                    # Sokrates sees: User as [Username], AIfred as [AIFRED]
                    messages.append({'role': 'user', 'content': f"[{user_label}]: {clean_user}"})
                    messages.append({'role': 'user', 'content': f"[AIFRED]: {clean_ai}"})
                elif perspective_lower == "aifred":
                    # AIfred sees: User as [Username], own responses as 'assistant'
                    messages.append({'role': 'user', 'content': f"[{user_label}]: {clean_user}"})
                    messages.append({'role': 'assistant', 'content': clean_ai})
                elif perspective_lower == "salomo":
                    # Salomo sees: User as [Username], AIfred's initial answer as [AIFRED]
                    messages.append({'role': 'user', 'content': f"[{user_label}]: {clean_user}"})
                    messages.append({'role': 'user', 'content': f"[AIFRED]: {clean_ai}"})
                elif perspective_lower == "observer":
                    # Observer sees: All as 'user' with labels (neutral viewpoint)
                    messages.append({'role': 'user', 'content': f"[{user_label}]: {clean_user}"})
                    messages.append({'role': 'user', 'content': f"[AIFRED]: {clean_ai}"})
                else:
                    # Unknown perspective → fallback to standard
                    messages.extend([
                        {'role': 'user', 'content': clean_user},
                        {'role': 'assistant', 'content': clean_ai}
                    ])
        else:
            # === STANDARD MODE (no perspective) ===
            if is_agent_only:
                # Agent-only message → system role for context
                messages.append({'role': 'system', 'content': f"[MULTI-AGENT CONTEXT]\n{clean_ai}"})
            else:
                # Normal user/AI exchange
                messages.extend([
                    {'role': 'user', 'content': clean_user},
                    {'role': 'assistant', 'content': clean_ai}
                ])

    # Add current user message only if provided (no prefix - role: user is sufficient)
    if current_user_text:
        messages.append({'role': 'user', 'content': current_user_text})

    return messages


def clean_content_for_llm(content: str) -> str:
    """
    Clean content for LLM history storage.

    Removes:
    - Thinking collapsibles (<details>...</details>)
    - Metadata spans (<span style="...">...</span>)
    - Timing patterns (*( Inference: ... )*)
    - [IMG:...] markers
    - Multi-agent markers (keeps label)

    Args:
        content: Raw content (may contain HTML, metadata, etc.)

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

    # 2. Remove thinking blocks - both raw <think> tags AND formatted <details> collapsibles
    # Raw <think>...</think> comes directly from LLM output (Qwen3 thinking mode)
    clean = re.sub(r'<think>.*?</think>', '', clean, flags=re.DOTALL)
    # Formatted <details>...</details> comes from format_thinking_process()
    clean = re.sub(r'<details[^>]*>.*?</details>', '', clean, flags=re.DOTALL)

    # 3. Remove metadata spans (<span style="...">( Inference: ... )</span>)
    clean = re.sub(r'<span[^>]*>\s*\([^)]+\)\s*</span>', '', clean, flags=re.DOTALL)

    # 4. Remove text timing patterns
    timing_patterns = [
        "*( STT:", "*( Agent:", "*( Inference:", "*( Vision:",
        "*( TTS:", "*( Decision:", "*( Cache-Hit:",
    ]
    for pattern in timing_patterns:
        if pattern in clean:
            clean = clean.split(pattern)[0]

    # 5. Remove [IMG:...] markers
    clean = re.sub(r'\[IMG:[^\]]*\]', '', clean)

    # 6. Cleanup: Remove multiple blank lines and whitespace
    clean = re.sub(r'\n\n+', '\n\n', clean.strip())

    return clean


def build_messages_from_llm_history(
    llm_history: List[Dict[str, str]],
    current_user_text: str = "",
    perspective: Optional[str] = None  # "sokrates", "aifred", "salomo", "observer", or None
) -> List[Dict[str, str]]:
    """
    Build LLM messages directly from llm_history (v2.13.0+).

    This is the PREFERRED function for building LLM messages.
    llm_history is already in the correct format - no parsing or cleaning needed!

    Advantages over build_messages_from_history():
    - No regex parsing needed (llm_history is pre-cleaned)
    - No marker detection (speaker labels already applied)
    - Faster and more reliable
    - Summaries already as system messages

    Args:
        llm_history: List of {"role": "user/assistant/system", "content": "..."}
        current_user_text: Current user message to append
        perspective: Multi-Agent perspective for role transformation
            - None: Use messages as-is
            - "sokrates": Sokrates speaking - transform AIfred's messages
            - "aifred": AIfred speaking - transform Sokrates's messages
            - "salomo": Salomo speaking - transform others' messages
            - "observer": Neutral observer - all as 'user' with labels

    Returns:
        list: Messages in Ollama format [{"role": "...", "content": "..."}, ...]
    """
    if not llm_history:
        messages = []
    elif not perspective:
        # Standard mode: Use messages as-is
        messages = llm_history.copy()
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
                    # Sokrates sees his own messages as 'assistant'
                    clean_content = content.replace("[SOKRATES]: ", "").strip()
                    messages.append({"role": "assistant", "content": clean_content})
                elif is_user:
                    messages.append({"role": "user", "content": f"[{user_label}]: {content}"})
                else:
                    # Others (AIfred, Salomo) as 'user' (keep their labels)
                    messages.append({"role": "user", "content": content})

            elif perspective_lower == "aifred":
                if is_aifred:
                    # AIfred sees his own messages as 'assistant'
                    clean_content = content.replace("[AIFRED]: ", "").strip()
                    messages.append({"role": "assistant", "content": clean_content})
                elif is_user:
                    messages.append({"role": "user", "content": f"[{user_label}]: {content}"})
                else:
                    # Others (Sokrates, Salomo) as 'user' (keep their labels)
                    messages.append({"role": "user", "content": content})

            elif perspective_lower == "salomo":
                if is_salomo:
                    # Salomo sees his own messages as 'assistant'
                    clean_content = content.replace("[SALOMO]: ", "").strip()
                    messages.append({"role": "assistant", "content": clean_content})
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
