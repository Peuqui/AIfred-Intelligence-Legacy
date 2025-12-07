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

            # === PRIMARY: Check Ollama capabilities array (official way) ===
            # Example: {"capabilities": ["completion", "vision"]}
            capabilities = data.get('capabilities', [])
            if 'vision' in capabilities:
                logger.info(f"✅ Vision model detected (Ollama capabilities): {model_name}")
                return True

            # === FALLBACK: Check model_info for .vision.* keys ===
            # Some older models may not have capabilities but have vision keys
            model_info = data.get('model_info') or data.get('modelinfo', {})

            vision_keys = [
                '.vision.block_count',
                '.vision.image_size',
                '.vision.patch_size',
                '.sam.block_count'  # Segment Anything Model (for OCR models like DeepSeek-OCR)
            ]

            for key in model_info.keys():
                if any(vision_key in key for vision_key in vision_keys):
                    logger.info(f"✅ Vision model detected (Ollama model_info): {model_name} has {key}")
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

                # Comprehensive Vision model patterns in HuggingFace config.json (2024/2025)
                # These match architecture names and model_type values
                vision_patterns = [
                    # Generic
                    'vision', 'vl', 'visual', 'vlm', 'multimodal',
                    # LLaVA variants
                    'llava', 'llavanext', 'llavaone',
                    # Qwen Vision
                    'qwen2vl', 'qwen2_vl', 'qwen3vl', 'qwen3_vl',
                    # Google
                    'paligemma', 'gemma3',
                    # Mistral
                    'pixtral',
                    # DeepSeek
                    'deepseek_vl', 'janus',
                    # InternLM/InternVL
                    'internvl', 'internlm',
                    # CogVLM
                    'cogvlm', 'cogagent',
                    # MiniCPM
                    'minicpm', 'openbmb',
                    # Microsoft
                    'phi3v', 'phi3vision', 'florence',
                    # BLIP
                    'blip', 'instructblip',
                    # Others
                    'moondream', 'idefics', 'kosmos', 'smolvlm',
                    'molmo', 'cambrian', 'aria', 'apollo',
                    # Meta LLaMA Vision
                    'mllama', 'llama_vision',
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

    Note:
        Pattern list based on 2024/2025 VLM landscape research.
        See: https://github.com/gokayfem/awesome-vlm-architectures
    """
    # Comprehensive list of Vision-Language Model name patterns (2024/2025)
    vision_markers = [
        # === Generic markers ===
        'vision', 'vl', 'visual', 'vlm', 'multimodal',

        # === Qwen Vision Series ===
        'qwen-vl', 'qwen2-vl', 'qwen2.5-vl', 'qwen3-vl',

        # === LLaVA Family ===
        'llava', 'llava-next', 'llava-cot', 'llava-onevision',

        # === Meta/LLaMA Vision ===
        'llama-vision', 'llama3.2-vision', 'llama-3.2-vision',

        # === Google/Gemma Vision ===
        'gemma-vision', 'gemma3', 'paligemma', 'paligemma2',

        # === Mistral Vision ===
        'pixtral',

        # === DeepSeek Vision ===
        'deepseek-vl', 'deepseek-ocr', 'deepseek-janus', 'janus',

        # === Alibaba/InternLM Vision ===
        'internvl', 'internlm-xcomposer', 'xcomposer',

        # === Tsinghua/CogVLM ===
        'cogvlm', 'cogvlm2', 'cogagent',

        # === OpenBMB/MiniCPM Vision ===
        'minicpm-v', 'minicpm-llama3-v', 'openbmb',

        # === Microsoft Vision ===
        'phi-vision', 'phi3-vision', 'phi-3-vision', 'florence',

        # === Salesforce/BLIP ===
        'blip', 'blip2', 'blip-2', 'instructblip',

        # === Other Vision Models ===
        'moondream',           # Vikhyat Moondream
        'idefics', 'idefics2', # HuggingFace IDEFICS
        'kosmos', 'kosmos-2',  # Microsoft Kosmos
        'smolvlm',             # HuggingFace SmolVLM
        'apollo',              # Apollo VLM
        'aria',                # Rhymes AI ARIA
        'molmo',               # Allen AI Molmo
        'cambrian',            # Cambrian-1

        # === OCR/Document Models ===
        'ocr', 'docvqa', 'layoutlm', 'donut',

        # === Segment Anything ===
        'sam', 'sam2', 'segment-anything',
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


async def get_vision_model_capabilities(backend_url: str, model_name: str) -> Tuple[bool, Optional[int]]:
    """
    Get vision model capabilities: chat template support and context window size.

    Combines two checks in a single API call for efficiency:
    1. Chat template support (system prompts vs. simple "{{ .Prompt }}")
    2. Context window size from model metadata

    Args:
        backend_url: Ollama backend URL
        model_name: Model name to check

    Returns:
        Tuple of (supports_chat_template, context_window_size)
        - supports_chat_template: True if model has proper chat template
        - context_window_size: Context window in tokens, or None if not found

    Examples:
        >>> await get_vision_model_capabilities("http://localhost:11434", "ministral-3:8b")
        (True, 32768)  # Full chat template, 32K context
        >>> await get_vision_model_capabilities("http://localhost:11434", "deepseek-ocr:3b")
        (False, 8192)  # Simple template, 8K context
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{backend_url}/api/show",
                json={"name": model_name}
            )
            response.raise_for_status()
            data = response.json()

            # === Check 1: Chat Template Support ===
            template = data.get('template', '')
            template_normalized = template.strip()

            supports_chat_template = True  # Default: assume chat support

            if template_normalized == "{{ .Prompt }}":
                logger.info(f"⚠️ Model {model_name} has simple prompt-only template (no chat support)")
                supports_chat_template = False
            else:
                # Check for role-based markers
                chat_markers = [
                    'SYSTEM', 'INST', 'system', 'user', 'assistant',
                    '[/INST]', '<|im_start|>', '<|start_header_id|>'
                ]
                if any(marker in template for marker in chat_markers):
                    logger.info(f"✅ Model {model_name} has full chat template support")
                    supports_chat_template = True
                else:
                    logger.warning(f"⚠️ Model {model_name} has unknown template format, assuming no chat support")
                    supports_chat_template = False

            # === Check 2: Context Window Size ===
            num_ctx = None
            model_info = data.get('model_info', {})

            if model_info:
                # Search for any key containing "context_length" (universal approach)
                for key in model_info.keys():
                    if "context_length" in key:
                        num_ctx = model_info[key]
                        logger.info(f"✅ Found context window: {num_ctx} tokens (from {key})")
                        break

                # Fallback: Try generic keys if no context_length found
                if not num_ctx:
                    for key in ["max_position_embeddings", "max_seq_len"]:
                        if key in model_info:
                            num_ctx = model_info[key]
                            logger.info(f"✅ Found context window: {num_ctx} tokens (from {key})")
                            break

            if not num_ctx:
                logger.warning(f"⚠️ Could not detect context window for {model_name}")

            return supports_chat_template, num_ctx

    except Exception as e:
        logger.warning(f"Failed to get model capabilities for {model_name}: {e}")
        # Fallback: Assume chat support, no context window
        return True, None


def resize_image_if_needed(image_bytes: bytes, max_dimension: int = None) -> bytes:
    """
    Resize image if larger than max_dimension (preserves aspect ratio).

    Args:
        image_bytes: Raw image data
        max_dimension: Maximum width or height in pixels (defaults to config.VISION_MAX_IMAGE_DIMENSION)

    Returns:
        Resized image bytes (or original if already smaller)

    Notes:
        - Preserves aspect ratio
        - Uses LANCZOS resampling for quality
        - Re-encodes as JPEG with quality=90
        - Configurable via config.VISION_MAX_IMAGE_DIMENSION
    """
    from .config import VISION_MAX_IMAGE_DIMENSION

    if max_dimension is None:
        max_dimension = VISION_MAX_IMAGE_DIMENSION
    from PIL import Image, ImageOps
    import io

    img = Image.open(io.BytesIO(image_bytes))

    # EXIF-Rotation korrigieren (wichtig für Handy-Fotos!)
    # Handys speichern Rotation oft nur als EXIF-Metadaten, nicht physisch im Bild
    # Ohne das kann ein Querformat-Bild um 90° gedreht ankommen
    img = ImageOps.exif_transpose(img)

    # Check if resize needed
    if img.width <= max_dimension and img.height <= max_dimension:
        # Auch wenn kein Resize nötig, müssen wir bei EXIF-Korrektur neu encodieren
        # (nur wenn das Bild tatsächlich transponiert wurde)
        if img.getexif():
            output = io.BytesIO()
            format_to_use = img.format if img.format in ['JPEG', 'PNG', 'GIF', 'WEBP', 'BMP'] else 'JPEG'
            img.save(output, format=format_to_use, quality=90)
            return output.getvalue()
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


def crop_and_resize_image(
    image_bytes: bytes,
    crop_box: dict = None,
    max_dimension: int = None
) -> bytes:
    """
    Crop image (optional) and resize to max_dimension.

    Args:
        image_bytes: Raw image data
        crop_box: {"x": 10, "y": 5, "width": 80, "height": 90} in Prozent (0-100)
                  x, y = obere linke Ecke des Crop-Bereichs
                  width, height = Größe des Crop-Bereichs
        max_dimension: Maximum width or height in pixels (defaults to config.VISION_MAX_IMAGE_DIMENSION)

    Returns:
        Cropped and resized image bytes

    Notes:
        - EXIF-Rotation wird automatisch korrigiert
        - Preserves aspect ratio during resize
        - Uses LANCZOS resampling for quality
        - Re-encodes as JPEG with quality=90
    """
    from .config import VISION_MAX_IMAGE_DIMENSION
    from PIL import Image, ImageOps
    import io

    if max_dimension is None:
        max_dimension = VISION_MAX_IMAGE_DIMENSION

    img = Image.open(io.BytesIO(image_bytes))

    # EXIF-Rotation korrigieren (wichtig für Handy-Fotos!)
    img = ImageOps.exif_transpose(img)

    original_width, original_height = img.size

    # STEP 1: Crop (wenn crop_box vorhanden)
    if crop_box:
        # Koordinaten von Prozent zu Pixel umrechnen
        x = int(original_width * crop_box["x"] / 100)
        y = int(original_height * crop_box["y"] / 100)
        w = int(original_width * crop_box["width"] / 100)
        h = int(original_height * crop_box["height"] / 100)

        # Sicherstellen dass Crop-Box innerhalb des Bildes liegt
        x = max(0, min(x, original_width - 1))
        y = max(0, min(y, original_height - 1))
        w = min(w, original_width - x)
        h = min(h, original_height - y)

        if w > 0 and h > 0:
            img = img.crop((x, y, x + w, y + h))
            logger.info(f"✂️ Image cropped: {original_width}x{original_height} → {w}x{h}")

    # STEP 2: Resize (wenn nötig)
    if img.width > max_dimension or img.height > max_dimension:
        ratio = min(max_dimension / img.width, max_dimension / img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        logger.info(f"📐 Image resized: {img.width}x{img.height} → {new_size[0]}x{new_size[1]}")

    # STEP 3: Re-encode als JPEG
    # RGBA (PNG mit Transparenz) → RGB konvertieren (JPEG unterstützt kein Alpha)
    if img.mode in ('RGBA', 'LA', 'P'):
        # Weißer Hintergrund für transparente Bereiche
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = background

    output = io.BytesIO()
    img.save(output, format='JPEG', quality=90)

    return output.getvalue()
