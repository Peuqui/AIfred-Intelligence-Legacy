"""
Configuration Module - Central location for all constants and paths

This module contains all global configuration variables used across
the AIfred Intelligence application.
"""

from pathlib import Path

# ============================================================
# PROJECT PATHS
# ============================================================
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()  # Go up to repo root
PIPER_MODEL_PATH = PROJECT_ROOT / "piper_models" / "de_DE-thorsten-medium.onnx"
SETTINGS_FILE = PROJECT_ROOT / "assistant_settings.json"
SSL_KEYFILE = PROJECT_ROOT / "ssl" / "privkey.pem"
SSL_CERTFILE = PROJECT_ROOT / "ssl" / "fullchain.pem"

# ============================================================
# DEBUG CONFIGURATION
# ============================================================
DEBUG_ENABLED = True  # Set to False to disable debug output

# ============================================================
# LOGGING CONFIGURATION (Unified System)
# ============================================================
# Console Debug: Messages ins UI Debug-Console senden
CONSOLE_DEBUG_ENABLED = True

# File Debug: Messages ins Log-File schreiben
FILE_DEBUG_ENABLED = True

# ============================================================
# WHISPER MODELS CONFIGURATION
# ============================================================
WHISPER_MODELS = {
    "tiny (39MB, schnell, englisch)": "tiny",
    "base (74MB, schneller, multilingual)": "base",
    "small (466MB, bessere Qualität, multilingual)": "small",
    "medium (1.5GB, hohe Qualität, multilingual)": "medium",
    "large-v3 (2.9GB, beste Qualität, multilingual)": "large-v3"
}

# ============================================================
# LANGUAGE CONFIGURATION (i18n)
# ============================================================
# Language for prompts and UI
# "auto" = Detect from user input
# "de"   = German (Deutsch)
# "en"   = English
DEFAULT_LANGUAGE = "auto"

# ============================================================
# DEFAULT SETTINGS
# ============================================================
DEFAULT_SETTINGS = {
    "model": "qwen3:8b",
    "automatik_model": "qwen2.5:3b",
    "voice": "Deutsch (Katja)",
    "tts_speed": 1.25,
    "enable_tts": False,
    "tts_engine": "Edge TTS (Cloud, beste Qualität)",
    "whisper_model": "small (466MB, bessere Qualität, multilingual)",
    "research_mode": "🤖 Automatik (variabel, KI entscheidet)",
    "show_transcription": False,
    "enable_gpu": True
    # Temperature wird NICHT gespeichert - immer 0.2 für Web-Recherche (sicher)
    # User kann pro Session im UI ändern, aber es bleibt nicht persistent
}

# ============================================================
# BACKEND-SPECIFIC DEFAULT MODELS
# ============================================================
# Jedes Backend hat andere Modellnamen und nicht alle Modelle sind überall verfügbar
BACKEND_DEFAULT_MODELS = {
    "ollama": {
        "selected_model": "qwen3:8b",           # GGUF Q4/Q8, ~5.2GB
        "automatik_model": "qwen2.5:3b",        # GGUF Q4/Q8, ~1.9GB
    },
    "vllm": {
        "selected_model": "Qwen/Qwen3-8B-AWQ",  # AWQ 4-bit, ~5GB (Main LLM)
        "automatik_model": "Qwen/Qwen3-8B-AWQ", # Same as main (vLLM loads only ONE model at a time)
    },
    "tabbyapi": {
        "selected_model": "turboderp/Qwen3-8B-4.0bpw-exl2",   # EXL2 4bpw
        "automatik_model": "turboderp/Qwen3-8B-4.0bpw-exl2",  # Same as main (TabbyAPI loads only ONE model)
    },
}

# ============================================================
# AVAILABLE VOICES
# ============================================================
VOICES = {
    "Deutsch (Katja)": "de-DE-KatjaNeural",
    "Deutsch (Conrad)": "de-DE-ConradNeural",
    "Englisch (Jenny)": "en-US-JennyNeural",
    "Englisch (Guy)": "en-US-GuyNeural",
    "Französisch (Denise)": "fr-FR-DeniseNeural",
    "Spanisch (Elvira)": "es-ES-ElviraNeural"
}

# ============================================================
# RESEARCH MODES
# ============================================================
RESEARCH_MODES = [
    "🤖 Automatik (variabel, KI entscheidet)",
    "❌ Aus (nur eigenes Wissen)",
    "🔍 Web-Suche Schnell (3 Quellen)",
    "📚 Web-Suche Ausführlich (5 Quellen)"
]

# ============================================================
# TTS ENGINES
# ============================================================
TTS_ENGINES = [
    "Edge TTS (Cloud, beste Qualität)",
    "Piper TTS (Lokal, Offline)"
]

# ============================================================
# CONTEXT MANAGEMENT
# ============================================================
# Maximale Tokens für RAG-Context (Recherche-Ergebnisse)
# Hinweis: Total Context = RAG_CONTEXT + System-Prompt + History + User-Message
# Bei 40k Model-Limit → empfohlen: 20k RAG Context (50% Reserve)
# Bei größeren Models (z.B. mit Tesla P40) kann dieser Wert erhöht werden
MAX_RAG_CONTEXT_TOKENS = 20000

# Maximale Wörter pro einzelner Quelle (Wikipedia, News-Artikel, etc.)
# Verhindert, dass eine einzelne Quelle den gesamten Context dominiert
MAX_WORDS_PER_SOURCE = 2000

# Token-zu-Zeichen Ratio für Context-Berechnung
# Deutsch/Englisch Mix: ~3 Zeichen pro Token
CHARS_PER_TOKEN = 3

# ============================================================
# HISTORY SUMMARIZATION CONFIGURATION
# ============================================================
# Trigger-Punkt: Bei welchem Prozentsatz des Context-Limits soll komprimiert werden?
HISTORY_COMPRESSION_THRESHOLD = 0.7  # 70% des Context-Limits (Produktiv-Wert)

# Anzahl der Messages die auf einmal komprimiert werden
# (6 Messages = 3 Frage-Antwort-Paare)
HISTORY_MESSAGES_TO_COMPRESS = 6  # 3 Frage-Antwort-Paare

# Maximale Anzahl von Summaries die gespeichert werden
# Bei mehr wird die älteste gelöscht (FIFO)
HISTORY_MAX_SUMMARIES = 10

# Target-Größe für eine Summary in Tokens
HISTORY_SUMMARY_TARGET_TOKENS = 1000

# Target-Größe für eine Summary in Wörtern (für Prompt)
HISTORY_SUMMARY_TARGET_WORDS = 750

# Temperature für Summary-Generierung (niedriger = faktischer)
HISTORY_SUMMARY_TEMPERATURE = 0.3

# Context-Limit für Summary-LLM (sollte nicht zu groß sein)
HISTORY_SUMMARY_CONTEXT_LIMIT = 4096

# ============================================================
# VECTOR CACHE CONFIGURATION (ChromaDB Similarity Thresholds)
# ============================================================
# Distance-Thresholds für semantische Ähnlichkeit (Cosine Distance)
# 0.0 = identisch, 2.0 = komplett verschieden

# Normale Cache-Abfrage (ohne explizite Keywords wie "recherchiere")
CACHE_DISTANCE_HIGH = 0.5      # < 0.5 = HIGH confidence Cache-Hit (direct answer)
CACHE_DISTANCE_MEDIUM = 0.5    # >= 0.5 = Trigger RAG check (not direct cache hit)

# Explizite Recherche-Keywords ("recherchiere", "google", etc.)
# Semantische Duplikat-Erkennung (zeitunabhängig)
CACHE_DISTANCE_DUPLICATE = 0.3  # < 0.3 = Sehr ähnlich (semantisches Duplikat, wird immer gemerged)
                                # Beispiele:
                                # - "recherchiere Python" vs "recherchiere Python Tutorial" = ~0.15
                                # - "recherchiere Wetter Berlin" vs "recherchiere Wetter Hamburg" = ~0.25
                                # - "recherchiere Python" vs "recherchiere Java" = ~0.6

# RAG-Mode Distance Threshold
CACHE_DISTANCE_RAG = 1.2  # < 1.2 = Ähnlich genug für RAG-Kontext (später implementiert)

# Volatile Keywords - Loaded from prompts/cache_volatile_keywords.txt
# Diese Keywords triggern eine LLM-Entscheidung, ob trotzdem gecacht werden soll
def _load_volatile_keywords():
    """
    Load volatile keywords from file (multilingual).
    File contains both German and English keywords.
    """
    keywords = []
    keywords_file = PROJECT_ROOT / "prompts" / "cache_volatile_keywords.txt"

    try:
        with open(keywords_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if line and not line.startswith('#'):
                    keywords.append(line)
    except FileNotFoundError:
        import warnings
        warnings.warn(f"⚠️ Keywords file not found: {keywords_file}, using empty list")

    return keywords

CACHE_EXCLUDE_VOLATILE = _load_volatile_keywords()

# ============================================================
# CONFIG VALIDATION (Safety Checks)
# ============================================================
# No validation needed - token-based compression handles all edge cases
