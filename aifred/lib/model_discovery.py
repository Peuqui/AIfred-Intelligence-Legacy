"""
Model Discovery - Backend-agnostic model discovery for AIfred

Provides functions to discover available models from different backends:
- vLLM/TabbyAPI: Scan HuggingFace cache
- KoboldCPP: Scan filesystem for GGUF files
- Ollama: Query server API

Returns Dict[model_id, display_label] for UI dropdown population.
"""

from pathlib import Path
from typing import Dict, Optional
import httpx

from .logging_utils import log_message


def discover_huggingface_models(
    backend_type: str,
    is_compatible_fn: callable
) -> Dict[str, str]:
    """
    Discover models from HuggingFace cache for vLLM/TabbyAPI backends.

    Args:
        backend_type: "vllm" or "tabbyapi"
        is_compatible_fn: Function(model_dir, backend_type) -> bool

    Returns:
        Dict mapping model_id to display label with size
    """
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"

    if not hf_cache.exists():
        log_message("⚠️ HuggingFace cache not found")
        return {}

    # Find all model directories (format: models--Org--ModelName)
    model_dirs = [
        d for d in hf_cache.iterdir()
        if d.is_dir() and d.name.startswith("models--")
    ]

    result = {}
    for model_dir in model_dirs:
        if is_compatible_fn(model_dir, backend_type):
            model_id = model_dir.name.replace("models--", "").replace("--", "/", 1)

            # Calculate size using blob-based calculation
            try:
                from .vllm_manager import get_model_size_bytes
                total_size = get_model_size_bytes(model_id)
                size_gb = total_size / (1024**3)
                result[model_id] = f"{model_id} ({size_gb:.1f} GB)"
            except Exception:
                # Fallback: show without size if calculation fails
                result[model_id] = model_id

    log_message(f"📂 Found {len(result)} {backend_type}-compatible models ({len(model_dirs)} total in cache)")
    return result


def discover_gguf_models() -> Dict[str, str]:
    """
    Discover GGUF models from filesystem for KoboldCPP backend.

    Returns:
        Dict mapping model_name to display label with size
    """
    from .gguf_utils import find_all_gguf_models

    try:
        gguf_models = find_all_gguf_models()

        if not gguf_models:
            log_message("⚠️ No GGUF models found")
            return {}

        result = {
            m.name: f"{m.name} ({m.size_gb:.1f} GB)"
            for m in gguf_models
        }

        log_message(f"📂 Found {len(result)} GGUF models")
        return result

    except Exception as e:
        log_message(f"❌ GGUF discovery failed: {e}")
        return {}


def discover_ollama_models(backend_url: str, timeout: float = 5.0) -> Dict[str, str]:
    """
    Discover models from Ollama server API.

    Args:
        backend_url: Ollama server URL (e.g., "http://localhost:11434")
        timeout: Request timeout in seconds

    Returns:
        Dict mapping model_name to display label with size
    """
    endpoint = f'{backend_url}/api/tags'

    try:
        response = httpx.get(endpoint, timeout=timeout)
        if response.status_code == 200:
            data = response.json()
            result = {
                m['name']: f"{m['name']} ({m['size'] / (1024**3):.1f} GB)"
                for m in data.get("models", [])
            }
            log_message(f"📂 Found {len(result)} Ollama models")
            return result
        else:
            log_message(f"⚠️ Ollama API returned {response.status_code}")
            return {}
    except httpx.RequestError as e:
        log_message(f"⚠️ Ollama API not reachable: {e}")
        return {}


def discover_models(
    backend_type: str,
    backend_url: Optional[str] = None,
    is_compatible_fn: Optional[callable] = None
) -> Dict[str, str]:
    """
    Unified model discovery for any backend type.

    Args:
        backend_type: "ollama", "vllm", "tabbyapi", or "koboldcpp"
        backend_url: Required for Ollama backend
        is_compatible_fn: Required for vLLM/TabbyAPI backends

    Returns:
        Dict mapping model_id to display label
    """
    if backend_type in ["vllm", "tabbyapi"]:
        if not is_compatible_fn:
            raise ValueError("is_compatible_fn required for vLLM/TabbyAPI")
        return discover_huggingface_models(backend_type, is_compatible_fn)

    elif backend_type == "koboldcpp":
        return discover_gguf_models()

    elif backend_type == "ollama":
        if not backend_url:
            raise ValueError("backend_url required for Ollama")
        return discover_ollama_models(backend_url)

    else:
        log_message(f"⚠️ Unknown backend type: {backend_type}")
        return {}
