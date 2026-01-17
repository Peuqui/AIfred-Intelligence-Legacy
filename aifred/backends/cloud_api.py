"""
Cloud API Backend Adapter

Supports Claude (Anthropic), Qwen (DashScope), and Kimi (Moonshot) APIs.
All providers use OpenAI-compatible endpoints.
"""

import os
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
from ..lib.config import CLOUD_API_PROVIDERS

logger = logging.getLogger(__name__)


class CloudAPIBackend(LLMBackend):
    """Cloud API backend implementation (OpenAI-compatible)"""

    def __init__(self, base_url: str, api_key: str, provider: str = "qwen"):
        """
        Initialize Cloud API backend.

        Args:
            base_url: API endpoint URL
            api_key: API key for authentication
            provider: Provider ID ("claude", "qwen", or "kimi")
        """
        super().__init__(base_url=base_url, api_key=api_key)
        self.provider = provider
        self.provider_config = CLOUD_API_PROVIDERS.get(provider, CLOUD_API_PROVIDERS["qwen"])

        # Use provided base_url or fall back to provider default
        effective_url = base_url if base_url else self.provider_config["base_url"]

        self.client = AsyncOpenAI(
            base_url=effective_url,
            api_key=api_key,
            timeout=120.0  # Cloud APIs can be slow
        )

        logger.info(f"☁️ CloudAPIBackend initialized: {self.provider_config['name']}")

    async def list_models(self) -> List[str]:
        """
        Get list of available models from Cloud API.

        Fetches models dynamically from /models endpoint.
        """
        try:
            response = await self.client.models.list()
            # Extract model IDs from response
            self._available_models = [model.id for model in response.data]
            logger.info(f"☁️ {self.provider_config['name']}: Found {len(self._available_models)} models")
            return self._available_models
        except Exception as e:
            logger.warning(f"☁️ Failed to fetch models from {self.provider_config['name']}: {e}")
            # Return empty list on failure - don't use hardcoded fallback
            self._available_models = []
            return self._available_models

    async def chat(
        self,
        model: str,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None,
        stream: bool = False
    ) -> LLMResponse:
        """
        Non-streaming chat with Cloud API.

        Args:
            model: Model name (e.g., "qwen-plus", "moonshot-v1-32k")
            messages: List of LLMMessage
            options: Generation options
            stream: Ignored (always False for this method)

        Returns:
            LLMResponse with full text and metrics
        """
        if options is None:
            options = LLMOptions()

        # Convert LLMMessage to OpenAI format
        openai_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        # Build kwargs
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
            "temperature": options.temperature,
            "top_p": options.top_p,
            "stream": False
        }

        # Max tokens (if specified)
        if options.num_predict:
            kwargs["max_tokens"] = options.num_predict

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
                raise BackendModelNotFoundError(f"Model '{model}' not found on {self.provider_config['name']}")
            elif "api key" in error_str.lower() or "authentication" in error_str.lower() or "401" in error_str:
                raise BackendConnectionError(f"Invalid API key for {self.provider_config['name']}: {e}")
            else:
                raise BackendInferenceError(f"{self.provider_config['name']} inference failed: {e}")

    async def chat_stream(
        self,
        model: str,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None
    ) -> AsyncIterator[Dict]:
        """
        Streaming chat with Cloud API.

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
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
            "temperature": options.temperature,
            "top_p": options.top_p,
            "stream": True,
            "stream_options": {"include_usage": True}  # Request usage stats in stream
        }

        # Max tokens (if specified)
        if options.num_predict:
            kwargs["max_tokens"] = options.num_predict

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
                        total_tokens += 1  # Rough estimate until final usage

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
            elif "api key" in error_str.lower() or "authentication" in error_str.lower() or "401" in error_str:
                raise BackendConnectionError(f"Invalid API key for {self.provider_config['name']}")
            else:
                raise BackendInferenceError(f"{self.provider_config['name']} streaming failed: {e}")

    async def preload_model(self, model: str, num_ctx: Optional[int] = None) -> tuple[bool, float]:
        """
        Preload a model - No-op for Cloud APIs.

        Cloud APIs don't need preloading - models are always available.

        Args:
            model: Model name (ignored)
            num_ctx: Context size (ignored)

        Returns:
            Tuple of (True, 0.0) - always succeeds instantly
        """
        logger.debug(f"☁️ Cloud API: Skipping preload for {model} (not needed)")
        return (True, 0.0)

    async def health_check(self) -> bool:
        """
        Check if Cloud API is reachable and API key is valid.

        Uses models.list() as a lightweight check.
        """
        try:
            # Try to list models - this validates the API key
            await self.client.models.list()
            return True
        except Exception as e:
            logger.warning(f"☁️ Cloud API health check failed: {e}")
            return False

    def get_backend_name(self) -> str:
        """Return the provider display name."""
        return self.provider_config["name"]

    async def get_backend_info(self) -> Dict:
        """Get Cloud API backend information."""
        try:
            models = await self.list_models()
            healthy = await self.health_check()

            return {
                "backend": "Cloud API",
                "provider": self.provider,
                "provider_name": self.provider_config["name"],
                "base_url": self.provider_config["base_url"],
                "available_models": len(models),
                "models": models,
                "healthy": healthy,
                "api_type": "OpenAI-compatible"
            }
        except Exception as e:
            return {
                "backend": "Cloud API",
                "provider": self.provider,
                "provider_name": self.provider_config["name"],
                "base_url": self.provider_config["base_url"],
                "available_models": 0,
                "models": [],
                "healthy": False,
                "error": str(e)
            }

    async def get_model_context_limit(self, model: str) -> tuple[int, int]:
        """
        Get context limit for a Cloud API model.

        Cloud APIs don't expose context limits - return "unknown".
        Context is managed by the cloud provider, not by us.

        Args:
            model: Model name

        Returns:
            tuple[int, int]: (0, 0) - unknown for cloud APIs
        """
        # Cloud APIs manage context themselves - we don't need to track it
        return (0, 0)

    async def is_model_loaded(self, model: str) -> bool:
        """
        Check if model is loaded - Always True for Cloud APIs.

        Cloud APIs don't "load" models - they're always available.
        """
        return True

    def get_capabilities(self) -> Dict[str, bool]:
        """
        Return Cloud API backend capabilities.

        Cloud API characteristics:
        - Models are always available (no loading/unloading)
        - Context is managed by cloud provider (not our concern)
        - Supports streaming responses
        - No preloading needed
        """
        return {
            "dynamic_models": False,     # Cannot load/unload (always available)
            "dynamic_context": False,    # Context managed by cloud provider
            "supports_streaming": True,  # Supports streaming responses
            "requires_preload": False    # No preloading needed
        }

    async def calculate_practical_context(self, model: str) -> tuple[int, list[str]]:
        """
        Calculate practical context for Cloud API model.

        For Cloud APIs, context is managed by the provider - we don't
        need to calculate or limit it.

        Args:
            model: Model name

        Returns:
            tuple[int, list[str]]: (0, debug_messages) - 0 means "unlimited/unknown"
        """
        debug_msgs = [
            f"☁️ {self.provider_config['name']}: {model}",
            "📊 Context: managed by cloud provider"
        ]

        return (0, debug_msgs)

    async def close(self):
        """Close HTTP client."""
        await self.client.close()


def get_cloud_api_key(provider: str) -> Optional[str]:
    """
    Get API key for a cloud provider from environment variables.

    Args:
        provider: Provider ID ("claude", "qwen", or "kimi")

    Returns:
        API key string or None if not configured
    """
    if provider not in CLOUD_API_PROVIDERS:
        return None

    env_key = CLOUD_API_PROVIDERS[provider]["env_key"]
    return os.environ.get(env_key)


def is_cloud_api_configured(provider: str) -> bool:
    """
    Check if a cloud provider's API key is configured.

    Args:
        provider: Provider ID ("claude", "qwen", or "kimi")

    Returns:
        True if API key is set in environment
    """
    return get_cloud_api_key(provider) is not None
