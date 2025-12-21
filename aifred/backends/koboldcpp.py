"""
KoboldCPP Backend Adapter

KoboldCPP is a llama.cpp-based inference server with OpenAI-compatible API.
Optimized for multi-GPU setups with context-offloading support.

Special Features:
- 26.8% faster than Ollama (137.79 vs 122.07 tokens/s)
- Fine-grained GPU layer control via --gpulayers
- Context-offloading for 2x GPU setups (model on GPU0, context on GPU1)
- Flash Attention and Quantized KV Cache support
"""

import time
import asyncio
import logging
from typing import List, Optional, AsyncIterator, Dict, Any
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
from aifred.lib.logging_utils import log_message

logger = logging.getLogger(__name__)

# NOTE: Python asyncio.Lock removed - KoboldCPP handles queuing internally via --multiuser 5
# The Python Lock caused deadlocks when async generators were not fully consumed.
# KoboldCPP's native queue is more robust and doesn't suffer from async generator lifecycle issues.
#
# For GPU inactivity monitoring, we now check KoboldCPP's queue status directly via /api/extra/perf

# Dummy lock for backwards compatibility with state.py inactivity monitor
# This is a simple flag that tracks if any request is in progress
_koboldcpp_request_active = False


class KoboldCPPBackend(LLMBackend):
    """KoboldCPP backend implementation (OpenAI-compatible)"""

    def __init__(self, base_url: str = "http://localhost:5001/v1", api_key: str = "dummy"):
        super().__init__(base_url=base_url, api_key=api_key)
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,  # KoboldCPP doesn't need real API key
            timeout=300.0  # 300s (5min) Timeout - absolute maximum for normal usage
        )
        # Track if we're in the middle of restarting (prevent recursive restart attempts)
        self._restarting = False

    async def list_models(self) -> List[str]:
        """Get list of available models from KoboldCPP"""
        try:
            models_response = await self.client.models.list()
            self._available_models = [model.id for model in models_response.data]
            return self._available_models
        except Exception as e:
            raise BackendConnectionError(f"Failed to list KoboldCPP models: {e}")

    async def _ensure_server_running(self) -> None:
        """
        Ensure KoboldCPP server is running, auto-restart if stopped.

        This method checks if the KoboldCPP server process is running and
        automatically restarts it if needed. Uses the manager from global
        state to leverage existing startup configuration.

        Raises:
            BackendConnectionError: If server cannot be started
        """
        # Prevent recursive restart attempts
        if self._restarting:
            logger.debug("Already restarting, skipping duplicate attempt")
            return

        try:
            from aifred.state import _global_backend_state

            # Get manager from global state
            manager = _global_backend_state.get("koboldcpp_manager")

            # Check if server is already running
            if manager and manager.is_running():
                return  # Server running, nothing to do

            # Server NOT running - need to restart
            logger.info("🔄 KoboldCPP server not running - auto-restarting...")
            self._restarting = True

            # NOTE: UI flag is now set by state.py's _ensure_koboldcpp_running() method
            # This allows Reflex to use `yield` for immediate UI updates

            # Check if manager exists
            if not manager:
                # No manager - cannot auto-restart
                # This should never happen in production (State initializes manager)
                raise BackendConnectionError(
                    "KoboldCPP manager not initialized. "
                    "Please start server via UI first (Settings → Backend → Start KoboldCPP)."
                )

            # Get model info from global state (needed for restart)
            gguf_models = _global_backend_state.get("gguf_models", {})
            selected_model = _global_backend_state.get("koboldcpp_selected_model")

            # If gguf_models not loaded yet (e.g. service restart), scan now
            if not gguf_models:
                from aifred.lib.gguf_utils import find_all_gguf_models
                gguf_models_list = find_all_gguf_models()
                gguf_models = {model.name: model for model in gguf_models_list}
                _global_backend_state["gguf_models"] = gguf_models
                logger.info(f"🔍 GGUF models scanned: {len(gguf_models)} found")

            if not selected_model or selected_model not in gguf_models:
                raise BackendConnectionError(
                    "Cannot auto-restart: Model configuration not cached. "
                    "Please start server via UI first."
                )

            model_info = gguf_models[selected_model]
            model_path = str(model_info.path)

            # Restart server with auto-detection (same logic as state.py)
            logger.info(f"   Model: {selected_model}")
            logger.info(f"   Path: {model_path}")

            success, config_info = await manager.start_with_auto_detection(
                model_path=model_path,
                model_name=selected_model,
                timeout=240  # 4min timeout for large models
            )

            if not success:
                raise BackendConnectionError(
                    "Failed to auto-restart KoboldCPP server. "
                    "Please check logs and restart manually via UI."
                )

            # Update global state with new config
            _global_backend_state["koboldcpp_context"] = config_info['context_size']
            _global_backend_state["koboldcpp_native_context"] = config_info.get('native_context')

            # Update context cache (same as state.py does)
            from aifred.lib.context_manager import _last_vram_limit_cache
            _last_vram_limit_cache["limit"] = config_info['context_size']

            logger.info(f"✅ KoboldCPP auto-restarted: {config_info['context_size']:,} tokens context")

            # Restart InactivityMonitor (Phase 2 - Auto-Shutdown)
            monitor = _global_backend_state.get("inactivity_monitor")
            if monitor and not monitor.is_monitoring():
                await monitor.start_monitoring()
                logger.info("🔍 Inactivity monitor restarted (timeout: 30s)")

            # NOTE: UI flag is cleared by state.py's _ensure_koboldcpp_running() method

        except BackendConnectionError:
            raise  # Re-raise our own exceptions
        except Exception as e:
            logger.error(f"❌ Auto-restart failed: {e}")
            raise BackendConnectionError(f"Auto-restart failed: {e}") from e
        finally:
            self._restarting = False

    # NOTE: _record_activity() removed - new GPU-based monitor tracks activity automatically
    # Old timestamp-based approach had race conditions and killed active requests
    # New approach uses nvidia-smi to check GPU utilization directly

    async def chat(
        self,
        model: str,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None,
        stream: bool = False
    ) -> LLMResponse:
        """
        Non-streaming chat with KoboldCPP

        Args:
            model: Model name
            messages: List of LLMMessage
            options: Generation options
            stream: Ignored

        Returns:
            LLMResponse
        """
        # CRITICAL: Ensure server is running BEFORE API call (auto-restart if needed)
        await self._ensure_server_running()

        # NOTE: No Python lock needed - KoboldCPP handles queuing via --multiuser 5
        # The server queues up to 5 concurrent requests and processes them sequentially

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

        # KoboldCPP-specific parameters (via extra_body)
        extra_body: Dict[str, Any] = {}
        if options.repeat_penalty and options.repeat_penalty != 1.0:
            extra_body["repetition_penalty"] = options.repeat_penalty
        if options.top_k and options.top_k != 40:
            extra_body["top_k"] = options.top_k
        if options.num_predict:
            kwargs["max_tokens"] = options.num_predict

        if extra_body:
            kwargs["extra_body"] = extra_body
            logger.info(f"📦 extra_body: {extra_body}")

        try:
            start_time = time.time()
            response = await self.client.chat.completions.create(**kwargs)
            inference_time = time.time() - start_time

            choice = response.choices[0]
            text = choice.message.content

            # Extract usage info
            usage = response.usage
            tokens_prompt = usage.prompt_tokens if usage else 0
            tokens_generated = usage.completion_tokens if usage else 0

            tokens_per_second = (tokens_generated / inference_time) if inference_time > 0 else 0

            # NOTE: No manual activity recording needed - GPU monitor tracks automatically

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
                raise BackendModelNotFoundError(f"Model '{model}' not found in KoboldCPP")
            else:
                raise BackendInferenceError(f"KoboldCPP inference failed: {e}")

    async def chat_stream(
        self,
        model: str,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None
    ) -> AsyncIterator[Dict]:
        """
        Streaming chat with KoboldCPP

        Args:
            model: Model name
            messages: List of LLMMessage
            options: Generation options

        Yields:
            Dict with either:
            - {"type": "content", "text": str} for content chunks
            - {"type": "done", "metrics": {...}} for final metrics
            - {"type": "debug", "message": str} for queue notification (if waiting)
        """
        # CRITICAL: Ensure server is running BEFORE API call (auto-restart if needed)
        await self._ensure_server_running()

        # NOTE: No Python lock needed - KoboldCPP handles queuing via --multiuser 5
        # The server queues up to 5 concurrent requests and processes them sequentially

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

        # KoboldCPP-specific parameters
        extra_body: Dict[str, Any] = {}
        if options.repeat_penalty and options.repeat_penalty != 1.0:
            extra_body["repetition_penalty"] = options.repeat_penalty
        if options.top_k and options.top_k != 40:
            extra_body["top_k"] = options.top_k
        if options.num_predict:
            kwargs["max_tokens"] = options.num_predict

        if extra_body:
            kwargs["extra_body"] = extra_body
            logger.info(f"📦 extra_body: {extra_body}")

        try:
            start_time = time.time()
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
                    total_tokens = chunk.usage.completion_tokens

            # Final metrics
            inference_time = time.time() - start_time
            tokens_per_second = (total_tokens / inference_time) if inference_time > 0 else 0

            # NOTE: No manual activity recording needed - GPU monitor tracks automatically

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
                raise BackendInferenceError(f"KoboldCPP streaming failed: {e}")

    async def health_check(self) -> bool:
        """Check if KoboldCPP is reachable"""
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False

    def get_backend_name(self) -> str:
        return "KoboldCPP"

    async def get_backend_info(self) -> Dict:
        """Get KoboldCPP backend information"""
        try:
            # Get models
            models = await self.list_models()

            return {
                "backend": "KoboldCPP",
                "version": "unknown",  # KoboldCPP doesn't expose version via API
                "base_url": self.base_url,
                "available_models": len(models),
                "models": models,
                "healthy": True
            }
        except Exception as e:
            return {
                "backend": "KoboldCPP",
                "version": "unknown",
                "base_url": self.base_url,
                "available_models": 0,
                "models": [],
                "healthy": False,
                "error": str(e)
            }

    async def get_model_context_limit(self, model: str) -> tuple[int, int]:
        """
        Get context limit and model size for a KoboldCPP model.

        KoboldCPP models have a fixed context limit set at server startup.
        Model size is not available via API.

        Args:
            model: Model ID (pure name without size suffix)

        Returns:
            tuple[int, int]: (context_limit, model_size_bytes)
                - context_limit: Maximum context window in tokens (from server config)
                - model_size_bytes: 0 (not available via API)

        Raises:
            RuntimeError: If model not found or context limit not available
        """
        try:
            # Query /v1/models endpoint
            models_response = await self.client.models.list()

            for model_info in models_response.data:
                # Match both exact ID and ID without "koboldcpp/" prefix
                model_id = model_info.id
                model_id_without_prefix = model_id.replace("koboldcpp/", "")

                if model_id == model or model_id_without_prefix == model:
                    # KoboldCPP doesn't expose context limit via API
                    # Try to get it from global state (set during server startup)
                    try:
                        from aifred.state import _global_backend_state

                        # IMPORTANT: Return NATIVE context (model's true max) not VRAM-optimized context
                        # This ensures "Model Max" shows 262k instead of 105k
                        native_context = _global_backend_state.get("koboldcpp_native_context")

                        if native_context and native_context > 0:
                            logger.info(f"Using native KoboldCPP context: {native_context:,} tokens (from GGUF metadata)")
                            return (native_context, 0)

                        # Fallback: Use VRAM-optimized context if native not available
                        cached_context = _global_backend_state.get("koboldcpp_context", 0)
                        if cached_context > 0:
                            logger.warning(
                                f"Native context not available, using VRAM-optimized context: {cached_context:,} tokens"
                            )
                            return (cached_context, 0)
                        else:
                            logger.warning(
                                f"KoboldCPP does not expose context limit via API for model '{model}'. "
                                f"Context size not yet cached - will use fallback."
                            )
                            return (0, 0)
                    except Exception as e:
                        logger.warning(f"Could not get cached context: {e}")
                        return (0, 0)

            raise RuntimeError(f"Model '{model}' not found in KoboldCPP")

        except Exception as e:
            raise RuntimeError(f"Failed to query KoboldCPP for model '{model}': {e}") from e

    async def is_model_loaded(self, model: str) -> bool:
        """
        Check if model is currently loaded in KoboldCPP's VRAM.

        KoboldCPP loads exactly one model at server startup and keeps it loaded.

        Args:
            model: Model name

        Returns:
            bool: Always True (model is always loaded)
        """
        return True

    async def preload_model(self, model: str, num_ctx: Optional[int] = None) -> tuple[bool, float]:
        """
        Preload a model into VRAM.

        KoboldCPP loads models at server startup, not at runtime.
        This method is a no-op for compatibility.

        Args:
            model: Model name (ignored)
            num_ctx: Ignored for KoboldCPP (context is fixed at startup)

        Returns:
            Tuple of (success: bool, load_time: float)
        """
        logger.info("KoboldCPP preload_model called, but models are loaded at server startup")
        return (True, 0.0)

    def get_capabilities(self) -> Dict[str, bool]:
        """
        Return KoboldCPP backend capabilities

        KoboldCPP:
        - Does NOT support dynamic model loading (server started with one model)
        - Does NOT support dynamic context calculation (context fixed at startup)
        - Supports streaming responses
        - Does NOT require preloading (model always loaded)
        """
        return {
            "dynamic_models": False,     # Server started with specific model
            "dynamic_context": False,    # Context fixed at server startup
            "supports_streaming": True,  # Supports streaming responses
            "requires_preload": False    # Model always loaded
        }

    async def calculate_practical_context(self, model: str) -> tuple[int, list[str]]:
        """
        Calculate practical context for KoboldCPP (FIXED at server startup)

        KoboldCPP models are started with a fixed context limit that cannot
        be changed at runtime. Return the cached startup context from global state.

        Args:
            model: Model name

        Returns:
            tuple[int, list[str]]: (context_limit, debug_messages)
        """
        debug_msgs = []

        # Read context from global state (single source of truth)
        from aifred.state import _global_backend_state
        cached_context = _global_backend_state.get("koboldcpp_context")

        if cached_context:
            return (cached_context, debug_msgs)

        # No cached context - server not started yet or startup failed
        logger.warning(
            f"No cached startup context for KoboldCPP model '{model}'. "
            f"Using default 4096 tokens. This may be incorrect."
        )
        debug_msgs.append(
            "⚠️ No cached context limit - using default 4096 tokens. "
            "This may be incorrect."
        )
        return (4096, debug_msgs)

    def set_startup_context(self, context: int, debug_messages: List[str]) -> None:
        """
        Set the startup context value (called by KoboldCPP Manager after server start)

        This method is called by KoboldCPP Manager after successfully starting the
        KoboldCPP server to cache the context limit that was calculated and used
        for the --contextsize parameter. Stores value in global backend state.

        Args:
            context: Context limit in tokens (from KoboldCPP Manager)
            debug_messages: Debug messages from context calculation
        """
        # Store in global backend state (single source of truth)
        from aifred.state import _global_backend_state
        _global_backend_state["koboldcpp_context"] = context
        logger.info(f"✅ KoboldCPP startup context cached: {context:,} tokens")

    async def close(self):
        """Close HTTP client"""
        await self.client.close()
