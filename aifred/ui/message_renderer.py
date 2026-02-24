"""Message rendering components for AIfred chat display."""

from __future__ import annotations

import reflex as rx

from ..state import AIState
from ..theme import COLORS
from .helpers import (
    MARKDOWN_COMPONENT_MAP,
    MARKDOWN_COMPONENT_MAP_WITH_LISTS,
    t,
)


# ============================================================
# THINKING PARSER
# ============================================================

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


# ============================================================
# SOURCE RENDERING
# ============================================================

def render_sources_collapsible_from_msg(msg) -> rx.Component:
    """
    Placeholder - sources are shown only for current request via State variables.
    For historical messages, sources are embedded in content as HTML comments
    and rendered via HTML export.
    """
    return rx.fragment()


# ============================================================
# IMAGE THUMBNAILS
# ============================================================

def render_history_thumbnail(img_data) -> rx.Component:
    """Render clickable thumbnail that opens lightbox on click.

    Args:
        img_data: Either a string URL or a dict with {"name": str, "url": str}
    """
    # Handle both string URLs and dict format
    img_url = rx.cond(
        img_data.is_string(),
        img_data,
        img_data["url"]
    )
    return rx.image(
        src=img_url,
        width="50px",
        height="50px",
        object_fit="cover",
        border_radius="4px",
        cursor="pointer",
        border=f"1px solid {COLORS['border']}",
        on_click=AIState.open_lightbox(img_url),  # type: ignore[call-arg, func-returns-value]
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


# ============================================================
# MESSAGE BUBBLES
# ============================================================

def render_user_message(msg: dict) -> rx.Component:
    """Render user message (right-aligned with emoji outside on the right)"""
    # NOTE: Since this is called from rx.cond, msg fields are already extracted as Vars
    # We can use them directly in rx components
    return rx.box(
        rx.hstack(
            rx.box(
                rx.text(
                    rx.cond(
                        AIState.user_name != "",
                        AIState.user_name,
                        "User"
                    ),
                    font_weight="bold",
                    font_size="12px",
                    color="#c06050",
                    margin_bottom="1",
                    text_align="right",
                ),
                # Content (text message)
                rx.markdown(msg["content"], color=COLORS["user_text"], font_size="13px", component_map=MARKDOWN_COMPONENT_MAP),
                padding="3",
                border_radius="6px",
                max_width="70%",
                background_color=COLORS["user_msg"],
            ),
            rx.text("\U0001f64b", font_size="13px"),
            spacing="2",
            align="start",
            justify="end",
            width="100%",
        ),
        padding="2",
        border_radius="8px",
        border="1px solid rgba(255, 255, 255, 0.1)",
        width="100%",
        margin_bottom="3",
    )


# ============================================================
# AUDIO BUTTONS
# ============================================================

def render_bubble_audio_buttons(msg: dict) -> rx.Component:
    """Render play and regenerate buttons for audio replay.

    KISS: Buttons werden IMMER gerendert mit display:none.
    JavaScript (initBubbleAudioButtons) zeigt sie und bindet click-handler.
    Das umgeht alle rx.cond Typ-Probleme mit Dict-Feldern.
    """
    return rx.hstack(
        # Play button - disabled during TTS regeneration
        rx.el.button(
            rx.icon("volume-2", size=18),  # type: ignore[operator]
            type="button",
            title=t("audio_play_tooltip"),
            disabled=AIState.tts_regenerating,
            **{"data-audio-urls": msg["audio_urls_json"]},
            class_name="bubble-audio-btn",
            style={
                "display": "none",  # JS zeigt Button wenn Audio vorhanden
                "opacity": rx.cond(AIState.tts_regenerating, "0.3", "0.6"),
                "cursor": rx.cond(AIState.tts_regenerating, "not-allowed", "pointer"),
                "padding": "6px 8px",
                "background": "transparent",
                "border": "none",
                "border_radius": "4px",
                "align_items": "center",
            },
        ),
        # Regenerate button - shows spinner during TTS regeneration
        rx.button(
            rx.cond(
                AIState.tts_regenerating,
                rx.spinner(size="1"),
                rx.icon("refresh-cw", size=16),  # type: ignore[operator]
            ),
            on_click=lambda: AIState.resynthesize_bubble_tts(msg.get("timestamp", "")),  # type: ignore[call-arg]
            title=t("audio_regenerate_tooltip"),
            size="1",
            variant="ghost",
            color_scheme="gray",
            disabled=AIState.tts_regenerating,
            class_name="bubble-regenerate-btn",
            style={
                "display": "none",  # JS zeigt Button wenn Audio vorhanden
                "opacity": rx.cond(AIState.tts_regenerating, "0.3", "0.5"),
                "cursor": rx.cond(AIState.tts_regenerating, "not-allowed", "pointer"),
                "padding": "6px 8px",
                "min_width": "auto",
            },
        ),
        spacing="1",
        align="center",
    )


# ============================================================
# ASSISTANT MESSAGE (with agent styling)
# ============================================================

def render_assistant_message(msg: dict) -> rx.Component:
    """Render assistant message (left-aligned, styled per agent)"""
    # Check agent type with nested rx.cond
    return rx.cond(
        msg["agent"] == "sokrates",
        # SOKRATES
        rx.box(
            rx.hstack(
                rx.text("\U0001f3db\ufe0f", font_size="13px"),
                rx.box(
                    rx.hstack(
                        rx.text(
                            "Sokrates",
                            font_weight="bold",
                            font_size="12px",
                            color="#cd7f32",
                        ),
                        render_bubble_audio_buttons(msg),
                        spacing="2",
                        align="center",
                        margin_bottom="1",
                    ),
                    rx.markdown(
                        msg["content"],
                        color=COLORS["ai_text"],
                        font_size="13px",
                        component_map=MARKDOWN_COMPONENT_MAP,
                    ),
                    background_color="rgba(205, 127, 50, 0.08)",
                    padding="3",
                    border_radius="6px",
                    width="100%",
                ),
                spacing="2",
                align="start",
                justify="start",
                width="100%",
            ),
            background_color="rgba(205, 127, 50, 0.03)",
            padding="2",
            border_radius="8px",
            border="1px solid rgba(205, 127, 50, 0.3)",
            width="100%",
            margin_bottom="3",
        ),
        # NOT SOKRATES - check if salomo
        rx.cond(
            msg["agent"] == "salomo",
            # SALOMO
            rx.box(
                rx.hstack(
                    rx.text("\U0001f451", font_size="13px"),
                    rx.box(
                        rx.hstack(
                            rx.text(
                                "Salomo",
                                font_weight="bold",
                                font_size="12px",
                                color="#daa520",
                            ),
                            render_bubble_audio_buttons(msg),
                            spacing="2",
                            align="center",
                            margin_bottom="1",
                        ),
                        rx.markdown(
                            msg["content"],
                            color=COLORS["ai_text"],
                            font_size="13px",
                            component_map=MARKDOWN_COMPONENT_MAP,
                        ),
                        background_color="rgba(218, 165, 32, 0.08)",
                        padding="3",
                        border_radius="6px",
                        width="100%",
                    ),
                    spacing="2",
                    align="start",
                    justify="start",
                    width="100%",
                ),
                background_color="rgba(218, 165, 32, 0.03)",
                padding="2",
                border_radius="8px",
                border="1px solid rgba(218, 165, 32, 0.3)",
                width="100%",
                margin_bottom="3",
            ),
            # AIFRED (default)
            rx.box(
                rx.hstack(
                    rx.text("\U0001f3a9", font_size="13px"),
                    rx.box(
                        rx.hstack(
                            rx.text(
                                "AIfred",
                                font_weight="bold",
                                font_size="12px",
                                color=COLORS["primary"],
                            ),
                            render_bubble_audio_buttons(msg),
                            spacing="2",
                            align="center",
                            margin_bottom="1",
                        ),
                        # Web sources collapsible (if available)
                        # Use msg["used_sources"] / msg["failed_sources"] directly
                        # These are top-level fields in the message dict
                        render_sources_collapsible_from_msg(msg),
                        rx.markdown(
                            msg["content"],
                            color=COLORS["ai_text"],
                            font_size="13px",
                            component_map=MARKDOWN_COMPONENT_MAP,
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
                margin_bottom="3",
            ),
        ),
    )


# ============================================================
# SYSTEM MESSAGE
# ============================================================

def render_system_message(msg: dict) -> rx.Component:
    """Render system message (summary)"""
    # Just render as markdown - summary formatting already in content
    return rx.markdown(
        msg["content"],
        color=COLORS["text_primary"],
        width="100%",
        component_map=MARKDOWN_COMPONENT_MAP,
    )


# ============================================================
# MESSAGE DISPATCHER
# ============================================================

def render_message_standalone(msg: dict) -> rx.Component:
    """
    Rendert eine einzelne Message aus chat_history (dict-based).

    Uses rx.cond to branch on message role since msg is a Reflex Var.
    """
    # Top-level branching with rx.cond
    return rx.cond(
        msg["role"] == "user",
        render_user_message(msg),
        rx.cond(
            msg["role"] == "assistant",
            render_assistant_message(msg),
            # system or unknown
            render_system_message(msg)
        )
    )


# ============================================================
# SOKRATES INLINE PANEL
# ============================================================

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
                    rx.text("\U0001f3db\ufe0f", font_size="13px"),
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
                                        rx.text(AIState.debate_round.to(str), font_weight="bold"),  # type: ignore[attr-defined]
                                        spacing="1",
                                    ),
                                    variant="soft",
                                    color_scheme="blue",
                                    size="1",
                                ),
                            ),
                            # LGTM badge if consensus reached
                            rx.cond(
                                AIState.sokrates_critique.contains("LGTM"),  # type: ignore[attr-defined]
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
                                            component_map=MARKDOWN_COMPONENT_MAP_WITH_LISTS,
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
                                            component_map=MARKDOWN_COMPONENT_MAP_WITH_LISTS,
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
                                component_map=MARKDOWN_COMPONENT_MAP_WITH_LISTS,
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
                # Outer container with slightly different background
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
