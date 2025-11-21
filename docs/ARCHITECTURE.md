# AIfred Intelligence - Software Architecture

**Version:** 2.0 (nach Backend-Refactoring Januar 2025)
**Status:** Production-Ready
**Letzte Aktualisierung:** 2025-01-18

---

## 📋 Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [System-Architektur](#system-architektur)
3. [Backend Abstraction Layer](#backend-abstraction-layer)
4. [Context Management](#context-management)
5. [Research Pipeline](#research-pipeline)
6. [Vector Cache System](#vector-cache-system)
7. [State Management](#state-management)
8. [Datenfluss](#datenfluss)
9. [Wichtige Design-Entscheidungen](#wichtige-design-entscheidungen)

---

## Überblick

AIfred Intelligence ist ein modulares LLM-basiertes Assistenzsystem mit:
- **Multi-Backend Support**: Ollama, vLLM, TabbyAPI
- **Automatische Web-Recherche** mit Scraping & Context Building
- **Vector Cache** für semantisches Caching von Recherche-Ergebnissen
- **Streaming UI** mit Reflex (React-basiert)
- **VRAM-optimierte Context-Berechnung**

### High-Level Architektur

```
┌─────────────────────────────────────────────────────────────────┐
│                         REFLEX UI (React)                       │
│  • Chat Interface  • Settings  • Debug Console  • Progress UI   │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│                      STATE MANAGEMENT                           │
│              aifred/state.py (Global State)                     │
│  • Backend Switching  • vLLM Manager  • Session Management      │
└────────────────────┬────────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
┌───────▼────┐  ┌───▼────┐  ┌───▼──────┐
│  Ollama    │  │  vLLM  │  │ TabbyAPI │
│  Backend   │  │Backend │  │ Backend  │
└────────────┘  └────────┘  └──────────┘
     (Dynamic)   (Fixed)      (Fixed)
```

---

## System-Architektur

### Komponentenübersicht

```
aifred/
├── backends/               # Backend Abstraction Layer (NEW!)
│   ├── base.py            # Abstract Base Class für alle Backends
│   ├── ollama.py          # Ollama Backend (dynamisch)
│   ├── vllm.py            # vLLM Backend (fixed context)
│   └── tabbyapi.py        # TabbyAPI Backend (fixed context)
│
├── lib/
│   ├── context_manager.py      # Context Window Management
│   ├── conversation_handler.py # Conversation Flow Control
│   ├── llm_client.py           # LLM Client Wrapper
│   ├── vllm_manager.py         # vLLM Process Management
│   ├── gpu_utils.py            # VRAM Detection & Calculation
│   ├── vector_cache.py         # Semantic Caching (ChromaDB)
│   │
│   ├── research/               # Research Pipeline
│   │   ├── orchestrator.py    # Phase Orchestration
│   │   ├── query_processor.py # Query Optimization
│   │   ├── context_builder.py # RAG Context Building
│   │   └── scraping.py        # Parallel Web Scraping
│   │
│   └── tools/                  # Agent Tools
│       ├── scraper_tool.py    # Web Scraping (trafilatura)
│       └── base.py            # Tool Base Class
│
├── state.py                # Reflex State Management
└── aifred_intelligence.py  # Main Entry Point
```

---

## Backend Abstraction Layer

### Architektur-Prinzip: **Dependency Inversion**

Statt dass der Code überall `if backend_type == "vllm"` Checks macht, definiert jedes Backend seine **Capabilities** und **Verhalten** selbst.

### Base Class: `LLMBackend`

**Datei:** [`aifred/backends/base.py`](../aifred/backends/base.py)

```python
class LLMBackend(ABC):
    """Abstract base class for all LLM backends"""

    @abstractmethod
    async def chat(self, model: str, messages: List[LLMMessage],
                   options: Optional[LLMOptions] = None) -> LLMResponse:
        """Non-streaming chat completion"""
        pass

    @abstractmethod
    def chat_stream(self, model: str, messages: List[LLMMessage],
                    options: Optional[LLMOptions] = None) -> AsyncIterator[Dict]:
        """Streaming chat completion (async generator)"""
        pass

    @abstractmethod
    def get_capabilities(self) -> Dict[str, bool]:
        """Return backend capabilities and behavior flags"""
        pass

    @abstractmethod
    async def calculate_practical_context(self, model: str) -> tuple[int, list[str]]:
        """Calculate maximum practical context window for a model"""
        pass
```

### Capabilities System

Jedes Backend deklariert seine Fähigkeiten:

```python
# Ollama (dynamisch)
{
    "dynamic_models": True,      # Kann Modelle zur Laufzeit laden/entladen
    "dynamic_context": True,     # Context kann neu berechnet werden
    "supports_streaming": True,
    "requires_preload": False
}

# vLLM / TabbyAPI (fixed)
{
    "dynamic_models": False,     # Model fix beim Server-Start
    "dynamic_context": False,    # Context fix beim Server-Start
    "supports_streaming": True,
    "requires_preload": False
}
```

### Backend-Implementierungen

#### 1. Ollama Backend

**Datei:** [`aifred/backends/ollama.py`](../aifred/backends/ollama.py)

**Besonderheiten:**
- **Dynamische Model-Verwaltung**: Kann Modelle zur Laufzeit laden/entladen
- **Dynamische Context-Berechnung**: Berechnet Context basierend auf aktuellem VRAM-Status
- **VRAM-Optimierung**: Query via `/api/ps` für geladene Modelle

```python
async def calculate_practical_context(self, model: str) -> tuple[int, list[str]]:
    """
    Ollama: Dynamische VRAM-Berechnung

    1. Query current free VRAM (via pynvml)
    2. Check if model already loaded (via /api/ps)
    3. Calculate: available_vram / VRAM_CONTEXT_RATIO
    4. Clip to model's architectural limit
    """
    from ..lib.gpu_utils import calculate_vram_based_context

    model_limit, model_size_bytes = await self.get_model_context_limit(model)
    model_is_loaded = await self.is_model_loaded(model)

    num_ctx, debug_msgs = calculate_vram_based_context(
        model_name=model,
        model_size_bytes=model_size_bytes,
        model_context_limit=model_limit,
        model_is_loaded=model_is_loaded
    )

    return num_ctx, debug_msgs
```

#### 2. vLLM Backend

**Datei:** [`aifred/backends/vllm.py`](../aifred/backends/vllm.py)

**Besonderheiten:**
- **Fixed Context**: Context wird beim Server-Start gesetzt via `--max-model-len`
- **Class-Level Caching**: Startup-Context wird in `_global_startup_context` gecached
- **Kein Recalculation**: Context KANN NICHT zur Laufzeit geändert werden

```python
class vLLMBackend(LLMBackend):
    # Class-level cache (shared across ALL instances)
    _global_startup_context: Optional[int] = None
    _global_startup_context_debug: List[str] = []

    async def calculate_practical_context(self, model: str) -> tuple[int, list[str]]:
        """
        vLLM: Return cached startup context (FIXED)

        Raises RuntimeError if not set (server not started properly)
        """
        if vLLMBackend._global_startup_context is None:
            raise RuntimeError("vLLM startup context not set")

        return vLLMBackend._global_startup_context, vLLMBackend._global_startup_context_debug

    def set_startup_context(self, context: int, debug_messages: List[str]) -> None:
        """Called by vLLM Manager after server start"""
        vLLMBackend._global_startup_context = context
        vLLMBackend._global_startup_context_debug = debug_messages
```

**Warum Class Variables?**
- Backend-Instanzen werden oft temporär erstellt (z.B. in `state.py`)
- Instance Variables würden verloren gehen bei Garbage Collection
- Class Variables persistieren über alle Instanzen hinweg
- Einmal gesetzt → für alle zukünftigen Instanzen verfügbar

#### 3. TabbyAPI Backend

**Datei:** [`aifred/backends/tabbyapi.py`](../aifred/backends/tabbyapi.py)

**Besonderheiten:**
- Ähnlich wie vLLM: Fixed Context
- Fallback auf API-Query wenn Startup-Context nicht gesetzt
- Class-Level Caching wie vLLM

---

## Context Management

### VRAM-basierte Context-Berechnung

**Problem:** Modelle haben ein architektonisches Context-Limit (z.B. 262k tokens für Qwen3), aber VRAM begrenzt praktisch nutzbare Größe.

**Lösung:** Dynamische Berechnung basierend auf verfügbarem VRAM

### Formel (für Ollama)

```python
# 1. Query free VRAM (via pynvml)
free_vram_mb = get_free_vram_mb()

# 2. Subtract safety margins
usable_vram = free_vram_mb - VRAM_SAFETY_MARGIN  # -512 MB

# 3. Account for model if not loaded
if not model_is_loaded:
    usable_vram -= model_size_mb

# 4. Convert to tokens
max_tokens = usable_vram / VRAM_CONTEXT_RATIO  # ÷ 0.097 MB/token

# 5. Clip to architectural limit
final_context = min(max_tokens, model_context_limit)
```

### VRAM Context Ratio

**Empirisch gemessen** für Qwen3-30B AWQ:
- **12k tokens = 1163 MB VRAM** (KV Cache)
- **Ratio: 0.097 MB/token** (~97 KB/token)

**Config:** [`aifred/lib/config.py`](../aifred/lib/config.py)
```python
VRAM_CONTEXT_RATIO = 0.097  # MB VRAM per token
VRAM_SAFETY_MARGIN = 512    # Reserve für OS, Xorg, Whisper
```

### vLLM: Pre-Calculation Strategy

**Problem:** vLLM crashed wenn `--max-model-len` zu groß → musste neu starten → 120s Startup!

**Lösung:** Context VOR dem Start berechnen (in vLLM Manager)

```python
# vLLM Manager: Pre-calculate BEFORE starting server
free_vram_mb = get_free_vram_mb()
model_size_mb = get_model_size_bytes(model) / (1024**2)

# Reserve space for model + safety margin
reserved_mb = model_size_mb + VRAM_SAFETY_MARGIN  # ~512 MB safety buffer

available_for_kv = free_vram_mb - reserved_mb
hardware_limit = int(available_for_kv / VRAM_CONTEXT_RATIO)

# Start vLLM ONCE with calculated limit
vllm serve model --max-model-len {hardware_limit}
```

**Ergebnis:**
- ✅ Kein Crash mehr
- ✅ Nur 1x Start (~60s statt 120s)
- ✅ Context wird gecached für alle zukünftigen Requests

---

## Research Pipeline

### Architektur: **Phase-basierte Orchestration**

**Datei:** [`aifred/lib/research/orchestrator.py`](../aifred/lib/research/orchestrator.py)

```
┌──────────────────────────────────────────────────────────────┐
│                   PHASE 1: Decision                          │
│  • Automatik-LLM entscheidet: Recherche nötig? JA/NEIN     │
│  • Output: Boolean + Reasoning                              │
└────────────────┬─────────────────────────────────────────────┘
                 │
                 ├─► NEIN → Direct LLM Response
                 │
                 ▼ JA
┌──────────────────────────────────────────────────────────────┐
│                   PHASE 2: Query Optimization                │
│  • Automatik-LLM optimiert User-Query für Web-Suche        │
│  • Output: Optimized Query                                  │
└────────────────┬─────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│                   PHASE 3: Web Scraping                      │
│  • Web-Suche → URLs extrahieren                             │
│  • Parallel Scraping (trafilatura + Playwright Fallback)    │
│  • Output: Scraped Content                                  │
└────────────────┬─────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│              PHASE 3.5: Fallback (if 0 sources)              │
│  • Retry mit neuem Web-Search Query                         │
│  • Cloudflare/404/Timeout Handling                          │
└────────────────┬─────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│                   PHASE 4: Context Building                  │
│  • Scraped Content → Chunking (2000 words/source)           │
│  • RAG Context Assembly (max 20k tokens)                    │
│  • System Prompt + Context → LLM                            │
└────────────────┬─────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│                   PHASE 5: LLM Response                      │
│  • Haupt-LLM generiert Response                             │
│  • Streaming Output → UI                                    │
│  • Extract <volatility> Tag                                 │
└────────────────┬─────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│                   PHASE 6: Vector Cache                      │
│  • Store (Query + Response + Scraped Content + Volatility)  │
│  • Semantic Indexing (ChromaDB)                             │
│  • TTL-based Expiration                                      │
└──────────────────────────────────────────────────────────────┘
```

### Scraping Strategy

**Tool:** [`aifred/lib/tools/scraper_tool.py`](../aifred/lib/tools/scraper_tool.py)

1. **Primary: trafilatura** (fast, clean extraction)
   - Filtert automatisch: Werbung, Navigation, Cookie-Banner
   - Timeout: 10s
   - Retry bei Cloudflare/Timeout (max 2 attempts)

2. **Fallback: Playwright** (slower, JavaScript-capable)
   - Wenn trafilatura < 800 Wörter liefert
   - Rendert JavaScript-Content
   - Gut für SPAs

**Retry Logic:**
```python
MAX_RETRY_ATTEMPTS = 2
RETRY_DELAY = 3.0  # seconds

if download_failed and retry_attempt < MAX_RETRY_ATTEMPTS:
    time.sleep(RETRY_DELAY)
    return _scrape_with_trafilatura(url, retry_attempt + 1)
```

---

## Vector Cache System

### TTL-based Semantic Caching

**Datei:** [`aifred/lib/vector_cache.py`](../aifred/lib/vector_cache.py)

**Architektur:**
```
User Query
    ↓
┌───────────────────────────────────┐
│  1. Semantic Search (ChromaDB)   │
│     Distance < 0.5 → Cache Hit   │
└─────────┬─────────────────────────┘
          │
    ┌─────┴─────┐
    │           │
  HIT         MISS
    │           │
    ▼           ▼
┌─────────┐  ┌────────────────┐
│ Check   │  │ Run Research   │
│ TTL     │  │ + Store Cache  │
└─────────┘  └────────────────┘
    │
    ├─► VALID → Return Cached
    └─► EXPIRED → Run Research
```

### Volatility Levels (TTL)

```python
TTL_HOURS = {
    'DAILY': 24,        # News, aktuelle Events
    'WEEKLY': 168,      # Politik-Updates (7 Tage)
    'MONTHLY': 720,     # Semi-aktuelle Themen (30 Tage)
    'PERMANENT': None   # Zeitlose Fakten
}
```

**LLM bestimmt Volatility:**
- Response enthält `<volatility>DAILY</volatility>` Tag
- Wird beim Caching extrahiert und als Metadatum gespeichert
- Automatische Cleanup-Jobs löschen expired Entries

### Distance Thresholds

```python
CACHE_DISTANCE_HIGH = 0.5       # < 0.5 = HIGH confidence Cache-Hit
CACHE_DISTANCE_MEDIUM = 0.5     # >= 0.5 = Trigger RAG check
CACHE_DISTANCE_DUPLICATE = 0.3  # < 0.3 = Semantisches Duplikat (merge)
CACHE_DISTANCE_RAG = 1.2        # < 1.2 = Ähnlich genug für RAG-Context
```

---

## State Management

### Global State Architecture

**Datei:** [`aifred/state.py`](../aifred/state.py)

**Problem:** Reflex ist session-based, aber Backend-Ressourcen (vLLM Server) müssen **global** persistieren.

**Lösung:** 2-Level State

```python
# Module-Level (Global across all sessions)
_global_backend_initialized = False
_global_backend_state = {
    "backend_type": None,
    "vllm_manager": None,     # vLLM Process Manager
    "available_models": [],
    "gpu_info": None
}

# Session-Level (Per User/Tab)
class AIState(rx.State):
    chat_history: List[Tuple[str, str]] = []
    backend_type: str = "ollama"
    selected_model: str = ""
    # ... session-specific state
```

### Backend Initialization Flow

```python
async def on_load(self):
    """Called when page loads"""

    # GLOBAL INIT (once per server start)
    if not _global_backend_initialized:
        initialize_debug_log()
        initialize_vector_cache()
        detect_gpu()
        _global_backend_initialized = True

    # SESSION INIT (per user/tab/reload)
    if not self._backend_initialized:
        load_settings()
        await self.initialize_backend()
        self._backend_initialized = True
```

### vLLM Manager Integration

**Start vLLM:**
```python
async def _start_vllm_server(self):
    vllm_manager = vLLMProcessManager(port=8001)

    success, context_info = await vllm_manager.start_with_auto_detection(
        model=self.selected_model,
        timeout=120
    )

    if success:
        # Cache startup context in vLLM backend
        vllm_backend = BackendFactory.create("vllm", base_url=self.backend_url)
        vllm_backend.set_startup_context(
            context=context_info["hardware_limit"],
            debug_messages=[...]
        )

        # Store in global state
        _global_backend_state["vllm_manager"] = vllm_manager
```

---

## Datenfluss

### Beispiel: User stellt Frage mit Automatik-Mode

```
1. USER INPUT
   └─> state.py: send_message()
       └─> conversation_handler.py: chat_interactive_mode()
           │
           ├─> Vector Cache: Semantic Search
           │   └─> HIT? → Return Cached Response
           │   └─> MISS? → Continue
           │
           ├─> PHASE 1: Decision (Automatik-LLM)
           │   └─> Backend.chat(automatik_model, decision_prompt)
           │   └─> Decision: "JA" (Recherche nötig)
           │
           ├─> PHASE 2: Query Optimization (Automatik-LLM)
           │   └─> Backend.chat(automatik_model, optimize_prompt)
           │   └─> Optimized Query: "Qwen3-30B vLLM context window"
           │
           ├─> PHASE 3: Web Scraping
           │   └─> agent_tools.search_web(optimized_query)
           │   └─> scraper_tool.scrape_urls(urls, parallel=True)
           │   └─> Scraped: 3 sources, 4500 words
           │
           ├─> PHASE 4: Context Building
           │   └─> context_builder.py: Build RAG Context
           │   └─> Chunking: 2000 words/source → 20k tokens total
           │   └─> System Prompt: prompts/de/system_rag.txt
           │
           ├─> PHASE 5: LLM Response (Haupt-LLM)
           │   └─> context_manager.calculate_dynamic_num_ctx()
           │       └─> Backend.calculate_practical_context(model)
           │           ├─> Ollama: Query current VRAM → 21,500 tokens
           │           └─> vLLM: Return cached → 21,101 tokens
           │   └─> Backend.chat_stream(selected_model, messages)
           │   └─> Streaming → UI (via yield)
           │   └─> Extract <volatility>WEEKLY</volatility>
           │
           └─> PHASE 6: Vector Cache Storage
               └─> vector_cache.store_research_result(
                   query, response, sources, volatility="WEEKLY"
                   )
               └─> TTL: 168 hours (7 days)
```

---

## Wichtige Design-Entscheidungen

### 1. **Backend Abstraction via ABC (Abstract Base Class)**

**Warum?**
- Eliminiert `if backend_type ==` spaghetti code
- Jedes Backend deklariert seine Capabilities selbst
- Einfaches Hinzufügen neuer Backends (z.B. llama.cpp)

**Vorher:**
```python
if backend_type == "vllm":
    # vLLM-spezifische Logik
elif backend_type == "ollama":
    # Ollama-spezifische Logik
```

**Nachher:**
```python
backend = BackendFactory.create(backend_type)
num_ctx, debug = await backend.calculate_practical_context(model)
```

### 2. **Class Variables für vLLM Context Caching**

**Problem:** Backend-Instanzen werden oft temporär erstellt und garbage collected.

**Lösung:** Class-level statt instance-level storage
```python
class vLLMBackend(LLMBackend):
    _global_startup_context: Optional[int] = None  # Shared across ALL instances
```

**Vorteil:**
- Einmal gesetzt (bei vLLM Start) → bleibt für alle Instanzen verfügbar
- Selbst wenn `state.py` temporäre Backend-Instanzen erstellt

### 3. **Two-Level State (Global + Session)**

**Problem:** Reflex ist session-based, aber vLLM Server ist global.

**Lösung:**
- **Global State** (`_global_backend_state`): vLLM Manager, GPU Info
- **Session State** (`AIState`): Chat History, User Settings

**Vorteil:**
- Page Reload → Session wird neu initialisiert
- vLLM Server → läuft weiter, muss nicht neu gestartet werden

### 4. **TTL-based Vector Cache statt Time-based Invalidation**

**Warum TTL?**
- Verschiedene Daten haben verschiedene Lebenszyklen
- News: 24h, Politik: 7 Tage, Wissenschaft: permanent
- LLM entscheidet Volatility basierend auf Content

**Vorteil:**
- Automatische Cleanup-Jobs
- Keine manuellen Cache-Invalidation nötig
- Optimale Balance: Freshness vs. Performance

### 5. **Pre-Calculation für vLLM Context**

**Problem:** vLLM crashed bei zu großem `--max-model-len` → musste neu starten → 120s!

**Lösung:** Context VOR dem Start berechnen basierend auf:
- Free VRAM
- Model Size
- Empirisch gemessene Overheads (CUDA Graphs, torch.compile)

**Ergebnis:**
- ✅ Nur 1x Start (~60s)
- ✅ Kein Crash
- ✅ Optimales Context-Limit

### 6. **Streaming-First Architecture**

**Warum Streaming?**
- User sieht Antwort sofort (TTFT: Time To First Token)
- Bessere UX für lange Antworten
- Progress Indication (Scraping, LLM Generation)

**Implementation:**
```python
async for chunk in backend.chat_stream(model, messages):
    if chunk["type"] == "content":
        self.current_ai_response += chunk["text"]
        yield  # Update UI in real-time
```

---

## Performance-Optimierungen

### 1. **Parallel Scraping**

```python
# Scrape multiple URLs concurrently
async def scrape_urls_parallel(urls: List[str], max_workers: int = 3):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(scraper.scrape, url) for url in urls]
        results = [f.result() for f in as_completed(futures)]
```

**Speedup:** 3-5x schneller als sequential

### 2. **Semantic Cache Hit Rate**

- **Ohne Cache:** Jede Query → Web-Suche → Scraping → LLM (5-15s)
- **Mit Cache:** Semantic Match → Instant Response (< 1s)
- **Typical Hit Rate:** ~30-40% (bei regelmäßiger Nutzung)

### 3. **VRAM-optimierte Context Windows**

**Vorher:** Fixed 32k context → CPU-Offload → langsam
**Nachher:** Dynamisch berechnet → nur GPU → schnell

**Beispiel (RTX 3090 Ti, 24 GB):**
- Qwen3-30B AWQ: **21,101 tokens** (statt 32k)
- Vermeidet CPU-Offload
- ~2-3x schnellere Inferenz

### 4. **Model Preloading**

```python
# Ollama: Preload Automatik-LLM beim Start
if self.backend_type == "ollama":
    subprocess.Popen(f'curl -s {url}/api/chat -d ...')  # Background preload
```

**Vorteil:** Erste Automatik-Decision ist sofort schnell (~2s statt ~10s)

---

## Fehlerbehandlung

### Backend Errors

```python
class BackendError(Exception):
    """Base exception for backend errors"""

class BackendConnectionError(BackendError):
    """Backend not reachable"""

class BackendModelNotFoundError(BackendError):
    """Requested model not available"""

class BackendInferenceError(BackendError):
    """Error during inference"""
```

### Graceful Degradation

1. **Vector Cache Offline**
   - System funktioniert weiter (ohne Caching)
   - Log Warning: "Vector Cache connection failed"

2. **Web-Scraping fehlgeschlagen (0 sources)**
   - **Fallback:** Retry mit neuem Web-Search Query
   - **Fallback 2:** LLM antwortet mit eigenem Wissen

3. **vLLM Server Down**
   - State meldet: "vLLM server not running"
   - User kann Backend wechseln (zu Ollama/TabbyAPI)

---

## Sicherheit & Best Practices

### 1. **No Hardcoded API Keys**

```python
# ✅ Good: API Keys in .env
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ❌ Bad: Hardcoded
OPENAI_API_KEY = "sk-proj-..."
```

### 2. **Input Validation**

```python
# Validate num_ctx before passing to LLM
if num_value < 2048:
    num_value = 2048
if num_value > 1048576:  # 1M tokens max
    num_value = 1048576
```

### 3. **SQL Injection Prevention**

Vector Cache verwendet **ChromaDB** (NoSQL) → keine SQL Injection möglich.

### 4. **XSS Prevention**

Reflex escaped automatisch alle User-Inputs in React Components.

---

## Testing Strategy

### Unit Tests

```bash
pytest aifred/backends/test_backends.py
pytest aifred/lib/test_context_manager.py
```

### Integration Tests

```bash
pytest tests/integration/test_research_pipeline.py
```

### Manual Testing Checklist

- [ ] Backend Switch (Ollama → vLLM → TabbyAPI)
- [ ] vLLM Context Calculation (sollte ~21k tokens sein, nicht 2048)
- [ ] Vector Cache Hit/Miss
- [ ] Web Research Automatik
- [ ] Scraping Fallback bei 0 sources
- [ ] Model Preloading (Ollama)

---

## Deployment

### Systemd Services

```bash
# AIfred Main Service
sudo systemctl start aifred-intelligence

# ChromaDB (Vector Cache)
docker-compose up -d chromadb

# Optional: vLLM (wenn Backend=vLLM)
# Started automatisch von aifred/lib/vllm_manager.py
```

### Resource Requirements

**Minimum (Ollama):**
- GPU: RTX 3060 (12 GB VRAM)
- RAM: 16 GB
- Disk: 50 GB (für Models)

**Recommended (vLLM):**
- GPU: RTX 3090 Ti / 4090 (24 GB VRAM)
- RAM: 32 GB
- Disk: 100 GB

---

## Changelog

### v2.0 (Januar 2025) - Backend Refactoring

**Breaking Changes:**
- Backend Abstraction Layer (neue `aifred/backends/` Struktur)
- `calculate_practical_context()` ersetzt alte VRAM-Logik

**Fixes:**
- ✅ vLLM Context Bug: 21k tokens statt 2048 Fallback
- ✅ Class Variables für vLLM Context Caching
- ✅ Eliminiert `if backend_type ==` spaghetti code

**Improvements:**
- Capabilities System für Backend-Verhalten
- Bessere Code-Organisation
- Einfacheres Hinzufügen neuer Backends

---

## Weiterführende Dokumentation

- **Configuration:** [`docs/CONFIGURATION_TEMPLATE.md`](./CONFIGURATION_TEMPLATE.md)
- **Installation:** [`docs/INSTALLATION.md`](./INSTALLATION.md)
- **API Docs:** [`docs/API.md`](./API.md)
- **vLLM Commits:** [`docs/vllm/COMMIT_HISTORY_VLLM.md`](./vllm/COMMIT_HISTORY_VLLM.md)

---

**Autoren:** AIfred Intelligence Team
**Lizenz:** MIT
**Support:** GitHub Issues
