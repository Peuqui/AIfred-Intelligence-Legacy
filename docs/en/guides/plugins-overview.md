# Plugin Overview

AIfred uses a unified plugin system. Plugins are auto-discovered — drop a `.py` file into `plugins/tools/` or `plugins/channels/`, done.

> **Developer Guide:** [Plugin Development Guide](plugin-development.md)
> **Security:** [Security Architecture](../architecture/security.md)

---

## Tool Plugins

Tool Plugins provide tools the LLM can call autonomously during conversations.

### Workspace (Files & Documents)

**File:** `plugins/tools/workspace.py`

File access to the documents directory (`data/documents/`) and semantic search via ChromaDB.

| Tool | Description | Tier |
|------|------------|------|
| `list_files` | List files in the documents directory | READONLY |
| `read_file` | Read a file (PDFs page-by-page with `pages="1-5"`) | READONLY |
| `write_file` | Write/edit a text file (with verify) | WRITE_DATA |
| `create_folder` | Create a subfolder | WRITE_DATA |
| `delete_file` | Delete a file from disk | WRITE_SYSTEM |
| `delete_folder` | Delete an empty folder | WRITE_SYSTEM |
| `index_document` | Index a file into the ChromaDB vector database | WRITE_DATA |
| `search_documents` | Search indexed documents semantically | READONLY |
| `list_indexed` | List all indexed documents | READONLY |
| `delete_document` | Remove a document from the vector database | WRITE_SYSTEM |

**Features:**
- Page-by-page PDF reading (`pages="3,7,10-12"`)
- Path traversal protection (confined to `data/documents/`)
- Write verify: files are read back after writing and compared
- Writing restricted to text formats (.txt, .md, .csv, .json, .xml, .html)

---

### EPIM (Personal Database)

**File:** `plugins/tools/epim/`

Full CRUD access to the [EssentialPIM](https://www.essentialpim.com/) Firebird database — appointments, contacts, notes, todos, passwords.

| Tool | Description | Tier |
|------|------------|------|
| `epim_search` | Search entries (calendar, contacts, notes, todos, passwords) | READONLY |
| `epim_create` | Create a new entry | WRITE_DATA |
| `epim_update` | Update/move an entry | WRITE_DATA |
| `epim_delete` | Delete an entry | WRITE_SYSTEM |

**Features:**
- Automatic name-to-ID resolution
- 7-day date reference in prompt
- Anti-hallucination guardrails
- Field mapping (English to German)

---

### Web Research

**File:** `plugins/tools/research.py`

Automatic web research with multiple search APIs and semantic cache.

| Tool | Description | Tier |
|------|------------|------|
| `web_search` | Web search via Brave, Tavily or SearXNG | READONLY |
| `web_fetch` | Fetch and extract URL content | READONLY |

**Features:**
- Multi-API with automatic fallback
- Result scraping and ranking
- Semantic vector cache via ChromaDB

---

### Sandbox (Code Execution)

**File:** `plugins/tools/sandbox.py`

Isolated Python code execution in subprocess.

| Tool | Description | Tier |
|------|------------|------|
| `execute_code` | Run Python code (numpy, pandas, matplotlib, plotly, etc.) | WRITE_DATA |

---

### Calculator

**File:** `plugins/tools/calculator.py`

| Tool | Description | Tier |
|------|------------|------|
| `calculate` | Evaluate mathematical expressions | READONLY |

---

### Audio Player

**File:** `plugins/tools/audio_player.py`

| Tool | Description | Tier |
|------|------------|------|
| `audio_play` | Play audio file (WAV, MP3) | WRITE_DATA |
| `audio_stop` | Stop playback | WRITE_DATA |
| `audio_status` | Query playback status | READONLY |

---

### Scheduler

**File:** `plugins/tools/scheduler_tool.py`

Scheduled tasks (cron jobs) for AIfred.

| Tool | Description | Tier |
|------|------------|------|
| `create_job` | Create a scheduled job (one-time or recurring) | WRITE_DATA |
| `list_jobs` | List all scheduled jobs | READONLY |
| `delete_job` | Delete a job | WRITE_DATA |

**Features:**
- Cron syntax for recurring jobs
- Isolated sessions per job
- Webhook API for external triggers

---

## Channel Plugins

Channel Plugins connect AIfred to external communication channels. Incoming messages are processed automatically with optional auto-reply.

### Email

**File:** `plugins/channels/email_channel/`

IMAP IDLE push-based email monitor with SMTP auto-reply.

**Features:**
- IMAP IDLE (push, no polling)
- Folder management (move, create, list)
- Flag management (read/unread/flagged)
- Auto-reply configurable per channel

---

### Discord

**File:** `plugins/channels/discord.py`

Discord bot with channel and DM support.

**Features:**
- WebSocket/Gateway connection
- `/clear` slash command
- Channel and DM messages

---

### Telegram

**File:** `plugins/channels/telegram_channel/`

Telegram bot via long polling.

**Features:**
- Whitelist-based access
- Auto-reply configurable
- Setup guide: [Telegram Setup](telegram-setup.md)

---

## Plugin Architecture

```
aifred/plugins/
├── tools/                  # Tool Plugins (LLM tools)
│   ├── workspace.py        # Files & ChromaDB
│   ├── research.py         # Web research
│   ├── sandbox.py          # Code execution
│   ├── calculator.py       # Math
│   ├── audio_player.py     # Audio playback
│   ├── scheduler_tool.py   # Scheduled tasks
│   └── epim/               # EPIM database
│       ├── tools.py
│       └── db.py
└── channels/               # Channel Plugins (communication)
    ├── email_channel/      # Email (IMAP/SMTP)
    ├── discord.py          # Discord bot
    └── telegram_channel/   # Telegram bot
```

**Auto-Discovery:** Any `.py` file with a `plugin` attribute (Tool) or `BaseChannel` subclass (Channel) is auto-discovered. No registration needed.

**Security Tiers:**

| Tier | Level | Examples |
|------|-------|---------|
| 0 | READONLY | Search, read, list |
| 1 | COMMUNICATE | Send email, Discord message |
| 2 | WRITE_DATA | Create, update, execute code |
| 3 | WRITE_SYSTEM | Delete, system operations |
| 4 | ADMIN | Shell access (not implemented) |

**Plugin Manager:** Plugins can be enabled/disabled at runtime via the UI modal (moves files to `disabled/`).
