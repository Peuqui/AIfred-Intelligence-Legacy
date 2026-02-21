# AIfred Intelligence - QWEN.md

## 📋 Projektübersicht

**AIfred Intelligence** ist ein fortschrittlicher KI-Assistent mit Multi-LLM-Unterstützung, automatischer Web-Recherche und Sprachinterface.

- **Framework:** Reflex (Python Full-Stack, React-basiert)
- **Backends:** llama.cpp (via llama-swap), Ollama, vLLM, TabbyAPI, Cloud APIs (Qwen, DeepSeek, Claude)
- **Sprachen:** Deutsch & Englisch (mehrsprachige Prompts)
- **Architektur:** Python/Reflex-App mit Multi-Agent-System

### Kern-Features
- **Multi-Agent-System:** AIfred (Hauptagent), Sokrates (Kritiker), Salomo (Richter)
- **History Compression:** Automatische Kompression bei 70% Context-Auslastung
- **Vector Cache:** ChromaDB mit multilingualen Embeddings
- **Voice Interface:** STT (Whisper) + TTS (Edge TTS, XTTS v2, MOSS-TTS, DashScope)
- **Vision/OCR:** Bildanalyse mit multimodalen LLMs
- **Thinking Mode:** Chain-of-Thought für Qwen3-Modelle
- **Web Research:** Automatische Recherche bei aktuellen Themen

---

## 🏗️ Projektstruktur

```
/home/mp/Projekte/AIfred-Intelligence/
├── aifred/                      # Hauptanwendung
│   ├── aifred.py               # Reflex App & UI-Komponenten
│   ├── state.py                # State Management (Chat, Settings)
│   ├── theme.py                # UI-Styling
│   ├── backends/               # LLM-Backend-Adapter
│   │   ├── base.py             # Abstrakte Basisklasse
│   │   ├── llamacpp.py         # llama.cpp via llama-swap
│   │   ├── ollama.py           # Ollama API
│   │   ├── vllm.py             # vLLM Server
│   │   ├── tabbyapi.py         # TabbyAPI (EXL2)
│   │   └── cloud_api.py        # Cloud-APIs (Qwen, DeepSeek, Claude)
│   └── lib/                    # Kern-Bibliotheken (IMMER hier zuerst suchen!)
│       ├── prompt_loader.py    # Prompt-Handling
│       ├── message_builder.py  # Message-Formatting
│       ├── multi_agent.py      # Multi-Agent-Logik
│       ├── vector_cache.py     # ChromaDB-Integration
│       ├── conversation_handler.py  # Automatik-Modus, RAG
│       ├── llamacpp_calibration.py  # VRAM-Kalibrierung
│       ├── config.py           # Konfiguration
│       └── formatting.py       # Zahlenformatierung (locale-aware)
├── prompts/de/ & prompts/en/   # Alle Prompts (NICHT hardcodiert!)
├── config/                     # Konfigurationsdateien
│   └── llama-swap-config.yaml  # llama-swap Modell-Konfiguration
├── scripts/                    # Utility-Skripte
│   ├── llama-swap-autoscan.py  # Auto-Modell-Erkennung
│   └── ...
├── systemd/                    # Systemd-Service-Konfiguration
├── docker/                     # Docker-Konfigurationen
├── docs/                       # Dokumentation
├── data/                       # Laufzeitdaten (Sessions, Logs, Cache)
├── venv/                       # Python Virtual Environment
└── .qwen/                      # QWEN-spezifische Konfiguration
    └── qwen.md                 # Projekt-spezifische QWEN-Regeln
```

---

## 🛠️ Build & Run Commands

### Entwicklungsumgebung starten

```bash
# In virtuelles Environment aktivieren
source venv/bin/activate

# Reflex Development Server (Frontend + Backend)
reflex run

# ODER: Production Build
reflex build
reflex export
```

### Systemdienst (Produktion)

```bash
# Status prüfen
systemctl --user status aifred-intelligence.service

# Neustart
systemctl --user restart aifred-intelligence.service

# Logs ansehen
journalctl --user -u aifred-intelligence -f
```

### llama-swap Management

```bash
# llama-swap neu starten (nach Modell-Änderungen)
systemctl --user restart llama-swap.service

# Autoscan manuell ausführen
source venv/bin/activate
python scripts/llama-swap-autoscan.py
```

### Code-Qualitätsprüfungen (PFLICHT nach Änderungen!)

```bash
# Syntax-Check
python3 -m py_compile aifred/DATEI.py

# Linting mit Ruff
source venv/bin/activate && ruff check aifred/DATEI.py

# Type-Checking mit mypy
source venv/bin/activate && mypy aifred/DATEI.py --ignore-missing-imports
```

**Bekannte Ignores (NICHT beheben):**
- `E402` in config.py/state.py: Import-Position (zirkuläre Imports)
- `F541` unnötige f-strings: Können mit `--fix` behoben werden
- mypy-Warnungen in Backends: OpenAI SDK Type-Mismatches
- mypy `no_implicit_optional`: Bestehender Code

---

## 📝 Entwicklungs-Konventionen

### ⚠️ KRITISCH: Git-Workflow
- **NIEMALS** automatisch commit oder push ausführen
- Nur auf explizite Ansage des Users ("commit", "push")
- Bei Änderungen: Zeigen, erklären, warten auf Freigabe

### ⚠️ Keine Fallbacks oder Backward-Compatibility
- **NIEMALS** automatisch Fallback-Logik einbauen
- **NIEMALS** Backward-Compatibility-Aliase erstellen
- Fallbacks nur nach **expliziter** Absprache mit User
- Im Zweifel: Alten Code löschen und sauber neu starten

### ⚠️ Keep It Simple
- Race Conditions strukturell vermeiden, dann Locks wenn nötig
- Edge Cases prüfen ob sie überhaupt eintreten können
- Vor jedem Fallback fragen: "Ist das wirklich nötig?"

### Zahlenformatierung (WICHTIG!)
- **IMMER** `format_number()` aus `aifred/lib/formatting.py` verwenden
- **NIEMALS** f-Strings mit direkten Zahlen in User-facing Output
```python
from .lib.formatting import format_number
# RICHTIG:
yield f"Model: {format_number(size_mb / 1024, 1)} GB"
# FALSCH:
yield f"Model: {size_mb / 1024:.1f} GB"
```

### History Compression Algorithmus

| Parameter | Wert | Beschreibung |
|-----------|------|--------------|
| `HISTORY_COMPRESSION_TRIGGER` | 0.7 (70%) | Trigger bei Context-Auslastung |
| `HISTORY_COMPRESSION_TARGET` | 0.3 (30%) | Ziel nach Kompression |
| `HISTORY_SUMMARY_RATIO` | 0.25 (4:1) | Summary = 25% des Inhalts |
| `HISTORY_SUMMARY_MIN_TOKENS` | 500 | Minimum für Zusammenfassungen |

**Ablauf:**
1. Trigger bei 70% Context-Auslastung
2. Sammle älteste Messages (FIFO) bis remaining < 30%
3. Komprimiere zu Summary (4:1 Ratio)
4. Neue History = [Summary] + [verbleibende Messages]

---

## 🔧 Konfiguration

### Wichtige Konfigurationsdateien

| Datei | Zweck |
|-------|-------|
| `.env` | Umgebungsvariablen (API-URLs, Ports) |
| `rxconfig.py` | Reflex-Konfiguration (Ports, Pfade) |
| `config/llama-swap-config.yaml` | llama-swap Modell-Konfiguration |
| `~/.config/llama-swap/config.yaml` | Aktive llama-swap Config |
| `aifred/lib/config.py` | Interne Konstanten & Defaults |

### Umgebungsvariablen (.env)

```bash
AIFRED_API_URL=http://localhost:8002    # Backend-API für Browser
AIFRED_ENV=dev                          # dev oder prod
AIFRED_FRONTEND_PATH=                   # Sub-Pfad für Nginx (z.B. "aifred")
```

### Ports

| Service | Port | Zweck |
|---------|------|-------|
| Reflex Frontend | 3002 | Web-UI |
| Reflex Backend | 8002 | API für Browser |
| llama-swap | 8080 | llama.cpp Proxy |
| Ollama | 11434 | Ollama API |

---

## 🤖 Multi-Agent System

### Agenten & Rollen

| Agent | Rolle | Temperatur |
|-------|-------|------------|
| 🎩 AIfred | Butler & Scholar - beantwortet Fragen | 0.2-1.1 (Auto) |
| 🏛️ Sokrates | Kritiker - hinterfragt mit sokratischer Methode | +0.2 Offset |
| 👑 Salomo | Weiser Richter - synthesiert Argumente | 0.3 |

### Diskussions-Modi

| Modus | Ablauf | Entscheidung |
|-------|--------|--------------|
| **Standard** | AIfred antwortet | — |
| **Critical Review** | AIfred → Sokrates (+ Pro/Contra) → STOP | User |
| **Auto-Consensus** | AIfred → Sokrates → Salomo (X Runden) | Salomo |
| **Tribunal** | AIfred ↔ Sokrates (X Runden) → Salomo | Salomo (Urteil) |

### Direkte Agenten-Ansprache
- "Sokrates, was denkst du über...?" → Sokrates antwortet
- "AIfred, erkläre..." → AIfred antwortet ohne Sokrates-Analyse
- Unterstützt STT-Varianten: "Alfred", "Eifred", "AI Fred"

---

## 📦 Abhängigkeiten

### Kern-Bibliotheken
- `reflex>=0.8.17` - Full-Stack Framework
- `pydantic>=2.0.0` - Datenmodelle
- `openai>=1.0.0` - vLLM & Cloud-APIs
- `httpx>=0.28.0` - Ollama HTTP API
- `pynvml>=11.0.0` - GPU-Monitoring
- `chromadb>=0.4.24` - Vector Cache
- `edge-tts==7.2.1` - Text-to-Speech
- `openai-whisper` - Speech-to-Text

### Entwicklung
- `pytest>=8.0.0` - Tests
- `black>=24.0.0` - Formatting
- `ruff` - Linting
- `mypy` - Type-Checking

---

## 🧪 Testing

```bash
# Alle Tests ausführen
source venv/bin/activate && pytest tests/

# Spezifischen Test ausführen
pytest tests/test_llamacpp_calibration.py -v

# Coverage
pytest --cov=aifred tests/
```

---

## 🐛 Bekannte Issues & Workarounds

### Reflex v0.8.24 Route-Matching Bug
- **Datei:** `venv/lib/python3.12/site-packages/reflex/route.py`, Zeile 217
- **Bug:** `path.removeprefix(config.frontend_path)` matcht nicht
- **Fix:** `path.removeprefix("/" + config.frontend_path)`
- **Auswirkung:** `on_load` feuert nie → App bleibt bei "wird initialisiert..."

### GPT-OSS-120B Parameter
- `--reasoning-format none` (NICHT deepseek!)
- `--chat-template-kwargs {"reasoning_effort": "medium"}`
- KEIN KV-Cache-Quant (`-ctk`/`-ctv`)!
- `--repeat-penalty 1.0` (kritisch!)

### GLM-4.7-REAP-218B Parameter
- `--reasoning-format deepseek`
- `--chat-template-kwargs {"enable_thinking": false}`
- `--repeat-penalty 1.0` (KRITISCH - sonst Endlos-Wiederholungen)

---

## 📚 Wichtige Dokumentation

| Datei | Inhalt |
|-------|--------|
| `README.md` | Hauptdokumentation (Englisch) |
| `README.de.md` | Hauptdokumentation (Deutsch) |
| `CHANGELOG.md` | Versionshistorie |
| `CLAUDE.md` | Projekt-spezifische Regeln |
| `docs/model-recommended-params.md` | Modell-spezifische Parameter |
| `docs/llamacpp-setup.md` | llama.cpp Setup-Anleitung |

---

## 🔗 Nützliche Befehle

### API - Message Injection
```bash
curl -s "http://localhost:8002/api/chat/inject" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"device_id": "SESSION_ID", "message": "Nachricht"}'
```

### Session-ID finden
```bash
# Debug-Log
tail data/logs/aifred_debug.log

# Session-Dateien
ls data/sessions/
```

### Modell-Kontext kalibrieren
```bash
# Binary Search für GPU-only Kontext
# (wird automatisch beim Service-Start ausgeführt)
```

---

## 🎯 Wichtige Hinweise

1. **NIEMALS Reflex-Prozesse manuell killen!** Immer über `systemctl --user` steuern
2. **Prompts aus `prompts/de/` und `prompts/en/` laden**, nicht hardcodieren
3. **Code-Qualitätsprüfungen sind PFLICHT** nach jeder Änderung
4. **Git-Workflow:** Keine automatischen Commits ohne explizite Anweisung
5. **Fallbacks nur nach Absprache** - lieber sauber neu starten
