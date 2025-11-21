"""
GPU Utilities - VRAM Detection and Context Calculation

Provides functions to query free VRAM and calculate practical context limits
based on available GPU memory.
"""

import logging
import httpx
from typing import Optional
from .config import (
    VRAM_SAFETY_MARGIN,
    VRAM_CONTEXT_RATIO,
    ENABLE_VRAM_CONTEXT_CALCULATION
)
from .logging_utils import log_message
from .formatting import format_number

logger = logging.getLogger(__name__)


# NOTE: is_model_loaded() wurde nach backends/base.py verschoben als abstractmethod
# Jedes Backend implementiert seine eigene Logik:
# - Ollama: Query /api/ps endpoint
# - vLLM: Always True (model fixed at server start)
# - TabbyAPI: Always True (model fixed at server start)


def get_free_vram_mb() -> Optional[int]:
    """
    Query free VRAM using pynvml (NVIDIA Management Library)

    This is the modern, fast way to query GPU memory.
    Replaces old nvidia-smi subprocess approach for better performance.

    Returns:
        int: Free VRAM in MB, or None if GPU unavailable
    """
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)  # GPU 0
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        free_mb = mem_info.free / (1024 * 1024)
        pynvml.nvmlShutdown()
        return int(free_mb)

    except ImportError:
        logger.warning("pynvml not installed - install via: pip install pynvml")
        return None
    except Exception as e:
        logger.debug(f"Could not query GPU via pynvml: {e}")
        return None


def get_model_size_from_cache(model_name: str) -> int:
    """
    Get model size in bytes from HuggingFace cache

    Args:
        model_name: Model name (e.g., "cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit")

    Returns:
        int: Model size in bytes, or 0 if not found
    """
    from pathlib import Path
    import os

    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"

    # Convert model name to cache folder format
    cache_folder_name = f"models--{model_name.replace('/', '--')}"

    try:
        for model_dir in cache_dir.glob(cache_folder_name):
            # Find all model files (safetensors, bin, gguf, etc.)
            total_size = 0

            # Search for model weight files
            for pattern in ["**/*.safetensors", "**/*.bin", "**/*.gguf", "**/*.pth"]:
                for file_path in model_dir.glob(pattern):
                    if file_path.is_file():
                        total_size += file_path.stat().st_size

            if total_size > 0:
                logger.debug(f"Model size for {model_name}: {total_size / (1024**3):.2f} GB")
                return total_size

        logger.warning(f"Could not determine size for model: {model_name}")
        return 0

    except Exception as e:
        logger.warning(f"Error getting model size: {e}")
        return 0


def calculate_vram_based_context(
    model_name: str,
    model_size_bytes: int,
    model_context_limit: int,
    vram_context_ratio: float = VRAM_CONTEXT_RATIO,
    safety_margin_mb: int = VRAM_SAFETY_MARGIN,
    model_is_loaded: bool = False
) -> tuple[int, list[str]]:
    """
    Calculate maximum practical context window based on available VRAM

    UNIVERSAL FUNCTION FOR ALL BACKENDS (Ollama, vLLM, TabbyAPI)

    Args:
        model_name: Name of the model (for logging only)
        model_size_bytes: Model size in bytes (from HF cache or Ollama blobs)
        model_context_limit: Model's architectural context limit (from config.json)
        vram_context_ratio: MB of VRAM per context token (default: 0.097 from config)
        safety_margin_mb: MB to reserve for system (default: 512 MB from config)
        model_is_loaded: Whether model is already loaded in VRAM (affects calculation)

    Returns:
        tuple[int, list[str]]: (num_ctx, debug_messages)
            - num_ctx: Maximum practical context based on VRAM constraints
            - debug_messages: List of debug messages for UI console (via yield)

    Process:
        1. Query free VRAM from nvidia-smi
        2. Subtract safety margin (OS, Xorg, Whisper)
        3. If model NOT loaded: Subtract model size from free VRAM
        4. If model IS loaded: Free VRAM already accounts for it
        5. Calculate: max_tokens = vram_for_context / vram_context_ratio
        6. Clip to model's architectural limit

    Fallbacks:
        - VRAM calculation disabled: Use model_context_limit
        - nvidia-smi unavailable: Use model_context_limit
        - Insufficient VRAM (<100 MB): Return 2048 tokens (minimal)
    """
    debug_msgs = []  # Collect messages for UI yield

    # Check if VRAM calculation is enabled
    if not ENABLE_VRAM_CONTEXT_CALCULATION:
        logger.debug("VRAM context calculation disabled in config")
        return model_context_limit, []

    # Wait for VRAM to stabilize (model fully loaded)
    # This ensures accurate measurements after model preload

    max_wait_time = 3.0  # Maximum 3 seconds
    poll_interval = 0.2  # Check every 200ms
    stability_checks = 2  # Need 2 consecutive stable readings
    waited = 0.0

    prev_vram = None
    stable_count = 0

    while waited < max_wait_time:
        current_vram = get_free_vram_mb()

        if current_vram is not None and prev_vram is not None:
            # VRAM stable if difference < 50 MB (tolerance for measurement noise)
            vram_diff = abs(current_vram - prev_vram)
            if vram_diff < 50:
                stable_count += 1
                if stable_count >= stability_checks:
                    break  # VRAM is stable, model fully loaded
            else:
                stable_count = 0  # Reset if VRAM still changing

        prev_vram = current_vram
        import time
        time.sleep(poll_interval)
        waited += poll_interval

    if waited >= max_wait_time:
        logger.warning(f"VRAM stabilization timed out after {max_wait_time}s")

    # Query free VRAM (after stabilization)
    free_vram_mb = get_free_vram_mb()

    if free_vram_mb is None:
        # Fallback: Use architectural limit
        msg = (
            "⚠️ VRAM query failed (CPU-only or nvidia-smi unavailable), "
            "using model's architectural limit"
        )
        log_message(msg)
        debug_msgs.append(msg)
        return model_context_limit, debug_msgs

    # Calculate usable VRAM (after safety margin)
    usable_vram = free_vram_mb - safety_margin_mb

    # Convert model size to MB for calculations
    model_size_mb = model_size_bytes / (1024**2) if model_size_bytes > 0 else 0

    # TWO-SCENARIO LOGIC:
    # Scenario 1: Model NOT loaded → Must subtract model size from free VRAM
    # Scenario 2: Model IS loaded → Free VRAM already reflects loaded model
    # (Caller determines this based on backend-specific logic)
    if model_is_loaded:
        # Model already in VRAM - free_vram_mb already accounts for it
        vram_for_context = usable_vram
        msg = (
            f"💾 Model loaded → {format_number(vram_for_context, 0)} MB for context "
            f"({format_number(free_vram_mb)} MB free - {format_number(safety_margin_mb)} MB margin)"
        )
        log_message(msg)
        debug_msgs.append(msg)
    else:
        # Model NOT loaded - must subtract its size from available VRAM
        vram_for_context = int(usable_vram - model_size_mb)
        msg = (
            f"💾 Model NOT loaded → {format_number(vram_for_context, 0)} MB for context "
            f"({format_number(free_vram_mb)} MB - {format_number(model_size_mb, 0)} MB model - {format_number(safety_margin_mb)} MB margin)"
        )
        log_message(msg)
        debug_msgs.append(msg)

    if vram_for_context < 100:
        msg = f"❌ Insufficient VRAM for context: {format_number(vram_for_context, 0)} MB (< 100 MB minimum) → Fallback 2.048"
        log_message(msg)
        debug_msgs.append(msg)
        return 2048, debug_msgs  # Minimal fallback

    # Calculate max tokens
    max_practical_tokens = int(vram_for_context / vram_context_ratio)

    # Clip to architectural limit
    final_num_ctx = min(max_practical_tokens, model_context_limit)

    # Log detailed VRAM calculation to debug console
    # Format with German thousands separator (dot instead of comma)
    formatted_ctx = format_number(final_num_ctx)
    formatted_vram_max = format_number(max_practical_tokens)
    formatted_model_max = format_number(model_context_limit)

    # Determine limiting factor and create compact message
    if max_practical_tokens <= model_context_limit:
        # VRAM is the bottleneck
        msg = f"🎯 VRAM-Limit: {formatted_ctx} tok (Model Max: {formatted_model_max} tok)"
    else:
        # Model is the bottleneck
        msg = f"🎯 Model-Limit: {formatted_ctx} tok (VRAM Max: {formatted_vram_max} tok)"
    log_message(msg)
    debug_msgs.append(msg)

    return final_num_ctx, debug_msgs
