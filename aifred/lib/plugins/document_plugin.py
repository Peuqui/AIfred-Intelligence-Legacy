"""Document store plugin (search_documents, list_documents, delete_document)."""

from dataclasses import dataclass
from typing import Any

from ..function_calling import Tool
from ..plugin import PluginContext
from ..i18n import t


@dataclass
class DocumentPlugin:
    name: str = "document"

    def is_available(self) -> bool:
        from ..document_store import get_document_store
        return get_document_store() is not None

    def get_tools(self, ctx: PluginContext) -> list[Tool]:
        from ..document_tools import get_document_tools
        return get_document_tools()

    def get_prompt_instructions(self, lang: str) -> str:
        return ""

    def get_ui_status(self, tool_name: str, tool_args: dict[str, Any], lang: str) -> str:
        if tool_name == "search_documents":
            query = tool_args.get("query", "")
            return f"📄 {query[:50]}" if query else t("tool_doc_search", lang=lang)
        elif tool_name == "list_documents":
            return t("tool_doc_list", lang=lang)
        elif tool_name == "delete_document":
            return t("tool_doc_delete", lang=lang, filename=tool_args.get("filename", ""))
        return ""


plugin = DocumentPlugin()
