"""Document tools for LLM function calling.

Provides search_documents, list_documents and delete_document tools
that operate on the ChromaDB document store.
"""

import json

from .function_calling import Tool
from .security import TIER_READONLY, TIER_WRITE_SYSTEM
from .prompt_loader import load_tool_description


def get_document_tools() -> list[Tool]:
    """Create document tools for LLM function calling."""

    async def _search_documents(query: str, n_results: int = 20) -> str:
        """Search uploaded documents semantically."""
        from .document_store import get_document_store
        store = get_document_store()
        if not store:
            return json.dumps({"error": "Document store not available (ChromaDB not running?)"})

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

    async def _list_documents() -> str:
        """List all uploaded documents."""
        from .document_store import get_document_store
        store = get_document_store()
        if not store:
            return json.dumps({"error": "Document store not available"})

        docs = store.list_documents()
        if not docs:
            return json.dumps({"documents": [], "message": "No documents uploaded yet."})

        return json.dumps({"total_count": len(docs), "documents": docs}, ensure_ascii=False)

    async def _delete_document(filename: str) -> str:
        """Delete a document and all its chunks."""
        from .document_store import get_document_store
        store = get_document_store()
        if not store:
            return json.dumps({"error": "Document store not available"})

        count = await store.delete_document(filename)
        if count == 0:
            return json.dumps({"error": f"Document not found: {filename}"})

        return json.dumps({"deleted": filename, "chunks_removed": count})

    description = load_tool_description("document_tools.txt")

    return [
        Tool(
            name="search_documents",
            tier=TIER_READONLY,
            description=f"{description} Search uploaded documents by semantic similarity.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query — what are you looking for in the documents?",
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Number of results to return (default: 20, max: 100)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
            executor=_search_documents,
        ),
        Tool(
            name="list_documents",
            tier=TIER_READONLY,
            description="List all uploaded documents with their metadata (filename, chunks, upload date).",
            parameters={
                "type": "object",
                "properties": {},
            },
            executor=_list_documents,
        ),
        Tool(
            name="delete_document",
            tier=TIER_WRITE_SYSTEM,
            description="Delete an uploaded document and all its indexed chunks from the store.",
            parameters={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Exact filename to delete (use list_documents to find it).",
                    },
                },
                "required": ["filename"],
            },
            executor=_delete_document,
        ),
    ]
