# Telegram Bot Setup

## 1. Create the Bot

1. Open Telegram, message `@BotFather`
2. Send `/newbot`
3. Choose a name and username for your bot
4. Copy the **bot token** (e.g. `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)

## 2. Find Your User ID

1. Open Telegram, message `@userinfobot`
2. Send `/start`
3. Note your **user ID** (e.g. `123456789`)

For multiple allowed users: comma-separated IDs.

## 3. Configure AIfred

In `.env` (or via the Settings UI):

```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_ALLOWED_USERS=123456789
```

Restart AIfred. In the web UI: **Settings > Telegram > Monitor: ON**.

## 4. Test

Send a message to the bot. AIfred replies automatically (`always_reply = True`).

### Commands

| Command | Description |
|---------|-------------|
| `/clear` | Reset conversation (new session) |

## Security

- **Whitelist:** Only user IDs in `TELEGRAM_ALLOWED_USERS` can message. Empty = nobody.
- **Tier:** Incoming Telegram messages get `max_tier=1` (TIER_COMMUNICATE). No filesystem access, no code execution.
- **Credentials:** Bot token managed via credential broker, never in the LLM context.
- **Sanitization:** All inbound/outbound messages go through the security pipeline.
