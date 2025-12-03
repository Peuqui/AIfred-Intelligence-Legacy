"""
Vision/Image Processing Utilities

Multi-backend vision model detection and image handling for AIfred Intelligence.
Supports Ollama, KoboldCPP (GGUF), vLLM, and TabbyAPI backends.
"""

import logging
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def is_vision_model_sync(model_name: str) -> bool:
    """
    Synchronous vision model detection by name patterns (for UI filtering).

    Fast name-based detection for dropdown filtering. Does not query backends.
    For precise detection, use async is_vision_model() with backend queries.

    Args:
        model_name: Model name (e.g., "qwen3-vl:30b" or "deepseek-ocr:3b")

    Returns:
        True if model name contains vision-related markers
    """
    vision_markers = [
        'vision', 'vl', 'visual', 'vlm',
        'qwen2-vl', 'qwen3-vl', 'llava', 'pixtral',
        'deepseek-ocr', 'ocr', 'internvl', 'cogvlm',
        'sam', 'minicpm-v'  # Segment Anything Model, MiniCPM-V
    ]
    model_lower = model_name.lower()
    return any(marker in model_lower for marker in vision_markers)


async def is_vision_model(state, model_name: str) -> bool:
    """
    Detect if model supports vision/multimodal input using backend-specific methods.

    Detection Strategy by Backend:
    1. **Ollama**: Query /api/show for model_info with .vision.* keys
    2. **KoboldCPP**: Read GGUF metadata for general.architecture (via gguf_utils_vision.py)
    3. **vLLM/TabbyAPI**: Read HuggingFace config.json for architectures/model_type
    4. **Fallback**: Name-based pattern matching

    Args:
        state: AIState instance (for backend_type and backend access)
        model_name: Model name (e.g., "qwen3-vl:30b" or "cpatonn/Qwen3-VL-8B")

    Returns:
        True if model has vision capabilities

    Examples:
        >>> await is_vision_model(state, "deepseek-ocr:3b")
        True  # Has .vision.* keys in Ollama model_info
        >>> await is_vision_model(state, "qwen3:8b")
        False  # Text-only model
    """
    backend_type = state.backend_type

    try:
        # === OLLAMA: Check model_info for .vision.* keys ===
        if backend_type == "ollama":
            from ..backends.ollama import OllamaBackend
            from ..backends import BackendFactory

            # Get backend instance (create if not cached)
            backend = BackendFactory.create("ollama", base_url=state.backend_url)
            if not isinstance(backend, OllamaBackend):
                logger.warning("Backend mismatch - expected Ollama")
                return _is_vision_model_by_name(model_name)

            response = await backend.client.post(
                f"{backend.base_url}/api/show",
                json={"name": model_name}
            )
            response.raise_for_status()
            data = response.json()

            model_info = data.get('model_info') or data.get('modelinfo', {})

            # Check for vision-specific parameters
            vision_keys = [
                '.vision.block_count',
                '.vision.image_size',
                '.vision.patch_size',
                '.sam.block_count'  # Segment Anything Model (for OCR models like DeepSeek-OCR)
            ]

            for key in model_info.keys():
                if any(vision_key in key for vision_key in vision_keys):
                    logger.info(f"✅ Vision model detected (Ollama): {model_name} has {key}")
                    return True

        # === KOBOLDCPP: Check GGUF metadata ===
        elif backend_type == "koboldcpp":
            from .gguf_utils import find_all_gguf_models
            from .gguf_utils_vision import get_gguf_architecture, is_vision_language_model

            # Find GGUF file for this model
            gguf_models = find_all_gguf_models()
            for gguf_model in gguf_models:
                # Match model name (case-insensitive, partial match)
                if gguf_model.name.lower() in model_name.lower() or model_name.lower() in gguf_model.name.lower():
                    arch = get_gguf_architecture(gguf_model.path)
                    if arch and is_vision_language_model(arch):
                        logger.info(f"✅ Vision model detected (GGUF): {model_name} has architecture '{arch}'")
                        return True

        # === vLLM/TabbyAPI: Check HuggingFace config.json ===
        elif backend_type in ["vllm", "tabbyapi"]:
            import json

            # Convert model name to HF cache path
            cache_dir_name = model_name.replace("/", "--")
            cache_base = Path.home() / ".cache" / "huggingface" / "hub" / f"models--{cache_dir_name}"

            # Find config.json in snapshots
            config_files = list(cache_base.glob("snapshots/*/config.json"))

            if config_files:
                with open(config_files[0], 'r') as f:
                    config = json.load(f)

                # Check architectures array
                architectures = config.get('architectures', [])
                model_type = config.get('model_type', '')

                # Vision model patterns in HuggingFace
                vision_patterns = [
                    'vision', 'vl', 'visual', 'vlm',
                    'llava', 'qwen2-vl', 'qwen3-vl',
                    'pixtral', 'internvl', 'cogvlm'
                ]

                for arch in architectures + [model_type]:
                    if any(pattern in arch.lower() for pattern in vision_patterns):
                        logger.info(f"✅ Vision model detected (HF config): {model_name} has architecture '{arch}'")
                        return True

        # No vision capabilities detected by metadata
        return False

    except Exception as e:
        logger.warning(f"Could not detect vision capabilities for {model_name}: {e}")
        # Fallback to name-based detection
        return _is_vision_model_by_name(model_name)


def _is_vision_model_by_name(model_name: str) -> bool:
    """
    Fallback: Detect vision models by name patterns.

    Used when metadata detection fails or backend doesn't provide metadata API.
    Less reliable than metadata detection but works across all backends.

    Args:
        model_name: Model name to check

    Returns:
        True if name matches known vision model patterns
    """
    vision_markers = [
        'vision', 'vl', 'visual', 'vlm',
        'qwen2-vl', 'qwen3-vl', 'llava', 'pixtral',
        'deepseek-ocr', 'ocr', 'internvl', 'cogvlm',
        'sam'  # Segment Anything Model
    ]
    model_lower = model_name.lower()
    is_vision = any(marker in model_lower for marker in vision_markers)

    if is_vision:
        logger.info(f"⚠️ Vision model detected by name pattern (fallback): {model_name}")

    return is_vision


def validate_image_file(filename: str, size_bytes: int) -> Tuple[bool, Optional[str]]:
    """
    Validate uploaded image file.

    Args:
        filename: Original filename
        size_bytes: File size in bytes (not currently used, but kept for future limits)

    Returns:
        (success, error_message) tuple

    Notes:
        - No hard file size limit (aspect ratio more important than file size)
        - Images will be resized to max 2048px dimension
        - Supported formats: JPG, PNG, GIF, WebP, BMP
    """
    # Check file extension
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
    ext = Path(filename).suffix.lower()

    if ext not in valid_extensions:
        return False, f"⚠️ Dateiformat nicht unterstützt. Erlaubt: {', '.join(valid_extensions)}"

    return True, None


def encode_image_to_base64(image_bytes: bytes) -> str:
    """
    Encode image to base64 for Ollama API.

    Args:
        image_bytes: Raw image data

    Returns:
        Base64-encoded string
    """
    import base64
    return base64.b64encode(image_bytes).decode('utf-8')


def resize_image_if_needed(image_bytes: bytes, max_dimension: int = 2048) -> bytes:
    """
    Resize image if larger than max_dimension (preserves aspect ratio).

    Args:
        image_bytes: Raw image data
        max_dimension: Maximum width or height in pixels

    Returns:
        Resized image bytes (or original if already smaller)

    Notes:
        - Preserves aspect ratio
        - Uses LANCZOS resampling for quality
        - Re-encodes as JPEG with quality=90
    """
    from PIL import Image
    import io

    img = Image.open(io.BytesIO(image_bytes))

    # Check if resize needed
    if img.width <= max_dimension and img.height <= max_dimension:
        return image_bytes

    # Calculate new size (preserve aspect ratio)
    ratio = min(max_dimension / img.width, max_dimension / img.height)
    new_size = (int(img.width * ratio), int(img.height * ratio))

    # Resize and re-encode
    img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
    output = io.BytesIO()

    # Preserve format if possible, otherwise use JPEG
    format_to_use = img.format if img.format in ['JPEG', 'PNG', 'GIF', 'WEBP', 'BMP'] else 'JPEG'
    img_resized.save(output, format=format_to_use, quality=90)

    logger.info(f"📐 Image resized: {img.width}x{img.height} → {new_size[0]}x{new_size[1]} ({format_to_use})")

    return output.getvalue()
