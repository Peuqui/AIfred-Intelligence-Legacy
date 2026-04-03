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

## Echo Dot 2 Puck-Mod / Raumintercom (FreeEchoDot2)

2x Echo Dot Gen 2 ("biscuit") bestellt (~15-18 EUR gesamt).
Hardware: MediaTek MT8163V (Cortex-A53 Quad 1.5GHz), 512MB RAM, 4GB eMMC,
7-Mikrofon-Array, TI TLV320AIC3101 Audio-Codecs, Fire OS (Android 5.1).
GitHub-Projekt: github.com/Peuqui/FreeEcho.2 (noch nicht gepusht)

#### Phase 1: Root + Alexa deaktivieren
- [x] Root via amonet-biscuit (persistent/untethered, Preloader-Patch in eMMC)
- [x] OTA-Updates blockieren (f1r30s.zip, hosts-Datei gepatcht)
- [x] ADB-Zugang hergestellt (Device: G090LF1072270LT0)
- [x] SELinux auf Permissive (Boot-Image cmdline Patch, funktioniert)
- [x] WiFi manuell funktioniert (conn_launcher war disabled, jetzt geloest!)
- [x] WiFi Auto-Boot (Ramdisk gepatcht: conn_launcher aktiviert, Boot-Script deployed)
- [x] LED Ring steuerbar (IS31FL3236, led_ring Tool mit color/spin/pulse/progress)
- [x] Speaker Playback funktioniert (TLV320AIC3204, Device 23, tinyplay)
- [ ] Alexa-Services deaktivieren / unnoetige Prozesse stoppen
- [ ] Zygote/system_server: NICHT NOETIG fuer WiFi! Optional fuer andere Android-Features

#### Phase 1.5: Audio-Kette — FUNKTIONIERT!

**Audio-Kette vollstaendig analysiert und funktionsfaehig (2026-04-02):**
```
Mikrofone (7+1) → 4x TLV320AIC3101 (I2C 0x18-0x1B) → I2S/TDM → FPGA (R3018, SPI) → CPU
```

Der FPGA ("dough") sitzt ZWISCHEN ADCs und SoC. Daten gehen ueber SPI,
NICHT ueber den MediaTek AFE. Deshalb liefern Device 13 und alle
AFE-Devices nur Nullen — die sind am falschen Bus.

| Device | Name | Datenquelle | Funktioniert? |
|--------|------|-------------|---------------|
| 13 | TDM_Debug_CAPTURE | MT8163 interner ADDA ADC | NEIN (falsche Quelle) |
| 16 | I2S0_AWB_CAPTURE | I2S0 Pin-Input | NEIN (FPGA nicht an I2S0) |
| 24 | AMZN_SPI_Capture | SPI → FPGA → TLV320 ADCs | JA (einzig richtiger Pfad) |

**Device 24 ist der einzige Weg.** Format: S24_3LE, 9ch, 16kHz.
Problem: `tinycap` kann S24_3LE nicht oeffnen.

**Was bestaetigt ist:**
- SPI-Device `spi32766.0` aktiv, Treiber `spi-audio-pltfm` gebunden
- 4 TLV320 ADCs auf I2C Bus 0 erkannt (0x18, 0x19, 0x1a, 0x1b)
- Kernel-Treiber `amzn-mt-spi-pcm.c` ist geladen (Device 24 existiert)
- Alle Mixer-Controls via tinymix steuerbar

**Naechste Schritte:**
1. **S24_3LE-faehiges Capture-Tool** auf Echo Dot bringen:
   - Option A: `arecord` (ALSA utils) cross-kompilieren fuer ARM
   - Option B: Minimales C-Tool basierend auf tinyalsa mit S24_3LE Support
   - Option C: Android AudioRecord API (Java/NDK App)
2. **FPGA-Status pruefen** — beim Boot-Log nach "FPGA Revision" suchen
   (dmesg Buffer rotiert schnell, evtl. `logcat` oder persistent logging)
3. **MCLK pruefen** — TLV320 braucht 9.6MHz MCLK, aktiviert ueber
   `AudDrv_GPIO_MCLK_Select()` im Kernel
4. **Falls Device 24 trotzdem Nullen liefert:** FPGA-Firmware fehlt oder
   nicht geladen. Firmware-Datei suchen in `/system/` oder `/vendor/`

**Source-Code:** `/tmp/echo_src/kernel/mediatek/mt8163/3.18/`
- `sound/soc/mediatek/mt_soc_audio_8163_amzn/amzn-spi-pcm/` — SPI-PCM-Treiber
- `sound/soc/codecs/tlv320aic3101.c` — ADC-Treiber
- `sound/soc/mediatek/mt_soc_audio_8163_amzn/mt_soc_machine.c` — Machine Driver
**Mixer-Dump gespeichert:** `data/FreeEchoDot2/docs/tinymix_dump.txt`

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
