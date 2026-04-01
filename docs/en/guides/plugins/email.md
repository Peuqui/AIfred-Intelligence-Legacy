# Email Channel Plugin

**File:** `aifred/plugins/channels/email_channel/`

Channel plugin for email communication via IMAP IDLE and SMTP.

## Features

- **Push-based:** IMAP IDLE for instant notification on new emails
- **Folder management:** Configurable IMAP folders to monitor
- **Flags:** Read/replied emails are correctly flagged
- **Auto-reply:** Automatic replies configurable per channel

## Configuration

- IMAP/SMTP server, port, credentials via `.env` or UI modal
- TLS/SSL configurable
- Monitored folders selectable
