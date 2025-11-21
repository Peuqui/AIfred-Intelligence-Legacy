"""
vLLM Context Cache Management with Interpolation

Manages a JSON-based lookup table that stores measured context limits
for different vLLM models at different VRAM levels. This eliminates the
need for trial-and-error context calculation on every startup and supports
linear interpolation between calibration points.

Cache location: ~/.config/aifred/vllm_context_cache.json

Structure:
{
    "model_id": {
        "calibrations": [
            {
                "free_vram_mb": 300,
                "max_context": 3296,
                "measured_at": "2025-01-21T19:30:00"
            },
            {
                "free_vram_mb": 22500,
                "max_context": 17654,
                "measured_at": "2025-01-21T20:15:00"
            }
        ],
        "native_context": 131072,
        "gpu_model": "NVIDIA GeForce RTX 3090 Ti"
    }
}
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

# Cache file location (same directory as settings.json)
CACHE_DIR = Path.home() / ".config" / "aifred"
CACHE_FILE = CACHE_DIR / "vllm_context_cache.json"


def ensure_cache_dir() -> None:
    """Create cache directory if it doesn't exist"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_cache() -> Dict[str, Any]:
    """
    Load vLLM context cache from JSON file

    Returns:
        Dict with model_id → context_info mappings
        Empty dict if file doesn't exist or is invalid
    """
    ensure_cache_dir()

    if not CACHE_FILE.exists():
        logger.info(f"Cache file not found: {CACHE_FILE}")
        return {}

    try:
        with open(CACHE_FILE, encoding='utf-8') as f:
            cache: Dict[str, Any] = json.load(f)
        logger.info(f"Loaded vLLM context cache: {len(cache)} models")
        return cache
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load cache file {CACHE_FILE}: {e}")
        return {}


def save_cache(cache: Dict[str, Any]) -> bool:
    """
    Save vLLM context cache to JSON file

    Args:
        cache: Dict with model_id → context_info mappings

    Returns:
        True if successful, False otherwise
    """
    ensure_cache_dir()

    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved vLLM context cache: {len(cache)} models")
        return True
    except IOError as e:
        logger.error(f"Failed to save cache file {CACHE_FILE}: {e}")
        return False


def get_calibrations(model_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Get all calibration points for a model

    Args:
        model_id: Model identifier (e.g., "cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit")

    Returns:
        List of calibration points (sorted by free_vram_mb), or None if no cache

    Example return value:
        [
            {"free_vram_mb": 300, "max_context": 3296, "measured_at": "2025-01-21T19:30:00"},
            {"free_vram_mb": 22500, "max_context": 17654, "measured_at": "2025-01-21T20:15:00"}
        ]
    """
    cache = load_cache()
    entry = cache.get(model_id)

    if not entry:
        logger.info(f"No cache entry for {model_id}")
        return None

    calibrations = entry.get("calibrations", [])

    if not calibrations:
        logger.info(f"No calibration points for {model_id}")
        return None

    # Sort by free VRAM (ascending)
    calibrations_sorted = sorted(calibrations, key=lambda x: x["free_vram_mb"])
    logger.info(f"Found {len(calibrations_sorted)} calibration points for {model_id}")

    return calibrations_sorted


def interpolate_context(model_id: str, current_vram_mb: int, tolerance_mb: int = 500) -> Optional[int]:
    """
    Interpolate max context based on current VRAM and cached calibrations

    Args:
        model_id: Model identifier
        current_vram_mb: Currently available VRAM in MB
        tolerance_mb: Exact match tolerance (default: ±500MB)

    Returns:
        Estimated max_context tokens, or None if interpolation not possible

    Logic:
        1. Find exact match within tolerance → return that value
        2. Find two surrounding calibration points → linear interpolation
        3. Outside calibration range → return None (need new calibration)
    """
    calibrations = get_calibrations(model_id)

    if not calibrations:
        logger.info(f"No calibrations for {model_id} - cannot interpolate")
        return None

    # Check for exact match (within tolerance)
    for cal in calibrations:
        vram_diff = abs(cal["free_vram_mb"] - current_vram_mb)
        if vram_diff <= tolerance_mb:
            max_ctx: int = cal["max_context"]
            logger.info(
                f"Exact match: {current_vram_mb}MB ≈ {cal['free_vram_mb']}MB "
                f"(Δ={vram_diff}MB) → {max_ctx:,} tokens"
            )
            return max_ctx

    # Find surrounding calibration points for interpolation
    lower = None
    upper = None

    for cal in calibrations:
        if cal["free_vram_mb"] <= current_vram_mb:
            lower = cal  # Keep updating to get the highest one below
        elif cal["free_vram_mb"] > current_vram_mb and upper is None:
            upper = cal  # First one above
            break

    # Need both lower and upper for interpolation
    if lower and upper:
        # Linear interpolation
        vram_range = upper["free_vram_mb"] - lower["free_vram_mb"]
        vram_offset = current_vram_mb - lower["free_vram_mb"]
        ratio = vram_offset / vram_range

        context_range = upper["max_context"] - lower["max_context"]
        estimated_context = int(lower["max_context"] + ratio * context_range)

        logger.info(
            f"Interpolation: {lower['free_vram_mb']}MB ({lower['max_context']:,} tok) "
            f"← {current_vram_mb}MB → "
            f"{upper['free_vram_mb']}MB ({upper['max_context']:,} tok) "
            f"= {estimated_context:,} tokens (ratio={ratio:.2f})"
        )

        return estimated_context

    # Outside calibration range
    if not lower:
        logger.info(f"Current VRAM ({current_vram_mb}MB) below all calibrations - need new measurement")
    elif not upper:
        logger.info(f"Current VRAM ({current_vram_mb}MB) above all calibrations - need new measurement")

    return None


def add_calibration_point(
    model_id: str,
    free_vram_mb: int,
    max_context: int,
    native_context: int,
    gpu_model: str
) -> bool:
    """
    Add a new calibration point to the cache

    Args:
        model_id: Model identifier
        free_vram_mb: Free VRAM at time of measurement
        max_context: Maximum practical context (measured from vLLM)
        native_context: Native model context limit (from config.json)
        gpu_model: GPU model name (e.g., "NVIDIA GeForce RTX 3090 Ti")

    Returns:
        True if successful, False otherwise
    """
    cache = load_cache()

    # Create new calibration point
    new_calibration = {
        "free_vram_mb": free_vram_mb,
        "max_context": max_context,
        "measured_at": datetime.now().isoformat(timespec='seconds')
    }

    # Get or create model entry
    if model_id not in cache:
        cache[model_id] = {
            "calibrations": [],
            "native_context": native_context,
            "gpu_model": gpu_model
        }

    # Check if this VRAM level already exists (update instead of duplicate)
    calibrations = cache[model_id]["calibrations"]
    updated = False

    for i, cal in enumerate(calibrations):
        if abs(cal["free_vram_mb"] - free_vram_mb) <= 500:  # ±500MB tolerance
            logger.info(
                f"Updating existing calibration point for {model_id} at {free_vram_mb}MB "
                f"(old: {cal['max_context']:,} → new: {max_context:,} tokens)"
            )
            calibrations[i] = new_calibration
            updated = True
            break

    if not updated:
        logger.info(
            f"Adding new calibration point for {model_id}: "
            f"{free_vram_mb}MB VRAM → {max_context:,} tokens"
        )
        calibrations.append(new_calibration)

    cache[model_id]["calibrations"] = calibrations

    return save_cache(cache)


def delete_cached_model(model_id: str) -> bool:
    """
    Delete a model from cache (useful for re-calibration)

    Args:
        model_id: Model identifier to remove

    Returns:
        True if deleted, False if not found or error
    """
    cache = load_cache()

    if model_id not in cache:
        logger.warning(f"Model {model_id} not in cache")
        return False

    del cache[model_id]
    logger.info(f"Deleted {model_id} from cache")

    return save_cache(cache)


def clear_cache() -> bool:
    """
    Clear entire cache (delete all entries)

    Returns:
        True if successful
    """
    logger.info("Clearing entire vLLM context cache")
    return save_cache({})


# Backward compatibility - keep old function signature
def save_context_measurement(
    model_id: str,
    max_context: int,
    native_context: int,
    gpu_model: str,
    vram_total_mb: int,
    model_size_mb: int,
    vram_context_ratio: float = 0.097
) -> bool:
    """
    Legacy function - converts to new calibration point format

    Calculates free_vram_mb and calls add_calibration_point()
    """
    # Estimate free VRAM (total - model size - some overhead)
    free_vram_mb = vram_total_mb - model_size_mb

    return add_calibration_point(
        model_id=model_id,
        free_vram_mb=free_vram_mb,
        max_context=max_context,
        native_context=native_context,
        gpu_model=gpu_model
    )


def get_cached_context(model_id: str) -> Optional[Dict[str, Any]]:
    """
    Legacy function - returns first calibration point for backward compatibility

    New code should use get_calibrations() and interpolate_context()
    """
    calibrations = get_calibrations(model_id)

    if not calibrations:
        return None

    # Return the calibration with most VRAM (likely highest context)
    best = max(calibrations, key=lambda x: x["free_vram_mb"])

    cache = load_cache()
    entry = cache.get(model_id, {})

    return {
        "max_context": best["max_context"],
        "native_context": entry.get("native_context", 0),
        "measured_at": best["measured_at"],
        "gpu_model": entry.get("gpu_model", "Unknown")
    }
