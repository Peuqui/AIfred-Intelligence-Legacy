"""Settings Modal for AIfred UI.

Fullscreen overlay with three tabs:
- Agents: Agent dropdown → Metadata + TTS + Prompts (all on one page)
- Memory: Agent dropdown → Memory entries with type filter
- Database: System collections (Research Cache, Documents) browse + delete

All text inputs are pure DOM elements (no per-keystroke state updates).
Values are read from DOM only on save/tab-switch/lang-switch via call_script.
"""
# mypy: disable-error-code="index, operator, call-arg, func-returns-value, arg-type"
# Reflex UI code: Var indexing, rx.icon module callable, event handler binding
# are all runtime-correct but not statically typeable.

from __future__ import annotations

import reflex as rx

from ..state import AIState
from .helpers import t

# Shared style for DOM-only input fields
_INPUT_STYLE = {
    "width": "100%",
    "color": "white",
    "background_color": "#333",
    "border": "1px solid #555",
    "border_radius": "6px",
    "padding": "6px 10px",
    "font_size": "14px",
}


# ============================================================
# SHARED HEADER (tabs + close)
# ============================================================

def _editor_header() -> rx.Component:
    """Shared header with tab navigation for the settings modal."""
    return rx.vstack(
        rx.hstack(
            rx.icon("settings", size=24, color="#FFD700"),
            rx.text(
                t("agent_editor_title"),
                color="white",
                font_weight="bold",
                font_size="18px",
            ),
            rx.spacer(),
            rx.button(
                rx.icon("x", size=16),
                on_click=AIState.close_agent_editor,
                size="1",
                variant="ghost",
                color_scheme="gray",
                cursor="pointer",
            ),
            width="100%",
            align="center",
        ),
        # Tab bar
        rx.hstack(
            rx.button(
                rx.icon("users", size=14),
                t("tab_agents"),
                on_click=AIState.set_agent_editor_tab("config"),
                size="2",
                variant=rx.cond(
                    AIState.agent_editor_mode == "config",
                    "solid", "soft",
                ),
                color_scheme=rx.cond(
                    AIState.agent_editor_mode == "config",
                    "orange", "gray",
                ),
                cursor="pointer",
            ),
            rx.button(
                rx.icon("brain", size=14),
                t("tab_memory"),
                on_click=AIState.set_agent_editor_tab("memory"),
                size="2",
                variant=rx.cond(
                    AIState.agent_editor_mode == "memory",
                    "solid", "soft",
                ),
                color_scheme=rx.cond(
                    AIState.agent_editor_mode == "memory",
                    "orange", "gray",
                ),
                cursor="pointer",
            ),
            rx.button(
                rx.icon("database", size=14),
                t("tab_database"),
                on_click=AIState.set_agent_editor_tab("database"),
                size="2",
                variant=rx.cond(
                    AIState.agent_editor_mode == "database",
                    "solid", "soft",
                ),
                color_scheme=rx.cond(
                    AIState.agent_editor_mode == "database",
                    "orange", "gray",
                ),
                cursor="pointer",
            ),
            spacing="2",
            width="100%",
        ),
        spacing="3",
        width="100%",
        flex_shrink="0",
        background_color="#1a1a1a",
        z_index="10",
        padding_bottom="8px",
        border_bottom="1px solid #333",
    )


# ============================================================
# PROMPT TAB BUTTON (for foreach)
# ============================================================

def _prompt_tab_button(key: rx.Var) -> rx.Component:
    """A single prompt layer tab button (rendered via foreach)."""
    return rx.button(
        key,
        on_click=AIState.set_editor_prompt_tab(key),
        size="1",
        variant=rx.cond(
            AIState.editor_prompt_tab == key,
            "solid",
            "soft",
        ),
        color_scheme=rx.cond(
            AIState.editor_prompt_tab == key,
            "blue",
            "gray",
        ),
        cursor="pointer",
    )


# JS to read all editor DOM fields as JSON
_READ_DOM_JS = (
    "JSON.stringify({"
    " name: (document.getElementById('editor-name')||{}).value||'',"
    " description: (document.getElementById('editor-description')||{}).value||'',"
    " prompt: (document.getElementById('editor-prompt-textarea')||{}).value||'',"
    " agent_id: (document.getElementById('editor-agent-id')||{}).value||''"
    "})"
)


# ============================================================
# CONFIG TAB — Dropdown + Metadata + TTS + Prompts
# ============================================================

def _config_view() -> rx.Component:
    """Config tab: agent dropdown at top, all settings below."""
    is_new = AIState.editor_agent_id == ""
    is_default = (
        (AIState.editor_agent_id == "aifred")
        | (AIState.editor_agent_id == "sokrates")
        | (AIState.editor_agent_id == "salomo")
        | (AIState.editor_agent_id == "vision")
    )

    return rx.vstack(
        _editor_header(),

        # Scrollable content
        rx.box(
            rx.vstack(
                # ── Agent Selector Row ──────────────────────────
                rx.hstack(
                    # Agent dropdown
                    rx.cond(
                        ~is_new,
                        rx.select(
                            AIState.agent_dropdown_options,
                            value=AIState.editor_agent_dropdown_value,
                            on_change=AIState.select_editor_agent,
                            size="2",
                            width="100%",
                        ),
                        # New agent mode — show ID input instead
                        rx.el.input(
                            id="editor-agent-id",
                            placeholder=t("agent_editor_agent_id_placeholder"),
                            auto_complete="off",
                            spell_check=False,
                            **_INPUT_STYLE,
                        ),
                    ),
                    # New Agent button
                    rx.tooltip(
                        rx.icon_button(
                            rx.icon("plus", size=16),
                            on_click=AIState.start_new_agent,
                            size="2",
                            variant="soft",
                            color_scheme="green",
                            cursor="pointer",
                        ),
                        content=t("agent_editor_new"),
                    ),
                    # Delete button (only custom agents, not during create)
                    rx.cond(
                        ~is_new & ~is_default,
                        rx.tooltip(
                            rx.icon_button(
                                rx.icon("trash-2", size=16),
                                on_click=AIState.delete_agent_editor(AIState.editor_agent_id),
                                size="2",
                                variant="soft",
                                color_scheme=rx.cond(
                                    AIState.editor_delete_confirm == AIState.editor_agent_id,
                                    "red", "gray",
                                ),
                                cursor="pointer",
                            ),
                            content=rx.cond(
                                AIState.editor_delete_confirm == AIState.editor_agent_id,
                                t("agent_editor_really_delete"),
                                t("agent_editor_delete_agent"),
                            ),
                        ),
                    ),
                    # Clear memory button (not vision, not during create)
                    rx.cond(
                        ~is_new & (AIState.editor_role != "vision"),
                        rx.tooltip(
                            rx.icon_button(
                                rx.icon("eraser", size=16),
                                on_click=AIState.clear_agent_memory(AIState.editor_agent_id),
                                size="2",
                                variant="soft",
                                color_scheme=rx.cond(
                                    AIState.editor_memory_confirm == AIState.editor_agent_id,
                                    "red", "orange",
                                ),
                                cursor="pointer",
                            ),
                            content=rx.cond(
                                AIState.editor_memory_confirm == AIState.editor_agent_id,
                                t("agent_editor_really_forget"),
                                t("agent_editor_clear_memories"),
                            ),
                        ),
                    ),
                    spacing="2",
                    align="center",
                    width="100%",
                ),

                # ── Metadata ────────────────────────────────────
                rx.hstack(
                    # Name
                    rx.vstack(
                        rx.text(t("agent_editor_name"), color="#aaa", font_size="12px"),
                        rx.el.input(
                            id="editor-name",
                            auto_complete="off",
                            spell_check=False,
                            **_INPUT_STYLE,
                        ),
                        spacing="1",
                        flex="1",
                    ),
                    # Emoji with picker
                    rx.vstack(
                        rx.text(t("agent_editor_emoji"), color="#aaa", font_size="12px"),
                        rx.box(
                            rx.button(
                                AIState.editor_emoji,
                                on_click=AIState.toggle_emoji_picker,
                                width="60px",
                                height="36px",
                                font_size="20px",
                                variant="outline",
                                color_scheme="gray",
                                cursor="pointer",
                                background_color="#333",
                            ),
                            rx.cond(
                                AIState.editor_emoji_picker_open,
                                rx.box(
                                    rx.flex(
                                        *[
                                            rx.button(
                                                e,
                                                on_click=AIState.set_editor_emoji(e),
                                                size="1",
                                                variant="ghost",
                                                cursor="pointer",
                                                font_size="18px",
                                                padding="4px",
                                                min_width="36px",
                                                height="36px",
                                            )
                                            for e in [
                                                "\U0001f3a9", "\U0001f3db\ufe0f", "\U0001f451",
                                                "\U0001f4f7", "\U0001f916", "\U0001f9e0",
                                                "\U0001f4a1", "\U0001f52c", "\U0001f3ad",
                                                "\U0001f98a", "\U0001f43a", "\U0001f989",
                                                "\U0001f409", "\U0001f9d9", "\U0001f468\u200d\u2695\ufe0f",
                                                "\U0001f468\u200d\U0001f52c", "\U0001f575\ufe0f",
                                                "\U0001f468\u200d\U0001f4bb", "\U0001f9d1\u200d\U0001f3eb",
                                                "\U0001f3af", "\u26a1", "\U0001f525",
                                                "\u2744\ufe0f", "\U0001f31f", "\U0001f480",
                                                "\U0001f47d", "\U0001f921", "\U0001f608",
                                                "\U0001f9be", "\U0001f9ec", "\u2699\ufe0f",
                                                "\U0001f3aa",
                                            ]
                                        ],
                                        wrap="wrap",
                                        gap="2px",
                                        max_width="300px",
                                    ),
                                    position="absolute",
                                    top="100%",
                                    left="0",
                                    z_index="100",
                                    background_color="#2a2a2a",
                                    border="1px solid #555",
                                    border_radius="8px",
                                    padding="8px",
                                    margin_top="4px",
                                ),
                            ),
                            position="relative",
                        ),
                        spacing="1",
                    ),
                    width="100%",
                    spacing="3",
                ),

                # Role + Description
                rx.hstack(
                    rx.vstack(
                        rx.text(t("agent_editor_role"), color="#aaa", font_size="12px"),
                        rx.select(
                            ["main", "critic", "judge", "custom"],
                            value=AIState.editor_role,
                            on_change=AIState.set_editor_role,
                            size="1",
                            width="120px",
                        ),
                        spacing="1",
                    ),
                    rx.vstack(
                        rx.text(t("agent_editor_description"), color="#aaa", font_size="12px"),
                        rx.el.input(
                            id="editor-description",
                            auto_complete="off",
                            spell_check=False,
                            **_INPUT_STYLE,
                        ),
                        spacing="1",
                        flex="1",
                    ),
                    width="100%",
                    spacing="3",
                    align="end",
                ),

                # ── TTS Settings (only existing agents, not vision) ─
                rx.cond(
                    ~is_new & (AIState.editor_role != "vision"),
                    rx.vstack(
                        # Header: Title + Enabled toggle
                        rx.hstack(
                            rx.text(
                                "\U0001f50a ", t("agent_editor_tts_title"),
                                color="#FFD700",
                                font_weight="bold",
                                font_size="14px",
                            ),
                            rx.spacer(),
                            rx.hstack(
                                rx.switch(
                                    checked=AIState.editor_agent_tts_enabled,
                                    on_change=AIState.toggle_editor_agent_tts,
                                    size="1",
                                ),
                                rx.text(
                                    rx.cond(AIState.editor_agent_tts_enabled, "ON", "OFF"),
                                    font_size="10px",
                                    color=rx.cond(AIState.editor_agent_tts_enabled, "#d4a14a", "#666"),
                                ),
                                spacing="1",
                                align="center",
                            ),
                            width="100%",
                            align="center",
                        ),
                        # Backend + Voice
                        rx.hstack(
                            rx.text("Backend", font_size="11px", color="#aaa", flex_shrink="0"),
                            rx.box(
                                rx.select(
                                    AIState.tts_engines,
                                    value=AIState.editor_tts_engine_label,
                                    on_change=AIState.set_editor_tts_engine,
                                    size="1",
                                    width="100%",
                                ),
                                flex="1",
                                min_width="0",
                            ),
                            rx.text("Voice", font_size="11px", color="#aaa", flex_shrink="0"),
                            rx.box(
                                rx.select(
                                    AIState.editor_tts_available_voices,
                                    value=AIState.editor_agent_tts_voice,
                                    on_change=AIState.set_editor_agent_tts_voice,
                                    placeholder="Default",
                                    size="1",
                                    width="100%",
                                ),
                                flex="1",
                                min_width="0",
                            ),
                            spacing="2",
                            align="center",
                            width="100%",
                        ),
                        # Speed + Pitch
                        rx.hstack(
                            rx.text("Speed", font_size="11px", color="#aaa", width="55px"),
                            rx.select(
                                ["0.8x", "0.9x", "1.0x", "1.1x", "1.2x", "1.25x", "1.5x", "2.0x"],
                                value=AIState.editor_agent_tts_speed,
                                on_change=AIState.set_editor_agent_tts_speed,
                                size="1",
                                width="90px",
                            ),
                            rx.text("Pitch", font_size="11px", color="#aaa", width="40px"),
                            rx.select(
                                ["0.8", "0.85", "0.9", "0.95", "1.0", "1.05", "1.1", "1.15", "1.2"],
                                value=AIState.editor_agent_tts_pitch,
                                on_change=AIState.set_editor_agent_tts_pitch,
                                size="1",
                                width="90px",
                            ),
                            spacing="2",
                            align="center",
                            width="100%",
                        ),
                        spacing="2",
                        width="100%",
                        padding="10px",
                        background_color="#222",
                        border_radius="8px",
                        border="1px solid #333",
                        overflow="hidden",
                    ),
                ),

                # ── Prompt Layer Editor (only existing agents) ──
                rx.cond(
                    ~is_new,
                    rx.vstack(
                        rx.hstack(
                            rx.text(
                                t("agent_editor_prompts"),
                                color="#FFD700",
                                font_weight="bold",
                                font_size="14px",
                            ),
                            rx.spacer(),
                            rx.hstack(
                                rx.button(
                                    "DE",
                                    on_click=AIState.set_editor_prompt_lang("de"),
                                    size="1",
                                    variant=rx.cond(AIState.editor_prompt_lang == "de", "solid", "soft"),
                                    color_scheme=rx.cond(AIState.editor_prompt_lang == "de", "blue", "gray"),
                                    cursor="pointer",
                                ),
                                rx.button(
                                    "EN",
                                    on_click=AIState.set_editor_prompt_lang("en"),
                                    size="1",
                                    variant=rx.cond(AIState.editor_prompt_lang == "en", "solid", "soft"),
                                    color_scheme=rx.cond(AIState.editor_prompt_lang == "en", "blue", "gray"),
                                    cursor="pointer",
                                ),
                                spacing="1",
                            ),
                            width="100%",
                            align="center",
                        ),
                        rx.hstack(
                            rx.foreach(
                                AIState.editor_prompt_keys,
                                _prompt_tab_button,
                            ),
                            spacing="2",
                            flex_wrap="wrap",
                        ),
                        rx.el.textarea(
                            id="editor-prompt-textarea",
                            width="100%",
                            min_height="200px",
                            color="white",
                            background_color="#1a1a1a",
                            border="1px solid #444",
                            font_family="monospace",
                            font_size="13px",
                            padding="12px",
                            border_radius="6px",
                            auto_complete="off",
                            spell_check=False,
                            style={"resize": "vertical"},
                        ),
                        spacing="2",
                        width="100%",
                    ),
                ),

                # ── Action Buttons ──────────────────────────────
                rx.hstack(
                    rx.button(
                        t("agent_editor_save"),
                        on_click=rx.call_script(
                            _READ_DOM_JS,
                            callback=AIState.save_agent_editor,
                        ),
                        variant="soft",
                        color_scheme="orange",
                        size="2",
                        cursor="pointer",
                    ),
                    rx.cond(
                        ~is_new,
                        rx.button(
                            t("agent_editor_reset"),
                            on_click=AIState.reset_editor_prompt,
                            variant="soft",
                            color_scheme="gray",
                            size="2",
                            cursor="pointer",
                        ),
                    ),
                    spacing="3",
                    width="100%",
                ),

                spacing="4",
                width="100%",
            ),
            flex="1",
            overflow_y="auto",
            width="100%",
        ),

        spacing="3",
        width="100%",
        flex="1",
        min_height="0",
    )


# ============================================================
# MEMORY TAB — Dropdown + Filter + Entries
# ============================================================

def _memory_entry_row(entry: rx.Var) -> rx.Component:
    """Render a single memory entry with expandable content."""
    return rx.box(
        rx.hstack(
            rx.badge(
                entry["type"],
                variant="soft",
                color_scheme=rx.cond(
                    entry["type"] == "session_summary", "blue",
                    rx.cond(entry["type"] == "sermon", "purple",
                    rx.cond(entry["type"] == "insight", "green", "gray")),
                ),
                font_size="10px",
            ),
            rx.text(entry["date"], font_size="11px", color="#888"),
            rx.spacer(),
            rx.icon_button(
                rx.icon("trash-2", size=12),
                on_click=AIState.delete_memory_entry(entry["id"]),
                size="1",
                variant="ghost",
                color_scheme="red",
                cursor="pointer",
            ),
            width="100%",
            align="center",
        ),
        rx.text(
            entry["summary"],
            font_size="15px",
            color="#ddd",
            font_weight="500",
            padding_top="4px",
        ),
        rx.cond(
            entry["content"] != entry["summary"],
            rx.text(
                entry["content"],
                font_size="14px",
                color="#aaa",
                padding_top="4px",
                style={"white_space": "pre-wrap"},
            ),
        ),
        rx.cond(
            entry["sources"] != "",
            rx.vstack(
                rx.text(t("memory_sources"), font_size="12px", color="#888", font_weight="600", padding_top="8px"),
                rx.foreach(
                    entry["sources"].split("\n"),  # type: ignore[union-attr]
                    _source_link,
                ),
                spacing="1",
                width="100%",
            ),
        ),
        padding="10px 12px",
        background="rgba(255,255,255,0.03)",
        border_radius="6px",
        border="1px solid #333",
        width="100%",
    )


def _source_link(url: rx.Var) -> rx.Component:
    """Render a clickable source URL."""
    return rx.link(
        rx.hstack(
            rx.icon("external-link", size=12, color="#4da6ff"),
            rx.text(url, font_size="12px", color="#4da6ff"),
            spacing="1",
            align="center",
        ),
        href=url,
        is_external=True,
        style={
            "text_decoration": "none",
            "&:hover": {"text_decoration": "underline"},
        },
    )


def _memory_view() -> rx.Component:
    """Memory tab: agent dropdown + type filter + entries."""
    return rx.vstack(
        _editor_header(),

        # Scrollable content
        rx.box(
            rx.vstack(
                # Agent dropdown
                rx.hstack(
                    rx.select(
                        AIState.memory_agent_dropdown_options,
                        value=AIState.memory_browser_agent_display,
                        on_change=AIState.select_memory_agent,
                        placeholder=t("agent_editor_select_agent"),
                        size="2",
                        width="100%",
                    ),
                    spacing="2",
                    width="100%",
                    align="center",
                ),

                # Filter buttons (only when agent selected)
                rx.cond(
                    AIState.memory_browser_agent != "",
                    rx.hstack(
                        rx.button(
                            t("memory_filter_all"),
                            on_click=AIState.set_memory_filter("all"),
                            size="1",
                            variant=rx.cond(AIState.memory_browser_filter == "all", "solid", "soft"),
                            color_scheme=rx.cond(AIState.memory_browser_filter == "all", "orange", "gray"),
                            cursor="pointer",
                        ),
                        rx.button(
                            "Session",
                            on_click=AIState.set_memory_filter("session"),
                            size="1",
                            variant=rx.cond(AIState.memory_browser_filter == "session", "solid", "soft"),
                            color_scheme=rx.cond(AIState.memory_browser_filter == "session", "blue", "gray"),
                            cursor="pointer",
                        ),
                        rx.button(
                            "Agent",
                            on_click=AIState.set_memory_filter("agent"),
                            size="1",
                            variant=rx.cond(AIState.memory_browser_filter == "agent", "solid", "soft"),
                            color_scheme=rx.cond(AIState.memory_browser_filter == "agent", "green", "gray"),
                            cursor="pointer",
                        ),
                        rx.spacer(),
                        rx.badge(
                            AIState.filtered_memory_entries.length(),  # type: ignore[union-attr]
                            variant="soft",
                            color_scheme="orange",
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                ),

                # Entries
                rx.cond(
                    AIState.memory_browser_agent == "",
                    rx.text(
                        t("memory_select_hint"),
                        color="#888",
                        font_size="13px",
                        padding_top="20px",
                        text_align="center",
                    ),
                    rx.cond(
                        AIState.filtered_memory_entries.length() > 0,  # type: ignore[union-attr]
                        rx.vstack(
                            rx.foreach(
                                AIState.filtered_memory_entries,
                                _memory_entry_row,
                            ),
                            spacing="2",
                            width="100%",
                        ),
                        rx.text(
                            t("memory_no_entries"),
                            color="#888",
                            font_size="13px",
                        ),
                    ),
                ),

                spacing="3",
                width="100%",
            ),
            flex="1",
            overflow_y="auto",
            width="100%",
        ),

        spacing="3",
        width="100%",
        flex="1",
        min_height="0",
    )


# ============================================================
# DATABASE VIEW (ChromaDB Management — System Collections)
# ============================================================

def _database_view() -> rx.Component:
    """Database tab: Research Cache + Documents with same browse/delete UI as Memory."""
    return rx.vstack(
        _editor_header(),

        # Scrollable content
        rx.box(
            rx.vstack(
                # Collection selector buttons + clear-all
                rx.hstack(
                    rx.button(
                        rx.icon("search", size=14),
                        " ", t("db_research_cache"),
                        on_click=AIState.select_db_collection("research_cache"),
                        size="2",
                        variant=rx.cond(
                            AIState.db_browser_collection == "research_cache",
                            "solid", "soft",
                        ),
                        color_scheme="orange",
                        cursor="pointer",
                        flex_shrink="0",
                    ),
                    rx.button(
                        rx.icon("file-text", size=14),
                        " ", t("db_documents"),
                        on_click=AIState.select_db_collection("aifred_documents"),
                        size="2",
                        variant=rx.cond(
                            AIState.db_browser_collection == "aifred_documents",
                            "solid", "soft",
                        ),
                        color_scheme="orange",
                        cursor="pointer",
                        flex_shrink="0",
                    ),
                    rx.spacer(),
                    # Entry count badge
                    rx.cond(
                        AIState.db_browser_collection != "",
                        rx.badge(
                            AIState.db_browser_entries.length(),  # type: ignore[union-attr]
                            variant="soft",
                            color_scheme="orange",
                        ),
                    ),
                    # Clear all button (with confirmation)
                    rx.cond(
                        AIState.db_browser_entries.length() > 0,  # type: ignore[union-attr]
                        rx.cond(
                            AIState.db_clear_confirm,
                            # Confirmation: two buttons
                            rx.hstack(
                                rx.button(
                                    t("db_really_delete"),
                                    on_click=AIState.clear_db_collection,
                                    size="1",
                                    variant="solid",
                                    color_scheme="red",
                                    cursor="pointer",
                                ),
                                rx.button(
                                    t("db_cancel"),
                                    on_click=AIState.confirm_clear_db,
                                    size="1",
                                    variant="soft",
                                    color_scheme="gray",
                                    cursor="pointer",
                                ),
                                spacing="1",
                            ),
                            # Normal: eraser icon
                            rx.tooltip(
                                rx.icon_button(
                                    rx.icon("eraser", size=16),
                                    on_click=AIState.confirm_clear_db,
                                    size="2",
                                    variant="soft",
                                    color_scheme="red",
                                    cursor="pointer",
                                ),
                                content=t("db_clear_all"),
                            ),
                        ),
                    ),
                    spacing="2",
                    width="100%",
                    align="center",
                ),

                # Entries list
                rx.cond(
                    AIState.db_browser_collection == "",
                    rx.text(
                        t("db_select_hint"),
                        color="#888",
                        font_size="13px",
                        padding_top="20px",
                        text_align="center",
                    ),
                    rx.cond(
                        AIState.db_browser_entries.length() > 0,  # type: ignore[union-attr]
                        rx.vstack(
                            rx.foreach(
                                AIState.db_browser_entries,
                                _db_entry_row,
                            ),
                            spacing="2",
                            width="100%",
                        ),
                        rx.text(
                            t("db_no_entries"),
                            color="#888",
                            font_size="13px",
                        ),
                    ),
                ),

                spacing="3",
                width="100%",
            ),
            flex="1",
            overflow_y="auto",
            width="100%",
        ),

        spacing="3",
        width="100%",
        flex="1",
        min_height="0",
    )


def _db_entry_row(entry: rx.Var) -> rx.Component:
    """Render a single database entry — same style as memory entries."""
    return rx.box(
        rx.hstack(
            rx.badge(
                entry["type"],
                variant="soft",
                color_scheme=rx.cond(
                    entry["type"] == "cache", "orange",
                    rx.cond(entry["type"] == "document", "blue", "gray"),
                ),
                font_size="10px",
            ),
            rx.text(entry["date"], font_size="11px", color="#888"),
            rx.spacer(),
            rx.icon_button(
                rx.icon("trash-2", size=12),
                on_click=AIState.delete_db_entry(entry["id"]),
                size="1",
                variant="ghost",
                color_scheme="red",
                cursor="pointer",
            ),
            width="100%",
            align="center",
        ),
        rx.text(
            entry["summary"],
            font_size="15px",
            color="#ddd",
            font_weight="500",
            padding_top="4px",
        ),
        rx.cond(
            entry["content"] != entry["summary"],
            rx.text(
                entry["content"],
                font_size="14px",
                color="#aaa",
                padding_top="4px",
                style={"white_space": "pre-wrap", "max_height": "150px", "overflow_y": "auto"},
            ),
        ),
        padding="10px 12px",
        background="rgba(255,255,255,0.03)",
        border_radius="6px",
        border="1px solid #333",
        width="100%",
    )


# ============================================================
# MAIN MODAL
# ============================================================

def agent_editor_modal() -> rx.Component:
    """Settings modal fullscreen overlay."""
    return rx.cond(
        AIState.agent_editor_open,
        rx.box(
            # Backdrop
            rx.box(
                position="absolute",
                top="0",
                left="0",
                width="100%",
                height="100%",
                background_color="rgba(0, 0, 0, 0.85)",
                on_click=AIState.close_agent_editor,
            ),
            # Modal content — switches between config, memory and database
            rx.box(
                rx.cond(
                    AIState.agent_editor_mode == "database",
                    _database_view(),
                    rx.cond(
                        AIState.agent_editor_mode == "memory",
                        _memory_view(),
                        _config_view(),
                    ),
                ),
                padding="25px",
                background_color="#1a1a1a",
                border_radius="12px",
                max_width="95vw",
                width="750px",
                height="90vh",
                max_height="95vh",
                overflow_x="hidden",
                overflow_y="hidden",
                display="flex",
                flex_direction="column",
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
