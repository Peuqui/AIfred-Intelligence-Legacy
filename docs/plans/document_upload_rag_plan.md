# Implementierungsplan: Dokument-Upload & RAG

## Status

### ✅ Paket 1: Config + Document Store (Backend)
- `config.py` — Config-Werte (DOCUMENTS_DIR, CHUNK_SIZE, etc.)
- `aifred/lib/document_store.py` — DocumentStore Klasse:
  - `index_document()` → Parse → Chunk → Embed → ChromaDB
  - `search()` → Semantische Suche über alle Dokumente
  - `list_documents()` → Alle Dokumente auflisten
  - `delete_document()` → Chunks + Datei löschen
- Parser: PDF (fitz), TXT/MD (chardet), CSV (markdown table)
- Chunking: 500 Tokens, 50 Overlap, char-basiert (1 Token ≈ 4 chars)
- ChromaDB Collection: `aifred_documents` (eigene, getrennt von research_cache)
- `requirements.txt` — chardet hinzugefügt

---

### 🔲 Paket 2: Tool-Definitionen
**Dateien:** `aifred/lib/document_tools.py`, `agent_memory.py`

- `get_document_tools()` → Liste von Tools:
  - `search_documents(query, n_results=5)` — Semantische Suche in Dokumenten
  - `list_documents()` — Alle hochgeladenen Dokumente auflisten
  - `delete_document(filename)` — Dokument entfernen
- Registration in `prepare_agent_toolkit()` (immer verfügbar wenn ChromaDB läuft)
- Tool-Beschreibungen: Prompt-Dateien in `prompts/shared/`
- i18n: Tool-Status-Messages in `i18n.py`
- `multi_agent.py`: Status-Messages für document tools

**DoD:** Tools registriert, LLM kann `search_documents` aufrufen

---

### 🔲 Paket 3: Upload UI + State Mixin
**Dateien:** `aifred/state/_document_mixin.py`, `aifred/ui/input_sections.py`, `_base.py`

- Upload-Handler nach Pattern von `_image_mixin.py`
- Upload-Widget in der UI (neben Image-Upload)
- Erlaubte Extensions: .pdf, .txt, .md, .csv
- Max Dateigröße: 50 MB (konfigurierbar)
- Fortschritts-Feedback an User
- Dokument-Liste anzeigen (welche Docs sind hochgeladen)
- Löschen-Button pro Dokument
- i18n für alle UI-Texte

**DoD:** Upload über Browser → Dokument wird indexiert → LLM kann darin suchen

---

### 🔲 Paket 4: RAG-Integration (Should-Have)
**Dateien:** `rag_context_builder.py`

- `build_rag_context()` erweitern: Neben Research-Cache auch Document-Collection abfragen
- Dokument-Chunks als automatischen Kontext einbauen wenn relevant
- Distance-Threshold für Document-Chunks (ähnlich wie Research-Cache)

**DoD:** Relevante Dokument-Chunks werden automatisch als RAG-Kontext mitgegeben

---

## Abhängigkeiten
```
Paket 1 (Store) ✅ → Paket 2 (Tools) → Paket 3 (UI)
                                      ↘ Paket 4 (RAG)
```

## Technische Details

### Bestehende Infra (wiederverwendet)
- ChromaDB: `chromadb.HttpClient(localhost:8000)` — Docker Container
- Embedding: `nomic-embed-text-v2-moe` via `OllamaCPUEmbeddingFunction`
- PDF: `fitz` (PyMuPDF)
- Tool-Infra: `prepare_agent_toolkit()` in `agent_memory.py`
- Upload-Pattern: `_image_mixin.py`

### Neue Dependency
- `chardet>=5.0.0` — Automatische Encoding-Erkennung (640 KB, zero deps)
