"""
Document Mixin – handles document upload, indexing and management.

Part of the AIfred State refactoring (aifred/state/ package).
"""

import reflex as rx
from typing import Any, Dict, List


class DocumentMixin(rx.State, mixin=True):
    """Mixin for document upload and management."""

    # State variables
    is_uploading_document: bool = False
    document_upload_status: str = ""
    uploaded_documents: List[Dict[str, Any]] = []
    document_manager_open: bool = False
    document_preview_filename: str = ""
    document_preview_content: str = ""

    def open_document_manager(self) -> None:
        """Open the document manager modal and refresh list."""
        self._refresh_document_list()
        self.document_manager_open = True

    def close_document_manager(self) -> None:
        """Close the document manager modal."""
        self.document_manager_open = False

    async def handle_document_upload(self, files: List[rx.UploadFile]) -> None:  # type: ignore[override]
        """Handle document file upload — parse, chunk, embed into ChromaDB."""
        from ..lib.config import DOCUMENT_ALLOWED_EXTENSIONS, DOCUMENT_MAX_FILE_SIZE_MB, DOCUMENTS_DIR
        from ..lib.document_store import get_document_store
        from ..lib.i18n import t
        from pathlib import Path

        self.is_uploading_document = True
        self.document_upload_status = ""
        yield  # type: ignore[misc]

        try:
            store = get_document_store()
            if not store:
                self.document_upload_status = t("doc_upload_no_store", lang=self.ui_language)  # type: ignore[attr-defined]
                return

            for file in files:
                filename = file.filename or "unknown.txt"
                suffix = Path(filename).suffix.lower()

                # Validate extension
                if suffix not in DOCUMENT_ALLOWED_EXTENSIONS:
                    self.document_upload_status = t(
                        "doc_upload_invalid_type", lang=self.ui_language,  # type: ignore[attr-defined]
                        filename=filename, allowed=", ".join(DOCUMENT_ALLOWED_EXTENSIONS),
                    )
                    self.add_debug(f"⚠️ Document rejected: {filename} (type {suffix})")  # type: ignore[attr-defined]
                    yield  # type: ignore[misc]
                    continue

                # Read content
                content = await file.read()

                # Validate size
                size_mb = len(content) / (1024 * 1024)
                if size_mb > DOCUMENT_MAX_FILE_SIZE_MB:
                    self.document_upload_status = t(
                        "doc_upload_too_large", lang=self.ui_language,  # type: ignore[attr-defined]
                        filename=filename, max_mb=DOCUMENT_MAX_FILE_SIZE_MB,
                    )
                    self.add_debug(f"⚠️ Document too large: {filename} ({size_mb:.1f} MB)")  # type: ignore[attr-defined]
                    yield  # type: ignore[misc]
                    continue

                # Save to disk
                DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
                file_path = DOCUMENTS_DIR / filename
                file_path.write_bytes(content)

                # Index in ChromaDB
                self.document_upload_status = t(
                    "doc_upload_indexing", lang=self.ui_language,  # type: ignore[attr-defined]
                    filename=filename,
                )
                self.add_debug(f"📄 Indexing document: {filename}")  # type: ignore[attr-defined]
                yield  # type: ignore[misc]

                chunks = await store.index_document(file_path, filename)

                self.document_upload_status = t(
                    "doc_upload_success", lang=self.ui_language,  # type: ignore[attr-defined]
                    filename=filename, chunks=chunks,
                )
                self.add_debug(f"✅ Document indexed: {filename} ({chunks} chunks)")  # type: ignore[attr-defined]
                yield  # type: ignore[misc]

            # Refresh document list
            self._refresh_document_list()

        except Exception as e:
            self.document_upload_status = f"❌ {e}"
            self.add_debug(f"❌ Document upload failed: {e}")  # type: ignore[attr-defined]

        finally:
            self.is_uploading_document = False
            # Auto-clear status after 4 seconds
            import asyncio
            await asyncio.sleep(4)
            self.document_upload_status = ""
            yield  # type: ignore[misc]

    def _refresh_document_list(self) -> None:
        """Refresh the list of uploaded documents from ChromaDB."""
        from ..lib.document_store import get_document_store
        store = get_document_store()
        if store:
            self.uploaded_documents = store.list_documents()
        else:
            self.uploaded_documents = []

    def preview_document(self, filename: str) -> None:
        """Load document content for preview in the modal."""
        from ..lib.config import DOCUMENTS_DIR
        from ..lib.document_store import PARSERS

        file_path = DOCUMENTS_DIR / filename
        if not file_path.exists():
            self.document_preview_filename = filename
            self.document_preview_content = "❌ File not found"
            return

        suffix = file_path.suffix.lower()
        parser = PARSERS.get(suffix)
        if not parser:
            self.document_preview_filename = filename
            self.document_preview_content = f"❌ No parser for {suffix}"
            return

        try:
            text = parser(file_path)
            # Truncate for UI display (full text could be huge)
            if len(text) > 10_000:
                text = text[:10_000] + f"\n\n... ({len(text) - 10_000} chars truncated)"
            self.document_preview_filename = filename
            self.document_preview_content = text
        except Exception as e:
            self.document_preview_filename = filename
            self.document_preview_content = f"❌ {e}"

    def close_document_preview(self) -> None:
        """Close the document preview."""
        self.document_preview_filename = ""
        self.document_preview_content = ""

    async def delete_uploaded_document(self, filename: str) -> None:
        """Delete a document from store and disk."""
        from ..lib.document_store import get_document_store
        from ..lib.i18n import t

        store = get_document_store()
        if store:
            count = await store.delete_document(filename)
            self.document_upload_status = t(
                "doc_delete_success", lang=self.ui_language,  # type: ignore[attr-defined]
                filename=filename, chunks=count,
            )
            self.add_debug(f"🗑️ Document deleted: {filename} ({count} chunks)")  # type: ignore[attr-defined]
            self._refresh_document_list()
            yield  # type: ignore[misc]
            import asyncio
            await asyncio.sleep(4)
            self.document_upload_status = ""
            yield  # type: ignore[misc]
