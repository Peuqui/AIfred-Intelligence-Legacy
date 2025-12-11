"""
Formatting Utilities - UI text formatting functions

This module provides formatting functions for displaying AI responses
and thinking processes in the Reflex UI.
"""

import re
import uuid
from pathlib import Path
from .logging_utils import log_message
from .config import XML_TAG_CONFIG  # Import from central config
from .html_tags import HTML_TAG_BLACKLIST  # HTML tags to exclude from XML processing
from datetime import datetime

# HTML Preview: Pfad zum assets/html_preview Verzeichnis
# Reflex serviert assets/ unter / - also /html_preview/dateiname.html
_ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"
_HTML_PREVIEW_DIR = _ASSETS_DIR / "html_preview"


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


def format_metadata(metadata_text: str) -> str:
    """
    Formatiert Metadaten (Inferenzzeiten, Quellen, etc.) als kursiven Text in Klammern.

    Args:
        metadata_text: Metadaten-Text, z.B. "Inferenz: 1.3s    Quelle: Web-Recherche"
                       (4 Leerzeichen als Trenner zwischen Werten)

    Returns:
        Markdown-formatierter Text (kursiv, in Klammern) mit geschützten Leerzeichen

    Example:
        >>> format_metadata("Inferenz: 1.3s    61,1 tok/s    Quelle: LLM")
        '*( Inferenz: 1.3s    61,1 tok/s    Quelle: LLM )*'  # mit non-breaking spaces

    Note:
        Verwendet Markdown statt HTML, da rx.markdown() inline HTML escapet.
        Die Kursiv-Formatierung (*...*) signalisiert Meta-Information.
        4 normale Leerzeichen werden zu 4 Non-Breaking Spaces konvertiert.
    """
    if not metadata_text:
        return metadata_text

    text = metadata_text.strip()
    # Ersetze 4 normale Leerzeichen durch 4 Non-Breaking Spaces (werden nicht zusammengekürzt)
    text = text.replace("    ", "\u00A0\u00A0\u00A0\u00A0")
    return f'*( {text} )*'


def get_timestamp() -> str:
    """
    Gibt aktuellen Timestamp im Format HH:MM:SS zurück (wie Legacy-Version).

    Returns:
        Formatted timestamp string (z.B. "18:32:33")
    """
    return datetime.now().strftime("%H:%M:%S")


def _save_html_to_assets(html_code: str) -> str:
    """
    Speichert HTML-Code als Datei in assets/html_preview/ und gibt URL zurück.

    Args:
        html_code: Der HTML-Code zum Speichern

    Returns:
        URL-Pfad zur gespeicherten Datei (z.B. "/html_preview/abc123.html")
    """
    # Stelle sicher dass das Verzeichnis existiert
    _HTML_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    # Generiere eindeutigen Dateinamen
    filename = f"{uuid.uuid4().hex[:8]}.html"
    filepath = _HTML_PREVIEW_DIR / filename

    # Speichere HTML-Code
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_code)

    log_message(f"🌐 HTML Preview: Datei gespeichert → {filepath}")

    # Reflex serviert assets/ unter / - also /html_preview/dateiname.html
    return f"/html_preview/{filename}"


def cleanup_old_html_previews(max_age_hours: int = 24) -> int:
    """
    Löscht alte HTML-Preview-Dateien aus assets/html_preview/.

    Args:
        max_age_hours: Maximales Alter in Stunden (default: 24)

    Returns:
        Anzahl gelöschter Dateien
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
            pass  # Ignoriere Fehler beim Löschen

    if deleted > 0:
        log_message(f"🧹 HTML Preview: {deleted} alte Datei(en) gelöscht")

    return deleted


def format_html_preview(text: str) -> str:
    """
    Erkennt ```html Code-Blöcke, speichert sie als Dateien und generiert Preview-Buttons.

    Die HTML-Dateien werden in assets/html_preview/ gespeichert und können
    über einen Link im neuen Browser-Tab geöffnet werden.

    Args:
        text: Text mit optionalen ```html Code-Blöcken

    Returns:
        Text mit HTML-Preview-Buttons und Collapsible Code

    Example:
        Input:  "Hier ist HTML:\n```html\n<h1>Hello</h1>\n```\nFertig!"
        Output: "Hier ist HTML:\n[🌐 Im Browser öffnen](/html_preview/abc123.html)\n<details>...</details>\nFertig!"
    """
    # Pattern für ```html Code-Blöcke (mit optionalem Whitespace)
    html_block_pattern = r'```html\s*\n([\s\S]*?)```'

    def replace_html_block(match):
        html_code = match.group(1).strip()

        # Speichere HTML-Code und erhalte URL
        preview_url = _save_html_to_assets(html_code)

        # Button-Link mit target="_blank" direkt im HTML (nicht Markdown!)
        # + Collapsible mit dem Code zum Ansehen/Kopieren
        code_collapsible = f"""<div style="margin-bottom: 1em; margin-top: 0.5em;">

<a href="{preview_url}" target="_blank" rel="noopener noreferrer" style="font-weight: bold; color: #58a6ff; text-decoration: none;">🌐 Im Browser öffnen</a> <em>(Neuer Tab)</em>

<details style="font-size: 0.9em; border: 1px solid #30363d; border-radius: 6px;">
<summary style="cursor: pointer; font-weight: bold; color: #58a6ff; padding: 0.5em;">📄 HTML Code anzeigen</summary>
<div style="padding: 0.5em;">

```html
{html_code}
```

</div>
</details>
</div>"""

        return code_collapsible

    # Ersetze alle ```html Blöcke
    result = re.sub(html_block_pattern, replace_html_block, text)

    # Log wenn HTML-Blöcke gefunden wurden
    if result != text:
        log_message("🌐 HTML Code: Preview-Button(s) generiert")

    return result


def fix_orphan_closing_think_tag(text: str) -> str:
    """
    Repariert verwaiste schließende </think> Tags (ohne öffnenden Tag).

    Manche Modelle (z.B. Qwen3 mit enable_thinking=false) geben den Denkprozess
    ohne öffnenden <think> Tag aus, aber mit schließendem </think> Tag.

    LOGIK:
    - Wenn <think> UND </think> vorhanden → Nichts tun (korrekte Tags)
    - Wenn NUR </think> vorhanden (ohne <think>) → <think> am Anfang einfügen

    Args:
        text: Text mit potentiell fehlendem öffnenden Tag

    Returns:
        Text mit repariertem Tag (falls nötig)

    Example:
        Input:  "Okay, let me think...\\n</think>\\nAnswer here"
        Output: "<think>Okay, let me think...\\n</think>\\nAnswer here"

        Input:  "<think>normal</think> text"  # Bleibt unverändert
        Output: "<think>normal</think> text"
    """
    has_opening = '<think>' in text
    has_closing = '</think>' in text

    # Nur reparieren wenn schließender Tag da ist, aber kein öffnender
    if has_closing and not has_opening:
        text = '<think>' + text
        log_message("🔧 Fehlender <think> Tag repariert (öffnender Tag hinzugefügt)")

    return text


def extract_xml_tags(text: str) -> list[tuple[str, str]]:
    """
    Extrahiert ALLE XML-Tags aus Text (generisch, nicht hardcoded).

    WICHTIG:
    1. HTML-Tags werden IGNORIERT (Blacklist in html_tags.py)
    2. Tags innerhalb von Markdown Code-Blocks werden IGNORIERT!
       (``` ... ``` Blöcke enthalten oft HTML/XML Code-Beispiele)
    3. Verwaiste schließende </think> Tags werden automatisch repariert!

    Args:
        text: Text mit optionalen XML-Tags

    Returns:
        Liste von (tag_name, content) Tuples (ohne HTML-Tags, ohne Code-Block-Tags!)

    Example:
        >>> extract_xml_tags("<think>foo</think> bar <python>code</python>")
        [("think", "foo"), ("python", "code")]

        >>> extract_xml_tags("<span style='...'>text</span>")  # HTML ignoriert!
        []

        >>> extract_xml_tags("```html\\n<head>...</head>\\n```")  # Code-Block ignoriert!
        []

        >>> extract_xml_tags("Thinking...\\n</think>\\nAnswer")  # Verwaister Tag repariert!
        [("think", "Thinking...")]

    Note:
        Die Reparatur verwaister </think> Tags erfolgt in den aufrufenden Funktionen
        (format_thinking_process, build_debug_accordion), BEVOR extract_xml_tags aufgerufen wird.
        Dies ist notwendig, damit clean_response korrekt funktioniert.
    """
    # STEP 1: Entferne Markdown Code-Blocks BEVOR wir nach XML-Tags suchen
    # Code-Blocks können HTML/XML Code-Beispiele enthalten, die NICHT verarbeitet werden sollen
    text_without_codeblocks = re.sub(r'```[\s\S]*?```', '', text)

    # STEP 2: Generic XML pattern: <tagname>content</tagname>
    pattern = r'<(\w+)>(.*?)</\1>'
    matches = re.findall(pattern, text_without_codeblocks, re.DOTALL)

    # STEP 3: Filter: Nur Non-HTML Tags zurückgeben (Blacklist aus html_tags.py)
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

    # STEP 0: Repariere verwaiste </think> Tags BEVOR wir extrahieren
    # (Wichtig: Muss auf ai_response angewendet werden, damit clean_response später funktioniert)
    ai_response = fix_orphan_closing_think_tag(ai_response)

    # Extract ALL XML tags generically
    xml_tags = extract_xml_tags(ai_response)

    # Build collapsibles for each detected tag (if any)
    collapsibles = []
    for tag_name, content in xml_tags:
        config = XML_TAG_CONFIG.get(tag_name)

        if config:
            # Known tag → Use config (schönes Icon + Label)
            icon = config['icon']
            label = config['label']
            css_class = config['class']
        else:
            # Unknown tag → SKIP (nicht als Collapsible formatieren!)
            # Kleine Modelle geben oft Tags wie <result>, <function> aus,
            # die nicht als Collapsibles gedacht sind
            log_message(f"ℹ️ Überspringe unbekanntes XML-Tag: <{tag_name}> (nicht in XML_TAG_CONFIG)")
            continue

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

    # Remove nur BEKANNTE Tags (die zu Collapsibles wurden) aus dem Response
    # Unbekannte Tags bleiben im Text stehen!
    clean_response = ai_response
    for tag_name, _ in xml_tags:
        # Nur entfernen wenn Tag in Config ist (also ein Collapsible erstellt wurde)
        if tag_name in XML_TAG_CONFIG:
            pattern = rf'<{tag_name}>.*?</{tag_name}>'
            clean_response = re.sub(pattern, '', clean_response, count=1, flags=re.DOTALL)
    clean_response = clean_response.strip()

    # Return: Collapsibles + Clean Response
    if collapsibles:
        result = "\n\n".join(collapsibles) + "\n\n" + clean_response
    else:
        result = clean_response

    # FINAL STEP: HTML Preview für ```html Code-Blöcke
    result = format_html_preview(result)

    return result


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

    # STEP 0: Repariere verwaiste </think> Tags BEVOR wir extrahieren
    ai_text = fix_orphan_closing_think_tag(ai_text)

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

    # Entferne nur BEKANNTE Tags (think) aus dem Response
    # In build_debug_accordion wird nur <think> verarbeitet
    clean_response = ai_text
    for tag_name, _ in xml_tags:
        # Nur <think> Tag entfernen (das einzige was hier als Debug-Section verwendet wird)
        if tag_name == "think":
            pattern = rf'<{tag_name}>.*?</{tag_name}>'
            clean_response = re.sub(pattern, '', clean_response, count=1, flags=re.DOTALL)
    clean_response = clean_response.strip()

    # Return: Debug Accordion + Clean Response
    if debug_accordion:
        result = f"{debug_accordion}\n\n{clean_response}"
    else:
        result = clean_response

    # FINAL STEP: HTML Preview für ```html Code-Blöcke
    result = format_html_preview(result)

    return result
