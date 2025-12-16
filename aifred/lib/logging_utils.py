"""
Logging Utilities - Reflex Edition

Portiert von Gradio-Legacy mit Anpassungen für Reflex State Management

UNIFIED LOGGING SYSTEM:
- log_message(): Zentrale Funktion für alle Logging-Anforderungen
- Config-gesteuert via CONSOLE_DEBUG_ENABLED und FILE_DEBUG_ENABLED
- debug_print_prompt() und debug_print_messages(): Spezialisierte Formatierung
"""

import os
import time
from datetime import datetime
from typing import List
from .config import CONSOLE_DEBUG_ENABLED, FILE_DEBUG_ENABLED

# ============================================================
# DEBUG-LOG-FILE Configuration
# ============================================================
_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_AIFRED_DIR = os.path.dirname(_LIB_DIR)
_PROJECT_ROOT = os.path.dirname(_AIFRED_DIR)
_LOGS_DIR = os.path.join(_PROJECT_ROOT, "logs")

# Logs-Ordner erstellen falls nicht vorhanden
os.makedirs(_LOGS_DIR, exist_ok=True)

DEBUG_LOG_FILE = os.path.join(_LOGS_DIR, "aifred_debug.log")
_debug_log_initialized = False
DEBUG_LOG_MAX_SIZE_MB = 1  # Max 1 MB, danach rotieren

# ============================================================
# CONSOLE STATE (für Reflex UI)
# ============================================================
_console_messages: List[str] = []  # Thread-safe list für Console-Output
MAX_CONSOLE_MESSAGES = 200

# Queue für Thread-to-UI Kommunikation (Pipe!)
import queue  # noqa: E402
_message_queue: queue.Queue = queue.Queue(maxsize=500)  # Thread-safe Pipe!


def initialize_debug_log(force_reset: bool = False) -> None:
    """
    Initialisiert Debug-Log-Datei (überschreibt bei Service-Start)

    Args:
        force_reset: Wenn True, wird Log immer zurückgesetzt (für Reflex-Start)
    """
    global _debug_log_initialized

    if _debug_log_initialized and not force_reset:
        return

    try:
        if os.path.exists(DEBUG_LOG_FILE):
            file_size_mb = os.path.getsize(DEBUG_LOG_FILE) / (1024 * 1024)
            if file_size_mb > DEBUG_LOG_MAX_SIZE_MB:
                # Rotiere: Alte Datei → .old
                old_file = DEBUG_LOG_FILE + ".old"
                if os.path.exists(old_file):
                    os.remove(old_file)
                os.rename(DEBUG_LOG_FILE, old_file)
                print(f"🔄 Debug-Log rotiert: {file_size_mb:.1f} MB → {old_file}", flush=True)

        # Neue Session: File ÜBERSCHREIBEN (frischer Start)
        # Alte Logs werden bei Rotation gesichert (.old)
        with open(DEBUG_LOG_FILE, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write(f"=== AIfred Intelligence - Service gestartet: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            f.write("=" * 60 + "\n\n")

        _debug_log_initialized = True
        print(f"✅ Debug-Log initialisiert: {DEBUG_LOG_FILE}", flush=True)

    except Exception as e:
        print(f"⚠️ Debug-Log-Initialisierung fehlgeschlagen: {e}", flush=True)


def log_message(message: str, category: str = "info") -> None:
    """
    ZENTRALE LOGGING-FUNKTION - Unified System

    Schreibt Messages basierend auf Config:
    - FILE_DEBUG_ENABLED: Ins Debug-Log-File
    - CONSOLE_DEBUG_ENABLED: In Queue für UI Debug-Console

    Args:
        message: Die zu loggende Nachricht (ohne Timestamp!)
        category: Kategorie für Filterung ("startup", "llm", "decision", "stats", "info")

    Behavior:
        - Fügt automatisch Timestamp hinzu (HH:MM:SS.mmm für File, HH:MM:SS für Console)
        - Auto-initialisiert Debug-Log beim ersten Aufruf
        - Thread-safe Queue für UI-Kommunikation
    """
    global _console_messages, _debug_log_initialized

    # Auto-initialize on first call
    if not _debug_log_initialized:
        initialize_debug_log()

    # ============================================================
    # FILE DEBUG (wenn aktiviert)
    # ============================================================
    if FILE_DEBUG_ENABLED:
        try:
            timestamp_file = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # HH:MM:SS.mmm
            with open(DEBUG_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"{timestamp_file} | {message}\n")
        except Exception as e:
            print(f"⚠️ Debug-Log-File-Fehler: {e}", flush=True)

    # ============================================================
    # CONSOLE DEBUG (wenn aktiviert)
    # ============================================================
    if CONSOLE_DEBUG_ENABLED:
        timestamp_console = time.strftime("%H:%M:%S")  # HH:MM:SS (wie Legacy)
        formatted_msg = f"{timestamp_console} | {message}"

        # In Console-State anhängen
        _console_messages.append(formatted_msg)

        # Limit einhalten (FIFO)
        if len(_console_messages) > MAX_CONSOLE_MESSAGES:
            _console_messages = _console_messages[-MAX_CONSOLE_MESSAGES:]

        # In Queue schreiben (für State-Polling!)
        try:
            _message_queue.put_nowait(formatted_msg)  # Non-blocking
        except queue.Full:
            pass  # Queue voll, alte Messages sind in _console_messages


def debug_print_prompt(prompt_type: str, prompt: str, model_name: str) -> None:
    """
    Logs prompt with standardized formatting

    Args:
        prompt_type: Type of prompt (e.g., "DECISION", "QUERY_OPT")
        prompt: The actual prompt text
        model_name: Name of the model receiving the prompt
    """
    log_message("=" * 60)
    log_message(f"📋 {prompt_type} PROMPT an {model_name}:")
    log_message("-" * 60)
    log_message(prompt)
    log_message("-" * 60)
    log_message(f"Prompt-Länge: {len(prompt)} Zeichen, ~{len(prompt.split())} Wörter")
    log_message("=" * 60)


def debug_print_messages(messages: list, model_name: str, context: str = "", **llm_params) -> None:
    """
    Logs LLM messages array with standardized formatting

    Args:
        messages: List of message dicts with 'role' and 'content'
        model_name: Name of the model receiving the messages
        context: Additional context (e.g., "(Decision)", "(Query-Opt)")
        **llm_params: Additional LLM parameters to log (temperature, num_ctx, etc.)
    """
    log_message("=" * 60)
    log_message(f"📨 MESSAGES an {model_name} {context}:")
    log_message("-" * 60)
    for i, msg in enumerate(messages):
        log_message(f"Message {i+1} - Role: {msg['role']}")
        content = msg['content']

        # Preview first 500 chars for system prompts, full content for user messages
        if len(content) > 500 and msg['role'] == 'system':
            preview = content[:500]
            log_message(f"Content (erste 500 Zeichen): {preview}")
            log_message(f"... [noch {len(content) - 500} Zeichen]")
        else:
            log_message(f"Content: {content}")
        log_message("-" * 60)

    # Log additional parameters if provided
    if llm_params:
        param_str = ", ".join([f"{k}: {v}" for k, v in llm_params.items()])
        log_message(f"Total Messages: {len(messages)}, {param_str}")
    else:
        log_message(f"Total Messages: {len(messages)}")
    log_message("=" * 60)


# Console Separator Konstante (zentral definiert, wird überall verwendet)
CONSOLE_SEPARATOR = "─" * 20

def console_separator() -> None:
    """Fügt eine horizontale Trennlinie in die Console ein"""
    global _console_messages, _message_queue
    _console_messages.append(CONSOLE_SEPARATOR)

    # In Queue schreiben (Pipe für UI-Thread!)
    try:
        _message_queue.put_nowait(CONSOLE_SEPARATOR)
    except queue.Full:
        pass  # Queue voll, ignorieren

    # Limit einhalten
    if len(_console_messages) > MAX_CONSOLE_MESSAGES:
        _console_messages = _console_messages[-MAX_CONSOLE_MESSAGES:]


def clear_console() -> None:
    """Löscht alle Console-Messages und Queue"""
    global _console_messages, _message_queue
    _console_messages = []

    # Queue leeren (alle Messages verwerfen)
    while not _message_queue.empty():
        try:
            _message_queue.get_nowait()
        except queue.Empty:
            break
