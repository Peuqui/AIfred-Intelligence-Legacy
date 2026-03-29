"""Centralized Debug Bus — single debug API for all contexts.

Replaces the dual debug paths (Browser State vs Hub debug_sink).
Plugin developers only need one call: debug("message").

Usage:
    from aifred.lib.debug_bus import debug, session_scope

    # Hub path: set session context once per request
    with session_scope(session_id):
        debug("🔍 Web search started")   # → log + session file
        debug("✅ 7 sources scraped")     # → log + session file
    # On exit: batched write to session file + set_update_flag

    # Browser path: state.add_debug() forwards to debug() internally
    # No session_scope needed — Reflex State handles live UI updates

    # Standalone (startup, no session): goes to logfile only
    debug("Server starting...")
"""

import contextvars
from datetime import datetime

from .logging_utils import log_message

# Session ID for the current async task (set via session_scope)
_current_session: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "debug_bus_session", default=None
)

# Message buffer for the current session_scope (batched write on exit)
_buffer: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "debug_bus_buffer", default=None
)


class session_scope:
    """Context manager that binds a session_id for debug message routing.

    Messages emitted via debug() inside this scope are collected in a buffer.
    On exit, the buffer is flushed once to the session file (batched I/O).
    Nest-safe: restores previous values on exit.
    """

    def __init__(self, session_id: str | None) -> None:
        self._session_id = session_id
        self._session_token: contextvars.Token | None = None
        self._buffer_token: contextvars.Token | None = None

    def __enter__(self) -> "session_scope":
        self._session_token = _current_session.set(self._session_id)
        self._buffer_token = _buffer.set([])
        return self

    def __exit__(self, *exc: object) -> None:
        messages = _buffer.get()
        if messages and self._session_id:
            _flush_to_session(self._session_id, messages)
        if self._buffer_token is not None:
            _buffer.reset(self._buffer_token)
        if self._session_token is not None:
            _current_session.reset(self._session_token)


def debug(msg: str) -> None:
    """Emit a debug message.

    - Always: writes to log_message() (logfile + console queue)
    - If session_scope active: also buffers for session file (batched on scope exit)

    Args:
        msg: The debug message (without timestamp — added automatically).
    """
    log_message(msg)

    buf = _buffer.get(None)
    if buf is not None:
        ts = datetime.now().strftime("%H:%M:%S")
        buf.append(f"{ts} | {msg}")


def flush() -> None:
    """Manually flush buffered debug messages to the session file.

    Call this mid-scope if you need messages to appear in the session
    before the scope exits (e.g. between processing phases).
    """
    buf = _buffer.get(None)
    sid = _current_session.get()
    if buf and sid:
        _flush_to_session(sid, list(buf))
        buf.clear()


def _flush_to_session(session_id: str, messages: list[str]) -> None:
    """Write buffered debug messages to the session file."""
    from .session_storage import load_session, update_chat_data, set_update_flag
    from .config import MESSAGE_HUB_OWNER

    session = load_session(session_id)
    data = session.get("data", {}) if session else {}
    existing = data.get("debug_messages", [])
    existing.extend(messages)

    update_chat_data(
        session_id=session_id,
        chat_history=data.get("chat_history", []),
        debug_messages=existing,
        owner=MESSAGE_HUB_OWNER,
    )
    set_update_flag(session_id)
