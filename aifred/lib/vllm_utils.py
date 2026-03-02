"""
vLLM Utility Functions

Helper functions for vLLM-specific operations like VRAM change detection
and context limit recommendations.
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def check_vram_change_for_vllm(
    model_id: str,
    gpu_indices: Optional[list[int]] = None
) -> Optional[Tuple[int, int, int, Optional[int], Optional[int]]]:
    """
    Check if VRAM has changed significantly since last vLLM calibration

    Args:
        model_id: Model identifier (e.g., "cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit")
        gpu_indices: GPU indices that vLLM uses (None = GPU 0 only)

    Returns:
        Tuple of (vram_diff_mb, current_vram_mb, cached_vram_mb, potential_tokens, current_tokens)
        or None if:
        - No GPU available
        - No cached calibration exists
        - VRAM difference < 3GB (not significant)

    Example:
        result = check_vram_change_for_vllm("cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit")
        if result:
            vram_diff, current_vram, cached_vram, potential_tokens, current_tokens = result
            print(f"VRAM increased by {vram_diff}MB")
    """
    # Query current free VRAM using centralized gpu_utils function
    from .gpu_utils import get_free_vram_for_single_gpu

    indices = gpu_indices if gpu_indices is not None else [0]
    current_vram_mb = 0
    for idx in indices:
        vram = get_free_vram_for_single_gpu(gpu_index=idx)
        if vram is not None:
            current_vram_mb += vram
    if current_vram_mb == 0:
        logger.warning("Could not query GPU VRAM")
        return None

    # Get cached calibration points for this model
    from .model_vram_cache import get_vllm_calibrations as get_calibrations

    calibrations = get_calibrations(model_id)
    if not calibrations:
        logger.debug(f"No calibrations found for {model_id} - cannot detect VRAM change")
        return None

    # Find calibration point closest to current VRAM
    # We use the most recent calibration (last in sorted list)
    cached_calibration = calibrations[-1]
    cached_vram_mb = cached_calibration["free_vram_mb"]
    current_tokens = cached_calibration["max_context"]

    # Calculate VRAM difference
    vram_diff_mb = int(current_vram_mb - cached_vram_mb)

    # Only report if POSITIVE difference is significant (>3GB increase)
    # Negative changes (VRAM decrease) should not trigger warnings
    if vram_diff_mb < 3000:
        if vram_diff_mb < 0:
            logger.debug(f"VRAM decreased by {abs(vram_diff_mb)}MB - no warning needed")
        else:
            logger.debug(f"VRAM change not significant: {vram_diff_mb}MB (< 3GB threshold)")
        return None

    # Estimate potential tokens with new VRAM
    # Try interpolation first, then fallback to None
    from .model_vram_cache import interpolate_vllm_context as interpolate_context

    potential_tokens = interpolate_context(model_id, int(current_vram_mb))

    logger.info(
        f"VRAM change detected for {model_id}: "
        f"{vram_diff_mb:+.0f}MB "
        f"(cached: {cached_vram_mb:.0f}MB → current: {current_vram_mb:.0f}MB)"
    )

    if potential_tokens:
        logger.info(
            f"Token potential: {current_tokens:,} → ~{potential_tokens:,} tokens "
            f"({potential_tokens - current_tokens:+,})"
        )

    return (
        vram_diff_mb,
        int(current_vram_mb),
        int(cached_vram_mb),
        potential_tokens,
        current_tokens
    )
