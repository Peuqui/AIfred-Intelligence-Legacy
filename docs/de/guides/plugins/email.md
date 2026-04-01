# Email Channel Plugin

**Datei:** `aifred/plugins/channels/email_channel/`

Channel-Plugin für E-Mail-Kommunikation via IMAP IDLE und SMTP.

## Features

- **Push-basiert:** IMAP IDLE für sofortige Benachrichtigung bei neuen E-Mails
- **Ordner-Management:** Konfigurierbare IMAP-Ordner zum Überwachen
- **Markierungen:** Gelesene/Beantwortete E-Mails werden korrekt geflaggt
- **Auto-Reply:** Automatische Antworten pro Kanal konfigurierbar

## Konfiguration

- IMAP/SMTP-Server, Port, Credentials über `.env` oder UI-Modal
- TLS/SSL konfigurierbar
- Überwachte Ordner wählbar
