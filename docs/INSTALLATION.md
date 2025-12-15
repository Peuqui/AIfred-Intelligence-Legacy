# AIfred Intelligence - Installationsanleitung

**Letzte Aktualisierung:** 2025-12-15

---

## Inhaltsverzeichnis

1. [Systemvoraussetzungen](#systemvoraussetzungen)
2. [Schnellinstallation](#schnellinstallation)
3. [Detaillierte Installation](#detaillierte-installation)
4. [Optionale Komponenten](#optionale-komponenten)
5. [Konfiguration](#konfiguration)
6. [Troubleshooting](#troubleshooting)

---

## Systemvoraussetzungen

### Minimum

- **OS:** Ubuntu 22.04+ / Debian 12+ / WSL2 (Windows 11)
- **Python:** 3.10+
- **RAM:** 16 GB
- **GPU:** NVIDIA mit 8+ GB VRAM (CUDA) oder AMD mit ROCm-Support
- **Speicher:** 10 GB für Basis, 50+ GB für LLM-Modelle

### Empfohlen

- **RAM:** 32+ GB
- **GPU:** NVIDIA RTX 3060+ (12 GB) oder Tesla P40 (24 GB)
- **Speicher:** 100+ GB SSD

---

## Schnellinstallation

```bash
# 1. Repository klonen
git clone https://github.com/Peuqui/AIfred-Intelligence.git
cd AIfred-Intelligence

# 2. Python Virtual Environment erstellen
python3 -m venv venv
source venv/bin/activate

# 3. Python-Abhängigkeiten installieren
pip install -r requirements.txt

# 4. System-Abhängigkeiten installieren
sudo apt install espeak-ng ffmpeg

# 5. ChromaDB Docker starten (für Vector Cache)
docker run -d --name chromadb -p 8000:8000 chromadb/chroma

# 6. Ollama installieren (wenn nicht vorhanden)
curl -fsSL https://ollama.ai/install.sh | sh

# 7. AIfred starten
reflex run
```

---

## Detaillierte Installation

### 1. System-Pakete

```bash
# Basis-Pakete
sudo apt update
sudo apt install -y \
    python3 python3-pip python3-venv \
    git curl wget \
    ffmpeg \
    build-essential
```

### 2. Python-Umgebung

```bash
# Virtual Environment erstellen
python3 -m venv venv
source venv/bin/activate

# Pip aktualisieren
pip install --upgrade pip

# Abhängigkeiten installieren
pip install -r requirements.txt
```

### 3. LLM-Backend (Ollama)

```bash
# Ollama installieren
curl -fsSL https://ollama.ai/install.sh | sh

# Ollama-Service starten
sudo systemctl start ollama
sudo systemctl enable ollama

# Modell herunterladen (Beispiel)
ollama pull qwen2.5:14b
```

Für GPU-Optimierung siehe [GPU_COMPATIBILITY.md](GPU_COMPATIBILITY.md).

### 4. Vector Cache (ChromaDB)

```bash
# Docker installieren (falls nicht vorhanden)
sudo apt install docker.io
sudo usermod -aG docker $USER
# Ausloggen und wieder einloggen für Gruppenänderung

# ChromaDB Container starten
docker run -d \
    --name chromadb \
    -p 8000:8000 \
    -v chromadb_data:/chroma/chroma \
    --restart unless-stopped \
    chromadb/chroma
```

### 5. TTS-Engines (Text-to-Speech)

#### Edge TTS (Cloud, empfohlen)
```bash
# Bereits in requirements.txt enthalten
pip install edge-tts==7.2.1
```

#### Piper TTS (Lokal, Offline)
```bash
# Piper installieren
pip install piper-tts

# Deutsche Stimme herunterladen
mkdir -p piper_models
cd piper_models
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx.json
cd ..
```

#### eSpeak (Roboter, Offline)
```bash
# Basis-Installation
sudo apt install espeak-ng

# Für natürlichere mbrola-Stimmen (optional)
sudo apt install mbrola mbrola-de2 mbrola-de3 mbrola-de4 mbrola-de5 mbrola-de6 mbrola-de7
```

**Verfügbare eSpeak-Stimmen nach Installation:**

| Stimme | Typ | Beschreibung |
|--------|-----|--------------|
| `de` | Standard | Roboterhaft |
| `de+m1`, `de+m2` | Standard | Männlich Varianten |
| `de+f1`, `de+f2` | Standard | Weiblich Varianten |
| `mb/mb-de2` | mbrola | Männlich, tief |
| `mb/mb-de3` | mbrola | Weiblich |
| `mb/mb-de4` | mbrola | Männlich, tief |
| `mb/mb-de5` | mbrola | Weiblich |
| `mb/mb-de6` | mbrola | Männlich, rauchig |
| `mb/mb-de7` | mbrola | Weiblich |

### 6. STT-Engine (Speech-to-Text)

```bash
# Whisper (bereits in requirements.txt)
pip install faster-whisper

# Modell wird automatisch beim ersten Start heruntergeladen
# Konfigurierbar in config.py: WHISPER_MODELS
```

---

## Optionale Komponenten

### Web-Recherche APIs

Für die automatische Web-Recherche werden API-Keys benötigt. Erstelle eine `.env` Datei:

```bash
# .env
TAVILY_API_KEY=tvly-xxxxx           # https://tavily.com
BRAVE_API_KEY=BSAxxx                # https://brave.com/search/api
SEARXNG_URL=http://localhost:8080   # Self-hosted SearXNG
```

Siehe [api/API_SETUP.md](api/API_SETUP.md) für Details.

### Alternative LLM-Backends

#### vLLM (für AWQ-Modelle)
```bash
pip install vllm
# Siehe docs/vllm/ für Konfiguration
```

#### KoboldCPP (erweiterter Kontext)
```bash
# Download von https://github.com/LostRuins/koboldcpp
# Siehe GPU_COMPATIBILITY.md
```

#### TabbyAPI (EXL2-Modelle)
```bash
# Siehe https://github.com/theroyallab/tabbyAPI
```

### Vision/OCR-Modelle

Für Bildanalyse:
```bash
ollama pull minicpm-v
ollama pull llava:13b
```

---

## Konfiguration

### Hauptkonfiguration

Die Hauptkonfiguration erfolgt in `aifred/lib/config.py`:

```python
# Sprache
DEFAULT_LANGUAGE = "auto"  # "auto", "de", "en"

# TTS
TTS_ENGINES = ["Edge TTS", "Piper TTS", "eSpeak"]
DEFAULT_TTS_ENGINE = "Edge TTS (Cloud, beste Qualität)"

# STT
WHISPER_DEVICE = "cpu"     # "cpu" oder "cuda"
WHISPER_COMPUTE_TYPE = "int8"

# Context
MAX_RAG_CONTEXT_TOKENS = 20000
```

### Umgebungsvariablen (.env)

```bash
# API Keys
TAVILY_API_KEY=
BRAVE_API_KEY=
SEARXNG_URL=

# Backend URLs (optional)
OLLAMA_HOST=http://localhost:11434
VLLM_HOST=http://localhost:8001
KOBOLDCPP_HOST=http://localhost:5001

# ChromaDB
CHROMA_HOST=localhost
CHROMA_PORT=8000
```

---

## Troubleshooting

### Edge TTS crasht Reflex

**Problem:** Service stürzt ab mit `aiohttp` Fehlern.

**Lösung:** Edge TTS 7.2.1 verwenden (7.2.3 hat einen Bug):
```bash
pip install edge-tts==7.2.1
```

### mbrola "Permission denied"

**Problem:** `mbrola: Permission denied` Fehlermeldung.

**Lösung:** mbrola-Paket installieren:
```bash
sudo apt install mbrola mbrola-de2 mbrola-de4 mbrola-de6
```

### ChromaDB verbindet nicht

**Problem:** Vector Cache funktioniert nicht.

**Lösung:**
```bash
# Container Status prüfen
docker ps -a | grep chromadb

# Neu starten
docker restart chromadb

# Logs prüfen
docker logs chromadb
```

### Ollama GPU nicht erkannt

**Problem:** Ollama nutzt nur CPU.

**Lösung für NVIDIA:**
```bash
# CUDA prüfen
nvidia-smi

# Ollama neu starten
sudo systemctl restart ollama
```

**Lösung für AMD (Radeon 780M):**
```bash
# Override für gfx1103 setzen
sudo mkdir -p /etc/systemd/system/ollama.service.d/
sudo tee /etc/systemd/system/ollama.service.d/override.conf << 'EOF'
[Service]
Environment="HSA_OVERRIDE_GFX_VERSION=11.0.2"
EOF
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

Siehe [GPU_COMPATIBILITY.md](GPU_COMPATIBILITY.md) für Details.

### Whisper lädt kein Modell

**Problem:** STT funktioniert nicht.

**Lösung:**
```bash
# Modell manuell herunterladen
python -c "from faster_whisper import WhisperModel; WhisperModel('base')"
```

---

## Nächste Schritte

1. **Modelle konfigurieren:** Lade LLM-Modelle via `ollama pull`
2. **API-Keys einrichten:** Für Web-Recherche (siehe [API_SETUP.md](api/API_SETUP.md))
3. **AIfred starten:** `reflex run`
4. **Browser öffnen:** http://localhost:3000

---

## Weiterführende Dokumentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - System-Architektur
- [GPU_COMPATIBILITY.md](GPU_COMPATIBILITY.md) - GPU-Kompatibilität
- [CONFIGURATION_TEMPLATE.md](CONFIGURATION_TEMPLATE.md) - Konfigurationsreferenz
- [api/API_SETUP.md](api/API_SETUP.md) - API-Keys Setup

---

**Bei Problemen:** GitHub Issues unter https://github.com/Peuqui/AIfred-Intelligence/issues
