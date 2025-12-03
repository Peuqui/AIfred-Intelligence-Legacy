# 📸 Vision/OCR Support Documentation

**Version:** 2.3.1
**Date:** 2025-12-04
**Status:** Production Ready

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Supported Models](#supported-models)
4. [Usage](#usage)
5. [Output Format](#output-format)
6. [Performance Benchmarks](#performance-benchmarks)
7. [Technical Details](#technical-details)
8. [Troubleshooting](#troubleshooting)

---

## Overview

AIfred Intelligence now supports **Vision/OCR capabilities** for analyzing images with multimodal LLMs. The system uses a **3-model architecture** to extract structured data from images, convert it to readable format, and optionally post-process with the Main-LLM.

### Key Features

- 📸 **Drag & Drop Image Upload**: Upload images directly into the chat
- 🤖 **Automatic Model Detection**: Auto-detects vision-capable models from your backend
- 📊 **Structured Data Extraction**: Converts images to JSON (tables, lists, forms, text)
- 🎯 **Smart Formatting**: Collapsible JSON + readable Markdown tables
- ⚡ **Fast Inference**: 3-10s for most documents (optimized prompts)
- 🔧 **Robust Parsing**: Auto-correction for malformed Vision-LLM output
- 💾 **Persistent Settings**: Vision model selection saved per backend

---

## Architecture

### 3-Model Pipeline

```
┌─────────────────┐
│  User uploads   │
│  image + text   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ PHASE 1: Vision-LLM (OCR/Extraction)                │
│ ─────────────────────────────────────────────────── │
│ • Model: Vision-LLM (e.g., ministral-3:8b)         │
│ • Input: Image + minimal system prompt              │
│ • Output: Structured JSON (table/list/form/text)    │
│ • Duration: 3-15s (depending on model size)         │
│ • Temperature: 0.1 (precise extraction)             │
└────────┬────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ JSON Parsing & Error Correction                     │
│ ─────────────────────────────────────────────────── │
│ • Extract JSON from markdown code blocks            │
│ • Auto-correct malformed structures                 │
│ • Convert to readable Markdown (tables/lists)       │
└────────┬────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ PHASE 2: Main-LLM (Optional Post-Processing)        │
│ ─────────────────────────────────────────────────── │
│ • Triggered by keywords: "formatiere", "übersetze"  │
│ • Input: Extracted JSON + user question             │
│ • Output: Formatted/translated/summarized response  │
│ • Duration: 5-15s                                    │
└────────┬────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ UI Display                                           │
│ ─────────────────────────────────────────────────── │
│ • Collapsible: 📊 Strukturierte Daten (model)      │
│ • JSON: Pretty-printed, clickable                   │
│ • Markdown Table: Human-readable format             │
│ • Metadata: (Vision: 3.7s (192.4 tok/s))           │
└─────────────────────────────────────────────────────┘
```

### History Management

- **Chat History**: Stores formatted response (Collapsible + Markdown + Metadata)
- **Follow-up Questions**: Main-LLM receives the structured JSON for interpretation
- **Compression**: `<data>` tags preserved (unlike `<think>` tags which are stripped)

---

## Supported Models

### ✅ Recommended Models

| Model | Size | Speed | Quality | Use Case |
|-------|------|-------|---------|----------|
| **Ministral-3:8b** | 2.8 GB | 14s | ⭐⭐⭐⭐⭐ | **Best balance** - detailed, accurate |
| **Ministral-3:3b** | 2.8 GB | 10s | ⭐⭐⭐⭐ | Fast, good for simple docs |
| **Ministral-3:14b** | 7.8 GB | 60s | ⭐⭐⭐⭐⭐ | Highest quality, but slow |

### ⚠️ Not Recommended

| Model | Issue | Details |
|-------|-------|---------|
| DeepSeek-OCR:3b | Ignores prompts | Outputs HTML tables instead of JSON |
| Qwen3-VL:8b | Empty output | Returns 0 characters after 56s |
| Qwen3-VL:30b | Too slow | 60s+ inference time |

### 🔍 Model Detection

AIfred automatically detects vision-capable models by querying backend metadata:

**Ollama:**
```bash
# Checks for .vision.* or .sam.* keys in model_info
curl http://localhost:11434/api/show -d '{"name": "ministral-3:3b"}'
```

**vLLM/TabbyAPI:**
```python
# Reads architectures from HuggingFace config.json
architectures: ["LlavaForConditionalGeneration", "Qwen2VLForConditionalGeneration"]
```

**KoboldCPP:**
```python
# Reads general.architecture from GGUF metadata
general.architecture: "llava", "qwen2vl", "minicpm"
```

---

## Usage

### 1. Select Vision Model

1. Click the **Vision-LLM dropdown** in the UI
2. Select a vision-capable model (e.g., `ministral-3:8b`)
3. Selection is **automatically saved** per backend

### 2. Upload Image

**Method A: Drag & Drop**
- Drag an image file into the chat input area
- Supported formats: JPG, PNG, WebP
- Max size: Auto-resized to 2048px longest edge

**Method B: File Dialog**
- Click the 📎 attach button
- Select image from file picker

### 3. Add Optional Text

**Pure OCR (no text):**
```
[Upload image only, press Send]
→ Extracts all data as structured JSON
```

**OCR + Question:**
```
[Upload image]
Welche Medikamente muss ich morgens nehmen?
→ Extracts data + answers specific question
```

**OCR + Formatting:**
```
[Upload image]
Formatiere die Tabelle als Markdown
→ Extracts data + Main-LLM reformats
```

### 4. View Results

**Output Structure:**
```markdown
📊 Strukturierte Daten (ministral-3:8b)
[Collapsible JSON]

| Column1 | Column2 | Column3 |
|---------|---------|---------|
| Value1  | Value2  | Value3  |

( Vision: 3.7s (192.4 tok/s) )
```

---

## Output Format

### JSON Types

Vision-LLM outputs one of 5 structured types:

#### 1. Table
```json
{
  "type": "table",
  "columns": ["Medikament", "Dosierung", "Morgens"],
  "rows": [
    ["Aspirin", "100mg", "1"],
    ["Ibuprofen", "400mg", "0"]
  ]
}
```

**Rendered as:**
| Medikament | Dosierung | Morgens |
|------------|-----------|---------|
| Aspirin    | 100mg     | 1       |
| Ibuprofen  | 400mg     | 0       |

#### 2. List
```json
{
  "type": "list",
  "items": [
    "Erste Aufgabe",
    "Zweite Aufgabe",
    "Dritte Aufgabe"
  ]
}
```

**Rendered as:**
- Erste Aufgabe
- Zweite Aufgabe
- Dritte Aufgabe

#### 3. Form
```json
{
  "type": "form",
  "fields": [
    {"label": "Name", "value": "Max Mustermann"},
    {"label": "Geburtsdatum", "value": "01.01.1980"}
  ]
}
```

**Rendered as:**
**Name:** Max Mustermann
**Geburtsdatum:** 01.01.1980

#### 4. Text
```json
{
  "type": "text",
  "content": "Der vollständige Text aus dem Dokument..."
}
```

#### 5. Mixed
```json
{
  "type": "mixed",
  "sections": [
    {
      "heading": "Überschrift",
      "type": "text",
      "content": "Text..."
    },
    {
      "heading": "Tabelle",
      "type": "table",
      "columns": ["A", "B"],
      "rows": [["1", "2"]]
    }
  ]
}
```

---

## Performance Benchmarks

### Test Setup
- **Hardware**: NVIDIA RTX 4090 (24 GB VRAM)
- **Backend**: Ollama
- **Image**: Medication plan (465 KB, 1024x1448 px)
- **Date**: 2025-12-03

### Results

| Model | Load Time | Inference | Total | Tokens | tok/s | Quality |
|-------|-----------|-----------|-------|--------|-------|---------|
| Ministral-3:3b | 1.2s | 9.8s | 11.0s | 313 | 192 | ⭐⭐⭐⭐ |
| Ministral-3:8b | 2.1s | 14.4s | 16.5s | 421 | 184 | ⭐⭐⭐⭐⭐ |
| Ministral-3:14b | 3.5s | 59.9s | 63.4s | 349 | 98 | ⭐⭐⭐⭐⭐ |
| DeepSeek-OCR:3b | 3.3s | 4.3s | 7.6s | 0* | - | ❌ HTML output |
| Qwen3-VL:8b | 4.2s | 56.6s | 60.8s | 0 | - | ❌ Empty |
| Qwen3-VL:30b | 8.1s | 120s+ | 128s+ | - | - | ⏱️ Timeout |

\* DeepSeek-OCR outputs HTML tables instead of JSON despite system prompt

### System Prompt Impact

**Before optimization (119 lines):**
- DeepSeek-OCR:3b: 30s (confused by examples)
- Ministral-3:3b: 20s

**After optimization (18 lines):**
- DeepSeek-OCR:3b: 4.3s (still outputs HTML)
- Ministral-3:3b: 9.8s

**Optimization:** 85% shorter prompt → 3-5x faster inference!

---

## Technical Details

### Image Processing Pipeline

```python
# 1. Upload & Validation
image = Image.open(uploaded_file)
if max(image.size) > 2048:
    image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)

# 2. Convert to Base64
buffered = BytesIO()
image.save(buffered, format="JPEG", quality=85)
base64_image = base64.b64encode(buffered.getvalue()).decode()

# 3. Build Multimodal Message
message = {
    "role": "user",
    "content": [
        {"type": "text", "text": user_text or ""},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
    ]
}
```

### JSON Error Correction

**Problem:** Some models output malformed JSON:
```json
{
  "type": "table",
  "columns": [
    ["Header1", "Header2"],  // Should NOT be nested!
    ["Row1Col1", "Row1Col2"],
    ["Row2Col1", "Row2Col2"]
  ]
}
```

**Solution:** Auto-detect and fix:
```python
if columns and isinstance(columns[0], list):
    # First element is actual headers
    rows = columns[1:]
    columns = columns[0]
    log_message("⚠️ Auto-corrected malformed JSON structure")
```

### Collapsible Rendering

**HTML Structure:**
```html
<details style="font-size: 0.9em; margin-bottom: 1em;">
  <summary style="cursor: pointer; color: #aaa;">
    📊 Strukturierte Daten (ministral-3:8b)
  </summary>
  <div class="thinking-compact">
    {JSON_CONTENT}
  </div>
</details>

{MARKDOWN_TABLE}

<span style="font-size: 0.85em; color: #bbb;">
  ( Vision: 3.7s (192.4 tok/s) )
</span>
```

### Context Management

**History Storage:**
- **UI Display**: Formatted HTML (Collapsible + Markdown + Metadata)
- **LLM Context**: Extracted JSON only (for follow-up questions)
- **Compression**: `<data>` tags preserved (unlike `<think>` tags)

**Follow-up Question Example:**
```python
User: [Uploads medication plan]
AI: [Shows formatted table]

User: "Welche Medikamente nehme ich mittags?"
# Main-LLM receives:
# - History: {"type": "table", "columns": [...], "rows": [...]}
# - Question: "Welche Medikamente nehme ich mittags?"
# - Main-LLM parses JSON and answers: "Bisoprolol 2.5mg"
```

---

## Troubleshooting

### Issue: Vision Model Not Appearing in Dropdown

**Symptom:** Dropdown shows "No vision models available"

**Cause:** Model not detected as vision-capable

**Solution:**
```bash
# Check if model has vision capabilities
curl http://localhost:11434/api/show -d '{"name": "ministral-3:3b"}' | jq '.model_info | keys'

# Look for keys containing "vision" or "sam":
# - .vision.block_count
# - .vision.image_size
# - .sam.block_count
```

### Issue: Image Upload Blocked

**Symptom:** "⚠️ Image upload blocked: Non-vision model selected"

**Cause:** Current Main-LLM is not vision-capable

**Solution:** Select a Vision-LLM from the dropdown first

### Issue: Empty Response After Upload

**Symptom:** Image processes but returns 0 characters

**Cause:** Model incompatibility (e.g., Qwen3-VL:8b)

**Solution:** Switch to Ministral-3:3b or 8b

### Issue: HTML Output Instead of JSON

**Symptom:** Vision-LLM returns `<table><tr><td>...` instead of JSON

**Cause:** Model (DeepSeek-OCR) ignores system prompt

**Solution:**
- Switch to Ministral-3 series
- Or: Fallback parsing handles HTML gracefully

### Issue: Slow Inference (>30s)

**Symptom:** Vision-LLM takes 30+ seconds

**Possible Causes:**
1. **Large model**: Qwen3-VL:30b, Ministral-3:14b
2. **Old system prompt**: Update to v2.3.0 (85% shorter)
3. **Large image**: Resize to 1024px instead of 2048px

**Solution:**
```python
# Reduce image size limit in config
MAX_IMAGE_SIZE = 1024  # instead of 2048
```

### Issue: Vision Model Not Saved

**Symptom:** Vision model resets to first available after restart

**Cause:** Fixed in v2.3.0 (bug in model validation logic)

**Solution:** Update to v2.3.0 or later

---

## Future Enhancements

### Planned Features
- 📹 **Video support**: Frame extraction + multi-frame analysis
- 🔍 **OCR confidence scores**: Show detection confidence per field
- 📊 **CSV export**: Direct export of extracted tables
- 🌐 **Multi-language OCR**: Language detection + translation
- 🎨 **Diagram understanding**: Flow charts, architecture diagrams

### Model Support
- **vLLM**: Add AWQ quantized vision models
- **TabbyAPI**: Add EXL2 quantized vision models
- **Local GPU**: Test AMD ROCm compatibility

---

## References

- **Implementation Plan**: [docs/development/VISION_IMAGE_SUPPORT_PLAN.md](development/VISION_IMAGE_SUPPORT_PLAN.md)
- **Main Code**: [aifred/lib/conversation_handler.py](../aifred/lib/conversation_handler.py)
- **Vision Detection**: [aifred/lib/vision_utils.py](../aifred/lib/vision_utils.py)
- **UI Integration**: [aifred/state.py](../aifred/state.py)
- **System Prompts**: [prompts/de/vision_ocr.txt](../prompts/de/vision_ocr.txt)

---

**Last Updated:** 2025-12-04
**Version:** 2.3.1
**Status:** ✅ Production Ready

## Changelog (v2.3.1)

### 🔍 Vision Model Intelligence (2025-12-04)

**New Features:**
- **Chat Template Detection**: Automatically detects model capabilities (system prompts vs. simple `{{ .Prompt }}`)
- **Smart Model Handling**: Ministral uses JSON prompts, DeepSeek-OCR gets default text
- **Intrinsic Context Windows**: Models use full context (262K for Ministral-3, 8K for DeepSeek-OCR)
- **Corrected JSON Display**: Collapsibles show auto-corrected JSON (not raw malformed output)

**Improvements:**
- Enhanced error correction for nested arrays and mixed header+data structures
- Type-safety checks prevent crashes from dict-typed content
- Separator line positioning improved (now after history save)
- Single API call for template + context detection (~50% faster)

**Model Compatibility:**
| Model | Context | Template | JSON Quality |
|-------|---------|----------|--------------|
| Ministral-3:8b | 262K | Full | ⭐⭐⭐⭐⭐ Perfect |
| Ministral-3:3b | 262K | Full | ⚠️ Needs correction |
| DeepSeek-OCR:3b | 8K | Simple | ❌ HTML fallback |
