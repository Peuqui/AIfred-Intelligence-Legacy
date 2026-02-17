"""
Vision/Image Processing Utilities

Multi-backend vision model detection and image handling for AIfred Intelligence.
Supports Ollama, llama.cpp (via llama-swap), vLLM, and TabbyAPI backends.
"""

import logging
from pathlib import Path
from typing import Tuple, Optional

# Imports for session-based image storage
from .config import DATA_DIR
from .logging_utils import log_message

# Images are stored in data/images/{session_id}/
# This directory is served by Reflex via /_upload/images/...
IMAGES_BASE_DIR = DATA_DIR / "images"

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
    2. **llama.cpp**: Name-based pattern matching (llama-swap keys are descriptive)
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

        # === LLAMACPP: Name-based detection (llama-swap keys are descriptive) ===
        elif backend_type == "llamacpp":
            return _is_vision_model_by_name(model_name)

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
        # For Ollama: Don't fallback to name-based detection - API is authoritative
        # For other backends: Use name-based fallback
        if backend_type == "ollama":
            return False  # Ollama API failed = assume not vision
        return _is_vision_model_by_name(model_name)


def _get_gguf_vision_metadata(gguf_path: Path) -> tuple:
    """
    Extract vision-relevant metadata from GGUF file.

    Args:
        gguf_path: Path to GGUF model file

    Returns:
        Tuple of (architecture, tags, name) - any can be None if not found
    """
    try:
        import gguf

        with open(gguf_path, "rb") as f:
            reader = gguf.GGUFReader(f)

            architecture = None
            tags = None
            name = None

            for field in reader.fields.values():
                try:
                    value_array = field.parts[-1]
                    if hasattr(value_array, 'tobytes'):
                        value = value_array.tobytes().decode('utf-8', errors='ignore').strip('\x00')
                    else:
                        value = str(value_array)

                    if field.name == 'general.architecture':
                        architecture = value
                    elif field.name == 'general.tags':
                        tags = value
                    elif field.name == 'general.name':
                        name = value
                except Exception:
                    continue

            return architecture, tags, name

    except ImportError:
        logger.warning("gguf-py library not installed")
        return None, None, None
    except Exception as e:
        logger.warning(f"Error reading GGUF metadata from {gguf_path}: {e}")
        return None, None, None


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
        return False, f"⚠️ File format not supported. Allowed: {', '.join(valid_extensions)}"

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
                log_message(f"📋 Model {model_name}: simple template (no chat support)")
                supports_chat_template = False
            else:
                # Check for role-based markers
                chat_markers = [
                    'SYSTEM', 'INST', 'system', 'user', 'assistant',
                    '[/INST]', '<|im_start|>', '<|start_header_id|>'
                ]
                if any(marker in template for marker in chat_markers):
                    log_message(f"📋 Model {model_name}: full chat template support")
                    supports_chat_template = True
                else:
                    log_message(f"📋 Model {model_name}: unknown template, assuming no chat support")
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
    original_size = (img.width, img.height)

    # Fix EXIF rotation (important for phone photos!)
    # Phones often store rotation only as EXIF metadata, not physically in the image
    # Without this, a landscape photo may arrive rotated 90°
    img = ImageOps.exif_transpose(img)

    # Check if EXIF transpose changed the image dimensions (rotation was applied)
    was_rotated = (img.width, img.height) != original_size

    # Check if resize needed
    if img.width <= max_dimension and img.height <= max_dimension:
        # Re-encode if rotation was applied (dimensions changed)
        # We must save the rotated image, not return original bytes
        if was_rotated:
            output = io.BytesIO()
            format_to_use = img.format if img.format in ['JPEG', 'PNG', 'GIF', 'WEBP', 'BMP'] else 'JPEG'
            img.save(output, format=format_to_use, quality=90)
            logger.info(f"📐 Image rotated: {original_size[0]}x{original_size[1]} → {img.width}x{img.height}")
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
        crop_box: {"x": 10, "y": 5, "width": 80, "height": 90} in percent (0-100)
                  x, y = top left corner of crop area
                  width, height = size of crop area
        max_dimension: Maximum width or height in pixels (defaults to config.VISION_MAX_IMAGE_DIMENSION)

    Returns:
        Cropped and resized image bytes

    Notes:
        - EXIF rotation is automatically corrected
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

    # Fix EXIF rotation (important for phone photos!)
    img = ImageOps.exif_transpose(img)

    original_width, original_height = img.size

    # STEP 1: Crop (if crop_box present)
    if crop_box:
        # Convert coordinates from percent to pixels
        x = int(original_width * crop_box["x"] / 100)
        y = int(original_height * crop_box["y"] / 100)
        w = int(original_width * crop_box["width"] / 100)
        h = int(original_height * crop_box["height"] / 100)

        # Ensure crop box is within image bounds
        x = max(0, min(x, original_width - 1))
        y = max(0, min(y, original_height - 1))
        w = min(w, original_width - x)
        h = min(h, original_height - y)

        if w > 0 and h > 0:
            img = img.crop((x, y, x + w, y + h))
            logger.info(f"✂️ Image cropped: {original_width}x{original_height} → {w}x{h}")

    # STEP 2: Resize (if needed)
    if img.width > max_dimension or img.height > max_dimension:
        ratio = min(max_dimension / img.width, max_dimension / img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        logger.info(f"📐 Image resized: {img.width}x{img.height} → {new_size[0]}x{new_size[1]}")

    # STEP 3: Re-encode as JPEG
    # RGBA (PNG with transparency) → Convert to RGB (JPEG doesn't support alpha)
    if img.mode in ('RGBA', 'LA', 'P'):
        # White background for transparent areas
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = background

    output = io.BytesIO()
    img.save(output, format='JPEG', quality=90)

    return output.getvalue()


# ============================================================
# Image File Storage (Session-based)
# ============================================================

# Images are stored in data/images/{session_id}/
# Structure: {session_id}/{timestamp}_{filename}
# Served by Reflex via /_upload/images/...


def save_image_to_file(image_bytes: bytes, session_id: str, filename: str) -> Path:
    """
    Save image bytes as JPEG file in session-specific directory.

    Files are stored in: data/images/{session_id}/{timestamp}_{filename}
    Served via: /_upload/images/{session_id}/{filename}

    Args:
        image_bytes: Raw JPEG image data
        session_id: Device identifier (32-char hex string)
        filename: Original filename (e.g., "Image_001.jpg")

    Returns:
        Absolute path to saved file
    """
    import time

    # Ensure session images directory exists
    # Structure: data/images/{session_id}/
    images_dir = IMAGES_BASE_DIR / session_id
    images_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename with timestamp
    timestamp = int(time.time() * 1000)  # Milliseconds for uniqueness
    safe_filename = f"{timestamp}_{filename}"
    file_path = images_dir / safe_filename

    # Write image bytes
    with open(file_path, 'wb') as f:
        f.write(image_bytes)

    logger.info(f"📁 Image saved: {file_path} ({len(image_bytes) // 1024} KB)")
    return file_path


def get_image_url(image_path: Path) -> str:
    """
    Convert absolute file path to relative URL for UI display.

    The URL uses Reflex's /_upload/ endpoint:
    data/images/{session_id}/{filename}

    Uses relative URL so the browser automatically uses the current host/port.
    This ensures images work correctly regardless of which port the user
    accessed the app from (e.g., :443 via nginx or :8443 directly).

    Args:
        image_path: Absolute path to image file

    Returns:
        Relative URL like "/_upload/images/{session_id}/{filename}"
    """
    # Extract relative path from IMAGES_BASE_DIR
    try:
        relative_path = image_path.relative_to(IMAGES_BASE_DIR)
    except ValueError:
        # Path not under IMAGES_BASE_DIR - use full path as fallback
        relative_path = image_path.name

    # Return relative URL - browser uses current host/port automatically
    return f"/_upload/images/{relative_path}"


def load_image_as_base64(image_path: Path) -> str:
    """
    Load image from file and return as Base64 string.

    Used for on-demand conversion when sending to LLM API.
    The file should be a valid JPEG image.

    Args:
        image_path: Path to JPEG image file

    Returns:
        Base64-encoded string (without data: prefix)

    Raises:
        FileNotFoundError: If image file doesn't exist
        IOError: If file cannot be read
    """
    import base64

    with open(image_path, 'rb') as f:
        image_bytes = f.read()

    return base64.b64encode(image_bytes).decode('utf-8')


def url_to_file_path(image_url: str) -> Optional[Path]:
    """
    Convert an image URL back to filesystem path.

    Handles URLs like:
    - /_upload/images/{session_id}/{filename}
    - http://host:port/_upload/images/{session_id}/{filename}

    Args:
        image_url: URL from get_image_url() or stored in chat

    Returns:
        Path object if valid, None if URL format not recognized
    """
    import re

    # Extract path part after /_upload/images/
    match = re.search(r'/_upload/images/(.+)$', image_url)
    if not match:
        return None

    relative_path = match.group(1)
    return IMAGES_BASE_DIR / relative_path


def load_image_url_as_base64(image_url: str) -> Optional[str]:
    """
    Load image from URL and return as Base64 data URI.

    Converts internal URLs (/_upload/sessions/...) to filesystem paths
    and returns the image as a data: URI for HTML embedding.

    Args:
        image_url: Internal image URL

    Returns:
        Data URI string (data:image/jpeg;base64,...) or None if failed
    """
    file_path = url_to_file_path(image_url)
    if not file_path or not file_path.exists():
        logger.warning(f"⚠️ Image not found for URL: {image_url}")
        return None

    try:
        base64_data = load_image_as_base64(file_path)
        return f"data:image/jpeg;base64,{base64_data}"
    except Exception as e:
        logger.warning(f"⚠️ Failed to load image: {e}")
        return None


def cleanup_session_images(session_id: str) -> int:
    """
    Delete all images for a session.

    Called when chat is cleared or session is deleted.
    Removes the images directory under data/images/{session_id}/.

    Args:
        session_id: Device identifier (32-char hex string)

    Returns:
        Number of files deleted
    """
    import shutil

    images_dir = IMAGES_BASE_DIR / session_id
    if not images_dir.exists():
        return 0

    # Count files before deletion
    files = list(images_dir.glob("*"))
    count = len(files)

    # Remove images directory (not the whole session folder!)
    try:
        shutil.rmtree(images_dir)
        logger.info(f"🗑️ Deleted {count} image(s) for session {session_id[:8]}...")
    except OSError as e:
        logger.warning(f"⚠️ Could not delete session images: {e}")
        return 0

    return count
