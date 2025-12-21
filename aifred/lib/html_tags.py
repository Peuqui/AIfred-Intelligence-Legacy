"""
HTML Tag Blacklist for XML-Tag Processing

This file defines HTML tags that should be EXCLUDED from generic XML-tag detection.
This prevents HTML elements like <span> or <div> from being accidentally formatted
as collapsibles.

The list is based on the HTML5 standard and should rarely need modification.
New tags can be added as needed (e.g., for Custom Elements).

Usage:
    from aifred.lib.html_tags import HTML_TAG_BLACKLIST

    if tag_name.lower() not in HTML_TAG_BLACKLIST:
        # Process as XML tag (create collapsible)
        ...
"""

# HTML tags that should NOT be processed as collapsibles
# These tags are ignored by extract_xml_tags()
HTML_TAG_BLACKLIST = {
    # ============================================================
    # INLINE ELEMENTS
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
    # BLOCK ELEMENTS
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
    # TABLES
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
    # FORMS
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
    # MEDIA
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
    # INTERACTIVE ELEMENTS (incl. our own collapsibles!)
    # ============================================================
    'details',   # Collapsible details (WE USE THIS!)
    'summary',   # Details summary
    'dialog',    # Dialog/modal
    'menu',      # Menu
    'menuitem',  # Menu item (deprecated)

    # ============================================================
    # DOCUMENT STRUCTURE (HTML document tags)
    # ============================================================
    'html',      # Root element
    'head',      # Document head
    'body',      # Document body
    'title',     # Page title
    'doctype',   # DOCTYPE declaration (detected as tag)

    # ============================================================
    # MISCELLANEOUS / META
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
