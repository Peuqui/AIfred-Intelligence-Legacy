"""
AIfred Intelligence - Reflex Edition

Full Gradio-Style UI with Single Column Layout
"""

import reflex as rx
from .state import AIState
from .theme import COLORS


def t(key: str) -> rx.Var:
    """
    Translation helper that returns German or English text based on state
    """
    # Define translation pairs directly since Reflex needs static values
    de_text = {
        "voice_input": "🎙️ Spracheingabe",
        "audio_input_placeholder": "Audio-Eingabe (Microphone Recording)",
        "stt_not_ported": "⚠️ STT/TTS noch nicht portiert - Coming Soon!",
        "tip_automatic_transcription": "💡 Tipp: Nach dem Stoppen läuft automatisch die Transkription",
        "text_input": "⌨️ Texteingabe",
        "enter_your_question": "Oder schreibe hier deine Frage...",
        "research_mode": "🎯 Recherche-Modus",
        "research_mode_auto": "🤖 Automatik (KI entscheidet)",
        "research_mode_none": "🧠 Eigenes Wissen (schnell)",
        "research_mode_quick": "⚡ Web-Suche Schnell (3 beste)",
        "research_mode_deep": "🔍 Web-Suche Ausführlich (7 beste)",
        "choose_research_mode": "Wähle, wie der Assistant Fragen beantwortet",
        "send_text": "💬 Senden",
        "clear_chat": "🗑️ Chat löschen",
        "share_chat": "🔗 Chat teilen",
        "llm_parameters": "⚙️ LLM-Parameter (Erweitert)",
        "temperature": "🌡️ Temperature",
        "current": "Aktuell:",
        "temperature_info": "0.0 = deterministisch, 0.2 = fakten, 0.8 = ausgewogen, 1.5+ = kreativ",
        "context_window": "📦 Context Window (num_ctx)",
        "context_window_info": "Auto-berechnet basierend auf Message-Größe",
        "automatic_decision": "Automatik-Entscheidung ...",
        "web_scraping": "Web-Scraping",
        "compressing_context": "Komprimiere Kontext ...",
        "generating_answer": "Generiere Antwort ...",
        "websites_unreachable": "Website nicht erreichbar",
        "websites_unreachable_plural": "Websites nicht erreichbar",
        "input": "Eingabe:",
        "ai_response": "AI Antwort:",
        "tts_output": "🔊 Sprachausgabe (AI-Antwort)",
        "tts_enabled": "Sprachausgabe aktiviert",
        "tts_regenerate": "🔄 Neu generieren",
        "tts_not_ported": "⚠️ TTS noch nicht portiert - Coming Soon!",
        "chat_history": "💬 Chat Verlauf",
        "messages_count": "messages",
        "debug_console": "🐛 Debug Console",
        "live_debug_output": "Live Debug-Output: LLM-Starts, Entscheidungen, Statistiken",
        "auto_scroll": "Auto-Scroll",
        "settings": "⚙️ Einstellungen",
        "ui_language": "🌐 UI Sprache:",
        "backend": "Backend:",
        "main_llm": "Haupt-LLM:",
        "automatic_llm": "Automatik-LLM:",
        "vision_llm": "Vision-LLM:",
        "system_control": "🔄 System-Steuerung",
        "restart_ollama": "🔄 Ollama Neustart",
        "restart_vllm": "🔄 vLLM Neustart",
        "restart_aifred": "🔄 AIfred Neustart",
        "ollama_restart_info": "ℹ️ Neustart: Stoppt laufende Generierungen, lädt Models neu",
        "vllm_restart_info": "ℹ️ Neustart: Stoppt vLLM Server, startet neu mit gewähltem Modell",
        "backend_restart_info": "ℹ️ Neustart: Startet Backend neu",
        "chat_preserved": "(Chats bleiben erhalten)",
        "aifred_restart_warning": "⚠️ AIfred-Neustart: Löscht ALLE Chats, Caches und Debug-Logs komplett!",
        "aifred_intelligence": "🎩 AIfred Intelligence",
        "subtitle": "AI at your service • Benannt nach Alfred (Großvater) und Wolfgang Alfred (Vater)",
    }
    
    en_text = {
        "voice_input": "🎙️ Voice Input",
        "audio_input_placeholder": "Audio Input (Microphone Recording)",
        "stt_not_ported": "⚠️ STT/TTS not yet ported - Coming Soon!",
        "tip_automatic_transcription": "💡 Tip: Automatic transcription runs after stopping",
        "text_input": "⌨️ Text Input",
        "enter_your_question": "Or write your question here...",
        "research_mode": "🎯 Research Mode",
        "research_mode_auto": "🤖 Automatic (AI decides)",
        "research_mode_none": "🧠 Own Knowledge (fast)",
        "research_mode_quick": "⚡ Web Search Quick (3 best)",
        "research_mode_deep": "🔍 Web Search Detailed (7 best)",
        "choose_research_mode": "Choose how the assistant answers questions",
        "send_text": "💬 Send Text",
        "clear_chat": "🗑️ Clear Chat",
        "share_chat": "🔗 Share Chat",
        "llm_parameters": "⚙️ LLM Parameters (Advanced)",
        "temperature": "🌡️ Temperature",
        "current": "Current:",
        "temperature_info": "0.0 = deterministic, 0.2 = factual, 0.8 = balanced, 1.5+ = creative",
        "context_window": "📦 Context Window (num_ctx)",
        "context_window_info": "Auto-calculated based on message size",
        "automatic_decision": "Automatic decision ...",
        "web_scraping": "Web Scraping",
        "compressing_context": "Compressing Context ...",
        "generating_answer": "Generating Answer ...",
        "websites_unreachable": "Website unreachable",
        "websites_unreachable_plural": "Websites unreachable",
        "input": "Input:",
        "ai_response": "AI Response:",
        "tts_output": "🔊 Text-to-Speech (AI Answer)",
        "tts_enabled": "Text-to-Speech enabled",
        "tts_regenerate": "🔄 Regenerate",
        "tts_not_ported": "⚠️ TTS not yet ported - Coming Soon!",
        "chat_history": "💬 Chat History",
        "messages_count": "messages",
        "debug_console": "🐛 Debug Console",
        "live_debug_output": "Live Debug Output: LLM starts, decisions, statistics",
        "auto_scroll": "Auto-Scroll",
        "settings": "⚙️ Settings",
        "ui_language": "🌐 UI Language:",
        "backend": "Backend:",
        "main_llm": "Main LLM:",
        "automatic_llm": "Automatic LLM:",
        "vision_llm": "Vision LLM:",
        "system_control": "🔄 System Control",
        "restart_ollama": "🔄 Ollama Restart",
        "restart_vllm": "🔄 vLLM Restart",
        "restart_aifred": "🔄 Restart AIfred",
        "ollama_restart_info": "ℹ️ Restart: Stops ongoing generations, reloads models",
        "vllm_restart_info": "ℹ️ Restart: Stops vLLM server, restarts with selected model",
        "backend_restart_info": "ℹ️ Restart: Restarts backend",
        "chat_preserved": "(Chats are preserved)",
        "aifred_restart_warning": "⚠️ AIfred restart: Deletes ALL chats, caches and debug logs completely!",
        "aifred_intelligence": "🎩 AIfred Intelligence",
        "subtitle": "AI at your service • Named after Alfred (grandfather) and Wolfgang Alfred (father)",
    }
    
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
                rx.text("Aufnahme", font_size="16px", display=["none", "none", "inline"]),  # Hide text on mobile
                id="recording-button",
                size="4",
                variant="soft",
                color_scheme="green",
                padding_y="24px",
                on_click=AIState.toggle_audio_recording,  # Trigger JavaScript via State handler
                disabled=AIState.is_generating,
            ),

            # Camera button (only visible if browser supports camera)
            rx.cond(
                AIState.camera_available,
                rx.upload(
                    rx.button(
                        rx.icon("camera", size=20),
                        rx.text("Kamera", font_size="16px", display=["none", "none", "inline"]),  # Hide text on mobile
                        size="4",
                        variant="soft",
                        color_scheme="red",
                        padding_y="24px",
                        disabled=AIState.is_generating | (AIState.pending_images.length() >= AIState.max_images_per_message),
                    ),
                    id="camera-upload",
                    accept={"image/*": []},  # Accept images from camera
                    capture="environment",  # Use rear camera (change to "user" for front camera)
                    max_files=1,  # Camera captures one photo at a time
                    on_drop=AIState.handle_camera_upload,  # Kamera-Handler kürzt Dateinamen
                    multiple=False,
                    border="none",
                    padding="0",
                ),
            ),

            # Upload button with drag & drop
            rx.upload(
                rx.button(
                    rx.icon("image", size=20),
                    rx.text("Bild hochladen", font_size="16px"),
                    size="4",
                    variant="soft",
                    color_scheme="red",
                    padding_y="24px",
                    disabled=AIState.is_generating | (AIState.pending_images.length() >= AIState.max_images_per_message),
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
                    rx.text("🎤 Audio", font_size="16px", display=["none", "none", "inline"]),  # Hide text on mobile
                    size="4",
                    variant="soft",
                    color_scheme="blue",
                    padding_y="24px",
                    disabled=AIState.is_generating,
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
                    rx.text("Alle löschen", font_size="16px"),
                    size="4",
                    variant="soft",
                    color_scheme="red",
                    padding_y="24px",
                    on_click=AIState.clear_pending_images,
                )
            ),

            spacing="2",
            width="100%",
            justify_content="flex-start",  # Buttons linksbündig
        ),

        # Row 2: Transkription bearbeiten Toggle (direkt unter Aufnahme-Button)
        rx.hstack(
            rx.text("Transkription bearbeiten:", font_size="11px", font_weight="500"),
            rx.switch(
                checked=AIState.show_transcription,
                on_change=AIState.toggle_show_transcription,
                size="1",
            ),
            rx.text(
                rx.cond(
                    AIState.show_transcription,
                    "✏️ Text editieren",
                    "🚀 Direkt senden"
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

        # Row 3: Hint text - linksbündig
        rx.text(
            "💡 Ziehe Bilder auf den Button oder klicke zum Auswählen",
            font_size="11px",
            color=COLORS["text_muted"],
            width="100%",
            text_align="left",  # Linksbündig
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
                            title="Zuschneiden",
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
            rx.cond(
                AIState.ui_language == "de",
                "📝 Texteingabe",
                "📝 Text Input"
            ),
            size="2"
        ),
        rx.text_area(
            placeholder=rx.cond(
                AIState.ui_language == "de",
                "Schreibe hier deine Frage...",
                "Write your question here..."
            ),
            value=AIState.current_user_input,
            on_change=AIState.set_user_input,
            width="100%",
            rows="5",
            disabled=AIState.is_generating | AIState.is_compressing,
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
            rx.text(t("research_mode"), font_weight="bold", font_size="12px"),
            rx.radio(
                [
                    rx.cond(AIState.ui_language == "de", "🤖 Automatik (KI entscheidet)", "🤖 Automatic (AI decides)"),
                    rx.cond(AIState.ui_language == "de", "🧠 Eigenes Wissen (schnell)", "🧠 Own Knowledge (fast)"),
                    rx.cond(AIState.ui_language == "de", "⚡ Web-Suche Schnell (3 beste)", "⚡ Web Search Quick (3 best)"),
                    rx.cond(AIState.ui_language == "de", "🔍 Web-Suche Ausführlich (7 beste)", "🔍 Web Search Detailed (7 best)")
                ],
                value=AIState.research_mode_display,
                on_change=AIState.set_research_mode_display,
                spacing="2",
            ),
            rx.text(
                t("choose_research_mode"),
                font_size="12px",
                color=COLORS["text_secondary"],
            ),
            width="100%",
        ),

        # Temperature Control Section (visible, compact - 60% width)
        rx.hstack(
            rx.hstack(
                # Slider
                rx.vstack(
                    rx.hstack(
                        rx.text("🌡️ Temperature:", font_weight="bold", font_size="12px"),
                        rx.text(
                            f"{AIState.temperature:.1f}",
                            font_size="11px",
                            color=COLORS["text_secondary"],
                        ),
                        spacing="2",
                    ),
                    rx.slider(
                        value=[AIState.temperature],  # REACTIVE: value statt default_value!
                        min=0.0,
                        max=2.0,
                        step=0.1,
                        on_change=AIState.set_temperature,
                        width="100%",
                    ),
                    flex="1",
                    spacing="1",
                ),
                # Toggle Button (rechts neben Slider)
                rx.vstack(
                    rx.text(
                        rx.cond(
                            AIState.temperature_mode == "manual",
                            "✋ Manual",
                            "🤖 Auto"
                        ),
                        font_weight="bold",
                        font_size="11px",
                        width="70px",  # Feste Breite verhindert Springen
                        text_align="center",
                    ),
                    rx.switch(
                        checked=AIState.temperature_mode == "manual",
                        on_change=AIState.set_temperature_mode,
                    ),
                    spacing="1",
                    align_items="center",
                ),
                spacing="3",
                width="60%",  # Nur 60% statt 100%
                align_items="flex-end",
            ),
            width="100%",
        ),
        # Info Text
        rx.text(
            rx.cond(
                AIState.temperature_mode == "manual",
                rx.cond(AIState.ui_language == "de", "Slider-Wert wird verwendet", "Slider value is used"),
                rx.cond(AIState.ui_language == "de", "Intent-Detection wählt optimale Temperature", "Intent-Detection chooses optimal temperature"),
            ),
            font_size="11px",
            color=COLORS["text_secondary"],
            font_style="italic",
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
                loading=AIState.is_generating | AIState.is_compressing,
                disabled=AIState.is_generating | AIState.is_compressing,
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
                disabled=AIState.is_generating | AIState.is_compressing,  # Deaktiviert während Inferenz und Kompression
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
                disabled=AIState.is_generating | AIState.is_compressing,
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


def llm_parameters_accordion() -> rx.Component:
    """LLM Parameters in collapsible accordion - Kompakt"""
    return rx.accordion.root(
        rx.accordion.item(
            header=rx.box(
                rx.text(
                    rx.cond(
                        AIState.ui_language == "de",
                        "⚙️ LLM-Parameter (Erweitert)",
                        "⚙️ LLM Parameters (Advanced)"
                    ),
                    font_weight="500",
                    font_size="12px",
                    color=COLORS["text_primary"]
                ),
                padding_y="2",  # Weniger Padding oben/unten
            ),
            content=rx.vstack(
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

                    # Radio Buttons für Mode Selection (nur Deutsch für Konsistenz)
                    rx.radio(
                        ["🛡️ Auto (VRAM-optimiert) - Empfohlen", "⚠️ Auto (Modell-Maximum) - Risiko CPU-Offload", "🔧 Manuell"],
                        default_value="🛡️ Auto (VRAM-optimiert) - Empfohlen",
                        on_change=AIState.set_num_ctx_mode_from_display,
                        direction="column",
                        spacing="2",
                        size="2",
                    ),

                    # Manual Input (immer sichtbar, aber disabled wenn nicht manual)
                    rx.vstack(
                        rx.input(
                            placeholder=rx.cond(
                                AIState.ui_language == "de",
                                "z.B. 16384",
                                "e.g. 16384"
                            ),
                            value=AIState.num_ctx_manual,
                            on_change=AIState.set_num_ctx_manual,
                            type="number",
                            width="100%",
                            disabled=AIState.num_ctx_mode != "manual",
                            opacity=rx.cond(
                                AIState.num_ctx_mode == "manual",
                                "1.0",
                                "0.5"
                            ),
                        ),
                        rx.text(
                            rx.cond(
                                AIState.ui_language == "de",
                                f"Wert: {AIState.num_ctx_manual:,} tokens",
                                f"Value: {AIState.num_ctx_manual:,} tokens"
                            ),
                            font_size="11px",
                            color=COLORS["text_secondary"],
                        ),
                        spacing="1",
                        width="100%",
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
        collapsible=True,  # WICHTIG: Macht Accordion schließbar!
        color_scheme="gray",
        variant="soft",
    )


def left_column() -> rx.Component:
    """Complete left column with all input controls"""
    return rx.vstack(
        audio_input_section(),
        text_input_section(),
        llm_parameters_accordion(),
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

    phase_text = rx.cond(
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
                                f"{failed_sources.length()} Quellen nicht verfügbar",
                                font_weight="500",
                                font_size="13px",
                                color="#cc6a00",  # Dunkleres Orange
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


def render_chat_message(msg: dict) -> rx.Component:
    """
    Rendert eine einzelne Chat-Message (User+AI oder Summary).

    msg ist ein Dict mit:
    - user_msg: User-Nachricht
    - ai_msg: AI-Nachricht (bereinigt)
    - failed_sources: Liste der fehlgeschlagenen URLs
    """
    # Check ob es eine Summary ist (leerer User-Teil + "[📊 Komprimiert" am Anfang)
    # Verwende Reflex bitwise operators: & statt 'and'
    is_summary = (msg["user_msg"] == "") & msg["ai_msg"].startswith("[📊 Komprimiert")

    return rx.cond(
        is_summary,
        # Summary-Anzeige mit Collapsible (vereinfacht für Reflex)
        rx.box(
            rx.accordion.root(
                rx.accordion.item(
                    value="summary_main",
                    header=rx.box(
                        rx.hstack(
                            rx.text("📊", font_size="14px"),
                            rx.text(
                                "Komprimierte Messages",  # Fester Text statt StringVar-Operation
                                font_weight="bold",
                                font_size="13px",
                                color=COLORS["accent_warning"]
                            ),
                            spacing="2",
                            align="center",
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
                            msg["ai_msg"],  # Zeige den kompletten Summary-Text
                            color=COLORS["text_primary"],
                            font_size="12px"
                        ),
                        padding="3",
                        background_color="rgba(255, 165, 0, 0.05)",  # Leichter Orange-Tint
                        border_radius="6px",
                        border=f"1px solid {COLORS['border']}",
                        width="100%",
                        max_height="600px",  # Scrollbar bei sehr langen Summaries
                        overflow_y="auto",
                    ),
                ),
                collapsible=True,
                variant="soft",
                width="100%",
            ),
            background_color="rgba(255, 165, 0, 0.1)",  # Orange Hintergrund für Container
            padding="3",
            border_radius="8px",
            border=f"1px solid {COLORS['accent_warning']}",
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
                        rx.markdown(msg["user_msg"], color=COLORS["user_text"], font_size="13px"),
                        background_color=COLORS["user_msg"],
                        padding="3",
                        border_radius="6px",
                        max_width="70%",
                    ),
                    rx.text("👤", font_size="13px"),
                    spacing="2",
                    align="start",
                    justify="end",
                    width="100%",
                ),
                background_color="rgba(255, 255, 255, 0.03)",
                padding="2",
                border_radius="8px",
                width="100%",
            ),
            # Failed Sources (wenn vorhanden) - ZWISCHEN User und AI Message
            render_failed_sources_inline(msg["failed_sources"]),
            # AI message (links, bis 100% wenn nötig) - mit hellgrauem Container
            rx.box(
                rx.hstack(
                    rx.text("🤖", font_size="13px"),
                    rx.box(
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
                width="100%",
            ),
            spacing="3",
            width="100%",
        )
    )


def chat_history_display() -> rx.Component:
    """Full chat history (like Gradio chatbot) - Collapsible"""
    # Loading spinner während Initialisierung oder Backend-Wechsel
    loading_spinner = rx.vstack(
        rx.spinner(size="3", color="orange"),
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
        rx.text(
            "Bitte warten, Backend startet (~40-70 Sekunden)",
            font_size="11px",
            color=COLORS["text_muted"],
            font_style="italic",
            margin_top="1",
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

    chat_content = rx.cond(
        AIState.backend_initializing | AIState.backend_switching | AIState.vllm_restarting | AIState.is_koboldcpp_auto_restarting,
        loading_spinner,  # Show spinner during initialization, backend switch, vLLM restart, or KoboldCPP auto-restart
        rx.cond(
            AIState.auto_refresh_enabled,
            # Auto-Scroll enabled: rx.auto_scroll scrollt automatisch
            rx.auto_scroll(
                rx.foreach(
                    AIState.chat_history_parsed,
                    render_chat_message  # Verwende separate Render-Funktion
                ),
                id="chat-history-box",
                width="100%",
                min_height="360px",  # Dreifache Höhe (120*3)
                max_height="2400px",  # Höheres Maximum (1200*2)
                padding="4",
                background_color=COLORS["readonly_bg"],
                border_radius="8px",
                border=f"1px solid {COLORS['border']}",
                style={
                    "transition": "all 0.4s ease-out",
                },
            ),
            # Auto-Scroll disabled: normale rx.box (kein Scroll)
            rx.box(
                rx.foreach(
                    AIState.chat_history_parsed,
                    render_chat_message  # Verwende separate Render-Funktion
                ),
                id="chat-history-box",
                width="100%",
                min_height="360px",  # Dreifache Höhe (120*3)
                max_height="2400px",  # Höheres Maximum (1200*2)
                overflow_y="auto",
                padding="4",
                background_color=COLORS["readonly_bg"],
                border_radius="8px",
                border=f"1px solid {COLORS['border']}",
                style={
                    "transition": "all 0.4s ease-out",
                },
            ),
        ),
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
        height="935px",  # Fixed height - matches Settings panel when fully expanded
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
                # UI Language Selection
                rx.hstack(
                    rx.text(t("ui_language"), font_weight="bold", font_size="12px"),
                    rx.select(
                        ["de", "en"],
                        value=AIState.ui_language,
                        on_change=AIState.set_ui_language,
                        size="2",
                    ),
                    spacing="3",
                    align="center",
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
                            ),
                            value=AIState.backend_type,
                            on_change=AIState.switch_backend,
                            size="2",
                            disabled=AIState.backend_switching,
                        ),
                    ),
                    rx.cond(
                        AIState.backend_switching,
                        rx.hstack(
                            rx.spinner(size="1", color="orange"),
                            rx.badge("Switching...", color_scheme="orange"),
                            spacing="2",
                            align="center",
                        ),
                        rx.cond(
                            AIState.backend_healthy,
                            rx.badge(AIState.backend_info, color_scheme="green"),
                            rx.badge(AIState.backend_info, color_scheme="red"),
                        ),
                    ),
                    spacing="3",
                    align="center",
                ),

                # GPU Info: Show detected GPU and filtered backends
                rx.cond(
                    AIState.gpu_detected,
                    rx.box(
                        rx.text(
                            f"🎮 GPU: {AIState.gpu_display_text}",
                            font_size="10px",
                            font_weight="500",
                            color="#2a9d8f",
                        ),
                        padding="4px 8px",
                        background="rgba(42, 157, 143, 0.1)",
                        border_radius="4px",
                        margin_top="4px",
                    ),
                ),

                # Backend Compatibility Info: Show why backends are filtered
                rx.cond(
                    AIState.gpu_detected & (AIState.gpu_compute_cap < 7.0),
                    rx.box(
                        rx.text(
                            "ℹ️ Backend-Einschränkung",
                            font_size="11px",
                            font_weight="600",
                            color="#b71c1c",  # Dark red (dezent)
                        ),
                        rx.text(
                            "vLLM & TabbyAPI benötigen Compute Capability 7.0+ und schnelles FP16.",
                            font_size="10px",
                            color="#666",
                            margin_top="2px",
                        ),
                        rx.text(
                            f"Deine GPU ({AIState.gpu_name}) hat Compute {AIState.gpu_compute_cap} → Nur Ollama verfügbar.",
                            font_size="10px",
                            color="#666",
                            margin_top="2px",
                        ),
                        rx.text(
                            "💡 Ollama nutzt INT8/Q4-Quantisierung und funktioniert optimal auf älteren GPUs!",
                            font_size="10px",
                            color="#2a9d8f",
                            margin_top="4px",
                            font_style="italic",
                        ),
                        padding="8px",
                        background="rgba(183, 28, 28, 0.08)",  # Dark red transparent background (dezent)
                        border_radius="4px",
                        margin_top="8px",
                        border_left="3px solid #b71c1c",  # Dark red border
                    ),
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

                # Model Selection - Mobile: Native select, Desktop: Radix UI
                rx.hstack(
                    rx.text(t("main_llm"), font_weight="bold", font_size="12px"),
                    rx.cond(
                        AIState.is_mobile,
                        # MOBILE: Native HTML <select> (simple list)
                        native_select_model(
                            AIState.selected_model,  # Display name with size
                            AIState.set_selected_model,  # Original handler
                            AIState.backend_switching,
                            AIState.available_models,  # Simple list of display names
                        ),
                        # DESKTOP: Radix UI Select
                        rx.select(
                            AIState.available_models,
                            value=AIState.selected_model,
                            on_change=AIState.set_selected_model,
                            size="2",
                            position="popper",  # Better mobile positioning (adapts to viewport)
                            disabled=AIState.backend_switching,  # Disable during backend switch
                        ),
                    ),
                    spacing="3",
                    align="center",
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

                # Thinking Mode Toggle (für alle Modelle sichtbar)
                rx.divider(margin_top="12px", margin_bottom="12px"),
                rx.vstack(
                    rx.hstack(
                        rx.text("🧠 Thinking Mode:", font_weight="bold", font_size="12px"),
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
                        "ℹ️ Chain-of-Thought Reasoning für komplexe Aufgaben",
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
                            f"⚠️ Nicht verfügbar für {AIState.thinking_mode_warning}",
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
                            rx.text("📏 YaRN Context Extension:", font_weight="bold", font_size="12px"),
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
                                    rx.text("Faktor:", font_size="11px", font_weight="500"),
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
                                            "(auto-detect erst nach Start)"
                                        ),
                                        font_size="10px",
                                        color="#999",
                                    ),
                                    rx.button(
                                        "Apply YaRN",
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
                                        f"📏 Maximum: ~{AIState.yarn_max_factor:.1f}x (aus Test ermittelt)",
                                        font_size="10px",
                                        color="#ff9800",  # Orange for better visibility
                                        font_weight="500",
                                        margin_top="2px",
                                    ),
                                    # Maximum unknown (not tested yet)
                                    rx.text(
                                        "📏 Maximum: Unbekannt (wird beim Start getestet)",
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
                                f"ℹ️ Modell: {(AIState.vllm_native_context / 1000).to(int)}K nativ | HW-Limit: {(AIState.vllm_max_tokens / 1000).to(int)}K. Benötigt Backend-Neustart!",
                                font_size="10px",
                                color="#999",
                                line_height="1.3",
                            ),
                            rx.text(
                                "ℹ️ Context-Limits werden beim ersten vLLM-Start automatisch erkannt",
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
                        rx.text("🔊 Sprachausgabe (TTS):", font_weight="bold", font_size="12px"),
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
                                rx.text("Engine:", font_size="11px", font_weight="500", width="80px"),
                                rx.select(
                                    ["Edge TTS (Cloud, beste Qualität)", "Piper TTS (Lokal, Offline)", "eSpeak (Roboter, Offline)"],
                                    value=AIState.tts_engine,
                                    on_change=AIState.set_tts_engine,
                                    size="1",
                                    width="100%",
                                ),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            # Voice Selection (dynamic based on engine)
                            rx.hstack(
                                rx.text("Stimme:", font_size="11px", font_weight="500", width="80px"),
                                rx.select(
                                    AIState.available_tts_voices,
                                    value=AIState.tts_voice,
                                    on_change=AIState.set_tts_voice,
                                    size="1",
                                    width="100%",
                                ),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            # Auto-Play Toggle (Speed control available in HTML5 audio player's 3-dot menu)
                            rx.hstack(
                                rx.text("Auto-Play:", font_size="11px", font_weight="500", width="80px"),
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
                    rx.text("🎤 Spracheingabe (STT):", font_weight="bold", font_size="12px"),
                    # Whisper Model Selection
                    rx.hstack(
                        rx.text("Modell:", font_size="11px", font_weight="500", width="80px"),
                        rx.select(
                            ["tiny (39MB, schnell, englisch)", "base (74MB, schneller, multilingual)", "small (466MB, bessere Qualität, multilingual)", "medium (1.5GB, hohe Qualität, multilingual)", "large-v3 (2.9GB, beste Qualität, multilingual)"],
                            value=AIState.whisper_model_name,
                            on_change=AIState.set_whisper_model,
                            size="1",
                            width="100%",
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
                # Info Text for Settings Reset
                rx.vstack(
                    rx.text(
                        rx.cond(
                            AIState.ui_language == "de",
                            "ℹ️ F5 / Browser neu laden: Lädt gespeicherte Einstellungen",
                            "ℹ️ F5 / Reload browser: Loads saved settings"
                        ),
                        font_size="10px",
                        color=COLORS["text_secondary"],
                        font_style="italic",
                    ),
                    rx.text(
                        rx.cond(
                            AIState.ui_language == "de",
                            "ℹ️ Button: Lädt Standard-Grundeinstellungen (config.py)",
                            "ℹ️ Button: Loads default settings (config.py)"
                        ),
                        font_size="10px",
                        color=COLORS["text_secondary"],
                        font_style="italic",
                    ),
                    spacing="1",
                    width="100%",
                ),
                rx.vstack(
                    rx.text(
                        rx.cond(
                            AIState.backend_type == "ollama",
                            t("ollama_restart_info"),
                            rx.cond(
                                AIState.backend_type == "vllm",
                                t("vllm_restart_info"),
                                t("backend_restart_info")
                            )
                        ),
                        font_size="11px",
                        color="#d4913d",  # Dunkles Orange - gut lesbar
                        line_height="1.5",
                    ),
                    rx.text(
                        t("chat_preserved"),
                        font_size="10px",
                        color="#a67a30",  # Etwas dunkler für Zusatzinfo
                        line_height="1.3",
                        margin_top="-2px",  # Näher an die Zeile darüber
                        margin_left="16px",  # Eingerückt
                    ),
                    rx.text(
                        t("aifred_restart_warning"),
                        font_size="11px",
                        color="#d4913d",  # Dunkles Orange - gut lesbar
                        line_height="1.5",
                    ),
                    spacing="2",
                    width="100%",
                ),

                spacing="4",
                width="100%",
            ),
        ),
        collapsible=True,  # WICHTIG: Macht Accordion schließbar!
        default_value="settings",  # Standardmäßig geöffnet
        color_scheme="gray",
        variant="soft",
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
                    rx.text("Bild zuschneiden", color="white", font_weight="bold"),
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
                    "Ziehe die Ecken oder Kanten",
                    font_size="12px",
                    color="#888",
                    text_align="center",
                ),

                # Buttons
                rx.hstack(
                    rx.button(
                        "Abbrechen",
                        on_click=AIState.cancel_crop,
                        variant="soft",
                        color_scheme="gray",
                        size="3",
                    ),
                    rx.button(
                        rx.hstack(
                            rx.icon("check", size=16),
                            rx.text("Zuschneiden"),
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
    // Find the auto-scroll switch by looking for the switch near the "Auto-Scroll" text
    // The switch has data-state="checked" or "unchecked"
    const switches = document.querySelectorAll('[role="switch"]');
    for (let sw of switches) {
        // Check if this switch is the auto-scroll switch (near "Auto-Scroll" text)
        const parent = sw.closest('.rx-Flex');
        if (parent && parent.textContent.includes('Auto-Scroll')) {
            const isEnabled = sw.getAttribute('data-state') === 'checked';
            return isEnabled;
        }
    }
    return true; // Default to enabled if switch not found
}

function autoScrollElement(element) {
    if (element) {
        console.log('📜 Scrolling element:', element.id, 'scrollTop:', element.scrollTop, 'scrollHeight:', element.scrollHeight);
        element.scrollTop = element.scrollHeight;
    }
}

// Observer für Debug-Console und Chat-History Updates
const observerConfig = { childList: true, subtree: true };

const callback = function(mutationsList, observer) {
    const enabled = isAutoScrollEnabled();
    console.log('🔍 MutationObserver triggered, auto-scroll enabled:', enabled);

    // Make all links open in new tab (always, regardless of auto-scroll)
    makeLinksOpenInNewTab();

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
    const chatBox = document.getElementById('chat-history-box');
    if (chatBox) {
        autoScrollElement(chatBox);
    }
};

function syncDebugConsoleHeight() {
    // Find Settings Accordion using multiple strategies
    let settingsElement = null;
    let settingsAccordion = null;

    // Strategy 1: Find the AccordionRoot in the grid container
    const gridContainer = document.querySelector('.debug-settings-grid');
    if (gridContainer) {
        // Settings accordion is the second child in the grid
        const accordions = gridContainer.querySelectorAll('.rt-AccordionRoot');
        if (accordions.length >= 1) {
            // The settings accordion is the one NOT containing debug console
            for (let acc of accordions) {
                if (!acc.querySelector('#debug-console-box')) {
                    settingsAccordion = acc;
                    break;
                }
            }
        }
    }

    // Strategy 2: Fallback - find by accordion region role
    if (!settingsAccordion) {
        const accordionRegions = document.querySelectorAll('[role="region"]');
        for (let region of accordionRegions) {
            const header = region.previousElementSibling;
            if (header && (header.textContent.includes('Einstellungen') || header.textContent.includes('Settings'))) {
                settingsElement = region;
                settingsAccordion = region.closest('.rt-AccordionRoot');
                break;
            }
        }
    }

    const debugBox = document.getElementById('debug-console-box');

    if (settingsAccordion && debugBox) {
        // Get the full height of the settings accordion (including all expanded sections)
        const settingsRect = settingsAccordion.getBoundingClientRect();
        const settingsHeight = settingsAccordion.scrollHeight || settingsRect.height;

        // Set Debug Console to match (minimum 500px, maximum 1200px)
        const targetHeight = Math.min(1200, Math.max(500, settingsHeight));
        debugBox.style.height = targetHeight + 'px';

        // Log only if height changed significantly
        const currentHeight = parseInt(debugBox.style.height) || 500;
        if (Math.abs(currentHeight - targetHeight) > 10) {
            console.log('📏 Synced heights - Settings:', settingsHeight, 'Target:', targetHeight);
        }
    } else {
        // Fallback: set a reasonable default
        if (debugBox) {
            debugBox.style.height = '500px';
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

    const chatBox = document.getElementById('chat-history-box');
    if (chatBox) {
        console.log('✅ Found chat-history-box');
        const observer = new MutationObserver(callback);
        observer.observe(chatBox, observerConfig);
    } else {
        console.warn('❌ chat-history-box not found');
    }

    // Sync heights on accordion open/close - observe the entire settings grid
    const gridContainer = document.querySelector('.debug-settings-grid');
    if (gridContainer) {
        // Observe all accordion changes in the grid
        const accordions = gridContainer.querySelectorAll('.rt-AccordionRoot');
        for (let acc of accordions) {
            // Skip the debug console accordion
            if (acc.querySelector('#debug-console-box')) continue;

            // ResizeObserver for the entire accordion
            const resizeObserver = new ResizeObserver(() => {
                syncDebugConsoleHeight();
            });
            resizeObserver.observe(acc);

            // Also observe mutations (for accordion open/close)
            const mutationObserver = new MutationObserver(() => {
                // Delay to allow animation to complete
                setTimeout(syncDebugConsoleHeight, 100);
                setTimeout(syncDebugConsoleHeight, 300);
            });
            mutationObserver.observe(acc, { childList: true, subtree: true, attributes: true });

            console.log('✅ Height sync observers attached to settings accordion');
        }

        // Also observe all accordion triggers for click events
        const triggers = gridContainer.querySelectorAll('.rt-AccordionTrigger');
        triggers.forEach(trigger => {
            trigger.addEventListener('click', () => {
                // Sync after accordion animation (multiple times for smooth transition)
                setTimeout(syncDebugConsoleHeight, 50);
                setTimeout(syncDebugConsoleHeight, 150);
                setTimeout(syncDebugConsoleHeight, 350);
            });
        });
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

    // Retry after 500ms in case elements render later
    setTimeout(() => {
        setupObservers();
        makeLinksOpenInNewTab();
        syncDebugConsoleHeight();
    }, 500);

    // Retry after 1000ms
    setTimeout(() => {
        setupObservers();
        makeLinksOpenInNewTab();
        syncDebugConsoleHeight();
    }, 1000);
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
        rx.script(src="/custom.js?v=4"),

        # Crop Modal (rendered but hidden until open)
        crop_modal(),

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
            chat_history_display(),

            # TTS Audio Player (only visible if TTS enabled and audio exists)
            rx.cond(
                AIState.enable_tts & (AIState.tts_audio_path != ""),
                rx.box(
                    rx.vstack(
                        rx.hstack(
                            rx.text("🔊 Sprachausgabe:", font_weight="bold", font_size="13px", color=COLORS["accent_blue"]),
                            rx.text(
                                f"{AIState.tts_voice} • {AIState.tts_speed:.2f}x",
                                font_size="11px",
                                color=COLORS["text_muted"],
                            ),
                            rx.spacer(),
                            # Re-Synth Button (regenerate TTS for last response)
                            rx.button(
                                rx.hstack(
                                    rx.text("🔄", font_size="14px"),
                                    rx.text("Resynth", font_size="12px", font_weight="500"),
                                    spacing="1",
                                    align="center",
                                ),
                                on_click=AIState.resynthesize_tts,
                                disabled=AIState.is_generating,
                                size="1",
                                variant="soft",
                                color_scheme="blue",
                                title="Sprachausgabe neu generieren",
                                style={
                                    "min_width": "85px",
                                    "padding": "6px 12px",
                                    "cursor": "pointer",
                                    "&:hover:not([disabled])": {
                                        "background": "rgba(66, 135, 245, 0.3)",
                                    },
                                },
                            ),
                            spacing="2",
                            align="center",
                            width="100%",
                        ),
                        # Audio Player - simple player with autoPlay attribute
                        # Using rx.cond to switch between autoplay and non-autoplay versions
                        rx.cond(
                            AIState.tts_should_autoplay,
                            # Autoplay version - only rendered briefly when TTS completes
                            rx.el.audio(
                                src=AIState.tts_audio_path,
                                key=f"autoplay-{AIState.tts_audio_path}",  # Different key forces remount
                                id="tts-player",
                                controls=True,
                                autoPlay=True,  # HTML5 autoplay attribute
                                style={"width": "100%", "height": "40px"},
                            ),
                            # Normal version - no autoplay
                            rx.el.audio(
                                src=AIState.tts_audio_path,
                                key=AIState.tts_audio_path,
                                id="tts-player",
                                controls=True,
                                style={"width": "100%", "height": "40px"},
                            ),
                        ),
                        spacing="2",
                        width="100%",
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


# Create app
app = rx.App(
    stylesheets=[
        "/custom.css",  # Custom CSS for dark theme
    ],
)
