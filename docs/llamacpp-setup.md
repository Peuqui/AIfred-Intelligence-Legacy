# llama.cpp + llama-swap Setup Guide

Referenzdokument fuer die llama.cpp Integration in AIfred via llama-swap.
Wird bei Hardware-Aenderungen oder neuen llama.cpp Releases aktualisiert.

**Stand:** 2026-02-16

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
| Flash Attention | ~15% Throughput-Steigerung | Nein (FP16 Penalty) | Ja | Ja |
| GPU Token Sampling | Eliminiert CPU-GPU Transfers | Ja | Ja | Ja |
| Model Loading | bis 65% schneller | Ja | Ja | Ja |
| FP8 W8A16 | Weight-only FP8 | Nein | Ja (vLLM) | Ja (Marlin) |
| NVFP4 | Neue Quantisierung | Nein | Nein | Nein |
| vLLM kompatibel | CC >= 7.0 noetig | Nein | Ja | Ja |

### Benchmark-Vergleich (Q4_K_M, Token Generation)

| Modell | P40 (tok/s) | RTX 8000 (tok/s) | 3090 Ti (tok/s) |
|---|---|---|---|
| ~8B | ~41 | ~74 | ~98 |
| ~14B | ~16 | ~43 | ~56 |
| ~30B MoE | - | ~34 | - |
| ~70B Q4 | Passt nicht (24GB) | ~10 (passt in 48GB) | Passt nicht (24GB) |

---

## Performance-Parameter

### Alle relevanten llama-server Flags

| Parameter | Syntax | Default | Beschreibung |
|---|---|---|---|
| `-ngl` | `-ngl 99` / `-ngl auto` | `auto` | Layer auf GPU offloaden |
| `-c` | `-c 8192` | aus Modell | Context-Groesse (KV-Cache skaliert linear) |
| `-fa` | `-fa` / `--no-fa` | `auto` | Flash Attention (global, nicht per GPU!) |
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
| `-np` | `-np 1` | `1` | Parallel Slots (Multi-User) |
| `-dev` | `-dev CUDA0,CUDA1` | | Explizite GPU-Auswahl |
| `-ot` | `-ot "regex=DEVICE"` | | Override Tensor (ik_llama.cpp) |

### Umgebungsvariablen

```bash
export CUDA_DEVICE_ORDER=PCI_BUS_ID    # Konsistente GPU-Reihenfolge
export GGML_CUDA_GRAPH_OPT=1           # 10-15% schnellere Token-Gen
```

### KV-Cache Quantisierung

| Typ | VRAM-Ersparnis vs f16 | Qualitaets-Impact | Hinweis |
|---|---|---|---|
| `q8_0` | ~50% | Vernachlaessigbar | Empfohlen |
| `q4_0` | ~75% | Spuerbar bei Keys | Nur `-ctv q4_0` nutzen |
| `f16` | Baseline | Kein | Standard |

**Wichtig:** KV-Cache Quantisierung benoetigt Flash Attention (`-fa`).

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

### Flash Attention Dilemma

FA ist global. Die P40 verliert ~50% Prompt-Processing-Speed mit FA, die RTX 8000 gewinnt ~15%.

**Empfehlung:** FA einschalten und die meisten Layer auf die RTX 8000 legen (z.B. `-ts 0.3,1`).
Dann betrifft der FA-Penalty nur die wenigen P40-Layer, und der Gesamtdurchsatz steigt.
KV-Cache Quantisierung (`-ctk q8_0 -ctv q8_0`) wird dadurch auch moeglich.

### Tensor-Split Empfehlungen

```bash
# P40 (GPU0) + RTX 8000 (GPU1)
# Standard: P40 ~28%, RTX 8000 ~72%
-ts 1,2.5

# Aggressiv: P40 nur VRAM-Erweiterung ~9%
-ts 0.1,1

# 2x RTX 8000 (gleich stark): Gleich verteilen
-ts 1,1
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
      -c 16384 -fa -ctk q8_0 -ctv q8_0
      -b 2048 -ub 512 --mlock
      --port ${PORT}
    ttl: 300  # 5min Inaktivitaet -> entladen

  llama3-70b:
    cmd: >
      llama-server -m /models/llama3-70b-Q4_K_M.gguf
      -ngl 99 -sm layer --tensor-split 1,2.5 --main-gpu 1
      -c 8192 -fa -ctk q8_0 -ctv q8_0
      --mlock --port ${PORT}
    ttl: 300

  # --- Kleine Modelle (nur RTX 8000) ---
  qwen3-8b:
    cmd: >
      llama-server -m /models/Qwen3-8B-Q4_K_M.gguf
      -ngl 99 -dev CUDA1
      -c 32768 -fa -ctk q8_0 -ctv q8_0
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
      -c 16384 -fa -ctk q8_0 -ctv q8_0
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
# llama-swap starten
CUDA_DEVICE_ORDER=PCI_BUS_ID GGML_CUDA_GRAPH_OPT=1 \
  llama-swap --config llama-swap.yaml --listen :8080
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

## AIfred Integration

llama-swap ist OpenAI-kompatibel. In AIfred wird es als eigenes Backend registriert:

- Backend-Typ: `llamacpp`
- URL: `LLAMACPP_URL` ENV oder `http://localhost:8080/v1`
- API-Key: Dummy (lokaler Service)
- Modell-Name in AIfred = Modell-Key in llama-swap Config

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
