# Email Channel Plugin

**Datei:** `aifred/plugins/channels/email_channel/`

Channel-Plugin fuer E-Mail-Kommunikation via IMAP IDLE und SMTP.

## Features

- **Push-basiert:** IMAP IDLE fuer sofortige Benachrichtigung bei neuen E-Mails
- **Ordner-Management:** Konfigurierbare IMAP-Ordner zum Ueberwachen
- **Markierungen:** Gelesene/Beantwortete E-Mails werden korrekt geflaggt
- **Auto-Reply:** Automatische Antworten pro Kanal konfigurierbar

## Konfiguration

- IMAP/SMTP-Server, Port, Credentials ueber `.env` oder UI-Modal
- TLS/SSL konfigurierbar
- Ueberwachte Ordner waehlbar

## User-Mapping und E-Mail-Routing

AIfred unterscheidet zwischen **eingehenden** und **ausgehenden** E-Mail-Adressen pro User.
Die Zuordnung wird in `data/user_mapping.json` konfiguriert:

```json
{
  "Lord Helmchen": {
    "telegram": ["8669153916"],
    "discord": [],
    "email": ["empfang@gmx.net"],
    "email_out": ["versand@mail.de"]
  }
}
```

### Routing-Logik

| Feld | Zweck | Beispiel |
|------|-------|---------|
| `email` | **Eingang:** Von dieser Adresse darf der User AIfred anschreiben | `empfang@gmx.net` |
| `email_out` | **Ausgang:** Hierhin sendet AIfred Ergebnisse (Scheduler, Tool-Calls) | `versand@mail.de` |

### Aufloesung bei ausgehenden E-Mails (Scheduler, Announce)

1. **Recipient im Job angegeben** (z.B. `"Lord Helmchen"`) → User-Mapping → `email_out` bevorzugt, Fallback auf `email`
2. **Kein Recipient** → Erster User im Mapping → `email_out` bevorzugt
3. **Kein Mapping** → Fallback auf `EMAIL_ALLOWED_SENDERS` (Allowlist, erster Eintrag)

### Allowlist (Eingang)

Die Allowlist in `EMAIL_ALLOWED_SENDERS` kontrolliert nur **eingehende** E-Mails — wer darf AIfred anschreiben. Ausgehende E-Mails koennen an jede Adresse gesendet werden.
