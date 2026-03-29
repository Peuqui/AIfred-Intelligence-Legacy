"""Base classes for the AIfred plugin system.

Two plugin types:
- ToolPlugin: Provides tools the LLM can call (search, EPIM, sandbox, ...)
- BaseChannel: Receives/sends messages via external services (email, Discord, ...)

Both are discovered automatically from aifred/plugins/tools/ and
aifred/plugins/channels/ by the unified registry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..lib.envelope import InboundMessage, OutboundMessage
    from ..lib.function_calling import Tool


# ============================================================
# TOOL PLUGIN
# ============================================================

@dataclass
class PluginContext:
    """Context passed to tool plugins when creating tools."""

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

    def get_tools(self, ctx: "PluginContext") -> list["Tool"]:
        """Return Tool instances bound to the given context."""
        ...

    def get_prompt_instructions(self, lang: str) -> str:
        """Return prompt text for the LLM system prompt. Empty string if none."""
        ...

    def get_ui_status(self, tool_name: str, tool_args: dict[str, Any], lang: str) -> str:
        """Return UI status string while this tool executes. Empty string if not owned."""
        ...


# ============================================================
# CHANNEL PLUGIN
# ============================================================

@dataclass
class CredentialField:
    """Describes a single credential field for the Settings UI."""

    env_key: str            # Environment variable name
    label_key: str          # i18n key for the label
    placeholder: str = ""
    default: str = ""
    is_password: bool = False
    width_ratio: int = 1    # Relative width in a row
    group: str = ""         # Group fields into one hstack


class BaseChannel(ABC):
    """Abstract base class for all message channel plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        ...

    @property
    @abstractmethod
    def icon(self) -> str:
        ...

    @property
    @abstractmethod
    def credential_fields(self) -> list[CredentialField]:
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        ...

    @abstractmethod
    def apply_credentials(self, values: dict[str, str]) -> None:
        ...

    @abstractmethod
    async def listener_loop(self) -> None:
        ...

    @abstractmethod
    async def send_reply(self, outbound: "OutboundMessage", original: "InboundMessage") -> None:
        ...

    @abstractmethod
    def build_context(self, message: "InboundMessage") -> str:
        ...

    def build_reply_metadata(self, message: "InboundMessage") -> dict:
        return {}

    def get_tools(self, ctx: "PluginContext") -> list["Tool"]:
        """Optional: Return tools this channel provides for LLM function calling.

        Override to expose channel-specific tools (e.g. discord_send).
        Default: no tools.
        """
        return []
