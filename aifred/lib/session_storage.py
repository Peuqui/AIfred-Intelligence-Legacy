"""
Server-side Session Storage für AIfred

Speichert Chat-History und Session-Daten pro Gerät.
Verwendet device_id aus Cookie zur Identifikation.

Sessions werden als JSON-Dateien in ~/.config/aifred/sessions/ gespeichert.
Jedes Gerät hat eine eigene Session-Datei (device_id.json).
"""

import json
import hashlib
import secrets
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from .settings import SETTINGS_DIR


# Session-Verzeichnis (Unterordner von Settings)
SESSION_DIR = SETTINGS_DIR / "sessions"


def _ensure_session_dir() -> None:
    """Erstellt Session-Verzeichnis falls nicht vorhanden."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def generate_device_id() -> str:
    """
    Generiert neue eindeutige Device-ID.

    Returns:
        32 Zeichen hex string (128 bit Entropie)
    """
    return secrets.token_hex(16)  # 128 bits für sichere Session-IDs


def _sanitize_device_id(device_id: str) -> str:
    """
    Validiert Device-ID Format (Hex-String mit 32 Zeichen).

    Erlaubt nur lowercase hex-Zeichen (a-f0-9) genau 32 Zeichen lang.
    Verhindert Path Traversal Angriffe durch strikte Format-Prüfung.

    Args:
        device_id: Device-ID zum Validieren

    Returns:
        Validierte Device-ID

    Raises:
        ValueError: Wenn Format ungültig ist
    """
    import re

    # Nur lowercase hex erlauben: 32 Zeichen lang
    if not re.match(r'^[a-f0-9]{32}$', device_id):
        raise ValueError(
            f"Invalid device_id format: Expected 32 hex chars, got '{device_id[:50]}'"
        )

    return device_id


def get_session_path(device_id: str) -> Path:
    """
    Gibt Pfad zur Session-Datei zurück mit Path Traversal Protection.

    Args:
        device_id: Geräte-Identifikator

    Returns:
        Path zur Session-JSON-Datei

    Raises:
        ValueError: Bei ungültiger device_id oder Path Traversal Versuch
    """
    safe_id = _sanitize_device_id(device_id)
    path = (SESSION_DIR / f"{safe_id}.json").resolve()

    # Sicherstellen dass Pfad innerhalb SESSION_DIR liegt
    try:
        path.relative_to(SESSION_DIR.resolve())
    except ValueError:
        raise ValueError(f"Path traversal attempt detected: {device_id}")

    return path


def load_session(device_id: str) -> Optional[Dict[str, Any]]:
    """
    Lädt Session für Device-ID.

    Aktualisiert automatisch last_seen Timestamp.

    Args:
        device_id: Geräte-Identifikator

    Returns:
        Session-Dict oder None wenn nicht gefunden
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
    Schreibt Session-Dict in Datei (interner Helper).

    Args:
        path: Pfad zur Session-Datei
        session: Session-Dict

    Returns:
        True bei Erfolg
    """
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
        return True
    except IOError:
        return False


def save_session(device_id: str, session_data: Dict[str, Any]) -> bool:
    """
    Speichert Session für Device-ID.

    Args:
        device_id: Geräte-Identifikator
        session_data: Vollständiges Session-Dict

    Returns:
        True bei Erfolg, False bei Fehler
    """
    _ensure_session_dir()

    try:
        session_path = get_session_path(device_id)
    except ValueError:
        return False

    # Timestamps sicherstellen
    now = datetime.now().isoformat()
    if "created_at" not in session_data:
        session_data["created_at"] = now
    session_data["last_seen"] = now
    session_data["device_id"] = device_id

    return _write_session_file(session_path, session_data)


def update_chat_data(
    device_id: str,
    chat_history: List[Tuple[str, str]],
    chat_summaries: Optional[List[str]] = None
) -> bool:
    """
    Aktualisiert Chat-Daten einer Session.

    Erstellt neue Session falls nicht vorhanden.
    Effizienter als save_session() wenn nur Chat-Daten geändert werden.

    Args:
        device_id: Geräte-Identifikator
        chat_history: Liste von (user, assistant) Tupeln
        chat_summaries: Optional - Liste von Summary-Strings

    Returns:
        True bei Erfolg
    """
    # Bestehende Session laden oder neue erstellen
    session = load_session(device_id)

    if session is None:
        session = {
            "created_at": datetime.now().isoformat(),
            "pin_hash": None,
            "data": {}
        }

    # Chat-Daten aktualisieren
    # WICHTIG: Tuples werden als Listen serialisiert, beim Laden zurückkonvertieren!
    session["data"]["chat_history"] = [list(msg) for msg in chat_history]

    if chat_summaries is not None:
        session["data"]["chat_summaries"] = list(chat_summaries)

    return save_session(device_id, session)


def delete_session(device_id: str) -> bool:
    """
    Löscht Session komplett.

    Args:
        device_id: Geräte-Identifikator

    Returns:
        True bei Erfolg
    """
    try:
        session_path = get_session_path(device_id)
        if session_path.exists():
            session_path.unlink()
        return True
    except (ValueError, IOError):
        return False


# ============================================================
# PIN-Funktionen (Phase 2 - für Cross-Device Access)
# ============================================================

def hash_pin(pin: str) -> str:
    """
    Hasht PIN mit SHA-256.

    Args:
        pin: Klartext-PIN

    Returns:
        Hash-String im Format "sha256:..."
    """
    return f"sha256:{hashlib.sha256(pin.encode()).hexdigest()}"


def verify_pin(pin: str, pin_hash: str) -> bool:
    """
    Verifiziert PIN gegen gespeicherten Hash.

    Args:
        pin: Klartext-PIN zum Prüfen
        pin_hash: Gespeicherter Hash

    Returns:
        True wenn PIN korrekt
    """
    if not pin_hash or not pin_hash.startswith("sha256:"):
        return False
    return hash_pin(pin) == pin_hash


def set_session_pin(device_id: str, pin: str) -> bool:
    """
    Setzt oder aktualisiert PIN für Session.

    Args:
        device_id: Geräte-Identifikator
        pin: Neuer PIN (Klartext, wird gehasht)

    Returns:
        True bei Erfolg
    """
    session = load_session(device_id)
    if not session:
        return False

    session["pin_hash"] = hash_pin(pin)
    return save_session(device_id, session)


def clear_session_pin(device_id: str) -> bool:
    """
    Entfernt PIN von Session.

    Args:
        device_id: Geräte-Identifikator

    Returns:
        True bei Erfolg
    """
    session = load_session(device_id)
    if not session:
        return False

    session["pin_hash"] = None
    return save_session(device_id, session)


def get_session_with_pin(device_id: str, pin: str) -> Optional[Dict[str, Any]]:
    """
    Lädt Session nur wenn PIN korrekt ist.

    Für Cross-Device Zugriff: User gibt fremde device_id + PIN ein.

    Args:
        device_id: Geräte-Identifikator
        pin: PIN zum Verifizieren

    Returns:
        Session-Dict wenn PIN korrekt, sonst None
    """
    session = load_session(device_id)
    if not session:
        return None

    pin_hash = session.get("pin_hash")
    if not pin_hash:
        # Session hat keinen PIN - Zugriff verweigern
        return None

    if not verify_pin(pin, pin_hash):
        return None

    return session


# ============================================================
# Cleanup (für Hintergrund-Task)
# ============================================================

def cleanup_old_sessions(max_age_days: int = 30) -> int:
    """
    Löscht Sessions die älter als max_age_days sind.

    Basiert auf Datei-Änderungszeit (nicht last_seen im JSON),
    da das effizienter ist als jede Datei zu parsen.

    Args:
        max_age_days: Maximales Alter in Tagen

    Returns:
        Anzahl gelöschter Sessions
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
