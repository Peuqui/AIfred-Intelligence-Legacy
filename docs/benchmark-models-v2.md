# Benchmark Model Overview — Dog vs Cat Tribunal

## Models Under Test

| Model | Total | Active | Type | Quant | Experts (total/used) | GGUF Size |
|-------|-------|--------|------|-------|---------------------|-----------|
| Qwen3-8B | 8B | 8B | Dense | Q8 | — | ~9 GB |
| GPT-OSS-120B-A5B | 120B | 5.1B | MoE | Q8_K | 128/4 | 60 GB |
| Qwen3.5-122B-A10B | 122B | 10B | MoE | Q5_K | 256/8 | 86 GB |
| MiniMax-M2.5 | 228B | 10.2B | MoE | IQ3_M | 256/8 | 93 GB |
| Qwen3-235B-A22B | 235B | 22B | MoE | Q3_K | 128/8 | 97 GB |

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
