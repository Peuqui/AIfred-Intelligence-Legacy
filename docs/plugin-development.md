# Plugin Development Guide

AIfred uses a unified plugin system. All plugins live in `aifred/plugins/`. System code (interfaces, registry) lives in `aifred/lib/`.

## Plugin Types

### Tool Plugins (`plugins/tools/`)

Provide tools the LLM can call during conversations (web search, EPIM, sandbox, etc.).

**Required interface** (`ToolPlugin` protocol in `aifred/lib/plugin_base.py`):

```python
from dataclasses import dataclass
from aifred.lib.function_calling import Tool
from aifred.lib.plugin_base import PluginContext

@dataclass
class MyPlugin:
    name: str = "my_plugin"

    def is_available(self) -> bool:
        """Check if this plugin can run (config, services, etc.)."""
        return True

    def get_tools(self, ctx: PluginContext) -> list[Tool]:
        """Return Tool instances for the LLM."""
        async def _execute(query: str) -> str:
            return f"Result for {query}"

        return [Tool(
            name="my_tool",
            description="What this tool does",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
            executor=_execute,
        )]

    def get_prompt_instructions(self, lang: str) -> str:
        """Prompt text injected into the LLM system prompt. Empty = none."""
        return ""

    def get_ui_status(self, tool_name: str, tool_args: dict, lang: str) -> str:
        """UI status text shown while this tool executes. Empty = not owned."""
        return ""

# Module-level instance (discovered by registry)
plugin = MyPlugin()
```

**Key points:**
- File goes in `aifred/plugins/tools/`
- Must expose a module-level `plugin` attribute
- `PluginContext` provides: `agent_id`, `lang`, `session_id`, `state` (None in Hub), `user_query`
- Tool executors are async functions returning strings (JSON for errors)
- Prompt instructions are loaded from `prompts/` files (not hardcoded)

### Channel Plugins (`plugins/channels/`)

Receive and send messages via external services (email, Discord, Telegram, etc.).

**Required interface** (`BaseChannel` ABC in `aifred/lib/plugin_base.py`):

```python
from aifred.lib.plugin_base import BaseChannel, CredentialField

class MyChannel(BaseChannel):
    # ── Identity (required) ──────────────────────────
    @property
    def name(self) -> str: return "my_channel"

    @property
    def display_name(self) -> str: return "My Channel"

    @property
    def icon(self) -> str: return "message-circle"  # Lucide icon name

    # ── Credentials (required) ───────────────────────
    @property
    def credential_fields(self) -> list[CredentialField]:
        return [
            CredentialField(env_key="MY_TOKEN", label_key="my_token_label", is_password=True),
        ]

    def is_configured(self) -> bool:
        from aifred.lib.config import MY_CHANNEL_TOKEN
        return bool(MY_CHANNEL_TOKEN)

    def apply_credentials(self, values: dict[str, str]) -> None:
        import os
        from aifred.lib import config
        os.environ["MY_TOKEN"] = values.get("MY_TOKEN", "")
        config.MY_CHANNEL_TOKEN = values["MY_TOKEN"]

    # ── Listener (required) ──────────────────────────
    async def listener_loop(self) -> None:
        """Long-running loop. Handle CancelledError for clean shutdown."""
        ...

    # ── Reply (required) ─────────────────────────────
    async def send_reply(self, outbound, original) -> None:
        """Send a reply to an incoming message."""
        ...

    # ── Context (required) ───────────────────────────
    def build_context(self, message) -> str:
        """Build LLM prompt context. Use prompts/ files, not hardcoded text."""
        from aifred.lib.prompt_loader import load_prompt
        return load_prompt("shared/channel_my_channel", sender=message.sender, text=message.text)

    # ── Optional ─────────────────────────────────────
    def build_reply_metadata(self, message) -> dict:
        """Channel-specific reply metadata (e.g. email In-Reply-To headers)."""
        return {}

    def get_tools(self, ctx) -> list:
        """Optional: Tools this channel provides (e.g. discord_send)."""
        return []

# Module-level instance (discovered by registry)
MyChannel_instance = MyChannel()
```

**Key points:**
- File goes in `aifred/plugins/channels/`
- Must expose a module-level `BaseChannel` instance
- `listener_loop()` must run indefinitely and handle `asyncio.CancelledError`
- `build_context()` should load prompts from `prompts/` directory
- `credential_fields` defines the Settings UI form (rendered dynamically)
- `get_tools()` is optional — for active sending (e.g. `discord_send`)

## Debug Messages

Use the centralized Debug Bus. Works in all contexts (browser, hub, standalone):

```python
from aifred.lib.debug_bus import debug

debug("🔍 Searching...")
debug("✅ Found 5 results")
```

Messages automatically go to:
- Log file (`data/logs/aifred_debug.log`) — always
- Browser debug console — if browser session is active
- Session file — if `session_scope` is active (Hub path)

## i18n

All user-facing text should use the i18n system:

```python
from aifred.lib.i18n import t
label = t("my_plugin_label", lang=ctx.lang)
```

Add keys to both language dicts in `aifred/lib/i18n.py`.
Prompt templates go in `prompts/de/` and `prompts/en/`.

## Enabling / Disabling

Plugins can be toggled via the Plugin Manager UI (Settings → Message Hub → gear icon). Disabling moves the file to `aifred/plugins/disabled/`. Re-enabling moves it back.

## File Structure

```
aifred/
├── lib/
│   ├── plugin_base.py      # Interfaces (BaseChannel, ToolPlugin, PluginContext)
│   ├── plugin_registry.py  # Discovery, enable/disable, list
│   ├── debug_bus.py         # debug(), session_scope, flush
│   └── function_calling.py  # Tool, ToolKit classes
└── plugins/
    ├── channels/
    │   ├── email.py         # IMAP/SMTP channel
    │   └── discord.py       # Discord bot channel
    ├── tools/
    │   ├── research.py      # web_search, web_fetch, calculate
    │   ├── email_tools.py   # email read/send/search
    │   ├── documents.py     # document search/list/delete
    │   ├── sandbox.py       # execute_code
    │   └── epim.py          # EPIM database CRUD
    └── disabled/            # Disabled plugins (moved here by UI toggle)
```
