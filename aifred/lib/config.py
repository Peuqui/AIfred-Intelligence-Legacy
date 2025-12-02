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
    # NOTE: Model names are defined in BACKEND_DEFAULT_MODELS below (backend-specific)
    # They will be merged in settings.py get_default_settings()
    "backend_type": "ollama",  # Default backend: "ollama", "vllm", "tabbyapi"
    "voice": "Deutsch (Katja)",
    "tts_speed": 1.25,
    "enable_tts": False,
    "tts_engine": "Edge TTS (Cloud, beste Qualität)",
    "whisper_model": "small (466MB, bessere Qualität, multilingual)",
    "research_mode": "automatik",  # Internal value: "automatik", "quick", "deep", "none"
    "show_transcription": False,
    "enable_gpu": True,
    "temperature": 0.7,
    "temperature_mode": "auto",  # "auto" (Intent-Detection) or "manual" (user slider)
    "enable_thinking": True  # Qwen3 Thinking Mode (Chain-of-Thought Reasoning)
}

# ============================================================
# OLLAMA SYSTEMD CONFIGURATION
# ============================================================
# Ollama runs as a systemd service and reads environment variables from:
# /etc/systemd/system/ollama.service.d/override.conf
#
# Current configuration (2x Tesla P40, 48GB total VRAM):
#   CUDA_VISIBLE_DEVICES=0,1          # Both GPUs visible
#   OLLAMA_MAX_LOADED_MODELS=2        # Max 2 models in VRAM (Automatik + Main)
#   OLLAMA_NUM_PARALLEL=2             # Parallel inference on both GPUs
#   OLLAMA_GPU_OVERHEAD=536870912     # 512 MB GPU overhead (default ~1GB)
#
# Note: For Dual-LLM Debate System (future feature), OLLAMA_MAX_LOADED_MODELS=2
# is perfect since we only need 2 models debating each other (no Automatik needed).
#
# To modify: Edit override.conf and reload systemd
#   sudo systemctl daemon-reload
#   sudo systemctl restart ollama
# ============================================================

# ============================================================
# BACKEND-SPECIFIC DEFAULT MODELS
# ============================================================
# Für Performance-Vergleiche: Alle Backends nutzen die gleichen Modell-Größen
# - Main LLM: Qwen3-30B-A3B-Instruct-2507 (~18GB, MoE mit 3B aktiv)
# - Automatik: Qwen3-4B-Instruct-2507 (~2.6GB)
BACKEND_DEFAULT_MODELS = {
    "ollama": {
        "selected_model": "qwen3:30b-a3b-instruct-2507-q4_K_M",           # GGUF Q4_K_M, ~17.3GB
        "automatik_model": "qwen3:4b-instruct-2507-q4_K_M",               # GGUF Q4_K_M, ~2.6GB
    },
    "vllm": {
        "selected_model": "cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit", # AWQ 4-bit, ~18GB (CONFIRMED)
        "automatik_model": "cpatonn/Qwen3-4B-Instruct-2507-AWQ-4bit",     # AWQ 4-bit, ~2.8GB (CONFIRMED)
    },
    "tabbyapi": {
        "selected_model": "turboderp/Qwen3-30B-A3B-exl3",                 # EXL3, ~18GB (CONFIRMED)
        "automatik_model": "ArtusDev/Qwen_Qwen3-4B-Instruct-2507-EXL3",   # EXL3, ~2.8GB (CONFIRMED)
    },
    "koboldcpp": {
        "selected_model": "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M",          # GGUF Q4_K_M, ~17.3GB (from ~/models/)
        "automatik_model": "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M",         # KoboldCPP: only 1 model (same as selected)
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
# VRAM MANAGEMENT (Dynamic Context Calculation)
# ============================================================
# Enable VRAM-based context calculation to prevent CPU offloading
# When disabled, uses model's architectural limit only
ENABLE_VRAM_CONTEXT_CALCULATION = True

# Safety margin reserved for OS and other GPU processes (MB)
# Realistic overhead: Xorg (~300MB) + Whisper STT (~1-2GB if active) + Buffer (~200MB)
# Optimized: 512MB for desktop + overhead (not wasteful)
VRAM_SAFETY_MARGIN = 512  # MB

# Empirical ratio: MB of VRAM per context token
# Based on KV cache measurements and research:
# - LLaMA-2 7B: ~0.5 MB/token (research baseline)
# - Qwen3-4B Q4_K_M: ~0.15 MB/token (empirically tested, 120k tokens @ 21GB VRAM)
# - Qwen3-30B-A3B MoE Q4_K_M: ~0.10 MB/token (empirically tested, 26.2k tokens @ 22GB VRAM)
# Different ratios for Dense vs MoE models:
# - Dense models: Use all parameters → higher KV cache overhead → 0.15 MB/token
# - MoE models: Only activate subset of experts → lower KV cache overhead → 0.10 MB/token
VRAM_CONTEXT_RATIO_DENSE = 0.15  # ~150KB per token (Dense models)
VRAM_CONTEXT_RATIO_MOE = 0.10    # ~100KB per token (MoE models, 48% more context!)

# vLLM Context Calibration Safety Buffer (Tokens)
# Fixed token buffer applied when parsing vLLM error messages
# Compensates for constant VRAM overhead (~100 tokens) between startup attempts:
# - CUDA context switches (~50MB)
# - GPU memory fragmentation (~30MB)
# - PyTorch cache residue (~20MB)
# - vLLM's VRAM estimates have ~2-3% variance between startup attempts
# Using percentage-based buffer to scale with context size (2% of vLLM's reported max)
VLLM_CONTEXT_SAFETY_PERCENT = 0.02  # 2% safety buffer (iteratively applied to each vLLM-reported max)

# KoboldCPP Context Calibration Safety Buffer (Fixed Tokens)
# Fixed token reduction for KoboldCPP when VRAM-calculated context fails
# Unlike vLLM (which uses percentage), llama.cpp benefits from fixed reduction:
# - GGUF models have fixed memory footprint (no dynamic allocation)
# - llama.cpp OOM errors don't provide exact limits (only "out of memory")
# - With Q4 KV cache: 1500 tokens ≈ 75MB safety buffer (realistic for Q4 quantized KV)
KOBOLDCPP_CONTEXT_SAFETY_TOKENS = 1500  # 1.5K token reduction for final attempt (Q4 KV)

# ============================================================
# KOBOLDCPP ROPE SCALING CONFIGURATION
# ============================================================
# Linear RoPE Scaling factor for context extension beyond native limit
#
# Quality Impact (Perplexity increase):
# - 1.0x: No scaling (native context only, best quality)
# - 1.5x: ~5% perplexity increase (barely noticeable)
# - 2.0x: ~10% perplexity increase (noticeable in long texts)
# - 3.0x+: 40-60% perplexity increase (significant quality loss)
#
# Example: Native 32K context → 1.5x = 48K, 2.0x = 64K
#
# NOTE: vLLM/TabbyAPI use superior YaRN scaling (better quality at same factor)
# KoboldCPP only supports Linear RoPE (llama.cpp limitation)
KOBOLDCPP_ROPE_SCALING_FACTOR = 1.5  # Conservative 1.5x for good quality/capacity balance

# Maximum context size supported by KoboldCPP (llama.cpp argparse limit)
# This is a hard limit in KoboldCPP's --contextsize parameter
# If this changes in future versions, update this constant
KOBOLDCPP_MAX_CONTEXT = 61440  # 60K tokens (Baseline für stufenweise Tests)

# ============================================================
# KOBOLDCPP INACTIVITY AUTO-SHUTDOWN (Rolling Window)
# ============================================================
# Automatically shutdown KoboldCPP after inactivity period to save power (~100W idle)
# Server restarts automatically on next request (Phase 1: Backend Auto-Restart)
#
# Rolling Window Approach:
# - Continuous GPU checks every KOBOLDCPP_INACTIVITY_CHECK_INTERVAL seconds
# - Shutdown when N consecutive checks were idle (N = TIMEOUT / INTERVAL)
# - Any GPU activity resets counter to 0
#
# Testing: Set KOBOLDCPP_INACTIVITY_TIMEOUT = 30 for 30-second tests
# Production: Set KOBOLDCPP_INACTIVITY_TIMEOUT = 1800 for 30-minute timeout
KOBOLDCPP_INACTIVITY_TIMEOUT = 300  # Seconds of inactivity before auto-shutdown (300s = 5 minutes)
KOBOLDCPP_INACTIVITY_CHECK_INTERVAL = 60  # Check GPU utilization every 60 seconds (1 minute)

# ============================================================
# VECTOR CACHE CONFIGURATION (ChromaDB Similarity Thresholds)
# ============================================================
# Distance-Thresholds für semantische Ähnlichkeit (Cosine Distance)
# 0.0 = identisch, 2.0 = komplett verschieden

# Normale Cache-Abfrage (ohne explizite Keywords wie "recherchiere")
CACHE_DISTANCE_HIGH = 0.5      # < 0.5 = HIGH confidence Cache-Hit (direct answer)

# ============================================================
# TTL-BASED CACHE SYSTEM (Volatility Levels)
# ============================================================
# Time-To-Live values for different volatility categories
# Main LLM determines volatility via <volatility> tag in response
TTL_HOURS = {
    'DAILY': 24,        # News, current events, "latest developments"
    'WEEKLY': 168,      # Political updates (7 days)
    'MONTHLY': 720,     # Semi-current topics (30 days)
    'PERMANENT': None   # Timeless facts, no expiry
}

# Cache cleanup configuration
CACHE_CLEANUP_INTERVAL_HOURS = 12  # Background task runs every 12 hours
CACHE_STARTUP_CLEANUP = True        # Delete expired entries on server startup

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
