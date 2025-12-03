"""
Vision-specific GGUF utilities

Helper functions to detect Vision-Language Models and calculate
appropriate KV cache dimensioning.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_gguf_architecture(gguf_path: Path) -> Optional[str]:
    """
    Extract architecture from GGUF model metadata.

    Args:
        gguf_path: Path to GGUF model file

    Returns:
        Architecture string (e.g. "qwen3vl", "qwen3vlmoe", "llama") or None

    Example:
        >>> get_gguf_architecture(Path("/models/qwen3-vl-8b.gguf"))
        'qwen3vl'
    """
    if not gguf_path.exists():
        logger.warning(f"GGUF file not found: {gguf_path}")
        return None

    try:
        import gguf

        with open(gguf_path, "rb") as f:
            try:
                reader = gguf.GGUFReader(f)

                # Search for general.architecture key
                for field in reader.fields.values():
                    if field.name == 'general.architecture':
                        value_array = field.parts[-1]
                        if hasattr(value_array, 'tobytes'):
                            arch = value_array.tobytes().decode('utf-8', errors='ignore').strip('\x00')
                            logger.info(f"✅ Architecture from GGUF: {arch}")
                            return arch

                logger.warning("No 'general.architecture' key found in GGUF metadata")
                return None

            except Exception as e:
                logger.error(f"Error parsing GGUF metadata: {e}")
                return None

    except ImportError:
        logger.warning("gguf-py library not installed")
        return None
    except Exception as e:
        logger.error(f"Error reading GGUF file {gguf_path}: {e}")
        return None


def is_vision_language_model(architecture: str) -> bool:
    """
    Determine if architecture is a Vision-Language Model.

    Vision-Language Models require more VRAM for KV cache due to
    vision encoder outputs (2.6x more than text-only models).

    Args:
        architecture: Model architecture string from GGUF

    Returns:
        True if VLM, False if text-only LLM

    Example:
        >>> is_vision_language_model("qwen3vlmoe")
        True
        >>> is_vision_language_model("qwen3moe")
        False
    """
    if not architecture:
        return False

    # Check for vision-related strings in architecture
    vision_markers = ['vl', 'vision', 'visual', 'vlm']
    arch_lower = architecture.lower()

    return any(marker in arch_lower for marker in vision_markers)


def get_kv_cache_mb_per_token(architecture: str, quantization: str) -> float:
    """
    Calculate MB per token for KV cache based on model architecture.

    IMPORTANT: KV cache size per token is IDENTICAL for text-only and vision-language models!
    Vision tokens (from Vision Encoder → Projection Layer) use the same KV cache as text tokens.
    The 2.6x VRAM multiplier for VLMs applies to TOTAL system memory (Vision Encoder + LLM),
    NOT to per-token KV cache allocation.

    Assumes Q4 KV cache quantization (--quantkv 2).

    Args:
        architecture: Model architecture from GGUF
        quantization: Quantization level (Q4_K_M, Q5_K_S, etc.)

    Returns:
        MB per token for KV cache allocation

    Example:
        >>> get_kv_cache_mb_per_token("qwen3vlmoe", "Q4_K_M")
        0.05  # Same as text-only models
        >>> get_kv_cache_mb_per_token("qwen3moe", "Q4_K_M")
        0.05  # Text-only model
    """
    # KV cache rates for Q4 quantization with Q4 KV cache (--quantkv 2)
    # These values are IDENTICAL for text-only and vision-language models
    kv_cache_mb_per_token = {
        "Q4": 0.05,   # Q4 KV cache (75% savings vs FP16)
        "Q5": 0.06,
        "Q8": 0.10,
        "IQ4": 0.05,
        "IQ3": 0.04,
    }

    # Detect quantization level
    quant_level = "Q4"  # Default
    for key in kv_cache_mb_per_token.keys():
        if key in quantization:
            quant_level = key
            break

    # Return base rate (NO multiplier for VLMs!)
    # Vision Encoder VRAM (~2-3GB) is separate from KV cache
    return kv_cache_mb_per_token[quant_level]
