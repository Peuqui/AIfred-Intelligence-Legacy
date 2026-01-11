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

import datetime
import time
from typing import Dict, List, Optional, AsyncIterator

from .llm_client import LLMClient
from .logging_utils import log_message, log_raw_messages, CONSOLE_SEPARATOR
from .prompt_loader import (
    get_research_decision_prompt,
    get_vision_ocr_prompt,
    get_vision_templateless_ocr_prompt,
    get_vision_templateless_default_prompt,
    get_aifred_system_minimal
)
from .message_builder import (
    inject_rag_context,
    inject_vision_json_context
)
from .formatting import format_thinking_process, format_metadata, format_number, format_age
# Cache system removed - will be replaced with Vector DB
from .context_manager import estimate_tokens, strip_thinking_blocks
from .model_vram_cache import get_ollama_calibration, get_rope_factor_for_model
from .config import (
    DEFAULT_OLLAMA_URL
)
from .intent_detector import get_temperature_for_intent, get_temperature_label
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


async def detect_research_decision(
    user_text: str,
    automatik_llm_client,
    automatik_model: str,
    has_images: bool = False,
    vision_json_context: Optional[Dict] = None,
    detected_language: str = "de",
    llm_history: Optional[List[Dict[str, str]]] = None
) -> Dict:
    """
    Combined Decision-Making + Query-Optimization in one LLM call.

    Replaces two separate calls:
    1. Decision-Making: <search>yes/no</search>
    2. Query-Optimization: 3 optimized search queries

    Args:
        user_text: User query text
        automatik_llm_client: LLM client for Automatik-Model
        automatik_model: Automatik-LLM model name (e.g., "qwen3:4b")
        has_images: Whether the message includes image(s)
        vision_json_context: Structured data extracted from images
        detected_language: Language from Intent Detection ("de" or "en")
        llm_history: Optional chat history for context (resolves pronouns like "this", "he", etc.)

    Returns:
        Dict with keys:
        - "web": bool (True = web research needed)
        - "queries": List[str] (3 optimized queries, only if web=True)
        - "decision_time": float (LLM call duration in seconds)
        - "raw_response": str (for debugging)
    """
    from .config import AUTOMATIK_LLM_NUM_CTX
    from ..backends.base import LLMMessage

    # Get the combined prompt
    prompt = get_research_decision_prompt(
        user_text=user_text,
        has_images=has_images,
        vision_json=vision_json_context,
        lang=detected_language
    )

    # DEBUG: Show complete prompt
    log_message("=" * 60)
    log_message("📋 RESEARCH DECISION PROMPT:")
    log_message("-" * 60)
    log_message(prompt)
    log_message("-" * 60)
    log_message(f"Prompt length: {len(prompt)} chars, ~{len(prompt.split())} words")
    log_message("=" * 60)

    # Build messages with optional history context
    # Reserve 2/3 of context for history, 1/3 for prompt + output
    messages: List[LLMMessage] = []

    if llm_history and len(llm_history) > 0:
        max_history_tokens = (AUTOMATIK_LLM_NUM_CTX * 2) // 3  # 2/3 for history
        history_tokens = 0
        selected_history: List[Dict[str, str]] = []

        # Iterate from newest to oldest, add until token limit
        # Use proper tokenizer for accurate estimation
        for entry in reversed(llm_history):
            entry_tokens = estimate_tokens([entry])
            if history_tokens + entry_tokens > max_history_tokens:
                break
            selected_history.insert(0, entry)  # Prepend to maintain order
            history_tokens += entry_tokens

        # Add history messages
        for entry in selected_history:
            role = entry.get("role", "user")
            content = entry.get("content", "")
            # Strip [AIFRED]: prefix for cleaner context
            if content.startswith("[AIFRED]:"):
                content = content[9:].strip()
            messages.append(LLMMessage(role=role, content=content))

        if selected_history:
            log_message(f"📜 History context: {len(selected_history)} entries, ~{int(history_tokens)} tokens")

    # Add the actual prompt as final user message
    messages.append(LLMMessage(role="user", content=prompt))

    # LLM options: JSON format for reliable parsing
    options = {
        "temperature": 0.2,  # Low for consistent decisions
        "num_ctx": AUTOMATIK_LLM_NUM_CTX,  # Explicit context
        "enable_thinking": False,  # Fast decisions
        "format": "json"  # Request JSON output format (Ollama)
    }

    decision_start = time.time()

    # DEBUG: Log raw messages sent to Automatik-LLM
    log_raw_messages("AUTOMATIK-LLM (detect_research_decision)", messages, estimate_tokens)

    try:
        response = await automatik_llm_client.chat(
            model=automatik_model,
            messages=messages,
            options=options
        )
        raw_response = response.text.strip()
        decision_time = time.time() - decision_start

        # DEBUG: Log raw response
        log_message("=" * 60)
        log_message("📝 RAW RESEARCH DECISION RESPONSE:")
        log_message("-" * 60)
        log_message(raw_response)
        log_message("-" * 60)
        log_message(f"Response length: {len(raw_response)} chars, time: {decision_time:.2f}s")
        log_message("=" * 60)

        # Parse JSON response with repair for common LLM errors
        def repair_json(s: str) -> str:
            """Fix common LLM JSON errors like ]] instead of ]}"""
            # Fix double brackets: ]] → ]}
            s = re.sub(r'\]\](?=\s*$)', ']}', s)
            s = re.sub(r'\]\](?=\s*})', ']}', s)
            # Fix missing closing brace
            if s.count('{') > s.count('}'):
                s = s + '}'
            return s

        try:
            # Try direct JSON parse
            result = json.loads(raw_response)
        except json.JSONDecodeError as e1:
            log_message(f"⚠️ JSON parse error: {e1}")
            # Try repair
            repaired = repair_json(raw_response)
            log_message(f"🔧 Attempting JSON repair: {repaired}")
            try:
                result = json.loads(repaired)
                log_message("✅ JSON repair successful")
            except json.JSONDecodeError:
                # Try extract JSON from text
                json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
                if json_match:
                    try:
                        extracted = repair_json(json_match.group())
                        result = json.loads(extracted)
                        log_message("✅ JSON extraction + repair successful")
                    except json.JSONDecodeError as e3:
                        # NO FALLBACK - raise error!
                        error_msg = f"JSON parse failed after all repair attempts: {e3}\nRaw: {raw_response}"
                        log_message(f"❌ {error_msg}")
                        raise ValueError(error_msg)
                else:
                    # NO FALLBACK - raise error!
                    error_msg = f"No JSON found in response: {raw_response}"
                    log_message(f"❌ {error_msg}")
                    raise ValueError(error_msg)

        # Normalize result
        web_needed = result.get("web", False)
        queries = result.get("queries", [])

        # Validate queries if web research is needed
        if web_needed and not queries:
            log_message("⚠️ web=true but no queries, setting web=false")
            web_needed = False

        log_message(f"✅ Research Decision: web={web_needed}, {len(queries)} queries")

        return {
            "web": web_needed,
            "queries": queries,
            "decision_time": decision_time,
            "raw_response": raw_response
        }

    except Exception as e:
        decision_time = time.time() - decision_start
        log_message(f"❌ Research decision failed: {e}")
        # NO FALLBACK - re-raise to make the error visible!
        raise


async def chat_with_vision_pipeline(
    user_text: str,
    images: List[Dict[str, str]],
    vision_model: str,
    main_model: str,
    backend_type: str = "ollama",
    backend_url: Optional[str] = None,
    llm_options: Optional[Dict] = None,
    state=None,  # AIState object (REQUIRED for per-agent num_ctx lookup)
    detected_language: str = "de"  # Language from Intent Detection or UI setting
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
        llm_options: Additional LLM options
        state: AIState object (REQUIRED for per-agent num_ctx lookup via get_agent_num_ctx)
        detected_language: Language from LLM-based Intent Detection ("de" or "en")

    Yields:
        Dict with keys: "type" (status/response/debug/error), "content"
    """
    # === DEBUG: Log entry point with image count ===
    log_message(f"🚀 Vision Pipeline started: {len(images)} image(s)")
    for i, img in enumerate(images):
        img_name = img.get("name", "unknown")
        img_size = len(img.get("base64", "")) // 1024  # KB
        log_message(f"   [{i+1}] {img_name} ({img_size} KB base64)")

    # Use detected_language from Intent Detection (passed from state.py)
    lang = detected_language
    log_message(f"🌐 Vision Pipeline using language: {lang.upper()}")

    # Collect image names for display
    image_names = ", ".join([img.get("name", "unknown") for img in images])
    log_message(f"📷 Analyzing images: {image_names}")

    # === PHASE 1: Vision-LLM OCR extraction ===
    # Note: Status message now shown in state.py for immediate feedback

    # === Get model capabilities (chat template + context window) in single API call ===
    from .vision_utils import get_vision_model_capabilities

    # Ensure backend_url is set (fallback to default Ollama URL)
    if not backend_url:
        backend_url = DEFAULT_OLLAMA_URL
        log_message(f"⚠️ No backend_url provided, using default: {DEFAULT_OLLAMA_URL}")

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
    llm_history: List[Dict[str, str]],
    session_id: Optional[str] = None,
    temperature_mode: str = 'auto',
    temperature: float = 0.2,
    llm_options: Optional[Dict] = None,
    backend_type: str = "ollama",
    backend_url: Optional[str] = None,
    state=None,  # AIState object (REQUIRED for per-agent num_ctx lookup)
    pending_images: Optional[List[Dict[str, str]]] = None,
    vision_json_context: Optional[dict] = None,
    user_name: Optional[str] = None,
    detected_intent: Optional[str] = None,
    detected_language: str = "de",
    cloud_provider_label: Optional[str] = None
) -> AsyncIterator[Dict]:
    """
    Automatik mode: AI decides whether web research is needed

    Note: For Ollama, per-model RoPE 2x toggle is read automatically from VRAM cache.

    Args:
        user_text: User question
        stt_time: STT time (0.0 for text input)
        model_choice: Main LLM for final response
        automatik_model: Automatik-LLM for decision
        history: Chat history (for UI display, tuple format)
        llm_history: LLM history (for LLM context, dict format with role/content)
        session_id: Session ID for research cache (optional)
        temperature_mode: 'auto' (intent detection) or 'manual' (fixed value)
        temperature: Temperature value (0.0-2.0) - only used if mode='manual'
        llm_options: Dict with Ollama options (num_ctx, etc.) - optional
        backend_type: LLM backend ("ollama", "vllm", "tabbyapi")
        backend_url: Backend URL (optional, uses default if not provided)
        state: AIState object (REQUIRED for per-agent num_ctx lookup via get_agent_num_ctx)
        pending_images: List of images (for multimodal messages)
        vision_json_context: Structured data extracted from images by Vision-LLM (optional)
        user_name: User's name for personalized prompts (optional)
        detected_language: Language from LLM-based Intent Detection ("de" or "en")

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

                log_message("🔍 Checking cache for exact duplicates before web research...")
                cache = get_cache()
                cache_result = await cache.query(user_text, n_results=1)

                distance = cache_result.get('distance', 1.0)

                # Check if EXACT duplicate found (distance < 0.05 = practically identical)
                if cache_result['source'] == 'CACHE' and distance < 0.05:
                    # Exact duplicate found - use cached result (avoid redundant research)
                    cache_time = datetime.datetime.fromisoformat(cache_result['metadata']['timestamp'])
                    age_seconds = (datetime.datetime.now() - cache_time).total_seconds()
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

                    # Add to histories (parallel: chat_history + llm_history)
                    # Dict-based chat_history format
                    history.append({
                        "role": "assistant",
                        "content": answer + timing_suffix,
                        "agent": "aifred",
                        "mode": "cache_hit",
                        "round_num": 0,
                        "metadata": {"source": "Vector Cache", "cache_time": cache_time_ms},
                        "timestamp": datetime.datetime.now().isoformat()
                    })
                    # llm_history: answer is already clean (from cache), no metadata
                    answer_clean = strip_thinking_blocks(answer) if answer else ""
                    if answer_clean:
                        llm_history.append({"role": "assistant", "content": f"[AIFRED]: {answer_clean}"})

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

            # Generate queries via research_decision (even for explicit requests)
            # This ensures pre_generated_queries is always provided to perform_agent_research
            yield {"type": "debug", "message": "🔍 Generating search queries..."}

            # Check if images are present (for research_decision context)
            has_images = (pending_images is not None and len(pending_images) > 0) or (vision_json_context is not None)

            research_result = await detect_research_decision(
                user_text=user_text,
                automatik_llm_client=automatik_llm_client,
                automatik_model=automatik_model,
                has_images=has_images,
                vision_json_context=vision_json_context,
                detected_language=detected_language,
                llm_history=llm_history[:-1] if len(llm_history) > 1 else None
            )
            pre_generated_queries = research_result.get("queries", [])
            query_gen_time = research_result.get("decision_time", 0)

            if pre_generated_queries:
                yield {"type": "debug", "message": f"✅ {len(pre_generated_queries)} queries generated ({format_number(query_gen_time, 1)}s)"}
                # Query list is shown in query_processor.py with API assignments
            else:
                # No queries = LLM parsing error. Log and raise for debugging.
                error_msg = "research_decision returned no queries (LLM parsing error?)"
                log_message(f"❌ {error_msg}")
                yield {"type": "debug", "message": f"❌ {error_msg}"}
                raise ValueError(error_msg)

            async for item in perform_agent_research(
                user_text=user_text,
                stt_time=stt_time,
                mode="deep",
                model_choice=model_choice,
                automatik_model=automatik_model,
                history=history,
                llm_history=llm_history,
                session_id=session_id,
                temperature_mode=temperature_mode,
                temperature=temperature,
                llm_options=llm_options,
                backend_type=backend_type,
                backend_url=backend_url,
                state=state,  # Pass state for per-agent num_ctx lookup
                vision_json_context=vision_json_context,  # CRITICAL: Pass Vision JSON to Research flow
                user_name=user_name,  # For personalized prompts
                detected_intent=detected_intent,  # Pass pre-detected intent (avoids duplicate LLM call)
                detected_language=detected_language,  # CRITICAL: Pass language for correct response language
                pre_generated_queries=pre_generated_queries  # Skip Query-Opt LLM call
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

                # Add to histories (parallel: chat_history + llm_history)
                # Dict-based chat_history format
                history.append({
                    "role": "assistant",
                    "content": answer + timing_suffix,
                    "agent": "aifred",
                    "mode": "cache_hit",
                    "round_num": 0,
                    "metadata": {"source": "Vector DB", "cache_time": cache_time},
                    "timestamp": datetime.datetime.now().isoformat()
                })
                # llm_history: answer is already clean (from cache), no metadata
                answer_clean = strip_thinking_blocks(answer) if answer else ""
                if answer_clean:
                    llm_history.append({"role": "assistant", "content": f"[AIFRED]: {answer_clean}"})

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
            yield {"type": "debug", "message": f"⚡ RAG Bypass: {num_sources}/{num_checked} relevant entries → Skip Automatic-LLM"}

            # Use detected_language from Intent Detection (passed from state.py)
            detected_user_language = detected_language
            log_message(f"🌐 Using language from Intent Detection: {detected_user_language.upper()}")

            # Clear progress - no web research needed, show LLM phase
            yield {"type": "progress", "phase": "llm"}

            # Now normal inference WITH timing
            # Build messages using centralized function (v2.16.0+)
            # Uses perspective="aifred" to correctly assign roles for all agents
            from .message_builder import build_messages_from_llm_history

            if multimodal_user_content is not None:
                # Multimodal: Build without user text, then append multimodal content
                messages = build_messages_from_llm_history(
                    llm_history,
                    perspective="aifred",
                    detected_language=detected_user_language
                )
                messages.append({"role": "user", "content": multimodal_user_content})
                log_message("📷 Multimodal content injected into user message")
            else:
                # Standard: Include user text directly
                messages = build_messages_from_llm_history(
                    llm_history,
                    current_user_text=user_text,
                    perspective="aifred",
                    detected_language=detected_user_language
                )

            # Inject minimal system prompt with timestamp (from load_prompt - automatically includes date/time)
            system_prompt_minimal = get_aifred_system_minimal(lang=detected_user_language)
            messages.insert(0, {"role": "system", "content": system_prompt_minimal})

            # Inject RAG context using centralized helper
            inject_rag_context(messages, rag_context)
            log_message(f"💡 RAG context injected into system prompt ({len(rag_context)} chars)")

            # Inject Vision JSON context if available (from Vision-LLM extraction)
            if vision_json_context:
                inject_vision_json_context(messages, vision_json_context)
                log_message(f"📷 Vision JSON injected into AIfred-LLM context ({len(str(vision_json_context))} chars)")

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

            # Log RAW messages for debugging (v2.16.0+)
            from .logging_utils import log_raw_messages
            log_raw_messages("AIfred (RAG Bypass)", llm_messages, estimate_tokens)

            # Temperature decision: Manual Override or Auto (reuse pre-detected intent)
            if temperature_mode == 'manual':
                final_temperature = temperature
                log_message(f"🌡️ RAG Bypass Temperature: {final_temperature} (MANUAL OVERRIDE)")
                yield {"type": "debug", "message": f"🌡️ Temperature: {final_temperature} (manual)"}
            else:
                # Auto: Reuse detected_intent from state.py (no duplicate LLM call)
                final_temperature = get_temperature_for_intent(detected_intent)
                temp_label = get_temperature_label(detected_intent)
                log_message(f"🌡️ RAG Bypass Temperature: {final_temperature} (Intent: {detected_intent})")
                yield {"type": "debug", "message": f"🌡️ Temperature: {final_temperature} (auto, {temp_label})"}

            # Calculate num_ctx using centralized function (respects per-agent settings)
            from .research.context_utils import get_agent_num_ctx
            if state:
                final_num_ctx, ctx_source = get_agent_num_ctx("aifred", state, model_choice)
                yield {"type": "debug", "message": f"🎯 num_ctx: {format_number(final_num_ctx)} ({ctx_source})"}
            else:
                # Fallback if no state available (shouldn't happen)
                rope_factor = get_rope_factor_for_model(model_choice)
                final_num_ctx = get_ollama_calibration(model_choice, rope_factor) or 4096
                yield {"type": "debug", "message": f"🎯 num_ctx: {format_number(final_num_ctx)} (fallback)"}

            # Get model max context for compact display
            model_limit, _ = await llm_client.get_model_context_limit(model_choice)

            yield {"type": "debug", "message": "✅ System prompt created"}

            # Show compact context info (like Automatik-LLM and Web-Research)
            yield {"type": "debug", "message": f"📊 AIfred-LLM: {format_number(input_tokens)} / {format_number(final_num_ctx)} tok (Model Max: {format_number(model_limit)} tok)"}
            log_message(f"📊 AIfred-LLM ({model_choice}): Input ~{format_number(input_tokens)} tok, num_ctx: {format_number(final_num_ctx)}, max: {format_number(model_limit)}")

            # Console: LLM starts
            yield {"type": "debug", "message": f"🎩 AIfred-LLM starting: {model_choice}"}

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
            tokens_prompt = metrics.get("tokens_prompt", 0)
            tokens_per_sec = metrics.get("tokens_per_second", 0)
            # Cloud APIs: Show output tokens + total (output for history, total for billing)
            if backend_type == "cloud_api" and tokens_prompt > 0:
                total_tokens = tokens_prompt + tokens_generated
                yield {"type": "debug", "message": f"✅ AIfred-LLM done ({format_number(inference_time, 1)}s, {format_number(tokens_generated)} out / {format_number(total_tokens)} total, {format_number(tokens_per_sec, 1)} tok/s)"}
            else:
                yield {"type": "debug", "message": f"✅ AIfred-LLM done ({format_number(inference_time, 1)}s, {format_number(tokens_generated)} tok, {format_number(tokens_per_sec, 1)} tok/s)"}

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

            # AI response with timing + source (RAG) + model name
            source_label = f"Cache+LLM RAG ({model_choice})"
            ttft_str = f"TTFT: {format_number(ttft, 2)}s    " if ttft is not None else ""
            metadata_str = format_metadata(f"{ttft_str}Inference: {format_number(inference_time, 1)}s    {format_number(tokens_per_sec, 1)} tok/s    Source: {source_label}")
            ai_with_source = f"{thinking_html}\n\n{metadata_str}"

            # Add AI response to histories (parallel: chat_history + llm_history)
            # User message was already added by state.py before calling this function
            # Dict-based chat_history format
            history.append({
                "role": "assistant",
                "content": ai_with_source,
                "agent": "aifred",
                "mode": "rag",
                "round_num": 0,
                "metadata": {
                    "ttft": ttft,
                    "inference_time": inference_time,
                    "tokens_per_sec": tokens_per_sec,
                    "source": source_label
                },
                "timestamp": datetime.datetime.now().isoformat()
            })
            # llm_history: ai_text is raw LLM output, strip thinking blocks
            ai_text_clean = strip_thinking_blocks(ai_text) if ai_text else ""
            if ai_text_clean:
                llm_history.append({"role": "assistant", "content": f"[AIFRED]: {ai_text_clean}"})

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

        # Use detected_language from Intent Detection (passed from state.py)
        detected_user_language = detected_language
        log_message(f"🌐 Using language from Intent Detection: {detected_user_language.upper()}")

        # Step 1: Combined Research Decision (Decision-Making + Query-Optimization in 1 call)
        # Check if images are present OR if Vision JSON context exists
        has_images = (pending_images is not None and len(pending_images) > 0) or (vision_json_context is not None)

        try:
            # Measure time for decision
            log_message(f"🤖 Research Decision with {automatik_model}")
            yield {"type": "progress", "phase": "automatik"}

            # NEW: Combined research decision (replaces Decision-Making + Query-Optimization)
            research_result = await detect_research_decision(
                user_text=user_text,
                automatik_llm_client=automatik_llm_client,
                automatik_model=automatik_model,
                has_images=has_images,
                vision_json_context=vision_json_context,
                detected_language=detected_user_language,
                llm_history=llm_history[:-1] if len(llm_history) > 1 else None
            )

            decision_time = research_result["decision_time"]
            web_research_needed = research_result["web"]
            pre_generated_queries = research_result["queries"]

            # User-friendly display
            decision_label = "Web Research YES" if web_research_needed else "Web Research NO"
            yield {"type": "debug", "message": f"🤖 Decision: {decision_label} ({format_number(decision_time, 1)}s)"}

            if web_research_needed and pre_generated_queries:
                yield {"type": "debug", "message": f"🔎 {len(pre_generated_queries)} queries pre-generated"}
                # Query list with API assignments shown in query_processor.py

            log_message(f"🤖 AI decision: {decision_label} ({format_number(decision_time, 1)}s)")

            # ============================================================
            # Parse decision AND respect it!
            # ============================================================
            if web_research_needed:
                log_message("✅ AI decides: NEW web research needed")

                # Start web research - Forward all yields
                # Pass pre-generated queries to avoid duplicate Query-Optimization LLM call
                async for item in perform_agent_research(
                    user_text=user_text,
                    stt_time=stt_time,
                    mode="deep",
                    model_choice=model_choice,
                    automatik_model=automatik_model,
                    history=history,
                    llm_history=llm_history,
                    session_id=session_id,
                    temperature_mode=temperature_mode,
                    temperature=temperature,
                    llm_options=llm_options,
                    backend_type=backend_type,
                    backend_url=backend_url,
                    state=state,  # Pass state for per-agent num_ctx lookup
                    vision_json_context=vision_json_context,
                    user_name=user_name,
                    detected_intent=detected_intent,
                    pre_generated_queries=pre_generated_queries  # NEW: Skip Query-Opt if provided
                ):
                    yield item
                return

            else:
                # AI decides: Own knowledge sufficient → use centralized handler
                log_message("❌ AI decides: Own knowledge sufficient → No agent")
                yield {"type": "debug", "message": "🤖 Decision: No web research needed"}

                # Use centralized handle_own_knowledge() function
                from .own_knowledge_handler import handle_own_knowledge

                # Get enable_thinking from llm_options
                enable_thinking = llm_options.get('enable_thinking', False) if llm_options else False

                # Track result for post-processing
                own_knowledge_result = None

                async for item in handle_own_knowledge(
                    user_text=user_text,
                    model_choice=model_choice,
                    llm_history=llm_history,
                    detected_intent=detected_intent,
                    detected_language=detected_user_language,
                    temperature_mode=temperature_mode,
                    temperature=temperature,
                    backend_type=backend_type,
                    backend_url=backend_url,
                    enable_thinking=enable_thinking,
                    state=state,
                    use_direct_prompt=False,  # Automatik mode doesn't use direct prompt
                    multimodal_content=multimodal_user_content,
                    rag_context=rag_context,
                    vision_json_context=vision_json_context,
                    stt_time=stt_time,
                    cloud_provider_label=cloud_provider_label,
                ):
                    # Forward debug/content/progress messages
                    if item["type"] in ["debug", "content", "progress"]:
                        yield item
                    elif item["type"] == "result":
                        own_knowledge_result = item["data"]

                # Process result and yield in expected format for state.py
                if own_knowledge_result:
                    # Yield separator
                    yield {"type": "debug", "message": CONSOLE_SEPARATOR}

                    # Yield result with source marker for state.py to handle history
                    yield {
                        "type": "result",
                        "data": {
                            "response_raw": own_knowledge_result["response_raw"],
                            "response_clean": own_knowledge_result["response_clean"],
                            "response_html": own_knowledge_result["response_html"],
                            "inference_time": own_knowledge_result["inference_time"],
                            "tokens_per_sec": own_knowledge_result["tokens_per_sec"],
                            "ttft": own_knowledge_result["ttft"],
                            "model_choice": own_knowledge_result["model_choice"],
                            "decision_time": decision_time,
                            "stt_time": stt_time,
                            "rag_context": rag_context,
                            "source": "own_knowledge",  # Mark source for state.py
                        }
                    }

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
