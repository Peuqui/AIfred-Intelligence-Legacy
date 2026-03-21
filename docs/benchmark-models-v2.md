# Benchmark Model Overview — Dog vs Cat Tribunal

## Models Under Test

| Model | Total | Active | Type | Quant | Experts | GGUF Size | Context (calibrated) | Context (native) |
|-------|-------|--------|------|-------|---------|-----------|---------------------|------------------|
| Qwen3-8B | 8B | 8B | Dense | Q8 | — | ~9 GB | 262K | 262K |
| GPT-OSS-120B-A5B | 120B | 5.1B | MoE | Q8_K | 128/4 | 60 GB | 131K | 131K |
| Qwen3.5-122B-A10B | 122B | 10B | MoE | Q5_K | 256/8 | 86 GB | 262K | 262K |
| MiniMax-M2.5 | 228B | 10.2B | MoE | IQ3_M | 256/8 | 93 GB | 101K | 197K |
| Qwen3-235B-A22B | 235B | 22B | MoE | Q3_K | 128/8 | 97 GB | 112K | 262K |

All models run **GPU-only** (no CPU offload) on 117 GB VRAM.
MiniMax and Qwen3-235B have reduced context windows because the large GGUF files (93-97 GB) leave less VRAM for KV cache.

## Test Setup

- **Hardware**: AOOSTAR GEM 10 MiniPC, 32GB RAM
  - 2x Tesla P40 (24GB each) via OCuLink
  - 1x Quadro RTX 8000 (48GB) via USB4
  - Total: ~117 GB VRAM
- **Backend**: llama.cpp via llama-swap, Direct-IO
- **Task**: "Was ist besser, Hund oder Katze?" / "What is better, dog or cat?"
- **Mode**: Tribunal (AIfred → Sokrates R1 → AIfred R2 → Sokrates R2 → Salomo Verdict)
- **Languages**: German + English (same question, same model)

## Metrics Per Run

- TTFT (Time to First Token)
- PP (Prompt Processing) tok/s
- TG (Token Generation) tok/s
- Total inference time
- Total tokens generated
- Quality assessment (argumentation depth, personality consistency, verdict quality)

## Results

*(To be filled after running benchmarks)*

### German Results

| Model | TTFT | PP tok/s | TG tok/s | Inference | Tokens | Quality |
|-------|------|----------|----------|-----------|--------|---------|
| Qwen3-8B | | | | | | |
| GPT-OSS-120B-A5B | | | | | | |
| Qwen3.5-122B-A10B | | | | | | |
| MiniMax-M2.5 | | | | | | |
| Qwen3-235B-A22B | | | | | | |

### English Results

| Model | TTFT | PP tok/s | TG tok/s | Inference | Tokens | Quality |
|-------|------|----------|----------|-----------|--------|---------|
| Qwen3-8B | | | | | | |
| GPT-OSS-120B-A5B | | | | | | |
| Qwen3.5-122B-A10B | | | | | | |
| MiniMax-M2.5 | | | | | | |
| Qwen3-235B-A22B | | | | | | |
