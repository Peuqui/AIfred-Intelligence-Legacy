"""
Unified Model VRAM Cache Management

Manages a JSON-based cache for VRAM-related measurements across ALL backends
(Ollama, vLLM, TabbyAPI). Combines:
- VRAM ratio measurements (MB/token) - Universal for all backends
- vLLM context calibrations - vLLM-specific

Cache location: ~/.config/aifred/model_vram_cache.json

Structure:
{
    "model_name": {
        "backend": "ollama|vllm|tabbyapi",
        "architecture": "moe|dense",
        "native_context": 262144,
        "gpu_model": "NVIDIA GeForce RTX 3090 Ti",

        "vram_ratio": {
            "measurements": [
                {
                    "context_tokens": 20720,
                    "measured_mb_per_token": 0.0872,
                    "measured_at": "2025-11-22T02:30:00"
                }
            ],
            "avg_mb_per_token": 0.0872
        },

        "vllm_calibrations": [  # Only for vLLM models
            {
                "free_vram_mb": 22968,
                "max_context": 21608,
                "measured_at": "2025-11-21T23:31:17"
            }
        ]
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
CACHE_FILE = CACHE_DIR / "model_vram_cache.json"
OLD_VLLM_CACHE = CACHE_DIR / "vllm_context_cache.json"


def ensure_cache_dir() -> None:
    """Create cache directory if it doesn't exist"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _migrate_old_vllm_cache() -> Dict[str, Any]:
    """
    Migrate old vllm_context_cache.json to new unified format

    Returns:
        Migrated cache dict (empty if no old cache exists)
    """
    if not OLD_VLLM_CACHE.exists():
        return {}

    try:
        with open(OLD_VLLM_CACHE, 'r', encoding='utf-8') as f:
            old_cache = json.load(f)

        logger.info(f"Migrating {len(old_cache)} models from old vLLM cache")

        # Convert old format to new format
        migrated = {}
        for model_id, model_data in old_cache.items():
            migrated[model_id] = {
                "backend": "vllm",  # Old cache was vLLM-only
                "architecture": "unknown",  # Will be detected on next use
                "native_context": model_data.get("native_context", 0),
                "gpu_model": model_data.get("gpu_model", "Unknown"),
                "vllm_calibrations": model_data.get("calibrations", [])
                # No vram_ratio yet - will be populated on first inference
            }

        logger.info(f"✅ Migration complete: {len(migrated)} models")
        return migrated

    except Exception as e:
        logger.error(f"Failed to migrate old vLLM cache: {e}")
        return {}


def load_cache() -> Dict[str, Any]:
    """
    Load unified model VRAM cache from JSON file

    Automatically migrates old vllm_context_cache.json if present.

    Returns:
        Dict with model_name → cache_data mappings
        Empty dict if file doesn't exist or is invalid
    """
    ensure_cache_dir()

    # Try to load new unified cache
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, encoding='utf-8') as f:
                cache: Dict[str, Any] = json.load(f)
            logger.info(f"Loaded unified model cache: {len(cache)} models")
            return cache
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load cache file {CACHE_FILE}: {e}")
            return {}

    # No unified cache - try to migrate old vLLM cache
    migrated = _migrate_old_vllm_cache()
    if migrated:
        # Save migrated cache
        save_cache(migrated)
        logger.info("Migrated old vLLM cache to unified format")

    return migrated


def save_cache(cache: Dict[str, Any]) -> bool:
    """
    Save unified model VRAM cache to JSON file

    Args:
        cache: Dict with model_name → cache_data mappings

    Returns:
        True if successful, False otherwise
    """
    ensure_cache_dir()

    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved unified model cache: {len(cache)} models")
        return True
    except IOError as e:
        logger.error(f"Failed to save cache file {CACHE_FILE}: {e}")
        return False


# ============================================================================
# VRAM RATIO FUNCTIONS (Universal - ALL backends)
# ============================================================================

def add_vram_measurement(
    model_name: str,
    context_tokens: int,
    vram_before_mb: int,
    vram_during_mb: int,
    architecture: str,  # "moe" or "dense"
    backend: str = "ollama"
) -> None:
    """
    Add a VRAM ratio measurement for a model

    Args:
        model_name: Name of the model
        context_tokens: Number of context tokens used
        vram_before_mb: Free VRAM before inference (after model load)
        vram_during_mb: Free VRAM during inference (KV cache allocated)
        architecture: "moe" or "dense"
        backend: "ollama", "vllm", or "tabbyapi"
    """
    # Calculate MB per token from the measurement
    vram_used_by_context = vram_before_mb - vram_during_mb

    # Ignore invalid measurements (negative values = measurement error)
    if vram_used_by_context <= 0 or context_tokens <= 0:
        return

    mb_per_token = vram_used_by_context / context_tokens

    # Load cache
    cache = load_cache()

    # Initialize model entry if not exists
    if model_name not in cache:
        cache[model_name] = {
            "backend": backend,
            "architecture": architecture,
            "native_context": 0,  # Will be updated later
            "gpu_model": "Unknown",  # Will be updated later
            "vram_ratio": {
                "measurements": [],
                "avg_mb_per_token": 0.0
            }
        }

    # Ensure vram_ratio exists (for migrated entries)
    if "vram_ratio" not in cache[model_name]:
        cache[model_name]["vram_ratio"] = {
            "measurements": [],
            "avg_mb_per_token": 0.0
        }

    # Update architecture if different
    cache[model_name]["architecture"] = architecture
    cache[model_name]["backend"] = backend

    # Add measurement
    measurement = {
        "context_tokens": context_tokens,
        "measured_mb_per_token": round(mb_per_token, 4),
        "measured_at": datetime.now().isoformat()
    }
    cache[model_name]["vram_ratio"]["measurements"].append(measurement)

    # Keep only last 10 measurements per model
    if len(cache[model_name]["vram_ratio"]["measurements"]) > 10:
        cache[model_name]["vram_ratio"]["measurements"] = \
            cache[model_name]["vram_ratio"]["measurements"][-10:]

    # Calculate average MB/token from all measurements
    measurements = cache[model_name]["vram_ratio"]["measurements"]
    avg = sum(m["measured_mb_per_token"] for m in measurements) / len(measurements)
    cache[model_name]["vram_ratio"]["avg_mb_per_token"] = round(avg, 4)

    # Save cache
    save_cache(cache)


def get_calibrated_ratio(model_name: str, architecture: str, default_ratio: float) -> float:
    """
    Get calibrated MB/token ratio for a model

    Args:
        model_name: Name of the model
        architecture: "moe" or "dense" (for fallback)
        default_ratio: Default ratio to use if no measurements exist

    Returns:
        Calibrated MB/token ratio, or default if no calibration data
    """
    cache = load_cache()

    if model_name in cache:
        vram_ratio = cache[model_name].get("vram_ratio", {})
        avg = vram_ratio.get("avg_mb_per_token", 0.0)
        if avg > 0:
            return avg

    return default_ratio


def get_measurement_count(model_name: str) -> int:
    """Get number of VRAM ratio measurements for a model"""
    cache = load_cache()
    if model_name in cache:
        vram_ratio = cache[model_name].get("vram_ratio", {})
        return len(vram_ratio.get("measurements", []))
    return 0


def get_ollama_calibrated_max_context(model_name: str) -> Optional[int]:
    """
    Get calibrated max_context_gpu_only for an Ollama model.

    Returns the experimentally measured maximum context that fits in GPU memory
    without CPU offloading. This is more accurate than dynamic VRAM calculation.

    Args:
        model_name: Ollama model name (e.g., "qwen3:30b-a3b-instruct-2507-q8_0")

    Returns:
        Calibrated max context tokens, or None if no calibration exists
    """
    cache = load_cache()

    if model_name not in cache:
        return None

    calibrations = cache[model_name].get("ollama_calibrations", [])
    if not calibrations:
        return None

    # Return the most recent calibration's max_context_gpu_only
    latest = calibrations[-1]
    return latest.get("max_context_gpu_only")


# ============================================================================
# vLLM CALIBRATION FUNCTIONS (vLLM-specific)
# ============================================================================

def get_vllm_calibrations(model_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Get all vLLM calibration points for a model

    Args:
        model_id: The model identifier (e.g., "Qwen/Qwen3-8B-AWQ")

    Returns:
        List of calibration dicts, or None if no calibrations exist
    """
    cache = load_cache()

    if model_id not in cache:
        return None

    return cache[model_id].get("vllm_calibrations", None)


def interpolate_vllm_context(model_id: str, current_vram_mb: int, tolerance_mb: int = 500) -> Optional[int]:
    """
    Get max context for a model at current VRAM level using interpolation

    Args:
        model_id: The model identifier
        current_vram_mb: Current free VRAM in MB
        tolerance_mb: Consider calibration points within ±tolerance_mb as exact matches

    Returns:
        Interpolated max context tokens, or None if insufficient calibration data
    """
    calibrations = get_vllm_calibrations(model_id)

    if not calibrations or len(calibrations) == 0:
        return None

    # Sort calibrations by VRAM (ascending)
    sorted_cal = sorted(calibrations, key=lambda x: x["free_vram_mb"])

    # Check for exact match within tolerance
    for cal in sorted_cal:
        if abs(cal["free_vram_mb"] - current_vram_mb) <= tolerance_mb:
            logger.info(f"Exact match: {cal['free_vram_mb']} MB ≈ {current_vram_mb} MB → {cal['max_context']} tokens")
            return cal["max_context"]

    # Interpolation logic (same as old vllm_context_cache.py)
    if current_vram_mb < sorted_cal[0]["free_vram_mb"]:
        # Below lowest calibration - extrapolate downward
        if len(sorted_cal) >= 2:
            x1, y1 = sorted_cal[0]["free_vram_mb"], sorted_cal[0]["max_context"]
            x2, y2 = sorted_cal[1]["free_vram_mb"], sorted_cal[1]["max_context"]
            slope = (y2 - y1) / (x2 - x1)
            interpolated = int(y1 + slope * (current_vram_mb - x1))
            return max(interpolated, 1024)  # Minimum 1K tokens
        else:
            return sorted_cal[0]["max_context"]

    elif current_vram_mb > sorted_cal[-1]["free_vram_mb"]:
        # Above highest calibration - use highest known value
        return sorted_cal[-1]["max_context"]

    else:
        # Between two calibration points - linear interpolation
        for i in range(len(sorted_cal) - 1):
            x1, y1 = sorted_cal[i]["free_vram_mb"], sorted_cal[i]["max_context"]
            x2, y2 = sorted_cal[i + 1]["free_vram_mb"], sorted_cal[i + 1]["max_context"]

            if x1 <= current_vram_mb <= x2:
                slope = (y2 - y1) / (x2 - x1)
                interpolated = int(y1 + slope * (current_vram_mb - x1))
                logger.info(f"Interpolated: {current_vram_mb} MB → {interpolated} tokens (between {x1} and {x2} MB)")
                return interpolated

    return None


def add_vllm_calibration(
    model_id: str,
    free_vram_mb: int,
    max_context: int,
    native_context: int,
    gpu_model: str,
    architecture: str = "unknown"
) -> bool:
    """
    Add a new vLLM calibration point for a model

    Args:
        model_id: The model identifier
        free_vram_mb: Free VRAM in MB when this context was measured
        max_context: Maximum context tokens at this VRAM level
        native_context: Model's native/architectural context limit
        gpu_model: GPU model name (e.g., "NVIDIA GeForce RTX 3090 Ti")
        architecture: "moe", "dense", or "unknown"

    Returns:
        True if successfully added, False otherwise
    """
    cache = load_cache()

    # Initialize model entry if not exists
    if model_id not in cache:
        cache[model_id] = {
            "backend": "vllm",
            "architecture": architecture,
            "native_context": native_context,
            "gpu_model": gpu_model,
            "vllm_calibrations": []
        }

    # Ensure vllm_calibrations exists (for Ollama models)
    if "vllm_calibrations" not in cache[model_id]:
        cache[model_id]["vllm_calibrations"] = []

    # Update metadata
    cache[model_id]["native_context"] = native_context
    cache[model_id]["gpu_model"] = gpu_model
    if architecture != "unknown":
        cache[model_id]["architecture"] = architecture

    # Add calibration point
    calibration = {
        "free_vram_mb": free_vram_mb,
        "max_context": max_context,
        "measured_at": datetime.now().isoformat()
    }

    cache[model_id]["vllm_calibrations"].append(calibration)

    # Save and return result
    return save_cache(cache)


def add_koboldcpp_calibration(
    model_id: str,
    free_vram_mb: int,
    max_context: int,
    quantization: str,
    gpu_model: str,
    model_size_gb: float
) -> bool:
    """
    Add a new KoboldCPP calibration point for a GGUF model

    Args:
        model_id: The model identifier (e.g., "bartowski/Qwen3-30B-Instruct-2507-GGUF (Q4_K_M)")
        free_vram_mb: Free VRAM in MB when this context was measured
        max_context: Maximum context tokens at this VRAM level
        quantization: Quantization level (Q4_K_M, Q5_K_S, Q8_0, etc.)
        gpu_model: GPU model name (e.g., "NVIDIA GeForce RTX 3090 Ti")
        model_size_gb: GGUF file size in GB

    Returns:
        True if successfully added, False otherwise
    """
    cache = load_cache()

    # Initialize model entry if not exists
    if model_id not in cache:
        cache[model_id] = {
            "backend": "koboldcpp",
            "quantization": quantization,
            "model_size_gb": model_size_gb,
            "gpu_model": gpu_model,
            "koboldcpp_calibrations": []
        }

    # Ensure koboldcpp_calibrations exists
    if "koboldcpp_calibrations" not in cache[model_id]:
        cache[model_id]["koboldcpp_calibrations"] = []

    # Update metadata
    cache[model_id]["quantization"] = quantization
    cache[model_id]["model_size_gb"] = model_size_gb
    cache[model_id]["gpu_model"] = gpu_model

    # Add calibration point
    calibration = {
        "free_vram_mb": free_vram_mb,
        "max_context": max_context,
        "measured_at": datetime.now().isoformat()
    }

    cache[model_id]["koboldcpp_calibrations"].append(calibration)

    # Save and return result
    return save_cache(cache)


def get_koboldcpp_calibrations(model_id: str) -> List[Dict[str, Any]]:
    """
    Get all KoboldCPP calibration points for a model

    Args:
        model_id: The model identifier

    Returns:
        List of calibration dicts, sorted by free_vram_mb (descending)
    """
    cache = load_cache()

    if model_id not in cache:
        return []

    calibrations = cache[model_id].get("koboldcpp_calibrations", [])

    # Sort by free_vram_mb (most VRAM first)
    return sorted(calibrations, key=lambda c: c["free_vram_mb"], reverse=True)


def interpolate_koboldcpp_context(
    model_id: str,
    current_free_vram_mb: int
) -> Optional[int]:
    """
    Interpolate maximum context size based on calibration points

    Similar to vLLM interpolation, but for KoboldCPP GGUF models.

    IMPORTANT: Calibrated contexts already have RoPE scaling applied during calibration.
    No need to apply RoPE factor again during interpolation.

    Args:
        model_id: The model identifier
        current_free_vram_mb: Current free VRAM in MB

    Returns:
        Estimated max context tokens, or None if no calibration data
    """
    calibrations = get_koboldcpp_calibrations(model_id)

    if not calibrations:
        return None

    # If we have exact match (within 100MB), use it
    for cal in calibrations:
        if abs(cal["free_vram_mb"] - current_free_vram_mb) < 100:
            logger.info(
                f"📊 Exact cache match for {model_id}: "
                f"{cal['max_context']:,} tokens @ {cal['free_vram_mb']:,}MB VRAM"
            )
            return cal["max_context"]

    # Find bracketing points for interpolation
    lower_cal = None  # Less VRAM, smaller context
    upper_cal = None  # More VRAM, larger context

    for cal in calibrations:
        if cal["free_vram_mb"] <= current_free_vram_mb:
            if lower_cal is None or cal["free_vram_mb"] > lower_cal["free_vram_mb"]:
                lower_cal = cal
        if cal["free_vram_mb"] >= current_free_vram_mb:
            if upper_cal is None or cal["free_vram_mb"] < upper_cal["free_vram_mb"]:
                upper_cal = cal

    # Case 1: We have bracketing points - interpolate
    if lower_cal and upper_cal and lower_cal != upper_cal:
        vram_range = upper_cal["free_vram_mb"] - lower_cal["free_vram_mb"]
        context_range = upper_cal["max_context"] - lower_cal["max_context"]
        vram_offset = current_free_vram_mb - lower_cal["free_vram_mb"]

        interpolated_context = lower_cal["max_context"] + int(
            (vram_offset / vram_range) * context_range
        )

        logger.info(
            f"📊 Interpolated context for {model_id}: {interpolated_context:,} tokens\n"
            f"   Lower: {lower_cal['max_context']:,} @ {lower_cal['free_vram_mb']:,}MB\n"
            f"   Upper: {upper_cal['max_context']:,} @ {upper_cal['free_vram_mb']:,}MB\n"
            f"   Current: {current_free_vram_mb:,}MB VRAM"
        )

        return interpolated_context

    # Case 2: Extrapolate down (less VRAM than any calibration)
    if upper_cal and not lower_cal:
        # Conservative: Scale down proportionally
        vram_ratio = current_free_vram_mb / upper_cal["free_vram_mb"]
        extrapolated = int(upper_cal["max_context"] * vram_ratio * 0.9)  # 10% safety margin

        logger.info(
            f"📊 Extrapolated DOWN for {model_id}: {extrapolated:,} tokens\n"
            f"   Reference: {upper_cal['max_context']:,} @ {upper_cal['free_vram_mb']:,}MB\n"
            f"   Current: {current_free_vram_mb:,}MB VRAM (less than calibrated)"
        )

        return extrapolated

    # Case 3: Extrapolate up (more VRAM than any calibration)
    if lower_cal and not upper_cal:
        # Conservative: Use calibration point + small increase
        vram_increase = current_free_vram_mb - lower_cal["free_vram_mb"]

        # Estimate MB/token from calibration (rough approximation)
        cache = load_cache()
        quantization = cache.get(model_id, {}).get("quantization", "Q4")

        mb_per_token = {
            "Q4": 0.15,
            "Q5": 0.18,
            "Q8": 0.30,
            "IQ4": 0.15,
            "IQ3": 0.12,
        }

        quant_level = "Q4"  # Default
        for key in mb_per_token.keys():
            if key in quantization:
                quant_level = key
                break

        additional_tokens = int(vram_increase / mb_per_token[quant_level])
        extrapolated = lower_cal["max_context"] + additional_tokens

        logger.info(
            f"📊 Extrapolated UP for {model_id}: {extrapolated:,} tokens\n"
            f"   Reference: {lower_cal['max_context']:,} @ {lower_cal['free_vram_mb']:,}MB\n"
            f"   Current: {current_free_vram_mb:,}MB VRAM (+{vram_increase:,}MB)\n"
            f"   Added: {additional_tokens:,} tokens ({quant_level} @ {mb_per_token[quant_level]} MB/tok)"
        )

        return extrapolated

    # Case 4: Single calibration point - use it
    if lower_cal:
        logger.info(
            f"📊 Using single calibration point for {model_id}: "
            f"{lower_cal['max_context']:,} tokens"
        )
        return lower_cal["max_context"]

    return None


def delete_cached_model(model_id: str) -> bool:
    """Delete all cache data for a specific model"""
    cache = load_cache()

    if model_id in cache:
        del cache[model_id]
        return save_cache(cache)

    return False


def clear_cache() -> bool:
    """Clear entire cache (delete all models)"""
    return save_cache({})


def get_cached_context(model_id: str) -> Optional[Dict[str, Any]]:
    """Get all cached data for a model"""
    cache = load_cache()
    return cache.get(model_id, None)
