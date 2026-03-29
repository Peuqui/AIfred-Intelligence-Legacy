# AIfred TODO

## Grundprinzip: Security im Framework, nicht in Plugins

Security wird im System-Code erzwungen (plugin_registry, function_calling,
message_processor). Plugins koennen die Sicherheitsmechanismen NICHT umgehen.

Pipeline: Inbound Sanitization → Tier-Check → Tool-Aufruf → Output-Sanitization → Audit-Log

---

## Naechste Schritte

### Audio-Player Plugin (Tool Plugin)
- [ ] Audiodateien abspielen auf dem lokalen System (aplay, mpv, etc.)
- [ ] Sandbox kann WAV generieren → Audio-Player spielt ab
- [ ] Integration mit Scheduler: Weckerton zu bestimmter Zeit abspielen
- [ ] Tier: TIER_WRITE_DATA (Systemzugriff fuer Audio-Output)

### TTS pro Agent (Stimmen-Zuordnung)
- [ ] Jeder Agent bekommt eigene TTS-Stimme (konfigurierbar)
- [ ] Generisch fuer unlimitierte Anzahl von Agenten
- [ ] Pro Agent: TTS-Backend + Voice-Name/ID speichern
- [ ] Voice-Cloning: User kann eigene Stimmen hochladen und Agenten zuweisen
- [ ] Vordefinierte Stimmen aus dem TTS-Paket als Default
- [ ] Persistenz in agent_config oder settings.json

### Wake Word / Keyword Detection
- [ ] Keyword-Erkennung: "Hallo AIfred" oder "Hey Alfred" aktiviert Aufnahme
- [ ] Lokales Wake-Word-Modell (z.B. openWakeWord, Porcupine, Snowboy)
- [ ] Laeuft als Background-Worker (wie Channel-Listener)
- [ ] Nach Aktivierung: Aufnahme → STT → AIfred Engine → TTS → Wiedergabe
- [ ] Konfigurierbar: Wake Word, Empfindlichkeit, Timeout

### Alexa-Puck Mod / Raumintercom
- [ ] Alexa-Hardware (Echo Dot Gen 1/2) als Audio-Terminal nutzen
- [ ] Alexa-Software entfernen, eigene Firmware/Client drauf
- [ ] Kommunikation via MQTT oder WebSocket zum AIfred-Server
- [ ] Mikrofon → Wake Word → STT → AIfred → TTS → Lautsprecher
- [ ] Mehrere Pucks im Haus = AIfred ueberall per Sprache erreichbar

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

---

## Offene Verbesserungen

- [ ] Layout-Shift beim Senden (User-Bubble einfuegen verschiebt Viewport ~5-10mm)
- [ ] Streaming-Absatzabstand zu gross (fast 2 Zeilen, sollte 1.5 sein → weniger Sprung beim Rendern)
- [ ] Multi-Email-Konto Support (mehrere IMAP/SMTP Accounts, Rechte pro Konto: read/write/delete)
- [ ] EPIM Kontakt-Erstellung: Telefon/E-Mail Fields korrekt mappen
- [ ] Kanaluebergreifendes Routing (eine Session ueber mehrere Kanaele)
- [ ] Research-Pipeline State-Abhaengigkeit weiter reduzieren
- [ ] Inbound-Sanitization Strictness pro Channel konfigurierbar
- [ ] Session Memory Sanitization nach Job-Ende
- [ ] Audit-Log UI Filter (Channel, Tool, Zeitraum)

---

## Promotion & Community

- [ ] Geeignetes Forum/Community fuer AIfred finden (nicht Reddit)
- [ ] Hacker News Show HN Post evaluieren
- [ ] Deutsche AI/Tech-Foren recherchieren

---

## Backlog

- [ ] Structured Output / Data Extraction
- [ ] READMEs weiter refaktorieren
