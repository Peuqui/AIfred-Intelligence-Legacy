"""
AIfred REST API Module

Provides HTTP API endpoints for remote control of AIfred.
Uses FastAPI and is mounted at /api by Reflex's app.api.mount().

API Documentation: http://localhost:8002/api/docs

Endpoints (all prefixed with /api):
- GET  /health              - Health check
- GET  /settings            - Get all settings
- PATCH /settings           - Update settings
- GET  /models              - List available models
- GET  /sessions            - List all sessions
- POST /chat/inject         - Inject message into browser session
- GET  /chat/status         - Get chat/generation status
- POST /chat/clear          - Clear chat history
- GET  /chat/history        - Get chat history
- POST /system/restart-ollama   - Restart Ollama service
- POST /system/restart-aifred   - Restart AIfred service
- POST /system/clear-vectordb   - Clear Vector DB
- POST /system/reset-defaults   - Reset to default settings
- POST /calibrate           - Run context calibration
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import asyncio
import subprocess

from .settings import load_settings, save_settings, get_default_settings
from .logging_utils import log_message
from .config import DEFAULT_OLLAMA_URL


# ============================================================
# Pydantic Models for API Request/Response
# ============================================================

class HealthResponse(BaseModel):
    """Health check response"""
    status: str = "ok"
    version: str = "2.15.0"
    backend_type: str = ""
    backend_healthy: bool = False


class SettingsResponse(BaseModel):
    """Current settings response"""
    # Backend
    backend_type: str = "ollama"
    backend_url: str = DEFAULT_OLLAMA_URL

    # Models
    aifred_model: str = ""
    sokrates_model: str = ""
    salomo_model: str = ""
    automatik_model: str = ""
    vision_model: str = ""

    # RoPE Factors
    aifred_rope_factor: float = 1.0
    sokrates_rope_factor: float = 1.0
    salomo_rope_factor: float = 1.0
    automatik_rope_factor: float = 1.0
    vision_rope_factor: float = 1.0

    # LLM Parameters
    temperature: float = 0.3
    temperature_mode: str = "auto"
    enable_thinking: bool = True

    # Research
    research_mode: str = "automatik"

    # Multi-Agent
    multi_agent_mode: str = "standard"
    max_debate_rounds: int = 3
    consensus_type: str = "majority"

    # TTS/STT
    enable_tts: bool = False
    tts_voice: str = "Deutsch (Katja)"
    tts_engine: str = "Edge TTS (Cloud, best quality)"
    whisper_model_key: str = "small"

    # UI
    ui_language: str = "de"
    user_name: str = ""


class SettingsUpdate(BaseModel):
    """Settings update request - all fields optional"""
    # Backend
    backend_type: Optional[str] = None

    # Models (by ID, not display name)
    aifred_model: Optional[str] = None
    sokrates_model: Optional[str] = None
    salomo_model: Optional[str] = None
    automatik_model: Optional[str] = None
    vision_model: Optional[str] = None

    # RoPE Factors
    aifred_rope_factor: Optional[float] = None
    sokrates_rope_factor: Optional[float] = None
    salomo_rope_factor: Optional[float] = None
    automatik_rope_factor: Optional[float] = None
    vision_rope_factor: Optional[float] = None

    # LLM Parameters
    temperature: Optional[float] = None
    temperature_mode: Optional[str] = None
    enable_thinking: Optional[bool] = None

    # Research
    research_mode: Optional[str] = None

    # Multi-Agent
    multi_agent_mode: Optional[str] = None
    max_debate_rounds: Optional[int] = None
    consensus_type: Optional[str] = None

    # TTS/STT
    enable_tts: Optional[bool] = None
    tts_voice: Optional[str] = None
    tts_engine: Optional[str] = None
    whisper_model_key: Optional[str] = None

    # UI
    ui_language: Optional[str] = None
    user_name: Optional[str] = None


class ModelsResponse(BaseModel):
    """Available models response"""
    backend_type: str
    models: Dict[str, str]  # {model_id: display_label}
    vision_models: List[str]  # List of vision-capable model IDs


class ChatInjectRequest(BaseModel):
    """Chat inject request - injects message into browser session"""
    message: str = Field(..., min_length=1, description="User message to inject")
    device_id: str = Field(..., description="Browser session device_id (required)")


class ChatHistoryResponse(BaseModel):
    """Chat history response"""
    chat_history: List[Dict[str, str]]  # [{user: "...", assistant: "..."}]
    llm_history: List[Dict[str, str]]  # [{role: "user/assistant/system", content: "..."}]
    session_id: str = ""


class SystemActionResponse(BaseModel):
    """Response for system actions"""
    success: bool
    message: str
    details: Optional[str] = None


# ============================================================
# FastAPI App
# ============================================================

api_app = FastAPI(
    title="AIfred Intelligence API",
    description="REST API for remote control of AIfred Intelligence",
    version="2.15.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# NOTE: CORS middleware is NOT added here.
# Reflex handles CORS via its own middleware when using api_transformer.
# Adding CORSMiddleware here causes "ASGI flow error: Connection already upgraded"
# because it conflicts with Reflex's WebSocket upgrade handling.


# ============================================================
# Global State Access
# ============================================================

def get_global_backend_state() -> Dict[str, Any]:
    """Get reference to global backend state from state.py"""
    try:
        from ..state import _global_backend_state
        return _global_backend_state
    except ImportError:
        return {}


def get_active_session_state():
    """
    Get the active AIState session if one exists.

    NOTE: This is tricky because Reflex state is session-bound.
    We use a module-level reference that gets set when a session is active.
    """
    try:
        from ..state import _active_api_state
        return _active_api_state
    except (ImportError, AttributeError):
        return None


# ============================================================
# Health Endpoint
# ============================================================

@api_app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint.

    Returns API status and backend connection info.
    """
    global_state = get_global_backend_state()
    settings = load_settings() or {}

    return HealthResponse(
        status="ok",
        version="2.15.0",
        backend_type=settings.get("backend_type", "ollama"),
        backend_healthy=global_state.get("backend_type") is not None
    )


# ============================================================
# Settings Endpoints
# ============================================================

@api_app.get("/settings", response_model=SettingsResponse, tags=["Settings"])
async def get_settings():
    """
    Get all current settings.

    Returns the complete settings configuration including models,
    multi-agent settings, TTS/STT config, etc.
    """
    settings = load_settings()
    if not settings:
        settings = get_default_settings()

    global_state = get_global_backend_state()

    # Extract models from backend_models if available
    backend_type = settings.get("backend_type", "ollama")
    backend_models = settings.get("backend_models", {}).get(backend_type, {})

    # Get backend URL with proper fallback (global_state may have None values)
    backend_url = global_state.get("backend_url") or DEFAULT_OLLAMA_URL

    return SettingsResponse(
        backend_type=backend_type,
        backend_url=backend_url,
        # Models can be in backend_models or directly in settings
        aifred_model=settings.get("model", backend_models.get("aifred_model", "")),
        sokrates_model=settings.get("sokrates_model", ""),
        salomo_model=settings.get("salomo_model", ""),
        automatik_model=settings.get("automatik_model", backend_models.get("automatik_model", "")),
        vision_model=settings.get("vision_model", backend_models.get("vision_model", "")),
        aifred_rope_factor=settings.get("aifred_rope_factor", 1.0),
        sokrates_rope_factor=settings.get("sokrates_rope_factor", 1.0),
        salomo_rope_factor=settings.get("salomo_rope_factor", 1.0),
        automatik_rope_factor=settings.get("automatik_rope_factor", 1.0),
        vision_rope_factor=settings.get("vision_rope_factor", 1.0),
        temperature=settings.get("temperature", 0.3),
        temperature_mode=settings.get("temperature_mode", "auto"),
        enable_thinking=settings.get("enable_thinking", True),
        research_mode=settings.get("research_mode", "automatik"),
        multi_agent_mode=settings.get("multi_agent_mode", "standard"),
        max_debate_rounds=settings.get("max_debate_rounds", 3),
        consensus_type=settings.get("consensus_type", "majority"),
        enable_tts=settings.get("enable_tts", False),
        # Handle different field names in settings.json
        tts_voice=settings.get("voice", settings.get("tts_voice", "Deutsch (Katja)")),
        tts_engine=settings.get("tts_engine", "Edge TTS (Cloud, best quality)"),
        whisper_model_key=settings.get("whisper_model", settings.get("whisper_model_key", "small")),
        ui_language=settings.get("ui_language", "de"),
        user_name=settings.get("user_name", "")
    )


@api_app.patch("/settings", response_model=SettingsResponse, tags=["Settings"])
async def update_settings(update: SettingsUpdate):
    """
    Update settings.

    Only provided fields are updated, others remain unchanged.
    Changes are persisted to settings.json.

    NOTE: Model changes may require backend restart to take effect.
    Use /api/system/restart-ollama after changing models.
    """
    settings = load_settings()
    if not settings:
        settings = get_default_settings()

    # Apply updates (only non-None values)
    update_dict = update.model_dump(exclude_none=True)

    # Map API field names to settings.json field names
    field_mapping = {
        "aifred_model": "model",
        "tts_voice": "voice",
        "whisper_model_key": "whisper_model",
    }

    for api_field, value in update_dict.items():
        settings_field = field_mapping.get(api_field, api_field)
        settings[settings_field] = value
        log_message(f"📝 API: Updated {settings_field} = {value}")

    # Save to file
    if not save_settings(settings):
        raise HTTPException(status_code=500, detail="Failed to save settings")

    log_message(f"✅ API: Settings saved ({len(update_dict)} fields updated)")

    # Set global settings update timestamp to trigger browser reload
    # NEW: Timestamp-based system - all browsers will see the update (no race condition)
    from .session_storage import set_settings_update_flag
    set_settings_update_flag()
    log_message("🔄 API: Settings update timestamp set for all browsers")

    # Return updated settings
    return await get_settings()


# ============================================================
# Models Endpoints
# ============================================================

@api_app.get("/models", response_model=ModelsResponse, tags=["Models"])
async def get_available_models():
    """
    Get list of available models.

    Returns all models from the current backend with their display labels
    and a separate list of vision-capable models.
    """
    global_state = get_global_backend_state()
    settings = load_settings() or {}

    models_dict: Dict[str, str] = {}
    vision_models: List[str] = []
    backend_type = settings.get("backend_type", "ollama")

    # Get models from global state (populated by initialize_backend)
    available = global_state.get("available_models", [])

    # If global state is empty, try to fetch from backend
    if not available:
        try:
            import httpx
            if backend_type == "ollama":
                backend_url = settings.get("backend_url", DEFAULT_OLLAMA_URL)
                response = httpx.get(f"{backend_url}/api/tags", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    for m in data.get("models", []):
                        model_id = m['name']
                        size_gb = m['size'] / (1024**3)
                        models_dict[model_id] = f"{model_id} ({size_gb:.1f} GB)"
                        # Check if vision model
                        if any(v in model_id.lower() for v in ['vision', 'vl', 'llava']):
                            vision_models.append(model_id)
        except Exception as e:
            log_message(f"⚠️ API: Failed to fetch models: {e}")
    else:
        # Use cached models - need to reconstruct dict
        # Global state stores display labels, we need to extract IDs
        for display_label in available:
            # Extract model ID from display label (e.g., "qwen3:8b (2.3 GB)" -> "qwen3:8b")
            model_id = display_label.split(" (")[0] if " (" in display_label else display_label
            models_dict[model_id] = display_label
            if any(v in model_id.lower() for v in ['vision', 'vl', 'llava']):
                vision_models.append(model_id)

    return ModelsResponse(
        backend_type=backend_type,
        models=models_dict,
        vision_models=vision_models
    )


# ============================================================
# Chat Endpoints
# ============================================================

class ChatInjectResponse(BaseModel):
    """Chat inject response"""
    success: bool
    message: str
    session_id: str = ""
    queued: bool = True


@api_app.post("/chat/inject", response_model=ChatInjectResponse, tags=["Chat"])
async def inject_message(request: ChatInjectRequest):
    """
    Inject a message into a browser session.

    The message is queued for the browser to process. The browser will
    automatically pick up the message and run the full pipeline:
    - Intent Detection
    - Research/Automatik Mode
    - Multi-Agent (Sokrates/Tribunal)
    - History Compression

    This ensures the API uses the exact same code path as manual browser input.
    The user sees everything live in the browser - streaming, debug messages, etc.

    Requires device_id to identify the target browser session.
    Use GET /api/sessions to list available sessions.
    """
    from .session_storage import set_pending_message

    log_message(f"📨 API: Injecting message to {request.device_id[:8]}...")

    success = set_pending_message(request.device_id, request.message)

    if success:
        log_message(f"✅ API: Message queued for {request.device_id[:8]}...")
        return ChatInjectResponse(
            success=True,
            message="Message queued for browser processing",
            session_id=request.device_id,
            queued=True
        )
    else:
        log_message(f"❌ API: Failed to queue message for {request.device_id[:8]}...")
        raise HTTPException(status_code=500, detail="Failed to queue message")


class ChatStatusResponse(BaseModel):
    """Chat status response"""
    is_generating: bool = False
    message_count: int = 0
    session_id: str = ""


@api_app.get("/chat/status", response_model=ChatStatusResponse, tags=["Chat"])
async def get_chat_status(device_id: str):
    """
    Get current chat status for a session.

    Use this to poll for completion after injecting a message.
    When is_generating becomes False, the response is complete.

    Args:
        device_id: Browser session device_id
    """
    from .session_storage import load_session

    session = load_session(device_id)
    if not session or "data" not in session:
        raise HTTPException(status_code=404, detail="Session not found")

    data = session["data"]
    chat_history = data.get("chat_history", [])

    return ChatStatusResponse(
        is_generating=data.get("is_generating", False),
        message_count=len(chat_history),
        session_id=device_id
    )


class ChatClearRequest(BaseModel):
    """Chat clear request"""
    device_id: Optional[str] = Field(None, description="Browser session device_id to clear")


@api_app.post("/chat/clear", response_model=SystemActionResponse, tags=["Chat"])
async def clear_chat(request: ChatClearRequest = ChatClearRequest()):
    """
    Clear chat history for a browser session.

    If device_id is provided, clears that session's chat history.
    Otherwise clears the most recently modified session.
    The browser will auto-reload and show empty chat.
    """
    from .session_storage import (
        update_chat_data, set_update_flag, get_latest_session_file
    )

    # Determine which session to clear
    device_id = request.device_id
    if not device_id:
        session_file = get_latest_session_file()
        if session_file:
            device_id = session_file.stem
        else:
            return SystemActionResponse(
                success=False,
                message="No sessions found to clear"
            )

    # Clear the session's chat data (including debug console, like browser button)
    success = update_chat_data(
        device_id=device_id,
        chat_history=[],
        llm_history=[],
        debug_messages=[]  # Clear debug console too!
    )

    if success:
        # Set update flag to trigger browser reload
        set_update_flag(device_id)
        log_message(f"🗑️ API: Chat session {device_id[:8]}... cleared")
        return SystemActionResponse(
            success=True,
            message=f"Chat session {device_id[:8]}... cleared"
        )
    else:
        return SystemActionResponse(
            success=False,
            message=f"Failed to clear session {device_id[:8]}..."
        )


class SessionInfo(BaseModel):
    """Session info for listing"""
    device_id: str
    last_seen: str
    message_count: int


class SessionsListResponse(BaseModel):
    """List of all sessions"""
    sessions: List[SessionInfo]


@api_app.get("/sessions", response_model=SessionsListResponse, tags=["Chat"])
async def list_all_sessions():
    """
    List all available sessions.

    Returns device_id, last_seen, and message_count for each session.
    Use device_id with /api/chat/send to write to a specific browser session.
    """
    from .session_storage import list_sessions

    sessions = list_sessions()
    return SessionsListResponse(
        sessions=[SessionInfo(**s) for s in sessions]
    )


@api_app.get("/chat/history", response_model=ChatHistoryResponse, tags=["Chat"])
async def get_chat_history(device_id: Optional[str] = None):
    """
    Get chat history for a session.

    If device_id is provided, returns that session's history.
    Otherwise returns the most recently modified session.

    Returns both the UI-friendly chat_history and the LLM-optimized llm_history.
    """
    from .session_storage import load_session, get_latest_session_file

    try:
        # Determine which session to load
        if device_id:
            session_data = load_session(device_id)
            session_id = device_id
        else:
            session_file = get_latest_session_file()
            if session_file:
                session_data = load_session(session_file.stem)
                session_id = session_file.stem
            else:
                session_data = None
                session_id = ""

        if session_data and "data" in session_data:
            # Convert chat_history format (stored as lists, need dicts)
            chat_history = []
            stored_history = session_data["data"].get("chat_history", [])
            for msg in stored_history:
                if isinstance(msg, (list, tuple)) and len(msg) >= 2:
                    chat_history.append({
                        "user": msg[0],
                        "assistant": msg[1]
                    })

            return ChatHistoryResponse(
                chat_history=chat_history,
                llm_history=session_data["data"].get("llm_history", []),
                session_id=session_id
            )
    except Exception as e:
        log_message(f"⚠️ API: Failed to load session: {e}")

    return ChatHistoryResponse(
        chat_history=[],
        llm_history=[],
        session_id=""
    )


# ============================================================
# System Endpoints
# ============================================================

@api_app.post("/system/restart-ollama", response_model=SystemActionResponse, tags=["System"])
async def restart_ollama():
    """
    Restart Ollama service.

    Uses systemctl to restart the ollama service.
    Waits for the service to be ready before returning.
    """
    log_message("🔄 API: Restarting Ollama service...")

    try:
        # Restart via systemctl
        result = subprocess.run(
            ["systemctl", "restart", "ollama"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"systemctl restart failed: {result.stderr}"
            )

        # Wait for Ollama to be ready
        import httpx
        settings = load_settings() or {}
        backend_url = settings.get("backend_url", DEFAULT_OLLAMA_URL)

        for attempt in range(20):  # 10 seconds max
            await asyncio.sleep(0.5)
            try:
                response = httpx.get(f"{backend_url}/api/tags", timeout=2.0)
                if response.status_code == 200:
                    log_message(f"✅ API: Ollama ready after {(attempt+1)*0.5:.1f}s")
                    return SystemActionResponse(
                        success=True,
                        message="Ollama restarted successfully",
                        details=f"Ready after {(attempt+1)*0.5:.1f}s"
                    )
            except httpx.RequestError:
                continue

        return SystemActionResponse(
            success=True,
            message="Ollama restart initiated",
            details="Service may still be starting"
        )

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Restart timed out")
    except Exception as e:
        log_message(f"❌ API: Ollama restart failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_app.post("/system/restart-aifred", response_model=SystemActionResponse, tags=["System"])
async def restart_aifred(background_tasks: BackgroundTasks):
    """
    Restart AIfred service.

    Schedules a restart and returns immediately.
    The service will restart after a short delay.
    """
    log_message("🔄 API: AIfred restart requested...")

    from .process_utils import restart_service

    def delayed_restart():
        import time
        time.sleep(1)
        restart_service("aifred-intelligence", check=False)

    background_tasks.add_task(delayed_restart)

    return SystemActionResponse(
        success=True,
        message="AIfred restart scheduled",
        details="Service will restart in ~1 second"
    )


@api_app.post("/system/clear-vectordb", response_model=SystemActionResponse, tags=["System"])
async def clear_vector_db():
    """
    Clear Vector DB (ChromaDB).

    Deletes all cached research entries from ChromaDB.
    The collection structure remains intact.
    """
    log_message("🗑️ API: Clearing Vector DB...")

    try:
        import chromadb
        client = chromadb.HttpClient(host='localhost', port=8000)
        collection = client.get_collection('research_cache')

        # Get all IDs
        all_ids = collection.get(include=[])["ids"]
        count = len(all_ids)

        if all_ids:
            collection.delete(ids=all_ids)
            log_message(f"✅ API: Deleted {count} entries from Vector DB")
            return SystemActionResponse(
                success=True,
                message=f"Vector DB cleared ({count} entries deleted)"
            )
        else:
            return SystemActionResponse(
                success=True,
                message="Vector DB is already empty"
            )

    except Exception as e:
        log_message(f"❌ API: Vector DB clear failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_app.post("/system/reset-defaults", response_model=SystemActionResponse, tags=["System"])
async def reset_to_defaults():
    """
    Reset all settings to defaults.

    Loads default values from config.py and saves them to settings.json.
    Backend restart may be required for changes to take effect.
    """
    from .settings import reset_to_defaults as do_reset

    log_message("💾 API: Resetting to default settings...")

    if do_reset():
        log_message("✅ API: Settings reset to defaults")
        return SystemActionResponse(
            success=True,
            message="Settings reset to defaults",
            details="Restart backend for changes to take effect"
        )
    else:
        raise HTTPException(status_code=500, detail="Failed to reset settings")


@api_app.post("/calibrate", response_model=SystemActionResponse, tags=["System"])
async def run_calibration():
    """
    Run context window calibration.

    Tests maximum context size for each model configuration.
    Results are cached for faster subsequent use.

    NOTE: This can take several minutes depending on number of models.
    """
    log_message("🔧 API: Starting context calibration...")

    try:
        from .model_vram_cache import calibrate_all_models

        settings = load_settings() or {}
        backend_type = settings.get("backend_type", "ollama")

        if backend_type != "ollama":
            return SystemActionResponse(
                success=False,
                message="Calibration only supported for Ollama backend"
            )

        # Run calibration (this can take a while)
        results = await calibrate_all_models()

        calibrated_count = len([r for r in results if r.get("success")])

        log_message(f"✅ API: Calibration complete ({calibrated_count} models)")

        return SystemActionResponse(
            success=True,
            message=f"Calibration complete ({calibrated_count} models calibrated)",
            details=str(results)
        )

    except Exception as e:
        log_message(f"❌ API: Calibration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Export for api_transformer
# ============================================================

def get_api_app() -> FastAPI:
    """
    Get the FastAPI app for use with Reflex api_transformer.

    Usage in rxconfig.py or aifred.py:
        from aifred.lib.api import get_api_app
        app = rx.App(api_transformer=get_api_app())
    """
    return api_app
