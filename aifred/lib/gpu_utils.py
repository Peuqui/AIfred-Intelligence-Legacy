"""
GPU Utilities - VRAM Detection and Context Calculation

Provides functions to query free VRAM and calculate practical context limits
based on available GPU memory.
"""

import subprocess
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


def is_model_loaded(model_name: str, ollama_base_url: str = "http://localhost:11434") -> bool:
    """
    Check if a model is currently loaded in Ollama via /api/ps

    Args:
        model_name: Name of the model to check (e.g., "qwen2.5:32b")
        ollama_base_url: Ollama API base URL

    Returns:
        bool: True if model is loaded, False otherwise
    """
    try:
        response = httpx.get(f"{ollama_base_url}/api/ps", timeout=2.0)
        if response.status_code != 200:
            logger.debug(f"/api/ps returned status {response.status_code}")
            return False

        data = response.json()
        loaded_models = data.get("models", [])

        # Check if our model is in the loaded models list
        for model in loaded_models:
            if model.get("name") == model_name or model.get("model") == model_name:
                log_message(f"✅ Model '{model_name}' is already loaded in VRAM")
                return True

        log_message(f"ℹ️ Model '{model_name}' is NOT loaded yet")
        return False

    except httpx.TimeoutException:
        logger.warning("/api/ps query timed out after 2s")
        return False
    except Exception as e:
        logger.warning(f"Failed to check model load status: {e}")
        return False


def get_free_vram_mb() -> Optional[int]:
    """
    Query free VRAM using nvidia-smi

    Returns:
        int: Free VRAM in MB, or None if nvidia-smi unavailable
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=2  # Fast timeout - don't block inference
        )

        if result.returncode != 0:
            logger.debug(f"nvidia-smi returned non-zero: {result.returncode}")
            return None

        # Parse output: "18432" (MB)
        free_mb = int(result.stdout.strip())
        return free_mb

    except subprocess.TimeoutExpired:
        logger.warning("nvidia-smi query timed out after 2s")
        return None
    except FileNotFoundError:
        logger.debug("nvidia-smi not found (CPU-only system or not in PATH)")
        return None
    except ValueError as e:
        logger.warning(f"Failed to parse nvidia-smi output: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error querying VRAM: {e}")
        return None


def calculate_vram_based_context(
    model_name: str,
    model_size_bytes: int,
    model_context_limit: int,
    vram_context_ratio: float = VRAM_CONTEXT_RATIO,
    safety_margin_mb: int = VRAM_SAFETY_MARGIN,
    ollama_base_url: str = "http://localhost:11434"
) -> tuple[int, list[str]]:
    """
    Calculate maximum practical context window based on available VRAM

    Args:
        model_name: Name of the model (for load detection via /api/ps)
        model_size_bytes: Model size in bytes (from blob filesystem lookup)
        model_context_limit: Model's architectural context limit
        vram_context_ratio: MB of VRAM per context token (default: from config)
        safety_margin_mb: MB to reserve for system (default: from config)
        ollama_base_url: Ollama API base URL

    Returns:
        tuple[int, list[str]]: (num_ctx, debug_messages)
            - num_ctx: Maximum practical context based on VRAM constraints
            - debug_messages: List of debug messages for UI console (via yield)

    Note:
        Falls back to model_context_limit if:
        - VRAM calculation disabled in config
        - nvidia-smi unavailable
        - Insufficient VRAM detected

    Two-Scenario Handling:
        - Model NOT loaded: Subtract model_size_bytes from free VRAM
        - Model IS loaded: Free VRAM already reflects loaded model, don't subtract again
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

    # Check if model is already loaded in VRAM
    model_is_loaded = is_model_loaded(model_name, ollama_base_url)

    # Calculate usable VRAM (after safety margin)
    usable_vram = free_vram_mb - safety_margin_mb

    # Convert model size to MB for calculations
    model_size_mb = model_size_bytes / (1024**2) if model_size_bytes > 0 else 0

    # TWO-SCENARIO LOGIC:
    # Scenario 1: Model NOT loaded → Must subtract model size from free VRAM
    # Scenario 2: Model IS loaded → Free VRAM already reflects loaded model
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
