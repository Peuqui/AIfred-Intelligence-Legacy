# Web Research Plugin

**Datei:** `aifred/plugins/tools/research.py`

Multi-API Websuche mit automatischem Scraping und semantischem Caching.

## Tools

| Tool | Beschreibung | Tier |
|------|-------------|------|
| `web_search` | Web-Suche über konfigurierte Such-API | READONLY |
| `web_fetch` | URL abrufen und Inhalt extrahieren | READONLY |

## Features

- **Multi-API:** Brave Search, Tavily, SearXNG — konfigurierbar per Backend
- **Automatisches Scraping + Ranking:** Suchergebnisse werden abgerufen und nach Relevanz sortiert
- **Semantischer Vector-Cache:** Ergebnisse werden in ChromaDB gecacht, wiederholte Anfragen nutzen den Cache
- **Content-Extraktion:** HTML wird zu lesbarem Text konvertiert

## Konfiguration

- Such-API wird über `.env` konfiguriert (API-Keys für Brave/Tavily)
- SearXNG als selbst-gehostete Alternative ohne API-Key
- ChromaDB-Collection `research_cache` für den Vector-Cache
