"""
Ollama Backend Adapter

Wraps Ollama API into unified LLMBackend interface
"""

import httpx
import time
import logging
from typing import List, Optional, AsyncIterator, Dict
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


class OllamaBackend(LLMBackend):
    """Ollama backend implementation"""

    def __init__(self, base_url: str = "http://localhost:11434"):
        super().__init__(base_url=base_url)
        # Timeout: None = UNLIMITED (Reflex will handle timeouts, not httpx)
        # Limits: Increase connection limits to avoid pooling issues
        # History: Was 300s fixed, now unlimited for better flexibility
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=300.0)
        timeout = httpx.Timeout(None)  # UNLIMITED - let Reflex/asyncio handle timeouts
        self.client = httpx.AsyncClient(timeout=timeout, limits=limits)

    async def list_models(self) -> List[str]:
        """Get list of available Ollama models"""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            self._available_models = [m["name"] for m in data.get("models", [])]
            return self._available_models
        except Exception as e:
            raise BackendConnectionError(f"Failed to list Ollama models: {e}")

    async def chat(
        self,
        model: str,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None,
        stream: bool = False
    ) -> LLMResponse:
        """
        Non-streaming chat with Ollama

        Args:
            model: Ollama model name (e.g., 'qwen3:8b')
            messages: List of LLMMessage
            options: Generation options
            stream: Ignored (use chat_stream for streaming)

        Returns:
            LLMResponse
        """
        if options is None:
            options = LLMOptions()

        # Convert LLMMessage to Ollama format (supports multimodal content)
        ollama_messages = []
        for msg in messages:
            # Handle multimodal content (text + images)
            if isinstance(msg.content, list):
                # Extract text and images from multimodal content
                text_parts = []
                image_base64_list = []

                for part in msg.content:
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif part.get("type") == "image_url":
                        # Extract base64 from data URL (format: "data:image/jpeg;base64,...")
                        image_url = part.get("image_url", {}).get("url", "")
                        if image_url.startswith("data:image"):
                            # Extract base64 part after "base64,"
                            base64_data = image_url.split("base64,", 1)[1] if "base64," in image_url else ""
                            if base64_data:
                                image_base64_list.append(base64_data)

                # Build Ollama message with separate images array
                ollama_msg = {
                    "role": msg.role,
                    "content": " ".join(text_parts)
                }
                if image_base64_list:
                    ollama_msg["images"] = image_base64_list
                    logger.info(f"🖼️ Added {len(image_base64_list)} image(s) to message (base64 length: {len(image_base64_list[0])})")

                ollama_messages.append(ollama_msg)
            elif isinstance(msg.content, str):
                # Legacy text-only format
                ollama_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })

        # Build options dict
        ollama_options = {
            "temperature": options.temperature,
            "repeat_penalty": options.repeat_penalty,
            "top_p": options.top_p,
            "top_k": options.top_k,
        }
        if options.num_ctx:
            ollama_options["num_ctx"] = options.num_ctx
        # NOTE: num_predict intentionally NOT set for Ollama
        # Ollama generates until EOS or num_ctx is full - no artificial limit needed
        if options.seed:
            ollama_options["seed"] = options.seed

        payload = {
            "model": model,
            "messages": ollama_messages,
            "options": ollama_options,
            "stream": False
        }

        # Thinking Mode: ALWAYS False for non-streaming chat (used by Automatik-LLM)
        # Automatik-LLM should never do reasoning - only fast decisions
        payload["think"] = False

        try:
            start_time = time.time()
            # Use client's default timeout (unlimited) - Reflex handles timeouts
            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json=payload
                # No explicit timeout - uses client default (unlimited from __init__)
            )
            response.raise_for_status()
            inference_time = time.time() - start_time

            data = response.json()

            # Extract text from response
            # Support both standard models (content) and thinking models (thinking field)
            message = data.get("message", {})
            content = message.get("content", "")
            thinking = message.get("thinking", "")

            # If thinking mode enabled and thinking present, wrap in <think> tags
            if thinking and content:
                # Both present: wrap thinking in tags, append content
                text = f"<think>{thinking}</think>\n\n{content}"
            elif thinking and not content:
                # Only thinking present: wrap in tags
                text = f"<think>{thinking}</think>"
            else:
                # No thinking or only content: use content
                text = content

            eval_count = data.get("eval_count", 0)
            eval_duration = data.get("eval_duration", 1)  # nanoseconds
            prompt_eval_count = data.get("prompt_eval_count", 0)

            tokens_per_second = (eval_count / (eval_duration / 1e9)) if eval_duration > 0 else 0

            return LLMResponse(
                text=text,
                tokens_prompt=prompt_eval_count,
                tokens_generated=eval_count,
                tokens_per_second=tokens_per_second,
                inference_time=inference_time,
                model=model
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise BackendModelNotFoundError(f"Model '{model}' not found in Ollama")
            elif e.response.status_code == 400 and options.enable_thinking:
                # Check if error is about thinking mode not supported
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get("error", "")
                    if "does not support thinking" in error_msg:
                        # Retry without thinking mode
                        logger.warning(f"⚠️ Model '{model}' does not support thinking mode, retrying with think=false")
                        payload["think"] = False

                        # Retry request
                        start_time = time.time()
                        response = await self.client.post(
                            f"{self.base_url}/api/chat",
                            json=payload
                        )
                        response.raise_for_status()
                        inference_time = time.time() - start_time

                        data = response.json()
                        message = data.get("message", {})
                        content = message.get("content", "")
                        thinking = message.get("thinking", "")

                        if thinking and content:
                            text = f"<think>{thinking}</think>\n\n{content}"
                        elif thinking and not content:
                            text = f"<think>{thinking}</think>"
                        else:
                            text = content

                        eval_count = data.get("eval_count", 0)
                        eval_duration = data.get("eval_duration", 1)
                        prompt_eval_count = data.get("prompt_eval_count", 0)
                        tokens_per_second = (eval_count / (eval_duration / 1e9)) if eval_duration > 0 else 0

                        return LLMResponse(
                            text=text,
                            tokens_prompt=prompt_eval_count,
                            tokens_generated=eval_count,
                            tokens_per_second=tokens_per_second,
                            inference_time=inference_time,
                            model=model
                        )
                except Exception:
                    pass  # If JSON parsing fails, fall through to normal error handling
                raise BackendInferenceError(f"Ollama HTTP error: {e}")
            elif e.response.status_code == 500:
                error_msg = e.response.text
                raise BackendInferenceError(f"Ollama inference error: {error_msg}")
            else:
                raise BackendInferenceError(f"Ollama HTTP error: {e}")
        except Exception as e:
            raise BackendInferenceError(f"Ollama chat failed: {e}")

    async def chat_stream(
        self,
        model: str,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None
    ) -> AsyncIterator[Dict]:
        """
        Streaming chat with Ollama
        
        Args:
            model: Ollama model name
            messages: List of LLMMessage
            options: Generation options
        
        Yields:
            Dict with either:
            - {"type": "content", "text": str} for content chunks
            - {"type": "done", "metrics": {...}} for final metrics
        """
        if options is None:
            options = LLMOptions()
        
        # Convert LLMMessage to Ollama format (supports multimodal content)
        ollama_messages = []
        for msg in messages:
            # Handle multimodal content (text + images)
            if isinstance(msg.content, list):
                # Extract text and images from multimodal content
                text_parts = []
                image_base64_list = []

                for part in msg.content:
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif part.get("type") == "image_url":
                        # Extract base64 from data URL (format: "data:image/jpeg;base64,...")
                        image_url = part.get("image_url", {}).get("url", "")
                        if image_url.startswith("data:image"):
                            # Extract base64 part after "base64,"
                            base64_data = image_url.split("base64,", 1)[1] if "base64," in image_url else ""
                            if base64_data:
                                image_base64_list.append(base64_data)

                # Build Ollama message with separate images array
                ollama_msg = {
                    "role": msg.role,
                    "content": " ".join(text_parts)
                }
                if image_base64_list:
                    ollama_msg["images"] = image_base64_list
                    logger.info(f"🖼️ Added {len(image_base64_list)} image(s) to message (base64 length: {len(image_base64_list[0])})")

                ollama_messages.append(ollama_msg)
            elif isinstance(msg.content, str):
                # Legacy text-only format
                ollama_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })

        # Build options
        ollama_options = {
            "temperature": options.temperature,
            "repeat_penalty": options.repeat_penalty,
            "top_p": options.top_p,
            "top_k": options.top_k,
        }
        if options.num_ctx:
            ollama_options["num_ctx"] = options.num_ctx
        # NOTE: num_predict intentionally NOT set for Ollama
        # Ollama generates until EOS or num_ctx is full - no artificial limit needed
        if options.seed:
            ollama_options["seed"] = options.seed

        payload = {
            "model": model,
            "messages": ollama_messages,
            "options": ollama_options,
            "stream": True
        }

        # Thinking Mode: Always send "think" parameter (true or false)
        # Treat None as False (disabled)
        payload["think"] = options.enable_thinking if options.enable_thinking is not None else False

        # Retry loop: try once, retry with think=false if needed
        retry_message_shown = False
        first_content_sent = False
        for attempt in range(2):

            try:
                start_time = time.time()
                thinking_started = False
                thinking_buffer = ""

                async with self.client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                    # Check for 400 error with thinking mode BEFORE raise_for_status
                    if response.status_code == 400 and options.enable_thinking and attempt == 0:
                        # Read error body while stream is still open
                        import json
                        error_body = await response.aread()
                        error_data = json.loads(error_body.decode('utf-8'))
                        error_msg = error_data.get("error", "")
                        
                        if "does not support thinking" in error_msg:
                            log_message(f"⚠️ Model '{model}' does not support thinking mode, retrying with think=false")
                            # Set payload for retry
                            payload["think"] = False
                            continue  # Retry with attempt=1 (warning will be shown with first content)
                        else:
                            # Different 400 error
                            response.raise_for_status()
                    elif response.status_code == 404:
                        raise BackendModelNotFoundError(f"Model '{model}' not found")
                    elif response.status_code >= 400:
                        response.raise_for_status()
                    
                    # Process stream
                    async for line in response.aiter_lines():
                        if line.strip():
                            import json
                            try:
                                data = json.loads(line)
                                message = data.get("message", {})
                                content = message.get("content", "")
                                thinking = message.get("thinking", "")
                                
                                # Handle thinking chunks
                                if thinking:
                                    if not thinking_started:
                                        yield {"type": "content", "text": "<think>"}
                                        thinking_started = True
                                    thinking_buffer += thinking
                                    yield {"type": "content", "text": thinking}
                                
                                # Handle content chunks
                                if content:
                                    # Show retry message and warning before first content (only on attempt 1)
                                    if not first_content_sent and attempt == 1 and not retry_message_shown:
                                        yield {"type": "thinking_warning", "model": model}
                                        yield {"type": "debug", "message": f"⚠️ Model '{model}' doesn't support reasoning - running without think mode"}
                                        retry_message_shown = True
                                        first_content_sent = True

                                    if thinking_started and thinking_buffer:
                                        yield {"type": "content", "text": "</think>\n\n"}
                                        thinking_started = False
                                        thinking_buffer = ""
                                    yield {"type": "content", "text": content}
                                
                                # Check if done - extract metrics
                                if data.get("done", False):
                                    inference_time = time.time() - start_time
                                    eval_count = data.get("eval_count", 0)
                                    eval_duration = data.get("eval_duration", 1)
                                    prompt_eval_count = data.get("prompt_eval_count", 0)
                                    tokens_per_second = (eval_count / (eval_duration / 1e9)) if eval_duration > 0 else 0
                                    
                                    yield {
                                        "type": "done",
                                        "metrics": {
                                            "tokens_prompt": prompt_eval_count,
                                            "tokens_generated": eval_count,
                                            "tokens_per_second": tokens_per_second,
                                            "inference_time": inference_time,
                                            "model": model
                                        }
                                    }
                                    return  # Success, exit function
                            except json.JSONDecodeError as e:
                                logger.warning(f"Invalid JSON in Ollama stream: {line[:100]}... Error: {e}")
                                continue
            
            except httpx.HTTPStatusError as e:
                # If this is attempt 0 and might be thinking-related, loop will retry
                # If this is attempt 1 or not thinking-related, raise the error
                if attempt == 1 or not (e.response.status_code == 400 and options.enable_thinking):
                    if e.response.status_code == 404:
                        raise BackendModelNotFoundError(f"Model '{model}' not found")
                    else:
                        raise BackendInferenceError(f"Ollama streaming error: {e}")
                # else: continue to retry

    async def unload_all_models(self) -> tuple[bool, list[str]]:
        """
        Unload ALL currently loaded models from VRAM.

        This ensures maximum VRAM is available for the next model to be loaded.
        Uses /api/ps to get loaded models, then unloads each via keep_alive=0.

        Returns:
            tuple[bool, list[str]]: (success, list of unloaded model names)
        """
        try:
            # Get list of currently loaded models
            response = await self.client.get(f"{self.base_url}/api/ps")
            if response.status_code != 200:
                logger.warning("Failed to get loaded models list")
                return (False, [])

            data = response.json()
            loaded_models = data.get("models", [])

            if not loaded_models:
                logger.info("No models currently loaded")
                return (True, [])

            unloaded_models = []

            # Unload each model
            for model_info in loaded_models:
                model_name = model_info.get("name", "")
                if not model_name:
                    continue

                logger.info(f"Unloading model: {model_name}")

                # Send minimal generate request with keep_alive=0 to unload
                unload_response = await self.client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": model_name,
                        "prompt": "",  # Required field for /api/generate
                        "keep_alive": 0  # Immediately unload after request
                    }
                )

                if unload_response.status_code != 200:
                    logger.warning(f"Failed to unload {model_name}")
                    return (False, unloaded_models)

                unloaded_models.append(model_name)

            logger.info(f"Successfully unloaded {len(unloaded_models)} model(s)")
            return (True, unloaded_models)

        except Exception as e:
            logger.warning(f"Failed to unload models: {e}")
            return (False, [])

    async def preload_model(self, model: str, num_ctx: Optional[int] = None) -> tuple[bool, float]:
        """
        Preload a model into VRAM by sending a minimal chat request.
        This warms up the model so future requests are faster.

        NOTE: Caller should explicitly call unload_all_models() BEFORE this
        to ensure proper model loading order (e.g., unload Automatik-LLM first).

        Args:
            model: Model name to preload (e.g., 'qwen3:8b')
            num_ctx: Context window size to use. IMPORTANT: Ollama uses this to
                     allocate KV cache and potentially split model across multiple
                     GPUs if the model + KV cache doesn't fit on a single GPU.

        Returns:
            Tuple of (success: bool, load_time: float in seconds)
        """
        try:
            from ..lib.logging_utils import log_message
            start_time = time.time()
            log_message(f"⏱️ preload_model: START for {model} (num_ctx={num_ctx})")

            # Load the requested model
            # Send minimal request to trigger model loading
            options = {
                "num_predict": 1,  # Only generate 1 token
                "temperature": 0.0
            }
            # IMPORTANT: Set num_ctx during preload so Ollama loads the model
            # with the correct KV-Cache and distributes across multiple GPUs if needed
            if num_ctx is not None:
                options["num_ctx"] = num_ctx
                logger.info(f"🎯 Preload with num_ctx={num_ctx:,} for multi-GPU distribution")

            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
                "options": options
            }

            log_message(f"⏱️ preload_model: Sending request to Ollama...")
            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json=payload
                # No timeout: Ollama queues requests automatically, even while model is loading
            )

            load_time = time.time() - start_time
            log_message(f"⏱️ preload_model: Response received after {load_time:.1f}s (status={response.status_code})")
            success = response.status_code == 200
            # Note: VRAM stabilization is handled in calculate_vram_based_context()
            return (success, load_time)
        except Exception as e:
            load_time = time.time() - start_time
            logger.warning(f"Preload failed for {model}: {e}")
            return (False, load_time)

    async def health_check(self) -> bool:
        """Check if Ollama is reachable"""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    def get_backend_name(self) -> str:
        return "Ollama"

    async def get_backend_info(self) -> Dict:
        """Get Ollama backend information"""
        try:
            # Try to get version
            response = await self.client.get(f"{self.base_url}/api/version")
            version = response.json().get("version", "unknown") if response.status_code == 200 else "unknown"

            # Get models
            models = await self.list_models()

            return {
                "backend": "Ollama",
                "version": version,
                "base_url": self.base_url,
                "available_models": len(models),
                "models": models,
                "healthy": True
            }
        except Exception as e:
            return {
                "backend": "Ollama",
                "version": "unknown",
                "base_url": self.base_url,
                "available_models": 0,
                "models": [],
                "healthy": False,
                "error": str(e)
            }

    async def get_model_context_limit(self, model: str) -> tuple[int, int]:
        """
        Get context limit and model size for an Ollama model.

        Queries /api/show endpoint and extracts context_length from modelinfo
        and model file size. Works even if model is not loaded.
        Very fast (~30ms).

        Args:
            model: Model name (e.g., "qwen3:8b", "phi3:mini")

        Returns:
            tuple[int, int]: (context_limit, model_size_bytes)
                - context_limit: Maximum context window in tokens
                - model_size_bytes: Model file size in bytes (0 if unavailable)

        Raises:
            RuntimeError: If model not found or context limit not extractable
        """
        try:
            # 1. Get context limit from /api/show
            response = await self.client.post(
                f"{self.base_url}/api/show",
                json={"name": model}
            )
            response.raise_for_status()
            data = response.json()

            # HTTP API uses 'model_info' (underscore), Python SDK uses 'modelinfo' (no underscore)
            model_details = data.get('model_info') or data.get('modelinfo', {})

            context_limit = None

            # Suche nach .context_length (tatsächliches nutzbares Kontextfenster)
            # WICHTIG: original_context_length ist nur für RoPE-Scaling intern relevant
            # und repräsentiert NICHT das nutzbare Kontextfenster!
            for key, value in model_details.items():
                if key.endswith('.context_length') and 'original' not in key.lower():
                    context_limit = int(value)
                    break

            # No context limit found
            if context_limit is None:
                available_keys = list(model_details.keys())[:10]
                raise RuntimeError(
                    f"Context limit not found for model '{model}'. "
                    f"Available keys: {available_keys}"
                )

            # 2. Get model file size from blob path in modelfile
            model_size_bytes = 0
            modelfile = data.get('modelfile', '')

            # Extract blob hash from FROM line (e.g., "FROM /path/to/blobs/sha256-...")
            import re
            blob_match = re.search(
                r'FROM\s+(/[^\s]+/blobs/(sha256-[a-f0-9]+))',
                modelfile
            )

            if blob_match:
                blob_path = blob_match.group(1)
                try:
                    # Get file size from filesystem
                    import os
                    if os.path.exists(blob_path):
                        model_size_bytes = os.path.getsize(blob_path)
                        log_message(
                            f"📦 Model '{model}' size: {model_size_bytes / (1024**3):.2f}GB "
                            f"(context limit: {context_limit:,} tokens)"
                        )
                    else:
                        logger.warning(f"Blob path not found: {blob_path}")
                except Exception as e:
                    logger.warning(f"Could not get blob size: {e}")
            else:
                logger.warning(
                    f"Could not extract blob path from modelfile for '{model}' "
                    f"- VRAM calculation will use model_limit fallback"
                )

            return (context_limit, model_size_bytes)

        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to query Ollama for model '{model}': {e}") from e

    async def is_model_loaded(self, model: str) -> bool:
        """
        Check if model is currently loaded in Ollama's VRAM.

        Queries /api/ps endpoint to get list of loaded models.

        Args:
            model: Model name (e.g., "qwen3:8b")

        Returns:
            bool: True if model is loaded, False otherwise
        """
        try:
            response = await self.client.get(f"{self.base_url}/api/ps")
            response.raise_for_status()
            data = response.json()

            # Check if model exists in 'models' array
            loaded_models = data.get('models', [])
            for loaded_model in loaded_models:
                if loaded_model.get('name') == model:
                    return True

            return False

        except httpx.HTTPError as e:
            logger.warning(f"Failed to query Ollama /api/ps: {e}")
            return False  # Assume not loaded on error

    async def get_loaded_model_context(self, model: str) -> Optional[int]:
        """
        Get the context length that a loaded model is currently using.

        This queries /api/ps to get the ACTUAL context_length value that Ollama
        is using for this model (which may be lower than the architectural maximum
        due to VRAM constraints or manual num_ctx settings).

        Args:
            model: Model name (e.g., "qwen3:8b")

        Returns:
            int: Context length the model is loaded with, or None if not loaded
        """
        try:
            response = await self.client.get(f"{self.base_url}/api/ps")
            response.raise_for_status()
            data = response.json()

            # Find model in 'models' array
            loaded_models = data.get('models', [])
            for loaded_model in loaded_models:
                if loaded_model.get('name') == model:
                    # Return the context_length Ollama is using for this model
                    return loaded_model.get('context_length')

            return None  # Model not loaded

        except httpx.HTTPError as e:
            logger.warning(f"Failed to query Ollama /api/ps: {e}")
            return None

    def get_capabilities(self) -> Dict[str, bool]:
        """
        Return Ollama backend capabilities

        Ollama supports:
        - Dynamic model loading/unloading (via /api/ps)
        - Dynamic context calculation (based on current VRAM)
        - Streaming responses
        - Model preloading
        """
        return {
            "dynamic_models": True,      # Can load/unload models at runtime
            "dynamic_context": True,     # Context can be recalculated based on VRAM
            "supports_streaming": True,  # Supports streaming responses
            "requires_preload": False    # Optional preloading (for performance only)
        }

    async def calculate_practical_context(
        self,
        model: str
    ) -> tuple[int, list[str]]:
        """
        Calculate practical context for Ollama (dynamic VRAM-based calculation)

        Ollama models can be loaded/unloaded dynamically, so context is calculated
        fresh each time based on current VRAM availability.

        IMPORTANT: This function UNLOADS ALL MODELS before measuring VRAM!
        This ensures accurate VRAM measurement even if Automatik-LLM or Vision-LLM
        were running before the Main-LLM inference.

        Note: Per-model RoPE 2x toggle is read automatically from VRAM cache.

        Args:
            model: Model name

        Returns:
            tuple[int, list[str]]: (context_limit, debug_messages)
        """
        import asyncio
        from ..lib.gpu_utils import calculate_vram_based_context, get_model_size_from_cache

        debug_msgs = []

        # Get model metadata FIRST (doesn't require unloading)
        model_limit, model_size_bytes = await self.get_model_context_limit(model)

        # If model size not available from API, try cache
        if model_size_bytes == 0:
            model_size_bytes = get_model_size_from_cache(model)

        # CRITICAL: Unload ALL models before VRAM measurement
        # This ensures we measure truly free VRAM, not VRAM minus Automatik-LLM
        success, unloaded = await self.unload_all_models()
        if success and unloaded:
            debug_msgs.append(f"🔄 Models unloaded: {', '.join(unloaded)}")
            # Wait for VRAM to be fully released by GPU driver
            await asyncio.sleep(2.0)
            debug_msgs.append("✅ VRAM released")

        # After unloading, model is definitely NOT loaded
        model_is_loaded = False

        # Calculate practical context based on current VRAM (with auto-MoE detection)
        # Note: use_extended is read from cache inside calculate_vram_based_context
        num_ctx, vram_debug_msgs = await calculate_vram_based_context(
            model_name=model,
            model_size_bytes=model_size_bytes,
            model_context_limit=model_limit,
            model_is_loaded=model_is_loaded,
            backend_type="ollama",
            backend=self  # Pass self for fallback unloading (shouldn't be needed now)
        )

        # Combine debug messages
        debug_msgs.extend(vram_debug_msgs)

        return num_ctx, debug_msgs

    async def _is_fully_in_vram(self, model: str) -> bool:
        """
        Check if model is fully loaded in VRAM (no CPU offloading).

        Queries /api/ps and compares `size` (total) vs `size_vram` (GPU only).
        If size == size_vram, the model fits entirely in GPU memory.

        Args:
            model: Model name (e.g., "qwen3:8b")

        Returns:
            True if model is 100% in VRAM, False if CPU offloading is active
        """
        try:
            response = await self.client.get(f"{self.base_url}/api/ps")
            response.raise_for_status()
            data = response.json()

            for loaded_model in data.get("models", []):
                # Match model name (handle tags like "qwen3:8b" vs "qwen3:8b-instruct")
                if loaded_model.get("name") == model or model in loaded_model.get("name", ""):
                    size = loaded_model.get("size", 0)
                    size_vram = loaded_model.get("size_vram", 0)

                    # Log for debugging
                    logger.debug(
                        f"📊 VRAM check: {model} → size={size:,}, size_vram={size_vram:,}, "
                        f"fully_in_vram={size == size_vram}"
                    )

                    return size == size_vram

            logger.warning(f"Model {model} not found in /api/ps response")
            return False

        except httpx.HTTPError as e:
            logger.warning(f"Failed to query /api/ps: {e}")
            return False

    async def calibrate_max_context_generator(
        self,
        model: str,
        extended: bool = False
    ):
        """
        Calibrate maximum context window without CPU offloading via binary search.

        This is an async generator that yields progress messages for UI updates.
        Uses /api/ps to detect if model fits entirely in VRAM (size == size_vram).
        Binary search finds the largest num_ctx that still fits in GPU memory.

        Supports two calibration modes:
        - Native (extended=False): Calibrates up to native context limit
        - Extended (extended=True): Calibrates up to 2x native (RoPE scaling)

        Args:
            model: Model name (e.g., "qwen3:8b")
            extended: If True, calibrate up to 2x native context (RoPE scaling)

        Yields:
            str: Progress messages (prefix "__RESULT__:" indicates final result)
        """
        import asyncio
        from ..lib.model_vram_cache import add_ollama_calibration
        from ..lib.gpu_utils import get_gpu_model_name
        from ..lib.formatting import format_number
        from ..lib.config import CALIBRATION_MIN_CONTEXT

        # Helper for locale-aware number formatting (follows UI language setting)
        def fmt(n: int) -> str:
            return format_number(n)

        # 1. Get native context limit
        native_ctx, _ = await self.get_model_context_limit(model)
        max_target = native_ctx * 2 if extended else native_ctx
        mode_label = "RoPE 2x" if extended else "Native"

        yield f"{mode_label} calibration: target {fmt(max_target)} tok"
        yield f"Native context: {fmt(native_ctx)} tok"

        # 2. Unload all models for clean VRAM state
        yield "Unloading all models..."
        await self.unload_all_models()
        await asyncio.sleep(2.0)

        # 3. First try: max target (often fits, saves binary search)
        yield f"[1] Testing {fmt(max_target)}..."
        success, _ = await self.preload_model(model, num_ctx=max_target)
        if success:
            await asyncio.sleep(1.5)
            if await self._is_fully_in_vram(model):
                yield f"✓ {fmt(max_target)} fits in VRAM"
                result = max_target
                # Skip binary search - go directly to save
                low = max_target
                high = max_target
            else:
                yield f"✗ {fmt(max_target)} too large, starting binary search..."
                low = CALIBRATION_MIN_CONTEXT
                high = max_target
                result = low
        else:
            yield f"⚠️ Preload failed, starting binary search..."
            low = CALIBRATION_MIN_CONTEXT
            high = max_target
            result = low

        # 4. Binary search (only if max target didn't fit)
        if low != high:
            granularity = 4096  # Start with 4k steps
            yield f"Binary search range: {fmt(low)} → {fmt(high)} tok"

            iteration = 1  # Already did iteration 1 with max target
            consecutive_fast_fails = 0  # Track rapid failures (system instability)
            RECOVERY_THRESHOLD = 262144  # 256k - restart threshold after crash

            while high - low > 512:  # End condition: 512 token precision
                iteration += 1
                # Adaptive granularity: narrow down as we get closer
                if high - low < 8192:
                    granularity = 512
                elif high - low < 16384:
                    granularity = 1024

                mid = ((low + high) // 2 // granularity) * granularity  # Align to granularity

                yield f"[{iteration}] Testing {fmt(mid)}..."

                # Load model with test context
                import time
                start_time = time.time()
                success, _ = await self.preload_model(model, num_ctx=mid)
                elapsed = time.time() - start_time

                if not success:
                    yield f"⚠️ Preload failed at {fmt(mid)}"
                    high = mid

                    # Detect rapid consecutive failures (< 2 sec each = system unstable)
                    if elapsed < 2.0:
                        consecutive_fast_fails += 1
                        if consecutive_fast_fails >= 3:
                            yield "⚠️ System instability detected (rapid failures)"
                            yield "🔄 Waiting for system recovery..."
                            await asyncio.sleep(5.0)

                            # Check if Ollama is still responsive
                            try:
                                await self.unload_all_models()
                                await asyncio.sleep(2.0)
                            except Exception:
                                yield "❌ Ollama unresponsive - please restart manually"
                                return

                            # Restart with lower ceiling if original was very high
                            if high > RECOVERY_THRESHOLD:
                                high = RECOVERY_THRESHOLD
                                yield f"🔄 Restarting search with ceiling {fmt(high)}"

                            consecutive_fast_fails = 0
                    else:
                        consecutive_fast_fails = 0  # Reset on slow fail (normal behavior)

                    continue

                # Success - reset fail counter
                consecutive_fast_fails = 0

                # Wait for model to stabilize
                await asyncio.sleep(1.5)

                # Check if fully in VRAM
                if await self._is_fully_in_vram(model):
                    result = mid
                    low = mid
                    yield f"✓ {fmt(mid)} fits in VRAM"
                else:
                    high = mid
                    yield f"✗ {fmt(mid)} → CPU offload"

            # Unload for next iteration
            await self.unload_all_models()
            await asyncio.sleep(1.0)

        # 4. Result (no safety buffer - Ollama handles memory management internally)
        final_ctx = result

        yield f"✅ Calibrated ({mode_label}): {fmt(final_ctx)} tok"

        # 5. Save to cache
        gpu_model = get_gpu_model_name() or "Unknown"
        add_ollama_calibration(
            model_name=model,
            max_context_gpu_only=final_ctx,
            native_context=native_ctx,
            gpu_model=gpu_model,
            extended=extended
        )

        # 6. Auto-set extended value if native calibration is VRAM-limited
        # If native calibration < native context limit, VRAM is the bottleneck
        # → RoPE 2x wouldn't help, so set extended = native calibrated value
        if not extended and final_ctx < native_ctx:
            add_ollama_calibration(
                model_name=model,
                max_context_gpu_only=final_ctx,
                native_context=native_ctx,
                gpu_model=gpu_model,
                extended=True  # Also save as extended value
            )
            yield f"ℹ️ VRAM-limited ({fmt(final_ctx)} < {fmt(native_ctx)} native)"
            yield f"   → RoPE 2x auto-set to {fmt(final_ctx)} (no benefit from scaling)"

        # Final yield with result marker
        yield f"__RESULT__:{final_ctx}"

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
