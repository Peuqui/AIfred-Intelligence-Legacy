"""TTS Engine Manager — Single Source of Truth for TTS engine lifecycle.

Handles VRAM management, Docker container start/stop, and LLM backend
restart when switching between TTS engines. Used by both the browser UI
(Reflex state) and headless channels (FreeEcho.2, future voice control).

All functions are synchronous and blocking — callers handle async if needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .logging_utils import log_message


# Engines that require a Docker container with GPU VRAM
GPU_ENGINES = {"xtts", "moss"}

# Engines that run without Docker / without VRAM
LIGHTWEIGHT_ENGINES = {"piper", "edge", "espeak", "dashscope"}


@dataclass
class SwitchResult:
    """Result of a TTS engine switch operation."""

    success: bool
    messages: list[str] = field(default_factory=list)
    # MOSS-specific: which device the model loaded on ("cuda", "cpu", "")
    moss_device: str = ""


def _emit(on_status: Callable[[str], None] | None, msg: str) -> None:
    """Send status message to callback and log."""
    log_message(msg)
    if on_status:
        on_status(msg)


def stop_engine(engine: str, on_status: Callable[[str], None] | None = None) -> list[str]:
    """Stop a running TTS engine container. Returns list of actions taken."""
    from .process_utils import stop_xtts_container, stop_moss_container

    actions: list[str] = []

    if engine == "xtts":
        success, msg = stop_xtts_container()
        if success:
            _emit(on_status, "XTTS container stopped")
            actions.append("XTTS stopped")
        else:
            _emit(on_status, f"XTTS stop failed: {msg}")
    elif engine == "moss":
        success, msg = stop_moss_container()
        if success:
            _emit(on_status, "MOSS-TTS container stopped")
            actions.append("MOSS-TTS stopped")
        else:
            _emit(on_status, f"MOSS-TTS stop failed: {msg}")

    return actions


def start_engine(
    engine: str,
    xtts_force_cpu: bool = False,
    on_status: Callable[[str], None] | None = None,
) -> SwitchResult:
    """Start a TTS engine container. Returns result with status."""
    from .process_utils import set_xtts_cpu_mode, ensure_moss_ready

    if engine == "xtts":
        from .process_utils import ensure_xtts_ready
        success, msg = set_xtts_cpu_mode(xtts_force_cpu)
        _emit(on_status, msg)
        if not success:
            return SwitchResult(success=False, messages=[msg])
        # Wait for model to load (set_xtts_cpu_mode only starts the container)
        success, ready_msg = ensure_xtts_ready(timeout=60)
        _emit(on_status, ready_msg)
        return SwitchResult(success=success, messages=[msg, ready_msg])

    elif engine == "moss":
        _emit(on_status, "MOSS-TTS: Loading model...")
        success, msg, device = ensure_moss_ready(timeout=120)
        _emit(on_status, msg)
        return SwitchResult(success=success, messages=[msg], moss_device=device)

    # Lightweight engines need no container
    return SwitchResult(success=True, messages=[f"{engine} ready (no container needed)"])


def ensure_engine_ready(
    engine: str,
    backend_type: str = "llamacpp",
    xtts_force_cpu: bool = False,
    on_status: Callable[[str], None] | None = None,
    defer_llm_restart: bool = False,
) -> SwitchResult:
    """Ensure a TTS engine is ready (container running, model loaded).

    For lightweight engines (piper, edge, espeak): always a no-op success.
    For GPU engines (xtts, moss): checks health first. If already running,
    returns immediately. If not running, performs full VRAM-managed startup
    via switch_tts_engine() — same path as the browser UI.

    This ensures the LLM is restarted with TTS-calibrated VRAM settings
    (llama-swap YAML profiles account for TTS VRAM reservation).
    """
    if engine not in GPU_ENGINES:
        return SwitchResult(success=True)

    # Fast path: check if already running via health endpoint
    import requests
    if engine == "xtts":
        from .config import XTTS_SERVICE_URL
        try:
            r = requests.get(f"{XTTS_SERVICE_URL}/health", timeout=2)
            if r.ok and r.json().get("model_loaded"):
                _emit(on_status, f"XTTS already ready ({r.json().get('device', '?')})")
                return SwitchResult(success=True, messages=["XTTS already running"])
        except OSError:
            pass
    elif engine == "moss":
        from .config import MOSS_TTS_SERVICE_URL
        try:
            r = requests.get(f"{MOSS_TTS_SERVICE_URL}/health", timeout=2)
            if r.ok and r.json().get("model_loaded"):
                device = r.json().get("device", "?")
                _emit(on_status, f"MOSS-TTS already ready ({device})")
                return SwitchResult(success=True, messages=["MOSS-TTS already running"], moss_device=device)
        except OSError:
            pass

    # Slow path: full VRAM-managed startup (same as browser engine switch)
    _emit(on_status, f"{engine.upper()} not running — starting with VRAM management")
    return switch_tts_engine(
        new_engine=engine,
        old_engine=None,
        backend_type=backend_type,
        xtts_force_cpu=xtts_force_cpu,
        on_status=on_status,
        defer_llm_restart=defer_llm_restart,
    )


def switch_tts_engine(
    new_engine: str,
    old_engine: str | None = None,
    backend_type: str = "llamacpp",
    xtts_force_cpu: bool = False,
    on_status: Callable[[str], None] | None = None,
    defer_llm_restart: bool = False,
) -> SwitchResult:
    """Switch from one TTS engine to another with full VRAM management.

    Orchestrates the complete engine switch:
    1. Stop old engine container (if GPU-based)
    2. Free VRAM (if new engine needs GPU)
    3. Start new engine container
    4. Restart LLM backend (unless defer_llm_restart=True)

    Args:
        new_engine: Target engine key ("xtts", "moss", "piper", "edge", "espeak", "dashscope")
        old_engine: Currently active engine key (None = unknown/first start)
        backend_type: Active LLM backend ("llamacpp", "ollama", "vllm", "tabbyapi")
        xtts_force_cpu: Force XTTS to CPU mode (only relevant for xtts engine)
        on_status: Optional callback for status messages (e.g. add_debug, channel_log)
        defer_llm_restart: If True, skip LLM restart — caller handles it
            (e.g. FreeEcho.2: TTS generates audio first, LLM restarts in background)

    Returns:
        SwitchResult with success flag, messages, and optional moss_device.
    """
    result = SwitchResult(success=True)
    needs_vram = new_engine in GPU_ENGINES

    # Step 1: Stop old engine container
    if old_engine and old_engine in GPU_ENGINES and old_engine != new_engine:
        actions = stop_engine(old_engine, on_status)
        result.messages.extend(actions)

    # Step 2: Free VRAM if new engine needs GPU
    if needs_vram:
        from .process_utils import unload_all_gpu_models
        actions = unload_all_gpu_models(backend_type)
        if actions:
            msg = f"VRAM freed: {', '.join(actions)}"
            _emit(on_status, msg)
            result.messages.append(msg)

    # Step 3: Start new engine
    start_result = start_engine(new_engine, xtts_force_cpu, on_status)
    result.success = start_result.success
    result.messages.extend(start_result.messages)
    result.moss_device = start_result.moss_device

    # Step 4: Restart LLM backend (unless deferred)
    if needs_vram and not defer_llm_restart:
        restart_llm_backend(backend_type, on_status)

    return result


def restart_llm_backend(
    backend_type: str = "llamacpp",
    on_status: Callable[[str], None] | None = None,
) -> bool:
    """Restart the LLM backend (after VRAM was freed for TTS).

    Exposed as public function so callers with defer_llm_restart=True
    can restart the LLM at the right time (e.g. after TTS is done).
    """
    if backend_type == "llamacpp":
        from .process_utils import start_llama_swap
        if start_llama_swap():
            _emit(on_status, "llama-swap restarted")
            return True
    # Ollama/vLLM/TabbyAPI restart automatically on next request
    return False
