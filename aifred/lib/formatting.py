"""
Formatting Utilities - UI text formatting functions

This module provides formatting functions for displaying AI responses
and thinking processes in the Reflex UI.
"""

import re
from .logging_utils import log_message
from .config import XML_TAG_CONFIG  # Import from central config
from .html_tags import HTML_TAG_BLACKLIST  # HTML tags to exclude from XML processing
from datetime import datetime


def format_number(n: int | float, decimals: int = 0) -> str:
    """
    Format number with German locale (dot for thousands, comma for decimals).

    Args:
        n: Number to format (int or float)
        decimals: Number of decimal places (default: 0 for integer formatting)

    Returns:
        Formatted string with German number formatting

    Examples:
        >>> format_number(40960)
        '40.960'
        >>> format_number(10.84, 2)
        '10,84'
        >>> format_number(1234567)
        '1.234.567'
        >>> format_number(46.7, 1)
        '46,7'
    """
    if decimals == 0:
        # Integer formatting with thousands separator
        return f"{int(n):,}".replace(",", ".")
    else:
        # Float formatting: swap separators
        # Python uses comma for thousands, dot for decimals
        # We want: dot for thousands, comma for decimals (German)
        formatted = f"{n:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return formatted


def format_metadata(metadata_text: str) -> str:
    """
    Formatiert Metadaten (Inferenzzeiten, Quellen, etc.) mit kleinerem Font und grauer Farbe.

    Args:
        metadata_text: Text in Klammern, z.B. "(Inferenz: 1.3s, Quelle: Web-Recherche)"

    Returns:
        Markdown-formatierter Text (kursiv, kleinere Optik durch Styling in UI)

    Example:
        >>> format_metadata("(Inferenz: 1.3s, Quelle: LLM)")
        '*( Inferenz: 1.3s, Quelle: LLM )*'

    Note:
        Verwendet Markdown statt HTML, da rx.markdown() inline HTML escapet.
        Die Kursiv-Formatierung (*...*) signalisiert Meta-Information.
    """
    if not metadata_text:
        return metadata_text

    # Entferne äußere Klammern für Formatierung
    text = metadata_text.strip()
    if text.startswith("(") and text.endswith(")"):
        inner = text[1:-1]
        # Markdown kursiv - erscheint automatisch auf neuer Zeile durch \n davor
        return f'*( {inner} )*'

    # Falls keine Klammern: formatiere komplett als kursiv
    return f'*{text}*'


def get_timestamp() -> str:
    """
    Gibt aktuellen Timestamp im Format HH:MM:SS zurück (wie Legacy-Version).

    Returns:
        Formatted timestamp string (z.B. "18:32:33")
    """
    return datetime.now().strftime("%H:%M:%S")


def extract_xml_tags(text: str) -> list[tuple[str, str]]:
    """
    Extrahiert ALLE XML-Tags aus Text (generisch, nicht hardcoded).

    WICHTIG: HTML-Tags werden IGNORIERT, damit sie nicht versehentlich
    als Collapsibles formatiert werden (z.B. <span>, <div>, <details>).
    Die Blacklist ist in html_tags.py definiert.

    Args:
        text: Text mit optionalen XML-Tags

    Returns:
        Liste von (tag_name, content) Tuples (ohne HTML-Tags!)

    Example:
        >>> extract_xml_tags("<think>foo</think> bar <python>code</python>")
        [("think", "foo"), ("python", "code")]

        >>> extract_xml_tags("<span style='...'>text</span>")  # HTML ignoriert!
        []
    """
    # Generic XML pattern: <tagname>content</tagname>
    pattern = r'<(\w+)>(.*?)</\1>'
    matches = re.findall(pattern, text, re.DOTALL)

    # Filter: Nur Non-HTML Tags zurückgeben (Blacklist aus html_tags.py)
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


def format_thinking_process(ai_response, model_name=None, inference_time=None, tokens_per_sec=None):
    """
    Formatiert XML-Tags als Collapsible Accordions (GENERISCH).

    Unterstützt ALLE in XML_TAG_CONFIG definierten Tags dynamisch.
    Keine Hardcodierung mehr - neue Tags können via Config hinzugefügt werden!

    Args:
        ai_response: Die AI-Antwort mit optionalen XML-Tags
        model_name: Name des verwendeten Modells (z.B. "qwen3:1.7b")
        inference_time: Inferenz-Zeit in Sekunden
        tokens_per_sec: Tokens pro Sekunde (optional)

    Returns:
        Formatted string mit Collapsibles für alle erkannten XML-Tags

    Supported Tags (via XML_TAG_CONFIG):
        <think>: Denkprozess (DeepSeek Reasoning)
        <data>: Strukturierte Daten (Vision-LLM JSON)
        <python>: Python Code
        <code>: Generic Code
        <sql>: SQL Query
        <json>: JSON Daten

    Example:
        Input: "<think>reasoning</think> Answer <python>code</python>"
        Output: 2 Collapsibles (Denkprozess + Python Code) + "Answer"
    """

    # DEBUG: Logge KOMPLETTE RAW Response
    log_message("=" * 80)
    log_message("🔍 RAW AI RESPONSE (KOMPLETT):")
    log_message(ai_response)
    log_message("=" * 80)

    # Extract ALL XML tags generically
    xml_tags = extract_xml_tags(ai_response)

    if not xml_tags:
        # No tags found, return original
        return ai_response

    # Build collapsibles for each detected tag
    collapsibles = []
    for tag_name, content in xml_tags:
        config = XML_TAG_CONFIG.get(tag_name)

        if config:
            # Known tag → Use config (schönes Icon + Label)
            icon = config['icon']
            label = config['label']
            css_class = config['class']
        else:
            # Unknown tag → Auto-generate (Fallback für ALLE Tags!)
            icon = "📄"
            label = tag_name.capitalize()
            css_class = "thinking-compact"
            log_message(f"ℹ️ Auto-formatiere unbekanntes XML-Tag: <{tag_name}> → {icon} {label}")

        # Build summary with icon + label
        summary_parts = [f"{icon} {label}"]
        if model_name:
            summary_parts.append(f"({model_name})")
        if inference_time and tag_name == "think":  # Nur für <think> Zeit zeigen
            summary_parts.append(f"• {inference_time:.1f}s")
        summary_text = " ".join(summary_parts)

        # Build collapsible HTML
        collapsible = f"""<details style="font-size: 0.9em; margin-bottom: 1em; margin-top: 0.2em;">
<summary style="cursor: pointer; font-weight: bold; color: #aaa;">{summary_text}</summary>
<div class="{css_class}">

{content}

</div>
</details>"""
        collapsibles.append(collapsible)

    # Remove nur die extrahierten Top-Level-Tags (nicht nested tags!)
    clean_response = ai_response
    for tag_name, _ in xml_tags:
        # Entferne nur das erste Vorkommen des extrahierten Tags
        pattern = rf'<{tag_name}>.*?</{tag_name}>'
        clean_response = re.sub(pattern, '', clean_response, count=1, flags=re.DOTALL)
    clean_response = clean_response.strip()

    # Return: Collapsibles + Clean Response
    if collapsibles:
        return "\n\n".join(collapsibles) + "\n\n" + clean_response
    else:
        return clean_response


def build_debug_accordion(query_reasoning, ai_text, automatik_model, main_model, query_time=None, final_time=None):
    """
    Baut Debug-Accordion für Agent-Recherche mit allen KI-Denkprozessen.

    Nutzt jetzt extract_xml_tags() für generische XML-Verarbeitung!

    Args:
        query_reasoning: <think> Content from Query Optimization
        ai_text: Final AI response with optional XML tags
        automatik_model: Name des Automatik-Modells (für Query-Opt)
        main_model: Name des Haupt-Modells (für finale Antwort)
        query_time: Inferenz-Zeit für Query Optimization (optional)
        final_time: Inferenz-Zeit für finale Antwort (optional)

    Returns:
        Formatted AI response with debug accordion prepended
    """

    # DEBUG: Logge KOMPLETTE RAW Response
    log_message("=" * 80)
    log_message("🔍 RAW AI RESPONSE (KOMPLETT):")
    log_message(ai_text)
    log_message("=" * 80)

    debug_sections = []

    # 1. Query Optimization Reasoning (falls vorhanden)
    if query_reasoning:
        time_suffix = f" • {query_time:.1f}s" if query_time else ""
        debug_sections.append(f"""<details style="font-size: 0.9em; margin-bottom: 0.5em;">
<summary style="cursor: pointer; font-weight: bold; color: #aaa;">🔍 Query-Optimierung ({automatik_model}){time_suffix}</summary>
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
            debug_sections.append(f"""<details style="font-size: 0.9em; margin-bottom: 0.5em;">
<summary style="cursor: pointer; font-weight: bold; color: #aaa;">💭 Finale Antwort Denkprozess ({main_model}){time_suffix}</summary>
<div class="thinking-compact">

{content}

</div>
</details>""")

    # Kombiniere alle Debug-Sections
    debug_accordion = "\n".join(debug_sections)

    # Entferne nur die extrahierten Top-Level-Tags (nicht nested tags!)
    clean_response = ai_text
    for tag_name, _ in xml_tags:
        pattern = rf'<{tag_name}>.*?</{tag_name}>'
        clean_response = re.sub(pattern, '', clean_response, count=1, flags=re.DOTALL)
    clean_response = clean_response.strip()

    # Return: Debug Accordion + Clean Response
    if debug_accordion:
        return f"{debug_accordion}\n\n{clean_response}"
    else:
        return clean_response
