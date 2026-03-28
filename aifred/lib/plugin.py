"""Tool plugin protocol and context for AIfred's plugin system.

Each tool plugin is a self-contained unit that declares its own availability,
tools, prompt instructions, and UI status messages. Plugins are discovered
automatically by the plugin registry.
"""

from dataclasses import dataclass
from typing import Any, Optional, Protocol, runtime_checkable

from .function_calling import Tool


@dataclass
class PluginContext:
    """Context passed to plugins when creating tools."""

    agent_id: str
    lang: str
    session_id: str
    state: Optional[Any] = None
    user_query: str = ""


@runtime_checkable
class ToolPlugin(Protocol):
    """Protocol that every tool plugin must satisfy."""

    name: str

    def is_available(self) -> bool:
        """Check if this plugin can run right now (config flags, services, etc.)."""
        ...

    def get_tools(self, ctx: PluginContext) -> list[Tool]:
        """Return Tool instances bound to the given context."""
        ...

    def get_prompt_instructions(self, lang: str) -> str:
        """Return prompt text for the LLM system prompt. Empty string if none."""
        ...

    def get_ui_status(self, tool_name: str, tool_args: dict[str, Any], lang: str) -> str:
        """Return UI status string while this tool executes. Empty string if not owned."""
        ...
