**🌍 Languages:** [English](README.md) | [Deutsch](README.de.md)

---

# 🤖 AIfred Intelligence - Advanced AI Assistant

**Production-Ready AI Assistant with Multi-LLM Support, Web Research & Voice Interface**

AIfred Intelligence is an advanced AI assistant with automatic web research, multi-model support, and history compression for unlimited conversations.

---

## 🎉 Latest Updates (2025-11-22)

### 🎯 Unified VRAM Cache System (v2.1.0)
- ✅ **Backend-Aware Cache**: Single `model_vram_cache.json` for all backends (Ollama/vLLM/TabbyAPI)
- ✅ **Universal VRAM Tracking**: Measures MB/token for all backends with architecture detection (MoE vs Dense)
- ✅ **Automatic Migration**: Old vLLM cache auto-migrated on first load
- ✅ **vLLM Calibrations**: Linear interpolation for context limits at different VRAM levels
- ✅ **Critical Bug Fix**: Fixed web research crash (ValueError in scraper orchestrator)
- 🎯 **Result**: 420-line unified module replacing 2 separate cache systems
- **Impact**: More accurate VRAM predictions, cleaner codebase, extensible for future backends

### 🧠 VRAM-Based Dynamic Context Window (RTX 3090 Ti Optimization)
- ✅ **Automatic Context Calculation** based on available GPU memory
- ✅ **Two-Scenario Detection**: Model loaded vs not loaded (prevents double-subtraction)
- ✅ **Model Size from Filesystem**: Reads actual blob file size (no hardcoded values)
- ✅ **Automatic Model Unloading**: Unloads all other models before preload (ensures maximum VRAM)
- ✅ **VRAM Stabilization**: Waits for VRAM to stabilize after model load (accurate measurements)
- ✅ **UI Integration**: Manual override option + real-time VRAM debug messages
- ✅ **Production-Ready**: 512 MB safety margin, 0.097 MB/token ratio (empirically tested)
- ✅ **Improved Readability**: Spaces between numbers and units in debug output
- 🎯 **Result**: qwen3:30b-a3b-instruct-2507 achieves **35,010 tokens** context (RTX 3090 Ti, 24GB)
- **Impact**: Prevents CPU offloading, maximizes usable context, automatic adaptation to VRAM conditions

### ✂️ Token Optimization in Prompts
- ✅ **Redundant Date Line Removed**: `- Jahr: 2025` removed from all prompts
- 🔧 **Reasoning**: Full date already shows year (`16.11.2025`), separate year line wasted tokens
- **Impact**: Saves ~15 tokens per prompt across all modes without information loss

### 🔍 Enhanced Debug Logging & Query Visibility (2025-11-15)
- ✅ **Consistent Debug Output** across all research modes (Own Knowledge, Automatik, Quick, Deep)
- ✅ **Precise Preload Timing** with `✅ Main-LLM loaded (X.Xs)` in all modes
- ✅ **Optimized Query Display** shows LLM-generated search terms: `🔎 Optimized Query: [terms]`
- ✅ **Backend-Aware Timing**: Ollama (actual load time) vs vLLM/TabbyAPI (prep time)
- 🔧 Comprehensive debug messages added: Token stats, Temperature, TTFT, Tokens/s
- **Impact**: Professional debug output, easier performance optimization, better web search quality assessment

### 🎯 Progress UI System Complete - MILESTONE (2025-11-14)
- ✅ **Full Progress Feedback** across all 4 research modes (Automatik, Quick, Deep, None)
- ✅ **Pulsing Animation** for "Generating Answer" in all modes (including "Own Knowledge")
- ✅ **Web-Scraping Progress Bar** now visible (1/3, 2/3, 3/3) with orange fill
- ✅ **Dynamic Status Text** reflects system activity in real-time
- **Impact**: Professional, consistent UI feedback - users always know what the system is doing

See [CHANGELOG.md](CHANGELOG.md) for detailed changes.

---

## ✨ Features

### 🎯 Core Features
- **Multi-Backend Support**: Ollama (GGUF), vLLM (AWQ), TabbyAPI (EXL2)
- **Qwen3 Thinking Mode**: Chain-of-Thought reasoning for complex tasks (Ollama + vLLM)
- **Automatic Web Research**: AI decides autonomously when research is needed
- **History Compression**: Intelligent compression at 70% context utilization
- **Voice Interface**: Speech-to-Text and Text-to-Speech integration
- **Vector Cache**: ChromaDB-based semantic cache for web research (Docker)
- **Per-Backend Settings**: Each backend remembers its preferred models

### 🔧 Technical Highlights
- **Reflex Framework**: React frontend generated from Python
- **WebSocket Streaming**: Real-time updates without polling
- **Adaptive Temperature**: AI selects temperature based on question type
- **Token Management**: Dynamic context window calculation
- **Debug Console**: Comprehensive logging and monitoring
- **ChromaDB Server Mode**: Thread-safe vector DB via Docker (0.0 distance for exact matches)
- **GPU Detection**: Automatic detection and warnings for incompatible backend-GPU combinations ([docs/GPU_COMPATIBILITY.md](docs/GPU_COMPATIBILITY.md))
- **KoboldCPP Dynamic RoPE**: Intelligent VRAM-based context optimization with automatic RoPE scaling

### ⚠️ Model Recommendations
- **Automatik-LLM (Decision/Intent/Query-Opt)**: Use **Instruct models** only
  - Thinking Models (QwQ-32B, DeepSeek-R1, etc.) are incompatible with Automatik tasks
  - These models ignore `enable_thinking` flags and produce verbose reasoning
  - This causes empty query optimization and failed decision-making
  - **Fallbacks are in place**, but performance is suboptimal
- **Main LLM**: Both Instruct and Thinking models work perfectly
  - Thinking models excel at complex reasoning and multi-step tasks
  - Enable "Thinking Mode" toggle for chain-of-thought reasoning

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

6. History Compression Check (AFTER every LLM response)
   ├─ Calculate token utilization: current_tokens / context_limit * 100
   ├─ IF utilization > 70%:
   │  ├─ Debug: "🗜️ History-Kompression startet: 78% Auslastung (21,800 / 28,000 tokens)"
   │  ├─ Select oldest 6 messages (3 Q&A pairs)
   │  ├─ LLM Call (Automatik-LLM):
   │  │  ├─ Prompt: history_compression
   │  │  ├─ Input: 6 messages (User + Assistant alternating)
   │  │  ├─ Output: 1 compact summary (~150 words)
   │  │  └─ Compression ratio: ~6:1 (e.g. 3000 tokens → 500 tokens)
   │  ├─ Replace 6 messages with 1 summary message
   │  ├─ Store in summaries[] (FIFO, max 10 summaries)
   │  └─ Debug: "📦 History compressed: 78% → 52% utilization (21,800 → 14,600 tokens, 6→1 messages, 3 summaries total)"
   └─ ELSE: Debug: "📊 History Compression Check: 45% utilization (12,500 / 28,000 tokens) - no compression needed"
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
   └─ Trigger fresh web research (mode='deep')
   └─ BYPASS Automatik decision
```

#### Phase 4: Automatik Decision
```
1. LLM Call - Decision Making
   ├─ Model: Automatik-LLM (e.g., Qwen2.5-3B)
   ├─ Prompt: decision_making
   ├─ Messages: NO history (focused decision)
   ├─ Options:
   │  ├─ temperature: 0.2 (consistent decisions)
   │  ├─ num_ctx: min(2048, automatik_limit // 2)
   │  └─ enable_thinking: False (fast)
   └─ Response: '<search>yes</search>' | '<search>no</search>'

2. Parse decision:
   ├─ IF yes: → Web Research (mode='deep')
   └─ IF no:  → Direct LLM Answer (Phase 5)
```

#### Phase 5: Direct LLM Answer (if decision = no)
```
1. Model Preloading (Ollama only)

2. Build Messages
   ├─ From chat history
   ├─ Inject system_minimal prompt
   └─ Optional: Inject RAG context (if found in Phase 2)

3. Intent Detection (if auto temp mode)
   ├─ LLM Call (Automatik-LLM)
   ├─ Prompt: intent_detection
   ├─ Response: "FACTUAL" | "CREATIVE" | "MIXED"
   └─ Map to temperature: 0.2 | 0.8 | 0.5

4. LLM Call - Main Response
   ├─ Model: Main-LLM
   ├─ Temperature: From intent detection or manual
   ├─ Streaming: Yes
   └─ TTFT + Tokens/s measurement

5. Format & Update History
   └─ Metadata: "Cache+LLM (RAG)" or "LLM"

6. History Compression Check (same as Own Knowledge mode)
   └─ Automatic compression at >70% context utilization
```

**LLM Calls:**
- Cache Hit: 0 + optional 1 Compression
- RAG Context: 2-6 + optional 1 Compression
- Web Research: 4-5 + optional 1 Compression
- Direct Answer: 2-3 + optional 1 Compression

**Code:** `aifred/lib/conversation_handler.py`

---

### 3️⃣ Quick Web Search Mode (Quick Research)

**Fastest web research mode**: Top 3 URLs, optimized for speed.

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
   ├─ Prompt: query_optimization
   ├─ Messages: Last 3 history turns (for follow-up context)
   ├─ Options:
   │  ├─ temperature: 0.3 (balanced for keywords)
   │  ├─ num_ctx: min(8192, automatik_limit)
   │  └─ enable_thinking: False
   ├─ Post-processing:
   │  ├─ Extract <think> tags (reasoning)
   │  ├─ Clean query (remove quotes)
   │  └─ Add temporal context (current year)
   └─ Output: optimized_query, query_reasoning

2. Web Search (Multi-API with Fallback)
   ├─ Try: Brave API
   ├─ Fallback: Tavily
   ├─ Fallback: SearXNG (local)
   └─ Deduplication across APIs
```

#### Phase 3: Parallel Web Scraping
```
PARALLEL EXECUTION:
├─ ThreadPoolExecutor (max 5 workers)
│  └─ Scrape Top 3 URLs simultaneously
│     └─ Extract text content + word count
│
└─ Async Task: Main LLM Preload (Ollama only)
   └─ llm_client.preload_model(model)
   └─ Runs parallel to scraping
   └─ vLLM/TabbyAPI: Skip (already loaded)

Progress Updates:
└─ Yield after each URL completion
```

#### Phase 4: Context Building + LLM Response
```
1. Build Context
   ├─ Filter successful scrapes (word_count > 0)
   ├─ build_context() - smart token limit aware
   └─ Build system_rag prompt (with context + timestamp)

2. Intent Detection (if auto temp mode)
   ├─ LLM Call (Automatik-LLM)
   └─ Map to temperature

3. LLM Call - Final Response
   ├─ Model: Main-LLM
   ├─ Context: ~3 sources, 5K-10K tokens
   ├─ Streaming: Yes
   └─ TTFT + Tokens/s measurement

4. Cache Decision (ONLY for Web Research)
   ├─ Check for volatile keywords (e.g., "today", "current", "now")
   │  └─ IF volatile: Skip caching (time-critical info)
   ├─ LLM Call (Automatik-LLM) - Cacheability Check
   │  ├─ Prompt: cache_decision
   │  ├─ Input: User query + LLM answer
   │  ├─ Decision based on:
   │  │  ├─ Timeless facts? (e.g., "What is Python?") → cacheable
   │  │  ├─ Time-bound events? (e.g., "current news") → not_cacheable
   │  │  ├─ Personal preferences? (e.g., "best restaurant") → not_cacheable
   │  │  └─ Volatile data? (e.g., weather, stock prices) → not_cacheable
   │  └─ Response: 'cacheable' | 'not_cacheable'
   ├─ IF cacheable:
   │  ├─ Semantic Duplicate Check (distance < 0.3 to existing entries)
   │  │  └─ IF duplicate: Delete old entry (ensures latest data)
   │  ├─ cache.add(query, answer, sources, metadata)
   │  └─ Debug: "💾 Answer cached" or "🔄 Cache entry updated"
   └─ ELSE: Debug: "⏭️ Answer not cached (volatile/time-bound)"

5. Format & Update History
   └─ Metadata: "(Agent: quick, {n} sources)"

6. History Compression Check (same as Own Knowledge mode)
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

**Most thorough mode**: Top 7 URLs for maximum information depth.

**Workflow:** Identical to Quick Web Search, with the following differences:

#### Scraping Strategy
```
Quick Mode:  3 URLs → ~3 successful sources
Deep Mode:   7 URLs → ~5-7 successful sources

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
     │                       │   ┌──────────────┐  │
     │                       │   │ LLM Decision │  │
     │                       │   │ (yes/no)     │  │
     │                       │   └──────────────┘  │
     │                       │         │     │      │
     │                       │         NO   YES     │
     │                       │         │     │      │
     │                       │         │     └──────┤
     ▼                       ▼         ▼            ▼
╔══════════════════════════════════════════════════════╗
║         DIRECT LLM INFERENCE                         ║
║  1. Build Messages (with/without RAG)                ║
║  2. Intent Detection (auto mode)                     ║
║  3. Main LLM Call (streaming)                        ║
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
   ┌────────┐          ┌─────────────────┐
   │ CACHE  │          │ Query           │
   │ HIT    │          │ Optimization    │
   └────────┘          │ (Automatik-LLM) │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Web Search      │
                       │ (Multi-API)     │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ PARALLEL TASKS  │
                       ├─────────────────┤
                       │ • Scraping      │
                       │   (3 or 7 URLs) │
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
                       ┌─────────────────┐
                       │ Main LLM        │
                       │ (streaming)     │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Cache Decision  │
                       │ (Automatik-LLM) │
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
- `aifred/lib/research/orchestrator.py` - Top-level orchestration
- `aifred/lib/research/cache_handler.py` - Session cache
- `aifred/lib/research/query_processor.py` - Query optimization + search
- `aifred/lib/research/scraper_orchestrator.py` - Parallel scraping
- `aifred/lib/research/context_builder.py` - Context building + LLM

**Supporting Modules:**
- `aifred/lib/vector_cache.py` - ChromaDB semantic cache
- `aifred/lib/rag_context_builder.py` - RAG context from cache
- `aifred/lib/query_optimizer.py` - Search query optimization
- `aifred/lib/intent_detector.py` - Temperature selection
- `aifred/lib/agent_tools.py` - Web search, scraping, context building

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
```

4. **Environment variables** (.env):
```env
# API Keys for web research
BRAVE_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here

# Ollama configuration
OLLAMA_BASE_URL=http://localhost:11434
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

# Or as systemd service
sudo cp vllm_qwen3_awq.service /etc/systemd/system/
sudo systemctl enable vllm_qwen3_awq
sudo systemctl start vllm_qwen3_awq
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
rm -rf aifred_vector_cache/
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

7. **Start application**:
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
- **TabbyAPI**: EXL2 models (ExLlamaV2/V3), experimental
- **KoboldCPP**: GGUF models with dynamic RoPE scaling and VRAM optimization

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

### Qwen3 Thinking Mode

**Chain-of-Thought Reasoning for Complex Tasks:**

AIfred supports Thinking Mode for Qwen3 models in Ollama and vLLM backends:

- **Thinking Mode ON**: Temperature 0.6, generates `<think>...</think>` blocks with reasoning process
- **Thinking Mode OFF**: Temperature 0.7, direct answers without CoT
- **UI**: Toggle only appears for Qwen3/QwQ models
- **Backends**:
  - **Ollama**: Uses `"think": true` API parameter, delivers separate `thinking` and `content` fields
  - **vLLM**: Uses `chat_template_kwargs: {"enable_thinking": true/false}` in `extra_body`
  - **TabbyAPI**: Not yet implemented
- **Formatting**: Reasoning process as collapsible accordion with model name and inference time
- **Automatik-LLM**: Thinking Mode DISABLED for Automatik decisions (8x faster)

**Recommended Models for Thinking Mode:**
- `qwen3:8b`, `qwen3:14b`, `qwen3:30b` (Ollama)
- `Qwen/Qwen3-8B-AWQ`, `Qwen/Qwen3-4B-AWQ` (vLLM)
- `qwq:32b` (dedicated reasoning model, Ollama only)

**Technical Details:**
- Ollama sends `thinking` + `content` in separate message fields
- vLLM uses Qwen3's chat template with `enable_thinking` flag
- Both backends wrap output in `<think>...</think>` tags for unified formatting
- Formatting module (`aifred/lib/formatting.py`) renders collapsibles with compact paragraph formatting

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
│   │   └── tabbyapi.py       # TabbyAPI Backend (EXL2)
│   ├── components/        # Reflex UI Components
│   ├── lib/              # Core Libraries
│   │   ├── agent_core.py     # Main agent logic
│   │   ├── context_manager.py # History compression
│   │   ├── config.py         # Default settings
│   │   ├── settings.py       # Settings persistence
│   │   └── vector_cache.py   # ChromaDB Vector Cache
│   └── state.py          # Reflex State Management
├── prompts/              # System Prompts
├── scripts/              # Utility Scripts
│   ├── download_all_models.sh     # Multi-Backend Model Downloader
│   ├── download_ollama_models.sh  # Ollama GGUF Models
│   ├── download_vllm_models.sh    # vLLM AWQ Models
│   ├── run_aifred.sh              # Development Runner
│   └── chroma_maintenance.py      # Vector Cache Maintenance
├── docs/                 # Documentation
│   ├── vllm/                      # vLLM-specific docs
│   └── GPU_COMPATIBILITY.md       # GPU compatibility matrix
└── CHANGELOG.md          # Project Changelog
```

### History Compression System

At 70% context utilization, older conversations are automatically compressed:

- **Trigger**: 70% of context window occupied
- **Compression**: 3 Q&A pairs → 1 summary
- **Efficiency**: ~6:1 compression ratio
- **FIFO**: Maximum 10 summaries (oldest are deleted)
- **Safety**: At least 1 current conversation remains visible

### Vector Cache & RAG System

AIfred uses a multi-tier cache system based on **semantic similarity** (Cosine Distance). **New in v1.3.0**: Pure semantic deduplication without time dependency + intelligent cache usage for explicit research keywords.

#### Cache Decision Logic

**Phase 0: Explicit Research Keywords** (NEW in v1.3.0)
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

#### Semantic Deduplication (v1.3.0)

**When Saving to Vector Cache:**
```
New Research Result → Check for Semantic Duplicates
└─ Distance < 0.3 (semantically similar)
   └─ ✅ ALWAYS Update (time-independent!)
      - Delete old entry
      - Save new entry
      - Guaranteed: Latest data is used
```

**Before (v1.2.0):**
- Time-based logic: < 5min = Skip, ≥ 5min = Update
- Led to race conditions and duplicates

**Now (v1.3.0):**
- Purely semantic: Distance < 0.3 = ALWAYS Update
- No more time checks → Consistent behavior

#### Cache Distance Thresholds

| Distance | Confidence | Behavior | Example |
|----------|-----------|----------|---------|
| `0.0 - 0.05` | EXACT | Explicit research uses cache | Identical query |
| `0.05 - 0.5` | HIGH | Direct cache hit | "Python tutorial" vs "Python guide" |
| `0.5 - 1.2` | MEDIUM | RAG candidate (relevance check via LLM) | "Python" vs "FastAPI" |
| `1.2+` | LOW | Cache miss → Research decision | "Python" vs "Weather" |

#### ChromaDB Maintenance Tool (v1.3.0)

**New maintenance tool** for Vector Cache:
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

#### Configuration

Cache behavior in `aifred/lib/config.py`:

```python
# Cache Distance Thresholds
CACHE_DISTANCE_DUPLICATE = 0.5   # < 0.5 = potential cache hit
CACHE_DISTANCE_MEDIUM = 0.5      # 0.5-1.2 = RAG range
CACHE_DISTANCE_RAG = 1.2         # < 1.2 = similar enough for RAG context

# Time Thresholds
CACHE_TIME_THRESHOLD = 300       # 5 minutes (in seconds)
```

**RAG Relevance Check**: Uses Automatik-LLM with dedicated prompt (`prompts/de/rag_relevance_check.txt`)

---

## 🔧 Configuration

All important parameters in `aifred/lib/config.py`:

```python
# Deployment Mode (Production vs Development)
USE_SYSTEMD_RESTART = True  # True for Production, False for Development

# History Compression
HISTORY_COMPRESSION_THRESHOLD = 0.7  # 70% Context
HISTORY_MESSAGES_TO_COMPRESS = 6     # 3 Q&A pairs
HISTORY_MIN_MESSAGES_BEFORE_COMPRESSION = 10

# LLM Settings (Default Models)
DEFAULT_SETTINGS = {
    "model": "qwen3:30b-instruct",      # Main-LLM (Tesla P40 optimized)
    "automatik_model": "qwen3:8b",      # Automatik decisions
}

# Temperature Presets
TEMPERATURE_PRESETS = {
    "faktisch": 0.2,
    "gemischt": 0.5,
    "kreativ": 0.8
}
```

### HTTP Timeout Configuration

In `aifred/backends/ollama.py`:
- **HTTP Client Timeout**: 300 seconds (5 minutes)
- Increased from 60s for large research requests with 30KB+ context
- Prevents timeout errors during first token generation

### Restart Button Behavior

The AIfred restart button can work in two modes:

- **Production Mode** (`USE_SYSTEMD_RESTART = True`):
  - Restarts the complete systemd service
  - Requires Polkit rule for sudo-less execution
  - For production systems with systemd

- **Development Mode** (`USE_SYSTEMD_RESTART = False`):
  - Soft-restart: Only clears caches and history
  - Keeps running instance for hot-reload
  - For local development without service

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
```

See [systemd/README.md](systemd/README.md) for details, troubleshooting, and monitoring.

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
Description=AIfred Intelligence Voice Assistant
After=network.target ollama.service aifred-chromadb.service
Requires=ollama.service aifred-chromadb.service

[Service]
Type=simple
User=mp
Group=mp
WorkingDirectory=/home/mp/Projekte/AIfred-Intelligence
Environment="PATH=/home/mp/Projekte/AIfred-Intelligence/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"
Environment="AIFRED_ENV=prod"
ExecStart=/home/mp/Projekte/AIfred-Intelligence/venv/bin/python -m reflex run --frontend-port 3002 --backend-port 8002 --backend-host 0.0.0.0
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Environment Variable `AIFRED_ENV` Explained**:
- `AIFRED_ENV=dev` (default): API-URL = `http://172.30.8.72:8002` (main machine/WSL with RTX 3060)
- `AIFRED_ENV=prod`: API-URL = `https://narnia.spdns.de:8443` (MiniPC with Tesla P40)

Without `AIFRED_ENV=prod`, all API requests are forwarded to the development machine, even if Nginx is correctly configured!

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

## 🛠️ Development

### Debug Logs
```bash
tail -f logs/aifred_debug.log
```

### Run Tests
```bash
pytest tests/
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

## 📝 Session Notes - November 3, 2025

### Internationalization (i18n) Implementation
- Complete translation table for UI strings
- Automatic language detection for prompts (de/en based on user input)
- Manual UI language switcher added to settings
- English prompt files completed (were incomplete)

### Network and Configuration Adjustments
- Fixed `api_url` in `rxconfig.py` to local IP for development environment
- Environment-dependent configuration: `AIFRED_ENV=dev` vs `AIFRED_ENV=prod`
- Fixed issue: Requests were forwarded to Mini-PC instead of processed locally
- Development: `http://172.30.8.72:3002` (with RTX 3060), Production: `https://narnia.spdns.de:8443`

### Bugfixes
- Fixed parameter error: `cache_metadata` → `cache_info` in `get_decision_making_prompt()` calls
- Now works correctly with the defined function signature

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file

---

**Version**: 2.1.0 (November 2025)
**Status**: Production-Ready 🚀
