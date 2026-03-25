# Implementierungsplan: Neue Tools für AIfred

## Architektur-Überblick

Alle neuen Tools folgen dem gleichen Muster:
1. Neue `*_tools.py` in `aifred/lib/` mit `get_*_tools()` Funktion
2. Einhängen in `prepare_agent_toolkit()` in `agent_memory.py`
3. Config-Werte in `config.py`
4. Tool-Beschreibungen in `prompts/shared/`

Zentraler Integrationspunkt: `prepare_agent_toolkit()` → baut ToolKit für LLM zusammen.

### Bereits implementiert
- **Feature 1: Code-Ausführung (Sandbox)** — ✅ v2.63.0
  - `execute_code` Tool, subprocess mit RLIMIT, matplotlib/plotly/pandas
  - Interactive HTML/JS als iframe im Chat, statische Plots als Images
  - Session-scoped Output, Cleanup bei Chat-Löschen, Chat-Export-Embedding

---

## Feature 2: Datei-Upload & Analyse

### Neue Dateien

**`aifred/lib/document_parser.py`** (~150 LOC)
- `async def parse_document(file_path: Path) -> ParsedDocument`
- PDF via `fitz` (PyMuPDF, bereits vorhanden)
- CSV via `csv` (stdlib)
- Excel via `openpyxl`
- Gescannte PDFs → Vision-Pipeline delegieren

**`aifred/lib/document_store.py`** (~150 LOC)
- ChromaDB-Collection `aifred_documents` (getrennt vom Research-Cache)
- Chunking: ~500-Token-Chunks mit Overlap
- Embeddings via Ollama (wie `vector_cache.py`)
- `index_document()`, `query_documents()`, `list_documents()`, `delete_document()`

**`aifred/lib/document_tools.py`** (~100 LOC)
- Tool `search_documents`: Sucht in persönlicher Wissensbasis
- Tool `list_documents`: Listet hochgeladene Dokumente

**`aifred/state/_document_mixin.py`** (~120 LOC)
- Upload-Handler für Reflex UI
- Progress-Tracking

### Änderungen

**`config.py`**
- `DOCUMENTS_DIR = DATA_DIR / "documents"`
- `DOCUMENT_CHUNK_SIZE = 500`
- `DOCUMENT_CHUNK_OVERLAP = 50`
- `DOCUMENT_MAX_FILE_SIZE_MB = 50`

**`aifred/state/_base.py`** → DocumentMixin einhängen

**`aifred/ui/input_sections.py`** → Upload-Widget (`.pdf, .csv, .xlsx, .txt, .md`)

**`agent_memory.py`** → `prepare_agent_toolkit()`

### Dependencies
- `openpyxl` (neu, für Excel)

### Schritte
1. Config-Werte definieren
2. `document_parser.py`: PDF/CSV/Excel Parser
3. `document_store.py`: ChromaDB Indexierung + Chunking
4. `document_tools.py`: Tool-Definitionen
5. `_document_mixin.py`: State-Mixin mit Upload-Handler
6. AIState erweitern, UI Upload-Widget
7. `prepare_agent_toolkit()` erweitern
8. Testen: PDF hochladen → Frage stellen → Antwort aus Dokument

---

## Feature 3: Kalender & ePIM Integration

### Vorarbeit: Reverse-Engineering der Firebird DB
- .epim Datei = Firebird-Datenbank
- Script: Alle Tabellen via `RDB$RELATIONS`, Spalten via `RDB$RELATION_FIELDS`
- Schema dokumentieren in `docs/epim_schema.md`
- Daten-Samples prüfen (Datumsformate, Encoding)

### Neue Dateien

**`aifred/lib/epim_client.py`** (~180 LOC)
- `class EPIMClient:` mit read-only Firebird Connection
- `get_appointments(date_from, date_to) -> list[Appointment]`
- `get_contacts(search: str) -> list[Contact]`
- `get_tasks(filter: str) -> list[Task]`
- `search(query: str) -> list[SearchResult]`
- Caching (5 Min TTL, NAS-Zugriff kann langsam sein)

**`aifred/lib/epim_tools.py`** (~120 LOC)
- Tool `calendar_today`: Tagesübersicht
- Tool `calendar_search`: Termine/Kontakte/Aufgaben suchen
- Tool `calendar_upcoming`: Nächste N Termine
- Executors: `asyncio.to_thread()` (Firebird-Driver ist synchron)

**`docs/epim_schema.md`** → Reverse-Engineered DB-Schema

### Änderungen

**`config.py`**
- `EPIM_DB_PATH = ""` (User setzt Pfad in Settings)
- `EPIM_ENABLED = False`
- `EPIM_CACHE_TTL_SECONDS = 300`

**`agent_memory.py`** → `prepare_agent_toolkit()` (nur wenn `epim_enabled`)

### Dependencies
- `firebird-driver>=1.10.0` (neu)
- `apt install firebird-dev` (Firebird Client Library)

### Besonderheiten
- Read-only: `read_only=True` bei Connection
- .epim liegt auf NAS (SMB-Mount) → Latenz + Verfügbarkeit beachten
- Testen ob Lesen möglich während ePIM auf Windows offen ist

### Schritte
1. `firebird-driver` installieren + Firebird Client Lib
2. **Reverse-Engineering**: DB-Schema auslesen und dokumentieren
3. Config-Werte definieren
4. `epim_client.py`: DB-Client
5. `epim_tools.py`: Tool-Definitionen
6. Settings-UI: ePIM-Pfad konfigurierbar
7. `prepare_agent_toolkit()` erweitern
8. Testen: "Was steht heute an?", "Nächster Termin mit X?"

---

## Feature 4: E-Mail (IMAP/SMTP)

### Funktionen
- `email_check` — Neue E-Mails abrufen (IMAP), Betreff/Absender/Preview anzeigen
- `email_read` — Volltext einer E-Mail lesen (inkl. Anhänge als Text/Zusammenfassung)
- `email_send` — E-Mail senden (SMTP), mit Bestätigungsabfrage vor dem Senden
- `email_reply` — Auf eine E-Mail antworten (Quote des Originals)
- `email_search` — E-Mails durchsuchen (IMAP SEARCH)

### Architektur
- **`aifred/lib/email_client.py`** (~200 LOC)
  - `class EmailClient:` mit IMAP + SMTP
  - `async def check_inbox(n: int) -> list[EmailSummary]`
  - `async def read_email(msg_id: str) -> EmailMessage`
  - `async def send_email(to, subject, body, reply_to?) -> bool`
  - `async def search_emails(query: str) -> list[EmailSummary]`
  - Connection-Pooling, TLS/SSL

- **`aifred/lib/email_tools.py`** (~120 LOC)
  - Tools für LLM Function Calling
  - Sicherheit: `email_send` erfordert Bestätigung (Tool gibt Preview zurück, User muss bestätigen)

### Config
- `EMAIL_IMAP_HOST`, `EMAIL_IMAP_PORT`, `EMAIL_IMAP_USER`, `EMAIL_IMAP_PASSWORD`
- `EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT`, `EMAIL_SMTP_USER`, `EMAIL_SMTP_PASSWORD`
- `EMAIL_ENABLED = False` (opt-in)
- Credentials via Environment-Variablen (nicht in settings.json!)

### Sicherheit
- **Senden nur mit Bestätigung** — LLM generiert Draft, User sieht Preview, bestätigt erst
- Kein automatisches Senden ohne User-Interaktion
- Credentials nur über Env-Vars, nie im UI exponiert

### Dependencies
- Keine neuen (stdlib: `imaplib`, `smtplib`, `email`)

---

## Feature 5: Messenger Integration (WhatsApp, Signal, Telegram, Discord)

### Optionen

**Option A: Telegram Bot (einfachster Einstieg)**
- Offizielles Bot-API, gut dokumentiert, kostenlos
- `python-telegram-bot` Library
- Bot empfängt Nachrichten → leitet an AIfred → antwortet
- Kann auch Bilder, Audio, Dokumente empfangen/senden
- Bidirektional: AIfred kann proaktiv Nachrichten senden

**Option B: Discord Bot**
- Offizielles Bot-API via `discord.py` Library
- Slash-Commands + Message-Handler
- Channels als Kontext (ein Channel = eine Konversation)
- Rich Embeds für formatierte Antworten, Bilder, Code-Blöcke
- Voice-Channel-Integration möglich (TTS/STT)
- Kostenlos, gut dokumentiert, große Community

**Option C: Signal (signal-cli)**
- `signal-cli` als Brücke (Java-basiert)
- REST-API via `signal-cli-rest-api` Docker Container
- End-to-End verschlüsselt
- Komplexeres Setup, aber datenschutzfreundlich

**Option D: WhatsApp (WhatsApp Business API)**
- Offizielles Business API (Meta) — erfordert Business-Konto + Verifizierung
- Oder: `whatsapp-web.js` (inoffiziell, fragil, kann jederzeit brechen)
- Hoher Setup-Aufwand, unzuverlässig bei inoffiziellen Lösungen

### Empfohlene Reihenfolge
1. **Telegram** — einfachstes Setup, offizielle API, sofort nutzbar
2. **Discord** — ähnlich einfach, gut für Multi-User/Community-Szenarien
3. **Signal** — nach Telegram, wenn signal-cli Docker läuft
4. **WhatsApp** — nur wenn wirklich benötigt (fragil)

### Architektur (am Beispiel Telegram)
- **`aifred/lib/telegram_bridge.py`** (~150 LOC)
  - Webhook oder Long-Polling empfängt Nachrichten
  - Leitet an AIfred's Chat-Pipeline weiter (wie API Message Injection)
  - Sendet Antwort zurück an Telegram
  - Unterstützt: Text, Bilder, Audio, Dokumente

- **`aifred/lib/messenger_tools.py`** (~100 LOC)
  - `send_telegram` — Nachricht an Telegram-Chat senden
  - `send_signal` — Nachricht an Signal senden
  - LLM kann proaktiv Nachrichten senden ("Erinnere mich um 18 Uhr via Telegram")

### Config
- `TELEGRAM_BOT_TOKEN` (Env-Var)
- `TELEGRAM_ALLOWED_USERS` (Whitelist von Telegram User-IDs)
- `SIGNAL_CLI_URL` (REST-API Endpoint)
- `SIGNAL_PHONE_NUMBER`

### Sicherheit
- **Whitelist** — nur autorisierte User können mit dem Bot interagieren
- **Rate Limiting** — max Nachrichten pro Minute
- **Kein automatisches Weiterleiten** von sensiblen Daten ohne Bestätigung

---

## Reihenfolge

```
Feature 1 (Sandbox)        → ✅ ERLEDIGT
Feature 2 (Dokumente)      → braucht UI-Arbeit, ChromaDB-Erweiterung
Feature 3 (Kalender/ePIM)  → nach erfolgreichem Reverse-Engineering
Feature 4 (E-Mail)         → stdlib, kein Setup nötig, schnell umsetzbar
Feature 5 (Messenger)      → Telegram zuerst, dann Signal
```
