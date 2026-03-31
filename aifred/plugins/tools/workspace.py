"""Workspace plugin — file access + ChromaDB document management.

Provides tools for:
- File system access: list, read, write files in data/documents/
- ChromaDB: index, search, list indexed, delete documents
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...lib.function_calling import Tool
from ...lib.security import TIER_READONLY, TIER_WRITE_DATA, TIER_WRITE_SYSTEM
from ...lib.plugin_base import PluginContext
from ...lib.i18n import t
from ...lib.logging_utils import log_message
from ...lib.prompt_loader import load_prompt

# Base directory for all file operations (path traversal protection)
_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
_DOCUMENTS_DIR = _DATA_DIR / "documents"


def _safe_resolve(relative_path: str) -> tuple[Path | None, str | None]:
    """Resolve a relative path safely within data/documents/. Returns (path, error)."""
    try:
        file_path = (_DOCUMENTS_DIR / relative_path).resolve()
        if not str(file_path).startswith(str(_DOCUMENTS_DIR.resolve())):
            return None, "Access denied: path outside documents directory"
        return file_path, None
    except Exception:
        return None, f"Invalid path: {relative_path}"


@dataclass
class WorkspacePlugin:
    name: str = "workspace"
    display_name: str = "Workspace"

    def is_available(self) -> bool:
        return True  # File access always available, ChromaDB optional

    def get_tools(self, ctx: PluginContext) -> list[Tool]:
        tools: list[Tool] = []

        # ============================================================
        # FILE SYSTEM TOOLS
        # ============================================================

        async def _list_files(subfolder: str = "") -> str:
            """List files in data/documents/ or a subfolder."""
            target = _DOCUMENTS_DIR / subfolder if subfolder else _DOCUMENTS_DIR
            target = target.resolve()
            if not str(target).startswith(str(_DOCUMENTS_DIR.resolve())):
                return json.dumps({"error": "Access denied: path outside documents directory"})
            if not target.exists():
                return json.dumps({"error": f"Directory not found: {subfolder}"})

            entries = []
            for item in sorted(target.iterdir()):
                entry: dict[str, Any] = {"name": item.name}
                if item.is_dir():
                    entry["type"] = "directory"
                    entry["items"] = len(list(item.iterdir()))
                else:
                    entry["type"] = "file"
                    entry["size_kb"] = round(item.stat().st_size / 1024, 1)
                    entry["extension"] = item.suffix.lower()
                entries.append(entry)

            log_message(f"📂 list_files: {target.relative_to(_DATA_DIR)} ({len(entries)} entries)")
            return json.dumps({"directory": str(target.relative_to(_DATA_DIR)), "entries": entries}, ensure_ascii=False)

        tools.append(Tool(
            name="list_files",
            tier=TIER_READONLY,
            description=(
                "List files and folders in the user's documents directory. "
                "Shows filename, type, size, and extension for each entry."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "subfolder": {
                        "type": "string",
                        "description": "Subfolder to list (empty = root of documents/)",
                        "default": "",
                    },
                },
            },
            executor=_list_files,
        ))

        async def _read_file(filename: str, pages: str = "") -> str:
            """Read a file from data/documents/. PDFs support page selection."""
            file_path, error = _safe_resolve(filename)
            if error:
                return json.dumps({"error": error})
            if not file_path or not file_path.exists():
                return json.dumps({"error": f"File not found: {filename}"})

            log_message(f"📄 read_file: {file_path.name}")

            try:
                if file_path.suffix.lower() == ".pdf":
                    import fitz  # PyMuPDF
                    doc = fitz.open(str(file_path))
                    total_pages = len(doc)

                    if pages:
                        # Parse page range: "3", "1-5", "3,7,10-12"
                        selected: list[int] = []
                        for part in pages.split(","):
                            part = part.strip()
                            if "-" in part:
                                start, end = part.split("-", 1)
                                selected.extend(range(int(start) - 1, int(end)))
                            else:
                                selected.append(int(part) - 1)
                        selected = [p for p in selected if 0 <= p < total_pages]
                        text = "\n\n".join(
                            f"--- Page {p + 1} ---\n{doc[p].get_text()}" for p in selected
                        )
                    else:
                        text = "\n\n".join(
                            f"--- Page {i + 1} ---\n{page.get_text()}" for i, page in enumerate(doc)
                        )
                    doc.close()

                    log_message(f"  read_file: PDF {file_path.name} ({total_pages} pages, {len(text)} chars)")
                    return json.dumps({
                        "filename": file_path.name,
                        "type": "pdf",
                        "total_pages": total_pages,
                        "content": text,
                    }, ensure_ascii=False)
                else:
                    # Text-based files
                    try:
                        text = file_path.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        import chardet
                        raw = file_path.read_bytes()
                        detected = chardet.detect(raw)
                        text = raw.decode(detected.get("encoding", "utf-8"), errors="replace")

                    log_message(f"  read_file: {file_path.name} ({len(text)} chars)")
                    return json.dumps({
                        "filename": file_path.name,
                        "type": file_path.suffix.lower().lstrip("."),
                        "size_kb": round(file_path.stat().st_size / 1024, 1),
                        "content": text,
                    }, ensure_ascii=False)
            except Exception as e:
                log_message(f"  read_file failed: {e}")
                return json.dumps({"error": f"Cannot read {filename}: {e}"})

        tools.append(Tool(
            name="read_file",
            tier=TIER_READONLY,
            description=(
                "Read a file from the documents directory. "
                "For PDFs, you can specify pages (e.g. '1-5' or '3,7'). "
                "Returns the full text content."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Filename relative to documents/ (e.g. 'report.pdf')",
                    },
                    "pages": {
                        "type": "string",
                        "description": "Page range for PDFs: '3', '1-5', '3,7,10-12' (empty = all pages)",
                        "default": "",
                    },
                },
                "required": ["filename"],
            },
            executor=_read_file,
        ))

        async def _write_file(filename: str, content: str) -> str:
            """Write or overwrite a text file in data/documents/."""
            file_path, error = _safe_resolve(filename)
            if error:
                return json.dumps({"error": error})
            if not file_path:
                return json.dumps({"error": f"Invalid path: {filename}"})

            # Only allow text-based writes
            allowed_extensions = {".txt", ".md", ".csv", ".json", ".xml", ".html"}
            if file_path.suffix.lower() not in allowed_extensions:
                return json.dumps({
                    "error": f"Cannot write {file_path.suffix} files. Allowed: {', '.join(sorted(allowed_extensions))}"
                })

            # Create parent dirs if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            file_path.write_text(content, encoding="utf-8")

            # Verify: read back and compare length
            written_text = file_path.read_text(encoding="utf-8")
            if len(written_text) != len(content):
                return json.dumps({
                    "error": f"Verify failed: wrote {len(content)} chars but read back {len(written_text)}"
                })

            size_kb = round(file_path.stat().st_size / 1024, 1)
            log_message(f"  write_file: {file_path.name} ({size_kb} KB, verified)")
            return json.dumps({
                "written": filename,
                "size_kb": size_kb,
                "chars": len(content),
                "verified": True,
            })

        tools.append(Tool(
            name="write_file",
            tier=TIER_WRITE_DATA,
            description=(
                "Write or overwrite a text file in the documents directory. "
                "Only text formats allowed: .txt, .md, .csv, .json, .xml, .html. "
                "Use this to create new documents or edit existing ones."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Filename relative to documents/ (e.g. 'notes/summary.md')",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full text content to write",
                    },
                },
                "required": ["filename", "content"],
            },
            executor=_write_file,
        ))

        # ============================================================
        # CHROMA DB TOOLS
        # ============================================================

        async def _index_document(filename: str) -> str:
            """Index a file from data/documents/ into ChromaDB."""
            from ...lib.document_store import get_document_store
            store = get_document_store()
            if not store:
                return json.dumps({"error": "ChromaDB not available"})

            file_path, error = _safe_resolve(filename)
            if error:
                return json.dumps({"error": error})
            if not file_path or not file_path.exists():
                return json.dumps({"error": f"File not found: {filename}"})

            from ...lib.config import DOCUMENT_ALLOWED_EXTENSIONS
            if file_path.suffix.lower() not in DOCUMENT_ALLOWED_EXTENSIONS:
                return json.dumps({
                    "error": f"Unsupported file type: {file_path.suffix}. "
                    f"Allowed: {', '.join(sorted(DOCUMENT_ALLOWED_EXTENSIONS))}"
                })

            log_message(f"📄 index_document: {file_path.name}")
            try:
                chunks = await store.index_document(file_path, file_path.name)
                log_message(f"  index_document: {file_path.name} -> {chunks} chunks")
                return json.dumps({
                    "indexed": file_path.name,
                    "chunks": chunks,
                })
            except Exception as e:
                log_message(f"  index_document failed: {e}")
                return json.dumps({"error": f"Indexing failed: {e}"})

        tools.append(Tool(
            name="index_document",
            tier=TIER_WRITE_DATA,
            description=(
                "Index a document from the documents directory into the vector database (ChromaDB). "
                "After indexing, the document can be searched semantically with search_documents. "
                "Supported formats: PDF, TXT, MD, CSV, DOCX, XLSX, PPTX, ODT, ODS, ODP."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Filename in documents/ to index (e.g. 'report.pdf')",
                    },
                },
                "required": ["filename"],
            },
            executor=_index_document,
        ))

        async def _search_documents(query: str, n_results: int = 5) -> str:
            """Semantic search in ChromaDB."""
            from ...lib.document_store import get_document_store
            store = get_document_store()
            if not store:
                return json.dumps({"error": "ChromaDB not available"})

            hits = await store.search(query, n_results=min(n_results, 100))
            if not hits:
                return json.dumps({"results": [], "message": "No matching documents found."})

            results = []
            for hit in hits:
                results.append({
                    "filename": hit["filename"],
                    "chunk": f"{hit['chunk_index'] + 1}/{hit['total_chunks']}",
                    "content": hit["content"],
                })
            return json.dumps({"total_results": len(results), "results": results}, ensure_ascii=False)

        tools.append(Tool(
            name="search_documents",
            tier=TIER_READONLY,
            description=(
                "Search indexed documents semantically in the vector database. "
                "Only finds documents that have been indexed (uploaded via UI or via index_document). "
                "Use list_files to see all files on disk, search_documents to search indexed content."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query — what are you looking for?",
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Number of results (default: 5, max: 100)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
            executor=_search_documents,
        ))

        async def _list_indexed() -> str:
            """List all documents indexed in ChromaDB."""
            from ...lib.document_store import get_document_store
            store = get_document_store()
            if not store:
                return json.dumps({"error": "ChromaDB not available"})

            docs = store.list_documents()
            if not docs:
                return json.dumps({"documents": [], "message": "No documents indexed yet."})
            return json.dumps({"total_count": len(docs), "documents": docs}, ensure_ascii=False)

        tools.append(Tool(
            name="list_indexed",
            tier=TIER_READONLY,
            description=(
                "List all documents that have been indexed in the vector database. "
                "Shows filename, chunk count, and upload date."
            ),
            parameters={"type": "object", "properties": {}},
            executor=_list_indexed,
        ))

        async def _delete_document(filename: str) -> str:
            """Delete a document from ChromaDB (and optionally from disk)."""
            from ...lib.document_store import get_document_store
            store = get_document_store()
            if not store:
                return json.dumps({"error": "ChromaDB not available"})

            count = await store.delete_document(filename)
            if count == 0:
                return json.dumps({"error": f"Document not found in index: {filename}"})

            return json.dumps({"deleted": filename, "chunks_removed": count})

        tools.append(Tool(
            name="delete_document",
            tier=TIER_WRITE_SYSTEM,
            description=(
                "Delete a document from the vector database index. "
                "This removes all indexed chunks. The file on disk is also removed."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Exact filename to delete (use list_indexed to find it)",
                    },
                },
                "required": ["filename"],
            },
            executor=_delete_document,
        ))

        return tools

    def get_prompt_instructions(self, lang: str) -> str:
        try:
            return load_prompt("shared/workspace_instructions", lang=lang)
        except FileNotFoundError:
            return ""

    def get_ui_status(self, tool_name: str, tool_args: dict[str, Any], lang: str) -> str:
        if tool_name == "list_files":
            sub = tool_args.get("subfolder", "")
            return f"📂 {sub or 'documents/'}"
        elif tool_name == "read_file":
            return f"📄 {tool_args.get('filename', '')}"
        elif tool_name == "write_file":
            return f"📝 {tool_args.get('filename', '')}"
        elif tool_name == "index_document":
            return f"📥 {tool_args.get('filename', '')}"
        elif tool_name == "search_documents":
            query = tool_args.get("query", "")
            return f"🔍 {query[:50]}" if query else t("tool_doc_search", lang=lang)
        elif tool_name == "list_indexed":
            return t("tool_doc_list", lang=lang)
        elif tool_name == "delete_document":
            return t("tool_doc_delete", lang=lang, filename=tool_args.get("filename", ""))
        return ""


plugin = WorkspacePlugin()
