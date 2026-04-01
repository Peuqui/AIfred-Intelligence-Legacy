# Audio Player Plugin

**Datei:** `aifred/plugins/tools/audio_player.py`

Server-seitige Audio-Wiedergabe von WAV- und MP3-Dateien.

## Tools

| Tool | Beschreibung | Tier |
|------|-------------|------|
| `audio_play` | Audiodatei abspielen | WRITE_DATA |
| `audio_stop` | Wiedergabe stoppen | WRITE_DATA |
| `audio_status` | Aktuellen Wiedergabestatus abfragen | READONLY |

## Features

- Spielt WAV/MP3 direkt auf dem Server ab
- Geplant für Puck-Hardware-Integration
