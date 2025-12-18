"""
llama.cpp Backend Adapter (Router Mode)

Wraps llama.cpp Server API into unified LLMBackend interface.
Uses the new Router Mode (Dec 2025) for dynamic model loading like Ollama.

API Reference: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
Router Mode: https://huggingface.co/blog/ggml-org/model-management-in-llamacpp

Key Features:
- OpenAI-compatible API (/v1/chat/completions)
- Dynamic model loading/unloading (/models/load, /models/unload)
- Multi-model support (--models-max N)
- MoE Expert Offloading (--n-cpu-moe) for large models
"""

import httpx
import time
import logging
import json
from typing import List, Optional, AsyncIterator, Dict
from openai import AsyncOpenAI
from .base import (
    LLMBackend,
    LLMMessage,
    LLMOptions,
    LLMResponse,
    BackendConnectionError,
    BackendModelNotFoundError,
    BackendInferenceError
)
from ..lib.logging_utils import log_message

logger = logging.getLogger(__name__)


class LlamaCppBackend(LLMBackend):
    """
    llama.cpp Server Backend (Router Mode)

    Uses OpenAI-compatible API for inference and native llama.cpp
    endpoints for model management.

    Router Mode Features:
    - GET /models - List available GGUF models
    - POST /models/load - Load model into VRAM
    - POST /models/unload - Unload model from VRAM
    - POST /v1/chat/completions - OpenAI-compatible chat

    Unlike Ollama:
    - Explicit load/unload (no keep_alive hack needed)
    - OpenAI-compatible API natively
    - MoE Expert Offloading (--n-cpu-moe)
    """

    def __init__(self, base_url: str = "http://localhost:8080", api_key: Optional[str] = None):
        """
        Initialize llama.cpp backend.

        Args:
            base_url: llama.cpp server URL (default: http://localhost:8080)
            api_key: Optional API key (usually not needed for local server)
        """
        super().__init__(base_url=base_url, api_key=api_key)

        # AsyncOpenAI client for chat completions
        # llama.cpp uses /v1 prefix for OpenAI-compatible endpoints
        self.openai_client = AsyncOpenAI(
            base_url=f"{base_url}/v1",
            api_key=api_key or "dummy",  # llama.cpp doesn't require API key
            timeout=None  # Let Reflex handle timeouts
        )

        # httpx client for native llama.cpp endpoints (/models, /health, etc.)
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=300.0)
        timeout = httpx.Timeout(None)  # Unlimited - let Reflex handle
        self.http_client = httpx.AsyncClient(timeout=timeout, limits=limits)

    async def list_models(self) -> List[str]:
        """
        Get list of available GGUF models from llama.cpp server.

        In Router Mode, the server discovers models from --models-dir.
        Each model entry has: id, object, owned_by, meta (loaded status).

        Returns:
            List of model IDs (GGUF filenames without path)
        """
        try:
            response = await self.http_client.get(f"{self.base_url}/models")
            response.raise_for_status()
            data = response.json()

            # Router Mode response format:
            # {"object": "list", "data": [{"id": "model.gguf", "object": "model", ...}]}
            models_data = data.get("data", [])
            self._available_models = [m.get("id", "") for m in models_data if m.get("id")]

            return self._available_models

        except httpx.HTTPStatusError as e:
            raise BackendConnectionError(f"Failed to list llama.cpp models: HTTP {e.response.status_code}")
        except Exception as e:
            raise BackendConnectionError(f"Failed to list llama.cpp models: {e}")

    async def chat(
        self,
        model: str,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None,
        stream: bool = False
    ) -> LLMResponse:
        """
        Non-streaming chat with llama.cpp (OpenAI-compatible API).

        Args:
            model: Model ID (GGUF filename)
            messages: List of LLMMessage
            options: Generation options
            stream: Ignored (use chat_stream for streaming)

        Returns:
            LLMResponse with full text
        """
        if options is None:
            options = LLMOptions()

        # Convert LLMMessage to OpenAI format
        openai_messages = self._convert_messages(messages)

        try:
            start_time = time.time()

            # Build request parameters
            params = {
                "model": model,
                "messages": openai_messages,
                "temperature": options.temperature,
                "top_p": options.top_p,
                "stream": False
            }

            # Add optional parameters
            if options.num_predict:
                params["max_tokens"] = options.num_predict
            if options.seed:
                params["seed"] = options.seed
            # Note: repeat_penalty and top_k are llama.cpp specific
            # They can be passed via extra_body if needed

            response = await self.openai_client.chat.completions.create(**params)
            inference_time = time.time() - start_time

            # Extract response
            choice = response.choices[0] if response.choices else None
            text = choice.message.content if choice and choice.message else ""

            # Extract token counts
            usage = response.usage
            tokens_prompt = usage.prompt_tokens if usage else 0
            tokens_generated = usage.completion_tokens if usage else 0

            # Calculate tokens/second
            tokens_per_second = tokens_generated / inference_time if inference_time > 0 else 0

            return LLMResponse(
                text=text or "",
                tokens_prompt=tokens_prompt,
                tokens_generated=tokens_generated,
                tokens_per_second=tokens_per_second,
                inference_time=inference_time,
                model=model
            )

        except Exception as e:
            error_msg = str(e)
            if "404" in error_msg or "not found" in error_msg.lower():
                raise BackendModelNotFoundError(f"Model '{model}' not found in llama.cpp")
            raise BackendInferenceError(f"llama.cpp chat failed: {e}")

    async def chat_stream(
        self,
        model: str,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None
    ) -> AsyncIterator[Dict]:
        """
        Streaming chat with llama.cpp (OpenAI-compatible API).

        Args:
            model: Model ID (GGUF filename)
            messages: List of LLMMessage
            options: Generation options

        Yields:
            Dict with either:
            - {"type": "content", "text": str} for content chunks
            - {"type": "done", "metrics": {...}} for final metrics
        """
        if options is None:
            options = LLMOptions()

        # Convert LLMMessage to OpenAI format
        openai_messages = self._convert_messages(messages)

        try:
            start_time = time.time()
            tokens_generated = 0

            # Build request parameters
            params = {
                "model": model,
                "messages": openai_messages,
                "temperature": options.temperature,
                "top_p": options.top_p,
                "stream": True,
                "stream_options": {"include_usage": True}  # Get token counts at end
            }

            # Add optional parameters
            if options.num_predict:
                params["max_tokens"] = options.num_predict
            if options.seed:
                params["seed"] = options.seed

            # Note: Thinking mode not supported by llama.cpp server yet
            # (Ollama has custom "think" parameter, llama.cpp doesn't)

            async with await self.openai_client.chat.completions.create(**params) as stream:
                tokens_prompt = 0

                async for chunk in stream:
                    # Handle content chunks
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        tokens_generated += 1  # Approximate - 1 chunk ≈ 1 token
                        yield {"type": "content", "text": content}

                    # Handle usage info (final chunk)
                    if hasattr(chunk, 'usage') and chunk.usage:
                        tokens_prompt = chunk.usage.prompt_tokens or 0
                        tokens_generated = chunk.usage.completion_tokens or tokens_generated

            # Calculate final metrics
            inference_time = time.time() - start_time
            tokens_per_second = tokens_generated / inference_time if inference_time > 0 else 0

            yield {
                "type": "done",
                "metrics": {
                    "tokens_prompt": tokens_prompt,
                    "tokens_generated": tokens_generated,
                    "tokens_per_second": tokens_per_second,
                    "inference_time": inference_time,
                    "model": model
                }
            }

        except Exception as e:
            error_msg = str(e)
            if "404" in error_msg or "not found" in error_msg.lower():
                raise BackendModelNotFoundError(f"Model '{model}' not found")
            raise BackendInferenceError(f"llama.cpp streaming error: {e}")

    async def unload_all_models(self) -> tuple[bool, list[str]]:
        """
        Unload ALL currently loaded models from VRAM.

        Uses /models endpoint to get loaded models, then /models/unload to unload each.

        Returns:
            tuple[bool, list[str]]: (success, list of unloaded model names)
        """
        try:
            # Get list of models and their status
            response = await self.http_client.get(f"{self.base_url}/models")
            if response.status_code != 200:
                logger.warning("Failed to get models list from llama.cpp")
                return (False, [])

            data = response.json()
            models_data = data.get("data", [])

            unloaded_models = []

            for model_info in models_data:
                model_id = model_info.get("id", "")
                meta = model_info.get("meta", {})

                # Check if model is loaded (Router Mode: meta.loaded = true)
                if meta.get("loaded", False):
                    logger.info(f"Unloading model: {model_id}")

                    unload_response = await self.http_client.post(
                        f"{self.base_url}/models/unload",
                        json={"model": model_id}
                    )

                    if unload_response.status_code == 200:
                        unloaded_models.append(model_id)
                    else:
                        logger.warning(f"Failed to unload {model_id}: HTTP {unload_response.status_code}")
                        return (False, unloaded_models)

            if unloaded_models:
                logger.info(f"Successfully unloaded {len(unloaded_models)} model(s)")
            else:
                logger.info("No models were loaded")

            return (True, unloaded_models)

        except Exception as e:
            logger.warning(f"Failed to unload llama.cpp models: {e}")
            return (False, [])

    async def preload_model(self, model: str, num_ctx: Optional[int] = None) -> tuple[bool, float]:
        """
        Preload a model into VRAM using /models/load endpoint.

        Args:
            model: Model ID (GGUF filename)
            num_ctx: Context window size (llama.cpp uses n_ctx parameter)

        Returns:
            Tuple of (success: bool, load_time: float in seconds)
        """
        try:
            start_time = time.time()

            # Build load request
            payload = {"model": model}

            # Note: llama.cpp Router Mode may support n_ctx in load request
            # Check server documentation for exact parameter name
            if num_ctx is not None:
                payload["n_ctx"] = num_ctx
                logger.info(f"Preload {model} with n_ctx={num_ctx:,}")

            response = await self.http_client.post(
                f"{self.base_url}/models/load",
                json=payload
            )

            load_time = time.time() - start_time

            if response.status_code == 200:
                logger.info(f"Model {model} loaded in {load_time:.1f}s")
                return (True, load_time)
            else:
                error_text = response.text
                logger.warning(f"Failed to preload {model}: HTTP {response.status_code} - {error_text}")
                return (False, load_time)

        except Exception as e:
            load_time = time.time() - start_time
            logger.warning(f"Preload failed for {model}: {e}")
            return (False, load_time)

    async def health_check(self) -> bool:
        """Check if llama.cpp server is reachable."""
        try:
            # llama.cpp has /health endpoint
            response = await self.http_client.get(f"{self.base_url}/health")
            if response.status_code == 200:
                return True

            # Fallback to /models (always works in Router Mode)
            response = await self.http_client.get(f"{self.base_url}/models")
            return response.status_code == 200

        except Exception:
            return False

    def get_backend_name(self) -> str:
        return "llama.cpp"

    async def get_backend_info(self) -> Dict:
        """Get llama.cpp server information."""
        try:
            # Try /health for version info
            version = "unknown"
            try:
                health_response = await self.http_client.get(f"{self.base_url}/health")
                if health_response.status_code == 200:
                    health_data = health_response.json()
                    # llama.cpp /health may contain build info
                    version = health_data.get("version", health_data.get("build", "unknown"))
            except Exception:
                pass

            # Get models
            models = await self.list_models()

            # Get loaded model count
            loaded_count = 0
            try:
                models_response = await self.http_client.get(f"{self.base_url}/models")
                if models_response.status_code == 200:
                    models_data = models_response.json().get("data", [])
                    loaded_count = sum(1 for m in models_data if m.get("meta", {}).get("loaded", False))
            except Exception:
                pass

            return {
                "backend": "llama.cpp",
                "version": version,
                "base_url": self.base_url,
                "available_models": len(models),
                "loaded_models": loaded_count,
                "models": models,
                "healthy": True
            }

        except Exception as e:
            return {
                "backend": "llama.cpp",
                "version": "unknown",
                "base_url": self.base_url,
                "available_models": 0,
                "loaded_models": 0,
                "models": [],
                "healthy": False,
                "error": str(e)
            }

    async def get_model_context_limit(self, model: str) -> tuple[int, int]:
        """
        Get context limit and model size for a llama.cpp model.

        llama.cpp Router Mode: /models endpoint includes model metadata.
        Falls back to props endpoint if available.

        Args:
            model: Model ID (GGUF filename)

        Returns:
            tuple[int, int]: (context_limit, model_size_bytes)
        """
        try:
            # Try /models endpoint first (Router Mode)
            response = await self.http_client.get(f"{self.base_url}/models")
            response.raise_for_status()
            data = response.json()

            models_data = data.get("data", [])
            for model_info in models_data:
                if model_info.get("id") == model:
                    meta = model_info.get("meta", {})

                    # llama.cpp reports n_ctx_train (training context) and n_ctx (current)
                    context_limit = meta.get("n_ctx_train") or meta.get("n_ctx", 4096)

                    # Model size (if available)
                    model_size = meta.get("n_params", 0)  # Parameters, not bytes
                    # Estimate bytes: 4 bytes per param for FP32, adjust for quantization
                    # For GGUF Q4, roughly 0.5 bytes per param
                    model_size_bytes = model_size // 2 if model_size else 0

                    return (context_limit, model_size_bytes)

            # Model not found in list
            raise RuntimeError(f"Model '{model}' not found in llama.cpp server")

        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to query llama.cpp for model '{model}': {e}") from e

    async def is_model_loaded(self, model: str) -> bool:
        """
        Check if model is currently loaded in llama.cpp's VRAM.

        In Router Mode, /models endpoint includes loaded status in meta.

        Args:
            model: Model ID (GGUF filename)

        Returns:
            bool: True if model is loaded, False otherwise
        """
        try:
            response = await self.http_client.get(f"{self.base_url}/models")
            response.raise_for_status()
            data = response.json()

            models_data = data.get("data", [])
            for model_info in models_data:
                if model_info.get("id") == model:
                    meta = model_info.get("meta", {})
                    return meta.get("loaded", False)

            return False

        except Exception as e:
            logger.warning(f"Failed to check model status: {e}")
            return False

    def get_capabilities(self) -> Dict[str, bool]:
        """
        Return llama.cpp backend capabilities.

        llama.cpp Router Mode supports:
        - Dynamic model loading/unloading (via /models/load, /models/unload)
        - Dynamic context calculation (can vary based on server config)
        - Streaming responses
        - Optional preloading
        """
        return {
            "dynamic_models": True,      # Router Mode: load/unload at runtime
            "dynamic_context": True,     # Context can be set at load time
            "supports_streaming": True,  # OpenAI-compatible streaming
            "requires_preload": False    # Models auto-load on first request
        }

    async def calculate_practical_context(self, model: str) -> tuple[int, list[str]]:
        """
        Calculate practical context for llama.cpp (dynamic VRAM-based calculation).

        Similar to Ollama, but uses llama.cpp's /models endpoint for model info.

        Args:
            model: Model ID

        Returns:
            tuple[int, list[str]]: (context_limit, debug_messages)
        """
        import asyncio
        from ..lib.gpu_utils import calculate_vram_based_context, get_model_size_from_cache

        debug_msgs = []

        # Get model metadata
        model_limit, model_size_bytes = await self.get_model_context_limit(model)

        # If model size not available, try cache
        if model_size_bytes == 0:
            model_size_bytes = get_model_size_from_cache(model)

        # Unload all models for accurate VRAM measurement
        success, unloaded = await self.unload_all_models()
        if success and unloaded:
            debug_msgs.append(f"Modelle entladen: {', '.join(unloaded)}")
            await asyncio.sleep(2.0)  # Wait for VRAM release
            debug_msgs.append("VRAM freigegeben")

        # Model is definitely not loaded after unload
        model_is_loaded = False

        # Calculate context based on VRAM
        num_ctx, vram_debug_msgs = await calculate_vram_based_context(
            model_name=model,
            model_size_bytes=model_size_bytes,
            model_context_limit=model_limit,
            model_is_loaded=model_is_loaded,
            backend_type="llamacpp",
            backend=self
        )

        debug_msgs.extend(vram_debug_msgs)
        return num_ctx, debug_msgs

    async def close(self):
        """Close HTTP clients."""
        await self.http_client.aclose()
        await self.openai_client.close()

    def _convert_messages(self, messages: List[LLMMessage]) -> List[Dict]:
        """
        Convert LLMMessage list to OpenAI format.

        Handles both text-only and multimodal (text + images) content.
        """
        openai_messages = []

        for msg in messages:
            if isinstance(msg.content, list):
                # Multimodal content - keep as-is (OpenAI format)
                openai_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
            else:
                # Text-only content
                openai_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })

        return openai_messages
