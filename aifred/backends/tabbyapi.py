"""
TabbyAPI Backend Adapter (ExLlamaV2/V3)

TabbyAPI is the official API server for ExLlamaV2/V3 inference.
It provides an OpenAI-compatible API endpoint.
"""

import logging
from typing import List, Optional, AsyncIterator, Dict
from openai import AsyncOpenAI
from ..lib.timer import Timer
from .base import (
    LLMBackend,
    LLMMessage,
    LLMOptions,
    LLMResponse,
    BackendConnectionError,
    BackendModelNotFoundError,
    BackendInferenceError
)

logger = logging.getLogger(__name__)


class TabbyAPIBackend(LLMBackend):
    """TabbyAPI backend implementation (ExLlamaV2/V3 with OpenAI-compatible API)"""

    def __init__(self, base_url: str = "http://localhost:5000/v1", api_key: str = "dummy"):
        super().__init__(base_url=base_url, api_key=api_key)
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,  # TabbyAPI doesn't need real API key by default
            timeout=120.0  # TabbyAPI may need more time for model loading (ExLlama quantization)
        )
        # Cache for startup context (set at server start)
        self._startup_context: Optional[int] = None
        self._startup_context_debug: List[str] = []

    async def list_models(self) -> List[str]:
        """Get list of available models from TabbyAPI"""
        try:
            models_response = await self.client.models.list()
            self._available_models = [model.id for model in models_response.data]
            return self._available_models
        except Exception as e:
            raise BackendConnectionError(f"Failed to list TabbyAPI models: {e}")

    async def chat(
        self,
        model: str,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None,
        stream: bool = False
    ) -> LLMResponse:
        """
        Non-streaming chat with TabbyAPI

        Args:
            model: Model name
            messages: List of LLMMessage
            options: Generation options
            stream: Ignored

        Returns:
            LLMResponse
        """
        if options is None:
            options = LLMOptions()

        # Convert LLMMessage to OpenAI format
        openai_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        # Build kwargs
        kwargs = {
            "model": model,
            "messages": openai_messages,
            "temperature": options.temperature,
            "top_p": options.top_p,
            "stream": False
        }

        # TabbyAPI-specific parameters (via extra_body)
        # ExLlamaV2/V3 supports advanced sampling parameters
        extra_body = {}
        if options.repeat_penalty and options.repeat_penalty != 1.0:
            extra_body["repetition_penalty"] = options.repeat_penalty
        if options.top_k and options.top_k != 40:
            extra_body["top_k"] = options.top_k
        if options.min_p > 0:
            extra_body["min_p"] = options.min_p
        if options.num_predict:
            kwargs["max_tokens"] = options.num_predict

        if extra_body:
            kwargs["extra_body"] = extra_body

        try:
            timer = Timer()
            response = await self.client.chat.completions.create(**kwargs)  # type: ignore[call-overload]
            inference_time = timer.elapsed()

            choice = response.choices[0]
            text = choice.message.content or ""

            # Extract usage info
            usage = response.usage
            tokens_prompt = usage.prompt_tokens if usage else 0
            tokens_generated = usage.completion_tokens if usage else 0

            tokens_per_second = (tokens_generated / inference_time) if inference_time > 0 else 0

            return LLMResponse(
                text=text,
                tokens_prompt=tokens_prompt,
                tokens_generated=tokens_generated,
                tokens_per_second=tokens_per_second,
                inference_time=inference_time,
                model=model
            )

        except Exception as e:
            error_str = str(e)
            if "model" in error_str.lower() and "not found" in error_str.lower():
                raise BackendModelNotFoundError(f"Model '{model}' not found in TabbyAPI")
            else:
                raise BackendInferenceError(f"TabbyAPI inference failed: {e}")

    async def chat_stream(
        self,
        model: str,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None
    ) -> AsyncIterator[Dict]:
        """
        Streaming chat with TabbyAPI

        Args:
            model: Model name
            messages: List of LLMMessage
            options: Generation options

        Yields:
            Dict with either:
            - {"type": "content", "text": str} for content chunks
            - {"type": "done", "metrics": {...}} for final metrics
        """
        if options is None:
            options = LLMOptions()

        # Convert messages
        openai_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        # Build kwargs
        kwargs = {
            "model": model,
            "messages": openai_messages,
            "temperature": options.temperature,
            "top_p": options.top_p,
            "stream": True,
            "stream_options": {"include_usage": True}  # Request usage stats in stream
        }

        # TabbyAPI-specific parameters
        extra_body = {}
        if options.repeat_penalty and options.repeat_penalty != 1.0:
            extra_body["repetition_penalty"] = options.repeat_penalty
        if options.top_k and options.top_k != 40:
            extra_body["top_k"] = options.top_k
        if options.min_p > 0:
            extra_body["min_p"] = options.min_p
        if options.num_predict:
            kwargs["max_tokens"] = options.num_predict

        if extra_body:
            kwargs["extra_body"] = extra_body

        try:
            timer = Timer()
            stream = await self.client.chat.completions.create(**kwargs)  # type: ignore[call-overload]

            total_tokens = 0
            prompt_tokens = 0

            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield {"type": "content", "text": delta.content}
                        total_tokens += 1  # Rough estimate

                # Check for usage info (sent at the end by OpenAI-compatible APIs)
                if hasattr(chunk, 'usage') and chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens
                    total_tokens = completion_tokens

            # Send final metrics
            inference_time = timer.elapsed()
            tokens_per_second = (total_tokens / inference_time) if inference_time > 0 else 0

            yield {
                "type": "done",
                "metrics": {
                    "tokens_prompt": prompt_tokens,
                    "tokens_generated": total_tokens,
                    "tokens_per_second": tokens_per_second,
                    "inference_time": inference_time,
                    "model": model
                }
            }

        except Exception as e:
            error_str = str(e)
            if "model" in error_str.lower() and "not found" in error_str.lower():
                raise BackendModelNotFoundError(f"Model '{model}' not found")
            else:
                raise BackendInferenceError(f"TabbyAPI streaming failed: {e}")

    async def preload_model(self, model: str, num_ctx: Optional[int] = None) -> tuple[bool, float]:
        """
        Preload a model into VRAM by sending a minimal chat request.

        For TabbyAPI: Models are already loaded at startup and kept in VRAM.
        Preloading is unnecessary and wastes time (~3-4s for queued test request).
        We return immediately with success.

        Args:
            model: Model name to preload
            num_ctx: Ignored for TabbyAPI (context is fixed at startup)

        Returns:
            Tuple of (success: bool, load_time: float in seconds)
        """
        # TabbyAPI keeps models loaded in VRAM at all times
        # No preloading needed - return immediately
        logger.debug(f"TabbyAPI: Skipping preload for {model} (already loaded)")
        return (True, 0.0)

    async def health_check(self) -> bool:
        """Check if TabbyAPI is reachable"""
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False

    def get_backend_name(self) -> str:
        return "TabbyAPI (ExLlamaV2/V3)"

    async def get_backend_info(self) -> Dict:
        """Get TabbyAPI backend information"""
        try:
            models = await self.list_models()

            return {
                "backend": "TabbyAPI",
                "exllama_version": "ExLlamaV2/V3",
                "base_url": self.base_url,
                "available_models": len(models),
                "models": models,
                "healthy": True,
                "api_type": "OpenAI-compatible"
            }
        except Exception as e:
            return {
                "backend": "TabbyAPI",
                "base_url": self.base_url,
                "available_models": 0,
                "models": [],
                "healthy": False,
                "error": str(e)
            }

    async def get_model_context_limit(self, model: str) -> tuple[int, int]:
        """
        Get context limit and model size for a TabbyAPI model.

        Queries /v1/models endpoint (OpenAI-compatible) and extracts max_model_len.

        Args:
            model: Model name/ID

        Returns:
            tuple[int, int]: (context_limit, model_size_bytes)
                - context_limit: Maximum context window in tokens
                - model_size_bytes: Model size (0 if unavailable)

        Raises:
            RuntimeError: If model not found or context limit not available

        Note:
            TabbyAPI doesn't expose VRAM usage, returns 0 for model_size.
        """
        try:
            # TabbyAPI follows OpenAI-compatible /v1/models/{model} endpoint
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/models/{model}")
                response.raise_for_status()
                data = response.json()

                context_limit = None

                # Check for max_model_len (common in ExLlama-based APIs)
                if "max_model_len" in data:
                    context_limit = int(data["max_model_len"])

                # Fallback: check in nested metadata
                elif "metadata" in data:
                    if "max_model_len" in data["metadata"]:
                        context_limit = int(data["metadata"]["max_model_len"])
                    elif "max_position_embeddings" in data["metadata"]:
                        context_limit = int(data["metadata"]["max_position_embeddings"])

                # Fallback: check for max_position_embeddings
                elif "max_position_embeddings" in data:
                    context_limit = int(data["max_position_embeddings"])

                if context_limit is None:
                    raise RuntimeError(
                        f"Context limit not found for TabbyAPI model '{model}'. "
                        f"Available keys: {list(data.keys())}"
                    )

                # TabbyAPI doesn't expose VRAM usage - return 0
                model_size_bytes = 0
                logger.debug(
                    "TabbyAPI doesn't expose model VRAM size, returning 0 "
                    "(VRAM calculation will use free memory estimation)"
                )

                return (context_limit, model_size_bytes)

        except Exception as e:
            raise RuntimeError(f"Failed to query TabbyAPI for model '{model}': {e}") from e

    async def is_model_loaded(self, model: str) -> bool:
        """
        Check if model is loaded in TabbyAPI.

        For TabbyAPI, the model is ALWAYS loaded since the server is started
        with a specific model and cannot switch models without restart.

        Args:
            model: Model name (ignored, always returns True)

        Returns:
            bool: Always True for TabbyAPI
        """
        return True  # TabbyAPI server always has its model loaded

    def get_capabilities(self) -> Dict[str, bool]:
        """
        Return TabbyAPI backend capabilities

        TabbyAPI characteristics:
        - Fixed model at server startup (no runtime loading/unloading)
        - Fixed context window set at startup (cannot be changed without restart)
        - Supports streaming responses
        - Model is preloaded by server startup
        """
        return {
            "dynamic_models": False,     # Cannot load/unload models (fixed at startup)
            "dynamic_context": False,    # Context is FIXED at startup, cannot recalculate
            "supports_streaming": True,  # Supports streaming responses
            "requires_preload": False    # Model always loaded at server startup
        }

    async def calculate_practical_context(self, model: str) -> tuple[int, list[str]]:
        """
        Return cached startup context for TabbyAPI (FIXED, cannot recalculate)

        TabbyAPI's context is set at server startup and cannot be changed without
        restarting the server. This method returns the cached value that was set
        when the TabbyAPI server started.

        Args:
            model: Model name (ignored, TabbyAPI only serves one model)

        Returns:
            tuple[int, list[str]]: (context_limit, debug_messages)

        Raises:
            RuntimeError: If startup context not set (server not started properly)
        """
        if self._startup_context is None:
            # For TabbyAPI, we can fall back to querying the API
            # (unlike vLLM which requires Manager setup)
            model_limit, _ = await self.get_model_context_limit(model)
            logger.info(f"📊 TabbyAPI context from API: {model_limit:,} tokens")
            return model_limit, [f"📊 TabbyAPI context: {model_limit:,} tokens (from API)"]

        # Return cached startup value (FIXED, cannot recalculate)
        return self._startup_context, self._startup_context_debug

    def set_startup_context(self, context: int, debug_messages: List[str]) -> None:
        """
        Set the startup context value (called after TabbyAPI server start)

        This method can be called after starting TabbyAPI to cache the context
        limit for faster subsequent queries.

        Args:
            context: Context limit in tokens
            debug_messages: Debug messages from context calculation
        """
        self._startup_context = context
        self._startup_context_debug = debug_messages
        logger.info(f"✅ TabbyAPI startup context cached: {context:,} tokens")

    async def close(self):
        """Close HTTP client"""
        await self.client.close()
