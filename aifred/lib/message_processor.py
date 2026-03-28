"""Message Processor — bridge between Message Hub and AIfred Engine.

Handles the complete flow for inbound messages:
1. Find or create a session (via routing table)
2. Call the AIfred engine (call_llm)
3. Collect the response
4. Optionally send a reply (auto-reply)
5. Update the session with the conversation
"""

import secrets
from pathlib import Path
from typing import Optional

from .config import MESSAGE_HUB_OWNER
from .envelope import InboundMessage, OutboundMessage
from .logging_utils import log_message
from .routing_table import routing_table
from .session_storage import create_empty_session, update_chat_data, set_update_flag

# Global notification file for Message Hub events (read by UI timer)
_NOTIFICATION_FILE = None


def _get_notification_path() -> "Path":
    global _NOTIFICATION_FILE
    if _NOTIFICATION_FILE is None:
        from .config import DATA_DIR
        _NOTIFICATION_FILE = DATA_DIR / "message_hub" / "notification.json"
        _NOTIFICATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    return _NOTIFICATION_FILE


def write_hub_notification(
    session_id: str, session_title: str, channel: str, sender: str,
    status: str = "received",
) -> None:
    """Write a notification for the UI to pick up.

    status: "received" (message incoming) or "done" (reply sent)
    """
    import json
    path = _get_notification_path()
    notification = {
        "session_id": session_id,
        "session_title": session_title,
        "channel": channel,
        "sender": sender,
        "status": status,
    }
    path.write_text(json.dumps(notification), encoding="utf-8")


def read_and_clear_hub_notification() -> dict | None:
    """Read and delete the notification file. Returns dict or None."""
    import json
    path = _get_notification_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        path.unlink()
        return data
    except (json.JSONDecodeError, OSError):
        return None


# Agent name detection for routing
_AGENT_KEYWORDS = {
    "sokrates": "sokrates",
    "salomo": "salomo",
}


def detect_target_agent(text: str) -> str:
    """Detect if a message is addressed to a specific agent.

    Checks if the message starts with or contains an agent name.
    Returns the agent ID or "aifred" as default.
    """
    text_lower = text.lower().strip()
    for keyword, agent_id in _AGENT_KEYWORDS.items():
        if text_lower.startswith(keyword) or f"@{keyword}" in text_lower:
            return agent_id
    return "aifred"


async def process_inbound(message: InboundMessage) -> Optional[OutboundMessage]:
    """Process an inbound message through the full pipeline.

    Each phase writes to the session file and sets the update flag
    so the UI updates progressively (incoming mail → processing → reply).
    """
    from datetime import datetime as _dt

    # 1. Detect target agent from message text
    message.target_agent = detect_target_agent(message.text)

    # 2. Find or create session via routing table
    route = routing_table.get_route(message.channel, message.channel_id)
    subject = message.metadata.get("subject", "?")

    def _ts() -> str:
        return _dt.now().strftime("%H:%M:%S")

    if route:
        session_id = route.session_id
        log_message(f"Message Processor: existing session {session_id[:8]}")
    else:
        session_id = secrets.token_hex(16)
        create_empty_session(session_id, owner=MESSAGE_HUB_OWNER)
        routing_table.set_route(message.channel, message.channel_id, session_id)
        log_message(f"Message Processor: new session {session_id[:8]} for {message.sender}")

    # ── Phase 1: Show incoming message immediately ─────────────
    from .agent_config import get_agent_config as _get_agent_cfg
    _cfg = _get_agent_cfg(message.target_agent)
    agent_display_name = _cfg.display_name if _cfg else message.target_agent.capitalize()

    phase1_debug = [
        f"{_ts()} | 📨 {message.channel.upper()}: message from {message.sender}",
    ]
    if subject and subject != "?":
        phase1_debug.append(f"{_ts()} | 📧 Subject: {subject}")
    phase1_debug.append(f"{_ts()} | 🤖 Agent: {agent_display_name}")
    _save_to_session(session_id, message, "", phase1_debug)

    # Toast: incoming message (stays visible until next phase)
    from .session_storage import get_session_title
    from .plugin_registry import get_channel
    import asyncio

    title = get_session_title(session_id) or subject
    plugin = get_channel(message.channel)
    channel_label = plugin.display_name if plugin else message.channel.capitalize()

    def _notify(status: str) -> None:
        write_hub_notification(session_id, title, channel_label, message.sender, status=status)

    _notify("received")

    # Give the browser time to pick up the toast before heavy work starts
    await asyncio.sleep(2)

    # ── Phase 2: Call AIfred engine ────────────────────────────
    _notify("processing")

    if plugin:
        llm_context = plugin.build_context(message)
    else:
        llm_context = f"[{channel_label} from {message.sender}]\n\n{message.text}"

    engine_debug: list[str] = []
    response_text = await _call_engine(
        user_text=llm_context,
        session_id=session_id,
        agent=message.target_agent,
        debug_sink=engine_debug,
    )

    if not response_text:
        log_message("Message Processor: engine returned no response", "warning")
        engine_debug.append(f"{_ts()} | ❌ Engine: no response")
        _append_debug(session_id, engine_debug)
        _notify("error")
        return None

    engine_debug.append(f"{_ts()} | ✅ Response generated ({len(response_text)} chars)")

    # ── Phase 3: Save response to session ─────────────────────
    _append_response(session_id, response_text)
    _append_debug(session_id, engine_debug)

    # ── Phase 4: Auto-reply if enabled ────────────────────────
    reply_metadata = plugin.build_reply_metadata(message) if plugin else {}
    outbound = OutboundMessage(
        channel=message.channel,
        channel_id=message.channel_id,
        recipient=message.sender,
        text=response_text,
        metadata=reply_metadata,
    )

    auto_reply_enabled = _is_auto_reply_enabled(message.channel)
    if plugin and auto_reply_enabled:
        await plugin.send_reply(outbound, message)
        _append_debug(session_id, [
            f"{_ts()} | 📤 Auto-reply sent to {message.sender}",
            f"{_ts()} | ────────────────────",
        ])
    else:
        _append_debug(session_id, [
            f"{_ts()} | 💬 Response ready (auto-reply off)",
            f"{_ts()} | ────────────────────",
        ])

    # ── Phase 5: Generate title if missing ────────────────────
    from .llm_engine import generate_session_title
    title = get_session_title(session_id)
    if not title:
        await generate_session_title(message.text, response_text, session_id)

    # ── Phase 6: Notify UI that processing is complete ────────
    title = get_session_title(session_id) or subject
    write_hub_notification(session_id, title, message.channel.upper(), message.sender, status="done")

    return outbound


async def _call_engine(
    user_text: str,
    session_id: str,
    agent: str = "aifred",
    debug_sink: list[str] | None = None,
) -> str:
    """Call the AIfred engine with full toolkit (memory + plugins).

    Same pipeline as the normal chat: loads history, prepares toolkit,
    resolves calibrated context, and forwards all debug messages.
    """
    from datetime import datetime as _dt
    from .llm_engine import call_llm
    from .session_storage import load_session
    from .settings import load_settings
    from .config import (
        DEFAULT_SETTINGS, BACKEND_DEFAULT_MODELS, BACKEND_URLS,
        MAIN_LLM_FALLBACK_CONTEXT,
    )

    def _dbg(msg: str) -> None:
        if debug_sink is not None:
            ts = _dt.now().strftime("%H:%M:%S")
            debug_sink.append(f"{ts} | {msg}")

    # Load current settings
    settings = load_settings() or {}
    backend_type = settings.get("backend_type", DEFAULT_SETTINGS["backend_type"])
    temperature_mode = settings.get("temperature_mode", "auto")
    temperature = settings.get("temperature", 0.7)
    enable_thinking = settings.get("enable_thinking", False)

    # Get model for the agent
    backend_models_saved = settings.get("backend_models", {}).get(backend_type, {})
    backend_models_default = BACKEND_DEFAULT_MODELS.get(backend_type, {})
    model_key = f"{agent}_model" if agent != "aifred" else "aifred_model"
    model = backend_models_saved.get(model_key, backend_models_default.get(model_key, ""))
    backend_url = BACKEND_URLS.get(backend_type, "")

    if not model:
        log_message(f"Message Processor: no model configured for {agent}/{backend_type}", "error")
        return ""

    # Load existing LLM history from session
    session = load_session(session_id)
    llm_history = session.get("data", {}).get("llm_history", []) if session else []

    # Resolve calibrated context (no State needed)
    from .research.context_utils import get_model_native_context
    num_ctx = get_model_native_context(model, backend_type)
    ctx_label = "native"
    if num_ctx <= 0:
        num_ctx = MAIN_LLM_FALLBACK_CONTEXT
        ctx_label = "fallback"

    from .agent_config import get_agent_config
    _agent_cfg = get_agent_config(agent)
    agent_display = _agent_cfg.display_name if _agent_cfg else agent.capitalize()

    _dbg(f"🎩 {agent_display}-LLM: {model} ({backend_type})")
    _dbg(f"📜 History: {len(llm_history)} messages")
    log_message(f"Message Processor: calling {agent_display} ({model}), history={len(llm_history)} msgs, for: {user_text[:80]}...")

    # Prepare full toolkit (memory + all plugin tools)
    # Language and memory toggle from settings (no State dependency)
    lang = settings.get("ui_language", "de")
    memory_enabled = settings.get("agent_memory_enabled", True)

    toolkit = None
    memory_ctx = ""
    from .agent_memory import prepare_agent_toolkit
    memory_ctx, toolkit = await prepare_agent_toolkit(
        agent, user_text, lang=lang,
        memory_enabled=memory_enabled,
        research_tools_enabled=True,
        session_id=session_id,
    )
    if toolkit:
        _dbg(f"🔧 Toolkit: {[t.name for t in toolkit.tools]} for {agent_display}")

    # Collect response — forward ALL debug chunks to session console
    from .research_tools import _hub_search_debug

    response_parts: list[str] = []
    try:
        async for chunk in call_llm(
            user_text=user_text,
            model_choice=model,
            history=[],
            llm_history=llm_history,
            detected_intent="ALLGEMEIN",
            detected_language=lang,
            temperature_mode=temperature_mode,
            temperature=temperature,
            backend_type=backend_type,
            backend_url=backend_url,
            enable_thinking=enable_thinking,
            num_ctx_manual_enabled=True,
            num_ctx_manual_value=num_ctx,
            num_ctx_source_label=ctx_label,
            agent=agent,
            external_toolkit=toolkit,
            rag_context=memory_ctx if memory_ctx else None,
        ):
            if chunk.get("type") == "content":
                response_parts.append(chunk.get("text", ""))
            elif chunk.get("type") == "debug":
                _dbg(chunk.get("message", ""))
                # Flush hub search debug messages (already have timestamps)
                if _hub_search_debug and debug_sink is not None:
                    debug_sink.extend(_hub_search_debug)
                    _hub_search_debug.clear()
            elif chunk.get("type") == "result":
                if _hub_search_debug and debug_sink is not None:
                    debug_sink.extend(_hub_search_debug)
                    _hub_search_debug.clear()
                data = chunk.get("data", {})
                if "response_clean" in data:
                    return data["response_clean"]
    except Exception as exc:
        log_message(f"Message Processor: engine error — {exc}", "error")
        _dbg(f"❌ Engine error: {exc}")
        return ""

    return "".join(response_parts)


def _save_to_session(
    session_id: str,
    message: InboundMessage,
    response_text: str,
    debug_messages: list[str] | None = None,
) -> None:
    """Append the inbound message (and optional response) to the session."""
    from .session_storage import load_session

    channel_label = message.channel.upper()
    subject = message.metadata.get("subject", "")
    header = f"[{channel_label}] {message.sender}"
    if subject:
        header += f" — {subject}"

    # Load existing history and append
    session = load_session(session_id)
    data = session.get("data", {}) if session else {}
    existing_chat = data.get("chat_history", [])
    existing_llm = data.get("llm_history", [])
    existing_debug = data.get("debug_messages", [])

    existing_chat.append({"role": "user", "content": header + "\n\n" + message.text})
    existing_llm.append({"role": "user", "content": message.text})

    if response_text:
        existing_chat.append({"role": "assistant", "content": response_text})
        existing_llm.append({"role": "assistant", "content": response_text})

    if debug_messages:
        existing_debug.extend(debug_messages)

    update_chat_data(
        session_id=session_id,
        chat_history=existing_chat,
        llm_history=existing_llm,
        debug_messages=existing_debug,
        owner=MESSAGE_HUB_OWNER,
    )

    # Signal the browser to reload the session
    set_update_flag(session_id)


def _append_response(session_id: str, response_text: str) -> None:
    """Append the assistant response to an existing session."""
    from .session_storage import load_session

    session = load_session(session_id)
    data = session.get("data", {}) if session else {}
    existing_chat = data.get("chat_history", [])
    existing_llm = data.get("llm_history", [])

    existing_chat.append({"role": "assistant", "content": response_text})
    existing_llm.append({"role": "assistant", "content": response_text})

    update_chat_data(
        session_id=session_id,
        chat_history=existing_chat,
        llm_history=existing_llm,
        owner=MESSAGE_HUB_OWNER,
    )
    set_update_flag(session_id)


def _append_debug(session_id: str, messages: list[str]) -> None:
    """Append debug messages to an existing session."""
    if not messages:
        return
    from .session_storage import load_session

    session = load_session(session_id)
    data = session.get("data", {}) if session else {}
    existing_debug = data.get("debug_messages", [])
    existing_debug.extend(messages)

    update_chat_data(
        session_id=session_id,
        chat_history=data.get("chat_history", []),
        debug_messages=existing_debug,
        owner=MESSAGE_HUB_OWNER,
    )
    set_update_flag(session_id)


def _is_auto_reply_enabled(channel: str) -> bool:
    """Check if auto-reply is enabled for a given channel."""
    from .settings import load_settings
    settings = load_settings() or {}
    channel_toggles = settings.get("channel_toggles", {})
    return channel_toggles.get(channel, {}).get("auto_reply", False)
