"""
vLLM Backend Adapter

vLLM uses OpenAI-compatible API, so we use the openai Python client
"""

import logging
from typing import List, Optional, AsyncIterator, Dict, Any
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


class vLLMBackend(LLMBackend):
    """vLLM backend implementation (OpenAI-compatible)"""

    def __init__(self, base_url: str = "http://localhost:8000/v1", api_key: str = "dummy"):
        super().__init__(base_url=base_url, api_key=api_key)
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,  # vLLM doesn't need real API key
            timeout=60.0  # 60s Timeout - sufficient for parallel requests
        )

    async def list_models(self) -> List[str]:
        """Get list of available models from vLLM"""
        try:
            models_response = await self.client.models.list()
            self._available_models = [model.id for model in models_response.data]
            return self._available_models
        except Exception as e:
            raise BackendConnectionError(f"Failed to list vLLM models: {e}")

    async def chat(
        self,
        model: str,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None,
        stream: bool = False
    ) -> LLMResponse:
        """
        Non-streaming chat with vLLM

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

        # Convert LLLMMessage to OpenAI format
        openai_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        # Build kwargs
        kwargs = {
            "model": model,
            "messages": openai_messages,
            "temperature": options.temperature,
            "top_p": options.top_p,
            "stream": False
        }

        # vLLM-specific parameters (via extra_body)
        extra_body: Dict[str, Any] = {}
        if options.repeat_penalty and options.repeat_penalty != 1.0:
            extra_body["repetition_penalty"] = options.repeat_penalty
        if options.top_k and options.top_k != 40:
            extra_body["top_k"] = options.top_k
        if options.min_p > 0:
            extra_body["min_p"] = options.min_p
        if options.num_predict:
            kwargs["max_tokens"] = options.num_predict

        # Thinking Mode - only send if explicitly set (not None)
        if options.enable_thinking is not None:
            extra_body["chat_template_kwargs"] = {"enable_thinking": options.enable_thinking}
            logger.info(f"🧠 enable_thinking set to: {options.enable_thinking}")

        if extra_body:
            kwargs["extra_body"] = extra_body
            logger.info(f"📦 extra_body: {extra_body}")

        try:
            timer = Timer()
            response = await self.client.chat.completions.create(**kwargs)
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
                raise BackendModelNotFoundError(f"Model '{model}' not found in vLLM")
            else:
                raise BackendInferenceError(f"vLLM inference failed: {e}")

    async def chat_stream(
        self,
        model: str,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None
    ) -> AsyncIterator[Dict]:
        """
        Streaming chat with vLLM

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

        # vLLM-specific parameters
        extra_body: Dict[str, Any] = {}
        if options.repeat_penalty and options.repeat_penalty != 1.0:
            extra_body["repetition_penalty"] = options.repeat_penalty
        if options.top_k and options.top_k != 40:
            extra_body["top_k"] = options.top_k
        if options.min_p > 0:
            extra_body["min_p"] = options.min_p
        if options.num_predict:
            kwargs["max_tokens"] = options.num_predict

        # Thinking Mode - only send if explicitly set (not None)
        if options.enable_thinking is not None:
            extra_body["chat_template_kwargs"] = {"enable_thinking": options.enable_thinking}
            logger.info(f"🧠 enable_thinking set to: {options.enable_thinking}")

        if extra_body:
            kwargs["extra_body"] = extra_body
            logger.info(f"📦 extra_body: {extra_body}")

        try:
            timer = Timer()
            stream = await self.client.chat.completions.create(**kwargs)

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
                raise BackendInferenceError(f"vLLM streaming failed: {e}")

    async def preload_model(self, model: str, num_ctx: Optional[int] = None) -> tuple[bool, float]:
        """
        Preload a model into VRAM by sending a minimal chat request.

        For vLLM: Models are already loaded at startup and kept in VRAM.
        Preloading is unnecessary and wastes time (~3-4s for queued test request).
        We return immediately with success.

        Args:
            model: Model name to preload (e.g., 'qwen3:8b')
            num_ctx: Ignored for vLLM (context is fixed at startup)

        Returns:
            Tuple of (success: bool, load_time: float in seconds)
        """
        # vLLM keeps models loaded in VRAM at all times
        # No preloading needed - return immediately
        logger.debug(f"vLLM: Skipping preload for {model} (already loaded)")
        return (True, 0.0)

    async def health_check(self) -> bool:
        """Check if vLLM is reachable"""
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False

    def get_backend_name(self) -> str:
        return "vLLM"

    async def get_backend_info(self) -> Dict:
        """Get vLLM backend information"""
        try:
            models = await self.list_models()

            return {
                "backend": "vLLM",
                "base_url": self.base_url,
                "available_models": len(models),
                "models": models,
                "healthy": True,
                "api_type": "OpenAI-compatible"
            }
        except Exception as e:
            return {
                "backend": "vLLM",
                "base_url": self.base_url,
                "available_models": 0,
                "models": [],
                "healthy": False,
                "error": str(e)
            }

    async def get_model_context_limit(self, model: str) -> tuple[int, int]:
        """
        Get context limit and estimated model size for a vLLM model.

        vLLM doesn't support /v1/models/{id} endpoint (returns 404).
        Instead, we query /v1/models (list) and find the model's max_model_len.

        Args:
            model: Model name/ID

        Returns:
            tuple[int, int]: (context_limit, model_size_bytes)
                - context_limit: Maximum context window in tokens
                - model_size_bytes: Estimated model size (0 if unavailable)

        Raises:
            RuntimeError: If query fails or model not found

        Note:
            vLLM doesn't expose VRAM usage directly. Model size is estimated
            from parameter count if available, otherwise returns 0.
        """
        try:
            # Query /v1/models endpoint (list all models)
            models_response = await self.client.models.list()

            # Find the requested model in the list
            for model_obj in models_response.data:
                if model_obj.id == model:
                    # Extract max_model_len from model object
                    context_limit = None
                    if hasattr(model_obj, 'max_model_len'):
                        context_limit = int(model_obj.max_model_len)
                    else:
                        # Try as dict if object doesn't have attribute
                        model_dict = model_obj.model_dump() if hasattr(model_obj, 'model_dump') else dict(model_obj)

                        if "max_model_len" in model_dict:
                            context_limit = int(model_dict["max_model_len"])
                        else:
                            raise RuntimeError(
                                f"Context limit field 'max_model_len' not found for vLLM model '{model}'. "
                                f"Available keys: {list(model_dict.keys())}"
                            )

                    # vLLM doesn't expose VRAM usage - return 0 (will use free VRAM estimation)
                    model_size_bytes = 0
                    logger.debug(
                        "vLLM doesn't expose model VRAM size, returning 0 "
                        "(VRAM calculation will use free memory estimation)"
                    )

                    return (context_limit, model_size_bytes)

            # Model not found in list - return reasonable default
            logger.warning(
                f"⚠️ Model '{model}' not found in vLLM models list. "
                f"Using default context limit: 16384 tokens"
            )
            return (16384, 0)  # Reasonable default for Qwen3 models

        except Exception as e:
            # Other errors are unexpected
            logger.error(f"❌ Failed to query vLLM for model '{model}': {e}")
            raise RuntimeError(f"Failed to query vLLM for model '{model}': {e}") from e

    async def is_model_loaded(self, model: str) -> bool:
        """
        Check if model is loaded in vLLM.

        For vLLM, the model is ALWAYS loaded since the server is started
        with a specific model and cannot switch models without restart.

        Args:
            model: Model name (ignored, always returns True)

        Returns:
            bool: Always True for vLLM
        """
        return True  # vLLM server always has its model loaded

    def get_capabilities(self) -> Dict[str, bool]:
        """
        Return vLLM backend capabilities

        vLLM characteristics:
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
        Return cached startup context for vLLM (FIXED, cannot recalculate)

        vLLM's context is set at server startup via --max-model-len and cannot
        be changed without restarting the server. This method returns the cached
        value from global state.

        Args:
            model: Model name (ignored, vLLM only serves one model)

        Returns:
            tuple[int, list[str]]: (context_limit, debug_messages)

        Raises:
            RuntimeError: If startup context not set (server not started properly)
        """
        # Read context from global state (single source of truth)
        from aifred.state import _global_backend_state
        cached_context = _global_backend_state.get("vllm_context")

        if cached_context is None:
            # This should never happen if vLLM Manager set the value correctly
            raise RuntimeError(
                "vLLM startup context not set. "
                "This indicates the vLLM server was not started via vLLM Manager."
            )

        # Return cached startup value (FIXED, cannot recalculate)
        debug_msgs = [f"💾 vLLM Context: {cached_context:,} tokens (from global state)"]
        return (cached_context, debug_msgs)

    def set_startup_context(self, context: int, debug_messages: List[str]) -> None:
        """
        Set the startup context value (called by vLLM Manager after server start)

        This method is called by vLLM Manager after successfully starting the
        vLLM server to cache the context limit that was calculated and used
        for the --max-model-len parameter. Stores value in global backend state.

        Args:
            context: Context limit in tokens (from vLLM Manager)
            debug_messages: Debug messages from context calculation
        """
        # Store in global backend state (single source of truth)
        from aifred.state import _global_backend_state
        _global_backend_state["vllm_context"] = context
        logger.info(f"✅ vLLM startup context cached: {context:,} tokens")

    async def close(self):
        """Close HTTP client"""
        await self.client.close()
