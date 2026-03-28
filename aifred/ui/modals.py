"""Modal dialogs for AIfred UI."""

from __future__ import annotations

import reflex as rx

from ..state import AIState
from .helpers import t


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
                            # Tribunal
                            rx.table.row(
                                rx.table.cell("Tribunal"),
                                rx.table.cell(t("multi_agent_help_tribunal_flow")),
                                rx.table.cell(t("multi_agent_help_tribunal_decision")),
                            ),
                            # Symposion
                            rx.table.row(
                                rx.table.cell("Symposion"),
                                rx.table.cell(t("multi_agent_help_symposion_flow")),
                                rx.table.cell(t("multi_agent_help_symposion_decision")),
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


def reasoning_thinking_help_modal() -> rx.Component:
    """
    Fullscreen Overlay explaining Reasoning vs. Thinking toggles.
    Same visual style as multi_agent_help_modal().
    """
    return rx.cond(
        AIState.reasoning_thinking_help_open,
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
                on_click=AIState.close_reasoning_thinking_help,
            ),

            # Modal Content - zentriert
            rx.vstack(
                # Header
                rx.hstack(
                    rx.icon("lightbulb", size=24, color="#FFD700"),
                    rx.text(t("reasoning_thinking_help_title"), color="white", font_weight="bold", font_size="20px"),
                    spacing="3",
                    align="center",
                ),

                # Reasoning Section
                rx.vstack(
                    rx.text(t("reasoning_thinking_help_reasoning_title"), color="#FFA500", font_weight="bold", font_size="17px"),
                    rx.text(t("reasoning_thinking_help_reasoning_desc"), color="#ccc", font_size="15px"),
                    rx.text(t("reasoning_thinking_help_reasoning_effect"), color="#aaa", font_size="14px", font_style="italic"),
                    spacing="2",
                    width="100%",
                    padding="12px",
                    background_color="#2a2a2a",
                    border_radius="8px",
                ),

                # Thinking Section
                rx.vstack(
                    rx.text(t("reasoning_thinking_help_thinking_title"), color="#4FC3F7", font_weight="bold", font_size="17px"),
                    rx.text(t("reasoning_thinking_help_thinking_desc"), color="#ccc", font_size="15px"),
                    rx.text(t("reasoning_thinking_help_thinking_effect"), color="#aaa", font_size="14px", font_style="italic"),
                    spacing="2",
                    width="100%",
                    padding="12px",
                    background_color="#2a2a2a",
                    border_radius="8px",
                ),

                # Combinations Section
                rx.divider(color="#444", margin_y="10px"),
                rx.text(t("reasoning_thinking_help_combinations_title"), color="#FFD700", font_weight="bold", font_size="16px"),
                rx.vstack(
                    rx.hstack(
                        rx.text("💭+🧠", min_width="60px", font_size="16px"),
                        rx.text(t("reasoning_thinking_help_both_on"), color="#ccc", font_size="15px"),
                        spacing="2",
                        align="center",
                    ),
                    rx.hstack(
                        rx.text("💭", min_width="60px", font_size="16px"),
                        rx.text(t("reasoning_thinking_help_reasoning_only"), color="#ccc", font_size="15px"),
                        spacing="2",
                        align="center",
                    ),
                    rx.hstack(
                        rx.text("🧠", min_width="60px", font_size="16px"),
                        rx.text(t("reasoning_thinking_help_thinking_only"), color="#ccc", font_size="15px"),
                        spacing="2",
                        align="center",
                    ),
                    rx.hstack(
                        rx.text("—", min_width="60px", font_size="16px", color="#666"),
                        rx.text(t("reasoning_thinking_help_both_off"), color="#ccc", font_size="15px"),
                        spacing="2",
                        align="center",
                    ),
                    spacing="2",
                    width="100%",
                ),

                # Close button
                rx.button(
                    t("reasoning_thinking_help_close"),
                    on_click=AIState.close_reasoning_thinking_help,
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
                width="550px",
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


def login_dialog() -> rx.Component:
    """
    Fullscreen Overlay für Login/Registrierung.
    Zeigt Login-Form oder Registrierungs-Form basierend auf login_mode.
    Enter-Taste im Passwort-Feld löst Login/Register aus.
    """
    return rx.cond(
        AIState.login_dialog_open,
        # Fullscreen Overlay
        rx.box(
            # Backdrop (nicht klickbar - Login ist erforderlich)
            rx.box(
                position="absolute",
                top="0",
                left="0",
                width="100%",
                height="100%",
                background_color="rgba(0, 0, 0, 0.9)",
            ),

            # Modal Content - zentriert
            rx.vstack(
                # Logo/Header
                rx.vstack(
                    rx.text("🎩", font_size="48px"),
                    rx.text("AIfred Intelligence", color="white", font_weight="bold", font_size="24px"),
                    spacing="1",
                    align="center",
                ),

                # Form Container - wrapped in <form> for browser password manager
                rx.el.form(
                    rx.box(
                        rx.vstack(
                            # Mode Toggle
                            rx.hstack(
                                rx.button(
                                    "Anmelden",
                                    on_click=lambda: AIState.open_login_dialog("login"),  # type: ignore[arg-type]
                                    variant=rx.cond(AIState.login_mode == "login", "solid", "ghost"),
                                    color_scheme="orange",
                                    size="2",
                                    type="button",  # Prevent form submit
                                ),
                                rx.button(
                                    "Registrieren",
                                    on_click=lambda: AIState.open_login_dialog("register"),  # type: ignore[arg-type]
                                    variant=rx.cond(AIState.login_mode == "register", "solid", "ghost"),
                                    color_scheme="orange",
                                    size="2",
                                    type="button",  # Prevent form submit
                                ),
                                spacing="2",
                                justify="center",
                            ),

                            # Username Input (with autocomplete for browser password manager)
                            rx.input(
                                placeholder="Username",
                                value=AIState.login_username,
                                on_change=AIState.set_login_username,
                                name="username",
                                custom_attrs={"autocomplete": "username"},
                                width="100%",
                                size="3",
                            ),

                            # Password Input (Enter triggers login/register, autocomplete for password manager)
                            rx.input(
                                placeholder="Passwort",
                                type="password",
                                value=AIState.login_password,
                                on_change=AIState.set_login_password,
                                on_key_down=AIState.handle_login_key_down,
                                name="password",
                                custom_attrs={"autocomplete": "current-password"},
                                width="100%",
                                size="3",
                            ),

                            # Error Message
                            rx.cond(
                                AIState.login_error != "",
                                rx.text(AIState.login_error, color="red", font_size="14px"),
                            ),

                            # Submit Button
                            rx.cond(
                                AIState.login_mode == "login",
                                rx.button(
                                    "Anmelden",
                                    on_click=AIState.do_login,
                                    color_scheme="orange",
                                    width="100%",
                                    size="3",
                                    type="submit",
                                ),
                                rx.button(
                                    "Account erstellen",
                                    on_click=AIState.do_register,
                                    color_scheme="green",
                                    width="100%",
                                    size="3",
                                    type="submit",
                                ),
                            ),

                            spacing="4",
                            width="100%",
                        ),
                        background_color="#1a1a1a",
                        border_radius="12px",
                        padding="24px",
                        width="320px",
                        border="1px solid #333",
                    ),
                    on_submit=AIState.handle_login_submit,
                    method="post",
                ),

                spacing="6",
                align="center",
                position="absolute",
                top="50%",
                left="50%",
                transform="translate(-50%, -50%)",
            ),

            # Fullscreen container
            position="fixed",
            top="0",
            left="0",
            width="100vw",
            height="100vh",
            z_index="9999",
        ),
    )


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
                        rx.icon("rotate-ccw", size=16),
                        on_click=AIState.rotate_crop_image_left,
                        variant="soft",
                        color_scheme="blue",
                        size="3",
                        title="90° links",
                    ),
                    rx.button(
                        rx.icon("rotate-cw", size=16),
                        on_click=AIState.rotate_crop_image_right,
                        variant="soft",
                        color_scheme="blue",
                        size="3",
                        title="90° rechts",
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


def _document_row(doc: dict) -> rx.Component:
    """Single row in the document manager list."""
    return rx.hstack(
        rx.icon("file-text", size=16, color="#d29922"),
        rx.vstack(
            rx.text(
                doc["filename"],
                font_weight="bold",
                font_size="12px",
                color="white",
                cursor="pointer",
                on_click=AIState.preview_document(doc["filename"]),
                _hover={"text_decoration": "underline"},
            ),
            rx.text(
                doc["upload_date"],
                font_size="10px",
                color="#888",
            ),
            spacing="0",
        ),
        rx.spacer(),
        # Fixed-width columns for chunks + action icons
        rx.hstack(
            rx.text(
                doc["total_chunks"].to(str),
                font_size="10px",
                color="#aaa",
                min_width="20px",
                text_align="right",
            ),
            rx.icon_button(
                rx.icon("eye", size=16),
                size="1",
                variant="ghost",
                color_scheme="blue",
                on_click=AIState.preview_document(doc["filename"]),
                cursor="pointer",
            ),
            rx.link(
                rx.icon_button(
                    rx.icon("download", size=16),
                    size="1",
                    variant="ghost",
                    color_scheme="green",
                    cursor="pointer",
                ),
                href="/_upload/documents/" + doc["filename"].to(str),
                download=doc["filename"],
                is_external=True,
            ),
            rx.icon_button(
                rx.icon("trash-2", size=16),
                size="1",
                variant="ghost",
                color_scheme="red",
                on_click=AIState.delete_uploaded_document(doc["filename"]),
                cursor="pointer",
            ),
            spacing="1",
            align="center",
            flex_shrink="0",
        ),
        width="100%",
        padding="6px 8px",
        align="center",
        border_bottom="1px solid #2a2a2a",
        _hover={"background_color": "rgba(255, 255, 255, 0.05)"},
    )


def document_manager_modal() -> rx.Component:
    """Modal for managing uploaded documents."""
    return rx.cond(
        AIState.document_manager_open,
        rx.box(
            # Backdrop
            rx.box(
                position="absolute",
                top="0",
                left="0",
                width="100%",
                height="100%",
                background_color="#000000",
                on_click=AIState.close_document_manager,
            ),

            # Modal Content — two-column layout
            rx.vstack(
                # Header
                rx.hstack(
                    rx.icon("file-text", size=24, color="#d29922"),
                    rx.text(
                        t("doc_manager_title"),
                        color="white",
                        font_weight="bold",
                        font_size="18px",
                    ),
                    rx.spacer(),
                    # Close button in header
                    rx.icon_button(
                        rx.icon("x", size=18),
                        size="2",
                        variant="ghost",
                        color_scheme="gray",
                        on_click=AIState.close_document_manager,
                        cursor="pointer",
                    ),
                    width="100%",
                    align="center",
                ),

                # Two-column (desktop) / stacked (mobile): list | preview
                rx.flex(
                    # Left: Document list
                    rx.vstack(
                        rx.cond(
                            AIState.uploaded_documents.length() > 0,
                            rx.vstack(
                                rx.foreach(
                                    AIState.uploaded_documents,
                                    _document_row,
                                ),
                                spacing="2",
                                width="100%",
                            ),
                            rx.text(
                                t("doc_manager_empty"),
                                color="#888",
                                font_size="14px",
                                padding="20px 0",
                            ),
                        ),
                        # Status message
                        rx.cond(
                            AIState.document_upload_status != "",
                            rx.text(
                                AIState.document_upload_status,
                                font_size="12px",
                                color="#aaa",
                            ),
                        ),
                        flex=["1 1 100%", "1 1 100%", "0 0 35%"],
                        max_height=["40vh", "40vh", "70vh"],
                        overflow_y="auto",
                        padding_right=["0", "0", "15px"],
                        padding_bottom=["10px", "10px", "0"],
                        border_right=["none", "none", "1px solid #333"],
                        border_bottom=["1px solid #333", "1px solid #333", "none"],
                    ),

                    # Right: Preview
                    rx.vstack(
                        rx.cond(
                            AIState.document_preview_filename != "",
                            rx.vstack(
                                rx.hstack(
                                    rx.icon("eye", size=16, color="#58a6ff"),
                                    rx.text(
                                        AIState.document_preview_filename,
                                        color="#58a6ff",
                                        font_weight="bold",
                                        font_size="14px",
                                    ),
                                    rx.spacer(),
                                    rx.icon_button(
                                        rx.icon("x", size=14),
                                        size="1",
                                        variant="ghost",
                                        color_scheme="gray",
                                        on_click=AIState.close_document_preview,
                                        cursor="pointer",
                                    ),
                                    width="100%",
                                    align="center",
                                ),
                                rx.box(
                                    rx.text(
                                        AIState.document_preview_content,
                                        white_space="pre-wrap",
                                        font_size="12px",
                                        color="#ccc",
                                        font_family="monospace",
                                    ),
                                    max_height="65vh",
                                    overflow_y="auto",
                                    width="100%",
                                    padding="10px",
                                    background_color="rgba(0, 0, 0, 0.3)",
                                    border_radius="6px",
                                    border="1px solid #333",
                                ),
                                spacing="2",
                                width="100%",
                            ),
                            # Empty preview state
                            rx.vstack(
                                rx.icon("eye-off", size=32, color="#444"),
                                rx.text(
                                    rx.cond(
                                        AIState.ui_language == "de",
                                        "Klicke auf ein Dokument um es anzuzeigen",
                                        "Click a document to preview it",
                                    ),
                                    color="#666",
                                    font_size="13px",
                                ),
                                align="center",
                                justify="center",
                                height="100%",
                                spacing="3",
                            ),
                        ),
                        flex=["1 1 100%", "1 1 100%", "0 0 65%"],
                        max_height=["40vh", "40vh", "70vh"],
                        overflow_y="auto",
                        padding_left=["0", "0", "15px"],
                        padding_top=["10px", "10px", "0"],
                    ),

                    width="100%",
                    align="start",
                    gap="0",
                    direction=rx.breakpoints(initial="column", md="row"),
                ),

                spacing="4",
                align="center",
                padding="25px",
                background_color="#1a1a1a",
                border_radius="12px",
                max_width="95vw",
                width=["95vw", "95vw", "1024px"],
                height=["90vh", "90vh", "1024px"],
                max_height="90vh",
                overflow_y="hidden",
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
# EMAIL CREDENTIALS MODAL
# ============================================================

def _cred_input(label_key: str, value: rx.Var, on_change: rx.EventHandler) -> rx.Component:
    """Reusable labeled input row for credentials modal."""
    return rx.vstack(
        rx.text(t(label_key), font_size="11px", color="#999"),
        rx.input(
            value=value,
            on_change=on_change,
            size="2",
            width="100%",
        ),
        spacing="1",
        width="100%",
    )


def email_credentials_modal() -> rx.Component:
    """Modal dialog for entering IMAP/SMTP credentials."""
    return rx.cond(
        AIState.email_credentials_modal_open,
        rx.box(
            # Backdrop (opaque)
            rx.box(
                on_click=AIState.close_email_credentials,
                position="fixed",
                top="0",
                left="0",
                width="100%",
                height="100%",
                background_color="rgba(0, 0, 0, 0.92)",
            ),
            # Modal content
            rx.vstack(
                rx.text(t("email_credentials_title"), font_weight="bold", font_size="16px", color="white"),

                # IMAP row (host + port side by side)
                rx.hstack(
                    rx.vstack(
                        rx.text(t("email_cred_imap_host"), font_size="11px", color="#999"),
                        rx.input(
                            value=AIState.email_cred_imap_host,
                            on_change=AIState.set_email_cred_imap_host,
                            placeholder="imap.example.com",
                            size="2",
                            width="100%",
                        ),
                        spacing="1",
                        flex="3",
                    ),
                    rx.vstack(
                        rx.text(t("email_cred_imap_port"), font_size="11px", color="#999"),
                        rx.input(
                            value=AIState.email_cred_imap_port,
                            on_change=AIState.set_email_cred_imap_port,
                            size="2",
                            width="100%",
                        ),
                        spacing="1",
                        flex="1",
                    ),
                    spacing="2",
                    width="100%",
                ),

                # SMTP row (host + port side by side)
                rx.hstack(
                    rx.vstack(
                        rx.text(t("email_cred_smtp_host"), font_size="11px", color="#999"),
                        rx.input(
                            value=AIState.email_cred_smtp_host,
                            on_change=AIState.set_email_cred_smtp_host,
                            placeholder="smtp.example.com",
                            size="2",
                            width="100%",
                        ),
                        spacing="1",
                        flex="3",
                    ),
                    rx.vstack(
                        rx.text(t("email_cred_smtp_port"), font_size="11px", color="#999"),
                        rx.input(
                            value=AIState.email_cred_smtp_port,
                            on_change=AIState.set_email_cred_smtp_port,
                            size="2",
                            width="100%",
                        ),
                        spacing="1",
                        flex="1",
                    ),
                    spacing="2",
                    width="100%",
                ),

                # Username
                _cred_input("email_cred_user", AIState.email_cred_user, AIState.set_email_cred_user),

                # Password with eye toggle — two inputs, conditionally rendered
                rx.vstack(
                    rx.text(t("email_cred_password"), font_size="11px", color="#999"),
                    rx.box(
                        rx.cond(
                            AIState.email_cred_show_password,
                            rx.input(
                                value=AIState.email_cred_password,
                                on_change=AIState.set_email_cred_password,
                                placeholder="••••••••",
                                size="2",
                                width="100%",
                            ),
                            rx.input(
                                value=AIState.email_cred_password,
                                on_change=AIState.set_email_cred_password,
                                type="password",
                                placeholder="••••••••",
                                size="2",
                                width="100%",
                            ),
                        ),
                        rx.icon_button(
                            rx.cond(
                                AIState.email_cred_show_password,
                                rx.icon("eye-off", size=14),
                                rx.icon("eye", size=14),
                            ),
                            on_click=AIState.toggle_email_cred_show_password,
                            size="1",
                            variant="ghost",
                            color_scheme="gray",
                            position="absolute",
                            right="6px",
                            top="50%",
                            transform="translateY(-50%)",
                            cursor="pointer",
                        ),
                        position="relative",
                        width="100%",
                    ),
                    spacing="1",
                    width="100%",
                ),

                # From address (optional)
                _cred_input("email_cred_from", AIState.email_cred_from, AIState.set_email_cred_from),

                # Buttons
                rx.hstack(
                    rx.button(
                        t("email_cred_cancel"),
                        on_click=AIState.close_email_credentials,
                        variant="soft",
                        color_scheme="gray",
                        size="1",
                        flex="1",
                    ),
                    rx.button(
                        t("email_cred_save"),
                        on_click=AIState.save_email_credentials,
                        variant="solid",
                        color_scheme="blue",
                        size="1",
                        flex="1",
                    ),
                    spacing="2",
                    width="100%",
                ),

                spacing="3",
                padding="24px",
                background="#1a1a2e",
                border_radius="12px",
                border="1px solid var(--gray-a6)",
                width="400px",
                max_width="90vw",
                position="relative",
                z_index="1001",
            ),
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
