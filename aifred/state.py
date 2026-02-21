"""
Reflex State Management for AIfred Intelligence

Main state for chat, settings, and backend management
"""

import reflex as rx
from typing import List, Any, Dict, TypedDict
import uuid
import os
import asyncio
import json
from .lib import (
    initialize_debug_log,
    log_message,
    console_separator,
    set_language
)
from .lib.logging_utils import CONSOLE_SEPARATOR
from .lib.context_manager import strip_thinking_blocks
from .lib import config
from .lib.config import (
    EDGE_TTS_VOICES, PIPER_VOICES, ESPEAK_VOICES,
    SOKRATES_TEMPERATURE_OFFSET, SALOMO_TEMPERATURE_OFFSET,
    DEBUG_MESSAGES_MAX,
    CLOUD_API_PROVIDERS,
    DEFAULT_TOP_K, DEFAULT_TOP_P, DEFAULT_MIN_P, DEFAULT_REPEAT_PENALTY,
    LLAMASERVER_DEFAULT_TEMPERATURE, LLAMASERVER_DEFAULT_TOP_K,
    LLAMASERVER_DEFAULT_TOP_P, LLAMASERVER_DEFAULT_MIN_P,
    LLAMASERVER_DEFAULT_REPEAT_PENALTY
)
from .backends.cloud_api import is_cloud_api_configured
from .lib.vllm_manager import vLLMProcessManager
from .lib.model_manager import (
    sort_models_grouped,
    is_backend_compatible
    # NOTE: backend_supports_dynamic_models not imported - State has own @rx.var implementation
)
from .lib.gpu_monitor import round_to_nominal_vram
from .lib.multi_agent import (
    run_sokrates_direct_response,
    run_salomo_direct_response,
    run_sokrates_analysis,
    run_tribunal,
)

# ============================================================
# TTS Audio Broker - Bridge between create_task and Frontend
# ============================================================
# TypedDicts for Reflex (foreach requires typed dicts)
# ============================================================

class FailedSourceDict(TypedDict):
    """A single failed source entry"""
    url: str
    error: str
    method: str

class ChatMessage(TypedDict):
    """Single chat message in new dict-based format.

    Each message is standalone - no more (user, ai) tuples.
    User messages and assistant messages are separate entries.
    """
    role: str           # "user" | "assistant" | "system" (for summaries)
    content: str        # Message content (with markers for UI display)
    agent: str          # "" | "aifred" | "sokrates" | "salomo"
    mode: str           # "" | "direct" | "synthesis" | "tribunal" | "refinement" | ...
    round_num: int | None  # None/0 = no round, 1+ = round number
    metadata: Dict[str, Any]  # ttft, inference_time, tokens_per_sec, etc.
    timestamp: str      # ISO timestamp
    # Web research sources (top-level for Reflex UI access - also in metadata for export)
    used_sources: List[Dict[str, Any]]    # [{"url": str, "word_count": int}]
    failed_sources: List[Dict[str, Any]]  # [{"url": str, "error": str, "method": str}]
    # Audio replay (top-level for Reflex UI access)
    has_audio: bool  # True if audio_urls is non-empty
    audio_urls_json: str  # JSON string of audio URLs (for JS playback)


# ============================================================
# Vector Cache - Now in aifred/lib/vector_cache.py
# ============================================================
from .lib.vector_cache import initialize_vector_cache  # noqa: E402


# ============================================================
# Module-Level Backend State (Global across all sessions)
# ============================================================
# Prevents re-initialization on page reload
# Backend is initialized once at server startup
_global_backend_initialized = False
_global_backend_state: dict[str, Any] = {
    "backend_type": None,
    "backend_url": None,
    "aifred_model": None,
    "automatik_model": None,
    "available_models": [],
    "gpu_info": None,
    "vllm_manager": None,  # Global vLLM process manager (persists across reloads)
}

# Lock to prevent race conditions during backend initialization
# (e.g., two browser tabs starting simultaneously)
_backend_init_lock = asyncio.Lock()


# ============================================================
# Whisper STT - Now in aifred/lib/audio_processing.py
# ============================================================
# Import from audio_processing module
from .lib.audio_processing import (  # noqa: E402
    initialize_whisper_model,
    unload_whisper_model,
    get_whisper_model
)

# Module-level storage for DashScope WebSocket TTS instances (keyed by session_id).
# Cannot be stored in Reflex state because WebSocket/SSLSocket objects are not serializable.
_dashscope_rt_instances: dict[str, object] = {}


class AIState(rx.State):
    """Main application state"""

    # Chat History - New dict-based format (each message standalone)
    chat_history: List[Dict[str, Any]] = []  # List[ChatMessage] - each message is a dict
    llm_history: List[Dict[str, str]] = []  # [{"role": "user/assistant/system", "content": "..."}] - LLM komprimiert
    current_user_input: str = ""
    current_user_message: str = ""  # The message currently being processed
    current_ai_response: str = ""  # Shared streaming buffer for all agents (AIfred, Sokrates, Salomo)
    current_agent: str = ""  # Current streaming agent: "aifred" | "sokrates" | "salomo" | ""
    is_generating: bool = False
    is_compressing: bool = False  # Shows if history compression is running
    is_uploading_image: bool = False  # Shows spinner during image upload
    is_calibrating: bool = False  # Shows spinner during context calibration

    # Per-Model RoPE Scaling Factors (1.0x, 1.5x, 2.0x)
    aifred_rope_factor: float = 1.0      # AIfred Main-LLM RoPE scaling
    automatik_rope_factor: float = 1.0   # Automatik-LLM RoPE scaling
    sokrates_rope_factor: float = 1.0    # Sokrates-LLM RoPE scaling
    salomo_rope_factor: float = 1.0      # Salomo-LLM RoPE scaling
    vision_rope_factor: float = 1.0      # Vision-LLM RoPE scaling

    # Per-Model Parameters (loaded from VRAM cache on model selection)
    aifred_max_context: int = 0          # Calibrated max context tokens
    aifred_is_hybrid: bool = False       # CPU+GPU offload mode
    aifred_supports_thinking: bool | None = None  # Reasoning capability (None=unknown)

    sokrates_max_context: int = 0
    sokrates_is_hybrid: bool = False
    sokrates_supports_thinking: bool | None = None

    salomo_max_context: int = 0
    salomo_is_hybrid: bool = False
    salomo_supports_thinking: bool | None = None

    # Per-Agent Personality Toggles (True = Butler/Philosopher/Judge style, False = factual)
    aifred_personality: bool = True      # 🎩 AIfred Butler style
    sokrates_personality: bool = True    # 🏛️ Sokrates philosophical style
    salomo_personality: bool = True      # 👑 Salomo judge style

    # Per-Agent Reasoning Toggles (True = reasoning prompt injected into system prompt)
    aifred_reasoning: bool = True        # 💭 AIfred step-by-step reasoning
    sokrates_reasoning: bool = True      # 💭 Sokrates step-by-step reasoning
    salomo_reasoning: bool = True        # 💭 Salomo step-by-step reasoning

    # Per-Agent Thinking Toggles (True = enable_thinking sent to backend API)
    # Separate from reasoning: thinking = model-internal CoT, reasoning = prompt injection
    aifred_thinking: bool = True         # 🧠 AIfred model thinking (CoT)
    sokrates_thinking: bool = True       # 🧠 Sokrates model thinking (CoT)
    salomo_thinking: bool = True         # 🧠 Salomo model thinking (CoT)

    # Per-Agent Sampling Parameters
    aifred_top_k: int = DEFAULT_TOP_K
    aifred_top_p: float = DEFAULT_TOP_P
    aifred_min_p: float = DEFAULT_MIN_P
    aifred_repeat_penalty: float = DEFAULT_REPEAT_PENALTY
    sokrates_top_k: int = DEFAULT_TOP_K
    sokrates_top_p: float = DEFAULT_TOP_P
    sokrates_min_p: float = DEFAULT_MIN_P
    sokrates_repeat_penalty: float = DEFAULT_REPEAT_PENALTY
    salomo_top_k: int = DEFAULT_TOP_K
    salomo_top_p: float = DEFAULT_TOP_P
    salomo_min_p: float = DEFAULT_MIN_P
    salomo_repeat_penalty: float = DEFAULT_REPEAT_PENALTY
    sampling_reset_key: int = 0          # UI key counter to force re-mount on reset

    # Per-Agent Speed Mode Toggles (llamacpp only: swap to -speed YAML variant)
    # True = aggressive tensor-split, 32K context; False = balanced split, max context
    aifred_speed_mode: bool = False      # ⚡ AIfred speed variant
    sokrates_speed_mode: bool = False    # ⚡ Sokrates speed variant
    salomo_speed_mode: bool = False      # ⚡ Salomo speed variant
    # Whether a speed variant exists for the currently selected model (from VRAM cache)
    aifred_has_speed_variant: bool = False
    sokrates_has_speed_variant: bool = False
    salomo_has_speed_variant: bool = False

    # Image Upload State
    pending_images: List[Dict[str, str]] = []  # [{"name": "img.jpg", "path": "/abs/path.jpg", "url": "/_upload/...", "size_kb": int}]
    image_upload_warning: str = ""  # Warning message if non-vision model selected
    max_images_per_message: int = 5  # Limit concurrent uploads
    camera_available: bool = False  # True if browser supports camera access (set by JavaScript)
    _camera_detection_done: bool = False  # Internal flag to prevent duplicate logging from Reflex hydration
    _last_settings_mtime: float = 0.0  # Last seen settings.json mtime (for multi-browser sync)

    # Web Research Sources State (for current request - shown in UI)
    # all_sources: Combined list sorted by rank_index for UI display
    all_sources: List[Dict[str, Any]] = []  # [{"url": str, "success": bool, "rank_index": int, ...}]
    used_sources: List[Dict[str, Any]] = []  # [{"url": "...", "word_count": int}]
    failed_sources: List[Dict[str, str]] = []  # [{"url": "...", "error": "...", "method": "..."}]
    # Pending sources for current request (will be embedded in AI response)
    _pending_used_sources: List[Dict[str, Any]] = []
    _pending_failed_sources: List[Dict[str, str]] = []

    # Image Crop State
    crop_modal_open: bool = False  # Show crop modal?
    crop_image_index: int = -1  # Which image is being cropped (index in pending_images)
    crop_preview_url: str = ""  # Data URL for crop preview (large image in modal)
    crop_box_x: float = 0.0  # Crop box position X in percent (0-100)
    crop_box_y: float = 0.0  # Crop box position Y in percent (0-100)
    crop_box_width: float = 100.0  # Crop box width in percent (0-100)
    crop_box_height: float = 100.0  # Crop box height in percent (0-100)
    crop_rotation: int = 0  # Cumulative rotation in degrees (0, 90, 180, 270)

    # Image Lightbox State (for viewing images in chat history)
    lightbox_open: bool = False  # Show lightbox modal?
    lightbox_image_url: str = ""  # Data URL for lightbox image

    # Multi-Agent Help Modal
    multi_agent_help_open: bool = False  # Show help modal?

    # Reasoning/Thinking Help Modal
    reasoning_thinking_help_open: bool = False

    # Session Management (Chat History Picker)
    available_sessions: List[Dict[str, Any]] = []  # List of sessions from list_sessions()
    current_session_title: str = ""  # Title of current session (for display)

    # Authentication State
    logged_in_user: str = ""  # Currently logged in username (empty = not logged in)
    login_dialog_open: bool = True  # Blocks UI until authenticated (closed by auto-login or manual login)
    login_mode: str = "login"  # "login" or "register"
    login_username: str = ""  # Input field for username
    login_password: str = ""  # Input field for password
    login_error: str = ""  # Error message to display

    # Backend Settings
    backend_type: str = "ollama"  # "ollama", "vllm", "tabbyapi", "cloud_api"
    backend_id: str = "ollama"  # NEW: Pure backend ID (synced with backend_type for compatibility)
    current_backend_label: str = "Ollama"  # NEW: Display label for current backend (synced with backend_id)
    backend_url: str = config.DEFAULT_OLLAMA_URL  # Default Ollama URL

    # Cloud API Settings (only relevant when backend_type == "cloud_api")
    cloud_api_provider: str = "qwen"  # "claude", "qwen", "kimi"
    cloud_api_provider_label: str = "Qwen (DashScope)"  # Display label
    cloud_api_key_configured: bool = False  # True if API key is set (from ENV or runtime)

    # Backend ID/Label Mapping (static - all possible backends)
    available_backends_dict: Dict[str, str] = {
        "ollama": "Ollama",
        "llamacpp": "llama.cpp",
        "tabbyapi": "TabbyAPI",
        "vllm": "vLLM",
        "cloud_api": "Cloud APIs",
    }

    # NOTE: Models loaded from settings.json first, fallback to config.py only if settings don't exist
    aifred_model: str = ""  # Initialized in on_load() from settings.json or config.py
    aifred_model_id: str = ""  # NEW: Pure model ID (synced with aifred_model)

    available_models: List[str] = []  # List of display labels for UI dropdowns
    available_models_dict: Dict[str, str] = {}  # NEW: {model_id: display_label}

    vision_models_cache: List[str] = []  # Cached list of vision model IDs (populated by initialize_backend)
    available_vision_models_list: List[str] = []  # NEW: Display names for vision models (synced with vision_models_cache)

    # Automatik-LLM (for decision and query optimization)
    # NOTE: Loaded from settings.json first, fallback to config.py only if settings don't exist
    automatik_model: str = ""  # Initialized in on_load() from settings.json or config.py
    automatik_model_id: str = ""  # NEW: Pure model ID (synced with automatik_model)

    # Vision-LLM (for image analysis/OCR - specialized for structured data extraction)
    # NOTE: Loaded from settings.json first, fallback to first available vision model
    vision_model: str = ""  # Initialized in on_load() from settings.json or auto-detect
    vision_model_id: str = ""  # NEW: Pure model ID (synced with vision_model)

    # LLM Options
    temperature: float = 0.3  # Default: low temperature for factual responses
    temperature_mode: str = "auto"  # "auto" (Intent-Detection) | "manual" (user slider)
    sokrates_temperature: float = 0.5  # Sokrates temperature (manual mode only)
    sokrates_temperature_offset: float = SOKRATES_TEMPERATURE_OFFSET  # From config.py
    salomo_temperature: float = 0.5  # Salomo temperature (manual mode only)
    salomo_temperature_offset: float = SALOMO_TEMPERATURE_OFFSET  # From config.py
    num_ctx: int = 32768

    # Context Window Control (NOT saved in settings.json - reset on every start)
    # Per-Agent manual values (used only when corresponding _enabled flag is True)
    num_ctx_manual_aifred: int = 4096  # Manual value for AIfred - Ollama default
    num_ctx_manual_sokrates: int = 4096  # Manual value for Sokrates
    num_ctx_manual_salomo: int = 4096  # Manual value for Salomo
    # Per-Agent manual toggle (True = use manual value, False = use auto-calibrated from VRAM cache)
    num_ctx_manual_aifred_enabled: bool = False
    num_ctx_manual_sokrates_enabled: bool = False
    num_ctx_manual_salomo_enabled: bool = False

    # Vision Context Window Control (PERSISTENT - saved to settings.json)
    # Unlike Chat LLMs, Vision context is saved because it significantly affects OCR quality vs speed
    vision_num_ctx_enabled: bool = False  # True = use manual value, False = use calibrated
    vision_num_ctx: int = 32768  # Manual context value (default: 32K - reasonable for most OCR)

    # Cached Model Metadata (to avoid repeated API calls)
    _automatik_model_context_limit: int = 0  # Cached context limit for automatik model
    _min_agent_context_limit: int = 0  # Cached min context limit of AIfred/Sokrates/Salomo (for session-load display)

    # Research Settings
    research_mode: str = "automatik"  # "quick", "deep", "automatik", "none"
    research_mode_display: str = "✨ Automatik (KI entscheidet)"  # UI display value

    # Multi-Agent Settings - PERSISTENT (saved to settings.json)
    multi_agent_mode: str = "standard"  # "standard", "critical_review", "auto_consensus", "devils_advocate", "tribunal"
    max_debate_rounds: int = 3  # Maximum rounds for auto_consensus/tribunal (UI slider: 1-10)
    consensus_type: str = "majority"  # "majority" (2/3) or "unanimous" (3/3) - only for auto_consensus
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
    user_gender: str = "male"  # "male" or "female" - for proper salutation (Herr/Frau)

    # TTS/STT Settings
    enable_tts: bool = False
    tts_voice: str = "AIfred"  # Default voice - XTTS custom voice
    tts_speed: float = 1.0  # Speed multiplier (1.0 = normal, browser playback handles tempo)
    tts_engine: str = "xtts"  # TTS engine key (default: XTTS)
    tts_autoplay: bool = True  # Auto-play TTS audio after generation (user setting)
    tts_playback_rate: str = "1.0x"  # Browser playback rate (1.0 = neutral, speed via Agent Settings)
    tts_pitch: str = "1.0"  # Pitch adjustment (0.8 = lower, 1.0 = normal, 1.2 = higher)
    # Per-Agent TTS Voice Settings (for Multi-Agent mode with distinct voices)
    # Format: agent_id -> {"voice": str, "speed": str, "pitch": str, "enabled": bool}
    # Agents: aifred (default), sokrates, salomo
    tts_agent_voices: Dict[str, Dict[str, Any]] = {
        "aifred": {"voice": "★ AIfred", "speed": "1.0x", "pitch": "1.0", "enabled": True},
        "sokrates": {"voice": "★ Sokrates", "speed": "1.0x", "pitch": "1.0", "enabled": True},
        "salomo": {"voice": "Baldur Sanjin", "speed": "1.0x", "pitch": "1.0", "enabled": True},
    }
    # XTTS voices cache - refreshed when engine changes to XTTS
    xtts_voices_cache: List[str] = []
    # XTTS CPU Mode - Force CPU inference (slower but saves GPU VRAM for LLM)
    xtts_force_cpu: bool = False
    # MOSS-TTS device ("cuda", "cpu", or "" if not running)
    # Used by context_manager/context_utils for VRAM reservation
    moss_tts_device: str = ""

    @rx.var(deps=["ui_language"], auto_deps=False)
    def tts_engines(self) -> List[str]:
        """Available TTS engines for dropdown selection (translated labels)."""
        from .lib.config import TTS_ENGINE_KEYS
        from .lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"
        return [t(f"tts_engine_{key}", lang=lang) for key in TTS_ENGINE_KEYS]

    @rx.var
    def xtts_gpu_enabled(self) -> bool:
        """Computed: True when GPU mode, False when CPU mode."""
        return not self.xtts_force_cpu
    whisper_model_key: str = "small"  # Whisper model key (tiny/base/small/medium/large)
    # whisper_device removed - now configured in config.py (WHISPER_DEVICE)
    show_transcription: bool = False  # Show transcribed text for editing before sending
    # NOTE: Whisper model is now managed in aifred/lib/audio_processing.py (use get_whisper_model())
    tts_audio_path: str = ""  # Path to generated TTS audio file
    tts_trigger_counter: int = 0  # Incremented to trigger TTS playback in frontend
    # TTS Audio Queue - for sequential playback of multiple agent responses
    # Queue URLs are added when add_agent_panel() generates TTS
    # Frontend plays queue sequentially (first in, first out)
    tts_audio_queue: List[str] = []  # Queue of audio URLs to play
    tts_queue_version: int = 0  # Incremented when queue changes (triggers frontend update)
    # Streaming TTS - send sentences to TTS as they are generated
    tts_streaming_enabled: bool = True  # Enable streaming TTS (vs waiting for full response)
    _tts_sentence_buffer: str = ""  # Accumulates tokens until sentence boundary detected
    _tts_short_carry: str = ""  # Short sentences (< 3 words) waiting to merge with next
    _tts_in_think_block: bool = False  # True when inside <think>...</think> block
    _tts_streaming_active: bool = False  # True during active streaming session
    _tts_streaming_agent: str = "aifred"  # Current agent for voice selection (aifred/sokrates/salomo)
    _pending_audio_urls: List[str] = []  # Audio URLs collected during streaming, for message assignment
    tts_regenerating: bool = False  # True while TTS regeneration is in progress (for spinner)
    # TTS Task Tracking - ensures finalize waits for all TTS tasks to complete
    _pending_tts_requests: List[str] = []  # Request-IDs of TTS tasks in flight (via create_task)
    _completed_tts_urls: Dict[str, str] = {}  # {request_id: audio_url} - completed TTS results
    # TTS Ordering - ensures sentences are pushed to queue in order (critical for cloud APIs)
    _tts_next_seq: int = 0  # Next sequence number to assign to a sentence
    _tts_push_seq: int = 0  # Next sequence number expected for queue push
    _tts_order_buffer: Dict[int, tuple] = {}  # {seq: (audio_url, playback_rate, request_id)} - completed but not yet pushed
    # Session Persistence (Cookie-based session identification)
    session_id: str = ""  # Session ID from cookie (32 hex chars)
    session_restored: bool = False  # True if chat history was loaded from session
    _session_initialized: bool = False  # Guard against multiple session restore callbacks
    _on_load_running: bool = False  # Guard against multiple on_load() calls
    _last_detected_language: str = ""  # Last detected language from Intent Detection (for title generation)

    # Backend Status
    backend_healthy: bool = False
    backend_info: str = ""
    model_count: int = 0  # Number of available models (for localized UI display)
    backend_switching: bool = False  # True during backend switch (UI will be disabled)
    backend_initializing: bool = True  # True during initial initialization (shows Loading Spinner)
    vllm_restarting: bool = False  # True during vLLM restart (model switch/YaRN)

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
    gpu_all_names: List[str] = []
    available_backends: List[str] = ["ollama", "llamacpp", "tabbyapi", "vllm", "cloud_api"]  # Filtered by GPU compatibility + cloud_api (always available)
    available_backends_list: List[str] = ["Ollama", "llama.cpp", "TabbyAPI", "vLLM", "Cloud APIs"]  # Display names (synced with available_backends)

    @rx.var
    def gpu_display_text(self) -> str:
        """
        Format GPU info for UI display.
        - Single GPU: "Tesla P40 (Compute 6.1, 24 GB)"
        - Same multi-GPU: "2x Tesla P40 (Compute 6.1, 48 GB total)"
        - Mixed multi-GPU: "Tesla P40 + Quadro RTX 8000 (70 GB total)"
        """
        if not self.gpu_detected:
            return ""

        if self.gpu_count == 1:
            return f"{self.gpu_name} (Compute {self.gpu_compute_cap}, {self.gpu_vram_gb} GB)"

        # Multi-GPU: check if all same model
        unique_names = list(dict.fromkeys(self.gpu_all_names))
        if len(unique_names) == 1:
            return f"{self.gpu_count}x {unique_names[0]} (Compute {self.gpu_compute_cap}, {self.gpu_vram_gb} GB total)"
        return f"{' + '.join(unique_names)} ({self.gpu_vram_gb} GB total)"

    @rx.var
    def gpu_compatible_text(self) -> str:
        """Compatible backends as display text (excluding cloud_api)."""
        display_names = {
            "ollama": "Ollama",
            "llamacpp": "llama.cpp",
            "vllm": "vLLM",
            "tabbyapi": "TabbyAPI",
        }
        names = [display_names.get(b, b) for b in self.available_backends if b != "cloud_api"]
        return ", ".join(names) if names else ""

    @rx.var
    def grouped_backends_display(self) -> List[str]:
        """
        Return backend list with headers and separators for dropdown display.

        Structure:
        - Header: "🔧 Universelle Kompatibilität (GGUF)"
        - ollama
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
        return config.BACKEND_LABELS.get(backend_id, backend_id)

    @rx.var
    def backend_supports_dynamic_models(self) -> bool:
        """
        Check if current backend supports dynamic model switching.
        Used to disable Automatik-LLM dropdown for vLLM.
        """
        # Default to True if no backend initialized yet
        if self.backend_type not in ["vllm", "tabbyapi"]:
            return True

        # vLLM can't switch models
        return self.backend_type not in ["vllm"]

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

    @rx.var
    def rope_factor_display(self) -> str:
        """Display value for AIfred RoPE factor select (e.g., '1.0x', '2.0x')"""
        return f"{self.aifred_rope_factor}x"

    @rx.var
    def automatik_rope_display(self) -> str:
        """Display value for Automatik RoPE factor select"""
        return f"{self.automatik_rope_factor}x"

    @rx.var
    def sokrates_rope_display(self) -> str:
        """Display value for Sokrates RoPE factor select"""
        return f"{self.sokrates_rope_factor}x"

    @rx.var
    def salomo_rope_display(self) -> str:
        """Display value for Salomo RoPE factor select"""
        return f"{self.salomo_rope_factor}x"

    @rx.var
    def vision_rope_display(self) -> str:
        """Display value for Vision RoPE factor select"""
        return f"{self.vision_rope_factor}x"

    # ===== NEW: KEY-VALUE COMPUTED PROPERTIES FOR MOBILE NATIVE SELECTS =====

    # Backend Computed Properties
    @rx.var
    def backend_label(self) -> str:
        """Get display label for current backend (e.g., 'ollama' -> 'Ollama')"""
        return self.available_backends_dict.get(self.backend_id, self.backend_id)

    @rx.var
    def available_backends_display(self) -> List[str]:
        """Get list of backend display names (filtered by GPU compatibility)

        Returns display names like ["Ollama", "llama.cpp"] for use in native select.
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
        Format: [["ollama", "Ollama"], ["llamacpp", "llama.cpp"]]
        """
        return [[bid, label] for bid, label in self.available_backends_dict.items()
                if bid in self.available_backends]

    # Model Computed Properties
    @rx.var
    def aifred_model_label(self) -> str:
        """Get display label for selected model"""
        return self.available_models_dict.get(self.aifred_model_id, self.aifred_model_id)

    @rx.var
    def automatik_model_label(self) -> str:
        """Get display label for automatik model (empty = same as AIfred)"""
        if not self.automatik_model_id:
            return self.available_models_dict.get(self.aifred_model_id, self.aifred_model_id)
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

    @rx.var(deps=["available_models", "ui_language"], auto_deps=False)
    def sokrates_available_models(self) -> list[str]:
        """Model list with localized '(wie AIfred-LLM)' as first selectable option."""
        from .lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"
        return [t("sokrates_llm_same", lang=lang)] + list(self.available_models)

    @rx.var(deps=["available_models", "ui_language"], auto_deps=False)
    def salomo_available_models(self) -> list[str]:
        """Model list with localized '(wie AIfred-LLM)' as first selectable option."""
        from .lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"
        return [t("sokrates_llm_same", lang=lang)] + list(self.available_models)

    @rx.var(deps=["sokrates_model", "ui_language"], auto_deps=False)
    def sokrates_model_select_value(self) -> str:
        """Maps empty string (auto) to the localized sentinel label for the select."""
        from .lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"
        return t("sokrates_llm_same", lang=lang) if self.sokrates_model == "" else self.sokrates_model

    @rx.var(deps=["salomo_model", "ui_language"], auto_deps=False)
    def salomo_model_select_value(self) -> str:
        """Maps empty string (auto) to the localized sentinel label for the select."""
        from .lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"
        return t("sokrates_llm_same", lang=lang) if self.salomo_model == "" else self.salomo_model

    @rx.var(deps=["available_models", "ui_language"], auto_deps=False)
    def automatik_available_models(self) -> list[str]:
        """Model list with localized '(wie AIfred-LLM)' as first selectable option."""
        from .lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"
        return [t("sokrates_llm_same", lang=lang)] + list(self.available_models)

    @rx.var(deps=["automatik_model", "ui_language"], auto_deps=False)
    def automatik_model_select_value(self) -> str:
        """Maps empty string (auto) to the localized sentinel label for the select."""
        from .lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"
        return t("sokrates_llm_same", lang=lang) if self.automatik_model == "" else self.automatik_model

    @property
    def _effective_automatik_id(self) -> str:
        """Resolve Automatik model ID: empty or same base model as AIfred = follow AIfred exactly."""
        if not self.automatik_model_id:
            return self.aifred_model_id
        # If Automatik is explicitly set to AIfred's base model (while AIfred may be in speed
        # mode), follow AIfred's current model_id to avoid llama-swap cold-start swaps.
        if self.automatik_model_id == self.aifred_model_id.removesuffix("-speed"):
            return self.aifred_model_id
        return self.automatik_model_id

    @rx.var
    def is_unanimous_consensus(self) -> bool:
        """Check if consensus type is unanimous (for toggle state)"""
        return self.consensus_type == "unanimous"

    @rx.var(deps=["ui_language"], auto_deps=False)
    def speed_switch_tooltip(self) -> str:
        """Localized tooltip for the Ctx/Speed switch."""
        from .lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"
        return t("speed_switch_tooltip", lang=lang)

    @rx.var(deps=["consensus_type", "ui_language"], auto_deps=False)
    def consensus_toggle_tooltip(self) -> str:
        """Get tooltip text for consensus toggle based on current state and language"""
        from .lib.i18n import t
        if self.consensus_type == "unanimous":
            return t("consensus_toggle_tooltip_on", lang=self.ui_language)
        return t("consensus_toggle_tooltip_off", lang=self.ui_language)

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
            ["critical_review", TranslationManager.get_text("multi_agent_critical_review", self.ui_language)],
            ["auto_consensus", TranslationManager.get_text("multi_agent_auto_consensus", self.ui_language)],
            # ["devils_advocate", ...] - Deaktiviert v2.15.28: Pro/Contra jetzt in critical_review integriert
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

    @rx.var(deps=["tts_engine", "xtts_voices_cache"], auto_deps=False)
    def available_tts_voices(self) -> List[str]:
        """
        Returns list of available TTS voices for the current engine.
        Edge TTS, XTTS v2, Piper and eSpeak have different voice sets.

        Note: Uses auto_deps=False with explicit deps to disable automatic
        dependency detection (Reflex cannot introspect module-level imports).
        XTTS voices come from xtts_voices_cache (refreshed via _refresh_xtts_voices).
        """
        if self.tts_engine == "xtts":
            # Use cached voices (refreshed when engine changes to XTTS)
            if self.xtts_voices_cache:
                return self.xtts_voices_cache  # Already sorted by _refresh_xtts_voices
            # Fallback when service unavailable
            from .lib.config import XTTS_VOICES_FALLBACK, sort_voices_custom_first
            return sort_voices_custom_first(list(XTTS_VOICES_FALLBACK.keys()))
        elif self.tts_engine == "moss":  # MOSS-TTS (batch)
            from .lib.config import get_moss_voices, MOSS_TTS_VOICES_FALLBACK
            voices = get_moss_voices()
            if voices:
                return sorted(list(voices.keys()))
            return sorted(list(MOSS_TTS_VOICES_FALLBACK.keys()))
        elif self.tts_engine == "dashscope":
            from .lib.config import DASHSCOPE_VOICES, sort_voices_custom_first
            return sort_voices_custom_first(list(DASHSCOPE_VOICES.keys()))
        elif self.tts_engine == "piper":
            return sorted(list(PIPER_VOICES.keys()))
        elif self.tts_engine == "espeak":
            return sorted(list(ESPEAK_VOICES.keys()))
        else:
            return sorted(list(EDGE_TTS_VOICES.keys()))

    @rx.var(deps=["tts_audio_queue"], auto_deps=False)
    def tts_queue_json(self) -> str:
        """Returns TTS audio queue as JSON string for frontend.

        The frontend JavaScript reads this to update its local queue
        for sequential playback of multi-agent responses.
        """
        import json
        return json.dumps(self.tts_audio_queue)

    @rx.var(deps=["enable_tts"], auto_deps=False)
    def tts_player_visible(self) -> bool:
        """Returns True if TTS audio player should be visible.

        Player is visible when TTS is enabled (always shows player controls).
        """
        return self.enable_tts

    @rx.var(deps=["enable_tts", "tts_engine", "ui_language"], auto_deps=False)
    def tts_engine_or_off(self) -> str:
        """Dropdown value: translated engine label when TTS enabled, translated 'Off' when disabled."""
        from .lib.i18n import tts_key_to_label
        lang = self.ui_language if self.ui_language != "auto" else "de"
        return tts_key_to_label(self.tts_engine, lang=lang) if self.enable_tts else tts_key_to_label("off", lang=lang)

    def _refresh_xtts_voices(self):
        """Refresh XTTS voices from Docker service.

        Also validates that agent voices are in the available list.
        If a saved voice is not found, it resets to the default.
        """
        from .lib.config import get_xtts_voices, TTS_AGENT_VOICE_DEFAULTS
        voices = get_xtts_voices()
        if voices:
            from .lib.config import sort_voices_custom_first
            self.xtts_voices_cache = sort_voices_custom_first(list(voices.keys()))
            self.add_debug(f"🎤 XTTS: {len(voices)} voices loaded")

            # Validate agent voices - reset if not in available list
            xtts_defaults = TTS_AGENT_VOICE_DEFAULTS.get("xtts", {})
            for agent in ["aifred", "sokrates", "salomo"]:
                current_voice = self.tts_agent_voices.get(agent, {}).get("voice", "")
                if current_voice and current_voice not in self.xtts_voices_cache:
                    # Voice not found - use default
                    default_voice = xtts_defaults.get(agent, {}).get("voice", "")
                    if default_voice:
                        self.tts_agent_voices[agent]["voice"] = default_voice
                        self.add_debug(f"⚠️ XTTS: Reset {agent} voice to {default_voice}")

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

            # Log platform info
            import platform
            kernel = platform.release()
            is_wsl = "microsoft" in kernel.lower()
            is_windows = os.name == "nt"
            if is_wsl:
                env_label = "WSL2 (WDDM — VRAM swapping possible)"
            elif is_windows:
                env_label = "Windows (WDDM — VRAM swapping possible)"
            else:
                env_label = "Native Linux (no VRAM swapping)"
            log_message(f"🖥️ Platform: {platform.system()} {kernel} — {env_label}")

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
                    # Round each GPU individually to avoid mixed-GPU rounding errors
                    total_vram_gb = sum(
                        round_to_nominal_vram(v) for v in gpu_info.all_gpu_vram_mb
                    ) if gpu_info.all_gpu_vram_mb else round_to_nominal_vram(gpu_info.vram_mb)

                    unique_names = list(dict.fromkeys(gpu_info.all_gpu_names))
                    if gpu_info.gpu_count == 1:
                        log_message(f"✅ GPU: {gpu_info.name} (Compute {gpu_info.compute_capability}, {total_vram_gb} GB)")
                    elif len(unique_names) == 1:
                        log_message(f"✅ GPU: {gpu_info.gpu_count}x {gpu_info.name} (Compute {gpu_info.compute_capability}, {total_vram_gb} GB total)")
                    else:
                        log_message(f"✅ GPU: {' + '.join(unique_names)} ({total_vram_gb} GB total)")

                    if gpu_info.unsupported_backends:
                        log_message(f"⚠️ Incompatible backends: {', '.join(gpu_info.unsupported_backends)}")
                    if gpu_info.warnings:
                        for warning in gpu_info.warnings[:2]:
                            log_message(f"⚠️ {warning}")
                else:
                    log_message("ℹ️ No GPU detected or nvidia-smi not available")
            except Exception as e:
                log_message(f"⚠️ GPU detection failed: {e}")

            # Unload all Ollama models to ensure clean VRAM slate
            # (Ollama may have models loaded from previous sessions)
            try:
                from .backends.ollama import OllamaBackend
                ollama = OllamaBackend()
                success, unloaded = await ollama.unload_all_models(wait_for_stability=False)
                if unloaded:
                    log_message(f"🧹 Startup: Unloaded {len(unloaded)} model(s) from VRAM: {', '.join(unloaded)}")
                else:
                    log_message("🧹 Startup: No models to unload (VRAM clean)")
                await ollama.client.aclose()
            except Exception as e:
                log_message(f"ℹ️ Ollama not available for startup cleanup: {e}")

            _global_backend_initialized = True
            print("✅ Global initialization complete")

        # PER-SESSION INITIALIZATION (every user/tab/reload)
        # Guard against multiple parallel on_load() calls (ASGI race condition)
        if self._on_load_running:
            print("⏭️ on_load already running, skipping duplicate call")
            return
        self._on_load_running = True

        # Load session list immediately (before backend init which can take time)
        self.refresh_session_list()

        if not self._backend_initialized:
            print("📱 Initializing session...")

            # Initialize global UI locale for number formatting
            from .lib.formatting import set_ui_locale
            set_ui_locale(self.ui_language)

            # Load saved settings
            from .lib.settings import load_settings
            saved_settings = load_settings()
            _had_backend_settings = False

            if saved_settings:
                # Use saved settings
                self.backend_type = saved_settings.get("backend_type", self.backend_type)
                self.backend_id = self.backend_type  # Sync ID with type
                self.current_backend_label = self.available_backends_dict.get(self.backend_id, self.backend_id)

                # Cloud API provider
                saved_provider = saved_settings.get("cloud_api_provider", self.cloud_api_provider)
                if saved_provider in CLOUD_API_PROVIDERS:
                    self.cloud_api_provider = saved_provider
                    self.cloud_api_provider_label = CLOUD_API_PROVIDERS[saved_provider]["name"]

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

                # Load UI language and update global locale + prompt language
                saved_ui_lang = saved_settings.get("ui_language", self.ui_language)
                if saved_ui_lang in ["de", "en"]:
                    self.ui_language = saved_ui_lang
                    set_ui_locale(saved_ui_lang)
                    set_language(saved_ui_lang)  # Sync prompt language

                # Load user name and gender
                self.user_name = saved_settings.get("user_name", self.user_name)
                self.user_gender = saved_settings.get("user_gender", self.user_gender)
                # Sync to prompt_loader for automatic injection into system prompts
                from .lib.prompt_loader import set_user_name, set_user_gender, init_system_prompt_cache, set_personality_enabled, set_reasoning_enabled
                set_user_name(self.user_name)
                set_user_gender(self.user_gender)

                # Load and sync personality toggles to prompt_loader
                self.aifred_personality = saved_settings.get("aifred_personality", self.aifred_personality)
                self.sokrates_personality = saved_settings.get("sokrates_personality", self.sokrates_personality)
                self.salomo_personality = saved_settings.get("salomo_personality", self.salomo_personality)
                set_personality_enabled("aifred", self.aifred_personality)
                set_personality_enabled("sokrates", self.sokrates_personality)
                set_personality_enabled("salomo", self.salomo_personality)

                # Persist personality defaults if not in settings (ensures they survive restarts)
                if "aifred_personality" not in saved_settings or "sokrates_personality" not in saved_settings or "salomo_personality" not in saved_settings:
                    self._save_personality_settings()

                # Load and sync reasoning toggles to prompt_loader
                self.aifred_reasoning = saved_settings.get("aifred_reasoning", self.aifred_reasoning)
                self.sokrates_reasoning = saved_settings.get("sokrates_reasoning", self.sokrates_reasoning)
                self.salomo_reasoning = saved_settings.get("salomo_reasoning", self.salomo_reasoning)
                set_reasoning_enabled("aifred", self.aifred_reasoning)
                set_reasoning_enabled("sokrates", self.sokrates_reasoning)
                set_reasoning_enabled("salomo", self.salomo_reasoning)

                # Persist reasoning defaults if not in settings (ensures they survive restarts)
                if "aifred_reasoning" not in saved_settings or "sokrates_reasoning" not in saved_settings or "salomo_reasoning" not in saved_settings:
                    self._save_reasoning_settings()

                # Load and sync thinking toggles to prompt_loader
                from .lib.prompt_loader import set_thinking_enabled
                self.aifred_thinking = saved_settings.get("aifred_thinking", self.aifred_thinking)
                self.sokrates_thinking = saved_settings.get("sokrates_thinking", self.sokrates_thinking)
                self.salomo_thinking = saved_settings.get("salomo_thinking", self.salomo_thinking)
                set_thinking_enabled("aifred", self.aifred_thinking)
                set_thinking_enabled("sokrates", self.sokrates_thinking)
                set_thinking_enabled("salomo", self.salomo_thinking)

                # Persist thinking defaults if not in settings
                if "aifred_thinking" not in saved_settings:
                    self._save_thinking_settings()

                # Note: Sampling params (top_k, top_p, min_p, repeat_penalty) NOT loaded
                # from settings — they reset to YAML defaults on restart via _reset_agent_sampling()

                # Load speed mode toggles (llamacpp only, restored after model is loaded)
                self.aifred_speed_mode = saved_settings.get("aifred_speed_mode", False)
                self.sokrates_speed_mode = saved_settings.get("sokrates_speed_mode", False)
                self.salomo_speed_mode = saved_settings.get("salomo_speed_mode", False)

                # Load Vision settings (PERSISTENT - unlike Chat LLM num_ctx)
                self.vision_num_ctx_enabled = saved_settings.get("vision_num_ctx_enabled", self.vision_num_ctx_enabled)
                self.vision_num_ctx = saved_settings.get("vision_num_ctx", self.vision_num_ctx)

                # Initialize system prompt token cache (v2.14.0+)
                # This caches all prompt sizes for accurate compression calculations
                init_system_prompt_cache()

                # Load TTS/STT Settings
                self.enable_tts = saved_settings.get("enable_tts", self.enable_tts)
                # Note: tts_speed no longer loaded - generation always at 1.0
                saved_engine = saved_settings.get("tts_engine", self.tts_engine)
                # Migrate old display-string format to key format
                if saved_engine and len(saved_engine) > 10:
                    engine_map = {"XTTS": "xtts", "MOSS": "moss", "DashScope": "dashscope",
                                  "Piper": "piper", "eSpeak": "espeak", "Edge": "edge"}
                    for name, key in engine_map.items():
                        if name in saved_engine:
                            saved_engine = key
                            break
                self.tts_engine = saved_engine
                self.xtts_force_cpu = saved_settings.get("xtts_force_cpu", self.xtts_force_cpu)
                self.tts_autoplay = saved_settings.get("tts_autoplay", self.tts_autoplay)
                self.tts_streaming_enabled = saved_settings.get("tts_streaming_enabled", self.tts_streaming_enabled)
                self.tts_playback_rate = saved_settings.get("tts_playback_rate", self.tts_playback_rate)
                self.tts_pitch = saved_settings.get("tts_pitch", self.tts_pitch)
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

                # Load per-agent TTS voice settings for current engine
                self._restore_agent_voices_for_engine(engine_key)

                # Load per-engine TTS toggles (overrides global autoplay/streaming)
                self._restore_tts_toggles_for_engine(engine_key)

                # Refresh XTTS voices from Docker service if XTTS engine is selected
                if self.tts_engine == "xtts":
                    self._refresh_xtts_voices()

                # Load vLLM YaRN Settings (only enable/disable, factor always starts at 1.0)
                self.enable_yarn = saved_settings.get("enable_yarn", self.enable_yarn)
                # yarn_factor is NOT loaded - always starts at 1.0, system calibrates maximum
                self.yarn_factor = 1.0
                self.yarn_factor_input = "1.0"
                # NOTE: vllm_max_tokens and vllm_native_context are NEVER loaded from settings!
                # They are calculated dynamically on every vLLM startup based on VRAM availability

                # Load UI Settings
                self.auto_refresh_enabled = saved_settings.get("auto_scroll", self.auto_refresh_enabled)

                # Load Multi-Agent Settings
                self.multi_agent_mode = saved_settings.get("multi_agent_mode", self.multi_agent_mode)
                self.max_debate_rounds = saved_settings.get("max_debate_rounds", self.max_debate_rounds)
                self.consensus_type = saved_settings.get("consensus_type", self.consensus_type)
                # Load Sokrates model (pure ID, display name set after models load)
                self.sokrates_model_id = saved_settings.get("sokrates_model", "")
                self.sokrates_model = self.sokrates_model_id  # Will be updated with display name after models load

                # Load Salomo model (pure ID, display name set after models load)
                self.salomo_model_id = saved_settings.get("salomo_model", "")
                self.salomo_model = self.salomo_model_id  # Will be updated with display name after models load
                self.salomo_temperature = saved_settings.get("salomo_temperature", self.salomo_temperature)
                self.salomo_temperature_offset = saved_settings.get("salomo_temperature_offset", self.salomo_temperature_offset)

                # Load per-backend models (all 5 agents: AIfred, Automatik, Vision, Sokrates, Salomo)
                backend_models = saved_settings.get("backend_models", {})
                _had_backend_settings = self.backend_id in backend_models
                if _had_backend_settings:
                    backend_data = backend_models[self.backend_id]
                    # Load pure IDs (backward compatible - extract from old display format)
                    selected_raw = backend_data.get("aifred_model", "")
                    automatik_raw = backend_data.get("automatik_model", "")
                    vision_raw = backend_data.get("vision_model", "")
                    sokrates_raw = backend_data.get("sokrates_model", "")
                    salomo_raw = backend_data.get("salomo_model", "")

                    # Settings store pure model IDs (dict keys)
                    self.aifred_model_id = selected_raw
                    self.automatik_model_id = automatik_raw
                    self.vision_model_id = vision_raw
                    self.sokrates_model_id = sokrates_raw
                    self.salomo_model_id = salomo_raw

                    # Load all model parameters from cache on startup (CRITICAL: prevents 400 errors!)
                    if self.backend_id == "ollama":
                        from .lib.model_vram_cache import get_model_parameters

                        if self.aifred_model_id:
                            params = get_model_parameters(self.aifred_model_id)
                            self.aifred_rope_factor = params["rope_factor"]
                            self.aifred_max_context = params["max_context"]
                            self.aifred_is_hybrid = params["is_hybrid"]
                            self.aifred_supports_thinking = params["supports_thinking"]

                        if self.sokrates_model_id:
                            params = get_model_parameters(self.sokrates_model_id)
                            self.sokrates_rope_factor = params["rope_factor"]
                            self.sokrates_max_context = params["max_context"]
                            self.sokrates_is_hybrid = params["is_hybrid"]
                            self.sokrates_supports_thinking = params["supports_thinking"]

                        if self.salomo_model_id:
                            params = get_model_parameters(self.salomo_model_id)
                            self.salomo_rope_factor = params["rope_factor"]
                            self.salomo_max_context = params["max_context"]
                            self.salomo_is_hybrid = params["is_hybrid"]
                            self.salomo_supports_thinking = params["supports_thinking"]

                    elif self.backend_id == "llamacpp":
                        from .lib.model_vram_cache import (
                            get_llamacpp_calibration,
                            get_thinking_support_for_model,
                            get_llamacpp_speed_split,
                        )

                        for agent, model_id in [
                            ("aifred", self.aifred_model_id),
                            ("sokrates", self.sokrates_model_id),
                            ("salomo", self.salomo_model_id),
                        ]:
                            if model_id:
                                setattr(self, f"{agent}_rope_factor", 1.0)
                                setattr(self, f"{agent}_max_context", get_llamacpp_calibration(model_id) or 0)
                                setattr(self, f"{agent}_is_hybrid", False)
                                setattr(self, f"{agent}_supports_thinking", get_thinking_support_for_model(model_id))
                                setattr(self, f"{agent}_has_speed_variant", get_llamacpp_speed_split(model_id) > 0)

                    # Sync deprecated variables (will be populated later after models load)
                    self.aifred_model = selected_raw
                    self.automatik_model = automatik_raw
                    self.vision_model = vision_raw
                    self.sokrates_model = sokrates_raw
                    self.salomo_model = salomo_raw

                self.add_debug(f"⚙️ Settings loaded (backend: {self.backend_type})")

                # Send TTS playback rate to JavaScript (after settings loaded)
                # Use setTimeout to ensure custom.js is loaded first
                rate_value = self.tts_playback_rate.replace("x", "")
                yield rx.call_script(f"setTimeout(() => {{ if (typeof setTtsPlaybackRate === 'function') setTtsPlaybackRate({rate_value}); }}, 100)")

            # Apply config.py defaults as final fallback (only if settings.json didn't provide values)
            backend_defaults = config.BACKEND_DEFAULT_MODELS.get(self.backend_type, {})

            if not self.aifred_model:
                self.aifred_model = backend_defaults.get("aifred_model", "")
                self.aifred_model_id = self.aifred_model  # Sync ID with display name
                if self.aifred_model:
                    self.add_debug(f"⚙️ Using default aifred_model from config.py: {self.aifred_model}")
                else:
                    self.add_debug("⚠️ No aifred_model configured")

            if not self.automatik_model and not _had_backend_settings:
                self.automatik_model = backend_defaults.get("automatik_model", "")
                self.automatik_model_id = self.automatik_model  # Sync ID with display name
                if self.automatik_model:
                    self.add_debug(f"⚙️ Using default automatik_model from config.py: {self.automatik_model}")
                else:
                    self.add_debug("⚠️ No automatik_model configured")

            if not self.vision_model:
                self.vision_model = backend_defaults.get("vision_model", "")
                self.vision_model_id = self.vision_model  # Sync ID with display name
                if self.vision_model:
                    self.add_debug(f"⚙️ Using default vision_model from config.py: {self.vision_model}")
                else:
                    self.add_debug("ℹ️ No vision_model configured - will auto-detect first available vision model")

            # Multi-Agent Models (optional - empty = use Main-LLM)
            if not self.sokrates_model_id:
                self.sokrates_model_id = backend_defaults.get("sokrates_model", "")
                self.sokrates_model = self.sokrates_model_id
                if self.sokrates_model_id:
                    self.add_debug(f"⚙️ Using default sokrates_model from config.py: {self.sokrates_model_id}")

            if not self.salomo_model_id:
                self.salomo_model_id = backend_defaults.get("salomo_model", "")
                self.salomo_model = self.salomo_model_id
                if self.salomo_model_id:
                    self.add_debug(f"⚙️ Using default salomo_model from config.py: {self.salomo_model_id}")

            # vLLM and TabbyAPI can only load ONE model at a time
            # Ensure automatik_model = aifred_model for these backends
            if self.backend_type in ["vllm", "tabbyapi"]:
                if self.automatik_model != self.aifred_model:
                    self.add_debug(f"⚠️ {self.backend_type} can only load one model - using {self.aifred_model} for both AIfred and Automatic")
                    self.automatik_model = self.aifred_model

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
                self.gpu_all_names = gpu_info.all_gpu_names

                # Calculate nominal VRAM (round each GPU individually)
                if gpu_info.all_gpu_vram_mb:
                    self.gpu_vram_gb = sum(round_to_nominal_vram(v) for v in gpu_info.all_gpu_vram_mb)
                else:
                    self.gpu_vram_gb = round_to_nominal_vram(gpu_info.vram_mb)

                # Show GPU info in debug console (use same logic as gpu_display_text)
                self.add_debug(f"🎮 GPU: {self.gpu_display_text}")

                # Filter available backends based on GPU compatibility
                # Only show backends that are actually compatible with the GPU
                if gpu_info.recommended_backends:
                    # Start with GPU-compatible backends
                    self.available_backends = gpu_info.recommended_backends.copy()
                    # Always add cloud_api (doesn't need GPU)
                    if "cloud_api" not in self.available_backends:
                        self.available_backends.append("cloud_api")
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

            # Authentication: Read username from cookie (async callback)
            # AFTER Backend-Init so chat history restore doesn't collide with loading
            if not self._session_initialized:
                from .lib.browser_storage import get_username_script
                print("🔐 Requesting username cookie from browser...")
                # Read username cookie and handle login
                yield rx.call_script(
                    get_username_script(),
                    callback=AIState.handle_username_loaded
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

            # Validate and sync aifred_model (use settings, not global state)
            if self.aifred_model_id and self.aifred_model_id in self.available_models_dict:
                self.aifred_model = self.available_models_dict[self.aifred_model_id]
            elif _global_backend_state.get("aifred_model_id") in self.available_models_dict:
                # Fallback to global state if settings model not found
                self.aifred_model_id = _global_backend_state["aifred_model_id"]
                self.aifred_model = self.available_models_dict[self.aifred_model_id]
            else:
                # Last resort: first available model
                first_id = next(iter(self.available_models_dict.keys()), "")
                self.aifred_model_id = first_id
                self.aifred_model = self.available_models_dict.get(first_id, first_id)

            # Validate and sync automatik_model (can be empty = use Main-LLM)
            if not self.automatik_model_id:
                # Empty = "same as AIfred-LLM" - keep empty
                self.automatik_model = ""
            elif self.automatik_model_id in self.available_models_dict:
                self.automatik_model = self.available_models_dict[self.automatik_model_id]
            elif _global_backend_state.get("automatik_model_id") in self.available_models_dict:
                self.automatik_model_id = _global_backend_state["automatik_model_id"]
                self.automatik_model = self.available_models_dict[self.automatik_model_id]
            else:
                # Model ID was set but model not found - clear it (same as AIfred)
                log_message(f"⚠️ Configured automatik model '{self.automatik_model_id}' not found, using same as AIfred")
                self.automatik_model_id = ""
                self.automatik_model = ""

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

            # vLLM can only load ONE model - ensure Automatik uses same as AIfred
            if self.backend_type == "vllm" and self.automatik_model_id:
                self.automatik_model = ""
                self.automatik_model_id = ""
                _global_backend_state["automatik_model"] = ""
                _global_backend_state["automatik_model_id"] = ""
                self._save_settings()

            # Check vLLM manager status if exists
            if self.backend_type == "vllm":
                vllm_manager = _global_backend_state.get("vllm_manager")
                if vllm_manager and vllm_manager.is_running():
                    self.add_debug("✅ vLLM server already running (restored from global state)")
                else:
                    self.add_debug("⚠️ vLLM manager exists but server not running")

            # TTS: Do NOT preload container on page reload — starts on first use

            # === RESET SAMPLING PARAMETERS TO YAML DEFAULTS ===
            # Temperature is preserved (loaded from settings.json in on_load)
            # Sampling params (top_k, top_p, min_p, repeat_penalty) reset to YAML values
            for agent in ["aifred", "sokrates", "salomo"]:
                self._reset_agent_sampling(agent, include_temperature=False)

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
            self.backend_url = config.BACKEND_URLS.get(self.backend_type, config.DEFAULT_OLLAMA_URL)

            # add_debug() already logs to file, so we only need one call
            self.add_debug(f"🔧 Creating backend: {self.backend_type}")
            # Detailed info only in log file (not in UI)
            log_message(f"   URL: {self.backend_url}")

            # SKIP health check - causes async deadlock in on_load context!
            # Assume backend is healthy and proceed
            self.backend_healthy = True
            self.backend_info = f"{self.backend_type} initializing..."
            self.add_debug(f"⚡ Backend: {self.backend_type} (skip health check)")

            # TTS: Do NOT preload container at startup — starts on first use
            # (ensure_*_ready is called in send_message and regenerate flows)

            # Load models using centralized discovery module
            from .lib.model_discovery import discover_models
            try:
                # Discover models based on backend type
                if self.backend_type in ["vllm", "tabbyapi"]:
                    self.available_models_dict = discover_models(
                        self.backend_type,
                        is_compatible_fn=is_backend_compatible
                    )
                    self.available_models = list(self.available_models_dict.values())
                    self.add_debug(f"📂 Found {len(self.available_models)} {self.backend_type}-compatible models")

                elif self.backend_type == "llamacpp":
                    # llama.cpp via llama-swap: Query /v1/models
                    models_dict = discover_models(
                        self.backend_type,
                        backend_url=self.backend_url
                    )
                    if not models_dict:
                        # Auto-start llama-swap service
                        self.add_debug("⚠️ llama-swap not reachable, starting service...")
                        try:
                            import os as _os
                            import subprocess as _sp
                            from pathlib import Path as _Path
                            _user_service = _Path.home() / ".config/systemd/user/llama-swap.service"
                            _cmd = ["systemctl", "--user"] if _user_service.exists() else ["systemctl"]
                            # AIfred runs as system service (User=mp) without D-Bus session env.
                            # systemctl --user needs XDG_RUNTIME_DIR + DBUS_SESSION_BUS_ADDRESS.
                            _env = _os.environ.copy()
                            _uid = _os.getuid()
                            _env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{_uid}")
                            _env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{_uid}/bus")
                            _sp.run([*_cmd, "start", "llama-swap"], check=True, timeout=15, env=_env)
                            import asyncio
                            await asyncio.sleep(2.0)
                            models_dict = discover_models(
                                self.backend_type,
                                backend_url=self.backend_url
                            )
                            if models_dict:
                                self.add_debug("✅ llama-swap auto-started")
                        except Exception as e:
                            self.add_debug(f"⚠️ Could not start llama-swap: {e}")

                    if models_dict:
                        self.available_models_dict = models_dict
                        self.available_models = list(self.available_models_dict.values())
                        self.add_debug(f"📂 Found {len(self.available_models)} llama.cpp models")
                    else:
                        self.available_models_dict = {}
                        self.available_models = []
                        self.add_debug(f"⚠️ llama-swap not reachable at {self.backend_url}")
                        self.add_debug("💡 Install llama-swap service or start manually")

                elif self.backend_type == "cloud_api":
                    # Cloud APIs: Fetch models dynamically from API
                    provider_config = CLOUD_API_PROVIDERS.get(self.cloud_api_provider)
                    if provider_config:
                        # Check if API key is configured first
                        self.cloud_api_key_configured = is_cloud_api_configured(self.cloud_api_provider)
                        if self.cloud_api_key_configured:
                            self.add_debug(f"✅ API key configured ({provider_config['env_key']})")
                            # Fetch models dynamically from Cloud API
                            try:
                                from .backends.cloud_api import CloudAPIBackend, get_cloud_api_key
                                api_key = get_cloud_api_key(self.cloud_api_provider)
                                temp_backend = CloudAPIBackend(
                                    base_url=provider_config["base_url"],
                                    api_key=api_key or "",
                                    provider=self.cloud_api_provider
                                )
                                models = await temp_backend.list_models()
                                await temp_backend.close()

                                if models:
                                    self.available_models_dict = sort_models_grouped({m: m for m in models})
                                    self.available_models = list(self.available_models_dict.values())
                                    self.add_debug(f"☁️ {provider_config['name']}: {len(models)} models loaded")
                                else:
                                    self.available_models_dict = {}
                                    self.available_models = []
                                    self.add_debug(f"⚠️ No models returned from {provider_config['name']} API")
                            except Exception as e:
                                self.available_models_dict = {}
                                self.available_models = []
                                self.add_debug(f"⚠️ Failed to fetch models: {e}")
                        else:
                            self.available_models_dict = {}
                            self.available_models = []
                            self.add_debug(f"⚠️ API key missing: Set {provider_config['env_key']} in .env")
                    else:
                        self.available_models_dict = {}
                        self.available_models = []
                        self.add_debug(f"⚠️ Unknown cloud provider: {self.cloud_api_provider}")

                else:
                    # Ollama: Query server API
                    self.available_models_dict = discover_models(
                        self.backend_type,
                        backend_url=self.backend_url
                    )
                    self.available_models = list(self.available_models_dict.values())

                # Check if saved model still exists in backend
                self.add_debug(f"🔍 Checking: '{self.aifred_model_id}' available in {self.backend_type}?")

                # Validate and sync aifred_model
                if self.aifred_model_id in self.available_models_dict:
                    self.aifred_model = self.available_models_dict[self.aifred_model_id]
                    self.add_debug(f"✅ Model found: {self.aifred_model_id}")
                elif self.available_models_dict:
                    # Model no longer available -> use first available
                    first_id = next(iter(self.available_models_dict.keys()))
                    self.add_debug(f"⚠️ '{self.aifred_model_id}' not in {self.backend_type}! Using: '{first_id}'")
                    log_message(f"⚠️ Configured model '{self.aifred_model_id}' not found, using '{first_id}'")
                    self.aifred_model_id = first_id
                    self.aifred_model = self.available_models_dict[first_id]

                # Validate and sync automatik_model (can be empty = use Main-LLM)
                if not self.automatik_model_id:
                    pass  # Empty = "same as AIfred-LLM"
                elif self.automatik_model_id in self.available_models_dict:
                    self.automatik_model = self.available_models_dict[self.automatik_model_id]
                elif self.available_models_dict:
                    # Model not found - clear it (same as AIfred)
                    log_message(f"⚠️ Configured automatik model '{self.automatik_model_id}' not found, using same as AIfred")
                    self.automatik_model_id = ""
                    self.automatik_model = ""

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

                # For backends without model switching (vLLM, TabbyAPI), show only Main model
                # Import VRAM cache for calibrated context limits
                from .lib.model_vram_cache import get_ollama_calibrated_max_context, get_rope_factor_for_model, get_llamacpp_calibration
                from .lib.formatting import format_number

                def format_model_with_ctx(model_display: str, model_id: str) -> str:
                    """Format model display with calibrated context limit merged into one bracket.
                    e.g., 'qwen3:8b (4.9 GB)' + ctx -> 'qwen3:8b (4.9 GB, 32.768 ctx)'
                    """
                    if not model_id:
                        return model_display
                    # Backend-aware calibration lookup
                    if self.backend_type == "llamacpp":
                        ctx = get_llamacpp_calibration(model_id)
                    else:
                        ctx = get_ollama_calibrated_max_context(model_id, get_rope_factor_for_model(model_id))
                    if ctx:
                        if model_display.endswith(")"):
                            return model_display[:-1] + f", {format_number(ctx)} ctx)"
                        return f"{model_display} ({format_number(ctx)} ctx)"
                    else:
                        if model_display.endswith(")"):
                            return model_display[:-1] + ", ctx not calibrated)"
                        return f"{model_display} (ctx not calibrated)"

                if self.backend_type.lower() in ["vllm", "tabbyapi"]:
                    # Compact format for Mobile: Multi-line with indentation
                    self.add_debug(f"✅ {len(self.available_models)} models available")
                    self.add_debug(f"   AIfred: {format_model_with_ctx(self.aifred_model, self.aifred_model_id)}")
                else:
                    # Compact format for Mobile: Multi-line with indentation
                    self.add_debug(f"✅ {len(self.available_models)} models available")
                    self.add_debug(f"   AIfred: {format_model_with_ctx(self.aifred_model, self.aifred_model_id)}")
                    if self.automatik_model_id:
                        self.add_debug(f"   Automatic: {format_model_with_ctx(self.automatik_model, self.automatik_model_id)}")
                    else:
                        self.add_debug("   Automatic: (= AIfred)")
                    # Show Sokrates and Salomo models if multi-agent mode is active
                    if self.multi_agent_mode != "standard":
                        if self.sokrates_model_id:
                            self.add_debug(f"   Sokrates: {format_model_with_ctx(self.sokrates_model, self.sokrates_model_id)}")
                        if self.salomo_model_id:
                            self.add_debug(f"   Salomo: {format_model_with_ctx(self.salomo_model, self.salomo_model_id)}")

                # Cache min context limit for session-load display
                context_limits = []
                for model_id in [self.aifred_model_id, self.sokrates_model_id, self.salomo_model_id]:
                    if model_id:
                        if self.backend_type == "llamacpp":
                            ctx = get_llamacpp_calibration(model_id)
                        else:
                            ctx = get_ollama_calibrated_max_context(model_id, get_rope_factor_for_model(model_id))
                        if ctx:
                            context_limits.append(ctx)
                self._min_agent_context_limit = min(context_limits) if context_limits else 0

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

            if not caps.get("dynamic_models", True) and self.automatik_model_id and self.automatik_model_id != self.aifred_model_id:
                # Non-dynamic backend: force same as AIfred (empty = already correct)
                self.automatik_model = ""
                self.automatik_model_id = ""
                self._save_settings()

            # Store in global state BEFORE starting servers (so fast path works on reload)
            _global_backend_state["backend_type"] = self.backend_type
            _global_backend_state["backend_url"] = self.backend_url
            _global_backend_state["aifred_model"] = self.aifred_model
            _global_backend_state["aifred_model_id"] = self.aifred_model_id
            _global_backend_state["automatik_model"] = self.automatik_model
            _global_backend_state["automatik_model_id"] = self.automatik_model_id
            _global_backend_state["available_models"] = self.available_models
            _global_backend_state["available_models_dict"] = self.available_models_dict  # CRITICAL for vision dropdown!
            _global_backend_state["current_backend_label"] = self.current_backend_label

            # === LOAD MODEL PARAMETERS FROM CACHE ===
            # CRITICAL: Must run during backend switch too (not just initial on_load)!
            # Without this, supports_thinking/max_context/is_hybrid retain values
            # from the PREVIOUS backend, causing e.g. unnecessary think=True retries.
            if self.backend_type == "ollama":
                from .lib.model_vram_cache import get_model_parameters
                for agent, model_id in [
                    ("aifred", self.aifred_model_id),
                    ("sokrates", self.sokrates_model_id),
                    ("salomo", self.salomo_model_id),
                ]:
                    if model_id:
                        params = get_model_parameters(model_id)
                        setattr(self, f"{agent}_rope_factor", params["rope_factor"])
                        setattr(self, f"{agent}_max_context", params["max_context"])
                        setattr(self, f"{agent}_is_hybrid", params["is_hybrid"])
                        setattr(self, f"{agent}_supports_thinking", params["supports_thinking"])
            elif self.backend_type == "llamacpp":
                from .lib.model_vram_cache import get_llamacpp_calibration, get_thinking_support_for_model
                for agent, model_id in [
                    ("aifred", self.aifred_model_id),
                    ("sokrates", self.sokrates_model_id),
                    ("salomo", self.salomo_model_id),
                ]:
                    if model_id:
                        setattr(self, f"{agent}_rope_factor", 1.0)
                        setattr(self, f"{agent}_max_context", get_llamacpp_calibration(model_id) or 0)
                        setattr(self, f"{agent}_is_hybrid", False)
                        setattr(self, f"{agent}_supports_thinking", get_thinking_support_for_model(model_id))

            # === RESET SAMPLING PARAMETERS TO YAML DEFAULTS ===
            # Temperature is preserved (loaded from settings.json in on_load)
            # Sampling params (top_k, top_p, min_p, repeat_penalty) reset to YAML values
            for agent in ["aifred", "sokrates", "salomo"]:
                self._reset_agent_sampling(agent, include_temperature=False)

            # === DETECT VISION MODELS (metadata-based) ===
            self.add_debug("🔍 Detecting vision-capable models...")
            await self._detect_vision_models()

            # Start vLLM process if backend is vLLM
            if self.backend_type == "vllm":
                await self._start_vllm_server()


            # Store in global state for future page reloads
            # vllm_manager is already stored in _global_backend_state by its start function
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

        # Only update backend models if model IDs are validated against current backend.
        # Prevents saving stale IDs from a different backend during transitions
        # (e.g., backend_id already switched but model_ids not yet validated).
        if self.aifred_model_id and self.backend_id and self.available_models_dict:
            if self.aifred_model_id in self.available_models_dict:
                backend_models[self.backend_id] = {
                    "aifred_model": self.aifred_model_id,
                    "automatik_model": self.automatik_model_id,
                    "vision_model": self.vision_model_id,
                    "sokrates_model": self.sokrates_model_id,
                    "salomo_model": self.salomo_model_id,
                }

        settings = {
            "backend_type": self.backend_type,
            "cloud_api_provider": self.cloud_api_provider,  # Cloud API provider (claude/qwen/kimi)
            "research_mode": self.research_mode,
            "temperature": self.temperature,
            "temperature_mode": self.temperature_mode,
            "sokrates_temperature": self.sokrates_temperature,
            "sokrates_temperature_offset": self.sokrates_temperature_offset,
            "enable_thinking": self.enable_thinking,
            "ui_language": self.ui_language,  # UI language (de/en)
            "user_name": self.user_name,  # User's name for personalized responses
            "user_gender": self.user_gender,  # Gender for salutation (male/female)
            "backend_models": backend_models,  # Merged: preserves all backends
            # Multi-Agent Settings
            "multi_agent_mode": self.multi_agent_mode,
            "max_debate_rounds": self.max_debate_rounds,
            "consensus_type": self.consensus_type,
            "sokrates_model": self.sokrates_model_id,  # Save pure ID
            "salomo_model": self.salomo_model_id,  # Save pure ID
            "salomo_temperature": self.salomo_temperature,
            "salomo_temperature_offset": self.salomo_temperature_offset,
            # vLLM YaRN Settings (only enable/disable, factor is calculated dynamically)
            "enable_yarn": self.enable_yarn,
            # NOTE: yarn_factor is NOT saved - always starts at 1.0, system calibrates maximum
            # NOTE: vllm_max_tokens and vllm_native_context are NEVER saved!
            # They are calculated dynamically on every vLLM startup based on VRAM
            # Vision LLM Context Settings (PERSISTENT)
            "vision_num_ctx_enabled": self.vision_num_ctx_enabled,
            "vision_num_ctx": self.vision_num_ctx,
            # Agent Personality & Reasoning Settings
            "aifred_personality": self.aifred_personality,
            "sokrates_personality": self.sokrates_personality,
            "salomo_personality": self.salomo_personality,
            "aifred_reasoning": self.aifred_reasoning,
            "sokrates_reasoning": self.sokrates_reasoning,
            "salomo_reasoning": self.salomo_reasoning,
            "aifred_thinking": self.aifred_thinking,
            "sokrates_thinking": self.sokrates_thinking,
            "salomo_thinking": self.salomo_thinking,
            # Note: Sampling params (top_k, top_p, min_p, repeat_penalty) NOT saved
            # They reset to YAML defaults on restart. Temperature IS saved (see below).
            "aifred_speed_mode": self.aifred_speed_mode,
            "sokrates_speed_mode": self.sokrates_speed_mode,
            "salomo_speed_mode": self.salomo_speed_mode,
            # TTS/STT Settings
            "enable_tts": self.enable_tts,
            "voice": self.tts_voice,  # Legacy key name for backward compatibility
            # Note: tts_speed removed - generation always at 1.0, tempo via tts_playback_rate
            "tts_engine": self.tts_engine,
            "xtts_force_cpu": self.xtts_force_cpu,
            "tts_autoplay": self.tts_autoplay,
            "tts_streaming_enabled": self.tts_streaming_enabled,
            "tts_playback_rate": self.tts_playback_rate,
            "tts_pitch": self.tts_pitch,
            "whisper_model": self.whisper_model_key,  # Save only key (tiny/base/small/medium/large)
            # whisper_device removed - now in config.py
            "show_transcription": self.show_transcription,
            # Language-specific TTS voices (user preferences per engine/language)
            "tts_voices_per_language": existing.get("tts_voices_per_language", {}),
            # Per-engine agent voice settings
            "tts_agent_voices_per_engine": existing.get("tts_agent_voices_per_engine", {}),
            # Per-engine TTS toggles (autoplay, streaming)
            "tts_toggles_per_engine": existing.get("tts_toggles_per_engine", {}),
            # UI Settings
            "auto_scroll": self.auto_refresh_enabled,
        }
        # Update tts_voices_per_language with current voice selection
        engine_key = self._get_engine_key()
        lang = self.ui_language
        if "tts_voices_per_language" not in settings:
            settings["tts_voices_per_language"] = {}
        if engine_key not in settings["tts_voices_per_language"]:
            settings["tts_voices_per_language"][engine_key] = {}
        settings["tts_voices_per_language"][engine_key][lang] = self.tts_voice

        # Update tts_agent_voices_per_engine with current agent voice settings
        import copy
        if "tts_agent_voices_per_engine" not in settings:
            settings["tts_agent_voices_per_engine"] = {}
        settings["tts_agent_voices_per_engine"][engine_key] = copy.deepcopy(self.tts_agent_voices)

        # Update tts_toggles_per_engine with current TTS toggles
        if "tts_toggles_per_engine" not in settings:
            settings["tts_toggles_per_engine"] = {}
        settings["tts_toggles_per_engine"][engine_key] = {
            "autoplay": self.tts_autoplay,
            "streaming": self.tts_streaming_enabled,
        }
        save_settings(settings)

        # Update mtime tracker to prevent immediate reload by check_for_updates()
        import os
        from .lib.settings import SETTINGS_FILE
        try:
            self._last_settings_mtime = os.path.getmtime(SETTINGS_FILE)
        except OSError:
            pass

    def _resolve_model_id(self, display_label: str) -> str:
        """Reverse lookup: find model_id (dict key) from display label."""
        for model_id, label in self.available_models_dict.items():
            if label == display_label:
                return model_id
        # Display label might already be a model_id (e.g., from settings)
        if display_label in self.available_models_dict:
            return display_label
        return display_label

    def _show_model_calibration_info(self, model_id: str):
        """Show calibration info in debug console.

        Displays calibrated context values or a warning
        if the model hasn't been calibrated yet.
        """
        if not model_id:
            return

        from .lib.formatting import format_number

        if self.backend_type == "llamacpp":
            from .lib.model_vram_cache import get_llamacpp_calibration
            calibrated = get_llamacpp_calibration(model_id)
            if calibrated:
                self.add_debug(f"   🎯 Calibrated: {format_number(calibrated)} tokens")
            else:
                self.add_debug("   ⚠️ Not calibrated - please run calibration for optimal context")
            return

        if self.backend_type != "ollama":
            return

        from .lib.model_vram_cache import get_ollama_calibrated_max_context

        native_ctx = get_ollama_calibrated_max_context(model_id, rope_factor=1.0)
        rope_1_5x_ctx = get_ollama_calibrated_max_context(model_id, rope_factor=1.5)
        rope_2x_ctx = get_ollama_calibrated_max_context(model_id, rope_factor=2.0)

        if native_ctx is not None or rope_1_5x_ctx is not None or rope_2x_ctx is not None:
            parts = []
            if native_ctx is not None:
                parts.append(f"Native: {format_number(native_ctx)}")
            if rope_1_5x_ctx is not None:
                parts.append(f"RoPE 1.5x: {format_number(rope_1_5x_ctx)}")
            if rope_2x_ctx is not None:
                parts.append(f"RoPE 2x: {format_number(rope_2x_ctx)}")
            self.add_debug(f"   🎯 Calibrated: {', '.join(parts)}")
        else:
            self.add_debug("   ⚠️ Not calibrated - please run calibration for optimal context")

    # ============================================================
    # CENTRAL AGENT PANEL MANAGEMENT
    # ============================================================
    # All agent panel operations (AIfred, Sokrates, Salomo) go through this central function
    # Eliminates code duplication across 10+ locations in state.py and multi_agent.py

    # Agent emoji mapping
    _AGENT_EMOJIS = {
        "aifred": "🎩",
        "sokrates": "🏛️",
        "salomo": "👑"
    }

    def _get_mode_label(self, mode: str, round_num: int | None) -> str:
        """Generate mode label based on mode and UI language.

        Args:
            mode: Mode identifier (e.g., "auto_consensus", "tribunal", "direct")
            round_num: Optional round number for multi-round debates

        Returns:
            Localized label string (e.g., "Auto-Konsens", "Tribunal", "Direkte Antwort")
        """
        from .lib.i18n import t

        # Mode label mapping (without round number)
        mode_labels = {
            "auto_consensus": t("auto_consensus_label", lang=self.ui_language).rstrip(":"),
            "tribunal": "Tribunal",  # Same in both languages
            "direct": t("direct_response_label", lang=self.ui_language).rstrip(":"),
            "refinement": t("refinement_label", lang=self.ui_language).rstrip(":"),
            "synthesis": t("salomo_synthesis_label", lang=self.ui_language).rstrip(":"),
            "verdict": t("salomo_verdict_label", lang=self.ui_language).rstrip(":"),
            "critical_review": t("critical_review_label", lang=self.ui_language).rstrip(":"),
            "advocatus_diaboli": t("advocatus_diaboli_label", lang=self.ui_language).rstrip(":"),
            "error": "Error",  # Same in both languages
            "standard": "",  # No label for standard mode
        }

        return mode_labels.get(mode, "")

    def _build_marker(self, agent: str, mode: str, round_num: int | None) -> str:
        """Build marker string for agent panels.

        Args:
            agent: Agent identifier ("aifred", "sokrates", "salomo")
            mode: Mode identifier (e.g., "refinement", "critical_review", "verdict")
            round_num: Optional round number

        Returns:
            Formatted marker like "<span style='...'>Auto-Konsens: Überarbeitung R2</span>\n\n"
            (includes multi_agent_mode prefix if active, no emoji - already shown left of bubble)
        """
        label = self._get_mode_label(mode, round_num)

        if not label:
            return ""  # No marker for standard mode

        # Prepend multi-agent mode prefix (e.g., "Auto-Konsens:", "Tribunal:")
        # Skip for "standard" mode, when mode already includes the prefix,
        # or when mode equals multi_agent_mode (prevents "[Critical Review: Critical Review R1]")
        mode_prefix = ""
        if self.multi_agent_mode != "standard" and mode not in ["auto_consensus", "tribunal", "devils_advocate"] and mode != self.multi_agent_mode:
            # Get localized multi-agent mode label
            multi_mode_label = self._get_mode_label(self.multi_agent_mode, None)
            if multi_mode_label:
                mode_prefix = f"{multi_mode_label}: "

        # Add round suffix if present
        round_suffix = f" R{round_num}" if round_num else ""

        # Format with HTML span for styling (no emoji - already in UI)
        # Color: rgba(255, 255, 255, 1.0) = 100% opacity white (fully opaque)
        # Style: italic, smaller font
        # Spacing: 2 newlines after (converted to <br><br> in HTML export)
        return f"<span style='color: rgba(255, 255, 255, 0.6; font-style: italic; font-size: 12px;'>[{mode_prefix}{label}{round_suffix}]</span>\n\n"

    def _format_panel_metadata(self, metadata: dict | None) -> str:
        """Format metadata footer for agent panels.

        Args:
            metadata: Dict with keys like ttft, inference_time, tokens_per_sec, source

        Returns:
            Formatted metadata string like "*( TTFT: 0,41s    Inference: 9,1s )*"
        """
        if not metadata:
            return ""

        from .lib.formatting import format_number

        # Split into speed metrics (no wrap) and info (wrap allowed before)
        perf_parts = []
        info_parts = []

        # TTFT (Time To First Token)
        if "ttft" in metadata and metadata["ttft"]:
            perf_parts.append(f"TTFT:\u00A0{format_number(metadata['ttft'], 2)}s")

        # PP speed (prompt processing)
        prompt_per_sec = metadata.get("prompt_per_sec", 0)
        if prompt_per_sec:
            perf_parts.append(f"PP:\u00A0{format_number(prompt_per_sec, 1)}\u00A0tok/s")

        # Tokens per second (generation)
        if "tokens_per_sec" in metadata and metadata["tokens_per_sec"]:
            perf_parts.append(f"{format_number(metadata['tokens_per_sec'], 1)}\u00A0tok/s")

        # Inference time
        if "inference_time" in metadata and metadata["inference_time"]:
            perf_parts.append(f"Inference:\u00A0{format_number(metadata['inference_time'], 1)}s")

        # Source (with backend label if available)
        if "source" in metadata and metadata["source"]:
            source = metadata["source"]
            backend = metadata.get("backend_type", "")
            source_display = f"{source}\u00A0[{backend}]" if backend else source
            # Replace all spaces within source so it stays as one unbreakable unit
            info_parts.append(f"Source:\u00A0{source_display.replace(' ', chr(0xA0))}")

        if not perf_parts and not info_parts:
            return ""

        from .lib.formatting import format_metadata
        # Within groups: "    " → non-breaking spaces (no wrap)
        # Between groups: 3 nbsp + regular space → allows line break on mobile
        groups = []
        if perf_parts:
            groups.append("    ".join(perf_parts))
        if info_parts:
            groups.append("    ".join(info_parts))
        metadata_text = "\u00A0\u00A0\u00A0 ".join(groups)
        return format_metadata(metadata_text)

    def _sync_to_llm_history(self, agent: str, content: str) -> None:
        """Sync agent response to llm_history with speaker label.

        Args:
            agent: Agent identifier ("aifred", "sokrates", "salomo")
            content: Agent response content (thinking blocks will be stripped)
        """
        from .lib.context_manager import strip_thinking_blocks

        label = agent.upper()
        clean_content = strip_thinking_blocks(content)

        self.llm_history.append({
            "role": "assistant",
            "content": f"[{label}]: {clean_content}"
        })

    def add_agent_panel(
        self,
        agent: str,  # "aifred", "sokrates", "salomo"
        content: str,
        mode: str = "standard",
        round_num: int | None = None,
        metadata: dict | None = None,
        sync_llm_history: bool = True,
        generate_tts: bool | None = None
    ) -> None:
        """Add an agent response as a new message to chat_history.

        This is the ONLY function that should be used to add agent panels to chat_history.
        It handles:
        - Emoji marker generation (🎩, 🏛️, 👑)
        - Mode labeling (Auto-Consensus, Tribunal, etc.)
        - Round numbering (R1, R2, ...)
        - Metadata formatting (TTFT, Inference time, tok/s, Source)
        - LLM history synchronization
        - Session persistence
        - TTS generation (queued for sequential playback)

        With the new dict-based chat_history, each message is standalone.
        No more replace_last logic - just append new messages.

        Args:
            agent: Agent identifier ("aifred", "sokrates", "salomo")
            content: Agent response content (WITHOUT marker, WITHOUT metadata)
            mode: Mode identifier (e.g., "auto_consensus", "tribunal", "direct", "standard")
            round_num: Round number for multi-round debates (None/0 = no round, 1+ = round number)
            metadata: Optional dict with TTFT, inference_time, tokens_per_sec, source
            sync_llm_history: If True, syncs to llm_history (set False if caller already did)
            generate_tts: If True, generate TTS and add to queue. If None, uses self.enable_tts.
                         If False, skip TTS. For multi-agent modes, this enables per-response TTS.

        Examples:
            # Sokrates direct response
            state.add_agent_panel(
                agent="sokrates",
                content=formatted_response,
                mode="direct",
                metadata={"ttft": 3.7, "inference_time": 16.4, "tokens_per_sec": 41.5, "source": "Sokrates (qwen3:4b)"}
            )

            # AIfred refinement R1
            state.add_agent_panel(
                agent="aifred",
                content=formatted_response,
                mode="refinement",
                round_num=1,
                metadata={...}
            )

            # Salomo synthesis R2
            state.add_agent_panel(
                agent="salomo",
                content=formatted_response,
                mode="synthesis",
                round_num=2,
                metadata={...}
            )
        """
        from datetime import datetime
        import asyncio

        # 1. Build marker (emoji + mode label + round number)
        marker = self._build_marker(agent, mode, round_num if round_num and round_num > 0 else None)

        # 2. Format metadata footer
        meta_footer = self._format_panel_metadata(metadata)

        # 3. Translate consensus tags to natural language for UI display
        # These are trigger words for the Multi-Agent system, already parsed by count_lgtm_votes()
        # Now we make them human-readable in the UI (and TTS will speak what's displayed)
        # Uses detected language (from Intent Detection) for correct localization
        import re
        from .lib.i18n import t
        from .lib.prompt_loader import get_language
        lang = self._last_detected_language or get_language()
        content = re.sub(r'\[LGTM\]', t("consensus_agreed", lang=lang), content, flags=re.IGNORECASE)
        content = re.sub(r'\[WEITER\]', t("consensus_continue", lang=lang), content, flags=re.IGNORECASE)

        # 4. Remove thinking blocks from content before storing (for History/Token estimation)
        from .lib.context_manager import strip_thinking_blocks
        clean_content = strip_thinking_blocks(content)

        # 5. Assemble final content for display
        if marker:
            final_content = f"{marker}{clean_content}\n\n{meta_footer}"
        else:
            # Standard mode: no marker, just content + metadata
            final_content = f"{clean_content}\n\n{meta_footer}" if meta_footer else clean_content

        # 5. Create new message entry (dict-based format)
        # Include audio URLs if streaming TTS generated them
        msg_metadata = metadata.copy() if metadata else {}
        if self._pending_audio_urls:
            msg_metadata["audio_urls"] = self._pending_audio_urls.copy()
            log_message(f"🔊 add_agent_panel: Stored {len(self._pending_audio_urls)} audio URLs in message metadata")
            self._pending_audio_urls = []  # Clear after storing

        # Store agent's playback rate for HTML export (browser speed setting, per-agent)
        # Always set when audio_urls are present, regardless of source
        audio_urls = msg_metadata.get("audio_urls", [])
        if audio_urls:
            msg_metadata["playback_rate"] = self.tts_agent_voices[agent]["speed"]
        new_message: Dict[str, Any] = {
            "role": "assistant",
            "content": final_content,
            "agent": agent,
            "mode": mode,
            "round_num": round_num,
            "metadata": msg_metadata,
            "timestamp": datetime.now().isoformat(),
            "used_sources": [],
            "failed_sources": [],
            "has_audio": bool(audio_urls),
            "audio_urls_json": json.dumps(audio_urls) if audio_urls else "[]",
        }

        # 5. Append to chat_history (no more replace_last!)
        self.chat_history.append(new_message)

        # 6. Sync to llm_history (with speaker label)
        # Note: Some callers (streaming functions) already sync to llm_history,
        # so they should pass sync_llm_history=False to avoid duplicates
        if sync_llm_history:
            self._sync_to_llm_history(agent, content)

        # 7. Save session (async, non-blocking)
        self._save_current_session()

        # 8. Generate TTS and add to queue (if enabled)
        # Determine if TTS should be generated
        # SKIP if streaming TTS is enabled - text was already sent sentence-by-sentence
        should_generate_tts = generate_tts if generate_tts is not None else self.enable_tts
        if should_generate_tts and not self.tts_streaming_enabled:
            # Check per-agent TTS enabled setting
            agent_tts_enabled = self.tts_agent_voices.get(agent, {}).get("enabled", True)
            if agent_tts_enabled:
                # Schedule TTS generation as background task
                # This runs async without blocking add_agent_panel()
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._queue_tts_for_agent(content, agent))
                except RuntimeError:
                    # No running loop - this shouldn't happen in normal operation
                    # but we handle it gracefully
                    self.add_debug(f"⚠️ TTS: No event loop for {agent}")

    # ============================================================
    # END: CENTRAL AGENT PANEL MANAGEMENT
    # ============================================================

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
            target_sokrates_model = None
            target_salomo_model = None

            self.add_debug(f"🔍 Settings contains backends: {list(backend_models.keys())}")
            if new_backend in backend_models:
                # Load saved models from settings.json
                saved_models = backend_models[new_backend]
                target_main_model = saved_models.get("aifred_model")
                target_auto_model = saved_models.get("automatik_model")
                target_vision_model = saved_models.get("vision_model")
                target_sokrates_model = saved_models.get("sokrates_model", "")
                target_salomo_model = saved_models.get("salomo_model", "")
                self.add_debug(f"📝 Loading {new_backend} from settings: AIfred={target_main_model}, Auto={target_auto_model}, Vision={target_vision_model}, Sokrates={target_sokrates_model or '(Main)'}, Salomo={target_salomo_model or '(Main)'}")
            else:
                # No entry in settings.json -> use config.py defaults
                default_models = config.BACKEND_DEFAULT_MODELS.get(new_backend, {})
                target_main_model = default_models.get("aifred_model")
                target_auto_model = default_models.get("automatik_model")
                target_sokrates_model = default_models.get("sokrates_model", "")
                target_salomo_model = default_models.get("salomo_model", "")
                self.add_debug(f"📝 No settings for {new_backend}, using config.py defaults: AIfred={target_main_model}, Auto={target_auto_model}")

            # Set target models BEFORE initialize_backend() so validation doesn't override them
            # CRITICAL: Set BOTH display name AND ID - initialize_backend() uses _id for validation!
            if target_main_model:
                self.aifred_model = target_main_model
                self.aifred_model_id = target_main_model
            # Automatik can be empty (= use Main-LLM), None means not in settings
            if target_auto_model is not None:
                self.automatik_model = target_auto_model
                self.automatik_model_id = target_auto_model
            if target_vision_model:
                self.vision_model = target_vision_model
                self.vision_model_id = target_vision_model
            # Sokrates and Salomo can be empty (= use Main-LLM)
            self.sokrates_model_id = target_sokrates_model or ""
            self.sokrates_model = target_sokrates_model or ""
            self.salomo_model_id = target_salomo_model or ""
            self.salomo_model = target_salomo_model or ""

            # vLLM and TabbyAPI can only load ONE model at a time
            # Force Automatik = same as AIfred (empty string)
            if new_backend in ["vllm", "tabbyapi"]:
                if self.automatik_model_id:
                    self.add_debug(f"⚠️ {new_backend} can only load one model - Automatic will use AIfred-LLM")
                self.automatik_model = ""
                self.automatik_model_id = ""

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

    async def set_cloud_api_provider_by_label(self, label: str):
        """Switch Cloud API provider using display label

        Maps "Claude (Anthropic)" -> "claude", etc.
        """
        label_to_id = {
            "Claude (Anthropic)": "claude",
            "Qwen (DashScope)": "qwen",
            "DeepSeek": "deepseek",
            "Kimi (Moonshot)": "kimi",
        }
        provider_id = label_to_id.get(label, "qwen")
        async for _ in self.set_cloud_api_provider(provider_id):
            yield

    async def set_cloud_api_provider(self, provider: str):
        """Switch Cloud API provider (claude, qwen, kimi)

        Only relevant when backend_type == "cloud_api".
        Triggers model list refresh, vision model refresh, and API key check.
        """
        if provider not in CLOUD_API_PROVIDERS:
            self.add_debug(f"⚠️ Unknown cloud provider: {provider}")
            return

        provider_config = CLOUD_API_PROVIDERS[provider]
        self.cloud_api_provider = provider
        self.cloud_api_provider_label = provider_config["name"]

        # Check API key
        self.cloud_api_key_configured = is_cloud_api_configured(provider)

        self.add_debug(f"☁️ Switching to {provider_config['name']}...")

        if self.cloud_api_key_configured:
            self.add_debug(f"✅ API key found ({provider_config['env_key']})")
            # Fetch models dynamically from Cloud API
            try:
                from .backends.cloud_api import CloudAPIBackend, get_cloud_api_key
                api_key = get_cloud_api_key(provider)
                temp_backend = CloudAPIBackend(
                    base_url=provider_config["base_url"],
                    api_key=api_key or "",
                    provider=provider
                )
                models = await temp_backend.list_models()
                await temp_backend.close()

                if models:
                    self.available_models_dict = {m: m for m in models}
                    self.available_models = models.copy()
                    self.add_debug(f"📋 {len(models)} models available")

                    # For Cloud APIs: Filter by name patterns (no metadata API)
                    from .lib.vision_utils import is_vision_model_sync
                    vl_models = [m for m in models if is_vision_model_sync(m)]
                    self.vision_models_cache = vl_models
                    self.available_vision_models_list = vl_models
                    if vl_models:
                        self.add_debug(f"📷 {len(vl_models)} vision models")

                    # Set default model (first in list)
                    default_model = models[0]
                    self.aifred_model = default_model
                    self.aifred_model_id = default_model
                    self.automatik_model = default_model
                    self.automatik_model_id = default_model

                    # Set default vision model (first VL model if available)
                    if vl_models:
                        self.vision_model = vl_models[0]
                        self.vision_model_id = vl_models[0]
                    else:
                        self.vision_model = ""
                        self.vision_model_id = ""
                else:
                    self.available_models_dict = {}
                    self.available_models = []
                    self.vision_models_cache = []
                    self.available_vision_models_list = []
                    self.add_debug("⚠️ No models returned from API")
            except Exception as e:
                self.available_models_dict = {}
                self.available_models = []
                self.vision_models_cache = []
                self.available_vision_models_list = []
                self.add_debug(f"⚠️ Failed to fetch models: {e}")
        else:
            self.available_models_dict = {}
            self.available_models = []
            self.vision_models_cache = []
            self.available_vision_models_list = []
            self.add_debug(f"⚠️ Set {provider_config['env_key']} in .env")

        self._save_settings()
        yield

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

        # Keep only last N messages (configurable in config.py)
        if len(self.debug_messages) > DEBUG_MESSAGES_MAX:
            self.debug_messages = self.debug_messages[-DEBUG_MESSAGES_MAX:]

    def _reload_settings_from_file(self):
        """
        Reload settings from settings.json file.

        Called when API update flag is detected. Updates all UI-visible settings
        to reflect changes made via REST API.
        """
        from .lib.settings import load_settings
        from .lib import TranslationManager

        settings = load_settings()
        if not settings:
            return

        # Core settings
        self.temperature = settings.get("temperature", self.temperature)
        self.temperature_mode = settings.get("temperature_mode", self.temperature_mode)
        self.enable_thinking = settings.get("enable_thinking", self.enable_thinking)

        # Research mode
        self.research_mode = settings.get("research_mode", self.research_mode)
        self.research_mode_display = TranslationManager.get_research_mode_display(
            self.research_mode, self.ui_language
        )

        # Multi-Agent settings
        self.multi_agent_mode = settings.get("multi_agent_mode", self.multi_agent_mode)
        self.max_debate_rounds = settings.get("max_debate_rounds", self.max_debate_rounds)
        self.consensus_type = settings.get("consensus_type", self.consensus_type)

        # Model IDs - update both ID and display variables
        # AIfred model (top-level "model" field in settings.json)
        if "model" in settings:
            model_id = settings["model"]
            self.aifred_model_id = model_id
            # Update display name if we have the models dict
            if model_id in self.available_models_dict:
                self.aifred_model = self.available_models_dict[model_id]
            else:
                self.aifred_model = model_id

        # Sokrates model
        if "sokrates_model" in settings:
            model_id = settings["sokrates_model"]
            self.sokrates_model_id = model_id
            if model_id in self.available_models_dict:
                self.sokrates_model = self.available_models_dict[model_id]
            else:
                self.sokrates_model = model_id

        # Salomo model
        if "salomo_model" in settings:
            model_id = settings["salomo_model"]
            self.salomo_model_id = model_id
            if model_id in self.available_models_dict:
                self.salomo_model = self.available_models_dict[model_id]
            else:
                self.salomo_model = model_id

        # Automatik model (can be empty = same as AIfred)
        if "automatik_model" in settings:
            model_id = settings["automatik_model"]
            self.automatik_model_id = model_id
            if not model_id:
                self.automatik_model = ""  # Same as AIfred
            elif model_id in self.available_models_dict:
                self.automatik_model = self.available_models_dict[model_id]
            else:
                self.automatik_model = model_id

        # Vision model
        if "vision_model" in settings:
            model_id = settings["vision_model"]
            self.vision_model_id = model_id
            if model_id in self.available_models_dict:
                self.vision_model = self.available_models_dict[model_id]
            else:
                self.vision_model = model_id

        # RoPE factors
        self.aifred_rope_factor = settings.get("aifred_rope_factor", self.aifred_rope_factor)
        self.sokrates_rope_factor = settings.get("sokrates_rope_factor", self.sokrates_rope_factor)
        self.salomo_rope_factor = settings.get("salomo_rope_factor", self.salomo_rope_factor)
        self.automatik_rope_factor = settings.get("automatik_rope_factor", self.automatik_rope_factor)
        self.vision_rope_factor = settings.get("vision_rope_factor", self.vision_rope_factor)

        # Personality toggles
        self.aifred_personality = settings.get("aifred_personality", self.aifred_personality)
        self.sokrates_personality = settings.get("sokrates_personality", self.sokrates_personality)
        self.salomo_personality = settings.get("salomo_personality", self.salomo_personality)
        # Sync to prompt_loader
        from .lib.prompt_loader import set_personality_enabled
        set_personality_enabled("aifred", self.aifred_personality)
        set_personality_enabled("sokrates", self.sokrates_personality)
        set_personality_enabled("salomo", self.salomo_personality)

        # TTS settings
        self.enable_tts = settings.get("enable_tts", self.enable_tts)
        self.tts_voice = settings.get("voice", self.tts_voice)
        saved_engine = settings.get("tts_engine", self.tts_engine)
        # Migrate old display-string format to key format
        if saved_engine and len(saved_engine) > 10:
            engine_map = {"XTTS": "xtts", "MOSS": "moss", "DashScope": "dashscope",
                          "Piper": "piper", "eSpeak": "espeak", "Edge": "edge"}
            for name, key in engine_map.items():
                if name in saved_engine:
                    saved_engine = key
                    break
        self.tts_engine = saved_engine
        self.xtts_force_cpu = settings.get("xtts_force_cpu", self.xtts_force_cpu)
        self.tts_autoplay = settings.get("tts_autoplay", self.tts_autoplay)
        self.tts_streaming_enabled = settings.get("tts_streaming_enabled", self.tts_streaming_enabled)

        # UI language
        new_ui_lang = settings.get("ui_language", self.ui_language)
        if new_ui_lang != self.ui_language and new_ui_lang in ["de", "en"]:
            self.ui_language = new_ui_lang
            from .lib.formatting import set_ui_locale
            set_ui_locale(new_ui_lang)
            set_language(new_ui_lang)  # Sync prompt language

        # User name
        self.user_name = settings.get("user_name", self.user_name)
        from .lib.prompt_loader import set_user_name
        set_user_name(self.user_name)

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

        Also checks for API update flags - if flag exists for this session_id,
        triggers browser reload to sync session data from API changes.
        """
        # Check if settings.json was modified (mtime-based, multi-browser safe)
        # Each browser tracks its own last-seen mtime - no race conditions
        import os
        from .lib.settings import SETTINGS_FILE
        try:
            current_mtime = os.path.getmtime(SETTINGS_FILE)
            if current_mtime > self._last_settings_mtime:
                self._reload_settings_from_file()
                self._last_settings_mtime = current_mtime
                self.add_debug("⚙️ Settings reloaded")
                yield
                return
        except OSError:
            pass  # File doesn't exist or not accessible

        # Check for pending message from API (message injection)
        if self.session_id and not self.is_generating:
            from .lib.session_storage import get_and_clear_pending_message
            pending_msg = get_and_clear_pending_message(self.session_id)
            if pending_msg:
                self.current_user_input = pending_msg
                self.add_debug(f"📨 API: Message injected ({len(pending_msg)} chars)")
                yield  # Update UI with debug message and input field
                # Trigger send_message as next event in chain
                return AIState.send_message

        # Check for API update flag (only if session_id is set)
        if self.session_id:
            from .lib.session_storage import check_and_clear_update_flag, load_session
            if check_and_clear_update_flag(self.session_id):
                # Load session directly from file (no browser reload needed!)
                session = load_session(self.session_id)
                if session and session.get("data"):
                    self._restore_session(session)
                    msg_count = len(self.chat_history)
                    self.add_debug(f"🔄 API update: Session reloaded ({msg_count} messages)")
                yield
                return

        # Just yield to propagate any state changes to UI
        # No need to modify anything - self.debug_messages already has the data
        yield

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

        For Cloud APIs: Filter by name patterns (vl, vision, ocr, etc.) - no metadata API.
        For local backends: Queries backend metadata for vision capabilities.
        """
        global _global_backend_state
        from .lib.vision_utils import is_vision_model, is_vision_model_sync

        vision_model_ids = []  # Store IDs, not display names

        # === CLOUD API: Filter by name patterns (no metadata API available) ===
        if self.backend_type == "cloud_api":
            # Use comprehensive name-based detection from vision_utils
            for model_id in self.available_models_dict.keys():
                if is_vision_model_sync(model_id):
                    vision_model_ids.append(model_id)

        else:
            # === LOCAL BACKENDS: Query metadata ===
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
            # Select first available vision model
            self.vision_model_id = vision_model_ids[0]
            self.vision_model = self.available_models_dict.get(self.vision_model_id, self.vision_model_id)
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
                self.vision_model = self.available_models_dict.get(self.vision_model_id, self.vision_model_id)
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
            # Therefore, start directly with the AIfred-Model (30B) to avoid slow restarts
            # Both Automatik and AIfred requests will use the same 30B model
            startup_model = self.aifred_model_id  # Pure ID
            self.add_debug(f"🚀 Starting vLLM server with {startup_model}...")
            self.add_debug("   (vLLM uses AIfred-Model for all requests - model switching requires slow restart)")

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
                        self.add_debug(f"📏 Maximum YaRN factor: ~{self.yarn_max_factor:.1f}x (determined by test)")
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
        Used by set_aifred_model() and apply_yarn_factor() to ensure actual restart.

        Note: This is called from async event handlers (apply_yarn_factor, set_aifred_model)
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
            _global_backend_state["aifred_model"] = self.aifred_model
            _global_backend_state["automatik_model"] = self.automatik_model

        except Exception as e:
            self.add_debug(f"❌ vLLM restart failed: {e}")
            raise

    async def _cleanup_old_backend(self, old_backend: str):
        """
        Clean up resources from previous backend before switching

        Args:
            old_backend: Backend type to clean up ("ollama", "vllm", etc.)
        """
        from .lib.process_utils import stop_backend_process

        if old_backend == "ollama":
            # Unload all Ollama models from VRAM
            self.add_debug("🧹 Unloading Ollama models from VRAM...")
            try:
                from .lib.llm_client import LLMClient
                llm_client = LLMClient(backend_type="ollama", base_url=config.DEFAULT_OLLAMA_URL)
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
            self.add_debug("🛑 Stopping vLLM server...")
            if await stop_backend_process("vllm"):
                self.add_debug("✅ vLLM server stopped")
                _global_backend_state["vllm_manager"] = None
            else:
                self.add_debug("ℹ️ vLLM server was not running")

        elif old_backend == "tabbyapi":
            self.add_debug("🛑 Stopping TabbyAPI server...")
            if await stop_backend_process("tabbyapi"):
                self.add_debug("✅ TabbyAPI server stopped")
            else:
                self.add_debug("ℹ️ TabbyAPI server was not running")

        elif old_backend == "llamacpp":
            # Stop llama-swap service to free GPU VRAM
            self.add_debug("🛑 Stopping llama-swap service...")
            try:
                import os as _os
                import subprocess as _sp
                from pathlib import Path as _Path
                _user_service = _Path.home() / ".config/systemd/user/llama-swap.service"
                _cmd = ["systemctl", "--user"] if _user_service.exists() else ["systemctl"]
                # AIfred runs as system service (User=mp) without D-Bus session env.
                # systemctl --user needs XDG_RUNTIME_DIR + DBUS_SESSION_BUS_ADDRESS.
                _env = _os.environ.copy()
                _uid = _os.getuid()
                _env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{_uid}")
                _env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{_uid}/bus")
                _sp.run([*_cmd, "stop", "llama-swap"], check=True, timeout=15, env=_env)
                self.add_debug("✅ llama-swap service stopped")
            except Exception as e:
                self.add_debug(f"⚠️ Could not stop llama-swap: {e}")

    async def _maybe_run_multi_agent(
        self,
        user_msg: str,
        ai_text: str,
        detected_language: str,
        skip_analysis: bool
    ):
        """
        Führt Multi-Agent Analyse aus, wenn aktiviert und nicht übersprungen.

        Args:
            user_msg: Die User-Nachricht
            ai_text: Die AI-Antwort (AIfred R1)
            detected_language: Sprache ("de" oder "en")
            skip_analysis: True wenn Multi-Agent übersprungen werden soll
                          (z.B. wenn User AIfred direkt angesprochen hat)

        Yields:
            Nothing directly, but updates state via run_tribunal/run_sokrates_analysis
        """
        # Skip if standard mode, no AI text, or explicitly skipped
        if self.multi_agent_mode == "standard" or not ai_text or skip_analysis:
            return

        # Generate TTS for AIfred's initial response BEFORE Multi-Agent starts
        # This ensures AIfred's voice is heard first, then Sokrates/Salomo follow
        # (Sokrates/Salomo TTS is generated via add_agent_panel() in multi_agent.py)
        # SKIP if streaming TTS is enabled - text was already sent sentence-by-sentence
        if self.enable_tts and not self.tts_streaming_enabled:
            agent_tts_enabled = self.tts_agent_voices.get("aifred", {}).get("enabled", True)
            if agent_tts_enabled:
                # Wait for TTS to complete so we can update message metadata with audio URL
                await self._queue_tts_for_agent(ai_text, agent="aifred")
                yield  # Update UI with audio button (chat_history was reassigned in _queue_tts_for_agent)

        if self.multi_agent_mode == "tribunal":
            self.add_debug("⚖️ Multi-Agent: Tribunal startet...")
            yield
            async for _ in run_tribunal(self, user_msg, ai_text, detected_language):
                yield
        else:
            self.add_debug("🏛️ Multi-Agent: Sokrates-Analyse startet...")
            yield
            async for _ in run_sokrates_analysis(self, user_msg, ai_text, detected_language):
                yield

    async def send_message(self):
        """
        Send message to LLM with optional web research

        Portiert von Gradio chat_interactive_mode() mit Research-Integration
        """
        # Must be logged in to send messages
        if not self.logged_in_user:
            self.add_debug("⚠️ Please log in first")
            return

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
        self.current_agent = "aifred"  # Set current agent for unified streaming UI
        self.used_sources = []  # Clear sources from previous request
        self.failed_sources = []
        self.all_sources = []  # Clear combined sources list
        # Clear TTS queue for new message (multi-agent responses will add to it)
        self.clear_tts_queue()

        # Initialize streaming TTS if enabled (sentences are sent to TTS as they're detected)
        # Works for all modes - Multi-Agent also streams and benefits from sentence-by-sentence TTS
        # Streaming requires AutoPlay - without autoplay, streaming makes no sense (generates but doesn't play)
        tts_stream_script = None
        if self.enable_tts and self.tts_autoplay and self.tts_streaming_enabled:
            self._init_streaming_tts(agent="aifred")
            # Clear API queue for this session (new message = new queue)
            from .lib.api import tts_queue_clear
            tts_queue_clear(self.session_id)
            # IMPORTANT: Ensure SSE stream is active BEFORE generating audio
            # This guarantees the browser is listening when audio events are pushed
            # The startTtsStream() function is idempotent - it checks ttsStreamActive
            tts_stream_script = rx.call_script(f"if(window.startTtsStream) startTtsStream('{self.session_id}');")

        # IMPORTANT: Yield immediately so UI shows spinner right away
        # Also starts TTS SSE stream if TTS is enabled (must be before audio generation!)
        if tts_stream_script:
            yield tts_stream_script
        else:
            yield

        # ============================================================
        # ADD USER MESSAGE TO CHAT IMMEDIATELY (before any backend operations)
        # ============================================================
        # This ensures the user sees their message right away, even during XTTS startup
        # Prepare display message (may include image markers for Vision)
        display_user_msg = user_msg
        if has_pending_images:
            # Generate clickable image thumbnails as HTML
            image_html_parts = []
            for img in self.pending_images:
                url = img.get('url', '')
                if url:
                    image_html_parts.append(
                        f'<a href="{url}" target="_blank" rel="noopener noreferrer">'
                        f'<img src="{url}" style="width:50px;height:50px;object-fit:cover;'
                        f'border-radius:4px;cursor:pointer;margin-right:4px;"></a>'
                    )
            image_html = "".join(image_html_parts)

            if not user_msg or user_msg.strip() == "":
                # Image-only upload
                if len(self.pending_images) == 1:
                    display_user_msg = f"{image_html}\n\n📷 {self.pending_images[0].get('name', 'Image')}"
                else:
                    img_names = ", ".join([img.get("name", "unknown") for img in self.pending_images])
                    display_user_msg = f"{image_html}\n\n📷 {len(self.pending_images)} images: {img_names}"
            else:
                # Text + images
                display_user_msg = f"{image_html}\n\n{user_msg}" if image_html else user_msg

        # Add to chat_history so user sees their message IMMEDIATELY
        from datetime import datetime
        self.chat_history.append({
            "role": "user",
            "content": display_user_msg,
            "agent": "",
            "mode": "",
            "round_num": 0,
            "metadata": {
                "images": [{"name": img.get("name", ""), "url": img.get("url", "")} for img in self.pending_images] if has_pending_images else []
            },
            "timestamp": datetime.now().isoformat(),
            "used_sources": [],
            "failed_sources": [],
            "has_audio": False,
            "audio_urls_json": "[]",
        })
        # Sync to llm_history (for LLM context - use ORIGINAL user_msg, not display variant)
        self.llm_history.append({"role": "user", "content": user_msg})
        self.add_debug("📨 User request received")

        yield  # Update UI - user sees their message + debug confirmation NOW

        # TTS: Ensure Docker container is running BEFORE Ollama loads models (reserves VRAM)
        # This runs on every message, not just at startup - handles container restart scenarios
        if self.enable_tts and self.tts_engine == "xtts" and not self.xtts_force_cpu:
            from .lib.process_utils import ensure_xtts_ready

            self.add_debug("🔊 XTTS: Checking container...")
            yield  # Show debug message
            success, msg = ensure_xtts_ready(timeout=60)
            if success:
                self.add_debug(f"✅ {msg}")
            else:
                self.add_debug(f"⚠️ {msg}")
            yield  # Update UI
        elif self.enable_tts and self.tts_engine == "moss":  # MOSS-TTS (batch)
            from .lib.process_utils import ensure_moss_ready

            self.add_debug("🔊 MOSS-TTS: Checking container...")
            yield
            success, msg, device = ensure_moss_ready(timeout=120)
            self.moss_tts_device = device if success else ""
            if success:
                self.add_debug(f"✅ {msg}")
            else:
                self.add_debug(f"⚠️ {msg}")
            yield

        try:
            # ============================================================
            # MAIN TRY BLOCK: Covers ALL stages from LLM client creation
            # through inference. Ensures is_generating is ALWAYS reset in finally,
            # even if intent detection hangs, compression fails, or the generator
            # is cancelled by WebSocket disconnect (GeneratorExit).
            # ============================================================

            # Create LLM client once - used for ALL LLM operations
            from .lib.llm_client import LLMClient
            llm_client = LLMClient(
                backend_type=self.backend_type,
                base_url=self.backend_url
            )

            # ============================================================
            # AUTOMATIK NUM_CTX CALCULATION (once, used for all Automatik calls)
            # ============================================================
            # When Automatik = AIfred (same model): don't set num_ctx → no model reload
            # When different models: use AUTOMATIK_LLM_NUM_CTX from config.py
            from .lib.config import AUTOMATIK_LLM_NUM_CTX
            from .lib.formatting import format_number
            effective_auto = self._effective_automatik_id
            if effective_auto == self.aifred_model_id:
                # Same model: MUST send same num_ctx as preload to prevent Ollama reload!
                # Ollama uses MODEL DEFAULT (not currently loaded context) when num_ctx is omitted.
                # Omitting num_ctx causes Ollama to reload with default → then main inference
                # sends calibrated num_ctx → Ollama reloads AGAIN. Two unnecessary reloads!
                auto_num_ctx: int | None = self.aifred_max_context if self.aifred_max_context else None
                log_message(f"🔧 Automatik = AIfred ({effective_auto}) → num_ctx={auto_num_ctx} (match preload)")

                # Warning if AIfred context is below recommended Automatik threshold
                effective_ctx = self.aifred_max_context or 0
                if effective_ctx > 0 and effective_ctx < AUTOMATIK_LLM_NUM_CTX:
                    self.add_debug(
                        f"⚠️ Automatik Context ({format_number(effective_ctx)}) < recommended ({format_number(AUTOMATIK_LLM_NUM_CTX)}) - Automatik tasks may be less reliable"
                    )
                    log_message(f"⚠️ Automatik Context warning: {effective_ctx} < {AUTOMATIK_LLM_NUM_CTX}")
            else:
                # Different model: use config constant
                auto_num_ctx = AUTOMATIK_LLM_NUM_CTX
                log_message(f"🔧 Automatik ≠ AIfred → Context: {auto_num_ctx}")

            # ============================================================
            # COLD START DETECTION (llama.cpp only)
            # llama-swap loads models on-demand — first request triggers cold start.
            # Check /running BEFORE the first LLM call so the user knows why it's slow.
            # ============================================================
            if self.backend_type == "llamacpp":
                try:
                    import httpx
                    swap_base = self.backend_url.rstrip("/").removesuffix("/v1")
                    async with httpx.AsyncClient(timeout=5.0) as http_client:
                        resp = await http_client.get(f"{swap_base}/running")
                        running_models = [m.get("model") for m in resp.json().get("running", [])]
                        if effective_auto not in running_models:
                            # Extract model details from llama-swap config
                            details = ""
                            try:
                                from .lib.llamacpp_calibration import parse_llamaswap_config
                                from .lib.config import LLAMASWAP_CONFIG_PATH
                                from .lib.formatting import format_number
                                model_info = parse_llamaswap_config(LLAMASWAP_CONFIG_PATH).get(effective_auto, {})
                                parts = []
                                if model_info.get("current_context"):
                                    parts.append(f"Context: {format_number(model_info['current_context'])}")
                                if model_info.get("kv_cache_quant"):
                                    parts.append(f"KV-Cache: {model_info['kv_cache_quant']}")
                                if parts:
                                    details = f" ({', '.join(parts)})"
                            except Exception:
                                pass
                            self.add_debug(f"🔄 Model Cold Start ({effective_auto}){details} — loading into VRAM, this may take a while")
                            log_message(f"🔄 Cold Start: {effective_auto}{details}")
                            yield
                except Exception:
                    pass  # Can't check — proceed normally, don't show false warnings

            # ============================================================
            # INTENT + ADDRESSEE + LANGUAGE DETECTION (first LLM call)
            # ============================================================
            # Must run BEFORE compression check to get detected_language
            from .lib.intent_detector import detect_query_intent_and_addressee

            # If user_msg is empty (image-only), skip Intent Detection and use UI language
            if not user_msg.strip():
                from .lib.prompt_loader import get_language
                detected_intent = "FAKTISCH"
                addressed_to = None
                detected_language = get_language()
                intent_raw = ""
                self.add_debug(f"🎯 Intent: {detected_intent} (image-only), Lang: {detected_language.upper()} (UI)")
                self._last_detected_language = detected_language  # Store for title generation
            else:
                detected_intent, addressed_to, detected_language, intent_raw = await detect_query_intent_and_addressee(
                    user_msg,
                    effective_auto,
                    llm_client,
                    automatik_num_ctx=auto_num_ctx
                )
                # Log Intent Detection result to UI debug console (always visible)
                addressee_display = addressed_to.capitalize() if addressed_to else "–"
                self.add_debug(f"🎯 Intent: {detected_intent}, Addressee: {addressee_display}, Lang: {detected_language.upper()}")
                self._last_detected_language = detected_language  # Store for title generation

            # ============================================================
            # PRE-MESSAGE: History Compression Check
            # ============================================================
            # Check BEFORE adding new message - handles session restore, model changes, etc.

            if self.chat_history:
                from .lib.context_manager import summarize_history_if_needed, get_largest_compression_model
                from .lib.research.context_utils import get_agent_num_ctx

                # Determine effective context limit using per-agent settings
                # Uses get_agent_num_ctx() which is the SINGLE SOURCE OF TRUTH
                context_limits = []

                # AIfred context
                aifred_ctx, _ = get_agent_num_ctx("aifred", self, self.aifred_model_id)
                context_limits.append(aifred_ctx)

                # Multi-agent contexts (if not standard mode)
                if self.multi_agent_mode != "standard":
                    if self.sokrates_model_id:
                        sokrates_ctx, _ = get_agent_num_ctx("sokrates", self, self.sokrates_model_id)
                        context_limits.append(sokrates_ctx)
                    if self.salomo_model_id:
                        salomo_ctx, _ = get_agent_num_ctx("salomo", self, self.salomo_model_id)
                        context_limits.append(salomo_ctx)

                # Use minimum of all agent limits
                context_limit = min(context_limits) if context_limits else 4096

                # Get system prompt tokens from cache (v2.14.0+)
                # Cache is populated at startup in on_load()
                from .lib.prompt_loader import get_max_system_prompt_tokens
                system_prompt_tokens = get_max_system_prompt_tokens(self.multi_agent_mode, detected_language)

                # Select largest model for compression (AIfred/Sokrates/Salomo)
                compression_model = get_largest_compression_model(
                    aifred_model=self.aifred_model_id,
                    sokrates_model=self.sokrates_model_id,
                    salomo_model=self.salomo_model_id
                )

                # Check and compress if needed (DUAL-HISTORY)
                async for event in summarize_history_if_needed(
                    history=self.chat_history,
                    llm_client=llm_client,
                    model_name=compression_model,  # Use largest available model for quality
                    context_limit=context_limit,
                    llm_history=self.llm_history,
                    system_prompt_tokens=system_prompt_tokens,
                    detected_language=detected_language  # From Intent Detection
                ):
                    if event["type"] == "history_update":
                        # DUAL-HISTORY: Update both histories
                        self.chat_history = event["chat_history"]
                        if event.get("llm_history") is not None:
                            self.llm_history = event["llm_history"]
                        self.add_debug(f"✅ Pre-Message Compression: {len(self.chat_history)} UI / {len(self.llm_history)} LLM messages")
                        yield
                    elif event["type"] == "debug":
                        self.add_debug(event["message"])
                        yield

            # NOTE: User message was already added to chat_history at the start of send_message()
            # (before XTTS check) so user sees their message immediately
            # ============================================================
            # DIALOG ROUTING (uses intent/addressee from above)
            # ============================================================

            # Track if Sokrates should be skipped (AIfred direct addressing)
            skip_sokrates_analysis = False

            if addressed_to == "sokrates":
                # User directly addresses Sokrates → Sokrates responds directly
                self.add_debug("🏛️ Direct addressing: Sokrates")
                yield  # Update UI immediately to show debug message
                async for _ in run_sokrates_direct_response(self, user_msg, detected_language):
                    yield
                # Clean up and return - Sokrates handled everything
                self.current_ai_response = ""
                self.current_user_message = ""
                self.is_generating = False
                self._save_current_session()
                yield
                return

            elif addressed_to == "aifred":
                # User directly addresses AIfred → Skip Sokrates analysis
                self.add_debug("🎩 Direct addressing: AIfred")
                yield  # Update UI immediately to show debug message
                skip_sokrates_analysis = True

            elif addressed_to == "salomo":
                # User directly addresses Salomo → Salomo responds directly
                self.add_debug("👑 Direct addressing: Salomo")
                yield  # Update UI immediately to show debug message
                async for _ in run_salomo_direct_response(self, user_msg, detected_language):
                    yield
                # Clean up and return - Salomo handled everything
                self.current_ai_response = ""
                self.current_user_message = ""
                self.is_generating = False
                self._save_current_session()
                yield
                return

            # ============================================================
            # VISION PIPELINE: Route to Vision-LLM if images present
            # ============================================================
            if has_pending_images:
                # CRITICAL FIX: Copy images to LOCAL variable BEFORE any yield!
                # Reflex State can be modified between yields, causing race conditions.
                # Deep copy ensures we keep the image data even if self.pending_images gets cleared.
                import copy
                local_images = copy.deepcopy(self.pending_images)

                # Clear pending images UI immediately (they're already in chat_history as HTML thumbnails)
                # This removes the editable thumbnails above the text input right away
                self.clear_pending_images()

                # Log Vision-LLM header + each image on separate line
                self.add_debug(f"📷 Vision-LLM ({self.vision_model}) analyzing:")
                for img in local_images:
                    self.add_debug(f"   • {img.get('name', 'unknown')}")
                yield  # Update UI immediately to show Vision Pipeline start

                # Save original user text (for Vision pipeline - may be empty!)
                original_user_text = user_msg

                # Import vision pipeline
                from .lib.conversation_handler import chat_with_vision_pipeline

                # NOTE: display_user_msg was already prepared and added to chat_history above (line ~3113)
                # No need to update it here - user panel is already correct

                # Build LLM options - use per-agent thinking toggle for enable_thinking
                from .lib.prompt_loader import get_thinking_enabled
                llm_options = {
                    'enable_thinking': get_thinking_enabled("aifred"),
                    'top_k': self.aifred_top_k,
                    'top_p': self.aifred_top_p,
                    'min_p': self.aifred_min_p,
                    'repeat_penalty': self.aifred_repeat_penalty,
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
                async for item in chat_with_vision_pipeline(
                    user_text=original_user_text,  # CRITICAL: Use original (may be empty!), not display_user_msg
                    images=local_images,  # CRITICAL: Use local copy, NOT self.pending_images!
                    vision_model=self.vision_model_id,  # Pure ID
                    main_model=self.aifred_model_id,  # Pure ID
                    backend_type=self.backend_type,
                    backend_url=self.backend_url,
                    llm_options=llm_options,
                    state=self,  # Pass entire state object (for per-agent num_ctx lookup)
                    detected_language=detected_language,  # From Intent Detection
                    provider=self.cloud_api_provider if self.backend_type == "cloud_api" else None
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
                        # Collect FULL response (with <think> tags) for later formatting
                        vision_readable_text += content
                        # Stream to UI WITHOUT <think> tags (will be shown as collapsible later)
                        # This prevents raw <think>...</think> from appearing during streaming
                        content_for_stream = strip_thinking_blocks(content)
                        self.stream_text_to_ui(content_for_stream)
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
                        from .lib.formatting import format_thinking_process

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

                        # Prepare Vision response content
                        if full_response:
                            # format_thinking_process() verarbeitet ALLE XML-Tags automatisch!
                            vision_content = format_thinking_process(
                                full_response,
                                model_name=self.vision_model_id,  # Pure ID
                                inference_time=vision_time,
                                tokens_per_sec=tokens_per_sec
                            )
                        elif vision_readable_text:
                            # Kein JSON, aber readable text vorhanden
                            vision_content = vision_readable_text
                        else:
                            # Neither JSON nor text - error
                            vision_content = "⚠️ Vision-LLM could not produce a result. See debug log."

                        # APPEND Vision response as separate panel
                        # Note: User panel was already created above with display_user_msg
                        self.add_agent_panel(
                            agent="aifred",  # Vision uses AIfred agent
                            content=vision_content,
                            mode="vision",
                            round_num=None,
                            metadata={
                                "inference_time": vision_time,
                                "tokens_per_sec": tokens_per_sec,
                                "source": f"Vision ({self.vision_model_id})"
                            },
                            sync_llm_history=False  # Sync manually below for proper formatting
                        )

                        # Sync to llm_history manually (strip thinking blocks)
                        response_clean = strip_thinking_blocks(full_response) if full_response else ""
                        if response_clean:
                            self.llm_history.append({"role": "assistant", "content": f"[AIFRED]: {response_clean}"})

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
                    self.add_debug("🎩 AIfred-LLM phase starting...")
                    yield

                    # Import here to avoid circular dependency
                    from .lib.conversation_handler import chat_interactive_mode

                    # Note: User message was already added to chat_history at the start of send_message()
                    # (line ~3058) with the image thumbnail. No need to add it again here.
                    self.current_ai_response = ""  # Reset for Main-LLM streaming

                    # Call chat_interactive_mode with Vision JSON context
                    # (EXACT same pattern as normal flow in line 2012-2027)
                    async for item in chat_interactive_mode(
                        user_text=original_user_text,
                        stt_time=0.0,
                        model_choice=self.aifred_model_id,
                        automatik_model=effective_auto,
                        history=self.chat_history,
                        llm_history=self.llm_history,
                        session_id=self.session_id,
                        temperature_mode=self.temperature_mode,
                        temperature=self.temperature,
                        llm_options=llm_options,
                        backend_type=self.backend_type,
                        backend_url=self.backend_url,
                        state=self,
                        pending_images=None,
                        vision_json_context=extracted_vision_json,
                        user_name=self.user_name,
                        detected_intent=detected_intent,
                        detected_language=detected_language,
                        cloud_provider_label=self.cloud_api_provider_label if self.backend_type == "cloud_api" else None,
                        automatik_num_ctx=auto_num_ctx
                    ):
                        # Handle Main-LLM items using NORMAL FLOW logic
                        if item["type"] == "debug":
                            self.add_debug(item["message"])
                            yield  # Update UI immediately for each debug message

                        elif item["type"] == "content":
                            # REAL-TIME streaming to UI via current_ai_response (NOT chat_history!)
                            # History is updated only at the end via "result" to avoid O(n) regex parsing on each token
                            self.stream_text_to_ui(item["text"])
                            yield

                        elif item["type"] == "result":
                            result_data = item["data"]
                            # Unified Dict format - history always included
                            self.chat_history = result_data["history"]

                            # Clear AI response and user message windows - yield IMMEDIATELY
                            self.current_ai_response = ""
                            self.current_user_message = ""
                            self.is_generating = False
                            yield

                            # Finalize streaming TTS and store audio URLs in message metadata
                            # (after yield so bubble is visible while waiting for TTS)
                            if self.enable_tts and self.tts_autoplay and self.tts_streaming_enabled:
                                # Wait for TTS completion and get combined audio URL
                                # (TTS tasks run in parallel via create_task, finalize waits for them)
                                audio_urls = await self._finalize_streaming_tts()
                                if audio_urls and self.chat_history:
                                    for i in range(len(self.chat_history) - 1, -1, -1):
                                        if self.chat_history[i].get("role") == "assistant":
                                            if "metadata" not in self.chat_history[i]:
                                                self.chat_history[i]["metadata"] = {}
                                            self.chat_history[i]["metadata"]["audio_urls"] = audio_urls
                                            self.chat_history[i]["has_audio"] = True
                                            self.chat_history[i]["audio_urls_json"] = json.dumps(audio_urls)
                                            log_message(f"🔊 TTS: Added {len(audio_urls)} audio URLs to message metadata (vision-mode)")
                                            break
                                    # Force Reflex to recognize the change by reassigning the list
                                    self.chat_history = list(self.chat_history)
                                    yield  # Update UI with audio button

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
                    # Note: pending_images already cleared at start of vision pipeline

                    # Clear both windows and stop generating
                    # (Response is already in chat_history, UI will show history)
                    self.current_ai_response = ""
                    self.current_user_message = ""
                    self.is_generating = False
                    yield  # Force UI update to show chat history

                # CRITICAL: Generate title and save session before early return
                # (finally block may not execute for async generators)
                async for _ in self._generate_session_title():
                    yield  # Forward UI updates from title generation
                self._save_current_session()
                self.refresh_session_list()
                yield

                return  # Exit send_message - vision pipeline complete

            # ============================================================
            # UNIFIED CHAT HANDLER (Single Source of Truth)
            # All modes (automatik, quick, deep, none) use chat_interactive_mode()
            # ============================================================

            from .lib.conversation_handler import chat_interactive_mode
            from .lib.prompt_loader import get_thinking_enabled

            llm_options = {
                'enable_thinking': get_thinking_enabled("aifred"),
                'top_k': self.aifred_top_k,
                'top_p': self.aifred_top_p,
                'min_p': self.aifred_min_p,
                'repeat_penalty': self.aifred_repeat_penalty,
            }
            result_data = None
            ai_text = ""

            # Single unified call - research_mode determines the path internally
            async for item in chat_interactive_mode(
                user_text=user_msg,
                stt_time=0.0,
                model_choice=self.aifred_model_id,
                automatik_model=effective_auto,
                history=self.chat_history,
                llm_history=self.llm_history,
                session_id=self.session_id,
                temperature_mode=self.temperature_mode,
                temperature=self.temperature,
                llm_options=llm_options,
                backend_type=self.backend_type,
                backend_url=self.backend_url,
                state=self,
                pending_images=self.pending_images if len(self.pending_images) > 0 else None,
                user_name=self.user_name,
                detected_intent=detected_intent,
                detected_language=detected_language,
                cloud_provider_label=self.cloud_api_provider_label if self.backend_type == "cloud_api" else None,
                research_mode=self.research_mode,
                automatik_num_ctx=auto_num_ctx
            ):
                # Route messages based on type
                if item["type"] == "debug":
                    self.add_debug(item["message"])
                    yield

                elif item["type"] == "content":
                    self.stream_text_to_ui(item["text"])
                    yield

                elif item["type"] == "result":
                    result_data = item["data"]
                    ai_text = result_data["response_clean"]
                    updated_history = result_data["history"]

                    # Extract sources
                    failed_sources = result_data.get("failed_sources", [])
                    used_sources = result_data.get("used_sources", [])

                    # Embed sources in last message for persistence
                    if updated_history:
                        import json as json_module
                        last_msg = updated_history[-1]
                        if last_msg.get("role") == "assistant":
                            if "metadata" not in last_msg:
                                last_msg["metadata"] = {}

                            all_failed = []
                            if failed_sources or self._pending_failed_sources:
                                all_failed = (self._pending_failed_sources or []) + (failed_sources or [])
                                if all_failed:
                                    failed_markup = f"<!--FAILED_SOURCES:{json_module.dumps(all_failed)}-->\n"
                                    last_msg["content"] = failed_markup + last_msg.get("content", "")
                                    last_msg["metadata"]["failed_sources"] = all_failed

                            if used_sources:
                                used_markup = f"<!--USED_SOURCES:{json_module.dumps(used_sources)}-->\n"
                                last_msg["content"] = used_markup + last_msg.get("content", "")
                                last_msg["metadata"]["used_sources"] = used_sources

                            last_msg["used_sources"] = used_sources or []
                            last_msg["failed_sources"] = all_failed or []

                    # Update State for UI
                    self.used_sources = used_sources or []
                    self.failed_sources = all_failed if 'all_failed' in dir() else []
                    self._pending_failed_sources = []
                    self._pending_used_sources = []

                    # Combine sources for UI display
                    combined = []
                    for src in (used_sources or []):
                        combined.append({
                            "url": src.get("url", ""),
                            "word_count": src.get("word_count", 0),
                            "rank_index": src.get("rank_index", 999),
                            "success": True
                        })
                    for src in (all_failed if 'all_failed' in dir() else []):
                        combined.append({
                            "url": src.get("url", ""),
                            "error": src.get("error", "Unknown"),
                            "rank_index": src.get("rank_index", 999),
                            "success": False
                        })
                    self.all_sources = sorted(combined, key=lambda x: x.get("rank_index", 999))

                    # Update history
                    self.chat_history = updated_history
                    if "llm_history" in result_data:
                        self.llm_history = result_data["llm_history"]

                    self.current_ai_response = ""
                    self.current_user_message = ""
                    yield

                    # Finalize streaming TTS
                    if self.enable_tts and self.tts_autoplay and self.tts_streaming_enabled:
                        audio_urls = await self._finalize_streaming_tts()
                        if audio_urls and self.chat_history:
                            for i in range(len(self.chat_history) - 1, -1, -1):
                                if self.chat_history[i].get("role") == "assistant":
                                    if "metadata" not in self.chat_history[i]:
                                        self.chat_history[i]["metadata"] = {}
                                    self.chat_history[i]["metadata"]["audio_urls"] = audio_urls
                                    self.chat_history[i]["has_audio"] = True
                                    self.chat_history[i]["audio_urls_json"] = json.dumps(audio_urls)
                                    log_message(f"🔊 TTS: Added {len(audio_urls)} audio URLs to message metadata")
                                    break
                            self.chat_history = list(self.chat_history)
                            yield

                    # Multi-Agent analysis
                    async for _ in self._maybe_run_multi_agent(
                        user_msg, ai_text, detected_language, skip_sokrates_analysis
                    ):
                        yield

                    self.is_generating = False
                    yield

                elif item["type"] == "progress":
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
                    self.chat_history = item["data"]
                    self.add_debug(f"📊 History updated: {len(item['data'])} messages")

                elif item["type"] == "thinking_warning":
                    self.thinking_mode_warning = item["model"]

                elif item["type"] == "failed_sources":
                    self.failed_sources = item["data"]
                    self._pending_failed_sources = item["data"]
                    from .lib.i18n import t
                    self.add_debug(f"⚠️ {t('sources_unavailable', count=len(item['data']))}")

                elif item["type"] == "error":
                    self.add_debug(f"❌ Error: {item.get('message', 'Unknown error')}")
                    self.is_generating = False
                    self.clear_progress()
                    self.current_user_message = ""
                    self.current_ai_response = ""

                yield

            # Final cleanup
            self.current_ai_response = ""
            yield

            # Debug line removed - User didn't want to see this
            # self.add_debug(f"✅ Response complete ({len(full_response)} chars)")

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self.current_ai_response = error_msg

            # APPEND error as separate panel
            # Note: User panel was already created above with user_msg/display_user_msg
            self.add_agent_panel(
                agent="aifred",
                content=error_msg,
                mode="error",
                round_num=None,
                metadata=None,  # No metrics for errors
                sync_llm_history=True  # Sync error to llm_history
            )

            self.add_debug(f"❌ Generation failed: {e}")
            import traceback
            self.add_debug(f"Traceback: {traceback.format_exc()}")

        finally:
            self.is_generating = False
            # NOTE: TTS polling stops automatically via data-polling attribute (MutationObserver)
            # Clear pending images after sending
            if len(self.pending_images) > 0:
                self.clear_pending_images()

            # TTS: Generate audio for AI response if enabled (BEFORE title generation for faster feedback)
            # IMPORTANT: Only for Standard mode! Multi-Agent modes generate TTS via add_agent_panel()
            # which adds to tts_audio_queue. This prevents duplicate TTS generation.
            # SKIP if streaming TTS is enabled - text was already sent sentence-by-sentence
            if self.enable_tts and self.multi_agent_mode == "standard" and not self.tts_streaming_enabled:
                try:
                    self.add_debug("🔊 TTS: Starting TTS generation...")
                    # Get AI response from llm_history (clean text without HTML formatting)
                    # Format: {"role": "assistant", "content": "[AGENT]: text"}
                    if len(self.llm_history) > 0:
                        last_msg = self.llm_history[-1]
                        if last_msg.get("role") == "assistant":
                            ai_response = last_msg.get("content", "")
                            # Extract agent from label prefix like "[AIFRED]: " or "[SOKRATES]: "
                            import re
                            agent = "aifred"  # Default
                            agent_match = re.match(r'^\[(AIFRED|SOKRATES|SALOMO)\]:\s*', ai_response)
                            if agent_match:
                                agent = agent_match.group(1).lower()
                                ai_response = ai_response[agent_match.end():]
                            if ai_response and ai_response.strip():
                                # Generate TTS and wait for completion
                                # This allows audio URL to be added to message metadata
                                await self._generate_tts_for_response(ai_response, agent=agent)
                                yield  # Update UI with audio button
                            else:
                                self.add_debug("⚠️ TTS: Enabled but no AI response to convert")
                                console_separator()
                                self.add_debug("────────────────────")
                        else:
                            self.add_debug("⚠️ TTS: Last message is not from assistant")
                            console_separator()
                            self.add_debug("────────────────────")
                    else:
                        self.add_debug("⚠️ TTS: Enabled but LLM history is empty")
                        console_separator()
                        self.add_debug("────────────────────")
                except Exception as tts_error:
                    self.add_debug(f"⚠️ TTS generation failed: {tts_error}")
                    log_message(f"❌ TTS error in finally block: {tts_error}")

            # Generate session title at end of flow (uses small Automatik model)
            # Only runs on first Q&A pair, skipped if title already exists
            async for _ in self._generate_session_title():
                yield  # Forward UI updates from title generation

            # Auto-Save: Session nach jeder Chat-Nachricht speichern
            # IMPORTANT: Save BEFORE refresh so message_count is up-to-date
            self._save_current_session()

            # Refresh session list to update sorting (last_seen changed) and message count
            self.refresh_session_list()
            yield

            # Final cleanup: Clear streaming state
            self.current_agent = ""
            self.current_ai_response = ""


    def clear_chat(self):
        """UI Event Handler: Clear chat history (shows debug message)."""
        if not self.logged_in_user:
            self.add_debug("⚠️ Bitte zuerst anmelden")
            return
        self._clear_chat_internal(silent=False)

    def _clear_chat_internal(self, silent: bool = False):
        """Internal: Clear chat history, pending images, and temporary files.

        Args:
            silent: If True, don't show "Chat cleared" debug message.
                    Used by new_session() to avoid confusing startup messages.
        """
        self.chat_history = []
        self.llm_history = []  # DUAL-HISTORY: LLM-History auch leeren!
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

        # Session-Bilder aufräumen (data/images/{session_id}/)
        if self.session_id:
            from .lib.vision_utils import cleanup_session_images
            try:
                deleted = cleanup_session_images(self.session_id)
                if deleted > 0:
                    self.add_debug(f"🗑️ {deleted} session image(s) deleted")
            except Exception as e:
                self.add_debug(f"⚠️ Image cleanup failed: {e}")

        # Session-Audio aufräumen (data/audio/{session_id}/)
        if self.session_id:
            from .lib.audio_processing import cleanup_session_audio
            try:
                deleted = cleanup_session_audio(self.session_id)
                if deleted > 0:
                    self.add_debug(f"🗑️ {deleted} session audio file(s) deleted")
            except Exception as e:
                self.add_debug(f"⚠️ Audio cleanup failed: {e}")

        # Clear Web-Quellen State (Sources Collapsible)
        self.used_sources = []
        self.failed_sources = []
        self.all_sources = []

        # Clear Sokrates Multi-Agent state
        self.sokrates_critique = ""
        self.sokrates_pro_args = ""
        self.sokrates_contra_args = ""
        self.show_sokrates_panel = False
        self.debate_round = 0
        self.debate_user_interjection = ""
        self.debate_in_progress = False

        # Clear Research Cache for this session
        # Wichtig: Sonst können alte (englische) Recherche-Daten wieder verwendet werden!
        if self.session_id:
            from .lib.cache_manager import delete_cached_research
            delete_cached_research(self.session_id)

        # Clear session title (new session has no title yet)
        self.current_session_title = ""

        # Clear title in session file too (so new title can be generated)
        if self.session_id:
            from .lib.session_storage import update_session_title
            update_session_title(self.session_id, "")  # Empty title = will regenerate

        if not silent:
            self.add_debug("🗑️ Chat cleared")
            # Separator after clear operation
            self.add_debug(CONSOLE_SEPARATOR)
            console_separator()  # Log-File

        # Session speichern (leerer Chat)
        self._save_current_session()

        # Refresh session list to show cleared title
        self.refresh_session_list()

    def refresh_session_list(self):
        """Refresh the list of available sessions for the session picker.

        Also synchronizes current session if it was modified externally
        (e.g., chat cleared in another tab/port).

        Additionally reconnects TTS SSE stream to ensure this device receives
        audio events (multi-device support - Last Writer Wins).
        """
        from .lib.session_storage import list_sessions, get_session_title, load_session

        # Only show sessions owned by logged in user
        self.available_sessions = list_sessions(owner=self.logged_in_user)

        # Update current session title
        if self.session_id:
            title = get_session_title(self.session_id)
            self.current_session_title = title or ""

            # Sync check: Compare local state with server state
            # If message counts differ, reload session from server
            session = load_session(self.session_id)
            if session and session.get("data"):
                server_count = len(session["data"].get("chat_history", []))
                local_count = len(self.chat_history)

                if server_count != local_count:
                    self.add_debug(f"🔄 Session changed externally ({local_count} → {server_count}), reloading...")
                    self._restore_session(session)
                    self.session_restored = True

        # Reconnect TTS SSE stream for this device (multi-device support)
        # When user clicks reload button, they signal "I want to work here now"
        # This ensures TTS audio plays on this device (Last Writer Wins)
        if self.session_id:
            return rx.call_script(f"if(window.startTtsStream) startTtsStream('{self.session_id}');")

    def switch_session(self, session_id: str):
        """Switch to a different session.

        Loads the target session and updates state.
        Note: No save here - sessions are auto-saved after each inference.
        """
        from .lib.session_storage import load_session
        from .lib.logging_utils import log_message

        self.add_debug(f"🔄 switch_session called: {session_id[:8] if session_id else 'None'}...")

        # If already on this session but chat_history is empty, reload it
        # (can happen when session_id was set from cookie but data wasn't loaded)
        if session_id == self.session_id:
            if self.chat_history:
                self.add_debug("⏭️ Already on this session, skipping")
                return
            else:
                self.add_debug("🔄 Same session but empty history, reloading...")

        # Load target session
        session = load_session(session_id)
        if session is None:
            self.add_debug(f"⚠️ Session {session_id[:8]}... not found, switching to newest")
            # Session was deleted - switch to newest available or create new
            self.refresh_session_list()
            if self.available_sessions:
                newest = self.available_sessions[0]
                self._load_session_by_id(newest["session_id"])
            else:
                self.new_session()
            return

        # Update session_id and load session data
        self.session_id = session_id
        data = session.get("data", {})

        # Load debug messages first (so subsequent add_debug calls are preserved)
        saved_debug = data.get("debug_messages", [])

        # Load chat history
        chat_history = data.get("chat_history", [])
        self.chat_history = chat_history
        self.llm_history = data.get("llm_history", [])

        # Normalize URLs to relative paths (fixes port-dependent image loading)
        self._normalize_upload_urls()

        # Restore debug messages and add load info
        self.debug_messages = saved_debug
        self.add_debug(f"📦 Loaded {len(chat_history)} messages")

        # Update session title
        self.current_session_title = data.get("title", "")

        # Clear streaming state
        self.current_ai_response = ""
        self.current_user_message = ""
        self.current_agent = ""

        # Note: Don't refresh_session_list() here - it would re-sort by last_seen
        # and move the clicked session to a different position. The highlighting
        # is based on session_id which is already updated above.

        log_message(f"📂 Switched to session: {session_id[:8]}...")
        self.add_debug(f"📂 Switched to session: {self.current_session_title or session_id[:8]}...")

        # Update session cookie for TTS SSE (so custom.js can open SSE on page reload)
        from .lib.browser_storage import set_session_id_script
        return rx.call_script(set_session_id_script(session_id))

    def new_session(self):
        """Create a new empty session and switch to it."""
        from .lib.session_storage import generate_session_id, create_empty_session
        from .lib.logging_utils import log_message

        # Must be logged in to create session
        if not self.logged_in_user:
            self.add_debug("⚠️ Not logged in")
            return

        # Note: No save here - sessions are auto-saved after each inference

        # Generate new device ID and create empty session file with owner
        new_id = generate_session_id()
        create_empty_session(new_id, owner=self.logged_in_user)

        # Switch to new device ID BEFORE clearing
        # (so clear_chat() cleans up the NEW session's directories)
        self.session_id = new_id
        self.current_session_title = ""

        # Reuse clear_chat() for state reset (avoids duplication)
        # silent=True: Avoid confusing "Chat cleared" message on new session creation
        self._clear_chat_internal(silent=True)

        # Refresh session list
        self.refresh_session_list()

        log_message(f"📄 Created new session: {new_id[:8]}...")

        # Update session cookie for TTS SSE (so custom.js can open SSE on page reload)
        from .lib.browser_storage import set_session_id_script
        return rx.call_script(set_session_id_script(new_id))

    def delete_session(self, session_id: str):
        """Delete a session (cannot delete current session)."""
        from .lib.session_storage import delete_session as storage_delete_session
        from .lib.logging_utils import log_message

        # Cannot delete current session
        if session_id == self.session_id:
            self.add_debug("⚠️ Cannot delete current session")
            return

        # Delete session
        if storage_delete_session(session_id):
            log_message(f"🗑️ Deleted session: {session_id[:8]}...")
            self.add_debug("🗑️ Session deleted")
            # Refresh list
            self.refresh_session_list()
        else:
            self.add_debug("⚠️ Failed to delete session")

    # ============================================================
    # Authentication (Login / Register / Logout)
    # ============================================================

    def set_login_username(self, value: str):
        """Set login username input (explicit setter for Reflex 0.9.0)."""
        self.login_username = value

    def set_login_password(self, value: str):
        """Set login password input (explicit setter for Reflex 0.9.0)."""
        self.login_password = value

    def handle_login_key_down(self, key: str):
        """Handle key press in login dialog - Enter triggers submit."""
        if key == "Enter":
            if self.login_mode == "login":
                return AIState.do_login
            else:
                return AIState.do_register

    def handle_login_submit(self, form_data: dict):
        """Handle form submit - for browser password manager support."""
        # Form submit triggered by Enter or Submit button
        # The actual login/register is handled by the button click handlers
        # This just prevents the default form submission (page reload)
        if self.login_mode == "login":
            return AIState.do_login
        else:
            return AIState.do_register

    def open_login_dialog(self, mode: str = "login"):
        """Open login dialog in specified mode."""
        self.login_mode = mode
        self.login_username = ""
        self.login_password = ""
        self.login_error = ""
        self.login_dialog_open = True

    def close_login_dialog(self):
        """Close login dialog and clear fields."""
        self.login_dialog_open = False
        self.login_username = ""
        self.login_password = ""
        self.login_error = ""

    def do_login(self):
        """Attempt to log in with entered credentials."""
        from .lib.session_storage import verify_account, account_exists, list_sessions
        from .lib.browser_storage import set_username_script

        username = self.login_username.strip()
        password = self.login_password

        if not username or not password:
            self.login_error = "Bitte Username und Passwort eingeben"
            return

        if not account_exists(username):
            self.login_error = "Account nicht gefunden"
            return

        if not verify_account(username, password):
            self.login_error = "Falsches Passwort"
            return

        # Login successful
        self.logged_in_user = username.lower()
        self.close_login_dialog()
        self.refresh_session_list()

        # Load most recent session or create new one
        sessions = list_sessions(owner=self.logged_in_user)
        if sessions:
            self._load_session_by_id(sessions[0]["session_id"])
            self.add_debug(f"✅ Logged in as: {self.logged_in_user}")
        else:
            self.new_session()
            self.add_debug(f"✅ Logged in as: {self.logged_in_user} (new)")

        # Save username AND session cookies + start TTS SSE stream
        # Combined into one script execution for simplicity
        from .lib.browser_storage import set_session_id_script
        combined_script = set_username_script(self.logged_in_user) + "; " + set_session_id_script(self.session_id) + f"; if(window.startTtsStream) startTtsStream('{self.session_id}');"
        return rx.call_script(combined_script)

    def do_register(self):
        """Attempt to create new account."""
        from .lib.session_storage import create_account, is_username_allowed
        from .lib.browser_storage import set_username_script

        username = self.login_username.strip()
        password = self.login_password

        if not username or not password:
            self.login_error = "Bitte Username und Passwort eingeben"
            return

        if not is_username_allowed(username):
            self.login_error = "Username nicht auf Whitelist"
            return

        if not create_account(username, password):
            self.login_error = "Account existiert bereits"
            return

        # Registration successful - auto login
        self.logged_in_user = username.lower()
        self.close_login_dialog()
        self.refresh_session_list()

        # New account always gets new session
        self.new_session()
        self.add_debug(f"✅ Account created: {self.logged_in_user}")

        # Save username AND session cookies + start TTS SSE stream
        from .lib.browser_storage import set_session_id_script
        combined_script = set_username_script(self.logged_in_user) + "; " + set_session_id_script(self.session_id) + f"; if(window.startTtsStream) startTtsStream('{self.session_id}');"
        return rx.call_script(combined_script)

    def do_logout(self):
        """Log out current user."""
        from .lib.browser_storage import clear_username_script

        self.add_debug(f"👋 Logged out: {self.logged_in_user}")
        self.logged_in_user = ""
        self.available_sessions = []
        self.session_id = ""
        # silent=True: Session data is preserved on disk, we're just clearing UI state
        self._clear_chat_internal(silent=True)

        # Show login dialog again
        self.login_dialog_open = True

        # Clear cookie
        return rx.call_script(clear_username_script())

    def share_chat(self):
        """Share chat history - export as HTML and open in new browser tab

        Creates a standalone HTML file with embedded CSS that looks like the AIfred UI.
        Uses the existing html_preview infrastructure for file management.
        """
        from datetime import datetime
        import mistune
        from .lib.formatting import _save_html_to_assets

        # Create markdown renderer with table support and URL auto-linking
        md = mistune.create_markdown(plugins=['table', 'strikethrough', 'url'])

        if not self.chat_history:
            self.add_debug("⚠️ No chat to share")
            return

        import re

        # Build HTML document
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        chat_title = self.current_session_title or ""
        html_parts = [self._get_export_html_header(timestamp, chat_title)]

        # Get username for display
        display_name = self.user_name if self.user_name else "User"

        # Import localization for failed sources
        from .lib.prompt_loader import get_language
        current_lang = get_language()
        if current_lang == "auto":
            current_lang = "de"

        for msg in self.chat_history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            agent = msg.get("agent", "aifred")
            mode = msg.get("mode", "")
            metadata = msg.get("metadata", {})

            if role == "user":
                # User message
                user_msg = content
                if not user_msg or not user_msg.strip():
                    continue

                # Convert markdown (for italic metadata like "*(Decision: 0,2s)*")
                user_msg_html = self._convert_markdown_preserve_html(user_msg, md)

                # Embed images as Base64 for portable HTML export
                from .lib.vision_utils import load_image_url_as_base64
                img_src_pattern = r'<img\s+src="([^"]*/_upload/[^"]+)"'
                img_matches = re.findall(img_src_pattern, user_msg_html)
                for img_url in img_matches:
                    base64_uri = load_image_url_as_base64(img_url)
                    if base64_uri:
                        user_msg_html = user_msg_html.replace(f'src="{img_url}"', f'src="{base64_uri}"')

                html_parts.append(f'''
                <div class="message user-message">
                    <div class="message-header">{display_name} 🙋</div>
                    <div class="message-content">{user_msg_html}</div>
                </div>
                ''')

            elif role == "assistant":
                # AI message
                ai_msg = content
                if not ai_msg or not ai_msg.strip():
                    continue

                # Extract sources from metadata or embedded comments
                used_sources_data = metadata.get("used_sources", [])
                failed_sources_data = metadata.get("failed_sources", [])

                # Check for embedded USED_SOURCES comment
                used_sources_pattern = r'<!--USED_SOURCES:(\[.*?\])-->\n?'
                used_sources_match = re.search(used_sources_pattern, ai_msg, re.DOTALL)
                if used_sources_match:
                    try:
                        import json as json_mod
                        embedded_data = json_mod.loads(used_sources_match.group(1))
                        if embedded_data:
                            used_sources_data = embedded_data
                        ai_msg = re.sub(used_sources_pattern, '', ai_msg, count=1)
                    except Exception:
                        pass

                # Check for embedded FAILED_SOURCES comment (legacy)
                failed_sources_pattern = r'<!--FAILED_SOURCES:(\[.*?\])-->\n?'
                failed_sources_match = re.search(failed_sources_pattern, ai_msg, re.DOTALL)
                if failed_sources_match:
                    try:
                        import json as json_mod
                        embedded_data = json_mod.loads(failed_sources_match.group(1))
                        if embedded_data:
                            failed_sources_data = embedded_data
                        ai_msg = re.sub(failed_sources_pattern, '', ai_msg, count=1)
                    except Exception:
                        pass

                # Build sources HTML (sorted by rank_index, mixed successful/failed)
                # Skip if content already contains a Web Sources collapsible
                sources_html = ""
                content_has_sources_collapsible = (
                    "Web-Quellen" in ai_msg or "Web Sources" in ai_msg
                ) and "<details" in ai_msg

                total_sources = len(used_sources_data) + len(failed_sources_data)
                if total_sources > 0 and not content_has_sources_collapsible:
                    # Header text
                    if current_lang == "de":
                        summary_text = f"{total_sources} Web-Quellen"
                        if failed_sources_data:
                            summary_text += f" ({len(failed_sources_data)} fehlgeschlagen)"
                        words_label = "Wörter"
                        sorted_label = "Sortiert nach Relevanz"
                    else:
                        summary_text = f"{total_sources} Web Sources"
                        if failed_sources_data:
                            summary_text += f" ({len(failed_sources_data)} failed)"
                        words_label = "words"
                        sorted_label = "Sorted by relevance"

                    # Combine and sort by rank_index
                    all_sources = []
                    for src in used_sources_data:
                        all_sources.append({
                            "url": src.get("url", ""),
                            "word_count": src.get("word_count", 0),
                            "rank_index": src.get("rank_index", 999),
                            "success": True
                        })
                    for src in failed_sources_data:
                        all_sources.append({
                            "url": src.get("url", ""),
                            "error": src.get("error", "Unknown"),
                            "rank_index": src.get("rank_index", 999),
                            "success": False
                        })
                    all_sources.sort(key=lambda x: x.get("rank_index", 999))

                    sources_list = []
                    for src in all_sources:
                        url = src.get('url', 'Unknown URL')
                        if src.get('success'):
                            word_count = src.get('word_count', 0)
                            sources_list.append(
                                f'<li class="used-source"><span class="source-icon">✓</span>'
                                f'<a href="{url}" target="_blank">{url}</a> '
                                f'<span class="source-info">({word_count} {words_label})</span></li>'
                            )
                        else:
                            error = src.get('error', 'Unknown error')
                            sources_list.append(
                                f'<li class="failed-source"><span class="source-icon">✗</span>'
                                f'<a href="{url}" target="_blank">{url}</a> '
                                f'<span class="failed-error">({error})</span></li>'
                            )

                    sources_html = f'''
                    <details class="sources-collapsible" style="font-size: 0.9em; margin-bottom: 1em; margin-top: 0.2em;">
                        <summary style="cursor: pointer; font-weight: bold; color: #aaa;">🔗 {summary_text}</summary>
                        <ul class="sources-list">
                            {"".join(sources_list)}
                        </ul>
                        <p style="font-size: 11px; font-style: italic; color: #7d8590; margin-top: 6px;">{sorted_label}</p>
                    </details>
                    '''

                ai_msg_stripped = ai_msg.strip()

                # Determine agent styling based on metadata or content
                if mode == "summary" or ai_msg_stripped.startswith("[📊"):
                    agent_class = "summary-message"
                    header = "📊 Summary"
                    ai_msg_content = ai_msg_stripped
                elif agent == "sokrates" or ai_msg_stripped.startswith("🏛️"):
                    agent_class = "sokrates-message"
                    mode_match = re.match(r'🏛️\s*\[([^\]]+)\]', ai_msg_stripped)
                    if mode_match:
                        mode_text = f" ({mode_match.group(1)})"
                        ai_msg_content = re.sub(r'^🏛️\s*\[[^\]]+\]\s*', '', ai_msg_stripped)
                    else:
                        mode_text = ""
                        ai_msg_content = ai_msg_stripped.lstrip("🏛️").lstrip()
                    header = f"🏛️ Sokrates{mode_text}"
                elif agent == "salomo" or ai_msg_stripped.startswith("👑"):
                    agent_class = "salomo-message"
                    mode_match = re.match(r'👑\s*\[([^\]]+)\]', ai_msg_stripped)
                    if mode_match:
                        mode_text = f" ({mode_match.group(1)})"
                        ai_msg_content = re.sub(r'^👑\s*\[[^\]]+\]\s*', '', ai_msg_stripped)
                    else:
                        mode_text = ""
                        ai_msg_content = ai_msg_stripped.lstrip("👑").lstrip()
                    header = f"👑 Salomo{mode_text}"
                else:
                    agent_class = "aifred-message"
                    mode_match = re.match(r'🎩\s*\[([^\]]+)\]', ai_msg_stripped)
                    if mode_match:
                        mode_text = f" ({mode_match.group(1)})"
                        ai_msg_content = re.sub(r'^🎩\s*\[[^\]]+\]\s*', '', ai_msg_stripped)
                    else:
                        mode_text = ""
                        ai_msg_content = ai_msg_stripped.lstrip("🎩").lstrip() if ai_msg_stripped.startswith("🎩") else ai_msg_stripped
                    header = f"🎩 AIfred{mode_text}"

                # Convert markdown to HTML
                ai_msg_html = self._convert_markdown_preserve_html(ai_msg_content, md)

                # Add line break after marker spans (e.g., "[Auto-Konsens: ...]")
                # The \n\n gets lost during markdown conversion, so add <br><br> after </span>
                ai_msg_html = re.sub(r'(</span>)(?!<br>)', r'\1<br><br>', ai_msg_html)

                # Embed audio as Base64 for portable HTML export
                audio_html = ""
                audio_urls = metadata.get("audio_urls", [])
                if audio_urls:
                    from .lib.audio_processing import load_audio_url_as_base64
                    # Get playback rate from CURRENT UI settings (not historical message metadata)
                    playback_rate = self.tts_agent_voices[agent]["speed"].replace("x", "")
                    audio_players = []
                    for audio_url in audio_urls:
                        base64_uri = load_audio_url_as_base64(audio_url)
                        if base64_uri:
                            # Set playback rate via onloadedmetadata (preload=metadata loads only duration/metadata, not full audio)
                            audio_players.append(
                                f'<audio controls src="{base64_uri}" preload="metadata" '
                                f'onloadedmetadata="this.playbackRate={playback_rate}"></audio>'
                            )
                    if audio_players:
                        audio_html = f'<div class="message-audio">{"".join(audio_players)}</div>'

                html_parts.append(f'''
                <div class="message {agent_class}">
                    <div class="message-header">{header}</div>
                    {sources_html}
                    <div class="message-content">{ai_msg_html}</div>
                    {audio_html}
                </div>
                ''')

        html_parts.append(self._get_export_html_footer())
        html_content = "\n".join(html_parts)

        # Save HTML file and get URL (with chat title for filename)
        preview_url = _save_html_to_assets(html_content, chat_title)

        self.add_debug(f"📋 Chat exported as HTML ({len(self.chat_history)} messages)")

        # Open in new browser tab via JavaScript
        js_script = f'window.open("{preview_url}", "_blank");'
        return rx.call_script(js_script)

    def _convert_markdown_preserve_html(self, text: str, md) -> str:
        """Convert markdown to HTML while preserving existing HTML elements.

        The AI response may contain:
        - Existing HTML (<details>, <span>, etc.) - preserve these
        - Markdown syntax (tables, **bold**, etc.) - convert to HTML

        Strategy: Extract HTML blocks, convert remaining markdown, restore HTML blocks.
        """
        import re

        # Extract and replace HTML blocks with unique placeholders
        placeholders = {}
        counter = [0]

        def extract_tag(tag_name: str, text: str) -> str:
            """Extract all occurrences of a specific HTML tag"""
            # Self-closing tags (img, br, hr, etc.)
            if tag_name in ['img', 'br', 'hr', 'input']:
                pattern = re.compile(
                    rf'<{tag_name}[^>]*(?:/>|>)',
                    re.IGNORECASE
                )
            else:
                # Match opening tag with any attributes, content (including newlines), and closing tag
                pattern = re.compile(
                    rf'<{tag_name}[^>]*>.*?</{tag_name}>',
                    re.DOTALL | re.IGNORECASE
                )

            def replace_match(match):
                placeholder = f"HTML_BLOCK_{counter[0]}"
                placeholders[placeholder] = match.group(0)
                counter[0] += 1
                return placeholder

            return pattern.sub(replace_match, text)

        # Extract HTML tags in order (most complex first)
        # Include 'a' and 'img' for embedded images in user messages
        text_with_placeholders = text
        for tag in ['details', 'div', 'span', 'table', 'a', 'img']:
            text_with_placeholders = extract_tag(tag, text_with_placeholders)

        # Convert markdown to HTML
        html_output = md(text_with_placeholders)

        # Restore preserved HTML blocks
        # Note: mistune may wrap placeholders in <p> tags, so we need to handle that
        for placeholder, original_html in placeholders.items():
            # Try various wrapper combinations that mistune might create
            html_output = html_output.replace(f"<p>{placeholder}</p>", original_html)
            html_output = html_output.replace(f"<p>{placeholder}\n</p>", original_html)
            html_output = html_output.replace(placeholder, original_html)

        # Convert metrics lines from <em>( ... )</em> to <span class="metrics">...</span>
        # Metrics pattern: *( Inference: Xs    Y tok/s    Source: ... )*
        metrics_pattern = re.compile(r'<em>\(\s*((?:TTFT|Inference):[^)]+)\s*\)</em>')
        html_output = metrics_pattern.sub(r'<span class="metrics">( \1 )</span>', html_output)

        # Ensure all links open in new tab (mistune's url plugin doesn't add target)
        html_output = self._add_target_blank_to_links(html_output)

        return html_output

    def _add_target_blank_to_links(self, html: str) -> str:
        """Add target="_blank" to all <a> tags that don't have it yet."""
        import re

        def add_target(match):
            tag = match.group(0)
            # Skip if already has target attribute
            if 'target=' in tag:
                return tag
            # Add target="_blank" before the closing >
            return tag[:-1] + ' target="_blank" rel="noopener noreferrer">'

        return re.sub(r'<a\s[^>]*>', add_target, html)

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters in user input"""
        return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
            .replace("\n", "<br>"))

    def _get_export_html_header(self, timestamp: str, title: str = "") -> str:
        """Generate HTML header with embedded CSS for chat export"""
        # KaTeX Assets inline einbetten (Fonts als Base64)
        from .lib.formatting import get_katex_inline_assets
        katex_assets = get_katex_inline_assets()
        katex_css = katex_assets.get('css', '')
        katex_js = katex_assets.get('js', '')
        mhchem_js = katex_assets.get('mhchem_js', '')
        autorender_js = katex_assets.get('autorender_js', '')

        # Use session title if available, otherwise generic
        html_title = f"🎩 AIfred - {title}" if title else "🎩 AIfred Intelligence - Chat Export"

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html_title}</title>
    <!-- KaTeX CSS mit eingebetteten Fonts -->
    <style>{katex_css}</style>
    <!-- KaTeX JavaScript -->
    <script>{katex_js}</script>
    <script>{mhchem_js}</script>
    <script>{autorender_js}</script>
    <script>
        document.addEventListener("DOMContentLoaded", function() {{
            renderMathInElement(document.body, {{
                delimiters: [
                    {{left: '$$', right: '$$', display: true}},
                    {{left: '$', right: '$', display: false}}
                ],
                throwOnError: false
            }});
        }});
    </script>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background-color: #0d1117;
            color: #e6edf3;
            line-height: 1.4;
            padding: 20px;
            max-width: 1000px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            padding: 20px;
            border-bottom: 1px solid #30363d;
            margin-bottom: 20px;
        }}
        .header h1 {{
            color: #e67700;
            font-size: 1.8em;
            margin-bottom: 5px;
        }}
        .header .timestamp {{
            color: #7d8590;
            font-size: 0.9em;
        }}
        .message {{
            margin-bottom: 15px;
            padding: 15px;
            border-radius: 8px;
        }}
        .message-header {{
            font-weight: bold;
            margin-bottom: 8px;
            font-size: 0.95em;
        }}
        .message-content {{
            word-wrap: break-word;
        }}
        /* Kompakte Abstände für Content-Elemente */
        .message-content p,
        .message-content ul,
        .message-content ol,
        .message-content table,
        .message-content details {{
            margin: 0 0 1em 0;
        }}
        /* Überschriften: mehr Abstand oben (Trennung), etwas Abstand unten */
        .message-content h1,
        .message-content h2,
        .message-content h3,
        .message-content h4 {{
            margin: 0.9em 0 0.3em 0;
            color: #e6edf3;
        }}
        .message-content h2 {{
            font-size: 1.3em;
            border-bottom: 1px solid #30363d;
            padding-bottom: 0.1em;
        }}
        .message-content h3 {{
            font-size: 1.1em;
        }}
        .message-content ul, .message-content ol {{
            padding-left: 1.5em;
        }}
        .message-content li {{
            margin: 0.1em 0;
        }}
        .message-content table {{
            border-collapse: collapse;
            width: 100%;
            font-size: 0.95em;
            margin: 1em 0;
        }}
        .message-content table th,
        .message-content table td {{
            border: 1px solid #30363d;
            padding: 8px 12px;
            text-align: left;
        }}
        .message-content table th {{
            background-color: #21262d;
            font-weight: bold;
            color: #e6edf3;
        }}
        .message-content table tr:nth-child(even) {{
            background-color: rgba(48, 54, 61, 0.3);
        }}
        /* Embedded chat images */
        .chat-image {{
            max-width: 300px;
            max-height: 300px;
            border-radius: 8px;
            margin: 8px 0;
            cursor: pointer;
            transition: transform 0.2s;
        }}
        .chat-image:hover {{
            transform: scale(1.02);
        }}
        /* User: box with border */
        .user-message {{
            background-color: #21262d;
            border: 1px solid #30363d;
            text-align: right;
            padding-right: 85px;
        }}
        .user-message .chat-image {{
            float: right;
            clear: both;
            margin-left: 10px;
        }}
        .user-message .message-header {{
            color: #c06050;
            text-align: right;
            margin-right: -70px;
        }}
        /* AIfred: box with border + left accent */
        .aifred-message {{
            background-color: #161b22;
            border: 1px solid #30363d;
            border-left: 3px solid #e67700;
        }}
        .aifred-message .message-header {{
            color: #e67700;
        }}
        /* Sokrates: full box with border */
        .sokrates-message {{
            background-color: #161b22;
            border: 1px solid #30363d;
            border-left: 3px solid #a371f7;
        }}
        .sokrates-message .message-header {{
            color: #a371f7;
        }}
        /* Salomo: full box with border */
        .salomo-message {{
            background-color: #161b22;
            border: 1px solid #30363d;
            border-left: 3px solid #d29922;
        }}
        .salomo-message .message-header {{
            color: #d29922;
        }}
        .summary-message {{
            background-color: #1c1c1c;
            border-left: 3px solid #7d8590;
        }}
        .summary-message .message-header {{
            color: #7d8590;
        }}
        /* Audio player styling */
        .message-audio {{
            margin-top: 12px;
            padding-top: 10px;
            border-top: 1px solid #30363d;
        }}
        .message-audio audio {{
            width: 100%;
            max-width: 400px;
            height: 36px;
            border-radius: 8px;
        }}
        /* Collapsible details styling */
        details {{
            border: 1px solid #30363d;
            border-radius: 6px;
            background-color: #0d1117;
        }}
        summary {{
            cursor: pointer;
            padding: 8px;
            font-weight: bold;
            color: #7d8590;
            background-color: #161b22;
            border-radius: 6px 6px 0 0;
        }}
        summary:hover {{
            background-color: #21262d;
        }}
        details[open] summary {{
            border-bottom: 1px solid #30363d;
            border-radius: 6px 6px 0 0;
        }}
        details > div {{
            padding: 8px;
        }}
        .thinking-compact {{
            color: #aaa;
            font-size: 0.9em;
            line-height: 1.3;
        }}
        .thinking-compact p {{
            margin: 0.3em 0;
        }}
        /* Web Sources Collapsible */
        .sources-collapsible {{
            margin-bottom: 12px;
            border: 1px solid #30363d;
            border-radius: 6px;
        }}
        .sources-collapsible summary {{
            color: #8b949e;
            background-color: rgba(139, 148, 158, 0.1);
            padding: 8px 12px;
            cursor: pointer;
            border-radius: 6px;
        }}
        .sources-collapsible summary:hover {{
            background-color: rgba(139, 148, 158, 0.2);
        }}
        .sources-list {{
            list-style: none;
            padding: 8px 12px;
            margin: 0;
        }}
        .sources-list li {{
            padding: 4px 0;
            border-bottom: 1px solid #30363d;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .sources-list li:last-child {{
            border-bottom: none;
        }}
        .sources-list .source-icon {{
            font-size: 12px;
            width: 16px;
            text-align: center;
        }}
        .sources-list .used-source .source-icon {{
            color: #4ade80;
        }}
        .sources-list .failed-source .source-icon {{
            color: #d29922;
        }}
        .sources-list a {{
            color: #56d4dd;
            text-decoration: underline;
            word-break: break-all;
        }}
        .sources-list a:hover {{
            color: #a0f0ff;
        }}
        .source-info {{
            color: #7d8590;
            font-size: 0.85em;
        }}
        .failed-error {{
            color: #7d8590;
            font-size: 0.85em;
            font-style: italic;
        }}
        /* Footer */
        .footer {{
            text-align: center;
            padding: 20px;
            border-top: 1px solid #30363d;
            margin-top: 20px;
            color: #7d8590;
            font-size: 0.85em;
        }}
        .footer a {{
            color: #56d4dd;
            text-decoration: underline;
        }}
        .footer a:hover {{
            color: #a0f0ff;
        }}
        /* Global link styling (for embedded content) */
        a {{
            color: #56d4dd;
            text-decoration: underline;
        }}
        a:hover {{
            color: #a0f0ff;
        }}
        /* Italic text (normal markdown *text*) */
        em {{
            font-style: italic;
            color: inherit;
        }}
        /* Metrics styling (wrapped in .metrics class) */
        .metrics {{
            color: #7d8590;
            font-style: normal;
            font-size: 0.85em;
            display: block;
            margin-top: 8px;
        }}
        /* Code blocks */
        pre, code {{
            background-color: #161b22;
            border-radius: 4px;
            font-family: 'Courier New', Consolas, monospace;
        }}
        pre {{
            padding: 8px;
            overflow-x: auto;
            margin: 0.3em 0;
        }}
        code {{
            padding: 2px 5px;
        }}
        /* Tables (from markdown) */
        th, td {{
            border: 1px solid #30363d;
            padding: 6px 10px;
            text-align: left;
        }}
        th {{
            background-color: #21262d;
            font-weight: bold;
            color: #e6edf3;
        }}
        tr:nth-child(even) {{
            background-color: #161b22;
        }}
        tr:hover {{
            background-color: #21262d;
        }}
        /* Bold and italic */
        strong {{
            color: #f0f6fc;
        }}
        /* KaTeX Block-Formeln zentrieren */
        .katex-display {{
            margin: 0.5em 0;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎩 AIfred Intelligence</h1>
        <div class="timestamp">Chat Export • {timestamp}</div>
    </div>
'''

    def _get_export_html_footer(self) -> str:
        """Generate HTML footer for chat export"""
        return '''
    <div class="footer">
        <p>Exported from <a href="https://github.com/Peuqui/AIfred-Intelligence" target="_blank">AIfred Intelligence</a></p>
        <p>AI at your service • Multi-Agent Debate System</p>
    </div>
</body>
</html>
'''

    # ============================================================
    # Session Persistence (Username-based authentication)
    # ============================================================

    def handle_username_loaded(self, username: str):
        """
        Callback nach Cookie-Read via rx.call_script().

        Wird aufgerufen wenn das JavaScript den Username aus dem Cookie gelesen hat.
        Prüft ob Account existiert und loggt ein, sonst Login-Dialog öffnen.
        """
        print(f"🔑 handle_username_loaded called: username='{username}'")

        # Guard: Nur einmal ausführen
        if self._session_initialized:
            print("⏭️ Session already initialized, skipping")
            return
        self._session_initialized = True

        from .lib.session_storage import account_exists, list_sessions

        if username and account_exists(username):
            # Valid username in cookie - auto login
            self.logged_in_user = username.lower()
            self.login_dialog_open = False
            self.refresh_session_list()

            # Load most recent session if available
            sessions = list_sessions(owner=self.logged_in_user)
            if sessions:
                # Switch to most recent session
                most_recent = sessions[0]
                self._load_session_by_id(most_recent["session_id"])
                self.add_debug(f"✅ Logged in as: {self.logged_in_user}")
            else:
                # No sessions yet - create first one
                self.new_session()
                self.add_debug(f"✅ Logged in as: {self.logged_in_user} (new)")

            console_separator()  # File log
            self.debug_messages.append("────────────────────")  # UI

            # Set session cookie AND start TTS SSE stream
            # The cookie allows custom.js to open SSE immediately on next page load
            from .lib.browser_storage import set_session_id_script
            combined_script = f"""
                {set_session_id_script(self.session_id)}
                if(window.startTtsStream) startTtsStream('{self.session_id}');
            """
            return rx.call_script(combined_script)
        else:
            # No valid username - dialog stays open (default is True)
            self.add_debug("🔐 Login required")

    def _load_session_by_id(self, session_id: str):
        """Load a specific session by ID (internal helper)."""
        from .lib.session_storage import load_session, get_session_title
        from .lib.context_manager import estimate_tokens_from_history
        from .lib.formatting import format_number
        from .lib.config import HISTORY_COMPRESSION_TRIGGER

        self.session_id = session_id
        session = load_session(session_id)

        if session and session.get("data"):
            self._restore_session(session)
            self.session_restored = True

            # Update title
            title = get_session_title(session_id)
            self.current_session_title = title or ""

            # Show context utilization after session restore
            if self.chat_history:
                estimated_tokens = estimate_tokens_from_history(self.chat_history)

                if self._min_agent_context_limit > 0:
                    utilization = (estimated_tokens / self._min_agent_context_limit) * 100
                    self.add_debug(f"   └─ History: {format_number(estimated_tokens)} / {format_number(self._min_agent_context_limit)} tok ({int(utilization)}%)")

                    # Warn if compression will trigger on next message
                    if utilization >= HISTORY_COMPRESSION_TRIGGER * 100:
                        self.add_debug(f"⚠️ History compression will trigger on next message (>{int(HISTORY_COMPRESSION_TRIGGER * 100)}%)")
                else:
                    self.add_debug(f"   └─ History: {format_number(estimated_tokens)} tokens")
        else:
            self.session_restored = False

    def handle_tts_callback(self, result: str):
        """
        Callback nach TTS rx.call_script() Ausführung.

        Wird aufgerufen wenn das JavaScript das TTS-Script ausgeführt hat.
        Dient hauptsächlich zum Debugging.
        """
        self.add_debug(f"🔊 TTS callback received: {result}")

    def _normalize_upload_urls(self):
        """
        Konvertiert absolute URLs in chat_history zu relativen URLs.

        Behebt das Problem, dass Sessions die auf einem Port erstellt wurden
        (z.B. 8443) nicht korrekt von einem anderen Port (z.B. 443) aus
        geladen werden können.

        Pattern: http(s)://host:port/_upload/... → /_upload/...
        """
        import re

        for msg in self.chat_history:
            # Skip invalid messages
            if not isinstance(msg, dict):
                continue

            # 1. Normalisiere URLs im content (HTML)
            content = msg.get("content")
            if content and isinstance(content, str):
                msg["content"] = re.sub(
                    r'https?://[^/]+/_upload/',
                    '/_upload/',
                    content
                )

            # 2. Normalisiere URLs in metadata.images
            images = msg.get("metadata", {}).get("images")
            if images and isinstance(images, list):
                for img in images:
                    if isinstance(img, dict):
                        url = img.get("url")
                        if url and isinstance(url, str):
                            img["url"] = re.sub(
                                r'https?://[^/]+/_upload/',
                                '/_upload/',
                                url
                            )

    def _restore_session(self, session: dict):
        """
        Stellt Chat-History aus gespeicherter Session wieder her.

        DUAL-HISTORY (v2.13.0+):
        - chat_history: UI-vollständig (Original-Messages erhalten)
        - llm_history: LLM-komprimiert (ready-to-use für LLM-Aufrufe)

        Args:
            session: Session-Dict mit "data" Feld
        """
        data = session.get("data", {})

        # Chat-History wiederherstellen (dict-based format)
        # PRE-MESSAGE Check in send_message() prüft automatisch ob Kompression nötig ist
        # WICHTIG: Auch leere Listen setzen (für API-Clear)!
        if "chat_history" in data:
            stored = data["chat_history"]
            # Check format: new dict-based or old tuple-based
            if stored and isinstance(stored[0], (list, tuple)):
                # Old tuple format - Clean Break, ignore old sessions
                self.chat_history = []
                self.add_debug("⚠️ Old session format detected - starting fresh")
            else:
                # New dict format - use directly
                self.chat_history = stored if stored else []
                # Normalize URLs to relative paths (fixes port-dependent image loading)
                self._normalize_upload_urls()

        # DUAL-HISTORY (v2.13.0+): llm_history laden
        # WICHTIG: Auch leere Listen setzen (für API-Clear)!
        if "llm_history" in data:
            self.llm_history = data["llm_history"]
        else:
            # Keine llm_history → leere Liste (alte Sessions werden nicht migriert)
            self.llm_history = []

        # DEBUG-PERSISTENCE (v2.14.0+): debug_messages wiederherstellen
        # Saved messages (from before restart) come first, then startup messages
        # This keeps chronological order: session messages < startup/login messages
        if "debug_messages" in data:
            if data["debug_messages"]:
                startup_messages = self.debug_messages.copy()
                self.debug_messages = data["debug_messages"] + startup_messages
            else:
                # Explizit gelöscht (z.B. via API clear_chat) → auch Startup-Messages entfernen
                self.debug_messages = []

        # Session title wiederherstellen
        self.current_session_title = data.get("title", "")

        # Note: Don't refresh_session_list() here - it's called once in on_load()
        # and only needs updating when new messages are sent (via _save_current_session)

    def _save_current_session(self):
        """
        Speichert aktuelle Session auf Server.

        Wird nach jeder Chat-Änderung aufgerufen (Auto-Save).
        Nur speichern wenn session_id vorhanden (Session initialisiert).
        DUAL-HISTORY (v2.13.0+): Speichert sowohl chat_history als auch llm_history.
        """
        if not self.session_id:
            return

        from .lib.session_storage import update_chat_data
        from .lib.config import DEBUG_LOG_MAX_ENTRIES

        # DEBUG-PERSISTENCE: Keep only last N entries
        debug_to_save = self.debug_messages[-DEBUG_LOG_MAX_ENTRIES:] if self.debug_messages else []

        update_chat_data(
            session_id=self.session_id,
            chat_history=self.chat_history,
            chat_summaries=None,  # Aktuell nicht persistiert
            llm_history=self.llm_history,  # DUAL-HISTORY: LLM-komprimierte History
            debug_messages=debug_to_save,  # DEBUG-PERSISTENCE: Last N debug entries
            is_generating=self.is_generating,  # API status check
            owner=self.logged_in_user  # Required for session creation
        )

    async def _generate_session_title(self):
        """
        Generate a chat title using LLM based on first Q&A pair.

        This is an async generator that yields for UI updates during title generation.
        Called at the END of send_message() flow (in finally block).
        Uses the Automatik model (same as Intent Detection and other Automatik tasks).

        Only executes on first Q&A pair - skipped if title already exists.

        Yields:
            None - yields are for UI updates only
        """
        from .lib.session_storage import get_session_title, update_session_title
        from .lib.prompt_loader import load_prompt, get_language
        from .lib.llm_client import LLMClient
        from .lib.logging_utils import log_message, console_separator

        # Skip if already has title
        if self.current_session_title:
            return

        existing_title = get_session_title(self.session_id)
        if existing_title:
            self.current_session_title = existing_title
            return

        # Need at least 2 messages (user + assistant)
        # Use llm_history - it's already cleaned (no think tags, no HTML)
        if len(self.llm_history) < 2:
            return

        # Find first user message and first assistant response from llm_history
        first_user_msg = None
        first_ai_response = None

        for msg in self.llm_history:
            content = msg.get("content", "")
            if msg.get("role") == "user" and first_user_msg is None:
                first_user_msg = content
            elif msg.get("role") == "assistant" and first_ai_response is None:
                # llm_history has "[AIFRED]: " prefix - remove it
                if content.startswith("[AIFRED]: "):
                    content = content[10:]
                first_ai_response = content

            if first_user_msg and first_ai_response:
                break

        # Vision-Only: If no user text but AI response exists, use placeholder
        # This allows title generation for image-only uploads
        if not first_user_msg and first_ai_response:
            first_user_msg = "📷 [Bildanalyse]"  # Placeholder for title generation

        if not first_user_msg or not first_ai_response:
            return

        # Clean up any remaining HTML/tags (llm_history should be clean, but just in case)
        import re
        first_user_msg = re.sub(r'<[^>]+>', '', first_user_msg).strip()
        first_ai_response = re.sub(r'<[^>]+>', '', first_ai_response).strip()

        # Truncate if too long (keep first ~500 chars each)
        if len(first_user_msg) > 500:
            first_user_msg = first_user_msg[:500] + "..."
        if len(first_ai_response) > 500:
            first_ai_response = first_ai_response[:500] + "..."

        # Track whether title was successfully generated (for finally block)
        _title_done = False

        try:
            # Show user that title is being generated (can take a few seconds)
            self.add_debug("🏷️ Generating session title...")
            yield  # Update UI immediately to show "Generating..." message

            # Load prompt in detected language (from Intent Detection, fallback to UI language)
            prompt = load_prompt(
                "utility/chat_title",
                lang=self._last_detected_language or get_language(),
                user_message=first_user_msg,
                ai_response=first_ai_response
            )

            title_model = self._effective_automatik_id

            llm_client = LLMClient(
                backend_type=self.backend_type,
                base_url=self._get_backend_url(),
                provider=self.cloud_api_provider if self.backend_type == "cloud_api" else None
            )

            messages = [{"role": "user", "content": prompt}]

            # num_ctx: Must match the currently loaded context to avoid Ollama reload.
            # Ollama uses model DEFAULT (not currently loaded ctx) when num_ctx is omitted.
            # → omitting num_ctx after main inference would cause a full reload (5-28s penalty).
            if title_model == self.aifred_model_id and self.aifred_max_context:
                # Same model as main LLM → reuse calibrated context, no reload
                title_num_ctx = self.aifred_max_context
            else:
                from .lib.config import AUTOMATIK_LLM_NUM_CTX
                title_num_ctx = AUTOMATIK_LLM_NUM_CTX

            options = {
                "temperature": 0.3,  # Low temperature for consistent titles
                "num_predict": 300,  # Room for reasoning (~100-150 tok) + title (~10 tok)
                "enable_thinking": False,  # Respected by Qwen3; GPT-OSS ignores it but works via num_predict headroom
                "num_ctx": title_num_ctx,
            }

            # Timeout: Title generation runs AFTER is_generating=False.
            # Large models (120B+) need significant PP time even for short prompts.
            import asyncio
            response = await asyncio.wait_for(
                llm_client.chat(
                    model=title_model,
                    messages=messages,
                    options=options
                ),
                timeout=30.0
            )

            # Extract and clean title - strip thinking blocks first!
            title = response.text.strip()
            title = strip_thinking_blocks(title)  # Remove <think>...</think>
            # Remove quotes if present
            title = title.strip('"\'')
            # Remove trailing punctuation
            title = title.rstrip('.!?:')

            if title:
                update_session_title(self.session_id, title)
                self.current_session_title = title
                # Note: refresh_session_list() is called in send_message() finally block

                # Debug output with closing separator
                self.add_debug(f"🏷️ Session title: {title}")
                console_separator()
                self.add_debug("────────────────────")
                _title_done = True
                yield  # Update UI to show generated title
            else:
                # LLM returned empty/thinking-only response
                log_message("⚠️ Title generation: LLM returned empty title")
                self.add_debug("⚠️ Session title: empty response")
                self.add_debug("────────────────────")
                _title_done = True

        except asyncio.TimeoutError:
            log_message("⚠️ Title generation timed out (>30s) - skipping")
            self.add_debug("⚠️ Session title: Timeout (>30s)")
            self.add_debug("────────────────────")
            _title_done = True
        except Exception as e:
            log_message(f"⚠️ Title generation failed: {e}")
            self.add_debug(f"⚠️ Session title failed: {e}")
            self.add_debug("────────────────────")
            _title_done = True
        finally:
            # Catch silent cancellations: GeneratorExit (aclose) and CancelledError
            # bypass except Exception. Log so user sees what happened.
            if not _title_done:
                log_message("⚠️ Title generation cancelled (generator closed)")
                self.add_debug("⚠️ Session title: cancelled")
                self.add_debug("────────────────────")

    def _get_backend_url(self) -> str:
        """Get current backend URL based on backend_type."""
        # Use already imported config from .lib.config (top of file)
        if self.backend_type == "ollama":
            return config.DEFAULT_OLLAMA_URL
        elif self.backend_type == "vllm":
            return config.DEFAULT_VLLM_URL
        elif self.backend_type == "tabbyapi":
            return config.DEFAULT_TABBY_URL
        elif self.backend_type == "llamacpp":
            return config.DEFAULT_LLAMACPP_URL
        elif self.backend_type == "cloud_api":
            # Cloud API URL is determined by provider in BackendFactory
            return None
        return config.DEFAULT_OLLAMA_URL

    # ============================================================
    # Image Upload Handlers
    # ============================================================

    def on_camera_click(self):
        """Debug message when camera button is clicked"""
        self.add_debug("📷 Opening camera...")
        yield

    def on_file_picker_click(self):
        """Debug message when file picker button is clicked"""
        self.add_debug("🖼️ Opening file picker...")
        yield

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
            resize_image_if_needed,
            save_image_to_file,
            get_image_url
        )

        # Show loading state immediately
        self.is_uploading_image = True

        # Log upload start with file count (visible feedback for slow mobile connections)
        file_count = len(files) if hasattr(files, '__len__') else 1
        source = "camera" if from_camera else "file picker"
        self.add_debug(f"📤 Uploading {file_count} image(s) from {source}...")
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

                # Save image as file (not Base64 in memory)
                # Uses session_id for persistent session-based storage
                image_path = save_image_to_file(resized_content, self.session_id, display_name)
                image_url = get_image_url(image_path)

                # Store with file path (for LLM) and URL (for UI)
                self.pending_images.append({
                    "name": display_name,
                    "path": str(image_path),  # Absolute path for LLM loading
                    "url": image_url,         # HTTP URL for UI display
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
    # REASONING/THINKING HELP MODAL HANDLERS
    # ============================================================

    def open_reasoning_thinking_help(self):
        """Opens the reasoning/thinking explanation modal"""
        self.reasoning_thinking_help_open = True

    def close_reasoning_thinking_help(self):
        """Closes the reasoning/thinking explanation modal"""
        self.reasoning_thinking_help_open = False

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
            self.crop_rotation = 0  # Reset rotation
            self.crop_modal_open = True
            self.add_debug(f"✂️ Crop mode opened for: {self.pending_images[index]['name']}")

    def cancel_crop(self):
        """Schließt Modal ohne Änderung"""
        self.crop_modal_open = False
        self.crop_image_index = -1
        self.crop_preview_url = ""
        self.crop_rotation = 0  # Reset rotation

    def rotate_crop_image_left(self):
        """Rotate image 90° counter-clockwise in crop preview"""
        self._rotate_crop_image(clockwise=False)

    def rotate_crop_image_right(self):
        """Rotate image 90° clockwise in crop preview"""
        self._rotate_crop_image(clockwise=True)

    def _rotate_crop_image(self, clockwise: bool = True):
        """Internal: Rotate image 90° in crop preview"""
        from PIL import Image
        from pathlib import Path

        if self.crop_image_index < 0 or self.crop_image_index >= len(self.pending_images):
            return

        image_data = self.pending_images[self.crop_image_index]
        image_path = Path(image_data.get("path", ""))

        if not image_path.exists():
            self.add_debug("❌ Rotate failed: Image file not found")
            return

        try:
            # Load image
            img = Image.open(image_path)

            # Rotate: ROTATE_270 = 90° clockwise, ROTATE_90 = 90° counter-clockwise
            if clockwise:
                img_rotated = img.transpose(Image.Transpose.ROTATE_270)
                rotation_delta = 90
                direction = "↻"
            else:
                img_rotated = img.transpose(Image.Transpose.ROTATE_90)
                rotation_delta = -90
                direction = "↺"

            # Save rotated image back to same file
            format_to_use = img.format if img.format in ['JPEG', 'PNG', 'GIF', 'WEBP', 'BMP'] else 'JPEG'
            img_rotated.save(image_path, format=format_to_use, quality=90)

            # Update file size in pending_images
            new_size_kb = image_path.stat().st_size // 1024
            self.pending_images[self.crop_image_index]["size_kb"] = new_size_kb

            # Update URLs with cache-busting timestamp
            import time
            cache_buster = f"?t={int(time.time() * 1000)}"
            base_url = image_data["url"].split("?")[0]  # Remove old query params
            new_url = f"{base_url}{cache_buster}"

            # Update BOTH preview URL and thumbnail URL in pending_images
            self.crop_preview_url = new_url
            self.pending_images[self.crop_image_index]["url"] = new_url

            # Track cumulative rotation
            self.crop_rotation = (self.crop_rotation + rotation_delta) % 360

            # Reset crop box (dimensions may have changed)
            self.crop_box_x = 0.0
            self.crop_box_y = 0.0
            self.crop_box_width = 100.0
            self.crop_box_height = 100.0

            self.add_debug(f"🔄 Image rotated {direction} 90°")

        except Exception as e:
            self.add_debug(f"❌ Rotate failed: {e}")

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
        from .lib.vision_utils import crop_and_resize_image, save_image_to_file, get_image_url
        from pathlib import Path

        if self.crop_image_index < 0 or self.crop_image_index >= len(self.pending_images):
            self.add_debug("❌ Crop failed: Invalid image index")
            self.cancel_crop()
            return

        image_data = self.pending_images[self.crop_image_index]

        # Read original bytes from file
        try:
            image_path = Path(image_data["path"])
            with open(image_path, 'rb') as f:
                original_bytes = f.read()
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

            # Save cropped image as new file (keeps original, adds cropped version)
            # Uses session_id for persistent session-based storage
            new_path = save_image_to_file(cropped_bytes, self.session_id, image_data["name"])
            new_url = get_image_url(new_path)

            # Delete old file (optional: keep for undo functionality)
            try:
                image_path.unlink()
            except OSError:
                pass  # Ignore if file doesn't exist

            # Update pending_images with new file
            self.pending_images[self.crop_image_index] = {
                "name": image_data["name"],
                "path": str(new_path),
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

        # Add separator after browser/device detection (marks end of startup)
        from aifred.lib.logging_utils import console_separator
        console_separator()  # File log
        self.debug_messages.append("────────────────────")  # UI

    # ============================================================
    # AUDIO UPLOAD HANDLER (STT)
    # ============================================================

    async def handle_audio_upload(self, files: List[rx.UploadFile]):
        """Handle audio file uploads and transcribe with Whisper STT"""
        # Lazy load Whisper model if not already loaded
        whisper_model = get_whisper_model()
        if whisper_model is None:
            self.add_debug("🎤 Loading Whisper model...")
            whisper_model = initialize_whisper_model(self.whisper_model_key)
            if whisper_model is None:
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

            user_text, stt_time = transcribe_audio(tmp_path, whisper_model, self.ui_language)

            if user_text:
                # Set transcribed text as user input
                self.current_user_input = user_text
                # German number format: 0,2s instead of 0.2s
                from .lib.formatting import format_number
                self.add_debug(f"✅ Transcription complete ({format_number(stt_time, 1)}s)")

                # Show Transcription Workflow
                if self.show_transcription:
                    # Mode: Edit text → Send manually
                    self.add_debug("✏️ Text in input field → Ready for editing")
                    # Separator after STT complete (user will edit + send manually)
                    self.add_debug(CONSOLE_SEPARATOR)
                    console_separator()  # Log-File
                else:
                    # Mode: Direct to AI
                    self.add_debug("🚀 Sending text directly to AI...")
                    # Separator after STT, before send_message starts
                    self.add_debug(CONSOLE_SEPARATOR)
                    console_separator()  # Log-File
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

    async def _generate_tts_for_response(self, ai_response: str, autoplay: bool = True, agent: str = "aifred"):
        """Generate TTS audio for AI response and store path for playback

        Args:
            ai_response: The AI response text to convert to speech
            autoplay: If True, set autoplay flag (respects user setting). If False, never autoplay.
            agent: Agent name for per-agent voice settings (aifred, sokrates, salomo)

        Note: This is a simple async function, NOT a generator. State updates happen directly.
        """
        try:
            from .lib.audio_processing import clean_text_for_tts, generate_tts, set_tts_agent

            # Set agent name for audio filename prefixing
            set_tts_agent(agent)

            # Clean text: Remove <think> tags, emojis, markdown, URLs, timing info
            clean_text = clean_text_for_tts(ai_response)

            if not clean_text or len(clean_text.strip()) < 5:
                self.add_debug("🔇 TTS: Text too short after cleanup")
                return

            self.add_debug(f"🔊 TTS: Generating audio ({len(clean_text)} chars)...")

            # Determine voice, pitch, and speed based on agent settings (generic for all engines)
            voice_choice = self.tts_voice
            pitch_value = float(self.tts_pitch) if self.tts_pitch else 1.0
            speed_value = 1.0  # Default speed

            # Use per-agent settings if configured (works with all TTS engines)
            if agent in self.tts_agent_voices:
                agent_settings = self.tts_agent_voices[agent]
                agent_voice = agent_settings.get("voice", "")
                agent_pitch = agent_settings.get("pitch", "")
                agent_speed = agent_settings.get("speed", "")

                if agent_voice:
                    voice_choice = agent_voice
                    self.add_debug(f"🎭 Using {agent}'s voice: {voice_choice}")
                if agent_pitch:
                    try:
                        pitch_value = float(agent_pitch)
                    except ValueError:
                        pass
                if agent_speed:
                    try:
                        # Parse speed like "1.1x" -> 1.1
                        speed_value = float(agent_speed.replace("x", ""))
                    except ValueError:
                        pass

            # Generate TTS audio (returns URL path like "/tts_audio/audio_123.mp3")
            # Per-agent speed is applied at generation time (different from browser playback rate)
            # Pitch adjustment is applied via ffmpeg post-processing
            tts_language = self._last_detected_language or self.ui_language
            audio_url = await generate_tts(
                text=clean_text,
                voice_choice=voice_choice,
                speed_choice=speed_value,
                tts_engine=self.tts_engine,
                pitch=pitch_value,
                language=tts_language
            )

            if audio_url:
                # Verify file exists on disk (convert URL to filesystem path)
                # URL: /_upload/tts_audio/audio_123.mp3 -> data/tts_audio/audio_123.mp3
                from .lib.config import DATA_DIR
                filename = audio_url.split("/")[-1]
                file_path = DATA_DIR / "tts_audio" / filename

                if os.path.exists(file_path):
                    # Set browser playback rate from agent speed setting
                    self.tts_playback_rate = f"{speed_value}x"
                    self.add_debug(f"🔊 TTS: Playback rate set to {speed_value}x")
                    # Store audio URL for playback (use temporary URL for autoplay)
                    self.tts_audio_path = audio_url
                    # Increment counter to trigger frontend playback via rx.use_effect
                    self.tts_trigger_counter += 1
                    file_size_kb = os.path.getsize(file_path) / 1024
                    self.add_debug(f"✅ TTS: Audio generated ({file_size_kb:.1f} KB) → {audio_url}")
                    self.add_debug(f"🔊 TTS: Trigger counter incremented to {self.tts_trigger_counter}")

                    # Save to session directory for permanent storage (replay button)
                    from .lib.audio_processing import save_audio_to_session
                    session_audio_url = save_audio_to_session([audio_url], self.session_id)
                    if session_audio_url:
                        log_message(f"🔊 TTS: Saved to session → {session_audio_url}")

                        # Update last assistant message with session audio URL (for replay button)
                        if self.chat_history:
                            for i in range(len(self.chat_history) - 1, -1, -1):
                                if self.chat_history[i].get("role") == "assistant":
                                    if "metadata" not in self.chat_history[i]:
                                        self.chat_history[i]["metadata"] = {}
                                    self.chat_history[i]["metadata"]["audio_urls"] = [session_audio_url]
                                    self.chat_history[i]["has_audio"] = True
                                    self.chat_history[i]["audio_urls_json"] = json.dumps([session_audio_url])
                                    log_message("🔊 TTS: Added audio URL to message metadata")
                                    break
                            # Force Reflex to recognize the change
                            self.chat_history = list(self.chat_history)
                            self._save_current_session()
                    else:
                        log_message("⚠️ TTS: Failed to save audio to session")

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

    async def _queue_tts_for_agent(self, content: str, agent: str) -> None:
        """Generate TTS and add to queue for sequential playback.

        This is called by add_agent_panel() when TTS is enabled.
        The audio is generated and added to tts_audio_queue.
        Frontend plays queue items sequentially.

        Args:
            content: The text content to convert to speech (will be cleaned)
            agent: Agent name for per-agent voice settings (aifred, sokrates, salomo)
        """
        from .lib.audio_processing import clean_text_for_tts, generate_tts, set_tts_agent
        from .lib.config import DATA_DIR
        import os

        try:
            # Clean text: Remove <think> tags, emojis, markdown, URLs, timing info
            clean_text = clean_text_for_tts(content)

            if not clean_text or len(clean_text.strip()) < 5:
                self.add_debug(f"🔇 TTS Queue: Text too short for {agent}")
                return

            self.add_debug(f"🔊 TTS Queue: Generating audio for {agent} ({len(clean_text)} chars)...")

            # Determine voice, pitch, and speed based on agent settings
            voice_choice = self.tts_voice
            pitch_value = float(self.tts_pitch) if self.tts_pitch else 1.0
            speed_value = 1.0

            # Use per-agent settings if configured
            if agent in self.tts_agent_voices:
                agent_settings = self.tts_agent_voices[agent]
                agent_voice = agent_settings.get("voice", "")
                agent_pitch = agent_settings.get("pitch", "")
                agent_speed = agent_settings.get("speed", "")

                if agent_voice:
                    voice_choice = agent_voice
                if agent_pitch:
                    try:
                        pitch_value = float(agent_pitch)
                    except ValueError:
                        pass
                if agent_speed:
                    try:
                        speed_value = float(agent_speed.replace("x", ""))
                    except ValueError:
                        pass

            # Set agent name for audio filename prefixing
            set_tts_agent(agent)

            # Generate TTS audio
            tts_language = self._last_detected_language or self.ui_language
            audio_url = await generate_tts(
                text=clean_text,
                voice_choice=voice_choice,
                speed_choice=speed_value,
                tts_engine=self.tts_engine,
                pitch=pitch_value,
                language=tts_language
            )

            if audio_url:
                # Verify file exists
                filename = audio_url.split("/")[-1]
                file_path = DATA_DIR / "tts_audio" / filename

                if os.path.exists(file_path):
                    # Add to queue (use temporary URL for autoplay)
                    self.tts_audio_queue = self.tts_audio_queue + [audio_url]
                    self.tts_queue_version += 1
                    # NOTE: Do NOT add to _pending_audio_urls here!
                    # _pending_audio_urls is for Streaming-TTS only, where URLs are collected
                    # during streaming and then passed to add_agent_panel().
                    # For Queue-TTS, we save directly to the agent's message below.
                    # Also set tts_audio_path so HTML5 player shows current audio
                    self.tts_audio_path = audio_url
                    # Set browser playback rate from agent speed setting
                    self.tts_playback_rate = f"{speed_value}x"
                    file_size_kb = os.path.getsize(file_path) / 1024
                    self.add_debug(f"✅ TTS Queue: Added {agent} audio ({file_size_kb:.1f} KB), queue size: {len(self.tts_audio_queue)}")

                    # Save to session directory for permanent storage (replay button)
                    from .lib.audio_processing import save_audio_to_session
                    session_audio_url = save_audio_to_session([audio_url], self.session_id)
                    if session_audio_url:
                        log_message(f"🔊 TTS Queue: Saved to session → {session_audio_url}")

                        # Update THIS agent's message with session audio URL (for replay button)
                        # IMPORTANT: Find message by agent name, not "last assistant-message"!
                        # Multi-Agent runs TTS async, so other agents may have added messages already.
                        if self.chat_history:
                            for i in range(len(self.chat_history) - 1, -1, -1):
                                msg = self.chat_history[i]
                                if msg.get("role") == "assistant" and msg.get("agent") == agent:
                                    if "metadata" not in msg:
                                        msg["metadata"] = {}
                                    msg["metadata"]["audio_urls"] = [session_audio_url]
                                    msg["metadata"]["playback_rate"] = f"{speed_value}x"
                                    msg["has_audio"] = True
                                    msg["audio_urls_json"] = json.dumps([session_audio_url])
                                    log_message(f"🔊 TTS Queue: Added audio URL + playback_rate to {agent}'s message")
                                    break
                            # Force Reflex to recognize the change
                            self.chat_history = list(self.chat_history)
                            self._save_current_session()
                    else:
                        log_message(f"⚠️ TTS Queue: Failed to save audio to session for {agent}")
                else:
                    self.add_debug(f"⚠️ TTS Queue: Audio file not found at {file_path}")
            else:
                self.add_debug(f"⚠️ TTS Queue: Generation failed for {agent}")

        except Exception as e:
            self.add_debug(f"❌ TTS Queue Error ({agent}): {e}")
            log_message(f"❌ TTS queue generation error for {agent}: {e}")

    def clear_tts_queue(self) -> None:
        """Clear the TTS audio queue (called when starting new message)."""
        if self.tts_audio_queue:
            self.tts_audio_queue = []
            self.tts_queue_version += 1
            self.add_debug("🔊 TTS Queue: Cleared")

    # ============================================================
    # STREAMING TTS - Sentence-by-Sentence Generation
    # ============================================================

    def stream_text_to_ui(self, chunk: str) -> None:
        """Zentrale Funktion für ALLE gestreamten Text-Ausgaben.

        Schreibt Text in den UI-Buffer und leitet ihn an den TTS-Satz-Detektor weiter.
        Wird von allen Streaming-Stellen aufgerufen (state.py + multi_agent.py).

        Args:
            chunk: Text chunk from LLM streaming
        """
        self.current_ai_response += chunk

        if self.enable_tts and self.tts_autoplay and self.tts_streaming_enabled:
            self._process_streaming_tts_chunk(chunk)

    def _init_streaming_tts(self, agent: str = "aifred"):
        """Initialize streaming TTS state for a new response.

        Call this at the start of send_message() when streaming TTS is enabled.
        For DashScope: Opens a WebSocket connection for realtime token-feeding.
        For other engines: Initializes sentence buffer for parallel sentence TTS.

        Args:
            agent: Agent name for per-agent voice settings
        """
        log_message(f"🔊 TTS Init: Starting streaming TTS for agent={agent}")
        log_message(f"🔊 TTS Init: enable_tts={self.enable_tts}, tts_streaming_enabled={self.tts_streaming_enabled}, engine={self.tts_engine}")
        self._tts_sentence_buffer = ""
        self._tts_short_carry = ""
        self._tts_in_think_block = False
        self._tts_streaming_active = True
        self._tts_streaming_agent = agent
        self._tts_next_seq = 0
        self._tts_push_seq = 0
        self._tts_order_buffer = {}

        # DashScope: Use sentence-level streaming (same as XTTS/Edge/Piper).
        # Better intonation per sentence, no chunk gaps.
        #
        # To re-enable realtime WebSocket streaming (word-level chunks, ~3s batches):
        # Uncomment the block below. This feeds tokens directly into the DashScope
        # WebSocket for immediate audio output during LLM inference, but produces
        # small audible gaps between chunks and slightly worse prosody.
        #
        # if self.tts_engine == "dashscope":
        #     self._init_dashscope_realtime(agent)
        # else:
        #     _dashscope_rt_instances.pop(self.session_id, None)
        _dashscope_rt_instances.pop(self.session_id, None)

        log_message("🔊 TTS Init: State initialized, ready for chunks")

    def _init_dashscope_realtime(self, agent: str) -> None:
        """Open DashScope WebSocket connection for realtime TTS streaming."""
        from .lib.audio_processing import DashScopeRealtimeTTS

        # Resolve voice for this agent
        voice_choice = self.tts_voice
        speed_value = 1.0
        tts_agent_voices = dict(self.tts_agent_voices)
        if agent in tts_agent_voices:
            agent_settings = tts_agent_voices[agent]
            if agent_settings.get("voice"):
                voice_choice = agent_settings["voice"]
            agent_speed = agent_settings.get("speed", "")
            if agent_speed:
                try:
                    speed_value = float(agent_speed.replace("x", ""))
                except ValueError:
                    pass

        # Strip ★ prefix (same as generate_tts() does centrally)
        if voice_choice.startswith("★ "):
            voice_choice = voice_choice[2:]

        log_message(f"🔊 DashScope RT Init: Opening WebSocket for voice={voice_choice}, agent={agent}")
        self.add_debug(f"🎤 TTS: DashScope Realtime WebSocket → {voice_choice}")
        rt_tts = DashScopeRealtimeTTS(
            voice_choice=voice_choice,
            session_id=self.session_id,
            agent=agent,
            speed=speed_value,
        )
        _dashscope_rt_instances[self.session_id] = rt_tts
        # Connect in background thread - doesn't block event loop
        # This allows the yield to happen immediately so the browser can set up SSE
        # TTFT is ~3s, so WebSocket connect (~0.6s) will be done before first token
        import threading
        threading.Thread(target=rt_tts.connect, daemon=True).start()

    async def _finalize_streaming_tts(self) -> list[str]:
        """Wait for TTS tasks to complete and return combined audio URL.

        DashScope Realtime: Calls finish() on WebSocket, waits for final audio.
        Other engines: Waits for parallel create_task() TTS tasks to complete.

        Returns:
            List with single combined audio URL, or empty list if no audio
        """
        if not self._tts_streaming_active:
            log_message("🔊 TTS Finalize: Not active, skipping")
            return []

        # DashScope Realtime: Finish WebSocket and get combined WAV
        if self.session_id in _dashscope_rt_instances:
            return await self._finalize_dashscope_realtime()

        # --- Other engines: Sentence-based parallel TTS ---

        # Merge carried-over short sentence with remaining buffer
        final_text = ""
        if self._tts_short_carry:
            final_text = self._tts_short_carry
            self._tts_short_carry = ""
        if self._tts_sentence_buffer and self._tts_sentence_buffer.strip():
            final_text = (final_text + " " + self._tts_sentence_buffer).strip() if final_text else self._tts_sentence_buffer
        self._tts_sentence_buffer = ""

        # Send remaining text to TTS (even if short - finalize sends everything)
        if final_text and final_text.strip():
            agent = getattr(self, '_tts_streaming_agent', 'aifred')
            seq = self._tts_next_seq
            self._tts_next_seq = seq + 1
            request_id = f"tts_{uuid.uuid4().hex[:8]}"
            self._pending_tts_requests = self._pending_tts_requests + [request_id]
            log_message(f"🔊 TTS Finalize: Adding remaining text seq={seq} ({len(final_text)} chars): {repr(final_text[:50])}")
            asyncio.create_task(self._tts_generate_sentence_async(
                final_text, agent, request_id, self.session_id, seq
            ))

        # Wait for all pending TTS tasks to complete
        log_message(f"🔊 TTS Finalize: Waiting for {len(self._pending_tts_requests)} pending tasks...")
        max_wait = 60  # Max 60 seconds - TTS can be slow for long sentences
        wait_interval = 0.2  # Check every 200ms
        waited = 0
        while self._pending_tts_requests and waited < max_wait:
            await asyncio.sleep(wait_interval)
            waited += wait_interval
            if waited % 2.0 < wait_interval:  # Log every 2 seconds
                log_message(f"🔊 TTS Finalize: Still waiting... pending={len(self._pending_tts_requests)}, completed={len(self._completed_tts_urls)}, waited={waited:.1f}s")

        if self._pending_tts_requests:
            log_message(f"🔊 TTS Finalize: ⚠️ Timeout! {len(self._pending_tts_requests)} tasks still pending after {max_wait}s")
        else:
            log_message(f"🔊 TTS Finalize: ✅ All {len(self._completed_tts_urls)} tasks completed in {waited:.1f}s")

        # Collect completed URLs
        completed_urls = list(self._completed_tts_urls.values())
        log_message(f"🔊 TTS Finalize: {len(completed_urls)} audio chunks collected")

        # Save audio to session directory (permanent storage)
        combined_url: str | None = None
        if completed_urls:
            if len(completed_urls) > 1:
                self.add_debug(f"🔗 TTS: Combining {len(completed_urls)} audio chunks...")
                self.add_debug(CONSOLE_SEPARATOR)
            from .lib.audio_processing import save_audio_to_session
            combined_url = save_audio_to_session(completed_urls, self.session_id)
            if combined_url:
                log_message(f"🔊 TTS Finalize: Saved to session → {combined_url}")

        # Reset streaming state
        self._tts_sentence_buffer = ""
        self._tts_in_think_block = False
        self._tts_streaming_active = False
        self._pending_tts_requests = []
        self._completed_tts_urls = {}
        self._pending_audio_urls = []
        log_message("🔊 TTS Finalize: State reset complete")

        return [combined_url] if combined_url else []

    async def _finalize_dashscope_realtime(self) -> list[str]:
        """Finalize DashScope WebSocket streaming and return combined WAV URL.

        Audio batches (sentence-aligned) are pushed to the browser during synthesis
        via _flush_push_buffer(). This method waits for the final audio, saves the
        combined WAV to the session for re-play, and cleans up.
        """
        from .lib.audio_processing import save_audio_to_session

        rt_tts = _dashscope_rt_instances.pop(self.session_id, None)
        if not rt_tts:
            log_message("🔊 DashScope RT Finalize: No active WebSocket for this session")
            return []

        log_message("🔊 DashScope RT Finalize: Finishing WebSocket stream...")
        self.add_debug("🎤 TTS: Waiting for remaining audio...")

        # finish() flushes remaining text, signals end, waits for remaining audio, saves WAV
        # Audio batches (sentence-aligned) are already pushed to browser during synthesis
        combined_url = await rt_tts.finish()

        # Save combined WAV to session directory (permanent storage for re-play)
        session_url: str | None = None
        if combined_url:
            session_url = save_audio_to_session([combined_url], self.session_id)
            if session_url:
                log_message(f"🔊 DashScope RT Finalize: Saved to session → {session_url}")

        self.add_debug(f"🎤 TTS: Streaming done ({rt_tts._push_count} chunks)")

        # Cleanup WebSocket
        rt_tts.close()

        # Reset streaming state
        self._tts_sentence_buffer = ""
        self._tts_in_think_block = False
        self._tts_streaming_active = False
        self._pending_tts_requests = []
        self._completed_tts_urls = {}
        self._pending_audio_urls = []
        log_message("🔊 DashScope RT Finalize: State reset complete")

        return [session_url] if session_url else []

    def _process_streaming_tts_chunk(self, chunk: str) -> None:
        """Process a streaming chunk for TTS.

        This is called for each content chunk during LLM streaming.

        DashScope: Feeds tokens directly into WebSocket (natural ordering).
        Other engines: Extracts sentences and generates TTS in parallel via create_task().

        Args:
            chunk: Text chunk from LLM streaming
        """
        if not self._tts_streaming_active or not self.enable_tts or not self.tts_streaming_enabled:
            return

        from .lib.audio_processing import (
            extract_complete_sentences,
            strip_think_content_streaming,
        )

        # Add chunk to buffer (used for think-block detection in all modes)
        self._tts_sentence_buffer += chunk
        log_message(f"🔊 TTS Chunk: +{len(chunk)} chars, buffer now {len(self._tts_sentence_buffer)} chars")

        # Check for <think> blocks - don't process content inside them
        if "<think>" in self._tts_sentence_buffer.lower():
            self._tts_in_think_block = True
            log_message("🔊 TTS Chunk: Entered <think> block")
        if "</think>" in self._tts_sentence_buffer.lower():
            self._tts_in_think_block = False
            log_message("🔊 TTS Chunk: Exited </think> block")
            self._tts_sentence_buffer = strip_think_content_streaming(self._tts_sentence_buffer)
            log_message(f"🔊 TTS Chunk: After strip, buffer now {len(self._tts_sentence_buffer)} chars")

        # Don't process content while inside think block
        if self._tts_in_think_block:
            log_message("🔊 TTS Chunk: Inside think block, waiting...")
            return

        # DashScope Realtime: Feed raw tokens into WebSocket buffer
        # Cleaning happens inside DashScopeRealtimeTTS on the accumulated buffer
        # (clean_text_for_tts needs complete text, not individual tokens)
        rt_tts = _dashscope_rt_instances.get(self.session_id)
        if rt_tts is not None:
            rt_tts.append_text(chunk)
            return

        # Try to extract complete sentences
        sentences, remaining = extract_complete_sentences(self._tts_sentence_buffer)
        self._tts_sentence_buffer = remaining

        if sentences:
            log_message(f"🔊 TTS Chunk: Extracted {len(sentences)} sentence(s), remaining buffer: {len(remaining)} chars")
            for i, s in enumerate(sentences):
                log_message(f"🔊 TTS Chunk: Sentence {i+1}: {repr(s)}")

        # Prepend any carried-over short sentence to the first extracted sentence
        if self._tts_short_carry and sentences:
            sentences[0] = self._tts_short_carry + " " + sentences[0]
            self._tts_short_carry = ""

        # XTTS hallucinates on very short text (< 3 words).
        # Carry short sentences over to be merged with the next batch.
        min_tts_words = 3

        # Send each complete sentence to TTS IMMEDIATELY via create_task
        agent = getattr(self, '_tts_streaming_agent', 'aifred')
        for sentence in sentences:
            # Skip empty/whitespace-only content
            if not sentence.strip():
                continue

            # Carry over short sentences to avoid XTTS hallucination
            if len(sentence.split()) < min_tts_words:
                self._tts_short_carry = sentence
                log_message(f"🔊 TTS Chunk: Carrying short sentence ({len(sentence.split())} words): {repr(sentence)}")
                continue

            # Assign sequence number for ordered queue push
            seq = self._tts_next_seq
            self._tts_next_seq = seq + 1
            log_message(f"🔊 TTS Chunk: Starting TTS task seq={seq} (agent={agent}): {repr(sentence)}")
            # Track pending request
            request_id = f"tts_{uuid.uuid4().hex[:8]}"
            self._pending_tts_requests = self._pending_tts_requests + [request_id]
            log_message(f"🔊 TTS Chunk: Created request {request_id}, pending={len(self._pending_tts_requests)}")
            # Start TTS generation IMMEDIATELY in parallel - no waiting!
            # Pass session_id for API-based queue push (create_task can't use Reflex state)
            session_id = self.session_id
            asyncio.create_task(self._tts_generate_sentence_async(sentence, agent, request_id, session_id, seq))

    async def _tts_generate_sentence_async(self, sentence: str, agent: str, request_id: str, session_id: str, seq: int) -> None:
        """Generate TTS for a single sentence - runs in parallel via create_task.

        This is a plain async function called via asyncio.create_task() from
        _process_streaming_tts_chunk(). It runs truly in parallel with streaming,
        without waiting for event handler completion.

        Since create_task runs outside Reflex's event system, we can't use
        `async with self:` to push state. Instead, we push to a global API queue
        that the frontend polls via HTTP.

        Sentences are generated in parallel but pushed to the queue in sequence
        order (by seq number). If a later sentence finishes first, it waits in
        _tts_order_buffer until all earlier sentences have been pushed.

        Args:
            sentence: Clean sentence text to synthesize
            agent: Agent name for per-agent voice settings and filename prefix
            request_id: Unique ID for tracking (removed from pending on completion)
            session_id: Session ID for API-based queue push
            seq: Sequence number for ordered queue push
        """
        from .lib.audio_processing import clean_text_for_tts, generate_tts
        from .lib.config import DATA_DIR
        import os

        try:
            # Light cleanup - remove markdown, emojis, but keep the text mostly intact
            clean_text = clean_text_for_tts(sentence)

            if not clean_text or not clean_text.strip():
                # Empty sentence: mark as done and drain buffer
                self._pending_tts_requests = [r for r in self._pending_tts_requests if r != request_id]
                self._tts_order_buffer = {**self._tts_order_buffer, seq: None}
                self._drain_tts_order_buffer(session_id)
                return

            # Read voice settings (snapshot for this task)
            voice_choice = self.tts_voice
            pitch_value = float(self.tts_pitch) if self.tts_pitch else 1.0
            speed_value = 1.0
            tts_engine = self.tts_engine
            tts_agent_voices = dict(self.tts_agent_voices)  # Copy to avoid issues

            if agent in tts_agent_voices:
                agent_settings = tts_agent_voices[agent]
                agent_voice = agent_settings.get("voice", "")
                agent_pitch = agent_settings.get("pitch", "")
                agent_speed = agent_settings.get("speed", "")

                if agent_voice:
                    voice_choice = agent_voice
                if agent_pitch:
                    try:
                        pitch_value = float(agent_pitch)
                    except ValueError:
                        pass
                if agent_speed:
                    try:
                        speed_value = float(agent_speed.replace("x", ""))
                    except ValueError:
                        pass

            # Generate TTS audio (this is the slow part - runs in parallel)
            tts_language = self._last_detected_language or self.ui_language
            log_message(f"🔊 TTS Generate: Calling generate_tts() seq={seq} for agent={agent}: {repr(clean_text)}")
            log_message(f"🔊 TTS Generate: voice={voice_choice}, speed={speed_value}, pitch={pitch_value}, engine={tts_engine}, lang={tts_language}")

            audio_url = await generate_tts(
                text=clean_text,
                voice_choice=voice_choice,
                speed_choice=speed_value,
                tts_engine=tts_engine,
                pitch=pitch_value,
                agent=agent,  # Pass agent for correct filename prefix
                language=tts_language
            )

            if audio_url:
                filename = audio_url.split("/")[-1]
                file_path = DATA_DIR / "tts_audio" / filename
                log_message(f"🔊 TTS Generate: Got audio_url={audio_url}, filename={filename}")

                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    log_message(f"🔊 TTS Generate: File exists, size={file_size} bytes")

                    playback_rate = f"{speed_value}x"

                    # Buffer result for ordered push
                    self._tts_order_buffer = {**self._tts_order_buffer, seq: (audio_url, playback_rate, request_id)}
                    self._drain_tts_order_buffer(session_id)

                    log_message(f"🔊 TTS Generate: pending_requests={len(self._pending_tts_requests)}")
                else:
                    log_message(f"🔊 TTS Generate: ⚠️ File does not exist: {file_path}")
                    self._pending_tts_requests = [r for r in self._pending_tts_requests if r != request_id]
                    self._tts_order_buffer = {**self._tts_order_buffer, seq: None}
                    self._drain_tts_order_buffer(session_id)
            else:
                log_message("🔊 TTS Generate: ⚠️ No audio_url returned from generate_tts()")
                self._pending_tts_requests = [r for r in self._pending_tts_requests if r != request_id]
                self._tts_order_buffer = {**self._tts_order_buffer, seq: None}
                self._drain_tts_order_buffer(session_id)

        except Exception as e:
            log_message(f"❌ TTS Stream Error: {e}")
            import traceback
            log_message(f"❌ TTS Stream Traceback: {traceback.format_exc()}")
            # Remove request from pending on error and mark seq as done
            self._pending_tts_requests = [r for r in self._pending_tts_requests if r != request_id]
            self._tts_order_buffer = {**self._tts_order_buffer, seq: None}
            self._drain_tts_order_buffer(session_id)

    def _drain_tts_order_buffer(self, session_id: str) -> None:
        """Push completed TTS results to the queue in sequence order.

        Called after each sentence completes (success, error, or empty).
        Drains all consecutive entries starting from _tts_push_seq.
        Skips entries marked as None (empty/failed sentences).
        """
        from .lib.api import tts_queue_push

        while self._tts_push_seq in self._tts_order_buffer:
            entry = self._tts_order_buffer[self._tts_push_seq]

            if entry is not None:
                audio_url, playback_rate, request_id = entry
                tts_queue_push(session_id, audio_url, playback_rate)
                log_message(f"🔊 TTS Order: ✅ Pushed seq={self._tts_push_seq} to queue")
                # Track completion
                self._completed_tts_urls = {**self._completed_tts_urls, request_id: audio_url}
                self._pending_tts_requests = [r for r in self._pending_tts_requests if r != request_id]
            else:
                log_message(f"🔊 TTS Order: Skipping seq={self._tts_push_seq} (empty/failed)")

            # Remove from buffer and advance
            new_buffer = dict(self._tts_order_buffer)
            del new_buffer[self._tts_push_seq]
            self._tts_order_buffer = new_buffer
            self._tts_push_seq = self._tts_push_seq + 1

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
                self.aifred_model = saved_settings.get("model", self.aifred_model)
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
        self._save_settings()

    async def restart_backend(self):
        """Restart current LLM backend service and reload model list"""
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
                from .lib.process_utils import restart_service
                restart_service("ollama", check=True)
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
            elif self.backend_type == "llamacpp":
                # llama-swap: restart via systemctl --user (user service)
                import os as _os
                import subprocess as _sp
                from pathlib import Path as _Path

                _user_service = _Path.home() / ".config/systemd/user/llama-swap.service"
                _cmd_prefix = ["systemctl", "--user"] if _user_service.exists() else ["systemctl"]
                _env = _os.environ.copy()
                _uid = _os.getuid()
                _env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{_uid}")
                _env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{_uid}/bus")

                result = _sp.run(
                    _cmd_prefix + ["restart", "llama-swap"],
                    env=_env,
                    capture_output=True,
                )

                if result.returncode == 0:
                    self.add_debug("✅ llama-swap service restarted (autoscan running...)")
                else:
                    err = result.stderr.decode(errors='replace').strip()
                    self.add_debug(f"⚠️ llama-swap restart failed: {err or 'unknown error'}")
                yield

                # Wait for llama-swap to be ready (ExecStartPre/autoscan may take a few seconds)
                self.add_debug("⏳ Waiting for llama-swap to be ready...")
                yield

                max_retries = 20  # up to 10s — autoscan ExecStartPre can take time
                llamacpp_ready = False
                for attempt in range(max_retries):
                    try:
                        response = httpx.get(f"{self.backend_url}/v1/models", timeout=2.0)
                        if response.status_code == 200:
                            elapsed = (attempt + 1) * 0.5
                            self.add_debug(f"✅ llama-swap ready after {elapsed:.1f}s")
                            llamacpp_ready = True
                            break
                    except httpx.RequestError:
                        pass
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5)
                        yield

                if not llamacpp_ready:
                    self.add_debug("⚠️ llama-swap might not be ready yet (timeout after 10s)")
                yield

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
                            json={"name": self.aifred_model},
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

        except Exception as e:
            self.add_debug(f"❌ {backend_name} restart failed: {e}")
        finally:
            self.backend_switching = False
            yield  # Re-enable buttons

    async def restart_ollama(self):
        """Legacy method - calls restart_backend()"""
        await self.restart_backend()

    def set_aifred_rope_factor(self, value: str):
        """Set RoPE scaling factor for AIfred-LLM"""
        # Convert UI string to float
        factor = float(value.replace("x", ""))
        self.aifred_rope_factor = factor
        self.add_debug(f"🎚️ AIfred RoPE Factor: {value}")

        # Save to VRAM cache (per-model setting)
        if self.aifred_model_id:
            from .lib.model_vram_cache import set_rope_factor_for_model, get_ollama_calibrated_max_context, get_rope_factor_for_model, get_llamacpp_calibration
            from .lib.formatting import format_number
            set_rope_factor_for_model(self.aifred_model_id, factor)

            # Helper for context limit display (merge GB and ctx into one bracket)
            def format_model_with_ctx(model_display: str, model_id: str) -> str:
                if not model_id:
                    return model_display
                # Backend-aware calibration lookup
                if self.backend_type == "llamacpp":
                    ctx = get_llamacpp_calibration(model_id)
                else:
                    ctx = get_ollama_calibrated_max_context(model_id, get_rope_factor_for_model(model_id))
                if ctx:
                    if model_display.endswith(")"):
                        return model_display[:-1] + f", {format_number(ctx)} ctx)"
                    return f"{model_display} ({format_number(ctx)} ctx)"
                else:
                    if model_display.endswith(")"):
                        return model_display[:-1] + ", ctx not calibrated)"
                    return f"{model_display} (ctx not calibrated)"

            # Re-display all agent models with updated context limits
            self.add_debug(f"   AIfred: {format_model_with_ctx(self.aifred_model, self.aifred_model_id)}")
            if self.multi_agent_mode != "standard":
                if self.sokrates_model_id:
                    self.add_debug(f"   Sokrates: {format_model_with_ctx(self.sokrates_model, self.sokrates_model_id)}")
                if self.salomo_model_id:
                    self.add_debug(f"   Salomo: {format_model_with_ctx(self.salomo_model, self.salomo_model_id)}")

            # Update cached min context limit
            context_limits = []
            for model_id in [self.aifred_model_id, self.sokrates_model_id, self.salomo_model_id]:
                if model_id:
                    if self.backend_type == "llamacpp":
                        ctx = get_llamacpp_calibration(model_id)
                    else:
                        ctx = get_ollama_calibrated_max_context(model_id, get_rope_factor_for_model(model_id))
                    if ctx:
                        context_limits.append(ctx)
            self._min_agent_context_limit = min(context_limits) if context_limits else 0

            # Show history utilization and warn if compression will trigger
            if self.chat_history and self._min_agent_context_limit > 0:
                from .lib.context_manager import estimate_tokens_from_history
                from .lib.config import HISTORY_COMPRESSION_TRIGGER
                estimated_tokens = estimate_tokens_from_history(self.chat_history)
                utilization = (estimated_tokens / self._min_agent_context_limit) * 100
                self.add_debug(f"   └─ History: {format_number(estimated_tokens)} / {format_number(self._min_agent_context_limit)} tok ({int(utilization)}%)")

                # Warn if compression will trigger on next message
                if utilization >= HISTORY_COMPRESSION_TRIGGER * 100:
                    self.add_debug(f"⚠️ History compression will trigger on next message (>{int(HISTORY_COMPRESSION_TRIGGER * 100)}%)")

            # Warn if no calibration exists for this mode
            if value >= 2.0:
                # Check if extended calibration exists
                extended_ctx = get_ollama_calibrated_max_context(self.aifred_model_id, rope_factor=2.0)
                if extended_ctx is None:
                    self.add_debug("⚠️ No RoPE 2x calibration found - please calibrate first!")
            else:
                # Check if native calibration exists
                native_ctx = get_ollama_calibrated_max_context(self.aifred_model_id, rope_factor=1.0)
                if native_ctx is None:
                    self.add_debug("⚠️ No native calibration found - please calibrate first!")

    def set_automatik_rope_factor(self, value: str):
        """Set RoPE scaling factor for Automatik-LLM"""
        factor = float(value.replace("x", ""))
        self.automatik_rope_factor = factor
        effective_auto = self._effective_automatik_id
        if effective_auto:
            from .lib.model_vram_cache import set_rope_factor_for_model
            set_rope_factor_for_model(effective_auto, factor)

    def set_sokrates_rope_factor(self, value: str):
        """Set RoPE scaling factor for Sokrates-LLM"""
        factor = float(value.replace("x", ""))
        self.sokrates_rope_factor = factor
        if self.sokrates_model_id:
            from .lib.model_vram_cache import set_rope_factor_for_model
            set_rope_factor_for_model(self.sokrates_model_id, factor)

    def set_salomo_rope_factor(self, value: str):
        """Set RoPE scaling factor for Salomo-LLM"""
        factor = float(value.replace("x", ""))
        self.salomo_rope_factor = factor
        if self.salomo_model_id:
            from .lib.model_vram_cache import set_rope_factor_for_model
            set_rope_factor_for_model(self.salomo_model_id, factor)

    def set_vision_rope_factor(self, value: str):
        """Set RoPE scaling factor for Vision-LLM"""
        factor = float(value.replace("x", ""))
        self.vision_rope_factor = factor
        if self.vision_model_id:
            from .lib.model_vram_cache import set_rope_factor_for_model
            set_rope_factor_for_model(self.vision_model_id, factor)

    def toggle_aifred_personality(self):
        """Toggle AIfred Butler personality style on/off"""
        self.aifred_personality = not self.aifred_personality
        status = "ON" if self.aifred_personality else "OFF"
        self.add_debug(f"🎩 AIfred personality: {status}")
        self._save_personality_settings()
        # Sync to prompt_loader
        from .lib.prompt_loader import set_personality_enabled
        set_personality_enabled("aifred", self.aifred_personality)

    def toggle_sokrates_personality(self):
        """Toggle Sokrates philosophical personality style on/off"""
        self.sokrates_personality = not self.sokrates_personality
        status = "ON" if self.sokrates_personality else "OFF"
        self.add_debug(f"🏛️ Sokrates personality: {status}")
        self._save_personality_settings()
        # Sync to prompt_loader
        from .lib.prompt_loader import set_personality_enabled
        set_personality_enabled("sokrates", self.sokrates_personality)

    def toggle_salomo_personality(self):
        """Toggle Salomo judge personality style on/off"""
        self.salomo_personality = not self.salomo_personality
        status = "ON" if self.salomo_personality else "OFF"
        self.add_debug(f"👑 Salomo personality: {status}")
        self._save_personality_settings()
        # Sync to prompt_loader
        from .lib.prompt_loader import set_personality_enabled
        set_personality_enabled("salomo", self.salomo_personality)

    def _save_personality_settings(self):
        """Save personality toggle states to settings.json"""
        from .lib.settings import load_settings, save_settings
        settings = load_settings() or {}
        settings["aifred_personality"] = self.aifred_personality
        settings["sokrates_personality"] = self.sokrates_personality
        settings["salomo_personality"] = self.salomo_personality
        save_settings(settings)

    def toggle_aifred_reasoning(self):
        """Toggle AIfred chain-of-thought reasoning on/off"""
        self.aifred_reasoning = not self.aifred_reasoning
        status = "ON" if self.aifred_reasoning else "OFF"
        self.add_debug(f"💭 AIfred reasoning: {status}")
        self._save_reasoning_settings()
        from .lib.prompt_loader import set_reasoning_enabled
        set_reasoning_enabled("aifred", self.aifred_reasoning)

    def toggle_sokrates_reasoning(self):
        """Toggle Sokrates chain-of-thought reasoning on/off"""
        self.sokrates_reasoning = not self.sokrates_reasoning
        status = "ON" if self.sokrates_reasoning else "OFF"
        self.add_debug(f"💭 Sokrates reasoning: {status}")
        self._save_reasoning_settings()
        from .lib.prompt_loader import set_reasoning_enabled
        set_reasoning_enabled("sokrates", self.sokrates_reasoning)

    def toggle_salomo_reasoning(self):
        """Toggle Salomo chain-of-thought reasoning on/off"""
        self.salomo_reasoning = not self.salomo_reasoning
        status = "ON" if self.salomo_reasoning else "OFF"
        self.add_debug(f"💭 Salomo reasoning: {status}")
        self._save_reasoning_settings()
        from .lib.prompt_loader import set_reasoning_enabled
        set_reasoning_enabled("salomo", self.salomo_reasoning)

    def toggle_aifred_speed_mode(self):
        """Toggle AIfred between speed variant (aggressive split, 32K ctx) and context variant."""
        self.aifred_speed_mode = not self.aifred_speed_mode
        base_id = self._resolve_model_id(self.aifred_model)
        self.aifred_model_id = f"{base_id}-speed" if self.aifred_speed_mode else base_id
        self.add_debug(f"🔀 AIfred mode: {self._speed_mode_debug_str(self.aifred_speed_mode, base_id, self.aifred_max_context)}")
        self._save_settings()

    def toggle_sokrates_speed_mode(self):
        """Toggle Sokrates between speed variant and context variant."""
        self.sokrates_speed_mode = not self.sokrates_speed_mode
        base_id = self._resolve_model_id(self.sokrates_model) or self._resolve_model_id(self.aifred_model)
        self.sokrates_model_id = f"{base_id}-speed" if self.sokrates_speed_mode else base_id
        self.add_debug(f"🔀 Sokrates mode: {self._speed_mode_debug_str(self.sokrates_speed_mode, base_id, self.sokrates_max_context)}")
        self._save_settings()

    def toggle_salomo_speed_mode(self):
        """Toggle Salomo between speed variant and context variant."""
        self.salomo_speed_mode = not self.salomo_speed_mode
        base_id = self._resolve_model_id(self.salomo_model) or self._resolve_model_id(self.aifred_model)
        self.salomo_model_id = f"{base_id}-speed" if self.salomo_speed_mode else base_id
        self.add_debug(f"🔀 Salomo mode: {self._speed_mode_debug_str(self.salomo_speed_mode, base_id, self.salomo_max_context)}")
        self._save_settings()

    def _speed_mode_debug_str(self, speed_on: bool, base_model_id: str, max_ctx: int) -> str:
        """Build debug string for speed mode toggle showing tensor-split and context."""
        from .lib.model_vram_cache import get_llamacpp_speed_split
        from .lib.formatting import format_number
        from .lib.config import MIN_USEFUL_CONTEXT_TOKENS
        if speed_on:
            split = get_llamacpp_speed_split(base_model_id)
            split_str = f" ({split}:1 tensor-split)" if split > 0 else ""
            ctx = format_number(MIN_USEFUL_CONTEXT_TOKENS)
            return f"⚡ speed — {ctx} tok{split_str}"
        else:
            ctx = format_number(max_ctx) if max_ctx else "n/a"
            return f"📖 context — {ctx} tok"

    def _save_reasoning_settings(self):
        """Save reasoning toggle states to settings.json"""
        from .lib.settings import load_settings, save_settings
        settings = load_settings() or {}
        settings["aifred_reasoning"] = self.aifred_reasoning
        settings["sokrates_reasoning"] = self.sokrates_reasoning
        settings["salomo_reasoning"] = self.salomo_reasoning
        save_settings(settings)

    def toggle_aifred_thinking(self):
        """Toggle AIfred model thinking (enable_thinking to backend) on/off"""
        self.aifred_thinking = not self.aifred_thinking
        status = "ON" if self.aifred_thinking else "OFF"
        self.add_debug(f"🧠 AIfred thinking: {status}")
        self._save_thinking_settings()
        from .lib.prompt_loader import set_thinking_enabled
        set_thinking_enabled("aifred", self.aifred_thinking)

    def toggle_sokrates_thinking(self):
        """Toggle Sokrates model thinking on/off"""
        self.sokrates_thinking = not self.sokrates_thinking
        status = "ON" if self.sokrates_thinking else "OFF"
        self.add_debug(f"🧠 Sokrates thinking: {status}")
        self._save_thinking_settings()
        from .lib.prompt_loader import set_thinking_enabled
        set_thinking_enabled("sokrates", self.sokrates_thinking)

    def toggle_salomo_thinking(self):
        """Toggle Salomo model thinking on/off"""
        self.salomo_thinking = not self.salomo_thinking
        status = "ON" if self.salomo_thinking else "OFF"
        self.add_debug(f"🧠 Salomo thinking: {status}")
        self._save_thinking_settings()
        from .lib.prompt_loader import set_thinking_enabled
        set_thinking_enabled("salomo", self.salomo_thinking)

    def _save_thinking_settings(self):
        """Save thinking toggle states to settings.json"""
        from .lib.settings import load_settings, save_settings
        settings = load_settings() or {}
        settings["aifred_thinking"] = self.aifred_thinking
        settings["sokrates_thinking"] = self.sokrates_thinking
        settings["salomo_thinking"] = self.salomo_thinking
        save_settings(settings)

    def set_aifred_sampling(self, param: str, value: str):
        """Set AIfred sampling parameter from UI input"""
        self._set_agent_sampling("aifred", param, value)

    def set_sokrates_sampling(self, param: str, value: str):
        """Set Sokrates sampling parameter from UI input"""
        self._set_agent_sampling("sokrates", param, value)

    def set_salomo_sampling(self, param: str, value: str):
        """Set Salomo sampling parameter from UI input"""
        self._set_agent_sampling("salomo", param, value)

    def _set_agent_sampling(self, agent: str, param: str, value: str):
        """Set a sampling parameter for an agent and save to settings"""
        try:
            if param == "top_k":
                int_val = int(float(value))
                setattr(self, f"{agent}_top_k", max(0, min(200, int_val)))
            elif param == "top_p":
                float_val = float(value)
                setattr(self, f"{agent}_top_p", max(0.0, min(1.0, float_val)))
            elif param == "min_p":
                float_val = float(value)
                setattr(self, f"{agent}_min_p", max(0.0, min(1.0, float_val)))
            elif param == "repeat_penalty":
                float_val = float(value)
                setattr(self, f"{agent}_repeat_penalty", max(1.0, min(2.0, float_val)))
            final_val = getattr(self, f"{agent}_{param}")
            self.add_debug(f"🎲 {agent.capitalize()} {param}={final_val}")
            self._save_settings()
        except (ValueError, TypeError):
            pass

    def reset_aifred_sampling(self):
        """Reset AIfred sampling to model defaults"""
        self._reset_agent_sampling("aifred")

    def reset_sokrates_sampling(self):
        """Reset Sokrates sampling to model defaults"""
        self._reset_agent_sampling("sokrates")

    def reset_salomo_sampling(self):
        """Reset Salomo sampling to model defaults"""
        self._reset_agent_sampling("salomo")

    def _reset_agent_sampling(self, agent: str, include_temperature: bool = True):
        """Reset sampling parameters for an agent to model/backend defaults.

        Args:
            agent: "aifred", "sokrates", or "salomo"
            include_temperature: If True, reset temperature too (model change / reset button).
                If False, keep current temperature (app restart — temperature is persisted).
        """
        defaults = {
            "temperature": LLAMASERVER_DEFAULT_TEMPERATURE,
            "top_k": DEFAULT_TOP_K,
            "top_p": DEFAULT_TOP_P,
            "min_p": DEFAULT_MIN_P,
            "repeat_penalty": DEFAULT_REPEAT_PENALTY,
        }

        if self.backend_type == "llamacpp":
            # Try to get model-specific values from llama-swap YAML
            # Sokrates/Salomo with empty model_id inherit from AIfred
            model_id = getattr(self, f"{agent}_model_id", "") or self.aifred_model_id
            if model_id:
                from .lib.llamacpp_calibration import parse_llamaswap_config, parse_sampling_from_cmd
                from .lib.config import LLAMASWAP_CONFIG_PATH
                config = parse_llamaswap_config(LLAMASWAP_CONFIG_PATH)
                if model_id in config:
                    yaml_sampling = parse_sampling_from_cmd(config[model_id]["full_cmd"])
                    defaults = {
                        "temperature": yaml_sampling.get("temperature", LLAMASERVER_DEFAULT_TEMPERATURE),
                        "top_k": yaml_sampling.get("top_k", LLAMASERVER_DEFAULT_TOP_K),
                        "top_p": yaml_sampling.get("top_p", LLAMASERVER_DEFAULT_TOP_P),
                        "min_p": yaml_sampling.get("min_p", LLAMASERVER_DEFAULT_MIN_P),
                        "repeat_penalty": yaml_sampling.get("repeat_penalty", LLAMASERVER_DEFAULT_REPEAT_PENALTY),
                    }

        if include_temperature:
            if agent == "aifred":
                self.temperature = defaults["temperature"]
            else:
                setattr(self, f"{agent}_temperature", defaults["temperature"])
        setattr(self, f"{agent}_top_k", int(defaults["top_k"]))
        setattr(self, f"{agent}_top_p", defaults["top_p"])
        setattr(self, f"{agent}_min_p", defaults["min_p"])
        setattr(self, f"{agent}_repeat_penalty", defaults["repeat_penalty"])

        # Debug log
        temp_info = f"temp={defaults['temperature']}, " if include_temperature else ""
        self.add_debug(
            f"🎲 {agent.capitalize()} sampling reset: "
            f"{temp_info}top_k={int(defaults['top_k'])}, "
            f"top_p={defaults['top_p']}, min_p={defaults['min_p']}, "
            f"rep={defaults['repeat_penalty']}"
        )

        # Increment key to force UI re-mount of input fields
        self.sampling_reset_key += 1

    async def calibrate_context(self):
        """
        Calibrate maximum context window for current model.

        Supported backends:
        - Ollama: Binary search via /api/ps (size == size_vram check)
        - llama.cpp: Binary search via direct llama-server start/health check
        """
        if self.backend_type not in ("ollama", "llamacpp"):
            self.add_debug("⚠️ Calibration only for Ollama and llama.cpp")
            return

        if not self.aifred_model_id:
            self.add_debug("⚠️ No model selected")
            return

        if self.is_calibrating:
            self.add_debug("⚠️ Calibration already in progress")
            return

        self.is_calibrating = True
        self.add_debug(f"🔧 Starting calibration for {self.aifred_model_id}...")
        yield

        # Dispatch to backend-specific calibration
        if self.backend_type == "llamacpp":
            async for _ in self._calibrate_llamacpp():
                yield
            return

        try:
            from .backends import BackendFactory
            from .lib.formatting import format_number
            from .lib.model_vram_cache import add_ollama_calibration
            from .lib.gpu_utils import get_gpu_model_name

            backend = BackendFactory.create(
                self.backend_type,
                base_url=self.backend_url
            )

            # Get native context limit first
            native_ctx, _ = await backend.get_model_context_limit(self.aifred_model_id)
            calibration_results = {}

            # === STEP 1: Calibrate Native (1.0x) ===
            self.add_debug("📐 Calibrating Native (1.0x)...")
            yield

            calibrated_ctx = None
            is_hybrid_mode = False  # Track if 1.0x resulted in hybrid mode
            async for progress_msg in backend.calibrate_max_context_generator(
                self.aifred_model_id,
                rope_factor=1.0
            ):
                if progress_msg.startswith("__RESULT__:"):
                    # Parse result: __RESULT__:{ctx}:{mode} where mode is gpu/hybrid/error
                    parts = progress_msg.split(":")
                    calibrated_ctx = int(parts[1])
                    calibration_results[1.0] = calibrated_ctx
                    if len(parts) > 2 and parts[2] == "hybrid":
                        is_hybrid_mode = True
                else:
                    self.add_debug(f"📊 {progress_msg}")
                    yield

            # === STEP 2: Check calibration result ===
            # Determine if RoPE calibration makes sense
            skip_rope_calibration = False

            # Check for calibration failure (model doesn't fit)
            if not calibrated_ctx or calibrated_ctx == 0:
                self.add_debug(CONSOLE_SEPARATOR)
                self.add_debug("❌ Calibration failed - model doesn't fit in memory")
                self.add_debug("   → Skipping RoPE calibration")
                yield
                skip_rope_calibration = True
            elif calibrated_ctx < native_ctx:
                # Memory is the bottleneck (VRAM or RAM) - RoPE scaling won't help
                # This applies to BOTH GPU-only and Hybrid mode
                skip_rope_calibration = True
                self.add_debug(CONSOLE_SEPARATOR)
                if is_hybrid_mode:
                    self.add_debug(f"🔀 Hybrid mode: {format_number(calibrated_ctx)} < {format_number(native_ctx)} native")
                    self.add_debug("   → RAM is the limit - RoPE scaling won't increase context")
                else:
                    self.add_debug(f"⚡ VRAM-limited: {format_number(calibrated_ctx)} < {format_number(native_ctx)} native")
                    self.add_debug("   → VRAM is the limit - RoPE scaling won't increase context")
                self.add_debug(f"   → Auto-setting RoPE 1.5x and 2.0x to {format_number(calibrated_ctx)}")
                yield
            elif is_hybrid_mode:
                # Hybrid mode but native context fits - RoPE might give us more!
                self.add_debug(CONSOLE_SEPARATOR)
                self.add_debug(f"🔀 Hybrid mode: {format_number(calibrated_ctx)} (native fits)")
                self.add_debug("   → Testing if RoPE scaling can extend context further...")
                yield
                # Don't skip - let it calibrate RoPE 1.5x and 2.0x

            if skip_rope_calibration and calibrated_ctx:
                # Save same value for 1.5x and 2.0x (no separate calibration needed)
                # Only if we have a valid context (not on error)
                gpu_model = get_gpu_model_name() or "Unknown"
                for rope_factor in [1.5, 2.0]:
                    add_ollama_calibration(
                        model_name=self.aifred_model_id,
                        max_context_gpu_only=calibrated_ctx,
                        native_context=native_ctx,
                        gpu_model=gpu_model,
                        rope_factor=rope_factor,
                        is_hybrid=is_hybrid_mode
                    )
                    calibration_results[rope_factor] = calibrated_ctx

            elif not skip_rope_calibration:
                # === STEP 3: Calibrate RoPE 1.5x and 2.0x ===
                # Start from 1.0x result, then use previous RoPE result as new minimum
                from .lib.config import CALIBRATION_MIN_CONTEXT
                prev_ctx = calibration_results.get(1.0, CALIBRATION_MIN_CONTEXT)

                for rope_factor in [1.5, 2.0]:
                    self.add_debug(CONSOLE_SEPARATOR)
                    self.add_debug(f"📐 Calibrating RoPE {rope_factor}x...")
                    yield

                    rope_calibrated_ctx = None
                    async for progress_msg in backend.calibrate_max_context_generator(
                        self.aifred_model_id,
                        rope_factor=rope_factor,
                        min_context=prev_ctx,  # Start from previous result (1.0x or 1.5x)
                        force_hybrid=is_hybrid_mode  # Continue in hybrid mode if 1.0x was hybrid
                    ):
                        if progress_msg.startswith("__RESULT__:"):
                            # Parse result: __RESULT__:{ctx}:{mode}
                            parts = progress_msg.split(":")
                            rope_calibrated_ctx = int(parts[1])
                            calibration_results[rope_factor] = rope_calibrated_ctx
                            # Update prev_ctx for next iteration (2.0x uses 1.5x result)
                            prev_ctx = rope_calibrated_ctx
                        else:
                            self.add_debug(f"📊 {progress_msg}")
                            yield

            # Summary
            self.add_debug("═" * 20)
            mode_info = " (Hybrid)" if is_hybrid_mode else ""
            self.add_debug(f"✅ Calibration complete for {self.aifred_model_id}{mode_info}:")
            for factor, ctx in calibration_results.items():
                label = "Native" if factor == 1.0 else f"RoPE {factor}x"
                suffix = " (auto)" if skip_rope_calibration and factor > 1.0 else ""
                self.add_debug(f"   {label}: {format_number(ctx)} tok{suffix}")
            self.add_debug("   → Values will be used automatically based on RoPE setting")

            # Test thinking capability if calibration was successful (shared helper)
            if calibration_results.get(1.0, 0) > 0:
                async for _ in self._test_and_save_thinking(backend, self.aifred_model_id):
                    yield

            self.add_debug(CONSOLE_SEPARATOR)

        except Exception as e:
            self.add_debug(f"❌ Calibration failed: {e}")

        finally:
            self.is_calibrating = False
            yield

    async def _test_and_save_thinking(self, backend: Any, model_id: str) -> None:
        """
        Test thinking capability and save result to cache + state.

        Shared between Ollama and llama.cpp calibration flows.
        """
        self.add_debug("─" * 20)
        self.add_debug("🧠 Testing reasoning capability...")
        yield

        try:
            supports_thinking = await backend.test_thinking_capability(model_id)

            from .lib.model_vram_cache import set_thinking_support_for_model
            set_thinking_support_for_model(model_id, supports_thinking)

            # Update state for ALL agents using this model
            if self.aifred_model_id == model_id:
                self.aifred_supports_thinking = supports_thinking
            if self.sokrates_model_id == model_id:
                self.sokrates_supports_thinking = supports_thinking
            if self.salomo_model_id == model_id:
                self.salomo_supports_thinking = supports_thinking

            if supports_thinking:
                self.add_debug("✅ Reasoning mode: Supported (<think> tags)")
            else:
                self.add_debug("⚠️ Reasoning mode: Not supported")

        except Exception as e:
            self.add_debug(f"⚠️ Thinking test failed: {e}")

    async def _calibrate_llamacpp(self):
        """
        llama.cpp calibration via direct llama-server binary search.

        Workflow:
        1. Stop llama-swap service (free VRAM)
        2. Phase 1: GPU-only binary search (ngl=99)
        3. Phase 2: Speed variant calibration (multi-GPU tensor-split, if Phase 1 succeeds)
        4. Phase 3: Hybrid NGL+context search (if GPU-only < MIN_USEFUL_CONTEXT_TOKENS)
        4. Update llama-swap YAML with calibrated -c and -ngl values
        5. Restart llama-swap service
        6. Test thinking capability
        """
        import subprocess
        from .lib.formatting import format_number
        from .lib.llamacpp_calibration import (
            update_llamaswap_context,
            update_llamaswap_ngl,
            add_llamaswap_speed_variant,
        )
        from .lib.config import LLAMASWAP_CONFIG_PATH, MIN_USEFUL_CONTEXT_TOKENS

        llama_swap_stopped = False

        try:
            from .backends import BackendFactory

            backend = BackendFactory.create(
                self.backend_type,
                base_url=self.backend_url
            )

            # Step 1: Stop llama-swap to free VRAM
            # Detect service type by checking if user service file exists
            from pathlib import Path
            _user_service_path = Path.home() / ".config/systemd/user/llama-swap.service"
            _systemctl_cmd = ["systemctl", "--user"] if _user_service_path.exists() else ["systemctl"]

            # AIfred runs as a system service (User=mp) without D-Bus session env.
            # systemctl --user needs these to reach the user session manager.
            import os
            _systemctl_env = os.environ.copy()
            uid = os.getuid()
            _systemctl_env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
            _systemctl_env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")

            self.add_debug("🛑 Stopping llama-swap service...")
            yield
            try:
                subprocess.run(
                    [*_systemctl_cmd, "stop", "llama-swap"],
                    check=True, timeout=15, env=_systemctl_env
                )
                llama_swap_stopped = True
                self.add_debug("   llama-swap stopped via systemctl")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                self.add_debug(f"⚠️ Could not stop llama-swap: {e}")
                self.add_debug("   Continuing anyway (VRAM may be limited)")
            yield

            # Step 2: Run calibration (Phase 1: GPU-only, Phase 2: Hybrid if needed,
            #          Phase 3: Speed split for multi-GPU models)
            # Result format: __RESULT__:{ctx}:{ngl}:{mode}:{thinks|nothink}
            # Speed format:  __SPEED__:{N}  (N:1 tensor-split for speed variant, 0=none)
            calibrated_ctx = None
            calibrated_ngl = 99
            calibrated_mode = "gpu"
            thinking_tested = False
            speed_split_n = 0
            async for progress_msg in backend.calibrate_max_context_generator(
                self.aifred_model_id
            ):
                if progress_msg.startswith("__RESULT__:"):
                    parts = progress_msg.split(":")
                    calibrated_ctx = int(parts[1])
                    calibrated_ngl = int(parts[2]) if len(parts) > 2 else 99
                    calibrated_mode = parts[3] if len(parts) > 3 else "gpu"
                    if len(parts) > 4:
                        thinking_tested = True
                        supports_thinking = parts[4] == "thinks"
                elif progress_msg.startswith("__SPEED__:"):
                    speed_split_n = int(progress_msg.split(":")[1])
                else:
                    self.add_debug(f"📊 {progress_msg}")
                    yield

            # Step 3: Process result
            if not calibrated_ctx or calibrated_ctx == 0:
                self.add_debug(CONSOLE_SEPARATOR)
                self.add_debug("❌ Calibration failed")
                yield
                return

            self.add_debug(CONSOLE_SEPARATOR)
            mode_str = f" (hybrid, ngl={calibrated_ngl})" if calibrated_mode == "hybrid" else ""
            self.add_debug(f"✅ Calibrated: {format_number(calibrated_ctx)} tokens{mode_str}")

            # Step 4: Update llama-swap YAML (-c and optionally -ngl)
            self.add_debug("📝 Updating llama-swap config...")
            updated_ctx = update_llamaswap_context(
                LLAMASWAP_CONFIG_PATH,
                self.aifred_model_id,
                calibrated_ctx
            )
            if updated_ctx:
                self.add_debug(
                    f"   -c {format_number(calibrated_ctx)} written to "
                    f"{LLAMASWAP_CONFIG_PATH.name}"
                )
            else:
                self.add_debug("⚠️ Could not update -c in llama-swap config")

            # Always write ngl: gpu-mode uses 99, hybrid uses the calculated value.
            # Without this, a stale ngl (e.g. from a previous hybrid calibration) stays.
            updated_ngl = update_llamaswap_ngl(
                LLAMASWAP_CONFIG_PATH,
                self.aifred_model_id,
                calibrated_ngl
            )
            if updated_ngl:
                mode_label = "hybrid mode" if calibrated_mode == "hybrid" else "gpu mode"
                self.add_debug(f"   -ngl {calibrated_ngl} written ({mode_label})")
            else:
                self.add_debug("⚠️ Could not update -ngl in llama-swap config")

            # Write speed variant YAML entry (only for multi-GPU models with valid split)
            if speed_split_n > 0:
                added_speed = add_llamaswap_speed_variant(
                    LLAMASWAP_CONFIG_PATH,
                    self.aifred_model_id,
                    speed_split_n,
                    MIN_USEFUL_CONTEXT_TOKENS,
                )
                if added_speed:
                    self.add_debug(
                        f"   ⚡ Speed variant: {self.aifred_model_id}-speed "
                        f"(split {speed_split_n}:1, ctx {format_number(MIN_USEFUL_CONTEXT_TOKENS)})"
                    )
                    # Patch speed_split into the latest calibration entry (already saved)
                    from .lib.model_vram_cache import update_llamacpp_speed_split
                    update_llamacpp_speed_split(self.aifred_model_id, speed_split_n)
                    # Toggle immediately visible without restart
                    self.aifred_has_speed_variant = True
                else:
                    self.add_debug("⚠️ Could not write speed variant to llama-swap config")
            yield

            # Step 5: Restart llama-swap
            self.add_debug("🔄 Restarting llama-swap service...")
            try:
                subprocess.run(
                    [*_systemctl_cmd, "start", "llama-swap"],
                    check=True, timeout=15, env=_systemctl_env
                )
                llama_swap_stopped = False
                self.add_debug("   llama-swap started")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                self.add_debug("⚠️ Could not restart llama-swap")
            yield

            # Step 6: Save thinking result (tested during calibration)
            if thinking_tested:
                from .lib.model_vram_cache import set_thinking_support_for_model
                set_thinking_support_for_model(self.aifred_model_id, supports_thinking)
                self.aifred_supports_thinking = supports_thinking
                self.add_debug(
                    f"🧠 Reasoning: {'yes' if supports_thinking else 'no'} "
                    f"(tested during calibration)"
                )

            self.add_debug(CONSOLE_SEPARATOR)

        except Exception as e:
            self.add_debug(f"❌ Calibration failed: {e}")

        finally:
            # Always restart llama-swap if we stopped it
            if llama_swap_stopped:
                try:
                    subprocess.run(
                        [*_systemctl_cmd, "start", "llama-swap"],
                        timeout=15, env=_systemctl_env
                    )
                except Exception:
                    pass
            self.is_calibrating = False
            yield

    def restart_aifred(self):
        """Restart AIfred service via systemctl"""
        import threading

        try:
            self.add_debug("🔄 Restarting AIfred service...")

            # Schedule systemd restart in background thread
            # This allows us to return rx.call_script() BEFORE the service dies
            from .lib.process_utils import restart_service as do_restart_service

            def delayed_restart():
                import time
                time.sleep(0.5)  # Short delay to let browser script execute first
                do_restart_service("aifred-intelligence", check=False)

            thread = threading.Thread(target=delayed_restart, daemon=True)
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
                # Separator after clear operation
                self.add_debug(CONSOLE_SEPARATOR)
                console_separator()  # Log-File
                yield  # Update UI
            else:
                self.add_debug("✅ Vector DB is already empty")
                # Separator after clear operation
                self.add_debug(CONSOLE_SEPARATOR)
                console_separator()  # Log-File
                yield  # Update UI

        except Exception as e:
            self.add_debug(f"❌ Vector DB clear failed: {e}")
            # Separator after error
            self.add_debug(CONSOLE_SEPARATOR)
            console_separator()  # Log-File
            yield  # Update UI even on error


    async def set_aifred_model(self, model: str):
        """Set selected model and restart backend if needed"""
        from .lib.vision_utils import is_vision_model

        old_model = self.aifred_model
        self.aifred_model = model
        self.aifred_model_id = self._resolve_model_id(model)
        # Clear thinking mode warning when model changes
        self.thinking_mode_warning = ""
        self.add_debug(f"📝 AIfred-LLM: {model}")

        # Load all model parameters from cache (rope_factor, max_context, is_hybrid, supports_thinking)
        if self.backend_type == "ollama":
            from .lib.model_vram_cache import get_model_parameters
            params = get_model_parameters(self.aifred_model_id)
            self.aifred_rope_factor = params["rope_factor"]
            self.aifred_max_context = params["max_context"]
            self.aifred_is_hybrid = params["is_hybrid"]
            self.aifred_supports_thinking = params["supports_thinking"]
        elif self.backend_type == "llamacpp":
            from .lib.model_vram_cache import (
                get_llamacpp_calibration,
                get_thinking_support_for_model,
                get_llamacpp_speed_split,
            )
            self.aifred_rope_factor = 1.0
            self.aifred_max_context = get_llamacpp_calibration(self.aifred_model_id) or 0
            self.aifred_is_hybrid = False
            self.aifred_supports_thinking = get_thinking_support_for_model(self.aifred_model_id)
            self.aifred_has_speed_variant = get_llamacpp_speed_split(self.aifred_model_id) > 0
            if not self.aifred_has_speed_variant:
                self.aifred_speed_mode = False

        # Show calibration info for Ollama models
        self._show_model_calibration_info(self.aifred_model_id)

        # Check if switching to non-vision model with pending images
        if len(self.pending_images) > 0:
            if not await is_vision_model(self, self.aifred_model_id):
                self.image_upload_warning = "⚠️ Selected model doesn't support images. Images will be ignored when sending."
            else:
                self.image_upload_warning = ""  # Clear warning

        # Reset sampling params to model defaults for all affected agents
        self._reset_agent_sampling("aifred")
        if not self.sokrates_model_id:
            self._reset_agent_sampling("sokrates")
        if not self.salomo_model_id:
            self._reset_agent_sampling("salomo")

        # ALWAYS save settings first (fixes Ollama not saving model changes)
        self._save_settings()

        # Note: For Ollama, model unloading happens JUST BEFORE VRAM measurement
        # in calculate_practical_context() - not here. This ensures accurate VRAM
        # readings even if other processes use GPU memory between model selection
        # and actual inference.

        # vLLM/TabbyAPI: Force restart backend for model change
        if self.backend_type in ["vllm", "tabbyapi"] and old_model != model:
            # vLLM can only load ONE model - set Automatik-LLM to same as Main-LLM
            if self.backend_type == "vllm" and self.automatik_model != model:
                self.automatik_model = model

            # Reset YaRN to 1.0 on model change (new model needs recalibration)
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
                self.add_debug(f"📏 YaRN factor: {factor_float}x (~{estimated_context} tokens)")
        except ValueError:
            pass  # Ignore invalid input during typing

    async def apply_yarn_factor(self):
        """Apply YaRN factor and restart backend"""
        try:
            # Normalize comma to point for German locale
            factor_normalized = self.yarn_factor_input.replace(',', '.')
            factor_float = float(factor_normalized)
            if not (1.0 <= factor_float <= 8.0):
                self.add_debug(f"❌ YaRN factor must be between 1.0 and 8.0 (entered: {factor_float})")
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

    def set_aifred_temperature_input(self, value: str):
        """Set AIfred temperature from text input field"""
        try:
            self.temperature = max(0.0, min(2.0, float(value)))
            self.add_debug(f"🌡️ AIfred temperature={self.temperature}")
            self._save_settings()
        except (ValueError, TypeError):
            pass

    def set_sokrates_temperature_input(self, value: str):
        """Set Sokrates temperature from text input field"""
        try:
            self.sokrates_temperature = max(0.0, min(2.0, float(value)))
            self.add_debug(f"🌡️ Sokrates temperature={self.sokrates_temperature}")
            self._save_settings()
        except (ValueError, TypeError):
            pass

    def set_salomo_temperature_input(self, value: str):
        """Set Salomo temperature from text input field"""
        try:
            self.salomo_temperature = max(0.0, min(2.0, float(value)))
            self.add_debug(f"🌡️ Salomo temperature={self.salomo_temperature}")
            self._save_settings()
        except (ValueError, TypeError):
            pass

    def calculate_manual_context(self):
        """
        Calculate and display context limits.
        Called when user clicks "Calculate" button.
        Shows all LLM context values (manual or auto-calibrated from persistent cache).
        """
        from .lib.formatting import format_number
        from .lib.context_manager import estimate_tokens_from_history
        from .lib.model_vram_cache import get_ollama_calibration, get_rope_factor_for_model
        from .lib.config import HISTORY_COMPRESSION_TRIGGER

        # Collect effective limits for compression calculation
        effective_limits = []

        def format_model_with_ctx(model_display: str, ctx_value: int, mode: str) -> str:
            """Format model display with context info and mode indicator"""
            if ctx_value > 0:
                ctx_str = format_number(ctx_value)
                mode_str = mode
            else:
                # Not calibrated - show clear indication
                ctx_str = "n/a"
                mode_str = "nicht kalibriert" if mode == "auto" else mode
            if model_display.endswith(")"):
                return model_display[:-1] + f", {ctx_str} ctx, {mode_str})"
            return f"{model_display} ({ctx_str} ctx, {mode_str})"

        self.add_debug("📊 Context configuration:")

        # AIfred - get auto value from persistent cache if not manual
        if self.num_ctx_manual_aifred_enabled:
            aifred_ctx = self.num_ctx_manual_aifred
            mode = "manual"
        else:
            rope_factor = get_rope_factor_for_model(self.aifred_model_id)
            aifred_ctx = get_ollama_calibration(self.aifred_model_id, rope_factor) or 0
            mode = "auto"
        self.add_debug(f"   AIfred: {format_model_with_ctx(self.aifred_model, aifred_ctx, mode)}")
        if aifred_ctx > 0:
            effective_limits.append(aifred_ctx)

        # Sokrates - always show (needed for multi-agent context display)
        if self.sokrates_model_id:
            if self.num_ctx_manual_sokrates_enabled:
                sokrates_ctx = self.num_ctx_manual_sokrates
                mode = "manual"
            else:
                rope_factor = get_rope_factor_for_model(self.sokrates_model_id)
                sokrates_ctx = get_ollama_calibration(self.sokrates_model_id, rope_factor) or 0
                mode = "auto"
            self.add_debug(f"   Sokrates: {format_model_with_ctx(self.sokrates_model, sokrates_ctx, mode)}")
            if sokrates_ctx > 0:
                effective_limits.append(sokrates_ctx)

        # Salomo - always show (needed for multi-agent context display)
        if self.salomo_model_id:
            if self.num_ctx_manual_salomo_enabled:
                salomo_ctx = self.num_ctx_manual_salomo
                mode = "manual"
            else:
                rope_factor = get_rope_factor_for_model(self.salomo_model_id)
                salomo_ctx = get_ollama_calibration(self.salomo_model_id, rope_factor) or 0
                mode = "auto"
            self.add_debug(f"   Salomo: {format_model_with_ctx(self.salomo_model, salomo_ctx, mode)}")
            if salomo_ctx > 0:
                effective_limits.append(salomo_ctx)

        # Vision - always show if vision model is selected
        if self.vision_model_id:
            if self.vision_num_ctx_enabled:
                vision_ctx = self.vision_num_ctx
                mode = "manual"
            else:
                rope_factor = get_rope_factor_for_model(self.vision_model_id)
                vision_ctx = get_ollama_calibration(self.vision_model_id, rope_factor) or 0
                mode = "auto"
            self.add_debug(f"   Vision: {format_model_with_ctx(self.vision_model, vision_ctx, mode)}")
            # Vision context is NOT added to effective_limits - it's separate from chat context

        # Calculate effective limit (minimum of all active limits)
        effective_limit = min(effective_limits) if effective_limits else 0

        # Update cached min context limit
        self._min_agent_context_limit = effective_limit

        # Show history utilization and warn if compression will trigger
        if self.chat_history and effective_limit > 0:
            estimated_tokens = estimate_tokens_from_history(self.chat_history)
            utilization = (estimated_tokens / effective_limit) * 100
            self.add_debug(f"   └─ History: {format_number(estimated_tokens)} / {format_number(effective_limit)} tok ({int(utilization)}%)")

            # Warn if compression will trigger on next message
            if utilization >= HISTORY_COMPRESSION_TRIGGER * 100:
                self.add_debug(f"⚠️ History compression will trigger on next message (>{int(HISTORY_COMPRESSION_TRIGGER * 100)}%)")
        elif not self.chat_history:
            self.add_debug("   └─ History: empty")
        else:
            self.add_debug(f"   └─ Effective limit: {format_number(effective_limit)} tokens")


    def set_num_ctx_manual_aifred(self, value: str):
        """Set manual num_ctx value for AIfred (only used when aifred_enabled=True)"""
        from .lib.config import NUM_CTX_MANUAL_MAX
        from .lib.formatting import format_number
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
            self.num_ctx_manual_aifred = num_value
            self.add_debug(f"🔧 Manual Context (AIfred): {format_number(num_value)}")
            # IMPORTANT: Not saved in settings.json!
        except (ValueError, TypeError):
            self.add_debug(f"❌ Invalid Context value: {value}")

    def set_num_ctx_manual_sokrates(self, value: str):
        """Set manual num_ctx value for Sokrates (only used when mode=manual)"""
        from .lib.config import NUM_CTX_MANUAL_MAX
        from .lib.formatting import format_number
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
            self.add_debug(f"🔧 Manual Context (Sokrates): {format_number(num_value)}")
        except (ValueError, TypeError):
            self.add_debug(f"❌ Invalid Context value: {value}")

    def set_num_ctx_manual_salomo(self, value: str):
        """Set manual num_ctx value for Salomo (only used when mode=manual)"""
        from .lib.config import NUM_CTX_MANUAL_MAX
        from .lib.formatting import format_number
        try:
            clean_value = str(value).replace(".", "").replace(",", "").replace(" ", "").strip()
            if not clean_value:
                return
            num_value = int(clean_value)
            if num_value < 1:
                num_value = 1
            if num_value > NUM_CTX_MANUAL_MAX:
                num_value = NUM_CTX_MANUAL_MAX
            self.num_ctx_manual_salomo = num_value
            self.add_debug(f"🔧 Manual Context (Salomo): {format_number(num_value)}")
        except (ValueError, TypeError):
            self.add_debug(f"❌ Invalid Context value: {value}")

    def toggle_num_ctx_manual_aifred(self, enabled: bool):
        """Toggle manual context for AIfred"""
        self.num_ctx_manual_aifred_enabled = enabled
        status = "Manual" if enabled else "Auto"
        self.add_debug(f"🎩 AIfred Context: {status}")

    def toggle_num_ctx_manual_sokrates(self, enabled: bool):
        """Toggle manual context for Sokrates"""
        self.num_ctx_manual_sokrates_enabled = enabled
        status = "Manual" if enabled else "Auto"
        self.add_debug(f"🏛️ Sokrates Context: {status}")

    def toggle_num_ctx_manual_salomo(self, enabled: bool):
        """Toggle manual context for Salomo"""
        self.num_ctx_manual_salomo_enabled = enabled
        status = "Manual" if enabled else "Auto"
        self.add_debug(f"👑 Salomo Context: {status}")

    def toggle_vision_num_ctx(self, enabled: bool):
        """Toggle manual context for Vision-LLM (PERSISTENT)"""
        self.vision_num_ctx_enabled = enabled
        status = "Manual" if enabled else "Auto (calibrated)"
        self.add_debug(f"👁️ Vision Context: {status}")
        self._save_settings()

    def set_vision_num_ctx(self, value: str):
        """Set manual vision context value (PERSISTENT)"""
        from .lib.config import NUM_CTX_MANUAL_MAX
        from .lib.formatting import format_number
        try:
            num_value = int(value)
            if num_value < 1024:  # Minimum 1K for vision
                num_value = 1024
            if num_value > NUM_CTX_MANUAL_MAX:
                num_value = NUM_CTX_MANUAL_MAX
            self.vision_num_ctx = num_value
            self.add_debug(f"👁️ Manual Context (Vision): {format_number(num_value)}")
            self._save_settings()
        except (ValueError, TypeError):
            self.add_debug(f"❌ Invalid Vision Context value: {value}")

    def set_research_mode(self, mode: str):
        """Set research mode"""
        self.research_mode = mode
        self.add_debug(f"🔍 Research mode: {mode}")

    def set_research_mode_display(self, display_value: str):
        """Set research mode from UI display value"""
        from .lib import TranslationManager

        # Use translation manager to get the internal mode value
        self.research_mode_display = display_value
        self.research_mode = TranslationManager.get_research_mode_value(display_value, self.ui_language)
        self.add_debug(f"🔍 Research mode: {self.research_mode} (from: '{display_value}')")
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
            "critical_review": "Critical Review",
            "auto_consensus": "Auto-Consensus",
            "devils_advocate": "Devil's Advocate"
        }
        self.add_debug(f"🤖 Discussion mode: {mode_labels.get(mode, mode)}")

    def set_max_debate_rounds(self, value: list[float]):
        """Set maximum debate rounds (from slider)"""
        self.max_debate_rounds = int(value[0])
        self._save_settings()
        self.add_debug(f"🔄 Max debate rounds: {self.max_debate_rounds}")

    def increase_debate_rounds(self):
        """Increase max debate rounds by 1 (max 10)"""
        if self.max_debate_rounds < 10:
            self.max_debate_rounds += 1
            self._save_settings()
            self.add_debug(f"🔄 Max debate rounds: {self.max_debate_rounds}")

    def decrease_debate_rounds(self):
        """Decrease max debate rounds by 1 (min 1)"""
        if self.max_debate_rounds > 1:
            self.max_debate_rounds -= 1
            self._save_settings()
            self.add_debug(f"🔄 Max debate rounds: {self.max_debate_rounds}")

    def set_consensus_type(self, consensus_type: str | list[str]):
        """Set consensus type for auto_consensus mode ('majority' or 'unanimous')"""
        # Handle both str and list[str] from segmented_control
        if isinstance(consensus_type, list):
            consensus_type = consensus_type[0] if consensus_type else "majority"
        self.consensus_type = consensus_type
        self._save_settings()
        type_label = "2/3 majority" if consensus_type == "majority" else "3/3 unanimous"
        self.add_debug(f"🗳️ Consensus type: {type_label}")

    def toggle_consensus_type(self, checked: bool):
        """Toggle consensus type between majority (off) and unanimous (on)"""
        self.consensus_type = "unanimous" if checked else "majority"
        self._save_settings()
        type_label = "3/3 unanimous" if checked else "2/3 majority"
        self.add_debug(f"🗳️ Consensus type: {type_label}")

    def set_sokrates_model(self, model: str):
        """Set Sokrates LLM model for multi-agent debate"""
        from .lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"
        if model == t("sokrates_llm_same", lang=lang):
            model = ""
        self.sokrates_model = model
        self.sokrates_model_id = self._resolve_model_id(model)

        if not self.sokrates_model_id:
            # "(wie AIfred-LLM)" selected — clear speed variant
            self.sokrates_has_speed_variant = False
            self.sokrates_speed_mode = False

        # Load all model parameters from cache (rope_factor, max_context, is_hybrid, supports_thinking)
        if self.backend_id == "ollama" and self.sokrates_model_id:
            from .lib.model_vram_cache import get_model_parameters
            params = get_model_parameters(self.sokrates_model_id)
            self.sokrates_rope_factor = params["rope_factor"]
            self.sokrates_max_context = params["max_context"]
            self.sokrates_is_hybrid = params["is_hybrid"]
            self.sokrates_supports_thinking = params["supports_thinking"]
        elif self.backend_type == "llamacpp" and self.sokrates_model_id:
            from .lib.model_vram_cache import (
                get_llamacpp_calibration,
                get_thinking_support_for_model,
                get_llamacpp_speed_split,
            )
            self.sokrates_rope_factor = 1.0
            self.sokrates_max_context = get_llamacpp_calibration(self.sokrates_model_id) or 0
            self.sokrates_is_hybrid = False
            self.sokrates_supports_thinking = get_thinking_support_for_model(self.sokrates_model_id)
            self.sokrates_has_speed_variant = get_llamacpp_speed_split(self.sokrates_model_id) > 0
            if not self.sokrates_has_speed_variant:
                self.sokrates_speed_mode = False

        # Reset sampling params to model defaults
        self._reset_agent_sampling("sokrates")

        self._save_settings()
        if model:
            self.add_debug(f"🧠 Sokrates-LLM: {model}")
            self._show_model_calibration_info(self.sokrates_model_id)
        else:
            self.add_debug("🧠 Sokrates-LLM: (same as Main-LLM)")

    def set_salomo_model(self, model: str):
        """Set Salomo LLM model for multi-agent debate"""
        from .lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"
        if model == t("sokrates_llm_same", lang=lang):
            model = ""
        self.salomo_model = model
        self.salomo_model_id = self._resolve_model_id(model)

        if not self.salomo_model_id:
            # "(wie AIfred-LLM)" selected — clear speed variant
            self.salomo_has_speed_variant = False
            self.salomo_speed_mode = False

        # Load all model parameters from cache (rope_factor, max_context, is_hybrid, supports_thinking)
        if self.backend_id == "ollama" and self.salomo_model_id:
            from .lib.model_vram_cache import get_model_parameters
            params = get_model_parameters(self.salomo_model_id)
            self.salomo_rope_factor = params["rope_factor"]
            self.salomo_max_context = params["max_context"]
            self.salomo_is_hybrid = params["is_hybrid"]
            self.salomo_supports_thinking = params["supports_thinking"]
        elif self.backend_type == "llamacpp" and self.salomo_model_id:
            from .lib.model_vram_cache import (
                get_llamacpp_calibration,
                get_thinking_support_for_model,
                get_llamacpp_speed_split,
            )
            self.salomo_rope_factor = 1.0
            self.salomo_max_context = get_llamacpp_calibration(self.salomo_model_id) or 0
            self.salomo_is_hybrid = False
            self.salomo_supports_thinking = get_thinking_support_for_model(self.salomo_model_id)
            self.salomo_has_speed_variant = get_llamacpp_speed_split(self.salomo_model_id) > 0
            if not self.salomo_has_speed_variant:
                self.salomo_speed_mode = False

        # Reset sampling params to model defaults
        self._reset_agent_sampling("salomo")

        self._save_settings()
        if model:
            self.add_debug(f"👑 Salomo-LLM: {model}")
            self._show_model_calibration_info(self.salomo_model_id)
        else:
            self.add_debug("👑 Salomo-LLM: (same as Main-LLM)")

    def queue_user_interjection(self, text: str):
        """Queue user input during active debate"""
        if self.debate_in_progress and text.strip():
            self.debate_user_interjection = text.strip()
            self.add_debug(f"💬 User interjection queued: {text[:50]}...")

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
    # GENERIC STREAMING HELPER - REMOVED (toter Code)
    # Note: _stream_llm_with_ui was never used - all streaming uses
    # dedicated functions in conversation_handler.py and multi_agent.py
    # ============================================================

    async def set_automatik_model(self, model: str):
        """Set automatik model for decision and query optimization"""
        from .lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"
        if model == t("sokrates_llm_same", lang=lang):
            model = ""

        old_model = self.automatik_model
        self.automatik_model = model
        self.automatik_model_id = self._resolve_model_id(model)
        self._save_settings()

        if model:
            self.add_debug(f"⚡ Automatic-LLM: {model}")
            self._show_model_calibration_info(self.automatik_model_id)
        else:
            self.add_debug("⚡ Automatic-LLM: (same as Main-LLM)")

        # vLLM/TabbyAPI: Auto-restart backend for model change
        if self.backend_type in ["vllm", "tabbyapi"] and old_model != model:
            self.add_debug("🔄 Backend restart for Automatic model switch...")
            await self.initialize_backend()
            self.add_debug("✅ New Automatic model loaded")

        # Note: Models are loaded on-demand during first inference (saves VRAM)
        # Context limit will be queried on first use (fast ~30ms) and cached by httpx

    async def set_vision_model(self, model: str):
        """Set vision model for OCR/image analysis"""
        self.vision_model = model
        self.vision_model_id = self._resolve_model_id(model)
        self.add_debug(f"👁️ Vision-LLM: {model}")
        # Show calibration info for Ollama models
        self._show_model_calibration_info(self.vision_model_id)
        self._save_settings()

        # Note: Vision model will be loaded on-demand when image is uploaded
        # No preloading needed here to save VRAM

    # ===== NEW: ID-BASED MODEL HANDLERS FOR KEY-VALUE SYSTEM =====

    async def set_aifred_model_by_id(self, model_id: str):
        """Set selected model using pure ID (new key-value system)"""
        # Update ID
        self.aifred_model_id = model_id

        # Load per-model RoPE 2x toggle from cache
        if self.backend_id == "ollama":
            from .lib.model_vram_cache import get_rope_factor_for_model
            self.aifred_rope_factor = get_rope_factor_for_model(model_id)
        elif self.backend_type == "llamacpp":
            self.aifred_rope_factor = 1.0

        # Sync deprecated display variable
        display_label = self.available_models_dict.get(model_id, model_id)
        self.aifred_model = display_label

        # Call existing handler with display label (reuses all logic)
        await self.set_aifred_model(display_label)

    async def set_automatik_model_by_id(self, model_id: str):
        """Set automatik model using pure ID (new key-value system)"""
        # Update ID
        self.automatik_model_id = model_id

        # Load per-model RoPE factor from cache (skip if empty = same as AIfred)
        if model_id:
            if self.backend_id == "ollama":
                from .lib.model_vram_cache import get_rope_factor_for_model
                self.automatik_rope_factor = get_rope_factor_for_model(model_id)
            elif self.backend_type == "llamacpp":
                self.automatik_rope_factor = 1.0

        # Sync deprecated display variable
        display_label = self.available_models_dict.get(model_id, model_id)
        self.automatik_model = display_label

        # Call existing handler with display label (reuses all logic)
        await self.set_automatik_model(display_label)

    async def set_vision_model_by_id(self, model_id: str):
        """Set vision model using pure ID (new key-value system)"""
        # Update ID
        self.vision_model_id = model_id

        # Load per-model RoPE factor from cache
        if self.backend_id == "ollama":
            from .lib.model_vram_cache import get_rope_factor_for_model
            self.vision_rope_factor = get_rope_factor_for_model(model_id)
        elif self.backend_type == "llamacpp":
            self.vision_rope_factor = 1.0

        # Sync deprecated display variable
        display_label = self.available_models_dict.get(model_id, model_id)
        self.vision_model = display_label

        # Call existing handler with display label (reuses all logic)
        await self.set_vision_model(display_label)

    # ============================================================
    # USER NAME & GENDER SETTINGS
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

    def set_user_gender(self, gender: str | list[str]):
        """Set user gender for salutation (male/female)"""
        # Reflex segmented_control can return str or list[str]
        if isinstance(gender, list):
            gender = gender[0] if gender else "male"
        self.user_gender = gender
        from .lib.prompt_loader import set_user_gender
        set_user_gender(gender)
        self.add_debug(f"👤 Gender: {'♂ male' if gender == 'male' else '♀ female'}")
        self._save_settings()

    # ============================================================
    # TTS/STT SETTINGS
    # ============================================================

    def toggle_tts(self):
        """Toggle TTS on/off.

        When XTTS is selected:
        - TTS OFF: Stop XTTS container (free VRAM)
        - TTS ON: Start XTTS container with current CPU/GPU setting
        """
        self.enable_tts = not self.enable_tts
        self.add_debug(f"🔊 TTS: {'enabled' if self.enable_tts else 'disabled'}")

        # Handle Docker TTS container start/stop
        if self.tts_engine == "xtts":
            from .lib.process_utils import set_xtts_cpu_mode, stop_xtts_container

            if self.enable_tts:
                success, message = set_xtts_cpu_mode(self.xtts_force_cpu)
                if success:
                    self.add_debug("✅ XTTS container started")
                    self._refresh_xtts_voices()
                else:
                    self.add_debug(f"❌ {message}")
            else:
                success, message = stop_xtts_container()
                if success:
                    self.add_debug("✅ XTTS container stopped")
                else:
                    self.add_debug(f"❌ {message}")
        elif self.tts_engine == "moss":  # MOSS-TTS (batch)
            from .lib.process_utils import ensure_moss_ready, stop_moss_container

            if self.enable_tts:
                success, message, device = ensure_moss_ready(timeout=120)
                self.moss_tts_device = device if success else ""
                if success:
                    self.add_debug(f"✅ {message}")
                else:
                    self.add_debug(f"❌ {message}")
            else:
                success, message = stop_moss_container()
                self.moss_tts_device = ""
                if success:
                    self.add_debug("✅ MOSS-TTS container stopped")
                else:
                    self.add_debug(f"❌ {message}")

        self._save_settings()

    def set_tts_engine_or_off(self, selection: str):
        """Combined TTS on/off + engine selection from single dropdown.

        Receives translated label from dropdown, maps to internal key.
        "Off"/"Aus" disables TTS, any engine label enables TTS.
        """
        from .lib.i18n import tts_label_to_key
        key = tts_label_to_key(selection)
        if key == "off":
            if not self.enable_tts:
                return

            # Save per-engine settings before disabling
            self._save_agent_voices_for_engine(self.tts_engine)
            self._save_tts_toggles_for_engine(self.tts_engine)

            self.enable_tts = False
            self.add_debug("🔊 TTS: disabled")

            # Stop running Docker containers
            if self.tts_engine == "xtts":
                from .lib.process_utils import stop_xtts_container

                success, message = stop_xtts_container()
                if success:
                    self.add_debug("✅ XTTS container stopped")
                else:
                    self.add_debug(f"❌ {message}")
            elif self.tts_engine == "moss":
                from .lib.process_utils import stop_moss_container

                success, message = stop_moss_container()
                self.moss_tts_device = ""
                if success:
                    self.add_debug("✅ MOSS-TTS container stopped")
                else:
                    self.add_debug(f"❌ {message}")

            self._save_settings()
            return

        # Engine selected — no-op if already active with same engine
        if self.enable_tts and key == self.tts_engine:
            return

        was_enabled = self.enable_tts
        old_key = self.tts_engine

        # Save current per-engine settings BEFORE switching
        if was_enabled:
            self._save_agent_voices_for_engine(old_key)
            self._save_tts_toggles_for_engine(old_key)

        # Enable TTS + set engine key, update UI immediately
        self.enable_tts = True
        self.tts_engine = key
        self.add_debug(f"🔊 TTS Engine: {key}")
        yield

        # Stop OLD Docker TTS container to free VRAM
        if was_enabled:
            if old_key == "xtts":
                from .lib.process_utils import stop_xtts_container

                stop_xtts_container()
                self.add_debug("🔊 XTTS container stopped (engine switch)")
                yield
            elif old_key == "moss":
                from .lib.process_utils import stop_moss_container

                stop_moss_container()
                self.moss_tts_device = ""
                self.add_debug("🔊 MOSS-TTS container stopped (engine switch)")
                yield

        # Start NEW Docker TTS container
        if key == "xtts":
            from .lib.process_utils import set_xtts_cpu_mode

            success, msg = set_xtts_cpu_mode(self.xtts_force_cpu)
            if success:
                self.add_debug(f"✅ {msg}")
            else:
                self.add_debug(f"⚠️ {msg}")
            self._refresh_xtts_voices()
        elif key == "moss":
            self.add_debug("🔊 MOSS-TTS: Loading model...")
            yield
            from .lib.process_utils import ensure_moss_ready

            success, msg, device = ensure_moss_ready(timeout=120)
            self.moss_tts_device = device if success else ""
            if success:
                self.add_debug(f"✅ {msg}")
            else:
                self.add_debug(f"⚠️ {msg}")

        # Restore per-engine settings for new engine
        self._restore_agent_voices_for_engine(key)
        self._restore_tts_toggles_for_engine(key)

        # Restore user's saved voice preference for this engine
        self._switch_tts_voice_for_language(self.ui_language)

        self._save_settings()

    def set_tts_voice(self, voice: str):
        """Set TTS voice"""
        self.tts_voice = voice
        self.add_debug(f"🔊 TTS Voice: {voice}")
        self._save_settings()

    def toggle_xtts_gpu(self, use_gpu: bool):
        """Toggle XTTS GPU mode with immediate UI feedback."""
        import os
        from .lib.process_utils import set_xtts_cpu_mode
        from .lib.settings import SETTINGS_FILE

        force_cpu = not use_gpu
        self.xtts_force_cpu = force_cpu
        mode_str = "GPU (auto)" if use_gpu else "CPU (forced)"
        self.add_debug(f"🔊 XTTS: Wechsle zu {mode_str}...")
        self._save_settings()
        # Update mtime tracker so periodic poll doesn't re-trigger "Settings reloaded"
        try:
            self._last_settings_mtime = os.path.getmtime(SETTINGS_FILE)
        except OSError:
            pass
        yield

        success, message = set_xtts_cpu_mode(force_cpu)
        if success:
            self.add_debug(f"✅ {message}")
        else:
            self.add_debug(f"❌ {message}")

    def set_xtts_force_cpu(self, force_cpu: bool):
        """Set XTTS CPU mode and restart container.

        When force_cpu=True:
        - XTTS runs on CPU (slower, but saves GPU VRAM for LLM)
        - No VRAM reservation needed for context calculation

        When force_cpu=False:
        - XTTS auto-detects GPU/CPU based on available VRAM
        - VRAM reservation applied to context calculation
        """
        from .lib.process_utils import set_xtts_cpu_mode

        self.xtts_force_cpu = force_cpu
        mode_str = "CPU (forced)" if force_cpu else "GPU (auto)"
        self.add_debug(f"🔊 XTTS Mode: {mode_str} - restarting container...")

        # Restart XTTS container with new setting
        success, message = set_xtts_cpu_mode(force_cpu)

        if success:
            self.add_debug(f"✅ {message}")
        else:
            self.add_debug(f"❌ {message}")

        self._save_settings()

    async def unload_xtts_model(self):
        """Unload XTTS model from memory to free VRAM."""
        import httpx
        from .lib.config import XTTS_SERVICE_URL

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(f"{XTTS_SERVICE_URL}/unload")
                response.raise_for_status()
                data = response.json()

                if data.get("success"):
                    freed_device = data.get("freed_device", "unknown")
                    self.add_debug(f"✅ XTTS model unloaded from {freed_device}")
                    yield rx.toast.success(f"XTTS model unloaded from {freed_device}", duration=3000)
                else:
                    self.add_debug("⚠️ XTTS unload failed")
                    yield rx.toast.error("Failed to unload XTTS model", duration=3000)

        except Exception as e:
            self.add_debug(f"❌ XTTS unload error: {e}")
            yield rx.toast.error(f"Error: {e}", duration=3000)

    # Note: set_tts_speed removed - generation always at 1.0, tempo via browser playback rate

    def toggle_tts_autoplay(self):
        """Toggle TTS auto-play"""
        self.tts_autoplay = not self.tts_autoplay
        self.add_debug(f"🔊 TTS Auto-Play: {'enabled' if self.tts_autoplay else 'disabled'}")
        self._save_settings()

    def toggle_tts_streaming(self):
        """Toggle streaming TTS (sentence-by-sentence vs complete response)"""
        self.tts_streaming_enabled = not self.tts_streaming_enabled
        mode = "Streaming (realtime)" if self.tts_streaming_enabled else "Standard (after response)"
        self.add_debug(f"🔊 TTS Mode: {mode}")
        self._save_settings()

    def set_tts_playback_rate(self, rate: str):
        """Set TTS playback rate (browser-side only, TTS generation stays at 1.0)"""
        self.tts_playback_rate = rate
        self.add_debug(f"🔊 TTS Tempo: {rate}")
        self._save_settings()
        # Apply rate to current audio player via JavaScript
        rate_value = rate.replace("x", "")
        return rx.call_script(f"setTtsPlaybackRate({rate_value})")

    def set_tts_pitch(self, pitch: str):
        """Set TTS pitch adjustment (applied via ffmpeg post-processing)"""
        self.tts_pitch = pitch
        self.add_debug(f"🔊 TTS Pitch: {pitch}")
        self._save_settings()

    # ============================================================
    # PER-AGENT VOICE SETTINGS (for Multi-Agent mode with XTTS)
    # ============================================================

    def set_agent_voice(self, agent: str, voice: str):
        """Set voice for a specific agent (aifred, sokrates, salomo)"""
        if agent in self.tts_agent_voices:
            self.tts_agent_voices[agent]["voice"] = voice
            self.add_debug(f"🔊 {agent.capitalize()} Voice: {voice}")
            self._save_settings()

    def set_agent_speed(self, agent: str, speed: str):
        """Set playback speed for a specific agent"""
        if agent in self.tts_agent_voices:
            self.tts_agent_voices[agent]["speed"] = speed
            self.add_debug(f"🔊 {agent.capitalize()} Speed: {speed}")
            self._save_settings()

    def set_agent_pitch(self, agent: str, pitch: str):
        """Set pitch for a specific agent"""
        if agent in self.tts_agent_voices:
            self.tts_agent_voices[agent]["pitch"] = pitch
            self.add_debug(f"🔊 {agent.capitalize()} Pitch: {pitch}")
            self._save_settings()

    def toggle_agent_tts(self, agent: str):
        """Toggle TTS enabled for a specific agent"""
        if agent in self.tts_agent_voices:
            self.tts_agent_voices[agent]["enabled"] = not self.tts_agent_voices[agent]["enabled"]
            status = "enabled" if self.tts_agent_voices[agent]["enabled"] else "disabled"
            self.add_debug(f"🔊 {agent.capitalize()} TTS: {status}")
            self._save_settings()

    # Helper methods to create bound event handlers for UI
    def set_aifred_voice(self, voice: str):
        """Set AIfred's voice"""
        self.set_agent_voice("aifred", voice)

    def set_sokrates_voice(self, voice: str):
        """Set Sokrates' voice"""
        self.set_agent_voice("sokrates", voice)

    def set_salomo_voice(self, voice: str):
        """Set Salomo's voice"""
        self.set_agent_voice("salomo", voice)

    def set_aifred_speed(self, speed: str):
        """Set AIfred's playback speed"""
        self.set_agent_speed("aifred", speed)
        # Also update browser playback rate immediately (so currently playing audio changes speed)
        self.tts_playback_rate = speed

    def set_sokrates_speed(self, speed: str):
        """Set Sokrates' playback speed"""
        self.set_agent_speed("sokrates", speed)
        # Also update browser playback rate immediately (so currently playing audio changes speed)
        self.tts_playback_rate = speed

    def set_salomo_speed(self, speed: str):
        """Set Salomo's playback speed"""
        self.set_agent_speed("salomo", speed)
        # Also update browser playback rate immediately (so currently playing audio changes speed)
        self.tts_playback_rate = speed

    def set_aifred_pitch(self, pitch: str):
        """Set AIfred's pitch"""
        self.set_agent_pitch("aifred", pitch)

    def set_sokrates_pitch(self, pitch: str):
        """Set Sokrates' pitch"""
        self.set_agent_pitch("sokrates", pitch)

    def set_salomo_pitch(self, pitch: str):
        """Set Salomo's pitch"""
        self.set_agent_pitch("salomo", pitch)

    def toggle_aifred_tts(self):
        """Toggle AIfred's TTS"""
        self.toggle_agent_tts("aifred")

    def toggle_sokrates_tts(self):
        """Toggle Sokrates' TTS"""
        self.toggle_agent_tts("sokrates")

    def toggle_salomo_tts(self):
        """Toggle Salomo's TTS"""
        self.toggle_agent_tts("salomo")

    # Computed vars for per-agent voice settings (for UI binding)
    @rx.var
    def aifred_voice(self) -> str:
        """Get AIfred's current voice"""
        return self.tts_agent_voices.get("aifred", {}).get("voice", "")

    @rx.var
    def sokrates_voice(self) -> str:
        """Get Sokrates' current voice"""
        return self.tts_agent_voices.get("sokrates", {}).get("voice", "")

    @rx.var
    def salomo_voice(self) -> str:
        """Get Salomo's current voice"""
        return self.tts_agent_voices.get("salomo", {}).get("voice", "")

    @rx.var
    def aifred_speed(self) -> str:
        """Get AIfred's current speed"""
        return self.tts_agent_voices.get("aifred", {}).get("speed", "1.0x")

    @rx.var
    def sokrates_speed(self) -> str:
        """Get Sokrates' current speed"""
        return self.tts_agent_voices.get("sokrates", {}).get("speed", "1.0x")

    @rx.var
    def salomo_speed(self) -> str:
        """Get Salomo's current speed"""
        return self.tts_agent_voices.get("salomo", {}).get("speed", "1.0x")

    @rx.var
    def aifred_pitch(self) -> str:
        """Get AIfred's current pitch"""
        return self.tts_agent_voices.get("aifred", {}).get("pitch", "1.0")

    @rx.var
    def sokrates_pitch(self) -> str:
        """Get Sokrates' current pitch"""
        return self.tts_agent_voices.get("sokrates", {}).get("pitch", "1.0")

    @rx.var
    def salomo_pitch(self) -> str:
        """Get Salomo's current pitch"""
        return self.tts_agent_voices.get("salomo", {}).get("pitch", "1.0")

    @rx.var
    def aifred_tts_enabled(self) -> bool:
        """Check if AIfred's TTS is enabled"""
        return self.tts_agent_voices.get("aifred", {}).get("enabled", True)

    @rx.var
    def sokrates_tts_enabled(self) -> bool:
        """Check if Sokrates' TTS is enabled"""
        return self.tts_agent_voices.get("sokrates", {}).get("enabled", True)

    @rx.var
    def salomo_tts_enabled(self) -> bool:
        """Check if Salomo's TTS is enabled"""
        return self.tts_agent_voices.get("salomo", {}).get("enabled", True)

    async def _regenerate_bubble_tts_core(self, bubble_index: int, save_session: bool = True) -> bool:
        """Core TTS regeneration logic for a single bubble.

        Args:
            bubble_index: Index of the bubble in chat_history
            save_session: Whether to save session after regeneration (False when called from resynthesize_all)

        Returns:
            True if successful, False otherwise
        """
        from .lib.audio_processing import clean_text_for_tts, generate_tts, set_tts_agent, save_audio_to_session
        from .lib.logging_utils import log_message
        import json
        import re

        msg = self.chat_history[bubble_index]
        agent = msg.get("agent", "aifred")

        # Use llm_history instead of chat_history - it's already cleaned
        # Find the corresponding entry in llm_history by counting assistant messages
        assistant_count = 0
        for i in range(bubble_index + 1):
            if self.chat_history[i].get("role") == "assistant":
                assistant_count += 1

        # Find the N-th assistant message in llm_history
        llm_content = None
        llm_assistant_count = 0
        for entry in self.llm_history:
            if entry.get("role") == "assistant":
                llm_assistant_count += 1
                if llm_assistant_count == assistant_count:
                    llm_content = entry.get("content", "")
                    break

        if not llm_content:
            # Fallback to chat_history if llm_history entry not found
            llm_content = msg.get("content", "")
            log_message(f"⚠️ TTS Re-Synth: Bubble {bubble_index} using chat_history fallback")

        if not llm_content or not llm_content.strip():
            log_message(f"⚠️ TTS Re-Synth: Bubble {bubble_index} content is empty")
            return False

        set_tts_agent(agent)
        # llm_history has format "[AGENT]: content" - remove the label
        content_without_label = re.sub(r'^\[(AIFRED|SOKRATES|SALOMO)\]:\s*', '', llm_content, flags=re.IGNORECASE)
        clean_text = clean_text_for_tts(content_without_label)

        if not clean_text or len(clean_text.strip()) < 5:
            log_message(f"⚠️ TTS Re-Synth: Bubble {bubble_index} text too short after cleanup")
            return False

        # Get agent voice settings
        voice_choice = self.tts_voice
        pitch_value = float(self.tts_pitch) if self.tts_pitch else 1.0
        speed_value = 1.0

        if agent in self.tts_agent_voices:
            agent_settings = self.tts_agent_voices[agent]
            if agent_settings.get("voice"):
                voice_choice = agent_settings["voice"]
            if agent_settings.get("pitch"):
                try:
                    pitch_value = float(agent_settings["pitch"])
                except ValueError:
                    pass
            if agent_settings.get("speed"):
                try:
                    speed_value = float(agent_settings["speed"].replace("x", ""))
                except ValueError:
                    pass

        # Generate TTS (complete bubble at once for best quality)
        tts_language = self._last_detected_language or self.ui_language
        audio_url = await generate_tts(
            text=clean_text,
            voice_choice=voice_choice,
            speed_choice=speed_value,
            tts_engine=self.tts_engine,
            pitch=pitch_value,
            language=tts_language
        )

        if not audio_url:
            log_message(f"⚠️ TTS Re-Synth: Bubble {bubble_index} audio generation failed")
            return False

        # Save to session directory for permanent storage
        session_audio_url = save_audio_to_session([audio_url], self.session_id)
        if not session_audio_url:
            log_message(f"⚠️ TTS Re-Synth: Bubble {bubble_index} failed to save to session")
            return False

        log_message(f"🔊 TTS: Bubble {bubble_index} saved → {session_audio_url}")

        # Update message with new audio URL
        if "metadata" not in self.chat_history[bubble_index]:
            self.chat_history[bubble_index]["metadata"] = {}
        self.chat_history[bubble_index]["metadata"]["audio_urls"] = [session_audio_url]
        self.chat_history[bubble_index]["has_audio"] = True
        self.chat_history[bubble_index]["audio_urls_json"] = json.dumps([session_audio_url])

        if save_session:
            self.chat_history = list(self.chat_history)
            self._save_current_session()

        return True

    async def resynthesize_bubble_tts(self, timestamp: str):
        """Re-synthesize TTS for a specific chat bubble.

        Args:
            timestamp: Timestamp of the message to regenerate
        """
        if self.tts_regenerating:
            return

        # Find message by timestamp
        bubble_index = None
        for i, msg in enumerate(self.chat_history):
            if msg.get("timestamp") == timestamp:
                bubble_index = i
                break

        if bubble_index is None:
            self.add_debug(f"⚠️ TTS Re-Synth: Message not found (timestamp: {timestamp})")
            return

        if self.chat_history[bubble_index].get("role") != "assistant":
            self.add_debug("⚠️ TTS Re-Synth: Message is not an assistant response")
            return

        self.tts_regenerating = True
        yield rx.call_script("stopTts()")

        # Auto-start TTS backend if not running
        if self.tts_engine == "xtts":
            self.add_debug("🔄 TTS Re-Synth: Starte XTTS Backend...")
            yield
            from .lib.process_utils import ensure_xtts_ready
            ok, msg = ensure_xtts_ready()
        elif self.tts_engine == "moss":
            self.add_debug("🔄 TTS Re-Synth: Starte MOSS-TTS Backend...")
            yield
            from .lib.process_utils import ensure_moss_ready
            ok, msg, _device = ensure_moss_ready()
        else:
            ok, msg = True, "OK"

        if not ok:
            self.add_debug(f"❌ TTS Re-Synth: {msg}")
            self.tts_regenerating = False
            return

        agent = self.chat_history[bubble_index].get("agent", "aifred")
        self.add_debug(f"🔄 TTS Re-Synth: Regenerating bubble {bubble_index} ({agent})...")
        yield

        try:
            success = await self._regenerate_bubble_tts_core(bubble_index, save_session=True)
            if success:
                self.add_debug(f"✅ TTS: Bubble {bubble_index} regenerated")
            else:
                self.add_debug(f"⚠️ TTS: Bubble {bubble_index} regeneration failed")
        except Exception as e:
            self.add_debug(f"❌ TTS Error: {e}")
            from .lib.logging_utils import log_message
            log_message(f"❌ TTS regeneration error: {e}")
        finally:
            self.tts_regenerating = False

    async def resynthesize_all_tts(self):
        """Re-synthesize TTS for all assistant messages in chat history."""
        if self.tts_regenerating:
            return

        if not self.chat_history:
            self.add_debug("⚠️ TTS Re-Synth: No chat history available")
            return

        assistant_indices = [i for i, msg in enumerate(self.chat_history) if msg.get("role") == "assistant"]
        if not assistant_indices:
            self.add_debug("⚠️ TTS Re-Synth: No assistant messages found")
            return

        self.tts_regenerating = True
        yield rx.call_script("stopTts()")

        # Auto-start TTS backend if not running
        if self.tts_engine == "xtts":
            self.add_debug("🔄 TTS Re-Synth (alle): Starte XTTS Backend...")
            yield
            from .lib.process_utils import ensure_xtts_ready
            ok, msg = ensure_xtts_ready()
        elif self.tts_engine == "moss":
            self.add_debug("🔄 TTS Re-Synth (alle): Starte MOSS-TTS Backend...")
            yield
            from .lib.process_utils import ensure_moss_ready
            ok, msg, _device = ensure_moss_ready()
        else:
            ok, msg = True, "OK"

        if not ok:
            self.add_debug(f"❌ TTS Re-Synth: {msg}")
            self.tts_regenerating = False
            return

        self.add_debug(f"🔄 TTS Re-Synth: Regenerating all {len(assistant_indices)} bubbles...")
        yield

        try:
            success_count = 0
            failed_bubbles = []
            for i, bubble_idx in enumerate(assistant_indices):
                self.add_debug(f"🔄 Processing bubble {i+1}/{len(assistant_indices)}...")
                yield

                # Use core method (don't save session after each - save once at end)
                success = await self._regenerate_bubble_tts_core(bubble_idx, save_session=False)
                if success:
                    success_count += 1
                else:
                    failed_bubbles.append(i + 1)
                    self.add_debug(f"⚠️ Bubble {i+1}/{len(assistant_indices)} failed (chat index {bubble_idx})")

            # Save session once after all regenerations
            self.chat_history = list(self.chat_history)
            self._save_current_session()

            if failed_bubbles:
                self.add_debug(f"⚠️ TTS: {success_count}/{len(assistant_indices)} bubbles regenerated — failed: {failed_bubbles}")
            else:
                self.add_debug(f"✅ TTS: {success_count}/{len(assistant_indices)} bubbles regenerated")

        except Exception as e:
            self.add_debug(f"❌ TTS Error: {e}")
            from .lib.logging_utils import log_message
            log_message(f"❌ TTS regeneration error: {e}")
        finally:
            self.tts_regenerating = False

    # TODO: clear_tts_autoplay removed - TTS Playback will be reimplemented

    def set_whisper_model(self, model_display_name: str):
        """Set Whisper model and reload.

        Args:
            model_display_name: Display name from dropdown (e.g., "small (466MB, bessere Qualität, multilingual)")
        """
        # Extract key from display name (e.g., "small (466MB, ...)" -> "small")
        model_key = model_display_name.split("(")[0].strip() if "(" in model_display_name else model_display_name
        self.whisper_model_key = model_key
        self.add_debug(f"🎤 Whisper Model: {model_key} (reload required)")
        # Reload Whisper model with new selection
        unload_whisper_model()  # Clear old model from memory
        initialize_whisper_model(model_key)
        self._save_settings()

    # REMOVED: toggle_whisper_device - Device is now configured in config.py
    # Whisper always runs on CPU to preserve GPU VRAM for LLM inference

    def toggle_show_transcription(self):
        """Toggle show transcription mode"""
        self.show_transcription = not self.show_transcription
        mode = "Edit text" if self.show_transcription else "Send directly"
        self.add_debug(f"🎤 Transcription: {mode}")
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
            # Update prompt language for LLM responses
            set_language(lang)
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
        """Get engine key for config lookup (xtts, moss, dashscope, piper, espeak, edge).

        Since tts_engine now stores keys directly, this just returns self.tts_engine.
        """
        return self.tts_engine

    def _save_agent_voices_for_engine(self, engine_key: str):
        """Save current agent voices to settings for the specified engine.

        Called before switching to a different TTS engine to preserve
        the user's agent voice preferences for that engine.
        """
        from .lib.settings import load_settings, save_settings

        settings = load_settings() or {}
        if "tts_agent_voices_per_engine" not in settings:
            settings["tts_agent_voices_per_engine"] = {}

        # Deep copy current agent voices
        import copy
        settings["tts_agent_voices_per_engine"][engine_key] = copy.deepcopy(self.tts_agent_voices)
        save_settings(settings)

    def _restore_agent_voices_for_engine(self, engine_key: str):
        """Restore agent voices from settings for the specified engine.

        Called after switching to a different TTS engine to restore
        the user's previously saved agent voice preferences for that engine.
        Falls back to engine-specific defaults if no saved preferences exist.
        """
        from .lib.settings import load_settings
        from .lib.config import TTS_AGENT_VOICE_DEFAULTS

        settings = load_settings() or {}
        saved_agent_voices = settings.get("tts_agent_voices_per_engine", {}).get(engine_key)

        if saved_agent_voices:
            # Restore from saved preferences
            for agent in self.tts_agent_voices:
                if agent in saved_agent_voices:
                    self.tts_agent_voices[agent].update(saved_agent_voices[agent])
            source = "Restored"
        else:
            # Use engine-specific defaults
            defaults = TTS_AGENT_VOICE_DEFAULTS.get(engine_key, {})
            for agent, settings_dict in defaults.items():
                if agent in self.tts_agent_voices:
                    self.tts_agent_voices[agent].update(settings_dict)
            source = "Default"

        # Log actual agent voices
        voice_list = ", ".join(
            f"{a.capitalize()}={self.tts_agent_voices[a].get('voice', '?')}"
            for a in self.tts_agent_voices
        )
        self.add_debug(f"🔊 {source} agent voices for {engine_key}: {voice_list}")

    def _save_tts_toggles_for_engine(self, engine_key: str):
        """Save current TTS toggles (autoplay, streaming) for the specified engine."""
        from .lib.settings import load_settings, save_settings

        settings = load_settings() or {}
        if "tts_toggles_per_engine" not in settings:
            settings["tts_toggles_per_engine"] = {}

        settings["tts_toggles_per_engine"][engine_key] = {
            "autoplay": self.tts_autoplay,
            "streaming": self.tts_streaming_enabled,
        }
        save_settings(settings)

    def _restore_tts_toggles_for_engine(self, engine_key: str):
        """Restore TTS toggles from settings for the specified engine.

        Falls back to engine-specific defaults if no saved preferences exist.
        """
        from .lib.settings import load_settings
        from .lib.config import TTS_TOGGLE_DEFAULTS

        settings = load_settings() or {}
        saved_toggles = settings.get("tts_toggles_per_engine", {}).get(engine_key)

        if saved_toggles:
            self.tts_autoplay = saved_toggles.get("autoplay", True)
            self.tts_streaming_enabled = saved_toggles.get("streaming", True)
            self.add_debug(f"🔊 Restored TTS toggles for {engine_key}: autoplay={self.tts_autoplay}, streaming={self.tts_streaming_enabled}")
        else:
            defaults = TTS_TOGGLE_DEFAULTS.get(engine_key, {"autoplay": True, "streaming": True})
            self.tts_autoplay = defaults["autoplay"]
            self.tts_streaming_enabled = defaults["streaming"]
            self.add_debug(f"🔊 Default TTS toggles for {engine_key}: autoplay={self.tts_autoplay}, streaming={self.tts_streaming_enabled}")

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
        elif engine_key == "xtts":
            # XTTS voices are loaded dynamically - use cached list or fallback
            from .lib.config import XTTS_VOICES_FALLBACK
            if self.xtts_voices_cache:
                voice_dict = {voice: voice for voice in self.xtts_voices_cache}
            else:
                voice_dict = XTTS_VOICES_FALLBACK
        elif engine_key == "moss":
            # MOSS voices are loaded dynamically - fetch fresh or use fallback
            from .lib.config import get_moss_voices, MOSS_TTS_VOICES_FALLBACK
            moss_voices = get_moss_voices()
            voice_dict = moss_voices if moss_voices else MOSS_TTS_VOICES_FALLBACK
        elif engine_key == "dashscope":
            from .lib.config import DASHSCOPE_VOICES
            voice_dict = DASHSCOPE_VOICES
        else:
            voice_dict = EDGE_TTS_VOICES

        # Priority 1: Check for user's saved preference
        saved_settings = load_settings() or {}
        user_voices = saved_settings.get("tts_voices_per_language", {})
        user_voice = user_voices.get(engine_key, {}).get(lang)

        if user_voice and user_voice in voice_dict:
            self.tts_voice = user_voice
            return

        # Priority 2: Use default voice from config
        default_voice = TTS_DEFAULT_VOICES.get(engine_key, {}).get(lang)

        if default_voice and default_voice in voice_dict:
            self.tts_voice = default_voice

    def get_text(self, key: str):
        """Get translated text based on current UI language"""
        from .lib import TranslationManager
        return TranslationManager.get_text(key, self.ui_language)
