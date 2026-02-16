"""
llama.cpp Backend Adapter (via llama-swap)

llama-swap is an OpenAI-compatible proxy that manages llama-server instances.
It handles model loading/unloading, GPU allocation, and hot-swapping.

See docs/llamacpp-setup.md for hardware configuration and performance tuning.
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


class LlamaCppBackend(LLMBackend):
    """llama.cpp backend via llama-swap (OpenAI-compatible)"""

    def __init__(self, base_url: str = "http://localhost:8080/v1", api_key: str = "dummy"):
        super().__init__(base_url=base_url, api_key=api_key)
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=120.0  # llama-swap may need to start a llama-server instance
        )

    async def list_models(self) -> List[str]:
        """Get list of available models from llama-swap"""
        try:
            models_response = await self.client.models.list()
            self._available_models = [model.id for model in models_response.data]
            return self._available_models
        except Exception as e:
            raise BackendConnectionError(f"Failed to list llama.cpp models: {e}")

    async def chat(
        self,
        model: str,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None,
        stream: bool = False
    ) -> LLMResponse:
        """Non-streaming chat with llama.cpp via llama-swap"""
        if options is None:
            options = LLMOptions()

        openai_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
            "temperature": options.temperature,
            "top_p": options.top_p,
            "stream": False
        }

        if options.num_predict:
            kwargs["max_tokens"] = options.num_predict

        # llama-server supports repetition_penalty and top_k via extra_body
        extra_body: Dict[str, Any] = {}
        if options.repeat_penalty and options.repeat_penalty != 1.0:
            extra_body["repetition_penalty"] = options.repeat_penalty
        if options.top_k and options.top_k != 40:
            extra_body["top_k"] = options.top_k
        if extra_body:
            kwargs["extra_body"] = extra_body

        try:
            timer = Timer()
            response = await self.client.chat.completions.create(**kwargs)
            inference_time = timer.elapsed()

            choice = response.choices[0]
            content = choice.message.content or ""

            # llama-server puts thinking in reasoning_content (OpenAI format)
            # Convert to <think> tags for unified handling across all backends
            msg_dict = choice.message.model_dump() if hasattr(choice.message, 'model_dump') else {}
            reasoning = msg_dict.get("reasoning_content") or ""

            if reasoning:
                text = f"<think>{reasoning}</think>\n\n{content}"
            else:
                text = content

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
                raise BackendModelNotFoundError(f"Model '{model}' not found in llama-swap")
            else:
                raise BackendInferenceError(f"llama.cpp inference failed: {e}")

    async def chat_stream(
        self,
        model: str,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None
    ) -> AsyncIterator[Dict]:
        """Streaming chat with llama.cpp via llama-swap"""
        if options is None:
            options = LLMOptions()

        openai_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
            "temperature": options.temperature,
            "top_p": options.top_p,
            "stream": True,
            "stream_options": {"include_usage": True}
        }

        if options.num_predict:
            kwargs["max_tokens"] = options.num_predict

        extra_body: Dict[str, Any] = {}
        if options.repeat_penalty and options.repeat_penalty != 1.0:
            extra_body["repetition_penalty"] = options.repeat_penalty
        if options.top_k and options.top_k != 40:
            extra_body["top_k"] = options.top_k
        if extra_body:
            kwargs["extra_body"] = extra_body

        try:
            timer = Timer()
            stream = await self.client.chat.completions.create(**kwargs)

            total_tokens = 0
            prompt_tokens = 0
            thinking_started = False

            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta

                    # llama-server puts thinking in reasoning_content (OpenAI format)
                    # Convert to <think> tags for unified handling (same as Ollama)
                    delta_dict = delta.model_dump() if hasattr(delta, 'model_dump') else {}
                    reasoning = delta_dict.get("reasoning_content") or ""

                    if reasoning:
                        if not thinking_started:
                            yield {"type": "content", "text": "<think>"}
                            thinking_started = True
                        yield {"type": "content", "text": reasoning}
                        total_tokens += 1

                    if delta.content:
                        if thinking_started:
                            yield {"type": "content", "text": "</think>\n\n"}
                            thinking_started = False
                        yield {"type": "content", "text": delta.content}
                        total_tokens += 1

                if hasattr(chunk, 'usage') and chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens
                    total_tokens = completion_tokens

            # Close think tag if stream ends during thinking (edge case)
            if thinking_started:
                yield {"type": "content", "text": "</think>\n\n"}

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
                raise BackendInferenceError(f"llama.cpp streaming failed: {e}")

    async def preload_model(self, model: str, num_ctx: Optional[int] = None) -> tuple[bool, float]:
        """
        Trigger llama-swap to load a model by sending a minimal completion request.

        llama-swap starts the model's llama-server on first request. By sending a
        minimal request during idle time (e.g. parallel to web scraping), we hide
        the cold-start latency from the user.

        num_ctx is ignored - llama-swap uses the -c value from its YAML config.
        """
        import time
        start = time.time()
        try:
            await self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            load_time = time.time() - start
            logger.info(f"llama.cpp: Preloaded {model} via llama-swap ({load_time:.1f}s)")
            return (True, load_time)
        except Exception as e:
            load_time = time.time() - start
            logger.warning(f"llama.cpp: Preload failed for {model}: {e}")
            return (False, load_time)

    async def health_check(self) -> bool:
        """Check if llama-swap is reachable"""
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False

    def get_backend_name(self) -> str:
        return "llama.cpp"

    async def get_backend_info(self) -> Dict:
        """Get llama.cpp/llama-swap backend information"""
        try:
            models = await self.list_models()
            return {
                "backend": "llama.cpp",
                "proxy": "llama-swap",
                "base_url": self.base_url,
                "available_models": len(models),
                "models": models,
                "healthy": True,
                "api_type": "OpenAI-compatible"
            }
        except Exception as e:
            return {
                "backend": "llama.cpp",
                "proxy": "llama-swap",
                "base_url": self.base_url,
                "available_models": 0,
                "models": [],
                "healthy": False,
                "error": str(e)
            }

    async def get_model_context_limit(self, model: str) -> tuple[int, int]:
        """
        Get context limit for a llama.cpp model.

        Tries in order:
        1. llama-server API (/v1/models max_model_len) - if server exposes it
        2. GGUF native context from file metadata - reliable fallback
        """
        # 1. Try API first (llama-server may expose max_model_len)
        try:
            models_response = await self.client.models.list()
            for model_obj in models_response.data:
                if model_obj.id == model:
                    model_dict = model_obj.model_dump() if hasattr(model_obj, 'model_dump') else {}
                    context_limit = model_dict.get("max_model_len", 0)
                    if context_limit:
                        return (int(context_limit), 0)
        except Exception:
            pass

        # 2. Read native context from GGUF metadata
        try:
            from ..lib.llamacpp_calibration import parse_llamaswap_config
            from ..lib.config import LLAMASWAP_CONFIG_PATH
            from ..lib.gguf_utils import get_gguf_native_context
            from pathlib import Path

            config = parse_llamaswap_config(LLAMASWAP_CONFIG_PATH)
            if model in config:
                gguf_path = Path(config[model]["gguf_path"])
                if gguf_path.exists():
                    native_ctx = get_gguf_native_context(gguf_path)
                    if native_ctx:
                        return (native_ctx, 0)
        except Exception as e:
            logger.debug(f"llama.cpp: GGUF metadata lookup failed for '{model}': {e}")

        return (0, 0)

    async def is_model_loaded(self, model: str) -> bool:
        """
        Check if model is loaded. With llama-swap, models auto-load on request.
        We check /v1/models availability as a proxy.
        """
        try:
            models = await self.list_models()
            return model in models
        except Exception:
            return False

    def get_capabilities(self) -> Dict[str, bool]:
        """
        llama.cpp/llama-swap capabilities.

        dynamic_models: True - llama-swap can load/unload models
        dynamic_context: True - calibration updates the -c value
        """
        return {
            "dynamic_models": True,
            "dynamic_context": True,
            "supports_streaming": True,
            "requires_preload": False
        }

    async def calculate_practical_context(self, model: str) -> tuple[int, list[str]]:
        """
        Get practical context for a llama.cpp model.

        Priority:
        1. Calibrated value from VRAM cache (most accurate)
        2. /v1/models response from llama-server
        3. Configured -c value from llama-swap YAML
        """
        from ..lib.model_vram_cache import get_llamacpp_calibration

        # Priority 1: Cached calibration
        calibrated = get_llamacpp_calibration(model)
        if calibrated:
            return (calibrated, [f"llama.cpp: Calibrated = {calibrated:,} tokens"])

        # Priority 2: Query running llama-server
        try:
            context_limit, _ = await self.get_model_context_limit(model)
            if context_limit > 0:
                return (context_limit, [f"llama.cpp: Server reports {context_limit:,} tokens"])
        except Exception:
            pass

        # Priority 3: llama-swap YAML config
        from ..lib.llamacpp_calibration import parse_llamaswap_config
        from ..lib.config import LLAMASWAP_CONFIG_PATH

        config = parse_llamaswap_config(LLAMASWAP_CONFIG_PATH)
        if model in config and config[model]["current_context"] > 0:
            ctx = config[model]["current_context"]
            return (ctx, [f"llama.cpp: Config -c = {ctx:,} tokens (not calibrated)"])

        return (0, ["llama.cpp: Context limit not available"])

    async def calibrate_max_context_generator(
        self,
        model: str,
    ) -> AsyncIterator[str]:
        """
        Calibrate maximum context for a llama.cpp model via binary search.

        Delegates to the llamacpp_calibration module. Yields progress messages.
        Final yield: "__RESULT__:{context}" or "__RESULT__:0:error"
        """
        from pathlib import Path
        from ..lib.llamacpp_calibration import (
            parse_llamaswap_config,
            calibrate_llamacpp_model,
        )
        from ..lib.config import LLAMASWAP_CONFIG_PATH

        config = parse_llamaswap_config(LLAMASWAP_CONFIG_PATH)
        if model not in config:
            yield f"Model '{model}' not found in llama-swap config: {LLAMASWAP_CONFIG_PATH}"
            yield "__RESULT__:0:error"
            return

        model_info = config[model]
        gguf_path = Path(model_info["gguf_path"])

        if not gguf_path.exists():
            yield f"GGUF file not found: {gguf_path}"
            yield "__RESULT__:0:error"
            return

        async for msg in calibrate_llamacpp_model(
            model_id=model,
            gguf_path=gguf_path,
            llama_server_bin=Path(model_info["llama_server_bin"]),
            ngl=model_info["ngl"],
        ):
            yield msg

    async def test_thinking_capability(self, model: str) -> bool:
        """
        Test if a model supports thinking mode.

        llama-server uses OpenAI-compatible format where thinking goes into
        a separate `reasoning_content` field (not <think> tags in content).
        We check both formats to be safe.
        """
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "What is 2+3? Think step by step."}],
                temperature=0.6,
                max_tokens=200,
                stream=False,
            )
            choice = response.choices[0]
            text = choice.message.content or ""

            # llama-server puts thinking in reasoning_content (OpenAI format)
            msg_dict = choice.message.model_dump() if hasattr(choice.message, 'model_dump') else {}
            reasoning = msg_dict.get("reasoning_content") or ""

            return bool(reasoning) or "<think>" in text
        except Exception as e:
            logger.warning(f"Thinking capability test failed for {model}: {e}")
            return False

    async def close(self):
        """Close HTTP client"""
        await self.client.close()
