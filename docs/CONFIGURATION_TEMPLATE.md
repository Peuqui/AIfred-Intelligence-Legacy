# AIfred Intelligence - Configuration Template

Dies ist die vollständige Referenz für alle Konfigurationsparameter in `aifred/lib/config.py`.

## 📋 Inhaltsverzeichnis

1. [Project Paths](#project-paths)
2. [Debug Configuration](#debug-configuration)
3. [Logging Configuration](#logging-configuration)
4. [Whisper Models](#whisper-models)
5. [Language Configuration](#language-configuration)
6. [Default Settings](#default-settings)
7. [Backend-Specific Models](#backend-specific-models)
8. [Available Voices](#available-voices)
9. [Research Modes](#research-modes)
10. [TTS Engines](#tts-engines)
11. [Context Management](#context-management)
12. [History Summarization](#history-summarization)
13. [VRAM Management](#vram-management)
14. [Vector Cache Configuration](#vector-cache-configuration)

---

## Project Paths

```python
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
PIPER_MODEL_PATH = PROJECT_ROOT / "piper_models" / "de_DE-thorsten-medium.onnx"
SETTINGS_FILE = PROJECT_ROOT / "assistant_settings.json"
SSL_KEYFILE = PROJECT_ROOT / "ssl" / "privkey.pem"
SSL_CERTFILE = PROJECT_ROOT / "ssl" / "fullchain.pem"
```

**Beschreibung:**
- `PROJECT_ROOT`: Wurzelverzeichnis des Projekts (automatisch erkannt)
- `PIPER_MODEL_PATH`: Pfad zum Piper TTS Model (lokales TTS)
- `SETTINGS_FILE`: Pfad zur Settings-Datei (deprecated, jetzt: `~/.config/aifred/settings.json`)
- `SSL_KEYFILE/CERTFILE`: SSL-Zertifikate für HTTPS

---

## Debug Configuration

```python
DEBUG_ENABLED = True  # Set to False to disable debug output
```

**Beschreibung:**
- Global Debug-Flag für das gesamte System
- `True`: Debug-Output aktiviert (Entwicklung)
- `False`: Nur kritische Fehler (Produktion)

---

## Logging Configuration

```python
CONSOLE_DEBUG_ENABLED = True  # Messages ins UI Debug-Console senden
FILE_DEBUG_ENABLED = True      # Messages ins Log-File schreiben
```

**Beschreibung:**
- **Console Debug**: Zeigt Debug-Messages in der UI Debug-Console
- **File Debug**: Schreibt Debug-Messages in `logs/aifred_debug.log`
- Beide können unabhängig aktiviert/deaktiviert werden

---

## Whisper Models

```python
WHISPER_MODELS = {
    "tiny (39MB, schnell, englisch)": "tiny",
    "base (74MB, schneller, multilingual)": "base",
    "small (466MB, bessere Qualität, multilingual)": "small",
    "medium (1.5GB, hohe Qualität, multilingual)": "medium",
    "large-v3 (2.9GB, beste Qualität, multilingual)": "large-v3"
}
```

**Beschreibung:**
- **tiny**: Schnellstes Modell, nur Englisch, geringe Qualität
- **base**: Guter Kompromiss, multilingual
- **small**: **Empfohlen** - Beste Balance aus Geschwindigkeit/Qualität
- **medium**: Hohe Qualität, benötigt mehr VRAM
- **large-v3**: Beste Qualität, benötigt viel VRAM (~2GB)

---

## Language Configuration

```python
DEFAULT_LANGUAGE = "auto"  # "auto", "de", or "en"
```

**Beschreibung:**
- `"auto"`: Automatische Spracherkennung basierend auf User-Input
- `"de"`: Deutsch (fester Modus)
- `"en"`: English (fester Modus)

---

## Default Settings

```python
DEFAULT_SETTINGS = {
    "voice": "Deutsch (Katja)",
    "tts_speed": 1.25,
    "enable_tts": False,
    "tts_engine": "Edge TTS (Cloud, beste Qualität)",
    "whisper_model": "small (466MB, bessere Qualität, multilingual)",
    "research_mode": "automatik",
    "show_transcription": False,
    "enable_gpu": True,
    "temperature": 0.7,
    "temperature_mode": "auto",
    "enable_thinking": True
}
```

**Beschreibung:**
- **voice**: TTS-Stimme (siehe [Available Voices](#available-voices))
- **tts_speed**: Sprech-Geschwindigkeit (0.5 - 2.0)
- **enable_tts**: TTS aktivieren (Text-to-Speech)
- **tts_engine**: TTS Engine (Edge TTS oder Piper TTS)
- **whisper_model**: STT Model für Sprach-Erkennung
- **research_mode**: Recherche-Modus (`"automatik"`, `"quick"`, `"deep"`, `"none"`)
- **show_transcription**: STT-Transkript in UI anzeigen
- **enable_gpu**: GPU-Nutzung für Whisper STT
- **temperature**: LLM Sampling Temperature (0.0-2.0)
- **temperature_mode**: `"auto"` (Intent-Detection) oder `"manual"` (fixer Wert)
- **enable_thinking**: Qwen3 Thinking Mode aktivieren (Chain-of-Thought Reasoning)

**Hinweis:** Model-Namen werden aus `BACKEND_DEFAULT_MODELS` geladen (siehe unten).

---

## Backend-Specific Models

```python
BACKEND_DEFAULT_MODELS = {
    "ollama": {
        "selected_model": "qwen3:30b-a3b-instruct-2507-q4_K_M",    # ~17.3GB
        "automatik_model": "qwen3:4b-instruct-2507-q4_K_M",        # ~2.6GB
    },
    "vllm": {
        "selected_model": "cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit",  # ~18GB
        "automatik_model": "cpatonn/Qwen3-4B-Instruct-2507-AWQ-4bit",      # ~2.8GB
    },
    "tabbyapi": {
        "selected_model": "turboderp/Qwen3-30B-A3B-exl3",                  # ~18GB
        "automatik_model": "ArtusDev/Qwen_Qwen3-4B-Instruct-2507-EXL3",    # ~2.8GB
    },
}
```

**Beschreibung:**
- **selected_model**: Haupt-LLM für finale Antworten (Qwen3-30B-A3B MoE)
- **automatik_model**: Automatik-LLM für Query-Optimierung & Entscheidungen (Qwen3-4B)
- Alle Backends nutzen die **gleiche Modell-Größe** für Performance-Vergleiche

**Model-Formate:**
- **Ollama**: GGUF Q4_K_M (quantisiert)
- **vLLM**: AWQ 4-bit (quantisiert)
- **TabbyAPI**: EXL3 (quantisiert)

---

## Available Voices

```python
VOICES = {
    "Deutsch (Katja)": "de-DE-KatjaNeural",
    "Deutsch (Conrad)": "de-DE-ConradNeural",
    "Englisch (Jenny)": "en-US-JennyNeural",
    "Englisch (Guy)": "en-US-GuyNeural",
    "Französisch (Denise)": "fr-FR-DeniseNeural",
    "Spanisch (Elvira)": "es-ES-ElviraNeural"
}
```

**Beschreibung:**
- Edge TTS (Microsoft Azure Neural Voices)
- Natürliche, hochqualitative Stimmen
- Kostenlos, aber benötigt Internet-Verbindung

---

## Research Modes

```python
RESEARCH_MODES = [
    "🤖 Automatik (variabel, KI entscheidet)",
    "❌ Aus (nur eigenes Wissen)",
    "🔍 Web-Suche Schnell (3 Quellen)",
    "📚 Web-Suche Ausführlich (5 Quellen)"
]
```

**Internal Values (in settings.json):**
- `"automatik"`: KI entscheidet automatisch (empfohlen)
- `"none"`: Keine Recherche, nur LLM-Wissen
- `"quick"`: Schnelle Web-Suche (3 Quellen)
- `"deep"`: Ausführliche Web-Suche (5 Quellen)

---

## TTS Engines

```python
TTS_ENGINES = [
    "Edge TTS (Cloud, beste Qualität)",
    "Piper TTS (Lokal, Offline)"
]
```

**Beschreibung:**
- **Edge TTS**: Cloud-basiert, beste Qualität, benötigt Internet
- **Piper TTS**: Lokal, Offline-fähig, etwas robotisch

---

## Context Management

```python
MAX_RAG_CONTEXT_TOKENS = 20000  # Maximale Tokens für RAG-Context
MAX_WORDS_PER_SOURCE = 2000     # Max. Wörter pro Quelle
CHARS_PER_TOKEN = 3             # Token-zu-Zeichen Ratio
```

**Beschreibung:**
- **MAX_RAG_CONTEXT_TOKENS**: Maximale Tokens für Recherche-Ergebnisse
  - Bei 40k Model-Limit → 20k RAG Context (50% Reserve für History/Prompt)
  - Kann bei größeren Models erhöht werden
- **MAX_WORDS_PER_SOURCE**: Verhindert, dass eine Quelle den Context dominiert
- **CHARS_PER_TOKEN**: Durchschnitt für Deutsch/Englisch Mix

---

## History Summarization

```python
HISTORY_COMPRESSION_THRESHOLD = 0.7   # 70% des Context-Limits
HISTORY_MESSAGES_TO_COMPRESS = 6      # 6 Messages = 3 Frage-Antwort-Paare
HISTORY_MAX_SUMMARIES = 10            # Max. Anzahl gespeicherter Summaries
HISTORY_SUMMARY_TARGET_TOKENS = 1000  # Target-Größe pro Summary
HISTORY_SUMMARY_TARGET_WORDS = 750    # Target-Wörter (für Prompt)
HISTORY_SUMMARY_TEMPERATURE = 0.3     # Temperature für Summary-Generierung
HISTORY_SUMMARY_CONTEXT_LIMIT = 4096  # Context-Limit für Summary-LLM
```

**Beschreibung:**
- **Compression Threshold**: Bei 70% Context-Auslastung wird komprimiert
- **Messages to Compress**: Anzahl älterer Messages die komprimiert werden
- **Max Summaries**: FIFO - älteste Summary wird gelöscht bei Overflow
- **Target Tokens/Words**: Ziel-Größe für komprimierte Summaries
- **Temperature**: Niedrig (0.3) für faktische, präzise Zusammenfassungen
- **Context Limit**: Summary-LLM sollte kleiner sein (4k statt 32k)

---

## VRAM Management

```python
ENABLE_VRAM_CONTEXT_CALCULATION = True  # VRAM-basierte Context-Berechnung
VRAM_SAFETY_MARGIN = 512                # Safety Margin (MB)
VRAM_CONTEXT_RATIO = 0.097              # MB VRAM pro Token
```

**Beschreibung:**
- **Enable VRAM Context Calculation**:
  - `True`: Dynamische Context-Berechnung basierend auf verfügbarem VRAM
  - `False`: Nur Model's architektonisches Limit verwenden
- **VRAM Safety Margin**: Reserve für OS, Xorg, Whisper STT (~512MB)
- **VRAM Context Ratio**: Empirischer Wert für Qwen3-30B (~97KB/Token)
  - Gemessen: 12K Tokens = 1163MB VRAM (KV Cache)
- **vLLM Overheads**: Empirisch gemessene Werte für RTX 3090 Ti
  - Können je nach GPU/Modell/Quantisierung variieren
  - Bei anderen GPUs anpassen falls nötig

---

## Vector Cache Configuration

```python
# Distance Thresholds (Cosine Distance: 0.0 = identisch, 2.0 = verschieden)
CACHE_DISTANCE_HIGH = 0.5       # < 0.5 = HIGH confidence Cache-Hit
CACHE_DISTANCE_MEDIUM = 0.5     # >= 0.5 = Trigger RAG check
CACHE_DISTANCE_DUPLICATE = 0.3  # < 0.3 = Semantisches Duplikat (merge)
CACHE_DISTANCE_RAG = 1.2        # < 1.2 = Ähnlich genug für RAG-Context

# TTL-Based Cache System (Volatility Levels)
TTL_HOURS = {
    'DAILY': 24,        # News, aktuelle Events
    'WEEKLY': 168,      # Politik-Updates (7 Tage)
    'MONTHLY': 720,     # Semi-aktuelle Themen (30 Tage)
    'PERMANENT': None   # Zeitlose Fakten
}

CACHE_CLEANUP_INTERVAL_HOURS = 12  # Background Cleanup alle 12h
CACHE_STARTUP_CLEANUP = True        # Cleanup beim Server-Start
```

**Beschreibung:**
- **Distance Thresholds**: Steuern semantische Ähnlichkeit für Cache-Hits
- **TTL System**: Automatisches Verfallen basierend auf Content-Volatilität
  - LLM bestimmt Volatilität via `<volatility>` Tag in Response
- **Cleanup**: Automatisches Löschen abgelaufener Einträge

**Volatile Keywords:**
- Geladen aus `prompts/cache_volatile_keywords.txt`
- Keywords die eine LLM-Entscheidung triggern (z.B. "heute", "aktuell")

---

## Verwendung

### Settings Zurücksetzen

```python
from aifred.lib.settings import reset_to_defaults

reset_to_defaults()  # Schreibt alle Werte aus config.py in settings.json
```

### Eigene Config-Werte

1. **Option A: settings.json editieren** (Runtime-Änderungen)
   - Datei: `~/.config/aifred/settings.json`
   - Änderungen werden sofort beim Neustart übernommen

2. **Option B: config.py editieren** (Default-Änderungen)
   - Datei: `aifred/lib/config.py`
   - Ändert die Defaults für alle neuen Installationen
   - Danach: `reset_to_defaults()` aufrufen

### Wichtige Hinweise

⚠️ **Model-Namen nicht in DEFAULT_SETTINGS!**
- Model-Namen werden aus `BACKEND_DEFAULT_MODELS` extrahiert
- `DEFAULT_SETTINGS` enthält nur backend-unabhängige Settings

⚠️ **Git ist dein Backup!**
- `config.py` ist versioniert
- Bei Problemen: `git restore aifred/lib/config.py`

⚠️ **Keine Secrets in config.py!**
- API-Keys gehören in `.env` oder `~/.config/aifred/.env`
- `config.py` ist öffentlich im Repository

---

## Beispiel-Konfiguration

### Minimal (Low-VRAM Setup)

```python
# Für RTX 3060 (12GB VRAM)
BACKEND_DEFAULT_MODELS = {
    "ollama": {
        "selected_model": "qwen3:8b-instruct-2507-q4_K_M",  # ~5GB
        "automatik_model": "qwen3:1.8b-instruct-2507-q4_K_M",  # ~1.5GB
    }
}

MAX_RAG_CONTEXT_TOKENS = 12000  # Reduziert für kleinere Models
VRAM_CONTEXT_RATIO = 0.05  # ~50KB/Token für 8B Models
```

### High-Performance (High-VRAM Setup)

```python
# Für RTX 4090 (24GB VRAM) oder Tesla P40 (24GB)
BACKEND_DEFAULT_MODELS = {
    "ollama": {
        "selected_model": "qwen3:70b-instruct-2507-q4_K_M",  # ~40GB (CPU Offload)
        "automatik_model": "qwen3:8b-instruct-2507-q4_K_M",  # ~5GB
    }
}

MAX_RAG_CONTEXT_TOKENS = 30000  # Mehr Context für größere Models
VRAM_SAFETY_MARGIN = 1024  # Mehr Reserve für größere KV Cache
```

---

## Support & Dokumentation

- **Haupt-Dokumentation**: [README.md](../README.md)
- **Installation**: [INSTALLATION.md](INSTALLATION.md)
- **API-Dokumentation**: [API.md](API.md)
- **GitHub Issues**: https://github.com/yourusername/aifred-intelligence/issues

---

**Letzte Aktualisierung:** 2025-01-18
**Version:** 1.0.0
