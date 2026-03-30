# AIfred TODO

## Grundprinzip: Security im Framework, nicht in Plugins

Security wird im System-Code erzwungen (plugin_registry, function_calling,
message_processor). Plugins koennen die Sicherheitsmechanismen NICHT umgehen.

Pipeline: Inbound Sanitization → Tier-Check → Tool-Aufruf → Output-Sanitization → Audit-Log

---

## Uebergabe / Aktueller Stand (2026-03-29)

### Was heute gebaut und getestet wurde:
- Security Layer komplett (S1-S7, S9): Tier-System, Audit-Log, Sanitization,
  Credential Broker, Rate Limiting, Circuit Breaker, Action Confirmation
- Scheduler (P1-P5): Job Store, isolierte Sessions, Delivery Modes, Webhook-API, Auto-Restart
- Telegram Bot Plugin: Channel + Tools + Whitelist + Tests
- Scheduler Tool Plugin: create/list/delete via Chat
- Audit-Log UI + Allowlist UI
- Proaktiver Assistent: Prompt-Vorlagen fuer E-Mail-Summary, Kalender etc.
- Audio Manager + Audio Player Plugin (lib/audio_manager.py + plugins/tools/audio_player.py)
  - Haendisch getestet mit echtem WAV, funktioniert
  - Noch nicht im Browser live getestet (kein Lautsprecher am Mini)
- Email Plugin komplett: move, list_folders, create_folder, mark (read/unread/flagged)
- EPIM Fixes: Field-Mapping, ID-Strings, Encoding-Bug (Byte vs. Char-Laenge), Kontakt-Fields
- Scroll-Fixes: Reconnect, Page-Load, Streaming-Absatzabstand
- 110+ Unit Tests, umfangreiche Live-Tests via Chrome DevTools
- Docs: Security-Architektur (DE/EN), Scheduler (DE/EN), Telegram Setup, Plugin Guide
- Repo: Neues privates Repo, Legacy-Repo umbenannt, TODO.md aus History entfernt

### TTS pro Agent (implementiert 2026-03-30)

- [x] `tts_agent_voices` dynamisch fuer ALLE registrierten Agenten
- [x] Neuer Agent → automatisch Default-Voice-Eintrag
- [x] Agent loeschen → TTS-Eintrag entfernen
- [x] TTS-Config (Voice/Speed/Pitch/Enabled) im Agent-Editor Modal fuer alle Agenten
- [x] Settings vereinfacht: nur Engine-Dropdown + Autoplay + Streaming
- [x] Persistenz pro Engine in settings.json (tts_agent_voices_per_engine)
- [ ] Live-Test im Browser

### ECC-RAM deaktiviert (2026-03-29)
Alle 4 GPUs: ECC off → 120 GB VRAM (vorher 112.5 GB). ~8.5% schneller.
Befehl war: `sudo nvidia-smi -i 0,1,2,3 --ecc-config=0` + Reboot.

---

## Audio-Player Plugin

Code existiert bereits (lib/audio_manager.py + plugins/tools/audio_player.py).
Haendisch getestet, funktioniert mit aplay/ffplay.
Warten auf Pucks / Lautsprecher-Setup fuer Live-Test.

- [ ] Live-Test im Browser (AIfred soll WAV abspielen)
- [ ] Integration mit Scheduler: Weckerton zu bestimmter Uhrzeit
- [ ] Netzwerk-Playback (PulseAudio remote oder eigener Audio-Server fuer Pucks)

---

## Echo Dot 2 Puck-Mod / Raumintercom

2x Echo Dot Gen 2 ("biscuit") bestellt (~15-18 EUR gesamt).
Hardware: MediaTek MT8163V (Cortex-A53 Quad 1.5GHz), 512MB RAM, 4GB eMMC,
7-Mikrofon-Array, TI TLV320DAC3203 Audio-Codec, Fire OS (Android 5.1).

Architektur-Entscheidung: Fire OS behalten + rooten (NICHT postmarketOS).
Vorteil: Alle Hardware-Treiber (Mikrofon-Array, Audio-Codec, WiFi) bleiben erhalten.
Eigene Python-App auf Termux als Puck-Client.

#### Phase 1: Root + Alexa deaktivieren
- [ ] Root via amonet-biscuit (persistent/untethered, Preloader-Patch in eMMC)
  - Geraet oeffnen, UART-Testpads kurzschliessen fuer Download-Modus
  - amonet Python-Script → Preloader patchen → TWRP flashen → Magisk
  - GitHub: k4y0z/amonet-biscuit
- [ ] OTA-Updates blockieren (DNS/hosts/iptables) — KRITISCH
- [ ] Alexa-Services deaktivieren (pm disable):
  - com.amazon.dee.app, com.amazon.avs, com.amazon.device.sync, com.amazon.ota.forced
- [ ] Termux installieren (ADB sideload)

#### Phase 2: AIfred Puck-Client (Python auf Termux)
- [ ] openWakeWord fuer Wake Word Detection (lokal auf ARM Cortex-A53)
- [ ] Mikrofon-Zugriff ueber Android AudioRecord API (pyaudio/sounddevice)
- [ ] WebSocket-Client zum AIfred-Server
- [ ] Audio-Stream nach Wake Word senden, TTS-Audio zurueck abspielen
- [ ] LED-Ring ansteuern (blau=Aufnahme, gruen=Antwort, rot=Fehler)
- [ ] Open-Source Beamforming-Ersatz (webrtcvad + Delay-and-Sum, ~4-5m Reichweite)

#### Phase 3: PuckChannel Plugin (AIfred-seitig)
- [ ] Neuer Channel-Plugin: PuckChannel (BaseChannel Pattern)
- [ ] WebSocket-Server, Pucks melden sich mit Raum-Name an
- [ ] Audio → Whisper STT → AIfred Engine → Piper TTS → Audio zurueck
- [ ] Audio Manager routet zum richtigen Puck

#### Phase 4: Raum-Routing + Intercom + Notfall
- [ ] Aktiver Puck = Raum wo Wake Word gehoert wurde
- [ ] Audio-Routing umschalten ("AIfred, spiel in der Kueche")
- [ ] Intercom: "Sage meinem Sohn das Essen ist fertig" → anderer Puck
- [ ] Notfall-Wake-Word ("Alfred Hilfe") → Alarm auf ALLEN Pucks + Push

#### Phase 5: Stimmerkennung (spaeter)
- [ ] Speaker Verification (pyannote-audio oder SpeechBrain)
- [ ] Stimm-Registrierung → Embedding → automatische Sprecher-Erkennung
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

- [ ] Multi-Email-Konto Support (mehrere IMAP/SMTP Accounts, Rechte pro Konto)
- [ ] Kanaluebergreifendes Routing (eine Session ueber mehrere Kanaele)
- [ ] Research-Pipeline State-Abhaengigkeit weiter reduzieren
- [ ] Inbound-Sanitization Strictness pro Channel konfigurierbar
- [ ] Session Memory Sanitization nach Job-Ende
- [ ] Audit-Log UI Filter (Channel, Tool, Zeitraum)

---

## Backlog

- [ ] Structured Output / Data Extraction
- [ ] READMEs weiter refaktorieren
