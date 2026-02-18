# llama.cpp + llama-swap Setup Guide

Referenzdokument fuer die llama.cpp Integration in AIfred via llama-swap.
Wird bei Hardware-Aenderungen oder neuen llama.cpp Releases aktualisiert.

**Stand:** 2026-02-18

---

## Hardware-Uebersicht

### GPU-Vergleich

| Spec | Tesla P40 | Quadro RTX 8000 | RTX 3090 Ti |
|------|-----------|-----------------|-------------|
| Architektur | Pascal (GP102) | Turing (TU102) | Ampere (GA102) |
| Compute Capability | 6.1 | 7.5 | 8.6 |
| VRAM | 24 GB GDDR5X | 48 GB GDDR6 | 24 GB GDDR6X |
| Bandbreite | 346 GB/s | 672 GB/s | 936 GB/s |
| Tensor Cores | Keine | 576 (1. Gen) | 328 (2. Gen) |
| FP16 | 1/64 von FP32 (!) | Voll (via TC) | Voll (via TC) |
| NVLink | Nein | Ja (100 GB/s) | Nein |
| TDP | 250W | 295W | 450W |

### NVIDIA llama.cpp Optimierungen (CES 2026)

| Optimierung | Effekt | P40 | RTX 8000 | 3090 Ti |
|---|---|---|---|---|
| CUDA Graphs | bis 35% schnellere Token-Gen | Ja | Ja | Ja |
| MMVQ Kernel | Bessere quantisierte Inferenz | Ja | Ja | Ja |
| MMQ (INT8 TC) | INT8 Tensor Core Kernels | Nein | Ja | Ja |
| Flash Attention | Weniger VRAM, schnellere PP | Ja (modellabhaengig!) | Ja | Ja |
| GPU Token Sampling | Eliminiert CPU-GPU Transfers | Ja | Ja | Ja |
| Model Loading | bis 65% schneller | Ja | Ja | Ja |
| FP8 W8A16 | Weight-only FP8 | Nein | Ja (vLLM) | Ja (Marlin) |
| NVFP4 | Neue Quantisierung | Nein | Nein | Nein |
| vLLM kompatibel | CC >= 7.0 noetig | Nein | Ja | Ja |

---

## Performance-Parameter

### Alle relevanten llama-server Flags

| Parameter | Syntax | Default | Beschreibung |
|---|---|---|---|
| `-ngl` | `-ngl 99` / `-ngl auto` | `auto` | Layer auf GPU offloaden |
| `-c` | `-c 8192` | aus Modell | Context-Groesse (KV-Cache skaliert linear) |
| `-fa` | `-fa on` / `--flash-attn off` | `auto` | Flash Attention (global, nicht per GPU!) |
| `-ctk` | `-ctk q8_0` | `f16` | KV-Cache Key Typ (q8_0, q4_0, f16, f32) |
| `-ctv` | `-ctv q8_0` | `f16` | KV-Cache Value Typ |
| `-b` | `-b 2048` | `2048` | Logische Batch-Size (Prompt Processing) |
| `-ub` | `-ub 512` | `512` | Physische Batch-Size (GPU Batch) |
| `-sm` | `-sm layer` | | Split-Mode: layer, row, none |
| `-ts` | `-ts 1,2.5` | | Tensor-Split Verhaeltnis zwischen GPUs |
| `-mg` | `-mg 1` | `0` | Main-GPU (Output-Layer, Scratch-Buffers) |
| `--mlock` | `--mlock` | off | RAM-Pages nicht swappen |
| `--no-mmap` | `--no-mmap` | mmap on | Modell komplett laden statt lazy |
| `-t` | `-t 8` | auto | CPU-Threads (Generation) |
| `-tb` | `-tb 16` | wie `-t` | CPU-Threads (Batch/Prompt) |
| `-np` | `-np 1` | `auto` (=4!) | Parallel Slots (Multi-User) |
| `-fit` | `-fit off` | `on` | Auto-Parameter an VRAM anpassen (P40: off!) |
| `-dev` | `-dev CUDA0,CUDA1` | | Explizite GPU-Auswahl |
| `-ot` | `-ot "regex=DEVICE"` | | Override Tensor (ik_llama.cpp) |

### Umgebungsvariablen

```bash
export CUDA_DEVICE_ORDER=PCI_BUS_ID    # Konsistente GPU-Reihenfolge
export GGML_CUDA_GRAPH_OPT=1           # 10-15% schnellere Token-Gen
```

### KV-Cache Quantisierung

| Typ | VRAM-Ersparnis vs f16 | Speed-Impact (PP) | Qualitaets-Impact | Hinweis |
|---|---|---|---|---|
| `q8_0` | ~50% | **+30-134% schneller** | Vernachlaessigbar | **Empfohlen** |
| `q4_0` | ~72% | +20-30% schneller | Spuerbar bei Keys | Nur wenn VRAM extrem knapp |
| `f16` | Baseline | Baseline | Kein | Standard |

**Wichtig:**
- KV-Cache Quantisierung benoetigt Flash Attention (`--flash-attn on`)
- Q8_0 ist schneller als Q4_0 bei PP (weniger Dequantisierungs-Overhead)
- Gen-Speed ist bei allen Varianten identisch (~46-63 tok/s je nach Modell)
- KV-Quant ≠ Modell-Quant: KV-Quant spart Bandbreite (Attention), Modell-Quant spart Rechenzeit (Matmul)

### P40-spezifische Hinweise

| Parameter | Empfehlung | Grund |
|---|---|---|
| `-fit` | `off` | `-fit on` crasht auf Pascal mit CUDA OOM bei `cudaMemGetInfo` |
| `-np` | `1` | Default `auto` setzt 4 Slots = 4x Compute Buffer VRAM |
| `--flash-attn` | `on` | Weniger VRAM (Compute Buffer -86%), schnellere PP bei Qwen3 |
| `-ctk`/`-ctv` | `q8_0` | KV-Cache halbieren, kaum Qualitaetsverlust |

---

## Benchmark: Tesla P40 (2x 24 GB, llama.cpp v8076)

Datum: 2026-02-17. Hardware: 2x Tesla P40 (24 GB GDDR5X, PCIe x16).
llama.cpp Version: 8076 (d61290111), kompiliert mit `GGML_CUDA=ON`.

**Test-Prompt:** `"Write a short poem about the sun in exactly 4 lines."` (21 Tokens, max_tokens=100)
**Basis-Parameter:** `-ngl 99 -np 1 -fit off -t 4 -b 2048 -ub 512`

### Qwen3-4B-Instruct-2507 (Q4_K_M, Single GPU CUDA0)

| Config | Context | Prompt (tok/s) | Gen (tok/s) | VRAM total (MiB) | KV Buffer (MiB) | Compute Buffer (MiB) |
|---|---|---|---|---|---|---|
| FA off, FP16 KV | 32K | 205,8 | 61,7 | 9.283 | 4.608 | 2.142 |
| **FA on, FP16 KV** | 32K | **352,9** | 63,9 | 7.441 | 4.608 | 302 |
| **FA on, Q8 KV** | 32K | **481,3** | 62,5 | **5.293** | **2.448** | 302 |
| FA on, Q8 KV | 131K | 490,2 | 62,7 | 12.747 | 9.792 | 410 |
| FA on, **Q4 KV** | 32K | 391,4 | 60,8 | 4.141 | **1.296** | 302 |

**Ergebnis:** FA + Q8 KV auf P40 ist der klare Gewinner:
- **PP: +134% schneller** als Baseline (481 vs 206 tok/s)
- **Gen: unveraendert** (~62 tok/s)
- **VRAM: -43%** (5.293 vs 9.283 MiB)
- **Max Context: 131K** (nativ 128K) auf einer einzelnen P40 mit 4B Q4_K_M

### Qwen3-30B-A3B-Instruct-2507 (Q8_0, Dual GPU, `-sm layer --tensor-split 1,1`)

| Config | Context | Prompt (tok/s) | Gen (tok/s) | GPU0 VRAM (MiB) | GPU1 VRAM (MiB) | Frei gesamt (MiB) |
|---|---|---|---|---|---|---|
| FA off, FP16 KV | 32K | 95,8 | 46,8 | 19.913 | 18.837 | 7.064 |
| FA on, FP16 KV | 32K | 91,7 | 47,4 | 17.953 | 16.929 | 10.932 |
| **FA on, Q8 KV** | 32K | **124,6** | 45,8 | 17.215 | 16.251 | **12.348** |
| FA on, Q8 KV | 65K | 114,6 | 46,5 | 18.353 | 17.161 | 10.300 |
| FA on, Q8 KV | 98K | 117,7 | 46,4 | 19.491 | 18.071 | 8.252 |
| FA on, Q8 KV | 131K | 122,4 | 47,2 | 20.631 | 18.983 | 6.200 |
| FA on, Q8 KV | 200K | 108,0 | 46,3 | 21.777 | 20.103 | 3.934 |
| FA on, Q8 KV | 220K | 115,1 | 46,9 | 22.353 | 20.581 | 2.880 |
| FA on, **Q4 KV** | 32K | 123,2 | 46,1 | 16.815 | 15.883 | 13.116 |

**Ergebnis:** FA + Q8 KV auch beim 30B optimal:
- **PP: +30% schneller** (124,6 vs 95,8 tok/s bei 32K)
- **Gen: stabil ~46-47 tok/s** unabhaengig vom Context-Window
- **VRAM: -5.284 MiB frei** gegenueber Baseline
- **Max Context: 220K** (nativ 262K) auf 2x P40 mit 30B Q8_0
- 262K crasht: "failed to allocate compute buffers" (793 MiB fehlend)

### Qwen3-Next-80B-A3B-Instruct (Q4_K_M, 48 Layer, 512 Experten/10 aktiv)

Modell: 46,6 GB (Q4_K_M), ~0,97 GB/Layer. 2x P40 = 48 GB VRAM.
Basis-Parameter: `-np 1 -fit off --flash-attn on -ctk q8_0 -ctv q8_0 -sm layer --tensor-split 1,1 -t 4 -b 512 -ub 256`

#### Layer-Offloading (`-ngl`): Speed vs Context Trade-off

| -ngl | CPU Layer (GB) | Context | Prompt (tok/s) | Gen (tok/s) | GPU0 frei (MiB) |
|---|---|---|---|---|---|
| 44 | 4 (~3,9 GB) | 4K | 75,7 | **24,1** | 452 |
| 44 | 4 | 32K | 91,8 | **24,3** | 232 |
| 44 | 4 | 57K | 81,5 | **22,9** | 42 |
| 44 | 4 | 65K | CRASH | - | - |
| 42 | 6 (~5,8 GB) | 4K | 65,2 | **21,9** | 1.344 |
| 42 | 6 | 131K | 75,3 | **21,7** | 236 |
| 42 | 6 | 144K | 75,3 | **21,5** | 92 |
| 42 | 6 | 160K | CRASH | - | - |
| **40** | **8 (~7,7 GB)** | **262K** | 63,7 | **20,5** | 380 |

#### MoE-Offloading (`-cmoe`): Experten auf CPU, Attention auf GPU

| Modus | Context | Prompt (tok/s) | Gen (tok/s) | GPU0 belegt (MiB) |
|---|---|---|---|---|
| `-ngl 99 -cmoe` | 4K | 3,2 | **6,8** | 1.539 |
| `-ngl 99 -cmoe` | 262K | 3,4 | **6,4** | 3.143 |
| `-ngl 99 -ncmoe 40` | 4K | 4,4 | **9,0** | 1.539/8.797 |

**Ergebnis und Empfehlung:**

- **`-ngl 40` ist der Sweet Spot:** Voller nativer Kontext (262K) bei nur 15% Gen-Speed-Verlust (20,5 vs 24,1 tok/s). ~7,7 GB auf CPU, passt locker in 30 GB RAM.
- **`-ngl 44`**: Maximal schnell (24 tok/s), aber nur 57K Context — zu wenig fuer langes Reasoning.
- **`-cmoe`**: 262K Context, aber **3,5x langsamer** (6,4 tok/s). Jedes Token muss 10 Experten ueber PCIe 3.0 laden. Nur sinnvoll wenn Speed egal ist.
- **Gen-Speed ist kontextunabhaengig**: ~20-24 tok/s egal ob 4K oder 262K.
- `-ngl 99` crasht (47 GB Modell passt nicht auf 48 GB VRAM)
- MoE-Weights werden per mmap geladen → erscheinen als "Puffer/Cache" im RAM, nicht als "benutzt"
- KV-Cache liegt primaer im VRAM (proportional zu GPU-Layern), nicht im CPU-RAM

### Erkenntnisse

1. **Flash Attention auf Pascal (P40) ist NICHT pauschal langsamer.** Bei Qwen3-Modellen ist PP bis zu 134% schneller. Das bekannte FA-Penalty betrifft hauptsaechlich GLM-4.7-FLASH (Issue #19020). Grund: Head-Dimension (siehe unten).

2. **Compute Buffer ist der groesste VRAM-Fresser, nicht der KV-Cache.** FA reduziert den Compute Buffer um 86% (2.142 -> 302 MiB beim 4B).

3. **Q8 KV-Quantisierung beschleunigt PP zusaetzlich** durch weniger Speicherbandbreite in der Attention-Berechnung.

4. **Gen-Speed ist kontextunabhaengig.** Egal ob 32K oder 262K Context: ~46-47 tok/s beim 30B, ~62-63 tok/s beim 4B, ~20-24 tok/s beim 80B.

5. **Pflicht-Parameter fuer P40:** `-fit off -np 1 --flash-attn on -ctk q8_0 -ctv q8_0`
   - `-fit on` crasht mit CUDA OOM auf Pascal
   - `-np auto` setzt 4 Slots = unnoetiger VRAM-Verbrauch
   - FA + Q8 KV spart VRAM und ist schneller

6. **Layer-Offloading vs MoE-Offloading fuer uebergrosse Modelle:**
   - `-ngl <N>`: Ganze Layer auf CPU. Speed sinkt moderat (~1 tok/s pro 2 Layer).
   - `-cmoe`: Nur MoE-Experten auf CPU. Speed bricht auf ~30% ein (PCIe-Bottleneck).
   - **Empfehlung:** Layer-Offloading bevorzugen, es sei denn maximaler Kontext ist wichtiger als Speed.

7. **`-ub` (Micro-Batch) reduziert Compute Buffer ohne Gen-Speed-Verlust.**
   `-ub 256` statt `512` halbiert den Compute Buffer (196 vs 392 MiB beim 30B).
   PP-Speed sinkt minimal (117 vs 120 tok/s). Gen-Speed identisch.

### Warum FA auf P40 modellabhaengig ist (technisch)

Quelle: `ggml/src/ggml-cuda/fattn.cu` und `fattn-tile.cuh` in llama.cpp.

Die P40 (CC 6.1) hat **keine Tensor Cores** und **kein schnelles FP16** (`FAST_FP16_AVAILABLE` ist fuer CC 6.1 explizit ausgeschlossen in `common.cuh:230`). Daher:

1. **Kernel-Auswahl:** P40 nutzt den generischen `tile`-Kernel im FP32-Modus. Turing+ GPUs nutzen MMA-Kernels (Tensor Cores).

2. **Vec-Kernel (fuer Token-Generation):** Nur verfuegbar bei `dkq <= 256 && dkq % 64 == 0`. Qwen3 (dkq=128) qualifiziert sich, GLM (dkq=576) nicht.

3. **FP32-Rechenaufwand skaliert mit Head-Dimension:**
   - Qwen3 (dkq=128): 128 FP32-MADs pro Dot-Product, tile-Config: `nbatch_fa=64, occupancy=3`
   - GLM (dkq=576): 576 FP32-MADs (4,5x mehr), tile-Config: `nbatch_fa=32, occupancy=2`

4. **Standard-Attention (ohne FA) nutzt cuBLAS GEMM**, das fuer FP32 auf P40 hochoptimiert ist. Bei grossen Dimensionen (576) hat cuBLAS besseren Durchsatz als der fusionierte FA-Kernel.

**Faustregel:** Modelle mit `attention.key_length <= 256` profitieren von FA auf P40. Modelle mit groesseren Head-Dimensionen (DeepSeek/MLA-Architektur) koennen langsamer werden.

---

## Heterogenes Multi-GPU (P40 + RTX 8000)

### Was funktioniert

- **Layer Split (`-sm layer`)** ueber PCIe x4 eGPU: Nur ~8 KB pro Layer-Grenze, kein Bandbreiten-Problem
- **Ungleiche Verteilung (`-ts`)**: Mehr Layer auf schnellere GPU
- **`-mg` auf RTX 8000**: Output-Layer und Scratch-Buffers auf der schnelleren GPU

### Was NICHT funktioniert

- **Row Split (`-sm row`)**: Staendige All-Reduce Synchronisation, ueber PCIe x4 unpraktikabel
- **Graph Split (`-sm graph`, ik_llama.cpp)**: Setzt gleich starke GPUs voraus, kein Auto-Balancing
- **KV-Cache Trennung**: KV-Cache ist architektonisch an seine Layer-GPU gebunden
- **Flash Attention per GPU**: Globaler Schalter, nicht per GPU steuerbar

### Flash Attention auf P40

Aeltere Annahme: FA ist auf Pascal pauschal langsamer. **Widerlegt durch Benchmarks (2026-02-17):**
FA ist bei Qwen3-Modellen auf P40 **schneller** (PP: +134% bei 4B, +30% bei 30B).
Das bekannte FA-Penalty betrifft hauptsaechlich GLM-4.7-FLASH (siehe Benchmark-Sektion).

**Empfehlung:** FA immer einschalten (`--flash-attn on`).
KV-Cache Quantisierung (`-ctk q8_0 -ctv q8_0`) spart zusaetzlich ~50% KV-VRAM.

### Benchmark: Tensor-Split Optimierung (2026-02-18)

**Hardware:** RTX 8000 (CUDA0, 46 GB) + Tesla P40 (CUDA1, 24 GB), `CUDA_DEVICE_ORDER=FASTEST_FIRST`
**Modell:** Qwen3-32B Q4_K_M (18,8 GB)
**Tool:** `llama-bench` (llama.cpp v8076)
**Parameter:** `-ngl 99 -np 1 -fit off --flash-attn on -ctk q8_0 -ctv q8_0 -sm layer -t 4 -b 2048 -ub 512`

| Config | Tensor-Split (RTX8000:P40) | PP (tok/s) | TG (tok/s) | Anmerkung |
|--------|---------------------------|-----------|-----------|-----------|
| A | RTX 8000 allein | 631 | **22,19** | Baseline (Single GPU) |
| B | P40 allein | 214 | **9,87** | Zum Vergleich |
| C | 1:1 | 326 | **13,42** | Gleich aufgeteilt |
| D | 2:1 (bisherige Config) | 394 | **15,59** | War Standard in llama-swap |
| E | 5:1 | 497 | **18,15** | Deutlich schneller |
| F | 10:1 | 565 | **19,68** | Optimum fuer 32B |

**Erkenntnisse:**

- **10:1 Split** ist **26% schneller** als 2:1 bei TG (19,68 vs. 15,59 tok/s)
- Jeder Layer auf der P40 bremst durch geringere Bandbreite (346 GB/s vs. 672 GB/s RTX 8000)
- Das PP-Optimum naehert sich ebenfalls dem Single-GPU-Wert (565 vs. 631)
- **Faustregel:** P40 nur so viel nutzen wie fuer VRAM noetig, den Rest auf die RTX 8000

**Empfehlung nach Modellgroesse und Kontext:**

| Modell | Modell-VRAM | Kontext | KV-Typ | Empf. Split (RTX:P40) | VRAM-Bedarf gesamt |
|--------|------------|---------|--------|----------------------|-------------------|
| 4B–14B Q4_K_M | < 10 GB | 131K | q8_0 | `-dev CUDA0` | < 20 GB |
| 32B Q4_K_M | 18,8 GB | 16K | q8_0 | `-dev CUDA0` | ~22 GB |
| 30B A3B Q8_0 | ~31 GB | 238K | q8_0 | `-ts 2,1` | ~50–55 GB |
| 80B Q4_K_M | 46,6 GB | 262K | q4_0 | `-ts 2,1` | ~65 GB |
| 120B Q8_0 | ~59 GB | 131K | q4_0 | `-ts 2,1` | ~65–70 GB |

**Warum Kontext den Split bestimmt:**

Der KV-Cache wird im selben Verhaeltnis wie das Modell auf die GPUs verteilt (-sm layer).
Bei einem 10:1-Split liegen 91% des KV-Cache auf der RTX 8000. Wenn das Modell schon
die meiste RTX-VRAM belegt, bleibt zu wenig Platz fuer den KV-Cache grosser Kontexte.

- **Modell passt auf RTX allein (< 46 GB):** hoher Split moeglich → P40 als Speed-Bremse minimieren
- **Modell passt NICHT auf RTX allein (≥ 46 GB):** Split ≈ VRAM-Verhaeltnis (46:24 ≈ 2:1) optimal, weil so KV-Cache gleichmaessig auf freien VRAM beider GPUs verteilt wird
- **2:1 als Faustformel:** Fuer grosse Modelle (80B+) und grosse Kontexte immer nahe am VRAM-Verhaeltnis bleiben

**Hinweis CUDA_DEVICE_ORDER:** Der llama-swap-Dienst laeuft mit `CUDA_DEVICE_ORDER=FASTEST_FIRST`,
daher ist CUDA0 = RTX 8000 und CUDA1 = P40. Tensor-Split-Werte beziehen sich auf CUDA0:CUDA1.

### Tensor-Split Empfehlungen

```bash
# Anmerkung: Mit CUDA_DEVICE_ORDER=FASTEST_FIRST gilt CUDA0=RTX 8000, CUDA1=P40

# 2x P40 (gleich stark): Gleich verteilen
-sm layer --tensor-split 1,1

# RTX 8000 (CUDA0) + P40 (CUDA1): Minimaler P40-Anteil (nur VRAM-Erweiterung)
# Fuer Modelle die BEIDE GPUs benoetigen (>46 GB)
-sm layer -ts 10,1   # 30B A3B Q8_0: gut
-sm layer -ts 24,1   # 80B Q4_K_M: VRAM-begrenzt

# Single GPU (Modell passt auf RTX 8000)
-dev CUDA0           # Bis 32B Q4_K_M: kein Split, volle RTX 8000 Speed

# 2x RTX 8000 (gleich stark): Gleich verteilen
-sm layer -ts 1,1
```

---

## llama-swap Konfiguration

### Installation

```bash
# llama-swap Binary (Go, single file)
# Download von: https://github.com/mostlygeek/llama-swap/releases
# Aktuell: v191 (Feb 2026)

# llama-server (Teil von llama.cpp)
# Kompilieren mit CUDA-Support:
cd llama.cpp && cmake -B build -DGGML_CUDA=ON && cmake --build build -j
```

### Beispiel-Config: P40 + RTX 8000

```yaml
# llama-swap.yaml
# Aktuelle Hardware: P40 (GPU0, 24GB) + RTX 8000 (GPU1, 48GB)

groups:
  main:  # Grosse Modelle, beide GPUs, nur 1 aktiv
    - qwen3-30b
    - llama3-70b

models:
  # --- Hauptmodelle (Gruppe "main") ---
  qwen3-30b:
    cmd: >
      llama-server -m /models/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf
      -ngl 99 -sm layer --tensor-split 1,2.5 --main-gpu 1
      -c 16384 --flash-attn on -ctk q8_0 -ctv q8_0
      -b 2048 -ub 512 --mlock
      --port ${PORT}
    ttl: 300  # 5min Inaktivitaet -> entladen

  llama3-70b:
    cmd: >
      llama-server -m /models/llama3-70b-Q4_K_M.gguf
      -ngl 99 -sm layer --tensor-split 1,2.5 --main-gpu 1
      -c 8192 --flash-attn on -ctk q8_0 -ctv q8_0
      --mlock --port ${PORT}
    ttl: 300

  # --- Kleine Modelle (nur RTX 8000) ---
  qwen3-8b:
    cmd: >
      llama-server -m /models/Qwen3-8B-Q4_K_M.gguf
      -ngl 99 -dev CUDA1
      -c 32768 --flash-attn on -ctk q8_0 -ctv q8_0
      --port ${PORT}
    # Kein TTL = optional permanent

  # --- Embedding (CPU-only) ---
  nomic-embed:
    cmd: >
      llama-server -m /models/nomic-embed-text.gguf
      -ngl 0 --embedding -c 8192
      --port ${PORT}
```

### Beispiel-Config: 4x RTX 8000 (Endausbau)

```yaml
# llama-swap.yaml
# Endausbau: 4x RTX 8000 (je 48GB = 192GB total)

groups:
  main:  # Riesige Modelle, alle 4 GPUs
    - qwen3-235b
    - llama3-405b

models:
  qwen3-235b:
    cmd: >
      llama-server -m /models/Qwen3-235B-A22B-Q4_K_M.gguf
      -ngl 99 -sm layer --tensor-split 1,1,1,1
      -c 16384 --flash-attn on -ctk q8_0 -ctv q8_0
      --mlock --port ${PORT}
    ttl: 600

  # Alternative: vLLM fuer MoE-Modelle (Pipeline Parallel)
  qwen3-235b-vllm:
    cmd: >
      vllm serve Qwen/Qwen3-235B-A22B-AWQ
      --pipeline-parallel-size 4
      --max-model-len 16384
      --port ${PORT}
    ttl: 600
```

### Starten

```bash
# llama-swap starten (Port 11435 = neben Ollama 11434)
CUDA_DEVICE_ORDER=PCI_BUS_ID GGML_CUDA_GRAPH_OPT=1 \
  llama-swap --config ~/.config/llama-swap/config.yaml --listen :11435
```

### Systemd-Service

```ini
# ~/.config/systemd/user/llama-swap.service
[Unit]
Description=llama-swap - LLM Model Proxy for llama.cpp
After=network.target

[Service]
Type=simple
ExecStartPre=/path/to/venv/bin/python /path/to/scripts/llama-swap-autoscan.py
ExecStart=/home/mp/llama-swap -config /home/mp/.config/llama-swap/config.yaml --listen :11435
Restart=on-failure
RestartSec=5
Environment=PATH=/usr/local/cuda/bin:/usr/local/bin:/usr/bin:/bin
Environment=LD_LIBRARY_PATH=/usr/local/cuda/lib64

[Install]
WantedBy=default.target
```

```bash
# Service steuern
systemctl --user enable llama-swap
systemctl --user start llama-swap
systemctl --user status llama-swap
journalctl --user -u llama-swap -f
```

### API-Endpunkte

| Endpoint | Beschreibung |
|---|---|
| `GET /v1/models` | Alle konfigurierten Modelle |
| `POST /v1/chat/completions` | Chat (OpenAI-kompatibel) |
| `GET /running` | Aktuell geladene Modelle |
| `POST /models/unload` | Modell manuell entladen |
| `GET /health` | Health Check |
| `GET /ui` | Web-UI fuer Monitoring |

---

## Automatische Modell-Erkennung (Autoscan)

Das Script `scripts/llama-swap-autoscan.py` erkennt automatisch neue GGUF-Modelle und konfiguriert sie fuer llama-swap. Es laeuft als `ExecStartPre` vor jedem llama-swap-Start.

### Was das Script macht

1. **Ollama-Manifests scannen** - Liest Ollama-Manifests aus System- und User-Pfaden, findet GGUF-Blobs und erstellt Symlinks mit beschreibenden Dateinamen in `~/models/`
   - Beispiel: `sha256-6335adf...` -> `Qwen3-14B-Q8_0.gguf`
   - Deduplizierung: Bei mehreren Tags fuer denselben Blob wird der laengste/beschreibendste Name gewaehlt
   - Embedding-Modelle (BERT, nomic, etc.) werden uebersprungen
2. **Neue GGUFs erkennen** - Vergleicht `~/models/*.gguf` mit bestehenden Eintraegen in der llama-swap Config
3. **llama-swap Config erweitern** - Fuer jedes neue Modell wird ein YAML-Block angehaengt mit Default-Parametern (`-ngl 99`, `--flash-attn on`, `-ctk q8_0 -ctv q8_0`, etc.)
4. **VRAM-Cache vorbereiten** - Minimale Eintraege in `data/model_vram_cache.json` anlegen (Kalibrierung erfolgt spaeter ueber die AIfred-UI)

### Manuell ausfuehren

```bash
python scripts/llama-swap-autoscan.py
```

### Typische Ausgabe

```
=== llama-swap Autoscan ===
Scanning Ollama models...
  + Symlink: Qwen3-14B-Q8_0.gguf -> sha256-6335adf...
  = Exists:  Qwen3-8B-Q4_K_M.gguf
  ~ Skip:    nomic-embed-text-v2-moe (embedding model)
Scanning ~/models/ for new GGUFs...
  Found 6 GGUFs, 1 new
Updating llama-swap config...
  + Added: Qwen3-14B-Q8_0 (native context: 40960)
Updating VRAM cache...
  + Added: Qwen3-14B-Q8_0
Done. 1 new model(s) added.
```

### Konfiguration

Die Konstanten stehen am Anfang des Scripts:

| Konstante | Default | Beschreibung |
|---|---|---|
| `MODELS_DIR` | `~/models/` | Verzeichnis fuer GGUF-Dateien und Symlinks |
| `OLLAMA_PATHS` | System + User | Ollama-Model-Verzeichnisse |
| `LLAMASWAP_CONFIG` | `~/.config/llama-swap/config.yaml` | llama-swap Konfigurationsdatei |
| `LLAMA_SERVER_BIN` | `~/llama.cpp/build/bin/llama-server` | Pfad zur llama-server Binary |
| `DEFAULT_TTL` | 300 | Inaktivitaets-Timeout in Sekunden |
| `DEFAULT_FLAGS` | `--flash-attn on -ctk q8_0 -ctv q8_0 -np 1 -t 4 --mlock` | Standard-Parameter |

---

## AIfred Integration

llama-swap ist OpenAI-kompatibel. In AIfred wird es als eigenes Backend registriert:

- Backend-Typ: `llamacpp`
- URL: `LLAMACPP_URL` ENV oder `http://localhost:11435/v1`
- API-Key: Dummy (lokaler Service)
- Modell-Name in AIfred = Modell-Key in llama-swap Config
- Config-Pfad: `~/.config/llama-swap/config.yaml` (XDG-Standard)

---

## Quellen

- [llama.cpp GitHub](https://github.com/ggml-org/llama.cpp)
- [llama-swap GitHub](https://github.com/mostlygeek/llama-swap)
- [ik_llama.cpp (Graph Parallel)](https://github.com/ikawrakow/ik_llama.cpp)
- [NVIDIA CUDA Graphs Blog](https://developer.nvidia.com/blog/optimizing-llama-cpp-ai-inference-with-cuda-graphs/)
- [NVIDIA RTX LLM Acceleration](https://developer.nvidia.com/blog/open-source-ai-tool-upgrades-speed-up-llm-and-diffusion-models-on-nvidia-rtx-pcs)
- [LocalScore.ai Benchmarks](https://www.localscore.ai)
- [llama.cpp Multi-GPU Discussion](https://github.com/ggml-org/llama.cpp/discussions/15013)
- [eGPU LLM Performance Impact](https://egpu.io/forums/pro-applications/impact-of-egpu-connection-speed-on-local-llm-inference-in-multi-egpu-setups/)
- [FA on Pascal: Issue #19020](https://github.com/ggml-org/llama.cpp/issues/19020) - FA ist modellabhaengig, bei Qwen3 schneller
- [FA Pascal Implementation: PR #7188](https://github.com/ggerganov/llama.cpp/pull/7188) - FA ohne Tensor Cores
- [Ollama KV-Quant](https://smcleod.net/2024/12/bringing-k/v-context-quantisation-to-ollama/) - Q8/Q4 KV in Ollama
- [FA + P40 Gibberish Fix: Issue #7400](https://github.com/ggml-org/llama.cpp/issues/7400) - MoE+FA Bug, gefixt
