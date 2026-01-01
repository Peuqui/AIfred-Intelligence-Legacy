"""
Formatting Utilities - UI text formatting functions

This module provides formatting functions for displaying AI responses
and thinking processes in the Reflex UI.
"""

import re
import uuid
import atexit
import threading
from pathlib import Path
from collections import OrderedDict
from .logging_utils import log_message
from .config import get_xml_tag_config  # Import function instead of static config
from .html_tags import HTML_TAG_BLACKLIST  # HTML tags to exclude from XML processing
from datetime import datetime

# HTML Preview: Path to uploaded_files/html_preview directory
# IMPORTANT: Must be outside assets/ to avoid triggering Reflex hot-reload!
# Reflex serves uploaded_files/ via /_upload/ endpoint (backend only)
from .config import PROJECT_ROOT, BACKEND_API_URL
_HTML_PREVIEW_DIR = PROJECT_ROOT / "uploaded_files" / "html_preview"

# LRU Cache for HTML preview files (max 50 files)
_html_file_cache: OrderedDict[str, Path] = OrderedDict()
_html_cache_lock = threading.Lock()
MAX_HTML_FILES = 50

# Global UI locale for number formatting (set by AIState on language change)
_ui_locale: str = "de"


def set_ui_locale(locale: str):
    """Set the global UI locale for number formatting (called by AIState)"""
    global _ui_locale
    if locale in ["de", "en"]:
        _ui_locale = locale


def get_ui_locale() -> str:
    """Get the current UI locale"""
    return _ui_locale


def format_number(n: int | float, decimals: int = 0, locale: str = None) -> str:
    """
    Format number with locale-aware separators.

    Args:
        n: Number to format (int or float)
        decimals: Number of decimal places (default: 0 for integer formatting)
        locale: Locale for formatting - "de" (German) or "en" (English)
                If None, uses the global UI locale set by set_ui_locale()
                German: dot for thousands, comma for decimals (1.234,56)
                English: comma for thousands, dot for decimals (1,234.56)

    Returns:
        Formatted string with locale-aware number formatting

    Examples:
        >>> format_number(40960)
        '40.960'
        >>> format_number(40960, locale="en")
        '40,960'
        >>> format_number(10.84, 2)
        '10,84'
        >>> format_number(10.84, 2, locale="en")
        '10.84'
    """
    # Use global UI locale if not specified
    if locale is None:
        locale = _ui_locale

    if locale == "en":
        # English: comma for thousands, dot for decimals (Python default)
        if decimals == 0:
            return f"{int(n):,}"
        else:
            return f"{n:,.{decimals}f}"
    else:
        # German (default): dot for thousands, comma for decimals
        if decimals == 0:
            return f"{int(n):,}".replace(",", ".")
        else:
            formatted = f"{n:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return formatted


def format_age(seconds: float) -> str:
    """
    Format age in seconds to human-readable format.

    Examples:
        >>> format_age(30)
        '30s'
        >>> format_age(90)
        '1min 30s'
        >>> format_age(3600)
        '1h'
        >>> format_age(7200)
        '2h'
        >>> format_age(86400)
        '1d'
        >>> format_age(90061)
        '1d 1h 1min'
    """
    if seconds < 60:
        return f"{seconds:.0f}s"

    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}min")
    if secs > 0 and days == 0:  # Only show seconds if less than a day
        parts.append(f"{secs}s")

    return " ".join(parts)


def convert_latex_delimiters(text: str) -> str:
    """
    Convert various LaTeX delimiter formats to $...$ syntax for rx.markdown.

    Handles common LLM output formats:
    - \\text{...} → plain text (rx.markdown doesn't support \\text well)
    - \\[...\\] → $$...$$ (block math)
    - \\(...\\) → $...$ (inline math)

    Args:
        text: Text with LaTeX formulas in various formats

    Returns:
        Text with LaTeX converted to $...$ syntax

    Example:
        >>> convert_latex_delimiters("\\text{ATP} + \\text{H}_2\\text{O}")
        'ATP + H_2O'
    """
    if not text:
        return text

    original_text = text

    # 1. Add space before \text{} if missing (after non-space, non-backslash char)
    # Fixes LLM output like "wobei\text{F}" → "wobei \text{F}" → "wobei F"
    text = re.sub(r'([^\s\\])\\text\{', r'\1 \\text{', text)

    # 2. Convert \text{...} to plain text (rx.markdown's KaTeX doesn't render it)
    text = re.sub(r'\\text\{([^}]*)\}', r'\1', text)

    # 3. Convert \[...\] to $$...$$ (LaTeX display mode)
    text = re.sub(r'\\\[(.*?)\\\]', r'$$\1$$', text, flags=re.DOTALL)

    # 4. Convert \(...\) to $...$ (LaTeX inline mode)
    text = re.sub(r'\\\((.*?)\\\)', r'$\1$', text, flags=re.DOTALL)

    # Debug: Log if any conversion happened
    if text != original_text:
        log_message(f"📐 LaTeX: Converted delimiters ({len(original_text)} → {len(text)} chars)")

    return text


def format_metadata(metadata_text: str) -> str:
    """
    Format metadata (inference times, sources, etc.) as italic text in parentheses.

    Args:
        metadata_text: Metadata text, e.g., "Inference: 1.3s    Source: Web Research"
                       (4 spaces as separator between values)

    Returns:
        Markdown-formatted text (italic, in parentheses) with non-breaking spaces

    Example:
        >>> format_metadata("Inference: 1.3s    61.1 tok/s    Source: LLM")
        '*( Inference: 1.3s    61.1 tok/s    Source: LLM )*'  # with non-breaking spaces

    Note:
        Uses Markdown instead of HTML since rx.markdown() escapes inline HTML.
        Italic formatting (*...*) signals meta-information.
        4 normal spaces are converted to 4 non-breaking spaces.
    """
    if not metadata_text:
        return metadata_text

    text = metadata_text.strip()
    # Replace 4 normal spaces with 4 non-breaking spaces (won't collapse)
    text = text.replace("    ", "\u00A0\u00A0\u00A0\u00A0")
    return f'*( {text} )*'


def get_timestamp() -> str:
    """
    Returns current timestamp in HH:MM:SS format (like legacy version).

    Returns:
        Formatted timestamp string (e.g., "18:32:33")
    """
    return datetime.now().strftime("%H:%M:%S")


def _save_html_to_assets(html_code: str) -> str:
    """
    Save HTML code as file in uploaded_files/html_preview/ and return URL.

    IMPORTANT: Files are saved outside assets/ to avoid Reflex hot-reload!
    Implements LRU Cache: Maximum 50 files are kept, oldest are deleted.

    Args:
        html_code: The HTML code to save

    Returns:
        Full URL to saved file (e.g., "http://host:8002/_upload/html_preview/abc123.html")
    """
    # Ensure directory exists
    _HTML_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    filename = f"{uuid.uuid4().hex[:8]}.html"
    filepath = _HTML_PREVIEW_DIR / filename

    # Save HTML code
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_code)

    # LRU Cache Management (thread-safe)
    with _html_cache_lock:
        _html_file_cache[filename] = filepath

        # If cache is full, delete oldest file
        if len(_html_file_cache) > MAX_HTML_FILES:
            oldest_filename, oldest_path = _html_file_cache.popitem(last=False)
            try:
                oldest_path.unlink()
                log_message(f"🗑️ HTML Preview: LRU evicted {oldest_filename} (Cache limit: {MAX_HTML_FILES})")
            except OSError as e:
                log_message(f"⚠️ HTML Preview: Could not delete {oldest_filename}: {e}")

    log_message(f"🌐 HTML Preview: File saved → {filepath} (Cache: {len(_html_file_cache)}/{MAX_HTML_FILES})")

    # Return full URL with auto-detected backend host
    return f"{BACKEND_API_URL}/_upload/html_preview/{filename}"


@atexit.register
def _cleanup_html_cache():
    """Cleanup on program exit: Delete all HTML preview files from cache"""
    with _html_cache_lock:
        for filepath in _html_file_cache.values():
            try:
                filepath.unlink()
            except OSError:
                pass
        _html_file_cache.clear()


# KaTeX inline embedding cache (loaded once, reused for all exports)
_katex_inline_cache: dict[str, str] = {}


def get_katex_inline_assets() -> dict[str, str]:
    """
    Load KaTeX assets and convert them to inline format for portable HTML export.

    Returns dict with:
        - 'css': KaTeX CSS with fonts embedded as Base64 data URLs
        - 'js': KaTeX main JS
        - 'mhchem_js': mhchem extension JS
        - 'autorender_js': auto-render extension JS

    Results are cached after first call.
    """
    import base64

    if _katex_inline_cache:
        return _katex_inline_cache

    katex_dir = PROJECT_ROOT / "assets" / "katex"
    fonts_dir = katex_dir / "fonts"

    # Load CSS and embed fonts as Base64
    css_path = katex_dir / "katex.min.css"
    if css_path.exists():
        css_content = css_path.read_text(encoding='utf-8')

        # Replace font URLs with Base64 data URLs (only woff2 for smaller size)
        for font_file in fonts_dir.glob("*.woff2"):
            font_name = font_file.name
            font_data = base64.b64encode(font_file.read_bytes()).decode('ascii')
            data_url = f"data:font/woff2;base64,{font_data}"
            # Replace all URL patterns for this font
            css_content = css_content.replace(f"url(/katex/fonts/{font_name})", f"url({data_url})")

        # Remove woff and ttf references (browser will use woff2)
        css_content = re.sub(r',url\([^)]+\.woff\)[^,}]*', '', css_content)
        css_content = re.sub(r',url\([^)]+\.ttf\)[^,}]*', '', css_content)

        _katex_inline_cache['css'] = css_content
    else:
        _katex_inline_cache['css'] = ""

    # Load JS files
    js_path = katex_dir / "katex.min.js"
    _katex_inline_cache['js'] = js_path.read_text(encoding='utf-8') if js_path.exists() else ""

    mhchem_path = katex_dir / "mhchem.min.js"
    _katex_inline_cache['mhchem_js'] = mhchem_path.read_text(encoding='utf-8') if mhchem_path.exists() else ""

    autorender_path = katex_dir / "auto-render.min.js"
    _katex_inline_cache['autorender_js'] = autorender_path.read_text(encoding='utf-8') if autorender_path.exists() else ""

    log_message(f"📐 KaTeX: Loaded assets for inline embedding (CSS: {len(_katex_inline_cache['css'])/1024:.1f}KB)")

    return _katex_inline_cache


def cleanup_old_html_previews(max_age_hours: int = 24) -> int:
    """
    Deletes old HTML preview files from assets/html_preview/.

    Args:
        max_age_hours: Maximum age in hours (default: 24)

    Returns:
        Number of deleted files
    """
    import time

    if not _HTML_PREVIEW_DIR.exists():
        return 0

    deleted = 0
    max_age_seconds = max_age_hours * 3600
    now = time.time()

    for filepath in _HTML_PREVIEW_DIR.glob("*.html"):
        try:
            age = now - filepath.stat().st_mtime
            if age > max_age_seconds:
                filepath.unlink()
                deleted += 1
        except OSError:
            pass  # Ignore errors during deletion

    if deleted > 0:
        log_message(f"🧹 HTML Preview: {deleted} old file(s) deleted")

    return deleted


def format_html_preview(text: str, lang: str = None) -> str:
    """
    Detect ```html code blocks, save them as files and generate preview buttons.

    HTML files are saved in assets/html_preview/ and can be opened
    via link in a new browser tab.

    Args:
        text: Text with optional ```html code blocks
        lang: Language for collapsible labels (de/en). If None, uses get_ui_locale()

    Returns:
        Text with HTML preview buttons and collapsible code

    Example:
        Input:  "Here is HTML:\n```html\n<h1>Hello</h1>\n```\nDone!"
        Output: "Here is HTML:\n[🌐 Open in Browser](/html_preview/abc123.html)\n<details>...</details>\nDone!"
    """
    # Import i18n for labels
    from .i18n import t

    # Use current UI locale if no lang specified
    if lang is None:
        lang = get_ui_locale()

    # Get translated label
    show_html_label = t("collapsible_show_html", lang=lang)

    # Pattern for ```html code blocks (with optional whitespace/newline)
    # Made robust: \s* allows any whitespace (including none) after "html"
    html_block_pattern = r'```html\s*([\s\S]*?)```'

    def replace_html_block(match):
        html_code = match.group(1).strip()

        # Save HTML code and get URL
        preview_url = _save_html_to_assets(html_code)

        # Button link with target="_blank" directly in HTML (not Markdown!)
        # + Collapsible with code for viewing/copying
        code_collapsible = f"""<div style="margin-bottom: 1em; margin-top: 0.5em;">

<a href="{preview_url}" target="_blank" rel="noopener noreferrer" style="font-weight: bold; color: #58a6ff; text-decoration: none;">🌐 Open in Browser</a> <em>(New Tab)</em>

<details style="font-size: 0.9em; border: 1px solid #30363d; border-radius: 6px;">
<summary style="cursor: pointer; font-weight: bold; color: #58a6ff; padding: 0.5em;">{show_html_label}</summary>
<div style="padding: 0.5em;">

```html
{html_code}
```

</div>
</details>
</div>"""

        return code_collapsible

    # Replace all ```html blocks
    result = re.sub(html_block_pattern, replace_html_block, text)

    # Log when HTML blocks were found
    if result != text:
        log_message("🌐 HTML Code: Preview button(s) generated")

    return result


def fix_orphan_closing_think_tag(text: str) -> str:
    """
    Repair orphaned closing </think> tags (without opening tag).

    Some models (e.g., Qwen3 with enable_thinking=false) output the thinking process
    without opening <think> tag, but with closing </think> tag.

    LOGIC:
    - If <think> AND </think> present → Do nothing (correct tags)
    - If ONLY </think> present (without <think>) → Insert <think> at beginning

    Args:
        text: Text with potentially missing opening tag

    Returns:
        Text with repaired tag (if needed)

    Example:
        Input:  "Okay, let me think...\\n</think>\\nAnswer here"
        Output: "<think>Okay, let me think...\\n</think>\\nAnswer here"

        Input:  "<think>normal</think> text"  # Remains unchanged
        Output: "<think>normal</think> text"
    """
    has_opening = '<think>' in text
    has_closing = '</think>' in text

    # Only repair if closing tag exists but no opening tag
    if has_closing and not has_opening:
        text = '<think>' + text
        log_message("🔧 Missing <think> tag repaired (opening tag added)")

    return text


def extract_xml_tags(text: str) -> list[tuple[str, str]]:
    """
    Extract ALL XML tags from text (generic, not hardcoded).

    IMPORTANT:
    1. HTML tags are IGNORED (blacklist in html_tags.py)
    2. Tags inside Markdown code blocks are IGNORED!
       (``` ... ``` blocks often contain HTML/XML code examples)
    3. Orphaned closing </think> tags are automatically repaired!

    Args:
        text: Text with optional XML tags

    Returns:
        List of (tag_name, content) tuples (without HTML tags, without code-block tags!)

    Example:
        >>> extract_xml_tags("<think>foo</think> bar <python>code</python>")
        [("think", "foo"), ("python", "code")]

        >>> extract_xml_tags("<span style='...'>text</span>")  # HTML ignored!
        []

        >>> extract_xml_tags("```html\\n<head>...</head>\\n```")  # Code block ignored!
        []

        >>> extract_xml_tags("Thinking...\\n</think>\\nAnswer")  # Orphaned tag repaired!
        [("think", "Thinking...")]

    Note:
        Repair of orphaned </think> tags happens in calling functions
        (format_thinking_process, build_debug_accordion), BEFORE extract_xml_tags is called.
        This is necessary for clean_response to work correctly.
    """
    # STEP 1: Remove Markdown code blocks BEFORE searching for XML tags
    # Code blocks can contain HTML/XML code examples that should NOT be processed
    text_without_codeblocks = re.sub(r'```[\s\S]*?```', '', text)

    # STEP 2: Generic XML pattern: <tagname>content</tagname>
    pattern = r'<(\w+)>(.*?)</\1>'
    matches = re.findall(pattern, text_without_codeblocks, re.DOTALL)

    # STEP 3: Filter: Only return non-HTML tags (blacklist from html_tags.py)
    return [
        (tag_name, content.strip())
        for tag_name, content in matches
        if tag_name.lower() not in HTML_TAG_BLACKLIST
    ]


def format_debug_message(message: str) -> str:
    """
    Formatiert Debug-Message mit Timestamp (wie Legacy-Version).

    Args:
        message: Debug message text

    Returns:
        Formatted message mit Timestamp (z.B. "18:32:33 | 📨 User Request empfangen")
    """
    timestamp = get_timestamp()
    return f"{timestamp} | {message}"


def format_thinking_process(ai_response, model_name=None, inference_time=None, tokens_per_sec=None, lang=None):
    """
    Format XML tags as collapsible accordions (GENERIC).

    Supports ALL tags defined in get_xml_tag_config() dynamically.
    No more hardcoding - new tags can be added via config!

    Args:
        ai_response: The AI response with optional XML tags
        model_name: Name of the model used (e.g., "qwen3:1.7b")
        inference_time: Inference time in seconds
        tokens_per_sec: Tokens per second (optional)
        lang: Language for collapsible labels (de/en). If None, uses get_ui_locale()

    Returns:
        Formatted string with collapsibles for all detected XML tags

    Supported Tags (via get_xml_tag_config):
        <think>: Thinking process (DeepSeek Reasoning)
        <data>: Structured data (Vision-LLM JSON)
        <python>: Python Code
        <code>: Generic Code
        <sql>: SQL Query
        <json>: JSON Data

    Example:
        Input: "<think>reasoning</think> Answer <python>code</python>"
        Output: 2 collapsibles (Thinking Process + Python Code) + "Answer"
    """
    # Use current UI locale if no lang specified
    if lang is None:
        lang = get_ui_locale()

    # Get XML tag config with i18n labels
    xml_tag_config = get_xml_tag_config(lang)

    # DEBUG: Log COMPLETE RAW Response
    log_message("=" * 80)
    log_message("🔍 RAW AI RESPONSE (COMPLETE):")
    log_message(ai_response)
    log_message("=" * 80)

    # STEP 0: Repair orphaned </think> tags BEFORE extraction
    # (Important: Must be applied to ai_response so clean_response works later)
    ai_response = fix_orphan_closing_think_tag(ai_response)

    # Extract ALL XML tags generically
    xml_tags = extract_xml_tags(ai_response)

    # Build collapsibles for each detected tag (if any)
    collapsibles = []
    for tag_name, content in xml_tags:
        config = xml_tag_config.get(tag_name)

        if config:
            # Known tag → Use config (nice icon + label)
            icon = config['icon']
            label = config['label']
            css_class = config['class']
        else:
            # Unknown tag → SKIP (don't format as collapsible!)
            # Smaller models often output tags like <result>, <function>,
            # which are not intended to be collapsibles
            log_message(f"ℹ️ Skipping unknown XML tag: <{tag_name}> (not in xml_tag_config)")
            continue

        # Build summary with icon + label
        summary_parts = [f"{icon} {label}"]
        if model_name:
            summary_parts.append(f"({model_name})")
        # NOTE: Inference time is already shown in final metrics (in parentheses)
        # so we don't add it to the collapsible header anymore
        summary_text = " ".join(summary_parts)

        # Build collapsible HTML
        collapsible = f"""<details style="font-size: 0.9em; margin-bottom: 1em; margin-top: 0.2em;">
<summary style="cursor: pointer; font-weight: bold; color: #aaa;">{summary_text}</summary>
<div class="{css_class}">

{content}

</div>
</details>"""
        collapsibles.append(collapsible)

    # Remove only KNOWN tags (that became collapsibles) from response
    # Unknown tags stay in the text!
    clean_response = ai_response
    for tag_name, _ in xml_tags:
        # Only remove if tag is in config (i.e., a collapsible was created)
        if tag_name in xml_tag_config:
            pattern = rf'<{tag_name}>.*?</{tag_name}>'
            clean_response = re.sub(pattern, '', clean_response, count=1, flags=re.DOTALL)
    clean_response = clean_response.strip()

    # Return: Collapsibles + Clean Response
    if collapsibles:
        result = "\n\n".join(collapsibles) + "\n\n" + clean_response
    else:
        result = clean_response

    # STEP: Convert LaTeX delimiters for rx.markdown compatibility
    result = convert_latex_delimiters(result)

    # FINAL STEP: HTML Preview für ```html Code-Blöcke
    result = format_html_preview(result)

    return result


def build_debug_accordion(query_reasoning, ai_text, automatik_model, main_model, query_time=None, final_time=None, lang=None):
    """
    Build debug accordion for agent research with all AI thinking processes.

    Now uses extract_xml_tags() for generic XML processing!

    Args:
        query_reasoning: <think> Content from Query Optimization
        ai_text: Final AI response with optional XML tags
        automatik_model: Name of Automatik model (for Query-Opt)
        main_model: Name of Main model (for final answer)
        query_time: Inference time for Query Optimization (optional)
        final_time: Inference time for final answer (optional)
        lang: Language for collapsible labels (de/en). If None, uses get_ui_locale()

    Returns:
        Formatted AI response with debug accordion prepended
    """
    # Import i18n for labels
    from .i18n import t

    # Use current UI locale if no lang specified
    if lang is None:
        lang = get_ui_locale()

    # DEBUG: Log COMPLETE RAW Response
    log_message("=" * 80)
    log_message("🔍 RAW AI RESPONSE (COMPLETE):")
    log_message(ai_text)
    log_message("=" * 80)

    # STEP 0: Repair orphaned </think> tags BEFORE extraction
    ai_text = fix_orphan_closing_think_tag(ai_text)

    debug_sections = []

    # 1. Query Optimization Reasoning (if present)
    if query_reasoning:
        time_suffix = f" • {query_time:.1f}s" if query_time else ""
        query_opt_label = t("collapsible_query_optimization", lang=lang)
        debug_sections.append(f"""<details style="font-size: 0.9em; margin-bottom: 0.5em;">
<summary style="cursor: pointer; font-weight: bold; color: #aaa;">{query_opt_label} ({automatik_model}){time_suffix}</summary>
<div class="thinking-compact">

{query_reasoning}

</div>
</details>""")

    # 2. Final Answer XML tags (generic extraction)
    xml_tags = extract_xml_tags(ai_text)

    for tag_name, content in xml_tags:
        if tag_name == "think":
            # <think> tag → Add as debug collapsible
            time_suffix = f" • {final_time:.1f}s" if final_time else ""
            thinking_label = t("collapsible_thinking_process", lang=lang)
            debug_sections.append(f"""<details style="font-size: 0.9em; margin-bottom: 0.5em;">
<summary style="cursor: pointer; font-weight: bold; color: #aaa;">{thinking_label} ({main_model}){time_suffix}</summary>
<div class="thinking-compact">

{content}

</div>
</details>""")

    # Combine all debug sections
    debug_accordion = "\n".join(debug_sections)

    # Remove only KNOWN tags (think) from response
    # In build_debug_accordion only <think> is processed
    clean_response = ai_text
    for tag_name, _ in xml_tags:
        # Only remove <think> tag (the only one used as debug section here)
        if tag_name == "think":
            pattern = rf'<{tag_name}>.*?</{tag_name}>'
            clean_response = re.sub(pattern, '', clean_response, count=1, flags=re.DOTALL)
    clean_response = clean_response.strip()

    # Return: Debug Accordion + Clean Response
    if debug_accordion:
        result = f"{debug_accordion}\n\n{clean_response}"
    else:
        result = clean_response

    # STEP: Convert LaTeX delimiters for rx.markdown compatibility
    result = convert_latex_delimiters(result)

    # FINAL STEP: HTML Preview für ```html Code-Blöcke
    result = format_html_preview(result)

    return result
