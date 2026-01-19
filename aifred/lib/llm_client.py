"""
LLM Client - Unified async interface for LLM backends

Provides async chat completions (streaming and non-streaming)
with proper integration into the existing Backend system.
"""

from typing import Dict, List, Optional, AsyncIterator, Union, Any, cast

from ..backends import BackendFactory
from ..backends.base import LLMMessage, LLMOptions, LLMResponse

# Type alias for messages: can be Dict[str, str] or LLMMessage
MessageType = Union[Dict[str, Any], LLMMessage]


class LLMClient:
    """
    Unified async LLM client

    Usage:
        # For short utility calls (non-streaming)
        client = LLMClient(backend_type="ollama")
        response = await client.chat(model, messages, options)

        # For long-form responses with streaming
        async for chunk in client.chat_stream(model, messages, options):
            if chunk["type"] == "content":
                print(chunk["text"], end="")
            elif chunk["type"] == "done":
                print(f"\\nMetrics: {chunk['metrics']}")
    """

    def __init__(
        self,
        backend_type: str = "ollama",
        base_url: Optional[str] = None,
        provider: Optional[str] = None
    ):
        """
        Initialize LLM client

        Args:
            backend_type: "ollama", "vllm", etc.
            base_url: Override default backend URL
            provider: Cloud API provider ("claude", "qwen", "kimi") - only for cloud_api
        """
        self.backend_type = backend_type
        self.base_url = base_url
        self.provider = provider
        # Cache backend instance to prevent premature GC during async operations
        self._backend = None

    def _get_backend(self):
        """Get or create backend instance (cached to prevent GC during async ops)"""
        if self._backend is None:
            self._backend = BackendFactory.create(
                self.backend_type,
                base_url=self.base_url,
                provider=self.provider
            )
        return self._backend

    async def __aenter__(self):
        """Async context manager entry - enables 'async with LLMClient() as client:' usage"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures cleanup even if exception occurs"""
        await self.close()
        return False  # Don't suppress exceptions

    async def chat(
        self,
        model: str,
        messages: List[MessageType],
        options: Optional[Union[Dict[str, Any], LLMOptions]] = None
    ) -> LLMResponse:
        """
        Async non-streaming chat completion

        Args:
            model: Model name
            messages: List of messages (dict or LLMMessage)
            options: Generation options (dict or LLMOptions)

        Returns:
            LLMResponse with complete text and metrics
        """
        backend = self._get_backend()

        # Convert dicts to LLMMessage if needed
        converted_messages: List[LLMMessage]
        if messages and isinstance(messages[0], dict):
            dict_messages = cast(List[Dict[str, Any]], messages)
            converted_messages = [LLMMessage(role=m["role"], content=m["content"]) for m in dict_messages]
        else:
            converted_messages = cast(List[LLMMessage], messages)

        # Convert dict to LLMOptions if needed, or pass through LLMOptions directly
        llm_options: LLMOptions
        if options is None:
            llm_options = LLMOptions()
        elif isinstance(options, LLMOptions):
            # Already an LLMOptions object - use directly (preserves num_ctx!)
            llm_options = options
        elif isinstance(options, dict):
            llm_options = LLMOptions(
                temperature=options.get("temperature", 0.2),
                num_ctx=options.get("num_ctx"),
                num_predict=options.get("num_predict"),
                repeat_penalty=options.get("repeat_penalty", 1.1),
                top_p=options.get("top_p", 0.9),
                top_k=options.get("top_k", 40),
                seed=options.get("seed"),
                enable_thinking=options.get("enable_thinking"),
                supports_thinking=options.get("supports_thinking")
            )
        else:
            # Unknown type - use defaults
            llm_options = LLMOptions()

        # NOTE: Backend is cached in self._backend to prevent GC during async operations
        response = await backend.chat(model, converted_messages, llm_options)
        return response


    async def chat_stream(
        self,
        model: str,
        messages: List[MessageType],
        options: Optional[Union[Dict[str, Any], LLMOptions]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Async streaming chat completion

        Args:
            model: Model name
            messages: List of messages (dict or LLMMessage)
            options: Generation options (dict or LLMOptions)

        Yields:
            Dict with either:
            - {"type": "content", "text": str} for content chunks
            - {"type": "done", "metrics": {...}} for final metrics
        """
        backend = self._get_backend()

        # Convert dicts to LLMMessage if needed
        converted_messages: List[LLMMessage]
        if messages and isinstance(messages[0], dict):
            dict_messages = cast(List[Dict[str, Any]], messages)
            converted_messages = [LLMMessage(role=m["role"], content=m["content"]) for m in dict_messages]
        else:
            converted_messages = cast(List[LLMMessage], messages)

        # Convert dict to LLMOptions if needed, or pass through LLMOptions directly
        llm_options: LLMOptions
        if options is None:
            llm_options = LLMOptions()
        elif isinstance(options, LLMOptions):
            # Already an LLMOptions object - use directly (preserves num_ctx!)
            llm_options = options
        elif isinstance(options, dict):
            llm_options = LLMOptions(
                temperature=options.get("temperature", 0.2),
                num_ctx=options.get("num_ctx"),
                num_predict=options.get("num_predict"),
                repeat_penalty=options.get("repeat_penalty", 1.1),
                top_p=options.get("top_p", 0.9),
                top_k=options.get("top_k", 40),
                seed=options.get("seed"),
                enable_thinking=options.get("enable_thinking"),
                supports_thinking=options.get("supports_thinking")
            )
        else:
            # Unknown type - use defaults
            llm_options = LLMOptions()

        # NOTE: Backend is cached in self._backend to prevent GC during async operations
        async for chunk in backend.chat_stream(model, converted_messages, llm_options):
            yield chunk

    async def get_model_context_limit(self, model: str) -> tuple[int, int]:
        """
        Get context window size and model size for a model.

        Queries the backend for model metadata and extracts the context limit
        and VRAM size. Very fast (~30ms for Ollama) and does NOT load the model.

        Args:
            model: Model name (e.g., "qwen3:8b", "phi3:mini")

        Returns:
            tuple[int, int]: (context_limit, model_size_bytes)
                - context_limit: Context limit in tokens
                - model_size_bytes: Model size in VRAM (0 if unavailable)

        Raises:
            RuntimeError: If model not found or context limit not available
        """
        backend = self._get_backend()
        return await backend.get_model_context_limit(model)

    async def preload_model(self, model: str) -> tuple[bool, float]:
        """
        Preload a model into VRAM by sending a minimal request.
        This warms up the model so future requests are faster.

        NOTE: Caller should explicitly call backend.unload_all_models() BEFORE this
        to ensure proper model loading order.

        Args:
            model: Model name to preload (e.g., 'qwen3:8b')

        Returns:
            Tuple of (success: bool, load_time: float in seconds)
        """
        backend = self._get_backend()
        # NOTE: Backend is cached in self._backend to prevent GC during async operations
        return await backend.preload_model(model)

    async def is_model_loaded(self, model: str) -> bool:
        """
        Check if a model is currently loaded in VRAM.

        Used for VRAM-based context calculation to determine if model size
        should be subtracted from free VRAM or not.

        Args:
            model: Model name/ID

        Returns:
            bool: True if model is currently loaded in VRAM, False otherwise
        """
        backend = self._get_backend()
        return await backend.is_model_loaded(model)

    async def close(self):
        """Cleanup resources (close cached backend if exists)"""
        if self._backend is not None:
            await self._backend.close()
            self._backend = None
