"""E-Mail tools for LLM function calling.

Provides email_check, email_read, email_search, email_send tools.
All IMAP/SMTP operations run in asyncio.to_thread() (blocking I/O).
"""

import asyncio
from pathlib import Path

from .function_calling import Tool


def _load_tool_description(name: str) -> str:
    """Load tool description from prompt file."""
    path = Path(__file__).parent.parent.parent / "prompts" / "shared" / f"{name}_tool.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return f"{name} tool"


def get_email_tools() -> list[Tool]:
    """Create email tools for LLM function calling."""

    async def _check_inbox(n: int = 10, folder: str = "INBOX") -> str:
        """Fetch recent emails from inbox."""
        from .email_client import check_inbox
        emails = await asyncio.to_thread(check_inbox, n=min(n, 20), folder=folder)
        if not emails:
            return "No emails found."
        lines = []
        for e in emails:
            status = "📩" if not e.is_read else "📧"
            lines.append(f"{status} [{e.msg_id}] {e.date} — {e.sender}\n   {e.subject}\n   {e.preview}")
        return "\n\n".join(lines)

    async def _read_email(msg_id: str, folder: str = "INBOX") -> str:
        """Read full email by message ID."""
        from .email_client import read_email
        msg = await asyncio.to_thread(read_email, msg_id=msg_id, folder=folder)
        parts = [
            f"From: {msg.sender}",
            f"To: {msg.to}",
            f"Date: {msg.date}",
            f"Subject: {msg.subject}",
        ]
        if msg.attachments:
            parts.append(f"Attachments: {', '.join(msg.attachments)}")
        parts.append(f"\n{msg.body}")
        return "\n".join(parts)

    async def _search_emails(query: str, folder: str = "INBOX") -> str:
        """Search emails by subject or sender."""
        from .email_client import search_emails
        emails = await asyncio.to_thread(search_emails, query=query, folder=folder)
        if not emails:
            return f"No emails found for '{query}'."
        lines = []
        for e in emails:
            lines.append(f"[{e.msg_id}] {e.date} — {e.sender}: {e.subject}")
        return "\n".join(lines)

    async def _send_email(to: str, subject: str, body: str) -> str:
        """Send an email. Returns confirmation or draft for review."""
        # Return draft for user confirmation — do NOT send directly
        return (
            f"EMAIL DRAFT (not sent yet):\n"
            f"To: {to}\n"
            f"Subject: {subject}\n"
            f"Body:\n{body}\n\n"
            f"Ask the user to confirm before sending. "
            f"If confirmed, call send_email_confirmed with the same parameters."
        )

    async def _send_email_confirmed(to: str, subject: str, body: str) -> str:
        """Actually send the email after user confirmation."""
        from .email_client import send_email
        result = await asyncio.to_thread(send_email, to=to, subject=subject, body=body)
        return result

    return [
        Tool(
            name="email_check",
            description=_load_tool_description("email_check"),
            parameters={
                "type": "object",
                "properties": {
                    "n": {
                        "type": "integer",
                        "description": "Number of recent emails to fetch (default 10, max 20)",
                    },
                    "folder": {
                        "type": "string",
                        "description": "IMAP folder (default INBOX)",
                    },
                },
                "required": [],
            },
            executor=_check_inbox,
        ),
        Tool(
            name="email_read",
            description=_load_tool_description("email_read"),
            parameters={
                "type": "object",
                "properties": {
                    "msg_id": {
                        "type": "string",
                        "description": "Message ID from email_check results",
                    },
                    "folder": {
                        "type": "string",
                        "description": "IMAP folder (default INBOX)",
                    },
                },
                "required": ["msg_id"],
            },
            executor=_read_email,
        ),
        Tool(
            name="email_search",
            description=_load_tool_description("email_search"),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term (matches subject and sender)",
                    },
                    "folder": {
                        "type": "string",
                        "description": "IMAP folder (default INBOX)",
                    },
                },
                "required": ["query"],
            },
            executor=_search_emails,
        ),
        Tool(
            name="email_send",
            description=_load_tool_description("email_send"),
            parameters={
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body text",
                    },
                },
                "required": ["to", "subject", "body"],
            },
            executor=_send_email,
        ),
        Tool(
            name="email_send_confirmed",
            description="Send an email that was previously drafted and confirmed by the user. Only call this after the user explicitly confirmed the draft.",
            parameters={
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body text",
                    },
                },
                "required": ["to", "subject", "body"],
            },
            executor=_send_email_confirmed,
        ),
    ]
