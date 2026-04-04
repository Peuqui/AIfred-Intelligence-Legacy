# AIfred TODO

## Grundprinzip: Security im Framework, nicht in Plugins

Security wird im System-Code erzwungen (plugin_registry, function_calling,
message_processor). Plugins koennen die Sicherheitsmechanismen NICHT umgehen.

Pipeline: Inbound Sanitization → Tier-Check → Tool-Aufruf → Output-Sanitization → Audit-Log

---

## Audio-Player Plugin

- [ ] Live-Test im Browser (AIfred soll WAV abspielen)
- [ ] Integration mit Scheduler: Weckerton zu bestimmter Uhrzeit
- [ ] Netzwerk-Playback (PulseAudio remote oder eigener Audio-Server fuer Pucks)
- [ ] **Musik-Streaming an Puck** — eigener Streaming-Kanal (nicht ueber TTS-Protokoll),
  Playlisten, Pause/Skip/Resume, setzt Bluetooth-Speaker am Puck voraus

---

## FreeEcho.2 Puck — AIfred Voice Interface

Separates Projekt: github.com/Peuqui/FreeEcho.2
Firmware-TODOs dort in TODO.md, hier nur AIfred-seitige Punkte.

### Naechste Schritte (AIfred-Seite)
- [ ] Latenz-Optimierung: Kaltstart ~30s (Modell-Ladezeit), ~2.7s warm
- [ ] Memory-Injektion fuer alle Agenten untersuchen

### Plugin-System Refactoring (PRIORITAET)

**Ziel:** Jedes Plugin ist eine selbststaendige, portable Einheit. Ordner loeschen = alles weg,
keine Leichen in .env oder zentraler i18n.py.

**Ordnerstruktur pro Plugin:**
```
aifred/plugins/channels/freeecho2_channel/
    __init__.py          # Plugin-Code
    i18n.json            # Eigene Uebersetzungen (min. DE/EN)
    settings.json        # Persistierte Settings (Port, Engine etc.)
```

**Grenze .env vs settings.json:**
- **.env**: NUR echte Secrets (Passwoerter, API Keys, Tokens) + ENABLED-Flags
- **settings.json im Plugin-Ordner**: Alles andere (Ports, Engines, Stimmen, Thresholds)

**Konkret pro Plugin:**
- FreeEcho.2: Null .env-Eintraege (keine Secrets), alles in settings.json
- Email: IMAP/SMTP Passwort → .env, Rest (Server, Port, Allowed Senders) → settings.json
- Telegram: Bot Token → .env, Rest → settings.json
- Discord: Bot Token → .env, Rest → settings.json
- EPIM: Alles in settings.json (kein Secret)
- Translator: API Key → .env

**Umsetzungsschritte:**
- [ ] `CredentialField` um `is_secret: bool = False` erweitern
- [ ] Plugin-eigene `settings.json` lesen/schreiben (statt .env fuer non-secrets)
- [ ] `credential_broker` aus beiden Quellen lesen (.env fuer Secrets, settings.json fuer Config)
- [ ] **Plugin-eigenes i18n** — `i18n.json` im Plugin-Ordner, wird beim Laden des Plugins registriert
  - Zentrale i18n.py entschlanken: Plugin-spezifische Keys raus
  - Plugin liefert eigene Uebersetzungen (min. DE/EN)
- [ ] **Credential-Modal Label-Rendering fixen** — zeigt i18n Keys statt Klartext
- [ ] Modal-Titel nutzt display_name + i18n "Einstellungen"/"Settings"
- [ ] Migration: bestehende .env-Eintraege in settings.json ueberfuehren (einmalig)

### FreeEcho.2 Plugin
- [ ] TTS Voice Dropdown dynamisch (abhaengig von gewaehlter Engine, verfuegbare Stimmen auflisten)
- [ ] Plugin TTS Engine Wechsel: automatisches VRAM Management + Docker Container Start/Stop

---

## Security-Verfeinerung

### Guard-LLM (S8)
- [ ] Kleines Modell als Vorfilter (safe/suspicious/malicious)
- [ ] Bei suspicious: Tier runterstufen
- [ ] Bei malicious: Block + Audit-Log
- [ ] Konfigurierbar pro Channel

### Action Confirmation Verfeinerung
- [ ] Rueckfrage an Sender statt hartem Block (Telegram Inline Keyboards etc.)
- [ ] Review-Queue fuer Cron-Jobs
- [ ] Optional: PIN/zweiter Faktor

### Erweiterte Output-Sanitization
- [ ] Entropy-Detection: Hochentropie-Strings flaggen
- [ ] Pattern-Liste konfigurierbar/erweiterbar

### Information Flow Control (S10)
- [ ] Taint-Tracking: Labels propagieren durch alle Schritte
- [ ] Cross-Channel-Exfiltration verhindern
- [ ] Network Egress Control (Default-Deny)

### RAG/Vector-DB Haertung
- [ ] Untrusted-Channel-Daten bekommen niedrigen Trust-Score
- [ ] Periodisches Auditing/Purging des Vector-Cache
- [ ] Namespace-Isolation pro Channel/Sender

---

## Plugins (spaeter)

### Community & Forum Plugins
- [ ] Reddit Plugin: lesen, posten, kommentieren, Subreddit-Monitoring
- [ ] Hacker News Plugin: lesen, suchen (read-only)
- [ ] Discourse Plugin (optional)

### Neue Kanaele
- [ ] Signal Plugin (signal-cli-rest-api Docker)

### Neue Tool Plugins
- [ ] RSS/News Feed Plugin: Nachrichten-Quellen ueberwachen und zusammenfassen
- [ ] Home Assistant Plugin: Smart Home Geraete steuern (REST API)
- [ ] Kalender-Sync Plugin: Google Calendar / CalDAV (unabhaengig von EPIM)

### KI-gestuetzte Kalibrierung
- [ ] LLM-basierte Schaetzung der optimalen Kalibrierungsparameter (Proof of Concept abgeschlossen)
- [ ] Implementierung als Alternative zum Binary-Search-Algorithmus
- [ ] Cloud-API oder CPU-only Modell fuer Schaetzung (kein VRAM-Verbrauch)

---

### UI Verbesserungen
- [ ] Tages-Separatoren bei Datumswechsel in Chat (Messenger-Stil)
- [ ] Clickable Tooltips: Hilfe-Modale fuer alle UI-Bereiche (Agenten-Editor, etc.)

## Offene Verbesserungen

- [ ] Multi-Email-Konto Support (mehrere IMAP/SMTP Accounts, Rechte pro Konto)
- [ ] Kanaluebergreifendes Routing (eine Session ueber mehrere Kanaele — Telegram/Discord/Email/Browser)
- [ ] Research-Pipeline State-Abhaengigkeit weiter reduzieren
- [ ] Inbound-Sanitization Strictness pro Channel konfigurierbar
- [ ] Session Memory Sanitization nach Job-Ende
- [ ] Audit-Log UI Filter (Channel, Tool, Zeitraum)

---

## Backlog

- [ ] Structured Output / Data Extraction
- [ ] READMEs weiter refaktorieren
