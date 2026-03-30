"""Agent Editor Modal for AIfred UI.

Fullscreen overlay for managing agent configurations:
- List all configured agents
- Edit agent metadata (name, emoji, role, description)
- Edit prompt layers (identity, personality, task, etc.) via text editor
- Create new agents from role templates
- Delete custom agents (default agents protected)

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


def _agent_row(agent: rx.Var) -> rx.Component:
    """Render a single agent row in the agent list.

    agent is an rx.Var[dict] from foreach - use bracket access for fields.
    """
    # Check if agent is a default (cannot be deleted)
    is_default = (
        (agent["id"] == "aifred")
        | (agent["id"] == "sokrates")
        | (agent["id"] == "salomo")
        | (agent["id"] == "vision")
    )

    return rx.hstack(
        # Emoji + Name
        rx.text(agent["emoji"], font_size="20px"),
        rx.vstack(
            rx.text(
                agent["display_name"],
                font_weight="bold",
                color="white",
                font_size="14px",
            ),
            rx.text(
                agent["description"],
                color="#aaa",
                font_size="12px",
            ),
            spacing="0",
            align_items="flex-start",
        ),
        rx.spacer(),
        # Role badge
        rx.badge(
            agent["role"],
            color_scheme=rx.cond(
                agent["role"] == "main",
                "blue",
                rx.cond(
                    agent["role"] == "critic",
                    "orange",
                    rx.cond(
                        agent["role"] == "judge",
                        "purple",
                        "gray",
                    ),
                ),
            ),
            size="1",
        ),
        # Default badge
        rx.cond(
            is_default,
            rx.badge(
                t("agent_editor_default_badge"),
                color_scheme="green",
                size="1",
                variant="soft",
            ),
        ),
        # Edit button
        rx.button(
            t("agent_editor_edit"),
            on_click=AIState.edit_agent(agent["id"]),
            size="1",
            variant="soft",
            color_scheme="blue",
            cursor="pointer",
        ),
        # Clear memory button (all agents except vision)
        rx.cond(
            agent["role"] != "vision",
            rx.button(
                rx.cond(
                    AIState.editor_memory_confirm == agent["id"],
                    t("agent_editor_forget_confirm"),
                    t("agent_editor_forget"),
                ),
                on_click=AIState.clear_agent_memory(agent["id"]),
                size="1",
                variant="soft",
                color_scheme=rx.cond(
                    AIState.editor_memory_confirm == agent["id"],
                    "red",
                    "orange",
                ),
                cursor="pointer",
            ),
        ),
        # Delete button (only for custom agents)
        rx.cond(
            ~is_default,
            rx.button(
                rx.cond(
                    AIState.editor_delete_confirm == agent["id"],
                    t("agent_editor_delete_confirm"),
                    t("agent_editor_delete"),
                ),
                on_click=AIState.delete_agent_editor(agent["id"]),
                size="1",
                variant="soft",
                color_scheme=rx.cond(
                    AIState.editor_delete_confirm == agent["id"],
                    "red",
                    "gray",
                ),
                cursor="pointer",
            ),
        ),
        width="100%",
        padding="10px 12px",
        background_color="#2a2a2a",
        border_radius="8px",
        align="center",
        spacing="3",
    )


def _editor_header() -> rx.Component:
    """Shared header with tab navigation for the agent editor modal."""
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
                rx.cond(AIState.ui_language == "de", "Agenten", "Agents"),
                on_click=AIState.back_to_agent_list,
                size="2",
                variant=rx.cond(
                    AIState.agent_editor_mode == "list",
                    "solid", "soft",
                ),
                color_scheme=rx.cond(
                    AIState.agent_editor_mode == "list",
                    "orange", "gray",
                ),
                cursor="pointer",
            ),
            rx.button(
                rx.icon("database", size=14),
                "Memory",
                on_click=AIState.open_memory_browser,
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


def _agent_list_view() -> rx.Component:
    """The agent list view (main view of the editor)."""
    return rx.vstack(
        _editor_header(),
        # Scrollable content
        rx.box(
            rx.vstack(
                # New agent button
                rx.button(
                    rx.hstack(
                        rx.icon("plus", size=16),
                        rx.text(t("agent_editor_new")),
                        spacing="2",
                        align="center",
                    ),
                    on_click=AIState.start_new_agent,
                    width="100%",
                    variant="soft",
                    color_scheme="green",
                    size="2",
                    cursor="pointer",
                ),
                # Agent list
                rx.foreach(
                    AIState.agent_list,
                    _agent_row,
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


def _agent_edit_view() -> rx.Component:
    """The agent edit view (shown when editing or creating an agent)."""
    is_new = AIState.editor_agent_id == ""

    return rx.vstack(
        # Header
        rx.hstack(
            rx.icon("pencil", size=24, color="#FFD700"),
            rx.text(
                rx.cond(
                    is_new,
                    t("agent_editor_new"),
                    AIState.editor_display_name,
                ),
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

        # Agent ID (only for new agents) — DOM-only
        rx.cond(
            is_new,
            rx.vstack(
                rx.text(t("agent_editor_id"), color="#aaa", font_size="12px"),
                rx.el.input(
                    id="editor-agent-id",
                    placeholder="z.B. dr_house",
                    auto_complete="off",
                    spell_check=False,
                    **_INPUT_STYLE,
                ),
                rx.text(
                    t("agent_editor_id_hint"),
                    color="#666",
                    font_size="11px",
                ),
                spacing="1",
                width="100%",
            ),
        ),

        # Metadata fields — DOM-only
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
                    # Emoji picker dropdown
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

        # Role selector (select is fine as controlled — no keystroke issue)
        rx.vstack(
            rx.text(t("agent_editor_role"), color="#aaa", font_size="12px"),
            rx.select(
                ["main", "critic", "judge", "custom"],
                value=AIState.editor_role,
                on_change=AIState.set_editor_role,
                width="100%",
            ),
            spacing="1",
            width="100%",
        ),

        # Description — DOM-only
        rx.vstack(
            rx.text(t("agent_editor_description"), color="#aaa", font_size="12px"),
            rx.el.input(
                id="editor-description",
                auto_complete="off",
                spell_check=False,
                **_INPUT_STYLE,
            ),
            spacing="1",
            width="100%",
        ),

        # Prompt Layer Editor (only when editing existing agent)
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
                    # Language toggle
                    rx.hstack(
                        rx.button(
                            "DE",
                            on_click=AIState.set_editor_prompt_lang("de"),
                            size="1",
                            variant=rx.cond(
                                AIState.editor_prompt_lang == "de",
                                "solid",
                                "soft",
                            ),
                            color_scheme=rx.cond(
                                AIState.editor_prompt_lang == "de",
                                "blue",
                                "gray",
                            ),
                            cursor="pointer",
                        ),
                        rx.button(
                            "EN",
                            on_click=AIState.set_editor_prompt_lang("en"),
                            size="1",
                            variant=rx.cond(
                                AIState.editor_prompt_lang == "en",
                                "solid",
                                "soft",
                            ),
                            color_scheme=rx.cond(
                                AIState.editor_prompt_lang == "en",
                                "blue",
                                "gray",
                            ),
                            cursor="pointer",
                        ),
                        spacing="1",
                    ),
                    width="100%",
                    align="center",
                ),
                # Tab buttons (dynamic from agent's prompt keys)
                rx.hstack(
                    rx.foreach(
                        AIState.editor_prompt_keys,
                        _prompt_tab_button,
                    ),
                    spacing="2",
                    flex_wrap="wrap",
                ),
                # Prompt textarea — DOM-only, no per-keystroke state updates
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

        # TTS Voice Settings (only for existing agents, not vision)
        rx.cond(
            ~is_new & (AIState.editor_role != "vision"),
            rx.vstack(
                rx.hstack(
                    rx.text(
                        "\U0001f50a Sprachausgabe",
                        color="#FFD700",
                        font_weight="bold",
                        font_size="14px",
                    ),
                    rx.spacer(),
                    # Enabled toggle
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
                # Voice dropdown
                rx.hstack(
                    rx.text("Voice", font_size="11px", color="#aaa", width="50px"),
                    rx.select(
                        AIState.available_tts_voices,
                        value=AIState.editor_agent_tts_voice,
                        on_change=AIState.set_editor_agent_tts_voice,
                        placeholder="Default",
                        size="1",
                        width="100%",
                    ),
                    spacing="2",
                    align="center",
                    width="100%",
                ),
                # Speed + Pitch
                rx.hstack(
                    rx.text("Speed", font_size="11px", color="#aaa", width="50px"),
                    rx.select(
                        ["0.8x", "0.9x", "1.0x", "1.1x", "1.2x", "1.25x", "1.5x", "2.0x"],
                        value=AIState.editor_agent_tts_speed,
                        on_change=AIState.set_editor_agent_tts_speed,
                        size="1",
                        width="90px",
                    ),
                    rx.text("Pitch", font_size="11px", color="#aaa", width="50px"),
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
            ),
        ),

        # Action buttons
        rx.hstack(
            rx.button(
                t("agent_editor_save"),
                on_click=rx.call_script(
                    _READ_DOM_JS,
                    callback=AIState.save_agent_editor,
                ),
                color_scheme="green",
                size="2",
                cursor="pointer",
            ),
            rx.cond(
                ~is_new,
                rx.button(
                    t("agent_editor_reset"),
                    on_click=AIState.reset_editor_prompt,
                    color_scheme="orange",
                    variant="soft",
                    size="2",
                    cursor="pointer",
                ),
            ),
            rx.button(
                rx.icon("arrow-left", size=14),
                on_click=AIState.back_to_agent_list,
                color_scheme="gray",
                variant="soft",
                size="2",
                cursor="pointer",
            ),
            spacing="3",
            width="100%",
        ),

        spacing="4",
        width="100%",
        flex="1",
        min_height="0",
        overflow_y="auto",
    )


def _memory_collection_row(col: rx.Var) -> rx.Component:
    """Render a single collection row in the memory browser overview."""
    return rx.hstack(
        rx.text(col["display_name"], font_weight="bold", font_size="13px", flex="1"),
        rx.badge(col["count"], variant="soft", color_scheme="orange"),
        rx.icon_button(
            rx.icon("eye", size=14),
            on_click=AIState.browse_memory_agent(col["agent_id"]),
            size="1",
            variant="soft",
            color_scheme="blue",
            cursor="pointer",
        ),
        width="100%",
        padding="8px 12px",
        background="rgba(255,255,255,0.03)",
        border_radius="6px",
        border="1px solid #333",
        align="center",
        cursor="pointer",
        on_click=AIState.browse_memory_agent(col["agent_id"]),
        style={"&:hover": {"background": "rgba(255,255,255,0.06)"}},
    )


def _memory_entry_row(entry: rx.Var) -> rx.Component:
    """Render a single memory entry with expandable content."""
    return rx.box(
        rx.hstack(
            # Type badge
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
            # Date
            rx.text(entry["date"], font_size="11px", color="#888"),
            rx.spacer(),
            # Delete button
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
        # Summary
        rx.text(
            entry["summary"],
            font_size="15px",
            color="#ddd",
            font_weight="500",
            padding_top="4px",
        ),
        # Content preview
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
        # Source links (research cache entries)
        rx.cond(
            entry["sources"] != "",
            rx.vstack(
                rx.text("Quellen:", font_size="12px", color="#888", font_weight="600", padding_top="8px"),
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


def _memory_browser_view() -> rx.Component:
    """Memory browser view — browse ChromaDB collections and entries."""
    return rx.vstack(
        # Fixed header (tabs)
        _editor_header(),
        # Fixed breadcrumb (only when agent selected)
        rx.cond(
            AIState.memory_browser_agent != "",
            rx.hstack(
                rx.button(
                    rx.icon("arrow-left", size=14),
                    on_click=AIState.open_memory_browser,
                    size="1",
                    variant="soft",
                    color_scheme="gray",
                    cursor="pointer",
                ),
                rx.text(
                    AIState.memory_browser_agent_display,
                    font_weight="bold",
                    font_size="14px",
                    color="#FFD700",
                ),
                rx.badge(
                    AIState.memory_browser_entries.length(),  # type: ignore[union-attr]
                    variant="soft",
                    color_scheme="orange",
                ),
                spacing="2",
                align="center",
                width="100%",
                flex_shrink="0",
                padding_bottom="8px",
                border_bottom="1px solid #333",
            ),
        ),
        # Scrollable content (only this part scrolls)
        rx.box(
            rx.cond(
                AIState.memory_browser_agent == "",
                # Overview: list all collections
                rx.vstack(
                    rx.text(
                        "ChromaDB Collections",
                        font_weight="bold",
                        font_size="14px",
                        color="#FFD700",
                    ),
                    rx.cond(
                        AIState.memory_browser_collections.length() > 0,  # type: ignore[union-attr]
                        rx.foreach(
                            AIState.memory_browser_collections,
                            _memory_collection_row,
                        ),
                        rx.text("No collections found", color="#888", font_size="13px"),
                    ),
                    spacing="2",
                    width="100%",
                ),
                # Detail: entries only
                rx.cond(
                    AIState.memory_browser_entries.length() > 0,  # type: ignore[union-attr]
                    rx.vstack(
                        rx.foreach(
                            AIState.memory_browser_entries,
                            _memory_entry_row,
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    rx.text("No entries", color="#888", font_size="13px"),
                ),
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


def agent_editor_modal() -> rx.Component:
    """Agent Editor fullscreen overlay modal."""
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
            # Modal content — switches between list, edit, and memory view
            rx.box(
                rx.cond(
                    AIState.agent_editor_mode == "edit",
                    _agent_edit_view(),
                    rx.cond(
                        AIState.agent_editor_mode == "memory",
                        _memory_browser_view(),
                        _agent_list_view(),
                    ),
                ),
                padding="25px",
                background_color="#1a1a1a",
                border_radius="12px",
                max_width="95vw",
                width="750px",
                height="90vh",
                max_height="95vh",
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
