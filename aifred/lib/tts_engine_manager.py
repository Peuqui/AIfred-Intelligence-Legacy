"""TTS Engine Manager — Single Source of Truth for TTS engine lifecycle.

Handles VRAM management, Docker container start/stop, and LLM backend
restart when switching between TTS engines. Used by both the browser UI
(Reflex state) and headless channels (FreeEcho.2, future voice control).

Central function: ensure_tts_state(wanted_tts, backend_type)
- Both browser and Puck call this with what they want.
- It checks what's running, and adjusts if needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generator

from .logging_utils import log_message


# Engines that require a Docker container with GPU VRAM
GPU_ENGINES = {"xtts", "moss"}

# Engines that run without Docker / without VRAM
LIGHTWEIGHT_ENGINES = {"piper", "edge", "espeak", "dashscope"}


@dataclass
class TTSState:
    """Result of ensure_tts_state check."""

    success: bool = True
    changed: bool = False           # True if VRAM state was modified
    deferred: bool = False          # True if LLM is loaded and caller should inferize first
    messages: list[str] = field(default_factory=list)
    moss_device: str = ""


def _detect_running_tts_engine() -> str:
    """Detect which GPU TTS engine is currently running via health check.

    Returns engine key ("xtts" or "moss") if running, empty string if none.
    Fast: only HTTP health checks, no Docker commands.
    """
    import requests

    from .config import XTTS_SERVICE_URL, MOSS_TTS_SERVICE_URL

    try:
        r = requests.get(f"{XTTS_SERVICE_URL}/health", timeout=1)
        if r.ok and r.json().get("model_loaded"):
            return "xtts"
    except OSError:
        pass

    try:
        r = requests.get(f"{MOSS_TTS_SERVICE_URL}/health", timeout=1)
        if r.ok and r.json().get("model_loaded"):
            return "moss"
    except OSError:
        pass

    return ""


def _is_llm_loaded(backend_type: str) -> bool:
    """Check if an LLM is currently loaded in VRAM."""
    if backend_type != "llamacpp":
        return False
    try:
        import requests
        r = requests.get("http://localhost:8099/running", timeout=2)
        if r.ok:
            models = r.json()
            return len(models) > 0
    except OSError:
        pass
    return False


def stop_engine(engine: str) -> tuple[bool, str]:
    """Stop a running TTS engine container."""
    from .process_utils import stop_xtts_container, stop_moss_container

    if engine == "xtts":
        return stop_xtts_container()
    elif engine == "moss":
        return stop_moss_container()
    return True, ""


def ensure_tts_state(
    wanted_tts: str,
    backend_type: str = "llamacpp",
    xtts_force_cpu: bool = False,
    check_defer: bool = False,
) -> Generator[str, None, TTSState]:
    """Ensure VRAM state matches TTS requirements. Yields status after each step.

    This is the SINGLE SOURCE OF TRUTH for TTS state management.
    Both browser and Puck call this with what they want.

    Args:
        wanted_tts: Desired TTS engine ("xtts", "moss", or "" for none)
        backend_type: Active LLM backend ("llamacpp", "ollama", etc.)
        xtts_force_cpu: Force XTTS to CPU mode (no VRAM needed)
        check_defer: If True and LLM is loaded, return deferred=True
                     so caller can inferize first before switching.
                     (Puck optimization: use existing LLM, switch after)

    Yields:
        Status messages after each blocking step.

    Returns:
        TTSState with success, changed, deferred flags.
    """
    # XTTS CPU mode doesn't need GPU VRAM
    if wanted_tts == "xtts" and xtts_force_cpu:
        wanted_tts = ""

    # Lightweight engines don't need VRAM management
    if wanted_tts and wanted_tts not in GPU_ENGINES:
        return TTSState(success=True)

    running = _detect_running_tts_engine()

    # Case 1: Already correct
    if running == wanted_tts:
        if running:
            yield f"{running.upper()} already running"
        return TTSState(success=True)

    # Case 2: Puck optimization — LLM loaded, wrong/no TTS
    # Caller can inferize with current LLM first, then switch
    if check_defer and wanted_tts and _is_llm_loaded(backend_type):
        yield "LLM loaded, deferring TTS switch to after inference"
        return TTSState(success=True, deferred=True)

    # Case 3: Want TTS but wrong/none running → switch
    if wanted_tts:
        yield from _do_switch(wanted_tts, running, backend_type, xtts_force_cpu)
        # Get final state
        final_running = _detect_running_tts_engine()
        return TTSState(
            success=final_running == wanted_tts,
            changed=True,
            messages=[],
        )

    # Case 4: Don't want TTS but one is running → stop it
    if running:
        yield f"Stopping {running.upper()} (not needed)..."
        success, msg = stop_engine(running)
        yield msg
        return TTSState(success=success, changed=True)

    return TTSState(success=True)


def _do_switch(
    new_engine: str,
    old_engine: str,
    backend_type: str,
    xtts_force_cpu: bool,
) -> Generator[str, None, None]:
    """Execute the actual TTS engine switch. Yields status after each step.

    Steps (all blocking, sequential):
    1. Stop old TTS container (if different one running)
    2. Free VRAM (stop LLM, stop other TTS containers)
    3. Start new TTS container + wait for model load
    4. Restart LLM backend with TTS-calibrated profile
    """
    from .process_utils import unload_all_gpu_models

    # Step 1: Stop old engine
    if old_engine and old_engine in GPU_ENGINES:
        success, msg = stop_engine(old_engine)
        status = f"{old_engine.upper()} stopped" if success else f"{old_engine.upper()} stop failed: {msg}"
        log_message(status)
        yield status

    # Step 2: Free VRAM (LLM + any remaining TTS, but keep the target)
    actions = unload_all_gpu_models(backend_type, keep_tts=new_engine)
    if actions:
        status = f"VRAM freed: {', '.join(actions)}"
        log_message(status)
        yield status

    # Step 3: Start new engine + wait for model load
    if new_engine == "xtts":
        from .process_utils import set_xtts_cpu_mode, ensure_xtts_ready

        success, msg = set_xtts_cpu_mode(xtts_force_cpu)
        log_message(msg)
        yield msg

        if success:
            success, ready_msg = ensure_xtts_ready(timeout=60)
            log_message(ready_msg)
            yield ready_msg

    elif new_engine == "moss":
        from .process_utils import ensure_moss_ready

        yield "MOSS-TTS: Loading model..."
        success, msg, device = ensure_moss_ready(timeout=120)
        log_message(msg)
        yield msg

    # Step 4: Restart LLM with TTS-calibrated profile
    restart_llm_backend(backend_type)
    yield "LLM restarted with TTS-calibrated profile"


def force_tts_switch(
    wanted_tts: str,
    backend_type: str = "llamacpp",
    xtts_force_cpu: bool = False,
) -> Generator[str, None, TTSState]:
    """Force TTS switch after deferred inference (Puck optimization).

    Called after Puck has used the existing LLM for inference.
    Now switch TTS (blocking) and restart LLM with correct profile.
    """
    running = _detect_running_tts_engine()
    if running == wanted_tts:
        return TTSState(success=True)

    yield from _do_switch(wanted_tts, running, backend_type, xtts_force_cpu)

    final_running = _detect_running_tts_engine()
    return TTSState(success=final_running == wanted_tts, changed=True)


def restart_llm_backend(
    backend_type: str = "llamacpp",
) -> bool:
    """Restart the LLM backend with current VRAM profile."""
    if backend_type == "llamacpp":
        from .process_utils import start_llama_swap
        if start_llama_swap():
            log_message("llama-swap restarted")
            return True
    return False
