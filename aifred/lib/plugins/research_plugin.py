"""Research plugin (web_search, web_fetch, calculate, read_document)."""

from dataclasses import dataclass
from typing import Any

from ..function_calling import Tool
from ..plugin import PluginContext
from ..i18n import t


@dataclass
class ResearchPlugin:
    name: str = "research"

    def is_available(self) -> bool:
        return True

    def get_tools(self, ctx: PluginContext) -> list[Tool]:
        from ..research_tools import get_research_tools
        return get_research_tools(state=ctx.state, lang=ctx.lang)

    def get_prompt_instructions(self, lang: str) -> str:
        return ""

    def get_ui_status(self, tool_name: str, tool_args: dict[str, Any], lang: str) -> str:
        if tool_name == "web_fetch":
            url = tool_args.get("url", "")
            if url:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                return f"🌐 {parsed.netloc}{parsed.path}"
            return ""
        elif tool_name == "web_search":
            queries = tool_args.get("queries", [])
            if queries:
                return f"🔍 {queries[0][:60]}..."
            return t("tool_search", lang=lang)
        elif tool_name == "calculate":
            return f"🔢 {tool_args.get('expression', '')}"
        elif tool_name == "read_document":
            return f"📄 {tool_args.get('path', '')}"
        return ""


plugin = ResearchPlugin()
