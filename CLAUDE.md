# Projekt-spezifische Regeln für AIfred-Intelligence

(Allgemeine Regeln siehe ~/.claude/CLAUDE.md)

---

## ⚠️ KRITISCH: Git-Workflow

- **NIEMALS** automatisch commit oder push ausführen
- Nur auf explizite Ansage des Users ("commit", "push")
- Bei Änderungen: Zeigen, erklären, warten auf Freigabe

---

## ⚠️ KRITISCH: Keine Fallbacks ohne Absprache

- **NIEMALS** automatisch Fallback-Logik einbauen
- Fallbacks (für alte Datenformate, fehlende Felder, Migration etc.) nur nach Absprache mit User
- Im Zweifel: Alte Daten löschen und sauber neu starten
- GRUND: Fallbacks verkomplizieren den Code und verstecken Probleme

---

## Bereits integrierte Features (NICHT vergessen!)

- **ChromaDB Vector Cache** - Semantischer Cache für Web-Research (Docker)
- **RAG-System** - Retrieval-Augmented Generation mit Relevanz-Check
- **History Compression** - Automatische Kompression (siehe unten)
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
  - Salomo (Richter im Tribunal-Mode)

---

## Code-Konventionen

### History Compression Algorithmus

Die History-Kompression verwendet folgende Schwellenwerte (konfigurierbar in `config.py`):

| Parameter | Wert | Beschreibung |
|-----------|------|--------------|
| `HISTORY_COMPRESSION_TRIGGER` | 0.7 (70%) | Bei dieser Context-Auslastung wird komprimiert |
| `HISTORY_COMPRESSION_TARGET` | 0.3 (30%) | Ziel nach Kompression (Platz für ~2 Roundtrips) |
| `HISTORY_SUMMARY_RATIO` | 0.25 (4:1) | Summary = 25% des zu komprimierenden Inhalts |
| `HISTORY_SUMMARY_MIN_TOKENS` | 500 | Minimum für sinnvolle Zusammenfassungen |
| `HISTORY_SUMMARY_TOLERANCE` | 0.5 (50%) | Erlaubte Überschreitung, darüber wird gekürzt |

**Ablauf:**
1. Trigger bei 70% Context-Auslastung
2. Sammle älteste Messages (FIFO) bis remaining < 30%
3. Komprimiere gesammelte Messages zu Summary (4:1 Ratio)
4. Neue History = [Summary] + [verbleibende Messages]

**Token-Estimation:** Ignoriert `<details>`, `<span>`, `<think>` Tags (gehen nicht ans LLM)

**Beispiele:**
- 7K Context: Trigger bei 4.900, Ziel 2.100, Summary ~700 tok
- 40K Context: Trigger bei 28.000, Ziel 12.000, Summary ~4.000 tok
- 200K Context: Trigger bei 140.000, Ziel 60.000, Summary ~20.000 tok

---

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

---

## ⚠️ Code-Qualitätsprüfungen (PFLICHT!)

**IMMER nach Code-Änderungen ausführen - KEINE Ausnahmen!**

```bash
# 1. Syntax-Check (schnell, immer zuerst)
python3 -m py_compile aifred/DATEI.py

# 2. Linting mit Ruff
source venv/bin/activate && ruff check aifred/DATEI.py

# 3. Type-Checking mit mypy
source venv/bin/activate && mypy aifred/DATEI.py --ignore-missing-imports
```

**Mehrere Dateien auf einmal:**
```bash
source venv/bin/activate && ruff check aifred/state.py aifred/aifred.py aifred/lib/context_manager.py
source venv/bin/activate && mypy aifred/state.py aifred/aifred.py --ignore-missing-imports
```

**Bekannte Ignores (NICHT beheben):**
- `E402` in config.py/state.py: Import-Position (notwendig wegen zirkulärer Imports)
- `F541` unnötige f-strings: Können mit `--fix` automatisch behoben werden
- mypy-Warnungen in Backends: OpenAI SDK Type-Mismatches (OpenAI-Library Issue)
- mypy `no_implicit_optional`: Bestehender Code, wird nicht refactored
