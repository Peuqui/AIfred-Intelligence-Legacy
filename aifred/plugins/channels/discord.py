"""Discord Channel Plugin — Bot listener + reply via discord.py.

Drop-in plugin for the Message Hub channel system.
Connects as a Discord bot and listens for messages in configured channels.
"""

from __future__ import annotations

import asyncio
from datetime import timezone
from typing import TYPE_CHECKING

import discord

from ...lib.plugin_base import BaseChannel, CredentialField
from ...lib.logging_utils import log_message

if TYPE_CHECKING:
    from ...lib.envelope import InboundMessage, OutboundMessage

# After a connection error, wait before reconnecting
_RECONNECT_DELAY_SECONDS = 30

# Module-level reference to the running Discord client.
# Needed so the reply path can send messages back.
_discord_client: discord.Client | None = None


def _parse_channel_ids(ids_str: str) -> set[int]:
    """Parse comma-separated channel IDs from config string."""
    if not ids_str:
        return set()
    ids: set[int] = set()
    for part in ids_str.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


class DiscordChannel(BaseChannel):
    """Discord channel via discord.py bot."""

    # ── Identity ──────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "discord"

    @property
    def display_name(self) -> str:
        return "Discord"

    @property
    def icon(self) -> str:
        return "message-circle"

    # ── Credentials ───────────────────────────────────────────

    @property
    def credential_fields(self) -> list[CredentialField]:
        return [
            CredentialField(
                env_key="DISCORD_BOT_TOKEN",
                label_key="discord_cred_bot_token",
                placeholder="MTIzNDU2Nzg5...",
                is_password=True,
            ),
            CredentialField(
                env_key="DISCORD_CHANNEL_IDS",
                label_key="discord_cred_channel_ids",
                placeholder="123456789,987654321",
            ),
        ]

    def is_configured(self) -> bool:
        from ...lib.config import DISCORD_ENABLED, DISCORD_BOT_TOKEN
        return DISCORD_ENABLED and bool(DISCORD_BOT_TOKEN)

    def apply_credentials(self, values: dict[str, str]) -> None:
        """Update runtime config from saved credentials."""
        import os
        from ...lib import config

        os.environ["DISCORD_ENABLED"] = "true"
        config.DISCORD_ENABLED = True

        token = values.get("DISCORD_BOT_TOKEN", "")
        if token:
            os.environ["DISCORD_BOT_TOKEN"] = token
            config.DISCORD_BOT_TOKEN = token

        channel_ids = values.get("DISCORD_CHANNEL_IDS", "")
        os.environ["DISCORD_CHANNEL_IDS"] = channel_ids
        config.DISCORD_CHANNEL_IDS = channel_ids

    # ── Listener ──────────────────────────────────────────────

    async def listener_loop(self) -> None:
        """Discord bot loop — runs until cancelled."""
        global _discord_client

        from ...lib.config import DISCORD_BOT_TOKEN, DISCORD_CHANNEL_IDS

        if not self.is_configured():
            log_message("Discord Plugin: not configured, not starting", "warning")
            return

        allowed_channels = _parse_channel_ids(DISCORD_CHANNEL_IDS)

        log_message("Discord Plugin: starting bot...")
        if allowed_channels:
            log_message(f"Discord Plugin: watching channels {allowed_channels}")
        else:
            log_message("Discord Plugin: no channel IDs configured, listening on all channels")

        intents = discord.Intents.default()
        intents.message_content = True

        client = discord.Client(intents=intents)
        _discord_client = client

        @client.event
        async def on_ready() -> None:
            log_message(f"Discord Plugin: connected as {client.user}")

        @client.event
        async def on_message(message: discord.Message) -> None:
            # Ignore own messages and other bots
            if message.author == client.user or message.author.bot:
                return

            # Filter by configured channels (empty = all)
            if allowed_channels and message.channel.id not in allowed_channels:
                return

            sender = f"{message.author.display_name} ({message.author.name})"
            timestamp = message.created_at.replace(tzinfo=timezone.utc)

            from ...lib.envelope import InboundMessage

            inbound = InboundMessage(
                channel="discord",
                channel_id=str(message.channel.id),
                sender=sender,
                text=message.content,
                timestamp=timestamp,
                metadata={
                    "guild_id": str(message.guild.id) if message.guild else "",
                    "guild_name": message.guild.name if message.guild else "DM",
                    "channel_name": getattr(message.channel, "name", "DM"),
                    "author_id": str(message.author.id),
                    "message_id": str(message.id),
                },
            )

            log_message(
                f"Discord Plugin: message from {sender} "
                f"in #{inbound.metadata.get('channel_name', '?')}"
            )
            await _dispatch_inbound(inbound)

        try:
            await client.start(DISCORD_BOT_TOKEN)
        except asyncio.CancelledError:
            log_message("Discord Plugin: shutting down")
            await client.close()
            _discord_client = None
        except discord.LoginFailure:
            log_message("Discord Plugin: invalid bot token", "error")
            _discord_client = None
        except Exception as exc:
            log_message(f"Discord Plugin: error — {exc}", "error")
            _discord_client = None

    # ── Reply ─────────────────────────────────────────────────

    async def send_reply(self, outbound: "OutboundMessage", original: "InboundMessage") -> None:
        """Send a reply message to the Discord channel."""
        if not _discord_client:
            log_message("Discord Plugin: no client connected, cannot send reply", "error")
            return

        channel_id = int(outbound.channel_id)
        channel = _discord_client.get_channel(channel_id)
        if not channel:
            log_message(f"Discord Plugin: channel {channel_id} not found", "error")
            return

        # Discord has a 2000 char limit per message
        text = outbound.text
        if len(text) > 2000:
            # Split into chunks
            chunks = [text[i:i + 2000] for i in range(0, len(text), 2000)]
            for chunk in chunks:
                await channel.send(chunk)  # type: ignore[union-attr]
        else:
            await channel.send(text)  # type: ignore[union-attr]

        log_message(f"Discord Plugin: reply sent to #{getattr(channel, 'name', channel_id)}")

    # ── Context ───────────────────────────────────────────────

    def build_context(self, message: "InboundMessage") -> str:
        """Prepare Discord message for LLM."""
        from ...lib.prompt_loader import load_prompt

        return load_prompt(
            "shared/channel_discord",
            sender=message.sender,
            guild_name=message.metadata.get("guild_name", "?"),
            channel_name=message.metadata.get("channel_name", "?"),
            text=message.text,
        )


async def _dispatch_inbound(message: "InboundMessage") -> None:
    """Hand an inbound message to the message processor."""
    from ...lib.message_processor import process_inbound

    outbound = await process_inbound(message)

    if outbound:
        log_message(
            f"Discord Plugin: processed — reply "
            f"{'sent' if outbound.metadata.get('sent') else 'ready'} "
            f"for {outbound.recipient}"
        )


# Module-level instance — discovered by registry
DiscordChannel_instance = DiscordChannel()
