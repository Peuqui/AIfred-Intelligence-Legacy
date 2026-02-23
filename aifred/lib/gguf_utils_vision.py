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
                reader = gguf.GGUFReader(f)  # type: ignore[arg-type]

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


def is_vision_language_model(architecture: str, tags: Optional[str] = None, name: Optional[str] = None) -> bool:
    """
    Determine if model is a Vision-Language Model using multiple GGUF metadata fields.

    Checks (in order):
    1. general.architecture - for vision-specific architectures (qwen3vl, mllama, etc.)
    2. general.tags - for "image-text-to-text" or similar vision tags
    3. general.name - for "V" suffix indicating vision capability (e.g. GLM-4.6V)

    Args:
        architecture: Model architecture string from GGUF (general.architecture)
        tags: Optional tags from GGUF (general.tags)
        name: Optional model name from GGUF (general.name)

    Returns:
        True if VLM, False if text-only LLM

    Example:
        >>> is_vision_language_model("qwen3vlmoe")
        True
        >>> is_vision_language_model("glm4", tags="image-text-to-text")
        True
        >>> is_vision_language_model("glm4", name="GLM-4.6V-Flash")
        True
        >>> is_vision_language_model("qwen3moe")
        False

    Note:
        Pattern list based on 2024/2025 GGUF VLM landscape.
    """
    # Check 1: Architecture-based detection
    if architecture:
        arch_lower = architecture.lower()

        # Comprehensive list of GGUF Vision-Language Model architectures (2024/2025)
        vision_architectures = [
            # === Generic markers ===
            'vl', 'vision', 'visual', 'vlm',

            # === Qwen Vision ===
            'qwen2vl', 'qwen3vl',  # qwen2vlmoe, qwen3vlmoe etc.

            # === LLaVA Family ===
            'llava', 'llavanext',

            # === Meta LLaMA Vision ===
            'mllama',  # LLaMA 3.2 Vision uses "mllama" architecture

            # === Google/Gemma Vision ===
            'paligemma', 'gemma3',

            # === Mistral Vision ===
            'pixtral',

            # === DeepSeek Vision ===
            'deepseek_vl', 'janus',

            # === InternLM/InternVL ===
            'internvl', 'internlm',

            # === CogVLM ===
            'cogvlm',

            # === MiniCPM Vision ===
            'minicpm',

            # === Microsoft Vision ===
            'phi3v', 'florence',

            # === Others ===
            'moondream', 'idefics', 'kosmos',
            'molmo', 'cambrian',

            # === CLIP-based (Vision Encoder) ===
            'clip',
        ]

        if any(marker in arch_lower for marker in vision_architectures):
            return True

    # Check 2: Tags-based detection (e.g. "image-text-to-text")
    if tags:
        vision_tags = ['image-text-to-text', 'vision', 'multimodal', 'vlm']
        if any(vt in tags.lower() for vt in vision_tags):
            return True

    # Check 3: Name-based detection (e.g. "GLM-4.6V", "Qwen2-VL")
    if name:
        import re
        # Matches: -V-, -VL, .V, V-Flash, etc. but not just any V in the name
        vision_name_patterns = [
            r'[-.]V[-.]',      # -V- or .V.
            r'[-.]V$',         # ends with -V or .V
            r'[-.]VL',         # -VL or .VL
            r'V-Flash',        # V-Flash (GLM style)
            r'[-.]Vision',     # -Vision
        ]
        for pattern in vision_name_patterns:
            if re.search(pattern, name, re.IGNORECASE):
                return True

    return False


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
