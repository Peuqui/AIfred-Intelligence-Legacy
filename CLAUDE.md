# Projekt-spezifische Regeln für AIfred-Intelligence

(Allgemeine Regeln siehe ~/.claude/CLAUDE.md)

---

## Bereits integrierte Features (NICHT vergessen!)

- **ChromaDB Vector Cache** - Semantischer Cache für Web-Research (Docker)
- **RAG-System** - Retrieval-Augmented Generation mit Relevanz-Check
- **History Compression** - Automatische Kompression bei 70% Context-Auslastung
- **Multi-Backend Support** - Ollama, vLLM, TabbyAPI, KoboldCPP
- **Thinking Mode** - Chain-of-Thought für Qwen3 Modelle

---

## Projekt-Struktur

### Wichtige Verzeichnisse
- `aifred/lib/` - Kern-Bibliotheken (IMMER hier zuerst suchen!)
  - `prompt_loader.py` - Prompt-Handling
  - `message_builder.py` - Message-Formatting
  - `multi_agent.py` - Multi-Agent Logik
  - `vector_cache.py` - ChromaDB Integration
  - `conversation_handler.py` - Automatik-Modus, RAG-Kontext
- `prompts/de/` und `prompts/en/` - Alle Prompts (NICHT hardcodiert im Code!)
- `aifred/backends/` - LLM-Backend Adapter

### Architektur
- Python/Reflex Anwendung (nicht Gradio!)
- Backends: Ollama, vLLM, TabbyAPI, KoboldCPP
- Multi-Agent System:
  - AIfred (Hauptagent)
  - Sokrates (Kritiker)
