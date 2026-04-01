# Audio Player Plugin

**File:** `aifred/plugins/tools/audio_player.py`

Server-side audio playback of WAV and MP3 files.

## Tools

| Tool | Description | Tier |
|------|------------|------|
| `audio_play` | Play audio file | WRITE_DATA |
| `audio_stop` | Stop playback | WRITE_DATA |
| `audio_status` | Query current playback status | READONLY |

## Features

- Plays WAV/MP3 directly on the server
- Planned for Puck hardware integration
