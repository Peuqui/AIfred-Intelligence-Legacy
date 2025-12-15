# llama.cpp vs Ollama - Recherche-Ergebnis

**Datum:** 2025-12-15
**Kontext:** Evaluierung ob llama.cpp als zusätzliches Backend für AIfred sinnvoll wäre

## TL;DR

llama.cpp bietet mit `--n-cpu-moe` die Möglichkeit, MoE-Experten gezielt auf CPU-RAM auszulagern. Das ermöglicht:
- **Größere Modelle** (70B+) mit brauchbarem Context
- **Mehr Context** bei Modellen die knapp ins VRAM passen

Für unser aktuelles Setup (2x P40, 48GB VRAM, 32GB RAM) bringt es wenig Mehrwert, da Qwen3-30B-A3B komplett ins VRAM passt.

---

## Der Killer-Feature: `--n-cpu-moe`

```bash
./llama-server \
  --model Qwen3-30B-A3B-Q8_0.gguf \
  --n-gpu-layers 99 \
  --n-cpu-moe 12 \        # 12 Expert-Layer auf CPU-RAM
  --ctx-size 110592 \
  --flash-attn \
  --jinja
```

### Wie funktioniert es?

Bei MoE-Modellen (Qwen3-30B-A3B: 30B Parameter, nur 3B aktiv pro Token):
- **Alle 30B Parameter** müssen normalerweise ins VRAM
- Aber nur **2-8 Experten** werden pro Token aktiviert
- Rest sitzt ungenutzt im VRAM

Mit `--n-cpu-moe`:
- Attention-Layer bleiben auf GPU (werden immer gebraucht)
- Experten-Weights liegen im CPU-RAM
- Nur kleine Aktivierungsvektoren (~KB) gehen über PCIe

### Performance-Benchmarks

| Modell | Ohne MoE-Offload | Mit `--n-cpu-moe` | Gewinn |
|--------|------------------|-------------------|--------|
| GPT-OSS 120B (RTX 3090) | 0.9 tok/s | 1.6 tok/s | +78% |
| GPT-OSS 120B (RTX 5090) | 3.4 tok/s | 8+ tok/s | +135% |

**Wichtig:** Der Speedup kommt daher, dass weniger Daten über PCIe müssen - nicht weil CPU schneller wäre.

---

## Vergleich llama.cpp vs Ollama

| Aspekt | llama.cpp | Ollama |
|--------|-----------|--------|
| **MoE-Expert-Offload** | `--n-cpu-moe` | Nicht möglich |
| **Tensor-Kontrolle** | `--override-tensor` (granular) | Automatisch |
| **VRAM-Kontrolle** | Präzise steuerbar | Black Box |
| **Setup** | Manuell, komplex | Einfach |
| **API** | OpenAI-kompatibel | OpenAI-kompatibel |
| **Overhead** | Keiner (direkt) | Wrapper-Layer |

### Selektives Tensor-Offloading

```bash
# Alle Expert FFN auf CPU
-ot ".ffn_.*_exps.=CPU"

# Nur bestimmte Layer
-ot "blk.{50-60}.ffn_.*_exps=CPU"

# Spezifische Tensoren
--override-tensor "blk.0.ffn_gate_exps.weight=CPU"
```

---

## Relevanz für unser Setup

### Aktuell: 2x P40 (48GB VRAM), 32GB RAM

| Modell | Status | Context |
|--------|--------|---------|
| Qwen3-30B-A3B Q8 (~30GB) | Passt komplett | 108K |
| 70B Q4 (~42GB) | Passt, aber... | 2-4K (unbrauchbar) |

### Mit llama.cpp MoE-Offload:

| Modell | Offload | Context | Problem |
|--------|---------|---------|---------|
| 30B | Nicht nötig | 108K | - |
| 30B + Offload | ~15GB auf CPU | ~150K | 32GB RAM wird knapp |
| 70B + Offload | ~20GB auf CPU | ~16-32K | 32GB RAM zu wenig |

### Fazit für uns:

Mit **32GB RAM** ist der Spielraum begrenzt:
- 30B läuft perfekt auf GPU (Ollama reicht)
- 70B würde am RAM scheitern, nicht am VRAM

**Interessant wird llama.cpp bei:**
- 64GB+ RAM → dann 70B Modelle mit Offload möglich
- Modelle die knapp nicht ins VRAM passen

---

## Neueste llama.cpp Releases (14-15. Dez 2025)

- **b7406:** SYCL-Support für MXFP4
- **b7405:** Audio/Speech Recognition (GLM-ASR)
- **b7404:** Preset-Argument-Handling
- **Vulkan:** Non-pow2 n_experts in topk_moe (flexible Expert-Anzahlen)

---

## Mögliche Implementierung als AIfred Backend

```python
# aifred/backends/llamacpp.py
class LlamaCppBackend(BaseBackend):
    def __init__(self, config):
        self.server_url = config.get("url", "http://localhost:8080")
        self.n_cpu_moe = config.get("n_cpu_moe", 0)
        # OpenAI-kompatible API

    async def chat_completion(self, messages, **kwargs):
        # Gleiche API wie Ollama
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.server_url}/v1/chat/completions",
                json={"messages": messages, **kwargs}
            ) as resp:
                # Streaming response handling
```

**Aufwand:** Gering, da API OpenAI-kompatibel ist. Hauptarbeit wäre Server-Management (Start/Stop/Config).

---

## Quellen

- https://github.com/ggerganov/llama.cpp
- https://dev.to/someoddcodeguy/understanding-moe-offloading-5co6
- https://medium.com/@david.sanftenberg/gpu-poor-how-to-configure-offloading-for-the-qwen-3-235b-a22b-moe-model-using-llama-cpp
- https://www.arsturn.com/blog/ollama-vs-llama-cpp-which-should-you-use-for-local-llms
