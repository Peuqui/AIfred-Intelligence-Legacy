# Projekt-spezifische Regeln für AIfred-Intelligence

(Allgemeine Regeln siehe ~/.claude/CLAUDE.md)

---

## ⚠️ KRITISCH: Git-Workflow

- **NIEMALS** automatisch commit oder push ausführen
- Nur auf explizite Ansage des Users ("commit", "push")
- Bei Änderungen: Zeigen, erklären, warten auf Freigabe

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

---

## Code-Konventionen

### Zahlenformatierung (WICHTIG!)
- **IMMER** `format_number()` aus `aifred/lib/formatting.py` verwenden
- Diese Funktion formatiert Zahlen locale-aware (DE: 1.000,5 vs EN: 1,000.5)
- **NIEMALS** f-Strings mit direkten Zahlen wie `f"{value:.1f}"` in User-facing Output
- Beispiel:
  ```python
  from .lib.formatting import format_number
  # RICHTIG:
  yield f"Model: {format_number(size_mb / 1024, 1)} GB"
  # FALSCH:
  yield f"Model: {size_mb / 1024:.1f} GB"
  ```
