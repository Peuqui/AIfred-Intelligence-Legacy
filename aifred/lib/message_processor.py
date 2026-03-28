"""Message Processor — bridge between Message Hub and AIfred Engine.

Handles the complete flow for inbound messages:
1. Find or create a session (via routing table)
2. Call the AIfred engine (call_llm)
3. Collect the response
4. Optionally send a reply (auto-reply)
5. Update the session with the conversation
"""

import secrets
from typing import Optional

from .config import (
    EMAIL_MONITOR_AUTO_REPLY,
    MESSAGE_HUB_OWNER,
)
from .email_client import send_email
from .envelope import InboundMessage, OutboundMessage
from .logging_utils import log_message
from .routing_table import routing_table
from .session_storage import create_empty_session, update_chat_data, set_update_flag


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

    Returns an OutboundMessage if a reply should be sent, or None.
    """
    # 1. Detect target agent from message text
    message.target_agent = detect_target_agent(message.text)

    # 2. Find or create session via routing table
    route = routing_table.get_route(message.channel, message.channel_id)

    # Track debug messages for the session
    debug: list[str] = []
    subject = message.metadata.get("subject", "?")

    if route:
        session_id = route.session_id
        log_message(f"Message Processor: existing session {session_id[:8]}")
        debug.append(f"📨 {message.channel.upper()}: Nachricht von {message.sender}")
    else:
        session_id = secrets.token_hex(16)
        create_empty_session(session_id, owner=MESSAGE_HUB_OWNER)
        routing_table.set_route(message.channel, message.channel_id, session_id)
        log_message(f"Message Processor: new session {session_id[:8]} for {message.sender}")
        debug.append(f"📨 {message.channel.upper()}: Neue Konversation von {message.sender}")

    debug.append(f"📧 Betreff: {subject}")
    debug.append(f"🤖 Agent: {message.target_agent}")

    # 3. Call AIfred engine
    response_text = await _call_engine(
        user_text=message.text,
        session_id=session_id,
        agent=message.target_agent,
    )

    if not response_text:
        log_message("Message Processor: engine returned no response", "warning")
        debug.append("❌ Engine: keine Antwort erhalten")
        _save_to_session(session_id, message, "", debug)
        return None

    debug.append(f"✅ Antwort generiert ({len(response_text)} Zeichen)")

    # 4. Build outbound message
    outbound = OutboundMessage(
        channel=message.channel,
        channel_id=message.channel_id,
        recipient=message.sender,
        text=response_text,
        metadata=_build_reply_metadata(message),
    )

    # 5. Auto-reply if enabled
    if message.channel == "email" and EMAIL_MONITOR_AUTO_REPLY:
        _send_email_reply(outbound, message)
        debug.append(f"📤 Auto-Reply gesendet an {message.sender}")
    else:
        debug.append("💬 Antwort bereit (Auto-Reply aus)")

    # 6. Save conversation + debug to session
    _save_to_session(session_id, message, response_text, debug)

    return outbound


async def _call_engine(
    user_text: str,
    session_id: str,
    agent: str = "aifred",
) -> str:
    """Call the AIfred engine and collect the response text.

    Uses call_llm() with settings from settings.json.
    """
    from .llm_engine import call_llm
    from .settings import load_settings
    from .config import DEFAULT_SETTINGS, BACKEND_DEFAULT_MODELS, MAIN_LLM_FALLBACK_CONTEXT

    # Load current settings
    settings = load_settings() or {}
    backend_type = settings.get("backend_type", DEFAULT_SETTINGS["backend_type"])
    temperature_mode = settings.get("temperature_mode", "auto")
    temperature = settings.get("temperature", 0.7)
    enable_thinking = settings.get("enable_thinking", False)

    # Get model for the agent — check per-backend saved models first
    backend_models_saved = settings.get("backend_models", {}).get(backend_type, {})
    backend_models_default = BACKEND_DEFAULT_MODELS.get(backend_type, {})
    model_key = f"{agent}_model" if agent != "aifred" else "aifred_model"
    model = backend_models_saved.get(model_key, backend_models_default.get(model_key, ""))

    # Get backend URL
    from .config import BACKEND_URLS
    backend_url = BACKEND_URLS.get(backend_type, "")

    if not model:
        log_message(f"Message Processor: no model configured for {agent}/{backend_type}", "error")
        return ""

    log_message(f"Message Processor: calling {agent} ({model}) for: {user_text[:80]}...")

    # Collect response from the async generator
    # Note: We use num_ctx_manual to bypass the state-dependent num_ctx lookup
    # (Message Hub runs outside of Reflex state context)
    response_parts: list[str] = []
    try:
        async for chunk in call_llm(
            user_text=user_text,
            model_choice=model,
            history=[],
            llm_history=[],
            detected_intent="ALLGEMEIN",
            detected_language="de",
            temperature_mode=temperature_mode,
            temperature=temperature,
            backend_type=backend_type,
            backend_url=backend_url,
            enable_thinking=enable_thinking,
            num_ctx_manual_enabled=True,
            num_ctx_manual_value=MAIN_LLM_FALLBACK_CONTEXT,
            agent=agent,
        ):
            if chunk.get("type") == "content":
                response_parts.append(chunk.get("text", ""))
            elif chunk.get("type") == "result":
                data = chunk.get("data", {})
                if "ai_response" in data:
                    return data["ai_response"]
    except Exception as exc:
        log_message(f"Message Processor: engine error — {exc}", "error")
        return ""

    return "".join(response_parts)


def _save_to_session(
    session_id: str,
    message: InboundMessage,
    response_text: str,
    debug_messages: list[str] | None = None,
) -> None:
    """Save the inbound message, response and debug info to the session."""
    channel_label = message.channel.upper()
    subject = message.metadata.get("subject", "")
    header = f"[{channel_label}] {message.sender}"
    if subject:
        header += f" — {subject}"

    chat_history = [
        {"role": "user", "content": header + "\n\n" + message.text},
    ]
    llm_history = [
        {"role": "user", "content": message.text},
    ]

    if response_text:
        chat_history.append({"role": "assistant", "content": response_text})
        llm_history.append({"role": "assistant", "content": response_text})

    update_chat_data(
        session_id=session_id,
        chat_history=chat_history,
        llm_history=llm_history,
        debug_messages=debug_messages,
        owner=MESSAGE_HUB_OWNER,
    )

    # Signal the browser to reload the session (triggers toast in UI)
    set_update_flag(session_id)


def _build_reply_metadata(message: InboundMessage) -> dict:
    """Build channel-specific metadata for the reply."""
    metadata: dict = {}
    if message.channel == "email":
        # Reply subject: add Re: if not already present
        subject = message.metadata.get("subject", "")
        if subject and not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        metadata["subject"] = subject
        metadata["in_reply_to"] = message.metadata.get("message_id", "")
        metadata["references"] = message.metadata.get("message_id", "")
    return metadata


def _send_email_reply(outbound: OutboundMessage, original: InboundMessage) -> None:
    """Send an email reply via SMTP."""
    subject = outbound.metadata.get("subject", "Re: AIfred")
    reply_to_id = outbound.metadata.get("in_reply_to")

    try:
        send_email(
            to=outbound.recipient,
            subject=subject,
            body=outbound.text,
            reply_to_id=reply_to_id,
        )
        log_message(f"Message Processor: auto-reply sent to {outbound.recipient}")
    except Exception as exc:
        log_message(f"Message Processor: failed to send reply — {exc}", "error")
