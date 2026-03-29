"""E-Mail Channel Plugin — IMAP IDLE listener + SMTP reply.

Drop-in plugin for the Message Hub channel system.
Monitors an IMAP inbox via IDLE and sends replies via SMTP.
"""

from __future__ import annotations

import asyncio
import email as email_lib
import email.utils
import imaplib
import ssl
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ...lib.plugin_base import BaseChannel, CredentialField
from ...lib.logging_utils import log_message

if TYPE_CHECKING:
    from ...lib.envelope import InboundMessage, OutboundMessage

# How often to re-issue IDLE (RFC recommends max 29 min, we use 5 min)
_IDLE_TIMEOUT_SECONDS = 5 * 60

# After a connection error, wait before reconnecting
_RECONNECT_DELAY_SECONDS = 30


class EmailChannel(BaseChannel):
    """E-Mail channel via IMAP IDLE + SMTP."""

    # ── Identity ──────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "email"

    @property
    def display_name(self) -> str:
        return "E-Mail Monitor"

    @property
    def icon(self) -> str:
        return "mail"

    # ── Credentials ───────────────────────────────────────────

    @property
    def credential_fields(self) -> list[CredentialField]:
        return [
            CredentialField(
                env_key="EMAIL_IMAP_HOST",
                label_key="email_cred_imap_host",
                placeholder="imap.example.com",
                group="imap",
                width_ratio=3,
            ),
            CredentialField(
                env_key="EMAIL_IMAP_PORT",
                label_key="email_cred_imap_port",
                default="993",
                group="imap",
                width_ratio=1,
            ),
            CredentialField(
                env_key="EMAIL_SMTP_HOST",
                label_key="email_cred_smtp_host",
                placeholder="smtp.example.com",
                group="smtp",
                width_ratio=3,
            ),
            CredentialField(
                env_key="EMAIL_SMTP_PORT",
                label_key="email_cred_smtp_port",
                default="587",
                group="smtp",
                width_ratio=1,
            ),
            CredentialField(
                env_key="EMAIL_USER",
                label_key="email_cred_user",
                placeholder="user@example.com",
            ),
            CredentialField(
                env_key="EMAIL_PASSWORD",
                label_key="email_cred_password",
                is_password=True,
            ),
            CredentialField(
                env_key="EMAIL_FROM",
                label_key="email_cred_from",
                placeholder="Display Name",
            ),
        ]

    def is_configured(self) -> bool:
        from ...lib.config import EMAIL_ENABLED, EMAIL_IMAP_HOST, EMAIL_USER, EMAIL_PASSWORD
        return EMAIL_ENABLED and bool(EMAIL_IMAP_HOST and EMAIL_USER and EMAIL_PASSWORD)

    def apply_credentials(self, values: dict[str, str]) -> None:
        """Update runtime config from saved credentials."""
        import os
        from ...lib import config

        os.environ["EMAIL_ENABLED"] = "true"
        config.EMAIL_ENABLED = True

        field_map = {
            "EMAIL_IMAP_HOST": "EMAIL_IMAP_HOST",
            "EMAIL_IMAP_PORT": "EMAIL_IMAP_PORT",
            "EMAIL_SMTP_HOST": "EMAIL_SMTP_HOST",
            "EMAIL_SMTP_PORT": "EMAIL_SMTP_PORT",
            "EMAIL_USER": "EMAIL_USER",
            "EMAIL_PASSWORD": "EMAIL_PASSWORD",
            "EMAIL_FROM": "EMAIL_FROM",
        }
        for env_key, config_attr in field_map.items():
            val = values.get(env_key, "")
            if not val:
                continue
            os.environ[env_key] = val
            if config_attr in ("EMAIL_IMAP_PORT", "EMAIL_SMTP_PORT"):
                setattr(config, config_attr, int(val))
            else:
                setattr(config, config_attr, val)

        # Default EMAIL_FROM to EMAIL_USER
        if not values.get("EMAIL_FROM"):
            from_val = values.get("EMAIL_USER", "")
            os.environ["EMAIL_FROM"] = from_val
            config.EMAIL_FROM = from_val

    # ── Listener ──────────────────────────────────────────────

    async def listener_loop(self) -> None:
        """IMAP IDLE loop — runs until cancelled."""
        from ...lib.config import EMAIL_IMAP_HOST, EMAIL_IMAP_PORT, EMAIL_USER, EMAIL_PASSWORD

        if not self.is_configured():
            log_message("Email Plugin: not configured, not starting", "warning")
            return

        log_message("Email Plugin: starting IMAP IDLE listener...")

        while True:
            imap: imaplib.IMAP4_SSL | None = None
            try:
                imap = await asyncio.to_thread(
                    _connect_imap, EMAIL_IMAP_HOST, EMAIL_IMAP_PORT, EMAIL_USER, EMAIL_PASSWORD
                )
                known_uids = await asyncio.to_thread(_get_existing_uids, imap)
                log_message(f"Email Plugin: connected, {len(known_uids)} existing messages")

                while True:
                    # Enter IDLE mode
                    tag = b"A001"
                    await asyncio.to_thread(imap.send, tag + b" IDLE\r\n")  # type: ignore[arg-type]

                    try:
                        response = await asyncio.wait_for(
                            asyncio.to_thread(_read_idle_response, imap),
                            timeout=_IDLE_TIMEOUT_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        response = b""

                    # Exit IDLE
                    await asyncio.to_thread(imap.send, b"DONE\r\n")  # type: ignore[arg-type]
                    await asyncio.to_thread(_drain_idle_response, imap, tag)

                    if b"EXISTS" in response:
                        current_uids = await asyncio.to_thread(_get_existing_uids, imap)
                        new_uids = current_uids - known_uids

                        for uid in new_uids:
                            inbound = await asyncio.to_thread(
                                _fetch_email_as_inbound, imap, uid
                            )
                            if inbound:
                                log_message(
                                    f"Email Plugin: new mail from {inbound.sender} "
                                    f"— {inbound.metadata.get('subject', '?')}"
                                )
                                await _dispatch_inbound(inbound)

                        known_uids = current_uids

            except asyncio.CancelledError:
                log_message("Email Plugin: shutting down")
                if imap:
                    try:
                        imap.logout()
                    except Exception:
                        pass
                return

            except Exception as exc:
                log_message(f"Email Plugin: error — {exc}, reconnecting in {_RECONNECT_DELAY_SECONDS}s", "error")
                if imap:
                    try:
                        imap.logout()
                    except Exception:
                        pass
                await asyncio.sleep(_RECONNECT_DELAY_SECONDS)

    # ── Reply ─────────────────────────────────────────────────

    async def send_reply(self, outbound: "OutboundMessage", original: "InboundMessage") -> None:
        """Send an email reply via SMTP."""
        from ..tools.email_tools.client import send_email

        subject = outbound.metadata.get("subject", "Re: AIfred")
        reply_to_id = outbound.metadata.get("in_reply_to")

        send_email(
            to=outbound.recipient,
            subject=subject,
            body=outbound.text,
            reply_to_id=reply_to_id,
        )
        from ...lib.debug_bus import debug
        debug(f"📤 Auto-reply sent to {outbound.recipient}")

    # ── Context ───────────────────────────────────────────────

    def build_context(self, message: "InboundMessage") -> str:
        """Prepare email for LLM with sender/subject context."""
        from ...lib.prompt_loader import load_prompt

        subject = message.metadata.get("subject", "?")
        return load_prompt(
            "shared/channel_email",
            sender=message.sender,
            subject=subject,
            text=message.text,
        )

    def build_reply_metadata(self, message: "InboundMessage") -> dict:
        """Build email-specific reply headers (In-Reply-To, References)."""
        subject = message.metadata.get("subject", "")
        if subject and not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        return {
            "subject": subject,
            "in_reply_to": message.metadata.get("message_id", ""),
            "references": message.metadata.get("message_id", ""),
        }


# ── IMAP helpers (moved from imap_listener.py) ───────────────


def _connect_imap(host: str, port: int, user: str, password: str) -> imaplib.IMAP4_SSL:
    """Create a fresh IMAP connection and select INBOX."""
    ctx = ssl.create_default_context()
    imap = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
    imap.login(user, password)
    imap.select("INBOX")
    return imap


def _get_existing_uids(imap: imaplib.IMAP4_SSL) -> set[bytes]:
    """Get all current message UIDs in INBOX."""
    _, data = imap.uid("SEARCH", None, "ALL")  # type: ignore[arg-type]
    if data[0]:
        return set(data[0].split())
    return set()


def _fetch_email_as_inbound(imap: imaplib.IMAP4_SSL, uid: bytes) -> "InboundMessage | None":
    """Fetch a single email by UID and convert to InboundMessage."""
    from ..tools.email_tools.client import _decode_header, _extract_body
    from ...lib.config import EMAIL_MAX_BODY_CHARS
    from ...lib.envelope import InboundMessage

    _, msg_data = imap.uid("FETCH", uid, "(RFC822)")  # type: ignore[arg-type]
    if not msg_data or not msg_data[0] or not isinstance(msg_data[0], tuple):
        return None

    msg = email_lib.message_from_bytes(msg_data[0][1])

    sender = _decode_header(msg.get("From", ""))
    subject = _decode_header(msg.get("Subject", ""))
    body = _extract_body(msg)[:EMAIL_MAX_BODY_CHARS]
    message_id = msg.get("Message-ID", "")
    in_reply_to = msg.get("In-Reply-To", "")
    references = msg.get("References", "")

    # Parse date
    date_raw = msg.get("Date", "")
    try:
        timestamp = email_lib.utils.parsedate_to_datetime(date_raw)
    except (ValueError, TypeError):
        timestamp = datetime.now(timezone.utc)

    # Thread-ID: use In-Reply-To or first Reference, or Message-ID
    thread_id = in_reply_to or (references.split()[0] if references else message_id)

    return InboundMessage(
        channel="email",
        channel_id=thread_id,
        sender=sender,
        text=body,
        timestamp=timestamp,
        metadata={
            "subject": subject,
            "message_id": message_id,
            "in_reply_to": in_reply_to,
            "references": references,
            "uid": uid.decode(),
        },
    )


def _read_idle_response(imap: imaplib.IMAP4_SSL) -> bytes:
    """Blocking read of one IDLE event from the server."""
    while True:
        line = imap.readline()
        if line.startswith(b"+"):
            continue  # Skip IDLE ack ("+ idling")
        return line


def _drain_idle_response(imap: imaplib.IMAP4_SSL, tag: bytes) -> None:
    """Read and discard lines until the tagged IDLE completion response."""
    for _ in range(20):
        line = imap.readline()
        if line.startswith(tag):
            return


async def _dispatch_inbound(message: "InboundMessage") -> None:
    """Hand an inbound message to the message processor."""
    from ...lib.message_processor import process_inbound

    outbound = await process_inbound(message)

    if outbound:
        log_message(
            f"Email Plugin: processed — reply "
            f"{'sent' if outbound.metadata.get('sent') else 'ready'} "
            f"for {outbound.recipient}"
        )


# Module-level instance — discovered by registry
EmailChannel_instance = EmailChannel()
