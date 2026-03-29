"""Template: Channel Plugin for AIfred.

Copy this file to aifred/plugins/channels/ and customize.
It will be auto-discovered on next AIfred restart.

This example shows the minimal structure for a message channel.
Replace the placeholder implementations with your service's API.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ...lib.plugin_base import BaseChannel, CredentialField
from ...lib.logging_utils import log_message

if TYPE_CHECKING:
    from ...lib.envelope import InboundMessage, OutboundMessage
    from ...lib.function_calling import Tool
    from ...lib.plugin_base import PluginContext


class MyChannel(BaseChannel):
    """Template channel plugin."""

    # ── Identity ──────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "my_channel"

    @property
    def display_name(self) -> str:
        return "My Channel"

    @property
    def icon(self) -> str:
        return "message-circle"  # Lucide icon name

    # ── Credentials ───────────────────────────────────────────

    @property
    def credential_fields(self) -> list[CredentialField]:
        return [
            CredentialField(
                env_key="MY_CHANNEL_TOKEN",
                label_key="my_channel_token",  # Add to aifred/lib/i18n.py
                placeholder="your-api-token",
                is_password=True,
            ),
        ]

    def is_configured(self) -> bool:
        import os
        return bool(os.environ.get("MY_CHANNEL_TOKEN"))

    def apply_credentials(self, values: dict[str, str]) -> None:
        import os
        token = values.get("MY_CHANNEL_TOKEN", "")
        if token:
            os.environ["MY_CHANNEL_TOKEN"] = token

    # ── Listener ──────────────────────────────────────────────

    async def listener_loop(self) -> None:
        """Long-running listener. Replace with your service's event loop."""
        if not self.is_configured():
            log_message(f"{self.display_name}: not configured", "warning")
            return

        log_message(f"{self.display_name}: starting listener...")

        try:
            while True:
                # TODO: Replace with your service's message polling/websocket
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            log_message(f"{self.display_name}: shutting down")

    # ── Reply ─────────────────────────────────────────────────

    async def send_reply(self, outbound: "OutboundMessage", original: "InboundMessage") -> None:
        """Send a reply via your service's API."""
        # TODO: Implement sending
        log_message(f"{self.display_name}: reply to {outbound.recipient}: {outbound.text[:50]}...")

    # ── Context ───────────────────────────────────────────────

    def build_context(self, message: "InboundMessage") -> str:
        """Build LLM context from incoming message.

        Use prompt files from prompts/de/ and prompts/en/ instead of hardcoded text.
        """
        from ...lib.prompt_loader import load_prompt
        return load_prompt(
            "shared/channel_my_channel",  # Create this prompt file
            sender=message.sender,
            text=message.text,
        )

    # ── Optional: Tools ───────────────────────────────────────

    def get_tools(self, ctx: "PluginContext") -> list["Tool"]:
        """Optional: Provide tools for active sending via this channel."""
        return []  # Override to add send tools


# Module-level instance — REQUIRED for auto-discovery
MyChannel_instance = MyChannel()
