"""
Reflex State Management for AIfred Intelligence

Main state for chat, settings, and backend management
"""

import reflex as rx
from typing import List, Tuple, Any
import uuid
import os
import asyncio
from pydantic import BaseModel
from .lib import (
    initialize_debug_log,
    log_message,
    console_separator,
    perform_agent_research,
    set_language
)
from .lib.formatting import format_debug_message
from .lib import config
from .lib.vllm_manager import vLLMProcessManager

# ============================================================
# Module-Level Vector Cache (ChromaDB Server Mode)
# ============================================================
# NEW: Using ChromaDB server mode via Docker - thread-safe by design
from .lib.vector_cache import get_cache

async def cleanup_expired_cache_task():
    """
    Background task: Runs every CACHE_CLEANUP_INTERVAL_HOURS to delete expired cache entries.
    Uses AsyncIO (not threading) for Reflex compatibility.
    """
    from .lib.vector_cache import get_cache
    from .lib.config import CACHE_CLEANUP_INTERVAL_HOURS
    import asyncio
    from datetime import datetime

    log_message(f"🗑️ Cache cleanup task started (interval: {CACHE_CLEANUP_INTERVAL_HOURS}h)")

    while True:
        try:
            # Wait for interval
            await asyncio.sleep(CACHE_CLEANUP_INTERVAL_HOURS * 3600)

            # Run cleanup
            cache = get_cache()
            deleted_count = await cache.delete_expired_entries()

            if deleted_count > 0:
                log_message(f"🗑️ Cache cleanup: {deleted_count} expired entries deleted at {datetime.now().strftime('%H:%M:%S')}")

        except Exception as e:
            log_message(f"⚠️ Cache cleanup task error: {e}")
            # Continue running despite errors


def initialize_vector_cache():
    """
    Initialize Vector Cache (Server Mode)

    Connects to ChromaDB Docker container via HTTP.
    Thread-safe by design - no worker threads needed.

    Also starts:
    - Startup cleanup (if enabled)
    - Background cleanup task
    """
    import asyncio
    from .lib.config import CACHE_STARTUP_CLEANUP, CACHE_CLEANUP_INTERVAL_HOURS

    try:
        log_message(f"🚀 Vector Cache: Connecting to ChromaDB server (PID: {os.getpid()})")
        cache = get_cache()
        log_message("✅ Vector Cache: Connected successfully")

        # Startup cleanup if enabled
        if CACHE_STARTUP_CLEANUP:
            async def startup_cleanup():
                deleted_count = await cache.delete_expired_entries()
                if deleted_count > 0:
                    log_message(f"🗑️ Startup cleanup: {deleted_count} expired entries deleted")

            asyncio.create_task(startup_cleanup())

        # Start background cleanup task
        asyncio.create_task(cleanup_expired_cache_task())
        log_message(f"🗑️ Background cleanup task started (every {CACHE_CLEANUP_INTERVAL_HOURS}h)")

        return cache
    except Exception as e:
        log_message(f"⚠️ Vector Cache connection failed: {e}")
        log_message("💡 Make sure ChromaDB is running: docker-compose up -d chromadb")
        return None


def is_backend_compatible(model_dir, backend: str) -> bool:
    """
    Check if model is compatible with backend by reading config.json

    vLLM supports:
    - AWQ (quantization_config.quant_method = "awq")
    - GPTQ (quantization_config.quant_method = "gptq")
    - compressed-tensors (quantization_config.quant_method = "compressed-tensors")
    - FP16/BF16 (no quantization_config)

    TabbyAPI supports:
    - EXL2 (quantization_config.quant_method = "exl2")
    - EXL3 (quantization_config.quant_method = "exl3" or model name contains "exl3")

    Both do NOT support:
    - GGUF (Ollama-only)
    - Non-LLM models (Whisper, Vision, etc.)
    """
    import json

    model_name = model_dir.name.replace("models--", "").replace("--", "/", 1)

    # Exclude non-LLM models by name pattern
    exclude_patterns = ['whisper', 'faster-whisper', 'table-transformer', 'resnet', 'gguf']
    if any(pattern in model_name.lower() for pattern in exclude_patterns):
        return False

    # Try to find config.json in model directory
    config_paths = list(model_dir.glob("**/config.json"))

    if not config_paths:
        # No config.json found - skip this model
        return False

    try:
        with open(config_paths[0], 'r') as f:
            config_data = json.load(f)

        # Check if it's a valid LLM config (has model_type)
        if "model_type" not in config_data:
            return False

        # Check quantization format
        if "quantization_config" in config_data:
            quant_method = config_data["quantization_config"].get("quant_method", "")

            if backend == "vllm":
                # vLLM supports: awq, gptq, compressed-tensors
                return quant_method in ["awq", "gptq", "compressed-tensors"]
            elif backend == "tabbyapi":
                # TabbyAPI supports: exl2, exl3
                # Also check model name for "exl2" or "exl3" (some repos don't have quant_method in config)
                return quant_method in ["exl2", "exl3"] or any(fmt in model_name.lower() for fmt in ["exl2", "exl3"])
        else:
            # No quantization config
            if backend == "vllm":
                # FP16/BF16 (supported by vLLM)
                return True
            elif backend == "tabbyapi":
                # TabbyAPI needs quantization - check model name for EXL format
                return any(fmt in model_name.lower() for fmt in ["exl2", "exl3"])

    except Exception:
        # Failed to read config.json
        return False


def backend_supports_dynamic_models(backend) -> bool:
    """
    Check if backend supports dynamic model loading using capabilities API.

    Returns:
        True if backend can load different models on-demand (like Ollama, TabbyAPI)
        False if backend requires server restart for model changes (like vLLM, KoboldCPP)

    Usage:
        backend = BackendFactory.create("vllm")
        if backend_supports_dynamic_models(backend):
            # Can switch models without restart
        else:
            # Needs restart - disable Automatik-LLM if different from Main
    """
    try:
        caps = backend.get_capabilities()
        return caps.get("dynamic_models", True)  # Default True for backwards compat
    except Exception:
        # Fallback to True (assume dynamic if capabilities not available)
        return True


# ============================================================
# Module-Level Backend State (Global across all sessions)
# ============================================================
# Prevents re-initialization on page reload
# Backend is initialized once at server startup
_global_backend_initialized = False
_global_backend_state: dict[str, Any] = {
    "backend_type": None,
    "backend_url": None,
    "selected_model": None,
    "automatik_model": None,
    "available_models": [],
    "gpu_info": None,
    "vllm_manager": None,  # Global vLLM process manager (persists across reloads)
}


class ChatMessage(BaseModel):
    """Single chat message"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: str = ""


class AIState(rx.State):
    """Main application state"""

    # Chat History
    chat_history: List[Tuple[str, str]] = []  # [(user_msg, ai_msg), ...]
    current_user_input: str = ""
    current_user_message: str = ""  # Die Nachricht die gerade verarbeitet wird
    current_ai_response: str = ""
    is_generating: bool = False
    is_compressing: bool = False  # NEU: Zeigt ob History-Kompression läuft

    # Backend Settings
    backend_type: str = "ollama"  # "ollama", "vllm", "tabbyapi"
    backend_url: str = "http://localhost:11434"  # Default Ollama URL
    # NOTE: Models loaded from settings.json first, fallback to config.py only if settings don't exist
    selected_model: str = ""  # Initialized in on_load() from settings.json or config.py
    available_models: List[str] = []

    # Automatik-LLM (für Decision und Query-Optimierung)
    # NOTE: Loaded from settings.json first, fallback to config.py only if settings don't exist
    automatik_model: str = ""  # Initialized in on_load() from settings.json or config.py

    # LLM Options
    temperature: float = 0.7
    temperature_mode: str = "auto"  # "auto" (Intent-Detection) | "manual" (user slider)
    num_ctx: int = 32768

    # Context Window Control (NICHT in settings.json gespeichert - Reset bei jedem Start)
    num_ctx_mode: str = "auto_vram"  # "auto_vram" | "auto_max" | "manual"
    num_ctx_manual: int = 16384  # Manueller Wert (nur wenn mode="manual")

    # Cached Model Metadata (to avoid repeated API calls)
    _automatik_model_context_limit: int = 0  # Cached context limit for automatik model

    # Research Settings
    research_mode: str = "automatik"  # "quick", "deep", "automatik", "none"
    research_mode_display: str = "🤖 Automatik (KI entscheidet)"  # UI display value

    # Qwen3 Thinking Mode (Chain-of-Thought Reasoning)
    enable_thinking: bool = True  # True = Thinking Mode (temp=0.6), False = Non-Thinking (temp=0.7)
    thinking_mode_warning: str = ""  # Empty = no warning, otherwise show model name that doesn't support thinking

    # vLLM YaRN Settings (RoPE Scaling for Context Extension)
    enable_yarn: bool = False  # Enable YaRN context extension
    yarn_factor: float = 1.0  # Currently active YaRN factor (applied to vLLM)
    yarn_factor_input: str = "1.0"  # Temporary input field value (user typing, not applied yet)
    yarn_max_factor: float = 0.0  # Maximum YaRN factor (0 = unknown, >0 = tested/known)
    yarn_max_tested: bool = False  # True if max was determined by actual VRAM test

    # vLLM Context Info (Runtime Only - NEVER saved to settings.json!)
    # Calculated dynamically on every vLLM startup based on available VRAM & model size
    vllm_max_tokens: int = 0  # Hardware-limited context (VRAM-based calculation)
    vllm_native_context: int = 0  # Native model context (from config.json)

    # VRAM-based Context Limit (Runtime Only - ALL backends)
    # Das berechnete VRAM-Limit vom letzten calculate_dynamic_num_ctx() Aufruf
    # Wird für History-Kompression genutzt (verhindert erneute Berechnung)
    last_vram_limit: int = 0  # min(VRAM-Limit, Model-Limit) - praktisches Maximum

    # TTS Settings
    enable_tts: bool = False

    # Session Management
    session_id: str = ""

    # Backend Status
    backend_healthy: bool = False
    backend_info: str = ""
    backend_switching: bool = False  # True während Backend-Wechsel (UI wird disabled)
    backend_initializing: bool = True  # True während erster Initialisierung (zeigt Loading Spinner)
    vllm_restarting: bool = False  # True während vLLM-Neustart (Modellwechsel/YaRN)
    koboldcpp_auto_restarting: bool = False  # True während KoboldCPP Auto-Restart nach Inaktivität

    # GPU Inactivity Monitoring
    gpu_monitoring_active: bool = False
    gpu_consecutive_idle_checks: int = 0
    gpu_total_checks: int = 0
    gpu_total_idle_checks: int = 0
    gpu_total_active_checks: int = 0
    gpu_last_check_time: str = ""
    gpu_current_utilization: List[int] = []

    # Debug Console
    debug_messages: List[str] = []
    auto_refresh_enabled: bool = True  # Für Debug Console + Chat History + AI Response Area

    # UI Language Settings
    ui_language: str = "de"  # "de" or "en" - für UI Sprache

    # Processing Progress (Automatik, Scraping, LLM)
    progress_active: bool = False
    progress_phase: str = ""  # "automatik", "scraping", "llm"
    progress_current: int = 0
    progress_total: int = 0
    progress_failed: int = 0  # Anzahl fehlgeschlagener URLs

    # Initialization flags
    _backend_initialized: bool = False
    _model_preloaded: bool = False

    # NOTE: vLLM Process Manager is stored in _global_backend_state["vllm_manager"]
    # NOT as a state variable to avoid serialization errors

    # GPU Detection (for backend compatibility warnings)
    gpu_detected: bool = False
    gpu_name: str = ""
    gpu_compute_cap: float = 0.0
    gpu_warnings: List[str] = []
    available_backends: List[str] = ["ollama", "koboldcpp", "tabbyapi", "vllm"]  # Filtered by GPU compatibility (P40-compatible first)

    @rx.var
    def grouped_backends_display(self) -> List[str]:
        """
        Return backend list with headers and separators for dropdown display.

        Structure:
        - Header: "🔧 Universelle Kompatibilität (GGUF)"
        - ollama
        - koboldcpp
        - Separator: "─────────────"
        - Header: "🚀 Moderne GPUs (FP16)"
        - tabbyapi
        - vllm
        """
        grouped = []

        # P40-compatible backends
        grouped.append("header_universal")  # Will be styled as header
        if "ollama" in self.available_backends:
            grouped.append("ollama")
        if "koboldcpp" in self.available_backends:
            grouped.append("koboldcpp")

        # Separator
        grouped.append("separator")

        # Modern GPU backends
        grouped.append("header_modern")
        if "tabbyapi" in self.available_backends:
            grouped.append("tabbyapi")
        if "vllm" in self.available_backends:
            grouped.append("vllm")

        return grouped

    def get_backend_display_label(self, backend_id: str) -> str:
        """
        Get display label for backend dropdown items.

        Maps special IDs (headers, separator) to display text.
        """
        labels = {
            "header_universal": "─── Universelle Kompatibilität (GGUF) ───",
            "separator": "─────────────────────────────────",
            "header_modern": "─── Moderne GPUs (FP16) ───",
            "ollama": "Ollama",
            "koboldcpp": "KoboldCPP",
            "tabbyapi": "TabbyAPI",
            "vllm": "vLLM",
        }
        return labels.get(backend_id, backend_id)

    def is_backend_item_selectable(self, backend_id: str) -> bool:
        """Check if backend item is selectable (not header/separator)"""
        return backend_id not in ["header_universal", "separator", "header_modern"]

    @rx.var
    def is_koboldcpp_auto_restarting(self) -> bool:
        """
        Check if KoboldCPP is currently auto-restarting after inactivity shutdown.

        This flag is set in backends/koboldcpp.py during _ensure_server_running()
        and displays a spinner in the chat UI.
        """
        return _global_backend_state.get("koboldcpp_auto_restarting", False)

    @rx.var
    def backend_supports_dynamic_models(self) -> bool:
        """
        Check if current backend supports dynamic model switching.
        Used to disable Automatik-LLM dropdown for vLLM/KoboldCPP.
        """
        # Default to True if no backend initialized yet
        if self.backend_type not in ["vllm", "koboldcpp", "tabbyapi"]:
            return True

        # vLLM and KoboldCPP can't switch models
        return self.backend_type not in ["vllm", "koboldcpp"]

    async def on_load(self):
        """
        Called when page loads - initialize backend and load models

        NEW: Backend is initialized once globally at server startup.
        Page reloads simply restore state from global variables.
        """
        global _global_backend_initialized, _global_backend_state

        print(f"🔥 on_load() CALLED - Global init: {_global_backend_initialized}, Session init: {self._backend_initialized}")

        # FIRST-TIME GLOBAL INITIALIZATION (once per server start)
        if not _global_backend_initialized:
            print("=" * 60)
            print("🚀 FIRST-TIME SERVER INITIALIZATION...")
            print("=" * 60)

            # Initialize debug log (only once)
            initialize_debug_log(force_reset=False)

            # Initialize language settings
            from .lib.config import DEFAULT_LANGUAGE
            set_language(DEFAULT_LANGUAGE)
            log_message(f"🌍 Language mode: {DEFAULT_LANGUAGE}")

            # Initialize Vector Cache
            initialize_vector_cache()
            log_message("💾 Vector Cache: Connected")

            # GPU Detection (once per server)
            log_message("🔍 Detecting GPU capabilities...")
            try:
                from .lib.gpu_detection import detect_gpu
                gpu_info = detect_gpu()
                if gpu_info:
                    _global_backend_state["gpu_info"] = gpu_info
                    log_message(f"✅ GPU: {gpu_info.name} (Compute {gpu_info.compute_capability})")
                    if gpu_info.unsupported_backends:
                        log_message(f"⚠️ Incompatible backends: {', '.join(gpu_info.unsupported_backends)}")
                    if gpu_info.warnings:
                        for warning in gpu_info.warnings[:2]:
                            log_message(f"⚠️ {warning}")
                else:
                    log_message("ℹ️ No GPU detected or nvidia-smi not available")
            except Exception as e:
                log_message(f"⚠️ GPU detection failed: {e}")

            _global_backend_initialized = True
            print("✅ Global initialization complete")

        # PER-SESSION INITIALIZATION (every user/tab/reload)
        if not self._backend_initialized:
            print("📱 Initializing session...")

            # Load saved settings
            from .lib.settings import load_settings
            saved_settings = load_settings()

            if saved_settings:
                # Use saved settings
                self.backend_type = saved_settings.get("backend_type", self.backend_type)
                self.research_mode = saved_settings.get("research_mode", self.research_mode)

                # Update research_mode_display to match loaded research_mode
                from .lib import TranslationManager
                self.research_mode_display = TranslationManager.get_research_mode_display(self.research_mode, self.ui_language)

                self.temperature = saved_settings.get("temperature", self.temperature)
                self.temperature_mode = saved_settings.get("temperature_mode", self.temperature_mode)
                self.enable_thinking = saved_settings.get("enable_thinking", self.enable_thinking)

                # Load vLLM YaRN Settings (only enable/disable, factor always starts at 1.0)
                self.enable_yarn = saved_settings.get("enable_yarn", self.enable_yarn)
                # yarn_factor is NOT loaded - always starts at 1.0, system calibrates maximum
                self.yarn_factor = 1.0
                self.yarn_factor_input = "1.0"
                # NOTE: vllm_max_tokens and vllm_native_context are NEVER loaded from settings!
                # They are calculated dynamically on every vLLM startup based on VRAM availability

                # Load per-backend models (if available)
                backend_models = saved_settings.get("backend_models", {})
                if self.backend_type in backend_models:
                    self.selected_model = backend_models[self.backend_type].get("selected_model", self.selected_model)
                    self.automatik_model = backend_models[self.backend_type].get("automatik_model", self.automatik_model)
                else:
                    # Fallback: Use old-style global model settings
                    self.selected_model = saved_settings.get("selected_model", self.selected_model)
                    self.automatik_model = saved_settings.get("automatik_model", self.automatik_model)

                self.add_debug(f"⚙️ Settings loaded (backend: {self.backend_type})")

            # Apply config.py defaults as final fallback (only if settings.json didn't provide values)
            backend_defaults = config.BACKEND_DEFAULT_MODELS.get(self.backend_type, {})

            if not self.selected_model:
                self.selected_model = backend_defaults.get("selected_model", "")
                if self.selected_model:
                    self.add_debug(f"⚙️ Using default selected_model from config.py: {self.selected_model}")
                else:
                    self.add_debug("⚠️ No selected_model configured")

            if not self.automatik_model:
                self.automatik_model = backend_defaults.get("automatik_model", "")
                if self.automatik_model:
                    self.add_debug(f"⚙️ Using default automatik_model from config.py: {self.automatik_model}")
                else:
                    self.add_debug("⚠️ No automatik_model configured")

            # vLLM and TabbyAPI can only load ONE model at a time
            # Ensure automatik_model = selected_model for these backends
            if self.backend_type in ["vllm", "tabbyapi"]:
                if self.automatik_model != self.selected_model:
                    self.add_debug(f"⚠️ {self.backend_type} can only load one model - using {self.selected_model} for both Main and Automatik")
                    self.automatik_model = self.selected_model

            # Generate session ID
            if not self.session_id:
                self.session_id = str(uuid.uuid4())
                self.add_debug(f"🆔 Session: {self.session_id[:8]}...")

            # Restore GPU info from global state
            gpu_info = _global_backend_state.get("gpu_info")
            if gpu_info:
                self.gpu_detected = True
                self.gpu_name = gpu_info.name
                self.gpu_compute_cap = gpu_info.compute_capability
                self.gpu_warnings = gpu_info.warnings

                # Filter available backends based on GPU compatibility
                # Only show backends that are actually compatible with the GPU
                if gpu_info.recommended_backends:
                    self.available_backends = gpu_info.recommended_backends
                    self.add_debug(f"✅ Compatible backends: {', '.join(self.available_backends)}")

                    # If current backend is not compatible, switch to first available
                    if self.backend_type not in self.available_backends:
                        old_backend = self.backend_type
                        self.backend_type = self.available_backends[0]
                        self.add_debug(f"⚠️ Backend '{old_backend}' not compatible with {gpu_info.name}")
                        self.add_debug(f"🔄 Auto-switched to '{self.backend_type}'")

            # Initialize backend (or restore from global state)
            self.add_debug("🔧 Initializing backend...")
            backend_init_success = False
            try:
                await self.initialize_backend()
                backend_init_success = True
            except Exception as e:
                self.add_debug(f"❌ Backend init failed: {e}")
                log_message(f"❌ Backend init failed: {e}")
                import traceback
                log_message(traceback.format_exc())

            # Only show "Backend ready" if initialization succeeded
            if backend_init_success:
                self.add_debug("✅ Backend ready")

                # Add separator after backend ready
                from aifred.lib.logging_utils import console_separator
                console_separator()  # File log
                self.debug_messages.append("────────────────────")  # UI

            self._backend_initialized = True
            print("✅ Session initialization complete")

    async def initialize_backend(self):
        """
        Initialize LLM backend

        NEW: Uses global state to prevent re-initialization on page reload.
        - First call: Load models, start vLLM if needed, store in global state
        - Subsequent calls: Restore from global state (fast!)
        """
        global _global_backend_state

        # Check if this backend was already initialized globally
        is_same_backend = (_global_backend_state["backend_type"] == self.backend_type)

        if is_same_backend and _global_backend_state["available_models"]:
            # FAST PATH: Restore from global state (page reload case)
            print(f"⚡ Backend '{self.backend_type}' already initialized, restoring from global state...")

            self.backend_url = _global_backend_state["backend_url"]
            self.available_models = _global_backend_state["available_models"]
            self.selected_model = _global_backend_state["selected_model"]
            self.automatik_model = _global_backend_state["automatik_model"]

            # vLLM can only load ONE model - ensure Automatik-LLM matches Main-LLM
            if self.backend_type == "vllm" and self.automatik_model != self.selected_model:
                self.automatik_model = self.selected_model
                _global_backend_state["automatik_model"] = self.selected_model  # Update global state
                self._save_settings()  # Persist the correction

            # Check vLLM manager status if exists
            if self.backend_type == "vllm":
                vllm_manager = _global_backend_state.get("vllm_manager")
                if vllm_manager and vllm_manager.is_running():
                    self.add_debug("✅ vLLM server already running (restored from global state)")
                else:
                    self.add_debug("⚠️ vLLM manager exists but server not running")

            # Check KoboldCPP manager status if exists
            if self.backend_type == "koboldcpp":
                koboldcpp_manager = _global_backend_state.get("koboldcpp_manager")
                if koboldcpp_manager and koboldcpp_manager.is_running():
                    self.add_debug("✅ KoboldCPP server already running (restored from global state)")
                else:
                    self.add_debug("⚠️ KoboldCPP manager exists but server not running")

            self.backend_healthy = True
            self.backend_info = f"{self.backend_type} - {len(self.available_models)} models"
            self.add_debug(f"✅ Backend ready (restored: {len(self.available_models)} models)")

            # Hide loading spinner (fast path = already initialized)
            self.backend_initializing = False

            return  # Done! No expensive initialization needed

        # SLOW PATH: Full initialization (first time or backend switch)
        print(f"🔧 Full backend initialization for '{self.backend_type}'...")

        try:
            # Update URL based on backend type
            if self.backend_type == "ollama":
                self.backend_url = "http://localhost:11434"
            elif self.backend_type == "vllm":
                # Use port 8001 for development (8000 will be used on production MiniPC)
                self.backend_url = "http://localhost:8001/v1"
            elif self.backend_type == "tabbyapi":
                self.backend_url = "http://localhost:5000/v1"
            elif self.backend_type == "koboldcpp":
                self.backend_url = "http://localhost:5001/v1"

            # add_debug() already logs to file, so we only need one call
            self.add_debug(f"🔧 Creating backend: {self.backend_type}")
            # Detailed info only in log file (not in UI)
            log_message(f"   URL: {self.backend_url}")

            # SKIP health check - causes async deadlock in on_load context!
            # Assume backend is healthy and proceed
            self.backend_healthy = True
            self.backend_info = f"{self.backend_type} initializing..."
            self.add_debug(f"⚡ Backend: {self.backend_type} (skip health check)")

            # Load models SYNCHRONOUSLY via curl (no async deadlock!)
            import subprocess
            import json
            try:
                # For vLLM/TabbyAPI: Get models from HuggingFace cache (local files)
                # For Ollama: Get models from server API
                if self.backend_type in ["vllm", "tabbyapi"]:
                    # Scan HuggingFace cache for downloaded models
                    from pathlib import Path
                    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"

                    if hf_cache.exists():
                        # Find all model directories (format: models--Org--ModelName)
                        model_dirs = [d for d in hf_cache.iterdir() if d.is_dir() and d.name.startswith("models--")]

                        # Filter models by reading config.json
                        self.available_models = []
                        for model_dir in model_dirs:
                            if is_backend_compatible(model_dir, self.backend_type):
                                model_id = model_dir.name.replace("models--", "").replace("--", "/", 1)
                                self.available_models.append(model_id)

                        self.add_debug(f"📂 Found {len(self.available_models)} {self.backend_type}-compatible models ({len(model_dirs)} total in cache)")
                    else:
                        self.available_models = []
                        self.add_debug("⚠️ HuggingFace cache not found")

                elif self.backend_type == "koboldcpp":
                    # KoboldCPP: Discover GGUF models from filesystem
                    from aifred.lib.gguf_utils import find_all_gguf_models

                    self.add_debug("🔍 Searching for GGUF models on filesystem...")

                    try:
                        gguf_models = find_all_gguf_models()

                        if gguf_models:
                            # Store model names in available_models
                            self.available_models = [m.name for m in gguf_models]

                            # Store full model info in global state for later use
                            _global_backend_state["gguf_models"] = {m.name: m for m in gguf_models}

                            # Select first model by default
                            if not self.selected_model or self.selected_model not in self.available_models:
                                self.selected_model = gguf_models[0].name

                            # KoboldCPP can only load ONE model - Automatik uses same model
                            self.automatik_model = self.selected_model
                        else:
                            self.available_models = []
                            self.add_debug("⚠️ No GGUF models found")
                            self.add_debug("💡 Download GGUF models:")
                            self.add_debug("   huggingface-cli download bartowski/Qwen3-30B-Instruct-2507-GGUF \\")
                            self.add_debug("       Qwen3-30B-Instruct-2507-Q4_K_M.gguf --local-dir ~/models/")

                    except Exception as e:
                        self.available_models = []
                        self.add_debug(f"❌ GGUF discovery failed: {e}")
                        import traceback
                        self.add_debug(f"   {traceback.format_exc()}")

                else:
                    # Ollama: Query server API
                    endpoint = f'{self.backend_url}/api/tags'

                    # Synchronous curl call to get model list
                    result = subprocess.run(
                        ['curl', '-s', endpoint],
                        capture_output=True,
                        text=True,
                        timeout=5.0
                    )

                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        self.available_models = [m["name"] for m in data.get("models", [])]
                    else:
                        self.available_models = []

                # Common validation for all backends
                # Validate that configured models exist, fallback to first available if not
                if self.selected_model not in self.available_models and self.available_models:
                    log_message(f"⚠️ Configured model '{self.selected_model}' not found, using '{self.available_models[0]}'")
                    self.selected_model = self.available_models[0]

                if self.automatik_model not in self.available_models and self.available_models:
                    log_message(f"⚠️ Configured automatik model '{self.automatik_model}' not found, using '{self.available_models[0]}'")
                    self.automatik_model = self.available_models[0]

                self.backend_info = f"{self.backend_type} - {len(self.available_models)} models"
                self.backend_healthy = True

                # For backends without model switching (vLLM, KoboldCPP, TabbyAPI), show only Main model
                if self.backend_type.lower() in ["vllm", "koboldcpp", "tabbyapi"]:
                    self.add_debug(f"✅ {len(self.available_models)} Models vorhanden (Main: {self.selected_model})")
                else:
                    self.add_debug(f"✅ {len(self.available_models)} Models vorhanden (Main: {self.selected_model}, Automatik: {self.automatik_model})")

            except Exception as e:
                self.backend_healthy = False
                self.backend_info = f"{self.backend_type} error"
                self.add_debug(f"❌ Model loading failed: {e}")
                log_message(f"❌ Model loading failed: {e}")

            # Backends that can't switch models: ensure Automatik-LLM matches Main-LLM
            # Check via capabilities instead of hardcoding backend names
            from aifred.backends import BackendFactory
            temp_backend = BackendFactory.create(self.backend_type, base_url=self.backend_url)
            caps = temp_backend.get_capabilities()

            if not caps.get("dynamic_models", True) and self.automatik_model != self.selected_model:
                self.automatik_model = self.selected_model
                self._save_settings()  # Persist the correction

            # Store in global state BEFORE starting servers (so fast path works on reload)
            _global_backend_state["backend_type"] = self.backend_type
            _global_backend_state["backend_url"] = self.backend_url
            _global_backend_state["selected_model"] = self.selected_model
            _global_backend_state["automatik_model"] = self.automatik_model
            _global_backend_state["available_models"] = self.available_models

            # Start vLLM process if backend is vLLM
            if self.backend_type == "vllm":
                await self._start_vllm_server()

            # Start KoboldCPP process if backend is koboldcpp
            if self.backend_type == "koboldcpp":
                await self._start_koboldcpp_server()

            # Preload Automatik-LLM via curl in background (simple & non-blocking!)
            # Note: For vLLM/KoboldCPP, skip preload curl since server was just started with the model
            if self.automatik_model and self.backend_type not in ["vllm", "koboldcpp"]:
                import subprocess
                try:
                    if self.backend_type == "ollama":
                        # Ollama-specific preload
                        preload_cmd = f'curl -s http://localhost:11434/api/chat -d \'{{"model":"{self.automatik_model}","messages":[{{"role":"user","content":"hi"}}],"stream":false,"options":{{"num_predict":1}}}}\' > /dev/null 2>&1 &'
                        subprocess.Popen(preload_cmd, shell=True)
                        log_message(f"🚀 Preloading {self.automatik_model} via curl (background)")
                        self.add_debug(f"🚀 Preloading {self.automatik_model}...")
                    elif self.backend_type == "tabbyapi":
                        # OpenAI-compatible preload (TabbyAPI)
                        preload_cmd = f'curl -s {self.backend_url}/chat/completions -H "Content-Type: application/json" -d \'{{"model":"{self.automatik_model}","messages":[{{"role":"user","content":"hi"}}],"max_tokens":1}}\' > /dev/null 2>&1 &'
                        subprocess.Popen(preload_cmd, shell=True)
                        log_message(f"🚀 Preloading {self.automatik_model} via {self.backend_type} (background)")
                        self.add_debug(f"🚀 Preloading {self.automatik_model}...")
                except Exception as e:
                    log_message(f"⚠️ Preload failed: {e}")
                    # Not critical, continue anyway

            # Store in global state for future page reloads
            # vllm_manager and koboldcpp_manager are already stored in _global_backend_state by their start functions
            print(f"✅ Backend '{self.backend_type}' fully initialized and stored in global state")

            # Mark initialization as complete (hide loading spinner)
            self.backend_initializing = False

        except Exception as e:
            self.backend_healthy = False
            self.backend_info = f"Error: {str(e)}"
            self.add_debug(f"❌ Backend initialization failed: {e}")
            self.backend_initializing = False  # Hide spinner even on error

    def _save_settings(self):
        """Save current settings to file (per-backend models)"""
        from .lib.settings import save_settings, load_settings

        # Load existing settings to preserve other backends
        existing = load_settings() or {}
        backend_models = existing.get("backend_models", {})

        # Update current backend's models
        backend_models[self.backend_type] = {
            "selected_model": self.selected_model,
            "automatik_model": self.automatik_model,
        }

        settings = {
            "backend_type": self.backend_type,
            "research_mode": self.research_mode,
            "temperature": self.temperature,
            "temperature_mode": self.temperature_mode,
            "enable_thinking": self.enable_thinking,
            "backend_models": backend_models,  # Merged: preserves all backends
            # vLLM YaRN Settings (only enable/disable, factor is calculated dynamically)
            "enable_yarn": self.enable_yarn,
            # NOTE: yarn_factor is NOT saved - always starts at 1.0, system calibrates maximum
            # NOTE: vllm_max_tokens and vllm_native_context are NEVER saved!
            # They are calculated dynamically on every vLLM startup based on VRAM
        }
        save_settings(settings)

    async def switch_backend(self, new_backend: str):
        """Switch to different backend and restore last used models"""
        # Ignore header and separator clicks
        if new_backend in ["header_universal", "separator", "header_modern"]:
            return

        # Prevent concurrent backend switches
        if self.backend_switching:
            self.add_debug("⚠️ Backend switch already in progress, please wait...")
            return

        self.backend_switching = True
        yield  # Update UI to disable controls

        try:
            # Clean up old backend resources (unload models, stop servers)
            old_backend = self.backend_type
            self.add_debug(f"🔄 Switching backend from {old_backend} to {new_backend}...")

            # Save current backend's models before switching
            self._save_settings()

            # Now clean up the old backend
            await self._cleanup_old_backend(old_backend)

            # Load saved settings for target backend BEFORE switching
            from .lib.settings import load_settings
            settings = load_settings() or {}
            backend_models = settings.get("backend_models", {})

            # Determine which models to use for new backend
            target_main_model = None
            target_auto_model = None

            if new_backend in backend_models:
                # Use saved models from backend_models.json
                saved_models = backend_models[new_backend]
                target_main_model = saved_models.get("selected_model")
                target_auto_model = saved_models.get("automatik_model")
                self.add_debug(f"📝 Found saved models for {new_backend}: Main={target_main_model}, Auto={target_auto_model}")
            else:
                # Use backend-specific defaults from config.py
                default_models = config.BACKEND_DEFAULT_MODELS.get(new_backend, {})
                target_main_model = default_models.get("selected_model")
                target_auto_model = default_models.get("automatik_model")
                self.add_debug(f"📝 Using default models for {new_backend}: Main={target_main_model}, Auto={target_auto_model}")

            # Set target models BEFORE initialize_backend() so validation doesn't override them
            if target_main_model:
                self.selected_model = target_main_model
            if target_auto_model:
                self.automatik_model = target_auto_model

            # vLLM and TabbyAPI can only load ONE model at a time
            # Set automatik_model = selected_model BEFORE initialize_backend() to prevent wrong model loading
            if new_backend in ["vllm", "tabbyapi"]:
                if self.automatik_model != self.selected_model:
                    self.add_debug(f"⚠️ {new_backend} can only load one model - using {self.selected_model} for both Main and Automatik")
                self.automatik_model = self.selected_model

            # Switch backend and load models
            self.backend_type = new_backend
            await self.initialize_backend()

            # Save settings for new backend
            self._save_settings()

        finally:
            # Re-enable UI controls
            self.backend_switching = False
            self.add_debug("✅ Backend switch complete")

            # Add separator after backend switch
            from aifred.lib.logging_utils import console_separator
            console_separator()  # File log
            self.debug_messages.append("────────────────────")  # UI (20 chars, matching pattern)

            yield  # Force UI update to re-enable controls and refresh model dropdowns

    def set_progress(self, phase: str, current: int = 0, total: int = 0, failed: int = 0):
        """Update processing progress"""
        self.progress_active = True
        self.progress_phase = phase
        self.progress_current = current
        self.progress_total = total
        self.progress_failed = failed

    def clear_progress(self):
        """Clear processing progress"""
        self.progress_active = False
        self.progress_phase = ""
        self.progress_current = 0
        self.progress_total = 0
        self.progress_failed = 0

    def add_debug(self, message: str):
        """Add message to debug console"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"{timestamp} | {message}"

        # Add to Reflex State
        self.debug_messages.append(formatted_msg)

        # Also add to lib console (for agent_core logging)
        log_message(message)

        # Keep only last 500 messages
        if len(self.debug_messages) > 500:
            self.debug_messages = self.debug_messages[-500:]

    def set_user_input(self, text: str):
        """Update user input"""
        self.current_user_input = text

    def refresh_debug_console(self):
        """
        Refresh debug console to propagate background task updates

        Background tasks (like InactivityMonitor) can modify self.debug_messages
        but without yield, changes don't propagate to UI. This event handler
        forces a UI refresh by yielding.

        Called periodically from UI via rx.moment() interval.
        """
        # Just yield to propagate any state changes to UI
        # No need to modify anything - self.debug_messages already has the data
        yield

    async def start_inactivity_monitoring(self):
        """
        Background Task: GPU Inactivity Monitoring (Rolling Window)

        Monitors GPU utilization and auto-shutdowns KoboldCPP after idle period.
        Uses Rolling Window approach: Continuous checks every 60s, shutdown when
        N consecutive checks were idle.

        User Use Case:
            - User finishes inference → has "Bedenkzeit" (thinking time)
            - If new inference starts within timeout → timer resets automatically
            - Only shutdowns if GPUs idle for full timeout duration

        Example (600s timeout):
            - Check every 60s
            - Need 10 consecutive idle checks (10*60s = 600s)
            - Any GPU activity → reset counter to 0
            - Counter reaches 10 → shutdown

        Lifecycle:
            - Started when KoboldCPP starts (self.gpu_monitoring_active = True)
            - Stopped when KoboldCPP stops (self.gpu_monitoring_active = False)
            - Auto-stops after shutdown threshold reached

        Config:
            - KOBOLDCPP_INACTIVITY_TIMEOUT: Seconds of GPU idle before shutdown
            - KOBOLDCPP_INACTIVITY_CHECK_INTERVAL: Seconds between checks (60s recommended)
        """
        from aifred.lib.gpu_utils import get_gpu_utilization, are_all_gpus_idle
        from aifred.lib.config import (
            KOBOLDCPP_INACTIVITY_TIMEOUT,
            KOBOLDCPP_INACTIVITY_CHECK_INTERVAL
        )
        from aifred.lib.logging_utils import console_separator
        import asyncio
        import datetime

        # Get KoboldCPP manager from global state
        koboldcpp_manager = _global_backend_state.get("koboldcpp_manager")
        if not koboldcpp_manager:
            self.add_debug("⚠️ No KoboldCPP manager found, monitor exiting")
            return

        # Calculate how many consecutive idle checks needed
        idle_checks_needed = max(1, KOBOLDCPP_INACTIVITY_TIMEOUT // KOBOLDCPP_INACTIVITY_CHECK_INTERVAL)

        # Log startup
        self.add_debug(
            f"🎯 GPU Inactivity Monitor started "
            f"(Rolling Window: {idle_checks_needed} consecutive checks à {KOBOLDCPP_INACTIVITY_CHECK_INTERVAL}s = {KOBOLDCPP_INACTIVITY_TIMEOUT}s timeout)"
        )

        try:
            # Rolling Window Loop - Continuous checking
            while True:
                # Check if monitoring should stop
                if not self.gpu_monitoring_active:
                    return

                # Sleep before check (allows quick start)
                await asyncio.sleep(KOBOLDCPP_INACTIVITY_CHECK_INTERVAL)

                # Check if still active (might have been stopped during sleep)
                if not self.gpu_monitoring_active:
                    return

                # Check GPUs and update State
                utilization = get_gpu_utilization()
                self.gpu_current_utilization = utilization or []
                self.gpu_total_checks += 1

                # Update timestamp
                self.gpu_last_check_time = datetime.datetime.now().strftime("%H:%M:%S")

                # Check if all GPUs idle
                if are_all_gpus_idle(utilization):
                    self.gpu_consecutive_idle_checks += 1
                    self.gpu_total_idle_checks += 1
                else:
                    # GPU activity detected - reset timer
                    if self.gpu_consecutive_idle_checks > 0:
                        self.debug_messages.append(
                            f"{datetime.datetime.now().strftime('%H:%M:%S')} | "
                            f"🔄 GPU activity detected - idle timer reset "
                            f"(was at {self.gpu_consecutive_idle_checks}/{idle_checks_needed} checks)"
                        )
                        # Also log to file
                        from aifred.lib.logging_utils import log_message
                        log_message(
                            f"🔄 GPU activity detected - idle timer reset "
                            f"(was at {self.gpu_consecutive_idle_checks}/{idle_checks_needed} checks)"
                        )
                    self.gpu_consecutive_idle_checks = 0
                    self.gpu_total_active_checks += 1

                # Check shutdown threshold
                if self.gpu_consecutive_idle_checks >= idle_checks_needed:
                    idle_duration = self.gpu_consecutive_idle_checks * KOBOLDCPP_INACTIVITY_CHECK_INTERVAL

                    # Log shutdown messages (via add_debug for UI propagation)
                    self.debug_messages.append(
                        f"{datetime.datetime.now().strftime('%H:%M:%S')} | "
                        f"🛑 KoboldCPP wird wegen Inaktivität heruntergefahren "
                        f"(GPUs waren {idle_duration}s idle, Timeout: {KOBOLDCPP_INACTIVITY_TIMEOUT}s)"
                    )
                    self.debug_messages.append(
                        f"{datetime.datetime.now().strftime('%H:%M:%S')} | "
                        f"   GPU-Statistik: {self.gpu_total_active_checks} aktiv / "
                        f"{self.gpu_total_idle_checks} idle Checks"
                    )

                    # Log to file
                    from aifred.lib.logging_utils import log_message
                    log_message(
                        f"🛑 KoboldCPP wird wegen Inaktivität heruntergefahren "
                        f"(GPUs waren {idle_duration}s idle, Timeout: {KOBOLDCPP_INACTIVITY_TIMEOUT}s)"
                    )
                    log_message(
                        f"   GPU-Statistik: {self.gpu_total_active_checks} aktiv / "
                        f"{self.gpu_total_idle_checks} idle Checks"
                    )

                    # Graceful shutdown
                    try:
                        await koboldcpp_manager.stop()

                        self.debug_messages.append(
                            f"{datetime.datetime.now().strftime('%H:%M:%S')} | "
                            "✅ KoboldCPP erfolgreich heruntergefahren"
                        )
                        log_message("✅ KoboldCPP erfolgreich heruntergefahren")

                        # Add separator
                        console_separator()  # File log
                        self.debug_messages.append(
                            f"{datetime.datetime.now().strftime('%H:%M:%S')} | "
                            "────────────────────"
                        )

                    except Exception as e:
                        self.debug_messages.append(
                            f"{datetime.datetime.now().strftime('%H:%M:%S')} | "
                            f"❌ Auto-Shutdown fehlgeschlagen: {e}"
                        )
                        log_message(f"❌ Auto-Shutdown fehlgeschlagen: {e}")

                    # Stop monitoring
                    self.gpu_monitoring_active = False
                    return

        except Exception as e:
            self.debug_messages.append(
                f"{datetime.datetime.now().strftime('%H:%M:%S')} | "
                f"❌ GPU monitoring error: {e}"
            )
            self.gpu_monitoring_active = False
            from aifred.lib.logging_utils import log_message
            log_message(f"❌ GPU monitoring error: {e}")

    async def _ensure_backend_initialized(self):
        """
        Ensure backend is initialized (called from send_message)

        This is now a no-op since initialization happens in on_load().
        Kept for backwards compatibility.
        """
        if self._backend_initialized:
            return  # Already initialized by on_load()

        # Fallback: Initialize now if on_load() didn't run
        print("⚠️ Fallback initialization (on_load didn't run)")
        # Re-use on_load() logic
        await self.on_load()

    async def _start_vllm_server(self):
        """Start vLLM server process with selected model"""
        global _global_backend_state

        try:
            # Check if vLLM is already running from global state
            existing_manager = _global_backend_state.get("vllm_manager")
            if existing_manager and existing_manager.is_running():
                self.add_debug("✅ vLLM server already running (using existing process)")
                return

            # IMPORTANT: vLLM cannot switch models like Ollama (requires full restart)
            # Therefore, start directly with the Main-Model (30B) to avoid slow restarts
            # Both Automatik and Main requests will use the same 30B model
            startup_model = self.selected_model
            self.add_debug(f"🚀 Starting vLLM server with {startup_model}...")
            self.add_debug("   (vLLM uses Main-Model for all requests - model switching requires slow restart)")

            # Auto-detect context from model config.json (no hardcoded values!)
            # Build YaRN config if enabled
            yarn_config = None
            if self.enable_yarn and self.yarn_factor > 1.0:
                yarn_config = {
                    "factor": self.yarn_factor,
                    "original_max_position_embeddings": self.vllm_native_context
                }
                self.add_debug(f"🔧 YaRN: {self.yarn_factor}x scaling ({self.vllm_native_context:,} → {int(self.vllm_native_context * self.yarn_factor):,} tokens)")

            # Initialize vLLM Process Manager
            # ALWAYS calculate dynamically based on current VRAM (never use cached values!)
            vllm_manager = vLLMProcessManager(
                port=8001,
                max_model_len=None,  # ALWAYS auto-detect based on current VRAM
                gpu_memory_utilization=0.90,  # 90% safe on modern GPUs
                yarn_config=yarn_config  # YaRN context extension (if enabled)
            )

            # Start server with VRAM-based context calculation
            # Process:
            #   1. Query free VRAM from nvidia-smi
            #   2. Get model size from HF cache
            #   3. Calculate: usable_vram = free_vram - model_size - safety_margin(512MB)
            #   4. Convert to tokens: max_tokens = usable_vram / VRAM_CONTEXT_RATIO(0.097)

            success, context_info = await vllm_manager.start_with_auto_detection(
                model=startup_model,
                timeout=120,
                feedback_callback=self.add_debug
            )

            if success and context_info:
                # Update state with calculated values (runtime only, not persisted!)
                self.vllm_native_context = context_info["native_context"]
                self.vllm_max_tokens = context_info["hardware_limit"]

                # Check if YaRN factor was reduced due to VRAM test (crash + auto-correction)
                native = context_info['native_context']
                hw_limit = context_info['hardware_limit']

                if "reduced_yarn_factor" in context_info:
                    # Maximum was determined by actual VRAM test (crash + parse)
                    reduced_factor = context_info["reduced_yarn_factor"]
                    self.yarn_factor = reduced_factor
                    self.yarn_factor_input = f"{reduced_factor:.2f}"
                    self._save_settings()

                    # Calculate and store the tested maximum
                    if native > 0:
                        self.yarn_max_factor = reduced_factor
                        self.yarn_max_tested = True
                        self.add_debug(f"✅ YaRN factor automatically reduced to {reduced_factor:.2f}x (VRAM limit)")
                        self.add_debug(f"📏 Maximum YaRN factor: ~{self.yarn_max_factor:.1f}x (ermittelt durch Test)")
                else:
                    # Successful start - we don't know the maximum yet
                    self.yarn_max_factor = 0.0  # Unknown
                    self.yarn_max_tested = False

                    # Sync input field with active factor after successful start
                    self.yarn_factor_input = f"{self.yarn_factor:.2f}"

                self.add_debug("📊 Context Info:")
                self.add_debug(f"  • Native: {context_info['native_context']:,} tokens (config.json)")
                self.add_debug(f"  • Hardware Limit: {context_info['hardware_limit']:,} tokens (VRAM)")
                self.add_debug(f"  • Used: {context_info['used_context']:,} tokens")

                # Cache startup context in vLLM backend (for calculate_practical_context)
                from .backends import BackendFactory
                vllm_backend = BackendFactory.create("vllm", base_url=self.backend_url)

                # Build debug messages for backend cache (matching the UI messages above)
                debug_messages = [
                    f"📊 Pre-calculated Context Limit: {context_info['hardware_limit']:,} tokens",
                    f"   Native: {context_info['native_context']:,} tokens (config.json)",
                    f"   Hardware Limit: {context_info['hardware_limit']:,} tokens (VRAM)",
                    f"   Used: {context_info['used_context']:,} tokens"
                ]

                vllm_backend.set_startup_context(
                    context=context_info["hardware_limit"],
                    debug_messages=debug_messages
                )

                # Store in global state so it persists across page reloads
                _global_backend_state["vllm_manager"] = vllm_manager

                self.add_debug("✅ vLLM server ready on port 8001")
            else:
                raise RuntimeError("vLLM failed to start with auto-detection")

        except Exception as e:
            self.add_debug(f"❌ Failed to start vLLM: {e}")
            _global_backend_state["vllm_manager"] = None

    async def _stop_vllm_server(self):
        """Stop vLLM server process gracefully"""
        global _global_backend_state

        vllm_manager = _global_backend_state.get("vllm_manager")
        if vllm_manager and vllm_manager.is_running():
            self.add_debug("🛑 Stopping vLLM server...")
            await vllm_manager.stop()
            _global_backend_state["vllm_manager"] = None  # Clear from global state
            self.add_debug("✅ vLLM server stopped")

    async def _restart_vllm_with_new_config(self):
        """
        Force restart vLLM server with new configuration (model or YaRN changes)

        This explicitly stops the server, clears global state, and starts fresh.
        Used by set_selected_model() and apply_yarn_factor() to ensure actual restart.

        Note: This is called from async event handlers (apply_yarn_factor, set_selected_model)
        but cannot yield since it's a helper function. The caller should yield after calling.
        """
        global _global_backend_state

        try:
            # Step 1: Stop existing vLLM server
            await self._stop_vllm_server()

            # Step 2: Clear global state to force re-initialization
            _global_backend_state["vllm_manager"] = None

            # Step 3: Start vLLM with new configuration
            await self._start_vllm_server()

            # Step 4: Update global state with new configuration
            _global_backend_state["selected_model"] = self.selected_model
            _global_backend_state["automatik_model"] = self.automatik_model

        except Exception as e:
            self.add_debug(f"❌ vLLM restart failed: {e}")
            raise

    async def _start_koboldcpp_server(self):
        """Start KoboldCPP server process with selected GGUF model"""
        global _global_backend_state

        try:
            # Check if KoboldCPP is already running from global state
            existing_manager = _global_backend_state.get("koboldcpp_manager")
            if existing_manager and existing_manager.is_running():
                self.add_debug("✅ KoboldCPP server already running (using existing process)")
                return

            # Get GGUF model info from global state
            gguf_models = _global_backend_state.get("gguf_models", {})
            if not gguf_models or self.selected_model not in gguf_models:
                raise RuntimeError(f"GGUF model '{self.selected_model}' not found")

            model_info = gguf_models[self.selected_model]
            model_path = str(model_info.path)

            # Initialize KoboldCPP Process Manager
            from aifred.lib.koboldcpp_manager import KoboldCPPProcessManager

            koboldcpp_manager = KoboldCPPProcessManager(port=5001)

            # Start server with automatic context detection (vLLM-style)
            # Uses cache interpolation and crash recovery
            def debug_callback(msg: str):
                self.add_debug(msg)

            success, config_info = await koboldcpp_manager.start_with_auto_detection(
                model_path=model_path,
                model_name=self.selected_model,  # For cache lookup
                timeout=240,  # 4 minutes for large models (30B needs ~2-3 min to load)
                feedback_callback=debug_callback
            )

            if success and config_info:
                # Show cache status
                if config_info.get('cached'):
                    self.add_debug("  • 📈 Context from cache (interpolated)")
                elif config_info.get('recalibrated'):
                    self.add_debug("  • 🔄 Context recalibrated (cache updated)")
                elif config_info.get('calibrated'):
                    self.add_debug("  • 🔬 Context calibrated (new cache entry)")

                # Cache startup context in backend (like vLLM does)
                from .backends import BackendFactory
                koboldcpp_backend = BackendFactory.create("koboldcpp", base_url=self.backend_url)
                debug_messages = [
                    f"   Model: {model_info.name}",
                    f"   GPU Config: {config_info['gpu_config']}"
                ]
                koboldcpp_backend.set_startup_context(
                    context=config_info['context_size'],
                    debug_messages=debug_messages
                )

                # Store in global state so it persists across page reloads
                _global_backend_state["koboldcpp_manager"] = koboldcpp_manager
                _global_backend_state["koboldcpp_context"] = config_info['context_size']
                _global_backend_state["koboldcpp_native_context"] = config_info.get('native_context')
                _global_backend_state["koboldcpp_selected_model"] = self.selected_model  # For auto-restart

                # Store context size in global cache for History compression
                # (same as vLLM does in context_manager.py)
                from aifred.lib.context_manager import _last_vram_limit_cache
                _last_vram_limit_cache["limit"] = config_info['context_size']

                # Start GPU Inactivity Monitoring (Reflex Background Task)
                # Automatically shuts down KoboldCPP after inactivity to save power (~100W idle)
                self.gpu_monitoring_active = True
                self.gpu_consecutive_idle_checks = 0
                self.gpu_total_checks = 0
                self.gpu_total_idle_checks = 0
                self.gpu_total_active_checks = 0

                # Start background task via Reflex Event system
                # Background event with @rx.event(background=True) handles State locking internally
                asyncio.create_task(self.start_inactivity_monitoring())

                self.add_debug("✅ KoboldCPP server ready on port 5001")
            else:
                raise RuntimeError("KoboldCPP failed to start with auto-config")

        except Exception as e:
            self.add_debug(f"❌ Failed to start KoboldCPP: {e}")
            import traceback
            self.add_debug(f"   {traceback.format_exc()}")
            _global_backend_state["koboldcpp_manager"] = None

    async def _ensure_koboldcpp_running(self):
        """Ensure KoboldCPP is running, start if stopped (e.g., by auto-unload monitor)"""
        global _global_backend_state

        existing_manager = _global_backend_state.get("koboldcpp_manager")

        # Check if already running
        if existing_manager and existing_manager.is_running():
            return  # Already running, nothing to do

        # KoboldCPP is not running - start it
        self.add_debug("⚠️ KoboldCPP not running - starting automatically...")

        # Set UI flag for auto-restart spinner (will be cleared by _start_koboldcpp_server)
        _global_backend_state["koboldcpp_auto_restarting"] = True
        yield  # Force immediate UI update to show spinner

        await self._start_koboldcpp_server()

        # Clear UI flag after successful start
        _global_backend_state["koboldcpp_auto_restarting"] = False
        yield  # Force immediate UI update to hide spinner

    async def _stop_koboldcpp_server(self):
        """Stop KoboldCPP server process gracefully"""
        global _global_backend_state

        # Stop GPU monitoring (background task will exit automatically)
        self.gpu_monitoring_active = False

        koboldcpp_manager = _global_backend_state.get("koboldcpp_manager")
        if koboldcpp_manager and koboldcpp_manager.is_running():
            self.add_debug("🛑 Stopping KoboldCPP server...")
            await koboldcpp_manager.stop()
            _global_backend_state["koboldcpp_manager"] = None  # Clear from global state
            _global_backend_state["koboldcpp_context"] = None
            self.add_debug("✅ KoboldCPP server stopped")

    async def _restart_koboldcpp_with_new_model(self):
        """
        Force restart KoboldCPP server with new model

        This explicitly stops the server, clears global state, and starts fresh.
        Used by set_selected_model() when switching GGUF models.
        """
        global _global_backend_state

        try:
            # Step 1: Stop existing KoboldCPP server
            await self._stop_koboldcpp_server()

            # Step 2: Clear global state to force re-initialization
            _global_backend_state["koboldcpp_manager"] = None

            # Step 3: Start KoboldCPP with new model
            await self._start_koboldcpp_server()

            # Step 4: Update global state with new configuration
            _global_backend_state["selected_model"] = self.selected_model
            _global_backend_state["automatik_model"] = self.automatik_model

        except Exception as e:
            self.add_debug(f"❌ KoboldCPP restart failed: {e}")
            raise

    async def _cleanup_old_backend(self, old_backend: str):
        """
        Clean up resources from previous backend before switching

        Args:
            old_backend: Backend type to clean up ("ollama", "vllm", etc.)
        """
        if old_backend == "ollama":
            # Unload all Ollama models from VRAM
            self.add_debug("🧹 Unloading Ollama models from VRAM...")
            try:
                # Create Ollama backend instance to call unload_all_models
                from .lib.llm_client import LLMClient
                llm_client = LLMClient(backend_type="ollama", base_url="http://localhost:11434")
                backend = llm_client._get_backend()

                if hasattr(backend, 'unload_all_models'):
                    success, unloaded_models = await backend.unload_all_models()
                    count = len(unloaded_models)
                    if count > 0:
                        self.add_debug(f"✅ Unloaded {count} Ollama model(s)")
                    else:
                        self.add_debug("ℹ️ No Ollama models were loaded")
            except Exception as e:
                self.add_debug(f"⚠️ Error unloading Ollama models: {e}")

        elif old_backend == "vllm":
            # Stop vLLM server to free VRAM - ALWAYS use pkill for reliability
            self.add_debug("🛑 Stopping vLLM server...")
            try:
                import subprocess
                import asyncio

                # Check if vLLM is running
                result = subprocess.run(["pgrep", "-f", "vllm serve"], capture_output=True, text=True)
                if result.returncode == 0:
                    # Kill vLLM process
                    subprocess.run(["pkill", "-f", "vllm serve"])
                    self.add_debug("✅ vLLM server stopped")

                    # Wait for VRAM to be freed (GPU driver needs time to release memory)
                    await asyncio.sleep(2)
                    self.add_debug("⏳ Waited for VRAM to be released")

                    # Clean up manager reference
                    _global_backend_state["vllm_manager"] = None
                else:
                    self.add_debug("ℹ️ vLLM server was not running")

            except Exception as e:
                self.add_debug(f"❌ Failed to stop vLLM: {e}")

        elif old_backend == "tabbyapi":
            # Stop TabbyAPI server to free VRAM
            self.add_debug("🛑 Stopping TabbyAPI server...")
            try:
                import subprocess
                import asyncio

                # Check if TabbyAPI is running (main.py or start.sh)
                result = subprocess.run(["pgrep", "-f", "tabbyapi"], capture_output=True, text=True)
                if result.returncode == 0:
                    # Kill TabbyAPI process
                    subprocess.run(["pkill", "-f", "tabbyapi"])
                    self.add_debug("✅ TabbyAPI server stopped")

                    # Wait for VRAM to be freed (GPU driver needs time to release memory)
                    await asyncio.sleep(2)
                    self.add_debug("⏳ Waited for VRAM to be released")
                else:
                    self.add_debug("ℹ️ TabbyAPI server was not running")

            except Exception as e:
                self.add_debug(f"❌ Failed to stop TabbyAPI: {e}")

        elif old_backend == "koboldcpp":
            # Stop KoboldCPP server to free VRAM
            self.add_debug("🛑 Stopping KoboldCPP server...")
            try:
                import subprocess
                import asyncio

                # Check if KoboldCPP is running
                result = subprocess.run(["pgrep", "-f", "koboldcpp"], capture_output=True, text=True)
                if result.returncode == 0:
                    # Kill KoboldCPP process
                    subprocess.run(["pkill", "-f", "koboldcpp"])
                    self.add_debug("✅ KoboldCPP server stopped")

                    # Wait for VRAM to be freed (GPU driver needs time to release memory)
                    await asyncio.sleep(2)
                    self.add_debug("⏳ Waited for VRAM to be released")

                    # Clean up manager reference
                    _global_backend_state["koboldcpp_manager"] = None
                    _global_backend_state["koboldcpp_context"] = None
                else:
                    self.add_debug("ℹ️ KoboldCPP server was not running")

            except Exception as e:
                self.add_debug(f"❌ Failed to stop KoboldCPP: {e}")

    async def send_message(self):
        """
        Send message to LLM with optional web research

        Portiert von Gradio chat_interactive_mode() mit Research-Integration
        """
        if not self.current_user_input.strip():
            return

        if self.is_generating:
            self.add_debug("⚠️ Already generating, please wait...")
            return

        # Ensure backend is initialized (should already be done by on_load)
        await self._ensure_backend_initialized()

        user_msg = self.current_user_input.strip()
        self.current_user_input = ""  # Clear input
        self.current_user_message = user_msg  # Zeige sofort die Eingabe an
        self.is_generating = True
        self.current_ai_response = ""
        yield  # Update UI sofort (Eingabefeld leeren + Spinner zeigen + Eingabe anzeigen)

        # Debug message wird von agent_core.py geloggt, nicht hier!

        try:
            # ============================================================
            # PHASE 1: Research/Automatik Mode - REAL STREAMING
            # ============================================================
            result_data = None

            if self.research_mode == "automatik":
                # Automatik mode: AI decides if research is needed
                # Debug message is already logged in conversation_handler.py

                # CRITICAL: Ensure KoboldCPP is running before LLM call
                if self.backend_type == "koboldcpp":
                    async for _ in self._ensure_koboldcpp_running():
                        yield  # Forward yields from _ensure_koboldcpp_running() to UI

                # Import chat_interactive_mode
                from .lib.conversation_handler import chat_interactive_mode

                # Initialize temporary history entry for real-time display
                temp_history_index = len(self.chat_history)
                self.chat_history.append((user_msg, self.current_ai_response))
                
                # Build LLM options (include enable_thinking toggle)
                llm_options = {
                    'enable_thinking': self.enable_thinking
                }

                # REAL STREAMING: Call async generator directly
                async for item in chat_interactive_mode(
                    user_text=user_msg,
                    stt_time=0.0,
                    model_choice=self.selected_model,
                    automatik_model=self.automatik_model,
                    history=self.chat_history[:-1],  # Exclude current temporary entry
                    session_id=self.session_id,
                    temperature_mode=self.temperature_mode,
                    temperature=self.temperature,
                    llm_options=llm_options,
                    backend_type=self.backend_type,
                    backend_url=self.backend_url,
                    num_ctx_mode=self.num_ctx_mode,
                    num_ctx_manual=self.num_ctx_manual
                ):
                    # Route messages based on type
                    if item["type"] == "debug":
                        self.debug_messages.append(format_debug_message(item["message"]))
                        if len(self.debug_messages) > 500:
                            self.debug_messages = self.debug_messages[-500:]
                    elif item["type"] == "content":
                        self.current_ai_response += item["text"]
                        # Update the temporary entry in chat history with the new content
                        if temp_history_index < len(self.chat_history):
                            self.chat_history[temp_history_index] = (user_msg, self.current_ai_response)
                        yield  # CRITICAL: Update UI to prevent backpressure during fast streaming
                    elif item["type"] == "result":
                        result_data = item["data"]
                        # Extract and update history IMMEDIATELY
                        ai_text, updated_history, inference_time = result_data
                        # Replace chat history with updated one from research - message is already in history
                        self.chat_history = updated_history
                        # The message is already in the history from the streaming, no need to re-add
                        yield  # Update UI to show new history entry
                        # Clear AI response and user message windows IMMEDIATELY
                        self.current_ai_response = ""
                        self.current_user_message = ""
                        self.is_generating = False  # Stop spinner, switch UI to history display
                        yield  # Force immediate UI update to clear both windows
                        # NOTE: Loop continues for cache metadata generation (important!)
                    elif item["type"] == "progress":
                        # Update processing progress
                        if item.get("clear", False):
                            self.clear_progress()
                        else:
                            self.set_progress(
                                phase=item.get("phase", ""),
                                current=item.get("current", 0),
                                total=item.get("total", 0),
                                failed=item.get("failed", 0)
                            )
                    elif item["type"] == "history_update":
                        # Update chat history (e.g. from summarization)
                        updated_history = item["data"]
                        self.chat_history = updated_history
                        self.add_debug(f"📊 History aktualisiert: {len(updated_history)} Messages")
                    elif item["type"] == "thinking_warning":
                        # Show thinking mode warning (model doesn't support reasoning)
                        self.thinking_mode_warning = item["model"]
                    elif item["type"] == "error":
                        # Handle error (e.g., context overflow, backend error)
                        error_msg = item.get("message", "Unknown error")
                        self.add_debug(f"❌ Error: {error_msg}")
                        # Reset UI state
                        self.is_generating = False
                        self.clear_progress()
                        self.current_user_message = ""
                        self.current_ai_response = ""

                    yield  # Update UI after each item

                # Separator wird bereits von conversation_handler gesendet
                # console_separator()  # Schreibt in Log-File
                # self.add_debug("────────────────────")  # Zeigt in Debug-Console
                # yield

            elif self.research_mode in ["quick", "deep"]:
                # Direct research mode (quick/deep)
                self.add_debug(f"🔍 Research Mode: {self.research_mode}")

                # CRITICAL: Ensure KoboldCPP is running before LLM call
                if self.backend_type == "koboldcpp":
                    async for _ in self._ensure_koboldcpp_running():
                        yield  # Forward yields from _ensure_koboldcpp_running() to UI

                # Initialize temporary history entry for real-time display
                temp_history_index = len(self.chat_history)
                self.chat_history.append((user_msg, self.current_ai_response))

                # Build LLM options (include enable_thinking toggle)
                llm_options = {
                    'enable_thinking': self.enable_thinking
                }

                # REAL STREAMING: Call async generator directly
                async for item in perform_agent_research(
                    user_text=user_msg,
                    stt_time=0.0,  # Kein STT in Reflex (noch)
                    mode=self.research_mode,
                    model_choice=self.selected_model,
                    automatik_model=self.automatik_model,
                    history=self.chat_history[:-1],  # Exclude current temporary entry
                    session_id=self.session_id,
                    temperature_mode=self.temperature_mode,
                    temperature=self.temperature,
                    llm_options=llm_options,
                    backend_type=self.backend_type,
                    backend_url=self.backend_url
                ):
                    # Route messages based on type
                    if item["type"] == "debug":
                        self.debug_messages.append(format_debug_message(item["message"]))
                        # Limit debug messages
                        if len(self.debug_messages) > 500:
                            self.debug_messages = self.debug_messages[-500:]
                    elif item["type"] == "content":
                        # REAL-TIME streaming to UI!
                        self.current_ai_response += item["text"]
                        # Update the temporary entry in chat history with the new content
                        if temp_history_index < len(self.chat_history):
                            self.chat_history[temp_history_index] = (user_msg, self.current_ai_response)
                    elif item["type"] == "result":
                        result_data = item["data"]
                        # Extract and update history IMMEDIATELY
                        ai_text, updated_history, inference_time = result_data
                        # Replace chat history with updated one from research - message is already in history
                        self.chat_history = updated_history
                        # The message is already in the history from the streaming, no need to re-add
                        yield  # Update UI to show new history entry
                        # Clear AI response and user message windows IMMEDIATELY
                        self.current_ai_response = ""
                        self.current_user_message = ""
                        self.is_generating = False  # Stop spinner, switch UI to history display
                        yield  # Force immediate UI update to clear both windows
                        # NOTE: Loop continues for cache metadata generation (important!)
                    elif item["type"] == "progress":
                        # Update processing progress
                        if item.get("clear", False):
                            self.clear_progress()
                        else:
                            self.set_progress(
                                phase=item.get("phase", ""),
                                current=item.get("current", 0),
                                total=item.get("total", 0),
                                failed=item.get("failed", 0)
                            )
                    elif item["type"] == "history_update":
                        # Update chat history (e.g. from summarization)
                        updated_history = item["data"]
                        self.chat_history = updated_history
                        self.add_debug(f"📊 History aktualisiert: {len(updated_history)} Messages")
                    elif item["type"] == "thinking_warning":
                        # Show thinking mode warning (model doesn't support reasoning)
                        self.thinking_mode_warning = item["model"]
                    elif item["type"] == "error":
                        # Handle error (e.g., context overflow, backend error)
                        error_msg = item.get("message", "Unknown error")
                        self.add_debug(f"❌ Error: {error_msg}")
                        # Reset UI state
                        self.is_generating = False
                        self.clear_progress()
                        self.current_user_message = ""
                        self.current_ai_response = ""

                    yield  # Update UI after each item

                # Set research_result flag if we got a result
                if result_data:
                    ai_text, updated_history, inference_time = result_data
                    # History and clearing already handled in loop above

            elif self.research_mode == "none":
                # No research mode: Direct LLM inference without web search
                self.add_debug("🧠 Eigenes Wissen (keine Websuche)")

                # Initialize temporary history entry for real-time display
                temp_history_index = len(self.chat_history)
                self.chat_history.append((user_msg, self.current_ai_response))

                # Start timing for preload phase (preparation + actual model loading)
                import time
                preload_start = time.time()

                # Build messages from history
                from .lib.message_builder import build_messages_from_history
                messages = build_messages_from_history(
                    history=self.chat_history[:-1],  # Exclude current temporary entry
                    current_user_text=user_msg
                )

                # Inject minimal system prompt with timestamp (from load_prompt - automatically includes date/time)
                from .lib.prompt_loader import load_prompt, detect_language
                detected_language = detect_language(user_msg)
                system_prompt_minimal = load_prompt('system_minimal', lang=detected_language)
                messages.insert(0, {"role": "system", "content": system_prompt_minimal})

                # Create backend and LLM client instances
                from .backends import BackendFactory, LLMOptions, LLMMessage
                from .lib.llm_client import LLMClient

                backend = BackendFactory.create(
                    self.backend_type,
                    base_url=self.backend_url
                )

                # Wrap backend in LLMClient for context calculation
                llm_client = LLMClient(
                    backend_type=self.backend_type,
                    base_url=self.backend_url
                )

                # Get model context limit
                model_limit, _ = await llm_client.get_model_context_limit(self.selected_model)

                # Count actual input tokens (using real tokenizer)
                from .lib.context_manager import estimate_tokens
                input_tokens = estimate_tokens(messages, model_name=self.selected_model)

                # IMPORTANT: Preload model BEFORE VRAM calculation!
                # Unload disabled - let Ollama manage VRAM automatically
                if self.backend_type == "ollama":
                    # STEP 1: Unload all models (DISABLED - Ollama LRU handles this)
                    # unload_success, unloaded_models = await backend.unload_all_models()
                    # if unloaded_models:
                    #     models_str = ", ".join(unloaded_models)
                    #     self.add_debug(f"🗑️ Entladene Modelle: {models_str}")
                    #     yield

                    # STEP 2: Load Haupt-LLM (Ollama loads on-demand if not in VRAM)
                    self.add_debug(f"🚀 Haupt-LLM ({self.selected_model}) wird vorgeladen...")
                    yield

                    # Preload via backend (measures actual model loading time)
                    success, load_time = await backend.preload_model(self.selected_model)

                    if success:
                        self.add_debug(f"✅ Haupt-LLM vorgeladen ({load_time:.1f}s)")
                    else:
                        self.add_debug(f"⚠️ Haupt-LLM Preload fehlgeschlagen ({load_time:.1f}s)")
                else:
                    # vLLM/TabbyAPI/KoboldCPP: Model bereits in VRAM beim Systemstart
                    # Kein Preload nötig - Backend lädt Modelle bei Server-Start
                    pass

                # Determine enable_vram_limit based on num_ctx_mode (same logic as Automatik)
                if self.num_ctx_mode == "manual":
                    # Manual mode: Use user-specified value directly (skip VRAM calculation)
                    final_num_ctx = self.num_ctx_manual
                    from .lib.logging_utils import log_message
                    log_message(f"🔧 Manual num_ctx: {self.num_ctx_manual:,} (VRAM calculation skipped)")
                    vram_debug_msgs = []
                else:
                    # Auto mode: Determine VRAM limiting
                    enable_vram_limit = (self.num_ctx_mode == "auto_vram")

                    # Dynamic num_ctx calculation (AFTER preload to get accurate VRAM state)
                    from .lib.context_manager import calculate_dynamic_num_ctx
                    final_num_ctx, vram_debug_msgs = await calculate_dynamic_num_ctx(
                        llm_client, self.selected_model, messages, None,
                        enable_vram_limit=enable_vram_limit
                    )

                # Show VRAM debug messages in console
                for msg in vram_debug_msgs:
                    self.add_debug(msg)
                    yield

                self.add_debug("✅ System-Prompt erstellt")
                yield

                # Show compact context info (matching Automatik mode style)
                self.add_debug(f"📊 Haupt-LLM: {input_tokens} / {final_num_ctx} Tokens (max: {model_limit})")
                yield

                # Temperature (matching Automatik mode style)
                self.add_debug(f"🌡️ Temperature: {self.temperature} (manual)")
                yield

                # Build LLM options
                llm_options = LLMOptions(
                    temperature=self.temperature,
                    num_ctx=final_num_ctx,  # Use dynamically calculated context (or manual override)
                    enable_thinking=self.enable_thinking
                )

                # Console: LLM starts (matching Automatik mode)
                self.add_debug(f"🤖 Haupt-LLM startet: {self.selected_model}")
                yield

                # Stream response directly from LLM
                import time
                inference_start = time.time()
                full_response = ""
                ttft = None
                first_token_received = False
                tokens_generated = 0

                async for chunk in llm_client.chat_stream(
                    model=self.selected_model,
                    messages=messages,
                    options=llm_options
                ):
                    if chunk["type"] == "content":
                        # Measure TTFT (matching Automatik mode)
                        if not first_token_received:
                            ttft = time.time() - inference_start
                            first_token_received = True
                            self.add_debug(f"⚡ TTFT: {ttft:.2f}s")
                            yield

                        # Stream content to UI in real-time
                        self.current_ai_response += chunk["text"]
                        full_response += chunk["text"]
                        # Update the temporary entry in chat history
                        if temp_history_index < len(self.chat_history):
                            self.chat_history[temp_history_index] = (user_msg, self.current_ai_response)
                        yield  # Update UI
                    elif chunk["type"] == "done":
                        metrics = chunk.get("metrics", {})
                        tokens_generated = metrics.get("tokens_generated", 0)

                inference_time = time.time() - inference_start

                # Console: LLM finished (matching Automatik mode)
                tokens_per_sec = tokens_generated / inference_time if inference_time > 0 else 0
                self.add_debug(f"✅ Haupt-LLM fertig ({inference_time:.1f}s, {tokens_generated} tokens, {tokens_per_sec:.1f} tok/s)")
                yield

                # Separator nach Haupt-LLM (matching other modes)
                console_separator()
                self.add_debug("────────────────────")
                yield

                # Format <think> tags as collapsible (if present)
                from .lib.formatting import format_thinking_process, format_metadata, format_number
                thinking_html = format_thinking_process(
                    full_response,
                    model_name=self.selected_model,
                    inference_time=inference_time,
                    tokens_per_sec=tokens_per_sec
                )

                # Add metadata footer (Inferenz + Tok/s + Quelle) like other modes
                metadata = format_metadata(
                    f"(Inferenz: {format_number(inference_time, 1)}s ({format_number(tokens_per_sec, 1)} tok/s), Quelle: Trainingsdaten)"
                )
                formatted_response = f"{thinking_html} {metadata}"

                # Update chat history with formatted response + metadata
                self.chat_history[temp_history_index] = (user_msg, formatted_response)
                yield  # Update UI

                # Clear response windows
                self.current_ai_response = ""
                self.current_user_message = ""
                self.is_generating = False
                yield  # Force UI update

                await llm_client.close()

            # ============================================================
            # POST-RESPONSE: History Summarization Check (im Hintergrund)
            # ============================================================
            # Kompression läuft NACH der Antwort, während User liest
            # Eingabefelder werden während Kompression disabled

            try:
                from .lib.context_manager import summarize_history_if_needed
                from .backends import BackendFactory

                # Immer prüfen - token-basiert (keine Message-Count-Prüfung mehr)
                if True:  # summarize_history_if_needed macht alle Checks intern
                    yield
                    # Backend für Summarization
                    temp_backend = BackendFactory.create(
                        self.backend_type,
                        base_url=self.backend_url
                    )

                    # Context-Limit für History-Kompression:
                    # Nutze gespeichertes VRAM-Limit aus letzter Inferenz (verhindert Neuberechnung!)
                    from aifred.lib.context_manager import _last_vram_limit_cache

                    if self.num_ctx_mode == "manual":
                        context_limit = self.num_ctx_manual
                    elif _last_vram_limit_cache["limit"] > 0:
                        # Nutze gespeichertes VRAM-Limit (aus calculate_dynamic_num_ctx)
                        context_limit = _last_vram_limit_cache["limit"]
                    else:
                        # Fallback: 8K (nur beim allerersten Aufruf vor erster Inferenz)
                        context_limit = 8192
                        self.add_debug("⚠️ Kein VRAM-Limit gespeichert, nutze Fallback 8K")

                    # Setze Kompression-Flag (disabled Input-Felder)
                    self.is_compressing = True
                    yield

                    # Summarization check (yields events wenn nötig)
                    async for event in summarize_history_if_needed(
                        history=self.chat_history,
                        llm_client=temp_backend,
                        model_name=self.automatik_model,  # Schnelles Model
                        context_limit=context_limit  # Uses only context_limit, not model_size
                    ):
                        if event["type"] == "history_update":
                            self.chat_history = event["data"]
                            self.add_debug(f"✅ History komprimiert: {len(self.chat_history)} Messages")
                            yield
                        elif event["type"] == "debug":
                            self.add_debug(event["message"])
                            yield
                        elif event["type"] == "progress":
                            self.set_progress(phase="compress")
                            yield

                    await temp_backend.close()

                    # Progress clearen falls gesetzt
                    if self.progress_phase == "compress":
                        self.clear_progress()
                        yield

                    # Kompression fertig - Input-Felder wieder enablen
                    self.is_compressing = False
                    yield

            except Exception as e:
                # Nicht kritisch - einfach weitermachen
                import traceback
                self.add_debug(f"⚠️ History compression check failed: {e}")
                self.add_debug(f"Traceback: {traceback.format_exc()}")
                self.is_compressing = False
                yield

            # Separator nach Compression-Check (einmal am Ende)
            console_separator()  # Schreibt in Log-File
            self.add_debug("────────────────────")  # Zeigt in Debug-Console
            yield

            # Clear response display
            self.current_ai_response = ""
            yield  # Final update to clear AI response window

            # Debug-Zeile entfernt - User wollte das nicht sehen
            # self.add_debug(f"✅ Response complete ({len(full_response)} chars)")

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self.current_ai_response = error_msg
            # Update the temporary entry in chat history with the error
            if temp_history_index < len(self.chat_history):
                self.chat_history[temp_history_index] = (user_msg, error_msg)
            self.add_debug(f"❌ Generation failed: {e}")
            import traceback
            self.add_debug(f"Traceback: {traceback.format_exc()}")

        finally:
            self.is_generating = False
            # Final debug sync


    def clear_chat(self):
        """Clear chat history"""
        self.chat_history = []
        self.current_ai_response = ""
        self.current_user_message = ""
        self.debug_messages = []  # Debug Console auch leeren!
        self.add_debug("🗑️ Chat cleared")

    async def load_default_settings(self):
        """Load default settings from config.py and apply them to state"""
        from .lib.settings import reset_to_defaults, load_settings
        from .lib import TranslationManager

        self.add_debug("💾 Loading default settings from config.py...")
        yield  # Update UI immediately

        if reset_to_defaults():
            self.add_debug("✅ Default settings saved to file")
            yield

            # Reload settings from file (all values MUST be present after reset_to_defaults())
            saved_settings = load_settings()
            if saved_settings:
                # Update state with loaded settings (only attributes that exist in state)
                # No fallbacks needed - reset_to_defaults() ensures all values are present
                self.backend_type = saved_settings["backend_type"]
                self.research_mode = saved_settings["research_mode"]

                # Update research_mode_display to match loaded research_mode
                self.research_mode_display = TranslationManager.get_research_mode_display(
                    self.research_mode, self.ui_language
                )

                self.temperature = saved_settings["temperature"]
                self.temperature_mode = saved_settings["temperature_mode"]
                self.enable_thinking = saved_settings["enable_thinking"]
                self.enable_tts = saved_settings["enable_tts"]
                self.enable_yarn = saved_settings["enable_yarn"]
                self.yarn_factor = saved_settings["yarn_factor"]

                # IMPORTANT: Set model names from defaults (prevents fallback to available_models[0])
                # The "model" and "automatik_model" keys come from get_default_settings()
                self.selected_model = saved_settings.get("model", self.selected_model)
                self.automatik_model = saved_settings.get("automatik_model", self.automatik_model)

                self.add_debug("🔄 Settings reloaded from file")
                yield

                # Reinitialize backend with new settings
                await self.initialize_backend()
                self.add_debug("✅ All settings applied successfully")
                yield
            else:
                self.add_debug("⚠️ Failed to reload settings from file")
                yield
        else:
            self.add_debug("❌ Failed to load default settings")
            yield  # Update UI even on error

    def toggle_auto_refresh(self):
        """Toggle auto-scroll for all areas (Debug Console, Chat History, AI Response)"""
        self.auto_refresh_enabled = not self.auto_refresh_enabled

    async def restart_backend(self):
        """Restart current LLM backend service and reload model list"""
        import subprocess
        import json
        import asyncio
        global _global_backend_state

        # Prevent concurrent restarts
        if self.backend_switching:
            self.add_debug("⚠️ Backend restart already in progress, please wait...")
            return

        self.backend_switching = True
        yield  # Update UI to disable buttons

        try:
            backend_name = self.backend_type.upper()
            self.add_debug(f"🔄 Restarting {backend_name} service...")
            yield  # Update UI

            if self.backend_type == "ollama":
                subprocess.run(["systemctl", "restart", "ollama"], check=True)
                self.add_debug(f"✅ {backend_name} service restarted")
                yield  # Update UI after restart

                # Wait for Ollama to be ready (active polling with retry)
                self.add_debug("⏳ Waiting for Ollama API to be ready...")
                yield  # Update UI

                max_retries = 10
                ollama_ready = False

                for attempt in range(max_retries):
                    try:
                        endpoint = f'{self.backend_url}/api/tags'
                        result = subprocess.run(
                            ['curl', '-s', endpoint],
                            capture_output=True,
                            text=True,
                            timeout=2.0
                        )

                        if result.returncode == 0:
                            # Try to parse JSON to verify API is actually ready
                            data = json.loads(result.stdout)
                            self.available_models = [m["name"] for m in data.get("models", [])]

                            # Update global state
                            _global_backend_state["available_models"] = self.available_models

                            elapsed_time = (attempt + 1) * 0.5
                            self.add_debug(f"✅ Ollama ready after {elapsed_time:.1f}s ({len(self.available_models)} models found)")
                            ollama_ready = True
                            break
                    except Exception:
                        pass  # Retry on any error

                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5)  # Short polling interval
                        yield  # Update UI during polling

                if not ollama_ready:
                    self.add_debug("⚠️ Ollama API might not be ready yet (timeout after 5s)")
                    yield

            elif self.backend_type == "vllm":
                # vLLM: Stop and restart with current model
                self.add_debug("⏹️ Stopping vLLM server...")
                yield  # Update UI
                await self._stop_vllm_server()

                self.add_debug("🚀 Starting vLLM server...")
                yield  # Update UI
                await self._start_vllm_server()

                # Verify vLLM is ready
                self.add_debug("⏳ Waiting for vLLM API to be ready...")
                yield

                max_retries = 10
                vllm_ready = False

                for attempt in range(max_retries):
                    try:
                        import requests
                        # vLLM health check endpoint
                        response = requests.get(
                            f"{self.backend_url}/health",
                            timeout=2.0
                        )

                        if response.status_code == 200:
                            elapsed_time = (attempt + 1) * 0.5
                            self.add_debug(f"✅ vLLM ready after {elapsed_time:.1f}s")
                            vllm_ready = True
                            break
                    except Exception:
                        pass  # Retry on any error

                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5)
                        yield

                if not vllm_ready:
                    self.add_debug("⚠️ vLLM might not be ready yet (timeout after 5s)")

                yield  # Update UI
            elif self.backend_type == "tabbyapi":
                # TabbyAPI: Unload and reload model via API
                self.add_debug("⏹️ Unloading TabbyAPI model...")
                yield  # Update UI

                try:
                    # Unload current model
                    import requests
                    response = requests.post(
                        f"{self.backend_url}/v1/model/unload",
                        headers={"Content-Type": "application/json"},
                        timeout=10.0
                    )

                    if response.status_code == 200:
                        self.add_debug("✅ Model unloaded successfully")
                        yield

                        # Reload model
                        self.add_debug("🚀 Reloading TabbyAPI model...")
                        yield

                        load_response = requests.post(
                            f"{self.backend_url}/v1/model/load",
                            json={"name": self.selected_model},
                            headers={"Content-Type": "application/json"},
                            timeout=30.0
                        )

                        if load_response.status_code == 200:
                            self.add_debug("✅ Model load command successful")
                            yield

                            # Verify model is actually loaded
                            self.add_debug("⏳ Verifying model is loaded...")
                            yield

                            max_retries = 10
                            model_ready = False

                            for attempt in range(max_retries):
                                try:
                                    verify_response = requests.get(
                                        f"{self.backend_url}/v1/models",
                                        headers={"Content-Type": "application/json"},
                                        timeout=2.0
                                    )

                                    if verify_response.status_code == 200:
                                        data = verify_response.json()
                                        # Check if any model is loaded
                                        if data.get("data") and len(data["data"]) > 0:
                                            elapsed_time = (attempt + 1) * 0.5
                                            self.add_debug(f"✅ TabbyAPI ready after {elapsed_time:.1f}s")
                                            model_ready = True
                                            break
                                except Exception:
                                    pass

                                if attempt < max_retries - 1:
                                    await asyncio.sleep(0.5)
                                    yield

                            if not model_ready:
                                self.add_debug("⚠️ Model might not be fully loaded yet (timeout after 5s)")
                        else:
                            self.add_debug(f"⚠️ Model reload failed: {load_response.status_code}")
                    else:
                        self.add_debug(f"⚠️ Model unload failed: {response.status_code}")

                except Exception as e:
                    self.add_debug(f"⚠️ TabbyAPI restart failed: {e}")

                yield  # Update UI

            elif self.backend_type == "koboldcpp":
                # KoboldCPP: Stop existing process, rescan models, restart with current model
                self.add_debug("⏹️ Stopping KoboldCPP server...")
                yield  # Update UI

                # Stop existing KoboldCPP process
                existing_manager = _global_backend_state.get("koboldcpp_manager")
                if existing_manager and existing_manager.is_running():
                    existing_manager.stop()
                    self.add_debug("✅ KoboldCPP process stopped")
                    yield

                # Rescan GGUF models to pick up newly downloaded files
                self.add_debug("🔍 Rescanning GGUF models...")
                yield

                from aifred.lib.gguf_utils import find_all_gguf_models

                gguf_models_list = find_all_gguf_models()
                gguf_models = {model.name: model for model in gguf_models_list}
                _global_backend_state["gguf_models"] = gguf_models

                # Update available models list
                self.available_models = list(gguf_models.keys())
                _global_backend_state["available_models"] = self.available_models

                self.add_debug(f"✅ Found {len(gguf_models)} GGUF models")
                yield

                # Restart KoboldCPP with current model
                if self.selected_model in gguf_models:
                    self.add_debug(f"🚀 Restarting KoboldCPP with {self.selected_model}...")
                    yield

                    # Trigger backend initialization (will start KoboldCPP)
                    await self._start_koboldcpp_server()
                else:
                    self.add_debug(f"⚠️ Model '{self.selected_model}' not found after rescan")
                    yield

        except Exception as e:
            self.add_debug(f"❌ {backend_name} restart failed: {e}")
        finally:
            self.backend_switching = False
            yield  # Re-enable buttons

    async def restart_ollama(self):
        """Legacy method - calls restart_backend()"""
        await self.restart_backend()


    def restart_aifred(self):
        """Restart AIfred service via systemctl"""
        import subprocess
        import threading

        try:
            self.add_debug("🔄 Restarting AIfred service...")

            # Schedule systemd restart in background thread
            # This allows us to return rx.call_script() BEFORE the service dies
            def restart_service_delayed():
                import time
                time.sleep(0.5)  # Short delay to let browser script execute first
                subprocess.run(["systemctl", "restart", "aifred-intelligence"], check=False)

            thread = threading.Thread(target=restart_service_delayed, daemon=True)
            thread.start()

            self.add_debug("✅ AIfred service restart initiated")
            self.add_debug("🔄 Browser wird in 0.5s neu geladen...")

            # Return the reload script IMMEDIATELY
            # This executes in browser BEFORE systemd kills the service
            # Browser will reload, wait for service to come back up, then reconnect
            return rx.call_script("window.location.reload(true)")

        except Exception as e:
            self.add_debug(f"❌ AIfred service restart failed: {e}")

    async def clear_vector_cache(self):
        """Clear Vector DB by deleting all documents (keeps collection intact)"""
        try:
            self.add_debug("🗑️ Clearing Vector DB...")
            yield  # Update UI immediately

            import chromadb
            client = chromadb.HttpClient(host='localhost', port=8000)

            # Get collection
            collection = client.get_collection('research_cache')

            # Get all document IDs
            all_ids = collection.get(include=[])["ids"]

            if all_ids:
                count = len(all_ids)
                self.add_debug(f"   📊 Deleting {count} entries...")
                yield  # Update UI

                # Delete all documents (keeps collection structure intact)
                collection.delete(ids=all_ids)

                self.add_debug(f"✅ Vector DB cleared successfully ({count} entries deleted)")
                yield  # Update UI
            else:
                self.add_debug("✅ Vector DB is already empty")
                yield  # Update UI

        except Exception as e:
            self.add_debug(f"❌ Vector DB clear failed: {e}")
            yield  # Update UI even on error


    async def set_selected_model(self, model: str):
        """Set selected model and restart backend if needed"""
        old_model = self.selected_model
        self.selected_model = model
        # Clear thinking mode warning when model changes
        self.thinking_mode_warning = ""
        self.add_debug(f"📝 Model changed: {old_model} → {model}")

        # vLLM/TabbyAPI/KoboldCPP: Force restart backend for model change
        if self.backend_type in ["vllm", "tabbyapi", "koboldcpp"] and old_model != model:
            # vLLM/KoboldCPP can only load ONE model - set Automatik-LLM to same as Main-LLM
            if self.backend_type in ["vllm", "koboldcpp"] and self.automatik_model != model:
                self.automatik_model = model

            # Reset YaRN to 1.0 on model change (new model needs recalibration)
            # Only for vLLM (KoboldCPP doesn't use YaRN)
            if self.backend_type == "vllm":
                old_yarn_factor = self.yarn_factor
                if old_yarn_factor != 1.0:
                    self.yarn_factor = 1.0
                    self.yarn_factor_input = "1.0"
                    self.yarn_max_factor = 0.0  # Unknown for new model
                    self.yarn_max_tested = False
                    self.add_debug(f"🔄 YaRN factor reset: {old_yarn_factor:.1f}x → 1.0x (new model needs recalibration)")

            self.add_debug("🔄 Backend-Neustart für Modell-Wechsel...")

            # Show loading spinner
            self.vllm_restarting = True
            yield  # Update UI to show spinner

            try:
                if self.backend_type == "vllm":
                    await self._restart_vllm_with_new_config()
                elif self.backend_type == "koboldcpp":
                    await self._restart_koboldcpp_with_new_model()
                else:  # tabbyapi
                    await self.initialize_backend()  # TabbyAPI might not need full restart
                self.add_debug(f"✅ Neues Modell geladen: {model}")
            finally:
                # Hide loading spinner
                self.vllm_restarting = False
                yield  # Update UI to hide spinner

        self._save_settings()

    def toggle_thinking_mode(self):
        """Toggle Qwen3 Thinking Mode"""
        self.enable_thinking = not self.enable_thinking
        mode_name = "Thinking Mode" if self.enable_thinking else "Non-Thinking Mode"
        self.add_debug(f"🧠 {mode_name} aktiviert")
        self._save_settings()

    def toggle_yarn(self):
        """Toggle YaRN context extension"""
        self.enable_yarn = not self.enable_yarn
        status = "aktiviert" if self.enable_yarn else "deaktiviert"
        self.add_debug(f"📏 YaRN Context Extension {status} (Faktor: {self.yarn_factor}x)")
        if self.enable_yarn:
            self.add_debug("⚠️ Klicke 'Apply YaRN' um Backend mit neuem Faktor zu starten!")
        self._save_settings()

    def set_yarn_factor_input(self, factor: str):
        """Update YaRN factor input field (temporary, not applied yet)"""
        self.yarn_factor_input = factor
        # Calculate estimated context for preview
        try:
            # Normalize comma to point for German locale
            factor_normalized = factor.replace(',', '.')
            factor_float = float(factor_normalized)
            if 1.0 <= factor_float <= 8.0 and self.vllm_max_tokens > 0:
                estimated_context = int(self.vllm_max_tokens * factor_float)
                self.add_debug(f"📏 YaRN Faktor: {factor_float}x (~{estimated_context} tokens)")
        except ValueError:
            pass  # Ignore invalid input during typing

    async def apply_yarn_factor(self):
        """Apply YaRN factor and restart backend"""
        try:
            # Normalize comma to point for German locale
            factor_normalized = self.yarn_factor_input.replace(',', '.')
            factor_float = float(factor_normalized)
            if not (1.0 <= factor_float <= 8.0):
                self.add_debug(f"❌ YaRN-Faktor muss zwischen 1.0 und 8.0 liegen (eingegeben: {factor_float})")
                return

            old_factor = self.yarn_factor
            self.yarn_factor = factor_float
            self._save_settings()

            estimated_context = int(self.vllm_max_tokens * factor_float)
            self.add_debug(f"✅ YaRN-Faktor gesetzt: {old_factor}x → {factor_float}x (~{estimated_context} tokens)")

            # Warn if factor is high (potential VRAM overflow)
            if factor_float > 2.0:
                self.add_debug(f"⚠️ Hoher YaRN-Faktor ({factor_float}x) kann VRAM überschreiten → möglicher Crash!")
                self.add_debug("💡 Tipp: Bei VRAM-Problemen Faktor reduzieren oder mehr GPU-RAM nutzen")

            # Force restart backend for YaRN change (vLLM/TabbyAPI)
            if self.backend_type in ["vllm", "tabbyapi"]:
                self.add_debug("🔄 Backend-Neustart für YaRN-Änderung...")

                # Show loading spinner
                self.vllm_restarting = True
                yield  # Update UI to show spinner

                try:
                    if self.backend_type == "vllm":
                        await self._restart_vllm_with_new_config()
                    else:  # tabbyapi
                        await self.initialize_backend()  # TabbyAPI might not need full restart

                    # Show actual factor after restart (might have been reduced by auto-calibration)
                    actual_factor = self.yarn_factor
                    if actual_factor != factor_float:
                        self.add_debug(f"✅ Backend neu gestartet (YaRN: {factor_float}x → {actual_factor}x nach Auto-Kalibrierung)")
                    else:
                        self.add_debug(f"✅ Backend neu gestartet mit YaRN {actual_factor}x")

                finally:
                    # Hide loading spinner
                    self.vllm_restarting = False
                    yield  # Update UI to hide spinner

        except ValueError:
            self.add_debug(f"❌ Ungültiger YaRN-Faktor: {self.yarn_factor_input}")

    def set_temperature(self, temp: list[float]):
        """Set temperature (from slider which returns list[float])"""
        self.temperature = temp[0] if isinstance(temp, list) else temp
        self._save_settings()

    def set_temperature_mode(self, checked: bool):
        """
        Set temperature mode from toggle switch

        Args:
            checked: True = manual mode (user slider), False = auto mode (Intent-Detection)
        """
        self.temperature_mode = "manual" if checked else "auto"
        self._save_settings()
        mode_label = "Manual" if checked else "Auto"
        self.add_debug(f"🌡️ Temperature Mode: {mode_label}")

    def set_num_ctx_mode(self, mode: str):
        """
        Set num_ctx mode (NICHT in settings.json gespeichert - Reset bei jedem Start)

        Modes:
        - auto_vram: VRAM-optimiert (Standard, verhindert CPU-Offload)
        - auto_max: Modell-Maximum (riskant, kann CPU-Offload auslösen)
        - manual: Manueller Wert aus num_ctx_manual
        """
        self.num_ctx_mode = mode
        self.add_debug(f"🎯 Context Mode: {mode}")
        # WICHTIG: Nicht in settings.json speichern!

    def set_num_ctx_mode_from_display(self, display_value: str):
        """Set num_ctx mode from UI display value (German text)"""
        # Map German display text to mode
        if "VRAM" in display_value:
            mode = "auto_vram"
        elif "Maximum" in display_value:
            mode = "auto_max"
        else:  # "Manuell"
            mode = "manual"
        self.set_num_ctx_mode(mode)

    def set_num_ctx_manual(self, value: str):
        """Set manual num_ctx value (only used when mode=manual)"""
        try:
            num_value = int(value)
            if num_value < 2048:
                num_value = 2048
            if num_value > 1048576:  # 1M tokens max
                num_value = 1048576
            self.num_ctx_manual = num_value
            self.add_debug(f"🔧 Manual num_ctx: {num_value:,}")
            # WICHTIG: Nicht in settings.json speichern!
        except ValueError:
            self.add_debug(f"❌ Ungültiger num_ctx Wert: {value}")

    def set_research_mode(self, mode: str):
        """Set research mode"""
        self.research_mode = mode
        self.add_debug(f"🔍 Research mode: {mode}")

    def set_research_mode_display(self, display_value: str):
        """Set research mode from UI display value"""
        from .lib import TranslationManager

        # Use translation manager to get the internal mode value
        self.research_mode_display = display_value
        self.research_mode = TranslationManager.get_research_mode_value(display_value)
        self.add_debug(f"🔍 Research mode: {self.research_mode}")
        self._save_settings()  # Persist research mode to settings.json

    async def set_automatik_model(self, model: str):
        """Set automatik model for decision and query optimization"""
        old_model = self.automatik_model
        self.automatik_model = model
        self.add_debug(f"⚡ Automatik model changed: {old_model} → {model}")
        self._save_settings()

        # vLLM/TabbyAPI: Auto-restart backend for model change
        if self.backend_type in ["vllm", "tabbyapi"] and old_model != model:
            self.add_debug("🔄 Backend-Neustart für Automatik-Modell-Wechsel...")
            await self.initialize_backend()
            self.add_debug("✅ Neues Automatik-Modell geladen")
        # Ollama: Preload new model in background (via curl)
        elif self.backend_type == "ollama":
            import subprocess
            preload_cmd = f'curl -s http://localhost:11434/api/chat -d \'{{"model":"{model}","messages":[{{"role":"user","content":"hi"}}],"stream":false,"options":{{"num_predict":1}}}}\' > /dev/null 2>&1 &'
            try:
                subprocess.Popen(preload_cmd, shell=True)
                log_message(f"🚀 Preloading new Automatik-LLM: {model}")
                self.add_debug(f"🚀 Preloading {model}...")
            except Exception as e:
                log_message(f"⚠️ Preload failed: {e}")

        # Note: Context limit will be queried on first use (fast ~30ms) and cached by httpx

    def toggle_tts(self):
        """Toggle TTS on/off"""
        self.enable_tts = not self.enable_tts
        self.add_debug(f"🔊 TTS: {'enabled' if self.enable_tts else 'disabled'}")

    def set_ui_language(self, lang: str):
        """Set UI language"""
        if lang in ["de", "en"]:
            self.ui_language = lang
            # Update research_mode_display to match new language
            from .lib import TranslationManager
            self.research_mode_display = TranslationManager.get_research_mode_display(self.research_mode, lang)
            self.add_debug(f"🌐 UI Language changed to: {lang}")
        else:
            self.add_debug(f"❌ Invalid language: {lang}. Use 'de' or 'en'")

    def get_text(self, key: str):
        """Get translated text based on current UI language"""
        from .lib import TranslationManager
        return TranslationManager.get_text(key, self.ui_language)
