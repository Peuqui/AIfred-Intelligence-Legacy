"""
GPU Utilities - VRAM Detection and Context Calculation

Provides functions to query free VRAM and calculate practical context limits
based on available GPU memory.
"""

import logging
import httpx
from typing import Optional, Dict, List
from .config import (
    VRAM_SAFETY_MARGIN,
    VRAM_CONTEXT_RATIO_DENSE,
    VRAM_CONTEXT_RATIO_MOE,
    ENABLE_VRAM_CONTEXT_CALCULATION,
    KOBOLDCPP_QUANTKV
)
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

    For multi-GPU systems, returns the SUM of free VRAM across ALL GPUs.
    This matches KoboldCPP's behavior which can utilize multiple GPUs.

    Returns:
        int: Total free VRAM in MB (summed across all GPUs), or None if GPU unavailable
    """
    try:
        import pynvml
        pynvml.nvmlInit()

        # Get number of GPUs
        device_count = pynvml.nvmlDeviceGetCount()

        # Sum free VRAM across all GPUs
        total_free_mb = 0
        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            free_mb = mem_info.free / (1024 * 1024)
            total_free_mb += free_mb

            # Log per-GPU VRAM for debugging
            if device_count > 1:
                gpu_name = pynvml.nvmlDeviceGetName(handle)
                logger.debug(f"   GPU {i} ({gpu_name}): {int(free_mb)} MB free")

        pynvml.nvmlShutdown()

        if device_count > 1:
            logger.debug(f"   Total free VRAM (sum of {device_count} GPUs): {int(total_free_mb)} MB")

        return int(total_free_mb)

    except ImportError:
        logger.warning("pynvml not installed - install via: pip install pynvml")
        return None
    except Exception as e:
        logger.debug(f"Could not query GPU via pynvml: {e}")
        return None


async def is_moe_model(model_name: str, ollama_url: str = "http://localhost:11434") -> bool:
    """
    Detect if model is MoE (Mixture of Experts) architecture

    Queries Ollama's /api/show endpoint to read model architecture from config.
    MoE models have lower VRAM per token (0.10) vs Dense models (0.15).

    Args:
        model_name: Model name in Ollama (e.g., "qwen3:30b-a3b-instruct-2507-q4_K_M")
        ollama_url: Ollama API base URL

    Returns:
        bool: True if MoE model, False if Dense or unknown

    Examples:
        - MoE: "qwen3moe" family → 0.10 MB/token (48% more context)
        - Dense: "qwen3", "llama" family → 0.15 MB/token (safe for all)
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{ollama_url}/api/show",
                json={"name": model_name}
            )

            if response.status_code == 200:
                data = response.json()

                # Check "family" field in details
                family = data.get("details", {}).get("family", "")

                # MoE indicators: "qwen3moe", "mixtral", "deepseek-moe", etc.
                moe_families = ["moe", "mixtral", "qwen3moe", "deepseek-moe"]

                is_moe = any(indicator in family.lower() for indicator in moe_families)

                if is_moe:
                    logger.debug(f"✅ MoE detected: {model_name} (family: {family})")
                else:
                    logger.debug(f"📊 Dense model: {model_name} (family: {family})")

                return is_moe
            else:
                logger.warning(f"Could not query model info for {model_name}: {response.status_code}")
                return False

    except Exception as e:
        logger.debug(f"MoE detection failed for {model_name}: {e}")
        return False  # Default to Dense (safer)


def measure_vram_during_inference(
    context_tokens: int,
    vram_before_mb: int
) -> Optional[Dict]:
    """
    Measure VRAM usage during inference to calibrate MB/token ratio

    Args:
        context_tokens: Number of context tokens used in this inference
        vram_before_mb: Free VRAM before inference started (baseline)

    Returns:
        Dict with measurement data:
        {
            "vram_during_mb": int,           # Free VRAM during inference
            "vram_used_by_context": int,     # VRAM consumed by KV cache
            "measured_mb_per_token": float   # Calculated MB/token ratio
        }
        or None if measurement failed
    """
    vram_during_mb = get_free_vram_mb()

    if vram_during_mb is None or vram_before_mb is None:
        return None

    # Calculate VRAM used by context (KV cache)
    vram_used_by_context = vram_before_mb - vram_during_mb

    # Ignore invalid measurements (negative = measurement error or noise)
    if vram_used_by_context <= 0 or context_tokens <= 0:
        return None

    # Calculate MB/token from this measurement
    measured_mb_per_token = vram_used_by_context / context_tokens

    return {
        "vram_during_mb": vram_during_mb,
        "vram_used_by_context": vram_used_by_context,
        "measured_mb_per_token": round(measured_mb_per_token, 4)
    }


def get_model_size_from_cache(model_name: str) -> int:
    """
    Get model size in bytes from HuggingFace cache

    Args:
        model_name: Model name (e.g., "cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit")

    Returns:
        int: Model size in bytes, or 0 if not found
    """
    from pathlib import Path

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


async def calculate_vram_based_context(
    model_name: str,
    model_size_bytes: int,
    model_context_limit: int,
    vram_context_ratio: float | None = None,
    safety_margin_mb: int = VRAM_SAFETY_MARGIN,
    model_is_loaded: bool = False,
    backend_type: str = "ollama",
    backend = None  # Backend instance for unloading models (Ollama only)
) -> tuple[int, list[str]]:
    """
    Calculate maximum practical context window based on available VRAM

    UNIVERSAL FUNCTION FOR ALL BACKENDS (Ollama, vLLM, TabbyAPI)

    Args:
        model_name: Name of the model (for MoE detection and logging)
        model_size_bytes: Model size in bytes (from HF cache or Ollama blobs)
        model_context_limit: Model's architectural context limit (from config.json)
        vram_context_ratio: MB of VRAM per context token (default: auto-detect via MoE)
        safety_margin_mb: MB to reserve for system (default: 512 MB from config)
        model_is_loaded: Whether model is already loaded in VRAM (affects calculation)
        backend_type: Backend type ("ollama", "vllm", "tabbyapi") for MoE detection

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

    # Auto-detect VRAM context ratio if not provided
    if vram_context_ratio is None:
        # Only detect MoE for Ollama (vLLM/TabbyAPI use manual override)
        if backend_type == "ollama":
            is_moe = await is_moe_model(model_name)
            architecture = "moe" if is_moe else "dense"
            default_ratio = VRAM_CONTEXT_RATIO_MOE if is_moe else VRAM_CONTEXT_RATIO_DENSE

            # Try to get calibrated ratio from unified cache
            from .model_vram_cache import get_calibrated_ratio, get_measurement_count
            vram_context_ratio = get_calibrated_ratio(model_name, architecture, default_ratio)

            # Show whether using calibrated or default ratio
            measurement_count = get_measurement_count(model_name)
            if measurement_count > 0:
                model_type = "MoE (calibrated)" if is_moe else "Dense (calibrated)"
                debug_msgs.append(f"🔍 {model_type} → {vram_context_ratio:.4f} MB/token ({measurement_count} measurements)")
            else:
                model_type = "MoE" if is_moe else "Dense"
                debug_msgs.append(f"🔍 {model_type} detected → {vram_context_ratio:.2f} MB/token")
        else:
            # For vLLM/TabbyAPI: Default to Dense (safer)
            vram_context_ratio = VRAM_CONTEXT_RATIO_DENSE

    # Check if VRAM calculation is enabled
    if not ENABLE_VRAM_CONTEXT_CALCULATION:
        logger.debug("VRAM context calculation disabled in config")
        return model_context_limit, []

    # Query free VRAM immediately (no stabilization wait)
    # REMOVED: 3-second VRAM stabilization loop - unnecessary overhead
    free_vram_mb = get_free_vram_mb()

    if free_vram_mb is None:
        # Fallback: Use architectural limit
        msg = (
            "⚠️ VRAM query failed (CPU-only or nvidia-smi unavailable), "
            "using model's architectural limit"
        )
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
        msg1 = f"💾 Model loaded → {format_number(vram_for_context, 0)} MB for context"
        msg2 = f"   ({format_number(free_vram_mb)} MB free - {format_number(safety_margin_mb)} MB margin)"
        debug_msgs.append(msg1)
        debug_msgs.append(msg2)
    else:
        # Model NOT loaded - must subtract its size from available VRAM
        vram_for_context_calc = int(usable_vram - model_size_mb)

        # Special case: Negative value indicates another model is still loaded
        # This is a FALLBACK - normally models are unloaded in calculate_practical_context()
        # before this function is called. This code path should rarely execute.
        if vram_for_context_calc < 0:
            msg = "⚠️ Anderes Modell noch geladen → Entlade alle Modelle..."
            debug_msgs.append(msg)

            # Unload all models if backend available (Ollama only)
            if backend and hasattr(backend, 'unload_all_models'):
                success, unloaded = await backend.unload_all_models()
                if success and unloaded:
                    msg = f"✅ Entladen: {', '.join(unloaded)}"
                    debug_msgs.append(msg)

                    # Wait 2 seconds for VRAM to be released
                    import asyncio
                    await asyncio.sleep(2.0)

                    free_vram_mb = get_free_vram_mb()
                    if free_vram_mb is None:
                        msg = "⚠️ VRAM-Abfrage fehlgeschlagen → Minimaler Fallback"
                        debug_msgs.append(msg)
                        return 2048, debug_msgs
                    usable_vram = free_vram_mb - safety_margin_mb
                    vram_for_context = int(usable_vram - model_size_mb)

                    msg1 = f"💾 Model NOT loaded → {format_number(vram_for_context, 0)} MB for context"
                    msg2 = f"   ({format_number(free_vram_mb)} MB - {format_number(model_size_mb, 0)} MB model - {format_number(safety_margin_mb)} MB margin)"
                    debug_msgs.append(msg1)
                    debug_msgs.append(msg2)
                else:
                    msg = "⚠️ Entladen fehlgeschlagen → Minimaler Fallback"
                    debug_msgs.append(msg)
                    return 2048, debug_msgs
            else:
                msg = "⚠️ Kein Backend verfügbar → Minimaler Fallback"
                debug_msgs.append(msg)
                return 2048, debug_msgs
        else:
            vram_for_context = vram_for_context_calc
            msg1 = f"💾 Model NOT loaded → {format_number(vram_for_context, 0)} MB for context"
            msg2 = f"   ({format_number(free_vram_mb)} MB - {format_number(model_size_mb, 0)} MB model - {format_number(safety_margin_mb)} MB margin)"
            debug_msgs.append(msg1)
            debug_msgs.append(msg2)

    if vram_for_context < 100:
        msg = f"❌ Insufficient VRAM for context: {format_number(vram_for_context, 0)} MB (< 100 MB minimum) → Fallback 2.048"
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
    debug_msgs.append(msg)

    return final_num_ctx, debug_msgs


# ===================================================================
# KoboldCPP GPU Configuration Detection
# ===================================================================

def detect_gpu_vendor() -> str:
    """
    Detect GPU vendor (NVIDIA, AMD, or CPU-only)

    Returns:
        "nvidia", "amd", or "cpu"
    """
    try:
        import pynvml
        pynvml.nvmlInit()
        pynvml.nvmlShutdown()
        return "nvidia"
    except Exception:
        pass

    # Try AMD ROCm detection
    try:
        import subprocess
        result = subprocess.run(
            ["rocm-smi", "--showproductname"],
            capture_output=True,
            text=True,
            timeout=2.0
        )
        if result.returncode == 0:
            return "amd"
    except Exception:
        pass

    return "cpu"


def get_gpu_count() -> int:
    """
    Get number of available GPUs

    Returns:
        Number of GPUs (0 if CPU-only)
    """
    try:
        import pynvml
        pynvml.nvmlInit()
        count: int = pynvml.nvmlDeviceGetCount()
        pynvml.nvmlShutdown()
        return count
    except Exception:
        return 0


def get_gpu_names() -> list[str]:
    """
    Get list of GPU names

    Returns:
        List of GPU names (e.g., ["NVIDIA GeForce RTX 3090 Ti", "NVIDIA GeForce RTX 3090 Ti"])
    """
    names = []
    try:
        import pynvml
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        for i in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode('utf-8')
            names.append(name)
        pynvml.nvmlShutdown()
    except Exception:
        pass

    return names


def get_gpu_vram_per_gpu() -> list[int]:
    """
    Get VRAM size for each GPU in MB

    Returns:
        List of VRAM sizes in MB (e.g., [24564, 24564] for dual P40)
    """
    vram_sizes = []
    try:
        import pynvml
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        for i in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            vram_mb = mem_info.total / (1024 * 1024)
            vram_sizes.append(int(vram_mb))
        pynvml.nvmlShutdown()
    except Exception:
        pass

    return vram_sizes


def detect_koboldcpp_gpu_config() -> Dict:
    """
    Detect GPU configuration and return KoboldCPP config template

    Returns:
        Dict with KoboldCPP configuration:
        {
            "type": "rtx" | "dual_p40" | "amd_rocm" | "cpu",
            "description": "RTX 3090 Ti (Single GPU)" | "2x Tesla P40 (Context-Offload)" | etc.,
            "gpu_count": 1 | 2,
            "gpu_names": ["NVIDIA GeForce RTX 3090 Ti"],
            "gpu_vram_mb": [24564],
            "total_vram_mb": 24564,
            "config": {
                "gpu_layers": -1 | 40,
                "context_offload": True | False,
                "tensor_split": "1,0" | None,
                "flash_attention": True | False,
                "quantized_kv": True | False,
                "use_cublas": True | False,
                "cublas_args": None | "mmq"
            }
        }
    """
    vendor = detect_gpu_vendor()

    if vendor == "cpu":
        return {
            "type": "cpu",
            "description": "CPU-only (No GPU acceleration)",
            "gpu_count": 0,
            "gpu_names": [],
            "gpu_vram_mb": [],
            "total_vram_mb": 0,
            "config": {
                "gpu_layers": 0,
                "context_offload": False,
                "tensor_split": None,
                "flash_attention": False,
                "quantized_kv": False,
                "quantkv": 0,  # No KV quantization for CPU
                "use_cublas": False,
                "cublas_args": None
            }
        }

    if vendor == "amd":
        gpu_count = 1  # Simplified: assume 1 AMD GPU
        return {
            "type": "amd_rocm",
            "description": "AMD GPU (ROCm)",
            "gpu_count": gpu_count,
            "gpu_names": ["AMD GPU (ROCm)"],
            "gpu_vram_mb": [0],  # Unknown without rocm-smi parsing
            "total_vram_mb": 0,
            "config": {
                "gpu_layers": -1,  # All layers
                "context_offload": False,
                "tensor_split": None,
                "flash_attention": True,
                "quantized_kv": True,
                "quantkv": 2,  # Q4 for single GPU (safe)
                "use_cublas": True,
                "cublas_args": "mmq"  # AMD-specific optimized kernels
            }
        }

    # NVIDIA GPUs
    gpu_count = get_gpu_count()
    gpu_names = get_gpu_names()
    gpu_vram = get_gpu_vram_per_gpu()
    total_vram = sum(gpu_vram) if gpu_vram else 0

    # Dual GPU detection
    if gpu_count == 2:
        # Check if both GPUs are Tesla P40
        is_dual_p40 = all("P40" in name for name in gpu_names)

        if is_dual_p40:
            # Default config for dual P40 (can be overridden dynamically by single-GPU check)
            return {
                "type": "dual_p40",
                "description": "2x Tesla P40 (Automatic Distribution)",
                "gpu_count": 2,
                "gpu_names": gpu_names,
                "gpu_vram_mb": gpu_vram,
                "total_vram_mb": total_vram,
                "single_gpu_vram_mb": gpu_vram[0] if gpu_vram else 0,  # For single-GPU decision
                "config": {
                    "gpu_layers": -1,           # All layers on GPU (distributed automatically)
                    "context_offload": False,   # Not supported by KoboldCPP (uses auto-distribution)
                    "tensor_split": None,       # Let KoboldCPP auto-distribute (50/50) - overridable
                    "flash_attention": True,    # P40 supports Flash Attention (Compute Capability 6.1)
                    "quantized_kv": True,       # Enable KV cache quantization
                    "quantkv": KOBOLDCPP_QUANTKV,  # Use config value (1=Q8 for multi-GPU stability)
                    "use_cublas": True,
                    "cublas_args": None
                }
            }

    # Single GPU or generic dual GPU (RTX config)
    # For single GPU, quantkv=2 is safe. For multi-GPU, use config default.
    quantkv_value = 2 if gpu_count == 1 else KOBOLDCPP_QUANTKV
    return {
        "type": "rtx",
        "description": f"{gpu_names[0] if gpu_names else 'NVIDIA GPU'} (Single GPU)" if gpu_count == 1 else f"{gpu_count}x {gpu_names[0]} (Generic)",
        "gpu_count": gpu_count,
        "gpu_names": gpu_names,
        "gpu_vram_mb": gpu_vram,
        "total_vram_mb": total_vram,
        "config": {
            "gpu_layers": -1,  # All layers
            "context_offload": False,
            "tensor_split": None,
            "flash_attention": True,
            "quantized_kv": True,
            "quantkv": quantkv_value,  # Q4 for single GPU, config default for multi-GPU
            "use_cublas": True,
            "cublas_args": None
        }
    }


def calculate_gpu_layers(model_size_gb: float, vram_mb: int) -> int:
    """
    Calculate optimal number of GPU layers based on model size and VRAM

    Args:
        model_size_gb: Model size in GB
        vram_mb: Available VRAM in MB

    Returns:
        Number of GPU layers to offload
    """
    # Safety margin
    safety_margin_mb = 2048  # 2GB safety margin

    usable_vram_mb = vram_mb - safety_margin_mb

    if usable_vram_mb < 0:
        return 0  # Not enough VRAM

    # Estimate layers based on VRAM
    # Rough approximation: 40 layers for 30B model = ~17GB
    # So 1 layer ≈ 425MB for 30B model

    model_size_mb = model_size_gb * 1024

    if model_size_mb <= usable_vram_mb:
        return -1  # All layers fit

    # Calculate partial layers
    # Assuming linear relationship (simplification)
    estimated_layers = int((usable_vram_mb / model_size_mb) * 40)

    return max(0, estimated_layers)


# ============================================================
# GPU UTILIZATION MONITORING (für InactivityMonitor)
# ============================================================

def get_gpu_utilization() -> Optional[List[int]]:
    """
    Get current GPU utilization for all GPUs via nvidia-smi

    Returns:
        List of utilization percentages (0-100) for each GPU
        None if nvidia-smi fails or no GPUs found

    Example:
        >>> utils = get_gpu_utilization()
        >>> print(utils)
        [0, 0]  # 2 GPUs, both idle
    """
    import subprocess

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False
        )

        if result.returncode != 0:
            return None

        # Parse output: "0\n15\n" -> [0, 15]
        utilizations = [
            int(line.strip())
            for line in result.stdout.strip().split('\n')
            if line.strip()
        ]

        return utilizations if utilizations else None

    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        return None


def are_all_gpus_idle(utilizations: Optional[List[int]]) -> bool:
    """
    Check if all GPUs are idle (0% utilization)

    Args:
        utilizations: List from get_gpu_utilization()

    Returns:
        True if all GPUs at 0%, False if any GPU active or None
    """
    if not utilizations:
        return False  # Assume active if can't determine

    return all(u == 0 for u in utilizations)
