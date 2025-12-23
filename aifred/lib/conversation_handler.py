"""
Conversation Handler - Interactive Chat and Decision-Making

This module handles the chat interactive mode where the AI decides
whether web research is needed or can answer from its own knowledge.

Includes:
- Automatic decision-making (research vs. direct answer)
- Keyword-based research triggering
- Cache-aware decision logic
- Direct LLM inference for knowledge-based answers
"""

import time
from typing import Dict, List, Optional, AsyncIterator

from .llm_client import LLMClient
from .logging_utils import log_message, CONSOLE_SEPARATOR
from .prompt_loader import (
    get_decision_making_prompt,
    get_vision_ocr_prompt,
    get_vision_templateless_ocr_prompt,
    get_vision_templateless_default_prompt
)
from .message_builder import (
    build_messages_from_history,
    inject_rag_context,
    inject_vision_json_context
)
from .formatting import format_thinking_process, format_metadata, format_number, format_age
# Cache system removed - will be replaced with Vector DB
from .context_manager import estimate_tokens, calculate_dynamic_num_ctx, prepare_main_llm
from .streaming_utils import stream_llm_response, log_llm_completion
from .config import (
    DYNAMIC_NUM_PREDICT_SAFETY_MARGIN,
    DYNAMIC_NUM_PREDICT_MINIMUM,
    DYNAMIC_NUM_PREDICT_HARD_LIMIT,
    AUTOMATIK_LLM_NUM_CTX
)
from .intent_detector import detect_query_intent, get_temperature_for_intent, get_temperature_label
from .research import perform_agent_research
import json
import re


def extract_model_name(model_display: str) -> str:
    """
    Extract pure model name from display format "model_name (X.X GB)".

    Args:
        model_display: Display name with size, e.g., "qwen3:4b (2.3 GB)"

    Returns:
        Pure model name, e.g., "qwen3:4b"
    """
    if " (" in model_display and model_display.endswith(")"):
        return model_display.split(" (")[0]
    return model_display


async def _process_single_image_vision(
    image: Dict[str, str],
    image_index: int,
    vision_model: str,
    backend_type: str,
    backend_url: str,
    num_ctx: int,
    supports_chat_template: bool,
    lang: str,
    llm_options: Optional[Dict] = None
) -> Dict:
    """
    Process a single image with Vision-LLM.

    This helper function handles the actual Vision-LLM call for one image.
    Used by chat_with_vision_pipeline() for sequential multi-image processing.

    Args:
        image: Dict with "name" and "base64" keys
        image_index: 0-based index for logging
        vision_model: Vision-LLM model name
        backend_type: Backend type (ollama, vllm, etc.)
        backend_url: Backend URL
        num_ctx: Context window size
        supports_chat_template: Whether model supports system prompts
        lang: Language code ("de" or "en")
        llm_options: Additional LLM options

    Returns:
        Dict with keys:
        - "success": bool
        - "json": Parsed JSON dict (if successful)
        - "raw": Raw response string
        - "metrics": Backend metrics (tokens/s, etc.)
        - "error": Error message (if failed)
        - "time": Processing time in seconds
    """
    from ..backends.base import LLMMessage

    img_name = image.get("name", f"image_{image_index + 1}")
    log_message(f"📷 [{image_index + 1}] Processing: {img_name}")

    # Build content parts for single image
    content_parts = []

    # Add default prompt for template-less models
    if not supports_chat_template:
        model_lower = vision_model.lower()
        if "ocr" in model_lower or "deepseek-ocr" in model_lower:
            default_prompt = get_vision_templateless_ocr_prompt(lang=lang)
        else:
            default_prompt = get_vision_templateless_default_prompt(lang=lang)
        content_parts.append({"type": "text", "text": default_prompt})

    # Add single image
    content_parts.append({
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{image['base64']}"}
    })

    # Build messages
    if supports_chat_template:
        vision_system_prompt = get_vision_ocr_prompt(lang=lang)
        messages = [
            LLMMessage(role="system", content=vision_system_prompt),
            LLMMessage(role="user", content=content_parts)
        ]
    else:
        messages = [
            LLMMessage(role="user", content=content_parts)
        ]

    # Call Vision-LLM
    llm_client = LLMClient(backend_type=backend_type, base_url=backend_url)

    vision_options = {
        "temperature": 0.1,
        "num_ctx": num_ctx,
        **(llm_options or {})
    }

    start_time = time.time()
    response_text = ""
    metrics = None

    try:
        async for chunk in llm_client.chat_stream(
            model=vision_model,
            messages=messages,
            options=vision_options
        ):
            if chunk.get("type") == "content":
                response_text += chunk.get("text", "")
            elif chunk.get("type") == "done":
                metrics = chunk.get("metrics", {})

        elapsed = time.time() - start_time
        log_message(f"✅ [{image_index + 1}] {img_name} done ({elapsed:.1f}s)")

        # Try to parse JSON
        try:
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text.strip()

            json_str = _sanitize_json_string(json_str)
            parsed_json = json.loads(json_str)

            return {
                "success": True,
                "json": parsed_json,
                "raw": response_text,
                "metrics": metrics,
                "time": elapsed,
                "image_name": img_name
            }
        except json.JSONDecodeError:
            # JSON parsing failed, return raw response
            return {
                "success": True,  # API call succeeded, just no JSON
                "json": None,
                "raw": response_text,
                "metrics": metrics,
                "time": elapsed,
                "image_name": img_name
            }

    except Exception as e:
        elapsed = time.time() - start_time
        log_message(f"❌ [{image_index + 1}] {img_name} Error: {e}")
        return {
            "success": False,
            "json": None,
            "raw": "",
            "metrics": None,
            "error": str(e),
            "time": elapsed,
            "image_name": img_name
        }


def _html_table_to_markdown(html_content: str) -> str:
    """
    Convert HTML table to Markdown (fallback for models like DeepSeek-OCR).

    Args:
        html_content: HTML string with <table> tags

    Returns:
        Markdown-formatted table
    """
    from html.parser import HTMLParser

    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows = []
            self.current_row = []
            self.in_table = False
            self.in_row = False
            self.in_cell = False
            self.cell_content = []

        def handle_starttag(self, tag, attrs):
            if tag == 'table':
                self.in_table = True
            elif tag == 'tr' and self.in_table:
                self.in_row = True
                self.current_row = []
            elif tag in ['td', 'th'] and self.in_row:
                self.in_cell = True
                self.cell_content = []

        def handle_endtag(self, tag):
            if tag == 'table':
                self.in_table = False
            elif tag == 'tr' and self.in_row:
                self.in_row = False
                if self.current_row:
                    self.rows.append(self.current_row)
            elif tag in ['td', 'th'] and self.in_cell:
                self.in_cell = False
                self.current_row.append(''.join(self.cell_content).strip())

        def handle_data(self, data):
            if self.in_cell:
                self.cell_content.append(data)

    parser = TableParser()
    parser.feed(html_content)

    if not parser.rows or len(parser.rows) < 2:
        raise ValueError("No valid HTML table found")

    # First row as header
    headers = parser.rows[0]
    data_rows = parser.rows[1:]

    # Build Markdown table
    markdown = "| " + " | ".join(headers) + " |\n"
    markdown += "| " + " | ".join(["---"] * len(headers)) + " |\n"

    for row in data_rows:
        # Pad row to match header length
        padded_row = row + [""] * (len(headers) - len(row))
        markdown += "| " + " | ".join(padded_row[:len(headers)]) + " |\n"

    return markdown


def _sanitize_json_string(json_str: str) -> str:
    """
    Remove invalid JSON comments (// ...) that some Vision-LLMs add.

    Args:
        json_str: JSON string possibly containing comments

    Returns:
        Sanitized JSON string without comments
    """
    # Remove single-line comments (// ...) but preserve URLs (http://, https://)
    # Use negative lookbehind to avoid removing // in URLs
    sanitized = re.sub(r'(?<!:)//[^\n]*', '', json_str)
    return sanitized


def _json_to_readable(parsed_json: dict, lang: str = "de") -> tuple[str, dict]:
    """
    Convert parsed JSON to human-readable text and return corrected JSON.

    Args:
        parsed_json: Parsed JSON from Vision-LLM (possibly with errors)
        lang: Language ("de" or "en")

    Returns:
        Tuple of (readable_text, corrected_json)
        - readable_text: Human-readable Markdown-formatted text
        - corrected_json: Corrected JSON (with error corrections)
    """
    # Create a copy to avoid modifying the original
    corrected_json = parsed_json.copy()
    doc_type = corrected_json.get("type", "unknown")

    if doc_type == "table":
        # Table → Markdown Table
        columns = corrected_json.get("columns", [])
        rows = corrected_json.get("rows", [])

        # ERROR CORRECTION: Ministral-3 sometimes packs EVERYTHING in "columns" as nested array
        # Format 1: {"columns": [["H1", "H2"]], "rows": [[...]]}  → len == 1
        # Format 2: {"columns": [["H1", "H2"], ["R1C1", "R1C2"], ...], "rows": [...]} → len > 1
        if columns and isinstance(columns[0], list):
            if len(columns) == 1:
                # Only header in nested array, rows separate
                columns = columns[0]
                log_message("⚠️ Vision-LLM format error: columns is nested array (len=1). Corrected.")
            else:
                # Header + data in columns, ignore rows (probably empty or old)
                rows = columns[1:]  # Rest are the actual rows
                columns = columns[0]  # First element is header
                log_message(f"⚠️ Vision-LLM format error: columns contains {len(columns)-1} rows. Corrected.")

            # Update corrected_json with fixed structure
            corrected_json["columns"] = columns
            corrected_json["rows"] = rows

        if not columns:
            return ("⚠️ Leere Tabelle" if lang == "de" else "⚠️ Empty table", corrected_json)

        # If rows is empty but columns is nested
        if not rows and columns:
            return ("⚠️ Tabelle ohne Daten" if lang == "de" else "⚠️ Table without data", corrected_json)

        # Create Markdown table
        table = "| " + " | ".join(str(col) for col in columns) + " |\n"
        table += "| " + " | ".join(["---"] * len(columns)) + " |\n"

        for row in rows:
            # Ensure row has the same length as columns
            row_padded = row + [""] * (len(columns) - len(row))
            table += "| " + " | ".join(str(cell) for cell in row_padded[:len(columns)]) + " |\n"

        return (table, corrected_json)

    elif doc_type == "list":
        # List → Markdown List
        items = corrected_json.get("items", [])
        if not items:
            return ("⚠️ Leere Liste" if lang == "de" else "⚠️ Empty list", corrected_json)

        return ("\n".join(f"- {item}" for item in items), corrected_json)

    elif doc_type == "form":
        # Form → Key-Value list (with subfield support)
        fields = corrected_json.get("fields", [])
        if not fields:
            return ("⚠️ Leeres Formular" if lang == "de" else "⚠️ Empty form", corrected_json)

        result = []
        for field in fields:
            label = field.get('label', '')
            value = field.get('value', '')
            # Support both "subfields" and "fields" for nested data (Vision-LLM uses "fields")
            subfields = field.get('subfields', []) or field.get('fields', [])

            if subfields:
                # Field has subfields → Process recursively
                result.append(f"**{label}**")
                for subfield in subfields:
                    sub_label = subfield.get('label', '')
                    sub_value = subfield.get('value', '')
                    result.append(f"  - {sub_label} {sub_value}")
            else:
                # Normal Key-Value field
                result.append(f"**{label}:** {value}")

        return ("\n".join(result), corrected_json)

    elif doc_type == "text":
        # Plain text - Newlines to Markdown line breaks (2 spaces + \n)
        content = corrected_json.get("content", "")
        # In Markdown \n is ignored - "  \n" creates hard line break without paragraph spacing
        if content:
            content = re.sub(r'\n{2,}', '\n\n', content)  # Multiple newlines → one paragraph
            content = re.sub(r'(?<!\n)\n(?!\n)', '  \n', content)  # Single \n → Markdown line break
        return (content, corrected_json)

    elif doc_type == "mixed" or doc_type == "document":
        # Mixed/complete document → recursively process all sections
        sections = corrected_json.get("sections", [])
        if not sections:
            return ("⚠️ Leeres Dokument" if lang == "de" else "⚠️ Empty document", corrected_json)

        result = []
        for section in sections:
            heading = section.get("heading", "")
            if heading:
                result.append(f"## {heading}\n")
            readable_text, _ = _json_to_readable(section, lang)  # Recursive call
            result.append(readable_text)
            result.append("")  # Empty line between sections

        return ("\n".join(result), corrected_json)

    elif doc_type == "multi_image":
        # Multi-Image analysis → Format each image individually
        images = corrected_json.get("images", [])
        if not images:
            return ("⚠️ Keine Bilder analysiert" if lang == "de" else "⚠️ No images analyzed", corrected_json)

        result = []
        for img in images:
            img_index = img.get("image_index", "?")
            description = img.get("description", "")
            content = img.get("content", {})

            # Header for each image
            header = f"📷 **Bild {img_index}**" if lang == "de" else f"📷 **Image {img_index}**"
            if description:
                header += f": {description}"
            result.append(header)

            # Process content recursively
            if isinstance(content, dict):
                readable_text, _ = _json_to_readable(content, lang)
                if readable_text and readable_text.strip():
                    result.append(readable_text)
            elif isinstance(content, str) and content.strip():
                result.append(content)

            result.append("")  # Empty line between images

        return ("\n".join(result).strip(), corrected_json)

    else:
        # Universal fallback: Try to extract content from known fields
        # This allows Vision-LLMs to use creative/unknown types
        result_parts = []

        # Helper for newline conversion (Markdown: "  \n" = hard line break)
        def _fix_newlines(text: str) -> str:
            text = re.sub(r'\n{2,}', '\n\n', text)  # Multiple newlines → one paragraph
            text = re.sub(r'(?<!\n)\n(?!\n)', '  \n', text)  # Single \n → Markdown line break
            return text

        # Try "content" (most common field)
        content = corrected_json.get("content")
        if content:
            if isinstance(content, dict):
                # Nested content (e.g., {"description": "..."})
                for key, value in content.items():
                    if isinstance(value, str) and value.strip():
                        result_parts.append(_fix_newlines(value))
            elif isinstance(content, str) and content.strip():
                result_parts.append(_fix_newlines(content))

        # Try "description"
        description = corrected_json.get("description")
        if description and isinstance(description, str) and description.strip():
            result_parts.append(_fix_newlines(description))

        # Try "text"
        text = corrected_json.get("text")
        if text and isinstance(text, str) and text.strip():
            result_parts.append(_fix_newlines(text))

        # Try "items" (list)
        items = corrected_json.get("items")
        if items and isinstance(items, list):
            result_parts.append("\n".join(f"- {item}" for item in items if item))

        # Try "sections" recursively
        sections = corrected_json.get("sections")
        if sections and isinstance(sections, list):
            for section in sections:
                if isinstance(section, dict):
                    readable, _ = _json_to_readable(section, lang)
                    if readable and readable.strip():
                        result_parts.append(readable)

        if result_parts:
            return ("\n\n".join(result_parts), corrected_json)

        # Last fallback: Return JSON as string
        return (json.dumps(corrected_json, indent=2, ensure_ascii=False), corrected_json)


async def chat_with_vision_pipeline(
    user_text: str,
    images: List[Dict[str, str]],
    vision_model: str,
    main_model: str,
    backend_type: str = "ollama",
    backend_url: Optional[str] = None,
    num_ctx_mode: str = "auto_vram",
    num_ctx_manual: int = 16384,
    llm_options: Optional[Dict] = None,
    state=None  # AIState object (for Automatik routing if user_text present)
) -> AsyncIterator[Dict]:
    """
    3-Model Architecture: Vision-LLM extracts structured data, Main-LLM optionally formats it.

    Pipeline:
    1. Vision-LLM analyzes image(s) with OCR system prompt → JSON output
    2. If user query contains formatting keywords ("formatiere", "tabelle", "markdown", etc.):
       → Main-LLM post-processes JSON → formatted output
    3. Otherwise: Return JSON directly

    Args:
        user_text: User query text
        images: List of image dicts with "name" and "base64" keys
        vision_model: Vision-LLM model name (e.g., "qwen3-vl:8b")
        main_model: Main LLM for post-processing (e.g., "qwen3:30b")
        backend_type: "ollama", "koboldcpp", "vllm", "tabbyapi"
        backend_url: Backend URL (optional, uses default if None)
        num_ctx_mode: "auto_vram", "auto_dynamic", "manual"
        num_ctx_manual: Manual context size if mode="manual"
        llm_options: Additional LLM options

    Yields:
        Dict with keys: "type" (status/response/debug/error), "content"
    """
    from .prompt_loader import detect_language, get_language

    # === DEBUG: Log entry point with image count ===
    log_message(f"🚀 Vision Pipeline started: {len(images)} image(s)")
    for i, img in enumerate(images):
        img_name = img.get("name", "unknown")
        img_size = len(img.get("base64", "")) // 1024  # KB
        log_message(f"   [{i+1}] {img_name} ({img_size} KB base64)")

    # Detect language from user text, fallback to history or global setting
    if user_text:
        lang = detect_language(user_text)
    else:
        # No user text (image only) → try to detect from recent chat history
        lang = None
        if state and hasattr(state, 'chat_history') and state.chat_history:
            # Check last 3 messages for language detection
            for user_msg, _ in reversed(state.chat_history[-3:]):
                if user_msg and len(user_msg.strip()) > 10:  # Meaningful text
                    lang = detect_language(user_msg)
                    log_message(f"🌐 Language detected from history: {lang.upper()}")
                    break

        # Fallback to global language setting if no history available
        if not lang:
            global_lang = get_language()
            if global_lang == "auto":
                # Auto mode + no history → default to German (AIfred's primary language)
                lang = "de"
                log_message("🌐 Language fallback: de (AIfred default)")
            else:
                # Fixed language mode (de/en) → use that
                lang = global_lang
                log_message(f"🌐 Language from config: {lang.upper()}")

    # Ensure lang is always set (mypy type narrowing)
    if not lang:
        lang = "de"

    # Collect image names for display
    image_names = ", ".join([img.get("name", "unknown") for img in images])
    log_message(f"📷 Analyzing images: {image_names}")

    # === PHASE 1: Vision-LLM OCR extraction ===
    # Note: Status message now shown in state.py for immediate feedback

    # === Get model capabilities (chat template + context window) in single API call ===
    from .vision_utils import get_vision_model_capabilities

    # Ensure backend_url is set (fallback to default Ollama URL)
    if not backend_url:
        backend_url = "http://localhost:11434"
        log_message("⚠️ No backend_url provided, using default: http://localhost:11434")

    log_message(f"📐 Reading model capabilities for Vision-LLM ({vision_model})...")
    supports_chat_template, intrinsic_num_ctx = await get_vision_model_capabilities(backend_url, vision_model)

    # === Calculate VRAM-based context limit (same as Main-LLM) ===
    # This prevents OOM errors when models have large intrinsic context (e.g., 262K for Ministral-3)
    from .gpu_utils import calculate_vram_based_context, get_model_size_from_cache

    # Get model size from Ollama API (for VRAM calculation)
    model_size_bytes = 0
    model_is_loaded = False

    if backend_type == "ollama":
        from ..backends import BackendFactory
        backend = BackendFactory.create("ollama", base_url=backend_url)

        # Get model metadata (size + loaded state)
        _, model_size_bytes = await backend.get_model_context_limit(vision_model)

        # If size not in API, try cache
        if model_size_bytes == 0:
            model_size_bytes = get_model_size_from_cache(vision_model)

        # Check if model is already loaded
        model_is_loaded = await backend.is_model_loaded(vision_model)

    # Calculate practical num_ctx based on VRAM (with MoE auto-detection)
    vram_num_ctx, debug_msgs = await calculate_vram_based_context(
        model_name=vision_model,
        model_size_bytes=model_size_bytes,
        model_context_limit=intrinsic_num_ctx or 4096,  # Fallback to 4K if detection failed
        model_is_loaded=model_is_loaded,
        backend_type=backend_type,
        backend=backend if backend_type == "ollama" else None  # Pass backend for auto-unloading
    )

    # === Dynamic Vision Context Calculation (v2.5.3) ===
    # Same logic as Main-LLM: min(calculated, VRAM-based, Model-Limit)
    # This ensures we use only as much context as needed, saving VRAM!
    from .formatting import format_number

    # Send debug messages to UI console (same as Main-LLM)
    for msg in debug_msgs:
        yield {"type": "debug", "message": msg}

    # Calculate required tokens for Vision (SEQUENTIAL: only 1 image at a time!)
    # - Image embeddings: ~2000 tokens per image (conservative estimate)
    # - System prompt: ~500 tokens
    # - Reserve for response: 8K tokens (Vision outputs can be long with OCR)
    # NOTE: We always calculate for 1 image since we process sequentially!
    image_tokens = 1 * 2000  # Only 1 image at a time
    system_prompt_tokens = 500
    response_reserve = 8192  # 8K reserve for Vision response

    estimated_tokens = image_tokens + system_prompt_tokens
    needed_tokens = estimated_tokens + response_reserve

    # Model limit (fallback to 128K if detection failed)
    model_limit = intrinsic_num_ctx or 131072

    # CRITICAL: Minimum for Vision (image embedding needs at least this)
    from .config import VISION_MINIMUM_CONTEXT  # Central constant

    if vram_num_ctx < VISION_MINIMUM_CONTEXT:
        msg = f"⚠️ VRAM context {vram_num_ctx} too small for Vision → Using minimum {VISION_MINIMUM_CONTEXT} tokens"
        log_message(msg)
        yield {"type": "debug", "message": msg}
        vram_num_ctx = VISION_MINIMUM_CONTEXT

    # Final context = min(needed, VRAM-max, model-max) - same as Main-LLM!
    # But ensure at least VISION_MINIMUM_CONTEXT
    calculated_ctx = max(needed_tokens, VISION_MINIMUM_CONTEXT)
    num_ctx = min(calculated_ctx, vram_num_ctx, model_limit)

    # Log detailed calculation (same style as Main-LLM)
    ctx_msg1 = f"🎯 Vision Context: {format_number(num_ctx)} tok"
    ctx_msg2 = f"   (needed: {format_number(needed_tokens)}, VRAM-max: {format_number(vram_num_ctx)}, Model-max: {format_number(model_limit)})"
    yield {"type": "debug", "message": ctx_msg1}
    yield {"type": "debug", "message": ctx_msg2}

    # ============================================================
    # SEQUENTIAL IMAGE PROCESSING (v2.6.0)
    # Process images one at a time for better model accuracy!
    # Even large Vision models produce inconsistent results with
    # multiple images in one request.
    # ============================================================

    num_images = len(images)
    vision_start_time = time.time()
    corrected_json = None  # Will be set after processing
    vision_metrics = None  # Will hold metrics from last image
    all_results = []  # Collect results from each image

    if num_images == 1:
        # === SINGLE IMAGE: Direct processing (original behavior) ===
        log_message("📷 Single image mode - direct processing")

        result = await _process_single_image_vision(
            image=images[0],
            image_index=0,
            vision_model=vision_model,
            backend_type=backend_type,
            backend_url=backend_url,
            num_ctx=num_ctx,
            supports_chat_template=supports_chat_template,
            lang=lang,
            llm_options=llm_options
        )

        if not result["success"]:
            yield {"type": "error", "content": f"❌ Vision-LLM error: {result.get('error', 'Unknown error')}"}
            return

        vision_metrics = result.get("metrics")
        vision_response = result["raw"]

        # Process result same as before
        if result["json"]:
            parsed_json = result["json"]
            vision_time = result["time"]

            log_message(f"✅ JSON successfully parsed: {parsed_json.get('type', 'unknown')} ({vision_time:.1f}s)")

            human_readable, corrected_json = _json_to_readable(parsed_json, lang)

            yield {"type": "thinking", "content": json.dumps(corrected_json, indent=2, ensure_ascii=False), "label": "📊 Structured Data"}
            yield {"type": "response", "content": human_readable}

            if vision_metrics:
                yield {"type": "done", "metrics": vision_metrics}
        else:
            # No JSON - try fallbacks
            if '<table' in vision_response.lower():
                log_message("🔄 Detected HTML table, attempting conversion to Markdown...")
                try:
                    markdown_table = _html_table_to_markdown(vision_response)
                    yield {"type": "response", "content": markdown_table}
                    if vision_metrics:
                        yield {"type": "done", "metrics": vision_metrics}
                except Exception as html_err:
                    log_message(f"⚠️ HTML conversion failed: {html_err}")
                    yield {"type": "response", "content": vision_response}
            else:
                log_message("⚠️ Returning raw Vision-LLM output")
                yield {"type": "response", "content": vision_response}
                if vision_metrics:
                    yield {"type": "done", "metrics": vision_metrics}

    else:
        # === MULTI-IMAGE: Sequential processing ===
        log_message(f"📷 Sequential mode: Processing {num_images} images one at a time")
        yield {"type": "debug", "message": f"📷 Sequential processing: {num_images} images one at a time"}

        for i, img in enumerate(images):
            img_name = img.get("name", f"image_{i + 1}")
            yield {"type": "debug", "message": f"🔄 [{i + 1}/{num_images}] Processing: {img_name}"}

            result = await _process_single_image_vision(
                image=img,
                image_index=i,
                vision_model=vision_model,
                backend_type=backend_type,
                backend_url=backend_url,
                num_ctx=num_ctx,
                supports_chat_template=supports_chat_template,
                lang=lang,
                llm_options=llm_options
            )

            all_results.append(result)

            if result["success"]:
                yield {"type": "debug", "message": f"✅ [{i + 1}/{num_images}] {img_name} done ({result['time']:.1f}s)"}
            else:
                yield {"type": "debug", "message": f"⚠️ [{i + 1}/{num_images}] {img_name} error: {result.get('error', 'Unknown')}"}

        # Capture metrics from last successful result
        for r in reversed(all_results):
            if r.get("metrics"):
                vision_metrics = r["metrics"]
                break

        total_time = time.time() - vision_start_time
        log_message(f"✅ All {num_images} images processed ({total_time:.1f}s total)")

        # === Combine results into multi_image JSON format ===
        combined_images = []
        combined_readable_parts = []

        for i, result in enumerate(all_results):
            img_name = result.get("image_name", f"image_{i + 1}")

            if result["json"]:
                # Add to combined JSON
                image_entry = {
                    "image_name": img_name,
                    **result["json"]  # Merge parsed JSON fields
                }
                combined_images.append(image_entry)

                # Generate human-readable for this image
                human_part, _ = _json_to_readable(result["json"], lang)
                combined_readable_parts.append(f"### 📷 {img_name}\n\n{human_part}")

            elif result["raw"]:
                # No JSON but has raw output
                combined_images.append({
                    "image_name": img_name,
                    "type": "raw_text",
                    "content": result["raw"][:500]  # Truncate for JSON
                })
                combined_readable_parts.append(f"### 📷 {img_name}\n\n{result['raw']}")

            else:
                # Failed
                error_msg = result.get("error", "Processing failed")
                combined_images.append({
                    "image_name": img_name,
                    "type": "error",
                    "error": error_msg
                })
                combined_readable_parts.append(f"### 📷 {img_name}\n\n❌ Error: {error_msg}")

        # Build final combined JSON
        corrected_json = {
            "type": "multi_image",
            "count": num_images,
            "processing_mode": "sequential",
            "total_time_seconds": round(total_time, 1),
            "images": combined_images
        }

        # Combine human-readable output
        human_readable = "\n\n---\n\n".join(combined_readable_parts)

        # Yield results
        yield {"type": "thinking", "content": json.dumps(corrected_json, indent=2, ensure_ascii=False), "label": f"📊 Structured Data ({num_images} images)"}
        yield {"type": "response", "content": human_readable}

        if vision_metrics:
            yield {"type": "done", "metrics": vision_metrics}

    # === PHASE 2: Signal completion - state.py will route to Automatik if needed ===
    # Send vision_complete signal with user_text flag
    # state.py will decide whether to route to chat_interactive_mode based on user_text
    yield {
        "type": "vision_complete",
        "vision_json": corrected_json,
        "metrics": vision_metrics,
        "has_user_text": bool(user_text and user_text.strip())  # Tell state.py if routing needed
    }

    if user_text and user_text.strip():
        log_message("📋 Vision done - continuing to Automatik/Research")
    else:
        log_message("✅ Vision extraction complete (no follow-up question)")


async def chat_interactive_mode(
    user_text: str,
    stt_time: float,
    model_choice: str,
    automatik_model: str,
    history: List,
    session_id: Optional[str] = None,
    temperature_mode: str = 'auto',
    temperature: float = 0.2,
    llm_options: Optional[Dict] = None,
    backend_type: str = "ollama",
    backend_url: Optional[str] = None,
    num_ctx_mode: str = "auto_vram",
    num_ctx_manual: int = 16384,
    pending_images: Optional[List[Dict[str, str]]] = None,
    vision_json_context: Optional[dict] = None
) -> AsyncIterator[Dict]:
    """
    Automatik mode: AI decides whether web research is needed

    Args:
        user_text: User question
        stt_time: STT time (0.0 for text input)
        model_choice: Main LLM for final response
        automatik_model: Automatik-LLM for decision
        history: Chat history
        session_id: Session ID for research cache (optional)
        temperature_mode: 'auto' (intent detection) or 'manual' (fixed value)
        temperature: Temperature value (0.0-2.0) - only used if mode='manual'
        llm_options: Dict with Ollama options (num_ctx, etc.) - optional
        backend_type: LLM backend ("ollama", "vllm", "tabbyapi")
        backend_url: Backend URL (optional, uses default if not provided)
        num_ctx_mode: Context mode ("auto_vram", "auto_max", "manual")
        num_ctx_manual: Manual num_ctx value (only used if mode="manual")
        pending_images: List of images (for multimodal messages)
        vision_json_context: Structured data extracted from images by Vision-LLM (optional)

    Yields:
        Dict with: {"type": "debug"|"content"|"metrics"|"separator"|"result", ...}
    """
    # Build multimodal content if images present
    if pending_images:
        user_content = [{"type": "text", "text": user_text}]
        for img in pending_images:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img['base64']}"}
            })
        # Override user_text with multimodal structure (will be used to build LLMMessage later)
        multimodal_user_content = user_content
        yield {"type": "debug", "message": f"📷 Message prepared with {len(pending_images)} image(s)"}
    else:
        multimodal_user_content = None  # Text-only mode

    # Extract pure model names from display format (e.g., "qwen3:4b (2.3 GB)" → "qwen3:4b")
    model_choice = extract_model_name(model_choice)
    automatik_model = extract_model_name(automatik_model)

    # Initialize LLM clients with correct backend
    llm_client = LLMClient(backend_type=backend_type, base_url=backend_url)

    # Only Ollama supports model switching - other backends reuse same client
    if backend_type == 'ollama':
        automatik_llm_client = LLMClient(backend_type=backend_type, base_url=backend_url)
    else:
        # KoboldCPP, vLLM, TabbyAPI: Same model, same client (no model switching)
        automatik_llm_client = llm_client

    # VRAM Change Detection (only for vLLM backend)
    vram_warning = None
    if backend_type == "vllm":
        from .vllm_utils import check_vram_change_for_vllm
        vram_info = check_vram_change_for_vllm(model_choice)
        if vram_info:
            vram_diff, current_vram, cached_vram, potential_tokens, current_tokens = vram_info
            # Store for later conditional warning
            vram_warning = {
                "vram_diff": vram_diff,
                "current_vram": current_vram,
                "cached_vram": cached_vram,
                "potential_tokens": potential_tokens,
                "current_tokens": current_tokens
            }
            log_message(f"📊 VRAM change detected: {vram_diff:+.0f}MB ({cached_vram:.0f}MB → {current_vram:.0f}MB)")

    # Pass vram_warning through llm_options (create dict if None)
    if llm_options is None:
        llm_options = {}
    if vram_warning:
        llm_options['_vram_warning'] = vram_warning

    try:
        log_message("🤖 Automatik mode: AI checking if research needed...")
        yield {"type": "debug", "message": "📨 User request received"}

        # ============================================================
        # CODE-OVERRIDE: Explicit research request (Trigger words + URLs)
        # ============================================================
        # These keywords/URLs trigger IMMEDIATE new research without AI decision!

        # URL Detection (skip Decision-Making for URL requests)
        from .research.query_processor import detect_urls_in_text
        detected_urls = detect_urls_in_text(user_text, max_urls=7)

        explicit_keywords = [
            'recherchiere', 'recherchier',  # German: "recherchiere!", "recherchier mal"
            'suche im internet', 'such im internet',
            'schau nach', 'schau mal nach',
            'google', 'googel', 'google mal',  # Also typos
            'finde heraus', 'find heraus',
            'check das', 'prüfe das'
        ]

        user_lower = user_text.lower()

        # Check for explicit keywords OR URLs
        if detected_urls or any(keyword in user_lower for keyword in explicit_keywords):
            if detected_urls:
                log_message(f"⚡ CODE-OVERRIDE: {len(detected_urls)} URL(s) detected → Skip Decision")
                yield {"type": "debug", "message": f"⚡ {len(detected_urls)} URL(s) detected → Direct Research"}
            else:
                log_message("⚡ CODE-OVERRIDE: Explicit research request detected")
                yield {"type": "debug", "message": "⚡ Explicit research request detected"}

            # Check cache first for exact duplicates (semantic distance < 0.05)
            # This avoids redundant web research for identical queries
            try:
                from .vector_cache import get_cache
                from datetime import datetime

                log_message("🔍 Checking cache for exact duplicates before web research...")
                cache = get_cache()
                cache_result = await cache.query(user_text, n_results=1)

                distance = cache_result.get('distance', 1.0)

                # Check if EXACT duplicate found (distance < 0.05 = practically identical)
                if cache_result['source'] == 'CACHE' and distance < 0.05:
                    # Exact duplicate found - use cached result (avoid redundant research)
                    cache_time = datetime.fromisoformat(cache_result['metadata']['timestamp'])
                    age_seconds = (datetime.now() - cache_time).total_seconds()
                    age_formatted = format_age(age_seconds)

                    log_message(f"✅ Exact duplicate in cache ({age_formatted} old, distance={format_number(distance, 4)}), using cache")
                    yield {"type": "debug", "message": f"✅ Exact match in cache ({age_formatted} ago, d={format_number(distance, 4)}) → Using cached result"}

                    answer = cache_result['answer']
                    cache_time_ms = cache_result.get('query_time_ms', 0) / 1000
                    timing_suffix = f" (Cache-Hit: {format_number(cache_time_ms, 2)}s, Age: {age_formatted}, Source: Vector Cache)"

                    # Emit failed_sources from cache for UI display (if any)
                    cached_failed_sources = cache_result.get('failed_sources', [])
                    if cached_failed_sources:
                        log_message(f"📋 Cache-Hit: {len(cached_failed_sources)} failed source(s) from cache")
                        yield {"type": "failed_sources", "data": cached_failed_sources}

                    # Add to history with timing suffix (no timestamp prefix)
                    history.append((user_text, answer + timing_suffix))

                    # Return result in same format as perform_agent_research
                    yield {
                        "type": "result",
                        "data": (answer + timing_suffix, history, cache_time_ms)
                    }
                    return  # Done!
                else:
                    # No exact duplicate - proceed with fresh research
                    log_message(f"❌ No exact duplicate (distance={format_number(distance, 4)} >= 0.05), performing fresh search")
                    yield {"type": "debug", "message": f"❌ No exact match (d={format_number(distance, 4)}) → Fresh web research"}

            except Exception as e:
                log_message(f"⚠️ Cache check failed: {e}")
                yield {"type": "debug", "message": f"⚠️ Cache check failed: {e}"}

            # Proceed with fresh web research (no exact match or error)
            yield {"type": "debug", "message": "🌐 Starting fresh web research..."}
            async for item in perform_agent_research(
                user_text=user_text,
                stt_time=stt_time,
                mode="deep",
                model_choice=model_choice,
                automatik_model=automatik_model,
                history=history,
                session_id=session_id,
                temperature_mode=temperature_mode,
                temperature=temperature,
                llm_options=llm_options,
                backend_type=backend_type,
                backend_url=backend_url,
                num_ctx_mode=num_ctx_mode,
                num_ctx_manual=num_ctx_manual,
                vision_json_context=vision_json_context  # CRITICAL: Pass Vision JSON to Research flow
            ):
                yield item
            return  # Generator ends after forwarding all items

        # ============================================================
        # Phase 1: Vector Cache Check (Semantic Similarity Search)
        # ============================================================
        try:
            from .vector_cache import get_cache

            log_message("🔍 Checking Vector DB...")
            yield {"type": "debug", "message": "🔍 Checking Vector DB..."}

            cache = get_cache()
            cache_result = await cache.query(user_text, n_results=1)

            if cache_result['source'] == 'CACHE':
                # Cache HIT! Return cached answer
                confidence = cache_result['confidence']
                distance = cache_result['distance']
                answer = cache_result['answer']
                cached_sources = cache_result.get('cached_sources', [])
                cached_failed_sources = cache_result.get('failed_sources', [])

                log_message(f"✅ Vector DB HIT! Confidence: {confidence.upper()}, Distance: {format_number(distance, 3)}")
                yield {"type": "debug", "message": f"✅ Cache HIT ({confidence}, d={format_number(distance, 3)})"}

                # Log cached sources info
                if cached_sources:
                    log_message(f"📚 Cache contains {len(cached_sources)} sources")

                # Emit failed_sources event if any were cached
                if cached_failed_sources:
                    yield {"type": "failed_sources", "data": cached_failed_sources}
                    log_message(f"⚠️ Cache contains {len(cached_failed_sources)} failed sources")

                # Return cached answer with timing info
                cache_time = cache_result.get('query_time_ms', 0) / 1000  # Convert to seconds
                timing_suffix = f" (Cache-Hit: {format_number(cache_time, 2)}s, Source: Vector DB)"

                # Add to history (no timestamp prefix)
                history.append((user_text, answer + timing_suffix))

                # Return result in same format as perform_agent_research
                yield {
                    "type": "result",
                    "data": (answer + timing_suffix, history, cache_time)
                }

                log_message(f"✅ Cache answer returned ({len(answer)} chars, {format_number(cache_time, 2)}s)")
                return  # Done!
            else:
                # Cache MISS - check for RAG context (distance 0.5-1.2)
                distance = cache_result.get('distance', 1.0)
                confidence = cache_result.get('confidence', 'low')
                log_message(f"❌ Vector Cache MISS (distance={format_number(distance, 3)}, confidence={confidence})")
                yield {"type": "debug", "message": f"❌ Cache miss (d={format_number(distance, 3)}, {confidence}) → Checking RAG context..."}

        except Exception as e:
            log_message(f"⚠️ Vector Cache error (continuing without cache): {e}")
            yield {"type": "debug", "message": f"⚠️ Cache unavailable: {e}"}

        # ============================================================
        # Phase 1b: RAG Context Check (if direct cache miss)
        # ============================================================
        rag_context = None
        try:
            from .vector_cache import get_cache
            from .rag_context_builder import build_rag_context

            cache = get_cache()
            rag_result = await build_rag_context(
                user_query=user_text,
                cache=cache,
                automatik_llm_client=automatik_llm_client,
                automatik_model=automatik_model,
                max_candidates=5
            )

            if rag_result:
                # Found relevant context!
                rag_context = rag_result['context']
                num_sources = rag_result['num_relevant']
                num_checked = rag_result['num_checked']
                sources = rag_result['sources']

                # Log RAG context details
                log_message(f"✅ RAG context available: {num_sources} relevant cache entries (from {num_checked} candidates)")
                yield {"type": "debug", "message": f"🎯 RAG: {num_sources}/{num_checked} relevant entries"}

                # Log which cache entries were used as context
                for i, source in enumerate(sources, 1):
                    cached_query_preview = source['query'][:60] + "..." if len(source['query']) > 60 else source['query']
                    log_message(f"  📌 RAG Source {i}: \"{cached_query_preview}\" (d={format_number(source['distance'], 3)})")
            else:
                log_message("❌ No relevant RAG context found")
                yield {"type": "debug", "message": "❌ No RAG context available"}

        except Exception as e:
            log_message(f"⚠️ RAG context building failed: {e}")
            # Continue without RAG context

        # ============================================================
        # RAG BYPASS: Skip Automatik-LLM if RAG context found
        # ============================================================
        if rag_context:
            log_message(f"✅ RAG context available ({num_sources} relevant entries) → Bypass Automatik-LLM, direct to main LLM")
            yield {"type": "debug", "message": f"⚡ RAG Bypass: {num_sources}/{num_checked} relevant entries → Skip Automatik-LLM"}

            # Language detection for user input
            from .prompt_loader import detect_language
            detected_user_language = detect_language(user_text)
            log_message(f"🌐 Language detection: User input is probably '{detected_user_language.upper()}' (for prompt selection)")

            # Clear progress - no web research needed, show LLM phase
            yield {"type": "progress", "phase": "llm"}

            # Now normal inference WITH timing
            # Build messages from history (all turns)
            messages = build_messages_from_history(history, user_text)

            # Replace last message content with multimodal if images present
            if multimodal_user_content is not None:
                messages[-1]['content'] = multimodal_user_content
                log_message("📷 Multimodal content injected into user message")

            # Inject minimal system prompt with timestamp (from load_prompt - automatically includes date/time)
            from .prompt_loader import load_prompt
            system_prompt_minimal = load_prompt('system_minimal', lang=detected_user_language)
            messages.insert(0, {"role": "system", "content": system_prompt_minimal})

            # Inject RAG context using centralized helper
            inject_rag_context(messages, rag_context)
            log_message(f"💡 RAG context injected into system prompt ({len(rag_context)} chars)")

            # Inject Vision JSON context if available (from Vision-LLM extraction)
            if vision_json_context:
                inject_vision_json_context(messages, vision_json_context)
                log_message(f"📷 Vision JSON injected into Main-LLM context ({len(str(vision_json_context))} chars)")

            # Log RAG context content (preview)
            rag_preview = rag_context[:500] + "..." if len(rag_context) > 500 else rag_context
            log_message(f"📄 RAG Context Preview:\n{rag_preview}")

            # Count actual input tokens (using real tokenizer)
            input_tokens = estimate_tokens(messages, model_name=model_choice)

            # Convert dict messages to LLMMessage objects (required by backend)
            # MUST be done AFTER all system prompts are injected
            from ..backends.base import LLMMessage
            llm_messages = [
                LLMMessage(role=msg['role'], content=msg['content'])
                for msg in messages
            ]

            # Temperature decision: Manual Override or Auto (Intent-Detection)
            # IMPORTANT: Intent Detection MUST run BEFORE Main-LLM preload!
            # Otherwise Ollama might unload the Main-LLM to load the Automatik-LLM,
            # then reload the Main-LLM again (wasting ~10s of loading time).
            if temperature_mode == 'manual':
                final_temperature = temperature
                log_message(f"🌡️ RAG Bypass Temperature: {final_temperature} (MANUAL OVERRIDE)")
                yield {"type": "debug", "message": f"🌡️ Temperature: {final_temperature} (manual)"}
            else:
                # Auto: Intent-Detection for RAG Bypass
                intent_start = time.time()
                log_message("🎯 Starting Intent-Detection...")
                yield {"type": "debug", "message": "🎯 Intent detection running..."}

                rag_intent = await detect_query_intent(
                    user_query=user_text,
                    automatik_model=automatik_model,
                    llm_client=automatik_llm_client,
                    llm_options=llm_options
                )
                intent_time = time.time() - intent_start

                final_temperature = get_temperature_for_intent(rag_intent)
                temp_label = get_temperature_label(rag_intent)
                log_message(f"🌡️ RAG Bypass Temperature: {final_temperature} (Intent: {rag_intent}, {format_number(intent_time, 1)}s)")
                yield {"type": "debug", "message": f"🌡️ Temperature: {final_temperature} (auto, {temp_label}, {format_number(intent_time, 1)}s)"}

            # Prepare Main-LLM: calculate num_ctx + preload (centralized function!)
            # IMPORTANT: prepare_main_llm() guarantees the correct order:
            # 1. Calculate num_ctx (Ollama auto_vram: with unload + VRAM measurement)
            # 2. Preload with num_ctx (Ollama loads model + allocates KV cache)
            # AsyncGenerator yields debug messages immediately for UI feedback
            backend = llm_client._get_backend()
            async for item in prepare_main_llm(
                backend=backend,
                llm_client=llm_client,
                model_name=model_choice,
                messages=messages,
                num_ctx_mode=num_ctx_mode,
                num_ctx_manual=num_ctx_manual,
                backend_type=backend_type
            ):
                if item["type"] == "debug":
                    yield item
                elif item["type"] == "result":
                    final_num_ctx, preload_success, preload_time = item["data"]

            # Get model max context for compact display
            model_limit, _ = await llm_client.get_model_context_limit(model_choice)

            yield {"type": "debug", "message": "✅ System prompt created"}

            # Show compact context info (like Automatik-LLM and Web-Research)
            yield {"type": "debug", "message": f"📊 Main-LLM: {format_number(input_tokens)} / {format_number(final_num_ctx)} tok (Model Max: {format_number(model_limit)} tok)"}
            log_message(f"📊 Main-LLM ({model_choice}): Input ~{format_number(input_tokens)} tok, num_ctx: {format_number(final_num_ctx)}, max: {format_number(model_limit)}")

            # Console: LLM starts
            yield {"type": "debug", "message": f"🤖 Main-LLM starting: {model_choice}"}

            # Build main LLM options (include enable_thinking from user settings)
            main_llm_options = {
                'temperature': final_temperature,  # Adaptive or manual temperature!
                'num_ctx': final_num_ctx  # Dynamically calculated or user-specified
            }

            # Add enable_thinking if provided in llm_options (user toggle)
            if llm_options and 'enable_thinking' in llm_options:
                main_llm_options['enable_thinking'] = llm_options['enable_thinking']

            # VRAM Monitoring: Measure before inference (baseline)
            from aifred.lib.gpu_utils import get_free_vram_mb
            vram_before_inference = get_free_vram_mb()

            # Time measurement for final inference - STREAM response
            inference_start = time.time()
            ai_text = ""
            metrics = {}
            ttft = None
            first_token_received = False
            vram_measurement = None

            async for chunk in llm_client.chat_stream(
                model=model_choice,
                messages=llm_messages,
                options=main_llm_options
            ):
                if chunk["type"] == "content":
                    # Measure TTFT
                    if not first_token_received:
                        ttft = time.time() - inference_start
                        first_token_received = True
                        log_message(f"⚡ TTFT: {format_number(ttft, 2)}s")
                        yield {"type": "debug", "message": f"⚡ TTFT: {format_number(ttft, 2)}s"}

                        # VRAM Monitoring: Measure after first token (KV cache allocated)
                        if vram_before_inference is not None and final_num_ctx > 0:
                            from aifred.lib.gpu_utils import measure_vram_during_inference
                            vram_measurement = measure_vram_during_inference(
                                context_tokens=final_num_ctx,
                                vram_before_mb=vram_before_inference
                            )

                    ai_text += chunk["text"]
                    yield {"type": "content", "text": chunk["text"]}
                elif chunk["type"] == "debug":
                    # Forward debug messages from backend (e.g., thinking mode retry warning)
                    yield chunk
                elif chunk["type"] == "thinking_warning":
                    # Forward thinking mode warning (model doesn't support reasoning)
                    yield chunk
                elif chunk["type"] == "done":
                    metrics = chunk["metrics"]

            inference_time = time.time() - inference_start

            # Console: LLM finished
            tokens_generated = metrics.get("tokens_generated", 0)
            tokens_per_sec = metrics.get("tokens_per_second", 0)
            yield {"type": "debug", "message": f"✅ Main-LLM done ({format_number(inference_time, 1)}s, {format_number(tokens_generated)} tok, {format_number(tokens_per_sec, 1)} tok/s)"}

            # VRAM Monitoring: Log and save measurement
            if vram_measurement is not None:
                from aifred.lib.model_vram_cache import add_vram_measurement
                from aifred.lib.gpu_utils import is_moe_model

                # Determine architecture for cache
                is_moe = await is_moe_model(model_choice) if backend_type == "ollama" else False
                architecture = "moe" if is_moe else "dense"

                # Save measurement to unified cache
                add_vram_measurement(
                    model_name=model_choice,
                    context_tokens=final_num_ctx,
                    vram_before_mb=vram_before_inference,
                    vram_during_mb=vram_measurement["vram_during_mb"],
                    architecture=architecture,
                    backend=backend_type
                )

                # Log measurement details
                measured_ratio = vram_measurement["measured_mb_per_token"]
                vram_used = vram_measurement["vram_used_by_context"]
                vram_during = vram_measurement["vram_during_mb"]

                log_message(
                    f"📊 VRAM Measurement: {format_number(vram_used)} MB used for {format_number(final_num_ctx)} tokens "
                    f"({measured_ratio:.4f} MB/token) | Free during inference: {format_number(vram_during)} MB"
                )
                yield {"type": "debug", "message": f"📊 VRAM: {measured_ratio:.4f} MB/tok (Free: {format_number(vram_during)} MB)"}

            # Separator as last element in debug console

            # Format <think> tags as collapsible for chat history (visible as collapsible!)
            thinking_html = format_thinking_process(ai_text, model_name=model_choice, inference_time=inference_time, tokens_per_sec=tokens_per_sec)

            # User text with timing (RAG Bypass - no decision time)
            if stt_time > 0:
                user_metadata = format_metadata(f"STT: {format_number(stt_time, 1)}s")
                user_with_time = f"{user_text}  \n{user_metadata}"
            else:
                user_with_time = user_text

            # AI response with timing + source (RAG)
            source_label = "Cache+LLM RAG"
            metadata = format_metadata(f"Inference: {format_number(inference_time, 1)}s    {format_number(tokens_per_sec, 1)} tok/s    Source: {source_label}")
            ai_with_source = f"{thinking_html}  \n{metadata}"

            # Add to history (WITH thinking collapsible + source!)
            history.append((user_with_time, ai_with_source))

            # Separator after LLM response block (end of unit)
            from .logging_utils import console_separator
            console_separator()
            yield {"type": "debug", "message": CONSOLE_SEPARATOR}

            # Clear progress before final result
            yield {"type": "progress", "clear": True}

            # Return chat history with timing metadata
            yield {
                "type": "result",
                "data": (ai_text, history, inference_time)
            }

            log_message(f"✅ RAG Bypass answer returned ({len(ai_text)} chars, {format_number(inference_time, 2)}s)")
            return  # Early return - skip Automatik-LLM decision

        # ============================================================
        # No RAG context - proceed with normal Automatik-LLM decision
        # ============================================================

        # Language detection for user input
        from .prompt_loader import detect_language
        detected_user_language = detect_language(user_text)
        log_message(f"🌐 Language detection: User input is probably '{detected_user_language.upper()}' (for prompt selection)")

        # Step 1: Ask AI if research is needed (with timing!)
        # Check if images are present OR if Vision JSON context exists
        has_images = (pending_images is not None and len(pending_images) > 0) or (vision_json_context is not None)

        decision_prompt = get_decision_making_prompt(
            user_text=user_text,
            has_images=has_images,
            vision_json=vision_json_context,  # NEW: Pass Vision JSON to Automatik
            lang=detected_user_language
        )

        # DEBUG: Show complete prompt for diagnosis (only in log, not in UI)
        log_message("=" * 60)
        log_message("📋 DECISION PROMPT:")
        log_message("-" * 60)
        log_message(decision_prompt)
        log_message("-" * 60)
        log_message(f"Prompt length: {len(decision_prompt)} chars, ~{len(decision_prompt.split())} words")
        log_message("=" * 60)

        try:
            # Measure time for decision
            log_message(f"🤖 Automatik decision with {automatik_model}")
            yield {"type": "progress", "phase": "automatik"}

            # IMPORTANT: NO History for Decision-Making!
            decision_messages_dict = [{'role': 'user', 'content': decision_prompt}]

            # Get model context limit (use RoPE-scaled value from KoboldCPP if available)
            # For KoboldCPP: Use the actual context from global state (includes RoPE scaling)
            # For other backends: Query the model
            from ..state import _global_backend_state

            if backend_type == 'koboldcpp' and 'context_limit' in _global_backend_state:
                # Use RoPE-scaled context from KoboldCPP startup
                automatik_limit = _global_backend_state['context_limit']
            else:
                # Fallback: Query model (returns native limit without RoPE)
                automatik_limit, _ = await automatik_llm_client.get_model_context_limit(automatik_model)

            decision_num_ctx = min(AUTOMATIK_LLM_NUM_CTX, automatik_limit)  # Use config constant (4K)

            # Count input tokens (using real tokenizer)
            input_tokens = estimate_tokens(decision_messages_dict, model_name=automatik_model)

            # Show compact context info
            yield {"type": "debug", "message": f"📊 Automatik-LLM: {format_number(input_tokens)} / {format_number(decision_num_ctx)} tok (Model Max: {format_number(automatik_limit)} tok)"}
            log_message(f"📊 Automatik-LLM ({automatik_model}): Input ~{format_number(input_tokens)} tok, num_ctx: {format_number(decision_num_ctx)}, max: {format_number(automatik_limit)}")

            decision_start = time.time()
            try:
                # Build automatik options
                automatik_options = {
                    'temperature': 0.2,  # Low for consistent yes/no decisions
                    'num_ctx': decision_num_ctx,  # Dynamic based on model
                    'num_predict': 64,  # Short: "<search>yes</search>" = ~20 tokens (3x buffer)
                    'enable_thinking': False  # Default: Fast decisions without reasoning
                }

                # Automatik tasks: Thinking is ALWAYS off (independent of user toggle)
                log_message("🧠 Decision enable_thinking: False (Automatik-Task)")

                # Convert decision messages to LLMMessage objects
                from ..backends.base import LLMMessage
                decision_messages = [
                    LLMMessage(role=msg['role'], content=msg['content'])
                    for msg in decision_messages_dict
                ]

                response = await automatik_llm_client.chat(
                    model=automatik_model,
                    messages=decision_messages,
                    options=automatik_options
                )

                decision = response.text.strip().lower()
                # Measure actual elapsed time instead of relying on backend's inference_time
                decision_time = time.time() - decision_start

                # Parse decision result for user-friendly display
                decision_label = "Web Research YES" if ('<search>yes</search>' in decision or ('yes' in decision and '<search>context</search>' not in decision)) else "Web Research NO"

                yield {"type": "debug", "message": f"🤖 Decision: {decision_label} ({format_number(decision_time, 1)}s)"}
                log_message(f"🤖 AI decision: {decision_label} ({format_number(decision_time, 1)}s, raw: {decision[:50]}...)")
            except Exception as e:
                decision_time = time.time() - decision_start
                log_message(f"⚠️ Automatik decision failed: {e}")
                log_message("   Fallback: Direct answer without research")
                yield {"type": "debug", "message": "⚠️ Decision failed, using fallback (direct answer)"}
                # Fallback: Assume no research needed, proceed with direct LLM answer
                decision = "no"

            # ============================================================
            # Parse decision AND respect it!
            # ============================================================
            if '<search>yes</search>' in decision or ('yes' in decision and '<search>context</search>' not in decision):
                log_message("✅ AI decides: NEW web research needed")
                # Debug message already yielded above (line 153)

                # Start web research - Forward all yields
                async for item in perform_agent_research(
                    user_text=user_text,
                    stt_time=stt_time,
                    mode="deep",
                    model_choice=model_choice,
                    automatik_model=automatik_model,
                    history=history,
                    session_id=session_id,
                    temperature_mode=temperature_mode,
                    temperature=temperature,
                    llm_options=llm_options,
                    backend_type=backend_type,
                    backend_url=backend_url,
                    num_ctx_mode=num_ctx_mode,
                    num_ctx_manual=num_ctx_manual,
                    vision_json_context=vision_json_context  # CRITICAL: Pass Vision JSON to Research flow
                ):
                    yield item
                return

            # Note: 'context' decision removed - cache system will be replaced with Vector DB

            else:
                log_message("❌ AI decides: Own knowledge sufficient → No agent")
                # Debug message already yielded above (line 153)

                # Clear progress - no web research needed, show LLM phase
                yield {"type": "progress", "phase": "llm"}

                # Now normal inference WITH time measurement
                # Build messages from history (all turns)
                messages = build_messages_from_history(history, user_text)

                # Replace last message content with multimodal if images present
                if multimodal_user_content is not None:
                    messages[-1]['content'] = multimodal_user_content
                    log_message("📷 Multimodal content injected into user message")

                # Inject minimal system prompt with timestamp (from load_prompt - automatically includes date/time)
                from .prompt_loader import load_prompt
                system_prompt_minimal = load_prompt('system_minimal', lang=detected_user_language)
                messages.insert(0, {"role": "system", "content": system_prompt_minimal})

                # Inject RAG context using centralized helper
                if rag_context:
                    inject_rag_context(messages, rag_context)
                    log_message(f"💡 RAG context injected into system prompt ({len(rag_context)} chars)")

                    # Log RAG context content (preview)
                    rag_preview = rag_context[:500] + "..." if len(rag_context) > 500 else rag_context
                    log_message(f"📄 RAG Context Preview:\n{rag_preview}")

                # Inject Vision JSON context if available (from Vision-LLM extraction)
                if vision_json_context:
                    inject_vision_json_context(messages, vision_json_context)
                    log_message(f"📷 Vision JSON injected into Main-LLM context ({len(str(vision_json_context))} chars)")

                # Count actual input tokens (using real tokenizer)
                input_tokens = estimate_tokens(messages, model_name=model_choice)

                # Convert dict messages to LLMMessage objects (required by backend)
                # MUST be done AFTER all system prompts are injected
                from ..backends.base import LLMMessage
                llm_messages_no_rag = [
                    LLMMessage(role=msg['role'], content=msg['content'])
                    for msg in messages
                ]

                # Temperature decision: Manual Override or Auto (Intent-Detection)
                # IMPORTANT: Intent Detection MUST run BEFORE Main-LLM preload!
                # Otherwise Ollama might unload the Main-LLM to load the Automatik-LLM,
                # then reload the Main-LLM again (wasting ~10s of loading time).
                if temperature_mode == 'manual':
                    final_temperature = temperature
                    log_message(f"🌡️ Own knowledge Temperature: {final_temperature} (MANUAL OVERRIDE)")
                    yield {"type": "debug", "message": f"🌡️ Temperature: {final_temperature} (manual)"}
                else:
                    # Auto: Intent-Detection for own knowledge
                    intent_start = time.time()
                    log_message("🎯 Starting Intent-Detection...")
                    yield {"type": "debug", "message": "🎯 Intent detection running..."}

                    own_knowledge_intent = await detect_query_intent(
                        user_query=user_text,
                        automatik_model=automatik_model,
                        llm_client=automatik_llm_client,
                        llm_options=llm_options
                    )
                    intent_time = time.time() - intent_start

                    final_temperature = get_temperature_for_intent(own_knowledge_intent)
                    temp_label = get_temperature_label(own_knowledge_intent)
                    log_message(f"🌡️ Own knowledge Temperature: {final_temperature} (Intent: {own_knowledge_intent}, {format_number(intent_time, 1)}s)")
                    yield {"type": "debug", "message": f"🌡️ Temperature: {final_temperature} (auto, {temp_label}, {format_number(intent_time, 1)}s)"}

                # Prepare Main-LLM: calculate num_ctx + Preload (centralized function!)
                # IMPORTANT: prepare_main_llm() guarantees correct order:
                # 1. Calculate num_ctx (Ollama auto_vram: with unload + VRAM measurement)
                # 2. Preload with num_ctx (Ollama loads model + allocates KV-Cache)
                # AsyncGenerator yields debug messages immediately for UI feedback
                backend = llm_client._get_backend()
                async for item in prepare_main_llm(
                    backend=backend,
                    llm_client=llm_client,
                    model_name=model_choice,
                    messages=messages,
                    num_ctx_mode=num_ctx_mode,
                    num_ctx_manual=num_ctx_manual,
                    backend_type=backend_type
                ):
                    if item["type"] == "debug":
                        yield item
                    elif item["type"] == "result":
                        final_num_ctx, preload_success, preload_time = item["data"]

                # Get model max context for compact display
                model_limit, _ = await llm_client.get_model_context_limit(model_choice)

                yield {"type": "debug", "message": "✅ System prompt created"}

                # Show compact context info (like Automatik-LLM and Web-Research)
                yield {"type": "debug", "message": f"📊 Main-LLM: {format_number(input_tokens)} / {format_number(final_num_ctx)} tok (Model Max: {format_number(model_limit)} tok)"}
                log_message(f"📊 Main-LLM ({model_choice}): Input ~{format_number(input_tokens)} tok, num_ctx: {format_number(final_num_ctx)}, max: {format_number(model_limit)}")

                # Console: LLM starts
                yield {"type": "debug", "message": f"🤖 Main-LLM starting: {model_choice}"}

                # Calculate dynamic num_predict: Available output space after input tokens
                available_output = max(
                    DYNAMIC_NUM_PREDICT_MINIMUM,
                    final_num_ctx - input_tokens - DYNAMIC_NUM_PREDICT_SAFETY_MARGIN
                )

                # HARD LIMIT: Prevents KV-Cache overflow to CPU RAM
                # Problem: Large num_predict causes KoboldCPP to pre-allocate huge KV-Cache
                # Example: 259K num_predict → 19.7 GB CPU RAM, 88°C CPU temp
                if available_output > DYNAMIC_NUM_PREDICT_HARD_LIMIT:
                    log_message(f"⚠️ num_predict capped: {format_number(available_output)} → {format_number(DYNAMIC_NUM_PREDICT_HARD_LIMIT)} tokens (KV-Cache protection)")
                    available_output = DYNAMIC_NUM_PREDICT_HARD_LIMIT

                log_message(f"🧮 Dynamic num_predict: {format_number(available_output)} tokens (num_ctx: {format_number(final_num_ctx)}, input: {format_number(input_tokens)}, margin: {DYNAMIC_NUM_PREDICT_SAFETY_MARGIN})")

                # Build main LLM options (include enable_thinking from user settings)
                main_llm_options = {
                    'temperature': final_temperature,  # Adaptive or Manual Temperature!
                    'num_ctx': final_num_ctx,  # Dynamically calculated or user setting
                    'num_predict': available_output  # Dynamic: Full available output space (capped at 4096)
                }

                # Add enable_thinking if provided in llm_options (user toggle)
                if llm_options and 'enable_thinking' in llm_options:
                    main_llm_options['enable_thinking'] = llm_options['enable_thinking']

                # Stream response using centralized utility
                ai_text = ""
                metrics = {}
                inference_time = 0.0
                tokens_per_sec = 0.0

                async for chunk in stream_llm_response(
                    llm_client, model_choice, llm_messages_no_rag, main_llm_options,
                    ttft_label="TTFT"
                ):
                    if chunk["type"] == "content":
                        yield chunk
                    elif chunk["type"] == "debug":
                        yield chunk
                    elif chunk["type"] == "thinking_warning":
                        yield chunk
                    elif chunk["type"] == "stream_result":
                        # Final chunk with accumulated data
                        ai_text = chunk["text"]
                        metrics = chunk["metrics"]
                        inference_time = chunk["inference_time"]
                        tokens_per_sec = metrics.get("tokens_per_second", 0)

                # Console: LLM finished
                yield log_llm_completion(inference_time, metrics)

                # Separator as last element in the Debug Console

                # Format <think> tags as collapsible for chat history (visible as collapsible!)
                thinking_html = format_thinking_process(ai_text, model_name=model_choice, inference_time=inference_time, tokens_per_sec=tokens_per_sec)

                # User text with timing (decision time + inference time)
                if stt_time > 0:
                    user_metadata = format_metadata(f"STT: {format_number(stt_time, 1)}s    Decision: {format_number(decision_time, 1)}s")
                    user_with_time = f"{user_text}  \n{user_metadata}"
                else:
                    user_metadata = format_metadata(f"Decision: {format_number(decision_time, 1)}s")
                    user_with_time = f"{user_text}  \n{user_metadata}"

                # AI response with timing + source (dynamic based on RAG/History)
                if rag_context:
                    source_label = "Cache+LLM RAG"
                elif len(history) > 0:
                    source_label = "LLM with History"
                else:
                    source_label = "LLM"

                metadata = format_metadata(f"Inference: {format_number(inference_time, 1)}s    {format_number(tokens_per_sec, 1)} tok/s    Source: {source_label}")
                ai_with_source = f"{thinking_html}  \n{metadata}"

                # Add to history (WITH Thinking Collapsible + Source!)
                history.append((user_with_time, ai_with_source))

                log_message(f"✅ AI response generated ({len(ai_text)} chars, Inference: {format_number(inference_time, 1)}s)")

                # Clear progress before final result
                yield {"type": "progress", "clear": True}

                # Yield separator directly
                yield {"type": "debug", "message": CONSOLE_SEPARATOR}

                # Yield final result: ai_with_source for AI response + History (with source!)
                yield {"type": "result", "data": (ai_with_source, history, inference_time)}

        except Exception as e:
            log_message(f"⚠️ Error in Automatik mode decision: {e}")
            log_message("   Fallback to own knowledge")
            # Fallback: Use standard chat function (must be imported in main)
            raise  # Re-raise to be handled by caller

    except Exception as e:
        log_message(f"⚠️ Error in Automatik mode decision: {e}")
        log_message("   Fallback to own knowledge")
        # Fallback: Use standard chat function (must be imported in main)
        raise  # Re-raise to be handled by caller
    finally:
        # Cleanup: Close LLM clients to free resources
        await llm_client.close()
        # Only close automatik_llm_client if it's a separate instance (Ollama)
        if backend_type == 'ollama':
            await automatik_llm_client.close()
