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
- [x] Vision Modell als vollwertiger Agent: Tools, Memory, Personality des aktiven Agenten

### Plugin-System Refactoring

- [x] `CredentialField` um `is_secret: bool = False` erweitern
- [x] Plugin-eigene `settings.json` lesen/schreiben (statt .env fuer non-secrets)
- [x] Settings beim Boot in os.environ laden (load_settings_to_env)
- [x] Plugin-eigenes i18n — `i18n.json` im Plugin-Ordner
- [x] Zentrale i18n.py entschlankt: Channel-Plugin-Keys raus
- [x] Credential-Modal: Labels aus Plugin-i18n, Fallback auf zentrale i18n
- [x] Modal-Titel nutzt display_name + i18n "Einstellungen"/"Settings"
- [x] Migration: bestehende .env-Eintraege in settings.json (einmalig, automatisch)
- [x] Discord in discord_channel/ Ordner migriert (alle Plugins = Ordner)
- [x] TTS Engine Manager: Single Source of Truth fuer Engine-Lifecycle (VRAM, Container)
- [x] Tool-Plugins in Ordner-Struktur migriert (calculator, research, sandbox, etc.)

### FreeEcho.2 Plugin
- [ ] TTS Voice Dropdown dynamisch (abhaengig von gewaehlter Engine, verfuegbare Stimmen auflisten)
- [x] Plugin TTS Engine Wechsel: automatisches VRAM Management + Docker Container Start/Stop

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
