"""Input section components for AIfred UI: upload, text input, debug console."""

from __future__ import annotations

import reflex as rx

from ..state import AIState
from ..theme import COLORS
from .helpers import t

from .helpers import native_select_generic
from .settings_accordion import llm_parameters_accordion
from .chat_display import processing_progress_banner


# ============================================================
# IMAGE / AUDIO UPLOAD SECTION
# ============================================================


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

        # Row 1: Buttons (Aufnahme, Camera, Upload, Audio, Clear) - responsive
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
                min_width=["auto", "auto", "160px"],  # Fixed on desktop
                flex=["2 1 0%", "2 1 0%", "0 0 auto"],  # Mobile: 2x share, Desktop: auto
                width=["100%", "100%", "auto"],
                on_click=AIState.toggle_audio_recording,
                disabled=AIState.is_generating | AIState.is_uploading_image,
            ),

            # Camera button (only visible if browser supports camera) - with drag & drop tooltip
            rx.cond(
                AIState.camera_available,
                rx.upload(
                    rx.tooltip(
                        rx.button(
                            rx.icon("camera", size=20),
                            rx.text(t("camera"), font_size="16px", display=["none", "none", "inline"]),
                            size="4",
                            variant="soft",
                            color_scheme="red",
                            padding_y="24px",
                            width="100%",
                            disabled=AIState.is_generating | AIState.is_uploading_image | (AIState.pending_images.length() >= AIState.max_images_per_message),
                            on_click=AIState.on_camera_click,
                        ),
                        content=t("image_hint"),
                    ),
                    id="camera-upload",
                    accept={"image/*": []},
                    max_files=1,
                    on_drop=AIState.handle_camera_upload,
                    multiple=False,
                    border="none",
                    padding="0",
                    flex=["1 1 0%", "1 1 0%", "0 0 auto"],  # Mobile: 1x share, Desktop: auto
                ),
            ),

            # Upload button with drag & drop - with tooltip
            rx.upload(
                rx.tooltip(
                    rx.button(
                        rx.icon("image", size=20),
                        rx.text(t("upload_image"), font_size="16px", display=["none", "none", "inline"]),
                        size="4",
                        variant="soft",
                        color_scheme="red",
                        padding_y="24px",
                        width="100%",
                        disabled=AIState.is_generating | AIState.is_uploading_image | (AIState.pending_images.length() >= AIState.max_images_per_message),
                        on_click=AIState.on_file_picker_click,
                    ),
                    content=t("image_hint"),
                ),
                id="image-upload",
                accept={"image/*": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]},
                max_files=AIState.max_images_per_message,
                on_drop=AIState.handle_image_upload,
                multiple=True,
                border="none",
                padding="0",
                flex=["1 1 0%", "1 1 0%", "0 0 auto"],  # Mobile: 1x share, Desktop: auto
            ),

            # Audio File Upload Button
            rx.upload(
                rx.button(
                    rx.icon("disc-3", size=20),
                    rx.text(t("audio"), font_size="16px", display=["none", "none", "inline"]),
                    size="4",
                    variant="soft",
                    color_scheme="blue",
                    padding_y="24px",
                    width="100%",
                    disabled=AIState.is_generating | AIState.is_uploading_image,
                ),
                id="audio-upload",
                accept={"audio/*": [".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"]},
                max_files=1,
                on_drop=AIState.handle_audio_upload,
                multiple=False,
                border="none",
                padding="0",
                flex=["1 1 0%", "1 1 0%", "0 0 auto"],  # Mobile: 1x share, Desktop: auto
            ),

            # Hidden upload for MediaRecorder (JavaScript will populate this)
            rx.upload(
                rx.box(display="none"),
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
                    rx.text(t("clear_all"), font_size="16px", display=["none", "none", "inline"]),
                    size="4",
                    variant="soft",
                    color_scheme="red",
                    padding_y="24px",
                    on_click=AIState.clear_pending_images,
                )
            ),

            spacing="2",
            width="100%",
            justify_content="flex-start",
            flex_wrap="wrap",  # Wrap to next line on very narrow screens
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
                            border=f"1px solid {COLORS['border']}",
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
                            on_click=AIState.open_crop_modal(idx),  # type: ignore[call-arg, func-returns-value]
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
                            on_click=AIState.remove_pending_image(idx),  # type: ignore[call-arg, func-returns-value]
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


# ============================================================
# TEXT INPUT SECTION
# ============================================================


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
            rows="3",
            spell_check=False,
            disabled=AIState.is_generating | AIState.is_compressing | AIState.is_uploading_image,
            style={
                "field_sizing": "content",
                "min_height": "4.5em",
                "max_height": "22.5em",
                "overflow_y": "auto",
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
                                # Advocatus Diaboli deaktiviert v2.15.28 - Pro/Contra jetzt in Critical Review integriert
                                # rx.select.item(
                                #     rx.cond(AIState.ui_language == "de", "Advocatus Diaboli", "Devil's Advocate"),
                                #     value="devils_advocate"
                                # ),
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
                    rx.tooltip(
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
                        content=t("discussion_mode_tooltip"),
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
                # Max Debate Rounds +/- Buttons (visible for "auto_consensus" and "tribunal" modes)
                rx.cond(
                    (AIState.multi_agent_mode == "auto_consensus") | (AIState.multi_agent_mode == "tribunal"),
                    rx.hstack(
                        rx.text(t("max_debate_rounds"), font_size="11px"),
                        rx.hstack(
                            rx.icon_button(
                                rx.icon("circle-minus", size=18),
                                on_click=AIState.decrease_debate_rounds,
                                size="2",
                                variant="soft",
                                disabled=AIState.max_debate_rounds <= 1,
                                style={
                                    "background-color": COLORS["warning_bg"],
                                    "color": "#cc8800",
                                },
                            ),
                            rx.badge(
                                AIState.max_debate_rounds,
                                variant="soft",
                                font_size="11px",
                                font_weight="600",
                                padding_x="8px",
                                padding_y="2px",
                                style={
                                    "background-color": "#5d4200",
                                    "color": "#cc8800",
                                    "min-width": "24px",
                                    "text-align": "center",
                                },
                            ),
                            rx.icon_button(
                                rx.icon("circle-plus", size=18),
                                on_click=AIState.increase_debate_rounds,
                                size="2",
                                variant="soft",
                                disabled=AIState.max_debate_rounds >= 10,
                                style={
                                    "background-color": COLORS["warning_bg"],
                                    "color": "#cc8800",
                                },
                            ),
                            spacing="2",
                            align="center",
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
                disabled=AIState.is_generating | AIState.is_compressing | AIState.is_uploading_image | AIState.tts_regenerating,
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
                        "color": COLORS["primary_hover"] + " !important",
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
                color=rx.cond(
                    msg.contains("\u2717") | msg.contains("\u274c"),  # ✗ or ❌
                    "#ff6b6b",  # Rot für Fehler
                    COLORS["debug_text"],  # Matrix Grün
                ),
                white_space="pre",
            ),
        ),
        id="debug-console-box",
        width="100%",
        overflow_y="auto",
        padding="3",
        background_color=COLORS["debug_bg"],
        border_radius="8px",
        border=f"2px solid {COLORS['debug_border']}",
        style={
            "scroll-behavior": "smooth",
            "max-height": "var(--debug-max-height, 60vh)",
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
