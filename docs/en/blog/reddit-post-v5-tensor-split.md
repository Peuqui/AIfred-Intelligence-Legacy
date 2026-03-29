Tensor split optimization: 15% faster generation on asymmetric eGPU setup (RTX 8000 + P40, both PCIe 3.0 x4)

Hey r/LocalLLaMA,

Quick follow-up to my [model benchmark post](https://www.reddit.com/r/LocalLLaMA/comments/1s5yl2p/aifred_intelligence_benchmarks_9_models_debating/) on my [Frankenstein's Mini](https://www.reddit.com/r/LocalLLaMA/comments/1s69y2x/my_frankenstein_minipc_4_gpus_3x_p40_rtx_8000_120/) — this time about squeezing more speed out of an asymmetric multi-GPU setup by optimizing the tensor split ratio.

**The setup:** At that time it was: RTX 8000 (48 GB, USB4 eGPU) + Tesla P40 (24 GB, OCuLink eGPU), both running at PCIe 3.0 x4. Not exactly a server rack — it's a tiny AOOSTAR GEM 10 MiniPC with GPUs dangling off it via adapters. But it works.

**The problem:** With the default `-ts 2,1` split (67% on RTX 8000, 33% on P40), the P40 becomes the bottleneck during generation. The RTX 8000 has nearly 2x the memory bandwidth (672 vs 346 GB/s), so every token has to wait for the slower card to finish its share.

**The idea:** What if we push as many layers as possible onto the fast GPU and only keep the minimum on the P40? Trade context length for generation speed.

---

## The Test

I ran my multi-agent tribunal system (AIfred argues, Sokrates attacks, Salomo judges — 6 turns, 2 rounds) with the same question ("Ist Wasser nass?" / "Is water wet?") on the same model (Qwen3-Next-80B-A3B, Q4_K_M), comparing two configurations:

| | Speed (11:1) | Normal (2:1) |
|---|---|---|
| Tensor split | 92% on RTX 8000 | 67% on RTX 8000 |
| Context | 32K tokens | 262K tokens (native max) |
| KV cache | q4_0 | q4_0 |

The 11:1 ratio was found automatically by AIfred's VRAM calibration — binary search across 7 ratios in about 7 minutes.

---

## Results

### Generation Speed (the interesting part)

| Turn | Speed (11:1) | Normal (2:1) | Delta |
|------|-------------|-------------|-------|
| AIfred R1 | **33.4 tok/s** | 29.0 tok/s | **+15.2%** |
| Sokrates R1 | 33.8 tok/s | 29.5 tok/s | +14.6% |
| Salomo R1 | 32.2 tok/s | 28.0 tok/s | +15.0% |
| AIfred R2 | 18.8 tok/s | 20.5 tok/s | -8.3% |
| Sokrates R2 | 25.8 tok/s | 22.4 tok/s | +15.2% |
| Salomo R2 | 15.8 tok/s | 19.2 tok/s | -17.7% |

**Round 1: consistently 15% faster.** When context is small, minimizing layers on the slow GPU pays off big.

**Round 2: mixed results.** As context grows (~3000 tokens), attention computation starts to dominate. The advantage shrinks or even reverses depending on output length. R2 numbers have higher variance because the model is nondeterministic — output lengths differ between runs.

### Prompt Processing (PP)

| Avg across all turns | Speed (11:1) | Normal (2:1) |
|---|---|---|
| PP | 327.3 tok/s | 334.5 tok/s |

PP is ~2% slower with aggressive split. Makes sense — with 2:1, KV cache writes are spread across both GPUs in parallel. With 11:1, 92% of the writes go to one GPU. Small effect, but consistent.

### Overall

| Metric | Speed (11:1) | Normal (2:1) |
|--------|-------------|-------------|
| Total wall-clock | **113.5s** | 123.6s |
| Effective throughput | **27.2 tok/s** | 24.6 tok/s |
| Total tokens | 3,087 | 3,044 |

10 seconds faster for a full 6-turn debate. Not bad for changing one number :-)

---

## What I Learned

1. **Asymmetric GPUs benefit from aggressive tensor split.** If one GPU is significantly faster, push layers toward it. The slower GPU becomes a bottleneck during autoregressive generation (token-by-token, sequential). The less work it does per token, the faster you go.

2. **The advantage is real but context-dependent.** At small context (R1, <1K tokens): solid 15% speedup. At larger context (R2, ~3K tokens): it depends. For typical chat conversations that stay under 8K tokens, the speed variant wins consistently.

3. **PP (prompt processing) slightly prefers balanced split.** PP is a parallel operation — all layers process the prompt simultaneously, KV cache writes happen in parallel. Spreading layers evenly gives both GPUs work to do. But the difference is only 2%, so it doesn't offset the 15% generation gain.

4. **PCIe x4 is fine for tensor split with layer mode.** I was worried about bandwidth, but layer-split (`-sm layer`) only transfers ~8 KB per layer boundary per token. Even at PCIe 3.0 x4 (~3.9 GB/s), that's nothing. Row-split (`-sm row`) would be a different story — constant all-reduce over x4 would be brutal.

5. **Automate the calibration.** Finding the optimal split by hand is tedious (try ratio, wait for OOM, try again...). Binary search converges in 7 iterations. I built this into AIfred and it saves a lot of time — especially when switching between models that have different VRAM requirements.

---

## The Takeaway

If you're running mixed GPUs (especially with different memory bandwidths), don't just use the "obvious" split ratio. Try pushing more layers to the fast card. You'll lose some context capacity, but for most conversations you won't need 262K tokens anyway.

The two configurations live side-by-side in my llama-swap config:
- `qwen3-next-80b-a3b-instruct-q4_k_m` → 262K context, balanced
- `qwen3-next-80b-a3b-instruct-q4_k_m-speed` → 32K context, 15% faster

Both hot-swappable, model stays loaded, zero downtime. Best of both worlds.

**Full benchmark data:** [Tensor Split Benchmark on GitHub](https://github.com/Peuqui/AIfred-Intelligence/blob/main/docs/en/benchmarks/tensor-split.md)

**GitHub:** https://github.com/Peuqui/AIfred-Intelligence

Happy to answer questions about the setup, the calibration process, or eGPU shenanigans :-)

Best,
Peuqui
