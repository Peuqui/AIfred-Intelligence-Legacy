**🌍 Languages:** [English](README.md) | [Deutsch](README.de.md)

---

# 🎩 AIfred Intelligence - Advanced AI Assistant

**AI Assistant with Multi-LLM Support, Web Research & Voice Interface**

AIfred Intelligence is an advanced AI assistant with automatic web research, multi-model support, and history compression for unlimited conversations.

For version history and recent changes, see [CHANGELOG.md](CHANGELOG.md).

**📺 [View Example Showcases](https://peuqui.github.io/AIfred-Intelligence/)** - Exported chats (via Share Chat button) showcasing Multi-Agent debates, Chemistry, Math, Coding, and Web Research.

---

## ✨ Features

### 🎯 Core Features
- **Multi-Backend Support**: Ollama (GGUF), vLLM (AWQ), TabbyAPI (EXL2), KoboldCPP (GGUF), **Cloud APIs** (Qwen, DeepSeek, Claude)
- **Vision/OCR Support**: Image analysis with multimodal LLMs (DeepSeek-OCR, Qwen3-VL, Ministral-3)
- **Image Crop Tool**: Interactive crop before OCR/analysis (8-point handles, 4K auto-resize)
- **3-Model Architecture**: Specialized Vision-LLM for OCR, Main-LLM for interpretation
- **Thinking Mode**: Chain-of-Thought reasoning for complex tasks (Qwen3, NemoTron, QwQ - Ollama + vLLM)
- **Automatic Web Research**: AI decides autonomously when research is needed
- **History Compression**: Intelligent compression at 70% context utilization
- **Automatic Context Calibration**: VRAM-aware context sizing with RoPE scaling (1.0x, 1.5x, 2.0x), hybrid mode for oversized models (CPU offload)
- **Voice Interface**: Configurable STT (Whisper) and TTS (Edge TTS, **XTTS v2 Voice Cloning**, Piper, espeak) with multiple voices, pitch control, smart filtering (code blocks, tables, LaTeX formulas excluded from speech), **per-agent voice settings**, **Multi-Agent TTS Queue** (sequential playback of agent responses)
- **Vector Cache**: ChromaDB with multilingual Ollama embeddings (nomic-embed-text-v2-moe, CPU-only)
- **Per-Backend Settings**: Each backend remembers its preferred models (including Vision-LLM)
- **User Authentication**: Username + password login with whitelist-based registration, admin CLI for user management
- **Session Persistence**: Chat history tied to user accounts, accessible from any device after login
- **Session Management**: Chat list sidebar with LLM-generated titles, switch between sessions, delete old chats
- **Share Chat**: Export conversation as portable HTML file in new browser tab (KaTeX fonts embedded inline, works offline)
- **HTML Preview**: AI-generated HTML code opens directly in browser (new tab)
- **LaTeX & Chemistry**: KaTeX for math formulas, mhchem extension for chemistry (`\ce{H2O}`, reactions, structure formulas)
- **Multi-Agent Debate System**: AIfred + Sokrates as critical discussion partner for improved answer quality

### 🎩 Multi-Agent Discussion Modes

AIfred supports various discussion modes with Sokrates (critic) and Salomo (judge):

| Mode | Flow | Who decides? |
|------|------|--------------|
| **Standard** | AIfred answers | — |
| **Critical Review** | AIfred → Sokrates (+ Pro/Contra) → STOP | User |
| **Auto-Consensus** | AIfred → Sokrates → Salomo (X rounds) | Salomo |
| **Tribunal** | AIfred ↔ Sokrates (X rounds) → Salomo | Salomo (Verdict) |

**Agents:**
- 🎩 **AIfred** - Butler & Scholar - answers questions (British butler style with subtle elegance)
- 🏛️ **Sokrates** - Critical Philosopher - questions & challenges using the Socratic method
- 👑 **Salomo** - Wise Judge - synthesizes arguments and makes final decisions

**Customizable Personalities:**
- All agent prompts are plain text files in `prompts/de/` and `prompts/en/`
- Personality can be toggled on/off in UI settings (keeps identity, removes style)
- 3-layer prompt system: Identity (who) + Personality (how, optional) + Task (what)
- Easily create your own agents or modify existing personalities
- **Multilingual**: Agents respond in the user's language (German prompts for German, English prompts for all other languages)

**Direct Agent Addressing** (NEW in v2.10):
- Address Sokrates directly: "Sokrates, what do you think about...?" → Sokrates answers with Socratic method
- Address AIfred directly: "AIfred, explain..." → AIfred answers without Sokrates analysis
- Supports STT transcription variants: "Alfred", "Eifred", "AI Fred"
- Works at sentence end too: "Great explanation. Sokrates." / "Well done. Alfred!"

**Intelligent Context Handling** (v2.10.2):
- Multi-Agent messages use `role: system` with `[MULTI-AGENT CONTEXT]` prefix
- Speaker labels `[SOKRATES]:` and `[AIFRED]:` preserved for LLM context
- Prevents LLM from confusing agent exchanges with its own responses
- All prompts automatically receive current date/time for temporal queries

**Perspective System** (v2.10.3):
- Each agent sees the conversation from their own perspective
- Sokrates sees AIfred's answers as `[AIFRED]:` (user role), his own as `assistant`
- AIfred sees Sokrates' critiques as `[SOKRATES]:` (user role), his own as `assistant`
- Prevents identity confusion between agents during multi-round debates

```
┌─────────────────────────────────────────┐
│          llm_history (stored)           │
│                                         │
│  [AIFRED]: "Answer 1"                   │
│  [SOKRATES]: "Critique"                 │
│  [AIFRED]: "Answer 2"                   │
└─────────────────────────────────────────┘
                    │
                    ▼
    ┌───────────────┼───────────────┐
    │               │               │
    ▼               ▼               ▼
┌─────────┐   ┌──────────┐   ┌─────────┐
│ AIfred  │   │ Sokrates │   │ Salomo  │
│  calls  │   │  calls   │   │  calls  │
└────┬────┘   └────┬─────┘   └────┬────┘
     │             │              │
     ▼             ▼              ▼
┌─────────┐   ┌──────────┐   ┌─────────┐
│assistant│   │  user    │   │  user   │
│"Answ 1" │   │[AIFRED]: │   │[AIFRED]:│
│  user   │   │assistant │   │  user   │
│[SOKR].. │   │"Critique"│   │[SOKR].. │
│assistant│   │  user    │   │  user   │
│"Answ 2" │   │[AIFRED]: │   │[AIFRED]:│
└─────────┘   └──────────┘   └─────────┘

One source, three views - depending on who is speaking.
Own messages = assistant (no label), others = user (with label).
```

**Structured Critic Prompts** (v2.10.3):
- Round number placeholder `{round_num}` - Sokrates knows which round it is
- Maximum 1-2 critique points per round
- Sokrates only critiques - never decides consensus (that's Salomo's job)

**Temperature Control** (v2.10.4):
- Auto mode: Intent-Detection determines base temperature (FACTUAL=0.2, MIXED=0.5, CREATIVE=1.1)
- Manual mode: Separate sliders for AIfred and Sokrates temperature
- Configurable Sokrates offset in Auto mode (default +0.2, capped at 1.0)
- All temperature settings in "LLM Parameters (Advanced)" collapsible

**Trialog Workflow (Auto-Consensus with Salomo):**
```
┌─────────────┐     ┌─────────────────┐     ┌─────────────────────┐
│   User      │────▶│   🎩 AIfred     │────▶│   🏛️ Sokrates       │
│   Query     │     │   + [LGTM/WEITER]│     │   + [LGTM/WEITER]  │
└─────────────┘     └─────────────────┘     └──────────┬──────────┘
                                                       │
                              ┌─────────────────────────┘
                              ▼
                    ┌─────────────────────┐
                    │   👑 Salomo         │
                    │   + [LGTM/WEITER]   │
                    └──────────┬──────────┘
                               │
               ┌───────────────┴───────────────┐
               ▼                               ▼
     ┌────────────────┐              ┌─────────────────┐
     │ 2/3 or 3/3     │              │ Not enough votes│
     │ = Consensus!   │              │ = Next Round    │
     └────────────────┘              └─────────────────┘
```

**Consensus Types (configurable in settings):**
- **Majority (2/3):** Two of three agents must vote `[LGTM]`
- **Unanimous (3/3):** All three agents must vote `[LGTM]`

**Tribunal Workflow:**
```
┌─────────────┐     ┌─────────────────────────────────────┐
│   User      │────▶│   🎩 AIfred ↔ 🏛️ Sokrates          │
│   Query     │     │   Debate for X Rounds               │
└─────────────┘     └──────────────────┬──────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │   👑 Salomo - Final Verdict         │
                    │   Weighs both sides, decides winner │
                    └─────────────────────────────────────┘
```

**Message Display Format:**

Each message is displayed individually with its emoji and mode label:

| Role | Agent | Display Format | Example |
|------|-------|----------------|---------|
| **User** | — | 🙋 {Username} (right-aligned) | 🙋 User: "What is Python?" |
| **Assistant** | `aifred` | 🎩 AIfred [{Mode} R{N}] (left-aligned) | 🎩 AIfred [Auto-Consensus: Refinement R2] |
| **Assistant** | `sokrates` | 🏛️ Sokrates [{Mode} R{N}] (left-aligned) | 🏛️ Sokrates [Tribunal: Critique R1] |
| **Assistant** | `salomo` | 👑 Salomo [{Mode} R{N}] (left-aligned) | 👑 Salomo [Tribunal: Verdict R3] |
| **System** | — | 📊 Summary (collapsible inline) | 📊 Summary #1 (5 Messages) |

**Mode Labels:**
- Standard responses: No label (clean display)
- Multi-Agent modes: `[{Mode}: {Action} R{N}]` format
  - Mode: `Auto-Consensus`, `Tribunal`, `Critical Review`
  - Action: `Refinement`, `Critique`, `Synthesis`, `Verdict`
  - Round: `R1`, `R2`, `R3`, etc.

**Examples:**
- Standard: `🎩 AIfred` (no label)
- Auto-Consensus R1: `🎩 AIfred [Auto-Consensus: Refinement R1]`
- Tribunal R2: `🏛️ Sokrates [Tribunal: Critique R2]`
- Final Verdict: `👑 Salomo [Tribunal: Verdict R3]`

**Prompt Files per Mode:**
| Mode | Agent | Prompt File | Mode Label | Display Example |
|------|-------|-------------|------------|-----------------|
| **Standard** | AIfred | `aifred/system_rag` or `system_minimal` | — | 🎩 AIfred |
| **Direct AIfred** | AIfred | `aifred/direct` | Direct Response | 🎩 AIfred [Direct Response] |
| **Direct Sokrates** | Sokrates | `sokrates/direct` | Direct Response | 🏛️ Sokrates [Direct Response] |
| **Critical Review** | Sokrates | `sokrates/critic` | Critical Review | 🏛️ Sokrates [Critical Review] |
| **Critical Review** | AIfred | `aifred/system_minimal` | Critical Review: Refinement | 🎩 AIfred [Critical Review: Refinement] |
| **Auto-Consensus** R{N} | Sokrates | `sokrates/critic` | Auto-Consensus: Critique R{N} | 🏛️ Sokrates [Auto-Consensus: Critique R2] |
| **Auto-Consensus** R{N} | AIfred | `aifred/system_minimal` | Auto-Consensus: Refinement R{N} | 🎩 AIfred [Auto-Consensus: Refinement R2] |
| **Auto-Consensus** R{N} | Salomo | `salomo/mediator` | Auto-Consensus: Synthesis R{N} | 👑 Salomo [Auto-Consensus: Synthesis R2] |
| **Tribunal** R{N} | Sokrates | `sokrates/critic` | Tribunal: Critique R{N} | 🏛️ Sokrates [Tribunal: Critique R1] |
| **Tribunal** R{N} | AIfred | `aifred/system_minimal` | Tribunal: Refinement R{N} | 🎩 AIfred [Tribunal: Refinement R1] |
| **Tribunal** Final | Salomo | `salomo/judge` | Tribunal: Verdict R{N} | 👑 Salomo [Tribunal: Verdict R3] |

**Note:** All prompts are in `prompts/de/` (German) and `prompts/en/` (English)

**UI Settings:**
- Sokrates-LLM and Salomo-LLM separately selectable (can be different models)
- Max debate rounds (1-10, default: 3)
- Discussion mode in Settings panel
- 💡 Help icon opens modal with all modes overview

**Thinking Support:**
- All agents (AIfred, Sokrates, Salomo) support Thinking Mode
- `<think>` blocks formatted as collapsibles

### 🔧 Technical Highlights
- **Reflex Framework**: React frontend generated from Python
- **WebSocket Streaming**: Real-time updates without polling
- **Adaptive Temperature**: AI selects temperature based on question type
- **Token Management**: Dynamic context window calculation
- **VRAM-Aware Context**: Automatic context sizing based on available GPU memory
- **Debug Console**: Comprehensive logging and monitoring
- **ChromaDB Server Mode**: Thread-safe vector DB via Docker (0.0 distance for exact matches)
- **GPU Detection**: Automatic detection and warnings for incompatible backend-GPU combinations ([docs/GPU_COMPATIBILITY.md](docs/GPU_COMPATIBILITY.md))
- **Ollama Context Calibration**: Intelligent per-model calibration with automatic hybrid mode detection
  - **VRAM Mode**: Binary search for models that fit completely in GPU memory (512 token precision)
  - **Hybrid Mode**: Binary search with RAM-based upper bound for CPU+GPU offload
    - Detects MoE vs Dense models (0.10 vs 0.15 MB/token ratio)
    - Fixed 3 GB RAM reserve to prevent swapping
    - Upper bound calculation: `(available_ram - 3GB) / ratio`
  - **Auto-Hybrid Threshold**: If VRAM-only yields < 16k tokens → switch to Hybrid mode
  - **Algorithm Flow**:
    ```
    1. Measure: Model size, free VRAM, free RAM
    2. Model > VRAM? → Hybrid Mode (CPU offload required)
    3. MoE Detection → ratio (0.10 MoE / 0.15 Dense)
    4. Calculate upper bound: (available_ram - 3GB) / ratio
    5. Binary search: min_context → upper_bound (512 token precision)
    6. Check RAM reserve after each test load
    7. VRAM-only result < 16k? → Switch to Hybrid, repeat 4-6
    8. Save calibration result (is_hybrid flag)
    ```
- **RoPE 2x Extended Context**: Optional extended calibration up to 2x native context limit
- **KoboldCPP Dynamic RoPE**: Intelligent VRAM-based context optimization with automatic RoPE scaling
- **Multi-User Queue**: KoboldCPP request queuing for concurrent users (up to 5 clients)
- **Parallel Web Search**: 2-3 optimized queries distributed in parallel across APIs (Tavily, Brave, SearXNG), automatic URL deduplication, optional self-hosted SearXNG
- **Parallel Scraping**: ThreadPoolExecutor scrapes 3-7 URLs simultaneously, first successful results are used
- **Failed Sources Display**: Shows unavailable URLs with error reasons (Cloudflare, 404, Timeout) - persisted in Vector Cache for cache hits
- **PDF Support**: Direct extraction from PDF documents (AWMF guidelines, PubMed PDFs) via PyMuPDF with browser-like User-Agent

### ☁️ Cloud API Support

AIfred supports cloud LLM providers via OpenAI-compatible APIs:

| Provider | Models | API Key Variable |
|----------|--------|------------------|
| **Qwen (DashScope)** | qwen-plus, qwen-turbo, qwen-max | `DASHSCOPE_API_KEY` |
| **DeepSeek** | deepseek-chat, deepseek-reasoner | `DEEPSEEK_API_KEY` |
| **Claude (Anthropic)** | claude-3.5-sonnet, claude-3-opus | `ANTHROPIC_API_KEY` |
| **Kimi (Moonshot)** | moonshot-v1-8k, moonshot-v1-32k | `MOONSHOT_API_KEY` |

**Features:**
- Dynamic model fetching (models loaded from provider's `/models` endpoint)
- Token usage tracking (prompt + completion tokens displayed in debug console)
- Per-provider model memory (each provider remembers its last used model)
- Vision model filtering (excludes `-vl` variants from main LLM dropdown)
- Streaming support with real-time output

**Note:** Cloud APIs don't require local GPU resources - ideal for:
- Testing larger models without hardware investment
- Mobile/laptop usage without dedicated GPU
- Comparing cloud vs local model quality

### ⚠️ Model Recommendations
- **Automatik-LLM** (Intent Detection, Query Optimization, Addressee Detection): Medium instruct models recommended
  - **Recommended**: `qwen3:14b` (Q4 or Q8 quantization)
  - Better semantic understanding for complex addressee detection ("What does Alfred think about Salomo's answer?")
  - Small 4B models may struggle with nuanced sentence semantics
  - Thinking mode is automatically disabled for Automatik tasks (fast decisions)
- **Main LLM**: Use larger models (14B+, ideally 30B+) for better context understanding and prompt following
  - Both Instruct and Thinking models work well
  - Enable "Thinking Mode" for chain-of-thought reasoning on complex tasks
  - **Language Note**: Small models (4B-14B) may respond in English when RAG context contains predominantly English web content, even with German prompts. Models 30B+ reliably follow language instructions regardless of context language.

---

## 🔄 Research Mode Workflows

AIfred offers 4 different research modes, each using different strategies depending on requirements. Here's the detailed workflow for each mode:

### 📊 LLM Calls Overview

| Mode | Min LLM Calls | Max LLM Calls | Typical Duration |
|------|---------------|---------------|------------------|
| **Own Knowledge** | 1 | 1 | 5-30s |
| **Automatik** (Cache Hit) | 0 | 0 | <1s |
| **Automatik** (Direct Answer) | 2 | 3 | 5-35s |
| **Automatik** (Web Research) | 4 | 5 | 15-60s |
| **Quick Web Search** | 3 | 4 | 10-40s |
| **Deep Web Search** | 3 | 4 | 15-60s |

---

### 🔄 Pre-Processing (all modes)

**Shared first step** for all Research modes:

```
Intent + Addressee Detection
├─ LLM Call (Automatik-LLM) - combined in one call
├─ Prompt: intent_detection
├─ Response: "FAKTISCH|sokrates" | "KREATIV|" | "GEMISCHT|aifred"
├─ Temperature usage:
│  ├─ Auto-Mode: FAKTISCH=0.2, GEMISCHT=0.5, KREATIV=1.0
│  └─ Manual-Mode: Intent ignored, manual value used
└─ Addressee: Direct agent addressing (sokrates/aifred/salomo)
```

When an agent is directly addressed, that agent is activated immediately, regardless of the selected Research mode or temperature setting.

---

### 1️⃣ Own Knowledge Mode (Direct LLM)

**Simplest mode**: Direct LLM call without web research or AI decision.

**Workflow:**
```
1. Message Building
   └─ Build from chat history
   └─ Inject system_minimal prompt (with timestamp)

2. Model Preloading (Ollama only)
   └─ backend.preload_model() - measures actual load time
   └─ vLLM/TabbyAPI: Skip (already in VRAM)

3. Token Management
   └─ estimate_tokens(messages, model_name)
   └─ calculate_dynamic_num_ctx()

4. LLM Call - Main Response
   ├─ Model: Main-LLM (e.g., Qwen2.5-32B)
   ├─ Temperature: Manual (user setting)
   ├─ Streaming: Yes (real-time updates)
   └─ TTFT + Tokens/s measurement

5. Format & Save
   └─ format_thinking_process() for <think> tags
   └─ Update chat history

6. History Compression (PRE-MESSAGE Check - BEFORE every LLM call)
   ├─ Trigger: 70% utilization of smallest context window
   │  └─ Multi-Agent: min_ctx of all agents is used
   ├─ Dual History: chat_history (UI) + llm_history (LLM, FIFO)
   └─ Summaries appear inline in chat where compression occurred
```

**LLM Calls:** 1 Main-LLM + optional 1 Compression-LLM (if >70% context)
**Async Tasks:** None
**Code:** `aifred/state.py` Lines 974-1117

---

### 2️⃣ Automatik Mode (AI Decision System)

**Most intelligent mode**: AI decides autonomously whether web research is needed.

#### Phase 1: Vector Cache Check
```
1. Query ChromaDB for similar questions
   └─ Distance < 0.5: HIGH Confidence → Cache Hit
   └─ Distance ≥ 0.5: CACHE_MISS → Continue

2. IF CACHE HIT:
   └─ Answer directly from cache
   └─ RETURN (0 LLM Calls!)
```

#### Phase 2: RAG Context Check
```
1. Query cache for RAG candidates (distance 0.5-1.2)

2. FOR EACH candidate:
   ├─ LLM Relevance Check (Automatik-LLM)
   │  └─ Prompt: rag_relevance_check
   │  └─ Options: temp=0.1, num_ctx=2048
   └─ Keep if relevant

3. Build formatted context from relevant entries
```

#### Phase 3: Keyword Override Check
```
1. Check for explicit research keywords:
   └─ "search", "google", "research on the internet", etc.

2. IF keyword found:
   └─ Trigger fresh web research (mode='deep' → 7 URLs)
   └─ BYPASS Automatik decision
```

#### Phase 4: Automatik Decision (Combined LLM Call)
```
1. LLM Call - Research Decision + Query Generation (combined)
   ├─ Model: Automatik-LLM (e.g., Qwen3:4B)
   ├─ Prompt: research_decision.txt
   │  ├─ Contains: Current date (for time-related queries)
   │  ├─ Vision context if images attached
   │  └─ Structured JSON output
   ├─ Messages: ❌ NO history (focused, unbiased decision)
   ├─ Options:
   │  ├─ temperature: 0.2 (consistent decisions)
   │  ├─ num_ctx: 4096 (AUTOMATIK_LLM_NUM_CTX)
   │  ├─ num_predict: 256
   │  └─ enable_thinking: False (fast)
   └─ Response: {"web": true, "queries": ["EN query", "DE query 1", "DE query 2"]}
              OR {"web": false}

2. Query Rules (if web=true):
   ├─ Query 1: ALWAYS in English (international sources)
   ├─ Query 2-3: In the language of the question
   └─ Each query: 4-8 keywords

3. Parse decision:
   ├─ IF web=true: → Web Research with pre-generated queries
   └─ IF web=false: → Direct LLM Answer (Phase 5)
```

**Why no history for Decision-Making?**
- Prevents bias from previous conversation context
- Decision based purely on current question + Vision data
- Ensures consistent, objective web research triggering

#### Phase 5: Direct LLM Answer (if decision = no)
```
1. Model Preloading (Ollama only)

2. Build Messages
   ├─ From chat history
   ├─ Inject system_minimal prompt
   └─ Optional: Inject RAG context (if found in Phase 2)

3. LLM Call - Main Response
   ├─ Model: Main-LLM
   ├─ Temperature: From Pre-Processing or manual
   ├─ Streaming: Yes
   └─ TTFT + Tokens/s measurement

4. Format & Update History
   └─ Metadata: "Cache+LLM (RAG)" or "LLM"

5. History Compression Check (same as Own Knowledge mode)
   └─ Automatic compression at >70% context utilization
```

**LLM Calls:**
- Cache Hit: 0 + optional 1 Compression
- RAG Context: 2-6 + optional 1 Compression
- Web Research: 4-5 + optional 1 Compression
- Direct Answer: 2-3 + optional 1 Compression

#### History & Context Usage Summary (Automatik Mode)

| LLM Call | Model | Chat History | Vision JSON | Temperature |
|----------|-------|--------------|-------------|-------------|
| Decision-Making | Automatik | ❌ No | ✅ In prompt | 0.2 |
| Query-Optimization | Automatik | ✅ Last 3 turns | ✅ In prompt | 0.3 |
| RAG-Relevance | Automatik | ✅ Indirect | ❌ No | 0.1 |
| Intent-Detection | Automatik | ❌ No | ❌ No | Internal |
| Main Response | Main-LLM | ✅ Full history | ✅ In context | Auto/Manual |

**Design Rationale:**
- **Decision-Making without history**: Unbiased decision based purely on current query
- **Query-Optimization with history**: Context-aware search for follow-up questions
- **Main-LLM with full history**: Complete conversation context for coherent responses

**Code:** `aifred/lib/conversation_handler.py`

---

### 3️⃣ Quick Web Search Mode (Quick Research)

**Fastest web research mode**: Scrapes top 3 URLs in parallel, optimized for speed.

#### Phase 1: Session Cache Check
```
1. Check session-based cache
   └─ IF cache hit: Use cached sources → Skip to Phase 4
   └─ IF miss: Continue to Phase 2
```

#### Phase 2: Query Optimization + Web Search
```
1. LLM Call - Query Optimization
   ├─ Model: Automatik-LLM
   ├─ Prompt: query_optimization (+ Vision JSON if present)
   ├─ Messages: ✅ Last 3 history turns (for follow-up context)
   ├─ Options:
   │  ├─ temperature: 0.3 (balanced for keywords)
   │  ├─ num_ctx: min(8192, automatik_limit)
   │  ├─ num_predict: 128 (keyword extraction)
   │  └─ enable_thinking: False
   ├─ Post-processing:
   │  ├─ Extract <think> tags (reasoning)
   │  ├─ Clean query (remove quotes)
   │  └─ Add temporal context (current year)
   └─ Output: optimized_query, query_reasoning

2. Web Search (Multi-API with Fallback)
   ├─ Try: Brave Search API
   ├─ Fallback: Tavily Search API
   ├─ Fallback: SearXNG (local instance)
   ├─ Each API returns up to 10 URLs
   └─ Deduplication across APIs
```

**Why history for Query-Optimization?**
- Enables context-aware follow-up queries (e.g., "Tell me more about that")
- Limited to 3 turns to keep prompt focused
- Vision JSON injected for image-based searches

#### Phase 2.5: URL Filtering + LLM-based Ranking (v2.15.30)
```
1. Non-Scrapable Domain Filter (BEFORE URL Ranking)
   ├─ Config: data/blocked_domains.txt (easy to edit, one domain per line)
   ├─ Filters video platforms: YouTube, Vimeo, TikTok, Twitch, Rumble, etc.
   ├─ Filters social media: Twitter/X, Facebook, Instagram, LinkedIn
   ├─ Reason: These sites cannot be scraped effectively
   ├─ Debug log: "🚫 Blocked: https://youtube.com/..."
   └─ Summary: "🚫 Filtered 6 non-scrapable URLs (video/social platforms)"

2. URL Ranking (Automatik-LLM)
   ├─ Input: ~22 URLs (after filtering) with titles and snippets
   ├─ Model: Automatik-LLM (num_ctx: 12K)
   ├─ Prompt: url_ranking.txt (EN only - output is numeric)
   ├─ Options:
   │  ├─ temperature: 0.0 (deterministic ranking)
   │  └─ num_predict: 100 (short response)
   ├─ Output: "3,7,1,12,5,8,2" (comma-separated indices)
   └─ Result: Top 7 (deep) or Top 3 (quick) URLs by relevance

3. Why LLM-based Ranking?
   ├─ Semantic understanding of query-URL relevance
   ├─ No maintenance of keyword lists or domain whitelists
   ├─ Adapts to any topic (universal)
   └─ Better than first-come-first-served ordering

4. Skip Conditions:
   ├─ Direct URL mode (user provided URLs directly)
   ├─ Less than top_n URLs found
   └─ No titles/snippets available (fallback to original order)
```

#### Phase 3: Parallel Web Scraping
```
PARALLEL EXECUTION:
├─ ThreadPoolExecutor (max 5 workers)
│  └─ Scrape Top 3/7 URLs (ranked by relevance)
│     └─ Extract text content + word count
│
└─ Async Task: Main LLM Preload (Ollama only)
   └─ llm_client.preload_model(model)
   └─ Runs parallel to scraping
   └─ vLLM/TabbyAPI: Skip (already loaded)

Progress Updates:
└─ Yield after each URL completion
```

**Scraping Strategy (trafilatura + Playwright Fallback):**
```
1. trafilatura (fast, lightweight)
   └─ Direct HTTP request, HTML parsing
   └─ Works for most static websites

2. IF trafilatura returns < 800 words:
   └─ Playwright fallback (headless Chromium)
   └─ Executes JavaScript, renders dynamic content
   └─ For SPAs: React, Vue, Angular sites

3. IF download failed (404, timeout, bot-protection):
   └─ NO Playwright fallback (pointless)
   └─ Mark URL as failed with error reason
```

The 800-word threshold is configurable via `PLAYWRIGHT_FALLBACK_THRESHOLD` in `config.py`.

#### Phase 4: Context Building + LLM Response
```
1. Build Context
   ├─ Filter successful scrapes (word_count > 0)
   ├─ build_context() - smart token limit aware
   └─ Build system_rag prompt (with context + timestamp)

2. LLM Call - Final Response
   ├─ Model: Main-LLM
   ├─ Temperature: From Pre-Processing or manual
   ├─ Context: ~3 sources, 5K-10K tokens
   ├─ Streaming: Yes
   └─ TTFT + Tokens/s measurement

3. Cache Decision (via Volatility Tag from Main LLM)
   ├─ Main LLM includes <volatility>DAILY/WEEKLY/MONTHLY/PERMANENT</volatility>
   ├─ Volatility determines TTL:
   │  ├─ DAILY (24h): News, current events
   │  ├─ WEEKLY (7d): Semi-current topics
   │  ├─ MONTHLY (30d): Statistics, reports
   │  └─ PERMANENT (∞): Timeless facts ("What is Python?")
   ├─ Semantic Duplicate Check (distance < 0.3 to existing entries)
   │  └─ IF duplicate: Delete old entry (ensures latest data)
   ├─ cache.add(query, answer, sources, metadata, ttl)
   └─ Debug: "💾 Answer cached (TTL: {volatility})"

4. Format & Update History
   └─ Metadata: "(Agent: quick, {n} sources)"

5. History Compression Check (same as Own Knowledge mode)
   └─ Automatic compression at >70% context utilization
```

**LLM Calls:**
- With Cache: 1-2 + optional 1 Compression
- Without Cache: 3-4 + optional 1 Compression

**Async Tasks:**
- Parallel URL scraping (3 URLs)
- Background LLM preload (Ollama only)

**Code:** `aifred/lib/research/orchestrator.py` + Submodules

---

### 4️⃣ Deep Web Search Mode (Deep Research)

**Most thorough mode**: Scrapes top 7 URLs in parallel for maximum information depth.

**Workflow:** Identical to Quick Web Search, with the following differences:

#### Scraping Strategy
```
URL Scraping (parallel via ThreadPoolExecutor):
├─ Quick Mode:  3 URLs scraped → ~3 successful sources
├─ Deep Mode:   7 URLs scraped → ~5-7 successful sources
└─ Automatik:   7 URLs scraped (uses deep mode)

Note: "APIs" refers to search APIs (Brave, Tavily, SearXNG)
      "URLs" refers to actual web pages being scraped

Parallel Execution:
├─ ThreadPoolExecutor (max 5 workers)
│  └─ Scrape Top 7 URLs simultaneously
│  └─ Continue until 5 successful OR all tried
│
└─ Async: Main LLM Preload (parallel)
```

#### Context Size
```
Quick: ~5K-10K tokens context
Deep:  ~10K-20K tokens context

→ More sources = richer context
→ Longer LLM inference (10-40s vs 5-30s)
```

**LLM Calls:** Identical to Quick (3-4 + optional 1 Compression)
**Async Tasks:** More parallel URLs (7 vs 3)
**Trade-off:** Higher quality vs longer duration
**History Compression:** Like all modes - automatic at >70% context

---

### 🔀 Decision Flow Diagram

```
USER INPUT
    │
    ▼
┌─────────────────────┐
│ Research Mode?      │
└─────────────────────┘
    │
    ├── "none" ────────────────────────┐
    │                                   │
    ├── "automatik" ──────────────┐   │
    │                              │   │
    ├── "quick" ──────────────┐  │   │
    │                          │  │   │
    └── "deep" ────────────┐  │  │   │
                           │  │  │   │
                           ▼  ▼  ▼   ▼
                      ╔═══════════════════╗
                      ║ MODE HANDLER      ║
                      ╚═══════════════════╝
                               │
     ┌─────────────────────────┼──────────────────────┐
     │                         │                      │
     ▼                         ▼                      ▼
┌──────────┐         ┌──────────────┐       ┌─────────────┐
│ OWN      │         │ AUTOMATIK    │       │ WEB         │
│ KNOWLEDGE│         │ (AI Decides) │       │ RESEARCH    │
└──────────┘         └──────────────┘       │ (quick/deep)│
     │                       │               └─────────────┘
     │                       ▼                      │
     │              ┌────────────────┐              │
     │              │ Vector Cache   │              │
     │              │ Check          │              │
     │              └────────────────┘              │
     │                       │                      │
     │          ┌────────────┼─────────────┐        │
     │          │            │             │        │
     │          ▼            ▼             ▼        │
     │     ┌────────┐  ┌─────────┐  ┌─────────┐   │
     │     │ CACHE  │  │ RAG     │  │ CACHE   │   │
     │     │ HIT    │  │ CONTEXT │  │ MISS    │   │
     │     │ RETURN │  │ FOUND   │  │         │   │
     │     └────────┘  └─────────┘  └─────────┘   │
     │                       │            │         │
     │                       │            ▼         │
     │                       │    ┌──────────────┐ │
     │                       │    │ Keyword      │ │
     │                       │    │ Override?    │ │
     │                       │    └──────────────┘ │
     │                       │         │     │      │
     │                       │         NO   YES     │
     │                       │         │     │      │
     │                       │         │     └──────┤
     │                       │         ▼            │
     │                       │   ┌──────────────────┐│
     │                       │   │ LLM Decision     ││
     │                       │   │ (Automatik-LLM)  ││
     │                       │   │ ❌ History: NO   ││
     │                       │   │ ✅ Vision JSON   ││
     │                       │   └──────────────────┘│
     │                       │         │     │       │
     │                       │         NO   YES      │
     │                       │         │     │       │
     │                       │         │     └───────┤
     ▼                       ▼         ▼             ▼
╔══════════════════════════════════════════════════════╗
║         DIRECT LLM INFERENCE                         ║
║  1. Build Messages (with/without RAG)                ║
║  2. Intent Detection (auto mode, ❌ no history)     ║
║  3. Main LLM Call (streaming, ✅ FULL history)      ║
║  4. Format & Update History                          ║
╚══════════════════════════════════════════════════════╝
                           │
                           ▼
                    ┌──────────┐
                    │ RESPONSE │
                    └──────────┘

         WEB RESEARCH PIPELINE
         ═════════════════════
                    │
                    ▼
        ┌───────────────────┐
        │ Session Cache?    │
        └───────────────────┘
                    │
        ┌───────────┴────────────┐
        │                        │
        ▼                        ▼
   ┌────────┐          ┌─────────────────────────┐
   │ CACHE  │          │ Query Optimization      │
   │ HIT    │          │ (Automatik-LLM)         │
   └────────┘          │ ✅ History: 3 turns     │
                       │ ✅ Vision JSON          │
                       └─────────────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Web Search      │
                       │ (Multi-API)     │
                       │ → ~30 URLs      │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ URL Ranking     │
                       │ (Automatik-LLM) │
                       │ → Top 3/7 URLs  │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ PARALLEL TASKS  │
                       ├─────────────────┤
                       │ • Scraping      │
                       │   (ranked URLs) │
                       │ • LLM Preload   │
                       │   (async)       │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Context Build   │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────────────┐
                       │ Main LLM (streaming)    │
                       │ ✅ History: FULL        │
                       │ ✅ Vision JSON          │
                       └─────────────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Cache Storage   │
                       │ (TTL from LLM)  │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ RESPONSE        │
                       └─────────────────┘
```

### 📁 Code Structure Reference

**Core Entry Points:**
- `aifred/state.py` - Main state management, send_message()

**Automatik Mode:**
- `aifred/lib/conversation_handler.py` - Decision logic, RAG context

**Web Research Pipeline:**
- `aifred/lib/research/orchestrator.py` - Top-level orchestration (incl. URL ranking)
- `aifred/lib/research/cache_handler.py` - Session cache
- `aifred/lib/research/query_processor.py` - Query optimization + search
- `aifred/lib/research/url_ranker.py` - LLM-based URL relevance ranking (NEW)
- `aifred/lib/research/scraper_orchestrator.py` - Parallel scraping
- `aifred/lib/research/context_builder.py` - Context building + LLM

**Supporting Modules:**
- `aifred/lib/vector_cache.py` - ChromaDB semantic cache
- `aifred/lib/rag_context_builder.py` - RAG context from cache
- `aifred/lib/intent_detector.py` - Temperature selection
- `aifred/lib/agent_tools.py` - Web search, scraping, context building

### 📝 Automatik-LLM Prompts Reference

The Automatik-LLM uses dedicated prompts in `prompts/{de,en}/automatik/` for various decisions:

| Prompt | Language | When Called | Purpose |
|--------|----------|-------------|---------|
| `intent_detection.txt` | EN only | Pre-processing | Determine query intent (FACTUAL/MIXED/CREATIVE) and addressee |
| `research_decision.txt` | DE + EN | Phase 4 | Decide if web research needed + generate queries |
| `rag_relevance_check.txt` | DE + EN | Phase 2 (RAG) | Check if cached entry is relevant to current question |
| `followup_intent_detection.txt` | DE + EN | Cache follow-up | Detect if user wants more details from cache |
| `url_ranking.txt` | EN only | Phase 2.5 | Rank URLs by relevance (output: numeric indices) |

**Language Rules:**
- **EN only**: Output is structured/numeric (parseable), language doesn't affect result
- **DE + EN**: Output depends on user's language or requires semantic understanding in that language

**Prompt Directory Structure:**
```
prompts/
├── de/
│   └── automatik/
│       ├── research_decision.txt      # German queries for German users
│       ├── rag_relevance_check.txt    # German semantic matching
│       └── followup_intent_detection.txt
└── en/
    └── automatik/
        ├── intent_detection.txt       # Universal intent detection
        ├── research_decision.txt      # English queries (Query 1 always EN)
        ├── rag_relevance_check.txt    # English semantic matching
        ├── followup_intent_detection.txt
        └── url_ranking.txt            # Numeric output (indices)
```

---

## 🌐 REST API (Browser Remote Control)

AIfred provides a complete REST API for programmatic control - enabling remote operation via Cloud, automation systems, and third-party integrations.

### Architecture: Browser as Execution Engine

The API acts as a **Browser Remote Control** - it doesn't run LLM inference itself, but injects messages into the browser session which then executes the full pipeline:

```
API Request ──→ set_pending_message() ──→ Browser polls (1s)
                                              │
                                              ↓
                                    send_message() pipeline
                                              │
                                              ↓
                              Intent Detection, Multi-Agent, Research...
                                              │
                                              ↓
                              Response visible in Browser + API
```

**Benefits:**
- **One code path**: API uses exactly the same code as manual browser input
- **All features work**: Multi-Agent, Research Mode, Vision, History Compression
- **Live feedback**: User sees streaming output in browser while API waits
- **Less code**: No duplicate LLM logic in API layer

### Key Features

- **Full Remote Control**: Control all AIfred settings from anywhere
- **Live Browser Sync**: API changes automatically appear in the browser UI
- **Message Injection**: Queue messages that browser processes with full pipeline
- **Session Management**: Access and manage multiple browser sessions
- **OpenAPI Documentation**: Interactive Swagger UI at `/docs`

### API Endpoints

The API enables **pure remote control** - messages are injected into browser sessions, the browser performs the full processing (Intent Detection, Multi-Agent, Research, etc.). The user sees everything live in the browser.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check with backend status |
| `/api/settings` | GET | Retrieve all settings |
| `/api/settings` | PATCH | Update settings (partial update) |
| `/api/models` | GET | List available models |
| `/api/chat/inject` | POST | Inject message into browser session |
| `/api/chat/status` | GET | Check if inference is running (is_generating, message_count) |
| `/api/chat/history` | GET | Get chat history |
| `/api/chat/clear` | POST | Clear chat history |
| `/api/sessions` | GET | List all browser sessions |
| `/api/system/restart-ollama` | POST | Restart Ollama |
| `/api/system/restart-aifred` | POST | Restart AIfred |
| `/api/calibrate` | POST | Start context calibration |

### Browser Synchronization

When you change settings or inject messages via API, the browser UI updates automatically:

- **Chat Sync**: Injected messages trigger full inference in browser within 2 seconds
- **Settings Sync**: Model changes, Multi-Agent mode, temperature etc. update live in the UI
- **Status Polling**: Use `/api/chat/status` to wait for inference completion

This enables true remote control - change AIfred's configuration from another device and see the changes reflected immediately in any connected browser.

### Example Usage

```bash
# Get current settings
curl http://localhost:8002/api/settings

# Change model and Multi-Agent mode
curl -X PATCH http://localhost:8002/api/settings \
  -H "Content-Type: application/json" \
  -d '{"aifred_model": "qwen3:14b", "multi_agent_mode": "critical_review"}'

# Inject a message (browser runs full pipeline)
curl -X POST http://localhost:8002/api/chat/inject \
  -H "Content-Type: application/json" \
  -d '{"message": "What is Python?", "device_id": "abc123..."}'

# Poll until inference is complete
curl "http://localhost:8002/api/chat/status?device_id=abc123..."
# Returns: {"is_generating": false, "message_count": 5}

# Get the response
curl "http://localhost:8002/api/chat/history?device_id=abc123..."

# List all browser sessions (to get device_id)
curl http://localhost:8002/api/sessions
```

### Use Cases

- **Cloud Control**: Operate AIfred from anywhere via HTTPS/API
- **Home Automation**: Integration with Home Assistant, Node-RED, etc.
- **Voice Assistants**: Alexa/Google Home can send AIfred queries
- **Batch Processing**: Automated queries via scripts
- **Mobile Apps**: Custom apps can use the API
- **Remote Maintenance**: Test and monitor AIfred on headless systems

---

## 🚀 Installation

### Prerequisites
- Python 3.10+
- **LLM Backend** (choose one):
  - **Ollama** (easy, GGUF models) - recommended for getting started
  - **vLLM** (fast, AWQ models) - best performance (requires Compute Capability 7.5+)
  - **TabbyAPI** (ExLlamaV2/V3, EXL2 models) - experimental
- 8GB+ RAM (12GB+ recommended for larger models)
- Docker (for ChromaDB Vector Cache)
- **GPU**: NVIDIA GPU recommended (see [GPU Compatibility Guide](docs/GPU_COMPATIBILITY.md))

### Setup

1. **Clone repository**:
```bash
git clone https://github.com/yourusername/AIfred-Intelligence.git
cd AIfred-Intelligence
```

2. **Create virtual environment**:
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
# Install Playwright browser (for JS-heavy pages)
playwright install chromium
```

**Main Dependencies** (see `requirements.txt`):
| Category | Packages |
|----------|----------|
| Framework | reflex, fastapi, pydantic |
| LLM Backends | httpx, openai, pynvml, psutil |
| Web Research | trafilatura, playwright, requests, pymupdf |
| Vector Cache | chromadb, ollama, numpy |
| Audio (STT/TTS) | edge-tts, XTTS v2 (Docker), openai-whisper |

4. **Environment variables** (.env):
```env
# API Keys for web research
BRAVE_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here

# Ollama configuration
OLLAMA_BASE_URL=http://localhost:11434

# Cloud LLM API Keys (optional - only needed if using cloud backends)
DASHSCOPE_API_KEY=your_key_here      # Qwen (DashScope) - https://dashscope.console.aliyun.com/
DEEPSEEK_API_KEY=your_key_here       # DeepSeek - https://platform.deepseek.com/
ANTHROPIC_API_KEY=your_key_here      # Claude (Anthropic) - https://console.anthropic.com/
MOONSHOT_API_KEY=your_key_here       # Kimi (Moonshot) - https://platform.moonshot.cn/
```

5. **Install LLM Models**:

**Option A: All Models (Recommended)**
```bash
# Master script for both backends
./scripts/download_all_models.sh
```

**Option B: Ollama Only (GGUF) - Easiest Installation**
```bash
# Ollama Models (GGUF Q4/Q8)
./scripts/download_ollama_models.sh

# Recommended core models:
# - qwen3:30b-instruct (18GB) - Main-LLM, 256K context
# - qwen3:8b (5.2GB) - Automatik, optional thinking
# - qwen2.5:3b (1.9GB) - Ultra-fast Automatik
```

**Option C: vLLM Only (AWQ) - Best Performance**
```bash
# Install vLLM (if not already done)
pip install vllm

# vLLM Models (AWQ Quantization)
./scripts/download_vllm_models.sh

# Recommended models:
# - Qwen3-8B-AWQ (~5GB, 40K→128K with YaRN)
# - Qwen3-14B-AWQ (~8GB, 32K→128K with YaRN)
# - Qwen2.5-14B-Instruct-AWQ (~8GB, 128K native)

# Start vLLM server with YaRN (64K context)
./venv/bin/vllm serve Qwen/Qwen3-14B-AWQ \
  --quantization awq_marlin \
  --port 8001 \
  --rope-scaling '{"rope_type":"yarn","factor":2.0,"original_max_position_embeddings":32768}' \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.85

# Systemd service setup: see docs/infrastructure/
```

**Option D: TabbyAPI (EXL2) - Experimental**
```bash
# Not yet fully implemented
# See: https://github.com/theroyallab/tabbyAPI
```

6. **Start ChromaDB Vector Cache** (Docker):

**Prerequisites:** Docker Compose v2 recommended
```bash
# Install Docker Compose v2 (if not already installed)
sudo apt-get install docker-compose-plugin
docker compose version  # should show v2.x.x
```

**Start ChromaDB:**
```bash
cd docker
docker compose up -d chromadb
cd ..

# Verify it's healthy
docker ps | grep chroma
# Should show: (healthy) in status

# Test API v2
curl http://localhost:8000/api/v2/heartbeat
```

**Optional: Also start SearXNG** (local search engine):
```bash
cd docker
docker compose --profile full up -d
cd ..
```

**Reset ChromaDB Cache** (if needed):

*Option 1: Complete restart (deletes all data)*
```bash
cd docker
docker compose stop chromadb
cd ..
rm -rf docker/aifred_vector_cache/
cd docker
docker compose up -d chromadb
cd ..
```

*Option 2: Delete collection only (while container is running)*
```bash
./venv/bin/python -c "
import chromadb
from chromadb.config import Settings

client = chromadb.HttpClient(
    host='localhost',
    port=8000,
    settings=Settings(anonymized_telemetry=False)
)

try:
    client.delete_collection('research_cache')
    print('✅ Collection deleted')
except Exception as e:
    print(f'⚠️ Error: {e}')
"
```

7. **Start XTTS Voice Cloning** (Optional, Docker):

XTTS v2 provides high-quality voice cloning with multilingual support and smart GPU/CPU selection.

```bash
cd docker/xtts
docker compose up -d
```

First start takes ~2-3 minutes (model download ~1.5GB). After that, XTTS is available as TTS engine in the UI settings.

**Features:**
- 58 built-in voices + custom voice cloning (6-10s reference audio)
- Automatic GPU/CPU selection based on available VRAM
- **Manual CPU-Mode Toggle**: Save GPU VRAM for larger LLM context window (slower TTS)
- Multilingual support (16 languages) with automatic code-switching (DE/EN mixed)
- Per-agent voices with individual pitch and speed settings
- **Multi-Agent TTS Queue**: Sequential playback of AIfred → Sokrates → Salomo responses
- Async TTS generation (doesn't block next LLM inference)
- **VRAM Management**: In GPU mode, ~2 GB VRAM is reserved and deducted from LLM context window

See [docker/xtts/README.md](docker/xtts/README.md) for full documentation.

8. **Start application**:
```bash
reflex run
```

The app will run at: http://localhost:3002

---

## ⚙️ Backend Switching & Settings

### Multi-Backend Support

AIfred supports different LLM backends that can be switched dynamically in the UI:

- **Ollama**: GGUF models (Q4/Q8), easiest installation
- **vLLM**: AWQ models (4-bit), best performance with AWQ Marlin kernel
- **KoboldCPP**: GGUF models with dynamic RoPE scaling and VRAM optimization
- **TabbyAPI**: EXL2 models (ExLlamaV2/V3) - experimental, basic support only

### GPU Compatibility Detection

AIfred automatically detects your GPU at startup and warns about incompatible backend configurations:

- **Tesla P40 / GTX 10 Series** (Pascal): Use Ollama (GGUF) - vLLM/AWQ not supported
- **RTX 20+ Series** (Turing/Ampere/Ada): vLLM (AWQ) recommended for best performance

Detailed information: [GPU_COMPATIBILITY.md](docs/GPU_COMPATIBILITY.md)

### Settings Persistence

Settings are saved in `~/.config/aifred/settings.json`:

**Per-Backend Model Storage:**
- Each backend remembers its last used models
- When switching backends, the correct models are automatically restored
- On first start, defaults from `aifred/lib/config.py` are used

**Example Settings Structure:**
```json
{
  "backend_type": "vllm",
  "enable_thinking": true,
  "backend_models": {
    "ollama": {
      "selected_model": "qwen3:8b",
      "automatik_model": "qwen2.5:3b"
    },
    "vllm": {
      "selected_model": "Qwen/Qwen3-8B-AWQ",
      "automatik_model": "Qwen/Qwen3-4B-AWQ"
    }
  }
}
```

### Reasoning Mode (Chain-of-Thought)

AIfred supports per-agent reasoning configuration for enhanced answer quality.

**Per-Agent Reasoning Toggles** (v2.23.0):

Each agent (AIfred, Sokrates, Salomo) has its own reasoning toggle in the LLM settings. These toggles control **both** mechanisms:

1. **Reasoning Prompt**: Chain-of-Thought instructions in the system prompt (works for ALL models)
2. **enable_thinking Flag**: Technical flag for thinking-capable models (Qwen3, QwQ, NemoTron)

| Toggle | Reasoning Prompt | enable_thinking | Effect |
|--------|------------------|-----------------|--------|
| **ON** | ✅ Injected | ✅ True | Full CoT with `<think>` blocks (thinking models) |
| **ON** | ✅ Injected | ✅ True | CoT instructions followed (instruct models, no `<think>`) |
| **OFF** | ❌ Not injected | ❌ False | Direct answers, no reasoning |

**Design Rationale:**
- Instruct models (without native `<think>` tags) benefit from CoT prompt instructions
- Thinking models receive both: CoT prompt + technical flag for `<think>` block generation
- This unified approach provides consistent behavior regardless of model type

**Additional Features:**
- **Formatting**: Reasoning process displayed as collapsible accordion with model name and inference time
- **Temperature**: Independent from reasoning - uses Intent Detection (auto) or manual slider
- **Automatik-LLM**: Reasoning always DISABLED for Automatik decisions (8x faster)

---

## 🏗️ Architecture

### Directory Structure
```
AIfred-Intelligence/
├── aifred/
│   ├── backends/          # LLM Backend Adapters
│   │   ├── base.py           # Abstract Base Class
│   │   ├── ollama.py         # Ollama Backend (GGUF)
│   │   ├── vllm.py           # vLLM Backend (AWQ)
│   │   ├── tabbyapi.py       # TabbyAPI Backend (EXL2)
│   │   └── koboldcpp.py      # KoboldCPP Backend (GGUF)
│   ├── lib/               # Core Libraries
│   │   ├── multi_agent.py       # Multi-Agent System (AIfred, Sokrates, Salomo)
│   │   ├── context_manager.py   # History compression
│   │   ├── conversation_handler.py # Automatik mode, RAG context
│   │   ├── config.py            # Default settings
│   │   ├── vector_cache.py      # ChromaDB Vector Cache
│   │   ├── research/            # Web research modules
│   │   │   ├── orchestrator.py      # Research orchestration
│   │   │   └── query_processor.py   # Query processing
│   │   └── tools/               # Tool implementations
│   │       ├── search_tools.py      # Parallel web search
│   │       └── scraper_tool.py      # Parallel web scraping
│   ├── aifred.py          # Main application / UI
│   └── state.py           # Reflex State Management
├── prompts/               # System Prompts (de/en)
├── scripts/               # Utility Scripts
├── docs/                  # Documentation
│   ├── infrastructure/          # Service setup guides
│   ├── architecture/            # Architecture docs
│   └── GPU_COMPATIBILITY.md     # GPU compatibility matrix
├── docker/                # Docker configurations
│   └── aifred_vector_cache/     # ChromaDB Docker setup
└── CHANGELOG.md           # Project Changelog
```

### History Compression System

At 70% context utilization, older conversations are automatically compressed using **PRE-MESSAGE checks** (v2.12.0):

| Parameter | Value | Description |
|-----------|-------|-------------|
| `HISTORY_COMPRESSION_TRIGGER` | 0.7 (70%) | Compression triggers at this context utilization |
| `HISTORY_COMPRESSION_TARGET` | 0.3 (30%) | Target after compression (room for ~2 roundtrips) |
| `HISTORY_SUMMARY_RATIO` | 0.25 (4:1) | Summary = 25% of content being compressed |
| `HISTORY_SUMMARY_MIN_TOKENS` | 500 | Minimum for meaningful summaries |
| `HISTORY_SUMMARY_TOLERANCE` | 0.5 (50%) | Allowed overshoot, above this gets truncated |
| `HISTORY_SUMMARY_MAX_RATIO` | 0.2 (20%) | Max context percentage for summaries (NEW) |

**Algorithm (PRE-MESSAGE):**
1. **PRE-CHECK** before each LLM call (not after!)
2. **Trigger** at 70% context utilization
3. **Dynamic max_summaries** based on context size (20% budget / 500 tok)
4. **FIFO cleanup**: If too many summaries, oldest is deleted first
5. **Collect** oldest messages until remaining < 30%
6. **Compress** collected messages to summary (4:1 ratio)
7. **New History** = [Summaries] + [remaining messages]

**Dynamic Summary Limits:**
| Context | Max Summaries | Calculation |
|---------|---------------|-------------|
| 4K | 1-2 | 4096 × 0.2 / 500 = 1.6 |
| 8K | 3 | 8192 × 0.2 / 500 = 3.3 |
| 32K | 10 | 32768 × 0.2 / 500 = 13 → capped at 10 |

**Token Estimation:** Ignores `<details>`, `<span>`, `<think>` tags (not sent to LLM)

**Examples by Context Size:**
| Context | Trigger | Target | Compressed | Summary |
|---------|---------|--------|------------|---------|
| 7K | 4,900 tok | 2,100 tok | ~2,800 tok | ~700 tok |
| 40K | 28,000 tok | 12,000 tok | ~16,000 tok | ~4,000 tok |
| 200K | 140,000 tok | 60,000 tok | ~80,000 tok | ~20,000 tok |

**Inline Summaries (UI, v2.14.2+):**
- Summaries appear inline where compression occurred
- Each summary as collapsible with header (number, message count)
- FIFO applies only to `llm_history` (LLM sees 1 summary)
- `chat_history` keeps ALL summaries (user sees full history)

### Vector Cache & RAG System

AIfred uses a multi-tier cache system based on **semantic similarity** (Cosine Distance) with pure semantic deduplication and intelligent cache usage for explicit research keywords.

#### Cache Decision Logic

**Phase 0: Explicit Research Keywords**
```
User Query: "research Python" / "google Python" / "search internet Python"
└─ Explicit keyword detected → Cache check FIRST
   ├─ Distance < 0.05 (practically identical)
   │  └─ ✅ Cache Hit (0.15s instead of 100s) - Shows age transparently
   └─ Distance ≥ 0.05 (not identical)
      └─ New web research (user wants fresh data)
```

**Phase 1a: Direct Cache Hit Check**
```
User Query → ChromaDB Similarity Search
├─ Distance < 0.5 (HIGH Confidence)
│  └─ ✅ Use Cached Answer (instant, no more time checks!)
├─ Distance 0.5-1.2 (MEDIUM Confidence) → Continue to Phase 1b (RAG)
└─ Distance > 1.2 (LOW Confidence) → Continue to Phase 2 (Research Decision)
```

**Phase 1b: RAG Context Check**
```
Cache Miss (d ≥ 0.5) → Query for RAG Candidates (0.5 ≤ d < 1.2)
├─ Found RAG Candidates?
│  ├─ YES → Automatik-LLM checks relevance for each candidate
│  │   ├─ Relevant (semantic match) → Inject as System Message Context
│  │   │   Example: "Python" → "FastAPI" ✅ (FastAPI is Python framework)
│  │   └─ Not Relevant → Skip
│  │       Example: "Python" → "Weather" ❌ (no connection)
│  └─ NO → Continue to Phase 2
└─ LLM Answer with RAG Context (Source: "Cache+LLM (RAG)")
```

**Phase 2: Research Decision**
```
No Direct Cache Hit & No RAG Context
└─ Automatik-LLM decides: Web Research needed?
   ├─ YES → Web Research + Cache Result
   └─ NO  → Pure LLM Answer (Source: "LLM-Training Data")
```

#### Semantic Deduplication

**When Saving to Vector Cache:**
```
New Research Result → Check for Semantic Duplicates
└─ Distance < 0.3 (semantically similar)
   └─ ✅ ALWAYS Update
      - Delete old entry
      - Save new entry
      - Guaranteed: Latest data is used
```

Purely semantic deduplication without time checks → Consistent behavior.

#### Cache Distance Thresholds

| Distance | Confidence | Behavior | Example |
|----------|-----------|----------|---------|
| `0.0 - 0.05` | EXACT | Explicit research uses cache | Identical query |
| `0.05 - 0.5` | HIGH | Direct cache hit | "Python tutorial" vs "Python guide" |
| `0.5 - 1.2` | MEDIUM | RAG candidate (relevance check via LLM) | "Python" vs "FastAPI" |
| `1.2+` | LOW | Cache miss → Research decision | "Python" vs "Weather" |

#### ChromaDB Maintenance Tool

Maintenance tool for Vector Cache:
```bash
# Show stats
python3 chroma_maintenance.py --stats

# Find duplicates
python3 chroma_maintenance.py --find-duplicates

# Remove duplicates (Dry-Run)
python3 chroma_maintenance.py --remove-duplicates

# Remove duplicates (Execute)
python3 chroma_maintenance.py --remove-duplicates --execute

# Delete old entries (> 30 days)
python3 chroma_maintenance.py --remove-old 30 --execute
```

#### RAG (Retrieval-Augmented Generation) Mode

**How it works**:
1. Query finds related cache entries (distance 0.5-1.2)
2. Automatik-LLM checks if cached content is relevant to current question
3. Relevant entries are injected as system message: "Previous research shows..."
4. Main LLM combines cached context + training knowledge for enhanced answer

**Example Flow**:
```
User: "What is Python?" → Web Research → Cache Entry 1 (d=0.0)
User: "What is FastAPI?" → RAG finds Entry 1 (d=0.7)
  → LLM checks: "Python" relevant for "FastAPI"? YES (FastAPI uses Python)
  → Inject Entry 1 as context → Enhanced LLM answer
  → Source: "Cache+LLM (RAG)"
```

**Benefits**:
- Leverages related past research without exact cache hits
- Avoids false context (LLM filters irrelevant entries)
- Multi-level context awareness (cache + conversation history)

#### TTL-Based Cache System (Volatility)

The Main LLM determines cache lifetime via `<volatility>` tag in response:

| Volatility | TTL | Use Case |
|------------|-----|----------|
| `DAILY` | 24h | News, current events, "latest developments" |
| `WEEKLY` | 7 days | Political updates, semi-current topics |
| `MONTHLY` | 30 days | Statistics, reports, less volatile data |
| `PERMANENT` | ∞ | Timeless facts ("What is Python?") |

**Automatic Cleanup**: Background task runs every 12 hours, deletes expired entries.

#### Configuration

Cache behavior in `aifred/lib/config.py`:

```python
# Cache Distance Thresholds
CACHE_DISTANCE_HIGH = 0.5        # < 0.5 = HIGH confidence cache hit
CACHE_DISTANCE_DUPLICATE = 0.3   # < 0.3 = semantic duplicate (always merged)
CACHE_DISTANCE_RAG = 1.2         # < 1.2 = similar enough for RAG context

# TTL (Time-To-Live)
TTL_HOURS = {
    'DAILY': 24,
    'WEEKLY': 168,
    'MONTHLY': 720,
    'PERMANENT': None
}
```

**RAG Relevance Check**: Uses Automatik-LLM with dedicated prompt (`prompts/de/rag_relevance_check.txt`)

---

## 🔧 Configuration

All important parameters in `aifred/lib/config.py`:

```python
# History Compression (dynamic, percentage-based)
HISTORY_COMPRESSION_TRIGGER = 0.7    # 70% - When to compress?
HISTORY_COMPRESSION_TARGET = 0.3     # 30% - Where to compress to?
HISTORY_SUMMARY_RATIO = 0.25         # 25% = 4:1 compression
HISTORY_SUMMARY_MIN_TOKENS = 500     # Minimum for summaries
HISTORY_SUMMARY_TOLERANCE = 0.5      # 50% overshoot allowed

# Intent-based Temperature
INTENT_TEMPERATURE_FAKTISCH = 0.2    # Factual queries
INTENT_TEMPERATURE_GEMISCHT = 0.5    # Mixed queries
INTENT_TEMPERATURE_KREATIV = 1.0     # Creative queries

# Backend-specific Default Models (in BACKEND_DEFAULT_MODELS)
# Ollama: qwen3:4b-instruct-2507-q4_K_M (Automatik), qwen3-vl:8b (Vision)
# vLLM: cpatonn/Qwen3-4B-Instruct-2507-AWQ-4bit, etc.
```

### HTTP Timeout Configuration

In `aifred/backends/ollama.py`:
- **HTTP Client Timeout**: 300 seconds (5 minutes)
- Increased from 60s for large research requests with 30KB+ context
- Prevents timeout errors during first token generation

### Restart Button Behavior

The AIfred restart button restarts the systemd service:
- Executes `systemctl restart aifred-intelligence`
- Browser reloads automatically after short delay
- Debug logs cleared, sessions preserved

---

## 📦 Deployment

### Systemd Service

For production operation as a service, pre-configured service files are available in the `systemd/` directory.

**⚠️ IMPORTANT**: The environment variable `AIFRED_ENV=prod` **MUST** be set for AIfred to run on the MiniPC and not redirect to the development machine!

#### Quick Installation

```bash
# 1. Copy service files
sudo cp systemd/aifred-chromadb.service /etc/systemd/system/
sudo cp systemd/aifred-intelligence.service /etc/systemd/system/

# 2. Enable and start services
sudo systemctl daemon-reload
sudo systemctl enable aifred-chromadb.service aifred-intelligence.service
sudo systemctl start aifred-chromadb.service aifred-intelligence.service

# 3. Check status
systemctl status aifred-chromadb.service
systemctl status aifred-intelligence.service

# 4. Create first user (required for login)
./aifred-admin add yourusername
# Then register in the web UI with username + password
```

See [systemd/README.md](systemd/README.md) for details, troubleshooting, and monitoring.

#### User Management (aifred-admin CLI)

AIfred requires user authentication. Manage users via the admin CLI:

```bash
./aifred-admin users              # List whitelist (who can register)
./aifred-admin add <username>     # Add user to whitelist
./aifred-admin remove <username>  # Remove from whitelist
./aifred-admin accounts           # List registered accounts
./aifred-admin delete <username>  # Delete account (with confirmation)
./aifred-admin delete <username> --sessions  # Also delete user's sessions
```

**Workflow:**
1. Admin adds username to whitelist: `./aifred-admin add alice`
2. User registers in web UI with username + password
3. User can now login from any device with their credentials

#### Service Files (Reference)

**1. ChromaDB Service** (`systemd/aifred-chromadb.service`):
```ini
[Unit]
Description=AIfred ChromaDB Vector Cache (Docker)
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/mp/Projekte/AIfred-Intelligence/docker
ExecStart=/usr/bin/docker compose up -d chromadb
ExecStop=/usr/bin/docker compose stop chromadb
```

**2. AIfred Intelligence Service** (`systemd/aifred-intelligence.service`):
```ini
[Unit]
Description=AIfred Intelligence Voice Assistant (Reflex Version)
After=network.target ollama.service aifred-chromadb.service
Wants=ollama.service
Requires=aifred-chromadb.service

[Service]
Type=simple
User=__USER__
Group=__USER__
WorkingDirectory=__PROJECT_DIR__
Environment="PATH=__PROJECT_DIR__/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=__PROJECT_DIR__/venv/bin/python -m reflex run --env prod --frontend-port 3002 --backend-port 8002 --backend-host 0.0.0.0
Restart=always
KillMode=control-group
ExecStopPost=/usr/bin/pkill -f koboldcpp || true
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**⚠️ Important: Replace placeholders** `__USER__` and `__PROJECT_DIR__` with your actual values!

#### Environment Configuration (.env)

For production/external access, create a `.env` file in the project root (this file is gitignored and NOT pushed to the repository):

```bash
# Environment Mode (required for production)
AIFRED_ENV=prod

# Backend API URL for external access via nginx reverse proxy
# Set this to your external domain/IP for HTTPS access
AIFRED_API_URL=https://your-domain.com:8443

# API Keys for web search (optional)
BRAVE_API_KEY=your_brave_api_key
TAVILY_API_KEY=your_tavily_api_key

# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434

# Backend URL for static files (HTML Preview, Images)
# With NGINX: Leave empty or omit - NGINX routes /_upload/ to backend
# Without NGINX (dev): Set to backend URL for direct access
# BACKEND_URL=http://localhost:8002

# Cloud LLM API Keys (optional - only needed if using cloud backends)
DASHSCOPE_API_KEY=your_key_here      # Qwen (DashScope)
DEEPSEEK_API_KEY=your_key_here       # DeepSeek
ANTHROPIC_API_KEY=your_key_here      # Claude (Anthropic)
MOONSHOT_API_KEY=your_key_here       # Kimi (Moonshot)
```

**Why is `AIFRED_API_URL` needed?**

The Reflex frontend needs to know where the backend is located. Without this setting:
- The frontend auto-detects the local IP (e.g., `http://192.168.0.252:8002`)
- This works for local network access but fails for external HTTPS access
- External users would see WebSocket connection errors to `localhost`

With `AIFRED_API_URL=https://your-domain.com:8443`:
- All API/WebSocket connections go through your nginx reverse proxy
- HTTPS works correctly for external access
- Local HTTP access continues to work

**Why `--env prod`?**

The `--env prod` flag in ExecStart:
- Disables Vite Hot Module Replacement (HMR) WebSocket
- Prevents "failed to connect to websocket localhost:3002" errors
- Reduces resource usage (no dev server overhead)
- Still recompiles on restart when code changes

**FOUC Issue in Production Mode**

In production mode (`--env prod`), a **FOUC (Flash of Unstyled Content)** may occur - a brief flash of unstyled text/CSS class names during page reload.

**Cause:** React Router 7 with `prerender: true` loads CSS asynchronously (lazy loading). The generated HTML is visible immediately, but Emotion CSS-in-JS is loaded afterwards.

**Solution: Use Dev Mode**

If FOUC is bothersome, use dev mode instead:

```bash
# Set in .env:
AIFRED_ENV=dev

# Or remove --env prod from the systemd service
```

**Dev Mode Characteristics:**
- No FOUC (CSS loaded synchronously)
- Slightly higher RAM usage (hot reload server)
- More console warnings (React Strict Mode)
- Non-minified bundles (slightly larger)

For a local home network server, these drawbacks are negligible.

**Additionally required for Dev Mode with external access:**

> ⚠️ **IMPORTANT:** The `.web/vite.config.js` file gets overwritten on Reflex updates!
> Use the patch script after updates: `./scripts/patch-vite-config.sh`

In `.web/vite.config.js`, the following must be configured:

1. **allowedHosts** - for external domain access:
```javascript
server: {
  allowedHosts: ["your-domain.com", "localhost", "127.0.0.1"],
}
```

2. **proxy** - for API and TTS SSE streaming (required when accessing via frontend port 3002):
```javascript
server: {
  proxy: {
    '/_upload': { target: 'http://0.0.0.0:8002', changeOrigin: true },
    '/api': { target: 'http://0.0.0.0:8002', changeOrigin: true },
  },
}
```

Without the `/api` proxy, TTS streaming will fail with "text/html instead of text/event-stream" errors.

**Optional: Polkit Rule for Restart Without sudo**

For the restart button in the web UI without password prompt:

`/etc/polkit-1/rules.d/50-aifred-restart.rules`:
```javascript
polkit.addRule(function(action, subject) {
    if ((action.id == "org.freedesktop.systemd1.manage-units") &&
        (action.lookup("unit") == "aifred-intelligence.service" ||
         action.lookup("unit") == "ollama.service") &&
        (action.lookup("verb") == "restart") &&
        (subject.user == "mp")) {
        return polkit.Result.YES;
    }
});
```

---

## ⚠️ Multi-User Capabilities & Limitations

AIfred is designed as a **single-user system** but supports 2-3 concurrent users with certain limitations.

### ✅ What Works (Concurrent Users)

**Session Isolation (Reflex Framework):**
- Each browser tab gets its own session with unique `client_token` (UUID)
- **Chat history is isolated** - users don't see each other's conversations
- **Streaming responses work in parallel** - each user gets their own real-time updates
- **Request queuing** - Ollama automatically queues concurrent requests internally

**Per-User Isolated State:**
- ✅ Chat history (`chat_history`, `llm_history`)
- ✅ Current messages and streaming responses
- ✅ Image uploads and crop state
- ✅ Session ID and device ID (cookie-based)
- ✅ Failed sources and debug messages

### ⚠️ What Is Shared (Global State)

**Backend Configuration (shared across all users):**
- ⚠️ **Selected backend** (Ollama, vLLM, TabbyAPI, Cloud API)
- ⚠️ **Backend URL**
- ⚠️ **Selected models** (AIfred-LLM, Automatik-LLM, Sokrates-LLM, Salomo-LLM, Vision-LLM)
- ⚠️ **Available models list**
- ⚠️ **GPU info and VRAM cache**
- ⚠️ **vLLM process manager**

**Settings File (`~/.config/aifred/settings.json`):**
- ⚠️ All settings are global (temperature, Multi-Agent mode, RoPE factors, etc.)
- ⚠️ If User A changes a setting → User B sees the change immediately
- ⚠️ No per-user settings profiles

### 🎯 Practical Usage Scenarios

**✅ SAFE: Multiple users sending requests**
```
Timeline (Ollama automatically queues requests):
─────────────────────────────────────────────────────
User A: Sends question → Ollama processes → Response to User A
User B:                → Sends question → Waits in queue → Ollama processes → Response to User B
User C:                                 → Sends question → Waits in queue → Ollama processes → Response to User C
```

- Each user gets their own correct answer
- Ollama's internal queue handles concurrent requests sequentially
- No race conditions as long as nobody changes settings during requests

**⚠️ PROBLEMATIC: Changing settings during active requests**
```
User A: Sends request with Qwen3:8b → Processing...
User B: Switches model to Llama3:70b → Global state changes!
User A: Request continues with Qwen3 parameters (OK - already passed)
User A: Next request would use Llama3 (unintended)
```

- Settings changes affect all users immediately
- Running requests are safe (parameters already passed to backend)
- New requests from User A would use User B's settings

### 📊 Memory & Session Management

**Session Storage:**
- Sessions stored in RAM (plain dict by default, no Redis)
- **No automatic expiration** - sessions stay in memory until server restart
- Empty sessions are small (~1-5 KB each)
- **Not a problem**: Even 100 empty sessions = ~500 KB RAM

**Chat History:**
- Users who regularly clear their chat history keep memory usage low
- Full conversations (50+ messages) use more RAM but are manageable
- History compression (70% trigger) keeps context manageable

### 🔧 Design Rationale

**Why is backend configuration global?**

AIfred is designed for local hardware with limited resources:
- **Single GPU**: Can only run one model at a time efficiently
- **VRAM constraints**: Loading different models per user would exceed VRAM
- **Hardware is single-user oriented**: All users must share the configured backend/models

**This is intentional** - the system is optimized for:
- **Primary use case**: 1 user, occasionally 2-3 users
- **Shared hardware**: Everyone uses the same GPU/models
- **Root control**: Administrator (you) manages settings, others use the system as configured

### 🛡️ Recommendations for Multi-User Setup

1. **Establish usage rules:**
   - Designate one admin (root user) who manages settings
   - Other users should not change backend/model settings
   - Communicate when changing critical settings

2. **Safe concurrent usage:**
   - ✅ Multiple users can send requests simultaneously
   - ✅ Each user gets their own response and chat history
   - ⚠️ Avoid changing settings while others are actively using the system

3. **Expected behavior:**
   - Users see the same available models (shared dropdown)
   - Settings changes sync across browser tabs within 1-2 seconds (via `settings.json` polling)
   - **UI Sync Delay**: Model dropdown may not visually update until clicked/reopened (known Reflex limitation)
   - Multi-Agent mode and other simple settings sync immediately and visibly
   - This is **by design** for single-GPU hardware

### 🚫 What AIfred Is NOT

- ❌ **Not a multi-tenant SaaS**: No per-user accounts, quotas, or isolated resources
- ❌ **Not designed for >5 concurrent users**: Request queue would become slow
- ❌ **Not for untrusted users**: Any user can change global settings (no permissions/roles)

### ✅ What AIfred IS

- ✅ **Personal AI assistant** for home/office use
- ✅ **Family-friendly**: 2-3 family members can use it simultaneously without issues
- ✅ **Developer-focused**: Root user has full control, others use it as configured
- ✅ **Hardware-optimized**: Makes best use of single GPU for all users

**Summary**: AIfred works well for small groups (2-3 users) who coordinate settings changes, but is not suitable for large-scale multi-user deployments or untrusted user access.

---

## 🛠️ Development

### Debug Logs
```bash
tail -f logs/aifred_debug.log
```

### Code Quality Checks
```bash
# Syntax check
python3 -m py_compile aifred/FILE.py

# Linting with Ruff
source venv/bin/activate && ruff check aifred/

# Type checking with mypy
source venv/bin/activate && mypy aifred/ --ignore-missing-imports
```

## 🔨 Troubleshooting

### Common Issues

#### HTTP ReadTimeout on Research Requests
**Problem**: `httpx.ReadTimeout` after 60 seconds on large research requests
**Solution**: Timeout is already increased to 300s in `aifred/backends/ollama.py`
**If problems persist**: Restart Ollama service with `systemctl restart ollama`

#### Service Won't Start
**Problem**: AIfred service doesn't start or stops immediately
**Solution**:
```bash
# Check logs
journalctl -u aifred-intelligence -n 50
# Check Ollama status
systemctl status ollama
```

#### Restart Button Not Working
**Problem**: Restart button in web UI has no effect
**Solution**: Check Polkit rule in `/etc/polkit-1/rules.d/50-aifred-restart.rules`

---

## 📚 Documentation

More documentation in the `docs/` directory:
- [Architecture Overview](docs/architecture/)
- [API Documentation](docs/api/)
- [Migration Guide](docs/infrastructure/MIGRATION.md)

---

## 🤝 Contributing

Pull requests are welcome! For major changes, please open an issue first.

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file
