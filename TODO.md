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

---

## FreeEcho.2 Puck — AIfred Voice Interface

Separates Projekt: github.com/Peuqui/FreeEcho.2
Code und Dokumentation dort, NICHT in diesem Repo.

### Erledigt (2026-04-03)
- [x] Mel-Spectrogram Fix (Slaney scale, matcht ONNX mit 0.07 dB)
- [x] Wake Word Detection funktioniert ("Hey Jarvis", 0.93 prob)
- [x] WebSocket Client + Server (Handshake-Protokoll mit Heartbeat)
- [x] FreeEcho.2 Channel Plugin in AIfred (STT → LLM → TTS Pipeline)
- [x] End-to-End Audio: Wake Word → Aufnahme → STT → LLM → TTS → Playback
- [x] 3 unabhängige Prozesse (LED-Daemon, Client, Watchdog)
- [x] Auto-Boot + Auto-Reconnect
- [x] LED Farben konfigurierbar (Idle, Listening, Processing, Speaking, Error, Muted)
- [x] Asymmetrischer Error-Puls (2:1 Duty Cycle)
- [x] ko-fi Links in READMEs

### Naechste Schritte
- [ ] Latenz-Optimierung: Intent-Detection dauert ~30s beim Kaltstart (Modell-Ladezeit)
- [ ] LED-Animationen erweitern (fire, sparkle, dual_spin, vumeter — Plan + Doku fertig)
- [ ] Custom Wake Words trainieren ("Hallo Alfred", "Hallo Sokrates" etc.)
- [ ] FreeEcho.2 Initial Git Commit (Repo existiert, leer)
- [ ] Timing-Debug-Prints aus message_processor.py entfernen
- [x] TTS Dropdown in Plugin-Settings (Engine-Auswahl als Dropdown)
- [x] TTS ueber generate_tts() Single Source of Truth (gleicher Pfad wie Browser)
- [x] Agenten-spezifische TTS-Stimmen aus TTS_AGENT_VOICE_DEFAULTS (pro Engine + Agent)
- [x] WebSocket Handshake-Protokoll mit Heartbeat + done/audio_start/error
- [x] Action-Button Abbruch waehrend Processing
- [x] Ping im Idle (alle 10s) + Heartbeat-Check in Processing (30s Timeout)

### Plugin-System Refactoring (PRIORITAET)
- [ ] Plugin-Settings in eigene JSON pro Plugin (`data/settings/<plugin>.json`) statt .env
  - .env Aenderungen triggern Hot-Reload! Das muss raus.
  - Secrets (API Keys, Tokens) koennen in .env bleiben
  - Config (Port, Engine, Stimme) gehoert in Plugin-JSON
- [ ] Plugin-eigenes i18n System (Uebersetzungen im Plugin, nicht zentrale i18n.py)
- [ ] Credential-Modal Label-Rendering fixen (zeigt i18n Keys statt Klartext)
- [ ] Allowlist-Anzeige: nur fuer Channels die eine brauchen (aktuell noch bei FreeEcho.2 sichtbar)
- [ ] Modal-Titel nutzt display_name + i18n "Einstellungen"/"Settings"

### FreeEcho.2 Plugin
- [ ] TTS Voice Dropdown dynamisch (abhaengig von gewaehlter Engine, verfuegbare Stimmen auflisten)
- [ ] Plugin TTS Engine Wechsel: automatisches VRAM Management + Docker Container Start/Stop
- [ ] Edge TTS Speed-Parameter korrekt uebergeben (aktuell wird speed als float statt "+25%" Format gesendet)

### FreeEcho.2 Hardware/Firmware
- [ ] Latenz-Optimierung: Intent-Detection ~30s beim Kaltstart (Modell-Ladezeit), ~2.7s warm
- [ ] Timing-Debug-Prints aus message_processor.py entfernen (print → nur bei Bedarf)
- [ ] LED-Animationen erweitern (fire, sparkle, dual_spin, vumeter — Plan in plans/ + Doku fertig)
- [ ] LED-Daemon CPU-Optimierung (solid Pattern schlaeft jetzt, aber pruefen ob es greift)
- [ ] Custom Wake Words trainieren ("Hallo Alfred", "Hallo Sokrates" etc.)
- [ ] FreeEcho.2 Initial Git Commit (Repo existiert, leer)
- [ ] 3.5mm Audio Jack (PMIC DAC Initialisierung ohne Android Framework — GPIO hpspk nicht bestückt)
- [ ] Bluetooth Speaker Support (BT-Stack ohne Android Framework testen)
- [ ] Speaking-LED Farbe: EE2200 (Orange) statt FF8000 (Gelb) — Config deployed, verifizieren
- [ ] Sprachsteuerung: Agenten wechseln, Modi umschalten per Voice
- [ ] Verschiedene Wake Words fuer verschiedene Agenten
- [ ] Raum-Routing + Intercom zwischen Pucks
- [ ] Stimmerkennung (Speaker Verification)
- [ ] AP-Modus / Pairing fuer Enduser-Setup
- [ ] Agenten-Begruessungs-WAVs (Voice Cloning: "Jawohl Sir", "Ja mein Sohn" etc.)

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
