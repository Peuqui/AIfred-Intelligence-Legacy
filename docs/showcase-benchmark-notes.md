# AIfred Tribunal Benchmark: 6 Modelle im Vergleich

## Konzept

Sechs lokale LLM-Modelle beantworten dieselbe Frage im AIfred Tribunal-Modus
(Multi-Agent-Debatte: AIfred vs. Sokrates + Salomo-Urteil).
Verglichen werden Inferenzgeschwindigkeit, Antwortqualität und philosophische Tiefe.

**Frage (DE):** "Was ist besser, Hund oder Katze?"
**Frage (EN):** "What is better, dog or cat?"

Beide Varianten werden separat inferiert (keine Übersetzung).

---

## Test-Setup

### Hardware

| Komponente | Details |
|---|---|
| GPU 1 | NVIDIA Quadro RTX 8000 (48 GB VRAM) |
| GPU 2 | NVIDIA Tesla P40 (24 GB VRAM) |
| Total VRAM | 72 GB |
| CPU RAM | 32 GB (davon ~20-27 GB nutzbar für Offload) |
| Tensor-Split | 2:1 (RTX 8000 : P40) |
| Backend | llama.cpp via llama-swap |

### Software

| Parameter | Wert |
|---|---|
| Frontend | AIfred Intelligence (Eigenentwicklung) |
| Backend | llama.cpp (llama-swap Proxy) |
| Tribunal-Modus | 2 Runden + Salomo-Urteil |
| Reasoning-Tiefe | Automatic (= Medium) |
| Temperaturen | AIfred=0.3, Sokrates=0.5, Salomo=0.6 |
| Flash Attention | Ein |
| Session | Frisch (keine Vorgeschichte) |

---

## Getestete Modelle

| Modell | Architektur | Params (total) | Aktive Params | Quant | GGUF-Größe | Context | KV-Cache | Offload |
|---|---|---|---|---|---|---|---|---|
| MiniMax-M2.5 | MoE (256x4.9B) | ~230B | ~39B | Q2_K_XL | 80 GB | 32.768 | q4_0 | Ja (ngl=48) |
| GPT-OSS-120B | MoE (128x4) | 120B | ~4B | Q8_0 | 59 GB | 131.072 | f16 | Nein |
| Qwen3-Next-80B-A3B (no-think) | MoE | 80B | 3B | Q4_K_M | 46.6 GB | 262.144 | f16 | Nein |
| Qwen3-Next-80B-A3B (thinking) | MoE | 80B | 3B | Q4_K_M | 45.2 GB | 262.144 | f16 | Nein |
| GLM-4.7 Reap 218B | Dense | 218B | 218B | IQ3 | TBD | TBD | TBD | TBD |
| Qwen 235B | TBD | 235B | TBD | TBD | TBD | TBD | TBD | TBD |

### Status der neuen Modelle

- **GLM-4.7 Reap 218B (IQ3):** Kalibrierung läuft (Stand: 2026-02-20)
- **Qwen 235B:** Kalibrierung steht noch aus

### Hinweise zur Fairness

- MiniMax bei Q2_K_XL ist aggressiv quantisiert (deutlicher Qualitätsverlust vs. Original)
- GPT-OSS bei Q8_0 ist nahe am Original (minimaler Verlust)
- Qwen3 bei Q4_K_M ist ein guter Kompromiss
- GLM-4.7 bei IQ3 ist aggressiv quantisiert (ähnlich wie MiniMax Q2)
- MiniMax benötigt CPU-Offload (ngl=48 von 62 Layern auf GPU)
- Dies ist kein Vergleich der Modelle an sich, sondern ein Vergleich dessen, was auf 72 GB VRAM + CPU-Offload lokal machbar ist

---

## Performance-Metriken (Deutsche Inferenz)

### AIfred (Erstantwort)

| Metrik | MiniMax Q2 | GPT-OSS Q8 | Qwen3 no-think | Qwen3 thinking |
|---|---|---|---|---|
| TTFT | 30,1s | 1,8s | 4,0s | 3,9s |
| Prompt Processing | 34,4 tok/s | 577 tok/s | 307 tok/s | 316 tok/s |
| Generation Speed | 7,8 tok/s | 52,1 tok/s | 33,4 tok/s | 44,0 tok/s |
| Inference Time | 59,6s | 13,6s | 13,8s | 69,2s |
| Output Tokens | 463 | 709 | 462 | 3.049* |

*Qwen3-Thinking: ~200 sichtbare Tokens, Rest sind interne Thinking-Tokens

### Gesamtes Tribunal (AIfred + Sokrates R1 + AIfred R2 + Sokrates R2 + Salomo)

| Metrik | MiniMax Q2 | GPT-OSS Q8 | Qwen3 no-think | Qwen3 thinking |
|---|---|---|---|---|
| Gesamtdauer | ~12 min* | ~1,9 min | ~2,1 min | ~4,6 min |
| Speed-Degradation | 7,8→? tok/s | 52→47 tok/s | 33→22 tok/s | 44→38 tok/s |
| TTFT-Anstieg | 30→65+s | 1,8→4,9s | 4→12s | 4→11s |

*MiniMax Tribunal läuft noch bei Erstellung dieses Dokuments

### Prompt Processing im Vergleich

GPT-OSS dominiert mit 577-880 tok/s (Faktor 17-25x vs. MiniMax).
Dies erklärt die extrem niedrigen TTFT-Werte von unter 5s selbst in späten Runden.

---

## Qualitätsanalyse

### Ranking

| Rang | Modell | Stärke | Schwäche |
|---|---|---|---|
| 1 | Qwen3-Next (no-think) | Literarische Brillanz, originelle Metaphern, echte philosophische Tiefe | Gelegentliche Halluzination (z.B. falsches Latein) |
| 2 | GPT-OSS-120B | Systematisch, strukturiert, faktenbasiert (referenziert Studien) | Seelenlos, schwache Butler-Persona, Over-Engineering |
| 3 | MiniMax-M2.5 | Guter Erzählfluss, konsistente Persona | Langsam, vereinzelte Sprachfehler, Q2-bedingte Limitierungen |
| 4 | Qwen3-Next (thinking) | — | Thinking-Tokens verschwenden Compute für Meta-Reasoning statt Inhalt |

### Herausragende Beispiele

**Qwen3 no-think — AIfred (Eröffnung):**
> "Wie die Frage, ob man lieber Earl Grey mit Zitrone oder mit Milch trinkt: beides ist vorzüglich, doch die Wahl verrät mehr über den Trinker als über den Tee."

**Qwen3 no-think — Sokrates R1 (rhetorische Frage):**
> "Wenn du einen Hund verlierst — weinst du, weil du einen Gefährten verloren hast? Wenn du eine Katze verlierst — weinst du, weil du eine Illusion verloren hast?"

**Qwen3 no-think — AIfred Verteidigung (philosophische Tiefe):**
> "Die virtus des Hundes liegt im Handeln — die virtus der Katze liegt im Sein."

**Qwen3 no-think — Sokrates R2 (vernichtender Konter):**
> "Du nennst das 'Liebe in Ruhe'. Ich nenne es Nichtstun mit Anspruch."

**Qwen3 no-think — Sokrates R2 (emotionaler Höhepunkt):**
> "Wenn du morgen sterben würdest — wer würde dich finden, mit dem Kopf auf deiner Brust?
> Der Hund — der dich nicht loslässt, bis der letzte Atem geht.
> Oder die Katze — die sich erst auf dich legt, wenn du kalt bist?"

**GPT-OSS — AIfred Verteidigung (Scoring-Modell mit Studienreferenzen):**
> Erstellt ein gewichtetes Scoring-Modell mit 6 Kriterien und referenziert Studien
> (Odendaal & Meintjes 2003, Kogan et al. 2015, Westgarth et al. 2014).
> Systematisch stark, aber für eine Haustier-Frage Over-Engineering.

### Schwächen und Fehler

| Modell | Fehler |
|---|---|
| MiniMax Q2 | "behaftest" statt "behauptest", chinesische Zeichen im Thinking ("忽略了") |
| GPT-OSS Q8 | "Sehr social" (englisch statt deutsch), "verleässt" (Tippfehler), Genderstern "Nutzer*innen" |
| Qwen3 no-think | "Vos ist nicht das, was du hast" (sinnloses Latein, Halluzination) |
| Qwen3 thinking | Inhaltlich dünn, Thinking zu 90% Meta-Reasoning über Formatierung |

---

## Key Findings

### 1. Thinking-Mode ist kontraproduktiv für kreative/diskursive Aufgaben

Qwen3-Next produziert im Non-Thinking-Modus deutlich bessere Outputs als im Thinking-Modus.
Die Thinking-Tokens werden zu ~90% für Meta-Reasoning über Formatierungsregeln verwendet,
nicht für inhaltliche Tiefe.

**Beispiel Thinking-Inhalt:**
> "The instruction says to use markdown pipe syntax for tables...
> need to make sure the table is properly formatted...
> 'indeed' is an adverb, so 'Hunde sind indeed treue Begleiter'
> — but in German, 'indeed' might not fit perfectly..."

**Ergebnis:** 3.049 Tokens generiert → sichtbar nur eine Mini-Tabelle + 3 Sätze.

**Finding:** "Reasoning efficiency matters more than reasoning volume."

### 2. MoE vs. Dense auf begrenzter Hardware

| Aspekt | MoE (MiniMax/Qwen3) | Dense (GPT-OSS) |
|---|---|---|
| Parameternutzung | Bruchteil aktiv pro Token | Alle aktiv |
| Speed | Variabel (3-44 tok/s) | Konsistent hoch (47-52 tok/s) |
| VRAM-Effizienz | Mehr Wissen pro GB | Weniger Wissen, aber schneller |
| Quality/Speed-Ratio | Qwen3 no-think am besten | GPT-OSS solide aber seelenlos |

### 3. CPU-Offload-Penalty

MiniMax mit CPU-Offload (ngl=48/62) zahlt einen enormen Speed-Preis:
- 7,8 tok/s Generation (vs. 33-52 tok/s bei GPU-only Modellen)
- TTFT 30-65+s (vs. 2-12s bei GPU-only)
- Gesamtes Tribunal ~12 min (vs. 2 min bei GPU-only)

### 4. MiniMax Reasoning-Effizienz

MiniMax' Thinking-Blöcke sind kurz und zielgerichtet (~10 Zeilen).
Trotz aggressiver Q2-Quantisierung und CPU-Offload liefert das Modell kohärente,
persona-konsistente Antworten. Die Reasoning-Effizienz ist bemerkenswert —
ob dies am Modell-Design oder an Q2-bedingter Verkürzung liegt,
lässt sich ohne Q4/Q8-Vergleich nicht klären.

---

## GGUF-Metadaten (MiniMax-M2.5)

Aus der GGUF-Datei ausgelesen:

| Feld | Wert |
|---|---|
| general.name | Minimax-M2.5 |
| general.size_label | 256x4.9B |
| general.quantized_by | Unsloth |
| minimax-m2.expert_count | 256 |
| minimax-m2.expert_used_count | 8 |
| minimax-m2.block_count | 62 |
| minimax-m2.embedding_length | 3.072 |
| minimax-m2.attention.head_count | 48 |
| minimax-m2.attention.head_count_kv | 8 (GQA) |
| minimax-m2.context_length | 196.608 (nativ) |

---

## Showcase-Struktur (geplant)

### Deutsche Version
- Deutsche Inferenzen (Original-Sessions)
- Deutsche Analyse
- TTS-Demo einer Session (XTTS/MOS-TTS)

### Englische Version
- Englische Inferenzen (separat gelaufen, keine Übersetzung)
- Englische Analyse
- TTS-Demo derselben Session auf Englisch

### Zusatz-Analyse
- Deutsch vs. Englisch Qualitätsvergleich (von Claude erstellt)
- Sprachliche Unterschiede, Persona-Konsistenz über Sprachen hinweg

### Reddit-Post
- Kurzer, knackiger Post mit Highlights
- Link zum GitHub.io Showcase für Details
- Hervorhebung der Neuerungen seit Jahreswechsel:
  - TTS-Integration (MOS-TTS, XTTS)
  - Tribunal-Modus (Multi-Agent-Debatte)
  - Autoscan & Kalibrierung für lokale Modelle
  - Hardware-Benchmarks auf Prosumer-Setup

---

## Offene Punkte

- [x] MiniMax deutsche Session abwarten — erledigt
- [x] HTML-Export der 4 deutschen Sessions — erledigt (liegen in data/html_preview/)
- [ ] GLM-4.7 Reap 218B (IQ3) kalibrieren — läuft
- [ ] Qwen 235B kalibrieren
- [ ] Deutsche Inferenzen für GLM-4.7 und Qwen 235B laufen lassen
- [ ] Englische Inferenzen für alle 6 Modelle laufen lassen
- [ ] TTS-Rendering einer Session (DE + EN)
- [ ] Deutsch/Englisch-Kreuzvergleich durch Claude
- [ ] Showcase-HTML erstellen (DE + EN)
- [ ] Reddit-Post verfassen

## Datenquellen

- Session-JSONs (data/sessions/) werden für den Showcase NICHT benötigt
- HTML-Previews (data/html_preview/) enthalten alle relevanten Metriken pro Bubble:
  TTFT, PP (tok/s), TG (tok/s), Inference-Zeit, Source (Agent + Modell + Backend)
