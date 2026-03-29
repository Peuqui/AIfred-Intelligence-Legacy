"""Email plugin."""

from dataclasses import dataclass
from typing import Any

from ....lib.function_calling import Tool
from ....lib.plugin_base import PluginContext
from ....lib.i18n import t


@dataclass
class EmailPlugin:
    name: str = "email"

    def is_available(self) -> bool:
        from ....lib.config import EMAIL_ENABLED
        return EMAIL_ENABLED

    def get_tools(self, ctx: PluginContext) -> list[Tool]:
        from .tools import get_email_tools
        return get_email_tools(session_id=ctx.session_id)

    def get_prompt_instructions(self, lang: str) -> str:
        return ""

    def get_ui_status(self, tool_name: str, tool_args: dict[str, Any], lang: str) -> str:
        if tool_name != "email":
            return ""
        if not tool_args:
            return t("tool_email", lang=lang)
        action = tool_args.get("action", "")
        if action == "check":
            return t("tool_email_check", lang=lang)
        elif action == "read":
            return t("tool_email_read", lang=lang, msg_id=tool_args.get("msg_id", ""))
        elif action == "search":
            return t("tool_email_search", lang=lang, query=tool_args.get("query", "")[:40])
        elif action == "delete":
            return t("tool_email_delete", lang=lang, msg_id=tool_args.get("msg_id", ""))
        elif action == "send":
            return t("tool_email_send", lang=lang, to=tool_args.get("to", "")[:30])
        return t("tool_email", lang=lang)


plugin = EmailPlugin()
