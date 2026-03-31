# Plugin-Übersicht

AIfred verwendet ein einheitliches Plugin-System. Plugins werden automatisch erkannt — eine `.py`-Datei in `plugins/tools/` oder `plugins/channels/` ablegen, fertig.

> **Entwickler-Guide:** [Plugin Development Guide (EN)](../../en/guides/plugin-development.md)
> **Security:** [Security-Architektur](../architecture/security.md)

---

## Tool Plugins

Tool Plugins stellen dem LLM Werkzeuge zur Verfügung, die es autonom aufrufen kann.

### Workspace (Dateien & Dokumente)

**Datei:** `plugins/tools/workspace.py`

Dateizugriff auf das Dokumenten-Verzeichnis (`data/documents/`) und semantische Suche über ChromaDB.

| Tool | Beschreibung | Tier |
|------|-------------|------|
| `list_files` | Dateien im Dokumenten-Ordner auflisten | READONLY |
| `read_file` | Datei lesen (PDFs seitenweise mit `pages="1-5"`) | READONLY |
| `write_file` | Textdatei schreiben/bearbeiten (mit Verify) | WRITE_DATA |
| `create_folder` | Unterordner anlegen | WRITE_DATA |
| `delete_file` | Datei von der Platte löschen | WRITE_SYSTEM |
| `delete_folder` | Leeren Ordner löschen | WRITE_SYSTEM |
| `index_document` | Datei in ChromaDB-Vektordatenbank einspeisen | WRITE_DATA |
| `search_documents` | Indexierte Dokumente semantisch durchsuchen | READONLY |
| `list_indexed` | Alle indexierten Dokumente anzeigen | READONLY |
| `delete_document` | Dokument aus Vektordatenbank entfernen | WRITE_SYSTEM |

**Features:**
- PDF-Lesen seitenweise (`pages="3,7,10-12"`)
- Path-Traversal-Schutz (nur `data/documents/`)
- Write-Verify: Geschriebene Dateien werden nach Schreiben zurückgelesen und verglichen
- Schreiben nur für Textformate (.txt, .md, .csv, .json, .xml, .html)

---

### EPIM (Persönliche Datenbank)

**Datei:** `plugins/tools/epim/`

Vollzugriff auf die [EssentialPIM](https://www.essentialpim.com/) Firebird-Datenbank — Termine, Kontakte, Notizen, Todos, Passwörter.

| Tool | Beschreibung | Tier |
|------|-------------|------|
| `epim_search` | Einträge suchen (Kalender, Kontakte, Notizen, Todos, Passwörter) | READONLY |
| `epim_create` | Neuen Eintrag anlegen | WRITE_DATA |
| `epim_update` | Eintrag ändern/verschieben | WRITE_DATA |
| `epim_delete` | Eintrag löschen | WRITE_SYSTEM |

**Features:**
- Automatische Name-zu-ID-Auflösung
- 7-Tage-Datumsreferenz im Prompt
- Anti-Halluzinations-Guardrails
- Field-Mapping (Englisch → Deutsch)

---

### Web Research

**Datei:** `plugins/tools/research.py`

Automatische Web-Recherche mit mehreren Such-APIs und semantischem Cache.

| Tool | Beschreibung | Tier |
|------|-------------|------|
| `web_search` | Web-Suche über Brave, Tavily oder SearXNG | READONLY |
| `web_fetch` | URL-Inhalt abrufen und extrahieren | READONLY |

**Features:**
- Multi-API mit automatischem Fallback
- Scraping und Ranking der Ergebnisse
- Semantischer Vector-Cache via ChromaDB (vermeidet Doppel-Suchen)

---

### Sandbox (Code-Ausführung)

**Datei:** `plugins/tools/sandbox.py`

Isolierte Python-Code-Ausführung in Subprocess.

| Tool | Beschreibung | Tier |
|------|-------------|------|
| `execute_code` | Python-Code ausführen (numpy, pandas, matplotlib, plotly, etc.) | WRITE_DATA |

**Features:**
- Isolierter Subprocess
- Unterstützt interaktive HTML/JS-Visualisierungen
- Timeout-Schutz

---

### Calculator

**Datei:** `plugins/tools/calculator.py`

Mathematische Berechnungen.

| Tool | Beschreibung | Tier |
|------|-------------|------|
| `calculate` | Mathematische Ausdrücke berechnen | READONLY |

---

### Audio Player

**Datei:** `plugins/tools/audio_player.py`

Audio-Wiedergabe auf dem Server.

| Tool | Beschreibung | Tier |
|------|-------------|------|
| `audio_play` | Audio-Datei abspielen (WAV, MP3) | WRITE_DATA |
| `audio_stop` | Wiedergabe stoppen | WRITE_DATA |
| `audio_status` | Wiedergabe-Status abfragen | READONLY |

---

### Scheduler

**Datei:** `plugins/tools/scheduler_tool.py`

Geplante Aufgaben (Cron-Jobs) für AIfred.

| Tool | Beschreibung | Tier |
|------|-------------|------|
| `create_job` | Zeitgesteuerten Job anlegen (einmalig oder wiederkehrend) | WRITE_DATA |
| `list_jobs` | Alle geplanten Jobs auflisten | READONLY |
| `delete_job` | Job löschen | WRITE_DATA |

**Features:**
- Cron-Syntax für wiederkehrende Jobs
- Isolierte Sessions pro Job
- Webhook-API für externe Trigger

---

## Channel Plugins

Channel Plugins verbinden AIfred mit externen Kommunikationskanälen. Eingehende Nachrichten werden automatisch verarbeitet und optional beantwortet.

### Email

**Datei:** `plugins/channels/email_channel/`

IMAP IDLE Push-basierter E-Mail-Monitor mit SMTP Auto-Reply.

**Features:**
- IMAP IDLE (Push, kein Polling)
- Ordner-Management (verschieben, erstellen, auflisten)
- Markieren (gelesen/ungelesen/markiert)
- Auto-Reply pro Kanal konfigurierbar

---

### Discord

**Datei:** `plugins/channels/discord.py`

Discord Bot mit Channel- und DM-Support.

**Features:**
- WebSocket/Gateway-Verbindung
- `/clear` Slash Command
- Kanal- und DM-Nachrichten

---

### Telegram

**Datei:** `plugins/channels/telegram_channel/`

Telegram Bot via Long Polling.

**Features:**
- Whitelist-basierter Zugang
- Auto-Reply konfigurierbar
- Setup-Guide: [Telegram Setup](telegram-setup.md)

---

## Plugin-Architektur

```
aifred/plugins/
├── tools/                  # Tool Plugins (LLM-Werkzeuge)
│   ├── workspace.py        # Dateien & ChromaDB
│   ├── research.py         # Web-Recherche
│   ├── sandbox.py          # Code-Ausführung
│   ├── calculator.py       # Mathematik
│   ├── audio_player.py     # Audio-Wiedergabe
│   ├── scheduler_tool.py   # Geplante Aufgaben
│   └── epim/               # EPIM-Datenbank
│       ├── tools.py
│       └── db.py
└── channels/               # Channel Plugins (Kommunikation)
    ├── email_channel/      # E-Mail (IMAP/SMTP)
    ├── discord.py          # Discord Bot
    └── telegram_channel/   # Telegram Bot
```

**Auto-Discovery:** Jede `.py`-Datei mit einem `plugin`-Attribut (Tool) oder einer `BaseChannel`-Subklasse (Channel) wird automatisch erkannt. Kein Registrieren nötig.

**Security Tiers:**

| Tier | Stufe | Beispiele |
|------|-------|-----------|
| 0 | READONLY | Suchen, Lesen, Auflisten |
| 1 | COMMUNICATE | E-Mail senden, Discord-Nachricht |
| 2 | WRITE_DATA | Erstellen, Ändern, Code ausführen |
| 3 | WRITE_SYSTEM | Löschen, System-Operationen |
| 4 | ADMIN | Shell-Zugriff (nicht implementiert) |

**Plugin Manager:** Plugins können zur Laufzeit über das UI-Modal aktiviert/deaktiviert werden (verschiebt Dateien nach `disabled/`).
