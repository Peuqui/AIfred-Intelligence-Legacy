"""EPIM database plugin (epim_search, epim_create, epim_update, epim_delete)."""

from dataclasses import dataclass
from typing import Any

from ..function_calling import Tool
from ..plugin import PluginContext


@dataclass
class EpimPlugin:
    name: str = "epim"

    def is_available(self) -> bool:
        from ..config import EPIM_ENABLED
        if not EPIM_ENABLED:
            return False
        from ..epim_db import get_epim_db
        return get_epim_db() is not None

    def get_tools(self, ctx: PluginContext) -> list[Tool]:
        from ..epim_tools import get_epim_tools
        return get_epim_tools(lang=ctx.lang)

    def get_prompt_instructions(self, lang: str) -> str:
        from ..prompt_loader import load_prompt
        return load_prompt("shared/epim_instructions", lang=lang) or ""

    def get_ui_status(self, tool_name: str, tool_args: dict[str, Any], lang: str) -> str:
        if tool_name == "epim_search":
            entity = tool_args.get("entity_type", "")
            query = tool_args.get("query", "")
            if query:
                return f"📅 {entity}: {query[:40]}"
            return f"📅 {entity}..." if entity else "📅 EPIM..."
        elif tool_name == "epim_create":
            entity = tool_args.get("entity_type", "")
            return f"📅 Erstelle {entity}..." if lang == "de" else f"📅 Creating {entity}..."
        elif tool_name == "epim_update":
            entity = tool_args.get("entity_type", "")
            return f"📅 Aktualisiere {entity}..." if lang == "de" else f"📅 Updating {entity}..."
        elif tool_name == "epim_delete":
            entity = tool_args.get("entity_type", "")
            return f"📅 Lösche {entity}..." if lang == "de" else f"📅 Deleting {entity}..."
        return ""


plugin = EpimPlugin()
