"""
AIfred Intelligence - Reflex Edition

Full Gradio-Style UI with Single Column Layout
"""

import reflex as rx
from .state import AIState
from .theme import COLORS
from .lib.i18n import TranslationManager


def t(key: str) -> rx.Var:
    """
    Translation helper that returns German or English text based on state.

    Uses centralized translations from i18n.py.
    Returns rx.cond() for Reflex frontend conditional rendering.
    """
    # Get translations from centralized TranslationManager
    de_text = TranslationManager._translations.get("de", {})
    en_text = TranslationManager._translations.get("en", {})

    return rx.cond(
        AIState.ui_language == "de",
        de_text.get(key, key),  # Fallback to key if not found
        en_text.get(key, key)   # Fallback to key if not found
    )


# ============================================================
# MOBILE NATIVE SELECT HELPERS
# ============================================================

def native_select_backend(value_var, on_change_handler, disabled_condition, backend_list) -> rx.Component:
    """Native HTML <select> for Backend Selection (Mobile)

    Simple approach: value and text are the same (display name like "Ollama").
    Identical pattern to native_select_model.

    Args:
        value_var: State variable for current backend display name (AIState.backend_label)
        on_change_handler: Event handler function (AIState.switch_backend_by_label)
        disabled_condition: Boolean condition to disable the select
        backend_list: List of backend display names (e.g., ["Ollama", "KoboldCPP"])
    """
    return rx.el.select(
        # Simple foreach - value and text are the same
        rx.foreach(
            backend_list,
            lambda backend: rx.el.option(
                backend,  # Display: "Ollama"
                value=backend,  # Value: "Ollama" (same!)
            ),
        ),
        value=value_var,
        on_change=on_change_handler,
        disabled=disabled_condition,
        # Dark theme styling for native select (same as native_select_model)
        style={
            "width": "100%",
            "min_width": "120px",  # Ensure minimum width for text
            "flex": "1",  # Take available space in hstack
            "padding": "8px 12px",
            "font_size": "12px",
            "color": COLORS["text_primary"],
            "background": COLORS["input_bg"],
            "border": f"1px solid {COLORS['border']}",
            "border_radius": "6px",
            "min_height": "48px",
            "cursor": "pointer",
            "white_space": "nowrap",
            "overflow": "hidden",
            "text_overflow": "ellipsis",
        },
    )


def native_select_model(value_var, on_change_handler, disabled_condition=False, model_list=None) -> rx.Component:
    """Native HTML <select> for Model Selection (Mobile)

    Uses simple list of display names (like before).
    The value must match one of the options exactly.

    Args:
        value_var: State variable for current value (display name with size)
        on_change_handler: Event handler function
        disabled_condition: Boolean condition to disable the select (default: False)
        model_list: List of model display names (default: AIState.available_models)
    """
    # Default to available_models if no list specified
    models = model_list if model_list is not None else AIState.available_models

    return rx.el.select(
        # Generate options - value and text are the same (display name)
        rx.foreach(
            models,
            lambda model: rx.el.option(
                model,  # Display: "qwen3:8b (2.3 GB)"
                value=model,  # Value: "qwen3:8b (2.3 GB)" (same!)
            ),
        ),
        value=value_var,
        on_change=on_change_handler,
        disabled=disabled_condition,
        # Dark theme styling for native select - Model names visible
        style={
            "width": "100%",
            "padding": "8px 12px",
            "font_size": "12px",  # Smaller font to fit more text
            "color": COLORS["text_primary"],
            "background": COLORS["input_bg"],
            "border": f"1px solid {COLORS['border']}",
            "border_radius": "6px",
            "min_height": "48px",  # Touch-friendly
            "cursor": "pointer",
            "white_space": "nowrap",  # Don't wrap long model names
            "overflow": "hidden",  # Hide overflow
            "text_overflow": "ellipsis",  # Show ... if text is too long
        },
    )


def native_select_tts(value_var, on_change_handler, options_list) -> rx.Component:
    """Native HTML <select> for TTS Settings (Mobile)

    Same styling as backend/model selects for consistent mobile experience.
    """
    return rx.el.select(
        rx.foreach(
            options_list,
            lambda option: rx.el.option(option, value=option),
        ),
        value=value_var,
        on_change=on_change_handler,
        style={
            "width": "100%",
            "flex": "1",
            "padding": "8px 12px",
            "font_size": "12px",
            "color": COLORS["text_primary"],
            "background": COLORS["input_bg"],
            "border": f"1px solid {COLORS['border']}",
            "border_radius": "6px",
            "min_height": "48px",
            "cursor": "pointer",
            "white_space": "nowrap",
            "overflow": "hidden",
            "text_overflow": "ellipsis",
        },
    )


def native_select_stt(value_var, on_change_handler, options_list) -> rx.Component:
    """Native HTML <select> for STT Settings (Mobile)

    Same styling as backend/model selects for consistent mobile experience.
    """
    return rx.el.select(
        rx.foreach(
            options_list,
            lambda option: rx.el.option(option, value=option),
        ),
        value=value_var,
        on_change=on_change_handler,
        style={
            "width": "100%",
            "flex": "1",
            "padding": "8px 12px",
            "font_size": "12px",
            "color": COLORS["text_primary"],
            "background": COLORS["input_bg"],
            "border": f"1px solid {COLORS['border']}",
            "border_radius": "6px",
            "min_height": "48px",
            "cursor": "pointer",
            "white_space": "nowrap",
            "overflow": "hidden",
            "text_overflow": "ellipsis",
        },
    )


def native_select_generic(value_var, on_change_handler, options_pairs) -> rx.Component:
    """Native HTML <select> for generic key/value options (Mobile)

    Args:
        value_var: State variable for current value (the key, e.g., "auto_consensus")
        on_change_handler: Handler for value changes
        options_pairs: List of [key, display_label] pairs, e.g., [["standard", "Standard"], ["auto_consensus", "Auto-Konsens"]]

    Same styling as backend/model selects for consistent mobile experience.
    """
    return rx.el.select(
        rx.foreach(
            options_pairs,
            lambda pair: rx.el.option(pair[1], value=pair[0]),  # pair[0]=key, pair[1]=label
        ),
        value=value_var,
        on_change=on_change_handler,
        style={
            "width": "100%",
            "flex": "1",
            "padding": "8px 12px",
            "font_size": "12px",
            "color": COLORS["text_primary"],
            "background": COLORS["input_bg"],
            "border": f"1px solid {COLORS['border']}",
            "border_radius": "6px",
            "min_height": "48px",
            "cursor": "pointer",
            "white_space": "nowrap",
            "overflow": "hidden",
            "text_overflow": "ellipsis",
        },
    )


# ============================================================
# LEFT COLUMN: Input Controls
# ============================================================

def audio_input_section() -> rx.Component:
    """Placeholder - audio button is now integrated in image_upload_section"""
    return rx.box()  # Empty - no longer needed


def image_upload_section() -> rx.Component:
    """Image and Audio upload components with preview"""
    return rx.vstack(
        # Warning box (if model doesn't support vision)
        rx.cond(
            AIState.image_upload_warning != "",
            rx.box(
                rx.text(AIState.image_upload_warning),
                background_color="rgba(255, 152, 0, 0.15)",
                border="2px solid rgba(255, 152, 0, 0.5)",
                padding="8px 12px",
                border_radius="6px",
                margin_bottom="8px",
            )
        ),

        # Row 1: Buttons (Aufnahme, Camera, Upload, Audio, Clear) - linksbündig
        rx.hstack(
            # Live Audio Recording Button (LEFTMOST - MediaRecorder)
            rx.button(
                rx.icon("mic", size=20),
                rx.text(t("recording"), font_size="16px", display=["none", "none", "inline"]),  # Hide text on mobile
                id="recording-button",
                size="4",
                variant="soft",
                color_scheme="green",
                padding_y="24px",
                on_click=AIState.toggle_audio_recording,  # Trigger JavaScript via State handler
                disabled=AIState.is_generating | AIState.is_uploading_image,
            ),

            # Camera button (only visible if browser supports camera)
            rx.cond(
                AIState.camera_available,
                rx.upload(
                    rx.button(
                        rx.icon("camera", size=20),
                        rx.text(t("camera"), font_size="16px", display=["none", "none", "inline"]),  # Hide text on mobile
                        size="4",
                        variant="soft",
                        color_scheme="red",
                        padding_y="24px",
                        disabled=AIState.is_generating | AIState.is_uploading_image | (AIState.pending_images.length() >= AIState.max_images_per_message),
                    ),
                    id="camera-upload",
                    accept={"image/*": []},  # Accept images from camera
                    max_files=1,  # Camera captures one photo at a time
                    on_drop=AIState.handle_camera_upload,  # Camera handler shortens filenames
                    multiple=False,
                    border="none",
                    padding="0",
                ),
            ),

            # Upload button with drag & drop
            rx.upload(
                rx.button(
                    rx.icon("image", size=20),
                    rx.text(t("upload_image"), font_size="16px"),
                    size="4",
                    variant="soft",
                    color_scheme="red",
                    padding_y="24px",
                    disabled=AIState.is_generating | AIState.is_uploading_image | (AIState.pending_images.length() >= AIState.max_images_per_message),
                ),
                id="image-upload",
                accept={"image/*": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]},
                max_files=AIState.max_images_per_message,
                on_drop=AIState.handle_image_upload,
                multiple=True,
                border="none",
                padding="0",
            ),

            # Audio File Upload Button (rightmost - next to image upload)
            rx.upload(
                rx.button(
                    rx.icon("file-audio", size=20),
                    rx.text(t("audio"), font_size="16px", display=["none", "none", "inline"]),  # Hide text on mobile
                    size="4",
                    variant="soft",
                    color_scheme="blue",
                    padding_y="24px",
                    disabled=AIState.is_generating | AIState.is_uploading_image,
                ),
                id="audio-upload",
                accept={"audio/*": [".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"]},
                max_files=1,
                on_drop=AIState.handle_audio_upload,
                multiple=False,
                border="none",
                padding="0",
            ),

            # Hidden upload for MediaRecorder (JavaScript will populate this)
            rx.upload(
                rx.box(display="none"),  # Hidden, only for JS interaction
                id="audio-recording-upload",
                accept={"audio/*": [".webm"]},
                max_files=1,
                on_drop=AIState.handle_audio_upload,
                multiple=False,
                border="none",
                padding="0",
            ),

            # Clear button (only show if images present)
            rx.cond(
                AIState.pending_images.length() > 0,
                rx.button(
                    rx.icon("trash-2", size=20),
                    rx.text(t("clear_all"), font_size="16px"),
                    size="4",
                    variant="soft",
                    color_scheme="red",
                    padding_y="24px",
                    on_click=AIState.clear_pending_images,
                )
            ),

            # Info-Icon mit Hover-Card für Drag & Drop Hint (nur Desktop)
            rx.cond(
                AIState.is_mobile,
                rx.fragment(),
                rx.hover_card.root(
                    rx.hover_card.trigger(
                        rx.icon("info", size=16, color=COLORS["text_secondary"], cursor="help"),
                    ),
                    rx.hover_card.content(
                        rx.text(t("image_hint"), font_size="12px", color=COLORS["text_primary"]),
                        side="top",
                        style={
                            "background": COLORS["card_bg"],
                            "border": f"1px solid {COLORS['border']}",
                            "border_radius": "8px",
                            "padding": "8px 12px",
                            "box_shadow": "0 4px 12px rgba(0,0,0,0.4)",
                        },
                    ),
                ),
            ),

            spacing="2",
            width="100%",
            justify_content="flex-start",  # Buttons linksbündig
        ),

        # Row 2: Transkription bearbeiten Toggle (direkt unter Aufnahme-Button)
        rx.hstack(
            rx.text(t("transcription_edit"), font_size="11px", font_weight="500"),
            rx.switch(
                checked=AIState.show_transcription,
                on_change=AIState.toggle_show_transcription,
                size="1",
            ),
            rx.text(
                rx.cond(
                    AIState.show_transcription,
                    t("text_edit"),
                    t("text_direct")
                ),
                font_size="10px",
                color=rx.cond(
                    AIState.show_transcription,
                    "#4CAF50",
                    "#999"
                ),
            ),
            spacing="2",
            align="center",
            margin_top="8px",
            margin_bottom="4px",
        ),

        # Row 3: Image previews (only if images present) - linksbündig
        rx.cond(
            AIState.pending_images.length() > 0,
            rx.hstack(
                rx.foreach(
                    AIState.pending_images,
                    lambda img, idx: rx.box(
                        # Thumbnail - 80px für bessere Sichtbarkeit
                        rx.image(
                            src=img["url"],
                            width="80px",
                            height="80px",
                            object_fit="cover",
                            border_radius="4px",
                            border="1px solid #30363d",
                        ),
                        # Crop-Button (links oben) - größer für Touch
                        rx.icon_button(
                            rx.icon("crop", size=16),
                            size="2",  # Größer für bessere Touch-Bedienung
                            color_scheme="green",
                            variant="solid",
                            position="absolute",
                            top="4px",
                            left="4px",
                            on_click=AIState.open_crop_modal(idx),
                            title=t("crop_tooltip"),
                        ),
                        # Remove-Button (rechts oben) - größer für Touch
                        rx.icon_button(
                            rx.icon("x", size=16),
                            size="2",  # Größer für bessere Touch-Bedienung
                            color_scheme="red",
                            variant="solid",
                            position="absolute",
                            top="4px",
                            right="4px",
                            on_click=AIState.remove_pending_image(idx),
                        ),
                        position="relative",
                    )
                ),
                spacing="3",
                wrap="wrap",
                justify_content="flex-start",  # Thumbnails linksbündig
                width="100%",
                margin_top="8px",
                margin_bottom="8px",
            ),
        ),

        width="100%",
        spacing="2"
    )


def text_input_section() -> rx.Component:
    """Text input section with research mode"""
    return rx.vstack(
        # Image Upload Section (NEW)
        image_upload_section(),

        # Text Input
        rx.heading(
            t("text_input_heading"),
            size="2"
        ),
        rx.text_area(
            placeholder=t("text_input_placeholder"),
            value=AIState.current_user_input,
            on_change=AIState.set_user_input,
            width="100%",
            rows="5",
            disabled=AIState.is_generating | AIState.is_compressing | AIState.is_uploading_image,
            style={
                "border": f"1px solid {COLORS['border']}",
                "&:focus": {
                    "border": f"1px solid {COLORS['accent_blue']}",
                    "outline": "none",
                },
            },
        ),

        # Research Mode Radio Buttons
        rx.vstack(
            rx.hstack(
                rx.text(t("research_mode"), font_weight="bold", font_size="12px"),
                # Info-Icon mit Hover-Card (nur Desktop) - in Header-Zeile
                rx.cond(
                    AIState.is_mobile,
                    rx.fragment(),
                    rx.hover_card.root(
                        rx.hover_card.trigger(
                            rx.icon("info", size=14, color=COLORS["text_secondary"], cursor="help"),
                        ),
                        rx.hover_card.content(
                            rx.text(t("choose_research_mode"), font_size="12px", color=COLORS["text_primary"]),
                            side="top",
                            style={
                                "background": COLORS["card_bg"],
                                "border": f"1px solid {COLORS['border']}",
                                "border_radius": "8px",
                                "padding": "8px 12px",
                                "box_shadow": "0 4px 12px rgba(0,0,0,0.4)",
                            },
                        ),
                    ),
                ),
                spacing="2",
                align="center",
            ),
            rx.radio(
                [
                    rx.cond(AIState.ui_language == "de", "✨ Automatik (KI entscheidet)", "✨ Automatic (AI decides)"),
                    rx.cond(AIState.ui_language == "de", "💡 Eigenes Wissen (schnell)", "💡 Own Knowledge (fast)"),
                    rx.cond(AIState.ui_language == "de", "⚡ Web-Suche Schnell (3 beste)", "⚡ Web Search Quick (3 best)"),
                    rx.cond(AIState.ui_language == "de", "🌍 Web-Suche Ausführlich (7 beste)", "🌍 Web Search Detailed (7 best)")
                ],
                value=AIState.research_mode_display,
                on_change=AIState.set_research_mode_display,
                spacing="2",
            ),
            width="100%",
        ),

        # Multi-Agent Mode + LLM Parameters Row
        rx.hstack(
            # Left: Multi-Agent Mode Dropdown
            rx.vstack(
                rx.text(t("multi_agent_mode"), font_weight="bold", font_size="12px"),
                rx.hstack(
                    rx.cond(
                        AIState.is_mobile,
                        # MOBILE: Native HTML <select>
                        native_select_generic(
                            AIState.multi_agent_mode,
                            AIState.set_multi_agent_mode,
                            AIState.multi_agent_mode_options,
                        ),
                        # DESKTOP: Radix UI Select
                        rx.select.root(
                            rx.select.trigger(),
                            rx.select.content(
                                rx.select.item(
                                    rx.cond(AIState.ui_language == "de", "Standard", "Standard"),
                                    value="standard"
                                ),
                                rx.select.item(
                                    rx.cond(AIState.ui_language == "de", "Kritische Prüfung", "Critical Review"),
                                    value="critical_review"
                                ),
                                rx.select.item(
                                    rx.cond(AIState.ui_language == "de", "Auto-Konsens", "Auto-Consensus"),
                                    value="auto_consensus"
                                ),
                                rx.select.item(
                                    rx.cond(AIState.ui_language == "de", "Advocatus Diaboli", "Devil's Advocate"),
                                    value="devils_advocate"
                                ),
                                rx.select.item(
                                    rx.cond(AIState.ui_language == "de", "Tribunal", "Tribunal"),
                                    value="tribunal"
                                ),
                            ),
                            value=AIState.multi_agent_mode,
                            on_change=AIState.set_multi_agent_mode,
                        ),
                    ),
                    # Glühbirnen-Icon für Hilfe-Modal (Desktop + Mobile)
                    rx.icon(
                        "lightbulb",
                        size=18,
                        color="#FFD700",
                        cursor="pointer",
                        on_click=AIState.open_multi_agent_help,
                        style={
                            "transition": "transform 0.2s ease",
                            "&:hover": {
                                "transform": "scale(1.15)",
                            },
                        },
                    ),
                    # Consensus Type Toggle (nur bei auto_consensus sichtbar, neben Glühbirne)
                    rx.cond(
                        AIState.multi_agent_mode == "auto_consensus",
                        rx.hstack(
                            # Dynamisches Label: 2/3 (grau) oder 3/3 (aktiv)
                            rx.text(
                                rx.cond(
                                    AIState.is_unanimous_consensus,
                                    "3/3",
                                    "2/3"
                                ),
                                font_size="11px",
                                color=rx.cond(
                                    AIState.is_unanimous_consensus,
                                    COLORS["primary"],
                                    "var(--gray-10)"
                                ),
                                font_weight="600",
                                min_width="24px",
                                text_align="right",
                            ),
                            rx.switch(
                                checked=AIState.is_unanimous_consensus,
                                on_change=AIState.toggle_consensus_type,
                                size="1",
                            ),
                            spacing="1",
                            align="center",
                            title=AIState.consensus_toggle_tooltip,
                            margin_left="8px",  # Mehr Abstand zur Glühbirne
                        ),
                    ),
                    spacing="3",
                    align="center",
                ),
                # Max Debate Rounds Slider (visible for "auto_consensus" and "tribunal" modes)
                rx.cond(
                    (AIState.multi_agent_mode == "auto_consensus") | (AIState.multi_agent_mode == "tribunal"),
                    rx.hstack(
                        rx.text(t("max_debate_rounds"), font_size="11px"),
                        rx.text(
                            AIState.max_debate_rounds,
                            font_size="11px",
                            font_weight="bold",
                            color=COLORS["primary"],
                        ),
                        rx.slider(
                            value=[AIState.max_debate_rounds],
                            min=1,
                            max=10,
                            step=1,
                            on_change=AIState.set_max_debate_rounds,
                            width="100px",
                        ),
                        spacing="2",
                        align="center",
                        padding_top="4px",
                    ),
                ),
                spacing="1",
            ),
            # Right: LLM Parameters Accordion (mit margin-top für Alignment mit Dropdown)
            rx.box(
                llm_parameters_accordion(),
                margin_top="18px",  # Aligned mit Auto-Konsens Dropdown
            ),
            spacing="4",
            align="start",
            width="100%",
        ),

        # Processing Progress Banner (above the send button - always visible)
        processing_progress_banner(),

        # Action Buttons
        rx.hstack(
            rx.button(
                t("send_text"),
                on_click=AIState.send_message,
                size="2",
                variant="solid",  # Explizit solid, ohne color_scheme
                loading=AIState.is_generating | AIState.is_compressing | AIState.is_uploading_image,
                disabled=AIState.is_generating | AIState.is_compressing | AIState.is_uploading_image,
                flex="1",  # Nimmt mehr Platz
                style={
                    "background": "#3d2a00 !important",  # Dunkles Orange (wichtig!)
                    "color": COLORS["accent_warning"] + " !important",  # Orange Text
                    "border": f"1px solid {COLORS['accent_warning']}",
                    "font_weight": "600",
                    "font_size": "14px",
                    "&:hover": {
                        "background": "#4d3500 !important",
                        "color": "#ffb84d !important",
                    },
                    "&:active": {
                        "background": "#331a00 !important",
                        "color": "#ff9500 !important",
                        "transform": "scale(0.98)",
                    },
                },
            ),
            rx.button(
                t("clear_chat"),
                on_click=AIState.clear_chat,
                disabled=AIState.is_generating | AIState.is_compressing | AIState.is_uploading_image,  # Deaktiviert während Inferenz und Kompression
                size="2",
                variant="outline",
                color_scheme="orange",
                style={
                    "min_width": "120px",
                    "background": "rgba(100, 10, 0, 0.4)",  # Dezenter transparenter roter Hintergrund
                    "&:hover:not([disabled])": {
                        "background": "rgba(150, 15, 0, 0.6) !important",
                        "border_color": "#ff6600 !important",
                        "transform": "scale(1.02)",
                    },
                    "&:active:not([disabled])": {
                        "background": "rgba(80, 5, 0, 0.7) !important",
                        "transform": "scale(0.98)",
                    },
                },
            ),
            rx.button(
                t("share_chat"),
                on_click=AIState.share_chat,
                disabled=AIState.is_generating | AIState.is_compressing | AIState.is_uploading_image,
                size="2",
                variant="outline",
                color_scheme="blue",
                style={
                    "min_width": "120px",
                    "background": "rgba(0, 50, 100, 0.4)",  # Dezenter transparenter blauer Hintergrund
                    "&:hover:not([disabled])": {
                        "background": "rgba(0, 80, 150, 0.6) !important",
                        "border_color": "#4da6ff !important",
                        "transform": "scale(1.02)",
                    },
                    "&:active:not([disabled])": {
                        "background": "rgba(0, 40, 80, 0.7) !important",
                        "transform": "scale(0.98)",
                    },
                },
            ),
            spacing="2",
            width="100%",
        ),

        spacing="3",
        width="100%",
    )


def temperature_control_section() -> rx.Component:
    """Temperature control with Auto/Manual toggle and multi-agent sliders"""
    return rx.vstack(
        # Header
        rx.text(
            rx.cond(
                AIState.ui_language == "de",
                "🌡️ Temperature",
                "🌡️ Temperature"
            ),
            font_weight="bold",
            font_size="12px"
        ),

        # Mode Toggle (Radio Buttons) - Language-aware
        rx.cond(
            AIState.ui_language == "de",
            rx.radio(
                ["🤖 Auto (Intent-Detection)", "✋ Manuell"],
                default_value=rx.cond(
                    AIState.temperature_mode == "manual",
                    "✋ Manuell",
                    "🤖 Auto (Intent-Detection)"
                ),
                on_change=AIState.set_temperature_mode_from_display,
                direction="column",
                spacing="2",
                size="2",
            ),
            rx.radio(
                ["🤖 Auto (Intent-Detection)", "✋ Manual"],
                default_value=rx.cond(
                    AIState.temperature_mode == "manual",
                    "✋ Manual",
                    "🤖 Auto (Intent-Detection)"
                ),
                on_change=AIState.set_temperature_mode_from_display,
                direction="column",
                spacing="2",
                size="2",
            ),
        ),

        # Conditional Sliders based on mode
        rx.cond(
            AIState.temperature_mode == "manual",
            # Manual Mode: Two separate sliders for AIfred and Sokrates
            rx.vstack(
                # AIfred Slider
                rx.hstack(
                    rx.text(
                        "🎩 AIfred:",
                        font_size="11px",
                        width="85px",
                        font_weight="500",
                    ),
                    rx.slider(
                        value=[AIState.temperature],
                        min=0.0,
                        max=2.0,
                        step=0.1,
                        on_change=AIState.set_temperature,
                        flex="1",
                    ),
                    rx.text(
                        f"{AIState.temperature:.1f}",
                        font_size="11px",
                        width="30px",
                        text_align="right",
                    ),
                    spacing="2",
                    width="100%",
                    align_items="center",
                ),
                # Sokrates Slider
                rx.hstack(
                    rx.text(
                        "🏛️ Sokrates:",
                        font_size="11px",
                        width="85px",
                        font_weight="500",
                    ),
                    rx.slider(
                        value=[AIState.sokrates_temperature],
                        min=0.0,
                        max=2.0,
                        step=0.1,
                        on_change=AIState.set_sokrates_temperature,
                        flex="1",
                    ),
                    rx.text(
                        f"{AIState.sokrates_temperature:.1f}",
                        font_size="11px",
                        width="30px",
                        text_align="right",
                    ),
                    spacing="2",
                    width="100%",
                    align_items="center",
                ),
                # Salomo Slider
                rx.hstack(
                    rx.text(
                        "⚖️ Salomo:",
                        font_size="11px",
                        width="85px",
                        font_weight="500",
                    ),
                    rx.slider(
                        value=[AIState.salomo_temperature],
                        min=0.0,
                        max=2.0,
                        step=0.1,
                        on_change=AIState.set_salomo_temperature,
                        flex="1",
                    ),
                    rx.text(
                        f"{AIState.salomo_temperature:.1f}",
                        font_size="11px",
                        width="30px",
                        text_align="right",
                    ),
                    spacing="2",
                    width="100%",
                    align_items="center",
                ),
                spacing="2",
                width="100%",
                padding_top="2",
            ),
            # Auto Mode: Offset sliders for Sokrates and Salomo
            rx.vstack(
                # Sokrates Offset
                rx.hstack(
                    rx.text(
                        "🏛️ Sokrates Offset:",
                        font_size="11px",
                        width="110px",
                        font_weight="500",
                    ),
                    rx.slider(
                        value=[AIState.sokrates_temperature_offset],
                        min=0.0,
                        max=0.5,
                        step=0.1,
                        on_change=AIState.set_sokrates_temperature_offset,
                        flex="1",
                    ),
                    rx.text(
                        f"+{AIState.sokrates_temperature_offset:.1f}",
                        font_size="11px",
                        width="35px",
                        text_align="right",
                    ),
                    spacing="2",
                    width="100%",
                    align_items="center",
                ),
                # Salomo Offset
                rx.hstack(
                    rx.text(
                        "⚖️ Salomo Offset:",
                        font_size="11px",
                        width="110px",
                        font_weight="500",
                    ),
                    rx.slider(
                        value=[AIState.salomo_temperature_offset],
                        min=0.0,
                        max=0.5,
                        step=0.1,
                        on_change=AIState.set_salomo_temperature_offset,
                        flex="1",
                    ),
                    rx.text(
                        f"+{AIState.salomo_temperature_offset:.1f}",
                        font_size="11px",
                        width="35px",
                        text_align="right",
                    ),
                    spacing="2",
                    width="100%",
                    align_items="center",
                ),
                rx.text(
                    rx.cond(
                        AIState.ui_language == "de",
                        "Agent-Temp = Intent-Temp + Offset (max 1.0)",
                        "Agent Temp = Intent Temp + Offset (max 1.0)"
                    ),
                    font_size="10px",
                    color=COLORS["text_secondary"],
                    font_style="italic",
                ),
                spacing="1",
                width="100%",
                padding_top="2",
            ),
        ),

        # Divider
        rx.divider(margin_y="3"),

        width="100%",
        spacing="2",
    )


def llm_parameters_accordion() -> rx.Component:
    """LLM Parameters in collapsible accordion - styled like select dropdown"""
    return rx.accordion.root(
        rx.accordion.item(
            header=rx.hstack(
                rx.text(
                    rx.cond(
                        AIState.ui_language == "de",
                        "⚙️ LLM-Parameter (Erweitert)",
                        "⚙️ LLM Parameters (Advanced)"
                    ),
                    font_weight="400",
                    font_size="13px",
                    color=COLORS["text_primary"]
                ),
                align="center",
                padding_x="6px",
                padding_y="0",
                height="28px",
            ),
            content=rx.vstack(
                # Temperature Control Section
                temperature_control_section(),

                # Context Window Control
                rx.vstack(
                    rx.text(
                        rx.cond(
                            AIState.ui_language == "de",
                            "📦 Context Window (num_ctx)",
                            "📦 Context Window (num_ctx)"
                        ),
                        font_weight="bold",
                        font_size="12px"
                    ),

                    # Per-LLM Context Control - Three columns with toggle + input
                    rx.hstack(
                        # AIfred num_ctx
                        rx.vstack(
                            rx.hstack(
                                rx.text(
                                    "🎩 AIfred",
                                    font_size="11px",
                                    font_weight="bold",
                                    color=COLORS["text_secondary"],
                                ),
                                rx.switch(
                                    checked=AIState.num_ctx_manual_aifred_enabled,
                                    on_change=AIState.toggle_num_ctx_manual_aifred,
                                    size="1",
                                ),
                                spacing="1",
                                align="center",
                            ),
                            rx.input(
                                placeholder="16384",
                                value=AIState.num_ctx_manual,
                                on_change=AIState.set_num_ctx_manual,
                                type="number",
                                width="75px",
                                disabled=~AIState.num_ctx_manual_aifred_enabled,
                                opacity=rx.cond(
                                    AIState.num_ctx_manual_aifred_enabled,
                                    "1.0",
                                    "0.5"
                                ),
                            ),
                            spacing="1",
                        ),
                        # Sokrates num_ctx
                        rx.vstack(
                            rx.hstack(
                                rx.text(
                                    "🏛️ Sokrates",
                                    font_size="11px",
                                    font_weight="bold",
                                    color=COLORS["text_secondary"],
                                ),
                                rx.switch(
                                    checked=AIState.num_ctx_manual_sokrates_enabled,
                                    on_change=AIState.toggle_num_ctx_manual_sokrates,
                                    size="1",
                                ),
                                spacing="1",
                                align="center",
                            ),
                            rx.input(
                                placeholder="16384",
                                value=AIState.num_ctx_manual_sokrates,
                                on_change=AIState.set_num_ctx_manual_sokrates,
                                type="number",
                                width="75px",
                                disabled=~AIState.num_ctx_manual_sokrates_enabled,
                                opacity=rx.cond(
                                    AIState.num_ctx_manual_sokrates_enabled,
                                    "1.0",
                                    "0.5"
                                ),
                            ),
                            spacing="1",
                        ),
                        # Salomo num_ctx
                        rx.vstack(
                            rx.hstack(
                                rx.text(
                                    "👑 Salomo",
                                    font_size="11px",
                                    font_weight="bold",
                                    color=COLORS["text_secondary"],
                                ),
                                rx.switch(
                                    checked=AIState.num_ctx_manual_salomo_enabled,
                                    on_change=AIState.toggle_num_ctx_manual_salomo,
                                    size="1",
                                ),
                                spacing="1",
                                align="center",
                            ),
                            rx.input(
                                placeholder="16384",
                                value=AIState.num_ctx_manual_salomo,
                                on_change=AIState.set_num_ctx_manual_salomo,
                                type="number",
                                width="75px",
                                disabled=~AIState.num_ctx_manual_salomo_enabled,
                                opacity=rx.cond(
                                    AIState.num_ctx_manual_salomo_enabled,
                                    "1.0",
                                    "0.5"
                                ),
                            ),
                            spacing="1",
                        ),
                        spacing="3",
                    ),

                    # Show Calculation Button (only visible in manual mode)
                    rx.cond(
                        AIState.num_ctx_mode == "manual",
                        rx.button(
                            rx.cond(
                                AIState.ui_language == "de",
                                "📊 Berechnung anzeigen",
                                "📊 Show Calculation"
                            ),
                            on_click=AIState.calculate_manual_context,
                            size="1",
                            variant="soft",
                            color_scheme="gray",
                        ),
                    ),

                    # Info Text
                    rx.text(
                        rx.cond(
                            AIState.ui_language == "de",
                            "Einstellung wird bei Neustart zurückgesetzt (nicht gespeichert)",
                            "Setting resets on restart (not saved)"
                        ),
                        font_size="11px",
                        color=COLORS["warning_text"],
                        font_style="italic",
                    ),

                    width="100%",
                    spacing="2",
                ),

                spacing="4",
                width="100%",
            ),
        ),
        collapsible=True,
        variant="ghost",  # Weniger visueller Overhead
        style={
            "border": "1px solid var(--gray-6)",
            "border_radius": "6px",
            "background": "var(--gray-2)",
            "min_height": "32px",
        },
    )


def left_column() -> rx.Component:
    """Complete left column with all input controls"""
    return rx.vstack(
        audio_input_section(),
        text_input_section(),
        spacing="4",
        width="100%",
    )


# ============================================================
# PROGRESS BANNER (wird unten eingefügt)
# ============================================================

def processing_progress_banner() -> rx.Component:
    """Progress banner for all processing phases (Automatik, Scraping, LLM) - Always visible"""

    # Berechne Fortschritt in Prozent (nur für Scraping relevant)
    progress_pct = rx.cond(
        AIState.progress_total > 0,
        (AIState.progress_current / AIState.progress_total) * 100,
        0
    )

    # Icon und Text basierend auf Phase
    phase_icon = rx.cond(
        AIState.is_uploading_image,
        "📤",  # Upload icon
        rx.cond(
            AIState.progress_active,
            rx.cond(
                AIState.progress_phase == "automatik",
                "🤖",
                rx.cond(
                    AIState.progress_phase == "scraping",
                    "🔍",
                    rx.cond(
                        AIState.progress_phase == "compress",
                        "🗜️",
                        "🧠"  # llm
                    )
                )
            ),
            "💤"  # Idle icon - sleeping/waiting
        )
    )

    phase_text = rx.cond(
        AIState.is_uploading_image,
        # Upload state - highest priority
        rx.cond(
            AIState.ui_language == "de",
            "Bild wird hochgeladen ...",
            "Uploading image ..."
        ),
        rx.cond(
            AIState.progress_active,
            rx.cond(
                AIState.progress_phase == "automatik",
                rx.cond(
                    AIState.ui_language == "de",
                    "Automatik-Entscheidung ...",
                    "Automatic decision ..."
                ),
                rx.cond(
                    AIState.progress_phase == "scraping",
                    rx.cond(
                        AIState.ui_language == "de",
                        "Web-Scraping",
                        "Web Scraping"
                    ),
                    rx.cond(
                        AIState.progress_phase == "compress",
                        rx.cond(
                            AIState.ui_language == "de",
                            "Komprimiere Kontext ...",
                            "Compressing Context ..."
                        ),
                        rx.cond(
                            AIState.ui_language == "de",
                            "Generiere Antwort ...",
                            "Generating Answer ..."
                        )
                    )
                )
            ),
            # Idle state text - aber zeige "Generiere Antwort" wenn is_generating=True
            rx.cond(
                AIState.is_generating,
                # Während Generierung (ohne Research)
                rx.cond(
                    AIState.ui_language == "de",
                    "Generiere Antwort ...",
                    "Generating Answer ..."
                ),
                # Wirklich idle
                rx.cond(
                    AIState.ui_language == "de",
                    "Warte auf Eingabe ...",
                    "Waiting for input ..."
                )
            )
        )
    )

    # Fortschrittsanzeige basierend auf Phase
    progress_content = rx.cond(
        # Progress-Bar nur für Scraping (wenn aktiv)
        (AIState.progress_active) & (AIState.progress_phase == "scraping"),
        rx.hstack(
            rx.text(phase_icon, font_size="14px"),
            rx.text(phase_text, font_weight="bold", font_size="13px", color=COLORS["primary"]),
            rx.box(
                rx.box(
                    width=f"{progress_pct}%",
                    height="100%",
                    background_color=COLORS["primary"],
                    border_radius="2px",
                    transition="width 0.3s ease",
                ),
                width="120px",
                height="14px",
                background_color="rgba(255, 255, 255, 0.1)",
                border_radius="4px",
                border=f"1px solid {COLORS['border']}",
                overflow="hidden",
            ),
            rx.text(
                f"{AIState.progress_current}/{AIState.progress_total}",
                font_size="12px",
                color=COLORS["primary"],  # Orange statt Grau - besser lesbar
                font_weight="600",
            ),
            rx.cond(
                AIState.progress_failed > 0,
                rx.text(
                    rx.cond(
                        AIState.progress_failed == 1,
                        rx.cond(
                            AIState.ui_language == "de",
                            "(1 Website nicht erreichbar)",
                            "(1 Website unreachable)"
                        ),
                        rx.cond(
                            AIState.ui_language == "de",
                            f"({AIState.progress_failed} Websites nicht erreichbar)",
                            f"({AIState.progress_failed} Websites unreachable)"
                        )
                    ),
                    font_size="11px",
                    color=COLORS["accent_warning"],  # Orange statt Grau - besser sichtbar
                    font_weight="500",
                ),
                rx.box(),
            ),
            spacing="2",
            align="center",
        ),
        # Nur Text für Automatik, LLM und Idle (mit Pulsier-Animation nur wenn aktiv)
        rx.hstack(
            rx.text(
                phase_icon,
                font_size="14px",
                style=rx.cond(
                    AIState.progress_active | AIState.is_generating,  # Pulse if progress OR generating
                    {
                        "animation": "pulse 2s ease-in-out infinite",
                        "@keyframes pulse": {
                            "0%, 100%": {"opacity": "1"},
                            "50%": {"opacity": "0.5"},
                        }
                    },
                    {}  # No animation when idle
                )
            ),
            rx.text(
                phase_text,
                font_weight=rx.cond(AIState.progress_active | AIState.is_generating, "bold", "500"),  # Bold if active OR generating
                font_size="13px",
                color=COLORS["primary"],  # Always orange text
                style=rx.cond(
                    AIState.progress_active | AIState.is_generating,  # Pulse if progress OR generating
                    {
                        "animation": "pulse 2s ease-in-out infinite",
                        "@keyframes pulse": {
                            "0%, 100%": {"opacity": "1"},
                            "50%": {"opacity": "0.5"},
                        }
                    },
                    {}  # No animation when idle
                )
            ),
            spacing="2",
            align="center",
        )
    )

    # Always return the banner (no conditional rendering)
    return rx.box(
        progress_content,
        padding="2",
        background_color=COLORS["primary_bg"],  # Always orange/yellow background
        border_radius="6px",
        border=f"1px solid {COLORS['primary']}",  # Always orange border
        width="100%",
    )


# NOTE: tts_section() removed - TTS controls are now in Settings Accordion


def parse_thinking(ai_response: str) -> tuple[str, str]:
    """
    Parse AI response to separate thinking from final answer.

    Returns:
        (thinking_text, final_answer)
    """
    # Check for common thinking patterns
    thinking_markers = [
        "After considering",
        "Let me think",
        "First, I'll",
        "To solve this",
        "Breaking this down",
        "Let's analyze",
        "Step by step"
    ]

    # Find if response starts with thinking
    for marker in thinking_markers:
        if ai_response.startswith(marker):
            # Find where thinking ends (usually before the actual answer)
            # Look for paragraph break or colon followed by newline
            parts = ai_response.split('\n\n', 1)
            if len(parts) == 2:
                return parts[0], parts[1]
            # Try splitting at colon + newline
            parts = ai_response.split(':\n', 1)
            if len(parts) == 2:
                return parts[0], parts[1]

    # No thinking found
    return "", ai_response


def render_failed_sources_inline(failed_sources) -> rx.Component:
    """
    Rendert failed sources als kompaktes Collapsible innerhalb einer Chat-Message.
    Dunkleres Orange-Theme für bessere Unterscheidbarkeit.
    """
    return rx.cond(
        failed_sources.length() > 0,
        rx.box(
            rx.accordion.root(
                rx.accordion.item(
                    value="inline_failed_sources",
                    header=rx.box(
                        rx.hstack(
                            rx.text("⚠", font_size="13px", line_height="1"),
                            rx.text(
                                rx.cond(
                                    AIState.ui_language == "de",
                                    # German: Singular/Plural
                                    rx.cond(
                                        failed_sources.length() == 1,
                                        f"{failed_sources.length()} Quelle nicht erreichbar",
                                        f"{failed_sources.length()} Quellen nicht erreichbar",
                                    ),
                                    # English: Singular/Plural
                                    rx.cond(
                                        failed_sources.length() == 1,
                                        f"{failed_sources.length()} source unavailable",
                                        f"{failed_sources.length()} sources unavailable",
                                    ),
                                ),
                                font_weight="500",
                                font_size="13px",
                                color="#cc6a00",  # Darker orange
                                line_height="1",
                            ),
                            spacing="1",
                            align="center",
                        ),
                        padding="0",
                        background_color="transparent",
                        cursor="pointer",
                    ),
                    content=rx.box(
                        rx.vstack(
                            rx.foreach(
                                failed_sources,
                                lambda src: rx.hstack(
                                    rx.link(
                                        rx.text(
                                            src["url"],
                                            font_size="13px",
                                            color=COLORS["accent_blue"],
                                            _hover={"text_decoration": "underline"},
                                            overflow="hidden",
                                            text_overflow="ellipsis",
                                            white_space="nowrap",
                                            max_width="450px",
                                        ),
                                        href=src["url"],
                                        is_external=True,
                                    ),
                                    rx.text(
                                        f"({src['error']})",
                                        font_size="12px",
                                        color=COLORS["text_muted"],
                                        font_style="italic",
                                    ),
                                    spacing="2",
                                    align="center",
                                    width="100%",
                                )
                            ),
                            spacing="0",
                            width="100%",
                            align_items="start",
                            padding_top="4px",
                        ),
                        padding="0",
                        width="100%",
                    ),
                ),
                collapsible=True,
                variant="ghost",
                width="auto",
            ),
            width="auto",
            margin_y="0",
        ),
        rx.fragment(),  # Empty component when no failed sources
    )


def render_history_thumbnail(img_url: str) -> rx.Component:
    """Render clickable thumbnail that opens lightbox on click"""
    return rx.image(
        src=img_url,
        width="50px",
        height="50px",
        object_fit="cover",
        border_radius="4px",
        cursor="pointer",
        border=f"1px solid {COLORS['border']}",
        on_click=AIState.open_lightbox(img_url),
        style={
            "transition": "transform 0.2s ease, box-shadow 0.2s ease",
            # Mobile touch handling - prevent native context menu
            "touch_action": "manipulation",
            "user_select": "none",
            "-webkit_touch_callout": "none",
            "-webkit_user_select": "none",
            "&:hover": {
                "transform": "scale(1.05)",
                "box_shadow": "0 2px 8px rgba(0,0,0,0.3)",
            },
            # Mobile active state (visual feedback on tap)
            "&:active": {
                "transform": "scale(0.95)",
                "opacity": "0.8",
            },
        },
    )


def render_image_thumbnails(images) -> rx.Component:
    """Render row of clickable image thumbnails"""
    return rx.cond(
        images.length() > 0,
        rx.hstack(
            rx.foreach(images, render_history_thumbnail),
            spacing="2",
            margin_bottom="2",
            flex_wrap="wrap",
        ),
        rx.fragment(),  # Empty component when no images
    )


def render_inline_summary(msg: dict) -> rx.Component:
    """
    Render a summary inline in the chat as a collapsible.

    This is shown at the position where the compression occurred in the chat,
    not at the top of the chat. Uses the same styling as the unified collapsible.

    Args:
        msg: Dict with summary_number, summary_count, summary_timestamp, summary_content
    """
    return rx.box(
        rx.accordion.root(
            rx.accordion.item(
                value="inline_summary",
                header=rx.box(
                    rx.hstack(
                        rx.text("📋", font_size="14px"),
                        # i18n label: "Zusammenfassung" (DE) / "Summary" (EN)
                        rx.cond(
                            AIState.ui_language == "de",
                            rx.text(
                                "Zusammenfassung",
                                font_weight="bold",
                                font_size="13px",
                                color=COLORS["accent_warning"],
                            ),
                            rx.text(
                                "Summary",
                                font_weight="bold",
                                font_size="13px",
                                color=COLORS["accent_warning"],
                            ),
                        ),
                        rx.text(
                            f"#{msg['summary_number']}",
                            font_weight="bold",
                            font_size="13px",
                            color=COLORS["accent_warning"],
                        ),
                        rx.text(
                            f"({msg['summary_count']} Messages)",
                            color=COLORS["text_secondary"],
                            font_size="11px",
                        ),
                        rx.spacer(),
                        rx.text(
                            msg["summary_timestamp"],
                            color=COLORS["text_secondary"],
                            font_size="10px",
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    padding_y="2",
                    padding_x="3",
                    background_color=COLORS["card_bg"],
                    border_radius="6px",
                    cursor="pointer",
                    transition="background-color 0.2s ease",
                    _hover={
                        "background_color": COLORS["primary_bg"],
                    },
                ),
                content=rx.box(
                    rx.markdown(
                        msg["summary_content"],
                        color=COLORS["text_primary"],
                        font_size="12px",
                    ),
                    padding="3",
                    background_color="rgba(255, 165, 0, 0.05)",
                    border_radius="6px",
                    border=f"1px solid {COLORS['border']}",
                    width="100%",
                    max_height="400px",
                    overflow_y="auto",
                ),
            ),
            collapsible=True,
            default_value=[],  # Collapsed by default
            variant="soft",
            width="100%",
        ),
        background_color="rgba(255, 165, 0, 0.1)",
        padding="3",
        border_radius="8px",
        border=f"1px solid {COLORS['accent_warning']}",
        width="100%",
        margin_bottom="3",
    )


def render_chat_message(msg: dict) -> rx.Component:
    """
    Rendert eine einzelne Chat-Message (User+AI, Sokrates, AIfred Refinement, Salomo, oder Summary).

    Summaries are rendered inline as collapsibles at the position where compression occurred.

    msg ist ein Dict mit:
    - user_msg: User-Nachricht
    - ai_msg: AI-Nachricht (bereinigt)
    - failed_sources: Liste der fehlgeschlagenen URLs
    - is_summary: True if this is a summary entry
    - summary_number, summary_count, summary_timestamp, summary_content: Summary details
    """
    # Check ob es eine Summary ist (inline rendering)
    is_summary = msg.get("is_summary", False)

    # Check ob es eine Sokrates-Nachricht ist (leerer User-Teil + "🏛️" am Anfang)
    is_sokrates = (msg["user_msg"] == "") & msg["ai_msg"].startswith("🏛️")

    # Check ob es eine AIfred-Refinement-Nachricht ist (leerer User-Teil + "🎩[" am Anfang)
    is_alfred_refinement = (msg["user_msg"] == "") & msg["ai_msg"].startswith("🎩[")

    # Check ob es eine Salomo-Nachricht ist (leerer User-Teil + "👑" am Anfang)
    is_salomo = (msg["user_msg"] == "") & msg["ai_msg"].startswith("👑")

    # Summaries are rendered inline via render_inline_summary()
    return rx.cond(
        is_summary,
        # Summary: Render inline collapsible at this position
        render_inline_summary(msg),
        # Not a summary: Check other message types
        rx.cond(
            is_sokrates,
            # Sokrates-Anzeige (nur AI-Teil, kein User, dezentes Kupfer/Terrakotta-Styling)
            rx.box(
                rx.hstack(
                    rx.text("🏛️", font_size="13px"),
                    rx.box(
                        # Header with Sokrates name + mode (e.g. "Sokrates (Advocatus Diaboli)")
                        rx.text(
                            rx.cond(
                                msg["sokrates_mode"] != "",
                                f"Sokrates ({msg['sokrates_mode']})",
                                "Sokrates"
                            ),
                            font_weight="bold",
                            font_size="12px",
                            color="#cd7f32",  # Bronze/Kupfer-Ton
                            margin_bottom="1",
                        ),
                        # Show sokrates_content (marker stripped) instead of ai_msg
                        rx.markdown(
                            msg["sokrates_content"],
                            color=COLORS["ai_text"],
                            font_size="13px"
                        ),
                        background_color="rgba(205, 127, 50, 0.08)",  # Dezenter Kupfer-Hintergrund
                        padding="3",
                        border_radius="6px",
                        width="100%",
                    ),
                    spacing="2",
                    align="start",
                    justify="start",
                    width="100%",
                ),
                background_color="rgba(205, 127, 50, 0.03)",  # Sehr dezenter Kupfer-Container
                padding="2",
                border_radius="8px",
                border="1px solid rgba(205, 127, 50, 0.3)",  # Dezenter Kupfer-Rand
                width="100%",
                margin_bottom="3",
            ),
            # Check if AIfred refinement message (during debate)
            rx.cond(
                is_alfred_refinement,
                # AIfred-Refinement-Anzeige (nur AI-Teil, kein User, leicht hervorgehoben)
                rx.box(
                    rx.hstack(
                        rx.text("🎩", font_size="13px"),
                        rx.box(
                            # Header with AIfred name + mode (e.g. "AIfred (Überarbeitung R2)")
                            rx.text(
                                rx.cond(
                                    msg["alfred_mode"] != "",
                                    f"AIfred ({msg['alfred_mode']})",
                                    "AIfred"
                                ),
                                font_weight="bold",
                                font_size="12px",
                                color=COLORS["primary"],
                                margin_bottom="1",
                            ),
                            # Show alfred_content (marker stripped) instead of ai_msg
                            rx.markdown(
                                msg["alfred_content"],
                                color=COLORS["ai_text"],
                                font_size="13px"
                            ),
                            background_color=COLORS["ai_msg"],
                            padding="3",
                            border_radius="6px",
                            width="100%",
                        ),
                        spacing="2",
                        align="start",
                        justify="start",
                        width="100%",
                    ),
                    background_color="rgba(255, 255, 255, 0.03)",
                    padding="2",
                    border_radius="8px",
                    width="100%",
                    margin_bottom="3",
                ),
                # Check if Salomo message (synthesis/verdict)
                rx.cond(
                    is_salomo,
                    # Salomo-Anzeige (nur AI-Teil, kein User, dezentes Gold-Styling)
                    rx.box(
                        rx.hstack(
                            rx.text("👑", font_size="13px"),
                            rx.box(
                                # Header with Salomo name + mode (e.g. "Salomo (Synthese R1)")
                                rx.text(
                                    rx.cond(
                                        msg["salomo_mode"] != "",
                                        f"Salomo ({msg['salomo_mode']})",
                                        "Salomo"
                                    ),
                                    font_weight="bold",
                                    font_size="12px",
                                    color="#daa520",  # Goldenrod
                                    margin_bottom="1",
                                ),
                                # Show salomo_content (marker stripped) instead of ai_msg
                                rx.markdown(
                                    msg["salomo_content"],
                                    color=COLORS["ai_text"],
                                    font_size="13px"
                                ),
                                background_color="rgba(218, 165, 32, 0.08)",  # Dezenter Gold-Hintergrund
                                padding="3",
                                border_radius="6px",
                                width="100%",
                            ),
                            spacing="2",
                            align="start",
                            justify="start",
                            width="100%",
                        ),
                        background_color="rgba(218, 165, 32, 0.03)",  # Sehr dezenter Gold-Container
                        padding="2",
                        border_radius="8px",
                        border="1px solid rgba(218, 165, 32, 0.3)",  # Dezenter Gold-Rand
                        width="100%",
                        margin_bottom="3",
                    ),
                    # Normale Message-Anzeige (User + AI + Failed Sources)
                    rx.vstack(
                # User message (rechts, max 70%) - mit hellgrauem Container
                rx.box(
                    rx.hstack(
                        rx.spacer(),
                        rx.box(
                            # Header mit Username (wie im HTML-Export) - weinrot wie ClearChat
                            rx.hstack(
                                rx.spacer(),
                                rx.text(
                                    rx.cond(
                                        AIState.user_name != "",
                                        AIState.user_name,
                                        "User",
                                    ),
                                    font_weight="bold",
                                    font_size="12px",
                                    color="#c06050",  # Weinrot (passend zu HTML-Export)
                                ),
                                rx.text("🙋", font_size="12px"),
                                spacing="1",
                                align="center",
                                margin_bottom="1",
                            ),
                            # Image thumbnails (if present) above the text
                            render_image_thumbnails(msg["images"]),
                            # User text
                            rx.markdown(msg["user_msg"], color=COLORS["user_text"], font_size="13px"),
                            padding="3",
                            border_radius="6px",
                            max_width="70%",
                        ),
                        spacing="2",
                        align="start",
                        justify="end",
                        width="100%",
                    ),
                    background_color=COLORS["user_msg"],
                    padding="2",
                    border_radius="8px",
                    border="1px solid rgba(255, 255, 255, 0.1)",
                    width="100%",
                ),
                # Failed Sources (wenn vorhanden) - ZWISCHEN User und AI Message
                render_failed_sources_inline(msg["failed_sources"]),
                # AI message (links, bis 100% wenn nötig) - mit hellgrauem Container
                # ONLY show if ai_msg is not empty (hides when Sokrates answers directly)
                rx.cond(
                    msg["ai_msg"] != "",
                    rx.box(
                        rx.hstack(
                            rx.text("🎩", font_size="13px"),
                            rx.box(
                                # Header with AIfred name
                                rx.text(
                                    "AIfred",
                                    font_weight="bold",
                                    font_size="12px",
                                    color=COLORS["primary"],
                                    margin_bottom="1",
                                ),
                                rx.markdown(
                                    msg["ai_msg"],
                                    color=COLORS["ai_text"],
                                    font_size="13px"
                                ),
                                background_color=COLORS["ai_msg"],
                                padding="3",
                                border_radius="6px",
                                width="100%",
                            ),
                            spacing="2",
                            align="start",
                            justify="start",
                            width="100%",
                        ),
                        background_color="rgba(255, 255, 255, 0.03)",
                        padding="2",
                        border_radius="8px",
                        border="1px solid rgba(255, 255, 255, 0.1)",
                        width="100%",
                    ),
                ),
                spacing="3",
                width="100%",
            ),
        ),  # Close is_salomo rx.cond
    ),  # Close is_alfred_refinement rx.cond
),  # Close is_sokrates rx.cond
)  # Close is_summary rx.cond


def render_sokrates_inline() -> rx.Component:
    """
    Renders Sokrates' response inline in the chat (same style as User/AI messages).
    Shows only when show_sokrates_panel is True.
    """
    return rx.cond(
        AIState.show_sokrates_panel,
        rx.vstack(
            # Sokrates message (links wie AI, aber mit anderem Styling)
            rx.box(
                rx.hstack(
                    rx.text("🏛️", font_size="13px"),
                    rx.box(
                        # Header mit Name und Badges
                        rx.hstack(
                            rx.text(
                                t("sokrates_title"),
                                font_weight="bold",
                                font_size="13px",
                                color=COLORS["accent_blue"],
                            ),
                            # Round indicator for auto_consensus
                            rx.cond(
                                AIState.multi_agent_mode == "auto_consensus",
                                rx.badge(
                                    rx.hstack(
                                        rx.text(t("debate_round_label"), font_size="9px"),
                                        rx.text(AIState.debate_round.to(str), font_weight="bold"),
                                        spacing="1",
                                    ),
                                    variant="soft",
                                    color_scheme="blue",
                                    size="1",
                                ),
                            ),
                            # LGTM badge if consensus reached
                            rx.cond(
                                AIState.sokrates_critique.contains("LGTM"),
                                rx.tooltip(
                                    rx.badge("LGTM", variant="soft", color_scheme="green", size="1"),
                                    content=t("lgtm_tooltip"),
                                ),
                            ),
                            spacing="2",
                            align="center",
                            margin_bottom="2",
                        ),
                        # Content based on mode
                        rx.cond(
                            AIState.multi_agent_mode == "devils_advocate",
                            # Devil's Advocate: Pro/Contra layout
                            rx.vstack(
                                # Pro section
                                rx.box(
                                    rx.vstack(
                                        rx.text(t("sokrates_pro_label"), font_weight="bold", font_size="11px", color="#4ade80"),
                                        rx.markdown(
                                            AIState.sokrates_pro_args,
                                            font_size="12px",
                                            component_map={
                                                "ul": lambda children: rx.el.ul(children, style={"margin_left": "16px", "list_style_type": "disc"}),
                                                "li": lambda children: rx.el.li(children, style={"margin_bottom": "4px"}),
                                            },
                                        ),
                                        spacing="1",
                                        width="100%",
                                    ),
                                    padding="10px",
                                    background_color="rgba(74, 222, 128, 0.1)",
                                    border_radius="6px",
                                    width="100%",
                                ),
                                # Contra section
                                rx.box(
                                    rx.vstack(
                                        rx.text(t("sokrates_contra_label"), font_weight="bold", font_size="11px", color="#f87171"),
                                        rx.markdown(
                                            AIState.sokrates_contra_args,
                                            font_size="12px",
                                            component_map={
                                                "ul": lambda children: rx.el.ul(children, style={"margin_left": "16px", "list_style_type": "disc"}),
                                                "li": lambda children: rx.el.li(children, style={"margin_bottom": "4px"}),
                                            },
                                        ),
                                        spacing="1",
                                        width="100%",
                                    ),
                                    padding="10px",
                                    background_color="rgba(248, 113, 113, 0.1)",
                                    border_radius="6px",
                                    width="100%",
                                ),
                                spacing="2",
                                width="100%",
                            ),
                            # Critique layout (critical_review, auto_consensus)
                            rx.markdown(
                                AIState.sokrates_critique,
                                color=COLORS["ai_text"],
                                font_size="12px",
                                component_map={
                                    "ul": lambda children: rx.el.ul(children, style={"margin_left": "16px", "list_style_type": "disc"}),
                                    "li": lambda children: rx.el.li(children, style={"margin_bottom": "4px"}),
                                },
                            ),
                        ),
                        # Sokrates-spezifischer Hintergrund (leicht blau)
                        background_color="rgba(59, 130, 246, 0.15)",
                        padding="3",
                        border_radius="6px",
                        width="100%",
                    ),
                    spacing="2",
                    align="start",
                    justify="start",
                    width="100%",
                ),
                # Äußerer Container mit leicht anderem Hintergrund
                background_color="rgba(59, 130, 246, 0.05)",
                padding="2",
                border_radius="8px",
                border="1px solid rgba(59, 130, 246, 0.2)",
                width="100%",
            ),
            spacing="3",
            width="100%",
            margin_top="3",
        ),
        rx.fragment(),  # Nichts anzeigen wenn Panel nicht aktiv
    )


def chat_history_display() -> rx.Component:
    """Full chat history (like Gradio chatbot) - Collapsible"""
    # Loading spinner während Initialisierung, Backend-Wechsel oder Bild-Upload
    loading_spinner = rx.vstack(
        rx.spinner(size="3", color="orange"),
        rx.cond(
            AIState.is_uploading_image,
            rx.text(
                rx.cond(
                    AIState.ui_language == "de",
                    "Bild wird hochgeladen...",
                    "Uploading image...",
                ),
                font_size="14px",
                color=COLORS["text_secondary"],
                margin_top="3",
            ),
            rx.cond(
                AIState.backend_initializing,
                rx.text(
                    "AIfred wird initialisiert...",
                    font_size="14px",
                    color=COLORS["text_secondary"],
                    margin_top="3",
                ),
                rx.cond(
                    AIState.vllm_restarting,
                    rx.text(
                        "vLLM wird neu gestartet...",
                        font_size="14px",
                        color=COLORS["text_secondary"],
                        margin_top="3",
                    ),
                    rx.cond(
                        AIState.is_koboldcpp_auto_restarting,
                        rx.text(
                            "KoboldCPP startet neu (nach Inaktivität)...",
                            font_size="14px",
                            color=COLORS["text_secondary"],
                            margin_top="3",
                        ),
                        rx.text(
                            "Backend wird gewechselt...",
                            font_size="14px",
                            color=COLORS["text_secondary"],
                            margin_top="3",
                        ),
                    ),
                ),
            ),
        ),
        rx.cond(
            AIState.is_uploading_image,
            rx.fragment(),  # No subtitle for image upload
            rx.text(
                "Bitte warten, Backend startet (~40-70 Sekunden)",
                font_size="11px",
                color=COLORS["text_muted"],
                font_style="italic",
                margin_top="1",
            ),
        ),
        align="center",
        justify="center",
        width="100%",
        min_height="360px",
        padding="4",
        background_color=COLORS["readonly_bg"],
        border_radius="8px",
        border=f"1px solid {COLORS['border']}",
    )

    # Chat History Box - JavaScript-basiertes Autoscroll (nicht rx.auto_scroll)
    # rx.auto_scroll ignoriert den Toggle während der Inferenz, daher JavaScript-Lösung
    chat_history_box = rx.box(
        rx.vstack(
            # All chat messages including inline summaries
            rx.foreach(
                AIState.chat_history_parsed,
                render_chat_message
            ),
            spacing="3",
            width="100%",
        ),
        id="chat-history-box",
        width="100%",
        min_height="360px",
        max_height="2400px",
        overflow_y="auto",
        padding="4",
        background_color=COLORS["readonly_bg"],
        border_radius="8px",
        border=f"1px solid {COLORS['border']}",
        style={
            "transition": "all 0.4s ease-out",
        },
    )

    chat_content = rx.cond(
        AIState.backend_initializing | AIState.backend_switching | AIState.vllm_restarting | AIState.is_koboldcpp_auto_restarting | AIState.is_uploading_image,
        loading_spinner,  # Show spinner during initialization, backend switch, vLLM restart, KoboldCPP auto-restart, or image upload
        chat_history_box,
    )
    
    return rx.accordion.root(
        rx.accordion.item(
            value="chat_history",  # Eindeutige ID für das Accordion Item
            header=rx.box(
                rx.hstack(
                    rx.text(
                        rx.cond(
                            AIState.ui_language == "de",
                            "💬 Chat Verlauf",
                            "💬 Chat History"
                        ),
                        font_size="14px",
                        font_weight="500",
                        color=COLORS["text_primary"]
                    ),
                    rx.badge(
                        rx.cond(
                            AIState.ui_language == "de",
                            f"{AIState.chat_history.length()} messages",
                            f"{AIState.chat_history.length()} messages"
                        ),
                        color_scheme="orange",
                        size="1",
                    ),
                    spacing="3",
                    align="center",
                ),
                padding_y="2",  # Kompakter Header
                background_color=COLORS["card_bg"],  # Dunkles Grau
                _hover={
                    "background_color": COLORS["primary_bg"],  # Orange beim Hover (15% Opacity)
                },
                border_radius="6px",
                padding_x="3",
                cursor="pointer",
                transition="background-color 0.2s ease",
            ),
            content=chat_content,
        ),
        default_value="chat_history",  # Standardmäßig GEÖFFNET
        collapsible=True,
        width="100%",
        variant="soft",  # Soft statt ghost für besseres Styling
        color_scheme="gray",  # Grau statt Blau
    )


# NOTE: Legacy failed_sources_display() removed - failed sources are now rendered
# inline within each chat message via render_failed_sources_inline()


def sokrates_panel() -> rx.Component:
    """Sokrates live streaming panel - shown only during active debate"""
    return rx.cond(
        AIState.debate_in_progress,  # Only show during live streaming
        rx.box(
            rx.vstack(
                # Header with Sokrates icon (Kupfer-Styling)
                rx.hstack(
                    rx.text("🏛️", font_size="16px"),
                    rx.text(
                        "Sokrates",
                        font_weight="bold",
                        font_size="13px",
                        color="#cd7f32",  # Kupfer/Bronze
                    ),
                    rx.text(
                        "(live)",
                        font_size="11px",
                        color="rgba(205, 127, 50, 0.6)",
                        font_style="italic",
                    ),
                    # Show round indicator for auto_consensus
                    rx.cond(
                        AIState.multi_agent_mode == "auto_consensus",
                        rx.badge(
                            rx.hstack(
                                rx.text(t("debate_round_label"), font_size="10px"),
                                rx.text(AIState.debate_round.to(str), font_weight="bold"),
                                spacing="1",
                            ),
                            variant="soft",
                            color_scheme="orange",
                        ),
                    ),
                    # Show LGTM badge if consensus reached
                    rx.cond(
                        AIState.sokrates_critique.contains("LGTM"),
                        rx.badge("LGTM", variant="soft", color_scheme="green"),
                    ),
                    spacing="2",
                    align="center",
                    width="100%",
                ),

                # Content based on mode
                rx.cond(
                    AIState.multi_agent_mode == "devils_advocate",
                    # Devil's Advocate: Pro/Contra layout
                    rx.vstack(
                        # Pro section
                        rx.box(
                            rx.vstack(
                                rx.text(t("sokrates_pro_label"), font_weight="bold", font_size="12px", color="#4ade80"),
                                rx.markdown(
                                    AIState.sokrates_pro_args,
                                    component_map={
                                        "ul": lambda children: rx.el.ul(children, style={"margin_left": "16px", "list_style_type": "disc"}),
                                        "li": lambda children: rx.el.li(children, style={"margin_bottom": "4px"}),
                                    },
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            padding="12px",
                            background_color="rgba(74, 222, 128, 0.1)",
                            border_radius="8px",
                            width="100%",
                        ),
                        # Contra section
                        rx.box(
                            rx.vstack(
                                rx.text(t("sokrates_contra_label"), font_weight="bold", font_size="12px", color="#f87171"),
                                rx.markdown(
                                    AIState.sokrates_contra_args,
                                    component_map={
                                        "ul": lambda children: rx.el.ul(children, style={"margin_left": "16px", "list_style_type": "disc"}),
                                        "li": lambda children: rx.el.li(children, style={"margin_bottom": "4px"}),
                                    },
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            padding="12px",
                            background_color="rgba(248, 113, 113, 0.1)",
                            border_radius="8px",
                            width="100%",
                        ),
                        spacing="3",
                        width="100%",
                    ),
                    # Critique layout (critical_review, auto_consensus) - Kupfer-Styling
                    rx.box(
                        rx.markdown(
                            AIState.sokrates_critique,
                            component_map={
                                "ul": lambda children: rx.el.ul(children, style={"margin_left": "16px", "list_style_type": "disc"}),
                                "li": lambda children: rx.el.li(children, style={"margin_bottom": "4px"}),
                            },
                            font_size="13px",
                        ),
                        padding="8px",
                        background_color="rgba(205, 127, 50, 0.08)",  # Kupfer-Hintergrund
                        border_radius="6px",
                        width="100%",
                    ),
                ),

                spacing="2",
                width="100%",
            ),
            padding="8px",
            background_color="rgba(205, 127, 50, 0.03)",  # Dezenter Kupfer-Container
            border_radius="8px",
            border="1px solid rgba(205, 127, 50, 0.3)",  # Kupfer-Rand
            width="100%",
            margin_top="4px",
        ),
    )


def right_column() -> rx.Component:
    """Right column removed completely"""
    # This function is now empty as the right column is completely removed
    return rx.vstack(
        spacing="4",
        width="100%",
    )


# ============================================================
# DEBUG CONSOLE (Bottom of Page)
# ============================================================

def debug_console() -> rx.Component:
    """Debug console with logs (25 lines like Gradio) - Matrix Terminal Style"""
    
    # JavaScript-based autoscroll (custom.js) instead of rx.auto_scroll()
    # rx.auto_scroll() breaks during fast State updates (Intent Detection, LLM generation)
    # Using single rx.box ensures scroll position is preserved when toggle is disabled
    debug_content = rx.box(
        rx.foreach(
            AIState.debug_messages,
            lambda msg: rx.text(
                msg,
                font_family="monospace",
                font_size="11px",
                color=COLORS["debug_text"],  # Matrix Grün
                white_space="pre",
            ),
        ),
        id="debug-console-box",
        width="100%",
        min_height="500px",  # Minimum height - CSS Grid stretch handles actual height
        overflow_y="auto",
        padding="3",
        background_color=COLORS["debug_bg"],
        border_radius="8px",
        border=f"2px solid {COLORS['debug_border']}",
        style={
            "scroll-behavior": "smooth",
        },
    )

    # Periodic refresh timer for background task state propagation
    # Without this, messages from background tasks (InactivityMonitor) won't appear in UI
    refresh_timer = rx.moment(
        interval=1000,  # 1 second - necessary for background task → UI propagation
        on_change=AIState.refresh_debug_console,
        display="none",
    )

    return rx.accordion.root(
        rx.accordion.item(
            value="debug",  # Eindeutige ID für das Accordion Item
            header=rx.box(
                rx.hstack(
                    rx.text(
                        rx.cond(
                            AIState.ui_language == "de",
                            "🐛 Debug Console",
                            "🐛 Debug Console"
                        ),
                        font_size="12px",
                        font_weight="500",
                        color=COLORS["debug_accent"]
                    ),
                    rx.badge(
                        f"{AIState.debug_messages.length()} messages",
                        color_scheme="green",
                        size="1",
                    ),
                    spacing="3",
                    align="center",
                ),
                padding_y="2",  # Kompakter Header
            ),
            content=rx.vstack(
                rx.hstack(
                    rx.text(
                        rx.cond(
                            AIState.ui_language == "de",
                            "Live Debug-Output: LLM-Starts, Entscheidungen, Statistiken",
                            "Live Debug Output: LLM starts, decisions, statistics"
                        ),
                        font_size="12px",
                        color=COLORS["text_secondary"]
                    ),
                    rx.spacer(),
                    rx.switch(
                        checked=AIState.auto_refresh_enabled,
                        on_change=AIState.toggle_auto_refresh,
                        color_scheme="orange",
                        high_contrast=True,
                        id="autoscroll-switch",
                    ),
                    rx.text(
                        rx.cond(
                            AIState.ui_language == "de",
                            "Auto-Scroll",
                            "Auto-Scroll"
                        ),
                        font_size="12px",
                        color=COLORS["text_secondary"]
                    ),
                    spacing="3",
                    align="center",
                    width="100%",
                ),
                debug_content,
                refresh_timer,  # Hidden timer for background task state propagation
                spacing="3",
                width="100%",
            ),
        ),
        collapsible=True,  # WICHTIG: Macht Accordion schließbar!
        default_value="debug",  # Standardmäßig geöffnet
        color_scheme="gray",
        variant="soft",
    )


# ============================================================
# SETTINGS ACCORDION (Bottom Settings)
# ============================================================

def settings_accordion() -> rx.Component:
    """Settings accordion at bottom - Kompakt"""
    return rx.accordion.root(
        rx.accordion.item(
            value="settings",  # Eindeutige ID für das Accordion Item
            header=rx.box(
                rx.text(t("settings"), font_size="12px", font_weight="500", color=COLORS["text_primary"]),
                padding_y="2",  # Kompakter Header
            ),
            content=rx.vstack(
                # UI Language + User Name Row
                rx.hstack(
                    # UI Language Selection
                    rx.hstack(
                        rx.text(t("ui_language"), font_weight="bold", font_size="12px"),
                        rx.cond(
                            AIState.is_mobile,
                            # MOBILE: Native HTML <select>
                            native_select_tts(
                                AIState.ui_language,
                                AIState.set_ui_language,
                                ["de", "en"],
                            ),
                            # DESKTOP: Radix UI Select
                            rx.select(
                                ["de", "en"],
                                value=AIState.ui_language,
                                on_change=AIState.set_ui_language,
                                size="2",
                            ),
                        ),
                        spacing="2",
                        align="center",
                    ),
                    # User Name Input + Gender Toggle (Subtle Orange style)
                    rx.box(
                        rx.icon("user", size=16, color="#B8860B"),
                        rx.input(
                            placeholder=t("your_name"),
                            value=AIState.user_name,
                            on_change=AIState.set_user_name,
                            on_blur=AIState.save_user_name,
                            size="2",
                            width="100px",
                            class_name="username-input-subtle",
                        ),
                        # Gender Toggle (♂/♀)
                        rx.segmented_control.root(
                            rx.segmented_control.item("♂", value="male"),
                            rx.segmented_control.item("♀", value="female"),
                            value=AIState.user_gender,
                            on_change=AIState.set_user_gender,
                            size="1",
                        ),
                        display="flex",
                        align_items="center",
                        gap="6px",
                        background_color="rgba(204, 136, 0, 0.15)",
                        border_radius="8px",
                        padding_left="8px",
                        padding_right="4px",
                        padding_y="4px",
                    ),
                    spacing="4",
                    align="center",
                    width="100%",
                ),

                # Backend Selection - Mobile: Native select, Desktop: Radix UI
                rx.hstack(
                    rx.text(t("backend"), font_weight="bold", font_size="12px"),
                    # Conditional rendering: Native select for mobile, Radix UI for desktop
                    rx.cond(
                        AIState.is_mobile,
                        # MOBILE: Native HTML <select>
                        native_select_backend(
                            AIState.current_backend_label,
                            AIState.switch_backend_by_label,
                            AIState.backend_switching,
                            AIState.available_backends_list,
                        ),
                        # DESKTOP: Radix UI Select with grouped headers
                        rx.select.root(
                            rx.select.trigger(),
                            rx.select.content(
                                # Universal Compatibility Header
                                rx.select.item(
                                    "─── Universelle Kompatibilität (GGUF) ───",
                                    value="header_universal",
                                    disabled=True,
                                    font_weight="bold",
                                    color="blue",
                                ),
                                # P40-compatible backends
                                rx.cond(
                                    AIState.available_backends.contains("ollama"),
                                    rx.select.item("Ollama", value="ollama"),
                                ),
                                rx.cond(
                                    AIState.available_backends.contains("koboldcpp"),
                                    rx.select.item("KoboldCPP", value="koboldcpp"),
                                ),
                                # Separator
                                rx.select.item(
                                    "─────────────────────────────────",
                                    value="separator",
                                    disabled=True,
                                    color="gray",
                                ),
                                # Modern GPUs Header
                                rx.select.item(
                                    "─── Moderne GPUs (FP16) ───",
                                    value="header_modern",
                                    disabled=True,
                                    font_weight="bold",
                                    color="blue",
                                ),
                                # Modern backends
                                rx.cond(
                                    AIState.available_backends.contains("tabbyapi"),
                                    rx.select.item("TabbyAPI", value="tabbyapi"),
                                ),
                                rx.cond(
                                    AIState.available_backends.contains("vllm"),
                                    rx.select.item("vLLM", value="vllm"),
                                ),
                                # Separator before Cloud APIs
                                rx.select.item(
                                    "─────────────────────────────────",
                                    value="separator2",
                                    disabled=True,
                                    color="gray",
                                ),
                                # Cloud APIs Header
                                rx.select.item(
                                    "─── Cloud APIs ───",
                                    value="header_cloud",
                                    disabled=True,
                                    font_weight="bold",
                                    color="purple",
                                ),
                                # Cloud API Backend (always available)
                                rx.select.item("☁️ Cloud APIs", value="cloud_api"),
                            ),
                            value=AIState.backend_type,
                            on_change=AIState.switch_backend,
                            size="2",
                            disabled=AIState.backend_switching,
                        ),
                    ),

                    # Backend Switching Status Badge
                    rx.cond(
                        AIState.backend_switching,
                        rx.hstack(
                            rx.spinner(size="1", color="orange"),
                            rx.badge(
                                rx.cond(
                                    AIState.ui_language == "de",
                                    "Wechsle...",
                                    "Switching...",
                                ),
                                color_scheme="orange"
                            ),
                            spacing="2",
                            align="center",
                        ),
                    ),

                    # GPU Details Collapsible (next to Backend dropdown)
                    rx.cond(
                        AIState.gpu_detected,
                        rx.accordion.root(
                            rx.accordion.item(
                                value="gpu-details",
                                header=rx.box(
                                    rx.text(
                                        rx.cond(
                                            AIState.ui_language == "de",
                                            "🖥️ GPU-Details",
                                            "🖥️ GPU Details"
                                        ),
                                        font_size="11px",
                                        font_weight="500",
                                        color="#2a9d8f",
                                    ),
                                    padding_y="2",
                                ),
                                content=rx.vstack(
                                    # GPU Hardware Info
                                    rx.text(
                                        f"🎮 {AIState.gpu_display_text}",
                                        font_size="10px",
                                        color="#2a9d8f",
                                    ),
                                    # Backend Compatibility (only if Compute < 7.0)
                                    rx.cond(
                                        AIState.gpu_compute_cap < 7.0,
                                        rx.box(
                                            rx.text(
                                                rx.cond(
                                                    AIState.ui_language == "de",
                                                    "vLLM & TabbyAPI benötigen Compute 7.0+",
                                                    "vLLM & TabbyAPI require Compute 7.0+"
                                                ),
                                                font_size="10px",
                                                color="#666",
                                            ),
                                            rx.text(
                                                rx.cond(
                                                    AIState.ui_language == "de",
                                                    "Verfügbar: Ollama, KoboldCPP",
                                                    "Available: Ollama, KoboldCPP"
                                                ),
                                                font_size="10px",
                                                color="#666",
                                                margin_top="2px",
                                            ),
                                            rx.text(
                                                rx.cond(
                                                    AIState.ui_language == "de",
                                                    "💡 Ollama nutzt INT8/Q4 - optimal für ältere GPUs",
                                                    "💡 Ollama uses INT8/Q4 - optimal for older GPUs"
                                                ),
                                                font_size="10px",
                                                color="#2a9d8f",
                                                margin_top="4px",
                                                font_style="italic",
                                            ),
                                            margin_top="4px",
                                        ),
                                    ),
                                    spacing="1",
                                    width="100%",
                                    align_items="start",
                                ),
                            ),
                            collapsible=True,
                            color_scheme="gray",
                            variant="ghost",
                        ),
                    ),

                    spacing="3",
                    align="center",
                ),

                # Single Model Warning (for backends that can't switch models)
                rx.cond(
                    ~AIState.backend_supports_dynamic_models,
                    rx.text(
                        rx.cond(
                            AIState.ui_language == "de",
                            f"ℹ️ {AIState.backend_type.upper()} kann nur EIN Modell gleichzeitig laden (Haupt- und Automatik-LLM nutzen dasselbe Modell)",
                            f"ℹ️ {AIState.backend_type.upper()} can only load ONE model at a time (Main and Automatik LLM use the same model)"
                        ),
                        font_size="11px",
                        color="#d4913d",  # Dunkles Orange - gut lesbar
                        line_height="1.5",
                        margin_top="8px",
                    ),
                ),

                # Context Calibration Row (only for Ollama, between Backend and Model selection)
                rx.cond(
                    AIState.backend_id == "ollama",
                    rx.hstack(
                        rx.button(
                            rx.cond(
                                AIState.is_calibrating,
                                rx.hstack(
                                    rx.spinner(size="1"),
                                    rx.text(t("calibrating"), font_size="11px"),
                                    spacing="2",
                                    align="center",
                                ),
                                rx.hstack(
                                    rx.icon("gauge", size=14),
                                    rx.text(t("calibrate_context"), font_size="11px"),
                                    spacing="2",
                                    align="center",
                                ),
                            ),
                            on_click=AIState.calibrate_context,
                            disabled=AIState.is_calibrating | AIState.backend_switching,
                            size="1",
                            variant="outline",
                            color_scheme="orange",
                        ),
                        spacing="2",
                        align="center",
                    ),
                ),

                # Cloud API Provider Selection (only visible for cloud_api backend)
                rx.cond(
                    AIState.backend_type == "cloud_api",
                    rx.hstack(
                        rx.text(t("cloud_api_provider"), font_weight="bold", font_size="12px"),
                        rx.select(
                            ["Claude (Anthropic)", "Qwen (DashScope)", "DeepSeek", "Kimi (Moonshot)"],
                            value=AIState.cloud_api_provider_label,
                            on_change=AIState.set_cloud_api_provider_by_label,
                            size="2",
                        ),
                        # API Key Status Badge
                        rx.cond(
                            AIState.cloud_api_key_configured,
                            rx.badge(t("cloud_api_key_configured"), color_scheme="green", size="1"),
                            rx.badge(t("cloud_api_key_missing"), color_scheme="red", size="1"),
                        ),
                        spacing="3",
                        align="center",
                        width="100%",
                    ),
                ),

                # AIfred-LLM Selection
                rx.hstack(
                    rx.text(t("main_llm"), font_weight="bold", font_size="12px"),
                    rx.cond(
                        AIState.is_mobile,
                        # MOBILE: Native HTML <select> (simple list)
                        native_select_model(
                            AIState.aifred_model,  # Display name with size
                            AIState.set_aifred_model,  # Original handler
                            AIState.backend_switching,
                            AIState.available_models,  # Simple list of display names
                        ),
                        # DESKTOP: Radix UI Select
                        rx.select(
                            AIState.available_models,
                            value=AIState.aifred_model,
                            on_change=AIState.set_aifred_model,
                            size="2",
                            position="popper",  # Better mobile positioning (adapts to viewport)
                            disabled=AIState.backend_switching,  # Disable during backend switch
                        ),
                    ),
                    spacing="3",
                    align="center",
                ),

                # AIfred RoPE Scaling - Only visible for Ollama
                rx.cond(
                    AIState.backend_id == "ollama",
                    rx.hstack(
                        rx.text("  └─ RoPE:", font_size="10px", color="gray"),
                        rx.select.root(
                            rx.select.trigger(placeholder=AIState.rope_factor_display),
                            rx.select.content(
                                rx.select.item("1.0x", value="1.0x"),
                                rx.select.item("1.5x", value="1.5x"),
                                rx.select.item("2.0x", value="2.0x"),
                            ),
                            value=AIState.rope_factor_display,
                            on_change=AIState.set_aifred_rope_factor,
                            size="1",
                        ),
                        # 🎩 AIfred Personality Toggle
                        rx.cond(
                            AIState.ui_language == "de",
                            rx.tooltip(
                                rx.hstack(
                                    rx.text("🎩", font_size="14px"),
                                    rx.checkbox(
                                        checked=AIState.aifred_personality,
                                        on_change=lambda _: AIState.toggle_aifred_personality(),
                                        size="1",
                                        color_scheme="orange",
                                        variant="classic",
                                    ),
                                    spacing="1",
                                    align="center",
                                ),
                                content="Butler-Persönlichkeit: Britisch-höflicher Sprachstil",
                            ),
                            rx.tooltip(
                                rx.hstack(
                                    rx.text("🎩", font_size="14px"),
                                    rx.checkbox(
                                        checked=AIState.aifred_personality,
                                        on_change=lambda _: AIState.toggle_aifred_personality(),
                                        size="1",
                                        color_scheme="orange",
                                        variant="classic",
                                    ),
                                    spacing="1",
                                    align="center",
                                ),
                                content="Butler personality: Polite British speech style",
                            ),
                        ),
                        spacing="2",
                        align="center",
                    ),
                ),

                # Sokrates LLM Selection - Only visible when multi-agent mode is not "standard"
                rx.cond(
                    (AIState.multi_agent_mode != "standard") & AIState.backend_supports_dynamic_models,
                    rx.hstack(
                        rx.text(
                            t("sokrates_llm"),
                            font_weight="bold",
                            font_size="12px",
                        ),
                        rx.cond(
                            AIState.is_mobile,
                            # MOBILE: Native HTML <select> (simple list)
                            native_select_model(
                                rx.cond(
                                    AIState.sokrates_model == "",
                                    t("sokrates_llm_same"),
                                    AIState.sokrates_model
                                ),
                                AIState.set_sokrates_model,
                                AIState.backend_switching,
                                AIState.available_models,  # Use same list as main model
                            ),
                            # DESKTOP: Radix UI Select with placeholder for "same as main"
                            rx.select(
                                AIState.available_models,
                                value=AIState.sokrates_model,
                                on_change=AIState.set_sokrates_model,
                                size="2",
                                position="popper",
                                disabled=AIState.backend_switching,
                                placeholder=t("sokrates_llm_same"),
                            ),
                        ),
                        spacing="3",
                        align="center",
                    ),
                ),

                # Sokrates RoPE Scaling - Only visible for Ollama and multi-agent mode != standard
                rx.cond(
                    (AIState.backend_id == "ollama") & (AIState.multi_agent_mode != "standard") & AIState.backend_supports_dynamic_models,
                    rx.hstack(
                        rx.text("  └─ RoPE:", font_size="10px", color="gray"),
                        rx.select.root(
                            rx.select.trigger(placeholder=AIState.sokrates_rope_display),
                            rx.select.content(
                                rx.select.item("1.0x", value="1.0x"),
                                rx.select.item("1.5x", value="1.5x"),
                                rx.select.item("2.0x", value="2.0x"),
                            ),
                            value=AIState.sokrates_rope_display,
                            on_change=AIState.set_sokrates_rope_factor,
                            size="1",
                        ),
                        # 🏛️ Sokrates Personality Toggle
                        rx.cond(
                            AIState.ui_language == "de",
                            rx.tooltip(
                                rx.hstack(
                                    rx.text("🏛️", font_size="14px"),
                                    rx.checkbox(
                                        checked=AIState.sokrates_personality,
                                        on_change=lambda _: AIState.toggle_sokrates_personality(),
                                        size="1",
                                        color_scheme="orange",
                                        variant="classic",
                                    ),
                                    spacing="1",
                                    align="center",
                                ),
                                content="Philosophen-Persönlichkeit: Sokratische Methode mit rhetorischen Fragen",
                            ),
                            rx.tooltip(
                                rx.hstack(
                                    rx.text("🏛️", font_size="14px"),
                                    rx.checkbox(
                                        checked=AIState.sokrates_personality,
                                        on_change=lambda _: AIState.toggle_sokrates_personality(),
                                        size="1",
                                        color_scheme="orange",
                                        variant="classic",
                                    ),
                                    spacing="1",
                                    align="center",
                                ),
                                content="Philosopher personality: Socratic method with rhetorical questions",
                            ),
                        ),
                        spacing="2",
                        align="center",
                    ),
                ),

                # Salomo LLM Selection - Only visible for auto_consensus or tribunal modes
                rx.cond(
                    ((AIState.multi_agent_mode == "auto_consensus") | (AIState.multi_agent_mode == "tribunal")) & AIState.backend_supports_dynamic_models,
                    rx.hstack(
                        rx.text(
                            t("salomo_llm"),
                            font_weight="bold",
                            font_size="12px",
                        ),
                        rx.cond(
                            AIState.is_mobile,
                            # MOBILE: Native HTML <select> (simple list)
                            native_select_model(
                                rx.cond(
                                    AIState.salomo_model == "",
                                    t("sokrates_llm_same"),  # Same placeholder as Sokrates
                                    AIState.salomo_model
                                ),
                                AIState.set_salomo_model,
                                AIState.backend_switching,
                                AIState.available_models,
                            ),
                            # DESKTOP: Radix UI Select with placeholder for "same as main"
                            rx.select(
                                AIState.available_models,
                                value=AIState.salomo_model,
                                on_change=AIState.set_salomo_model,
                                size="2",
                                position="popper",
                                disabled=AIState.backend_switching,
                                placeholder=t("sokrates_llm_same"),  # Same placeholder as Sokrates
                            ),
                        ),
                        spacing="3",
                        align="center",
                    ),
                ),

                # Salomo RoPE Scaling - Only visible for Ollama and auto_consensus/tribunal modes
                rx.cond(
                    (AIState.backend_id == "ollama") & ((AIState.multi_agent_mode == "auto_consensus") | (AIState.multi_agent_mode == "tribunal")) & AIState.backend_supports_dynamic_models,
                    rx.hstack(
                        rx.text("  └─ RoPE:", font_size="10px", color="gray"),
                        rx.select.root(
                            rx.select.trigger(placeholder=AIState.salomo_rope_display),
                            rx.select.content(
                                rx.select.item("1.0x", value="1.0x"),
                                rx.select.item("1.5x", value="1.5x"),
                                rx.select.item("2.0x", value="2.0x"),
                            ),
                            value=AIState.salomo_rope_display,
                            on_change=AIState.set_salomo_rope_factor,
                            size="1",
                        ),
                        # 👑 Salomo Personality Toggle
                        rx.cond(
                            AIState.ui_language == "de",
                            rx.tooltip(
                                rx.hstack(
                                    rx.text("👑", font_size="14px"),
                                    rx.checkbox(
                                        checked=AIState.salomo_personality,
                                        on_change=lambda _: AIState.toggle_salomo_personality(),
                                        size="1",
                                        color_scheme="orange",
                                        variant="classic",
                                    ),
                                    spacing="1",
                                    align="center",
                                ),
                                content="König-Persönlichkeit: Weiser Richterstil mit hebräischen Weisheiten",
                            ),
                            rx.tooltip(
                                rx.hstack(
                                    rx.text("👑", font_size="14px"),
                                    rx.checkbox(
                                        checked=AIState.salomo_personality,
                                        on_change=lambda _: AIState.toggle_salomo_personality(),
                                        size="1",
                                        color_scheme="orange",
                                        variant="classic",
                                    ),
                                    spacing="1",
                                    align="center",
                                ),
                                content="King personality: Wise arbiter style with Hebrew proverbs",
                            ),
                        ),
                        spacing="2",
                        align="center",
                    ),
                ),

                # Automatik LLM Selection - Hidden for KoboldCPP (single model only)
                rx.cond(
                    AIState.backend_supports_dynamic_models,
                    rx.hstack(
                        rx.text(
                            t("automatic_llm"),
                            font_weight="bold",
                            font_size="12px",
                        ),
                        rx.cond(
                            AIState.is_mobile,
                            # MOBILE: Native HTML <select> (simple list)
                            native_select_model(
                                AIState.automatik_model,  # Display name with size
                                AIState.set_automatik_model,  # Original handler
                                AIState.backend_switching,
                                AIState.available_models,  # Simple list of display names
                            ),
                            # DESKTOP: Radix UI Select
                            rx.select(
                                AIState.available_models,
                                value=AIState.automatik_model,
                                on_change=AIState.set_automatik_model,
                                size="2",
                                position="popper",  # Better mobile positioning (adapts to viewport)
                                disabled=AIState.backend_switching,  # Disable during backend switch
                            ),
                        ),
                        spacing="3",
                        align="center",
                    ),
                ),

                # Automatik RoPE Scaling - Only visible for Ollama
                rx.cond(
                    (AIState.backend_id == "ollama") & AIState.backend_supports_dynamic_models,
                    rx.hstack(
                        rx.text("  └─ RoPE:", font_size="10px", color="gray"),
                        rx.select.root(
                            rx.select.trigger(placeholder=AIState.automatik_rope_display),
                            rx.select.content(
                                rx.select.item("1.0x", value="1.0x"),
                                rx.select.item("1.5x", value="1.5x"),
                                rx.select.item("2.0x", value="2.0x"),
                            ),
                            value=AIState.automatik_rope_display,
                            on_change=AIState.set_automatik_rope_factor,
                            size="1",
                        ),
                        spacing="2",
                        align="center",
                    ),
                ),

                # Vision LLM Selection - Hidden for KoboldCPP (single model only)
                rx.cond(
                    AIState.backend_supports_dynamic_models,
                    rx.hstack(
                        rx.text(
                            t("vision_llm"),
                            font_weight="bold",
                            font_size="12px",
                        ),
                        rx.cond(
                            AIState.is_mobile,
                            # MOBILE: Native HTML <select> (simple list)
                            native_select_model(
                                AIState.vision_model,  # Display name with size
                                AIState.set_vision_model,  # Original handler
                                AIState.backend_switching,
                                AIState.available_vision_models_list,  # Vision models list (state var, not computed)
                            ),
                            # DESKTOP: Radix UI Select
                            rx.select(
                                AIState.available_vision_models_list,  # State var instead of computed property
                                value=AIState.vision_model,
                                on_change=AIState.set_vision_model,
                                size="2",
                                position="popper",  # Better mobile positioning (adapts to viewport)
                                disabled=AIState.backend_switching,  # Disable during backend switch
                                placeholder="Select vision model..."
                            ),
                        ),
                        spacing="3",
                        align="center",
                    ),
                ),

                # Vision RoPE Scaling - Only visible for Ollama
                rx.cond(
                    (AIState.backend_id == "ollama") & AIState.backend_supports_dynamic_models,
                    rx.hstack(
                        rx.text("  └─ RoPE:", font_size="10px", color="gray"),
                        rx.select.root(
                            rx.select.trigger(placeholder=AIState.vision_rope_display),
                            rx.select.content(
                                rx.select.item("1.0x", value="1.0x"),
                                rx.select.item("1.5x", value="1.5x"),
                                rx.select.item("2.0x", value="2.0x"),
                            ),
                            value=AIState.vision_rope_display,
                            on_change=AIState.set_vision_rope_factor,
                            size="1",
                        ),
                        spacing="2",
                        align="center",
                    ),
                ),

                # Thinking Mode Toggle (für alle Modelle sichtbar)
                rx.divider(margin_top="12px", margin_bottom="12px"),
                rx.vstack(
                    rx.hstack(
                        rx.text(t("thinking_mode_label"), font_weight="bold", font_size="12px"),
                        rx.switch(
                            checked=AIState.enable_thinking,
                            on_change=AIState.toggle_thinking_mode,
                            size="1",
                        ),
                        rx.text(
                            rx.cond(
                                AIState.enable_thinking,
                                "ON",
                                "OFF"
                            ),
                            font_size="11px",
                            color=rx.cond(
                                AIState.enable_thinking,
                                "#4CAF50",
                                "#999"
                            ),
                        ),
                        spacing="2",
                        align="center",
                    ),
                    rx.text(
                        t("thinking_mode_info"),
                        font_size="10px",
                        color="#999",
                        line_height="1.3",
                    ),
                    spacing="2",
                    width="100%",
                ),
                # Pulsierende Warnung unterhalb der Erklärung (nur sichtbar wenn thinking_mode_warning gesetzt)
                rx.cond(
                    AIState.thinking_mode_warning != "",
                    rx.box(
                        rx.text(
                            t("thinking_mode_unavailable") + " " + AIState.thinking_mode_warning,
                            font_size="11px",
                            font_weight="bold",
                            color="#ff9800",
                        ),
                        padding="6px 10px",
                        border_radius="4px",
                        background_color="rgba(255, 152, 0, 0.15)",
                        border="2px solid rgba(255, 152, 0, 0.5)",
                        class_name="thinking-warning-pulse",
                        margin_top="3px",
                        margin_bottom="-12px",
                    ),
                ),

                # vLLM YaRN Context Extension (nur sichtbar bei vLLM)
                rx.cond(
                    AIState.backend_type == "vllm",
                    rx.vstack(
                        rx.divider(margin="0px 0px 12px 0px"),
                        rx.hstack(
                            rx.text(t("yarn_heading"), font_weight="bold", font_size="12px"),
                            rx.switch(
                                checked=AIState.enable_yarn,
                                on_change=AIState.toggle_yarn,
                                size="1",
                            ),
                            rx.text(
                                rx.cond(
                                    AIState.enable_yarn,
                                    f"ON ({AIState.yarn_factor}x)",
                                    "OFF"
                                ),
                                font_size="11px",
                                color=rx.cond(
                                    AIState.enable_yarn,
                                    "#4CAF50",
                                    "#999"
                                ),
                            ),
                            spacing="2",
                            align="center",
                        ),
                        rx.cond(
                            AIState.enable_yarn,
                            rx.vstack(
                                rx.hstack(
                                    rx.text(t("yarn_factor_label"), font_size="11px", font_weight="500"),
                                    rx.input(
                                        value=AIState.yarn_factor_input,
                                        on_change=AIState.set_yarn_factor_input,
                                        type="number",
                                        step="0.1",
                                        min="1.0",
                                        max="8.0",  # No hard limit - let user experiment
                                        size="1",
                                        width="80px",
                                    ),
                                    rx.text(
                                        rx.cond(
                                            AIState.vllm_max_tokens > 0,
                                            f"(~{(AIState.vllm_max_tokens * AIState.yarn_factor).to(int)} tokens)",
                                            t("yarn_autodetect_hint")
                                        ),
                                        font_size="10px",
                                        color="#999",
                                    ),
                                    rx.button(
                                        t("yarn_apply_button"),
                                        on_click=AIState.apply_yarn_factor,
                                        size="1",
                                        variant="soft",
                                        color_scheme="blue",
                                    ),
                                    spacing="2",
                                    align="center",
                                ),
                                # Show maximum YaRN factor info (dynamic based on testing)
                                rx.cond(
                                    AIState.yarn_max_tested,
                                    # Maximum was tested (from VRAM crash)
                                    rx.text(
                                        "📏 Maximum: ~" + AIState.yarn_max_factor.to(str) + "x",
                                        font_size="10px",
                                        color="#ff9800",  # Orange for better visibility
                                        font_weight="500",
                                        margin_top="2px",
                                    ),
                                    # Maximum unknown (not tested yet)
                                    rx.text(
                                        t("yarn_max_unknown"),
                                        font_size="10px",
                                        color="#999",  # Gray for unknown
                                        font_weight="400",
                                        margin_top="2px",
                                    ),
                                ),
                                spacing="2",
                            ),
                            rx.box(),
                        ),
                        rx.cond(
                            AIState.vllm_max_tokens > 0,
                            rx.text(
                                "ℹ️ " + (AIState.vllm_native_context / 1000).to(int).to(str) + "K nativ | HW: " + (AIState.vllm_max_tokens / 1000).to(int).to(str) + "K",
                                font_size="10px",
                                color="#999",
                                line_height="1.3",
                            ),
                            rx.text(
                                t("yarn_context_info"),
                                font_size="10px",
                                color="#999",
                                line_height="1.3",
                            ),
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    rx.box(),  # Empty box when not vLLM
                ),

                # TTS/STT Settings
                rx.divider(margin_top="12px", margin_bottom="12px"),

                # TTS (Text-to-Speech) Section
                rx.vstack(
                    rx.hstack(
                        rx.text(t("tts_heading"), font_weight="bold", font_size="12px"),
                        rx.switch(
                            checked=AIState.enable_tts,
                            on_change=AIState.toggle_tts,
                            size="1",
                        ),
                        rx.text(
                            rx.cond(
                                AIState.enable_tts,
                                "ON",
                                "OFF"
                            ),
                            font_size="11px",
                            color=rx.cond(
                                AIState.enable_tts,
                                "#4CAF50",
                                "#999"
                            ),
                        ),
                        spacing="2",
                        align="center",
                    ),
                    rx.cond(
                        AIState.enable_tts,
                        rx.vstack(
                            # TTS Engine Selection
                            rx.hstack(
                                rx.text(t("tts_engine_label"), font_size="11px", font_weight="500", width="80px"),
                                rx.cond(
                                    AIState.is_mobile,
                                    # Mobile: Native select
                                    native_select_tts(
                                        AIState.tts_engine,
                                        AIState.set_tts_engine,
                                        ["Edge TTS (Cloud)", "Piper TTS (Offline)", "eSpeak (Roboter, Offline)"],
                                    ),
                                    # Desktop: Radix UI select
                                    rx.select(
                                        ["Edge TTS (Cloud)", "Piper TTS (Offline)", "eSpeak (Roboter, Offline)"],
                                        value=AIState.tts_engine,
                                        on_change=AIState.set_tts_engine,
                                        size="2",
                                    ),
                                ),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            # Voice Selection (dynamic based on engine)
                            rx.hstack(
                                rx.text(t("tts_voice_label"), font_size="11px", font_weight="500", width="80px"),
                                rx.cond(
                                    AIState.is_mobile,
                                    # Mobile: Native select
                                    native_select_tts(
                                        AIState.tts_voice,
                                        AIState.set_tts_voice,
                                        AIState.available_tts_voices,
                                    ),
                                    # Desktop: Radix UI select
                                    rx.select(
                                        AIState.available_tts_voices,
                                        value=AIState.tts_voice,
                                        on_change=AIState.set_tts_voice,
                                        size="2",
                                    ),
                                ),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            # Playback Speed Selection (browser playback rate, persisted)
                            rx.hstack(
                                rx.text(t("tts_speed_label"), font_size="11px", font_weight="500", width="80px"),
                                rx.cond(
                                    AIState.is_mobile,
                                    # Mobile: Native select
                                    native_select_tts(
                                        AIState.tts_playback_rate,
                                        AIState.set_tts_playback_rate,
                                        ["0.5x", "0.75x", "1x", "1.25x", "1.5x", "2x"],
                                    ),
                                    # Desktop: Radix UI select
                                    rx.select(
                                        ["0.5x", "0.75x", "1x", "1.25x", "1.5x", "2x"],
                                        value=AIState.tts_playback_rate,
                                        on_change=AIState.set_tts_playback_rate,
                                        size="2",
                                    ),
                                ),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            # Pitch Selection (applied via ffmpeg post-processing)
                            rx.hstack(
                                rx.text(t("tts_pitch_label"), font_size="11px", font_weight="500", width="80px"),
                                rx.cond(
                                    AIState.is_mobile,
                                    # Mobile: Native select
                                    native_select_tts(
                                        AIState.tts_pitch,
                                        AIState.set_tts_pitch,
                                        ["0.8", "0.85", "0.9", "0.95", "1.0", "1.05", "1.1", "1.15", "1.2"],
                                    ),
                                    # Desktop: Radix UI select
                                    rx.select(
                                        ["0.8", "0.85", "0.9", "0.95", "1.0", "1.05", "1.1", "1.15", "1.2"],
                                        value=AIState.tts_pitch,
                                        on_change=AIState.set_tts_pitch,
                                        size="2",
                                    ),
                                ),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            # Auto-Play Toggle
                            rx.hstack(
                                rx.text(t("tts_autoplay_label"), font_size="11px", font_weight="500", width="80px"),
                                rx.switch(
                                    checked=AIState.tts_autoplay,
                                    on_change=AIState.toggle_tts_autoplay,
                                    size="1",
                                ),
                                rx.text(
                                    rx.cond(
                                        AIState.tts_autoplay,
                                        "ON",
                                        "OFF"
                                    ),
                                    font_size="10px",
                                    color=rx.cond(
                                        AIState.tts_autoplay,
                                        "#4CAF50",
                                        "#999"
                                    ),
                                ),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            spacing="3",
                            width="100%",
                        ),
                        rx.box(),  # Empty when TTS disabled
                    ),
                    spacing="2",
                    width="100%",
                ),

                # STT (Speech-to-Text) Section
                rx.divider(margin_top="12px", margin_bottom="12px"),
                rx.vstack(
                    rx.text(t("stt_heading"), font_weight="bold", font_size="12px"),
                    # Whisper Model Selection
                    rx.hstack(
                        rx.text(t("stt_model_label"), font_size="11px", font_weight="500", width="80px"),
                        rx.cond(
                            AIState.is_mobile,
                            # Mobile: Native select
                            native_select_stt(
                                AIState.whisper_model_display,
                                AIState.set_whisper_model,
                                [t("stt_model_tiny"), t("stt_model_base"), t("stt_model_small"), t("stt_model_medium"), t("stt_model_large")],
                            ),
                            # Desktop: Radix UI select
                            rx.select(
                                [t("stt_model_tiny"), t("stt_model_base"), t("stt_model_small"), t("stt_model_medium"), t("stt_model_large")],
                                value=AIState.whisper_model_display,
                                on_change=AIState.set_whisper_model,
                                size="2",
                            ),
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    # Device is now fixed to CPU (configured in config.py)
                    # GPU would use precious VRAM needed for LLM inference
                    # REMOVED: Show Transcription Toggle (moved to top, near recording buttons)
                    spacing="3",
                    width="100%",
                ),

                # Restart Buttons
                rx.divider(),
                rx.text(t("system_control"), font_weight="bold", font_size="12px"),
                rx.vstack(
                    # Row 1: Backend and AIfred restart buttons (side by side, each 50%)
                    rx.hstack(
                        rx.button(
                            rx.cond(
                                AIState.backend_type == "ollama",
                                t("restart_ollama"),
                                rx.cond(
                                    AIState.backend_type == "vllm",
                                    t("restart_vllm"),
                                    rx.text(f"🔄 {AIState.backend_type.upper()} Neustart")
                                )
                            ),
                            on_click=AIState.restart_backend,
                            size="2",
                            variant="soft",
                            color_scheme="blue",
                            disabled=AIState.backend_switching,
                            flex="1",
                            style={
                                "&:hover:not([disabled])": {
                                    "background": "var(--blue-a6) !important",
                                    "transform": "scale(1.02)",
                                },
                                "&:active:not([disabled])": {
                                    "background": "var(--blue-a8) !important",
                                    "transform": "scale(0.98)",
                                },
                            },
                        ),
                        rx.button(
                            t("restart_aifred"),
                            on_click=AIState.restart_aifred,
                            size="2",
                            variant="soft",
                            color_scheme="orange",
                            disabled=AIState.backend_switching,
                            flex="1",
                            style={
                                "&:hover:not([disabled])": {
                                    "background": "var(--orange-a6) !important",
                                    "transform": "scale(1.02)",
                                },
                                "&:active:not([disabled])": {
                                    "background": "var(--orange-a8) !important",
                                    "transform": "scale(0.98)",
                                },
                            },
                        ),
                        spacing="3",
                        width="100%",
                    ),
                    # Row 2: Vector DB clear button (full width, same style as chat clear)
                    rx.button(
                        "🗑️ Vector-DB leeren",
                        on_click=AIState.clear_vector_cache,
                        size="2",
                        variant="outline",
                        color_scheme="orange",
                        disabled=AIState.backend_switching,
                        width="100%",
                        style={
                            "background": "rgba(100, 10, 0, 0.4)",  # Same as chat clear button
                            "&:hover:not([disabled])": {
                                "background": "rgba(150, 15, 0, 0.6) !important",
                                "border_color": "#ff6600 !important",
                                "transform": "scale(1.02)",
                            },
                            "&:active:not([disabled])": {
                                "background": "rgba(80, 5, 0, 0.7) !important",
                                "transform": "scale(0.98)",
                            },
                        },
                    ),
                    # Row 3: Load Default Settings button
                    rx.button(
                        "💾 Grundeinstellungen laden",
                        on_click=AIState.load_default_settings,
                        size="2",
                        variant="solid",
                        color_scheme="blue",
                        disabled=AIState.backend_switching,
                        width="100%",
                        style={
                            "&:hover:not([disabled])": {
                                "background": "var(--blue-a9) !important",
                                "transform": "scale(1.02)",
                            },
                            "&:active:not([disabled])": {
                                "background": "var(--blue-a11) !important",
                                "transform": "scale(0.98)",
                            },
                        },
                    ),
                    spacing="2",
                    width="100%",
                ),
                # Neustart-Info Texte
                rx.vstack(
                    rx.text(
                        t("backend_restart_info"),
                        font_size="10px",
                        color=COLORS["text_secondary"],
                    ),
                    rx.text(
                        t("aifred_restart_info"),
                        font_size="10px",
                        color=COLORS["text_secondary"],
                    ),
                    spacing="1",
                    width="100%",
                ),

                spacing="4",
                width="100%",
            ),
        ),
        id="settings-accordion",  # ID for JavaScript height sync
        collapsible=True,  # WICHTIG: Macht Accordion schließbar!
        default_value="settings",  # Standardmäßig geöffnet
        color_scheme="gray",
        variant="soft",
    )


# ============================================================
# MULTI-AGENT HELP MODAL - Übersicht aller Diskussionsmodi
# ============================================================

def multi_agent_help_modal() -> rx.Component:
    """
    Fullscreen Overlay für Multi-Agent Modus-Übersicht.
    Zeigt alle Modi mit Ablauf und wer entscheidet.
    """
    return rx.cond(
        AIState.multi_agent_help_open,
        # Fullscreen Overlay
        rx.box(
            # Backdrop (klickbar zum Schließen)
            rx.box(
                position="absolute",
                top="0",
                left="0",
                width="100%",
                height="100%",
                background_color="rgba(0, 0, 0, 0.85)",
                on_click=AIState.close_multi_agent_help,
            ),

            # Modal Content - zentriert
            rx.vstack(
                # Header
                rx.hstack(
                    rx.icon("lightbulb", size=24, color="#FFD700"),
                    rx.text(t("multi_agent_help_title"), color="white", font_weight="bold", font_size="18px"),
                    spacing="3",
                    align="center",
                ),

                # Tabelle der Modi
                rx.box(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell(t("multi_agent_help_mode"), style={"color": "#FFD700", "font_weight": "bold"}),
                                rx.table.column_header_cell(t("multi_agent_help_flow"), style={"color": "#FFD700", "font_weight": "bold"}),
                                rx.table.column_header_cell(t("multi_agent_help_decision"), style={"color": "#FFD700", "font_weight": "bold"}),
                            ),
                        ),
                        rx.table.body(
                            # Standard
                            rx.table.row(
                                rx.table.cell(rx.cond(AIState.ui_language == "de", "Standard", "Standard")),
                                rx.table.cell(t("multi_agent_help_standard_flow")),
                                rx.table.cell(t("multi_agent_help_standard_decision")),
                            ),
                            # Kritische Prüfung / Critical Review
                            rx.table.row(
                                rx.table.cell(rx.cond(AIState.ui_language == "de", "Kritische Prüfung", "Critical Review")),
                                rx.table.cell(t("multi_agent_help_critical_review_flow")),
                                rx.table.cell(t("multi_agent_help_critical_review_decision")),
                            ),
                            # Auto-Konsens / Auto Consensus
                            rx.table.row(
                                rx.table.cell(rx.cond(AIState.ui_language == "de", "Auto-Konsens", "Auto Consensus")),
                                rx.table.cell(t("multi_agent_help_auto_consensus_flow")),
                                rx.table.cell(t("multi_agent_help_auto_consensus_decision")),
                            ),
                            # Advocatus Diaboli / Devil's Advocate
                            rx.table.row(
                                rx.table.cell(rx.cond(AIState.ui_language == "de", "Advocatus Diaboli", "Devil's Advocate")),
                                rx.table.cell(t("multi_agent_help_devils_advocate_flow")),
                                rx.table.cell(t("multi_agent_help_devils_advocate_decision")),
                            ),
                            # Tribunal
                            rx.table.row(
                                rx.table.cell("Tribunal"),
                                rx.table.cell(t("multi_agent_help_tribunal_flow")),
                                rx.table.cell(t("multi_agent_help_tribunal_decision")),
                            ),
                        ),
                        style={
                            "width": "100%",
                            "border_collapse": "collapse",
                            "& th, & td": {
                                "padding": "10px 15px",
                                "text_align": "left",
                                "border_bottom": "1px solid #444",
                            },
                        },
                    ),
                    width="100%",
                    overflow_x="auto",
                ),

                # Agenten-Beschreibungen
                rx.divider(color="#444", margin_y="15px"),
                rx.text(t("multi_agent_help_agents_title"), color="#FFD700", font_weight="bold", font_size="14px"),
                rx.vstack(
                    rx.hstack(
                        rx.text("🎩 AIfred:", color="white", font_weight="bold", min_width="120px"),
                        rx.text(t("multi_agent_help_aifred_desc"), color="#ccc"),
                        spacing="2",
                        align="start",
                    ),
                    rx.hstack(
                        rx.text("🏛️ Sokrates:", color="white", font_weight="bold", min_width="120px"),
                        rx.text(t("multi_agent_help_sokrates_desc"), color="#ccc"),
                        spacing="2",
                        align="start",
                    ),
                    rx.hstack(
                        rx.text("👑 Salomo:", color="white", font_weight="bold", min_width="120px"),
                        rx.text(t("multi_agent_help_salomo_desc"), color="#ccc"),
                        spacing="2",
                        align="start",
                    ),
                    spacing="2",
                    width="100%",
                    align_items="start",
                ),

                # Schließen-Button
                rx.button(
                    t("multi_agent_help_close"),
                    on_click=AIState.close_multi_agent_help,
                    variant="soft",
                    color_scheme="gray",
                    size="3",
                    margin_top="15px",
                ),

                spacing="4",
                align="center",
                padding="25px",
                background_color="#1a1a1a",
                border_radius="12px",
                max_width="95vw",
                width="600px",
                max_height="90vh",
                overflow_y="auto",
                position="relative",
                z_index="1001",
                color="white",
            ),

            # Fullscreen container
            position="fixed",
            top="0",
            left="0",
            width="100vw",
            height="100vh",
            z_index="1000",
            display="flex",
            justify_content="center",
            align_items="center",
        ),
    )


# ============================================================
# IMAGE CROP MODAL - Fullscreen Overlay (besser für Mobile)
# ============================================================

def crop_modal() -> rx.Component:
    """
    Fullscreen Overlay für Bild-Zuschnitt.
    Verwendet rx.cond statt rx.dialog für bessere Mobile-Kompatibilität.
    """
    return rx.cond(
        AIState.crop_modal_open,
        # Fullscreen Overlay
        rx.box(
            # Backdrop (klickbar zum Schließen)
            rx.box(
                position="absolute",
                top="0",
                left="0",
                width="100%",
                height="100%",
                background_color="rgba(0, 0, 0, 0.85)",
                on_click=AIState.cancel_crop,
            ),

            # Modal Content - zentriert
            rx.vstack(
                # Header
                rx.hstack(
                    rx.icon("crop", size=20, color="white"),
                    rx.text(t("crop_modal_title"), color="white", font_weight="bold"),
                    spacing="2",
                    align="center",
                ),

                # Bild + Crop-Overlay Container
                rx.box(
                    # Das Bild
                    rx.image(
                        src=AIState.crop_preview_url,
                        id="crop-image",
                        max_width="90vw",
                        max_height="60vh",
                        object_fit="contain",
                        border_radius="8px",
                        display="block",
                    ),
                    # Crop-Overlay
                    rx.box(
                        rx.box(
                            # 4 Ecken
                            rx.box(class_name="crop-handle crop-handle-nw", id="crop-nw"),
                            rx.box(class_name="crop-handle crop-handle-ne", id="crop-ne"),
                            rx.box(class_name="crop-handle crop-handle-sw", id="crop-sw"),
                            rx.box(class_name="crop-handle crop-handle-se", id="crop-se"),
                            # 4 Kanten
                            rx.box(class_name="crop-handle crop-handle-n", id="crop-n"),
                            rx.box(class_name="crop-handle crop-handle-s", id="crop-s"),
                            rx.box(class_name="crop-handle crop-handle-w", id="crop-w"),
                            rx.box(class_name="crop-handle crop-handle-e", id="crop-e"),
                            id="crop-box",
                            class_name="crop-box",
                        ),
                        id="crop-overlay",
                        class_name="crop-overlay",
                    ),
                    id="crop-container",
                    position="relative",
                    display="inline-block",  # Passt sich an Bildgröße an
                ),

                # Info-Text
                rx.text(
                    t("crop_modal_hint"),
                    font_size="12px",
                    color="#888",
                    text_align="center",
                ),

                # Buttons
                rx.hstack(
                    rx.button(
                        t("crop_cancel"),
                        on_click=AIState.cancel_crop,
                        variant="soft",
                        color_scheme="gray",
                        size="3",
                    ),
                    rx.button(
                        rx.hstack(
                            rx.icon("check", size=16),
                            rx.text(t("crop_apply")),
                            spacing="1",
                        ),
                        on_click=rx.call_script(
                            """
                            (() => {
                                const cropBox = document.getElementById('crop-box');
                                if (cropBox) {
                                    const left = parseFloat(cropBox.style.left) || 0;
                                    const top = parseFloat(cropBox.style.top) || 0;
                                    const width = parseFloat(cropBox.style.width) || 100;
                                    const height = parseFloat(cropBox.style.height) || 100;
                                    return JSON.stringify({ x: left, y: top, width: width, height: height });
                                }
                                return JSON.stringify({ x: 0, y: 0, width: 100, height: 100 });
                            })()
                            """,
                            callback=AIState.apply_crop_with_coords
                        ),
                        color_scheme="green",
                        size="3",
                    ),
                    spacing="3",
                ),

                spacing="4",
                align="center",
                padding="20px",
                background_color="#1a1a1a",
                border_radius="12px",
                max_width="95vw",
                max_height="90vh",
                position="relative",
                z_index="1001",
            ),

            # Fullscreen container
            position="fixed",
            top="0",
            left="0",
            width="100vw",
            height="100vh",
            z_index="1000",
            display="flex",
            justify_content="center",
            align_items="center",
            style={"touch_action": "none"},  # Verhindert Browser-Scroll
        ),
    )


def image_lightbox_modal() -> rx.Component:
    """
    Fullscreen Overlay for viewing chat history images full-size.
    Click anywhere to close.
    """
    return rx.cond(
        AIState.lightbox_open,
        # Fullscreen Overlay
        rx.box(
            # Backdrop (click to close)
            rx.box(
                position="absolute",
                top="0",
                left="0",
                width="100%",
                height="100%",
                background_color="rgba(0, 0, 0, 0.92)",
                on_click=AIState.close_lightbox,
                cursor="pointer",
            ),

            # Close button (top-right corner)
            rx.box(
                rx.icon("x", size=28, color="white"),
                position="absolute",
                top="20px",
                right="20px",
                cursor="pointer",
                padding="8px",
                border_radius="50%",
                background_color="rgba(255, 255, 255, 0.1)",
                on_click=AIState.close_lightbox,
                z_index="1002",
                style={
                    "transition": "background-color 0.2s ease",
                    "&:hover": {
                        "background_color": "rgba(255, 255, 255, 0.2)",
                    },
                },
            ),

            # Image - centered, click to close
            rx.image(
                src=AIState.lightbox_image_url,
                max_width="90vw",
                max_height="85vh",
                object_fit="contain",
                border_radius="8px",
                on_click=AIState.close_lightbox,
                cursor="pointer",
                position="relative",
                z_index="1001",
            ),

            # Fullscreen container
            position="fixed",
            top="0",
            left="0",
            width="100vw",
            height="100vh",
            z_index="1000",
            display="flex",
            justify_content="center",
            align_items="center",
            style={"touch_action": "none"},  # Prevent browser scroll
        ),
    )


# ============================================================
# MAIN PAGE
# ============================================================

@rx.page(route="/", on_load=AIState.on_load, title="AIfred Intelligence")
def index() -> rx.Component:
    """Main page with single column layout for mobile optimization"""

    # Inline JavaScript for auto-scroll (must be inline to ensure execution)
    autoscroll_js = """
console.log('🔧 Autoscroll script loaded');

// Make all external links open in new tab
function makeLinksOpenInNewTab() {
    const links = document.querySelectorAll('a[href^="http"]');
    links.forEach(link => {
        if (!link.hasAttribute('target')) {
            link.setAttribute('target', '_blank');
            link.setAttribute('rel', 'noopener noreferrer');
        }
    });
}

function isAutoScrollEnabled() {
    const sw = document.getElementById('autoscroll-switch');
    if (!sw) return true; // Default: enabled if switch not found
    return sw.getAttribute('data-state') === 'checked';
}

function autoScrollElement(element) {
    if (element) {
        element.scrollTop = element.scrollHeight;
    }
}

// Observer für Debug-Console und Chat-History Updates
const observerConfig = { childList: true, subtree: true };

// Track if chat-history-box observer is already running
let chatObserverAttached = false;

const callback = function(mutationsList, observer) {
    const enabled = isAutoScrollEnabled();

    // Make all links open in new tab (always, regardless of auto-scroll)
    makeLinksOpenInNewTab();

    // Get elements once
    const chatBox = document.getElementById('chat-history-box');

    // Lazy-attach observer to chat-history-box when it appears
    // (it's conditionally rendered after backend_initializing=False)
    if (!chatObserverAttached && chatBox) {
        const chatObserver = new MutationObserver(callback);
        chatObserver.observe(chatBox, observerConfig);
        chatObserverAttached = true;
    }

    // Only scroll if auto-scroll is enabled
    if (!enabled) {
        return;
    }

    // Auto-scroll Debug Console
    const debugBox = document.getElementById('debug-console-box');
    if (debugBox) {
        autoScrollElement(debugBox);
    }

    // Auto-scroll Chat History
    if (chatBox) {
        autoScrollElement(chatBox);
    }
};

function syncDebugConsoleHeight() {
    // Find elements by ID (simple and reliable)
    const settingsAccordion = document.getElementById('settings-accordion');
    const debugBox = document.getElementById('debug-console-box');

    if (settingsAccordion && debugBox) {
        // Get the full height of the settings accordion (including all expanded sections)
        const settingsHeight = settingsAccordion.scrollHeight || settingsAccordion.getBoundingClientRect().height;

        // Set Debug Console to match (minimum 900px, maximum 1600px)
        const targetHeight = Math.min(1600, Math.max(900, settingsHeight));
        debugBox.style.height = targetHeight + 'px';

        // Log only if height changed significantly
        const currentHeight = parseInt(debugBox.style.height) || 900;
        if (Math.abs(currentHeight - targetHeight) > 10) {
            console.log('📏 Synced heights - Settings:', settingsHeight, 'Target:', targetHeight);
        }
    } else {
        // Fallback: set a reasonable default matching Python height
        if (debugBox) {
            debugBox.style.height = '955px';
        }
        if (!settingsAccordion) {
            console.warn('⚠️ settings-accordion not found');
        }
    }
}

function setupObservers() {
    console.log('🚀 Setting up observers...');

    const debugBox = document.getElementById('debug-console-box');
    if (debugBox) {
        console.log('✅ Found debug-console-box');
        const observer = new MutationObserver(callback);
        observer.observe(debugBox, observerConfig);
    } else {
        console.warn('❌ debug-console-box not found');
    }

    // Chat History - JavaScript-basiertes Autoscroll (statt rx.auto_scroll)
    // May not exist yet if backend is still initializing (rx.cond renders it later)
    if (!chatObserverAttached) {
        const chatBox = document.getElementById('chat-history-box');
        if (chatBox) {
            console.log('✅ Found chat-history-box');
            const chatObserver = new MutationObserver(callback);
            chatObserver.observe(chatBox, observerConfig);
            chatObserverAttached = true;
        } else {
            console.warn('❌ chat-history-box not found (will attach via debug-console callback)');
        }
    }

    // Sync heights on accordion open/close - observe settings-accordion by ID
    const settingsAccordion = document.getElementById('settings-accordion');
    if (settingsAccordion) {
        // ResizeObserver for size changes
        const resizeObserver = new ResizeObserver(() => {
            syncDebugConsoleHeight();
        });
        resizeObserver.observe(settingsAccordion);

        // MutationObserver for accordion open/close
        const mutationObserver = new MutationObserver(() => {
            // Delay to allow animation to complete
            setTimeout(syncDebugConsoleHeight, 100);
            setTimeout(syncDebugConsoleHeight, 300);
        });
        mutationObserver.observe(settingsAccordion, { childList: true, subtree: true, attributes: true });

        // Click handler for accordion triggers
        const triggers = settingsAccordion.querySelectorAll('.rt-AccordionTrigger');
        triggers.forEach(trigger => {
            trigger.addEventListener('click', () => {
                // Sync after accordion animation (multiple times for smooth transition)
                setTimeout(syncDebugConsoleHeight, 50);
                setTimeout(syncDebugConsoleHeight, 150);
                setTimeout(syncDebugConsoleHeight, 350);
            });
        });

        console.log('✅ Height sync observers attached to settings-accordion');
    } else {
        console.warn('⚠️ settings-accordion not found for observers');
    }

    // Also observe on window resize
    window.addEventListener('resize', syncDebugConsoleHeight);
}

// Initialize immediately or wait for DOMContentLoaded
function initialize() {
    console.log('📄 Initializing autoscroll...');

    // Make existing links open in new tab
    makeLinksOpenInNewTab();

    setupObservers();

    // Initial height sync
    syncDebugConsoleHeight();

    // Einmaliger Retry nach 1.5s für Elemente die erst nach Backend-Init erscheinen
    // (chat-history-box wird durch rx.cond erst gerendert wenn backend_initializing=False)
    setTimeout(() => {
        setupObservers();
        makeLinksOpenInNewTab();
        syncDebugConsoleHeight();
    }, 1500);
}

// Check if DOM is already loaded (script loaded late)
if (document.readyState === 'loading') {
    // DOM not yet loaded, wait for it
    document.addEventListener('DOMContentLoaded', initialize);
} else {
    // DOM already loaded, run immediately
    initialize();
}
"""

    # Paste handler for image support (desktop)
    paste_handler_js = """
console.log('📋 Image paste handler loaded');

// Global paste event handler for images
document.addEventListener('paste', async function(e) {
    console.log('📋 Paste event detected');
    const items = e.clipboardData.items;
    const imageFiles = [];

    for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.type.startsWith('image/')) {
            console.log('🖼️ Image found in clipboard:', item.type);
            const file = item.getAsFile();
            if (file) {
                imageFiles.push(file);
            }
        }
    }

    if (imageFiles.length > 0) {
        e.preventDefault();
        console.log('📸 Triggering upload for', imageFiles.length, 'image(s)');

        // Trigger Reflex upload handler
        const uploadEl = document.getElementById('image-upload');
        if (uploadEl) {
            // Simulate file drop event
            const dataTransfer = new DataTransfer();
            imageFiles.forEach(f => dataTransfer.items.add(f));

            const dropEvent = new DragEvent('drop', {
                dataTransfer: dataTransfer,
                bubbles: true,
                cancelable: true
            });

            uploadEl.dispatchEvent(dropEvent);
            console.log('✅ Upload event dispatched');
        } else {
            console.error('❌ Upload element not found');
        }
    }
});

console.log('✅ Paste handler initialized');
"""

    # JavaScript für Crop-Funktionalität
    crop_js = """
console.log('✂️ Crop handler loaded');

// Crop-Box Drag-Funktionalität
(function() {
    let isDragging = false;
    let dragType = null; // 'move', 'nw', 'ne', 'sw', 'se', 'n', 's', 'w', 'e'
    let startX, startY;
    let startBox = { x: 0, y: 0, width: 100, height: 100 };
    let currentBox = { x: 0, y: 0, width: 100, height: 100 };
    let listenersAdded = false;

    function initCrop() {
        const overlay = document.getElementById('crop-overlay');
        const cropBox = document.getElementById('crop-box');
        const image = document.getElementById('crop-image');
        const container = document.getElementById('crop-container');

        if (!overlay || !cropBox || !image || !container) {
            return; // Modal nicht offen
        }

        // WICHTIG: Body-Scroll blockieren und nach oben scrollen
        document.body.style.overflow = 'hidden';
        document.documentElement.style.overflow = 'hidden';
        window.scrollTo(0, 0);  // Scroll nach oben
        console.log('✂️ Body scroll disabled, scrolled to top');

        // Positioniere Overlay auf Bildgröße (wichtig für object-fit: contain)
        function positionOverlay() {
            const containerRect = container.getBoundingClientRect();
            const imageRect = image.getBoundingClientRect();

            // Berechne Offset des Bildes innerhalb des Containers
            const offsetLeft = imageRect.left - containerRect.left;
            const offsetTop = imageRect.top - containerRect.top;

            overlay.style.left = offsetLeft + 'px';
            overlay.style.top = offsetTop + 'px';
            overlay.style.width = imageRect.width + 'px';
            overlay.style.height = imageRect.height + 'px';

            console.log('✂️ Overlay positioned on image:', imageRect.width.toFixed(0), 'x', imageRect.height.toFixed(0));
        }

        // Warte auf Bild-Load
        if (image.complete && image.naturalWidth > 0) {
            setTimeout(positionOverlay, 50); // Kurze Verzögerung für Layout
        } else {
            image.onload = () => setTimeout(positionOverlay, 50);
        }

        // Initial: Ganzes Bild selektiert
        currentBox = { x: 0, y: 0, width: 100, height: 100 };
        updateCropBoxUI();

        // Nur einmal Listener hinzufügen
        if (listenersAdded) return;
        listenersAdded = true;

        // Event Listener für Crop-Box (move)
        cropBox.addEventListener('mousedown', (e) => {
            if (e.target === cropBox) {
                startDrag(e, 'move');
                e.preventDefault();
            }
        });
        cropBox.addEventListener('touchstart', (e) => {
            if (e.target === cropBox) {
                startDrag(e.touches[0], 'move');
                e.preventDefault();
                e.stopPropagation();
            }
        }, { passive: false });

        // Event Listener für Handles
        const handles = ['nw', 'ne', 'sw', 'se', 'n', 's', 'w', 'e'];
        handles.forEach(h => {
            const handle = document.getElementById('crop-' + h);
            if (handle) {
                handle.addEventListener('mousedown', (e) => {
                    startDrag(e, h);
                    e.preventDefault();
                    e.stopPropagation();
                });
                handle.addEventListener('touchstart', (e) => {
                    startDrag(e.touches[0], h);
                    e.preventDefault();
                    e.stopPropagation();
                }, { passive: false });
            }
        });

        // Global mouse/touch events
        document.addEventListener('mousemove', onDrag);
        document.addEventListener('mouseup', endDrag);
        document.addEventListener('touchmove', (e) => {
            if (isDragging) {
                onDrag(e.touches[0]);
                e.preventDefault();
                e.stopPropagation();
            }
        }, { passive: false });
        document.addEventListener('touchend', endDrag);
        document.addEventListener('touchcancel', endDrag);

        console.log('✂️ Crop initialized with touch support');
    }

    function startDrag(e, type) {
        isDragging = true;
        dragType = type;
        startX = e.clientX;
        startY = e.clientY;
        startBox = { ...currentBox };
        // Verhindere Selektion während Drag
        document.body.style.userSelect = 'none';
        document.body.style.webkitUserSelect = 'none';
    }

    function onDrag(e) {
        if (!isDragging) return;

        const overlay = document.getElementById('crop-overlay');
        if (!overlay) return;

        const rect = overlay.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;

        const deltaX = ((e.clientX - startX) / rect.width) * 100;
        const deltaY = ((e.clientY - startY) / rect.height) * 100;

        let newBox = { ...startBox };

        switch(dragType) {
            case 'move':
                newBox.x = Math.max(0, Math.min(100 - startBox.width, startBox.x + deltaX));
                newBox.y = Math.max(0, Math.min(100 - startBox.height, startBox.y + deltaY));
                break;
            case 'nw':
                newBox.x = Math.max(0, Math.min(startBox.x + startBox.width - 10, startBox.x + deltaX));
                newBox.y = Math.max(0, Math.min(startBox.y + startBox.height - 10, startBox.y + deltaY));
                newBox.width = startBox.width - (newBox.x - startBox.x);
                newBox.height = startBox.height - (newBox.y - startBox.y);
                break;
            case 'ne':
                newBox.y = Math.max(0, Math.min(startBox.y + startBox.height - 10, startBox.y + deltaY));
                newBox.width = Math.max(10, Math.min(100 - startBox.x, startBox.width + deltaX));
                newBox.height = startBox.height - (newBox.y - startBox.y);
                break;
            case 'sw':
                newBox.x = Math.max(0, Math.min(startBox.x + startBox.width - 10, startBox.x + deltaX));
                newBox.width = startBox.width - (newBox.x - startBox.x);
                newBox.height = Math.max(10, Math.min(100 - startBox.y, startBox.height + deltaY));
                break;
            case 'se':
                newBox.width = Math.max(10, Math.min(100 - startBox.x, startBox.width + deltaX));
                newBox.height = Math.max(10, Math.min(100 - startBox.y, startBox.height + deltaY));
                break;
            case 'n':
                newBox.y = Math.max(0, Math.min(startBox.y + startBox.height - 10, startBox.y + deltaY));
                newBox.height = startBox.height - (newBox.y - startBox.y);
                break;
            case 's':
                newBox.height = Math.max(10, Math.min(100 - startBox.y, startBox.height + deltaY));
                break;
            case 'w':
                newBox.x = Math.max(0, Math.min(startBox.x + startBox.width - 10, startBox.x + deltaX));
                newBox.width = startBox.width - (newBox.x - startBox.x);
                break;
            case 'e':
                newBox.width = Math.max(10, Math.min(100 - startBox.x, startBox.width + deltaX));
                break;
        }

        currentBox = newBox;
        updateCropBoxUI();
    }

    function endDrag() {
        if (isDragging) {
            isDragging = false;
            dragType = null;
            document.body.style.userSelect = '';
            document.body.style.webkitUserSelect = '';
        }
    }

    function updateCropBoxUI() {
        const cropBox = document.getElementById('crop-box');
        if (cropBox) {
            cropBox.style.left = currentBox.x + '%';
            cropBox.style.top = currentBox.y + '%';
            cropBox.style.width = currentBox.width + '%';
            cropBox.style.height = currentBox.height + '%';
        }
    }

    // Reset bei Modal-Schließung
    function resetCrop() {
        currentBox = { x: 0, y: 0, width: 100, height: 100 };
        listenersAdded = false;
        isDragging = false;
        // Body-Scroll wieder aktivieren
        document.body.style.overflow = '';
        document.documentElement.style.overflow = '';
        console.log('✂️ Body scroll re-enabled');
    }

    // Observer für Modal-Öffnung/Schließung
    const observer = new MutationObserver((mutations) => {
        const overlay = document.getElementById('crop-overlay');
        if (overlay) {
            initCrop();
        } else {
            resetCrop();
        }
    });

    observer.observe(document.body, { childList: true, subtree: true });
})();
"""

    return rx.box(
        # Inline JavaScript (guaranteed to execute)
        rx.script(autoscroll_js),
        rx.script(paste_handler_js),
        rx.script(crop_js),

        # Load custom.js for MediaRecorder and other features (cache-busting version)
        rx.script(src="/custom.js?v=13"),

        # Crop Modal (rendered but hidden until open)
        crop_modal(),

        # Image Lightbox Modal (for viewing history images full-size)
        image_lightbox_modal(),

        # Multi-Agent Help Modal (Diskussionsmodi-Übersicht)
        multi_agent_help_modal(),

        # Hidden element to trigger camera detection on mount
        rx.box(
            id="camera-detector",
            display="none",
            on_mount=[
                # Camera Detection
                rx.call_script(
                    """
                    (async () => {
                        try {
                            if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
                                const devices = await navigator.mediaDevices.enumerateDevices();
                                const hasCamera = devices.some(device => device.kind === 'videoinput');
                                console.log('📷 Camera detected:', hasCamera);
                                return hasCamera;
                            }
                        } catch (err) {
                            console.log('⚠️ Camera detection failed:', err);
                        }
                        return false;
                    })()
                    """,
                    callback=AIState.set_camera_available
                ),
                # Mobile Detection (User-Agent + Touch)
                rx.call_script(
                    """
                    (() => {
                        // Check User-Agent for mobile devices
                        const userAgent = navigator.userAgent || navigator.vendor || window.opera;
                        const mobileRegex = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini|mobile/i;
                        const isMobileUA = mobileRegex.test(userAgent.toLowerCase());

                        // Check for touch support
                        const hasTouch = ('ontouchstart' in window) ||
                                        (navigator.maxTouchPoints > 0) ||
                                        (navigator.msMaxTouchPoints > 0);

                        // Mobile = Mobile UA + Touch support
                        const isMobile = isMobileUA && hasTouch;

                        console.log('📱 Mobile detection:', {
                            userAgent: userAgent,
                            isMobileUA: isMobileUA,
                            hasTouch: hasTouch,
                            maxTouchPoints: navigator.maxTouchPoints,
                            isMobile: isMobile
                        });

                        return isMobile;
                    })()
                    """,
                    callback=AIState.set_is_mobile
                )
            ]
        ),

        rx.vstack(
            # Header
            rx.heading(t("aifred_intelligence"), size="6", margin_bottom="2"),
            rx.text(
                t("subtitle"),
                color=COLORS["text_secondary"],
                font_size="12px",
                font_style="italic",
                margin_bottom="4",
            ),

            # Chat History (top - read conversation first)
            # NOTE: Failed sources are now displayed inline within each message (persistent)
            # NOTE: Sokrates now streams directly into chat_history (no separate panel)
            chat_history_display(),

            # TTS Audio Player - shows when TTS enabled AND chat history exists
            # This allows "Neu generieren" after app restart (before any audio generated)
            rx.cond(
                AIState.enable_tts & (AIState.chat_history.length() > 0),
                rx.box(
                    rx.hstack(
                        rx.text("🔊", font_size="18px"),
                        rx.text(t("tts_player_label"), font_weight="bold", font_size="13px", color=COLORS["accent_blue"]),
                        rx.spacer(),
                        # Regenerate TTS Button - re-synthesize with current voice settings
                        rx.button(
                            t("tts_regenerate"),
                            on_click=AIState.resynthesize_tts,
                            size="1",
                            variant="soft",
                            color_scheme="blue",
                            cursor="pointer",
                        ),
                        spacing="2",
                        align="center",
                    ),
                    # HTML5 Audio Element - only show when audio exists
                    rx.cond(
                        AIState.tts_audio_path != "",
                        rx.el.audio(
                            src=AIState.tts_audio_path,
                            id="tts-audio-player",
                            controls=True,
                            autoPlay=True,  # Auto-play when audio element is mounted
                            key="tts-audio-" + AIState.tts_trigger_counter.to(str),  # Force remount on new audio
                            style={"width": "100%", "height": "40px", "margin_top": "8px"},
                        ),
                        # Placeholder when no audio yet - shows hint
                        rx.text(
                            t("tts_regenerate_hint"),
                            font_size="11px",
                            color="#888",
                            margin_top="8px",
                            font_style="italic",
                        ),
                    ),
                    padding="3",
                    background_color="rgba(66, 135, 245, 0.08)",
                    border_radius="8px",
                    border=f"1px solid {COLORS['accent_blue']}",
                    width="100%",
                    margin_top="4",
                    margin_bottom="4",
                ),
            ),

            # Input controls (below chat history for easy access after reading)
            rx.box(
                left_column(),
                padding="4",
                background_color=COLORS["card_bg"],
                border_radius="12px",
                border=f"1px solid {COLORS['border']}",
                width="100%",
            ),

            # Debug Console & Settings side-by-side (bottom)
            # Desktop: Debug Console flexibel (1fr), Settings schmaler (max 360px)
            # Mobile: Automatisches Umbrechen via CSS Container Query (custom.css)
            rx.box(
                rx.box(
                    debug_console(),
                    settings_accordion(),
                    class_name="debug-settings-grid",
                    width="100%",
                ),
                class_name="debug-settings-container",
                width="100%",
            ),

            spacing="4",
            width="100%",
            padding="16",  # Padding rundherum (64px) - deutlich größer!
            max_width="1200px",  # Festgelegte maximale Breite
            margin="0 auto",  # Zentriert
            background_color=COLORS["page_bg"],  # Explizite Hintergrundfarbe
        ),

        width="100%",
        min_height="100vh",
        background_color=COLORS["page_bg"],
        display="flex",
        justify_content="center",
    )


# ==============================================================
# Note: Automatik-LLM Preloading moved to State.on_load()
# ==============================================================
# Model preloading now happens in state.py initialize_backend()
# when the user first opens the page. This ensures:
# 1. Models are loaded from State settings (not hardcoded)
# 2. Available models list is populated before preloading
# 3. Everything happens in one place (cleaner architecture)


# Create app (API routes are mounted separately below)
app = rx.App(
    stylesheets=[
        "/custom.css",  # Custom CSS for dark theme
    ],
    head_components=[
        # SVG Favicon - uses system emoji font for consistent 🎩 display
        rx.el.link(rel="icon", type="image/svg+xml", href="/favicon.svg"),
    ],
)

# Mount REST API routes directly on Reflex's backend
# This avoids the "ASGI flow error: Connection already upgraded" bug
# that occurs when using api_transformer with WebSocket connections
from .lib.api import api_app
app._api.mount("/api", api_app)
