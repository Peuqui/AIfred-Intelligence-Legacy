"""
Server-side Session Storage for AIfred

Stores chat history and session data per device.
Uses device_id from cookie for identification.

Sessions are saved as JSON files in ~/.config/aifred/sessions/.
Each device has its own session file (device_id.json).
"""

import json
import hashlib
import secrets
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

from .settings import SETTINGS_DIR


# Session directory (subdirectory of Settings)
SESSION_DIR = SETTINGS_DIR / "sessions"


def _ensure_session_dir() -> None:
    """Create session directory if it doesn't exist."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def generate_device_id() -> str:
    """
    Generate new unique Device-ID.

    Returns:
        32 character hex string (128 bit entropy)
    """
    return secrets.token_hex(16)  # 128 bits for secure session IDs


def _sanitize_device_id(device_id: str) -> str:
    """
    Validate Device-ID format (hex string with 32 characters).

    Only allows lowercase hex characters (a-f0-9) exactly 32 characters long.
    Prevents path traversal attacks through strict format checking.

    Args:
        device_id: Device-ID to validate

    Returns:
        Validated Device-ID

    Raises:
        ValueError: If format is invalid
    """
    import re

    # Only allow lowercase hex: exactly 32 characters (128 bit)
    if not re.match(r'^[a-f0-9]{32}$', device_id):
        raise ValueError(
            f"Invalid device_id format: Expected 32 hex chars, got '{device_id[:50]}'"
        )

    return device_id


def get_session_path(device_id: str) -> Path:
    """
    Return path to session file with path traversal protection.

    Args:
        device_id: Device identifier

    Returns:
        Path to session JSON file

    Raises:
        ValueError: On invalid device_id or path traversal attempt
    """
    safe_id = _sanitize_device_id(device_id)
    path = (SESSION_DIR / f"{safe_id}.json").resolve()

    # Ensure path is within SESSION_DIR
    try:
        path.relative_to(SESSION_DIR.resolve())
    except ValueError:
        raise ValueError(f"Path traversal attempt detected: {device_id}")

    return path


def load_session(device_id: str) -> Optional[Dict[str, Any]]:
    """
    Load session for Device-ID.

    Automatically updates last_seen timestamp.

    Args:
        device_id: Device identifier

    Returns:
        Session dict or None if not found
    """
    _ensure_session_dir()

    try:
        session_path = get_session_path(device_id)
    except ValueError:
        return None

    if not session_path.exists():
        return None

    try:
        with open(session_path, "r", encoding="utf-8") as f:
            session = json.load(f)

        # Update last_seen (speichert auch gleich)
        session["last_seen"] = datetime.now().isoformat()
        _write_session_file(session_path, session)

        return session

    except (json.JSONDecodeError, IOError, KeyError):
        return None


def _write_session_file(path: Path, session: Dict[str, Any]) -> bool:
    """
    Write session dict to file (internal helper).

    Args:
        path: Path to session file
        session: Session dict

    Returns:
        True on success
    """
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
        return True
    except IOError:
        return False


def create_empty_session(device_id: str) -> bool:
    """
    Create an empty session file for a new device.

    This is called when a browser connects and no session file exists yet.
    Creates the file immediately so the API can inject messages right away.

    Args:
        device_id: Device identifier

    Returns:
        True on success, False on error
    """
    return save_session(device_id, {"data": {}})


def save_session(device_id: str, session_data: Dict[str, Any]) -> bool:
    """
    Save session for Device-ID.

    Args:
        device_id: Device identifier
        session_data: Complete session dict

    Returns:
        True on success, False on error
    """
    _ensure_session_dir()

    try:
        session_path = get_session_path(device_id)
    except ValueError:
        return False

    # Ensure timestamps
    now = datetime.now().isoformat()
    if "created_at" not in session_data:
        session_data["created_at"] = now
    session_data["last_seen"] = now
    session_data["device_id"] = device_id

    return _write_session_file(session_path, session_data)


def update_chat_data(
    device_id: str,
    chat_history: List[Dict[str, Any]],
    chat_summaries: Optional[List[str]] = None,
    llm_history: Optional[List[Dict[str, str]]] = None,
    debug_messages: Optional[List[str]] = None,
    is_generating: Optional[bool] = None
) -> bool:
    """
    Update chat data of a session.

    Creates new session if not present.
    More efficient than save_session() when only chat data changes.

    Args:
        device_id: Device identifier
        chat_history: List of ChatMessage dicts (UI - vollständig)
        chat_summaries: Optional - List of summary strings
        llm_history: Optional - List of {"role": ..., "content": ...} dicts (LLM - komprimiert)
        debug_messages: Optional - List of debug log entries (last N entries)
        is_generating: Optional - Current generation status (for API polling)

    Returns:
        True on success
    """
    # Load existing session or create new one
    session = load_session(device_id)

    if session is None:
        session = {
            "created_at": datetime.now().isoformat(),
            "pin_hash": None,
            "data": {}
        }

    # Update chat data (Dict-based format - no conversion needed)
    session["data"]["chat_history"] = chat_history

    if chat_summaries is not None:
        session["data"]["chat_summaries"] = list(chat_summaries)

    # DUAL-HISTORY (v2.13.0+): Store llm_history separately
    if llm_history is not None:
        session["data"]["llm_history"] = llm_history

    # DEBUG-PERSISTENCE (v2.14.0+): Store last N debug entries
    if debug_messages is not None:
        session["data"]["debug_messages"] = debug_messages

    # API STATUS (v2.15.9+): Store is_generating for API polling
    if is_generating is not None:
        session["data"]["is_generating"] = is_generating

    return save_session(device_id, session)


def delete_session(device_id: str) -> bool:
    """
    Delete session completely.

    Args:
        device_id: Device identifier

    Returns:
        True on success
    """
    try:
        session_path = get_session_path(device_id)
        if session_path.exists():
            session_path.unlink()
        return True
    except (ValueError, IOError):
        return False


# ============================================================
# PIN Functions (Phase 2 - for Cross-Device Access)
# ============================================================

def hash_pin(pin: str) -> str:
    """
    Hash PIN with SHA-256.

    Args:
        pin: Plaintext PIN

    Returns:
        Hash string in format "sha256:..."
    """
    return f"sha256:{hashlib.sha256(pin.encode()).hexdigest()}"


def verify_pin(pin: str, pin_hash: str) -> bool:
    """
    Verify PIN against stored hash.

    Args:
        pin: Plaintext PIN to check
        pin_hash: Stored hash

    Returns:
        True if PIN is correct
    """
    if not pin_hash or not pin_hash.startswith("sha256:"):
        return False
    return hash_pin(pin) == pin_hash


def set_session_pin(device_id: str, pin: str) -> bool:
    """
    Set or update PIN for session.

    Args:
        device_id: Device identifier
        pin: New PIN (plaintext, will be hashed)

    Returns:
        True on success
    """
    session = load_session(device_id)
    if not session:
        return False

    session["pin_hash"] = hash_pin(pin)
    return save_session(device_id, session)


def clear_session_pin(device_id: str) -> bool:
    """
    Remove PIN from session.

    Args:
        device_id: Device identifier

    Returns:
        True on success
    """
    session = load_session(device_id)
    if not session:
        return False

    session["pin_hash"] = None
    return save_session(device_id, session)


def get_session_with_pin(device_id: str, pin: str) -> Optional[Dict[str, Any]]:
    """
    Load session only if PIN is correct.

    For cross-device access: User enters foreign device_id + PIN.

    Args:
        device_id: Device identifier
        pin: PIN to verify

    Returns:
        Session dict if PIN correct, else None
    """
    session = load_session(device_id)
    if not session:
        return None

    pin_hash = session.get("pin_hash")
    if not pin_hash:
        # Session has no PIN - deny access
        return None

    if not verify_pin(pin, pin_hash):
        return None

    return session


# ============================================================
# Session Discovery (for API access)
# ============================================================

def get_latest_session_file() -> Optional[Path]:
    """
    Get the most recently modified session file.

    Useful for API access when device_id is not known.
    Returns the session file with the newest modification time.

    Returns:
        Path to newest session file, or None if no sessions exist
    """
    _ensure_session_dir()

    session_files = list(SESSION_DIR.glob("*.json"))
    if not session_files:
        return None

    # Sort by modification time, newest first
    session_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return session_files[0]


def list_sessions() -> List[Dict[str, Any]]:
    """
    List all sessions with basic info.

    Returns list of dicts with:
    - device_id: Session identifier
    - last_seen: Last activity timestamp
    - message_count: Number of chat messages

    Returns:
        List of session info dicts, sorted by last_seen (newest first)
    """
    _ensure_session_dir()

    sessions = []
    for session_file in SESSION_DIR.glob("*.json"):
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            chat_history = data.get("data", {}).get("chat_history", [])
            sessions.append({
                "device_id": session_file.stem,
                "last_seen": data.get("last_seen", ""),
                "message_count": len(chat_history)
            })
        except (json.JSONDecodeError, IOError):
            continue

    # Sort by last_seen, newest first
    sessions.sort(key=lambda s: s.get("last_seen", ""), reverse=True)
    return sessions


# ============================================================
# Cleanup (for background task)
# ============================================================

def cleanup_old_sessions(max_age_days: int = 30) -> int:
    """
    Delete sessions older than max_age_days.

    Based on file modification time (not last_seen in JSON),
    as this is more efficient than parsing every file.

    Args:
        max_age_days: Maximum age in days

    Returns:
        Number of deleted sessions
    """
    _ensure_session_dir()
    cutoff_timestamp = datetime.now().timestamp() - (max_age_days * 24 * 60 * 60)
    deleted_count = 0

    for session_file in SESSION_DIR.glob("*.json"):
        try:
            if session_file.stat().st_mtime < cutoff_timestamp:
                session_file.unlink()
                deleted_count += 1
        except IOError:
            pass

    return deleted_count


# ============================================================
# API Update Flags (for Browser Auto-Reload)
# ============================================================

def set_update_flag(device_id: str) -> bool:
    """
    Set update flag file to signal browser should reload.

    Called by API after modifying session data.
    Browser timer checks for this flag and triggers reload.

    Args:
        device_id: Device identifier

    Returns:
        True on success
    """
    _ensure_session_dir()

    try:
        safe_id = _sanitize_device_id(device_id)
        flag_path = SESSION_DIR / f"{safe_id}.update"
        flag_path.touch()
        return True
    except (ValueError, IOError):
        return False


def check_and_clear_update_flag(device_id: str) -> bool:
    """
    Check if update flag exists and clear it.

    Called by browser timer to detect API updates.
    Returns True if flag was present (browser should reload).

    Args:
        device_id: Device identifier

    Returns:
        True if flag was present (now cleared), False otherwise
    """
    _ensure_session_dir()

    try:
        safe_id = _sanitize_device_id(device_id)
        flag_path = SESSION_DIR / f"{safe_id}.update"

        if flag_path.exists():
            flag_path.unlink()
            return True
        return False
    except (ValueError, IOError):
        return False


# ============================================================
# Pending Message (API → Browser Message Injection)
# ============================================================

def set_pending_message(device_id: str, message: str) -> bool:
    """
    Set pending message for browser to process.

    Called by API to inject a message into a browser session.
    Browser polls for .pending flag, reads message, triggers send_message().

    Args:
        device_id: Device identifier
        message: User message to inject

    Returns:
        True on success
    """
    _ensure_session_dir()

    try:
        safe_id = _sanitize_device_id(device_id)

        # Load existing session or create minimal structure
        session_path = get_session_path(device_id)
        if session_path.exists():
            with open(session_path, 'r', encoding='utf-8') as f:
                session = json.load(f)
        else:
            session = {"device_id": device_id, "data": {}}

        # Set pending message in session data
        if "data" not in session:
            session["data"] = {}
        session["data"]["pending_message"] = message

        # Save session
        with open(session_path, 'w', encoding='utf-8') as f:
            json.dump(session, f, ensure_ascii=False, indent=2)

        # Set .pending flag file
        flag_path = SESSION_DIR / f"{safe_id}.pending"
        flag_path.touch()

        return True
    except (ValueError, IOError, json.JSONDecodeError):
        return False


def get_and_clear_pending_message(device_id: str) -> Optional[str]:
    """
    Get pending message and clear it.

    Called by browser to check for API-injected messages.
    Returns the message if present, clears it from session.

    Args:
        device_id: Device identifier

    Returns:
        Pending message string, or None if no pending message
    """
    _ensure_session_dir()

    try:
        safe_id = _sanitize_device_id(device_id)
        flag_path = SESSION_DIR / f"{safe_id}.pending"

        # Check flag first (fast path)
        if not flag_path.exists():
            return None

        # Flag exists - clear it
        flag_path.unlink()

        # Load session and extract message
        session_path = get_session_path(device_id)
        if not session_path.exists():
            return None

        with open(session_path, 'r', encoding='utf-8') as f:
            session = json.load(f)

        pending_msg = session.get("data", {}).get("pending_message")
        if not pending_msg:
            return None

        # Clear pending_message from session
        session["data"]["pending_message"] = None
        with open(session_path, 'w', encoding='utf-8') as f:
            json.dump(session, f, ensure_ascii=False, indent=2)

        return pending_msg

    except (ValueError, IOError, json.JSONDecodeError):
        return None
