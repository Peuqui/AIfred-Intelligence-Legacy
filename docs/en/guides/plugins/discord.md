# Discord Channel Plugin

**File:** `aifred/plugins/channels/discord.py`

Channel plugin for Discord bot integration with channel and DM support.

## Features

- **WebSocket/Gateway:** Permanent connection via Discord Gateway API
- **Channel + DM:** Receives messages from server channels and direct messages
- **/clear command:** Slash command to reset the conversation
- **Auto-reply:** Automatic replies configurable per channel

## Configuration

- Discord bot token via `.env`
- Bot must be created in the Discord Developer Portal and invited to the server
