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

### Echo Dot 2 Puck-Mod / Raumintercom

2x Echo Dot Gen 2 ("biscuit") bestellt (~15-18 EUR gesamt).
Hardware: MediaTek MT8163V (Cortex-A53 Quad 1.5GHz), 512MB RAM, 4GB eMMC,
7-Mikrofon-Array, TI TLV320DAC3203 Audio-Codec, Fire OS (Android 5.1).

#### Phase 1: Root + Alexa deaktivieren (Fire OS behalten!)
- [ ] Root via amonet-biscuit (persistent/untethered, Preloader-Patch in eMMC)
  - Geraet oeffnen, UART-Testpads kurzschliessen fuer Download-Modus
  - amonet Python-Script ausfuehren → Preloader patchen → TWRP flashen → Magisk
  - GitHub: k4y0z/amonet-biscuit
- [ ] OTA-Updates blockieren (DNS/hosts/iptables) — KRITISCH, sonst ueberschreibt Amazon
- [ ] Alexa-Services deaktivieren (pm disable):
  - com.amazon.dee.app (Alexa App)
  - com.amazon.avs (Alexa Voice Service)
  - com.amazon.device.sync (Cloud Sync)
  - com.amazon.ota.forced (OTA Updates)
- [ ] Termux installieren (ADB sideload) fuer Python-Umgebung

#### Phase 2: AIfred Puck-Client (Python auf Termux)
- [ ] openWakeWord fuer Wake Word Detection (laeuft lokal auf ARM Cortex-A53)
- [ ] Mikrofon-Zugriff ueber Android AudioRecord API (pyaudio/sounddevice)
- [ ] WebSocket-Client zum AIfred-Server (Mini)
- [ ] Nach Wake Word: Audio-Stream per WebSocket an AIfred senden
- [ ] TTS-Audio zurueck empfangen und ueber Lautsprecher abspielen
- [ ] LED-Ring ansteuern (Aufnahme=blau, Antwort=gruen, Fehler=rot)
- [ ] Open-Source Beamforming-Ersatz (webrtcvad + Delay-and-Sum)
  - Amazons proprietaeres Beamforming geht verloren wenn AVS deaktiviert wird
  - webrtcvad + einfaches Delay-and-Sum reicht fuer Raumgroessen bis ~4-5m

#### Phase 3: PuckChannel Plugin (AIfred-seitig)
- [ ] Neuer Channel-Plugin: PuckChannel (BaseChannel Pattern)
- [ ] WebSocket-Server, jeder Puck meldet sich mit Raum-Name an
- [ ] Audio empfangen → Whisper STT → Text
- [ ] Text → AIfred Engine (source="puck", Tier je nach Stimmerkennung)
- [ ] Antwort → Piper TTS → Audio-Stream zurueck an den aktiven Puck
- [ ] Audio Manager kennt alle Pucks und routet Audio zum richtigen Raum

#### Phase 4: Raum-Routing + Intercom + Notfall
- [ ] Aktiver Puck = Raum wo Wake Word gehoert wurde
- [ ] "AIfred, spiel in der Kueche" → Audio-Routing umschalten
- [ ] Intercom: "Sage meinem Sohn das Essen ist fertig" → Nachricht an anderen Puck
- [ ] Notfall-Wake-Word ("Alfred Hilfe") → Alarm-Sound auf ALLEN Pucks + Push-Notification
- [ ] Puck bei Eltern (untere Wohnung) als Notruf-Terminal

#### Phase 5: Stimmerkennung (optional, spaeter)
- [ ] Speaker Verification (pyannote-audio oder SpeechBrain)
- [ ] Stimm-Registrierung: 5 Sekunden Sprachprobe als Embedding speichern
- [ ] Automatische Sprecher-Erkennung nach Wake Word
- [ ] Rechte ableiten: Owner=Tier 4, Family=Tier 1, Unbekannt=Blocked

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

- [x] Layout-Shift beim Senden — Page scroll preservation via MutationObserver
- [x] Streaming-Absatzabstand — line_height 1.35 + double newline compression
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
