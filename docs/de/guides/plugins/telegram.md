# Telegram Channel Plugin

**Datei:** `aifred/plugins/channels/telegram_channel/`

Channel-Plugin für Telegram-Bot via Long Polling.

## Features

- **Long Polling:** Effizientes Abrufen neuer Nachrichten ohne Webhook-Server
- **Whitelist-basiert:** Nur autorisierte Chat-IDs werden verarbeitet
- **Auto-Reply:** Automatische Antworten pro Kanal konfigurierbar

## Konfiguration

- Telegram Bot-Token über `.env`
- Whitelist der erlaubten Chat-IDs
- Detaillierte Setup-Anleitung: [telegram-setup.md](../telegram-setup.md)
