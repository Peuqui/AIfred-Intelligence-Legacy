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
        success, msg = set_xtts_cpu_mode(xtts_force_cpu)
        _emit(on_status, msg)
        return SwitchResult(success=success, messages=[msg])

    elif engine == "moss":
        _emit(on_status, "MOSS-TTS: Loading model...")
        success, msg, device = ensure_moss_ready(timeout=120)
        _emit(on_status, msg)
        return SwitchResult(success=success, messages=[msg], moss_device=device)

    # Lightweight engines need no container
    return SwitchResult(success=True, messages=[f"{engine} ready (no container needed)"])


def ensure_engine_ready(
    engine: str,
    xtts_force_cpu: bool = False,
    on_status: Callable[[str], None] | None = None,
) -> SwitchResult:
    """Ensure a TTS engine is ready (container running, model loaded).

    Unlike switch_tts_engine(), this does NOT free VRAM or stop other engines.
    Use this for lazy-start scenarios (e.g. FreeEcho.2 first TTS call after boot).
    For lightweight engines this is always a no-op success.
    """
    if engine not in GPU_ENGINES:
        return SwitchResult(success=True)

    # Check if already running via health endpoint
    if engine == "xtts":
        from .process_utils import ensure_xtts_ready
        success, msg = ensure_xtts_ready(timeout=60)
        if on_status and msg:
            on_status(msg)
        return SwitchResult(success=success, messages=[msg] if msg else [])
    elif engine == "moss":
        from .process_utils import ensure_moss_ready
        success, msg, device = ensure_moss_ready(timeout=120)
        if on_status and msg:
            on_status(msg)
        return SwitchResult(success=success, messages=[msg] if msg else [], moss_device=device)

    return SwitchResult(success=True)


def switch_tts_engine(
    new_engine: str,
    old_engine: str | None = None,
    backend_type: str = "llamacpp",
    xtts_force_cpu: bool = False,
    on_status: Callable[[str], None] | None = None,
) -> SwitchResult:
    """Switch from one TTS engine to another with full VRAM management.

    Orchestrates the complete engine switch:
    1. Stop old engine container (if GPU-based)
    2. Free VRAM (if new engine needs GPU)
    3. Start new engine container
    4. Restart LLM backend (if it was stopped for VRAM)

    Args:
        new_engine: Target engine key ("xtts", "moss", "piper", "edge", "espeak", "dashscope")
        old_engine: Currently active engine key (None = unknown/first start)
        backend_type: Active LLM backend ("llamacpp", "ollama", "vllm", "tabbyapi")
        xtts_force_cpu: Force XTTS to CPU mode (only relevant for xtts engine)
        on_status: Optional callback for status messages (e.g. add_debug, channel_log)

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

    # Step 4: Restart LLM backend (was stopped in step 2)
    if needs_vram:
        from .process_utils import start_llama_swap
        if backend_type == "llamacpp":
            if start_llama_swap():
                _emit(on_status, "llama-swap restarted")
                result.messages.append("llama-swap restarted")
        # Ollama/vLLM/TabbyAPI restart automatically on next request

    return result
