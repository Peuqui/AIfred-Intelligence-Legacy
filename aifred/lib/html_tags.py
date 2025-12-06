"""
HTML Tag Blacklist for XML-Tag Processing

Diese Datei definiert HTML-Tags, die von der generischen XML-Tag-Erkennung
AUSGESCHLOSSEN werden sollen. Das verhindert, dass HTML-Elemente wie <span>
oder <div> versehentlich als Collapsibles formatiert werden.

Die Liste basiert auf dem HTML5-Standard und sollte selten angepasst werden.
Neue Tags können bei Bedarf hinzugefügt werden (z.B. für Custom Elements).

Usage:
    from aifred.lib.html_tags import HTML_TAG_BLACKLIST

    if tag_name.lower() not in HTML_TAG_BLACKLIST:
        # Process as XML tag (create collapsible)
        ...
"""

# HTML-Tags die NICHT als Collapsibles verarbeitet werden sollen
# Diese Tags werden von extract_xml_tags() ignoriert
HTML_TAG_BLACKLIST = {
    # ============================================================
    # INLINE-ELEMENTE
    # ============================================================
    'span',      # Inline container
    'a',         # Hyperlink
    'b',         # Bold (deprecated, use <strong>)
    'i',         # Italic (deprecated, use <em>)
    'u',         # Underline
    's',         # Strikethrough
    'em',        # Emphasis
    'strong',    # Strong importance
    'mark',      # Highlighted text
    'small',     # Small print
    'sub',       # Subscript
    'sup',       # Superscript
    'code',      # Inline code (NOT to be confused with <code> XML tag!)
    'kbd',       # Keyboard input
    'samp',      # Sample output
    'var',       # Variable
    'abbr',      # Abbreviation
    'cite',      # Citation
    'dfn',       # Definition
    'q',         # Inline quote
    'time',      # Time/date
    'br',        # Line break
    'wbr',       # Word break opportunity

    # ============================================================
    # BLOCK-ELEMENTE
    # ============================================================
    'div',       # Block container
    'p',         # Paragraph
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',  # Headings
    'pre',       # Preformatted text
    'blockquote',  # Block quote
    'hr',        # Horizontal rule
    'ul',        # Unordered list
    'ol',        # Ordered list
    'li',        # List item
    'dl',        # Description list
    'dt',        # Description term
    'dd',        # Description details
    'figure',    # Figure (image + caption)
    'figcaption',  # Figure caption
    'main',      # Main content
    'section',   # Section
    'article',   # Article
    'aside',     # Aside content
    'header',    # Header
    'footer',    # Footer
    'nav',       # Navigation
    'address',   # Address/contact info

    # ============================================================
    # TABELLEN
    # ============================================================
    'table',     # Table
    'thead',     # Table head
    'tbody',     # Table body
    'tfoot',     # Table foot
    'tr',        # Table row
    'th',        # Table header cell
    'td',        # Table data cell
    'caption',   # Table caption
    'colgroup',  # Column group
    'col',       # Column

    # ============================================================
    # FORMULARE
    # ============================================================
    'form',      # Form
    'input',     # Input field
    'button',    # Button
    'select',    # Dropdown
    'option',    # Dropdown option
    'optgroup',  # Option group
    'textarea',  # Text area
    'label',     # Label
    'fieldset',  # Field set
    'legend',    # Fieldset legend
    'datalist',  # Data list
    'output',    # Output
    'progress',  # Progress bar
    'meter',     # Meter

    # ============================================================
    # MEDIEN
    # ============================================================
    'img',       # Image
    'audio',     # Audio
    'video',     # Video
    'source',    # Media source
    'track',     # Text track (subtitles)
    'picture',   # Picture element
    'canvas',    # Canvas
    'svg',       # SVG
    'iframe',    # Inline frame

    # ============================================================
    # INTERAKTIVE ELEMENTE (inkl. unsere eigenen Collapsibles!)
    # ============================================================
    'details',   # Collapsible details (WIR NUTZEN DAS!)
    'summary',   # Details summary
    'dialog',    # Dialog/modal
    'menu',      # Menu
    'menuitem',  # Menu item (deprecated)

    # ============================================================
    # SONSTIGE / META
    # ============================================================
    'script',    # JavaScript
    'style',     # CSS
    'link',      # External resource link
    'meta',      # Metadata
    'base',      # Base URL
    'noscript',  # No-script fallback
    'template',  # Template
    'slot',      # Web component slot
}
