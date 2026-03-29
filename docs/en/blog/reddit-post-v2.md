# Reddit Post Draft — r/LocalLLaMA Follow-Up

**Title:** AIfred Intelligence v2.59 — Custom Agents, Long-Term Memory, 235B models on 117GB VRAM (3-month update) (AIfred with upper "I" instead of lower "L" :-)

---

Hey r/LocalLLaMA,

Some of you might remember my post from New Year's where I shared AIfred Intelligence — the self-hosted AI assistant with multi-agent debates and web research. Back then I was running 2x Tesla P40 (48GB total) with 30B models.

Well... things got a bit out of hand since then :-) Here's what happened in 3 months.

**Hardware first:** I squeezed an RTX 8000 (48GB) via USB4 into the mix. So the little MiniPC now has ~117GB VRAM across 3 GPUs. Sounds crazy, but it works! This lets me run **Qwen3-235B** fully GPU-resident. The quality jump from 30B to 235B is... just wow. The multi-agent debates became genuinely sophisticated — AIfred argues with historical references, Sokrates throws in actual philosophical frameworks, and Salomo delivers verdicts that make you think. Can't stop reading these debates sometimes :-)

**Biggest new feature: Agent Memory.** The agents now remember stuff across sessions! Each one gets a persistent ChromaDB collection. They store insights on their own (via function calling) and when you start a new chat, relevant memories get pulled in automatically. You can also hit the "Pin" button to manually save a conversation summary — it goes to ALL agents who participated.

I built a Memory Browser right into the UI so I can actually see what's in the vector database. No more black box.

**Custom Agents.** You can now create your own agents — give them a name, an emoji, a personality, multilingual prompts. They participate in debates, can be addressed by name, and get their own memory. I built a "Pater Tuck" (medieval friar) who delivers sermons and spiritual counsel. He actually stores his sermons in his own memory. It's hilarious and heartwarming at the same time.

**Switched to llama.cpp** (via [llama-swap](https://github.com/mostlygeek/llama-swap)) as primary backend. Game changer. Direct-IO speeds up model loading significantly — the model file is memory-mapped almost instantly, though the full initialization (KV cache allocation etc.) still takes maybe 20-30 seconds for large models before the first token comes. Still way faster than the 60-90 seconds without Direct-IO. Plus automatic 3-phase calibration that figures out the best GPU split, context size, and KV quantization for each model. Calibrate once, never think about it again.

**RPC Distributed Inference.** llama.cpp RPC connects the MiniPC GPUs with my dev machine's RTX 3090 Ti over direct Ethernet. That's 141GB combined VRAM when I need it. Running 235B dense models (not MoE) fully on GPU — no CPU offload, proper speed.

**Voice Cloning.** On top of the existing TTS engines (Edge TTS, Piper, espeak), I added three new ones with voice cloning support: XTTS v2 (clone any voice from a 6-second sample), MOSS-TTS 1.7B (higher quality but needs more VRAM), and DashScope Qwen3-TTS (cloud streaming). Each agent can have its own voice now — AIfred sounds different from Sokrates. Gapless playback during inference, no awkward pauses.

**UI got a facelift too.** Active agent toggle (pill buttons), research mode pills, LLM parameters as floating popover, mobile-friendly icon buttons. The agent editor now has two tabs: one for managing agents, one for browsing the memory database.

Updated showcases with the bigger models are coming — I want to redo the classic "Dog vs Cat" debate and the Code Review with 235B. Stay tuned for that.

**Coming up in Part 2:** Model benchmarks! Same "Dog vs Cat" debate across different model sizes (8B → 30B → 70B → 235B), local vs RPC distributed inference speeds, and audio samples of the different TTS voices with embedded playback. Stay tuned.

**Already working:**
- Session pinning (manual via "Pin" button — LLM summary stored for all participating agents)
- Combined recall (10 most recent + semantic search, deduplicated)
- Cross-agent memory — agents write to their own collection but session summaries go to all participants

**On the roadmap:**
- Explicit time-window queries ("what did we discuss last Tuesday?" → date-filtered recall)
- Auto-pinning based on conversation quality/length (no manual button needed)

**GitHub**: https://github.com/Peuqui/AIfred-Intelligence

🔗 **[Live Example Showcases](https://peuqui.github.io/AIfred-Intelligence/)** (being updated with new models soon)

Still running 100% local. Still Python/Reflex. Still having way too much fun with this :-)

Happy to answer questions!

Best,
Peuqui

---

*Previous post: [I built AIfred-Intelligence - a self-hosted AI assistant with automatic web research and multi-agent debates](https://www.reddit.com/r/LocalLLaMA/comments/...)*
