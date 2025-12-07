# Changelog

All notable changes to AIfred Intelligence will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.5.1] - 2025-12-07

### 📱 Mobile UX Improvements - Crop Modal & Image Upload

**Enhanced mobile experience:** Fullscreen crop modal, improved thumbnail layout, and smarter image naming.

#### Fixed

- **Crop Modal Positioning** ([aifred.py:409-590](aifred/aifred.py#L409-L590)):
  - **Problem:** Crop modal appeared at bottom-right on mobile devices, often off-screen when page was scrolled
  - **Fix:** Replaced `rx.dialog` with fullscreen overlay using `position: fixed`
  - Added JavaScript to scroll page to top and block body scroll when modal opens
  - Restored scroll on modal close

- **Touch Interaction Issues** ([custom.css:238-395](assets/custom.css#L238-L395)):
  - **Problem:** "Snap-to-grid" behavior on mobile made crop box hard to control
  - **Fix:** Added `touch-action: none` on all crop elements (container, overlay, box, handles)
  - Disabled webkit touch callout and user-select

- **Backend Dropdown Empty on Mobile** ([aifred.py](aifred/aifred.py)):
  - **Problem:** Backend dropdown showed nothing in closed state on mobile
  - **Root Cause:** CSS layout issue - badge next to dropdown consumed all space
  - **Fix:** Added `min_width: 120px` and `flex: 1` to native select

#### Changed

- **Image Upload Layout** ([aifred.py:348-407](aifred/aifred.py#L348-L407)):
  - Buttons and hint text now left-aligned (not centered)
  - Thumbnails display below buttons (not beside them)
  - Thumbnail size increased: 60px → 80px
  - Crop/delete buttons enlarged for better touch targets (size="2")

- **Image Name Shortening** ([state.py:2743-2752](aifred/state.py#L2743-L2752)):
  - Camera images with long names (>20 chars) like `2025-12-07_11.36.123456789.jpg` now display as `Bild_001.jpg`
  - Original filename preserved internally

- **Crop Completion Messages** ([state.py:2916-2920](aifred/state.py#L2916-L2920)):
  - Simplified from: `✂️ Bild zugeschnitten: image.png (1920 x 1080 → 91% x 47% → 1747 x 508 px)`
  - To: `✂️ Bild zugeschnitten: 91% x 47% → 1747 x 508 px`
  - Filename already shown in previous message

#### Technical Details

**Scroll Fix JavaScript:**
```javascript
// When modal opens:
document.body.style.overflow = 'hidden';
document.documentElement.style.overflow = 'hidden';
window.scrollTo(0, 0);

// When modal closes:
document.body.style.overflow = '';
document.documentElement.style.overflow = '';
```

---

## [2.5.0] - 2025-12-07

### ✂️ Image Crop & 4K Auto-Resize

**New feature:** Crop images before sending to Vision-LLM, with automatic 4K resolution limit.

#### Added

- **Interactive Crop Modal** ([aifred.py:409-590](aifred/aifred.py#L409-L590)):
  - Full-screen modal with dark semi-transparent overlay
  - Image displayed with `object-fit: contain` for proper aspect ratio
  - Draggable crop box with visual selection area
  - "Zuschneiden" (Crop) and "Abbrechen" (Cancel) buttons

- **8-Point Drag Handles** ([custom.css:234-381](assets/custom.css#L234-L381)):
  - 4 corner handles (nw, ne, sw, se) - diagonal resizing
  - 4 edge handles (n, s, e, w) - single-axis resizing
  - Touch-friendly: 24px hit area, 12px visible circle
  - Visual feedback with `cursor` styles and hover effects

- **Crop Button per Image** ([aifred.py:348-407](aifred/aifred.py#L348-L407)):
  - Green crop icon button on each image thumbnail
  - Position: top-left corner of preview
  - Opens crop modal for that specific image

- **Crop State Variables** ([state.py:282-291](aifred/state.py#L282-L291)):
  - `crop_modal_open`: Modal visibility toggle
  - `crop_image_index`: Which image is being cropped
  - `crop_image_url`: Data-URL for crop preview
  - `crop_box`: {x, y, width, height} in percent (0-100)

- **Crop Handler** ([state.py:2858-2937](aifred/state.py#L2858-L2937)):
  - `open_crop_modal(index)`: Opens modal with selected image
  - `apply_crop()`: Applies crop and replaces image in pending_images
  - `cancel_crop()`: Closes modal without changes
  - Detailed logging: `✂️ Bild zugeschnitten: image.png (1920 x 1080 → 91% x 47% → 1747 x 508 px)`

- **crop_and_resize_image() Function** ([vision_utils.py:377-453](aifred/lib/vision_utils.py#L377-L453)):
  - Crop image based on percentage box `{x, y, width, height}`
  - EXIF rotation fix with `ImageOps.exif_transpose()`
  - Automatic resize to max dimension (4K)
  - RGBA→RGB conversion for PNG transparency (white background)

#### Changed

- **4K Resolution Limit** ([config.py:358](aifred/lib/config.py#L358)):
  - `VISION_MAX_IMAGE_DIMENSION`: 2048 → 3840 (4K UHD)
  - Better quality for detailed documents and images

- **EXIF Rotation Handling** ([vision_utils.py:392-395](aifred/lib/vision_utils.py#L392-L395)):
  - Mobile photos now correctly oriented before cropping
  - Uses `PIL.ImageOps.exif_transpose()` to auto-rotate

- **RGBA to RGB Conversion** ([vision_utils.py:428-441](aifred/lib/vision_utils.py#L428-L441)):
  - PNG screenshots with transparency now work correctly
  - Transparent areas filled with white background
  - Supports RGBA, LA, and P (palette) modes

#### Technical Details

**Crop Flow:**
```
User clicks crop button on thumbnail
    ↓
open_crop_modal(index) → Shows modal with image
    ↓
User drags corners/edges to adjust crop box
    ↓
JavaScript updates crop_box state via on_change
    ↓
User clicks "Zuschneiden"
    ↓
apply_crop() → crop_and_resize_image(original_bytes, crop_box)
    ↓
Cropped image replaces original in pending_images
    ↓
Modal closes, thumbnail updates
```

**Crop Box Calculation:**
```python
# crop_box = {x: 10, y: 20, width: 60, height: 50} (percent)
# Image size = 1920 x 1080 pixels

x_px = 1920 * 10 / 100 = 192
y_px = 1080 * 20 / 100 = 216
w_px = 1920 * 60 / 100 = 1152
h_px = 1080 * 50 / 100 = 540

cropped = img.crop((192, 216, 192+1152, 216+540))
```

#### Files Modified

1. [aifred/aifred.py](aifred/aifred.py) - Crop button + modal UI
2. [aifred/lib/config.py](aifred/lib/config.py) - 4K resolution limit
3. [aifred/lib/vision_utils.py](aifred/lib/vision_utils.py) - crop_and_resize_image(), EXIF fix, RGBA→RGB
4. [aifred/state.py](aifred/state.py) - Crop state variables + handlers
5. [assets/custom.css](assets/custom.css) - Crop modal styling with drag handles

---

## [2.4.2] - 2025-12-06

### 🔧 Model-Sync Fix & Universelle Vision-Erkennung

**Kritische Bugfixes:** Model-IDs werden jetzt korrekt synchronisiert wenn User im Dropdown wechselt. Vision-LLM unterstützt jetzt beliebige Dokumenttypen ohne Fehlermeldungen.

#### Fixed

- **Model-ID Sync beim Dropdown-Wechsel** ([state.py:3207-3209](aifred/state.py#L3207-L3209), [state.py:3414-3415](aifred/state.py#L3414-L3415), [state.py:3431](aifred/state.py#L3431)):
  - **Problem:** Vision-LLM zeigte falsches Modell (UI: qwen3-vl:8b, tatsächlich: deepseek-ocr:3b)
  - **Root Cause:** `set_selected_model()`, `set_automatik_model()`, `set_vision_model()` setzten nur Display-Variable, nicht die `*_model_id`
  - **Fix:** Alle drei Handler synchronisieren jetzt die ID via `extract_model_name()`
  - Model-Änderungen werden jetzt auch korrekt gespeichert

- **Model-Settings nicht gespeichert bei Ollama** ([state.py:3210-3211](aifred/state.py#L3210-L3211)):
  - **Problem:** `_save_settings()` wurde bei Ollama-Backend nicht aufgerufen (nur bei vLLM/TabbyAPI/KoboldCPP)
  - **Fix:** `_save_settings()` wird jetzt VOR dem Backend-spezifischen Code aufgerufen

#### Added

- **Universeller Vision-Dokumenttyp-Handler** ([conversation_handler.py:289-333](aifred/lib/conversation_handler.py#L289-L333)):
  - **Vorher:** Unbekannte Typen wie `image_description` zeigten Fehlermeldung
  - **Nachher:** Dynamischer Fallback extrahiert Inhalt aus bekannten Feldern (`content`, `description`, `text`, `items`, `sections`)
  - Vision-LLM kann jetzt beliebige Typen zurückgeben (`photo`, `scene`, `diagram`, etc.)
  - Keine Hardcodierung neuer Typen mehr nötig

---

## [2.4.1] - 2025-12-06

### 🔧 Generic XML-Tag Processing & Vision Collapsible Bugfix

**Major refactor:** Replaced hardcoded XML-tag handling with generic, config-driven processing. Fixed critical double-collapsible bug in Vision-LLM responses.

#### Fixed

- **Double Collapsible Bug in Vision-LLM** ([conversation_handler.py:494-502](aifred/lib/conversation_handler.py#L494-L502), [state.py:1799-1907](aifred/state.py#L1799-L1907)):
  - **Problem:** Vision-LLM with `<think>` tags (qwen3-vl:30b) showed thinking process TWICE
  - **Root Cause:** `<think>` content extracted in conversation_handler.py, rebuilt in state.py, then extracted AGAIN by format_thinking_process()
  - **Fix:** Removed `<think>` extraction from conversation_handler.py; let format_thinking_process() handle it once
  - Vision-LLM responses now show single collapsible as expected

- **Nested XML-Tag Stripping** ([formatting.py:195-201](aifred/lib/formatting.py#L195-L201), [formatting.py:267-272](aifred/lib/formatting.py#L267-L272)):
  - **Problem:** Nested tags like `<code><function>...</function></code>` lost inner tags
  - **Root Cause:** Global regex `re.sub(r'<(\w+)>.*?</\1>', '', ...)` removed ALL tags
  - **Fix:** Only remove extracted top-level tags; preserve nested tags in collapsible content

#### Added

- **Generic XML-Tag Detection** ([formatting.py:94-111](aifred/lib/formatting.py#L94-L111)):
  - New `extract_xml_tags()` helper function with regex `r'<(\w+)>(.*?)</\1>'`
  - Detects ANY XML-style tags automatically (not just hardcoded `<think>`, `<data>`)
  - Returns list of `(tag_name, content)` tuples for processing

- **XML Tag Configuration Dictionary** ([config.py:340-347](aifred/lib/config.py#L340-L347)):
  - `XML_TAG_CONFIG` dict defines icon, label, CSS class per tag
  - Known tags: `think` (💭), `data` (📊), `python` (🐍), `code` (💻), `sql` (🗃️), `json` (📋)
  - **Unknown tags get auto-fallback:** "📄 Tagname" (capitalized)
  - Config-driven: Add new tags without code changes!

- **Auto-Formatting for Unknown XML Tags** ([formatting.py:164-172](aifred/lib/formatting.py#L164-L172)):
  - Any XML tag not in `XML_TAG_CONFIG` gets automatic collapsible with "📄" icon
  - Log info: `ℹ️ Auto-formatiere unbekanntes XML-Tag: <tagname> → 📄 Tagname`
  - Example: LLM generates `<peitenfunktion>code</peitenfunktion>` → "📄 Peitenfunktion" collapsible

#### Changed

- **Refactored format_thinking_process()** ([formatting.py:128-206](aifred/lib/formatting.py#L128-L206)):
  - **Before:** Hardcoded pattern matching for `<think>` and `<data>` tags only
  - **After:** Generic loop over all detected XML tags with config lookup
  - Supports unlimited tag types via `XML_TAG_CONFIG`
  - Inference time shown only for `<think>` tags (reasoning)

- **Refactored build_debug_accordion()** ([formatting.py:209-277](aifred/lib/formatting.py#L209-L277)):
  - Now uses `extract_xml_tags()` instead of hardcoded patterns
  - Consistent behavior with main formatter

- **Simplified Vision Response Reconstruction** ([state.py:1867-1889](aifred/state.py#L1867-L1889)):
  - Removed `vision_think_content` variable (no longer needed)
  - `vision_readable_text` may contain `<think>` tags - handled by format_thinking_process()
  - Only `<data>` block explicitly constructed for JSON responses

#### Technical Details

**Before (Buggy Flow):**
```
conversation_handler → Extracts <think> → yields {"type": "thinking"}
                                          ↓
state.py → Collects think_content → Rebuilds <think> tags
                                          ↓
format_thinking_process() → Extracts <think> AGAIN → DOUBLE COLLAPSIBLE!
```

**After (Fixed Flow):**
```
conversation_handler → Leaves <think> tags in vision_readable_text
                                          ↓
state.py → Passes vision_readable_text unchanged
                                          ↓
format_thinking_process() → Extracts <think> ONCE → Single collapsible!
```

**Generic XML Processing:**
```python
# Old (hardcoded):
if '<think>' in response: ...  # Only 2 tags supported
if '<data>' in response: ...

# New (generic):
xml_tags = extract_xml_tags(response)  # ANY tag detected!
for tag_name, content in xml_tags:
    config = XML_TAG_CONFIG.get(tag_name, fallback)
```

#### Files Modified

1. [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py) - Removed <think> extraction
2. [aifred/state.py](aifred/state.py) - Simplified Vision response handling
3. [aifred/lib/formatting.py](aifred/lib/formatting.py) - Generic XML processing, nested tag fix
4. [aifred/lib/config.py](aifred/lib/config.py) - Added XML_TAG_CONFIG dictionary

---

### 🎨 Metadata Formatting & HTML Tag Blacklist (2025-12-06)

**UI refinement:** Improved metadata display and added HTML tag blacklist for XML processing.

#### Added

- **HTML Tag Blacklist** ([html_tags.py](aifred/lib/html_tags.py)):
  - New file with 96 HTML5 tags excluded from XML-Tag processing
  - Prevents HTML elements like `<span>`, `<div>`, `<details>` from becoming collapsibles
  - Categories: inline, block, table, form, media, interactive, meta elements
  - `extract_xml_tags()` now checks against `HTML_TAG_BLACKLIST`

#### Changed

- **Metadata Formatting** ([formatting.py:47-76](aifred/lib/formatting.py#L47-L76)):
  - Changed from HTML `<span style="...">` to Markdown `*...*` (italic)
  - **Why:** `rx.markdown()` escapes inline HTML by default
  - CSS styling in [custom.css](assets/custom.css) makes `<em>` tags gray (#888)
  - Metadata now appears on its own line (Markdown line break: `"  \n"`)

- **Metadata Line Breaks** ([conversation_handler.py](aifred/lib/conversation_handler.py), [state.py](aifred/state.py), [context_builder.py](aifred/lib/research/context_builder.py)):
  - Changed from `\n\n` (paragraph) to `  \n` (Markdown line break)
  - Removes extra blank line between content and metadata
  - Metadata displays directly below content on its own line

#### Files Modified

5. [aifred/lib/html_tags.py](aifred/lib/html_tags.py) - **NEW:** HTML tag blacklist (96 tags)
6. [aifred/lib/formatting.py](aifred/lib/formatting.py) - Markdown metadata formatting
7. [assets/custom.css](assets/custom.css) - CSS for gray italic `<em>` tags
8. [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py) - Metadata line breaks
9. [aifred/state.py](aifred/state.py) - Metadata line breaks
10. [aifred/lib/research/context_builder.py](aifred/lib/research/context_builder.py) - Metadata line breaks

## [2.4.0] - 2025-12-04

### 🔗 Vision + Research Integration

**Game Changer:** Intelligent image data extraction flows seamlessly into web research and AI analysis.

#### Added (2025-12-04 03:00)

- **Camera Button for Mobile Devices** ([aifred.py:195-217](aifred/aifred.py#L195-L217), [state.py:228](aifred/state.py#L228), [state.py:2552-2558](aifred/state.py#L2552-L2558)):
  - Browser-based camera detection via JavaScript (`navigator.mediaDevices.enumerateDevices()`)
  - Camera button only visible if browser supports camera access
  - Desktop without camera: Button hidden (no confusing file requestor)
  - Mobile/Tablet with camera: Button visible, opens camera for photo capture
  - Uses `rx.call_script` with callback to set `camera_available` state
  - Positioned left of "Bild hochladen" button

#### Key Feature: Vision JSON Context Propagation

Enable complex queries like: *"Recherchiere die Nebenwirkungen des ersten Medikaments auf der Liste"* (Research side effects of the first medication on the list) - where the medication name is extracted from an uploaded image.

**Example Flow:**
1. Upload medication plan image → Vision-LLM extracts table with 8 medications
2. User asks: *"Recherchiere die Nebenwirkungen des ersten Medikaments"*
3. Query Optimizer receives Vision JSON → Resolves "erstes Medikament" → "Acetylsalicylsäure"
4. Web research: "Acetylsalicylsäure Nebenwirkungen 2025"
5. Main-LLM generates comprehensive answer with sources

#### Added

- **Vision JSON Context Propagation** ([7 files modified]()):
  - Vision JSON automatically passed through entire research pipeline
  - Query Optimizer receives structured data for reference resolution
  - Main-LLM gets Vision JSON as system context for interpretation

- **Two-Phase Vision Architecture** ([state.py:1788-1982](aifred/state.py#L1788-L1982)):
  - **Phase 1:** Vision-LLM extraction (processes ONLY vision items: thinking, response, done, vision_complete)
  - **Phase 2:** Automatik/Research flow (if user text present)
  - Clean separation: Vision loop → Break → Automatik call
  - No race conditions, no duplicate messages

- **Enhanced Query Optimization Prompts**:
  - [prompts/de/query_optimization.txt](prompts/de/query_optimization.txt#L10-L11): Vision JSON awareness
  - [prompts/en/query_optimization.txt](prompts/en/query_optimization.txt#L10-L11): Vision JSON awareness
  - Example: "Recherchiere Nebenwirkungen des ersten Medikaments" + JSON → "Acetylsalicylsäure Nebenwirkungen 2025"

- **Enhanced Automatik Decision Prompts**:
  - [prompts/de/decision_making.txt](prompts/de/decision_making.txt#L1): `{vision_json_context}` placeholder
  - [prompts/en/decision_making.txt](prompts/en/decision_making.txt#L1): `{vision_json_context}` placeholder
  - Automatik-LLM sees Vision JSON for informed research decisions

#### Changed

- **Vision Pipeline Simplification** ([conversation_handler.py:487-500](aifred/lib/conversation_handler.py#L487-L500)):
  - Removed `chat_interactive_mode` call from Vision pipeline
  - Now only yields `vision_complete` signal with `has_user_text` flag
  - state.py handles routing decision (cleaner architecture)

- **Query Optimizer Function Signature** ([query_optimizer.py:22-55](aifred/lib/query_optimizer.py#L22-L55)):
  - Added `vision_json_context: Optional[Dict] = None` parameter
  - Passes Vision JSON to prompt builder

- **Research Query Processor** ([query_processor.py:142-167](aifred/lib/research/query_processor.py#L142-L167)):
  - `process_query_and_search()` accepts `vision_json_context` parameter
  - Forwards Vision JSON to Query Optimizer in all modes (Direct, Hybrid, Normal)

- **Prompt Loader** ([prompt_loader.py:198-219](aifred/lib/prompt_loader.py#L198-L219)):
  - `get_decision_making_prompt()` accepts `vision_json` parameter
  - `get_query_optimization_prompt()` accepts `vision_json` parameter
  - Injects Vision JSON into prompts when available

#### Fixed

- **Race Condition in Vision + Research Flow**:
  - **Problem:** conversation_handler.py called `chat_interactive_mode(history=state.chat_history)` BEFORE state.py processed `vision_complete` signal
  - **Result:** Research pipeline didn't see Vision-Entry in history
  - **Fix:** conversation_handler.py no longer calls chat_interactive_mode; state.py calls it AFTER vision_complete

- **Triple Message Duplication**:
  - **Problem:** Vision-Loop, Research Pipeline, and state.py all created separate history entries
  - **Fix:** Research Pipeline receives `history[:-1]` (excludes temp entry), creates single final entry

- **Missing Progress Updates in UI** ([state.py:1954-1955](aifred/state.py#L1954-L1955)):
  - Added `yield` after progress handler (was missing)
  - Scraping status messages now displayed in UI

#### Technical Implementation

**Files Modified:**
1. [aifred/state.py](aifred/state.py#L1788-L1982) - Two-phase Vision → Automatik flow
2. [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py#L487-L500) - Vision pipeline simplification
3. [aifred/lib/query_optimizer.py](aifred/lib/query_optimizer.py#L22-L55) - Vision JSON parameter
4. [aifred/lib/research/query_processor.py](aifred/lib/research/query_processor.py#L142-L167) - Vision JSON propagation
5. [aifred/lib/prompt_loader.py](aifred/lib/prompt_loader.py#L198-L219) - Prompt builders
6. [prompts/de/query_optimization.txt](prompts/de/query_optimization.txt) - Vision JSON awareness
7. [prompts/en/query_optimization.txt](prompts/en/query_optimization.txt) - Vision JSON awareness
8. [prompts/de/decision_making.txt](prompts/de/decision_making.txt) - Vision JSON context
9. [prompts/en/decision_making.txt](prompts/en/decision_making.txt) - Vision JSON context

**Architecture:**
```
User uploads image + asks question
    ↓
PHASE 1: Vision-LLM (Pure OCR)
├─ Input: Image + System Prompt ONLY
├─ User text: STORED (not sent to Vision-LLM)
└─ Output: Structured JSON → vision_complete signal
    ↓
PHASE 2: Automatik-LLM (Decision with Vision Context)
├─ Input: User text + Vision JSON
├─ Decision: <search>yes/no</search>
└─ Example: "Recherchiere Nebenwirkungen von Aspirin" + JSON {"rows": [["Aspirin",...]]}
   → Recognizes medication from JSON → <search>yes</search>
    ↓
PHASE 3: Query Optimization (with Vision JSON)
├─ Input: User text + Vision JSON
├─ Resolves: "erstes Medikament" → "Acetylsalicylsäure" (from JSON row 0)
└─ Output: "Acetylsalicylsäure Nebenwirkungen 2025"
    ↓
PHASE 4: Web Research → Main-LLM (with Vision JSON)
├─ Input: Vision JSON + Research results + User text
└─ Output: Comprehensive answer with sources
```

**Performance:**
- Vision extraction: ~10s (104 tok/s, Ministral-3:8b)
- Query optimization: ~2s (Vision JSON context added)
- Web research: ~5s (6/7 URLs scraped)
- Main-LLM inference: ~23s (14.3k tokens context)
- **Total:** ~40s for complete Vision + Research flow

## [2.3.1] - 2025-12-04

### 🔍 Vision Model Intelligence (2025-12-04)

#### Added
- **Chat Template Detection** ([vision_utils.py](aifred/lib/vision_utils.py)):
  - `get_vision_model_capabilities()`: Single API call for template + context detection
  - Detects `{{ .Prompt }}` (simple) vs. `[SYSTEM_PROMPT]` (full chat support)
  - Auto-detects chat markers: `SYSTEM`, `INST`, `<|im_start|>`, etc.
  - Returns tuple: `(supports_chat_template, context_window_size)`

- **Smart Model Handling** ([conversation_handler.py](aifred/lib/conversation_handler.py)):
  - **Models WITH chat template** (Ministral, Qwen2): Use JSON extraction system prompt
  - **Models WITHOUT chat template** (DeepSeek-OCR, Qwen3-Coder): Skip system prompt + add default text
  - Default prompt for template-less models: "Extrahiere den Text." (DE) / "Extract the text." (EN)
  - Prevents empty inference (DeepSeek-OCR needs text to work)

- **Intrinsic Context Windows**:
  - Vision models now use full model context size (8K-32K)
  - No more 4K Ollama default truncation
  - Reads from model metadata: `deepseekocr.context_length`, `llama.context_length`, etc.

#### Changed
- **Corrected JSON in Collapsibles**:
  - `_json_to_readable()` now returns `tuple[str, dict]` (readable_text, corrected_json)
  - Collapsibles display **auto-corrected JSON**, not raw malformed output
  - Consistent with what's actually processed and sent to Main-LLM

- **Enhanced Error Correction** ([conversation_handler.py:165-185](aifred/lib/conversation_handler.py#L165-L185)):
  - **Nested Array Fix**: `{"columns": [["A", "B"]]}` → `{"columns": ["A", "B"]}`
  - **Header+Data Mix Fix**: `{"columns": [["H"], ["R1"], ["R2"]], "rows": []}` → Split correctly
  - **Ministral-3:3b Compatibility**: Handles malformed JSON with 9-element nested columns
  - **Ministral-3:8b**: Generates perfect JSON, no correction needed

- **Separator Line Positioning** ([state.py:1880-1884](aifred/state.py#L1880-L1884)):
  - Moved separator to AFTER history save (was before)
  - Now shows after "💾 History gespeichert" message
  - Consistent with Main-LLM flow

#### Fixed
- **TypeError Prevention** ([state.py:1820-1827](aifred/state.py#L1820-L1827)):
  - Type-safety check for `item["content"]` (was causing crashes)
  - Gracefully handles dict-typed content with warning log
  - Fallback to `str(content)` if type mismatch detected

- **Vision Model Persistence**:
  - Fixed validation logic to search entire model list (not just first element)
  - Vision model selection now correctly saved and restored across sessions

- **Separator Display**:
  - Separator now always shown (even for HTML fallback models like DeepSeek-OCR)
  - Was missing when `vision_json_response` was empty

#### Performance
- **Single API Call Optimization**:
  - Combined chat template + context window detection (was 2 separate calls)
  - Faster model capability detection (~50% reduction in API overhead)

#### Technical Details

**Model Compatibility Matrix:**

| Model | Template | System Prompt | Auto-Text | Context | JSON Quality |
|-------|----------|---------------|-----------|---------|--------------|
| Ministral-3:8b | `[SYSTEM_PROMPT]` | ✅ Yes | ❌ No | 32768 | ⭐⭐⭐⭐⭐ Perfect |
| Ministral-3:3b | `[SYSTEM_PROMPT]` | ✅ Yes | ❌ No | 32768 | ⚠️ Nested arrays |
| Qwen2-57b | `<\|im_start\|>` | ✅ Yes | ❌ No | 32768 | ⭐⭐⭐⭐⭐ Perfect |
| DeepSeek-OCR:3b | `{{ .Prompt }}` | ❌ No | ✅ Yes | 8192 | ❌ HTML output |
| Qwen3-Coder:30b | `{{ .Prompt }}` | ❌ No | ✅ Yes | 32768 | ❓ Untested |

**Performance Impact:**
- Ministral-3:8b: 9.3s (105.6 tok/s) - Perfect JSON, no corrections needed
- Ministral-3:3b: 3.8s (185.0 tok/s) - Fast but needs auto-correction
- DeepSeek-OCR:3b: 2.3s (312.4 tok/s) - Fastest, but HTML output (fallback works)

## [2.3.0] - 2025-12-03

### 📸 Vision/OCR Support (2025-12-03)

#### Added
- **Vision/OCR Integration** - Complete multimodal image analysis pipeline:
  - **3-Model Architecture**: Vision-LLM (OCR) → Main-LLM (interpretation) → Automatik-LLM (decisions)
  - **Drag & Drop Upload**: Images can be uploaded directly into chat via drag-and-drop or file picker
  - **Auto-Detection**: Automatically detects vision-capable models via backend metadata queries
    - Ollama: Checks `.vision.*` and `.sam.*` keys in model_info
    - vLLM/TabbyAPI: Reads `architectures` from HuggingFace config.json
    - KoboldCPP: Reads `general.architecture` from GGUF metadata
  - **Supported Models**: DeepSeek-OCR, Qwen3-VL, Ministral-3 (3B/8B/14B variants)
  - **Structured Output**: JSON extraction with 5 types (table, list, form, text, mixed)
  - **Smart Formatting**:
    - Collapsible JSON display: `📊 Strukturierte Daten (model-name)`
    - Automatic Markdown conversion (tables, lists, forms)
    - Metadata footer: `( Vision: 3.7s (192.4 tok/s) )`
  - **Performance**: 3-15s inference (85% faster prompts: 119 lines → 18 lines)
  - **Robust Parsing**: Auto-correction for malformed Vision-LLM output
    - Detects nested columns array and auto-splits into columns + rows
    - HTML-to-Markdown fallback for models that ignore system prompts
  - **Image Processing**: Auto-resize to 2048px, JPEG optimization (quality 85)
  - **History Management**: Stores formatted HTML for UI, preserves JSON for follow-up questions

- **Vision Model Selector** - Dedicated dropdown in UI for Vision-LLM selection
  - Shows only vision-capable models (metadata-based filtering)
  - Selection persisted per backend in settings.json
  - Independent from Main-LLM selection

- **New System Prompts**:
  - `prompts/de/vision_ocr.txt`: German OCR prompt (18 lines, optimized)
  - `prompts/en/vision_ocr.txt`: English OCR prompt (18 lines, optimized)

- **Documentation**:
  - `docs/VISION_OCR.md`: Comprehensive Vision/OCR documentation (600+ lines)
    - Architecture diagrams
    - Model benchmarks (performance testing with 7 models)
    - Usage examples
    - Troubleshooting guide
    - JSON format specifications
  - `docs/development/VISION_IMAGE_SUPPORT_PLAN.md`: Implementation plan (archived)

#### Changed
- **README.md**: Updated with Vision/OCR features
  - Added Vision-LLM to Core Features
  - Model recommendations for Vision-LLM (Ministral-3 series)
  - Updated version to 2.3.0

- **Context Manager** (`aifred/lib/context_manager.py`):
  - Modified `strip_thinking_blocks()` to only remove `<think>` tags
  - Preserves `<data>` tags (Vision JSON) during history compression

- **Formatting** (`aifred/lib/formatting.py`):
  - Added `<data>` block rendering (similar to `<think>` but with 📊 icon)
  - Removed inference time from Collapsible headers (now only in metadata footer)
  - Consistent formatting for `<think>` and `<data>` blocks

- **State Management** (`aifred/state.py`):
  - Added `vision_model` field with per-backend persistence
  - Fixed vision model selection bug (was always resetting to first available)
  - Vision pipeline now formats response after stream completion (like Main-LLM)
  - Metrics capture: tokens/s, inference time from backend `done` signal
  - Debug logging: Separator line + timing info after Vision-LLM completion

#### Fixed
- **Vision Model Persistence** - Vision model selection now correctly saved and restored
  - Bug: Validation logic always overwrote selection with first model in list
  - Fix: Search entire list for matching model, not just first element
  - Now correctly handles different model orders across backends

- **Collapsible Display** - Vision JSON now properly rendered in collapsible HTML
  - Bug: Chat history stored raw JSON, causing unformatted display
  - Fix: Store formatted response (Collapsible + Markdown + Metadata) in history
  - Metadata footer now appears below table: `( Vision: 3.7s (192.4 tok/s) )`

- **Malformed JSON Handling** - Auto-correction for common Vision-LLM errors
  - Bug: Some models nest entire table data in `columns` array
  - Fix: Detect `columns[0]` as array → split into proper columns + rows structure
  - Graceful fallback to raw output if all parsing fails

- **HTML Output Handling** - Fallback for models that ignore system prompts
  - Bug: DeepSeek-OCR outputs HTML tables instead of JSON
  - Fix: HTML parser converts `<table>` to Markdown automatically
  - Still displays formatted table despite wrong output format

#### Performance Benchmarks
Model performance on medication plan image (465 KB, Ollama, RTX 4090):

| Model | Inference | Tokens | tok/s | Quality |
|-------|-----------|--------|-------|---------|
| Ministral-3:3b | 9.8s | 313 | 192 | ⭐⭐⭐⭐ |
| Ministral-3:8b | 14.4s | 421 | 184 | ⭐⭐⭐⭐⭐ |
| Ministral-3:14b | 59.9s | 349 | 98 | ⭐⭐⭐⭐⭐ |
| DeepSeek-OCR:3b | 4.3s | 0* | - | ❌ HTML |
| Qwen3-VL:8b | 56.6s | 0 | - | ❌ Empty |

\* Outputs HTML instead of JSON

#### Technical Details
- **Multimodal Messages**: Support for mixed text + image content arrays
- **Base64 Encoding**: Images converted to data URLs for API compatibility
- **Backend Integration**: Works with Ollama (tested), vLLM, TabbyAPI, KoboldCPP
- **Error Correction**: Robust JSON parsing with multiple fallback strategies
- **Streaming**: Non-streaming for Vision-LLM (prevents fragment display)

#### Files Modified
- `aifred/state.py`: Vision pipeline, model persistence, metrics capture
- `aifred/lib/conversation_handler.py`: Vision extraction, JSON parsing, HTML fallback
- `aifred/lib/formatting.py`: `<data>` block rendering, header time removal
- `aifred/lib/context_manager.py`: `<data>` tag preservation
- `aifred/lib/vision_utils.py`: Vision model detection (new file)
- `prompts/de/vision_ocr.txt`: Optimized OCR prompt (85% shorter)
- `prompts/en/vision_ocr.txt`: Optimized OCR prompt (85% shorter)
- `README.md`: Vision/OCR features documentation
- `docs/VISION_OCR.md`: Comprehensive technical documentation (new file)

---

## [2.2.0] - 2025-12-02

### 📚 Documentation & Configuration (2025-12-02)

#### Changed
- **Documentation Refactoring** - Complete restructuring for better maintainability:
  - **READMEs Cleaned Up**: Removed detailed changelog sections from README.md and README.de.md
  - Replaced with concise "What's New" section linking to CHANGELOG.md
  - README now focuses purely on project description and features
  - **Session Changelogs Archived**: Moved to `docs/archive/session-changelogs/`
    - CHANGELOG_2025-11-01.md, CHANGELOG_2025-11-02.md, CHANGELOG_2025-11-02_Session4.md
    - CHANGELOG_tokens_per_sec_uniformity.md
  - **PDF Duplicates Removed** (118KB freed):
    - Deleted vllm_pascal_patches.pdf and multi_agent_research_technical.pdf
    - Markdown versions remain as source of truth in `docs/research/`
  - **docs/INDEX.md Updated**: New archive/ directory structure documented

- **GPU Display Enhancements**:
  - Multi-GPU support: "2x Tesla P40 (Compute 6.1, 48 GB total)"
  - Single GPU format: "Tesla P40 (Compute 6.1, 24 GB)"
  - **Nominal VRAM Values**: Shows marketing specs (48 GB) instead of actual available (45 GB)
  - GPU info now displayed in Settings UI, startup log, and debug console
  - Added `gpu_count`, `gpu_vram_gb`, and `gpu_display_text` computed property

- **Ollama Configuration Documented** ([aifred/lib/config.py](aifred/lib/config.py)):
  - Comprehensive documentation of Ollama systemd environment variables
  - Explains current setup: 2x Tesla P40 with `OLLAMA_MAX_LOADED_MODELS=2`
  - Notes that MAX_LOADED_MODELS=2 is perfect for future Dual-LLM Debate System
  - Instructions for modifying `/etc/systemd/system/ollama.service.d/override.conf`

#### Fixed
- **Model Display Bug** ([aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py), [aifred/lib/research/query_processor.py](aifred/lib/research/query_processor.py)):
  - Fixed Ollama 500 Internal Server Error when passing model names with size suffix
  - Added `extract_model_name()` helper to remove " (X.X GB)" before backend API calls
  - Model names with sizes (e.g., "qwen3:4b (2.3 GB)") now correctly converted to pure names

#### Files Modified (2025-12-02)
- README.md, README.de.md: Changelog sections removed (-66 lines)
- docs/INDEX.md: Updated structure with archive directory
- aifred/state.py: GPU display fields and computed properties
- aifred/lib/gpu_detection.py: Multi-GPU detection with total VRAM
- aifred/aifred.py: GPU display in Settings UI
- aifred/lib/config.py: Ollama systemd configuration documentation
- aifred/lib/conversation_handler.py: Model name extraction
- aifred/lib/research/query_processor.py: Model name extraction

---

### ⚡ KoboldCPP Auto-Shutdown: Rolling Window Monitoring (2025-11-30)

#### Changed
- **Rolling Window Inactivity Monitoring** ([aifred/state.py:966-1086](aifred/state.py#L966-L1086)):
  - **Simplified Logic**: Replaced complex "Simple Reset" approach with clean Rolling Window pattern
  - **Continuous Checking**: GPU checks every 60s (was: 10s) from start to finish
  - **Responsive Timer Reset**: Any GPU activity resets counter with debug message
  - **"Bedenkzeit" Use Case**: User has full timeout duration after inference to start new query
  - **Example**: 5min timeout = 5 consecutive idle checks à 60s
    - Inferenz finishes at 16:22 → idle checks at 16:23, 16:24, 16:25, 16:26, 16:27 → shutdown at 16:27
    - New inference at 16:25 → counter reset (was 3/5) → new 5min timer starts after inference

- **Updated Configuration** ([aifred/lib/config.py:234-248](aifred/lib/config.py#L234-L248)):
  - `KOBOLDCPP_INACTIVITY_TIMEOUT = 300` (5 minutes for testing, was: 30s)
  - `KOBOLDCPP_INACTIVITY_CHECK_INTERVAL = 60` (1 minute, was: 10s)
  - Added Rolling Window documentation to config comments

#### Technical Details
- **Before (Complex)**:
  - Wait period (timeout - 30s) with activity detection
  - Final 30s with separate check loop
  - Nested loops, activity detection during wait
  - ~130 lines of code
- **After (Simple)**:
  - Single while loop with 60s sleep
  - Continuous checks with consecutive idle counter
  - GPU activity → reset counter + debug message
  - ~100 lines of code (-23% reduction)
- **Debug Message**: `🔄 GPU activity detected - idle timer reset (was at X/5 checks)`

#### Impact
- **Simpler Code**: Single loop instead of nested wait + check loops
- **More Efficient**: 60s intervals (6x less CPU/GPU queries than 10s)
- **Better UX**: User sees timer reset messages when new inference starts
- **Accurate Timeout**: Integer division ensures exact timeout (300s = 5 × 60s)

#### Files Modified
- [aifred/state.py](aifred/state.py): Lines 966-1086 (complete function rewrite)
- [aifred/lib/config.py](aifred/lib/config.py): Lines 234-248 (updated config + docs)

---

## [Unreleased] - 2025-11-29

### 🔔 KoboldCPP Auto-Shutdown: Debug Console Messages (Fixed)

#### Changed
- **Unified Logging System for Auto-Shutdown** ([aifred/lib/inactivity_monitor.py:31-32, 60-76, 240-252](aifred/lib/inactivity_monitor.py#L60-L76)):
  - **Fixed**: Shutdown messages now correctly appear in Debug Console UI
  - **Removed**: Custom `debug_callback` parameter (was bypassing queue system)
  - **Solution**: Direct use of `log_message()` from `logging_utils`
  - `log_message()` automatically writes to BOTH:
    - `/logs/aifred_debug.log` (file logging)
    - `_message_queue` (UI Debug Console via queue polling)
  - **Removed**: GPU statistics message (user request)
  - **Example Messages** (now visible in Debug Console):
    - `🛑 KoboldCPP wird wegen Inaktivität heruntergefahren (GPUs waren 30s idle, Timeout: 30s)`
    - `✅ KoboldCPP erfolgreich heruntergefahren`

#### Technical Details
- **Root Cause**: Custom callback was bypassing the `_message_queue` used by UI polling
- **Fix**: Use existing `log_message()` function that writes to queue when `CONSOLE_DEBUG_ENABLED=True`
- **Pattern**: Follows same approach as all other logging throughout the codebase
- **Removed Code**:
  - `Callable` import (no longer needed)
  - `debug_callback` parameter from `__init__`
  - Conditional callback logic in shutdown messages
  - GPU statistics line: `GPU-Statistik: X aktiv / Y idle Checks`

#### Impact
- **Before**: Messages appeared in log file but NOT in Debug Console UI
- **After**: Real-time shutdown notifications in BOTH log file AND Debug Console UI
- **Simpler**: No custom callbacks - uses unified logging system
- **Cleaner**: Removed unnecessary GPU statistics message

#### Files Modified
- [aifred/lib/inactivity_monitor.py](aifred/lib/inactivity_monitor.py): Lines 31-32, 60-76, 240-252
- [aifred/state.py](aifred/state.py): Line 1174-1178 (removed `debug_callback` parameter)

---

## [Unreleased] - 2025-11-25

### 🧠 Automatik-LLM: Thinking Model Compatibility & Robust Fallbacks

#### Added
- **Query Optimization Fallback** ([aifred/lib/query_optimizer.py:118-124](aifred/lib/query_optimizer.py#L118-L124)):
  - Empty query detection when Thinking Models fail to produce keywords
  - Falls back to original user query instead of empty search
  - Preserves full question with temporal context (e.g., "Wie wird das Wetter morgen?" → adds "2025")
  - Ensures web search always works, even with suboptimal models

- **`enable_thinking` Toggle Propagation** ([aifred/lib/conversation_handler.py:631-636](aifred/lib/conversation_handler.py#L631-L636), [aifred/lib/intent_detector.py:77-82](aifred/lib/intent_detector.py#L77-L82), [aifred/lib/query_optimizer.py:81-86](aifred/lib/query_optimizer.py#L81-L86)):
  - User's thinking toggle now propagates to all Automatik-LLM tasks
  - Explicit logging shows when toggle is active vs. default
  - Default: `enable_thinking: False` (fast mode without reasoning)
  - Allows debugging Thinking Model behavior when needed

#### Changed
- **Optimized `num_predict` Values** for Automatik-LLM tasks:
  - Decision-Making: 256 → **64 tokens** (`<search>yes</search>` = ~20 tokens, 3x buffer)
  - Intent Detection: 256 → **32 tokens** (`FAKTISCH`/`KREATIV` = ~10 tokens, 3x buffer)
  - Query Optimization: 512 → **128 tokens** (keywords = ~30 tokens, 4x buffer)
  - Minimizes generation time while maintaining sufficient headroom
  - Reduces VRAM waste for short, structured outputs

- **Removed Redundant Log** ([aifred/backends/koboldcpp.py:383-384](aifred/backends/koboldcpp.py#L383-L384)):
  - Removed "💾 KoboldCPP Context: X tokens (from global state)" message
  - Context is already logged during server startup
  - Reduces console clutter on every request

#### Known Issues
- **Thinking Models Incompatible with Automatik-LLM**:
  - Thinking Models (e.g., QwQ-32B, DeepSeek-R1) ignore `enable_thinking: False`
  - Always output `<think>` tags and verbose reasoning
  - Exceed `num_predict` limits before reaching expected output
  - **Impact**: Query-Opt produces empty string (fallback works), Decision-Making may fail
  - **Recommendation**: Use Instruct models for Automatik-LLM, Thinking models for main LLM only
  - **Technical Details**:
    - With `num_predict: 64`, Decision-Making works if `enable_thinking: True` (compact reasoning)
    - With `num_predict: 128`, Query-Opt always fails (reasoning too verbose)
    - Models trained to reason cannot be suppressed by flags or prompts

### 🎯 KoboldCPP Dynamic RoPE Scaling & VRAM Optimization

#### Added
- **KoboldCPP Backend Support** ([aifred/backends/koboldcpp.py](aifred/backends/koboldcpp.py)):
  - Full KoboldCPP integration as fourth backend (alongside Ollama, vLLM, TabbyAPI)
  - Auto-start functionality with intelligent VRAM-based context calculation
  - Dynamic RoPE (Rotary Position Embedding) scaling for context extension
  - Single-pass optimization: calculates optimal context + RoPE factor before first start
  - OOM retry strategy with automatic MB/token adjustment

- **Intelligent Context + RoPE Calculation** ([aifred/lib/koboldcpp_manager.py:443-534](aifred/lib/koboldcpp_manager.py#L443-L534)):
  - New `calculate_optimal_context_and_rope()` method for VRAM-based optimization
  - Automatically determines if RoPE scaling is beneficial or if context is VRAM-limited
  - **Logic**:
    - If `max_tokens > native_context`: Apply RoPE scaling (extend context beyond native)
    - If `max_tokens ≤ native_context`: Use available VRAM without RoPE (VRAM-limited)
  - Caps RoPE factor at configurable maximum (default: 2.0x)
  - Caps context at KoboldCPP hard limit (262,144 tokens)

- **GGUF Metadata Utilities** ([aifred/lib/gguf_utils.py](aifred/lib/gguf_utils.py), [aifred/lib/gguf_utils_vision.py](aifred/lib/gguf_utils_vision.py)):
  - Extract native context from GGUF files (avoids hardcoded values)
  - Detect architecture (Qwen2, Llama, etc.) for accurate KV cache calculation
  - Extract quantization level from filename (Q4_K_M, Q8_0, etc.)
  - Calculate MB/token for KV cache based on architecture + quantization
  - Vision model support: VL models use same KV cache as text models (no multiplier)

- **Configuration Options** ([aifred/lib/config.py:228-259](aifred/lib/config.py#L228-L259)):
  ```python
  KOBOLDCPP_TARGET_FREE_VRAM_MB = 600        # Target free VRAM after start
  KOBOLDCPP_SAFETY_MARGIN_MB = 150           # CUDA scratch buffer (fixed)
  KOBOLDCPP_MAX_ROPE_FACTOR = 2.0            # Maximum RoPE scaling factor
  KOBOLDCPP_OOM_RETRY_MB_PER_TOKEN_ADJUSTMENT = 0.10  # 10% more conservative per retry
  KOBOLDCPP_MAX_OOM_RETRIES = 3              # Maximum retry attempts
  ```

#### Changed
- **Removed vLLM/TabbyAPI/KoboldCPP Automatik-LLM Messages** ([aifred/state.py:561,730,2130](aifred/state.py)):
  - Removed verbose "🔄 Automatik-LLM angepasst..." debug messages
  - These backends can only load one model - adjustment happens silently
  - Reduces console clutter and prevents horizontal scrolling

#### Fixed
- **KoboldCPP RoPE Calculation Bugs** (3 critical fixes):
  - **Bug #1**: Added KoboldCPP maximum context cap (262,144 tokens) - prevented exceeding hard limit
  - **Bug #2**: Removed incorrect `--overridenativecontext` parameter - was using wrong value
  - **Bug #3**: Fixed scope error with `log_feedback()` - replaced with `logger.info()` in calculation method

#### Technical Details

**RoPE Scaling Strategy:**
- **Small Models** (32k native context): Benefit from RoPE extension
  - Example: Qwen3-14B (32k native) → 65k with RoPE 2.0x @ RTX 3090 Ti
- **Large Models** (262k native context): Already at maximum
  - Example: Qwen3-VL-8B (262k native) → No RoPE needed, at KoboldCPP limit

**VRAM Calculation:**
```python
usable_vram = total_vram - model_size - safety_margin - target_free_vram
max_tokens = usable_vram / mb_per_token

if max_tokens > native_context:
    rope_factor = max_tokens / native_context  # Extend beyond native
    context = min(max_tokens, 262144)          # Cap at KoboldCPP max
else:
    rope_factor = 1.0                          # No RoPE, VRAM-limited
    context = max_tokens
```

**OOM Retry Strategy:**
If initial calculation is too optimistic:
1. Attempt 1: Optimal calculation with measured MB/token
2. Attempt 2: +10% more conservative MB/token → recalculate
3. Attempt 3: +10% again → recalculate
4. Fail after 3 attempts

**KV Cache Optimization:**
- Q4 quantization: 0.05 MB/token (75% savings vs FP16)
- Vision models: Same KV cache as text (vision encoder separate)
- Architecture-aware: Dense vs MoE models handled correctly

#### Files Modified
- [aifred/backends/koboldcpp.py](aifred/backends/koboldcpp.py): Complete backend implementation
- [aifred/lib/koboldcpp_manager.py](aifred/lib/koboldcpp_manager.py): Process management + optimization
- [aifred/lib/gguf_utils.py](aifred/lib/gguf_utils.py): GGUF metadata extraction
- [aifred/lib/gguf_utils_vision.py](aifred/lib/gguf_utils_vision.py): Architecture detection + KV cache calculation
- [aifred/lib/config.py](aifred/lib/config.py): KoboldCPP configuration constants
- [aifred/state.py](aifred/state.py): Removed verbose Automatik-LLM sync messages (3 locations)

#### Performance Results
**RTX 3090 Ti (24GB VRAM):**
- Qwen3-VL-8B (8.5 GB): 262,144 tokens (maximum, no RoPE needed)
- Qwen3-14B (8 GB): 65,536 tokens (32k native × 2.0 RoPE)
- Target free VRAM: ~600 MB (optimal for stability)

---

## [2.1.0] - 2025-11-22

### 🚀 Major Features

#### Unified VRAM Cache System
- **Created**: `aifred/lib/model_vram_cache.py` - Unified cache combining vLLM calibrations and VRAM ratio measurements
- **Backend-Aware Structure**: Single cache file with per-backend model tracking (Ollama/vLLM/TabbyAPI)
- **Automatic Migration**: Old `vllm_context_cache.json` automatically migrated to new unified format on first load
- **Universal VRAM Ratio Tracking**: Measures MB/token for ALL backends (Ollama active, vLLM/TabbyAPI for validation)
- **Architecture Detection**: Separate ratios for MoE vs Dense models (0.10 vs 0.15 MB/token)

### Added

#### Model VRAM Cache Functions
- **`load_cache()`**: Loads unified cache with automatic migration from old vLLM cache
- **`add_vram_measurement()`**: Records VRAM ratio measurements for any backend (with backend parameter)
- **`get_calibrated_ratio()`**: Returns measured MB/token ratio or default fallback
- **`add_vllm_calibration()`**: Stores vLLM-specific context calibration points
- **`interpolate_vllm_context()`**: Linear interpolation for vLLM context limits at different VRAM levels
- **`get_measurement_count()`**: Returns number of VRAM measurements for a model

#### Cache File Structure
```json
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
    "vllm_calibrations": [
      {
        "free_vram_mb": 22968,
        "max_context": 21608,
        "measured_at": "2025-11-21T23:31:17"
      }
    ]
  }
}
```

- **Dynamic Context Window Optimization** ([aifred/lib/context_manager.py:184-187](aifred/lib/context_manager.py#L184-L187)):
  - Removed fixed context size rounding (2K, 4K, 8K, etc.)
  - Now uses exact calculated `num_ctx` values for maximum efficiency
  - Automatically utilizes full VRAM-based limit for large contexts
  - **Example**: 42K needed → Uses 42K directly (instead of rounding to 64K or capping at 40K)
  - **Benefit**: ~7-10% more context available for long conversations without wasting RAM

- **Ollama: Loaded Model Context Detection** ([aifred/backends/ollama.py:610-640](aifred/backends/ollama.py#L610-L640)):
  - New `get_loaded_model_context()` method queries `/api/ps` for actual context length
  - Returns the exact `num_ctx` value a loaded model is using
  - Used for accurate history compression limits

### Changed

#### Updated All VRAM Cache Imports (6 Files Modified)
- **`aifred/lib/gpu_utils.py`** (Line 243):
  - Changed: `from .vram_ratio_cache import ...` → `from .model_vram_cache import ...`
  - Functions: `get_calibrated_ratio`, `get_measurement_count`

- **`aifred/lib/conversation_handler.py`** (Lines 498-513):
  - Changed: `from aifred.lib.vram_ratio_cache import add_measurement` → `from aifred.lib.model_vram_cache import add_vram_measurement`
  - **NEW Parameter**: Added `backend=backend_type` to measurement calls
  - Impact: VRAM measurements now backend-aware for Ollama/vLLM/TabbyAPI

- **`aifred/lib/vllm_manager.py`** (5 locations - lines 503, 557, 603, 780, 831):
  - Changed: `from aifred.lib.vllm_context_cache import ...` → `from aifred.lib.model_vram_cache import ...`
  - Function renames:
    - `interpolate_context` → `interpolate_vllm_context as interpolate_context`
    - `add_calibration_point` → `add_vllm_calibration as add_calibration_point`

- **`aifred/lib/vllm_utils.py`** (Lines 48, 75):
  - Changed: `from .vllm_context_cache import ...` → `from .model_vram_cache import ...`
  - Function renames:
    - `get_calibrations` → `get_vllm_calibrations as get_calibrations`
    - `interpolate_context` → `interpolate_vllm_context as interpolate_context`

### Removed

- **Deleted Old Cache Modules** (No backward compatibility per user requirement):
  - `aifred/lib/vram_ratio_cache.py` - Replaced by unified cache
  - `aifred/lib/vllm_context_cache.py` - Replaced by unified cache
  - `~/.config/aifred/vllm_context_cache.json` - Automatically migrated to `model_vram_cache.json`

### Fixed

#### Critical Web Research Crash - ValueError in Scraper Orchestrator
- **Problem**: `ValueError: too many values to unpack (expected 2)` during web research
- **Location**: [aifred/lib/research/scraper_orchestrator.py:158](aifred/lib/research/scraper_orchestrator.py#L158)
- **Root Cause**:
  - Line 84 `unload_and_preload()` returns 3 values: `(success, load_time, models)`
  - Line 128 correctly unpacks 3 values in the first code path
  - Line 158 **incorrectly** only unpacked 2 values: `success, load_time = await preload_task`
- **Impact**: Web research would crash when Main-LLM preload finished after scraping completed
- **Fix Applied**:
  ```python
  # Before (Line 158)
  success, load_time = await preload_task

  # After (Line 158-162)
  success, load_time, unloaded_models = await preload_task
  if unloaded_models:
      models_str = ", ".join(unloaded_models)
      log_message(f"🗑️ Entladene Modelle: {models_str}")
      yield {"type": "debug", "message": f"🗑️ Entladene Modelle: {models_str}"}
  ```
- **Additional Enhancement**: Now properly logs unloaded models in both code paths (lines 126-135, 158-169)
- **Testing**: Syntax validated with `python3 -m py_compile`

### Technical Details

#### Files Modified (7 total)
1. **Created**: [aifred/lib/model_vram_cache.py](aifred/lib/model_vram_cache.py) (420 lines)
   - Unified cache management with automatic migration
   - VRAM ratio tracking for all backends
   - vLLM calibration with linear interpolation

2. **Modified**: [aifred/lib/gpu_utils.py](aifred/lib/gpu_utils.py) (Line 243)
   - Updated imports from old `vram_ratio_cache` to `model_vram_cache`

3. **Modified**: [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py) (Lines 498-513)
   - Added `backend` parameter to VRAM measurement calls
   - Backend-aware measurement storage

4. **Modified**: [aifred/lib/vllm_manager.py](aifred/lib/vllm_manager.py) (5 locations)
   - Updated all vLLM cache function imports
   - Function alias mapping for compatibility

5. **Modified**: [aifred/lib/vllm_utils.py](aifred/lib/vllm_utils.py) (2 locations)
   - Updated vLLM utility imports

6. **Modified**: [aifred/lib/research/scraper_orchestrator.py](aifred/lib/research/scraper_orchestrator.py) (Lines 158-169)
   - **CRITICAL FIX**: Corrected async task unpacking
   - Added unloaded models logging

7. **Deleted**: `aifred/lib/vram_ratio_cache.py` - Functionality moved to unified cache
8. **Deleted**: `aifred/lib/vllm_context_cache.py` - Functionality moved to unified cache
9. **Deleted**: `~/.config/aifred/vllm_context_cache.json` - Auto-migrated to `model_vram_cache.json`

#### Cache Migration Details
- **Automatic**: No user intervention required
- **One-Time**: Migration runs on first `load_cache()` call
- **Data Preservation**: All vLLM calibrations preserved
- **Format**: 5 models migrated (Qwen3-8B-AWQ, Qwen3-4B, Qwen2.5-3B, Qwen3-4B-AWQ, Qwen3-30B-A3B-AWQ)
- **Location**: `~/.config/aifred/model_vram_cache.json`

#### Performance Impact
- **VRAM Optimization**: More accurate context limits with calibrated ratios
- **Bug Fix Impact**: Web research stability improved (no more mid-research crashes)
- **Cache Efficiency**: Single cache file instead of two separate files
- **Future-Ready**: Extensible for new backends (e.g., LM Studio, LocalAI)

#### GPU Performance Observations
- **MoE Models** (Qwen3-30B-A3B): 17-21% → 59-60% GPU utilization (prefill → generation)
  - Speed: 61.4 tok/s
  - Power: 117-221W
  - VRAM: 22.8 GB
  - **Reason**: Sparse activation (10-20% active parameters), memory-bound operation

- **Dense Models** (Qwen3-32B): 14-37% → 83-95% GPU utilization (prefill → generation)
  - Speed: 31.9 tok/s (50% slower)
  - Power: 118-446W (2x power consumption)
  - VRAM: 23.9 GB
  - **Reason**: All parameters active, compute-bound operation

- **Conclusion**: MoE ~60% GPU utilization at double the speed is expected and optimal behavior

### Changed (History Compression)
- **History Compression Context Limit** ([aifred/state.py:1404-1444](aifred/state.py#L1404-L1444)):
  - **Ollama**: Now uses `/api/ps` to get actual loaded model context (e.g., 40960 or 44051)
  - **vLLM/TabbyAPI**: Uses `calculate_dynamic_num_ctx()` for consistent limit calculation
  - **Result**: History percentage now shows accurate utilization
  - **Before**: "2,169 / 7,505 tok (28%)" ❌ (wrong VRAM calculation)
  - **After**: "2,169 / 40,960 tok (5%)" ✅ (actual model context)

### Fixed
- **vLLM Context Calibration Safety Buffer** ([aifred/lib/vllm_manager.py:537-544, 666-673](aifred/lib/vllm_manager.py#L537-L544)):
  - Changed from fixed 150 token buffer to 2% percentage-based safety margin
  - Applied iteratively at each calibration attempt
  - **Before**: 3 attempts needed, 150 tokens wasted regardless of context size
  - **After**: 2 attempts, scales with context (e.g., 440 tokens at 22K context)
  - **Result**: More efficient calibration with better success rate

- **vLLM: Automatik-LLM Synchronization** ([aifred/state.py:460-466, 566-571, 1786-1822](aifred/state.py#L1786-L1822)):
  - vLLM can only load ONE model at a time (unlike Ollama)
  - Now automatically syncs Automatik-LLM to match Main-LLM for vLLM backend
  - Applied at three points: model change, backend init (slow path), backend init (fast path)
  - **Before**: 404 errors when Automatik-LLM differed from Main-LLM
  - **After**: Automatic sync with debug message explaining why

- **YaRN Factor Reset on Model Change** ([aifred/state.py:1786-1822](aifred/state.py#L1786-L1822)):
  - YaRN factor now automatically resets to 1.0 when changing models
  - Prevents crashes from trying to load new model with old YaRN extension
  - Resets all YaRN state: factor, input, max_factor, max_tested
  - Shows loading spinner during model change (40-70 seconds for vLLM)

## [Unreleased] - 2025-11-18

### Changed
- **UI Layout Optimization** ([aifred/aifred.py:1486-1506](aifred/aifred.py#L1486-L1506)):
  - Improved usability by reordering main UI components
  - **New order**: Chat History → Input Controls → Debug Console & Settings
  - **Benefit**: After reading conversation, text input is directly accessible without scrolling
  - Debug console moved to bottom for quick access when needed

- **Query Optimization: URL Handling** ([prompts/de/query_optimization.txt](prompts/de/query_optimization.txt), [prompts/en/query_optimization.txt](prompts/en/query_optimization.txt)):
  - Enhanced query optimization to preserve URLs completely
  - **New rule**: URLs and web addresses (https://, www., domain.com, github.com/...) are returned UNFILTERED
  - **Examples added**: github.com/user/repo, example.com/blog/article
  - **Benefit**: Web search modes (quick/detailed) can now handle URL-based queries correctly without breaking them into keywords

### Fixed
- **Model Preload Order** ([aifred/backends/ollama.py](aifred/backends/ollama.py), [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py), [aifred/lib/research/scraper_orchestrator.py](aifred/lib/research/scraper_orchestrator.py), [aifred/state.py:1066-1086](aifred/state.py#L1066-L1086)):
  - Fixed unnecessary model unload/reload during preload phase
  - **Problem**: `preload_model()` internally called `unload_all_models()`, which unloaded ALL models including the target model if already loaded
  - **Symptom**: Debug showed `🗑️ Entladene Modelle: qwen3:4b, qwen3:14b` (14B shouldn't be there!)
  - **Root Cause**: Sequence was Automatik-LLM decision → preload → unload ALL → reload target
  - **Solution**: Removed `unload_all_models()` from `preload_model()` internals, added explicit calls before preload in callers
  - **Impact**: Eliminates unnecessary model reload, clearer debug output, proper VRAM management
  - Changed return signature: `tuple[bool, float, list[str]]` → `tuple[bool, float]`
  - Correct order now: Automatik decision → explicit unload → load Haupt-LLM

---

### 🧠 VRAM-Based Dynamic Context Window Calculation

#### Added
- **Automatic VRAM-Based Context Calculation** ([aifred/lib/gpu_utils.py](aifred/lib/gpu_utils.py)):
  - Dynamically calculates maximum practical `num_ctx` based on available GPU memory
  - Prevents CPU offloading by staying within VRAM limits
  - Two-scenario detection: Model loaded vs not loaded (via `/api/ps` endpoint)
  - Reads model size from blob filesystem (no hardcoded values)
  - Safety margin: 512 MB (optimized from initial 1024 MB)
  - KV-cache ratio: 0.097 MB/token (empirically measured for Qwen3 MoE models)
  - **VRAM Stabilization Polling** ([aifred/lib/gpu_utils.py:138-169](aifred/lib/gpu_utils.py#L138-L169)):
    - Waits for VRAM to stabilize after model preload (prevents premature measurement)
    - Polls every 200ms, requires 2 consecutive stable readings (< 50 MB difference)
    - Maximum wait time: 3 seconds
    - Ensures accurate context calculation after Ollama finishes loading model into VRAM

- **Model Load Detection** ([aifred/lib/gpu_utils.py:22-56](aifred/lib/gpu_utils.py#L22-L56)):
  - `is_model_loaded()` checks Ollama `/api/ps` endpoint
  - Prevents double-subtraction of model size from free VRAM
  - Scenario 1 (model NOT loaded): `vram_for_context = free_vram - model_size - margin`
  - Scenario 2 (model IS loaded): `vram_for_context = free_vram - margin`

- **Model Size Extraction** ([aifred/backends/ollama.py:430-520](aifred/backends/ollama.py#L430-L520)):
  - Enhanced `get_model_context_limit()` to return `(context_limit, model_size_bytes)`
  - Extracts blob path from modelfile (`FROM /path/to/blobs/sha256-...`)
  - Reads actual file size from filesystem (e.g., 17.28 GB for qwen3:30b)
  - Falls back gracefully if blob not found (no VRAM calculation)

- **Automatic Model Unloading** ([aifred/backends/ollama.py:349-454](aifred/backends/ollama.py#L349-L454)):
  - **Problem**: Multiple models loaded simultaneously (e.g., Automatik 3B + Main 30B) consumed VRAM
  - **Solution**: `preload_model()` now unloads ALL other models before loading requested model
  - Uses `/api/ps` to detect loaded models, then sends `keep_alive=0` to unload each
  - Returns list of unloaded models for debug output
  - **Impact**: Ensures maximum VRAM available for context calculation (23GB → 35K tokens instead of 730MB → 7K tokens)
  - **UI Feedback**: Shows `🗑️ Entladene Modelle: qwen2.5:3b` in debug console
  - **Bug Fix**: Added required `prompt` field to `/api/generate` unload request (prevents preload failure with 0.0s time)

- **UI Integration** ([aifred/aifred.py:1151-1188](aifred/aifred.py#L1151-L1188)):
  - Manual context override option (numeric input field)
  - Checkbox: "Setze Context-Fenster auf Basis von VRAM"
  - Warning message when manual override active
  - Real-time VRAM debug messages in UI console

- **Debug Logging** ([aifred/lib/gpu_utils.py:196-236](aifred/lib/gpu_utils.py#L196-L236)):
  - Detailed VRAM calculation messages collected as list
  - Yielded to UI console for real-time visibility
  - Shows: Free VRAM, model size, safety margin, calculated context, architectural limit
  - German number formatting (35.010 T instead of 35,010T)
  - **Improved Readability**: Spaces between numbers and units (e.g., `3853 MB` instead of `3853MB`, `0.097 MB/T` instead of `0.097MB/T`)

#### Configuration
- **Optimized Constants** ([aifred/lib/config.py](aifred/lib/config.py)):
  - `VRAM_SAFETY_MARGIN = 512` (MB) - reduced from 1024 MB
  - `VRAM_CONTEXT_RATIO = 0.097` (MB/token) - empirically measured
  - `ENABLE_VRAM_CONTEXT_CALCULATION = True` - feature flag

#### Performance Results (RTX 3090 Ti, 24GB VRAM)
- **qwen3:30b-a3b-instruct-2507-q4_K_M** (17.28 GB):
  - Free VRAM: 3908 MB
  - Context for KV-cache: 3396 MB (after 512 MB safety margin)
  - **Calculated Context**: 35,010 tokens (3396 MB / 0.097 MB/T)
  - Model architectural limit: 262,144 tokens
  - **Practical limit**: 35,010 tokens (VRAM-constrained, prevents CPU offloading)

- **qwen3:32b-q4_K_M** (18.81 GB, older generation):
  - Free VRAM: 1780 MB (with Whisper loaded)
  - Context for KV-cache: 1268 MB
  - **Calculated Context**: 13,072 tokens
  - Model architectural limit: 40,960 tokens (only!)
  - **Problem**: Input 16K tokens → exceeds 13K limit → CPU offloading (17.6 t/s instead of 80+ t/s)
  - **Recommendation**: Use qwen3:30b-a3b instead (newer, larger context, smaller size)

#### Impact
- **Before**: Hardcoded context windows → frequent CPU offloading on large inputs
- **After**: Automatic adaptation to available VRAM → maximizes usable context
- **User Benefit**: No more manual tuning, system automatically prevents CPU offloading

#### Technical Details
- **VRAM Query**: Uses `nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits`
- **Model Load Detection**: HTTP GET to `http://localhost:11434/api/ps`
- **Fallback**: If VRAM calculation fails → use model's architectural limit
- **Validation**: Minimum 100 MB VRAM required, otherwise fallback to 2048 tokens

#### Files Modified
- [aifred/lib/gpu_utils.py](aifred/lib/gpu_utils.py): Lines 22-238 (VRAM calculation, stabilization polling, model load detection, improved debug formatting)
- [aifred/backends/ollama.py](aifred/backends/ollama.py): Lines 349-520 (automatic model unloading, model size extraction)
- [aifred/backends/base.py](aifred/backends/base.py): Lines 159-173 (preload_model signature updated)
- [aifred/backends/vllm.py](aifred/backends/vllm.py): Lines 221-239 (preload_model signature updated)
- [aifred/backends/tabbyapi.py](aifred/backends/tabbyapi.py): Lines 212-230 (preload_model signature updated)
- [aifred/lib/llm_client.py](aifred/lib/llm_client.py): Lines 183-198 (preload_model signature updated)
- [aifred/state.py](aifred/state.py): Lines 92, 556-603, 1017-1035, 1348-1372 (state management, preload with unload feedback, settings persistence)
- [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py): Lines 419-437 (Automatik mode with unload feedback)
- [aifred/lib/config.py](aifred/lib/config.py): Lines 168-171 (VRAM constants)
- [aifred/aifred.py](aifred/aifred.py): Lines 1151-1188 (UI integration)

---

### ✂️ Token Optimization: Redundant Date Line Removed

#### Changed
- **Prompt Timestamp Format** ([aifred/lib/prompt_loader.py:137-147](aifred/lib/prompt_loader.py#L137-L147)):
  - Removed redundant `- Jahr: {now.year}` line from German timestamp
  - Removed redundant `- Year: {now.year}` line from English timestamp
  - Date already contains full year (`16.11.2025` or `2025-11-16`)
  - Separate year line was wasting tokens without adding information

#### Impact
- **Token Savings**: ~15 tokens saved per prompt (affects ALL prompts across all modes)
- **Information Loss**: None - full date already shows year
- **User Experience**: Cleaner prompt headers, more efficient token usage

#### Files Modified
- [aifred/lib/prompt_loader.py](aifred/lib/prompt_loader.py): Lines 137-147 (timestamp generation)

---

## [Unreleased] - 2025-11-15

### 🔍 Enhanced Debug Logging & Query Visibility

#### Added
- **Consistent Debug Logging Across All Modes** ([aifred/state.py:1014-1030](aifred/state.py#L1014-L1030), [aifred/lib/conversation_handler.py:395-414](aifred/lib/conversation_handler.py#L395-L414)):
  - "Eigenes Wissen" mode now shows comprehensive debug messages matching Automatik mode style
  - LLM preloading messages with precise timing: `🚀 Haupt-LLM wird vorgeladen...` → `✅ Haupt-LLM vorgeladen (X.Xs)`
  - System prompt creation confirmation
  - Token statistics: `📊 Haupt-LLM: input / num_ctx Tokens (max: limit)`
  - Temperature settings display
  - TTFT (Time To First Token) measurement
  - Final completion stats with tokens/s

- **Precise Preload Time Measurement** ([aifred/state.py:1019-1030](aifred/state.py#L1019-L1030)):
  - Ollama backend: Actual model loading time via `backend.preload_model()` (1-5 seconds)
  - vLLM/TabbyAPI: Preparation time only (models stay in VRAM, 0.1-0.5 seconds)
  - Backend-aware timing ensures accurate performance metrics

- **Optimized Query Display in Debug Console** ([aifred/lib/research/query_processor.py:61](aifred/lib/research/query_processor.py#L61)):
  - Shows the LLM-optimized search query after query optimization completes
  - Enables quality assessment of web research queries
  - Visible in all web research modes (Automatik, Websuche schnell, Websuche ausführlich)
  - Format: `🔎 Optimierte Query: [optimized search terms]`

#### Enhanced
- **Web Research Modes Debug Output** ([aifred/lib/research/query_processor.py:43-61](aifred/lib/research/query_processor.py#L43-L61)):
  - Query optimization progress: `🔍 Query-Optimierung läuft...`
  - Completion with timing: `✅ Query-Optimierung fertig (X.Xs)`
  - Optimized query display for quality assessment

#### Impact
- **Before**: Debug output varied significantly between modes, making performance comparison difficult
- **After**: All modes show consistent, detailed debug information for easier troubleshooting and optimization
- **User Benefit**: Better visibility into AIfred's internal processes, easier quality assessment of web searches

#### Files Modified
- [aifred/state.py](aifred/state.py): Lines 982-1030, 1036-1093 (Eigenes Wissen mode logging)
- [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py): Lines 356-417 (Automatik mode logging)
- [aifred/lib/research/query_processor.py](aifred/lib/research/query_processor.py): Line 61 (optimized query display)

---

## [Unreleased] - 2025-11-14

### Fix: Research Mode Persistence

#### Fixed
- **Research Mode not persisted** ([aifred/state.py:1314](aifred/state.py#L1314)):
  - `set_research_mode_display()` changed the variable but didn't call `_save_settings()`
  - Settings infrastructure was complete (load + save to dict), only the trigger was missing
  - Inconsistent with other setters like `set_automatik_model()` which correctly save
  - Now calls `_save_settings()` after mode change to persist immediately

#### How it works
1. **Startup**: Loads `research_mode` from `settings.json` (Line 219) or falls back to `"automatik"` from `config.py`
2. **User changes mode**: UI calls `set_research_mode_display()` → `_save_settings()` → `settings.json` updated
3. **Next startup**: Saved mode is restored correctly

#### Impact
- **Before**: Research mode reset to default on every restart
- **After**: Research mode persists across sessions like all other settings

#### Files Modified
- [aifred/state.py](aifred/state.py): Line 1314 (added `_save_settings()` call)

---

### 🎯 Progress UI System Complete - MILESTONE

#### Added
- **Complete Progress Event Handling** ([aifred/state.py:942-960](aifred/state.py#L942-L960)):
  - Quick/Deep research modes now handle all progress events (`progress`, `history_update`, `thinking_warning`)
  - Identical event routing logic as Automatik mode
  - Shows Web-Scraping progress (1/3, 2/3, 3/3) and LLM generation phase
  - Visual feedback for all research pipeline stages

- **Pulsing Animation for All Modes** ([aifred/aifred.py:526,539,543](aifred/aifred.py#L526)):
  - Animation triggers on `progress_active | is_generating` (previously only `progress_active`)
  - "Generiere Antwort" now pulses in "none" mode (Eigenes Wissen) during LLM inference
  - Consistent visual feedback across all 4 research modes
  - Bold text weight during active phases

- **Dynamic Status Text** ([aifred/aifred.py:449-464](aifred/aifred.py#L449-L464)):
  - Status text shows "Generiere Antwort" when `is_generating=True` even if `progress_active=False`
  - Fixes idle state in "none" mode where status stayed on "Warte auf Eingabe"
  - Properly reflects system activity in all modes

#### Fixed
- **Progress Bar Visibility** ([assets/custom.css:90](assets/custom.css#L90)):
  - Removed `.rt-Box` from dark theme CSS selector
  - Orange progress bar fill (#e67700) was hidden by `!important` background override
  - Progress bar now visible in all research modes
  - Root cause: Commit d8e4d55 ("Force dark theme") introduced CSS specificity conflict

- **Missing Progress Events in Quick/Deep Modes**:
  - Quick/Deep modes had no progress event handling (only debug, content, result)
  - Web-Scraping and LLM phases were invisible to user
  - Now shows full pipeline: "Web-Scraping 1/7" → "Generiere Antwort"

#### Testing Results
- ✅ **Automatik Mode**: Progress bar + phases (Automatik → Scraping → LLM)
- ✅ **Quick Mode**: Progress bar + phases (Scraping 1/3 → LLM)
- ✅ **Deep Mode**: Progress bar + phases (Scraping 1/7 → LLM)
- ✅ **None Mode**: Pulsing "Generiere Antwort" during LLM

#### Technical Details
- Progress event flow: `scraper_orchestrator.py` → `orchestrator.py` → `state.py` → `aifred.py`
- Event types: `progress` (scraping, llm, compress), `debug`, `content`, `result`, `history_update`
- State variables: `progress_active`, `progress_phase`, `progress_current`, `progress_total`, `is_generating`
- Reflex reactive rendering: `rx.cond()` for conditional UI updates

#### Impact
- **Before**: Inconsistent progress feedback, Quick/Deep modes had no visual pipeline status
- **After**: Professional, consistent UI feedback across all modes. User always knows system status.
- **UX Improvement**: No more confusion about "is it working?" - clear visual feedback at every stage

#### Files Modified
- [assets/custom.css](assets/custom.css): Line 90 (removed `.rt-Box`)
- [aifred/state.py](aifred/state.py): Lines 942-960 (progress event handling)
- [aifred/aifred.py](aifred/aifred.py): Lines 449-464, 526, 539, 543 (status text, pulsing animation)
- [TODO.md](TODO.md): Comprehensive milestone documentation

---

### 🏷️ Source Label Consistency & Double Metadata Bug Fix

#### Fixed
- **Double Source Metadata Bug** ([aifred/lib/message_builder.py](aifred/lib/message_builder.py), [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py)):
  - Fixed issue where responses showed duplicate source labels (e.g., `( Inferenz: 62.3s, Quelle: Web-Recherche ) ( Inferenz: 53.2s, Quelle: LLM-Trainingsdaten )`)
  - Root cause: HTML metadata (`<span>` tags) and thinking collapsibles (`<details>` tags) were NOT removed from chat history before passing to LLM
  - LLM sometimes copied old metadata into new responses, resulting in duplicate sources
  - Solution: Enhanced `build_messages_from_history()` to strip ALL HTML tags and metadata using regex patterns

#### Changed
- **Message History Cleaning** ([aifred/lib/message_builder.py:86-100](aifred/lib/message_builder.py#L86-L100)):
  - Added `import re` for regex-based HTML tag removal
  - Four-step cleaning process for AI messages:
    1. Remove thinking collapsibles: `<details>...</details>`
    2. Remove metadata spans: `<span style="...">( Inferenz: ... )</span>`
    3. Fallback: Remove text-based metadata patterns
    4. Cleanup: Remove multiple newlines and excess whitespace
  - Prevents LLM from seeing or copying old metadata from history

- **Source Label Consistency** ([aifred/lib/conversation_handler.py:480-486](aifred/lib/conversation_handler.py#L480-L486)):
  - Replaced ambiguous `"LLM-Trainingsdaten"` label with context-aware labels:
    - `"Cache+LLM (RAG)"` - RAG context from Vector Cache
    - `"LLM (mit History)"` - Chat history available as context (NEW)
    - `"LLM"` - Pure LLM without additional context (NEW)
  - Consistent with existing labels: `"Vector Cache"` (direct hit), `"Web-Recherche"` (agent research)

#### Impact
- **Before**: Confusing duplicate source labels, inconsistent terminology
- **After**: Clean, single source label per response with clear context indication
- **User Experience**: Users can now clearly see where each response comes from:
  - First message: `( Inferenz: 2.5s, Quelle: LLM )`
  - Follow-up with history: `( Inferenz: 3.2s, Quelle: LLM (mit History) )`
  - RAG context: `( Inferenz: 4.1s, Quelle: Cache+LLM (RAG) )`
  - Web research: `( Inferenz: 62.3s, 35.2 tok/s, Quelle: Web-Recherche )`

#### Files Modified
- [aifred/lib/message_builder.py](aifred/lib/message_builder.py): Lines 11 (import re), 84-100 (HTML cleaning)
- [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py): Lines 480-486 (source labels)

---

### 🧹 Debug Console Separator Structure

#### Fixed
- **Separator Placement Logic** ([aifred/lib/research/context_builder.py](aifred/lib/research/context_builder.py), [aifred/state.py](aifred/state.py)):
  - Separators now appear AFTER each logical processing unit (not before)
  - Implemented "separator marks end of unit" principle across all code paths
  - Eliminated double separators after LLM completion
  - Three logical units with proper separation:
    1. LLM Response Generation → Separator
    2. Vector Cache Decision (web research only) → Separator
    3. History Compression Check → Separator

#### Changed
- **Web Research Path** ([aifred/lib/research/context_builder.py:204-207](aifred/lib/research/context_builder.py#L204-L207)):
  - Added separator after "✅ Haupt-LLM fertig" message
  - Added separator after Cache-Decision block (lines 329-332)
- **Normal Chat Path** ([aifred/state.py:866-869](aifred/state.py#L866-L869)):
  - Removed redundant separator (conversation_handler already emits one)
- **Compression Check** ([aifred/state.py:997-1016](aifred/state.py#L997-L1016)):
  - Separator now appears after compression completion message

#### Impact
- **Debug Console Output**: Clean, predictable structure with logical block boundaries
- **Before**: Inconsistent separator placement, double separators in some paths
- **After**: Each processing unit ends with exactly one separator line

#### Files Modified
- [aifred/lib/research/context_builder.py](aifred/lib/research/context_builder.py): Lines 204-207, 329-332
- [aifred/state.py](aifred/state.py): Lines 866-869 (commented), 997-1016

---

### 🔄 Auto-Reload Model List on Backend Restart

#### Added
- **Model List Auto-Refresh on Ollama Restart** ([aifred/state.py:1044-1092](aifred/state.py#L1044-L1092)):
  - After Ollama service restart via UI, automatically reload model list from `/api/tags`
  - Update both session state (`self.available_models`) and global state (`_global_backend_state`)
  - No need to restart AIfred just to see newly downloaded models
  - Shows immediate feedback: "🔄 Reloading model list..." and "✅ Model list updated: N models found"

#### Changed
- **`restart_backend()` Method Enhancement**:
  - Added automatic model list refresh after Ollama restart
  - Uses same curl-based API call as initial backend initialization
  - Preserves existing vLLM/TabbyAPI restart logic unchanged

#### Impact
- **User Experience**: Download new models → Restart Ollama → Models instantly available in dropdown
- **Before**: Had to restart entire AIfred service to refresh model list
- **After**: Just click "Restart Ollama" button in system control panel

#### Files Modified
- [aifred/state.py](aifred/state.py): Lines 1044-1092

---

### 🌍 Language Detection for All Prompts

#### Fixed
- **Language Not Passed to Prompt Loading Functions** (8 locations across 7 files):
  - Language was detected but not passed as `lang=` parameter to prompt functions
  - German user queries were receiving English prompts despite correct detection
  - Root cause: Missing `detected_user_language` parameter in function calls

#### Changed
- **Intent Detection** ([aifred/lib/intent_detector.py](aifred/lib/intent_detector.py)):
  - Line 62: Added `lang=detected_user_language` to `get_intent_detection_prompt()`
  - Lines 110-113: Added language detection for followup intent classification
- **Query Optimization** ([aifred/lib/query_optimizer.py:47](aifred/lib/query_optimizer.py#L47)):
  - Added `lang=detected_user_language` to `get_query_optimization_prompt()`
- **Decision Making** ([aifred/lib/conversation_handler.py:268](aifred/lib/conversation_handler.py#L268)):
  - Added `lang=detected_user_language` to `get_decision_making_prompt()`
- **Cache Hit Prompt** ([aifred/lib/research/cache_handler.py:77](aifred/lib/research/cache_handler.py#L77)):
  - Added `lang=detected_user_language` to `load_prompt('system_rag_cache_hit')`
- **System RAG Prompt** ([aifred/lib/research/context_builder.py:99](aifred/lib/research/context_builder.py#L99)):
  - Added `lang=detected_user_language` and `user_text` parameter
- **Cache Decision** ([aifred/lib/research/context_builder.py:241](aifred/lib/research/context_builder.py#L241)):
  - Added `lang=detected_user_language` to `load_prompt('cache_decision')`
- **RAG Relevance Check** ([aifred/lib/rag_context_builder.py:89](aifred/lib/rag_context_builder.py#L89)):
  - Added `lang=detected_user_language` to `load_prompt('rag_relevance_check')`
- **History Summarization** ([aifred/lib/context_manager.py:290](aifred/lib/context_manager.py#L290)):
  - Special case: Detects language from first user message in conversation history
  - Fallback to "de" if no messages available

#### Impact
- **User Experience**: German queries now receive German prompts, English queries receive English prompts
- **All Subsystems Affected**: Intent detection, query optimization, research mode, cache decisions, history compression
- **Consistent i18n**: All 8 prompt loading locations now respect detected language

#### Files Modified
- [aifred/lib/intent_detector.py](aifred/lib/intent_detector.py): Lines 62, 110-113
- [aifred/lib/query_optimizer.py](aifred/lib/query_optimizer.py): Line 47
- [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py): Lines 268-270
- [aifred/lib/research/cache_handler.py](aifred/lib/research/cache_handler.py): Lines 76-89
- [aifred/lib/research/context_builder.py](aifred/lib/research/context_builder.py): Lines 98-110, 244-251
- [aifred/lib/rag_context_builder.py](aifred/lib/rag_context_builder.py): Lines 86-100
- [aifred/lib/context_manager.py](aifred/lib/context_manager.py): Lines 289-301

---

### 🧠 Thinking Mode Support for Ollama and vLLM Backends

#### Added
- **Ollama Thinking Mode Implementation** ([aifred/backends/ollama.py](aifred/backends/ollama.py)):
  - Added `"think": true` API parameter support in `chat()` and `chat_stream()` methods
  - Parse separate `thinking` and `content` fields from Ollama response
  - Wrap thinking output in `<think>...</think>` tags for unified formatting
  - Streaming support: Properly handle thinking chunks before content chunks
- **vLLM Thinking Mode Enhancement** ([aifred/backends/vllm.py](aifred/backends/vllm.py)):
  - Improved type safety: Replaced `# type: ignore` with proper `Dict[str, Any]` annotations
  - Use `chat_template_kwargs: {"enable_thinking": bool}` in `extra_body` for Qwen3 models
  - Consistent implementation across `chat()` and `chat_stream()` methods
- **Unified Thinking Process Formatting** ([aifred/lib/formatting.py](aifred/lib/formatting.py)):
  - Created `format_metadata()` function for metadata display (color: `#bbb`, font-size: `0.85em`)
  - Enhanced `format_thinking_process()` with model name and inference time in collapsible header
  - Added line break reduction regex (`r'\n\n+'`) to reduce excessive blank lines while preserving paragraphs
  - Fallback logic for malformed `<think>` tags (missing opening tag)
  - Updated `build_debug_accordion()` with same improvements for agent research mode
- **UI Styling** ([aifred/theme.py](aifred/theme.py)):
  - Added `.thinking-compact` CSS class for proper paragraph spacing (`0.75em` margins)
  - Text color matches collapsible header (`#aaa`)
  - Compact spacing for first/last child elements
- **User Message HTML Rendering** ([aifred/aifred.py](aifred/aifred.py#L725)):
  - Changed from `rx.text()` to `rx.markdown()` to properly render HTML metadata spans
- **Settings Update** ([aifred/lib/settings.py](aifred/lib/settings.py#L74)):
  - Default `enable_thinking` set to `True` for optimal user experience

#### Changed
- **Type Safety Improvements**:
  - Import `Any` from typing in vLLM backend
  - Declare `extra_body: Dict[str, Any] = {}` instead of untyped dict with `# type: ignore`
  - Removed all type ignore comments in vLLM backend
- **Metadata Color**: Adjusted from `#999` → `#aaa` → `#bbb` for better readability
- **Collapsible Styling**: Removed complex inline div styling in favor of CSS class approach

#### Fixed
- **HTML Rendering in User Messages**: Metadata now properly displays as styled HTML instead of raw tags
- **Type Safety**: MyPy passes without warnings for vLLM `extra_body` dictionary assignments
- **Line Break Handling**: Regex correctly reduces 2+ consecutive newlines to exactly 2 (one blank line)
- **Paragraph Spacing**: Thinking process collapsibles now have proper spacing (not too cramped, not too spaced)

#### Technical Details
- **Ollama API**: Uses `"think": true` payload parameter (not `enable_thinking` in options)
- **Ollama Response Structure**: Provides separate `thinking` and `content` fields in message dict
- **vLLM API**: Uses `extra_body["chat_template_kwargs"] = {"enable_thinking": bool}`
- **Unified Format**: Both backends output `<think>...</think>` wrapped content for consistent parsing
- **Automatik-LLM**: Thinking mode intentionally DISABLED for all automatik tasks (8x faster decisions)

#### Files Modified
- [aifred/backends/ollama.py](aifred/backends/ollama.py): Lines 93-95, 116-125, 199-236
- [aifred/backends/vllm.py](aifred/backends/vllm.py): Lines 9, 79, 88-90, 163, 172-174
- [aifred/lib/formatting.py](aifred/lib/formatting.py): Lines 13-37, 64-152, 155-235
- [aifred/theme.py](aifred/theme.py): Lines 125-142
- [aifred/lib/settings.py](aifred/lib/settings.py): Line 74
- [aifred/aifred.py](aifred/aifred.py): Line 725
- [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py): Lines 467-478

---

### 📱 Mobile Dropdown Optimization

#### Problem Solved
- **Fixed**: Select dropdowns disappeared below viewport on mobile devices
- **Impact**: Users couldn't select models/backends when list was too long or positioned at bottom
- **Root Cause**: Default "item-aligned" positioning opens downward without viewport awareness
- **Solution**: Intelligent positioning + scrollable dropdowns with max-height

#### Implementation
- **Intelligent Positioning**: Added `position="popper"` to all select dropdowns
  - Backend select, Model select, Automatik-Model select
  - Adapts to available viewport space (opens upward if no space below)
- **Scrollable Dropdowns**: CSS max-height with internal scroll
  - Max height: 300px or available viewport height (whichever is smaller)
  - Internal scrollbar when list exceeds height
  - Dropdown stays open while scrolling (no accidental close)
- **Mobile-Friendly**: Touch scroll works correctly inside dropdown

#### Files Modified
- [aifred/aifred.py](aifred/aifred.py): Added `position="popper"` to 3 select components
- [aifred/theme.py](aifred/theme.py): CSS for `.rt-SelectContent` and `.rt-SelectViewport`

---

### 🛡️ GPU Compatibility Backend Filter

#### Problem Solved
- **Fixed**: Incompatible backends (vLLM, TabbyAPI) were selectable on Pascal GPUs (P40, GTX 10 series)
- **Impact**: vLLM would crash with Triton compiler errors or be extremely slow (FP16 1:64 ratio)
- **Root Cause**: Backend selection showed all backends regardless of GPU capabilities
- **Solution**: Automatic backend filtering based on GPU detection

#### Implementation
- **GPU Detection**: Existing `GPUDetector` now filters UI backend options
  - Detects GPU compute capability and FP16 performance
  - Tesla P40 (Compute 6.1) → Only shows "ollama" backend
  - RTX 3060+ (Compute 8.6) → Shows "ollama", "vllm", "tabbyapi"
- **Auto-Switch**: If saved backend is incompatible, auto-switch to first available backend
- **UI Updates**:
  - Backend select dropdown shows only compatible backends
  - GPU info badge shows detected GPU and compute capability
  - Removed redundant GPU warning box (no longer needed)
- **Backend Requirements**:
  - **Ollama**: Works on ALL GPUs (Compute 3.5+, INT8/Q4/Q8 quantization)
  - **vLLM**: Requires Compute 7.0+, fast FP16 performance (Volta or newer)
  - **TabbyAPI**: Same as vLLM (Compute 7.0+, fast FP16)

#### GPU Compatibility Matrix
| GPU | Compute Cap | Available Backends | Reason |
|-----|-------------|-------------------|--------|
| Tesla P40 | 6.1 | ollama only | FP16 ratio 1:64 (extremely slow) |
| Tesla P100 | 6.0 | ollama only | Compute < 7.0 (Triton unsupported) |
| GTX 1080 Ti | 6.1 | ollama only | Pascal architecture (slow FP16) |
| RTX 2080 | 7.5 | ollama, vllm, tabbyapi | Turing (fast FP16, Tensor Cores) |
| RTX 3060 | 8.6 | ollama, vllm, tabbyapi | Ampere (fast FP16, AWQ Marlin) |
| RTX 4090 | 8.9 | ollama, vllm, tabbyapi | Ada Lovelace (excellent) |

#### Files Modified
- [aifred/state.py](aifred/state.py#L146): Added `available_backends` state field
- [aifred/state.py](aifred/state.py#L240-L251): Backend filtering logic on session load
- [aifred/aifred.py](aifred/aifred.py#L994): Dynamic backend select with `AIState.available_backends`
- [aifred/aifred.py](aifred/aifred.py#L1013-L1028): GPU info badge
- [aifred/lib/gpu_detection.py](aifred/lib/gpu_detection.py): Existing GPU detection (no changes)

---

### 📐 vLLM Context Auto-Detection (40K-128K+ Support)

#### Problem Solved
- **Fixed**: vLLM context limit was only 16K tokens
- **Impact**: Responses were cut off mid-sentence, chat history was severely limited
- **Root Cause**: Hardcoded context limits didn't match actual model capabilities
- **Solution**: Automatic detection from model's config.json

#### Implementation
- **Auto-Detection**: `get_model_max_position_embeddings()` reads `max_position_embeddings` from HuggingFace cache
  - Searches `~/.cache/huggingface/hub/models--{vendor}--{model}/snapshots/*/config.json`
  - Returns native context limit (e.g., 40,960 for Qwen3-8B-AWQ, 131,072 for Qwen2.5-Instruct)
  - No more hardcoded values - works with any model!
- **Enhanced**: `vLLMProcessManager.start()` uses auto-detected context
  - `max_model_len=None` triggers auto-detection
  - Falls back to vLLM default if config not found
- **YaRN Support**: Optional RoPE scaling for extending context beyond training limits
  - Accepts YaRN config dict: `{"rope_type": "yarn", "factor": 2.0, "original_max_position_embeddings": 40960}`
  - Can extend context (e.g., 40K → 80K with factor=2.0)
  - Not used by default - native context is sufficient
- **Error Diagnostics**: Improved vLLM startup error logging (captures stderr)
- **Memory Fix**: Increase GPU memory utilization to 95% (40K context needs ~5.6 GiB KV cache)
- **Compatibility**: Use vLLM v0.11.0 defaults (v1 engine with multiprocessing)

#### Context Limits
- **Before**: 16K tokens (hardcoded, responses cut off!)
- **After**: Hardware-constrained maximum:
  - **RTX 3060 (12GB, Ampere 8.6)**: **26,608 tokens** @ 90% GPU memory ✅ Tested
  - Native model support: 40,960 tokens (requires ~5.6 GiB KV cache)
- **Note**: Context size limited by VRAM + GPU architecture, not model capability
- **VRAM Usage**: ~12 GB (97.7% utilization) at 26K context - GPU fully utilized but stable
- **Future**: Can use YaRN for extension when more VRAM available (e.g., RTX 3090, A100, H100)

#### Files Modified
- [aifred/lib/vllm_manager.py](aifred/lib/vllm_manager.py#L19-L64): Added `get_model_max_position_embeddings()`
- [aifred/lib/vllm_manager.py](aifred/lib/vllm_manager.py#L134-L158): Auto-detect in `start()` method
- [aifred/state.py](aifred/state.py#L569-L580): Removed hardcoded values, use auto-detection

---

### ⚡ Backend Pre-Initialization (Page Reload Performance)

#### Problem Solved
- **Fixed**: Backend re-initialization on every page reload (F5)
- **Impact**: Eliminated 30-120s wait time on page refresh
- **Behavior**: Backend now initializes ONCE at server start, persists across page reloads

#### Implementation
- **Added**: Module-level `_global_backend_state` dict for persistent backend state
- **Added**: `_global_backend_initialized` flag to prevent redundant initialization
- **Refactored**: `on_load()` method with two-phase initialization:
  - **Global Phase** (runs once at server start):
    - Debug log initialization
    - Language settings
    - Vector Cache connection
    - GPU detection
  - **Session Phase** (runs per user/tab/reload):
    - Load user settings
    - Generate session ID
    - Restore backend state from global cache
- **Optimized**: `initialize_backend()` with fast/slow paths:
  - **Fast Path**: Backend already initialized → Restore from global state (instant!)
  - **Slow Path**: First initialization or backend switch → Full model loading
- **Optimized**: vLLM Process Manager persistence:
  - `_vllm_manager` stored in global state
  - vLLM server survives page reloads
  - Prevents unnecessary vLLM restarts (saves 70-120s)

#### State Persistence
- **Preserved on page reload**:
  - Chat history
  - Debug console messages
  - Backend configuration
  - Loaded models
  - vLLM server process
  - GPU detection results

#### Restart Buttons
- **Enhanced**: `restart_backend()` method:
  - Ollama: Restarts systemd service
  - vLLM: Stops and restarts vLLM server process
  - TabbyAPI: Shows info message (manual restart)
- **Preserved**: "AIfred Neustarten" button behavior:
  - Clears chat history, debug console, caches
  - Does NOT restart backend or vLLM
  - Soft restart for development (hot-reload mode)
  - Hard restart via systemd for production

#### Code Quality
- **Passed**: ruff linter checks (no errors)
- **Fixed**: Unused variable `research_result` in generate loop
- **Added**: Type annotations for `_global_backend_state: dict[str, Any]`
- **Tested**: Backend switching, page reload, restart buttons

---

### 🔍 GPU Detection & Compatibility Checking

#### GPU Detection System
- **Added**: `aifred/lib/gpu_detection.py` - Automatic GPU capability detection
- **Features**:
  - Detects GPU compute capability via nvidia-smi
  - Identifies compatible/incompatible backends per GPU
  - Warns about known GPU limitations (Tesla P40 FP16 issues, etc.)
- **State Integration**:
  - GPU info stored in AIState (gpu_name, gpu_compute_cap, gpu_warnings)
  - Detection runs on startup via `on_load()`
  - Debug console shows GPU capabilities and warnings

#### UI Warnings
- **Added**: Visual warning in Settings when vLLM selected on incompatible GPU
- **Shows**:
  - GPU name and compute capability
  - Backend requirements (Compute Cap 7.5+ for vLLM/AWQ)
  - Recommendation to switch to Ollama for better performance
- **Styling**: Red warning box with icon, auto-shows when vLLM + Pascal GPU

#### Download Scripts Enhanced
- **Enhanced**: `download_vllm_models.sh` with GPU compatibility check
- **Features**:
  - Automatic GPU detection before download
  - Detailed warning for incompatible GPUs (P40, GTX 10 series)
  - Explains why vLLM/AWQ won't work (Triton, FP16 ratio, Compute Cap)
  - Offers exit with recommendation to use Ollama
  - User can override with explicit confirmation

#### Documentation
- **Added**: `docs/GPU_COMPATIBILITY.md` - Comprehensive GPU compatibility guide
- **Covers**:
  - GPU compatibility matrix (Pascal, Turing, Ampere, Ada, Hopper)
  - Backend comparison (Ollama GGUF vs vLLM AWQ vs TabbyAPI EXL2)
  - Technical explanation of Pascal limitations
  - Performance benchmarks (P40 vs RTX 4090)
  - Recommendations by use case
  - Troubleshooting guide

#### Backend Compatibility Summary
- **Ollama (GGUF)**: ✅ Works on all GPUs (Compute Cap 3.5+)
- **vLLM (AWQ)**: ⚠️ Requires Compute Cap 7.5+ (Turing+), fast FP16
- **TabbyAPI (EXL2)**: ⚠️ Requires Compute Cap 7.0+ (Volta+), fast FP16

#### Known GPU Issues Documented
- **Tesla P40**: FP16 ratio 1:64 → vLLM/ExLlama ~1-5 tok/s (unusable)
- **Tesla P100**: FP16 ratio 1:2 → vLLM possible but slower than Ollama
- **GTX 10 Series**: Compute Cap 6.1 → vLLM not supported
- **Recommendation**: Use Ollama (GGUF) on Pascal GPUs for best performance

### 🚀 Performance - 8x Faster Automatik, 7s Saved per Web Research

#### vLLM Preloading Optimization
- **Skip unnecessary preloading** for vLLM/TabbyAPI (models stay in VRAM)
- **Result**: 7s faster web research, UI shows "ℹ️ Haupt-LLM bereits geladen"
- **Files**: `aifred/backends/vllm.py`, `aifred/backends/tabbyapi.py`, `aifred/lib/research/scraper_orchestrator.py`

#### Thinking Mode Disabled for Automatik Tasks
- **Problem**: Qwen3 Thinking Mode slowed decisions from 1-2s to 7-13s
- **Solution**: `enable_thinking=False` for all automatik tasks (decisions, intent, RAG)
- **Result**: 8x faster total flow (3s instead of 24s)
  - Automatik decision: 8.7s → 2.1s (4x faster)
  - Intent detection: 13.0s → 0.3s (43x faster)
- **Files**: Fixed parameter passing in `llm_client.py`, vLLM `chat_template_kwargs` structure, 9 LLM call sites

### 🎯 Context Window Improvements

#### Real Tokenizer instead of Estimation
- **Problem**: Token estimation (3.5 chars/token) was 25% too low → context overflow
- **Solution**: HuggingFace AutoTokenizer with local cache
- **Fallback**: 2.5 chars/token (conservative) when tokenizer unavailable
- **Files**: `aifred/lib/context_manager.py` + 5 call sites

#### vLLM Context Auto-Detection (16K → 40K for Qwen3)
- **Problem**: vLLM hardcoded to 16K despite Qwen3-8B supporting 40K
- **Solution**: Remove `--max-model-len` → auto-detect from model config
- **Benefits**:
  - Qwen3-8B: 40K context (matches Ollama)
  - Qwen2.5-32B: 128K context automatically
  - No hardcoding, each model uses native limit
- **Files**: `vllm_startup.py`, `aifred/lib/vllm_manager.py`

### 🐛 Bug Fixes

- **Backend switching**: Fixed AttributeError and wrong model selection
- **Dead code**: Removed 83 lines (77 unreachable + 6 unused variables)
- **UI**: Debug console limit 100 → 500 messages

### 🔄 Portability

- ✅ No absolute paths
- ✅ No system-specific dependencies
- ✅ HuggingFace tokenizer: offline-capable (local cache)
- ✅ vLLM auto-detection: works on any system
- ✅ Systemd services: Template-based with sed substitution
- ✅ **Fully portable to MiniPC**

### 📦 Model Configuration

#### Restructured Download Scripts with YaRN Support
- **Added**: Separate download scripts for better organization
  - `download_ollama_models.sh` - Ollama (GGUF) models
  - `download_vllm_models.sh` - vLLM (AWQ) models with YaRN docs
  - `download_all_models.sh` - Master script for both backends
- **Archived**: Old scripts renamed to `.old` (preserved for reference)

#### Qwen3 AWQ Models (Primary Recommendation)
- **Added**: Qwen3 AWQ series with YaRN context extension support
  - Qwen3-4B-AWQ (~2.5GB, 40K native, YaRN→128K)
  - Qwen3-8B-AWQ (~5GB, 40K native, YaRN→128K)
  - Qwen3-14B-AWQ (~8GB, 32K native, YaRN→128K)
- **Features**:
  - Optional Thinking Mode (enable_thinking parameter)
  - Newest generation (2025)
  - Flexible context: Native 32-40K, YaRN extendable to 64K/128K

#### Qwen2.5 Instruct-AWQ Models (Alternative)
- **Available**: As alternative option with native 128K context
  - Qwen2.5-7B-Instruct-AWQ (~4GB, 128K native)
  - Qwen2.5-14B-Instruct-AWQ (~8GB, 128K native)
  - Qwen2.5-32B-Instruct-AWQ (~18GB, 128K native)
- **Benefits**: No YaRN needed, older generation but proven stable

#### YaRN Context Extension Support
- **Documentation**: Added comprehensive YaRN configuration examples
- **Flexible Factors**:
  - factor=2.0 → 64K context (recommended for chat history)
  - factor=4.0 → 128K context (for long documents)
- **Implementation**: Command-line and Python examples in download scripts
- **Trade-offs**: Documented perplexity loss vs context gain

## [1.0.0] - 2025-11-10

### 🎉 Milestone: Vector Cache Production Ready

#### Added
- **ChromaDB Vector Cache**: Thread-safe semantic caching for web research results
  - Docker-based ChromaDB server mode (port 8000)
  - Automatic duplicate detection with configurable distance thresholds
  - Time-based cache invalidation (5-minute threshold for explicit research keywords)
  - Query-only embeddings for improved similarity matching (distance 0.000 for exact matches)
  - Auto-learning from web research results
- **Configurable Distance Thresholds** (`aifred/lib/config.py`):
  - `CACHE_DISTANCE_HIGH = 0.5` - High confidence cache hits
  - `CACHE_DISTANCE_MEDIUM = 0.85` - Medium confidence cache hits
  - `CACHE_DISTANCE_DUPLICATE = 0.3` - Duplicate detection for explicit keywords
  - `CACHE_TIME_THRESHOLD = 300` - 5 minutes for time-based invalidation
- **Enhanced Cache Logging**: Distance and confidence displayed for all cache operations (hits, misses, duplicates)
- **Docker Compose Consolidation**: Unified `docker/docker-compose.yml` with ChromaDB + optional SearXNG
- **Docker Documentation**: New `docker/README.md` with service management instructions

#### Changed
- **Vector Cache Architecture**: Migrated from PersistentClient to HttpClient (Docker server mode)
  - Fixes: File lock issues and deadlocks in async operations
  - Improvement: Thread-safe by design, no worker threads needed
- **Cache Query Strategy**: Implemented `query_newest()` method
  - Returns most recent match instead of best similarity match
  - Prevents outdated cache entries from being returned
- **Context Window Management**: Generous reserve strategy (8K-16K tokens) to prevent answer truncation
- **Project Structure**:
  - Moved `docker-compose.yml` from root to `docker/` directory
  - Consolidated separate ChromaDB and SearXNG compose files
- **Duplicate Detection**: Time-aware duplicate prevention
  - Skip save if similar entry exists and is < 5 minutes old
  - Allow new entry if existing entry is > 5 minutes old (allows updates)

#### Removed
- **Obsolete Implementations**: Deleted `archive/vector_cache_old/` directory
  - Old PersistentClient implementation (vector_cache.py)
  - Old worker thread implementation (vector_cache_v2.py)
  - Still available in git history if needed

#### Fixed
- **KeyError 'data'**: Fixed cache hit result format for explicit research keywords
- **Missing user_with_time**: Added timestamp generation for history entries
- **Cache Miss on Recent Entries**: Fixed `query_newest()` to find most recent duplicate
- **Duplicate Log Messages**: Proper distinction between saved entries and skipped duplicates
- **Distance Logging**: Distance now displayed for all cache operations (hits and misses)

#### Technical Details
- **ChromaDB Version**: Using latest ChromaDB Docker image
- **API Version**: ChromaDB v2 API (v1 deprecated)
- **Collection Management**:
  - Collection name: `research_cache`
  - Persistent storage: `./aifred_vector_cache/` (Docker volume)
  - Health checks: Automatic with 30s interval
- **Cache Statistics**: Available via `get_cache().get_stats()`

#### Migration Notes
- **Docker Commands Updated**: All docker-compose commands now require `-f docker/docker-compose.yml` or working from `docker/` directory
- **ChromaDB Reset**: Two methods documented in README
  - Option 1: Full restart (stop container, delete data, restart)
  - Option 2: API-based collection deletion (faster, no container restart)
- **Configuration**: All cache thresholds centralized in `aifred/lib/config.py`

---

## [1.1.0] - 2025-11-10

### 🧠 Intelligent Cache Decision System

#### Added
- **LLM-Based Cache Decision**: Automatic cache filtering with AI-powered override capability
  - Two-stage filter: Volatile keywords → LLM decision
  - Override logic: Concept questions (e.g., "Was ist Wetter?") are cached despite volatile keywords
  - Automatik-LLM makes decision (fast, deterministic with temperature=0.1)
- **Volatile Keywords List** (`aifred/lib/config.py`):
  - `CACHE_EXCLUDE_VOLATILE` - 40+ keywords for volatile data detection
  - Weather, finance, live sports, breaking news, time-specific queries
  - Triggers LLM decision for smart caching
- **Cache Decision Prompt** (`prompts/de/cache_decision.txt`):
  - Clear rules: Cache facts/concepts, don't cache live data
  - Examples for both cacheable and non-cacheable queries
  - Override examples for ambiguous cases
- **Source Attribution**: Transparent source labeling in chat history
  - "Quelle: LLM-Trainingsdaten" - Answer from model's training data
  - "Quelle: Vector Cache" - Answer from semantic cache
  - "Quelle: Session Cache" - Answer from session-based cache
  - "Quelle: Web-Recherche" - Answer from fresh web research
- **Cache Inspection Scripts**:
  - `scripts/list_cache.py` - List all cached entries with timestamps
  - `scripts/search_cache.py` - Semantic similarity search in cache

#### Changed
- **Cache Distance Thresholds**: Stricter matching for better quality
  - `CACHE_DISTANCE_MEDIUM` lowered from 0.85 to 0.5
  - Preparation for RAG mode (0.5-1.2 range)
- **Cache Auto-Learning Logic** (`context_builder.py`):
  - Intelligent filtering before saving to cache
  - LLM evaluates if content is timeless or volatile
  - Debug messages for cache decision transparency
- **Volatile Keywords**: Moved to external file for easier maintenance
  - Now loaded from `prompts/cache_volatile_keywords.txt`
  - Multilingual file (German + English keywords)
  - Easy to edit without code changes
  - 68 keywords covering weather, finance, sports, news, time references

#### Fixed
- **UnboundLocalError**: Fixed duplicate `load_prompt` import causing variable shadowing
  - Removed local imports at lines 231 and 261 in `context_builder.py`
  - Now uses module-level import correctly
- **Deadlock in Cache Decision**: Fixed LLM client resource conflict
  - Was creating new LLMClient instances for cache decision
  - Now uses existing `automatik_llm_client` parameter
  - Prevents deadlock when Haupt-LLM just finished generating
  - Removed unnecessary `from ..llm_client import LLMClient` import

#### Technical Details
- **Cache Decision Flow**:
  1. Check user query for volatile keywords
  2. If keyword found → Ask LLM (can override to "cacheable")
  3. If no keyword → Ask LLM (default decision)
  4. Save to cache only if LLM approves
- **Source Display Format**:
  - Appears at end of AI answer (not user question)
  - Format: `(Inferenz: 2.5s, Quelle: <source>)`
  - Consistent across all answer types

---

## [1.3.0] - 2025-11-11

### 🚀 Pure Semantic Deduplication + Smart Cache for Explicit Research

#### Added
- **Smart Cache-Check for Explicit Research Keywords** (`conversation_handler.py`):
  - Cache check BEFORE web research for keywords like "recherchiere", "google", "suche im internet"
  - Distance < 0.05 (practically identical) → Use cache (0.15s instead of 100s)
  - Distance ≥ 0.05 → Perform fresh research
  - Transparent display: Shows cache age (e.g., "Cache-Hit (681s old, d=0.0000)")
  - User can still force fresh research via UI mode selection (Web-Suche schnell/tief)
- **ChromaDB Maintenance Tool** (`chroma_maintenance.py`):
  - Display cache statistics (entries, age, size)
  - Find duplicates (text similarity-based)
  - Remove duplicates (keeps newest entry)
  - Delete old entries (by age threshold)
  - Clear entire database
  - Dry-run mode for safe testing

#### Changed
- **Pure Semantic Deduplication** (No Time Dependencies):
  - Removed: `CACHE_TIME_THRESHOLD` (5-minute logic)
  - New: Always update semantic duplicates (distance < 0.3) regardless of age
  - Benefit: Consistent behavior, no race conditions, latest data guaranteed
  - Affected files: `vector_cache.py`, `config.py`, `conversation_handler.py`
- **Automatik-LLM Default Model**:
  - Changed from `qwen3:8b` to `qwen2.5:3b`
  - Performance: 2.7x faster decisions (0.3s instead of 0.8s)
  - VRAM: ~63% reduction (~3GB instead of ~8GB)
  - Main LLM remains `qwen3:8b` for final answers

#### Fixed
- **LLMResponse AttributeError** (`context_builder.py`):
  - Fixed: `response.get('message', {}).get('content', '')` → `response.text`
  - Issue: LLMResponse is dataclass with `.text` attribute, not a dict
  - Affected: Cache decision logic (2 locations)
- **10x Python Duplicates**:
  - Root cause: Time-based logic allowed duplicates after 5 minutes
  - Fix: Pure semantic deduplication always updates duplicates
  - Result: No more duplicate cache entries

#### Performance
- **Identical Research Query**: ~667x faster (0.15s instead of 100s) ✅
- **Automatik Decision**: 2.7x faster (0.3s instead of 0.8s) ✅
- **VRAM Savings**: ~63% less for Automatik-LLM ✅

#### Breaking Changes
None - Fully backwards compatible

---

## [Unreleased]

### Planned Features
- RAG mode improvements: Better relevance detection
- Cache statistics dashboard in UI
- Export/import cache entries
- Multi-language support for cache queries
- Background cache cleanup scheduler

---

**Note**: This is the first formal release with changelog tracking. Previous development history is available in git commit history.
