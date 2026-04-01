# Discord Channel Plugin

**Datei:** `aifred/plugins/channels/discord.py`

Channel-Plugin für Discord-Bot-Integration mit Channel- und DM-Unterstützung.

## Features

- **WebSocket/Gateway:** Permanente Verbindung über Discord Gateway API
- **Channel + DM:** Empfängt Nachrichten aus Server-Kanälen und Direktnachrichten
- **/clear Command:** Slash-Command zum Zurücksetzen der Konversation
- **Auto-Reply:** Automatische Antworten pro Kanal konfigurierbar

## Konfiguration

- Discord Bot-Token über `.env`
- Bot muss im Discord Developer Portal erstellt und zum Server eingeladen werden
