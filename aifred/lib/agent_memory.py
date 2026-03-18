"""Agent long-term memory using ChromaDB.

Each agent gets its own ChromaDB collection for persistent memory.
Agents can write to their own collection and read from all collections.
Memory is retrieved via semantic search and injected into the agent's context.

Uses the same ChromaDB server and embedding function as the research cache.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import chromadb
from chromadb.config import Settings

from .config import (
    AGENT_MEMORY_COLLECTION_MAX,
    AGENT_MEMORY_DISTANCE_THRESHOLD,
    AGENT_MEMORY_RESULTS,
    DEFAULT_OLLAMA_URL,
)
from .function_calling import Tool, ToolKit

logger = logging.getLogger(__name__)

# Reuse embedding config from vector_cache (same model, same Ollama instance)
OLLAMA_EMBEDDING_MODEL = "nomic-embed-text-v2-moe"


class AgentMemory:
    """Agent memory backed by ChromaDB collections.

    One collection per agent. Write-own, read-all.
    """

    def __init__(self, host: str = "localhost", port: int = 8000) -> None:
        from .vector_cache import OllamaCPUEmbeddingFunction

        self._client = chromadb.HttpClient(
            host=host, port=port,
            settings=Settings(anonymized_telemetry=False),
        )
        self._client.heartbeat()
        self._embed_fn = OllamaCPUEmbeddingFunction(
            model_name=OLLAMA_EMBEDDING_MODEL,
            host=DEFAULT_OLLAMA_URL,
        )
        self._collections: dict[str, Any] = {}
        logger.info("AgentMemory connected to ChromaDB")

    def _collection(self, agent_id: str) -> Any:
        """Get or create a collection for an agent (cached)."""
        if agent_id not in self._collections:
            self._collections[agent_id] = self._client.get_or_create_collection(
                name=f"agent_memory_{agent_id}",
                metadata={"agent": agent_id, "embedding_model": OLLAMA_EMBEDDING_MODEL},
                embedding_function=self._embed_fn,  # type: ignore[arg-type]
            )
        return self._collections[agent_id]

    async def store(
        self, agent_id: str, content: str, memory_type: str, summary: str,
    ) -> str:
        """Store a memory in the agent's collection.

        The summary is used as the document (embedded for search),
        the full content goes into metadata.
        """
        col = self._collection(agent_id)

        # Enforce size limit: remove oldest if at capacity
        count = col.count()
        if count >= AGENT_MEMORY_COLLECTION_MAX:
            all_data = col.get(include=["metadatas"])
            if all_data["ids"]:
                oldest_idx = min(
                    range(len(all_data["ids"])),
                    key=lambda i: all_data["metadatas"][i].get("date", ""),  # type: ignore[index]
                )
                col.delete(ids=[all_data["ids"][oldest_idx]])
                logger.info(f"AgentMemory({agent_id}): evicted oldest entry (limit {AGENT_MEMORY_COLLECTION_MAX})")

        doc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        col.add(
            ids=[doc_id],
            documents=[summary],
            metadatas=[{
                "agent_id": agent_id,
                "date": now,
                "type": memory_type,
                "summary": summary,
                "content": content,
            }],
        )
        logger.info(f"AgentMemory({agent_id}): stored [{memory_type}] {summary[:60]}")
        return f"Memory stored: [{memory_type}] {summary}"

    async def recall(
        self, agent_id: str, query: str, n_results: int = AGENT_MEMORY_RESULTS,
    ) -> list[dict[str, Any]]:
        """Query an agent's memory by semantic similarity."""
        col = self._collection(agent_id)
        if col.count() == 0:
            return []

        results = col.query(
            query_texts=[query],
            n_results=min(n_results, col.count()),
            include=["metadatas", "distances"],
        )

        memories = []
        for i, dist in enumerate(results["distances"][0]):  # type: ignore[index]
            if dist > AGENT_MEMORY_DISTANCE_THRESHOLD:
                continue
            meta = results["metadatas"][0][i]  # type: ignore[index]
            memories.append({
                "summary": meta.get("summary", ""),
                "content": meta.get("content", ""),
                "type": meta.get("type", ""),
                "date": meta.get("date", ""),
                "distance": dist,
            })
        return memories

    def make_toolkit(self, agent_id: str) -> ToolKit:
        """Create a ToolKit with memory tools bound to a specific agent."""

        async def store_memory(content: str, memory_type: str, summary: str) -> str:
            return await self.store(agent_id, content, memory_type, summary)

        return ToolKit(tools=[
            Tool(
                name="store_memory",
                description=(
                    "Store important content to your long-term memory. "
                    "Use this for noteworthy insights, analyses, sermons, prayers, "
                    "or anything you want to remember across conversations. "
                    "Use sparingly - only for truly memorable content."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "The full text to remember",
                        },
                        "memory_type": {
                            "type": "string",
                            "description": "Category (e.g. sermon, prayer, analysis, insight, code_review, counsel)",
                        },
                        "summary": {
                            "type": "string",
                            "description": "Short summary for later retrieval (1-2 sentences)",
                        },
                    },
                    "required": ["content", "memory_type", "summary"],
                },
                executor=store_memory,
            ),
        ])


def format_memory_context(memories: list[dict[str, Any]]) -> str:
    """Format retrieved memories for injection into the system prompt."""
    if not memories:
        return ""

    lines = [
        "Du erinnerst dich an eigene fruehere Texte, die zum aktuellen Gespraech passen:",
    ]
    for mem in memories:
        date_str = mem["date"][:10] if mem["date"] else "?"
        lines.append(f"- [{date_str}, {mem['type']}] {mem['summary']}")
        if mem["content"] and mem["content"] != mem["summary"]:
            # Truncate long content for context window
            content_preview = mem["content"][:500]
            if len(mem["content"]) > 500:
                content_preview += "..."
            lines.append(f"  {content_preview}")

    lines.append("")
    lines.append("Das sind deine eigenen Worte. Du kannst darauf aufbauen oder sie weiterentwickeln.")
    return "\n".join(lines)


# Singleton
_instance: Optional[AgentMemory] = None


def get_agent_memory() -> Optional[AgentMemory]:
    """Get the global AgentMemory instance. Returns None if ChromaDB unavailable."""
    global _instance
    if _instance is None:
        try:
            _instance = AgentMemory()
        except Exception as e:
            logger.warning(f"AgentMemory unavailable: {e}")
            return None
    return _instance
