"""Document plugin (search, list, delete, read documents)."""

import json
from dataclasses import dataclass
from typing import Any

from ...lib.function_calling import Tool
from ...lib.plugin_base import PluginContext
from ...lib.i18n import t


@dataclass
class DocumentPlugin:
    name: str = "document"
    display_name: str = "Documents"

    def is_available(self) -> bool:
        from ...lib.document_store import get_document_store
        return get_document_store() is not None

    def get_tools(self, ctx: PluginContext) -> list[Tool]:
        from ...lib.document_tools import get_document_tools
        tools = get_document_tools()

        async def _execute_read(path: str) -> str:
            """Read a local document (uploaded files, PDFs, text files)."""
            from pathlib import Path as P
            from ...lib.logging_utils import log_message

            base_dir = P(__file__).parent.parent.parent.parent / "data"
            try:
                file_path = (base_dir / path).resolve()
                if not str(file_path).startswith(str(base_dir.resolve())):
                    return json.dumps({"error": "Access denied: path outside data directory"})
            except Exception:
                return json.dumps({"error": f"Invalid path: {path}"})

            if not file_path.exists():
                return json.dumps({"error": f"File not found: {path}"})

            log_message(f"📄 read_document: {file_path.name}")

            try:
                if file_path.suffix.lower() == ".pdf":
                    import fitz  # PyMuPDF
                    doc = fitz.open(str(file_path))
                    text = "\n\n".join(page.get_text() for page in doc)
                    doc.close()
                    log_message(f"✅ read_document: PDF {file_path.name} ({len(text)} chars)")
                    return f"# {file_path.name}\n\n{text}"
                else:
                    text = file_path.read_text(encoding="utf-8")
                    log_message(f"✅ read_document: {file_path.name} ({len(text)} chars)")
                    return f"# {file_path.name}\n\n{text}"
            except Exception as e:
                log_message(f"❌ read_document failed: {e}")
                return json.dumps({"error": f"Cannot read {path}: {e}"})

        tools.append(Tool(
            name="read_document",
            description=(
                "Read a document from the local file system (uploaded files, PDFs, text files). "
                "The path is relative to the data/ directory. "
                "Use this when the user has uploaded a file or references a local document."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path relative to data/ directory (e.g. 'uploads/document.pdf')",
                    },
                },
                "required": ["path"],
            },
            executor=_execute_read,
        ))

        return tools

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
        elif tool_name == "read_document":
            return f"📄 {tool_args.get('path', '')}"
        return ""


plugin = DocumentPlugin()
