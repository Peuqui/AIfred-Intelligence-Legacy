# Vision/Image Support Implementation Plan

## User Requirements (Clarified)
- ✅ NO automatic model selection - user chooses via settings
- ✅ System must work portably on both machines (already does)
- ⚠️ Show warning if image uploaded but non-vision model selected
- 📸 Support drag & drop, paste (desktop), camera (mobile)
- 🎯 Use existing model dropdown infrastructure (Haupt-LLM)

## Architecture Overview

### Current State (Verified)
- **Hardware Detection**: Already robust (gpu_detection.py)
- **Model Selection**: Two dropdowns (Haupt-LLM, Automatik-LLM) in settings panel
- **Backend**: Ollama supports vision API but AIfred doesn't use it yet
- **Message Format**: Currently string-only, needs multimodal support
- **Warning System**: Well-established (debug console + pulsing orange boxes)

### Key Files to Modify
1. `aifred/backends/base.py` - Extend LLMMessage for multimodal content
2. `aifred/backends/ollama.py` - Add vision API message formatting
3. `aifred/state.py` - Add image state management + validation
4. `aifred/aifred.py` - Add upload UI components
5. `aifred/lib/vision_utils.py` - NEW: Image processing utilities

---

## Pre-Implementation: Create Milestone

### Step 0: Tag Current Commit
**Before any changes**, create a git tag for easy rollback:

```bash
git tag -a v2.2.0-pre-vision -m "Milestone before Vision/Image support implementation"
git push origin v2.2.0-pre-vision
```

**Rationale**: Allows easy rollback with `git reset --hard v2.2.0-pre-vision` if needed.

---

## Implementation Phases

## Phase 1: Message Format Extension

### 1.1 Extend LLMMessage Class
**File**: `aifred/backends/base.py` (lines 12-17)

**Current**:
```python
@dataclass
class LLMMessage:
    role: str  # "system", "user", "assistant"
    content: str  # String only
```

**Change to**:
```python
@dataclass
class LLMMessage:
    role: str  # "system", "user", "assistant"
    content: Union[str, List[Dict[str, Any]]]  # String or multimodal content array
```

**Rationale**: Support both legacy string format and new multimodal array format. No backward compatibility needed (user confirmed).

### 1.2 Vision Model Detection (Multi-Backend Support)
**File**: `aifred/lib/vision_utils.py` (NEW)

**Challenge**: Each backend has different metadata sources:
- **Ollama**: `/api/show` endpoint → `model_info` with `.vision.*` keys
- **KoboldCPP/GGUF**: `general.architecture` from GGUF metadata (already implemented in `gguf_utils_vision.py`)
- **vLLM/TabbyAPI**: HuggingFace `config.json` → `architectures` array or `model_type`

**Solution**: Backend-specific detection with fallback chain

```python
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
    """
    backend_type = state.backend_type

    try:
        # === OLLAMA: Check model_info for .vision.* keys ===
        if backend_type == "ollama":
            backend = state._get_backend()  # Access current backend instance
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
                '.sam.block_count'  # Segment Anything Model (for OCR models)
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
                if gguf_model.name.lower() in model_name.lower():
                    arch = get_gguf_architecture(gguf_model.path)
                    if arch and is_vision_language_model(arch):
                        logger.info(f"✅ Vision model detected (GGUF): {model_name} has architecture '{arch}'")
                        return True

        # === vLLM/TabbyAPI: Check HuggingFace config.json ===
        elif backend_type in ["vllm", "tabbyapi"]:
            from pathlib import Path
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
        size_bytes: File size in bytes

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
    """Encode image to base64 for Ollama API"""
    import base64
    return base64.b64encode(image_bytes).decode('utf-8')

def resize_image_if_needed(image_bytes: bytes, max_dimension: int = 2048) -> bytes:
    """Resize image if larger than max_dimension (preserves aspect ratio)"""
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
    img_resized.save(output, format=img.format or 'JPEG', quality=90)
    return output.getvalue()
```

**Dependencies**: Add to requirements: `Pillow>=10.0.0`

---

## Phase 2: State Management

### 2.1 Add Image State Variables
**File**: `aifred/state.py`

**Add after line 236** (after current_ai_response):
```python
# Image Upload State
pending_images: List[Dict[str, str]] = []  # [{"name": "img.jpg", "base64": "...", "url": "..."}]
image_upload_warning: str = ""  # Warning message if non-vision model selected
max_images_per_message: int = 5  # Limit concurrent uploads
```

### 2.2 Add Image Upload Handler
**File**: `aifred/state.py`

**Add new method** (around line 900, near other handlers):
```python
async def handle_image_upload(self, files: List[rx.UploadFile]):
    """Handle image file uploads with validation"""
    from .lib.vision_utils import (
        validate_image_file,
        encode_image_to_base64,
        resize_image_if_needed,
        is_vision_model
    )

    # Check if vision model selected
    selected_model_pure = extract_model_name(self.selected_model)

    if not is_vision_model(selected_model_pure):
        self.image_upload_warning = "⚠️ Gewähltes Modell unterstützt keine Bilder. Bitte wähle ein Vision-Modell (z.B. Qwen3-VL, DeepSeek-OCR)."
        self.add_debug("⚠️ Image upload blocked: Non-vision model selected")
        return

    # Clear previous warning
    self.image_upload_warning = ""

    # Check max images limit
    if len(self.pending_images) + len(files) > self.max_images_per_message:
        self.image_upload_warning = f"⚠️ Maximal {self.max_images_per_message} Bilder pro Nachricht"
        return

    for file in files:
        # Read file content
        content = await file.read()

        # Validate
        valid, error = validate_image_file(file.filename, len(content))
        if not valid:
            self.image_upload_warning = error
            continue

        # Resize if needed (save bandwidth/VRAM)
        resized_content = resize_image_if_needed(content)

        # Encode to base64
        base64_data = encode_image_to_base64(resized_content)

        # Create data URL for preview
        data_url = f"data:image/jpeg;base64,{base64_data}"

        # Store
        self.pending_images.append({
            "name": file.filename,
            "base64": base64_data,
            "url": data_url,  # For UI preview
            "size_kb": len(resized_content) // 1024
        })

        self.add_debug(f"📷 Bild hochgeladen: {file.filename} ({len(resized_content) // 1024} KB)")

def remove_pending_image(self, index: int):
    """Remove image from pending uploads"""
    if 0 <= index < len(self.pending_images):
        removed = self.pending_images.pop(index)
        self.add_debug(f"🗑️ Bild entfernt: {removed['name']}")

        # Clear warning if it was about model compatibility
        if self.image_upload_warning.startswith("⚠️ Gewähltes Modell"):
            self.image_upload_warning = ""

def clear_pending_images(self):
    """Clear all pending images"""
    count = len(self.pending_images)
    self.pending_images = []
    self.image_upload_warning = ""
    if count > 0:
        self.add_debug(f"🗑️ {count} Bilder gelöscht")
```

### 2.3 Check Model on Selection Change
**File**: `aifred/state.py`

**Modify `set_selected_model()`** (around line 850):
```python
def set_selected_model(self, model_name: str):
    """Set selected model and validate against pending images"""
    from .lib.vision_utils import is_vision_model

    self.selected_model = model_name

    # Check if switching to non-vision model with pending images
    if len(self.pending_images) > 0:
        model_pure = extract_model_name(model_name)
        if not is_vision_model(model_pure):
            self.image_upload_warning = "⚠️ Gewähltes Modell unterstützt keine Bilder. Bilder werden beim Senden ignoriert."
        else:
            self.image_upload_warning = ""  # Clear warning

    # Save settings (existing logic)
    self._save_settings()
```

---

## Phase 3: Backend Integration

### 3.1 Extend Ollama Message Formatting
**File**: `aifred/backends/ollama.py`

**Modify `chat()` method** (around lines 48-109):

**Current** (line 71-77):
```python
ollama_messages = [
    {"role": msg.role, "content": msg.content}
    for msg in messages
]
```

**Change to**:
```python
ollama_messages = []
for msg in messages:
    # Handle multimodal content
    if isinstance(msg.content, list):
        # Already in multimodal format
        ollama_messages.append({"role": msg.role, "content": msg.content})
    elif isinstance(msg.content, str):
        # Legacy string format
        content_parts = [{"type": "text", "text": msg.content}]

        # Add images if present (deprecated field)
        if hasattr(msg, 'images') and msg.images:
            for img_base64 in msg.images:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}
                })

        ollama_messages.append({"role": msg.role, "content": content_parts})
```

---

## Phase 4: UI Components

### 4.1 Image Upload Component
**File**: `aifred/aifred.py`

**Add BEFORE text input** (before line 173):

```python
def image_upload_section() -> rx.Component:
    """Image upload component with preview"""
    return rx.box(
        # Warning box (if model doesn't support vision)
        rx.cond(
            AIState.image_upload_warning != "",
            rx.box(
                rx.text(AIState.image_upload_warning),
                background_color="rgba(255, 152, 0, 0.15)",
                border="2px solid rgba(255, 152, 0, 0.5)",
                padding="8px 12px",
                border_radius="6px",
                margin_bottom="8px",
                class_name="warning-pulse"  # Uses existing animation
            )
        ),

        # Image preview grid
        rx.cond(
            AIState.pending_images.length() > 0,
            rx.hstack(
                rx.foreach(
                    AIState.pending_images,
                    lambda img, idx: rx.box(
                        rx.image(
                            src=img["url"],
                            width="80px",
                            height="80px",
                            object_fit="cover",
                            border_radius="4px",
                        ),
                        rx.badge(
                            img["name"],
                            font_size="10px",
                            max_width="80px",
                            overflow="hidden",
                            text_overflow="ellipsis",
                            white_space="nowrap"
                        ),
                        rx.icon_button(
                            rx.icon("x", size=12),
                            size="1",
                            color_scheme="red",
                            position="absolute",
                            top="4px",
                            right="4px",
                            on_click=lambda: AIState.remove_pending_image(idx),
                        ),
                        position="relative",
                        margin_right="8px"
                    )
                ),
                spacing="8px",
                margin_bottom="8px",
                wrap="wrap"
            )
        ),

        # Upload button + clear button
        rx.hstack(
            rx.upload(
                rx.button(
                    rx.icon("image", size=16),
                    rx.text("Bild hochladen"),
                    size="2",
                    variant="soft",
                    disabled=AIState.is_generating | (AIState.pending_images.length() >= AIState.max_images_per_message),
                ),
                id="image-upload",
                accept={"image/*": [".jpg", ".jpeg", ".png", ".gif", ".webp"]},
                max_files=AIState.max_images_per_message,
                on_drop=AIState.handle_image_upload,
                border="2px dashed transparent",
                padding="0",
            ),

            rx.cond(
                AIState.pending_images.length() > 0,
                rx.button(
                    rx.icon("trash-2", size=16),
                    rx.text("Alle löschen"),
                    size="2",
                    variant="soft",
                    color_scheme="red",
                    on_click=AIState.clear_pending_images,
                )
            ),

            spacing="8px",
            margin_bottom="12px"
        ),

        width="100%"
    )
```

**Insert in main chat UI** (before line 173):
```python
# Current:
rx.text_area(...)

# Change to:
image_upload_section(),  # NEW
rx.text_area(...)
```

### 4.2 Mobile Camera Support
**File**: `aifred/aifred.py`

**Add mobile-specific button** (responsive):
```python
rx.box(
    rx.button(
        rx.icon("camera", size=16),
        rx.text("📸 Foto aufnehmen", display=["block", "none"]),  # Mobile only
        size="2",
        variant="soft",
        on_click=rx.call_script("document.getElementById('camera-input').click()"),
    ),
    rx.input(
        id="camera-input",
        type="file",
        accept="image/*",
        capture="environment",  # Use rear camera
        display="none",
        on_change=AIState.handle_image_upload
    ),
    display=["block", "none"]  # Show on mobile, hide on desktop
)
```

### 4.3 Paste Support (Desktop)
**File**: `aifred/aifred.py`

**Add global paste handler** (in app root):
```python
rx.script("""
document.addEventListener('paste', async (e) => {
    const items = e.clipboardData.items;
    const imageFiles = [];

    for (let item of items) {
        if (item.type.startsWith('image/')) {
            const file = item.getAsFile();
            imageFiles.push(file);
        }
    }

    if (imageFiles.length > 0) {
        e.preventDefault();
        // Trigger Reflex upload handler
        const uploadComponent = document.getElementById('image-upload');
        if (uploadComponent) {
            // Simulate file drop
            const dataTransfer = new DataTransfer();
            imageFiles.forEach(f => dataTransfer.items.add(f));
            uploadComponent.dispatchEvent(new DragEvent('drop', {dataTransfer}));
        }
    }
});
""")
```

---

## Phase 5: Message Sending with Images

### 5.1 Modify Send Message Handler
**File**: `aifred/lib/conversation_handler.py`

**Modify `handle_user_message()`** to include images:

**Current** (creates LLMMessage with string content):
```python
user_message = LLMMessage(role="user", content=user_text)
```

**Change to**:
```python
# Build multimodal content if images present
if state.pending_images:
    content_parts = [{"type": "text", "text": user_text}]

    for img in state.pending_images:
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{img['base64']}"}
        })

    user_message = LLMMessage(role="user", content=content_parts)

    state.add_debug(f"📷 Sende Nachricht mit {len(state.pending_images)} Bild(ern)")
    state.clear_pending_images()  # Clear after sending
else:
    # Text-only message (legacy format)
    user_message = LLMMessage(role="user", content=user_text)
```

### 5.2 History Storage with Images
**File**: `aifred/state.py`

**Current history format** (line 231):
```python
chat_history: List[Tuple[str, str]] = []  # [(user_msg, ai_msg)]
```

**Issue**: Tuple format can't store images!

**Proposed Change** (backward compatible):
```python
chat_history: List[Dict[str, Any]] = []  # [{"user": "...", "assistant": "...", "images": [...]}]
```

**Migration**: Keep tuple format for now, add separate image storage:
```python
chat_history: List[Tuple[str, str]] = []  # Legacy format
chat_images: Dict[int, List[str]] = {}    # {message_index: [base64_images]}
```

---

## Phase 6: Testing & Polish

### 6.1 Test Cases
1. **Upload single image** (JPEG, PNG, WebP)
2. **Upload multiple images** (up to max limit)
3. **Paste screenshot** (Ctrl+V on desktop)
4. **Mobile camera capture** (rear camera)
5. **Model switch warning** (upload image → switch to text-only model)
6. **File size validation** (>10MB rejection)
7. **Invalid format rejection** (PDF, DOC)
8. **Message send with images** (verify Ollama receives correct format)
9. **Clear images** (individual + all)
10. **History with images** (messages display correctly)

### 6.2 Edge Cases
- ✅ Empty text + image only → should work
- ✅ Upload max images → button disabled
- ✅ Clear images → warning cleared
- ✅ Switch model → revalidate images
- ⚠️ Ollama server down → proper error message
- ⚠️ Vision model not installed → suggest installation

### 6.3 Performance Optimization
- ✅ Image resizing (max 2048px) - already in vision_utils.py
- ✅ Base64 encoding in background (async handler)
- ✅ Thumbnail generation for preview (use resized version)
- ⚠️ Consider lazy loading for chat history images

---

## Critical Files Summary

### Files to Modify
1. **aifred/backends/base.py** (lines 12-17)
   - Extend `LLMMessage.content` to support multimodal arrays

2. **aifred/backends/ollama.py** (lines 71-77)
   - Format messages with images for Ollama API

3. **aifred/state.py**
   - Add image state variables (after line 236)
   - Add handlers: `handle_image_upload`, `remove_pending_image`, `clear_pending_images`
   - Modify `set_selected_model()` for validation (line 850)

4. **aifred/aifred.py**
   - Add `image_upload_section()` component (before line 173)
   - Add mobile camera button (responsive)
   - Add paste handler script

5. **aifred/lib/conversation_handler.py**
   - Modify message sending to include images

### Files to Create
6. **aifred/lib/vision_utils.py** (NEW)
   - Image validation, encoding, resizing
   - Vision model detection

### Dependencies to Add
- `Pillow>=10.0.0` (image processing)

---

## Deployment Strategy

### Development (Haupt-PC)
1. Implement on Haupt-PC (faster development cycle)
2. Test with Qwen3-VL-8B (4.7 GB - fits in 24 GB)
3. Test mobile UI via browser responsive mode

### Production (MiniPC)
1. Git push from Haupt-PC
2. Git pull on MiniPC
3. Test with Qwen3-VL-30B (18 GB - uses 2x P40)
4. Test mobile access via Fritzbox forwarding

### Portable Guarantees
- ✅ No hardcoded paths (already portable)
- ✅ Settings stored per-instance (settings.json)
- ✅ GPU detection handles both systems
- ✅ Model selection independent (user chooses)

---

## User Decisions (from feedback)

### ✅ Q1: Backward Compatibility
**Decision**: NO backward compatibility needed
- Remove `images: Optional[List[str]]` field from LLMMessage
- Clean break, simpler implementation

### ✅ Q2: Vision Model Detection
**Decision**: Use metadata-based detection with fallback
- **Ollama**: Check `model_info` for `.vision.*` keys ✅
- **KoboldCPP**: Read GGUF `general.architecture` (already implemented) ✅
- **vLLM/TabbyAPI**: Read HuggingFace `config.json` for `architectures` ✅
- **Fallback**: Name-based pattern matching
- **More reliable than name-only detection**

### ✅ Q3: Image Size Limits
**Decision**: No hard file size limit
- **Rationale**: Aspect ratio matters more than file size
- Images resized to max 2048px dimension automatically
- Large originals handled gracefully by resize

### ✅ Q4: Bitmap (BMP) Support
**Decision**: YES, include BMP in supported formats
- Supported: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.bmp`

### ✅ Q5: Git Milestone Before Implementation
**Decision**: Create git tag BEFORE starting
- Tag: `v2.2.0-pre-vision`
- Allows easy rollback if needed
- **Must be done in Step 0**

### ✅ Q6: Image Preview in Chat History
**Decision**: Collapsed thumbnails (click to expand)
- Save space in chat history
- Click thumbnail → fullscreen preview
- User confirmed this approach

### ✅ Q7: OCR Post-Processing Features
**Decision**: Phase 2 (after basic vision support)
- Table → Markdown conversion
- Copy-to-clipboard for extracted text
- JSON/CSV export
- **Implement basic upload/inference first, then add OCR tools**

---

## Timeline Estimate

### Phase 1-2 (Core functionality): 3-4 hours
- Message format extension
- State management
- Backend integration

### Phase 3-4 (UI): 2-3 hours
- Upload components
- Image preview
- Mobile camera support

### Phase 5-6 (Testing & Polish): 2-3 hours
- Test all platforms
- Edge case handling
- Performance optimization

**Total**: 7-10 hours of focused development

---

## Success Criteria
- ✅ User can upload images via drag-drop, paste, or camera
- ✅ Images preview correctly before sending
- ✅ Warning shown if non-vision model selected with images
- ✅ Images sent correctly to Ollama vision API
- ✅ Works on both Haupt-PC (3090 Ti) and MiniPC (2x P40)
- ✅ Mobile camera access works via Fritzbox forwarding
- ✅ No hardcoded hardware assumptions
