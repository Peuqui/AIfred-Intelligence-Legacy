# Reddit Post Draft — r/LocalLLaMA Benchmark Follow-Up

**Title:** AIfred Intelligence benchmarks: 9 models debating "Dog vs Cat" in multi-agent tribunal — quality vs speed across 80B-235B (AIfred with upper "I" instead of lower "L" :-)

---

Hey r/LocalLLaMA,

Some of you might remember [my post from New Year's](https://www.reddit.com/r/LocalLLaMA/comments/...) about AIfred Intelligence — the self-hosted AI assistant with multi-agent debates, web research and voice interface. I promised model benchmarks back then. Here they are!

**What I did:** I ran the same question — "What is better, dog or cat?" — through AIfred's Tribunal mode across 9 different models. In Tribunal mode, AIfred (the butler) argues his case, then Sokrates (the philosopher) tears it apart, they go 2 rounds, and finally Salomo (the judge) delivers a verdict. 18 sessions total, both in German and English. All benchmarked through AIfred's built-in performance metrics.

**My setup has grown a bit since the last post :-)**

I added a third Tesla P40 via M.2 OCuLink, so the little MiniPC now runs 3x P40 + RTX 8000 = **~115 GB VRAM** across 4 GPUs. All models run fully GPU-resident through llama.cpp (via llama-swap) with Direct-IO and flash-attn. Zero CPU offload.

---

## The Speed Numbers

| Model | Active Params | Quant | TG tok/s | PP tok/s | TTFT | Full Tribunal |
|-------|--------------|-------|----------|----------|------|---------------|
| GPT-OSS-120B-A5B | 5.1B | Q8 | **~50** | **~649** | **~2s** | ~70s |
| Qwen3-Next-80B-A3B | 3B | Q4_K_M | ~31 | ~325 | ~9s | ~150s |
| MiniMax-M2.5.i1 | 10.2B | IQ3_M | ~22 | ~193 | ~10s | ~260s |
| Qwen3.5-122B-A10B | 10B | Q5_K_XL | ~21 | ~296 | ~12s | ~255s |
| Qwen3-235B-A22B | 22B | Q3_K_XL | ~11 | ~161 | ~18s | ~517s |
| MiniMax-M2.5 | 10.2B | Q2_K_XL | ~8 | ~51 | ~36s | ~460s |
| Qwen3-235B-A22B | 22B | Q2_K_XL | ~6 | ~59 | ~30s | — |
| GLM-4.7-REAP-218B | 32B | IQ3_XXS | **~2.3** | ~40 | **~70s** | gave up |

GPT-OSS at 50 tok/s with a 120B model is wild. The whole tribunal — 5 agent turns, full debate — finishes in about a minute. On P40s. I was surprised too.

---

## The Quality Numbers — This Is Where It Gets Really Interesting

I rated each model on Butler style (does AIfred sound like a proper English butler?), philosophical depth (does Sokrates actually challenge or just agree?), debate dynamics (do they really argue?) and humor.

| Model | Butler | Philosophy | Debate | Humor | **Overall** |
|-------|--------|-----------|--------|-------|-------------|
| Qwen3-Next-80B-A3B | 9.5 | 9.5 | 9.5 | 9.0 | **9.5/10** |
| Qwen3-235B-A22B Q3 | 9.0 | 9.5 | 9.5 | 8.5 | **9.5/10** |
| Qwen3.5-122B-A10B | 8.0 | 8.5 | 8.5 | 7.5 | **8.5/10** |
| MiniMax-M2.5.i1 IQ3 | 8.0 | 8.0 | 8.0 | 7.5 | **8.0/10** |
| Qwen3-235B-A22B Q2 | 7.5 | 8.0 | 7.5 | 7.5 | **7.5/10** |
| GPT-OSS-120B-A5B | 6.0 | 6.5 | 5.5 | 5.0 | **6.0/10** |
| GLM-4.7-REAP-218B | 1.0 | 2.0 | 2.0 | 0.0 | **2.0/10** |

**The big surprise:** Qwen3-Next-80B with only 3B active parameters matches the 235B model in quality — at 3x the speed. It's been my daily driver ever since. Can't stop reading the debates, honestly :-)

---

## Some Of My Favorite Quotes

These are actual quotes from the debates, generated through AIfred's multi-agent system. The agents really do argue — Sokrates doesn't just agree with AIfred, he attacks the premises.

**Qwen3-Next-80B (AIfred defending dogs, German):**
> "A dog greets you like a hero returning from war — even after an absence of merely three minutes."

**Qwen3-Next-80B (Sokrates, getting philosophical):**
> "Tell me: when you love the dog, do you love *him* — or do you love your own need for devotion?"

**Qwen3-235B (Sokrates, pulling out Homer):**
> "Even the poets knew this: Argos, faithful hound of Odysseus, waited twenty years — though beaten, starved, and near death — until his master returned. Tell me, AIfred, has any cat ever been celebrated for such fidelity?"

**Qwen3-235B (Salomo's verdict):**
> "If you seek ease, choose the cat. If you seek love that acts, choose the dog. And if wisdom is knowing what kind of love you need — then the answer is not in the animal, but in the depth of your own soul. *Shalom.*"

**And then there's GLM-4.7-REAP at IQ3_XXS quantization:**
> "Das ist, indeed, a rather weighty question, meine geschten Fe Herrenhelmhen."

"Geschten Fe Herrenhelmhen" is not a word in any language. Don't quantize 218B models to IQ3_XXS. Just don't :-)

---

## What I Learned

1. **Model size ≠ quality.** Qwen3-Next-80B (3B active) ties with Qwen3-235B (22B active) in quality. GPT-OSS-120B is the speed king but its debates read like a term paper.

2. **Quantization matters A LOT.** MiniMax at Q2_K_XL: 8 tok/s, quality 6.5/10. Same model at IQ3_M: 22 tok/s, quality 8.0/10. Almost 3x faster AND better. If you can afford the extra few GB, go one quant level up.

3. **The agents actually debate.** I was worried that using the same LLM for all three agents would just produce agreement. It doesn't. The 5-layer prompt system (identity + reasoning + multi-agent roles + task + personality) creates real friction. Sokrates genuinely attacks AIfred's position, the arguments evolve over rounds, and Salomo synthesizes rather than just splitting the difference.

4. **Speed champion ≠ quality champion.** GPT-OSS finishes a tribunal in ~70 seconds but scores 6/10 on quality. Qwen3-Next takes 150 seconds but produces debates I actually enjoy reading. For me, that's the better trade-off.

5. **Below Q3 quantization, large MoE models fall apart.** GLM at IQ3_XXS was completely unusable — invented words, 2.3 tok/s. Qwen3-235B at Q2 was functional but noticeably worse than Q3.

---

You can explore some of the exported debate sessions in browser:
🔗 **[Live Showcases](https://peuqui.github.io/AIfred-Intelligence/)** (being updated with the new model debates)

**GitHub**: https://github.com/Peuqui/AIfred-Intelligence

There's a lot of new features since my last post (sandboxed code execution, custom agents with long-term memory, EPIM database integration, voice cloning, and more). I'll do a separate feature update post soon. And I might also do a hardware post about my Frankenstein MiniPC setup — 4 GPUs hanging off a tiny box via OCuLink and USB4, with photos. It's not pretty, but it works 24/7 :-)

Happy to answer questions about the benchmarks, the setup, or anything else!

Best,
Peuqui
