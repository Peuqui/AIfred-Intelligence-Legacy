"""E-Mail client for IMAP (read) and SMTP (send).

All operations are synchronous (imaplib/smtplib) — wrapped in
asyncio.to_thread() by the tool executors.

Credentials are accessed exclusively through the CredentialBroker.
"""

import email
import email.header
import email.utils
import imaplib
import smtplib
import ssl
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from ....lib.config import EMAIL_MAX_BODY_CHARS, EMAIL_MAX_FETCH
from ....lib.credential_broker import broker
from ....lib.logging_utils import log_message


@dataclass
class EmailSummary:
    """Compact email representation for inbox listing."""

    msg_id: str
    subject: str
    sender: str
    date: str
    preview: str  # First ~200 chars of body
    is_read: bool = True


@dataclass
class EmailMessage:
    """Full email with body text."""

    msg_id: str
    subject: str
    sender: str
    to: str
    date: str
    body: str
    attachments: list[str] = field(default_factory=list)  # Attachment filenames


def _decode_header(raw: Optional[str]) -> str:
    """Decode RFC2047 encoded header."""
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _extract_body(msg: email.message.Message) -> str:
    """Extract plain text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        # Fallback: try text/html
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return f"[HTML]\n{payload.decode(charset, errors='replace')}"
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def _get_attachments(msg: email.message.Message) -> list[str]:
    """Get list of attachment filenames."""
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                filename = part.get_filename()
                if filename:
                    attachments.append(_decode_header(filename))
    return attachments


def _imap_connect() -> imaplib.IMAP4_SSL:
    """Create authenticated IMAP connection via broker."""
    ctx = ssl.create_default_context()
    host = broker.get("email", "imap_host")
    port = int(broker.get("email", "imap_port") or "993")
    imap = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
    imap.login(broker.get("email", "user"), broker.get("email", "password"))
    return imap


def check_inbox(n: int = EMAIL_MAX_FETCH, folder: str = "INBOX") -> list[EmailSummary]:
    """Fetch the N most recent emails from IMAP inbox."""
    results: list[EmailSummary] = []

    with _imap_connect() as imap:
        imap.select(folder, readonly=True)

        _, data = imap.search(None, "ALL")
        msg_ids = data[0].split()
        recent_ids = msg_ids[-n:] if len(msg_ids) > n else msg_ids
        recent_ids.reverse()  # Newest first

        for msg_id in recent_ids:
            _, msg_data = imap.fetch(msg_id, "(FLAGS RFC822.HEADER BODY.PEEK[TEXT]<0.400>)")
            if not msg_data or not msg_data[0]:
                continue

            # Parse flags
            flags_raw = ""
            header_raw = b""
            preview_raw = b""

            for part in msg_data:
                if isinstance(part, tuple):
                    desc = part[0].decode("utf-8", errors="replace") if isinstance(part[0], bytes) else str(part[0])
                    if "FLAGS" in desc:
                        flags_raw = desc
                    if "HEADER" in desc:
                        header_raw = part[1] if len(part) > 1 else b""
                    if "TEXT" in desc or "BODY" in desc:
                        preview_raw = part[1] if len(part) > 1 else b""

            is_read = "\\Seen" in flags_raw

            if header_raw:
                msg = email.message_from_bytes(header_raw)
                subject = _decode_header(msg.get("Subject", ""))
                sender = _decode_header(msg.get("From", ""))
                date = msg.get("Date", "")
                # Parse date to readable format
                parsed_date = email.utils.parsedate_to_datetime(date) if date else None
                date_str = parsed_date.strftime("%d.%m.%Y %H:%M") if parsed_date else date

                preview = preview_raw.decode("utf-8", errors="replace")[:200].strip()

                results.append(EmailSummary(
                    msg_id=msg_id.decode(),
                    subject=subject,
                    sender=sender,
                    date=date_str,
                    preview=preview,
                    is_read=is_read,
                ))

    log_message(f"📧 Email: fetched {len(results)} from {folder}")
    return results


def read_email(msg_id: str, folder: str = "INBOX") -> EmailMessage:
    """Read full email by message ID."""
    with _imap_connect() as imap:
        imap.select(folder, readonly=True)

        _, msg_data = imap.fetch(msg_id.encode(), "(RFC822)")
        if not msg_data or not msg_data[0] or not isinstance(msg_data[0], tuple):
            raise ValueError(f"Email {msg_id} not found")

        msg = email.message_from_bytes(msg_data[0][1])
        body = _extract_body(msg)[:EMAIL_MAX_BODY_CHARS]
        attachments = _get_attachments(msg)

        date = msg.get("Date", "")
        parsed_date = email.utils.parsedate_to_datetime(date) if date else None
        date_str = parsed_date.strftime("%d.%m.%Y %H:%M") if parsed_date else date

        log_message(f"📧 Email: read msg {msg_id}")
        return EmailMessage(
            msg_id=msg_id,
            subject=_decode_header(msg.get("Subject", "")),
            sender=_decode_header(msg.get("From", "")),
            to=_decode_header(msg.get("To", "")),
            date=date_str,
            body=body,
            attachments=attachments,
        )


def search_emails(query: str, folder: str = "INBOX", n: int = EMAIL_MAX_FETCH) -> list[EmailSummary]:
    """Search emails via IMAP SEARCH."""
    results: list[EmailSummary] = []

    with _imap_connect() as imap:
        imap.select(folder, readonly=True)

        # IMAP SEARCH: search in subject and from
        search_criteria = f'(OR SUBJECT "{query}" FROM "{query}")'
        _, data = imap.search(None, search_criteria)
        msg_ids = data[0].split()[-n:]
        msg_ids.reverse()

        for msg_id in msg_ids:
            _, msg_data = imap.fetch(msg_id, "(FLAGS RFC822.HEADER)")
            if not msg_data or not msg_data[0]:
                continue

            for part in msg_data:
                if isinstance(part, tuple) and b"HEADER" in part[0]:
                    msg = email.message_from_bytes(part[1])
                    date = msg.get("Date", "")
                    parsed_date = email.utils.parsedate_to_datetime(date) if date else None

                    results.append(EmailSummary(
                        msg_id=msg_id.decode(),
                        subject=_decode_header(msg.get("Subject", "")),
                        sender=_decode_header(msg.get("From", "")),
                        date=parsed_date.strftime("%d.%m.%Y %H:%M") if parsed_date else date,
                        preview="",
                    ))

    log_message(f"📧 Email: search '{query}' → {len(results)} results")
    return results


def send_email(to: str, subject: str, body: str, reply_to_id: Optional[str] = None) -> str:
    """Send an email via SMTP. Returns confirmation string."""
    email_user = broker.get("email", "user")
    email_from = broker.get("email", "from") or email_user

    # If EMAIL_FROM is a display name without address, combine with EMAIL_USER
    if email_from and "@" not in email_from:
        sender = f'"{email_from}" <{email_user}>'
    else:
        sender = email_from

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    # Generate Message-ID so replies can be routed back
    import email.utils as _eu
    message_id = _eu.make_msgid(domain=email_user.split("@")[-1] if "@" in email_user else "local")
    msg["Message-ID"] = message_id
    if reply_to_id:
        msg["In-Reply-To"] = reply_to_id
        msg["References"] = reply_to_id
    msg.attach(MIMEText(body, "plain", "utf-8"))

    smtp_host = broker.get("email", "smtp_host")
    smtp_port = int(broker.get("email", "smtp_port") or "587")
    ctx = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.starttls(context=ctx)
        smtp.login(email_user, broker.get("email", "password"))
        smtp.send_message(msg)

    log_message(f"📧 Email: sent to {to} — {subject} (Message-ID: {message_id})")
    return f"Email sent to {to}: {subject} [msg_id:{message_id}]"


def delete_email(msg_id: str, folder: str = "INBOX") -> str:
    """Delete an email by message ID (moves to Trash)."""
    with _imap_connect() as imap:
        imap.select(folder)
        imap.store(msg_id.encode(), '+FLAGS', '\\Deleted')
        imap.expunge()

    log_message(f"📧 Email: deleted msg {msg_id} from {folder}")
    return f"Email {msg_id} deleted from {folder}"
