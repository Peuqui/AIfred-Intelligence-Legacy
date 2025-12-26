"""
Reflex State Management for AIfred Intelligence

Main state for chat, settings, and backend management
"""

import reflex as rx
from typing import List, Tuple, Any, Dict, TypedDict
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
from .lib.logging_utils import CONSOLE_SEPARATOR
from .lib.formatting import format_debug_message
from .lib.conversation_handler import extract_model_name
from .lib import config
from .lib.config import EDGE_TTS_VOICES, PIPER_VOICES, ESPEAK_VOICES
from .lib.vllm_manager import vLLMProcessManager
from .lib.model_manager import (
    sort_models_grouped,
    is_backend_compatible
    # NOTE: backend_supports_dynamic_models not imported - State has own @rx.var implementation
)
from .lib.gpu_monitor import round_to_nominal_vram
from .lib.multi_agent import (
    run_sokrates_direct_response,
    run_sokrates_analysis,
    run_tribunal,
)

# ============================================================
# TypedDicts for Reflex (foreach requires typed dicts)
# ============================================================

class FailedSourceDict(TypedDict):
    """A single failed source entry"""
    url: str
    error: str
    method: str

class ChatMessageParsed(TypedDict):
    """Parsed chat message with embedded failed sources and images"""
    user_msg: str
    ai_msg: str
    failed_sources: List[FailedSourceDict]
    images: List[str]  # List of data URLs for image thumbnails
    sokrates_mode: str  # Extracted mode from 🏛️[Mode] marker (e.g., "Advocatus Diaboli")
    sokrates_content: str  # AI message with marker stripped for display
    alfred_mode: str  # Extracted mode from 🎩[Mode] marker (e.g., "Überarbeitung R2")
    alfred_content: str  # AI message with marker stripped for display
    salomo_mode: str  # Extracted mode from 👑[Mode] marker (e.g., "Synthese R1", "Urteil")
    salomo_content: str  # AI message with marker stripped for display


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

# Lock to prevent race conditions during backend initialization
# (e.g., two browser tabs starting simultaneously)
_backend_init_lock = asyncio.Lock()


# ============================================================
# Module-Level Whisper Model (Global across all sessions)
# ============================================================
_whisper_model = None  # Shared WhisperModel instance


def unload_whisper_model():
    """Unload Whisper model from memory (free GPU/RAM)"""
    global _whisper_model
    if _whisper_model is not None:
        _whisper_model = None
        import gc
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        log_message("🗑️ Whisper: Model unloaded from memory")
    else:
        log_message("⚠️ Whisper: No model loaded")


def initialize_whisper_model(model_name: str = "small"):
    """
    Initialize Whisper STT model (module-level, shared across sessions)

    Args:
        model_name: Whisper model size (tiny, base, small, medium, large)

    Returns:
        WhisperModel instance or None on failure
    """
    global _whisper_model

    if _whisper_model is not None:
        log_message(f"✅ Whisper: Model already loaded ({model_name})")
        return _whisper_model

    try:
        from faster_whisper import WhisperModel
        from .lib.config import WHISPER_MODELS, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE

        # Extract model ID from display name (e.g., "small (466MB, ...)" -> "small")
        model_id = WHISPER_MODELS.get(model_name, model_name)

        log_message(f"🎤 Whisper: Loading model '{model_id}'...")

        # Use device and compute type from config.py
        # Default: CPU to preserve GPU VRAM for LLM inference
        device = WHISPER_DEVICE
        compute_type = WHISPER_COMPUTE_TYPE

        _whisper_model = WhisperModel(model_id, device=device, compute_type=compute_type)

        log_message(f"✅ Whisper: Model '{model_id}' loaded on {device} ({compute_type})")
        return _whisper_model

    except ImportError as e:
        log_message(f"⚠️ Whisper: Import failed - {str(e)}")
        return None
    except Exception as e:
        log_message(f"❌ Whisper: Failed to load model: {e}")
        return None


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
    current_user_message: str = ""  # The message currently being processed
    current_ai_response: str = ""
    is_generating: bool = False
    is_compressing: bool = False  # Shows if history compression is running
    is_uploading_image: bool = False  # Shows spinner during image upload
    is_calibrating: bool = False  # Shows spinner during context calibration
    calibrate_extended: bool = False  # Toggle for RoPE 2x calibration mode

    # Image Upload State
    pending_images: List[Dict[str, str]] = []  # [{"name": "img.jpg", "base64": "...", "url": "...", "original_bytes": bytes}]
    image_upload_warning: str = ""  # Warning message if non-vision model selected
    max_images_per_message: int = 5  # Limit concurrent uploads
    camera_available: bool = False  # True if browser supports camera access (set by JavaScript)
    _camera_detection_done: bool = False  # Internal flag to prevent duplicate logging from Reflex hydration

    # Failed Sources State (shown as clickable bubble before AI response)
    failed_sources: List[Dict[str, str]] = []  # [{"url": "...", "error": "...", "method": "..."}]
    # Pending failed sources for current request (will be embedded in AI response)
    _pending_failed_sources: List[Dict[str, str]] = []

    # Image Crop State
    crop_modal_open: bool = False  # Show crop modal?
    crop_image_index: int = -1  # Which image is being cropped (index in pending_images)
    crop_preview_url: str = ""  # Data URL for crop preview (large image in modal)
    crop_box_x: float = 0.0  # Crop box position X in percent (0-100)
    crop_box_y: float = 0.0  # Crop box position Y in percent (0-100)
    crop_box_width: float = 100.0  # Crop box width in percent (0-100)
    crop_box_height: float = 100.0  # Crop box height in percent (0-100)

    # Image Lightbox State (for viewing images in chat history)
    lightbox_open: bool = False  # Show lightbox modal?
    lightbox_image_url: str = ""  # Data URL for lightbox image

    # Multi-Agent Help Modal
    multi_agent_help_open: bool = False  # Show help modal?

    # Backend Settings
    backend_type: str = "ollama"  # "ollama", "vllm", "tabbyapi" [DEPRECATED - use backend_id]
    backend_id: str = "ollama"  # NEW: Pure backend ID (synced with backend_type for compatibility)
    current_backend_label: str = "Ollama"  # NEW: Display label for current backend (synced with backend_id)
    backend_url: str = "http://localhost:11434"  # Default Ollama URL

    # Backend ID/Label Mapping (static - all possible backends)
    available_backends_dict: Dict[str, str] = {
        "ollama": "Ollama",
        "koboldcpp": "KoboldCPP",
        "tabbyapi": "TabbyAPI",
        "vllm": "vLLM"
    }

    # NOTE: Models loaded from settings.json first, fallback to config.py only if settings don't exist
    selected_model: str = ""  # Initialized in on_load() from settings.json or config.py [DEPRECATED]
    selected_model_id: str = ""  # NEW: Pure model ID (synced with selected_model)

    available_models: List[str] = []  # List of display labels [DEPRECATED]
    available_models_dict: Dict[str, str] = {}  # NEW: {model_id: display_label}

    vision_models_cache: List[str] = []  # Cached list of vision model IDs (populated by initialize_backend)
    available_vision_models_list: List[str] = []  # NEW: Display names for vision models (synced with vision_models_cache)

    # Automatik-LLM (for decision and query optimization)
    # NOTE: Loaded from settings.json first, fallback to config.py only if settings don't exist
    automatik_model: str = ""  # Initialized in on_load() from settings.json or config.py [DEPRECATED]
    automatik_model_id: str = ""  # NEW: Pure model ID (synced with automatik_model)

    # Vision-LLM (for image analysis/OCR - specialized for structured data extraction)
    # NOTE: Loaded from settings.json first, fallback to first available vision model
    vision_model: str = ""  # Initialized in on_load() from settings.json or auto-detect [DEPRECATED]
    vision_model_id: str = ""  # NEW: Pure model ID (synced with vision_model)

    # LLM Options
    temperature: float = 0.3  # Default: low temperature for factual responses
    temperature_mode: str = "auto"  # "auto" (Intent-Detection) | "manual" (user slider)
    sokrates_temperature: float = 0.5  # Sokrates temperature (manual mode only)
    sokrates_temperature_offset: float = 0.2  # Offset for auto mode: Sokrates = AIfred + offset
    salomo_temperature: float = 0.5  # Salomo temperature (manual mode only)
    salomo_temperature_offset: float = 0.1  # Offset for auto mode: Salomo = AIfred + offset
    num_ctx: int = 32768

    # Context Window Control (NOT saved in settings.json - reset on every start)
    num_ctx_mode: str = "auto"  # "auto" | "manual" (RoPE extension via calibrate_extended toggle)
    num_ctx_manual: int = 4096  # Manual value for AIfred (only if mode="manual") - Ollama default
    num_ctx_manual_sokrates: int = 4096  # Manual value for Sokrates (only if mode="manual")
    num_ctx_manual_salomo: int = 4096  # Manual value for Salomo (only if mode="manual")

    # Cached Model Metadata (to avoid repeated API calls)
    _automatik_model_context_limit: int = 0  # Cached context limit for automatik model

    # Research Settings
    research_mode: str = "automatik"  # "quick", "deep", "automatik", "none"
    research_mode_display: str = "✨ Automatik (KI entscheidet)"  # UI display value

    # Multi-Agent Settings - PERSISTENT (saved to settings.json)
    multi_agent_mode: str = "standard"  # "standard", "user_judge", "auto_consensus", "devils_advocate", "tribunal"
    max_debate_rounds: int = 3  # Maximum rounds for auto_consensus/tribunal (UI slider: 1-5)
    sokrates_model: str = ""  # Sokrates LLM model (empty = same as Main-LLM)
    sokrates_model_id: str = ""  # Pure model ID for Sokrates (without size suffix)
    salomo_model: str = ""  # Salomo LLM model (empty = same as Main-LLM)
    salomo_model_id: str = ""  # Pure model ID for Salomo (without size suffix)

    # Multi-Agent Runtime State (reset on session start)
    sokrates_critique: str = ""  # Current critique from Sokrates
    sokrates_pro_args: str = ""  # Pro arguments (Devil's Advocate)
    sokrates_contra_args: str = ""  # Contra arguments (Devil's Advocate)
    show_sokrates_panel: bool = False  # Show Sokrates UI panel?
    salomo_synthesis: str = ""  # Current synthesis/verdict from Salomo
    show_salomo_panel: bool = False  # Show Salomo UI panel?
    debate_round: int = 0  # Current debate round (for Auto-Consensus/Tribunal)
    debate_user_interjection: str = ""  # Queued user input during debate
    debate_in_progress: bool = False  # Signals active debate (for UI)

    # Internal streaming result (used by _stream_llm_with_ui helper)
    _stream_result: Dict[str, Any] = {}

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
    # The calculated VRAM limit from the last calculate_dynamic_num_ctx() call
    # Used for history compression (prevents recalculation)
    last_vram_limit: int = 0  # min(VRAM-Limit, Model-Limit) - practical maximum

    # User Settings
    user_name: str = ""  # User's name for personalized responses (optional)

    # TTS/STT Settings
    enable_tts: bool = False
    tts_voice: str = "Deutsch (Katja)"  # Voice selection (from VOICES dict)
    tts_speed: float = 1.0  # Speed multiplier (1.0 = normal, browser playback handles tempo)
    tts_engine: str = "Edge TTS (Cloud, best quality)"  # TTS engine selection
    tts_autoplay: bool = True  # Auto-play TTS audio after generation (user setting)
    tts_playback_rate: str = "1.25x"  # Browser playback rate (persisted)
    whisper_model_key: str = "small"  # Whisper model key (tiny/base/small/medium/large)
    # whisper_device removed - now configured in config.py (WHISPER_DEVICE)
    show_transcription: bool = False  # Show transcribed text for editing before sending
    _whisper_model = None  # Loaded WhisperModel instance (module-level, shared across sessions)
    tts_audio_path: str = ""  # Path to generated TTS audio file (TODO: UI player missing)
    tts_trigger_counter: int = 0  # Incremented to trigger TTS playback in frontend

    # Session Management
    session_id: str = ""

    # Session Persistence (Cookie-based device identification)
    device_id: str = ""  # Device ID from cookie (32 hex chars)
    session_restored: bool = False  # True if chat history was loaded from session
    _session_initialized: bool = False  # Guard against multiple session restore callbacks
    _on_load_running: bool = False  # Guard against multiple on_load() calls

    # Backend Status
    backend_healthy: bool = False
    backend_info: str = ""
    model_count: int = 0  # Number of available models (for localized UI display)
    backend_switching: bool = False  # True during backend switch (UI will be disabled)
    backend_initializing: bool = True  # True during initial initialization (shows Loading Spinner)
    vllm_restarting: bool = False  # True during vLLM restart (model switch/YaRN)
    koboldcpp_auto_restarting: bool = False  # True during KoboldCPP auto-restart after inactivity

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
    auto_refresh_enabled: bool = True  # For Debug Console + Chat History + AI Response Area

    # UI Language Settings
    ui_language: str = "de"  # "de" or "en" - for UI language

    # Mobile Detection (client-side via JavaScript)
    is_mobile: bool = False  # True if mobile device detected (User-Agent + Touch)
    _mobile_detection_done: bool = False  # Internal flag to prevent duplicate logging from Reflex hydration

    # Processing Progress (Automatik, Scraping, LLM)
    progress_active: bool = False
    progress_phase: str = ""  # "automatik", "scraping", "llm"
    progress_current: int = 0
    progress_total: int = 0
    progress_failed: int = 0  # Number of failed URLs

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
    gpu_count: int = 1
    gpu_vram_gb: int = 0
    available_backends: List[str] = ["ollama", "koboldcpp", "tabbyapi", "vllm"]  # Filtered by GPU compatibility (P40-compatible first)
    available_backends_list: List[str] = ["Ollama", "KoboldCPP", "TabbyAPI", "vLLM"]  # NEW: Display names (synced with available_backends)

    @rx.var
    def gpu_display_text(self) -> str:
        """
        Format GPU info for UI display.
        - Single GPU: "Tesla P40 (Compute 6.1, 24 GB)"
        - Multi-GPU: "2x Tesla P40 (Compute 6.1, 48 GB total)"
        """
        if not self.gpu_detected:
            return ""

        if self.gpu_count > 1:
            return f"{self.gpu_count}x {self.gpu_name} (Compute {self.gpu_compute_cap}, {self.gpu_vram_gb} GB total)"
        else:
            return f"{self.gpu_name} (Compute {self.gpu_compute_cap}, {self.gpu_vram_gb} GB)"

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

        # P40-compatible backends (GGUF)
        grouped.append("header_universal")  # Will be styled as header
        if "ollama" in self.available_backends:
            grouped.append("ollama")
        if "koboldcpp" in self.available_backends:
            grouped.append("koboldcpp")

        # Separator
        grouped.append("separator")

        # Modern GPU backends (FP16)
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
        Uses centralized config for consistency.
        """
        # Merge dropdown items with backend labels
        labels = {**config.BACKEND_DROPDOWN_ITEMS, **config.BACKEND_LABELS}
        return labels.get(backend_id, backend_id)

    def is_backend_item_selectable(self, backend_id: str) -> bool:
        """Check if backend item is selectable (not header/separator)"""
        return backend_id not in config.BACKEND_NON_SELECTABLE

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

    @rx.var
    def available_vision_models(self) -> List[str]:
        """
        Filter available_models to only include vision-capable models.
        Used for Vision-LLM dropdown.

        Returns display names (with size) for vision models.
        vision_models_cache stores IDs, we map them to display names.
        """
        # Map IDs to display names using available_models_dict
        return [self.available_models_dict.get(mid, mid) for mid in self.vision_models_cache
                if mid in self.available_models_dict]

    # ===== NEW: KEY-VALUE COMPUTED PROPERTIES FOR MOBILE NATIVE SELECTS =====

    # Backend Computed Properties
    @rx.var
    def backend_label(self) -> str:
        """Get display label for current backend (e.g., 'ollama' -> 'Ollama')"""
        return self.available_backends_dict.get(self.backend_id, self.backend_id)

    @rx.var
    def available_backends_display(self) -> List[str]:
        """Get list of backend display names (filtered by GPU compatibility)

        Returns display names like ["Ollama", "KoboldCPP"] for use in native select.
        Mirrors how available_models works for model dropdowns.
        """
        return [self.available_backends_dict.get(bid, bid) for bid in self.available_backends
                if bid in self.available_backends_dict]

    @rx.var
    def available_backend_ids(self) -> List[str]:
        """Get list of available backend IDs (filtered by GPU compatibility)"""
        # Return only backends that are compatible with current GPU
        return [bid for bid in self.available_backends_dict.keys()
                if bid in self.available_backends]

    @rx.var
    def available_backends_for_select(self) -> List[List[str]]:
        """Get filtered list of [id, label] pairs for native select (GPU-compatible only)

        Returns List[List[str]] instead of Dict because rx.foreach() works better with lists.
        Format: [["ollama", "Ollama"], ["koboldcpp", "KoboldCPP"]]
        """
        return [[bid, label] for bid, label in self.available_backends_dict.items()
                if bid in self.available_backends]

    # Model Computed Properties
    @rx.var
    def selected_model_label(self) -> str:
        """Get display label for selected model"""
        return self.available_models_dict.get(self.selected_model_id, self.selected_model_id)

    @rx.var
    def automatik_model_label(self) -> str:
        """Get display label for automatik model"""
        return self.available_models_dict.get(self.automatik_model_id, self.automatik_model_id)

    @rx.var
    def vision_model_label(self) -> str:
        """Get display label for vision model"""
        return self.available_models_dict.get(self.vision_model_id, self.vision_model_id)

    @rx.var
    def sokrates_model_label(self) -> str:
        """Get display label for Sokrates model"""
        if not self.sokrates_model_id:
            return ""  # Empty = use Main-LLM
        return self.available_models_dict.get(self.sokrates_model_id, self.sokrates_model_id)

    @rx.var(deps=["whisper_model_key", "ui_language"], auto_deps=False)
    def whisper_model_display(self) -> str:
        """Get localized display name for current Whisper model.

        Maps key (tiny/base/small/medium/large) to translated display name.
        """
        from .lib import TranslationManager
        # Translation map: key -> translation_key
        key_to_translation = {
            "tiny": "stt_model_tiny",
            "base": "stt_model_base",
            "small": "stt_model_small",
            "medium": "stt_model_medium",
            "large-v3": "stt_model_large",
            "large": "stt_model_large",  # Alias
        }
        translation_key = key_to_translation.get(self.whisper_model_key, "stt_model_small")
        return TranslationManager.get_text(translation_key, self.ui_language)

    @rx.var(deps=["ui_language"], auto_deps=False)
    def multi_agent_mode_options(self) -> List[List[str]]:
        """Get localized multi-agent mode options as [key, label] pairs for dropdown.

        Returns List[List[str]] for rx.foreach() compatibility.
        """
        from .lib import TranslationManager
        return [
            ["standard", TranslationManager.get_text("multi_agent_standard", self.ui_language)],
            ["user_judge", TranslationManager.get_text("multi_agent_user_judge", self.ui_language)],
            ["auto_consensus", TranslationManager.get_text("multi_agent_auto_consensus", self.ui_language)],
            ["devils_advocate", TranslationManager.get_text("multi_agent_devils_advocate", self.ui_language)],
            ["tribunal", TranslationManager.get_text("multi_agent_tribunal", self.ui_language)],
        ]

    @rx.var(deps=["ui_language", "multi_agent_mode"], auto_deps=False)
    def multi_agent_mode_info(self) -> str:
        """Get localized description for the currently selected multi-agent mode."""
        from .lib import TranslationManager
        info_key = f"multi_agent_info_{self.multi_agent_mode}"
        return TranslationManager.get_text(info_key, self.ui_language)

    @rx.var
    def available_models_for_select(self) -> List[List[str]]:
        """Get list of [id, label] pairs for native model select

        Returns List[List[str]] instead of Dict because rx.foreach() works better with lists.
        Format: [["qwen3:8b", "qwen3:8b (2.3 GB)"], ...]
        """
        return [[mid, label] for mid, label in self.available_models_dict.items()]

    @rx.var
    def available_vision_models_for_select(self) -> List[List[str]]:
        """Get list of [id, label] pairs for vision model select

        Returns List[List[str]] instead of Dict because rx.foreach() works better with lists.
        """
        return [[mid, self.available_models_dict[mid]]
                for mid in self.vision_models_cache
                if mid in self.available_models_dict]

    @rx.var(deps=["tts_engine"], auto_deps=False)
    def available_tts_voices(self) -> List[str]:
        """
        Returns list of available TTS voices for the current engine.
        Edge TTS, Piper and eSpeak have different voice sets.

        Note: Uses auto_deps=False with explicit deps to disable automatic
        dependency detection (Reflex cannot introspect module-level imports).
        """
        if "Piper" in self.tts_engine:
            return list(PIPER_VOICES.keys())
        elif "eSpeak" in self.tts_engine:
            return list(ESPEAK_VOICES.keys())
        else:
            return list(EDGE_TTS_VOICES.keys())

    @rx.var
    def chat_history_parsed(self) -> List[ChatMessageParsed]:
        """
        Parse chat_history and extract embedded failed_sources from AI messages
        and image URLs from user messages.

        Returns list of dicts:
        [
            {
                "user_msg": "..." (text without [IMG:...] markers),
                "ai_msg": "..." (cleaned, without comment),
                "failed_sources": [...] or [],
                "images": [...] or []  # List of data URLs for thumbnails
            }
        ]

        This computed property allows the UI to render failed_sources and image thumbnails per message.
        """
        import json
        import re

        result = []
        failed_sources_pattern = r'<!--FAILED_SOURCES:(\[.*?\])-->\n?'
        image_pattern = r'\[IMG:(data:image/[^;]+;base64,[^\]]+)\]'
        # Sokrates marker pattern: 🏛️[Mode]Content or 🏛️[Mode R2]Content
        sokrates_marker_pattern = r'^🏛️\[([^\]]+)\]'
        # AIfred marker pattern: 🎩[Mode]Content (e.g., 🎩[Überarbeitung R2])
        alfred_marker_pattern = r'^🎩\[([^\]]+)\]'
        # Salomo marker pattern: 👑[Mode]Content (e.g., 👑[Synthese R1] or 👑[Urteil])
        salomo_marker_pattern = r'^👑\[([^\]]+)\]'

        def extract_sokrates_info(ai_text: str) -> tuple[str, str]:
            """Extract mode and content from Sokrates marker.
            Returns (mode, content) or ("", ai_text) if no marker."""
            sokrates_match = re.match(sokrates_marker_pattern, ai_text)
            if sokrates_match:
                mode = sokrates_match.group(1)
                content = ai_text[sokrates_match.end():]
                return mode, content
            return "", ai_text

        def extract_alfred_info(ai_text: str) -> tuple[str, str]:
            """Extract mode and content from AIfred marker.
            Returns (mode, content) or ("", ai_text) if no marker."""
            alfred_match = re.match(alfred_marker_pattern, ai_text)
            if alfred_match:
                mode = alfred_match.group(1)
                content = ai_text[alfred_match.end():]
                return mode, content
            return "", ai_text

        def extract_salomo_info(ai_text: str) -> tuple[str, str]:
            """Extract mode and content from Salomo marker.
            Returns (mode, content) or ("", ai_text) if no marker."""
            salomo_match = re.match(salomo_marker_pattern, ai_text)
            if salomo_match:
                mode = salomo_match.group(1)
                content = ai_text[salomo_match.end():]
                return mode, content
            return "", ai_text

        for user_msg, ai_msg in self.chat_history:
            # Extract images from user message
            images = re.findall(image_pattern, user_msg)
            # Remove [IMG:...] markers from user message for clean display
            clean_user_msg = re.sub(r'\[IMG:[^\]]*\]', '', user_msg).strip()

            # Extract failed sources from AI message
            match = re.search(failed_sources_pattern, ai_msg, re.DOTALL)

            if match:
                try:
                    failed_sources = json.loads(match.group(1))
                    clean_ai_msg = re.sub(failed_sources_pattern, '', ai_msg, count=1)
                    sokrates_mode, sokrates_content = extract_sokrates_info(clean_ai_msg)
                    alfred_mode, alfred_content = extract_alfred_info(clean_ai_msg)
                    salomo_mode, salomo_content = extract_salomo_info(clean_ai_msg)
                    result.append({
                        "user_msg": clean_user_msg,
                        "ai_msg": clean_ai_msg,
                        "failed_sources": failed_sources,
                        "images": images,
                        "sokrates_mode": sokrates_mode,
                        "sokrates_content": sokrates_content,
                        "alfred_mode": alfred_mode,
                        "alfred_content": alfred_content,
                        "salomo_mode": salomo_mode,
                        "salomo_content": salomo_content
                    })
                except json.JSONDecodeError:
                    sokrates_mode, sokrates_content = extract_sokrates_info(ai_msg)
                    alfred_mode, alfred_content = extract_alfred_info(ai_msg)
                    salomo_mode, salomo_content = extract_salomo_info(ai_msg)
                    result.append({
                        "user_msg": clean_user_msg,
                        "ai_msg": ai_msg,
                        "failed_sources": [],
                        "images": images,
                        "sokrates_mode": sokrates_mode,
                        "sokrates_content": sokrates_content,
                        "alfred_mode": alfred_mode,
                        "alfred_content": alfred_content,
                        "salomo_mode": salomo_mode,
                        "salomo_content": salomo_content
                    })
            else:
                sokrates_mode, sokrates_content = extract_sokrates_info(ai_msg)
                alfred_mode, alfred_content = extract_alfred_info(ai_msg)
                salomo_mode, salomo_content = extract_salomo_info(ai_msg)
                result.append({
                    "user_msg": clean_user_msg,
                    "ai_msg": ai_msg,
                    "failed_sources": [],
                    "images": images,
                    "sokrates_mode": sokrates_mode,
                    "sokrates_content": sokrates_content,
                    "alfred_mode": alfred_mode,
                    "alfred_content": alfred_content,
                    "salomo_mode": salomo_mode,
                    "salomo_content": salomo_content
                })

        return result

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

            # Initialize Whisper STT Model (once per server)
            from .lib.config import DEFAULT_SETTINGS
            whisper_model_key = str(DEFAULT_SETTINGS.get("whisper_model", "small"))
            # Extract key if old format with display name
            if "(" in whisper_model_key:
                whisper_model_key = whisper_model_key.split("(")[0].strip()
            initialize_whisper_model(whisper_model_key)

            # GPU Detection (once per server)
            log_message("🔍 Detecting GPU capabilities...")
            try:
                from .lib.gpu_detection import detect_gpu
                gpu_info = detect_gpu()
                if gpu_info:
                    _global_backend_state["gpu_info"] = gpu_info

                    # Format GPU info with count and VRAM (nominal specs)
                    # Uses centralized round_to_nominal_vram from gpu_monitor.py
                    vram_per_gpu_gb = round_to_nominal_vram(gpu_info.vram_mb)
                    total_vram_gb = vram_per_gpu_gb * gpu_info.gpu_count

                    if gpu_info.gpu_count > 1:
                        # Multi-GPU: "2x Tesla P40 (Compute 6.1, 48 GB total)"
                        log_message(f"✅ GPU: {gpu_info.gpu_count}x {gpu_info.name} (Compute {gpu_info.compute_capability}, {total_vram_gb} GB total)")
                    else:
                        # Single GPU: "Tesla P40 (Compute 6.1, 24 GB)"
                        log_message(f"✅ GPU: {gpu_info.name} (Compute {gpu_info.compute_capability}, {vram_per_gpu_gb} GB)")

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
        # Guard against multiple parallel on_load() calls (ASGI race condition)
        if self._on_load_running:
            print("⏭️ on_load already running, skipping duplicate call")
            return
        self._on_load_running = True

        if not self._backend_initialized:
            print("📱 Initializing session...")

            # Initialize global UI locale for number formatting
            from .lib.formatting import set_ui_locale
            set_ui_locale(self.ui_language)

            # Load saved settings
            from .lib.settings import load_settings
            saved_settings = load_settings()

            if saved_settings:
                # Use saved settings
                self.backend_type = saved_settings.get("backend_type", self.backend_type)
                self.backend_id = self.backend_type  # Sync ID with type
                self.current_backend_label = self.available_backends_dict.get(self.backend_id, self.backend_id)
                self.research_mode = saved_settings.get("research_mode", self.research_mode)

                # Update research_mode_display to match loaded research_mode
                from .lib import TranslationManager
                self.research_mode_display = TranslationManager.get_research_mode_display(self.research_mode, self.ui_language)

                self.temperature = saved_settings.get("temperature", self.temperature)
                self.temperature_mode = saved_settings.get("temperature_mode", self.temperature_mode)
                self.sokrates_temperature = saved_settings.get("sokrates_temperature", self.sokrates_temperature)
                self.sokrates_temperature_offset = saved_settings.get("sokrates_temperature_offset", self.sokrates_temperature_offset)
                self.salomo_temperature = saved_settings.get("salomo_temperature", self.salomo_temperature)
                self.salomo_temperature_offset = saved_settings.get("salomo_temperature_offset", self.salomo_temperature_offset)
                self.enable_thinking = saved_settings.get("enable_thinking", self.enable_thinking)

                # Load UI language and update global locale
                saved_ui_lang = saved_settings.get("ui_language", self.ui_language)
                if saved_ui_lang in ["de", "en"]:
                    self.ui_language = saved_ui_lang
                    set_ui_locale(saved_ui_lang)

                # Load user name
                self.user_name = saved_settings.get("user_name", self.user_name)
                # Sync to prompt_loader for automatic injection into system prompts
                from .lib.prompt_loader import set_user_name
                set_user_name(self.user_name)

                # Load TTS/STT Settings
                self.enable_tts = saved_settings.get("enable_tts", self.enable_tts)
                # Note: tts_speed no longer loaded - generation always at 1.0
                self.tts_engine = saved_settings.get("tts_engine", self.tts_engine)
                self.tts_autoplay = saved_settings.get("tts_autoplay", self.tts_autoplay)
                self.tts_playback_rate = saved_settings.get("tts_playback_rate", self.tts_playback_rate)
                # Load whisper model key (backwards compatible: extract key from old display name)
                saved_whisper = saved_settings.get("whisper_model", self.whisper_model_key)
                # Extract key from display name if old format (e.g., "small (466MB, ...)" -> "small")
                if "(" in saved_whisper:
                    saved_whisper = saved_whisper.split("(")[0].strip()
                self.whisper_model_key = saved_whisper
                # whisper_device removed - now in config.py (backwards compatibility: ignore old saved value)
                self.show_transcription = saved_settings.get("show_transcription", self.show_transcription)

                # Load TTS voice: Try engine-specific saved voice first, fallback to legacy "voice" key
                user_voices = saved_settings.get("tts_voices_per_language", {})
                engine_key = self._get_engine_key()
                saved_voice = user_voices.get(engine_key, {}).get(self.ui_language)
                if saved_voice:
                    self.tts_voice = saved_voice
                else:
                    self.tts_voice = saved_settings.get("voice", self.tts_voice)  # Legacy key

                # Load vLLM YaRN Settings (only enable/disable, factor always starts at 1.0)
                self.enable_yarn = saved_settings.get("enable_yarn", self.enable_yarn)
                # yarn_factor is NOT loaded - always starts at 1.0, system calibrates maximum
                self.yarn_factor = 1.0
                self.yarn_factor_input = "1.0"
                # NOTE: vllm_max_tokens and vllm_native_context are NEVER loaded from settings!
                # They are calculated dynamically on every vLLM startup based on VRAM availability

                # Load Multi-Agent Settings
                self.multi_agent_mode = saved_settings.get("multi_agent_mode", self.multi_agent_mode)
                self.max_debate_rounds = saved_settings.get("max_debate_rounds", self.max_debate_rounds)
                # Load Sokrates model (pure ID, display name set after models load)
                self.sokrates_model_id = saved_settings.get("sokrates_model", "")
                self.sokrates_model = self.sokrates_model_id  # Will be updated with display name after models load

                # Load Salomo model (pure ID, display name set after models load)
                self.salomo_model_id = saved_settings.get("salomo_model", "")
                self.salomo_model = self.salomo_model_id  # Will be updated with display name after models load
                self.salomo_temperature = saved_settings.get("salomo_temperature", self.salomo_temperature)
                self.salomo_temperature_offset = saved_settings.get("salomo_temperature_offset", self.salomo_temperature_offset)

                # Load per-backend models (if available)
                from .lib.conversation_handler import extract_model_name
                backend_models = saved_settings.get("backend_models", {})
                if self.backend_id in backend_models:
                    # NEW: Load pure IDs (backward compatible - extract from old display format)
                    selected_raw = backend_models[self.backend_id].get("selected_model", "")
                    automatik_raw = backend_models[self.backend_id].get("automatik_model", "")
                    vision_raw = backend_models[self.backend_id].get("vision_model", "")

                    # Extract pure IDs (handles both old "model (size)" and new "model" formats)
                    self.selected_model_id = extract_model_name(selected_raw)
                    self.automatik_model_id = extract_model_name(automatik_raw)
                    self.vision_model_id = extract_model_name(vision_raw)

                    # Load per-model RoPE 2x toggle from cache
                    if self.backend_id == "ollama" and self.selected_model_id:
                        from .lib.model_vram_cache import get_use_extended_for_model
                        self.calibrate_extended = get_use_extended_for_model(self.selected_model_id)

                    # Sync deprecated variables (will be populated later after models load)
                    self.selected_model = selected_raw
                    self.automatik_model = automatik_raw
                    self.vision_model = vision_raw
                else:
                    # Fallback: Use old-style global model settings
                    selected_raw = saved_settings.get("selected_model", "")
                    automatik_raw = saved_settings.get("automatik_model", "")
                    vision_raw = saved_settings.get("vision_model", "")

                    self.selected_model_id = extract_model_name(selected_raw)
                    self.automatik_model_id = extract_model_name(automatik_raw)
                    self.vision_model_id = extract_model_name(vision_raw)

                    # Load per-model RoPE 2x toggle from cache
                    if self.backend_id == "ollama" and self.selected_model_id:
                        from .lib.model_vram_cache import get_use_extended_for_model
                        self.calibrate_extended = get_use_extended_for_model(self.selected_model_id)

                    self.selected_model = selected_raw
                    self.automatik_model = automatik_raw
                    self.vision_model = vision_raw

                self.add_debug(f"⚙️ Settings loaded (backend: {self.backend_type})")

                # Send TTS playback rate to JavaScript (after settings loaded)
                # Use setTimeout to ensure custom.js is loaded first
                rate_value = self.tts_playback_rate.replace("x", "")
                yield rx.call_script(f"setTimeout(() => {{ if (typeof setTtsPlaybackRate === 'function') setTtsPlaybackRate({rate_value}); }}, 100)")

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

            if not self.vision_model:
                self.vision_model = backend_defaults.get("vision_model", "")
                if self.vision_model:
                    self.add_debug(f"⚙️ Using default vision_model from config.py: {self.vision_model}")
                else:
                    self.add_debug("ℹ️ No vision_model configured - will auto-detect first available vision model")

            # vLLM and TabbyAPI can only load ONE model at a time
            # Ensure automatik_model = selected_model for these backends
            if self.backend_type in ["vllm", "tabbyapi"]:
                if self.automatik_model != self.selected_model:
                    self.add_debug(f"⚠️ {self.backend_type} can only load one model - using {self.selected_model} for both Main and Automatik")
                    self.automatik_model = self.selected_model

            # Generate internal session ID (for Reflex, not displayed)
            if not self.session_id:
                self.session_id = str(uuid.uuid4())

            # Restore GPU info from global state
            gpu_info = _global_backend_state.get("gpu_info")
            if gpu_info:
                self.gpu_detected = True
                self.gpu_name = gpu_info.name
                self.gpu_compute_cap = gpu_info.compute_capability
                self.gpu_warnings = gpu_info.warnings
                self.gpu_count = gpu_info.gpu_count

                # Calculate nominal VRAM (round up to marketing specs)
                # Uses centralized round_to_nominal_vram from gpu_monitor.py
                vram_per_gpu_gb = round_to_nominal_vram(gpu_info.vram_mb)
                self.gpu_vram_gb = vram_per_gpu_gb * gpu_info.gpu_count

                # Show GPU info in debug console
                if self.gpu_count > 1:
                    self.add_debug(f"🎮 GPU: {self.gpu_count}x {self.gpu_name} (Compute {self.gpu_compute_cap}, {self.gpu_vram_gb} GB total)")
                else:
                    self.add_debug(f"🎮 GPU: {self.gpu_name} (Compute {self.gpu_compute_cap}, {self.gpu_vram_gb} GB)")

                # Filter available backends based on GPU compatibility
                # Only show backends that are actually compatible with the GPU
                if gpu_info.recommended_backends:
                    self.available_backends = gpu_info.recommended_backends
                    # Sync display names list
                    self.available_backends_list = [
                        self.available_backends_dict.get(bid, bid)
                        for bid in self.available_backends
                    ]
                    # Store in global state for fast-path restore
                    _global_backend_state["available_backends"] = self.available_backends
                    _global_backend_state["available_backends_list"] = self.available_backends_list
                    self.add_debug(f"✅ Compatible backends: {', '.join(self.available_backends)}")

                    # If current backend is not compatible, switch to first available
                    if self.backend_type not in self.available_backends:
                        old_backend = self.backend_type
                        self.backend_type = self.available_backends[0]
                        self.backend_id = self.backend_type  # Sync ID with type
                        self.add_debug(f"⚠️ Backend '{old_backend}' not compatible with {gpu_info.name}")
                        self.add_debug(f"🔄 Auto-switched to '{self.backend_type}'")

                    # ALWAYS sync current_backend_label (fixes closed dropdown display)
                    self.current_backend_label = self.available_backends_dict.get(self.backend_id, self.backend_id)
                    _global_backend_state["current_backend_label"] = self.current_backend_label

            # Initialize backend (or restore from global state)
            self.add_debug("🔧 Initializing backend...")
            backend_init_success = False
            was_fast_path = False
            try:
                was_fast_path = await self.initialize_backend()
                backend_init_success = True
            except Exception as e:
                self.add_debug(f"❌ Backend init failed: {e}")
                log_message(f"❌ Backend init failed: {e}")
                import traceback
                log_message(traceback.format_exc())

            # Only show "Backend ready" for SLOW PATH (FAST PATH already logged its own message)
            if backend_init_success and not was_fast_path:
                self.add_debug("✅ Backend ready")

            # Add separator after backend ready (both paths)
            if backend_init_success:
                from aifred.lib.logging_utils import console_separator
                console_separator()  # File log
                self.debug_messages.append("────────────────────")  # UI

            self._backend_initialized = True
            print("✅ Session initialization complete")

            # Session Persistence: Read device_id from cookie (async callback)
            # AFTER Backend-Init so chat history restore doesn't collide with loading
            if not self._session_initialized:
                from .lib.browser_storage import get_device_id_script
                # First attempt: immediate
                yield rx.call_script(
                    get_device_id_script(),
                    callback=AIState.handle_device_id_loaded
                )
                # Retry after 2 seconds (in case first callback didn't get through due to race condition)
                # Guard _session_initialized prevents duplicate processing
                yield rx.call_script(
                    get_device_id_script(delay_ms=2000),
                    callback=AIState.handle_device_id_loaded
                )

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
        # Also check that vision detection is complete (prevents race condition)
        init_complete = _global_backend_state.get("_init_complete", False)

        if is_same_backend and _global_backend_state["available_models"] and init_complete:
            # FAST PATH: Restore from global state (page reload case)
            print(f"⚡ Backend '{self.backend_type}' already initialized, restoring from global state...")

            # Restore backend URL and available models list from global state
            self.backend_url = _global_backend_state["backend_url"]
            self.available_models = _global_backend_state["available_models"]
            self.available_models_dict = _global_backend_state.get("available_models_dict", {})  # CRITICAL for vision dropdown!
            self.vision_models_cache = _global_backend_state.get("vision_models_cache", [])
            self.available_vision_models_list = _global_backend_state.get("available_vision_models_list", [])

            # Restore backend dropdown data
            self.available_backends = _global_backend_state.get("available_backends", self.available_backends)
            self.available_backends_list = _global_backend_state.get("available_backends_list", self.available_backends_list)
            self.current_backend_label = _global_backend_state.get("current_backend_label",
                self.available_backends_dict.get(self.backend_type, self.backend_type))

            # FIX: Respect settings.json model selection instead of blindly using global state!
            # The model IDs were already loaded from settings.json in on_load() before this call.
            # We only need to validate they exist and sync the display labels.

            # Validate and sync selected_model (use settings, not global state)
            if self.selected_model_id and self.selected_model_id in self.available_models_dict:
                self.selected_model = self.available_models_dict[self.selected_model_id]
            elif _global_backend_state.get("selected_model_id") in self.available_models_dict:
                # Fallback to global state if settings model not found
                self.selected_model_id = _global_backend_state["selected_model_id"]
                self.selected_model = self.available_models_dict[self.selected_model_id]
            else:
                # Last resort: first available model
                first_id = next(iter(self.available_models_dict.keys()), "")
                self.selected_model_id = first_id
                self.selected_model = self.available_models_dict.get(first_id, first_id)

            # Validate and sync automatik_model (use settings, not global state)
            if self.automatik_model_id and self.automatik_model_id in self.available_models_dict:
                self.automatik_model = self.available_models_dict[self.automatik_model_id]
            elif _global_backend_state.get("automatik_model_id") in self.available_models_dict:
                self.automatik_model_id = _global_backend_state["automatik_model_id"]
                self.automatik_model = self.available_models_dict[self.automatik_model_id]
            else:
                first_id = next(iter(self.available_models_dict.keys()), "")
                self.automatik_model_id = first_id
                self.automatik_model = self.available_models_dict.get(first_id, first_id)

            # Validate and sync vision_model (use settings, not global state)
            if self.vision_model_id and self.vision_model_id in self.vision_models_cache:
                self.vision_model = self.available_models_dict.get(self.vision_model_id, self.vision_model_id)
            elif _global_backend_state.get("vision_model_id") in self.vision_models_cache:
                self.vision_model_id = _global_backend_state["vision_model_id"]
                self.vision_model = self.available_models_dict.get(self.vision_model_id, self.vision_model_id)
            elif self.vision_models_cache:
                # Fallback to first vision model
                self.vision_model_id = self.vision_models_cache[0]
                self.vision_model = self.available_models_dict.get(self.vision_model_id, self.vision_model_id)

            # Validate and sync sokrates_model (use settings, not global state)
            # sokrates_model can be empty (= use Main-LLM)
            if self.sokrates_model_id and self.sokrates_model_id in self.available_models_dict:
                self.sokrates_model = self.available_models_dict[self.sokrates_model_id]
            elif self.sokrates_model_id:
                # Model ID was set but model not found - clear it
                self.sokrates_model_id = ""
                self.sokrates_model = ""

            # Validate and sync salomo_model (use settings, not global state)
            # salomo_model can be empty (= use Main-LLM)
            if self.salomo_model_id and self.salomo_model_id in self.available_models_dict:
                self.salomo_model = self.available_models_dict[self.salomo_model_id]
            elif self.salomo_model_id:
                # Model ID was set but model not found - clear it
                self.salomo_model_id = ""
                self.salomo_model = ""

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
            self.model_count = len(self.available_models)
            self.backend_info = f"{self.model_count} models"
            self.add_debug(f"✅ Backend ready (restored: {self.model_count} models)")

            # Hide loading spinner (fast path = already initialized)
            self.backend_initializing = False

            return True  # FAST PATH - caller should NOT add another "Backend ready"

        # SLOW PATH: Full initialization (first time or backend switch)
        print(f"🔧 Full backend initialization for '{self.backend_type}'...")

        try:
            # Update URL based on backend type (from centralized config)
            self.backend_url = config.BACKEND_URLS.get(self.backend_type, "http://localhost:11434")

            # add_debug() already logs to file, so we only need one call
            self.add_debug(f"🔧 Creating backend: {self.backend_type}")
            # Detailed info only in log file (not in UI)
            log_message(f"   URL: {self.backend_url}")

            # SKIP health check - causes async deadlock in on_load context!
            # Assume backend is healthy and proceed
            self.backend_healthy = True
            self.backend_info = f"{self.backend_type} initializing..."
            self.add_debug(f"⚡ Backend: {self.backend_type} (skip health check)")

            # Load models SYNCHRONOUSLY via httpx (no async deadlock!)
            import httpx
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

                        # Filter models by reading config.json and calculate sizes
                        unsorted_dict = {}
                        for model_dir in model_dirs:
                            if is_backend_compatible(model_dir, self.backend_type):
                                model_id = model_dir.name.replace("models--", "").replace("--", "/", 1)

                                # Calculate size using blob-based calculation (avoids counting duplicates)
                                try:
                                    from .lib.vllm_manager import get_model_size_bytes
                                    total_size = get_model_size_bytes(model_id)
                                    size_gb = total_size / (1024**3)
                                    unsorted_dict[model_id] = f"{model_id} ({size_gb:.1f} GB)"
                                except Exception:
                                    # Fallback: show without size if calculation fails
                                    unsorted_dict[model_id] = model_id

                        # Sort by model family, then by size
                        self.available_models_dict = sort_models_grouped(unsorted_dict)
                        # Keep list for compatibility (DEPRECATED)
                        self.available_models = list(self.available_models_dict.values())

                        self.add_debug(f"📂 Found {len(self.available_models)} {self.backend_type}-compatible models ({len(model_dirs)} total in cache)")
                    else:
                        self.available_models_dict = {}
                        self.available_models = []
                        self.add_debug("⚠️ HuggingFace cache not found")

                elif self.backend_type == "koboldcpp":
                    # KoboldCPP: Discover GGUF models from filesystem
                    from aifred.lib.gguf_utils import find_all_gguf_models

                    self.add_debug("🔍 Searching for GGUF models on filesystem...")

                    try:
                        gguf_models = find_all_gguf_models()

                        if gguf_models:
                            # Build dict: {model_id: display_label}
                            unsorted_dict = {
                                m.name: f"{m.name} ({m.size_gb:.1f} GB)"
                                for m in gguf_models
                            }
                            # Sort by model family, then by size
                            self.available_models_dict = sort_models_grouped(unsorted_dict)
                            # Keep list for compatibility (DEPRECATED)
                            self.available_models = list(self.available_models_dict.values())

                            # Store full model info in global state (keyed by pure name)
                            _global_backend_state["gguf_models"] = {m.name: m for m in gguf_models}

                            # Select first model by default
                            if not self.selected_model or self.selected_model not in self.available_models:
                                self.selected_model = gguf_models[0].name

                            # KoboldCPP can only load ONE model - Automatik uses same model
                            self.automatik_model = self.selected_model
                        else:
                            self.available_models_dict = {}
                            self.available_models = []
                            self.add_debug("⚠️ No GGUF models found")
                            self.add_debug("💡 Download GGUF models:")
                            self.add_debug("   huggingface-cli download bartowski/Qwen3-30B-Instruct-2507-GGUF \\")
                            self.add_debug("       Qwen3-30B-Instruct-2507-Q4_K_M.gguf --local-dir ~/models/")

                    except Exception as e:
                        self.available_models_dict = {}
                        self.available_models = []
                        self.add_debug(f"❌ GGUF discovery failed: {e}")
                        import traceback
                        self.add_debug(f"   {traceback.format_exc()}")

                else:
                    # Ollama: Query server API
                    endpoint = f'{self.backend_url}/api/tags'

                    # Synchronous httpx call to get model list (replaces subprocess+curl)
                    try:
                        response = httpx.get(endpoint, timeout=5.0)
                        if response.status_code == 200:
                            data = response.json()
                            # Build dict: {model_id: display_label}
                            unsorted_dict = {
                                m['name']: f"{m['name']} ({m['size'] / (1024**3):.1f} GB)"
                                for m in data.get("models", [])
                            }
                            # Sort by model family, then by size
                            self.available_models_dict = sort_models_grouped(unsorted_dict)
                            # Keep list for compatibility (DEPRECATED)
                            self.available_models = list(self.available_models_dict.values())
                        else:
                            self.available_models_dict = {}
                            self.available_models = []
                    except httpx.RequestError:
                        self.available_models_dict = {}
                        self.available_models = []

                # NEW: Sync deprecated display variables with IDs using dict lookup
                # No more extract_model_name() needed - direct dict access!

                # Validate and sync selected_model
                if self.selected_model_id in self.available_models_dict:
                    self.selected_model = self.available_models_dict[self.selected_model_id]
                elif self.available_models_dict:
                    # Fallback to first available model
                    first_id = next(iter(self.available_models_dict.keys()))
                    log_message(f"⚠️ Configured model '{self.selected_model_id}' not found, using '{first_id}'")
                    self.selected_model_id = first_id
                    self.selected_model = self.available_models_dict[first_id]

                # Validate and sync automatik_model
                if self.automatik_model_id in self.available_models_dict:
                    self.automatik_model = self.available_models_dict[self.automatik_model_id]
                elif self.available_models_dict:
                    # Fallback to first available model
                    first_id = next(iter(self.available_models_dict.keys()))
                    log_message(f"⚠️ Configured automatik model '{self.automatik_model_id}' not found, using '{first_id}'")
                    self.automatik_model_id = first_id
                    self.automatik_model = self.available_models_dict[first_id]

                # Validate and sync sokrates_model (can be empty = use Main-LLM)
                if self.sokrates_model_id and self.sokrates_model_id in self.available_models_dict:
                    self.sokrates_model = self.available_models_dict[self.sokrates_model_id]
                elif self.sokrates_model_id:
                    # Model ID was set but model not found - clear it
                    log_message(f"⚠️ Configured sokrates model '{self.sokrates_model_id}' not found, clearing")
                    self.sokrates_model_id = ""
                    self.sokrates_model = ""

                # Validate and sync salomo_model (can be empty = use Main-LLM)
                if self.salomo_model_id and self.salomo_model_id in self.available_models_dict:
                    self.salomo_model = self.available_models_dict[self.salomo_model_id]
                elif self.salomo_model_id:
                    # Model ID was set but model not found - clear it
                    log_message(f"⚠️ Configured salomo model '{self.salomo_model_id}' not found, clearing")
                    self.salomo_model_id = ""
                    self.salomo_model = ""

                self.model_count = len(self.available_models)
                self.backend_info = f"{self.model_count} models"
                self.backend_healthy = True

                # For backends without model switching (vLLM, KoboldCPP, TabbyAPI), show only Main model
                if self.backend_type.lower() in ["vllm", "koboldcpp", "tabbyapi"]:
                    # Compact format for Mobile: Multi-line with indentation
                    self.add_debug(f"✅ {len(self.available_models)} models available")
                    self.add_debug(f"   Main: {self.selected_model}")
                else:
                    # Compact format for Mobile: Multi-line with indentation
                    self.add_debug(f"✅ {len(self.available_models)} models available")
                    self.add_debug(f"   Main: {self.selected_model}")
                    self.add_debug(f"   Automatik: {self.automatik_model}")
                    # Show Sokrates model if multi-agent mode is active
                    if self.multi_agent_mode != "standard" and self.sokrates_model_id:
                        self.add_debug(f"   Sokrates: {self.sokrates_model}")

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
            _global_backend_state["selected_model_id"] = self.selected_model_id
            _global_backend_state["automatik_model"] = self.automatik_model
            _global_backend_state["automatik_model_id"] = self.automatik_model_id
            _global_backend_state["available_models"] = self.available_models
            _global_backend_state["available_models_dict"] = self.available_models_dict  # CRITICAL for vision dropdown!
            _global_backend_state["current_backend_label"] = self.current_backend_label

            # === DETECT VISION MODELS (metadata-based) ===
            self.add_debug("🔍 Detecting vision-capable models...")
            await self._detect_vision_models()

            # Start vLLM process if backend is vLLM
            if self.backend_type == "vllm":
                await self._start_vllm_server()

            # Start KoboldCPP process if backend is koboldcpp
            if self.backend_type == "koboldcpp":
                await self._start_koboldcpp_server()

            # Preload Automatik-LLM with SMALL context (Ollama only)
            # CRITICAL: Models like Qwen3:4B have 262K default context!
            # Without preloading with explicit num_ctx, Ollama allocates HUGE KV-Cache.
            # Main-LLM is loaded on-demand with proper context calculation.
            if self.backend_type == "ollama" and self.automatik_model_id:
                from .lib.context_manager import prepare_automatik_llm
                from aifred.backends import BackendFactory
                auto_backend = BackendFactory.create(self.backend_type, base_url=self.backend_url)
                async for item in prepare_automatik_llm(
                    backend=auto_backend,
                    model_name=self.automatik_model_id,
                    backend_type=self.backend_type
                ):
                    if item.get("type") == "debug":
                        self.add_debug(item["message"])
                    # Ignore result - we don't need to store it

            # Store in global state for future page reloads
            # vllm_manager and koboldcpp_manager are already stored in _global_backend_state by their start functions
            _global_backend_state["_init_complete"] = True  # Mark init complete (enables fast-path for page reloads)
            print(f"✅ Backend '{self.backend_type}' fully initialized and stored in global state")

            # Mark initialization as complete (hide loading spinner)
            self.backend_initializing = False

            return False  # SLOW PATH - caller should add "Backend ready"

        except Exception as e:
            self.backend_healthy = False
            self.backend_info = f"Error: {str(e)}"
            self.add_debug(f"❌ Backend initialization failed: {e}")
            self.backend_initializing = False  # Hide spinner even on error
            return False  # Error case - let caller handle

    def _save_settings(self):
        """Save current settings to file (per-backend models)"""
        from .lib.settings import save_settings, load_settings

        # Load existing settings to preserve other backends
        existing = load_settings() or {}
        backend_models = existing.get("backend_models", {})

        # Only update backend models if we have valid model IDs
        # This prevents overwriting with empty strings during early initialization
        # (e.g., when UI language is switched before backend is fully loaded)
        if self.selected_model_id and self.backend_id:
            backend_models[self.backend_id] = {
                "selected_model": self.selected_model_id,  # Pure ID: "qwen3:8b"
                "automatik_model": self.automatik_model_id,
                "vision_model": self.vision_model_id,
            }

        settings = {
            "backend_type": self.backend_type,
            "research_mode": self.research_mode,
            "temperature": self.temperature,
            "temperature_mode": self.temperature_mode,
            "sokrates_temperature": self.sokrates_temperature,
            "sokrates_temperature_offset": self.sokrates_temperature_offset,
            "enable_thinking": self.enable_thinking,
            "ui_language": self.ui_language,  # UI language (de/en)
            "user_name": self.user_name,  # User's name for personalized responses
            "backend_models": backend_models,  # Merged: preserves all backends
            # Multi-Agent Settings
            "multi_agent_mode": self.multi_agent_mode,
            "max_debate_rounds": self.max_debate_rounds,
            "sokrates_model": self.sokrates_model_id,  # Save pure ID
            "salomo_model": self.salomo_model_id,  # Save pure ID
            "salomo_temperature": self.salomo_temperature,
            "salomo_temperature_offset": self.salomo_temperature_offset,
            # vLLM YaRN Settings (only enable/disable, factor is calculated dynamically)
            "enable_yarn": self.enable_yarn,
            # NOTE: yarn_factor is NOT saved - always starts at 1.0, system calibrates maximum
            # NOTE: vllm_max_tokens and vllm_native_context are NEVER saved!
            # They are calculated dynamically on every vLLM startup based on VRAM
            # TTS/STT Settings
            "enable_tts": self.enable_tts,
            "voice": self.tts_voice,  # Legacy key name for backward compatibility
            # Note: tts_speed removed - generation always at 1.0, tempo via tts_playback_rate
            "tts_engine": self.tts_engine,
            "tts_autoplay": self.tts_autoplay,
            "tts_playback_rate": self.tts_playback_rate,
            "whisper_model": self.whisper_model_key,  # Save only key (tiny/base/small/medium/large)
            # whisper_device removed - now in config.py
            "show_transcription": self.show_transcription,
            # Language-specific TTS voices (user preferences per engine/language)
            "tts_voices_per_language": existing.get("tts_voices_per_language", {}),
        }
        # Update tts_voices_per_language with current voice selection
        engine_key = self._get_engine_key()
        lang = self.ui_language
        if "tts_voices_per_language" not in settings:
            settings["tts_voices_per_language"] = {}
        if engine_key not in settings["tts_voices_per_language"]:
            settings["tts_voices_per_language"][engine_key] = {}
        settings["tts_voices_per_language"][engine_key][lang] = self.tts_voice
        save_settings(settings)

    def _show_model_calibration_info(self, model_id: str):
        """Show calibration info for Ollama models in debug console.

        Displays calibrated context values (Native and/or RoPE 2x) or a warning
        if the model hasn't been calibrated yet.
        """
        if self.backend_id != "ollama" or not model_id:
            return

        from .lib.model_vram_cache import get_ollama_calibrated_max_context
        from .lib.formatting import format_number

        native_ctx = get_ollama_calibrated_max_context(model_id, extended=False)
        extended_ctx = get_ollama_calibrated_max_context(model_id, extended=True)

        if native_ctx is not None or extended_ctx is not None:
            # Show calibrated values
            parts = []
            if native_ctx is not None:
                parts.append(f"Native: {format_number(native_ctx)}")
            if extended_ctx is not None:
                parts.append(f"RoPE 2x: {format_number(extended_ctx)}")
            self.add_debug(f"   🎯 Calibrated: {', '.join(parts)}")
        else:
            # Not calibrated - show warning
            self.add_debug("   ⚠️ Not calibrated - please run calibration for optimal context")

    async def switch_backend_by_label(self, label: str):
        """Switch backend using display label (for native mobile select)

        Maps display label like "Ollama" to ID like "ollama" and calls switch_backend.
        """
        # Reverse lookup: label -> ID
        label_to_id = {v: k for k, v in self.available_backends_dict.items()}
        backend_id = label_to_id.get(label, label.lower())  # Fallback to lowercase
        async for _ in self.switch_backend(backend_id):
            yield

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
            target_vision_model = None

            if new_backend in backend_models:
                # Use saved models from backend_models.json
                saved_models = backend_models[new_backend]
                target_main_model = saved_models.get("selected_model")
                target_auto_model = saved_models.get("automatik_model")
                target_vision_model = saved_models.get("vision_model")
                self.add_debug(f"📝 Found saved models for {new_backend}: Main={target_main_model}, Auto={target_auto_model}, Vision={target_vision_model}")
            else:
                # Use backend-specific defaults from config.py
                default_models = config.BACKEND_DEFAULT_MODELS.get(new_backend, {})
                target_main_model = default_models.get("selected_model")
                target_auto_model = default_models.get("automatik_model")
                self.add_debug(f"📝 Using default models for {new_backend}: Main={target_main_model}, Auto={target_auto_model}")

            # Set target models BEFORE initialize_backend() so validation doesn't override them
            # CRITICAL: Set BOTH display name AND ID - initialize_backend() uses _id for validation!
            if target_main_model:
                self.selected_model = target_main_model
                self.selected_model_id = target_main_model  # IDs are same as names in settings
            if target_auto_model:
                self.automatik_model = target_auto_model
                self.automatik_model_id = target_auto_model  # IDs are same as names in settings
            if target_vision_model:
                self.vision_model = target_vision_model
                self.vision_model_id = target_vision_model  # IDs are same as names in settings

            # vLLM and TabbyAPI can only load ONE model at a time
            # Set automatik_model = selected_model BEFORE initialize_backend() to prevent wrong model loading
            if new_backend in ["vllm", "tabbyapi"]:
                if self.automatik_model != self.selected_model:
                    self.add_debug(f"⚠️ {new_backend} can only load one model - using {self.selected_model} for both Main and Automatik")
                self.automatik_model = self.selected_model
                self.automatik_model_id = self.selected_model_id  # Sync IDs too

            # Switch backend and load models
            self.backend_type = new_backend
            self.backend_id = new_backend  # Sync ID with type
            self.current_backend_label = self.available_backends_dict.get(new_backend, new_backend)
            # Reset init flag to force full initialization
            _global_backend_state["_init_complete"] = False
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
            - User finishes inference → has thinking time
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

        # Log startup (two lines for better readability on mobile)
        self.add_debug("🎯 GPU Inactivity Monitor started")
        self.add_debug(
            f"  • Rolling Window: {idle_checks_needed} checks à {KOBOLDCPP_INACTIVITY_CHECK_INTERVAL}s = {KOBOLDCPP_INACTIVITY_TIMEOUT}s timeout"
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

                # Check if all GPUs idle AND no requests in KoboldCPP's internal queue
                # Query KoboldCPP's native queue status via /api/extra/perf
                koboldcpp_busy = False
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=2.0) as client:
                        resp = await client.get("http://127.0.0.1:5001/api/extra/perf")
                        if resp.status_code == 200:
                            perf = resp.json()
                            # queue > 0 means requests waiting, idle == 0 means currently processing
                            koboldcpp_busy = perf.get("queue", 0) > 0 or perf.get("idle", 1) == 0
                except Exception:
                    pass  # If we can't query, assume not busy

                if koboldcpp_busy:
                    # Requests in KoboldCPP queue - treat as active
                    if self.gpu_consecutive_idle_checks > 0:
                        from aifred.lib.logging_utils import log_message
                        log_message(
                            f"🔒 KoboldCPP busy (queue active) - idle timer reset "
                            f"(was at {self.gpu_consecutive_idle_checks}/{idle_checks_needed} checks)"
                        )
                    self.gpu_consecutive_idle_checks = 0
                    self.gpu_total_active_checks += 1
                elif are_all_gpus_idle(utilization):
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
                    # CRITICAL: Final check before shutdown - are requests waiting?
                    # This prevents killing server while a request just arrived
                    # Query KoboldCPP's native queue status via /api/extra/perf
                    koboldcpp_busy_final = False
                    try:
                        async with httpx.AsyncClient(timeout=2.0) as client:
                            resp = await client.get("http://127.0.0.1:5001/api/extra/perf")
                            if resp.status_code == 200:
                                perf = resp.json()
                                koboldcpp_busy_final = perf.get("queue", 0) > 0 or perf.get("idle", 1) == 0
                    except Exception:
                        pass  # If we can't query, proceed with shutdown

                    if koboldcpp_busy_final:
                        from aifred.lib.logging_utils import log_message
                        log_message(
                            "🔒 Shutdown aborted - KoboldCPP queue active"
                        )
                        self.gpu_consecutive_idle_checks = 0  # Reset timer
                        continue  # Skip shutdown, continue monitoring

                    idle_duration = self.gpu_consecutive_idle_checks * KOBOLDCPP_INACTIVITY_CHECK_INTERVAL

                    # Log shutdown messages (via add_debug for UI propagation)
                    self.debug_messages.append(
                        f"{datetime.datetime.now().strftime('%H:%M:%S')} | "
                        f"🛑 KoboldCPP shutting down due to inactivity "
                        f"(GPUs were {idle_duration}s idle, Timeout: {KOBOLDCPP_INACTIVITY_TIMEOUT}s)"
                    )
                    self.debug_messages.append(
                        f"{datetime.datetime.now().strftime('%H:%M:%S')} | "
                        f"   GPU stats: {self.gpu_total_active_checks} active / "
                        f"{self.gpu_total_idle_checks} idle checks"
                    )

                    # Log to file
                    from aifred.lib.logging_utils import log_message
                    log_message(
                        f"🛑 KoboldCPP shutting down due to inactivity "
                        f"(GPUs were {idle_duration}s idle, Timeout: {KOBOLDCPP_INACTIVITY_TIMEOUT}s)"
                    )
                    log_message(
                        f"   GPU stats: {self.gpu_total_active_checks} active / "
                        f"{self.gpu_total_idle_checks} idle checks"
                    )

                    # Graceful shutdown
                    try:
                        await koboldcpp_manager.stop()

                        self.debug_messages.append(
                            f"{datetime.datetime.now().strftime('%H:%M:%S')} | "
                            "✅ KoboldCPP successfully shut down"
                        )
                        log_message("✅ KoboldCPP successfully shut down")

                        # Add separator
                        console_separator()  # File log
                        self.debug_messages.append(
                            f"{datetime.datetime.now().strftime('%H:%M:%S')} | "
                            "────────────────────"
                        )

                    except Exception as e:
                        self.debug_messages.append(
                            f"{datetime.datetime.now().strftime('%H:%M:%S')} | "
                            f"❌ Auto-Shutdown failed: {e}"
                        )
                        log_message(f"❌ Auto-Shutdown failed: {e}")

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

    async def _detect_vision_models(self):
        """
        Detect vision-capable models using backend-specific metadata.
        Populates self.vision_models_cache for UI dropdown.
        """
        global _global_backend_state
        from .lib.vision_utils import is_vision_model

        vision_model_ids = []  # NEW: Store IDs, not display names

        # NEW: Iterate over dict items
        for model_id, model_display in self.available_models_dict.items():
            try:
                # Query backend metadata to check vision capability
                if await is_vision_model(self, model_id):  # model_id is already pure
                    vision_model_ids.append(model_id)  # Store pure ID
            except Exception as e:
                # Fallback: skip on error (don't block initialization)
                log_message(f"⚠️ Vision detection failed for {model_id}: {e}")

        self.vision_models_cache = vision_model_ids  # Store IDs
        _global_backend_state["vision_models_cache"] = vision_model_ids

        # Build display names list for dropdown (synced state variable, not computed property)
        self.available_vision_models_list = [
            self.available_models_dict.get(mid, mid) for mid in vision_model_ids
            if mid in self.available_models_dict
        ]
        _global_backend_state["available_vision_models_list"] = self.available_vision_models_list

        self.add_debug(f"✅ Found {len(vision_model_ids)} vision-capable models")

        # Auto-select vision_model if not set or empty
        if (not self.vision_model_id or self.vision_model_id.strip() == "") and vision_model_ids:
            self.vision_model_id = vision_model_ids[0]
            self.vision_model = self.available_models_dict[self.vision_model_id]  # Sync display
            self.add_debug(f"⚙️ Auto-selected vision_model: {self.vision_model_id}")
            self._save_settings()
        # Validate existing vision_model is in cache
        elif self.vision_model_id and vision_model_ids:
            if self.vision_model_id in vision_model_ids:
                # Sync display variable
                self.vision_model = self.available_models_dict.get(self.vision_model_id, self.vision_model_id)
            else:
                # Saved model not found in vision models, auto-select first available
                self.add_debug(f"⚠️ Saved vision_model '{self.vision_model_id}' not found in vision models, auto-selecting...")
                self.vision_model_id = vision_model_ids[0]
                self.vision_model = self.available_models_dict[self.vision_model_id]
                self._save_settings()

        # Show selected vision model (consistent with Main/Automatik format)
        if self.vision_model_id:
            self.add_debug(f"   Vision: {self.vision_model}")

        # Store vision_model in global state for fast path restore
        _global_backend_state["vision_model"] = self.vision_model
        _global_backend_state["vision_model_id"] = self.vision_model_id

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
            startup_model = self.selected_model_id  # Pure ID
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
        """Start KoboldCPP server process with selected GGUF model

        This is the public method that acquires the lock. For internal use
        when already holding the lock, use _start_koboldcpp_server_internal().
        """
        # Use lock to prevent race condition when multiple sessions start simultaneously
        async with _backend_init_lock:
            await self._start_koboldcpp_server_internal()

    async def _start_koboldcpp_server_internal(self):
        """Internal: Start KoboldCPP without lock (caller must hold _backend_init_lock)"""
        global _global_backend_state

        try:
            # Check if KoboldCPP is already running from global state
            existing_manager = _global_backend_state.get("koboldcpp_manager")
            if existing_manager and existing_manager.is_running():
                self.add_debug("✅ KoboldCPP server already running (using existing process)")
                return

            # Get GGUF model info from global state
            # Extract pure model name (remove size suffix)
            pure_model_name = self.selected_model_id  # Pure ID
            gguf_models = _global_backend_state.get("gguf_models", {})

            # If gguf_models not loaded yet (e.g. service restart), scan now
            if not gguf_models:
                from aifred.lib.gguf_utils import find_all_gguf_models
                gguf_models_list = find_all_gguf_models()
                gguf_models = {model.name: model for model in gguf_models_list}
                _global_backend_state["gguf_models"] = gguf_models
                self.add_debug(f"🔍 GGUF models scanned: {len(gguf_models)} found")

            if pure_model_name not in gguf_models:
                raise RuntimeError(f"GGUF model '{pure_model_name}' not found")

            model_info = gguf_models[pure_model_name]
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
                model_name=self.selected_model_id,  # For cache lookup (pure ID)
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
                _global_backend_state["koboldcpp_selected_model"] = self.selected_model_id  # Pure ID for auto-restart lookup

                # Store context size in global cache for History compression
                # (same as vLLM does in context_manager.py)
                from aifred.lib.context_manager import _last_vram_limit_cache
                _last_vram_limit_cache["limit"] = config_info['context_size']
                _last_vram_limit_cache["aifred_limit"] = config_info['context_size']

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
        """Ensure KoboldCPP is running, start if stopped (e.g., by auto-unload monitor)

        IMPORTANT: Uses _backend_init_lock to prevent race condition when multiple
        browser sessions call this simultaneously. The check AND start must be atomic.
        """
        global _global_backend_state

        # Use lock to make check-and-start atomic (prevents double-start race condition)
        async with _backend_init_lock:
            existing_manager = _global_backend_state.get("koboldcpp_manager")

            # Check if already running (now protected by lock)
            if existing_manager and existing_manager.is_running():
                return  # Already running, nothing to do

            # KoboldCPP is not running - start it
            self.add_debug("⚠️ KoboldCPP not running - starting automatically...")

            # Set UI flag for auto-restart spinner
            _global_backend_state["koboldcpp_auto_restarting"] = True
            yield  # Force immediate UI update to show spinner

            # Call internal start (without lock, since we already hold it)
            await self._start_koboldcpp_server_internal()

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
        # If no text but images present, use default prompt
        has_pending_images = len(self.pending_images) > 0
        user_text = self.current_user_input.strip()

        if not user_text and not has_pending_images:
            return  # Nothing to send

        # Leerer user_text ist erlaubt für reine OCR-Extraktion (ohne Interpretation)

        if self.is_generating:
            self.add_debug("⚠️ Already generating, please wait...")
            return

        # Ensure backend is initialized (should already be done by on_load)
        await self._ensure_backend_initialized()

        user_msg = user_text
        self.current_user_input = ""  # Clear input
        self.current_user_message = user_msg  # Zeige sofort die Eingabe an
        self.is_generating = True
        self.current_ai_response = ""
        self.failed_sources = []  # Clear failed sources from previous request

        # Add user message to chat history IMMEDIATELY (before any pipeline processing)
        # This ensures the user sees their message right away, even during STT transcription
        temp_history_index = len(self.chat_history)
        self.chat_history.append((user_msg, ""))

        yield  # Update UI sofort (Eingabefeld leeren + Spinner zeigen + User-Nachricht anzeigen)

        # Debug message wird von agent_core.py geloggt, nicht hier!

        try:
            # ============================================================
            # DIALOG ROUTING: Check for direct addressing (@Sokrates, @AIfred)
            # ============================================================
            from .lib.intent_detector import detect_dialog_addressing
            addressed_to, cleaned_text = detect_dialog_addressing(user_msg)

            # Track if Sokrates should be skipped (AIfred direct addressing)
            skip_sokrates_analysis = False
            use_aifred_direct_prompt = False

            if addressed_to == "sokrates":
                # User directly addresses Sokrates → Sokrates responds directly
                self.add_debug("🏛️ Direct addressing: Sokrates")
                yield  # Update UI immediately to show debug message
                async for _ in run_sokrates_direct_response(self, user_msg, temp_history_index):
                    yield
                # Clean up and return - Sokrates handled everything
                self.current_ai_response = ""
                self.current_user_message = ""
                self.is_generating = False
                self._save_current_session()
                yield
                return

            elif addressed_to == "alfred":
                # User directly addresses AIfred → Skip Sokrates analysis, use special prompt
                self.add_debug("🎩 Direct addressing: AIfred")
                yield  # Update UI immediately to show debug message
                skip_sokrates_analysis = True
                use_aifred_direct_prompt = True
                # Continue with normal flow, but with AIfred's direct response persona

            # ============================================================
            # VISION PIPELINE: Route to Vision-LLM if images present
            # ============================================================
            if has_pending_images:
                # CRITICAL FIX: Copy images to LOCAL variable BEFORE any yield!
                # Reflex State can be modified between yields, causing race conditions.
                # Deep copy ensures we keep the image data even if self.pending_images gets cleared.
                import copy
                local_images = copy.deepcopy(self.pending_images)
                local_image_names = ", ".join([img.get("name", "unknown") for img in local_images])

                # Generate image markers for embedding in chat history
                # Format: [IMG:data:image/jpeg;base64,...] - will be rendered as clickable thumbnails
                image_markers = " ".join([f"[IMG:{img.get('url', '')}]" for img in local_images if img.get('url')])

                # Log Vision-LLM header + each image on separate line (like Main/Automatik)
                self.add_debug(f"📷 Vision-LLM ({self.vision_model}) analyzing:")
                for img in local_images:
                    self.add_debug(f"   • {img.get('name', 'unknown')}")
                yield  # Update UI immediately to show Vision Pipeline start

                # Save original user text (for Vision pipeline - may be empty!)
                original_user_text = user_msg

                # Build display_user_msg with embedded image markers for chat history
                # Image markers are prepended so thumbnails appear before text
                display_user_msg = user_msg
                if not user_msg or user_msg.strip() == "":
                    # Image-only upload: show image names + markers
                    if len(local_images) == 1:
                        display_user_msg = f"{image_markers}\n📷 {local_images[0].get('name', 'Image')}"
                    else:
                        display_user_msg = f"{image_markers}\n📷 {len(local_images)} images: {local_image_names}"
                else:
                    # Text + images: prepend markers to text
                    display_user_msg = f"{image_markers}\n{user_msg}" if image_markers else user_msg

                # CRITICAL: Ensure KoboldCPP is running before LLM call
                if self.backend_type == "koboldcpp":
                    async for _ in self._ensure_koboldcpp_running():
                        yield  # Forward yields from _ensure_koboldcpp_running() to UI

                # Import vision pipeline
                from .lib.conversation_handler import chat_with_vision_pipeline

                # Update history entry with display_user_msg (may differ from user_msg for images)
                # History entry was already created at the start of send_message()
                if display_user_msg != user_msg:
                    # Update the user message part (e.g., for image-only uploads)
                    self.chat_history[temp_history_index] = (display_user_msg, self.current_ai_response)

                # Build LLM options (include enable_thinking toggle)
                llm_options = {
                    'enable_thinking': self.enable_thinking
                }

                # Storage für Vision-JSON (wird in history gespeichert statt readable text)
                vision_json_response = ""
                vision_readable_text = ""
                vision_metrics = None
                extracted_vision_json = {}  # Store for passing to chat_interactive_mode
                has_user_text_for_automatik = False  # Flag from vision_complete

                # ==============================================================================
                # PHASE 1: VISION EXTRACTION (Process Vision-LLM items only)
                # ==============================================================================
                from .lib.logging_utils import log_message

                async for item in chat_with_vision_pipeline(
                    user_text=original_user_text,  # CRITICAL: Use original (may be empty!), not display_user_msg
                    images=local_images,  # CRITICAL: Use local copy, NOT self.pending_images!
                    vision_model=self.vision_model_id,  # Pure ID
                    main_model=self.selected_model_id,  # Pure ID
                    backend_type=self.backend_type,
                    backend_url=self.backend_url,
                    num_ctx_mode=self.num_ctx_mode,
                    num_ctx_manual=self.num_ctx_manual,
                    llm_options=llm_options,
                    state=self  # Pass entire state object (for accessing config, not for calling functions)
                ):

                    # Route Vision-LLM items only (NOT Automatik items!)
                    if item["type"] == "status":
                        self.add_debug(item.get("content", ""))

                    elif item["type"] == "debug":
                        msg = item.get("content") or item.get("message", "")
                        if msg:
                            self.add_debug(msg)
                        yield  # Update UI immediately for each debug message

                    elif item["type"] == "thinking":
                        # Vision-LLM structured data → sammle für Collapsible
                        # <think> tags bleiben jetzt in vision_readable_text!
                        vision_json_response = item["content"]

                    elif item["type"] == "response":
                        # Readable text (Markdown table) → sammle und zeige im Stream
                        content = item["content"]
                        if not isinstance(content, str):
                            self.add_debug(f"⚠️ WARNING: Vision response content is {type(content)}, expected str. Converting...")
                            content = str(content) if content is not None else ""
                        vision_readable_text += content
                        self.current_ai_response += content
                        yield

                    elif item["type"] == "done":
                        # Metrics vom Backend sammeln
                        vision_metrics = item.get("metrics", {})

                    elif item["type"] == "error":
                        self.add_debug(item.get("content", "Unknown error"))

                    elif item["type"] == "vision_complete":
                        # ======================================================================
                        # CRITICAL: Vision extraction complete - finalize and break!
                        # ======================================================================

                        # Extract data from signal
                        final_vision_metrics = item.get("metrics", vision_metrics or {})
                        extracted_vision_json = item.get("vision_json", {})
                        has_user_text_for_automatik = item.get("has_user_text", False)

                        # Finalize Vision response (with or without JSON)
                        from .lib.formatting import format_thinking_process, format_metadata, format_number

                        vision_time = final_vision_metrics.get("inference_time", 0) if final_vision_metrics else 0
                        tokens_generated = final_vision_metrics.get("tokens_generated", 0) if final_vision_metrics else 0
                        tokens_per_sec = final_vision_metrics.get("tokens_per_second", 0) if final_vision_metrics else 0

                        if vision_json_response:
                            # JSON vorhanden → Build <data> Block
                            data_block = f"<data>\n{vision_json_response}\n</data>"
                            full_response = f"{data_block}\n\n{vision_readable_text}"
                        else:
                            # Kein JSON → vision_readable_text enthält ggf. <think> tags!
                            full_response = vision_readable_text

                        if full_response:
                            # format_thinking_process() verarbeitet ALLE XML-Tags automatisch!
                            formatted_html = format_thinking_process(
                                full_response,
                                model_name=self.vision_model_id,  # Pure ID
                                inference_time=vision_time,
                                tokens_per_sec=tokens_per_sec
                            )

                            # Metadata footer with model name
                            metadata = format_metadata(
                                f"Vision: {format_number(vision_time, 1)}s    {format_number(tokens_per_sec, 1)} tok/s ({self.vision_model_id})"
                            )
                            formatted_response = f"{formatted_html}\n\n{metadata}"
                        elif vision_readable_text:
                            # Kein JSON, aber readable text vorhanden (z.B. Fallback oder nur Description)
                            metadata = format_metadata(
                                f"Vision: {format_number(vision_time, 1)}s    {format_number(tokens_per_sec, 1)} tok/s ({self.vision_model_id})"
                            )
                            formatted_response = f"{vision_readable_text}\n\n{metadata}"
                        else:
                            # Neither JSON nor text - error
                            formatted_response = "⚠️ Vision-LLM could not produce a result. See debug log."

                        # ALWAYS update current response and history (even if empty/error)
                        # Use display_user_msg (with image name) for history display
                        self.current_ai_response = formatted_response
                        self.chat_history[temp_history_index] = (display_user_msg, formatted_response)

                        self.add_debug(f"✅ Vision-LLM done ({vision_time:.1f}s, {tokens_generated} tokens, {tokens_per_sec:.1f} tok/s)")
                        self.add_debug("────────────────────")
                        yield

                        # BREAK out of Vision loop - Phase 1 complete!
                        break

                    else:
                        # Unknown type - log warning
                        self.add_debug(f"⚠️ Unknown item type from Vision pipeline: {item.get('type', 'MISSING')}")

                # ==============================================================================
                # PHASE 2: AUTOMATIK/RESEARCH FLOW (if user text present)
                # ==============================================================================
                if has_user_text_for_automatik:
                    self.add_debug("🤖 Main-LLM Phase startet...")
                    yield

                    # Import here to avoid circular dependency
                    from .lib.conversation_handler import chat_interactive_mode

                    # Initialize temporary history entry for real-time display
                    # Use original_user_text (actual user question, not image filename)
                    temp_history_index_main = len(self.chat_history)
                    self.chat_history.append((original_user_text, ""))
                    self.current_ai_response = ""  # Reset for Main-LLM streaming

                    # Call chat_interactive_mode with Vision JSON context
                    # (EXACT same pattern as normal flow in line 2012-2027)
                    async for item in chat_interactive_mode(
                        user_text=original_user_text,  # Actual user question
                        stt_time=0.0,  # No STT for Vision follow-up
                        model_choice=self.selected_model_id,
                        automatik_model=self.automatik_model_id,
                        history=self.chat_history[:-1],  # Exclude current temporary entry (CRITICAL!)
                        session_id=self.session_id,
                        temperature_mode=self.temperature_mode,
                        temperature=self.temperature,
                        llm_options=llm_options,
                        backend_type=self.backend_type,
                        backend_url=self.backend_url,
                        num_ctx_mode=self.num_ctx_mode,
                        num_ctx_manual=self.num_ctx_manual,
                        pending_images=None,  # Images already processed
                        vision_json_context=extracted_vision_json,  # Pass Vision JSON!
                        user_name=self.user_name  # For personalized prompts
                    ):
                        # Handle Main-LLM items using NORMAL FLOW logic
                        # (EXACT same pattern as normal flow in line 2029-2068)
                        if item["type"] == "debug":
                            self.debug_messages.append(format_debug_message(item["message"]))
                            if len(self.debug_messages) > 500:
                                self.debug_messages = self.debug_messages[-500:]
                            yield  # Update UI immediately for each debug message

                        elif item["type"] == "content":
                            self.current_ai_response += item["text"]
                            # Update the temporary entry in chat history with the new content
                            if temp_history_index_main < len(self.chat_history):
                                self.chat_history[temp_history_index_main] = (user_msg, self.current_ai_response)
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

                        # Note: Update UI after each item (including unknown types)
                        yield

                else:
                    # No user text - just Vision extraction, finalize normally
                    # Clear images after Vision processing
                    self.clear_pending_images()

                    # Clear both windows and stop generating
                    # (Response is already in chat_history, UI will show history)
                    self.current_ai_response = ""
                    self.current_user_message = ""
                    self.is_generating = False
                    yield  # Force UI update to show chat history

                return  # Exit send_message - vision pipeline complete

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

                # History entry was already created at the start of send_message()
                # No need to append again - temp_history_index already points to it

                # Build LLM options (include enable_thinking toggle)
                llm_options = {
                    'enable_thinking': self.enable_thinking
                }

                # REAL STREAMING: Call async generator directly
                async for item in chat_interactive_mode(
                    user_text=user_msg,
                    stt_time=0.0,
                    model_choice=self.selected_model_id,
                    automatik_model=self.automatik_model_id,
                    history=self.chat_history[:-1],  # Exclude current temporary entry
                    session_id=self.session_id,
                    temperature_mode=self.temperature_mode,
                    temperature=self.temperature,
                    llm_options=llm_options,
                    backend_type=self.backend_type,
                    backend_url=self.backend_url,
                    num_ctx_mode=self.num_ctx_mode,
                    num_ctx_manual=self.num_ctx_manual,
                    pending_images=self.pending_images if len(self.pending_images) > 0 else None,
                    user_name=self.user_name  # For personalized prompts
                ):
                    # Route messages based on type
                    if item["type"] == "debug":
                        self.debug_messages.append(format_debug_message(item["message"]))
                        if len(self.debug_messages) > 500:
                            self.debug_messages = self.debug_messages[-500:]
                        yield  # IMPORTANT: Update UI immediately for each debug message
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
                        # Embed failed_sources in the last message if any pending
                        if self._pending_failed_sources and updated_history:
                            import json as json_module
                            last_idx = len(updated_history) - 1
                            user_msg, ai_msg = updated_history[last_idx]
                            # Prepend failed sources markup to AI message
                            failed_markup = f"<!--FAILED_SOURCES:{json_module.dumps(self._pending_failed_sources)}-->\n"
                            updated_history[last_idx] = (user_msg, failed_markup + ai_msg)
                            self._pending_failed_sources = []  # Clear pending
                        # Replace chat history with updated one from research - message is already in history
                        self.chat_history = updated_history
                        # The message is already in the history from the streaming, no need to re-add
                        yield  # Update UI to show new history entry

                        # ============================================================
                        # MULTI-AGENT: Sokrates/Salomo Analysis (if enabled and not skipped)
                        # skip_sokrates_analysis is set when user directly addresses AIfred
                        # ============================================================
                        if self.multi_agent_mode != "standard" and ai_text and not skip_sokrates_analysis:
                            if self.multi_agent_mode == "tribunal":
                                async for _ in run_tribunal(self, user_msg, ai_text):
                                    yield  # Forward yields to update agent panels
                            else:
                                async for _ in run_sokrates_analysis(self, user_msg, ai_text):
                                    yield  # Forward yields to update Sokrates panel

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
                        self.add_debug(f"📊 History updated: {len(updated_history)} messages")
                    elif item["type"] == "thinking_warning":
                        # Show thinking mode warning (model doesn't support reasoning)
                        self.thinking_mode_warning = item["model"]
                    elif item["type"] == "failed_sources":
                        # Store failed sources for UI display AND persistent history
                        self.failed_sources = item["data"]
                        self._pending_failed_sources = item["data"]  # Will be embedded in message
                        self.add_debug(f"⚠️ {len(item['data'])} sources unavailable")
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

                # Separator is already sent by conversation_handler
                # console_separator()  # Writes to log file
                # self.add_debug("────────────────────")  # Shows in debug console
                # yield

            elif self.research_mode in ["quick", "deep"]:
                # Direct research mode (quick/deep)
                self.add_debug(f"🔍 Research Mode: {self.research_mode}")

                # CRITICAL: Ensure KoboldCPP is running before LLM call
                if self.backend_type == "koboldcpp":
                    async for _ in self._ensure_koboldcpp_running():
                        yield  # Forward yields from _ensure_koboldcpp_running() to UI

                # History entry was already created at the start of send_message()
                # No need to append again - temp_history_index already points to it

                # Build LLM options (include enable_thinking toggle)
                llm_options = {
                    'enable_thinking': self.enable_thinking
                }

                # REAL STREAMING: Call async generator directly
                # Extract pure model names (remove size suffix like "(9.3 GB)")
                async for item in perform_agent_research(
                    user_text=user_msg,
                    stt_time=0.0,  # Kein STT in Reflex (noch)
                    mode=self.research_mode,
                    model_choice=self.selected_model_id,  # Pure ID
                    automatik_model=self.automatik_model_id,  # Pure ID
                    history=self.chat_history[:-1],  # Exclude current temporary entry
                    session_id=self.session_id,
                    temperature_mode=self.temperature_mode,
                    temperature=self.temperature,
                    llm_options=llm_options,
                    backend_type=self.backend_type,
                    backend_url=self.backend_url,
                    user_name=self.user_name  # For personalized prompts
                ):
                    # Route messages based on type
                    if item["type"] == "debug":
                        self.debug_messages.append(format_debug_message(item["message"]))
                        # Limit debug messages
                        if len(self.debug_messages) > 500:
                            self.debug_messages = self.debug_messages[-500:]
                        yield  # Update UI immediately for each debug message
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
                        # Embed failed_sources in the last message if any pending
                        if self._pending_failed_sources and updated_history:
                            import json as json_module
                            last_idx = len(updated_history) - 1
                            user_msg_hist, ai_msg_hist = updated_history[last_idx]
                            # Prepend failed sources markup to AI message
                            failed_markup = f"<!--FAILED_SOURCES:{json_module.dumps(self._pending_failed_sources)}-->\n"
                            updated_history[last_idx] = (user_msg_hist, failed_markup + ai_msg_hist)
                            self._pending_failed_sources = []  # Clear pending
                        # Replace chat history with updated one from research - message is already in history
                        self.chat_history = updated_history
                        # The message is already in the history from the streaming, no need to re-add
                        yield  # Update UI to show new history entry

                        # ============================================================
                        # MULTI-AGENT: Sokrates/Salomo Analysis (if enabled and not skipped)
                        # skip_sokrates_analysis is set when user directly addresses AIfred
                        # ============================================================
                        if self.multi_agent_mode != "standard" and ai_text and not skip_sokrates_analysis:
                            if self.multi_agent_mode == "tribunal":
                                async for _ in run_tribunal(self, user_msg, ai_text):
                                    yield  # Forward yields to update agent panels
                            else:
                                async for _ in run_sokrates_analysis(self, user_msg, ai_text):
                                    yield  # Forward yields to update Sokrates panel

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
                        self.add_debug(f"📊 History updated: {len(updated_history)} messages")
                    elif item["type"] == "thinking_warning":
                        # Show thinking mode warning (model doesn't support reasoning)
                        self.thinking_mode_warning = item["model"]
                    elif item["type"] == "failed_sources":
                        # Store failed sources for UI display AND persistent history
                        self.failed_sources = item["data"]
                        self._pending_failed_sources = item["data"]  # Will be embedded in message
                        self.add_debug(f"⚠️ {len(item['data'])} sources unavailable")
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
                self.add_debug("🧠 Own knowledge (no web search)")

                # History entry was already created at the start of send_message()
                # No need to append again - temp_history_index already points to it

                # Start timing for preload phase (preparation + actual model loading)
                import time

                # Build messages from history
                from .lib.message_builder import build_messages_from_history
                messages = build_messages_from_history(
                    history=self.chat_history[:-1],  # Exclude current temporary entry
                    current_user_text=user_msg
                )

                # Inject system prompt with timestamp (from load_prompt - automatically includes date/time)
                from .lib.prompt_loader import load_prompt, detect_language, get_aifred_direct_prompt
                detected_language = detect_language(user_msg)

                # Use AIfred direct prompt if user addressed AIfred directly
                if use_aifred_direct_prompt:
                    system_prompt = get_aifred_direct_prompt(lang=detected_language)
                else:
                    system_prompt = load_prompt('aifred/system_minimal', lang=detected_language)

                messages.insert(0, {"role": "system", "content": system_prompt})

                # Create backend and LLM client instances
                from .backends import BackendFactory, LLMOptions
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

                # Extract pure model name (remove size suffix)
                pure_model_name = self.selected_model_id  # Pure ID

                # Import format_number for locale-aware number formatting (uses global ui_locale)
                from .lib.formatting import format_number

                # Temperature decision: Manual Override or Auto (Intent-Detection)
                # IMPORTANT: Intent Detection MUST run BEFORE Main-LLM preload!
                # Otherwise Ollama might unload the Main-LLM to load the Automatik-LLM,
                # then reload the Main-LLM again (wasting ~10s of loading time).
                if self.temperature_mode == 'manual':
                    final_temperature = self.temperature
                    self.add_debug(f"🌡️ Temperature: {final_temperature} (manual)")
                else:
                    # Auto: Intent-Detection for own knowledge mode
                    from .lib.intent_detector import detect_query_intent, get_temperature_for_intent, get_temperature_label

                    # Use automatik model for intent detection
                    automatik_llm_client = LLMClient(backend_type=self.backend_type, base_url=self.backend_url)

                    self.add_debug("🎯 Intent detection running...")
                    yield

                    intent_start = time.time()
                    own_knowledge_intent = await detect_query_intent(
                        user_query=user_msg,
                        automatik_model=self.automatik_model_id,
                        llm_client=automatik_llm_client,
                        llm_options={'temperature': 0.2, 'num_predict': 64}
                    )
                    intent_time = time.time() - intent_start

                    final_temperature = get_temperature_for_intent(own_knowledge_intent)
                    temp_label = get_temperature_label(own_knowledge_intent)
                    # Store intent-based temperature in state for Multi-Agent mode
                    self.temperature = final_temperature
                    self.add_debug(f"🌡️ Temperature: {final_temperature} (auto, {temp_label}, {format_number(intent_time, 1)}s)")
                yield

                # Count actual input tokens (using real tokenizer)
                from .lib.context_manager import estimate_tokens, prepare_main_llm
                input_tokens = estimate_tokens(messages, model_name=pure_model_name)

                # Prepare Main-LLM: calculate num_ctx + Preload (central function!)
                # IMPORTANT: prepare_main_llm() guarantees the correct order:
                # 1. Calculate num_ctx (Ollama auto: with unload + VRAM measurement)
                # 2. Preload with num_ctx (Ollama loads model + allocates KV-Cache)
                # AsyncGenerator yields debug messages immediately for UI feedback
                async for item in prepare_main_llm(
                    backend=backend,
                    llm_client=llm_client,
                    model_name=pure_model_name,
                    messages=messages,
                    num_ctx_mode=self.num_ctx_mode,
                    num_ctx_manual=self.num_ctx_manual,
                    backend_type=self.backend_type
                ):
                    if item["type"] == "debug":
                        self.add_debug(item["message"])
                        yield
                    elif item["type"] == "result":
                        final_num_ctx, preload_success, preload_time = item["data"]

                # Get model context limit for display
                model_limit, _ = await llm_client.get_model_context_limit(pure_model_name)

                self.add_debug("✅ System prompt created")
                yield

                # Show compact context info (matching Automatik mode style)
                self.add_debug(f"📊 Main-LLM: {format_number(input_tokens)} / {format_number(final_num_ctx)} tokens (max: {format_number(model_limit)})")
                yield

                # Build LLM options
                llm_options = LLMOptions(
                    temperature=final_temperature,
                    num_ctx=final_num_ctx,  # Use dynamically calculated context (or manual override)
                    enable_thinking=self.enable_thinking
                )

                # Console: LLM starts (matching Automatik mode)
                self.add_debug(f"🤖 Main-LLM starting: {self.selected_model}")
                yield

                # Stream response directly from LLM
                from .lib.logging_utils import log_message
                log_message(f"🔬 DEBUG: Setting inference_start at {time.time()}")
                inference_start = time.time()
                log_message(f"🔬 DEBUG: inference_start = {inference_start}")
                full_response = ""
                ttft = None
                first_token_received = False
                tokens_generated = 0

                log_message(f"🔬 DEBUG: Starting chat_stream at {time.time()}")
                async for chunk in llm_client.chat_stream(
                    model=pure_model_name,
                    messages=messages,
                    options=llm_options
                ):
                    if chunk["type"] == "content":
                        # Measure TTFT (matching Automatik mode)
                        if not first_token_received:
                            now = time.time()
                            log_message(f"🔬 DEBUG: First token received at {now}, inference_start was {inference_start}")
                            ttft = now - inference_start
                            log_message(f"🔬 DEBUG: TTFT = {ttft:.6f}s (now={now}, start={inference_start})")
                            first_token_received = True
                            self.add_debug(f"⚡ TTFT: {format_number(ttft, 2)}s")
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
                self.add_debug(f"✅ Main-LLM done ({format_number(inference_time, 1)}s, {format_number(tokens_generated)} tokens, {format_number(tokens_per_sec, 1)} tok/s)")
                yield

                # Separator after Main-LLM (matching other modes)
                console_separator()
                self.add_debug("────────────────────")
                yield

                # Format <think> tags as collapsible (if present)
                from .lib.formatting import format_thinking_process, format_metadata
                thinking_html = format_thinking_process(
                    full_response,
                    model_name=self.selected_model_id,  # Use pure ID, not display name with size
                    inference_time=inference_time,
                    tokens_per_sec=tokens_per_sec
                )

                # Add metadata footer (Inference + Tok/s + Source + Model) like other modes
                metadata = format_metadata(
                    f"Inference: {format_number(inference_time, 1)}s    {format_number(tokens_per_sec, 1)} tok/s    Source: Training data ({self.selected_model_id})"
                )
                formatted_response = f"{thinking_html}  \n{metadata}"

                # Update chat history with formatted response + metadata
                self.chat_history[temp_history_index] = (user_msg, formatted_response)
                yield  # Update UI

                # ============================================================
                # MULTI-AGENT: Sokrates/Salomo Analysis (if enabled and not direct AIfred addressing)
                # ============================================================
                # skip_sokrates_analysis is True when user directly addresses AIfred
                if self.multi_agent_mode != "standard" and full_response and not skip_sokrates_analysis:
                    if self.multi_agent_mode == "tribunal":
                        async for _ in run_tribunal(self, user_msg, full_response):
                            yield  # Forward yields to update agent panels
                    else:
                        async for _ in run_sokrates_analysis(self, user_msg, full_response):
                            yield  # Forward yields to update Sokrates panel

                # Clear response windows
                self.current_ai_response = ""
                self.current_user_message = ""
                self.is_generating = False
                yield  # Force UI update

                await llm_client.close()

            # ============================================================
            # POST-RESPONSE: History Summarization Check (in background)
            # ============================================================
            # Compression runs AFTER the response, while user reads
            # Input fields are disabled during compression
            # NOTE: Skip for Multi-Agent - compression already runs in run_sokrates_analysis

            try:
                from .lib.context_manager import summarize_history_if_needed
                from .backends import BackendFactory

                # Skip for Multi-Agent (compression already done in run_sokrates_analysis)
                if self.multi_agent_mode == "standard":  # Only run for standard mode
                    yield
                    # Backend for summarization
                    temp_backend = BackendFactory.create(
                        self.backend_type,
                        base_url=self.backend_url
                    )

                    # Context limit for history compression:
                    # Use saved VRAM limit from last inference (prevents recalculation!)
                    from aifred.lib.context_manager import _last_vram_limit_cache

                    if self.num_ctx_mode == "manual":
                        context_limit = self.num_ctx_manual
                    elif _last_vram_limit_cache["limit"] > 0:
                        # Use saved context limit (from last inference)
                        context_limit = _last_vram_limit_cache["limit"]
                    else:
                        # Fallback: 8K (no inference run yet, limit will be calculated on first inference)
                        context_limit = 8192
                        self.add_debug("ℹ️ Context limit will be calculated on first inference (Fallback: 8K)")

                    # Set compression flag (disables input fields)
                    self.is_compressing = True
                    yield

                    # Summarization check (yields events if needed)
                    async for event in summarize_history_if_needed(
                        history=self.chat_history,
                        llm_client=temp_backend,
                        model_name=self.automatik_model_id,  # Pure model ID (not display name!)
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

                    # Clear progress if set
                    if self.progress_phase == "compress":
                        self.clear_progress()
                        yield

                    # Compression done - re-enable input fields
                    self.is_compressing = False
                    yield

            except Exception as e:
                # Not critical - just continue
                import traceback
                self.add_debug(f"⚠️ History compression check failed: {e}")
                self.add_debug(f"Traceback: {traceback.format_exc()}")
                self.is_compressing = False
                yield

            # Separator nach Compression-Check (NUR für standard mode)
            # Multi-Agent mode hat bereits Separator nach Main-LLM (Zeile ~3158)
            if self.multi_agent_mode == "standard":
                console_separator()  # Schreibt in Log-File
                self.add_debug("────────────────────")  # Zeigt in Debug-Console
                yield

            # Clear response display
            self.current_ai_response = ""
            yield  # Final update to clear AI response window

            # Debug line removed - User didn't want to see this
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
            # Clear pending images after sending
            if len(self.pending_images) > 0:
                self.clear_pending_images()

            # TTS: Generate audio for AI response if enabled
            if self.enable_tts:
                try:
                    self.add_debug("🔊 TTS: Starting TTS generation in finally block...")
                    # Get AI response from chat history (current_ai_response may be cleared)
                    if 'temp_history_index' in locals() and temp_history_index < len(self.chat_history):
                        _, ai_response = self.chat_history[temp_history_index]
                        if ai_response and ai_response.strip():
                            # Generate TTS (sets tts_audio_path and increments tts_trigger_counter)
                            # State changes automatically propagate to frontend → audio plays via autoPlay
                            await self._generate_tts_for_response(ai_response)
                        else:
                            self.add_debug("⚠️ TTS: Aktiviert aber keine AI-Antwort zum Konvertieren")
                            console_separator()
                            self.add_debug("────────────────────")
                    else:
                        self.add_debug("⚠️ TTS: Aktiviert aber Chat-History-Eintrag fehlt")
                        console_separator()
                        self.add_debug("────────────────────")
                except Exception as tts_error:
                    self.add_debug(f"⚠️ TTS generation failed: {tts_error}")
                    from .lib.logging_utils import log_message
                    log_message(f"❌ TTS error in finally block: {tts_error}")

            # Auto-Save: Session nach jeder Chat-Nachricht speichern
            self._save_current_session()


    def clear_chat(self):
        """Clear chat history, pending images, and temporary files"""
        self.chat_history = []
        self.current_ai_response = ""
        self.current_user_message = ""
        self.tts_audio_path = ""  # Clear TTS player
        self.debug_messages = []  # Debug Console auch leeren!
        self.pending_images = []  # Clear pending image uploads
        self.image_upload_warning = ""

        # TTS Audio-Dateien aufräumen
        from .lib.audio_processing import cleanup_old_tts_audio
        try:
            cleanup_old_tts_audio(max_age_hours=0)  # 0 = alle löschen
        except Exception as e:
            self.add_debug(f"⚠️ TTS cleanup failed: {e}")

        # HTML Preview Dateien aufräumen
        from .lib.config import PROJECT_ROOT
        html_preview_dir = PROJECT_ROOT / "uploaded_files" / "html_preview"
        try:
            if html_preview_dir.exists():
                for f in html_preview_dir.iterdir():
                    if f.is_file():
                        f.unlink()
        except Exception as e:
            self.add_debug(f"⚠️ HTML preview cleanup failed: {e}")

        # Clear Sokrates Multi-Agent state
        self.sokrates_critique = ""
        self.sokrates_pro_args = ""
        self.sokrates_contra_args = ""
        self.show_sokrates_panel = False
        self.debate_round = 0
        self.debate_user_interjection = ""
        self.debate_in_progress = False

        self.add_debug("🗑️ Chat + Images + Audio + HTML Preview + Sokrates cleared")

        # Session speichern (leerer Chat)
        self._save_current_session()

    def share_chat(self):
        """Share chat history - copy to clipboard as formatted text

        Handles multi-agent debate messages correctly:
        - Regular messages: (user_msg, ai_msg) where user_msg is non-empty
        - Sokrates/AIfred refinements: ("", ai_msg) where ai_msg starts with agent marker
        """
        if not self.chat_history:
            self.add_debug("⚠️ No chat to share")
            return

        # Format chat history as readable text
        lines = ["═" * 50, "🎩 AIfred Intelligence - Chat Export", "═" * 50, ""]

        message_num = 0
        for user_msg, ai_msg in self.chat_history:
            ai_msg_stripped = ai_msg.strip()

            # Determine message type based on content (new marker format)
            is_sokrates = ai_msg_stripped.startswith("🏛️")
            is_alfred_refinement = ai_msg_stripped.startswith("🎩[")
            is_summary = ai_msg_stripped.startswith("[📊 Komprimiert") or ai_msg_stripped.startswith("[📊 Compressed")
            has_user_input = bool(user_msg and user_msg.strip())

            if has_user_input:
                # Regular user message followed by AI response
                message_num += 1
                lines.append(f"👤 User ({message_num}):")
                lines.append(user_msg)
                lines.append("")

            # Skip empty AI responses (e.g., when Sokrates answers directly)
            if not ai_msg_stripped:
                continue

            # Determine AI label based on message type
            if is_summary:
                # Summary (compressed messages) - use special marker
                lines.append("📊 [Komprimierte History]:")
                lines.append(ai_msg)
            elif is_sokrates:
                # Sokrates message - already has proper header with emoji
                lines.append(ai_msg)
            elif is_alfred_refinement:
                # AIfred refinement - already has proper header
                lines.append(ai_msg)
            elif has_user_input:
                # Regular AIfred response to user question
                lines.append(f"🤖 AIfred ({message_num}):")
                lines.append(ai_msg)
            else:
                # AI-only message without user input (shouldn't happen often)
                lines.append("🤖 AIfred:")
                lines.append(ai_msg)

            lines.append("")
            lines.append(CONSOLE_SEPARATOR)
            lines.append("")

        # Remove trailing separator (last 3 lines: empty, separator, empty)
        if len(lines) >= 3 and lines[-2] == CONSOLE_SEPARATOR:
            lines = lines[:-3]
            lines.append("")  # Keep one trailing newline

        chat_text = "\n".join(lines)

        # Sicheres Escaping via JSON (verhindert XSS)
        import json
        escaped_text = json.dumps(chat_text)

        # Copy to clipboard via JavaScript
        # JSON-escaped string ist sicher gegen XSS (kein Template Literal nötig)
        js_script = f"""
        (async () => {{
            try {{
                await navigator.clipboard.writeText({escaped_text});
                console.log('Chat copied to clipboard');
            }} catch (err) {{
                console.error('Failed to copy:', err);
            }}
        }})();
        """

        self.add_debug(f"📋 Chat copied to clipboard ({len(self.chat_history)} messages)")
        return rx.call_script(js_script)

    # ============================================================
    # Session Persistence (Cookie-based device identification)
    # ============================================================

    def handle_device_id_loaded(self, device_id: str):
        """
        Callback nach Cookie-Read via rx.call_script().

        Wird aufgerufen wenn das JavaScript die Device-ID aus dem Cookie gelesen hat.
        Lädt bestehende Session oder erstellt neue.
        """
        # Guard: Nur einmal ausführen (Retry-Callback nach 2s überspringen)
        if self._session_initialized:
            return  # Kein Debug-Log für Retry-Callback
        self._session_initialized = True

        from .lib.session_storage import load_session, generate_device_id
        from .lib.browser_storage import set_device_id_script

        # Validiere device_id Format (muss 32 hex chars sein)
        import re
        is_valid_id = device_id and re.match(r'^[a-f0-9]{32}$', device_id)

        if device_id == "NEW" or not device_id or not is_valid_id:
            # New device or invalid ID - generate new Device-ID
            if device_id and not is_valid_id:
                self.add_debug(f"⚠️ Invalid Device-ID ({device_id[:8]}...), generating new one")
            self.device_id = generate_device_id()
            self.session_restored = False
            self.add_debug(f"🆕 New session: {self.device_id[:8]}...")
            console_separator()  # File log
            self.debug_messages.append("────────────────────")  # UI
            return rx.call_script(set_device_id_script(self.device_id))

        # Bekanntes Gerät - versuche Session zu laden
        self.device_id = device_id
        session = load_session(device_id)

        if session and session.get("data"):
            self._restore_session(session)
            self.session_restored = True
            msg_count = len(self.chat_history)
            self.add_debug(f"✅ Session loaded: {device_id[:8]}... ({msg_count} messages)")
        else:
            self.session_restored = False
            self.add_debug(f"🆕 Empty session: {device_id[:8]}...")

        # Separator after session restore
        console_separator()  # File log
        self.debug_messages.append("────────────────────")  # UI

    def handle_tts_callback(self, result: str):
        """
        Callback nach TTS rx.call_script() Ausführung.

        Wird aufgerufen wenn das JavaScript das TTS-Script ausgeführt hat.
        Dient hauptsächlich zum Debugging.
        """
        self.add_debug(f"🔊 TTS callback received: {result}")

    def _restore_session(self, session: dict):
        """
        Stellt Chat-History aus gespeicherter Session wieder her.

        Args:
            session: Session-Dict mit "data" Feld
        """
        data = session.get("data", {})

        # Chat-History wiederherstellen
        # WICHTIG: JSON serialisiert Tuples als Listen, hier zurückkonvertieren!
        if "chat_history" in data and data["chat_history"]:
            self.chat_history = [tuple(msg) for msg in data["chat_history"]]

        if "chat_summaries" in data and data["chat_summaries"]:
            # Falls chat_summaries existiert (für zukünftige Erweiterung)
            pass  # Aktuell nicht in State gespeichert

    def _save_current_session(self):
        """
        Speichert aktuelle Session auf Server.

        Wird nach jeder Chat-Änderung aufgerufen (Auto-Save).
        Nur speichern wenn device_id vorhanden (Session initialisiert).
        """
        if not self.device_id:
            return

        from .lib.session_storage import update_chat_data
        update_chat_data(
            device_id=self.device_id,
            chat_history=self.chat_history,
            chat_summaries=None  # Aktuell nicht persistiert
        )

    # ============================================================
    # Image Upload Handlers
    # ============================================================

    async def handle_image_upload(self, files: List[rx.UploadFile]):
        """Handle image file uploads - keeps original filename"""
        async for _ in self._process_image_upload(files, from_camera=False):
            yield

    async def handle_camera_upload(self, files: List[rx.UploadFile]):
        """Handle camera uploads - shortens filename to Image_001.jpg"""
        async for _ in self._process_image_upload(files, from_camera=True):
            yield

    async def _process_image_upload(self, files: List[rx.UploadFile], from_camera: bool = False):
        """Internal handler for image uploads with validation (async generator for UI updates)"""
        from .lib.vision_utils import (
            validate_image_file,
            encode_image_to_base64,
            resize_image_if_needed
        )

        # Show loading state immediately
        self.is_uploading_image = True
        yield  # Update UI to show spinner

        try:
            # Check if vision model selected
            if not self.vision_model:
                self.image_upload_warning = "⚠️ Please select a Vision model in settings first."
                self.add_debug("⚠️ Image upload blocked: No vision model selected")
                return

            # Check if vision_model is in the vision models cache (metadata-validated)
            # Compare IDs, not display names
            if self.vision_model_id not in self.vision_models_cache:
                self.image_upload_warning = "⚠️ Selected Vision model doesn't support images. Please choose a different Vision model from the dropdown."
                self.add_debug("⚠️ Image upload blocked: Non-vision model selected")
                return

            # Clear previous warning
            self.image_upload_warning = ""

            # Check max images limit
            if len(self.pending_images) + len(files) > self.max_images_per_message:
                self.image_upload_warning = f"⚠️ Maximum {self.max_images_per_message} images per message"
                return

            for file in files:
                # Read file content
                content = await file.read()

                # Validate
                valid, error = validate_image_file(file.filename, len(content))
                if not valid:
                    self.image_upload_warning = error
                    continue

                # Resize if needed (save bandwidth/VRAM)
                resized_content = resize_image_if_needed(content)

                # Encode to base64
                base64_data = encode_image_to_base64(resized_content)

                # Create data URL for preview
                data_url = f"data:image/jpeg;base64,{base64_data}"

                # Camera photos: Shorten to "Image_001.jpg" (browser names are unreadably long)
                # File uploads: Keep original filename
                if from_camera:
                    name_parts = file.filename.rsplit(".", 1)
                    if len(name_parts) == 2:
                        _, ext = name_parts
                        display_name = f"Image_{len(self.pending_images) + 1:03d}.{ext}"
                    else:
                        display_name = f"Image_{len(self.pending_images) + 1:03d}.jpg"
                else:
                    display_name = file.filename

                # Store
                self.pending_images.append({
                    "name": display_name,
                    "base64": base64_data,
                    "url": data_url,  # For UI preview
                    "size_kb": len(resized_content) // 1024
                })

                self.add_debug(f"📷 Image uploaded: {display_name} ({len(resized_content) // 1024} KB)")
                yield  # Update UI after each image

        finally:
            # Always hide loading state
            self.is_uploading_image = False
            yield  # Update UI to hide spinner

    def remove_pending_image(self, index: int):
        """Remove image from pending uploads"""
        if 0 <= index < len(self.pending_images):
            removed = self.pending_images.pop(index)
            self.add_debug(f"🗑️ Image removed: {removed['name']}")

            # Clear warning if it was about model compatibility
            if self.image_upload_warning.startswith("⚠️ Selected model"):
                self.image_upload_warning = ""

    def clear_pending_images(self):
        """Clear all pending images"""
        count = len(self.pending_images)
        self.pending_images = []
        self.image_upload_warning = ""
        if count > 0:
            self.add_debug(f"🗑️ {count} image(s) deleted")

    # ============================================================
    # IMAGE LIGHTBOX HANDLERS (for viewing images in chat history)
    # ============================================================

    def open_lightbox(self, image_url: str):
        """Opens lightbox to view image in full size"""
        self.lightbox_image_url = image_url
        self.lightbox_open = True

    def close_lightbox(self):
        """Closes the lightbox modal"""
        self.lightbox_open = False
        self.lightbox_image_url = ""

    # ============================================================
    # MULTI-AGENT HELP MODAL HANDLERS
    # ============================================================

    def open_multi_agent_help(self):
        """Opens the multi-agent modes help modal"""
        self.multi_agent_help_open = True

    def close_multi_agent_help(self):
        """Closes the multi-agent modes help modal"""
        self.multi_agent_help_open = False

    # ============================================================
    # IMAGE CROP HANDLERS
    # ============================================================

    def open_crop_modal(self, index: int):
        """Opens crop modal for image at index"""
        if 0 <= index < len(self.pending_images):
            self.crop_image_index = index
            self.crop_preview_url = self.pending_images[index]["url"]
            # Reset crop box to full image
            self.crop_box_x = 0.0
            self.crop_box_y = 0.0
            self.crop_box_width = 100.0
            self.crop_box_height = 100.0
            self.crop_modal_open = True
            self.add_debug(f"✂️ Crop-Modus geöffnet für: {self.pending_images[index]['name']}")

    def cancel_crop(self):
        """Schließt Modal ohne Änderung"""
        self.crop_modal_open = False
        self.crop_image_index = -1
        self.crop_preview_url = ""

    def update_crop_box(self, x: float, y: float, width: float, height: float):
        """Update Crop-Box Koordinaten (von JavaScript/UI)"""
        self.crop_box_x = max(0, min(100, x))
        self.crop_box_y = max(0, min(100, y))
        self.crop_box_width = max(1, min(100 - self.crop_box_x, width))
        self.crop_box_height = max(1, min(100 - self.crop_box_y, height))

    async def apply_crop(self):
        """Applies crop and updates the image in pending_images (Legacy, uses State coordinates)"""
        await self._do_apply_crop(self.crop_box_x, self.crop_box_y, self.crop_box_width, self.crop_box_height)

    async def apply_crop_with_coords(self, coords_json: str):
        """Applies crop with coordinates from JavaScript (JSON String)"""
        import json
        try:
            coords = json.loads(coords_json)
            x = float(coords.get("x", 0))
            y = float(coords.get("y", 0))
            width = float(coords.get("width", 100))
            height = float(coords.get("height", 100))
            await self._do_apply_crop(x, y, width, height)
        except Exception as e:
            self.add_debug(f"❌ Crop failed: {e}")
            self.cancel_crop()

    async def _do_apply_crop(self, x: float, y: float, width: float, height: float):
        """Interne Funktion: Führt den Crop mit gegebenen Koordinaten aus"""
        from .lib.vision_utils import crop_and_resize_image, encode_image_to_base64
        import base64

        if self.crop_image_index < 0 or self.crop_image_index >= len(self.pending_images):
            self.add_debug("❌ Crop failed: Invalid image index")
            self.cancel_crop()
            return

        image_data = self.pending_images[self.crop_image_index]

        # Original-Bytes aus Base64 dekodieren
        try:
            original_bytes = base64.b64decode(image_data["base64"])
        except Exception as e:
            self.add_debug(f"❌ Crop failed: {e}")
            self.cancel_crop()
            return

        # Original-Größe auslesen
        from PIL import Image
        import io
        original_img = Image.open(io.BytesIO(original_bytes))
        orig_width, orig_height = original_img.size

        # Crop anwenden (nur wenn nicht 100%)
        if x > 0.5 or y > 0.5 or width < 99.5 or height < 99.5:
            crop_box = {
                "x": x,
                "y": y,
                "width": width,
                "height": height
            }
            cropped_bytes = crop_and_resize_image(original_bytes, crop_box=crop_box)

            # Get pixel size from cropped image
            cropped_img = Image.open(io.BytesIO(cropped_bytes))
            px_width, px_height = cropped_img.size

            # Update pending_images
            new_base64 = encode_image_to_base64(cropped_bytes)
            new_url = f"data:image/jpeg;base64,{new_base64}"

            self.pending_images[self.crop_image_index] = {
                "name": image_data["name"],
                "base64": new_base64,
                "url": new_url,
                "size_kb": len(cropped_bytes) // 1024
            }

            self.add_debug(f"✂️ Image cropped: {width:.0f}% x {height:.0f}% → {px_width} x {px_height} px")
        else:
            self.add_debug(f"ℹ️ No crop needed: {image_data['name']}")

        # Close modal
        self.cancel_crop()

    def set_camera_available(self, available: bool):
        """Set camera availability based on browser capabilities (called from JavaScript)"""
        # Guard: Only log once per session to avoid duplicate messages from Reflex hydration
        if self._camera_detection_done:
            return  # Already logged once, skip duplicate from hydration

        self.camera_available = available
        self._camera_detection_done = True  # Mark as logged

        if available:
            self.add_debug("📷 Browser supports camera access")
        else:
            self.add_debug("⚠️ Browser does not support camera access")

    def set_is_mobile(self, is_mobile: bool):
        """Set mobile device detection based on User-Agent and touch capabilities (called from JavaScript)"""
        # Guard: Only log once per session to avoid duplicate messages from Reflex hydration
        if self._mobile_detection_done:
            return  # Already logged once, skip duplicate from hydration

        self.is_mobile = is_mobile
        self._mobile_detection_done = True  # Mark as logged

        device_type = "📱 Mobile" if is_mobile else "🖥️ Desktop"
        self.add_debug(f"{device_type} device detected")

    # ============================================================
    # AUDIO UPLOAD HANDLER (STT)
    # ============================================================

    async def handle_audio_upload(self, files: List[rx.UploadFile]):
        """Handle audio file uploads and transcribe with Whisper STT"""
        global _whisper_model

        # Lazy load Whisper model if not already loaded
        if _whisper_model is None:
            self.add_debug("🎤 Loading Whisper model...")
            initialize_whisper_model(self.whisper_model_key)
            if _whisper_model is None:
                self.add_debug("❌ Failed to load Whisper model")
                return

        # Validate file
        if not files or len(files) == 0:
            self.add_debug("⚠️ No audio file provided")
            return

        file = files[0]  # Only process first file

        # Validate audio file type
        allowed_extensions = [".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"]
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            self.add_debug(f"⚠️ Unsupported audio format: {file_ext}")
            return

        # Read file content
        content = await file.read()
        file_size_mb = len(content) / (1024 * 1024)

        # Size limit: 25 MB (Whisper can handle longer files)
        if file_size_mb > 25:
            from .lib.formatting import format_number
            self.add_debug(f"⚠️ Audio file too large: {format_number(file_size_mb, 1)} MB (max 25 MB)")
            return

        # Save to temporary file for Whisper processing
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name

        try:
            # Transcribe with Whisper
            from .lib.audio_processing import transcribe_audio
            from .lib.formatting import format_number

            # Show KB for small files, MB for larger files (German number format)
            if file_size_mb < 1:
                file_size_kb = len(content) / 1024
                size_display = f"{format_number(file_size_kb, 0)} KB"
            else:
                size_display = f"{format_number(file_size_mb, 1)} MB"

            self.add_debug(f"🎤 Transcribing audio: {file.filename} ({size_display})...")

            user_text, stt_time = transcribe_audio(tmp_path, _whisper_model, self.ui_language)

            if user_text:
                # Set transcribed text as user input
                self.current_user_input = user_text
                # German number format: 0,2s instead of 0.2s
                from .lib.formatting import format_number
                self.add_debug(f"✅ Transcription complete ({format_number(stt_time, 1)}s)")

                # Show Transcription Workflow
                if self.show_transcription:
                    # Mode: Text editieren → Manuell senden
                    self.add_debug("✏️ Text im Eingabefeld → Zum Editieren bereit")
                else:
                    # Mode: Direkt zur AI
                    self.add_debug("🚀 Sende Text direkt zur AI...")
                    # Forward yields from send_message() to update UI in real-time
                    async for _ in self.send_message():
                        yield  # Forward to UI for real-time updates
            else:
                self.add_debug("⚠️ Transcription returned empty text")

        except Exception as e:
            self.add_debug(f"❌ Audio transcription failed: {e}")
            log_message(f"❌ Audio transcription error: {e}")
        finally:
            # Clean up temporary file
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    async def _generate_tts_for_response(self, ai_response: str, autoplay: bool = True):
        """Generate TTS audio for AI response and store path for playback

        Args:
            ai_response: The AI response text to convert to speech
            autoplay: If True, set autoplay flag (respects user setting). If False, never autoplay.

        Note: This is a simple async function, NOT a generator. State updates happen directly.
        """
        try:
            from .lib.audio_processing import clean_text_for_tts, generate_tts
            from .lib.config import PROJECT_ROOT

            # Clean text: Remove <think> tags, emojis, markdown, URLs, timing info
            clean_text = clean_text_for_tts(ai_response)

            if not clean_text or len(clean_text.strip()) < 5:
                self.add_debug("🔇 TTS: Text zu kurz nach Bereinigung")
                return

            self.add_debug(f"🔊 TTS: Generating audio ({len(clean_text)} chars)...")

            # Generate TTS audio (returns URL path like "/tts_audio/audio_123.mp3")
            # Note: speed_choice is always 1.0 - tempo control happens in browser via tts_playback_rate
            audio_url = await generate_tts(
                text=clean_text,
                voice_choice=self.tts_voice,
                speed_choice=1.0,  # Always generate at normal speed
                tts_engine=self.tts_engine
            )

            if audio_url:
                # Verify file exists on disk (convert URL to filesystem path)
                # URL: /_upload/tts_audio/audio_123.mp3 -> uploaded_files/tts_audio/audio_123.mp3
                filename = audio_url.split("/")[-1]
                file_path = PROJECT_ROOT / "uploaded_files" / "tts_audio" / filename

                if os.path.exists(file_path):
                    # Store audio URL for playback
                    self.tts_audio_path = audio_url
                    # Increment counter to trigger frontend playback via rx.use_effect
                    self.tts_trigger_counter += 1
                    file_size_kb = os.path.getsize(file_path) / 1024
                    self.add_debug(f"✅ TTS: Audio generated ({file_size_kb:.1f} KB) → {audio_url}")
                    self.add_debug(f"🔊 TTS: Trigger counter incremented to {self.tts_trigger_counter}")
                    # Separator nach TTS-Ausgabe (Log-File + Debug-Konsole)
                    from aifred.lib.logging_utils import console_separator
                    console_separator()  # Schreibt in Log-File
                    self.add_debug("────────────────────")  # Zeigt in Debug-Console
                else:
                    self.tts_audio_path = ""
                    self.add_debug(f"⚠️ TTS: Audio file not found at {file_path}")
            else:
                self.tts_audio_path = ""
                self.add_debug("⚠️ TTS: Audio generation failed")

        except Exception as e:
            self.add_debug(f"❌ TTS Error: {e}")
            log_message(f"❌ TTS generation error: {e}")

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
                self.backend_id = self.backend_type  # Sync ID with type
                self.current_backend_label = self.available_backends_dict.get(self.backend_id, self.backend_id)
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
        import httpx
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
                        response = httpx.get(endpoint, timeout=2.0)

                        if response.status_code == 200:
                            # Parse JSON to verify API is actually ready
                            data = response.json()
                            # Build dict: {model_id: display_label}
                            unsorted_dict = {
                                m['name']: f"{m['name']} ({m['size'] / (1024**3):.1f} GB)"
                                for m in data.get("models", [])
                            }
                            # Sort by model family, then by size
                            self.available_models_dict = sort_models_grouped(unsorted_dict)
                            # Keep list for compatibility (DEPRECATED)
                            self.available_models = list(self.available_models_dict.values())

                            # Update global state
                            _global_backend_state["available_models"] = self.available_models

                            elapsed_time = (attempt + 1) * 0.5
                            self.add_debug(f"✅ Ollama ready after {elapsed_time:.1f}s ({len(self.available_models)} models found)")
                            ollama_ready = True
                            break
                    except httpx.RequestError:
                        pass  # Retry on connection error

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
                        # vLLM health check endpoint
                        response = httpx.get(
                            f"{self.backend_url}/health",
                            timeout=2.0
                        )

                        if response.status_code == 200:
                            elapsed_time = (attempt + 1) * 0.5
                            self.add_debug(f"✅ vLLM ready after {elapsed_time:.1f}s")
                            vllm_ready = True
                            break
                    except httpx.RequestError:
                        pass  # Retry on connection error

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
                    response = httpx.post(
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

                        load_response = httpx.post(
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
                                    verify_response = httpx.get(
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
                                except httpx.RequestError:
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

                except httpx.RequestError as e:
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

                # Update available models list with sizes
                self.available_models = [f"{model.name} ({model.size_gb:.1f} GB)" for model in gguf_models_list]
                _global_backend_state["available_models"] = self.available_models

                self.add_debug(f"✅ Found {len(gguf_models)} GGUF models")
                yield

                # Restart KoboldCPP with current model (extract pure name for lookup)
                pure_model_name = self.selected_model_id  # Pure ID
                if pure_model_name in gguf_models:
                    self.add_debug(f"🚀 Restarting KoboldCPP with {pure_model_name}...")
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

    def set_calibrate_extended(self, value: bool):
        """Toggle RoPE 2x extended calibration mode and save to cache"""
        self.calibrate_extended = value
        mode = "RoPE 2x" if value else "Native"
        self.add_debug(f"🎚️ Calibration mode: {mode}")

        # Save to VRAM cache (per-model setting)
        if self.selected_model_id:
            from .lib.model_vram_cache import set_use_extended_for_model, get_ollama_calibrated_max_context
            set_use_extended_for_model(self.selected_model_id, value)

            # Warn if no calibration exists for this mode
            if value:
                # Check if extended calibration exists
                extended_ctx = get_ollama_calibrated_max_context(self.selected_model_id, extended=True)
                if extended_ctx is None:
                    self.add_debug("⚠️ No RoPE 2x calibration found - please calibrate first!")
            else:
                # Check if native calibration exists
                native_ctx = get_ollama_calibrated_max_context(self.selected_model_id, extended=False)
                if native_ctx is None:
                    self.add_debug("⚠️ No native calibration found - please calibrate first!")

    async def calibrate_context(self):
        """
        Calibrate maximum context window for current Ollama model.

        Uses binary search with /api/ps to find the largest context
        that fits entirely in VRAM without CPU offloading.

        If calibrate_extended=True, calibrates up to 2x native context (RoPE scaling).
        """
        if self.backend_id != "ollama":
            self.add_debug("⚠️ Calibration only available for Ollama")
            return

        if not self.selected_model_id:
            self.add_debug("⚠️ No model selected")
            return

        if self.is_calibrating:
            self.add_debug("⚠️ Calibration already in progress")
            return

        self.is_calibrating = True
        mode_label = "RoPE 2x" if self.calibrate_extended else "Native"
        self.add_debug(f"🔧 Starting {mode_label} calibration for {self.selected_model_id}...")
        yield

        try:
            from .backends import BackendFactory

            backend = BackendFactory.create(
                self.backend_type,
                base_url=self.backend_url
            )

            calibrated_ctx = None
            async for progress_msg in backend.calibrate_max_context_generator(
                self.selected_model_id,
                extended=self.calibrate_extended  # Pass extended flag
            ):
                # Check for result marker
                if progress_msg.startswith("__RESULT__:"):
                    calibrated_ctx = int(progress_msg.split(":")[1])
                else:
                    self.add_debug(f"📊 {progress_msg}")
                    yield  # Update UI after each progress message

            if calibrated_ctx:
                self.add_debug("   → Value will be used automatically on next inference")
                self.add_debug("─" * 40)

        except Exception as e:
            self.add_debug(f"❌ Calibration failed: {e}")

        finally:
            self.is_calibrating = False
            yield

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
            self.add_debug("🔄 Browser will reload in 0.5s...")

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

            # Get collection (must match name in vector_cache.py)
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
        from .lib.vision_utils import is_vision_model

        old_model = self.selected_model
        self.selected_model = model
        # CRITICAL: Sync selected_model_id from display label
        self.selected_model_id = extract_model_name(model)
        # Clear thinking mode warning when model changes
        self.thinking_mode_warning = ""
        self.add_debug(f"📝 Main-LLM: {model}")

        # Show calibration info for Ollama models
        self._show_model_calibration_info(self.selected_model_id)

        # Check if switching to non-vision model with pending images
        if len(self.pending_images) > 0:
            # Use ID directly - extract_model_name() not needed anymore
            if not await is_vision_model(self, self.selected_model_id):
                self.image_upload_warning = "⚠️ Selected model doesn't support images. Images will be ignored when sending."
            else:
                self.image_upload_warning = ""  # Clear warning

        # ALWAYS save settings first (fixes Ollama not saving model changes)
        self._save_settings()

        # Note: For Ollama, model unloading happens JUST BEFORE VRAM measurement
        # in calculate_practical_context() - not here. This ensures accurate VRAM
        # readings even if other processes use GPU memory between model selection
        # and actual inference.

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

            self.add_debug("🔄 Backend restart for model switch...")

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
                self.add_debug(f"✅ New model loaded: {model}")
            finally:
                # Hide loading spinner
                self.vllm_restarting = False
                yield  # Update UI to hide spinner

    def toggle_thinking_mode(self):
        """Toggle Qwen3 Thinking Mode"""
        self.enable_thinking = not self.enable_thinking
        mode_name = "Thinking Mode" if self.enable_thinking else "Non-Thinking Mode"
        self.add_debug(f"🧠 {mode_name} activated")
        self._save_settings()

    def toggle_yarn(self):
        """Toggle YaRN context extension"""
        self.enable_yarn = not self.enable_yarn
        status = "enabled" if self.enable_yarn else "disabled"
        self.add_debug(f"📏 YaRN Context Extension {status} (Factor: {self.yarn_factor}x)")
        if self.enable_yarn:
            self.add_debug("⚠️ Click 'Apply YaRN' to start backend with new factor!")
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
            self.add_debug(f"✅ YaRN factor set: {old_factor}x → {factor_float}x (~{estimated_context} tokens)")

            # Warn if factor is high (potential VRAM overflow)
            if factor_float > 2.0:
                self.add_debug(f"⚠️ High YaRN factor ({factor_float}x) may exceed VRAM → possible crash!")
                self.add_debug("💡 Tip: For VRAM issues, reduce factor or use more GPU RAM")

            # Force restart backend for YaRN change (vLLM/TabbyAPI)
            if self.backend_type in ["vllm", "tabbyapi"]:
                self.add_debug("🔄 Backend restart for YaRN change...")

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
                        self.add_debug(f"✅ Backend restarted (YaRN: {factor_float}x → {actual_factor}x after auto-calibration)")
                    else:
                        self.add_debug(f"✅ Backend restarted with YaRN {actual_factor}x")

                finally:
                    # Hide loading spinner
                    self.vllm_restarting = False
                    yield  # Update UI to hide spinner

        except ValueError:
            self.add_debug(f"❌ Invalid YaRN factor: {self.yarn_factor_input}")

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

    def set_temperature_mode_radio(self, value: str):
        """
        Set temperature mode from radio group (returns string directly)

        Args:
            value: "auto" or "manual"
        """
        self.temperature_mode = value
        self._save_settings()
        self.add_debug(f"🌡️ Temperature Mode: {value.title()}")

    def set_temperature_mode_from_display(self, display_value: str):
        """
        Set temperature mode from radio display value

        Args:
            display_value: Display string like "🤖 Auto (Intent-Detection)" or "✋ Manuell"
        """
        # Extract mode from display value
        if "Auto" in display_value:
            self.temperature_mode = "auto"
        else:
            self.temperature_mode = "manual"
        self._save_settings()
        self.add_debug(f"🌡️ Temperature Mode: {self.temperature_mode.title()}")

    def set_sokrates_temperature(self, temp: list[float]):
        """Set Sokrates temperature (from slider which returns list[float])"""
        self.sokrates_temperature = temp[0] if isinstance(temp, list) else temp
        self._save_settings()

    def set_sokrates_temperature_offset(self, offset: list[float]):
        """Set Sokrates temperature offset for Auto mode (from slider which returns list[float])"""
        self.sokrates_temperature_offset = offset[0] if isinstance(offset, list) else offset
        self._save_settings()
        self.add_debug(f"🌡️ Sokrates Offset: +{self.sokrates_temperature_offset:.1f}")

    def set_salomo_temperature(self, temp: list[float]):
        """Set Salomo temperature for Manual mode (from slider which returns list[float])"""
        self.salomo_temperature = temp[0] if isinstance(temp, list) else temp
        self._save_settings()

    def set_salomo_temperature_offset(self, offset: list[float]):
        """Set Salomo temperature offset for Auto mode (from slider which returns list[float])"""
        self.salomo_temperature_offset = offset[0] if isinstance(offset, list) else offset
        self._save_settings()
        self.add_debug(f"🌡️ Salomo Offset: +{self.salomo_temperature_offset:.1f}")

    def set_num_ctx_mode(self, mode: str):
        """
        Set num_ctx mode (NICHT in settings.json gespeichert - Reset bei jedem Start)

        Modes:
        - auto: Auto-Modus (nutzt Kalibrierung, extended wenn calibrate_extended=True)
        - manual: Manueller Wert aus num_ctx_manual
        """
        self.num_ctx_mode = mode
        self.add_debug(f"🎯 Context Mode: {mode}")
        # WICHTIG: Nicht in settings.json speichern!

    def set_num_ctx_mode_from_display(self, display_value: str):
        """Set num_ctx mode from UI display value"""
        # Map display text to mode (simplified: Auto or Manual)
        if "Manuell" in display_value or "Manual" in display_value:
            mode = "manual"
        else:  # "Auto" (default)
            mode = "auto"
        self.set_num_ctx_mode(mode)

    def set_num_ctx_manual(self, value: str):
        """Set manual num_ctx value for AIfred (only used when mode=manual)"""
        from .lib.config import NUM_CTX_MANUAL_MAX
        try:
            # Handle locale-formatted numbers and spaces (e.g., "1.472", "1,472", "1 472")
            clean_value = str(value).replace(".", "").replace(",", "").replace(" ", "").strip()
            if not clean_value:
                return  # Empty input, ignore
            num_value = int(clean_value)
            if num_value < 1:
                num_value = 1
            if num_value > NUM_CTX_MANUAL_MAX:
                num_value = NUM_CTX_MANUAL_MAX
            self.num_ctx_manual = num_value
            self.add_debug(f"🔧 Manual num_ctx (AIfred): {num_value:,}")
            # WICHTIG: Nicht in settings.json speichern!
        except (ValueError, TypeError):
            self.add_debug(f"❌ Ungültiger num_ctx Wert: {value}")

    def set_num_ctx_manual_sokrates(self, value: str):
        """Set manual num_ctx value for Sokrates (only used when mode=manual)"""
        from .lib.config import NUM_CTX_MANUAL_MAX
        try:
            clean_value = str(value).replace(".", "").replace(",", "").replace(" ", "").strip()
            if not clean_value:
                return
            num_value = int(clean_value)
            if num_value < 1:
                num_value = 1
            if num_value > NUM_CTX_MANUAL_MAX:
                num_value = NUM_CTX_MANUAL_MAX
            self.num_ctx_manual_sokrates = num_value
            self.add_debug(f"🔧 Manual num_ctx (Sokrates): {num_value:,}")
        except (ValueError, TypeError):
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

    # ===== Multi-Agent Settings =====

    def set_multi_agent_mode(self, mode: str):
        """Set multi-agent discussion mode"""
        self.multi_agent_mode = mode
        # Reset Sokrates panel when switching modes
        self.show_sokrates_panel = False
        self.sokrates_critique = ""
        self.sokrates_pro_args = ""
        self.sokrates_contra_args = ""
        self.debate_round = 0
        self._save_settings()

        mode_labels = {
            "standard": "Standard",
            "user_judge": "Critical Review",
            "auto_consensus": "Auto-Consensus",
            "devils_advocate": "Devil's Advocate"
        }
        self.add_debug(f"🤖 Discussion mode: {mode_labels.get(mode, mode)}")

    def set_max_debate_rounds(self, value: list[float]):
        """Set maximum debate rounds (from slider)"""
        self.max_debate_rounds = int(value[0])
        self._save_settings()
        self.add_debug(f"🔄 Max debate rounds: {self.max_debate_rounds}")

    def set_sokrates_model(self, model: str):
        """Set Sokrates LLM model for multi-agent debate"""
        self.sokrates_model = model
        # Extract pure model ID (remove size suffix)
        self.sokrates_model_id = extract_model_name(model)
        self._save_settings()
        if model:
            self.add_debug(f"🧠 Sokrates-LLM: {model}")
            # Show calibration info for Ollama models
            self._show_model_calibration_info(self.sokrates_model_id)
        else:
            self.add_debug("🧠 Sokrates-LLM: (wie Haupt-LLM)")

    def set_salomo_model(self, model: str):
        """Set Salomo LLM model for multi-agent debate"""
        self.salomo_model = model
        # Extract pure model ID (remove size suffix)
        self.salomo_model_id = extract_model_name(model)
        self._save_settings()
        if model:
            self.add_debug(f"👑 Salomo-LLM: {model}")
            # Show calibration info for Ollama models
            self._show_model_calibration_info(self.salomo_model_id)
        else:
            self.add_debug("👑 Salomo-LLM: (wie Haupt-LLM)")

    def queue_user_interjection(self, text: str):
        """Queue user input during active debate"""
        if self.debate_in_progress and text.strip():
            self.debate_user_interjection = text.strip()
            self.add_debug(f"💬 User-Einwurf gequeued: {text[:50]}...")

    def get_and_clear_user_interjection(self) -> str:
        """Get queued user interjection and clear it (called by orchestrator)"""
        interjection = self.debate_user_interjection
        self.debate_user_interjection = ""
        return interjection

    def reset_sokrates_state(self):
        """Reset all Sokrates-related runtime state"""
        self.sokrates_critique = ""
        self.sokrates_pro_args = ""
        self.sokrates_contra_args = ""
        self.show_sokrates_panel = False
        self.debate_round = 0
        self.debate_user_interjection = ""
        self.debate_in_progress = False

    def reset_salomo_state(self):
        """Reset all Salomo-related runtime state"""
        self.salomo_synthesis = ""
        self.show_salomo_panel = False

    def reset_multi_agent_state(self):
        """Reset all multi-agent runtime state (Sokrates + Salomo)"""
        self.reset_sokrates_state()
        self.reset_salomo_state()

    # ============================================================
    # GENERIC STREAMING HELPER (DRY - reusable for all LLM calls)
    # ============================================================

    async def _stream_llm_with_ui(
        self,
        llm_client,
        model: str,
        messages: list,
        options,
        target_var: str,
        source_label: str,
        history_index: int = None,
    ):
        """
        Generic LLM streaming helper with UI updates and metadata collection.

        Reusable for AIfred, Sokrates, Vision, etc.
        Uses the same chunk structure as the main chat_stream.

        Args:
            llm_client: LLMClient instance
            model: Model name/ID
            messages: List of message dicts
            options: LLMOptions
            target_var: State variable to update (e.g., "sokrates_critique")
            source_label: Label for metadata (e.g., "Sokrates", "Training data")
            history_index: Optional chat_history index for live updates

        Yields:
            For UI updates during streaming

        Sets self._stream_result after completion with:
            - text: Full response text
            - metadata: Formatted metadata string
            - metrics: Dict with time, tokens, tok_per_sec
        """
        import time
        from .lib.formatting import format_metadata, format_number

        full_response = ""
        token_count = 0
        start_time = time.time()
        ttft = None
        first_token = False

        async for chunk in llm_client.chat_stream(model, messages, options):
            if chunk["type"] == "content":
                # TTFT measurement
                if not first_token:
                    ttft = time.time() - start_time
                    # Guard against negative TTFT (WSL2 time sync issues)
                    if ttft < 0:
                        ttft = 0.0
                    first_token = True

                full_response += chunk["text"]
                token_count += 1

                # Update target state variable
                setattr(self, target_var, full_response)

                # Optionally update chat_history for live display
                if history_index is not None and history_index < len(self.chat_history):
                    user_msg = self.chat_history[history_index][0]
                    self.chat_history[history_index] = (user_msg, full_response)

                yield  # UI Update

            elif chunk["type"] == "done":
                metrics = chunk.get("metrics", {})
                token_count = metrics.get("tokens_generated", token_count)

        # Calculate final metrics
        inference_time = time.time() - start_time
        tokens_per_sec = token_count / inference_time if inference_time > 0 else 0

        # Build metadata footer (same format as AIfred)
        metadata = format_metadata(
            f"Inference: {format_number(inference_time, 1)}s    "
            f"{format_number(tokens_per_sec, 1)} tok/s    "
            f"Source: {source_label} ({model})"
        )

        # Store result for caller to access
        self._stream_result = {
            "text": full_response,
            "metadata": metadata,
            "metrics": {
                "time": inference_time,
                "tokens": token_count,
                "tok_per_sec": tokens_per_sec,
                "ttft": ttft
            }
        }

    async def set_automatik_model(self, model: str):
        """Set automatik model for decision and query optimization"""
        old_model = self.automatik_model
        self.automatik_model = model
        # CRITICAL: Sync automatik_model_id from display label
        self.automatik_model_id = extract_model_name(model)
        self.add_debug(f"⚡ Automatik-LLM: {model}")
        # Show calibration info for Ollama models
        self._show_model_calibration_info(self.automatik_model_id)
        self._save_settings()

        # vLLM/TabbyAPI: Auto-restart backend for model change
        if self.backend_type in ["vllm", "tabbyapi"] and old_model != model:
            self.add_debug("🔄 Backend restart for Automatik model switch...")
            await self.initialize_backend()
            self.add_debug("✅ New Automatik model loaded")

        # Note: Models are loaded on-demand during first inference (saves VRAM)
        # Context limit will be queried on first use (fast ~30ms) and cached by httpx

    async def set_vision_model(self, model: str):
        """Set vision model for OCR/image analysis"""
        self.vision_model = model
        # CRITICAL: Sync vision_model_id from display label (fixes Vision-LLM using wrong model)
        self.vision_model_id = extract_model_name(model)
        self.add_debug(f"👁️ Vision-LLM: {model}")
        # Show calibration info for Ollama models
        self._show_model_calibration_info(self.vision_model_id)
        self._save_settings()

        # Note: Vision model will be loaded on-demand when image is uploaded
        # No preloading needed here to save VRAM

    # ===== NEW: ID-BASED MODEL HANDLERS FOR KEY-VALUE SYSTEM =====

    async def set_selected_model_by_id(self, model_id: str):
        """Set selected model using pure ID (new key-value system)"""
        # Update ID
        self.selected_model_id = model_id

        # Load per-model RoPE 2x toggle from cache
        if self.backend_id == "ollama":
            from .lib.model_vram_cache import get_use_extended_for_model
            self.calibrate_extended = get_use_extended_for_model(model_id)

        # Sync deprecated display variable
        display_label = self.available_models_dict.get(model_id, model_id)
        self.selected_model = display_label

        # Call existing handler with display label (reuses all logic)
        await self.set_selected_model(display_label)

    async def set_automatik_model_by_id(self, model_id: str):
        """Set automatik model using pure ID (new key-value system)"""
        # Update ID
        self.automatik_model_id = model_id

        # Sync deprecated display variable
        display_label = self.available_models_dict.get(model_id, model_id)
        self.automatik_model = display_label

        # Call existing handler with display label (reuses all logic)
        await self.set_automatik_model(display_label)

    async def set_vision_model_by_id(self, model_id: str):
        """Set vision model using pure ID (new key-value system)"""
        # Update ID
        self.vision_model_id = model_id

        # Sync deprecated display variable
        display_label = self.available_models_dict.get(model_id, model_id)
        self.vision_model = display_label

        # Call existing handler with display label (reuses all logic)
        await self.set_vision_model(display_label)

    # ============================================================
    # USER NAME SETTINGS
    # ============================================================

    def set_user_name(self, name: str):
        """Set user name (called on every keystroke)"""
        self.user_name = name

    def save_user_name(self, name: str):
        """Save user name when input loses focus"""
        self.user_name = name.strip()
        # Sync to prompt_loader for automatic injection into system prompts
        from .lib.prompt_loader import set_user_name
        set_user_name(self.user_name)
        if self.user_name:
            self.add_debug(f"👤 User name: {self.user_name}")
        self._save_settings()

    # ============================================================
    # TTS/STT SETTINGS
    # ============================================================

    def toggle_tts(self):
        """Toggle TTS on/off"""
        self.enable_tts = not self.enable_tts
        self.add_debug(f"🔊 TTS: {'enabled' if self.enable_tts else 'disabled'}")
        self._save_settings()

    def set_tts_engine(self, engine: str):
        """Set TTS engine and restore saved voice for this engine"""
        self.tts_engine = engine
        self.add_debug(f"🔊 TTS Engine: {engine}")

        # Restore user's saved voice preference for this engine (calls _switch_tts_voice_for_language)
        # This will either restore the saved voice or fallback to defaults
        self._switch_tts_voice_for_language(self.ui_language)

        self._save_settings()

    def set_tts_voice(self, voice: str):
        """Set TTS voice"""
        self.tts_voice = voice
        self.add_debug(f"🔊 TTS Voice: {voice}")
        self._save_settings()

    # Note: set_tts_speed removed - generation always at 1.0, tempo via browser playback rate

    def toggle_tts_autoplay(self):
        """Toggle TTS auto-play"""
        self.tts_autoplay = not self.tts_autoplay
        self.add_debug(f"🔊 TTS Auto-Play: {'enabled' if self.tts_autoplay else 'disabled'}")
        self._save_settings()

    def set_tts_playback_rate(self, rate: str):
        """Set TTS playback rate (browser-side only, TTS generation stays at 1.0)"""
        self.tts_playback_rate = rate
        self.add_debug(f"🔊 TTS Tempo: {rate}")
        self._save_settings()
        # Apply rate to current audio player via JavaScript
        rate_value = rate.replace("x", "")
        return rx.call_script(f"setTtsPlaybackRate({rate_value})")

    async def resynthesize_tts(self):
        """Re-synthesize TTS for the last AI response"""
        if not self.chat_history:
            self.add_debug("⚠️ TTS Re-Synth: Keine Antwort vorhanden")
            return

        # Get last AI response from chat history
        _, last_ai_response = self.chat_history[-1]
        if not last_ai_response or not last_ai_response.strip():
            self.add_debug("⚠️ TTS Re-Synth: Letzte Antwort ist leer")
            return

        # FIRST: Stop any currently playing audio to avoid overlap
        yield rx.call_script("stopTts()")

        self.add_debug("🔄 TTS Re-Synth: Generiere Audio neu...")

        # Generate TTS for last response
        # State changes (tts_audio_path, tts_trigger_counter) auto-propagate to frontend
        await self._generate_tts_for_response(last_ai_response, autoplay=True)

    # TODO: clear_tts_autoplay removed - TTS Playback will be reimplemented

    def set_whisper_model(self, model_display_name: str):
        """Set Whisper model and reload.

        Args:
            model_display_name: Display name from dropdown (e.g., "small (466MB, bessere Qualität, multilingual)")
        """
        global _whisper_model
        # Extract key from display name (e.g., "small (466MB, ...)" -> "small")
        model_key = model_display_name.split("(")[0].strip() if "(" in model_display_name else model_display_name
        self.whisper_model_key = model_key
        self.add_debug(f"🎤 Whisper Model: {model_key} (reload required)")
        # Reload Whisper model with new selection
        _whisper_model = None  # Clear old model
        initialize_whisper_model(model_key)
        self._save_settings()

    # REMOVED: toggle_whisper_device - Device is now configured in config.py
    # Whisper always runs on CPU to preserve GPU VRAM for LLM inference

    def toggle_show_transcription(self):
        """Toggle show transcription mode"""
        self.show_transcription = not self.show_transcription
        mode = "Text editieren" if self.show_transcription else "Direkt senden"
        self.add_debug(f"🎤 Transkription: {mode}")
        self._save_settings()

    def toggle_audio_recording(self):
        """Toggle audio recording (calls JavaScript MediaRecorder)"""
        return rx.call_script("toggleRecording()")

    def set_ui_language(self, lang: str):
        """Set UI language and switch TTS voice to matching language"""
        if lang in ["de", "en"]:
            self.ui_language = lang
            # Update global locale for number formatting
            from .lib.formatting import set_ui_locale
            set_ui_locale(lang)
            # Update research_mode_display to match new language
            from .lib import TranslationManager
            self.research_mode_display = TranslationManager.get_research_mode_display(self.research_mode, lang)
            self.add_debug(f"🌐 UI Language changed to: {lang}")

            # Auto-switch TTS voice to matching language
            self._switch_tts_voice_for_language(lang)

            # Save to settings
            self._save_settings()
        else:
            self.add_debug(f"❌ Invalid language: {lang}. Use 'de' or 'en'")

    def _get_engine_key(self) -> str:
        """Get engine key for config lookup (edge, piper, espeak)"""
        if "Piper" in self.tts_engine:
            return "piper"
        elif "eSpeak" in self.tts_engine:
            return "espeak"
        else:
            return "edge"

    def _switch_tts_voice_for_language(self, lang: str):
        """Switch TTS voice to appropriate language voice for current engine.

        Priority:
        1. User's saved preference for this engine/language (from assistant_settings.json)
        2. Default voice from TTS_DEFAULT_VOICES config
        """
        from .lib.config import TTS_DEFAULT_VOICES, EDGE_TTS_VOICES, PIPER_VOICES, ESPEAK_VOICES
        from .lib.settings import load_settings

        engine_key = self._get_engine_key()

        # Get voice dictionary for current engine
        if engine_key == "piper":
            voice_dict = PIPER_VOICES
        elif engine_key == "espeak":
            voice_dict = ESPEAK_VOICES
        else:
            voice_dict = EDGE_TTS_VOICES

        # Priority 1: Check for user's saved preference
        saved_settings = load_settings() or {}
        user_voices = saved_settings.get("tts_voices_per_language", {})
        user_voice = user_voices.get(engine_key, {}).get(lang)

        if user_voice and user_voice in voice_dict:
            old_voice = self.tts_voice
            self.tts_voice = user_voice
            self.add_debug(f"🔊 TTS Voice restored (user pref): {old_voice} → {user_voice}")
            return

        # Priority 2: Use default voice from config
        default_voice = TTS_DEFAULT_VOICES.get(engine_key, {}).get(lang)

        if default_voice and default_voice in voice_dict:
            old_voice = self.tts_voice
            self.tts_voice = default_voice
            self.add_debug(f"🔊 TTS Voice auto-switched: {old_voice} → {default_voice}")
            self._save_settings()
        else:
            self.add_debug(f"⚠️ No default {lang} voice found for {engine_key}")

    def get_text(self, key: str):
        """Get translated text based on current UI language"""
        from .lib import TranslationManager
        return TranslationManager.get_text(key, self.ui_language)
