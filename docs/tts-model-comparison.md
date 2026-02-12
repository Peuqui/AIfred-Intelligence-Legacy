# TTS Model Comparison for AIfred Intelligence

> Stand: 2026-02-12 | Quellen: Community-Reviews, GitHub, HuggingFace

## AIfred-Anforderungen

- **Multilingual** (mindestens Deutsch + Englisch)
- **Voice Cloning** (eigene Stimmen, keine Presets)
- **Expressiv** (Betonung, Emotion, Persoenlichkeit)
- **Streaming-faehig** (Satz-fuer-Satz TTS waehrend LLM streamt)
- **VRAM-Budget**: RTX 3090 Ti (24 GB), LLM laeuft parallel

## Aktuell: XTTS v2

Gute Betonung, Sprachpausen, multilingual (17+ Sprachen inkl. DE), Voice Cloning.
Schwaechen: Halluzination bei kurzem Text (< 3 Woerter), nicht sehr expressiv,
relativ langsam. Bestehende geklonte Stimmen muessen mit neuem Modell kompatibel sein
oder neu geklont werden.

---

## Streaming-Modi erklaert

Es gibt drei Stufen von TTS-"Streaming":

### 1. Chunk-basiert (XTTS v2, F5-TTS, Higgs-Audio)
```
LLM streamt → Satz erkennen → ganzer Satz an TTS → warten bis Audio fertig → abspielen
```
- Latenz = komplette Generierungszeit pro Satz (1-3 Sekunden)
- **Vorteil:** Modell sieht ganzen Satz → bessere Intonationsplanung
  (Fragesatz wird von Anfang an anders betont als Aussage)
- **Nachteil:** Hoechste Latenz, Satzerkennung noetig
- AIfred nutzt diesen Modus aktuell mit Carry-Mechanismus fuer kurze Saetze

### 2. Autoregressive Streaming (Qwen3-TTS, VoxCPM 1.5, Spark-TTS)
```
Satz an Modell → erste Audio-Frames sofort → abspielen WAEHREND Rest generiert wird
```
- Latenz = First-Audible ~200-300ms
- **Vorteil:** Niedrige Latenz, Satzanfang hoerbar bevor Satzende fertig
- **Nachteil:** Modell muss Intonation "raten" bevor Satzende bekannt

### 3. Echtes Text-Streaming (VibeVoice Realtime)
```
LLM streamt Wort fuer Wort → direkt an TTS → Audio kommt sofort
```
- Latenz = niedrigste (~80-300ms First-Packet)
- **Vorteil:** Keine Satzerkennung noetig, direktes LLM→TTS Piping
- **Nachteil:** Modell hat am wenigsten Kontext fuer Intonation

**Fazit:** Chunk-basiert ist nicht schlechter - nur langsamer. Die Qualitaet kann
sogar besser sein, weil das Modell den vollen Satzkontext hat. Fuer AIfred ist die
Latenz akzeptabel, da der LLM ohnehin satzweise streamt.

---

## Vergleichstabelle

| Modell | Parameter | Sprachen | DE | Voice Cloning | Expressiv | Streaming | Speed (RTFX) | Sample Rate | VRAM | Architektur | Lizenz |
|--------|-----------|----------|-----|---------------|-----------|-----------|-------------|-------------|------|-------------|--------|
| **XTTS v2** (aktuell) | ~1.5B | 17+ | Ja | Ja (6-15s Audio) | Mittel | Nein (Chunk-basiert) | ~0.5-1x | 24 kHz | ~2-4 GB | Autoregressive + DVAE | CPML |
| **F5-TTS** | ~335M | Multilingual | Ja (Fine-Tune existiert) | Ja (Zero-Shot) | Sehr hoch | Nein (Flow-basiert) | RTF 0.15 (~7x) | 24 kHz | ~2-4 GB | Flow Matching | CC-BY-NC 4.0 |
| **Qwen3-TTS** | 1.7B | 10 (CN,EN,DE,FR,JA,KO,RU,PT,ES,IT) | Ja (nativ) | Ja (3s Audio) | Hoch | Ja (via Fork) | ~1.8x | 24 kHz | ~4-6 GB | LLM-basiert | Apache 2.0 |
| **Higgs-Audio V2** | 3B | 50+ | Ja | Ja (3-10s Audio) | Sehr hoch (beste) | Unklar | ~1.8x | 24 kHz | ~8-12 GB | Llama-3.2-3B + DualFFN | Apache 2.0 |
| **EchoTTS** | Unklar | Unklar | Unklar | Ja (beste Aehnlichkeit) | Niedrig (monoton) | Nein | ~10x | 44.1 kHz | Unklar | Diffusion | Unklar |
| **Spark-TTS** | 0.5B | CN + EN | Nein | Ja (Zero-Shot) | Hoch | Ja | ~50x (schnellste!) | 16 kHz | ~2-4 GB | LLM Single-Stream | Apache 2.0 |
| **VoxCPM 1.5** | Unklar | CN + EN | Nein | Ja (Zero-Shot) | Unklar | Ja (RTF 0.17) | ~6x | 44.1 kHz | Unklar | Diffusion Autoregressive | Unklar |
| **VibeVoice TTS** | 1.5B | EN, CN, weitere | Unklar | Ja | Hoch | Nein | Unklar | Unklar | ~6-8 GB | Next-Token Diffusion @ 7.5Hz | MIT |
| **VibeVoice Realtime** | 0.5B | EN, CN, weitere | Unklar | Ja | Hoch | Ja (300ms Latenz) | Unklar | Unklar | ~2-4 GB | Next-Token Diffusion | MIT |
| **VibeVoice 7B** | 7B | EN, CN, weitere | Unklar | Ja (Multi-Speaker) | Hoch | Nein (Langform) | Unklar | Unklar | ~19 GB | Next-Token Diffusion | MIT |
| **PocketTTS** | Klein | Unklar | Unklar | Ja (Safetensors) | Unklar | Ja (OpenAI-API) | Unklar | Unklar | CPU moeglich! | Unklar | Unklar |
| **Dia (Nari Labs)** | 1.6B | Nur EN | Nein | Ja (wenige Sek.) | Sehr hoch | Unklar | Unklar | Unklar | ~6-8 GB | Unklar | Apache 2.0 |
| **CosyVoice-3** | Unklar | Multilingual | Unklar | Ja | Mittel | Unklar | Unklar | Unklar | Unklar | Unklar | Unklar |
| **IndexTTS 2** | Unklar | Unklar | Unklar | Ja | Unklar | Unklar | Unklar | Unklar | Unklar | Unklar | Unklar |
| **MOSS-TTS Local** | 1.7B | 20+ (CN,EN,DE,FR,ES,JA,KO,...) | Ja (nativ) | Ja (Zero-Shot) | Hoch | Nein (Chunk-basiert) | Unklar | 22.05 kHz | ~6-8 GB | Global Latent + Local Transformer | Apache 2.0 |
| **MOSS-TTS** | 8B | 20+ | Ja (nativ) | Ja (Zero-Shot) | Hoch | Nein | Unklar | 16 kHz | ~16 GB | MossTTSDelay | Apache 2.0 |
| **MOSS-TTS Realtime** | 2B | 20+ | Ja | Ja | Hoch | Ja (Low-Latency) | Unklar | Unklar | ~4-6 GB | MossTTSRealtime | Apache 2.0 |
| **Chatterbox** | Unklar | EN | Nein | Ja | Hoch | Ja (Sub-200ms) | Unklar | Unklar | Unklar | Unklar | Unklar |

## Community-Bewertungen (Audiobook Use-Case)

### Prompt Audio Similarity (wie gut wird die Stimme geklont)
EchoTTS > Qwen3-TTS > Higgs-Audio > Spark-TTS

### Expressiveness (Betonung, Emotion, Dynamik)
Higgs-Audio > Spark-TTS ~ Qwen3-TTS > EchoTTS

### Stability (fehlende Woerter, Artefakte)
EchoTTS > Higgs-Audio > Spark-TTS ~ Qwen3-TTS

### Voice Variation (Stimmvariation je nach Textinhalt)
Higgs-Audio > Spark-TTS > Qwen3-TTS > EchoTTS

### Natural Sounding (Natuerlichkeit)
Spark-TTS ~ Qwen3-TTS > Higgs-Audio > EchoTTS

### Clarity (Audioqualitaet, abhaengig von Sample Rate)
EchoTTS (44 kHz) > Qwen3-TTS (24 kHz) > Higgs-Audio (24 kHz) > Spark-TTS (16 kHz)

### Cross-Lingual Voice Cloning (Stimme in Sprache X klonen, Sprache Y sprechen)
XTTS v2 > Qwen3-TTS > MOSS-TTS Local

**Eigener Test:** MOSS-TTS behaelt den Akzent der Referenz-Sprache. Englischer Sprecher
klingt auf Deutsch "auslaendisch". XTTS v2 trennt Stimm-Identitaet von Akzent besser
und klingt bei Cross-Lingual deutlich natuerlicher.

## Ausgeschiedene Modelle (Community-Feedback)

| Modell | Grund |
|--------|-------|
| VoxCPM 1.5 | "Overly sibilant" (zu viele Zischlaute) - ABER: Anderer Reviewer sagt "best streaming model" |
| VibeVoice | "Insufficient stability" |
| CosyVoice-3 | Audio nicht sauber, Klicks, Rauschen, Artefakte |
| IndexTTS 2 | Audio nicht sauber, Klicks, Rauschen, Artefakte |
| MOSS-TTS (alte Version) | Audio nicht sauber, Klicks und Rauschartefakte (Bewertung vor MOSS-TTS Family Release 10.02.2026) |
| Chatterbox | Viele Artefakte |

**Anmerkung:** Diese Bewertungen stammen aus dem Audiobook-Use-Case (Langform).
Fuer AIfred (kurze Saetze, konversationell) koennen die Ergebnisse abweichen.

## Top-Kandidaten fuer AIfred

### 1. F5-TTS
- **Pro:** Hoechste Qualitaet laut Community, DE Fine-Tune existiert, schnell (RTF 0.15),
  sehr expressiv, relativ klein (~335M), Voice Cloning
- **Contra:** Kein natives Streaming (Flow-basiert, generiert ganzen Satz auf einmal),
  CC-BY-NC Lizenz (nicht-kommerziell)
- **Links:** [GitHub](https://github.com/SWivid/F5-TTS) |
  [DE Fine-Tune](https://huggingface.co/aihpi/F5-TTS-German) |
  [DE Voice Clone](https://huggingface.co/tabularisai/f5-tts-german-voice-clone)

### 2. Qwen3-TTS
- **Pro:** Deutsch nativ unterstuetzt, Streaming via Fork, guter Allrounder,
  3s Voice Cloning, Cross-lingual Cloning, Apache 2.0
- **Contra:** Nur ~1.8x RTFX, nicht die expressivste
- **Links:** [GitHub](https://github.com/QwenLM/Qwen3-TTS) |
  [Streaming Fork](https://github.com/dffdeeq/Qwen3-TTS-streaming)

### 3. Higgs-Audio V2
- **Pro:** Expressivste aller Modelle, 50+ Sprachen, Voice Cloning,
  75.7% Win-Rate ueber GPT-4o-mini-tts bei Emotionen, Apache 2.0
- **Contra:** Qualitaetsschwankungen bei starker Variation, 3B braucht mehr VRAM,
  ~1.8x RTFX
- **Links:** [GitHub](https://github.com/boson-ai/higgs-audio) |
  [HuggingFace](https://huggingface.co/bosonai/higgs-audio-v2-generation-3B-base)

### 4. MOSS-TTS Local (1.7B)
- **Pro:** State-of-the-Art Benchmarks (EN SIM 73.42%, ZH SIM 78.82% - beste Open-Source),
  20 Sprachen inkl. Deutsch nativ, Zero-Shot Voice Cloning, Pinyin/IPA Phonem-Kontrolle,
  bis zu 1 Stunde Audio in einem Run, Apache 2.0
- **Contra:** Brandneu (10.02.2026), braucht Python 3.12 + PyTorch 2.9 + Transformers 5.0
  (bleeding edge Dependencies), Community-Bewertung der Vorgaengerversion war negativ
  (Artefakte), ~6-8 GB VRAM, Cross-Lingual Voice Cloning schwach (behaelt Akzent der
  Referenzsprache), nicht merklich schneller als XTTS v2
- **Links:** [GitHub](https://github.com/OpenMOSS/MOSS-TTS) |
  [HuggingFace Local](https://huggingface.co/OpenMOSS-Team/MOSS-TTS-Local-Transformer) |
  [HuggingFace 8B](https://huggingface.co/OpenMOSS-Team/MOSS-TTS) |
  [HuggingFace Realtime](https://huggingface.co/OpenMOSS-Team/MOSS-TTS-Realtime)
- **Benchmarks (Seed-TTS-eval):**
  | Modell | EN WER | EN SIM | ZH CER | ZH SIM |
  |--------|--------|--------|--------|--------|
  | MOSS-TTS Local 1.7B | 1.85 | 73.42 | 1.2 | 78.82 |
  | Qwen3-TTS 1.7B | 1.33 | 71.45 | 1.33 | 76.72 |
  | CosyVoice3 1.5B | 2.22 | 72.0 | 1.12 | 78.1 |

## Voice Cloning Kompatibilitaet

XTTS v2 Voice Clones (WAV/OGG Referenz-Audio) koennen **nicht** direkt in andere
Modelle uebernommen werden. Jedes Modell hat sein eigenes Cloning-Format:

- **XTTS v2**: 6-15 Sekunden Referenz-Audio (WAV)
- **F5-TTS**: Wenige Sekunden Referenz-Audio (Zero-Shot)
- **Qwen3-TTS**: 3 Sekunden Referenz-Audio
- **Higgs-Audio V2**: 3-10 Sekunden Referenz-Audio
- **MOSS-TTS**: Referenz-Audio (keine Transkription noetig)

Die **originalen Audioaufnahmen** der Stimmen koennen aber fuer jedes Modell
als Referenz verwendet werden. Solange die Originalaufnahmen vorhanden sind,
ist ein Wechsel problemlos.

## Empfohlene Evaluierungsreihenfolge

1. **MOSS-TTS Local** testen (beste Benchmarks, brandneu, Docker-Container bereit)
2. **F5-TTS** mit deutschem Fine-Tune testen (kleinstes Modell, schnellstes)
3. **Qwen3-TTS** testen (nativer DE-Support, Streaming)
4. **Higgs-Audio V2** testen (wenn mehr Expressivitaet gewuenscht)
5. Falls keines ueberzeugt: XTTS v2 mit Carry-Mechanismus weiter optimieren

## Tipps aus der Community

- **Sentence Chunking** ist bei ALLEN Modellen noetig (nicht nur XTTS)
- **Kurze Saetze buffern** (wie unser Carry-Mechanismus) - universelles Problem
- **Mehrere Seeds testen** - beeinflusst Sprechweise und Stabilitaet
- **Silero VAD** fuer konsistente Stille zwischen Saetzen
- **STT-basierte Validierung** (Whisper) um fehlende Woerter zu erkennen
- **FlowHigh** kann 16kHz auf 48kHz upsamplen (relevant fuer Spark-TTS)
