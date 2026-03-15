"""Agent Editor Modal for AIfred UI.

Fullscreen overlay for managing agent configurations:
- List all configured agents
- Edit agent metadata (name, emoji, role, description)
- Edit prompt layers (identity, personality, task, etc.) via text editor
- Create new agents from role templates
- Delete custom agents (default agents protected)
"""
# mypy: disable-error-code="index, operator, call-arg, func-returns-value, arg-type"
# Reflex UI code: Var indexing, rx.icon module callable, event handler binding
# are all runtime-correct but not statically typeable.

from __future__ import annotations

import reflex as rx

from ..state import AIState
from .helpers import t


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


def _agent_list_view() -> rx.Component:
    """The agent list view (main view of the editor)."""
    return rx.vstack(
        # Header
        rx.hstack(
            rx.icon("users", size=24, color="#FFD700"),
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

        # Agent ID (only for new agents)
        rx.cond(
            is_new,
            rx.vstack(
                rx.text(t("agent_editor_id"), color="#aaa", font_size="12px"),
                rx.el.input(
                    id="editor-agent-id",
                    placeholder="z.B. dr_house",
                    width="100%",
                    color="white",
                    background_color="#333",
                    border="1px solid #555",
                    border_radius="6px",
                    padding="6px 10px",
                    font_size="14px",
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

        # Metadata fields
        rx.hstack(
            # Name (pure DOM, no state binding)
            rx.vstack(
                rx.text(t("agent_editor_name"), color="#aaa", font_size="12px"),
                rx.el.input(
                    id="editor-name",
                    width="100%",
                    color="white",
                    background_color="#333",
                    border="1px solid #555",
                    border_radius="6px",
                    padding="6px 10px",
                    font_size="14px",
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

        # Role selector
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

        # Description (pure DOM, no state binding)
        rx.vstack(
            rx.text(t("agent_editor_description"), color="#aaa", font_size="12px"),
            rx.el.input(
                id="editor-description",
                width="100%",
                color="white",
                background_color="#333",
                border="1px solid #555",
                border_radius="6px",
                padding="6px 10px",
                font_size="14px",
            ),
            spacing="1",
            width="100%",
        ),

        # Prompt Layer Editor (only when editing existing agent)
        rx.cond(
            ~is_new,
            rx.vstack(
                rx.text(
                    t("agent_editor_prompts"),
                    color="#FFD700",
                    font_weight="bold",
                    font_size="14px",
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
                # Prompt textarea — pure DOM, populated via JS
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
                    style={"resize": "vertical"},
                ),
                spacing="2",
                width="100%",
            ),
        ),

        # Action buttons
        rx.hstack(
            rx.button(
                t("agent_editor_save"),
                on_click=AIState.save_agent_editor,  # reads DOM via call_script
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
            # Modal content - switches between list and edit view
            rx.box(
                rx.cond(
                    AIState.agent_editor_mode == "edit",
                    _agent_edit_view(),
                    _agent_list_view(),
                ),
                padding="25px",
                background_color="#1a1a1a",
                border_radius="12px",
                max_width="95vw",
                width="700px",
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
