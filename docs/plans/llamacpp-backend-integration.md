# Plan: llama.cpp Backend Integration

**Erstellt:** 2025-12-15
**Status:** Geplant (Hohe Priorität)
**Referenz:** `docs/research/llama-cpp-vs-ollama.md`

## Kontext & Recherche-Ergebnis

Basierend auf:
- `docs/research/llama-cpp-vs-ollama.md`
- [llama.cpp Router Mode Dokumentation](https://huggingface.co/blog/ggml-org/model-management-in-llamacpp)

### Wichtige Entdeckung: Router Mode

llama.cpp hat jetzt einen **Router Mode** mit dynamischem Model-Loading wie Ollama!

| Feature | Ollama | llama.cpp Router |
|---------|--------|-----------------|
| Models per API laden | ✅ | ✅ `/models/load` |
| Models per API entladen | ✅ | ✅ `/models/unload` |
| Modell-Liste | ✅ `/api/tags` | ✅ `/models` |
| Auto-Discovery | ✅ | ✅ `--models-dir` |
| Multi-Model | ✅ | ✅ `--models-max N` |
| MoE-Offload | ❌ | ✅ `--n-cpu-moe` |

### Killer-Feature: MoE Expert Offloading

```bash
llama-server --models-dir /pfad/gguf --n-cpu-moe 12 -ngl 99
```
- Experten-Weights im CPU-RAM statt VRAM
- Ermöglicht größere Modelle oder mehr Context
- Nur sinnvoll bei 64GB+ RAM (aktuell 32GB)

---

## Entscheidungen

| Frage | Entscheidung |
|-------|-------------|
| Server-Management | **Wie Ollama** - systemd Service, AIfred verbindet per API |
| GGUF-Verzeichnis | **Shared mit KoboldCPP** - `GGUF_MODELS_DIR` aus config.py |
| Backend-Typ | **Dynamisch** (wie Ollama, nicht wie vLLM/KoboldCPP) |
| MoE-Offload | **Später** - erst bei RAM-Upgrade auf 64GB+ |

---

## Architektur-Vergleich

```
OLLAMA (dynamisch)          LLAMA.CPP ROUTER (dynamisch)
├─ /api/tags               ├─ /models
├─ /api/chat               ├─ /v1/chat/completions
├─ /api/show               ├─ (N/A - aber /models hat Status)
├─ /api/generate           ├─ /models/load
└─ keep_alive: 0           └─ /models/unload
```

**llama.cpp ist näher an OpenAI-API** → einfacher zu implementieren!

---

## Implementierungsplan

### Phase 1: Backend-Grundgerüst

**Neue Datei: `aifred/backends/llamacpp.py`**

```python
class LlamaCppBackend(LLMBackend):
    """llama.cpp Router Mode Backend - Dynamic model loading like Ollama"""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.client = AsyncOpenAI(base_url=f"{base_url}/v1", api_key="dummy")

    async def list_models(self) -> List[str]:
        # GET /models → Liste der GGUF-Dateien

    async def chat(self, model, messages, options) -> LLMResponse:
        # POST /v1/chat/completions (OpenAI-kompatibel)

    async def chat_stream(self, model, messages, options):
        # POST /v1/chat/completions mit stream=True

    async def health_check(self) -> bool:
        # GET /models

    async def is_model_loaded(self, model) -> bool:
        # GET /models → check status == "loaded"

    async def preload_model(self, model) -> tuple[bool, float]:
        # POST /models/load

    async def unload_model(self, model) -> bool:
        # POST /models/unload

    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "dynamic_models": True,   # Wie Ollama!
            "dynamic_context": True,  # Kann pro Request variieren
            "supports_streaming": True,
            "requires_preload": False,
        }
```

**Geschätzter Aufwand:** ~300-400 Zeilen (ähnlich wie ollama.py)

### Phase 2: Config & Factory

**Datei: `aifred/backends/__init__.py`**
```python
_backends = {
    "ollama": OllamaBackend,
    "vllm": vLLMBackend,
    "tabbyapi": TabbyAPIBackend,
    "koboldcpp": KoboldCPPBackend,
    "llamacpp": LlamaCppBackend,  # NEU
}
```

**Datei: `aifred/lib/config.py`**
```python
BACKEND_URLS = {
    ...
    "llamacpp": "http://localhost:8080",  # llama.cpp Standard-Port
}

BACKEND_LABELS = {
    ...
    "llamacpp": "llama.cpp",
}

BACKEND_DEFAULT_MODELS = {
    ...
    "llamacpp": {
        "selected_model": "Qwen3-30B-A3B-Q8_0.gguf",
        "automatik_model": "Qwen3-4B-Q8_0.gguf",
    },
}
```

### Phase 3: State Integration

**Datei: `aifred/state.py`**

1. Backend in `available_backends` hinzufügen
2. GPU-Kompatibilität: P40 (CUDA) = kompatibel
3. Model-Discovery: Shared `GGUF_MODELS_DIR` nutzen
4. Per-Backend Settings speichern/laden

### Phase 4: Systemd Service (Dokumentation)

**Datei: `docs/infrastructure/llamacpp-setup.md`**

```bash
# /etc/systemd/system/llamacpp.service
[Unit]
Description=llama.cpp Server (Router Mode)
After=network.target

[Service]
Type=simple
User=mp
ExecStart=/pfad/zu/llama-server \
    --models-dir /pfad/zu/gguf/models \
    --host 0.0.0.0 \
    --port 8080 \
    -ngl 99 \
    --models-max 2
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## Kritische Dateien

| Datei | Änderung |
|-------|----------|
| `aifred/backends/llamacpp.py` | **NEU**: Backend-Implementierung (~400 Zeilen) |
| `aifred/backends/__init__.py` | BackendFactory erweitern (+3 Zeilen) |
| `aifred/lib/config.py` | URLs, Labels, Defaults (+15 Zeilen) |
| `aifred/state.py` | available_backends, GPU-Check (+20 Zeilen) |
| `docs/infrastructure/llamacpp-setup.md` | **NEU**: Setup-Anleitung |

---

## API-Mapping: Ollama → llama.cpp

| Operation | Ollama | llama.cpp |
|-----------|--------|-----------|
| List models | `GET /api/tags` | `GET /models` |
| Chat | `POST /api/chat` | `POST /v1/chat/completions` |
| Load model | (implizit bei chat) | `POST /models/load` |
| Unload model | `POST /api/generate` + `keep_alive:0` | `POST /models/unload` |
| Model info | `GET /api/show` | Status in `/models` Response |
| Health | `GET /api/tags` | `GET /models` |

---

## Unterschiede zu Ollama

1. **OpenAI-kompatible API** → Kann `AsyncOpenAI` Client nutzen (wie vLLM)
2. **Explizites Load/Unload** → Sauberer als Ollama's `keep_alive: 0` Hack
3. **MoE-Offload** → Globaler Server-Parameter (nicht per Request)
4. **Kein `/api/show`** → Modell-Info aus `/models` Response extrahieren

---

## Zukunft: MoE-Offload UI (Phase 5)

Wenn 64GB RAM vorhanden:
```python
# In Settings-Panel
rx.text("MoE Expert Offloading"),
rx.slider(
    value=AIState.llamacpp_cpu_moe,
    min=0, max=64, step=4,
    on_change=AIState.set_llamacpp_cpu_moe,
),
rx.text(f"{AIState.llamacpp_cpu_moe} Experten auf CPU")
```

**Nicht Teil dieser Implementierung** - später hinzufügen.

---

## Nächste Schritte

1. ✅ Plan fertig
2. ✅ Plan in `docs/plans/` gespeichert
3. ⏳ Phase 1: `llamacpp.py` implementieren
4. ⏳ Phase 2: Config & Factory erweitern
5. ⏳ Phase 3: State Integration
6. ⏳ Phase 4: Dokumentation & Systemd Service
7. ⏳ Testen mit manuell gestartetem llama-server

---

## Quellen

- [llama.cpp Model Management Blog](https://huggingface.co/blog/ggml-org/model-management-in-llamacpp)
- [llama.cpp Server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- [Feature Request #13027](https://github.com/ggml-org/llama.cpp/issues/13027)
