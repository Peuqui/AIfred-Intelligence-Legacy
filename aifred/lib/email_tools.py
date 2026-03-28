"""E-Mail tool for LLM function calling.

Single `email` tool with action parameter to reduce tool count.
All IMAP/SMTP operations run in asyncio.to_thread() (blocking I/O).
"""

import asyncio

from .function_calling import Tool
from .prompt_loader import load_tool_description


def get_email_tools(session_id: str = "") -> list[Tool]:
    """Create email tool for LLM function calling."""

    async def _email(action: str, **kwargs: str) -> str:
        """Unified email tool — dispatches by action."""
        action = action.lower().strip()

        if action == "check":
            from .email_client import check_inbox
            n = int(kwargs.get("n", "10"))
            folder = kwargs.get("folder", "INBOX")
            emails = await asyncio.to_thread(check_inbox, n=min(n, 20), folder=folder)
            if not emails:
                return "No emails found."
            lines = []
            for e in emails:
                status = "📩" if not e.is_read else "📧"
                lines.append(f"{status} [{e.msg_id}] {e.date} — {e.sender}\n   {e.subject}\n   {e.preview}")
            return "\n\n".join(lines)

        elif action == "read":
            from .email_client import read_email
            msg_id = kwargs.get("msg_id", "")
            if not msg_id:
                return "Error: msg_id required"
            folder = kwargs.get("folder", "INBOX")
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

        elif action == "search":
            from .email_client import search_emails
            query = kwargs.get("query", "")
            if not query:
                return "Error: query required"
            folder = kwargs.get("folder", "INBOX")
            emails = await asyncio.to_thread(search_emails, query=query, folder=folder)
            if not emails:
                return f"No emails found for '{query}'."
            lines = []
            for e in emails:
                lines.append(f"[{e.msg_id}] {e.date} — {e.sender}: {e.subject}")
            return "\n".join(lines)

        elif action == "delete":
            from .email_client import delete_email
            msg_id = kwargs.get("msg_id", "")
            if not msg_id:
                return "Error: msg_id required"
            folder = kwargs.get("folder", "INBOX")
            result = await asyncio.to_thread(delete_email, msg_id=msg_id, folder=folder)
            return result

        elif action == "send":
            from .email_client import send_email
            to = kwargs.get("to", "")
            subject = kwargs.get("subject", "")
            body = kwargs.get("body", "")
            if not to or not subject or not body:
                return "Error: to, subject, body required"
            result = await asyncio.to_thread(send_email, to=to, subject=subject, body=body)

            # Register route so replies land in the same session
            if session_id and "[msg_id:" in result:
                msg_id = result.split("[msg_id:")[1].rstrip("]")
                from .routing_table import routing_table
                routing_table.set_route("email", msg_id, session_id)

            return result

        else:
            return f"Unknown action: {action}. Valid: check, read, search, delete, send"

    return [
        Tool(
            name="email",
            description=load_tool_description("email_tool.txt"),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["check", "read", "search", "delete", "send"],
                        "description": "Action to perform",
                    },
                    "msg_id": {
                        "type": "string",
                        "description": "Message ID (for read, delete)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search term (for search)",
                    },
                    "n": {
                        "type": "string",
                        "description": "Number of emails to fetch (for check, default 10)",
                    },
                    "to": {
                        "type": "string",
                        "description": "Recipient email address (for send)",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject (for send)",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body (for send)",
                    },
                    "folder": {
                        "type": "string",
                        "description": "IMAP folder (default INBOX)",
                    },
                },
                "required": ["action"],
            },
            executor=_email,
        ),
    ]
