**🌍 Sprachen:** [English](README.md) | [Deutsch](README.de.md)

---

# 🤖 AIfred Intelligence - Fortschrittlicher KI-Assistent

**Produktionsreifer KI-Assistent mit Multi-LLM-Unterstützung, Web-Recherche & Sprachschnittstelle**

AIfred Intelligence ist ein fortschrittlicher KI-Assistent mit automatischer Web-Recherche, Multi-Model-Support und History-Kompression für unbegrenzte Konversationen.

---

## 🎉 Neueste Updates (2025-11-15)

### 🔍 Verbessertes Debug-Logging & Query-Anzeige
- ✅ **Konsistente Debug-Ausgabe** über alle Recherche-Modi (Eigenes Wissen, Automatik, Schnell, Ausführlich)
- ✅ **Präzises Preload-Timing** mit `✅ Haupt-LLM vorgeladen (X.Xs)` in allen Modi
- ✅ **Optimierte Query-Anzeige** zeigt LLM-generierte Suchbegriffe: `🔎 Optimierte Query: [terms]`
- ✅ **Backend-abhängiges Timing**: Ollama (echte Ladezeit) vs vLLM/TabbyAPI (Vorbereitungszeit)
- 🔧 Umfassende Debug-Meldungen hinzugefügt: Token-Statistiken, Temperature, TTFT, Tokens/s
- **Auswirkung**: Professionelle Debug-Ausgabe, einfachere Performance-Optimierung, bessere Qualitätsbewertung der Web-Recherche

### 🔧 Persistenz des Research-Modus (2025-11-14)
- ✅ **Research-Modus bleibt erhalten** über Anwendungsneustarts hinweg
- 🔧 Fehlender `_save_settings()`-Aufruf in `set_research_mode_display()` behoben
- **Auswirkung**: Dein bevorzugter Research-Modus (Automatik/Schnell/Ausführlich/Keiner) wird gespeichert

### 🎯 Progress-UI-System vollständig - MEILENSTEIN (2025-11-14)
- ✅ **Vollständiges Progress-Feedback** über alle 4 Research-Modi (Automatik, Schnell, Ausführlich, Keiner)
- ✅ **Pulsierende Animation** für "Generiere Antwort" in allen Modi (inklusive "Eigenes Wissen")
- ✅ **Web-Scraping-Fortschrittsbalken** jetzt sichtbar (1/3, 2/3, 3/3) mit oranger Füllung
- ✅ **Dynamischer Statustext** zeigt Systemaktivität in Echtzeit
- **Auswirkung**: Professionelles, konsistentes UI-Feedback - Nutzer wissen immer, was das System gerade tut

Siehe [CHANGELOG.md](CHANGELOG.md) für detaillierte Änderungen.

---

## ✨ Features

### 🎯 Kern-Features
- **Multi-Backend-Unterstützung**: Ollama (GGUF), vLLM (AWQ), TabbyAPI (EXL2)
- **Qwen3-Denkmodus**: Chain-of-Thought-Reasoning für komplexe Aufgaben (Ollama + vLLM)
- **Automatische Web-Recherche**: KI entscheidet selbst, wann Recherche nötig ist
- **History-Kompression**: Intelligente Kompression bei 70% Context-Auslastung
- **Sprachschnittstelle**: Speech-to-Text und Text-to-Speech Integration
- **Vector-Cache**: ChromaDB-basierter semantischer Cache für Web-Recherchen (Docker)
- **Backend-spezifische Einstellungen**: Jedes Backend merkt sich seine bevorzugten Modelle

### 🔧 Technische Highlights
- **Reflex-Framework**: React-Frontend aus Python generiert
- **WebSocket-Streaming**: Echtzeit-Updates ohne Polling
- **Adaptive Temperatur**: KI wählt Temperatur basierend auf Fragetyp
- **Token-Management**: Dynamische Context-Window-Berechnung
- **Debug-Konsole**: Umfangreiches Logging und Monitoring
- **ChromaDB-Server-Modus**: Thread-sichere Vector-DB via Docker (0.0 Distance für exakte Matches)
- **GPU-Erkennung**: Automatische Erkennung und Warnung bei inkompatiblen Backend-GPU-Kombinationen ([docs/GPU_COMPATIBILITY.md](docs/GPU_COMPATIBILITY.md))

---

## 🔄 Research Mode Workflows

AIfred bietet 4 verschiedene Research-Modi, die je nach Anforderung unterschiedliche Strategien verwenden. Hier ist der detaillierte Ablauf jedes Modus:

### 📊 LLM Calls Übersicht

| Modus | Min LLM Calls | Max LLM Calls | Typische Dauer |
|-------|---------------|---------------|----------------|
| **Eigenes Wissen** | 1 | 1 | 5-30s |
| **Automatik** (Cache Hit) | 0 | 0 | <1s |
| **Automatik** (Direct Answer) | 2 | 3 | 5-35s |
| **Automatik** (Web Research) | 4 | 5 | 15-60s |
| **Websuche Schnell** | 3 | 4 | 10-40s |
| **Websuche Ausführlich** | 3 | 4 | 15-60s |

---

### 1️⃣ Eigenes Wissen Mode (Direct LLM)

**Einfachster Modus**: Direkter LLM-Aufruf ohne Web-Recherche oder KI-Entscheidung.

**Workflow:**
```
1. Message Building
   └─ Build from chat history
   └─ Inject system_minimal prompt (mit Timestamp)

2. Model Preloading (Ollama only)
   └─ backend.preload_model() - misst echte Ladezeit
   └─ vLLM/TabbyAPI: Skip (bereits in VRAM)

3. Token Management
   └─ estimate_tokens(messages, model_name)
   └─ calculate_dynamic_num_ctx()

4. LLM Call - Main Response
   ├─ Model: Haupt-LLM (z.B. Qwen2.5-32B)
   ├─ Temperature: Manual (User-Einstellung)
   ├─ Streaming: Ja (Echtzeit-Updates)
   └─ TTFT + Tokens/s Messung

5. Format & Save
   └─ format_thinking_process() für <think> Tags
   └─ Update chat history

6. History Compression Check (NACH jeder LLM-Antwort)
   ├─ Berechne Token-Auslastung: current_tokens / context_limit * 100
   ├─ IF Auslastung > 70%:
   │  ├─ Debug: "🗜️ History-Kompression startet: 78% Auslastung (21,800 / 28,000 tokens)"
   │  ├─ Wähle älteste 6 Messages (3 Frage-Antwort-Paare)
   │  ├─ LLM Call (Automatik-LLM):
   │  │  ├─ Prompt: history_compression
   │  │  ├─ Input: 6 Messages (User + Assistant abwechselnd)
   │  │  ├─ Output: 1 kompakte Zusammenfassung (~150 Wörter)
   │  │  └─ Kompressionsrate: ~6:1 (z.B. 3000 Tokens → 500 Tokens)
   │  ├─ Ersetze 6 Messages durch 1 Summary-Message
   │  ├─ Speichere in summaries[] (FIFO, max 10 Summaries)
   │  └─ Debug: "📦 History komprimiert: 78% → 52% Auslastung (21,800 → 14,600 tokens, 6→1 messages, 3 Summaries total)"
   └─ ELSE: Debug: "📊 History Compression Check: 45% Auslastung (12,500 / 28,000 tokens) - keine Kompression nötig"
```

**LLM Calls:** 1 Haupt-LLM + optional 1 Compression-LLM (bei >70% Context)
**Async Tasks:** Keine
**Code:** `aifred/state.py` Lines 974-1117

---

### 2️⃣ Automatik Mode (AI Decision System)

**Intelligentester Modus**: KI entscheidet selbst, ob Web-Recherche nötig ist.

#### Phase 1: Vector Cache Check
```
1. Query ChromaDB für ähnliche Fragen
   └─ Distance < 0.5: HIGH Confidence → Cache Hit
   └─ Distance ≥ 0.5: CACHE_MISS → Weiter

2. IF CACHE HIT:
   └─ Antwort direkt aus Cache
   └─ RETURN (0 LLM Calls!)
```

#### Phase 2: RAG Context Check
```
1. Query cache für RAG candidates (distance 0.5-1.2)

2. FOR EACH candidate:
   ├─ LLM Relevance Check (Automatik-LLM)
   │  └─ Prompt: rag_relevance_check
   │  └─ Options: temp=0.1, num_ctx=2048
   └─ Keep if relevant

3. Build formatted context from relevant entries
```

#### Phase 3: Keyword Override Check
```
1. Check für explicit research keywords:
   └─ "recherchiere", "suche im internet", "google", etc.

2. IF keyword found:
   └─ Trigger fresh web research (mode='deep')
   └─ BYPASS Automatik decision
```

#### Phase 4: Automatik Decision
```
1. LLM Call - Decision Making
   ├─ Model: Automatik-LLM (z.B. Qwen2.5-3B)
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
   ├─ Response: "FAKTISCH" | "KREATIV" | "GEMISCHT"
   └─ Map to temperature: 0.2 | 0.8 | 0.5

4. LLM Call - Main Response
   ├─ Model: Haupt-LLM
   ├─ Temperature: From intent detection or manual
   ├─ Streaming: Ja
   └─ TTFT + Tokens/s Messung

5. Format & Update History
   └─ Metadata: "Cache+LLM (RAG)" or "LLM"

6. History Compression Check (wie in Eigenes Wissen Mode)
   └─ Automatische Kompression bei >70% Context-Auslastung
```

**LLM Calls:**
- Cache Hit: 0 + optional 1 Compression
- RAG Context: 2-6 + optional 1 Compression
- Web Research: 4-5 + optional 1 Compression
- Direct Answer: 2-3 + optional 1 Compression

**Code:** `aifred/lib/conversation_handler.py`

---

### 3️⃣ Websuche Schnell Mode (Quick Research)

**Schnellster Web-Research Modus**: Top 3 URLs, optimiert für Speed.

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
   ├─ Model: Haupt-LLM
   ├─ Context: ~3 sources, 5K-10K tokens
   ├─ Streaming: Ja
   └─ TTFT + Tokens/s Messung

4. Cache Decision (NUR bei Web-Recherche)
   ├─ Check for volatile keywords (z.B. "heute", "aktuell", "jetzt")
   │  └─ IF volatile: Skip caching (zeitkritische Info)
   ├─ LLM Call (Automatik-LLM) - Cacheability Check
   │  ├─ Prompt: cache_decision
   │  ├─ Input: User-Query + LLM-Antwort
   │  ├─ Entscheidung basiert auf:
   │  │  ├─ Zeitlose Fakten? (z.B. "Was ist Python?") → cacheable
   │  │  ├─ Zeitgebundene Events? (z.B. "aktuelle News") → not_cacheable
   │  │  ├─ Persönliche Präferenzen? (z.B. "bestes Restaurant") → not_cacheable
   │  │  └─ Volatile Daten? (z.B. Wetter, Aktienkurse) → not_cacheable
   │  └─ Response: 'cacheable' | 'not_cacheable'
   ├─ IF cacheable:
   │  ├─ Semantic Duplicate Check (distance < 0.3 zu existierenden Einträgen)
   │  │  └─ IF duplicate: Lösche alten Eintrag (garantiert neueste Daten)
   │  ├─ cache.add(query, answer, sources, metadata)
   │  └─ Debug: "💾 Antwort gecacht" oder "🔄 Cache-Eintrag aktualisiert"
   └─ ELSE: Debug: "⏭️ Antwort nicht gecacht (volatil/zeitgebunden)"

5. Format & Update History
   └─ Metadata: "(Agent: quick, {n} Quellen)"

6. History Compression Check (wie in Eigenes Wissen Mode)
   └─ Automatische Kompression bei >70% Context-Auslastung
```

**LLM Calls:**
- With Cache: 1-2 + optional 1 Compression
- Without Cache: 3-4 + optional 1 Compression

**Async Tasks:**
- Parallel URL scraping (3 URLs)
- Background LLM preload (Ollama only)

**Code:** `aifred/lib/research/orchestrator.py` + Submodules

---

### 4️⃣ Websuche Ausführlich Mode (Deep Research)

**Gründlichster Modus**: Top 7 URLs für maximale Informationstiefe.

**Workflow:** Identisch zu Websuche Schnell, mit folgenden Unterschieden:

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

→ Mehr Quellen = reicherer Kontext
→ Längere LLM Inference (10-40s vs 5-30s)
```

**LLM Calls:** Identisch zu Quick (3-4 + optional 1 Compression)
**Async Tasks:** Mehr URLs parallel (7 vs 3)
**Trade-off:** Höhere Qualität vs längere Dauer
**History Compression:** Wie alle Modi - automatisch bei >70% Context

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
│ EIGENES  │         │ AUTOMATIK    │       │ WEB         │
│ WISSEN   │         │ (AI Decides) │       │ RESEARCH    │
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

### Voraussetzungen
- Python 3.10+
- **LLM Backend** (wähle eins):
  - **Ollama** (einfach, GGUF-Modelle) - empfohlen für Start
  - **vLLM** (schnell, AWQ-Modelle) - beste Performance (requires Compute Capability 7.5+)
  - **TabbyAPI** (ExLlamaV2/V3, EXL2-Modelle) - experimentell
- 8GB+ RAM (12GB+ empfohlen für größere Modelle)
- Docker (für ChromaDB Vector Cache)
- **GPU**: NVIDIA GPU empfohlen (siehe [GPU Compatibility Guide](docs/GPU_COMPATIBILITY.md))

### Setup

1. **Repository klonen**:
```bash
git clone https://github.com/yourusername/AIfred-Intelligence.git
cd AIfred-Intelligence
```

2. **Virtual Environment erstellen**:
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# oder
venv\Scripts\activate     # Windows
```

3. **Dependencies installieren**:
```bash
pip install -r requirements.txt
```

4. **Umgebungsvariablen** (.env):
```env
# API Keys für Web-Recherche
BRAVE_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here

# Ollama Konfiguration
OLLAMA_BASE_URL=http://localhost:11434
```

5. **LLM Models installieren**:

**Option A: Alle Models (Empfohlen)**
```bash
# Master-Script für beide Backends
./scripts/download_all_models.sh
```

**Option B: Nur Ollama (GGUF) - Einfachste Installation**
```bash
# Ollama Models (GGUF Q4/Q8)
./scripts/download_ollama_models.sh

# Empfohlene Core-Modelle:
# - qwen3:30b-instruct (18GB) - Haupt-LLM, 256K context
# - qwen3:8b (5.2GB) - Automatik, optional thinking
# - qwen2.5:3b (1.9GB) - Ultra-schnelle Automatik
```

**Option C: Nur vLLM (AWQ) - Beste Performance**
```bash
# vLLM installieren (falls noch nicht geschehen)
pip install vllm

# vLLM Models (AWQ Quantization)
./scripts/download_vllm_models.sh

# Empfohlene Modelle:
# - Qwen3-8B-AWQ (~5GB, 40K→128K mit YaRN)
# - Qwen3-14B-AWQ (~8GB, 32K→128K mit YaRN)
# - Qwen2.5-14B-Instruct-AWQ (~8GB, 128K native)

# vLLM Server starten mit YaRN (64K context)
./venv/bin/vllm serve Qwen/Qwen3-14B-AWQ \
  --quantization awq_marlin \
  --port 8001 \
  --rope-scaling '{"rope_type":"yarn","factor":2.0,"original_max_position_embeddings":32768}' \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.85

# Oder als systemd Service
sudo cp vllm_qwen3_awq.service /etc/systemd/system/
sudo systemctl enable vllm_qwen3_awq
sudo systemctl start vllm_qwen3_awq
```

**Option C: TabbyAPI (EXL2) - Experimentell**
```bash
# Noch nicht vollständig implementiert
# Siehe: https://github.com/theroyallab/tabbyAPI
```

6. **ChromaDB Vector Cache starten** (Docker):
```bash
cd docker
docker compose up -d chromadb
cd ..
```

**Optional: SearXNG auch starten** (lokale Suchmaschine):
```bash
cd docker
docker compose --profile full up -d
cd ..
```

**ChromaDB Cache zurücksetzen** (bei Bedarf):

*Option 1: Kompletter Neustart (löscht alle Daten)*
```bash
cd docker
docker compose stop chromadb
cd ..
rm -rf aifred_vector_cache/
cd docker
docker compose up -d chromadb
cd ..
```

*Option 2: Nur Collection löschen (während Container läuft)*
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
    print('✅ Collection gelöscht')
except Exception as e:
    print(f'⚠️ Fehler: {e}')
"
```

7. **Starten**:
```bash
reflex run
```

Die App läuft dann unter: http://localhost:3002

---

## ⚙️ Backend-Wechsel & Settings

### Multi-Backend Support

AIfred unterstützt verschiedene LLM-Backends, die in der UI dynamisch gewechselt werden können:

- **Ollama**: GGUF-Modelle (Q4/Q8), einfachste Installation
- **vLLM**: AWQ-Modelle (4-bit), beste Performance mit AWQ Marlin Kernel
- **TabbyAPI**: EXL2-Modelle (ExLlamaV2/V3), experimentell

### GPU Compatibility Detection

AIfred erkennt automatisch beim Start deine GPU und warnt vor inkompatiblen Backend-Konfigurationen:

- **Tesla P40 / GTX 10 Series** (Pascal): Nutze Ollama (GGUF) - vLLM/AWQ wird nicht unterstützt
- **RTX 20+ Series** (Turing/Ampere/Ada): vLLM (AWQ) empfohlen für beste Performance

Detaillierte Informationen: [GPU_COMPATIBILITY.md](docs/GPU_COMPATIBILITY.md)

### Settings-Persistenz

Settings werden in `~/.config/aifred/settings.json` gespeichert:

**Per-Backend Modell-Speicherung:**
- Jedes Backend merkt sich seine zuletzt verwendeten Modelle
- Beim Backend-Wechsel werden automatisch die richtigen Modelle wiederhergestellt
- Beim ersten Start werden Defaults aus `aifred/lib/config.py` verwendet

**Beispiel Settings-Struktur:**
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

**Chain-of-Thought Reasoning für komplexe Aufgaben:**

AIfred unterstützt Thinking Mode für Qwen3-Modelle in Ollama und vLLM Backends:

- **Thinking Mode ON**: Temperature 0.6, generiert `<think>...</think>` Blocks mit Denkprozess
- **Thinking Mode OFF**: Temperature 0.7, direkte Antworten ohne CoT
- **UI**: Toggle erscheint nur bei Qwen3/QwQ-Modellen
- **Backends**:
  - **Ollama**: Nutzt `"think": true` API-Parameter, liefert separate `thinking` und `content` Felder
  - **vLLM**: Nutzt `chat_template_kwargs: {"enable_thinking": true/false}` in `extra_body`
  - **TabbyAPI**: Noch nicht implementiert
- **Formatierung**: Denkprozess als ausklappbares Collapsible mit Modellname und Inferenzzeit
- **Automatik-LLM**: Thinking Mode für Automatik-Entscheidungen DEAKTIVIERT (8x schneller)

**Empfohlene Modelle für Thinking Mode:**
- `qwen3:8b`, `qwen3:14b`, `qwen3:30b` (Ollama)
- `Qwen/Qwen3-8B-AWQ`, `Qwen/Qwen3-4B-AWQ` (vLLM)
- `qwq:32b` (dediziertes Reasoning-Modell, nur Ollama)

**Technische Details:**
- Ollama sendet `thinking` + `content` in separaten Message-Feldern
- vLLM nutzt Qwen3's Chat-Template mit `enable_thinking` Flag
- Beide Backends wrappen Output in `<think>...</think>` Tags für einheitliche Formatierung
- Formatting-Modul (`aifred/lib/formatting.py`) rendert Collapsibles mit kompakter Absatz-Formatierung

---

## 🏗️ Architektur

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
│   │   ├── agent_core.py     # Haupt-Agent-Logik
│   │   ├── context_manager.py # History-Kompression
│   │   ├── config.py         # Default Settings
│   │   ├── settings.py       # Settings Persistence
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

Bei 70% Context-Auslastung werden automatisch ältere Konversationen komprimiert:

- **Trigger**: 70% des Context Windows belegt
- **Kompression**: 3 Frage-Antwort-Paare → 1 Summary
- **Effizienz**: ~6:1 Kompressionsrate
- **FIFO**: Maximal 10 Summaries (älteste werden gelöscht)
- **Safety**: Mindestens 1 aktuelle Konversation bleibt sichtbar

### Vector Cache & RAG System

AIfred nutzt ein mehrstufiges Cache-System basierend auf **semantischer Ähnlichkeit** (Cosine Distance). **Neu in v1.3.0**: Pure Semantic Deduplication ohne Zeit-Abhängigkeit + intelligente Cache-Nutzung bei expliziten Recherche-Keywords.

#### Cache-Entscheidungs-Logik

**Phase 0: Explizite Recherche-Keywords** (NEW in v1.3.0)
```
User Query: "recherchiere Python" / "google Python" / "suche im internet Python"
└─ Explizites Keyword erkannt → Cache-Check ZUERST
   ├─ Distance < 0.05 (praktisch identisch)
   │  └─ ✅ Cache-Hit (0.15s statt 100s) - Zeigt Alter transparent an
   └─ Distance ≥ 0.05 (nicht identisch)
      └─ Neue Web-Recherche (User will neue Daten)
```

**Phase 1a: Direct Cache Hit Check**
```
User Query → ChromaDB Similarity Search
├─ Distance < 0.5 (HIGH Confidence)
│  └─ ✅ Use Cached Answer (sofort, keine Zeit-Checks mehr!)
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
   └─ NO  → Pure LLM Answer (Source: "LLM-Trainingsdaten")
```

#### Semantic Deduplication (v1.3.0)

**Beim Speichern in Vector Cache:**
```
New Research Result → Check for Semantic Duplicates
└─ Distance < 0.3 (semantisch ähnlich)
   └─ ✅ IMMER Update (zeitunabhängig!)
      - Löscht alten Eintrag
      - Speichert neuen Eintrag
      - Garantiert: Neueste Daten werden verwendet
```

**Vorher (v1.2.0):**
- Zeit-basierte Logik: < 5min = Skip, ≥ 5min = Update
- Führte zu Race Conditions und Duplikaten

**Jetzt (v1.3.0):**
- Rein semantisch: Distance < 0.3 = IMMER Update
- Keine Zeit-Checks mehr → Konsistentes Verhalten

#### Cache Distance Thresholds

| Distance | Confidence | Behavior | Example |
|----------|-----------|----------|---------|
| `0.0 - 0.05` | EXACT | Explizite Recherche nutzt Cache | Identische Query |
| `0.05 - 0.5` | HIGH | Direct cache hit | "Python tutorial" vs "Python Anleitung" |
| `0.5 - 1.2` | MEDIUM | RAG candidate (relevance check via LLM) | "Python" vs "FastAPI" |
| `1.2+` | LOW | Cache miss → Research decision | "Python" vs "Weather" |

#### ChromaDB Maintenance Tool (v1.3.0)

**Neues Wartungstool** für Vector Cache:
```bash
# Stats anzeigen
python3 chroma_maintenance.py --stats

# Duplikate finden
python3 chroma_maintenance.py --find-duplicates

# Duplikate entfernen (Dry-Run)
python3 chroma_maintenance.py --remove-duplicates

# Duplikate entfernen (Execute)
python3 chroma_maintenance.py --remove-duplicates --execute

# Alte Einträge löschen (> 30 Tage)
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
User: "Was ist Python?" → Web Research → Cache Entry 1 (d=0.0)
User: "Was ist FastAPI?" → RAG finds Entry 1 (d=0.7)
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

## 🔧 Konfiguration

Alle wichtigen Parameter in `aifred/lib/config.py`:

```python
# Deployment Mode (Production vs Development)
USE_SYSTEMD_RESTART = True  # True für Production, False für Development

# History Compression
HISTORY_COMPRESSION_THRESHOLD = 0.7  # 70% Context
HISTORY_MESSAGES_TO_COMPRESS = 6     # 3 Q&A Paare
HISTORY_MIN_MESSAGES_BEFORE_COMPRESSION = 10

# LLM Settings (Default Models)
DEFAULT_SETTINGS = {
    "model": "qwen3:30b-instruct",      # Haupt-LLM (Tesla P40 optimiert)
    "automatik_model": "qwen3:8b",      # Automatik-Entscheidungen
}

# Temperature Presets
TEMPERATURE_PRESETS = {
    "faktisch": 0.2,
    "gemischt": 0.5,
    "kreativ": 0.8
}
```

### HTTP Timeout Konfiguration

In `aifred/backends/ollama.py`:
- **HTTP Client Timeout**: 300 Sekunden (5 Minuten)
- Erhöht von 60s für große Research-Anfragen mit 30KB+ Context
- Verhindert Timeout-Fehler bei erster Token-Generation

### Restart-Button Verhalten

Der AIfred Restart-Button kann in zwei Modi arbeiten:

- **Production Mode** (`USE_SYSTEMD_RESTART = True`):
  - Startet den kompletten systemd-Service neu
  - Benötigt Polkit-Regel für sudo-lose Ausführung
  - Für produktive Systeme mit systemd

- **Development Mode** (`USE_SYSTEMD_RESTART = False`):
  - Soft-Restart: Löscht nur Caches und History
  - Behält laufende Instanz für Hot-Reload
  - Für lokale Entwicklung ohne Service

---

## 📦 Deployment

### Systemd Service

Für produktiven Betrieb als Service sind vorkonfigurierte Service-Dateien im `systemd/` Verzeichnis verfügbar.

**⚠️ WICHTIG**: Die Umgebungsvariable `AIFRED_ENV=prod` **MUSS** gesetzt sein, damit AIfred auf dem MiniPC läuft und nicht auf den Entwicklungsrechner weiterleitet!

#### Schnellinstallation

```bash
# 1. Service-Dateien kopieren
sudo cp systemd/aifred-chromadb.service /etc/systemd/system/
sudo cp systemd/aifred-intelligence.service /etc/systemd/system/

# 2. Services aktivieren und starten
sudo systemctl daemon-reload
sudo systemctl enable aifred-chromadb.service aifred-intelligence.service
sudo systemctl start aifred-chromadb.service aifred-intelligence.service

# 3. Status prüfen
systemctl status aifred-chromadb.service
systemctl status aifred-intelligence.service
```

Siehe [systemd/README.md](systemd/README.md) für Details, Troubleshooting und Monitoring.

#### Service-Dateien (Referenz)

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

**Umgebungsvariable `AIFRED_ENV` erklärt**:
- `AIFRED_ENV=dev` (Standard): API-URL = `http://172.30.8.72:8002` (Hauptrechner/WSL mit RTX 3060)
- `AIFRED_ENV=prod`: API-URL = `https://narnia.spdns.de:8443` (MiniPC mit Tesla P40)

Ohne `AIFRED_ENV=prod` werden alle API-Requests an den Entwicklungsrechner weitergeleitet, auch wenn Nginx korrekt konfiguriert ist!

2. Service aktivieren:
```bash
sudo systemctl daemon-reload
sudo systemctl enable aifred-intelligence
sudo systemctl start aifred-intelligence
```

3. **Optional: Polkit-Regel für Restart ohne sudo**

Für den Restart-Button in der Web-UI ohne Passwort-Abfrage:

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

### Tests ausführen
```bash
pytest tests/
```

## 🔨 Troubleshooting

### Häufige Probleme

#### HTTP ReadTimeout bei Research-Anfragen
**Problem**: `httpx.ReadTimeout` nach 60 Sekunden bei großen Recherchen
**Lösung**: Timeout ist bereits auf 300s erhöht in `aifred/backends/ollama.py`
**Falls weiterhin Probleme**: Ollama Service neustarten mit `systemctl restart ollama`

#### Service startet nicht
**Problem**: AIfred Service startet nicht oder stoppt sofort
**Lösung**:
```bash
# Logs prüfen
journalctl -u aifred-intelligence -n 50
# Ollama Status prüfen
systemctl status ollama
```

#### Restart-Button funktioniert nicht
**Problem**: Restart-Button in Web-UI ohne Funktion
**Lösung**: Polkit-Regel prüfen in `/etc/polkit-1/rules.d/50-aifred-restart.rules`

---

## 📚 Dokumentation

Weitere Dokumentation im `docs/` Verzeichnis:
- [Architecture Overview](docs/architecture/)
- [API Documentation](docs/api/)
- [Migration Guide](docs/infrastructure/MIGRATION.md)

---

## 🤝 Contributing

Pull Requests sind willkommen! Für größere Änderungen bitte erst ein Issue öffnen.

---

## 📝 Session Notes - 03. November 2025

### Internationalisierung (i18n) Implementierung
- Vollständige Übersetzungstabelle für UI-Strings
- Automatische Spracherkennung für Prompts (de/en basierend auf Nutzereingabe)
- Manueller UI-Sprachumschalter in den Einstellungen hinzugefügt
- Englische Prompt-Dateien vervollständigt (waren unvollständig)

### Netzwerk- und Konfigurationsanpassungen
- `api_url` in `rxconfig.py` auf lokale IP für Entwicklungsumgebung korrigiert
- Umgebungsabhängige Konfiguration: `AIFRED_ENV=dev` vs `AIFRED_ENV=prod`
- Problem behoben: Anfragen wurden zu Mini-PC weitergeleitet statt lokal verarbeitet
- Entwicklung: `http://172.30.8.72:3002` (mit RTX 3060), Produktion: `https://narnia.spdns.de:8443`

### Bugfixes
- Parameterfehler behoben: `cache_metadata` → `cache_info` in `get_decision_making_prompt()` Aufrufen
- Funktioniert jetzt korrekt mit der definierten Funktionssignatur

---

## 📄 License

MIT License - siehe [LICENSE](LICENSE) file

---

**Version**: 2.0.0 (November 2025)
**Status**: Production-Ready 🚀