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
SSL_KEYFILE = PROJECT_ROOT / "ssl" / "privkey.pem"
SSL_CERTFILE = PROJECT_ROOT / "ssl" / "fullchain.pem"
# Settings are stored in ~/.config/aifred/settings.json (see aifred/lib/settings.py)

# ============================================================
# BACKEND API URL (for TTS audio URLs, HTML preview, etc.)
# ============================================================
# Import from rxconfig (single source of truth - auto-detects local IP)
# The /_upload/ endpoint is only served by the backend, not frontend
from rxconfig import API_URL as BACKEND_API_URL

# ============================================================
# DEBUG CONFIGURATION
# ============================================================
DEBUG_ENABLED = True  # Set to False to disable debug output
DEBUG_MESSAGES_MAX = 500  # Maximum number of debug messages to keep in UI console

# ============================================================
# LOGGING CONFIGURATION (Unified System)
# ============================================================
# Console Debug: Send messages to UI debug console
CONSOLE_DEBUG_ENABLED = True

# File Debug: Write messages to log file
FILE_DEBUG_ENABLED = True

# ============================================================
# WHISPER MODELS CONFIGURATION
# ============================================================
WHISPER_MODELS = {
    "tiny (39MB, fast, english)": "tiny",
    "base (74MB, faster, multilingual)": "base",
    "small (466MB, better quality, multilingual)": "small",
    "medium (1.5GB, high quality, multilingual)": "medium",
    "large-v3 (2.9GB, best quality, multilingual)": "large-v3"
}

# Whisper Device Configuration
# "cpu" = Runs on CPU (preserves GPU VRAM for LLM inference)
# "cuda" = Runs on GPU (faster but uses VRAM - not recommended with Tesla P40)
# NOTE: CPU inference on Ryzen 7 7840HS is very fast (0.1-0.2s) and recommended
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"  # int8 for CPU, float16 for GPU

# ============================================================
# LANGUAGE CONFIGURATION (i18n)
# ============================================================
# Language for prompts and UI (synced with ui_language in state.py)
# Language detection is done via LLM-based Intent Detection
# "de" = German (Deutsch)
# "en" = English
DEFAULT_LANGUAGE = "de"

# ============================================================
# DEFAULT SETTINGS
# ============================================================
DEFAULT_SETTINGS = {
    # NOTE: Model names are defined in BACKEND_DEFAULT_MODELS below (backend-specific)
    # They will be merged in settings.py get_default_settings()
    "user_name": "",  # User's name (leave empty - set via UI, saved in settings.json)
    "backend_type": "ollama",  # Default backend: "ollama", "vllm", "tabbyapi"
    "voice": "Deutsch (Katja)",
    "tts_playback_rate": "1.25x",  # Browser playback speed (generation always at 1.0)
    "enable_tts": False,
    "tts_engine": "Edge TTS (Cloud, best quality)",
    "whisper_model": "small (466MB, better quality, multilingual)",
    "research_mode": "automatik",  # Internal value: "automatik", "quick", "deep", "none"
    "show_transcription": False,
    "enable_gpu": True,
    "temperature": 0.7,
    "temperature_mode": "auto",  # "auto" (Intent-Detection) or "manual" (user slider)
    "enable_thinking": False  # Qwen3 Thinking Mode (Chain-of-Thought Reasoning)
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
# For performance comparisons: All backends use the same model sizes
# - Main LLM: Qwen3-30B-A3B-Instruct-2507 (~18GB, MoE with 3B active)
# - Automatik: Qwen3-4B-Instruct-2507 (~2.6GB)
# - Multi-Agent (Sokrates, Salomo, AIfred): Qwen3-4B-Instruct-2507 (~2.6GB)
BACKEND_DEFAULT_MODELS = {
    "ollama": {
        "aifred_model": "qwen3:4b-instruct-2507-q4_K_M",                  # AIfred Main-LLM: GGUF Q8_0, ~32GB
        "automatik_model": "qwen3:4b-instruct-2507-q4_K_M",               # Automatik: GGUF Q4_K_M, ~2.6GB
        "sokrates_model": "qwen3:4b-instruct-2507-q4_K_M",                # Sokrates: GGUF Q4_K_M, ~2.6GB
        "salomo_model": "qwen3:4b-instruct-2507-q4_K_M",                  # Salomo: GGUF Q4_K_M, ~2.6GB
        "vision_model": "qwen3-vl:8b",                                    # Vision: Qwen3-VL 8B
    },
    "vllm": {
        "aifred_model": "cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit",   # AIfred Main-LLM: AWQ 4-bit, ~18GB (CONFIRMED)
        "automatik_model": "cpatonn/Qwen3-4B-Instruct-2507-AWQ-4bit",     # Automatik: AWQ 4-bit, ~2.8GB (CONFIRMED)
        "sokrates_model": "cpatonn/Qwen3-4B-Instruct-2507-AWQ-4bit",      # Sokrates: AWQ 4-bit, ~2.8GB
        "salomo_model": "cpatonn/Qwen3-4B-Instruct-2507-AWQ-4bit",        # Salomo: AWQ 4-bit, ~2.8GB
        "vision_model": "",                                                # Vision: Auto-detect
    },
    "tabbyapi": {
        "aifred_model": "turboderp/Qwen3-30B-A3B-exl3",                   # AIfred Main-LLM: EXL3, ~18GB (CONFIRMED)
        "automatik_model": "ArtusDev/Qwen_Qwen3-4B-Instruct-2507-EXL3",   # Automatik: EXL3, ~2.8GB (CONFIRMED)
        "sokrates_model": "ArtusDev/Qwen_Qwen3-4B-Instruct-2507-EXL3",    # Sokrates: EXL3, ~2.8GB
        "salomo_model": "ArtusDev/Qwen_Qwen3-4B-Instruct-2507-EXL3",      # Salomo: EXL3, ~2.8GB
        "vision_model": "",                                                # Vision: Auto-detect
    },
    "koboldcpp": {
        "aifred_model": "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M",            # AIfred Main-LLM: GGUF Q4_K_M, ~17.3GB (from ~/models/)
        "automatik_model": "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M",         # KoboldCPP: only 1 model (same as AIfred)
        "sokrates_model": "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M",          # KoboldCPP: only 1 model
        "salomo_model": "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M",            # KoboldCPP: only 1 model
        "vision_model": "",                                                # Vision: Not supported
    },
    "llamacpp": {
        "aifred_model": "Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf",        # AIfred Main-LLM: GGUF Q4_K_M, ~17.3GB (from ~/models/)
        "automatik_model": "Qwen3-8B-Q4_K_M.gguf",                        # Automatik: GGUF Q4_K_M, ~4.7GB
        "sokrates_model": "Qwen3-8B-Q4_K_M.gguf",                         # Sokrates: GGUF Q4_K_M, ~4.7GB
        "salomo_model": "Qwen3-8B-Q4_K_M.gguf",                           # Salomo: GGUF Q4_K_M, ~4.7GB
        "vision_model": "",                                                # Vision: Auto-detect
    },
    "cloud_api": {
        "aifred_model": "qwen-plus",                                          # Default: Qwen Plus (free tier)
        "automatik_model": "qwen-turbo",                                      # Automatik: Qwen Turbo (faster, free)
        "sokrates_model": "qwen-turbo",                                       # Sokrates: Qwen Turbo
        "salomo_model": "qwen-turbo",                                         # Salomo: Qwen Turbo
        "vision_model": "",                                                   # Vision: Not yet supported
    },
}

# ============================================================
# CLOUD API PROVIDERS
# ============================================================
# Configuration for cloud-based LLM APIs (OpenAI-compatible)
# API keys are read from environment variables (not stored in settings!)
CLOUD_API_PROVIDERS = {
    "claude": {
        "name": "Claude (Anthropic)",
        "base_url": "https://api.anthropic.com/v1",
        "env_key": "ANTHROPIC_API_KEY",
        # Models are fetched dynamically from API - no hardcoded list!
    },
    "qwen": {
        "name": "Qwen (DashScope)",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "env_key": "DASHSCOPE_API_KEY",
        # Models are fetched dynamically from API - no hardcoded list!
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "env_key": "DEEPSEEK_API_KEY",
        # Models are fetched dynamically from API - no hardcoded list!
    },
    "kimi": {
        "name": "Kimi (Moonshot)",
        "base_url": "https://api.moonshot.cn/v1",
        "env_key": "MOONSHOT_API_KEY",
        # Models are fetched dynamically from API - no hardcoded list!
    },
}

# Cloud API: No context calculation needed
# Cloud providers manage context themselves - we don't need to track limits
# History compression uses LOCAL models only (where we know actual limits)

# ============================================================
# BACKEND URLs
# ============================================================
# Default URLs for each backend type (localhost development)
# Use these constants instead of hardcoding URLs!
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_VLLM_URL = "http://localhost:8001/v1"
DEFAULT_TABBYAPI_URL = "http://localhost:5000/v1"
DEFAULT_KOBOLDCPP_URL = "http://localhost:5001/v1"

BACKEND_URLS = {
    "ollama": DEFAULT_OLLAMA_URL,
    "vllm": DEFAULT_VLLM_URL,      # Port 8001 for dev (8000 on production MiniPC)
    "tabbyapi": DEFAULT_TABBYAPI_URL,
    "koboldcpp": DEFAULT_KOBOLDCPP_URL,
    "cloud_api": "",  # Dynamic - set based on provider selection
}

# Backend display labels (for UI dropdowns)
BACKEND_LABELS = {
    "ollama": "Ollama",
    "koboldcpp": "KoboldCPP",
    "tabbyapi": "TabbyAPI",
    "vllm": "vLLM",
    "cloud_api": "Cloud APIs",
}

# Backend dropdown special items (headers, separators)
BACKEND_DROPDOWN_ITEMS = {
    "header_universal": "─── Universal Compatibility (GGUF) ───",
    "separator": "─────────────────────────────────",
    "header_modern": "─── Modern GPUs (FP16) ───",
    "header_cloud": "─── Cloud APIs ───",
}

# Non-selectable backend items (headers and separators)
BACKEND_NON_SELECTABLE = ["header_universal", "separator", "header_modern", "header_cloud"]

# Default backend ordering (for dropdowns)
BACKEND_ORDER = ["ollama", "koboldcpp", "llamacpp", "tabbyapi", "vllm", "cloud_api"]

# ============================================================
# AVAILABLE VOICES (Engine-specific)
# ============================================================
# Edge TTS Voices (Cloud - Microsoft Neural Voices)
EDGE_TTS_VOICES = {
    # Deutschland (de-DE)
    "Deutsch (Katja)": "de-DE-KatjaNeural",
    "Deutsch (Amala)": "de-DE-AmalaNeural",
    "Deutsch (Seraphina)": "de-DE-SeraphinaMultilingualNeural",
    "Deutsch (Conrad)": "de-DE-ConradNeural",
    "Deutsch (Killian)": "de-DE-KillianNeural",
    "Deutsch (Florian)": "de-DE-FlorianMultilingualNeural",
    # Österreich (de-AT)
    "Österreich (Ingrid)": "de-AT-IngridNeural",
    "Österreich (Jonas)": "de-AT-JonasNeural",
    # Schweiz (de-CH)
    "Schweiz (Leni)": "de-CH-LeniNeural",
    "Schweiz (Jan)": "de-CH-JanNeural",
    # Englisch
    "Englisch (Jenny)": "en-US-JennyNeural",
    "Englisch (Guy)": "en-US-GuyNeural",
    # Weitere Sprachen
    "Französisch (Denise)": "fr-FR-DeniseNeural",
    "Spanisch (Elvira)": "es-ES-ElviraNeural",
}

# Piper TTS Voices (Local - ONNX models)
# Format: Display Name -> (model_filename, language_code)
# Models stored in ~/.local/share/piper/
PIPER_VOICES = {
    # Deutsch - Männliche Stimmen
    "Deutsch (Thorsten)": ("de_DE-thorsten-high.onnx", "de"),
    "Deutsch (Karlsson)": ("de_DE-karlsson-low.onnx", "de"),
    # Deutsch - Weibliche Stimmen
    "Deutsch (Ramona)": ("de_DE-ramona-low.onnx", "de"),
    "Deutsch (Kerstin)": ("de_DE-kerstin-low.onnx", "de"),
    "Deutsch (Eva K)": ("de_DE-eva_k-x_low.onnx", "de"),
    "Deutsch (MLS)": ("de_DE-mls-medium.onnx", "de"),  # Multi-speaker
}

# Legacy compatibility - defaults to Edge TTS voices
VOICES = EDGE_TTS_VOICES

# ============================================================
# RESEARCH MODES
# ============================================================
RESEARCH_MODES = [
    "🤖 Automatic (AI decides)",
    "❌ Off (own knowledge only)",
    "🔍 Web Search Quick (3 sources)",
    "📚 Web Search Detailed (5 sources)"
]

# ============================================================
# TTS ENGINES
# ============================================================
TTS_ENGINES = [
    "Edge TTS (Cloud, best quality)",
    "Piper TTS (Local, Offline)",
    "eSpeak (Robot, Offline)"
]

# eSpeak Voices (Local - system package)
# Install: sudo apt install espeak-ng (or espeak)
# Format: "Display Name": ("voice_id", "language_code")
# Voice variants: +m1/+m2 = male, +f1/+f2 = female
# mbrola voices: mb/mb-deX (more natural, requires mbrola package)

# All known eSpeak voices (will be filtered by get_available_espeak_voices())
_ESPEAK_VOICES_ALL = {
    # Deutsch - Standard eSpeak (roboterhaft, always available)
    "Deutsch Standard": ("de", "de"),
    "Deutsch Männlich 1": ("de+m1", "de"),
    "Deutsch Männlich 2": ("de+m2", "de"),
    "Deutsch Weiblich 1": ("de+f1", "de"),
    "Deutsch Weiblich 2": ("de+f2", "de"),
    # Deutsch - mbrola Stimmen (natürlicher, requires mbrola + mbrola-deX packages)
    "Deutsch mbrola-2 (M)": ("mb/mb-de2", "de"),
    "Deutsch mbrola-3 (F)": ("mb/mb-de3", "de"),
    "Deutsch mbrola-4 (M)": ("mb/mb-de4", "de"),
    "Deutsch mbrola-5 (F)": ("mb/mb-de5", "de"),
    "Deutsch mbrola-6 (M)": ("mb/mb-de6", "de"),
    "Deutsch mbrola-7 (F)": ("mb/mb-de7", "de"),
    # Englisch - Standard eSpeak (always available)
    "Englisch Standard": ("en", "en"),
    "Englisch US": ("en-us", "en"),
    "Englisch UK": ("en-gb", "en"),
    # Englisch - mbrola Stimmen (requires mbrola + mbrola-en1/us1-3 packages)
    "Englisch mbrola UK (M)": ("mb/mb-en1", "en"),
    "Englisch mbrola US-1 (F)": ("mb/mb-us1", "en"),
    "Englisch mbrola US-2 (M)": ("mb/mb-us2", "en"),
    "Englisch mbrola US-3 (M)": ("mb/mb-us3", "en"),
}

def get_available_espeak_voices() -> dict:
    """
    Detect available eSpeak voices at runtime.

    Standard eSpeak voices (de, en, etc.) are always available.
    mbrola voices require: sudo apt install mbrola mbrola-deX mbrola-en1 etc.

    Returns:
        dict: Filtered ESPEAK_VOICES with only available voices
    """
    import subprocess

    available = {}

    # Get list of available mbrola voices from espeak-ng (or espeak fallback)
    mbrola_available = set()
    try:
        # Try espeak-ng first (modern), fallback to espeak (legacy)
        espeak_cmd = "espeak-ng"
        try:
            subprocess.run([espeak_cmd, "--version"], capture_output=True, timeout=2)
        except (FileNotFoundError, OSError):
            espeak_cmd = "espeak"

        result = subprocess.run(
            [espeak_cmd, "--voices=mb"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n')[1:]:  # Skip header
                parts = line.split()
                if len(parts) >= 5:
                    # File column contains voice ID like "mb/mb-de2"
                    voice_file = parts[4] if len(parts) > 4 else ""
                    if voice_file.startswith("mb/"):
                        mbrola_available.add(voice_file)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # espeak not installed or timeout

    # Filter voices: include standard voices, only include available mbrola voices
    for name, (voice_id, lang) in _ESPEAK_VOICES_ALL.items():
        if voice_id.startswith("mb/"):
            # mbrola voice - check if available
            if voice_id in mbrola_available:
                available[name] = (voice_id, lang)
        else:
            # Standard eSpeak voice - always available
            available[name] = (voice_id, lang)

    return available

# Initialize ESPEAK_VOICES with available voices (cached at module load)
ESPEAK_VOICES = get_available_espeak_voices()

# ============================================================
# DEFAULT TTS VOICES PER LANGUAGE
# ============================================================
# When UI language changes, these voices are selected as defaults.
# User can override in Settings → saved per language in assistant_settings.json
TTS_DEFAULT_VOICES = {
    "edge": {
        "de": "Deutsch (Katja)",
        "en": "Englisch (Jenny)",
    },
    "piper": {
        "de": "Deutsch (Thorsten)",
        "en": "Deutsch (Thorsten)",  # No English Piper model yet
    },
    "espeak": {
        "de": "Deutsch Standard",
        "en": "Englisch mbrola UK (M)",  # User preference: en1
    },
}

# ============================================================
# CONTEXT MANAGEMENT
# ============================================================
# Maximum tokens for RAG context (research results)
# Note: Total Context = RAG_CONTEXT + System-Prompt + History + User-Message
# For 40k model limit → recommended: 20k RAG context (50% reserve)
# For larger models (e.g., with Tesla P40) this value can be increased
MAX_RAG_CONTEXT_TOKENS = 20000

# Maximum words per single source (Wikipedia, news articles, etc.)
# Prevents a single source from dominating the entire context
MAX_WORDS_PER_SOURCE = 2000

# Maximum words for single-source research (Direct URL)
# For only 1 source (e.g., PDF analysis, scientific paper) we need the full document
# Typical scientific paper: 4000-8000 words
# Longer reviews/guidelines: up to 15000 words
MAX_WORDS_SINGLE_SOURCE = 12000

# Token-to-character ratio for context calculation
# German/English mix: ~3 characters per token
CHARS_PER_TOKEN = 3

# ============================================================
# CONTEXT ESTIMATION CONSTANTS
# ============================================================
# Token estimates for system prompt, history and user input
# Used for VRAM-based context calculation

# System prompt token estimate (RAG mode)
SYSTEM_PROMPT_ESTIMATE_RAG = 2000  # RAG system prompt is ~2K tokens

# System prompt token estimate (Cache-Hit mode - slightly larger)
SYSTEM_PROMPT_ESTIMATE_CACHE = 2500  # Cache-Hit prompt with extra context

# Token estimate per history turn (question + answer)
TOKENS_PER_HISTORY_TURN = 500  # Rough estimate: 500 tok/turn

# ============================================================
# DYNAMIC OUTPUT GENERATION CONSTANTS
# ============================================================
# For dynamic num_predict calculation (available output tokens)

# Safety margin: buffer for tokenizer inaccuracies
# Subtracted from num_ctx before output space is calculated
DYNAMIC_NUM_PREDICT_SAFETY_MARGIN = 2048  # tokens

# Minimum output tokens (prevents too small answers)
DYNAMIC_NUM_PREDICT_MINIMUM = 512  # tokens

# Maximum output tokens (prevents KV cache overflow with large contexts)
# ~10-20 pages of text - realistic maximum for a response
DYNAMIC_NUM_PREDICT_HARD_LIMIT = 4096  # tokens

# ============================================================
# AUTOMATIK-LLM CONTEXT CONSTANTS
# ============================================================
# Context window for Automatik-LLM tasks (Decision, Query-Opt, Intent, RAG-Check)
# CRITICAL: Models like Qwen3:4B have 262K default context!
# Without explicit num_ctx, Ollama allocates HUGE KV-Cache across all GPUs.
# 4K is sufficient for all Automatik tasks and keeps VRAM usage minimal.
AUTOMATIK_LLM_NUM_CTX = 4096  # 4K context for all Automatik tasks

# Maximum manual num_ctx value (for UI input validation)
# 2M tokens should cover even the largest context windows (Gemini 2M, future models)
NUM_CTX_MANUAL_MAX = 2097152  # 2M tokens

# Minimum context for Ollama calibration binary search
# This is the lower bound - models with context < this are unusable for conversation
# 8K ensures models can handle multi-turn conversations and summaries
# If GPU-only calibration yields < 8K, Hybrid calibration is triggered
CALIBRATION_MIN_CONTEXT = 8192  # 8K minimum for usable context

# ============================================================
# VISION/OCR CONTEXT CONSTANTS
# ============================================================
# Minimum context for Vision-LLM (OCR, image analysis)
# Below this value, vision processing does not work reliably
VISION_MINIMUM_CONTEXT = 4096  # 4K minimum for Vision-LLM

# ============================================================
# WEB SCRAPING CONSTANTS
# ============================================================
# Playwright fallback threshold for web scraping
# When trafilatura extracts fewer words than this,
# Playwright (headless browser) is tried as fallback
PLAYWRIGHT_FALLBACK_THRESHOLD = 800  # words - below this value Playwright is tried

# ============================================================
# HISTORY SUMMARIZATION CONFIGURATION
# ============================================================
# Trigger: At what percentage of context limit should compression occur?
HISTORY_COMPRESSION_TRIGGER = 0.7  # 70% - when to compress

# Target: Compress down to this percentage (aggressive, leaves room for ~2 roundtrips)
HISTORY_COMPRESSION_TARGET = 0.3  # 30% - where to compress to

# Summary size: Percentage of content being compressed (4:1 compression ratio)
HISTORY_SUMMARY_RATIO = 0.25  # 25% of compressed content = 4:1 ratio

# Minimum summary size in tokens (for very small compressions)
HISTORY_SUMMARY_MIN_TOKENS = 500

# Tolerance: How much larger than target is acceptable before truncation
HISTORY_SUMMARY_TOLERANCE = 0.5  # 50% over target allowed, above that: truncate

# Maximum number of summaries stored (FIFO when exceeded)
HISTORY_MAX_SUMMARIES = 10

# Maximum percentage of context that can be used by summaries
# Used for dynamic max_summaries calculation based on context size
HISTORY_SUMMARY_MAX_RATIO = 0.2  # 20% of context for summaries

# Temperature for summary generation (lower = more factual)
HISTORY_SUMMARY_TEMPERATURE = 0.3

# ============================================================
# INTENT-BASED TEMPERATURE (Auto-Temperature Mode)
# ============================================================
# Temperature values for automatic intent-based temperature selection.
# Used when temperature_mode="auto" in settings.

# Factual queries: precise, deterministic answers (research, facts, code)
INTENT_TEMPERATURE_FAKTISCH = 0.2

# Mixed queries: general conversation, explanations
INTENT_TEMPERATURE_GEMISCHT = 0.5

# Creative queries: stories, poems, brainstorming (higher = more creative)
INTENT_TEMPERATURE_KREATIV = 1.0

# Temperature offsets for multi-agent mode (auto temperature)
# Sokrates and Salomo get slightly higher temperatures for more varied responses
SOKRATES_TEMPERATURE_OFFSET = 0.2  # Sokrates = AIfred + 0.2
SALOMO_TEMPERATURE_OFFSET = 0.3   # Salomo = AIfred + 0.3 (wisest, most creative)

# ============================================================
# DEBUG LOG PERSISTENCE
# ============================================================
# Maximum number of debug log entries to persist in session
# Allows debug log to survive browser refresh during long inferences
DEBUG_LOG_MAX_ENTRIES = 250

# Log RAW messages sent to LLMs (debug.log only)
# Useful for debugging prompt injection issues
# Shows full message list with role and content preview for each LLM call
DEBUG_LOG_RAW_MESSAGES = True

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
# OLLAMA HYBRID MODE (CPU OFFLOAD) CONFIGURATION
# ============================================================
# When a model is larger than available VRAM, Ollama automatically offloads
# some layers to CPU/RAM. This "hybrid mode" requires careful RAM management
# to avoid swapping.

# Minimum context to start with in hybrid mode (fallback)
HYBRID_MIN_CONTEXT = 2048  # 2K tokens (conservative fallback)

# Minimum RAM reserve to prevent swapping
RAM_RESERVE_MIN = 2048  # 2 GB minimum reserve

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

# KoboldCPP Hard Limit (llama.cpp limitation)
# KoboldCPP enforces: --contextsize must be within [256, 262144]
# This is independent of model architecture or VRAM - it's a hard coded limit in llama.cpp
KOBOLDCPP_HARD_MAX_CONTEXT = 262144  # Maximum allowed by KoboldCPP CLI

# ============================================================
# KOBOLDCPP QUANTKV CONFIGURATION
# ============================================================
# KV-Cache Quantization Level (--quantkv parameter)
# Reduces VRAM usage for large context windows
#
# Options:
#   0 = FP16 (no quantization, 100% VRAM, best quality)
#   1 = Q8   (8-bit quantization, ~50% VRAM savings, minimal quality loss)
#   2 = Q4   (4-bit quantization, ~75% VRAM savings, slight quality loss)
#
# NOTE: quantkv=2 has a known deadlock bug on multi-GPU setups with
# flashattention enabled after 2-3 large requests. Use quantkv=1 for stability.
#
# Recommended:
#   - Single GPU: quantkv=2 (max VRAM savings)
#   - Multi-GPU (2x P40): quantkv=1 (stability, confirmed working with 262k context)
KOBOLDCPP_QUANTKV = 1  # Q8 quantization - stable on multi-GPU, ~50% VRAM savings

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
# Distance thresholds for semantic similarity (Cosine Distance)
# 0.0 = identical, 2.0 = completely different

# Normal cache query (without explicit keywords like "research")
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

# Explicit research keywords ("research", "google", etc.)
# Semantic duplicate detection (time-independent)
CACHE_DISTANCE_DUPLICATE = 0.3  # < 0.3 = Very similar (semantic duplicate, always merged)
                                # Examples:
                                # - "research Python" vs "research Python Tutorial" = ~0.15
                                # - "research weather Berlin" vs "research weather Hamburg" = ~0.25
                                # - "research Python" vs "research Java" = ~0.6

# RAG-Mode Distance Threshold
CACHE_DISTANCE_RAG = 1.2  # < 1.2 = Similar enough for RAG context (implemented later)

# Volatile Keywords - Loaded from prompts/cache_volatile_keywords.txt
# These keywords trigger an LLM decision whether to cache anyway
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
# XML TAG FORMATTING CONFIGURATION
# ============================================================
# Collapsible formatting for XML tags in AI responses
# Config dictionary defines icon, label and CSS class per tag
# ALL XML tags are recognized - this list is only for nice icons!
# Unknown tags automatically get "📄 Tagname" as fallback
def get_xml_tag_config(lang: str = "de") -> dict:
    """
    Get XML tag config with i18n labels.

    Args:
        lang: Language code ("de" or "en")

    Returns:
        Config dict with icon, label and CSS class per tag
    """
    # Import here to avoid circular imports
    from .i18n import t

    return {
        "think": {"icon": "💭", "label": t("collapsible_thinking", lang=lang), "class": "thinking-compact"},
        "data": {"icon": "📊", "label": t("collapsible_data", lang=lang), "class": "thinking-compact"},
        "python": {"icon": "🐍", "label": t("collapsible_python", lang=lang), "class": "thinking-compact"},
        "code": {"icon": "💻", "label": t("collapsible_code", lang=lang), "class": "thinking-compact"},
        "sql": {"icon": "🗃️", "label": t("collapsible_sql", lang=lang), "class": "thinking-compact"},
        "json": {"icon": "📋", "label": t("collapsible_json", lang=lang), "class": "thinking-compact"},
    }



# ============================================================
# VISION/OCR CONFIGURATION
# ============================================================
# Maximum image dimension (longest edge) for Vision-LLM processing
# Images larger than this will be resized (preserving aspect ratio)
# Trade-offs:
# - 2048px: Fast inference (8-15s), low VRAM (~512MB), good for most documents
# - 3072px: Medium inference (15-25s), medium VRAM (~1-1.5GB), high detail
# - 4096px: Slow inference (25-40s), high VRAM (~2-3GB), excellent detail
VISION_MAX_IMAGE_DIMENSION = 3840  # 4K UHD - beste OCR-Qualität bei akzeptabler Inferenzzeit

# REMOVED: VISION_CONTEXT_LIMIT (v2.5.3)
# Vision context is now dynamically calculated using the same VRAM-based logic
# as the Main-LLM (via calculate_vram_based_context()). The model's intrinsic
# context limit serves as the upper bound instead of a hardcoded value.
# This allows Vision-LLMs with larger context (e.g., 131K for gemma3) to use
# more context when VRAM allows it.

# ============================================================
# UI LAYOUT CONSTANTS (Single Source of Truth for CSS)
# ============================================================
# These constants are injected as CSS custom properties (:root variables)
# and used in both Python (Reflex components) and CSS (media queries)

# Chat History Box
UI_CHAT_HISTORY_MAX_HEIGHT_DESKTOP = "2400px"  # Desktop: Large fixed height
UI_CHAT_HISTORY_MAX_HEIGHT_MOBILE = "70vh"     # Mobile: 70% viewport, leaves 30% "grip space"

# Thinking Process Collapsible (<details> tag)
UI_THINKING_MAX_HEIGHT_DESKTOP = "450px"       # Desktop: ~15-20 lines of text
UI_THINKING_MAX_HEIGHT_MOBILE = "40vh"         # Mobile: 40% viewport height

# Debug Console
UI_DEBUG_CONSOLE_MAX_HEIGHT = "1200px"         # Maximum height (prevents endless growth)

# Media Query Breakpoint
UI_MOBILE_BREAKPOINT = "768px"                 # Mobile: <= 768px, Desktop: > 768px

# ============================================================
# CONFIG VALIDATION (Safety Checks)
# ============================================================
# No validation needed - token-based compression handles all edge cases
