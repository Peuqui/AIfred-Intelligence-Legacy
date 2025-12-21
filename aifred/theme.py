"""
Dark Theme Configuration for AIfred Intelligence (Gradio-Style)
"""

# Hybrid Dark Theme - GitHub Professional + Matrix Debug Console
COLORS = {
    # === BACKGROUNDS (3-level hierarchy) ===
    "page_bg": "#0d1117",        # GitHub Dark (darkest)
    "card_bg": "#161b22",        # GitHub Cards (medium)
    "input_bg": "#21262d",       # GitHub Inputs (lightest)
    "readonly_bg": "#161b22",    # Same as cards

    # === TEXT (high contrast) ===
    "text_primary": "#e6edf3",   # GitHub Text (almost white)
    "text_secondary": "#7d8590",  # GitHub Gray (labels)
    "text_muted": "#484f58",     # GitHub Muted (helper text)

    # === ACCENT COLORS ===
    "primary": "#e67700",        # Muted orange (more professional)
    "primary_hover": "#ff9500",  # Brighter orange on hover
    "primary_active": "#cc6a00",  # Darker on click
    "primary_bg": "rgba(230, 119, 0, 0.15)",  # Semi-transparent orange background (15% opacity)
    "accent_blue": "#58a6ff",    # GitHub Blue (for links)
    "accent_success": "#3fb950", # GitHub Green (success)
    "accent_warning": "#d29922", # GitHub Yellow (warning)
    "danger": "#f85149",         # GitHub Red (error/delete)

    # === CHAT BUBBLES (subtle distinction) ===
    "user_msg": "#21262d",       # Dark blue-gray - User
    "user_text": "#d1d5db",      # Softer gray (not harsh)
    "ai_msg": "#161b22",         # Even darker - AI
    "ai_text": "#e6edf3",        # Slightly dimmed

    # === BORDERS (GitHub Style) ===
    "border": "#30363d",         # GitHub Border (subtle but visible)
    "border_light": "#484f58",   # Slightly lighter

    # === DEBUG CONSOLE (Matrix/Hacker Terminal) ===
    "debug_bg": "#0d1117",       # Very dark (almost black)
    "debug_text": "#00ff41",     # Matrix neon green
    "debug_border": "#1a4d1a",   # Dark green (subtle)
    "debug_accent": "#00aa00",   # Medium green (for header)

    # === WARNING/INFO ===
    "warning_bg": "#2d1f00",     # Even darker brown (darker than send text button)
    "warning_text": "#d29922",   # GitHub Yellow
}

# Custom CSS for Reflex components
CUSTOM_CSS = """
/* Global dark theme */
body {
    background-color: #0b0f19;
    color: #e2e8f0;
}

/* Override Reflex default card backgrounds */
.rx-Box {
    background-color: transparent;
}

/* Select dropdown content - max height with scroll for mobile */
.rt-SelectContent {
    max-height: min(var(--radix-select-content-available-height), 300px) !important;
    overflow-y: auto !important;
}

/* Ensure select viewport is scrollable */
.rt-SelectViewport {
    max-height: inherit !important;
    overflow-y: auto !important;
}

/* Debug console monospace */
.debug-console {
    font-family: 'Courier New', Consolas, monospace !important;
    font-size: 11px !important;
    line-height: 1.4 !important;
    background-color: #1a1a1a !important;
    color: #00ff00 !important;
}

/* Switch Styling - Orange Warning Colors */
.rt-SwitchRoot[data-state="checked"] {
    background-color: #2d1f00 !important;  /* Dark orange background */
}

.rt-SwitchRoot[data-state="unchecked"] {
    background-color: #30363d !important;  /* Gray when off */
}

.rt-SwitchThumb {
    background-color: #d29922 !important;  /* Bright orange for circle */
}

/* Scrollbar styling for dark theme */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

::-webkit-scrollbar-track {
    background: #1a202c;
}

::-webkit-scrollbar-thumb {
    background: #4a5568;
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: #718096;
}

/* Chat History Accordion - Orange instead of Blue */
.rt-AccordionTrigger[data-state="open"],
.rt-AccordionTrigger[data-state="closed"] {
    background-color: #161b22 !important;  /* Dark gray */
}

.rt-AccordionTrigger:hover {
    background-color: rgba(230, 119, 0, 0.15) !important;  /* Orange on hover */
}

/* Thinking Process Collapsible - More compact paragraphs */
.thinking-compact {
    color: #aaa !important;
}

.thinking-compact p {
    margin-top: 0.75em !important;
    margin-bottom: 0.75em !important;
    color: #aaa !important;
}

.thinking-compact > :first-child {
    margin-top: 0.5em !important;
}

.thinking-compact > :last-child {
    margin-bottom: 0.3em !important;
}

/* NOTE: Link styles moved to assets/custom.css for proper loading */
"""
