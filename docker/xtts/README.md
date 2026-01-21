# XTTS v2 Voice Cloning Service

Coqui XTTS v2 als Docker-Service für AIfred mit Voice Cloning und multilingualer Unterstützung.

## Features

- **Voice Cloning**: Klone Stimmen aus 6-10 Sekunden Referenz-Audio
- **Multilinguale Unterstützung**: 16 Sprachen inkl. automatisches Code-Switching (DE/EN gemischt)
- **58 Built-in Stimmen**: Sofort nutzbare Stimmen aus der XTTS-Bibliothek
- **Custom Voices**: Eigene Stimmen persistent speichern (AIfred, Sokrates, ...)
- **Auto-Chunking**: Lange Texte werden automatisch aufgeteilt (XTTS 400-Token-Limit)
- **Smart Device Selection**: Automatische GPU/CPU-Auswahl basierend auf VRAM
- **Web UI**: Integriertes Test-Interface unter `http://localhost:5051`

## Quick Start

```bash
cd docker/xtts
docker compose up -d
```

Erster Start dauert ~2-3 Minuten (Modell-Download ~1.5GB).

## Konfiguration

### Umgebungsvariablen

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `XTTS_VRAM_THRESHOLD` | `2.0` | Minimum freies VRAM (GB) für GPU-Nutzung |
| `XTTS_FORCE_CPU` | `0` | Erzwingt CPU-Modus wenn `1` oder `true` |
| `CUDA_VISIBLE_DEVICES` | `0` | GPU-Index für CUDA |

### Smart Device Selection

XTTS prüft beim ersten Request den verfügbaren VRAM via `nvidia-smi`:

- **GPU-Modus**: Wenn freies VRAM >= `XTTS_VRAM_THRESHOLD` (schnell, ~2-3s pro Satz)
- **CPU-Modus**: Wenn VRAM nicht ausreicht (langsamer, ~15-30s, aber konkurriert nicht mit Ollama)

```
🔍 GPU 0 (NVIDIA GeForce RTX 3090 Ti): 19.18 GB free / 24.0 GB total
✅ Sufficient VRAM (19.18 GB >= 2.0 GB) - using GPU
🎯 Selected device: CUDA
```

## API Endpoints

### TTS Generation

```bash
POST /tts
Content-Type: application/json

{
  "text": "Hallo, ich bin AIfred. How can I help you?",
  "speaker": "aifred",      # oder "Claribel Dervla" für built-in
  "language": "de"          # de, en, fr, es, it, pt, pl, tr, ru, nl, cs, ar, zh-cn, ja, hu, ko
}

# Returns: audio/wav
```

### Voice Cloning

```bash
POST /voices/clone
Content-Type: multipart/form-data

- audio: WAV-Datei (6-10s klare Sprache, mono, 22-24kHz)
- name: Name für die geklonte Stimme

# Returns: {"success": true, "voice": "name"}
```

### Status & Info

```bash
# Health Check
GET /health
# {"status": "ok", "model_loaded": true, "device": "cuda", "custom_voices": 2}

# Detaillierter Status mit VRAM-Info
GET /status
# {"device": "cuda", "system_vram": {...}, "torch_memory": {...}, ...}

# Verfügbare Stimmen
GET /voices
# {"custom": ["aifred", "sokrates"], "builtin": ["Claribel Dervla", ...], "default": "Claribel Dervla"}

# Unterstützte Sprachen
GET /languages
# {"de": "German", "en": "English", ...}
```

## Custom Voices hinzufügen

### Methode 1: WAV-Datei im voices/ Verzeichnis

1. WAV-Datei erstellen (6-10s klare Sprache, mono, 22-24kHz empfohlen)
2. Datei in `docker/xtts/voices/` ablegen (z.B. `meine_stimme.wav`)
3. Container neustarten: `docker compose restart`
4. Embedding wird automatisch generiert

### Methode 2: Web UI

1. `http://localhost:5051` öffnen
2. "Voice Cloning" Sektion nutzen
3. WAV hochladen und Namen vergeben

### Methode 3: API

```bash
curl -X POST http://localhost:5051/voices/clone \
  -F "audio=@meine_stimme.wav" \
  -F "name=meine_stimme"
```

## Volumes

| Volume | Pfad im Container | Beschreibung |
|--------|-------------------|--------------|
| `xtts_models` | `/root/.local/share/tts` | XTTS Modell (~1.5GB) |
| `xtts_voices` | `/app/custom_voices` | Geklonte Stimmen (.pth) |
| `./voices` | `/app/voices` (ro) | Referenz-WAVs für Auto-Cloning |

## Troubleshooting

### Container startet nicht

```bash
# Logs prüfen
docker logs xtts

# Health Check
curl http://localhost:5051/health
```

### CUDA out of memory

```bash
# Prüfen welches Device gewählt wurde
curl http://localhost:5051/status | jq .device

# CPU-Modus erzwingen
# In docker-compose.yml:
# - XTTS_FORCE_CPU=1
```

### Stimme klingt schlecht

- Referenz-Audio sollte 6-10 Sekunden sein
- Klare Sprache ohne Hintergrundgeräusche
- Mono-Kanal, 22-24kHz Sample-Rate
- Keine Musik oder Effekte

## Auto-Chunking (Lange Texte)

XTTS hat ein internes Limit von 400 Tokens (~250 Zeichen). Der Service teilt längere Texte automatisch auf:

1. **Satz-basiert**: Trennung an `.` `!` `?`
2. **Klausel-basiert**: Bei langen Sätzen Trennung an `,` `;` `:`
3. **Wort-basiert**: Fallback für sehr lange Passagen ohne Interpunktion

Die Audio-Chunks werden mit 100ms Pause dazwischen zusammengefügt.

```bash
# Beispiel: Langer Text wird automatisch verarbeitet
curl -X POST http://localhost:5051/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Ein sehr langer Text mit vielen Sätzen...", "speaker": "AIfred"}' \
  --output long_text.wav
```

## Performance

| Device | RTF* | ~Latenz pro Satz |
|--------|------|------------------|
| RTX 3090 Ti | ~0.15 | 2-3s |
| RTX 3060 | ~0.3 | 4-5s |
| CPU (i7-12700) | ~2.0 | 15-30s |

*RTF = Real-Time Factor (< 1.0 = schneller als Echtzeit)

## Unterstützte Sprachen

- Deutsch (de)
- English (en)
- Español (es)
- Français (fr)
- Italiano (it)
- Português (pt)
- Polski (pl)
- Türkçe (tr)
- Русский (ru)
- Nederlands (nl)
- Čeština (cs)
- العربية (ar)
- 中文 (zh-cn)
- 日本語 (ja)
- Magyar (hu)
- 한국어 (ko)

## Text-Normalisierung & Best Practices

XTTS v2 ist empfindlich gegenüber bestimmten Textmustern. Der Service führt automatische Normalisierung durch, um Halluzinationen und Artefakte zu vermeiden.

### Automatische Normalisierung (in server.py)

| Was | Transformation | Grund |
|-----|----------------|-------|
| Lach-Emojis | 😂🤣😆 → "hahaha" | Klingt natürlich |
| Andere Emojis | Entfernt | Nicht aussprechbar |
| Doppelpunkte | `:` → `.` (außer in Zeiten/URLs) | Verursacht hastiges Sprechen |
| Fehlende Satzzeichen | Punkt am Ende hinzufügen | Verhindert Halluzinationen |
| Sonderzeichen | Entfernt (außer Whitelist) | Verursacht "Quirzel"-Sounds |

### Erlaubte Zeichen (Whitelist)

```
Buchstaben:  a-z A-Z äöüÄÖÜß (+ weitere europäische Zeichen)
Zahlen:      0-9
Interpunktion: . , ! ? ; : - ' " ( ) [ ]
Whitespace:  Leerzeichen, Newlines
```

### Community Best Practices

Basierend auf Erfahrungen der Coqui TTS Community:

**Interpunktion:**
- ✅ Sätze immer mit `.` `!` oder `?` beenden (verhindert Halluzinationen)
- ✅ Anführungszeichen `"` und `'` bleiben erhalten
- ✅ Bindestriche `-` funktionieren gut für zusammengesetzte Wörter
- ⚠️ Doppelpunkte `:` werden zu Punkten konvertiert (verursachen hastiges Sprechen)
- ⚠️ Keine Kommas am Satzanfang (mittlere Abschnitte werden übersprungen)

**Text-Struktur:**
- ✅ Kurze bis mittellange Sätze (< 250 Zeichen)
- ✅ Natürliche Pausen durch Interpunktion
- ⚠️ Keine trailing Leerzeichen nach `.` (verursacht Halluzinationen)
- ❌ Markdown, Code-Blöcke, Tabellen (vom Client vorfiltern!)

**Inference-Parameter (Umgebungsvariablen):**

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `XTTS_TEMPERATURE` | `0.65` | Niedrigere Werte = stabiler, weniger kreativ |
| `XTTS_REPETITION_PENALTY` | `15.0` | Höhere Werte = weniger Wiederholungen |
| `XTTS_TOP_K` | `30` | Niedrigere Werte = deterministischer |
| `XTTS_TOP_P` | `0.75` | Niedrigere Werte = weniger Variation |
| `XTTS_LENGTH_PENALTY` | `1.0` | Beeinflusst Output-Länge |
| `XTTS_MAX_CHUNK_CHARS` | `250` | Max. Zeichen pro Chunk (400 Token Limit) |

**Bei Halluzinationen/Wiederholungen:**
1. `XTTS_REPETITION_PENALTY` erhöhen (z.B. auf 20.0)
2. `XTTS_TEMPERATURE` senken (z.B. auf 0.5)
3. `XTTS_TOP_K` senken (z.B. auf 20)

### Quellen

- [GitHub Discussion #4146 - Hallucination Prevention](https://github.com/coqui-ai/TTS/discussions/4146)
- [HuggingFace Discussion #104 - Problematic Tokens](https://huggingface.co/coqui/XTTS-v2/discussions/104)
- [GitHub Discussion #2742 - Reducing Hallucinations](https://github.com/coqui-ai/TTS/discussions/2742)

## Lizenz

XTTS v2 ist unter der Coqui Public Model License lizenziert.
Durch Nutzung stimmst du den Coqui Terms of Service zu (`COQUI_TOS_AGREED=1`).
