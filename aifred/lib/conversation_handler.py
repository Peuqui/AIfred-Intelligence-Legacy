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
from typing import Any, Dict, List, Optional, AsyncIterator

from .llm_client import LLMClient
from .timer import Timer
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
from .formatting import format_thinking_process, format_number, format_age, build_inference_metadata
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


def _select_history_for_context(
    llm_history: List[Dict[str, str]],
    effective_ctx: int
) -> List[Dict[str, str]]:
    """
    Build a history subset that fits within a token budget (2/3 of effective_ctx).

    Iterates from newest to oldest entries, adding until the token limit is reached.

    Args:
        llm_history: Full LLM history (list of role/content dicts)
        effective_ctx: Effective context window size in tokens

    Returns:
        Selected history entries (chronological order), fitting within budget.
    """
    max_history_tokens = (effective_ctx * 2) // 3
    history_tokens = 0
    selected_history: List[Dict[str, str]] = []

    for entry in reversed(llm_history):
        entry_tokens = estimate_tokens([entry])
        if history_tokens + entry_tokens > max_history_tokens:
            break
        selected_history.insert(0, entry)
        history_tokens += entry_tokens

    return selected_history


def _repair_json(s: str) -> str:
    """Fix common LLM JSON errors like ]] instead of ]}."""
    # Fix double brackets: ]] → ]}
    s = re.sub(r'\]\](?=\s*$)', ']}', s)
    s = re.sub(r'\]\](?=\s*})', ']}', s)
    # Fix missing closing brace
    if s.count('{') > s.count('}'):
        s = s + '}'
    return s


def _parse_json_with_recovery(response: str, context: str) -> Any:
    """
    Parse a JSON string with recovery strategies for common LLM errors.

    Tries: direct parse -> repair -> extract from text -> raise ValueError.

    Args:
        response: Raw response string (potentially containing JSON)
        context: Description for error messages (e.g., "research_decision")

    Returns:
        Parsed JSON as dict.

    Raises:
        ValueError: If all parse attempts fail.
    """
    try:
        return json.loads(response)
    except json.JSONDecodeError as e1:
        log_message(f"⚠️ JSON parse error ({context}): {e1}")
        # Try repair
        repaired = _repair_json(response)
        log_message(f"🔧 Attempting JSON repair: {repaired}")
        try:
            result = json.loads(repaired)
            log_message("✅ JSON repair successful")
            return result
        except json.JSONDecodeError:
            # Try extract JSON from text
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                try:
                    extracted = _repair_json(json_match.group())
                    result = json.loads(extracted)
                    log_message("✅ JSON extraction + repair successful")
                    return result
                except json.JSONDecodeError as e3:
                    error_msg = f"JSON parse failed after all repair attempts ({context}): {e3}\nRaw: {response}"
                    log_message(f"❌ {error_msg}")
                    raise ValueError(error_msg)
            else:
                error_msg = f"No JSON found in response ({context}): {response}"
                log_message(f"❌ {error_msg}")
                raise ValueError(error_msg)


async def _process_single_image_vision(
    image: Dict[str, str],
    image_index: int,
    vision_model: str,
    backend_type: str,
    backend_url: Optional[str],
    num_ctx: int,
    supports_chat_template: bool,
    lang: str,
    llm_options: Optional[Dict] = None,
    provider: Optional[str] = None  # Cloud API provider
) -> Dict:
    """
    Process a single image with Vision-LLM.

    This helper function handles the actual Vision-LLM call for one image.
    Used by chat_with_vision_pipeline() for sequential multi-image processing.

    Args:
        image: Dict with "name" and "path" keys (path to JPEG file)
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
    from .vision_utils import load_image_as_base64
    from pathlib import Path

    img_name = image.get("name", f"image_{image_index + 1}")
    log_message(f"📷 [{image_index + 1}] Processing: {img_name}")

    # Build content parts for single image
    content_parts: list[dict[str, Any]] = []

    # Add default prompt for template-less models
    if not supports_chat_template:
        model_lower = vision_model.lower()
        if "ocr" in model_lower or "deepseek-ocr" in model_lower:
            default_prompt = get_vision_templateless_ocr_prompt(lang=lang)
            log_message(f"📝 Vision Prompt: vision_templateless_ocr.txt ({lang})")
        else:
            default_prompt = get_vision_templateless_default_prompt(lang=lang)
            log_message(f"📝 Vision Prompt: vision_ocr.txt ({lang})")
        content_parts.append({"type": "text", "text": default_prompt})

    # Add single image (load from file on-demand)
    image_path = Path(image['path'])
    log_message(f"📂 Loading image: {image_path}")
    base64_data = load_image_as_base64(image_path)
    log_message(f"📦 Base64 size: {len(base64_data)} chars ({len(base64_data) // 1024} KB)")
    content_parts.append({
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{base64_data}"}
    })

    # Build messages
    if supports_chat_template:
        vision_system_prompt = get_vision_ocr_prompt(lang=lang)
        log_message(f"📝 Vision Prompt: vision_ocr.txt [system] ({lang})")

        # Add /no_think to user content if thinking is disabled
        # This is needed because Qwen3-VL ignores the API "think" parameter
        enable_thinking = (llm_options or {}).get('enable_thinking', True)
        if not enable_thinking:
            # Prepend /no_think as text before the image
            content_parts.insert(0, {"type": "text", "text": "/no_think"})

        messages = [
            LLMMessage(role="system", content=vision_system_prompt),
            LLMMessage(role="user", content=content_parts)
        ]
    else:
        messages = [
            LLMMessage(role="user", content=content_parts)
        ]

    # Call Vision-LLM
    llm_client = LLMClient(backend_type=backend_type, base_url=backend_url, provider=provider)

    from .config import VISION_MODEL_TEMPERATURE
    vision_options = {
        "temperature": VISION_MODEL_TEMPERATURE,
        "num_ctx": num_ctx,
        **(llm_options or {})
    }
    # Note: num_predict intentionally NOT set for Vision
    # - Ollama ignores it for thinking models anyway
    # - For OCR, we want complete output without arbitrary limits

    timer = Timer()
    response_text = ""
    metrics = None
    ttft = None  # Time To First Token

    try:
        async for chunk in llm_client.chat_stream(
            model=vision_model,
            messages=messages,  # type: ignore[arg-type]
            options=vision_options
        ):
            if chunk.get("type") == "content":
                if ttft is None:
                    ttft = timer.elapsed()
                response_text += chunk.get("text", "")
            elif chunk.get("type") == "done":
                metrics = chunk.get("metrics", {})

        elapsed = timer.elapsed()

        # Inject TTFT into backend metrics (backend doesn't provide it)
        if metrics is not None and ttft is not None:
            metrics["ttft"] = ttft

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
        elapsed = timer.elapsed()
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
    llm_history: Optional[List[Dict[str, str]]] = None,
    automatik_num_ctx: Optional[int] = None
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

    # Effective context for history budget calculation
    effective_ctx = automatik_num_ctx or AUTOMATIK_LLM_NUM_CTX

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
    messages: List[LLMMessage] = []

    if llm_history and len(llm_history) > 0:
        selected_history = _select_history_for_context(llm_history, effective_ctx)

        # Add history messages
        for entry in selected_history:
            role = entry.get("role", "user")
            content = entry.get("content", "")
            # Strip [AIFRED]: prefix for cleaner context
            if content.startswith("[AIFRED]:"):
                content = content[9:].strip()
            messages.append(LLMMessage(role=role, content=content))

        if selected_history:
            history_tokens = estimate_tokens(selected_history)
            log_message(f"📜 History context: {len(selected_history)} entries, ~{int(history_tokens)} tokens")

    # Add the actual prompt as final user message
    messages.append(LLMMessage(role="user", content=prompt))

    # LLM options: JSON format for reliable parsing
    options: Dict = {
        "temperature": 0.2,  # Low for consistent decisions
        "enable_thinking": False,  # Fast decisions
        "format": "json"  # Request JSON output format (Ollama)
    }
    if automatik_num_ctx is not None:
        options["num_ctx"] = automatik_num_ctx

    decision_timer = Timer()

    # DEBUG: Log raw messages sent to Automatik-LLM
    log_raw_messages("AUTOMATIK-LLM (detect_research_decision)", messages, estimate_tokens)

    try:
        response = await automatik_llm_client.chat(
            model=automatik_model,
            messages=messages,
            options=options
        )
        raw_response = strip_thinking_blocks(response.text).strip()
        decision_time = decision_timer.elapsed()

        # DEBUG: Log raw response
        log_message("=" * 60)
        log_message("📝 RAW RESEARCH DECISION RESPONSE:")
        log_message("-" * 60)
        log_message(raw_response)
        log_message("-" * 60)
        log_message(f"Response length: {len(raw_response)} chars, time: {decision_time:.2f}s")
        log_message("=" * 60)

        # Parse JSON response
        result = _parse_json_with_recovery(raw_response, "research_decision")

        # Normalize result
        web_needed = result.get("web", False)
        queries = result.get("queries", [])
        volatility = result.get("volatility", "DAILY")  # Fallback to DAILY if not specified

        # Validate queries if web research is needed
        if web_needed and not queries:
            log_message("⚠️ web=true but no queries, setting web=false")
            web_needed = False

        log_message(f"✅ Research Decision: web={web_needed}, {len(queries)} queries, volatility={volatility}")

        return {
            "web": web_needed,
            "queries": queries,
            "volatility": volatility,
            "decision_time": decision_time,
            "raw_response": raw_response
        }

    except Exception as e:
        decision_time = decision_timer.elapsed()
        log_message(f"❌ Research decision failed ({decision_time:.2f}s): {e}")
        # NO FALLBACK - re-raise to make the error visible!
        raise


async def generate_search_queries(
    user_text: str,
    automatik_llm_client,
    automatik_model: str,
    has_images: bool = False,
    vision_json_context: Optional[Dict] = None,
    detected_language: str = "de",
    llm_history: Optional[List[Dict[str, str]]] = None,
    automatik_num_ctx: Optional[int] = None
) -> Dict:
    """
    Generate search queries WITHOUT deciding if web search is needed.

    Used in explicit web search modes (quick/deep) where the user has
    already decided that web search is needed. This function ONLY generates
    3 optimized search queries.

    Args:
        user_text: User query text
        automatik_llm_client: LLM client for Automatik-Model
        automatik_model: Automatik-LLM model name (e.g., "qwen3:4b")
        has_images: Whether the message includes image(s)
        vision_json_context: Structured data extracted from images
        detected_language: Language from Intent Detection ("de" or "en")
        llm_history: Optional chat history for context

    Returns:
        Dict with keys:
        - "queries": List[str] (3 optimized queries)
        - "generation_time": float (LLM call duration in seconds)
        - "raw_response": str (for debugging)
    """
    from .config import AUTOMATIK_LLM_NUM_CTX
    from ..backends.base import LLMMessage
    from .prompt_loader import get_query_generation_prompt

    # Get the query-only prompt
    prompt = get_query_generation_prompt(
        user_text=user_text,
        has_images=has_images,
        vision_json=vision_json_context,
        lang=detected_language
    )

    # DEBUG: Show complete prompt
    log_message("=" * 60)
    log_message("📋 QUERY GENERATION PROMPT:")
    log_message("-" * 60)
    log_message(prompt)
    log_message("-" * 60)
    log_message(f"Prompt length: {len(prompt)} chars, ~{len(prompt.split())} words")
    log_message("=" * 60)

    # Build messages with optional history context
    messages: List[LLMMessage] = []

    effective_ctx = automatik_num_ctx or AUTOMATIK_LLM_NUM_CTX
    if llm_history and len(llm_history) > 0:
        selected_history = _select_history_for_context(llm_history, effective_ctx)

        for entry in selected_history:
            role = entry.get("role", "user")
            content = entry.get("content", "")
            if content.startswith("[AIFRED]:"):
                content = content[9:].strip()
            messages.append(LLMMessage(role=role, content=content))

        if selected_history:
            history_tokens = estimate_tokens(selected_history)
            log_message(f"📜 History context: {len(selected_history)} entries, ~{int(history_tokens)} tokens")

    messages.append(LLMMessage(role="user", content=prompt))

    options: Dict = {
        "temperature": 0.3,  # Slightly higher for query diversity
        "enable_thinking": False,
        "format": "json"
    }
    if automatik_num_ctx is not None:
        options["num_ctx"] = automatik_num_ctx

    generation_timer = Timer()

    log_raw_messages("AUTOMATIK-LLM (generate_search_queries)", messages, estimate_tokens)

    try:
        response = await automatik_llm_client.chat(
            model=automatik_model,
            messages=messages,
            options=options
        )
        raw_response = strip_thinking_blocks(response.text).strip()
        generation_time = generation_timer.elapsed()

        log_message("=" * 60)
        log_message("📝 RAW QUERY GENERATION RESPONSE:")
        log_message("-" * 60)
        log_message(raw_response)
        log_message("-" * 60)
        log_message(f"Response length: {len(raw_response)} chars, time: {generation_time:.2f}s")
        log_message("=" * 60)

        # Parse JSON response
        result = _parse_json_with_recovery(raw_response, "query_generation")

        queries = result.get("queries", [])

        # Validate: must have at least 1 query - NO FALLBACK, raise error
        if not queries:
            error_msg = "LLM returned no queries (parsing error?)"
            log_message(f"❌ {error_msg}")
            raise ValueError(error_msg)

        log_message(f"✅ Query Generation: {len(queries)} queries")

        return {
            "queries": queries,
            "generation_time": generation_time,
            "raw_response": raw_response
        }

    except Exception as e:
        generation_time = generation_timer.elapsed()
        log_message(f"❌ Query generation failed ({generation_time:.2f}s): {e}")
        # NO FALLBACK - re-raise to make error visible
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
    detected_language: str = "de",  # Language from Intent Detection or UI setting
    provider: Optional[str] = None  # Cloud API provider ("claude", "qwen", "kimi")
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
        backend_type: "ollama", "llamacpp", "vllm", "tabbyapi"
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
        # Use size_kb from pending_images (set during upload), not base64 length
        img_size = img.get("size_kb", 0)
        log_message(f"   [{i+1}] {img_name} ({img_size} KB)")

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

    # Ensure backend_url is set (fallback based on backend type)
    if not backend_url:
        if backend_type == "cloud_api":
            # Cloud API URL is determined by provider in BackendFactory - don't override!
            log_message("📋 Cloud API: URL will be set by provider config")
        else:
            backend_url = DEFAULT_OLLAMA_URL
            log_message(f"⚠️ No backend_url provided, using default: {DEFAULT_OLLAMA_URL}")

    log_message(f"📐 Reading model capabilities for Vision-LLM ({vision_model})...")

    # Cloud API doesn't have /api/show endpoint - use sensible defaults
    intrinsic_num_ctx: Optional[int]
    if backend_type == "cloud_api":
        supports_chat_template = True  # Cloud APIs always support chat format
        intrinsic_num_ctx = 128000     # Most cloud models have 128K+ context
        log_message("📋 Cloud API: assuming chat support, 128K context")
    else:
        assert backend_url is not None, "backend_url required for non-cloud backends"
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

    # === Vision num_ctx: Use calibrated value from VRAM cache ===
    # The calibrated max_context is the experimentally measured maximum that fits
    # in GPU memory without CPU offloading. This is the ONLY reliable source.
    #
    # Why not calculate dynamically?
    # - Thinking models need the FULL context for <think> blocks (can be 40K+ tokens)
    # - Hardcoded "response reserves" are arbitrary guesses
    # - The calibration was done with THIS model on THIS hardware = accurate
    #
    # vram_num_ctx comes from calculate_vram_based_context() which already
    # checks the calibration cache first (see gpu_utils.py line 543-566)

    # Model limit (fallback to 128K if detection failed)
    model_limit = intrinsic_num_ctx or 131072

    # Check for manual vision context override (PERSISTENT setting from UI)
    # Note: num_predict removed - Ollama ignores it for thinking models anyway
    if state and getattr(state, 'vision_num_ctx_enabled', False):
        manual_ctx = getattr(state, 'vision_num_ctx', 32768)
        num_ctx = min(manual_ctx, model_limit)
        ctx_msg1 = f"🎯 Vision Context: {format_number(num_ctx)} tok (MANUAL)"
        ctx_msg2 = f"   (Manual: {format_number(manual_ctx)}, Model-max: {format_number(model_limit)})"
    else:
        # Use the VRAM-calibrated context directly (no "needed" calculation!)
        num_ctx = min(vram_num_ctx, model_limit)
        ctx_msg1 = f"🎯 Vision Context: {format_number(num_ctx)} tok (calibrated)"
        ctx_msg2 = f"   (VRAM-max: {format_number(vram_num_ctx)}, Model-max: {format_number(model_limit)})"

    # Log the context choice
    yield {"type": "debug", "message": ctx_msg1}
    yield {"type": "debug", "message": ctx_msg2}

    # ============================================================
    # SEQUENTIAL IMAGE PROCESSING (v2.6.0)
    # Process images one at a time for better model accuracy!
    # Even large Vision models produce inconsistent results with
    # multiple images in one request.
    # ============================================================

    num_images = len(images)
    vision_timer = Timer()
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
            llm_options=llm_options,
            provider=provider
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
                llm_options=llm_options,
                provider=provider
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

        total_time = vision_timer.elapsed()
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


async def _handle_own_knowledge_mode(
    user_text: str,
    model_choice: str,
    history: List,
    llm_history: List[Dict[str, str]],
    detected_intent: Optional[str],
    detected_language: str,
    temperature_mode: str,
    temperature: float,
    backend_type: str,
    backend_url: Optional[str],
    llm_options: Optional[Dict],
    state: Any,
    multimodal_user_content: Optional[list],
    cloud_provider_label: Optional[str],
) -> AsyncIterator[Dict]:
    """Handle research_mode == "none": Direct LLM response from own knowledge."""
    log_message("🧠 Own Knowledge mode: Direct LLM response (no web)")
    yield {"type": "debug", "message": "🧠 Own Knowledge mode"}

    from .own_knowledge_handler import handle_own_knowledge
    enable_thinking = llm_options.get('enable_thinking', False) if llm_options else False

    async for item in handle_own_knowledge(
        user_text=user_text,
        model_choice=model_choice,
        history=history,
        llm_history=llm_history,
        detected_intent=detected_intent or "chat",
        detected_language=detected_language,
        temperature_mode=temperature_mode,
        temperature=temperature,
        backend_type=backend_type,
        backend_url=backend_url,
        enable_thinking=enable_thinking,
        state=state,
        use_direct_prompt=False,
        multimodal_content=multimodal_user_content,
        cloud_provider_label=cloud_provider_label,
    ):
        if item["type"] in ["debug", "content", "progress"]:
            yield item
        elif item["type"] == "result":
            yield {"type": "debug", "message": CONSOLE_SEPARATOR}
            yield item


async def _handle_forced_web_search(
    user_text: str,
    stt_time: float,
    research_mode: str,
    model_choice: str,
    automatik_model: str,
    history: List,
    llm_history: List[Dict[str, str]],
    session_id: Optional[str],
    temperature_mode: str,
    temperature: float,
    llm_options: Optional[Dict],
    backend_type: str,
    backend_url: Optional[str],
    state: Any,
    automatik_llm_client: Any,
    pending_images: Optional[List[Dict[str, str]]],
    vision_json_context: Optional[dict],
    user_name: Optional[str],
    detected_intent: Optional[str],
    detected_language: str,
    automatik_num_ctx: Optional[int],
) -> AsyncIterator[Dict]:
    """Handle research_mode in ["quick", "deep"]: Forced web search with query generation."""
    log_message(f"🔍 Explicit Web mode: {research_mode} (forced search)")
    yield {"type": "debug", "message": f"🔍 Web mode: {research_mode}"}
    yield {"type": "debug", "message": "🔍 Generating search queries..."}

    # Generate queries (NO decision - web is forced)
    has_images = (pending_images is not None and len(pending_images) > 0) or (vision_json_context is not None)

    query_result = await generate_search_queries(
        user_text=user_text,
        automatik_llm_client=automatik_llm_client,
        automatik_model=automatik_model,
        has_images=has_images,
        vision_json_context=vision_json_context,
        detected_language=detected_language,
        llm_history=llm_history[:-1] if len(llm_history) > 1 else None,
        automatik_num_ctx=automatik_num_ctx
    )

    pre_generated_queries = query_result["queries"]
    query_gen_time = query_result["generation_time"]

    yield {"type": "debug", "message": f"✅ {len(pre_generated_queries)} queries ({format_number(query_gen_time, 1)}s)"}
    for i, q in enumerate(pre_generated_queries, 1):
        yield {"type": "debug", "message": f"   {i}. {q}"}

    # Execute web research
    async for item in perform_agent_research(
        user_text=user_text,
        stt_time=stt_time,
        mode=research_mode,  # "quick" or "deep"
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
        state=state,
        vision_json_context=vision_json_context,
        user_name=user_name,
        detected_intent=detected_intent,
        detected_language=detected_language,
        pre_generated_queries=pre_generated_queries,
        automatik_num_ctx=automatik_num_ctx
    ):
        yield item


async def _handle_rag_bypass(
    user_text: str,
    model_choice: str,
    history: List,
    llm_history: List[Dict[str, str]],
    rag_context: str,
    num_sources: int,
    num_checked: int,
    detected_language: str,
    temperature_mode: str,
    temperature: float,
    detected_intent: Optional[str],
    llm_options: Optional[Dict],
    backend_type: str,
    backend_url: Optional[str],
    state: Any,
    llm_client: Any,
    multimodal_user_content: Optional[list],
    vision_json_context: Optional[dict],
) -> AsyncIterator[Dict]:
    """Handle RAG bypass: LLM inference with RAG context (skip Automatik-LLM decision)."""
    log_message(f"✅ RAG context available ({num_sources} relevant entries) → Bypass Automatik-LLM, direct to main LLM")
    yield {"type": "debug", "message": f"⚡ RAG Bypass: {num_sources}/{num_checked} relevant entries → Skip Automatic-LLM"}

    # Use detected_language from Intent Detection (passed from state.py)
    detected_user_language = detected_language
    log_message(f"🌐 Using language from Intent Detection: {detected_user_language.upper()}")

    # Clear progress - no web research needed, show LLM phase
    yield {"type": "progress", "phase": "llm"}

    # Build messages using centralized function
    from .message_builder import build_messages_from_llm_history

    if multimodal_user_content is not None:
        # Multimodal: Build without user text, then append multimodal content
        messages: list[dict[str, Any]] = build_messages_from_llm_history(
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

    # Inject minimal system prompt with timestamp
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

    # Log RAW messages for debugging
    log_raw_messages("AIfred (RAG Bypass)", llm_messages, estimate_tokens)

    # Temperature decision: Manual Override or Auto (reuse pre-detected intent)
    if temperature_mode == 'manual':
        final_temperature = temperature
        log_message(f"🌡️ RAG Bypass Temperature: {final_temperature} (MANUAL OVERRIDE)")
        yield {"type": "debug", "message": f"🌡️ Temperature: {final_temperature} (manual)"}
    else:
        # Auto: Reuse detected_intent from state.py (no duplicate LLM call)
        intent = detected_intent or "chat"
        final_temperature = get_temperature_for_intent(intent)
        temp_label = get_temperature_label(intent)
        log_message(f"🌡️ RAG Bypass Temperature: {final_temperature} (Intent: {intent})")
        yield {"type": "debug", "message": f"🌡️ Temperature: {final_temperature} (auto, {temp_label})"}

    # Calculate num_ctx using centralized function (respects per-agent settings)
    from .research.context_utils import get_agent_num_ctx
    if state:
        final_num_ctx, ctx_source = get_agent_num_ctx("aifred", state, model_choice)
        yield {"type": "debug", "message": f"🎯 Context: {format_number(final_num_ctx)} ({ctx_source})"}
    else:
        # Fallback if no state available (shouldn't happen)
        rope_factor = get_rope_factor_for_model(model_choice)
        final_num_ctx = get_ollama_calibration(model_choice, rope_factor) or 4096
        yield {"type": "debug", "message": f"🎯 Context: {format_number(final_num_ctx)} (fallback)"}

    # Get native context limit for display (local read, no API call!)
    from .research.context_utils import get_model_native_context
    model_limit = get_model_native_context(model_choice, backend_type)

    yield {"type": "debug", "message": "✅ System prompt created"}

    # Show compact context info (like Automatik-LLM and Web-Research)
    yield {"type": "debug", "message": f"📊 AIfred-LLM: {format_number(input_tokens)} / {format_number(final_num_ctx)} tok (Model Max: {format_number(model_limit)} tok)"}
    log_message(f"📊 AIfred-LLM ({model_choice}): Input ~{format_number(input_tokens)} tok, Context: {format_number(final_num_ctx)}, max: {format_number(model_limit)}")

    # Console: LLM starts (with MoE/Dense architecture + calibration info)
    from aifred.lib.gpu_utils import is_moe_model
    is_moe = is_moe_model(model_choice) if backend_type in ("ollama", "llamacpp") else False
    arch_label = "MoE" if is_moe else "Dense"
    if backend_type == "llamacpp":
        from aifred.lib.model_vram_cache import get_llamacpp_calibration_info
        _cal = get_llamacpp_calibration_info(model_choice)
        if _cal and _cal["mode"] == "hybrid":
            arch_label += f", hybrid ngl={_cal['ngl']}"
    yield {"type": "debug", "message": f"🎩 AIfred-LLM starting: {model_choice} ({arch_label})"}

    # Build main LLM options (include enable_thinking from user settings)
    main_llm_options: Dict[str, Any] = {
        'temperature': final_temperature,  # Adaptive or manual temperature!
        'num_ctx': final_num_ctx  # Dynamically calculated or user-specified
    }

    # Add enable_thinking and sampling params if provided in llm_options (user toggle)
    if llm_options:
        for key in ('enable_thinking', 'top_k', 'top_p', 'min_p', 'repeat_penalty'):
            if key in llm_options:
                main_llm_options[key] = llm_options[key]

    # Add supports_thinking from state (prevents 400 errors for calibrated models)
    if state and backend_type in ("ollama", "llamacpp"):
        main_llm_options['supports_thinking'] = state.aifred_supports_thinking

    # VRAM Monitoring: Measure before inference (baseline)
    from aifred.lib.gpu_utils import get_free_vram_mb
    vram_before_inference = get_free_vram_mb()

    # Time measurement for final inference - STREAM response
    inference_timer = Timer()
    ai_text = ""
    metrics: Dict = {}
    ttft = None
    first_token_received = False
    vram_measurement = None

    async for chunk in llm_client.chat_stream(
        model=model_choice,
        messages=llm_messages,  # type: ignore[arg-type]
        options=main_llm_options
    ):
        if chunk["type"] == "content":
            # Measure TTFT
            if not first_token_received:
                ttft = inference_timer.elapsed()
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

    inference_time = inference_timer.elapsed()
    tokens_generated = metrics.get("tokens_generated", 0)
    tokens_prompt = metrics.get("tokens_prompt", 0)
    tokens_per_sec = metrics.get("tokens_per_second", 0)

    # Update llm_history BEFORE calculating history_tokens (SSoT)
    # so "History: X tok" reflects the current conversation state (incl. AI response)
    ai_text_clean = strip_thinking_blocks(ai_text) if ai_text else ""
    state._sync_to_llm_history("aifred", ai_text)

    # Centralized metadata (PP speed, debug log, chat bubble)
    from .context_manager import estimate_tokens_from_llm_history
    history_tokens = estimate_tokens_from_llm_history(llm_history)
    source_label = f"Cache+LLM RAG ({model_choice})"

    metadata_dict, metadata_display, debug_msg = build_inference_metadata(
        ttft=ttft,
        inference_time=inference_time,
        tokens_generated=tokens_generated,
        tokens_per_sec=tokens_per_sec,
        source=source_label,
        backend_metrics=metrics,
        tokens_prompt=tokens_prompt,
        history_tokens=history_tokens,
        backend_type=backend_type,
    )
    yield {"type": "debug", "message": debug_msg}

    # VRAM Monitoring: Log and save measurement
    if vram_measurement is not None:
        from aifred.lib.model_vram_cache import add_vram_measurement
        from aifred.lib.gpu_utils import is_moe_model as is_moe_model_check

        # Determine architecture for cache
        is_moe = is_moe_model_check(model_choice) if backend_type in ("ollama", "llamacpp") else False
        architecture = "moe" if is_moe else "dense"

        # Save measurement to unified cache
        assert vram_before_inference is not None  # guaranteed by guard above
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

    # Format <think> tags as collapsible for chat history (visible as collapsible!)
    thinking_html = format_thinking_process(ai_text, model_name=model_choice, inference_time=inference_time, tokens_per_sec=tokens_per_sec)

    # AI response with thinking collapsible + metadata
    ai_with_source = f"{thinking_html}\n\n{metadata_display}"

    # Add AI response to histories (parallel: chat_history + llm_history)
    # User message was already added by state.py before calling this function
    history.append({
        "role": "assistant",
        "content": ai_with_source,
        "agent": "aifred",
        "mode": "rag",
        "round_num": 0,
        "metadata": metadata_dict,
        "timestamp": datetime.datetime.now().isoformat(),
        "has_audio": False,
        "audio_urls_json": "[]"
    })
    # llm_history already updated above (before metadata calculation)

    # Separator after LLM response block (end of unit)
    from .logging_utils import console_separator
    console_separator()
    yield {"type": "debug", "message": CONSOLE_SEPARATOR}

    # Clear progress before final result
    yield {"type": "progress", "clear": True}

    # Return result - unified Dict format
    yield {
        "type": "result",
        "data": {
            "response_clean": ai_text_clean,
            "response_html": ai_with_source,
            "history": history,
            "inference_time": inference_time,
            "tokens_per_sec": tokens_per_sec,
            "ttft": ttft,
            "model_choice": model_choice,
            "failed_sources": [],
        }
    }

    log_message(f"✅ RAG Bypass answer returned ({len(ai_text)} chars, {format_number(inference_time, 2)}s)")


async def _handle_automatik_mode(
    user_text: str,
    stt_time: float,
    model_choice: str,
    automatik_model: str,
    history: List,
    llm_history: List[Dict[str, str]],
    session_id: Optional[str],
    temperature_mode: str,
    temperature: float,
    llm_options: Optional[Dict],
    backend_type: str,
    backend_url: Optional[str],
    state: Any,
    llm_client: Any,
    automatik_llm_client: Any,
    pending_images: Optional[List[Dict[str, str]]],
    vision_json_context: Optional[dict],
    user_name: Optional[str],
    detected_intent: Optional[str],
    detected_language: str,
    multimodal_user_content: Optional[list],
    cloud_provider_label: Optional[str],
    automatik_num_ctx: Optional[int],
) -> AsyncIterator[Dict]:
    """Handle the full automatik path: URL/keyword override, cache, RAG, research decision."""
    log_message("🤖 Automatik mode: AI checking if research needed...")

    # ============================================================
    # CODE-OVERRIDE: Explicit research request (Trigger words + URLs)
    # ============================================================
    # These keywords/URLs trigger IMMEDIATE new research without AI decision!

    # URL Detection (skip Decision-Making for URL requests)
    from .research.query_processor import detect_urls_in_text, detect_search_intent
    detected_urls = detect_urls_in_text(user_text, max_urls=7)
    has_search_intent = detect_search_intent(user_text)

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
                    "timestamp": datetime.datetime.now().isoformat(),
                    "has_audio": False,
                    "audio_urls_json": "[]"
                })
                # llm_history: sync via SSoT (strips thinking blocks internally)
                answer_clean = strip_thinking_blocks(answer) if answer else ""
                state._sync_to_llm_history("aifred", answer)

                # Return result - unified Dict format
                yield {
                    "type": "result",
                    "data": {
                        "response_clean": answer_clean,
                        "response_html": answer + timing_suffix,
                        "history": history,
                        "inference_time": cache_time_ms,
                        "tokens_per_sec": 0,
                        "ttft": None,
                        "model_choice": model_choice,
                        "failed_sources": cached_failed_sources,
                        "cache_hit": True,
                    }
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

        # OPTIMIZATION: Skip query generation for direct URLs without search intent
        # query_processor.py will handle these in Direct-Scraping mode
        if detected_urls and not has_search_intent:
            # Direct URL mode - no queries needed
            log_message("⚡ Direct URL detected (no search intent) → Skipping query generation")
            yield {"type": "debug", "message": "⚡ Direct-Scraping mode → Skip query generation"}
            pre_generated_queries: List[str] = []  # Empty list signals Direct-Scraping mode
        else:
            # CODE-OVERRIDE: Use generate_search_queries (same path as quick/deep mode)
            # Bypasses unreliable LLM decision - we already KNOW we want to research
            yield {"type": "debug", "message": "🔍 Generating search queries..."}

            # Check if images are present (for query generation context)
            has_images = (pending_images is not None and len(pending_images) > 0) or (vision_json_context is not None)

            query_result = await generate_search_queries(
                user_text=user_text,
                automatik_llm_client=automatik_llm_client,
                automatik_model=automatik_model,
                has_images=has_images,
                vision_json_context=vision_json_context,
                detected_language=detected_language,
                llm_history=llm_history[:-1] if len(llm_history) > 1 else None,
                automatik_num_ctx=automatik_num_ctx
            )
            pre_generated_queries = query_result.get("queries", [])
            query_gen_time = query_result.get("generation_time", 0)

            if pre_generated_queries:
                yield {"type": "debug", "message": f"✅ {len(pre_generated_queries)} queries generated ({format_number(query_gen_time, 1)}s)"}
                # Query list is shown in query_processor.py with API assignments
            else:
                # Should never happen unless LLM completely fails to parse
                error_msg = "Query generation failed (LLM parsing error?)"
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
            state=state,
            vision_json_context=vision_json_context,
            user_name=user_name,
            detected_intent=detected_intent,
            detected_language=detected_language,
            pre_generated_queries=pre_generated_queries,
            automatik_num_ctx=automatik_num_ctx
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
                "timestamp": datetime.datetime.now().isoformat(),
                "has_audio": False,
                "audio_urls_json": "[]"
            })
            # llm_history: sync via SSoT (strips thinking blocks internally)
            answer_clean = strip_thinking_blocks(answer) if answer else ""
            state._sync_to_llm_history("aifred", answer)

            # Return result - unified Dict format
            yield {
                "type": "result",
                "data": {
                    "response_clean": answer_clean,
                    "response_html": answer + timing_suffix,
                    "history": history,
                    "inference_time": cache_time,
                    "tokens_per_sec": 0,
                    "ttft": None,
                    "model_choice": model_choice,
                    "failed_sources": cached_failed_sources,
                    "cache_hit": True,
                }
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
    num_sources = 0
    num_checked = 0
    try:
        from .vector_cache import get_cache
        from .rag_context_builder import build_rag_context

        cache = get_cache()
        rag_result = await build_rag_context(
            user_query=user_text,
            cache=cache,
            automatik_llm_client=automatik_llm_client,
            automatik_model=automatik_model,
            max_candidates=5,
            automatik_num_ctx=automatik_num_ctx
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
        async for item in _handle_rag_bypass(
            user_text=user_text,
            model_choice=model_choice,
            history=history,
            llm_history=llm_history,
            rag_context=rag_context,
            num_sources=num_sources,
            num_checked=num_checked,
            detected_language=detected_language,
            temperature_mode=temperature_mode,
            temperature=temperature,
            detected_intent=detected_intent,
            llm_options=llm_options,
            backend_type=backend_type,
            backend_url=backend_url,
            state=state,
            llm_client=llm_client,
            multimodal_user_content=multimodal_user_content,
            vision_json_context=vision_json_context,
        ):
            yield item
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
            llm_history=llm_history[:-1] if len(llm_history) > 1 else None,
            automatik_num_ctx=automatik_num_ctx
        )

        decision_time = research_result["decision_time"]
        web_research_needed = research_result["web"]
        pre_generated_queries = research_result["queries"]
        research_volatility = research_result.get("volatility", "DAILY")

        # User-friendly display (include cache decision for web research)
        decision_label = "Web Research YES" if web_research_needed else "Web Research NO"
        if web_research_needed:
            cache_label = "NOCACHE" if research_volatility == "NOCACHE" else research_volatility
            yield {"type": "debug", "message": f"🤖 Decision: {decision_label} | Cache: {cache_label} ({format_number(decision_time, 1)}s)"}
        else:
            yield {"type": "debug", "message": f"🤖 Decision: {decision_label} ({format_number(decision_time, 1)}s)"}

        if web_research_needed and pre_generated_queries:
            yield {"type": "debug", "message": f"🔎 {len(pre_generated_queries)} queries pre-generated"}

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
                state=state,
                vision_json_context=vision_json_context,
                user_name=user_name,
                detected_intent=detected_intent,
                detected_language=detected_user_language,
                pre_generated_queries=pre_generated_queries,
                volatility=research_volatility,
                automatik_num_ctx=automatik_num_ctx
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
                history=history,
                llm_history=llm_history,
                detected_intent=detected_intent or "chat",
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

            # Forward result (own_knowledge_handler already updated history)
            if own_knowledge_result:
                yield {"type": "debug", "message": CONSOLE_SEPARATOR}
                yield {"type": "result", "data": own_knowledge_result}

    except Exception as e:
        log_message(f"⚠️ Error in Automatik mode decision: {e}")
        log_message("   Fallback to own knowledge")
        raise  # Re-raise to be handled by caller


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
    cloud_provider_label: Optional[str] = None,
    research_mode: str = "automatik",  # "automatik", "quick", "deep", "none"
    automatik_num_ctx: Optional[int] = None
) -> AsyncIterator[Dict]:
    """
    Unified chat handler for all research modes (Single Source of Truth).

    Dispatches to sub-functions based on research_mode:
    - "none"      -> _handle_own_knowledge_mode()
    - "quick"/"deep" -> _handle_forced_web_search()
    - "automatik" -> _handle_automatik_mode()

    Args:
        user_text: User question
        stt_time: STT time (0.0 for text input)
        model_choice: Main LLM for final response
        automatik_model: Automatik-LLM for decision/query generation
        history: Chat history (for UI display, dict format)
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
        cloud_provider_label: Cloud provider label for display (optional)
        research_mode: Research mode - "automatik", "quick", "deep", or "none"
        automatik_num_ctx: Context window for Automatik-LLM (optional)

    Yields:
        Dict with: {"type": "debug"|"content"|"metrics"|"separator"|"result", ...}
    """
    # Build multimodal content if images present
    if pending_images:
        user_content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        for img in pending_images:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img['base64']}"}
            })
        multimodal_user_content = user_content
        yield {"type": "debug", "message": f"📷 Message prepared with {len(pending_images)} image(s)"}
    else:
        multimodal_user_content = None  # Text-only mode

    # Initialize LLM clients with correct backend
    llm_client = LLMClient(backend_type=backend_type, base_url=backend_url)

    # Only Ollama supports model switching - other backends reuse same client
    if backend_type == 'ollama':
        automatik_llm_client = LLMClient(backend_type=backend_type, base_url=backend_url)
    else:
        automatik_llm_client = llm_client

    # VRAM Change Detection (only for vLLM backend)
    vram_warning = None
    if backend_type == "vllm":
        from .vllm_utils import check_vram_change_for_vllm
        from aifred.state import _global_backend_state
        vllm_manager = _global_backend_state.get("vllm_manager")
        vllm_gpu_indices = vllm_manager.gpu_indices if vllm_manager else None
        vram_info = check_vram_change_for_vllm(model_choice, gpu_indices=vllm_gpu_indices)
        if vram_info:
            vram_diff, current_vram, cached_vram, potential_tokens, current_tokens = vram_info
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
        # ============================================================
        # RESEARCH MODE ROUTING (Single Source of Truth)
        # ============================================================
        if research_mode == "none":
            async for item in _handle_own_knowledge_mode(
                user_text=user_text,
                model_choice=model_choice,
                history=history,
                llm_history=llm_history,
                detected_intent=detected_intent,
                detected_language=detected_language,
                temperature_mode=temperature_mode,
                temperature=temperature,
                backend_type=backend_type,
                backend_url=backend_url,
                llm_options=llm_options,
                state=state,
                multimodal_user_content=multimodal_user_content,
                cloud_provider_label=cloud_provider_label,
            ):
                yield item
            return

        elif research_mode in ["quick", "deep"]:
            async for item in _handle_forced_web_search(
                user_text=user_text,
                stt_time=stt_time,
                research_mode=research_mode,
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
                state=state,
                automatik_llm_client=automatik_llm_client,
                pending_images=pending_images,
                vision_json_context=vision_json_context,
                user_name=user_name,
                detected_intent=detected_intent,
                detected_language=detected_language,
                automatik_num_ctx=automatik_num_ctx,
            ):
                yield item
            return

        # ========== AUTOMATIK MODE (full path) ==========
        async for item in _handle_automatik_mode(
            user_text=user_text,
            stt_time=stt_time,
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
            state=state,
            llm_client=llm_client,
            automatik_llm_client=automatik_llm_client,
            pending_images=pending_images,
            vision_json_context=vision_json_context,
            user_name=user_name,
            detected_intent=detected_intent,
            detected_language=detected_language,
            multimodal_user_content=multimodal_user_content,
            cloud_provider_label=cloud_provider_label,
            automatik_num_ctx=automatik_num_ctx,
        ):
            yield item

    except Exception as e:
        log_message(f"⚠️ Error in chat_interactive_mode: {e}")
        raise  # Re-raise to be handled by caller
    finally:
        # Cleanup: Close LLM clients to free resources
        await llm_client.close()
        # Only close automatik_llm_client if it's a separate instance (Ollama)
        if backend_type == 'ollama':
            await automatik_llm_client.close()
