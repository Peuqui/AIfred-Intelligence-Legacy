# Scheduler Plugin

**Datei:** `aifred/plugins/tools/scheduler_tool.py`

Geplante Aufgaben und Cron-Jobs, die AIfred automatisch zu definierten Zeitpunkten ausführt.

## Tools

| Tool | Beschreibung | Tier |
|------|-------------|------|
| `scheduler_create` | Neuen geplanten Job anlegen | WRITE_DATA |
| `scheduler_list` | Alle geplanten Jobs auflisten | READONLY |
| `scheduler_delete` | Geplanten Job löschen | WRITE_SYSTEM |

## Features

- **Cron-Syntax:** Standard-Cron-Ausdrücke für flexible Zeitplanung
- **Isolierte Sessions:** Jeder Job läuft in eigener Session
- **Webhook-API:** Jobs können auch extern per HTTP ausgelöst werden
- **Auto-Restart:** Jobs überleben Neustarts des Services
