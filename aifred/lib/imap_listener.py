"""IMAP IDLE Listener — monitors inbox for new emails.

Maintains a persistent IMAP connection using the IDLE command.
When a new email arrives, it creates an InboundMessage and hands it
to the message processing pipeline.

Runs as an asyncio task, registered with the MessageHub.
"""

import asyncio
import email as email_lib
import email.utils
import imaplib
import ssl
from datetime import datetime, timezone

from .config import (
    EMAIL_ENABLED,
    EMAIL_IMAP_HOST,
    EMAIL_IMAP_PORT,
    EMAIL_MAX_BODY_CHARS,
    EMAIL_PASSWORD,
    EMAIL_USER,
)
from .email_client import _decode_header, _extract_body
from .envelope import InboundMessage
from .logging_utils import log_message

# How often to re-issue IDLE (RFC recommends max 29 min, we use 5 min)
_IDLE_TIMEOUT_SECONDS = 5 * 60

# After a connection error, wait before reconnecting
_RECONNECT_DELAY_SECONDS = 30


def _connect_imap() -> imaplib.IMAP4_SSL:
    """Create a fresh IMAP connection and select INBOX."""
    ctx = ssl.create_default_context()
    imap = imaplib.IMAP4_SSL(EMAIL_IMAP_HOST, EMAIL_IMAP_PORT, ssl_context=ctx)
    imap.login(EMAIL_USER, EMAIL_PASSWORD)
    imap.select("INBOX")
    return imap


def _get_existing_uids(imap: imaplib.IMAP4_SSL) -> set[bytes]:
    """Get all current message UIDs in INBOX."""
    _, data = imap.uid("SEARCH", None, "ALL")  # type: ignore[arg-type]
    if data[0]:
        return set(data[0].split())
    return set()


def _fetch_email_as_inbound(imap: imaplib.IMAP4_SSL, uid: bytes) -> InboundMessage | None:
    """Fetch a single email by UID and convert to InboundMessage."""
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

    # Use Message-ID as channel_id (unique per email thread)
    # For replies, use In-Reply-To or References to find the thread
    thread_id = in_reply_to or references.split()[0] if references else message_id

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


async def imap_idle_loop() -> None:
    """Main IMAP IDLE loop — runs until cancelled.

    1. Connects to IMAP, snapshots existing UIDs
    2. Enters IDLE mode, waits for server notifications
    3. On new mail: fetches it, creates InboundMessage, dispatches
    4. Re-enters IDLE
    5. Reconnects on errors
    """
    if not EMAIL_ENABLED:
        log_message("IMAP Listener: EMAIL_ENABLED is false, not starting")
        return

    if not all([EMAIL_IMAP_HOST, EMAIL_USER, EMAIL_PASSWORD]):
        log_message("IMAP Listener: missing credentials, not starting", "warning")
        return

    log_message("IMAP Listener: starting...")

    while True:
        imap: imaplib.IMAP4_SSL | None = None
        try:
            # Connect and get current state
            imap = await asyncio.to_thread(_connect_imap)
            known_uids = await asyncio.to_thread(_get_existing_uids, imap)
            log_message(f"IMAP Listener: connected, {len(known_uids)} existing messages")

            while True:
                # Enter IDLE mode
                tag = b"A001"
                await asyncio.to_thread(imap.send, tag + b" IDLE\r\n")  # type: ignore[arg-type]

                # Wait for server response (EXISTS = new mail)
                # imaplib doesn't have native IDLE support, so we read raw
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(_read_idle_response, imap),
                        timeout=_IDLE_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    response = b""  # No event, just re-enter IDLE

                # Exit IDLE mode: send DONE and drain the tagged response
                await asyncio.to_thread(imap.send, b"DONE\r\n")  # type: ignore[arg-type]
                await asyncio.to_thread(_drain_idle_response, imap, tag)

                if b"EXISTS" in response:
                    # New mail arrived — find new UIDs
                    current_uids = await asyncio.to_thread(_get_existing_uids, imap)
                    new_uids = current_uids - known_uids

                    for uid in new_uids:
                        inbound = await asyncio.to_thread(
                            _fetch_email_as_inbound, imap, uid
                        )
                        if inbound:
                            log_message(
                                f"IMAP Listener: new email from {inbound.sender} "
                                f"— {inbound.metadata.get('subject', '?')}"
                            )
                            await _dispatch_inbound(inbound)

                    known_uids = current_uids

        except asyncio.CancelledError:
            log_message("IMAP Listener: shutting down")
            if imap:
                try:
                    imap.logout()
                except Exception:
                    pass
            return

        except Exception as exc:
            log_message(f"IMAP Listener: error — {exc}, reconnecting in {_RECONNECT_DELAY_SECONDS}s", "error")
            if imap:
                try:
                    imap.logout()
                except Exception:
                    pass
            await asyncio.sleep(_RECONNECT_DELAY_SECONDS)


def _read_idle_response(imap: imaplib.IMAP4_SSL) -> bytes:
    """Blocking read of one IDLE event from the server.

    Called via asyncio.to_thread() so it doesn't block the event loop.
    Skips the initial "+ idling" acknowledgement and returns the first
    untagged response (e.g. b'* 42 EXISTS').
    """
    while True:
        line = imap.readline()
        if line.startswith(b"+"):
            continue  # Skip IDLE ack ("+ idling")
        return line


def _drain_idle_response(imap: imaplib.IMAP4_SSL, tag: bytes) -> None:
    """Read and discard lines until the tagged IDLE completion response.

    After sending DONE, the server sends the tagged response like
    b'A001 OK IDLE completed'. We need to consume it (and any
    untagged lines before it) so imaplib's state stays clean.
    """
    for _ in range(20):  # Safety limit
        line = imap.readline()
        if line.startswith(tag):
            return  # Got the tagged OK — done
    # If we didn't find the tag, the connection is likely broken.
    # The outer loop will reconnect.


async def _dispatch_inbound(message: InboundMessage) -> None:
    """Hand an inbound message to the message processor."""
    from .message_processor import process_inbound

    outbound = await process_inbound(message)

    if outbound:
        log_message(
            f"IMAP Listener: processed — reply "
            f"{'sent' if outbound.metadata.get('sent') else 'ready'} "
            f"for {outbound.recipient}"
        )
