# Telegram Channel Plugin

**File:** `aifred/plugins/channels/telegram_channel/`

Channel plugin for Telegram bot via long polling.

## Features

- **Long polling:** Efficient retrieval of new messages without webhook server
- **Whitelist-based:** Only authorized chat IDs are processed
- **Auto-reply:** Automatic replies configurable per channel

## Configuration

- Telegram bot token via `.env`
- Whitelist of allowed chat IDs
- Detailed setup guide: [telegram-setup.md](../telegram-setup.md)
