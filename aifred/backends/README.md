# AIfred LLM Backends

AIfred supports multiple LLM backends for maximum flexibility and performance comparisons.

## Available Backends

### 1. Ollama (Default)
- **URL**: `http://localhost:11434`
- **Installation**: See [ollama.com](https://ollama.com)
- **Advantages**: Easy setup, good model management
- **Disadvantages**: Slightly slower than native inference engines

### 2. vLLM
- **URL**: `http://localhost:8001/v1`
- **Installation**: `pip install vllm`
- **Start**: `vllm serve <model-name> --port 8001`
- **Note**: Port 8001 is used (Port 8000 is reserved for ChromaDB)
- **Advantages**: Very fast, Page Attention, good batching
- **Disadvantages**: Higher RAM consumption

### 3. TabbyAPI (ExLlamaV2/V3)
- **URL**: `http://localhost:5000/v1`
- **Installation**: See [github.com/theroyallab/tabbyAPI](https://github.com/theroyallab/tabbyAPI)
- **Advantages**: Very fast inference with EXL2/EXL3 quantization, low VRAM usage
- **Disadvantages**: More complex setup, requires ExL quantization

### 4. llama.cpp
- **URL**: `http://localhost:8080/v1`
- **Installation**: See [github.com/ggerganov/llama.cpp](https://github.com/ggerganov/llama.cpp)
- **Start**: `./llama-server -m <model.gguf> --port 8080 --host 0.0.0.0`
- **Advantages**: C++ performance, GGUF format, CPU support
- **Disadvantages**: Slower than GPU-based backends

## Switching Backends

### Method 1: Programmatic (LLMClient)

```python
from aifred.lib.llm_client import LLMClient

# Ollama (Default)
client = LLMClient(backend_type="ollama")

# vLLM
client = LLMClient(backend_type="vllm", base_url="http://localhost:8001/v1")

# TabbyAPI (ExLlamaV2/V3)
client = LLMClient(backend_type="tabbyapi", base_url="http://localhost:5000/v1")

# llama.cpp
client = LLMClient(backend_type="llamacpp", base_url="http://localhost:8080/v1")
```

### Method 2: Config File (TODO)

```python
# aifred/lib/config.py
DEFAULT_BACKEND = "ollama"  # or "vllm", "tabbyapi", "llamacpp"
BACKEND_URLS = {
    "ollama": "http://localhost:11434",
    "vllm": "http://localhost:8001/v1",
    "tabbyapi": "http://localhost:5000/v1",
    "llamacpp": "http://localhost:8080/v1",
}
```

## Performance Comparison (Tesla P40, Qwen3:8B)

| Backend | Tokens/s | VRAM | Setup | Compatibility |
|---------|----------|------|-------|---------------|
| Ollama | ~45 t/s | 9GB | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| vLLM | ~80 t/s | 11GB | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| TabbyAPI | ~90 t/s | 7GB (EXL2) | ⭐⭐ | ⭐⭐⭐ |
| llama.cpp | ~35 t/s | 8GB (GGUF) | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

## TabbyAPI Setup (Recommended for Performance)

```bash
# 1. Installation
git clone https://github.com/theroyallab/tabbyAPI
cd tabbyAPI
pip install -r requirements.txt

# 2. Download model in EXL2 format
# Search on HuggingFace for "<model-name>-exl2"
# e.g. Qwen/Qwen2.5-7B-Instruct-EXL2

# 3. Start
python main.py --host 0.0.0.0 --port 5000

# 4. Use in AIfred
# Set backend_type="tabbyapi"
```

## llama.cpp Setup

```bash
# 1. Installation
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
make LLAMA_CUBLAS=1  # With CUDA support

# 2. Download model in GGUF format
# e.g. from HuggingFace: bartowski/<model-name>-GGUF

# 3. Start server
./llama-server -m models/qwen3-8b-q4_k_m.gguf \
    --port 8080 \
    --host 0.0.0.0 \
    --ctx-size 40960 \
    --n-gpu-layers 99

# 4. Use in AIfred
# Set backend_type="llamacpp"
```

## vLLM Setup

```bash
# 1. Installation
pip install vllm

# 2. Start server
vllm serve Qwen/Qwen2.5-7B-Instruct \
    --port 8000 \
    --host 0.0.0.0 \
    --max-model-len 40960 \
    --gpu-memory-utilization 0.9

# 3. Use in AIfred
# Set backend_type="vllm"
```

## Troubleshooting

### Backend not reachable
```python
from aifred.backends import BackendFactory

backend = BackendFactory.create("tabbyapi")
is_healthy = await backend.health_check()
print(f"Backend healthy: {is_healthy}")
```

### Show available models
```python
backend = BackendFactory.create("vllm")
models = await backend.list_models()
print(f"Available models: {models}")
```

### Query context limit
```python
backend = BackendFactory.create("ollama")
limit = await backend.get_model_context_limit("qwen3:8b")
print(f"Context limit: {limit} tokens")
```

## Next Steps (TODO)

- [ ] Backend selection in UI Settings
- [ ] Automatic backend switching on error
- [ ] Performance monitoring dashboard
- [ ] Multi-backend load balancing
