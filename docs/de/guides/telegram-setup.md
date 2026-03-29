# Telegram Bot Setup

## 1. Bot erstellen

1. Telegram oeffnen, `@BotFather` anschreiben
2. `/newbot` senden
3. Bot-Name und Username vergeben
4. **Bot-Token** kopieren (z.B. `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)

## 2. User-ID herausfinden

1. Telegram oeffnen, `@userinfobot` anschreiben
2. `/start` senden
3. **User-ID** notieren (z.B. `123456789`)

Fuer mehrere erlaubte User: Jede User-ID kommagetrennt.

## 3. AIfred konfigurieren

In `.env` (oder ueber die Settings-UI):

```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_ALLOWED_USERS=123456789
```

AIfred neu starten. In der Web-UI: **Settings > Telegram > Monitor: ON**.

## 4. Testen

Dem Bot eine Nachricht schicken. AIfred antwortet automatisch (`always_reply = True`).

### Befehle

| Befehl | Beschreibung |
|--------|-------------|
| `/clear` | Konversation zuruecksetzen (neue Session) |

## Security

- **Whitelist:** Nur User-IDs in `TELEGRAM_ALLOWED_USERS` duerfen schreiben. Leer = niemand.
- **Tier:** Eingehende Telegram-Nachrichten bekommen `max_tier=1` (TIER_COMMUNICATE). Kein Dateisystem-Zugriff, keine Code-Ausfuehrung.
- **Credentials:** Bot-Token wird ueber den Credential Broker verwaltet, nie im LLM-Kontext.
- **Sanitization:** Alle ein-/ausgehenden Nachrichten werden durch die Security-Pipeline geschleust.
