"""
Abstract Base Class for LLM Backends

Supports: Ollama, vLLM, llama.cpp, OpenAI, etc.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, AsyncIterator, Union, Any
from dataclasses import dataclass

from aifred.lib.config import DEFAULT_OLLAMA_URL


@dataclass
class LLMMessage:
    """
    Standard message format (OpenAI-style)

    Supports both text-only and multimodal (text + images) content.

    Examples:
        # Text-only message
        LLMMessage(role="user", content="Hello")

        # Multimodal message with images
        LLMMessage(role="user", content=[
            {"type": "text", "text": "What's in this image?"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
        ])
    """
    role: str  # "system", "user", "assistant"
    content: Union[str, List[Dict[str, Any]]]  # String for text-only, list for multimodal


@dataclass
class LLMOptions:
    """LLM generation options"""
    temperature: float = 0.2
    num_ctx: Optional[int] = None  # Context window
    num_predict: Optional[int] = None  # Max tokens to generate
    repeat_penalty: float = 1.1
    top_p: float = 0.9
    top_k: int = 40
    min_p: float = 0.0  # Min-P sampling (0 = disabled, typical: 0.05)
    seed: Optional[int] = None
    enable_thinking: Optional[bool] = None  # User preference: enable thinking if model supports it
    supports_thinking: Optional[bool] = None  # Model capability: None=unknown, True=supports, False=not supported


@dataclass
class LLMResponse:
    """Unified response format"""
    text: str
    tokens_prompt: int = 0
    tokens_generated: int = 0
    tokens_per_second: float = 0.0
    inference_time: float = 0.0
    model: str = ""


class LLMBackend(ABC):
    """
    Abstract base class for all LLM backends

    Implementations: OllamaBackend, vLLMBackend, LlamaCppBackend, OpenAIBackend
    """

    def __init__(self, base_url: str = DEFAULT_OLLAMA_URL, api_key: Optional[str] = None):
        self.base_url = base_url
        self.api_key = api_key
        self._available_models: List[str] = []

    @abstractmethod
    async def list_models(self) -> List[str]:
        """Get list of available models"""
        pass

    @abstractmethod
    async def chat(
        self,
        model: str,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None,
        stream: bool = False
    ) -> LLMResponse:
        """
        Non-streaming chat completion

        Args:
            model: Model name/ID
            messages: List of messages (OpenAI format)
            options: Generation options
            stream: Whether to stream (for this method, always False)

        Returns:
            LLMResponse with full text
        """
        pass

    @abstractmethod
    def chat_stream(
        self,
        model: str,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None
    ) -> AsyncIterator[Dict]:
        """
        Streaming chat completion (async generator)

        Args:
            model: Model name/ID
            messages: List of messages
            options: Generation options

        Yields:
            Dict with either:
            - {"type": "content", "text": str} for content chunks
            - {"type": "done", "metrics": {...}} for final metrics

        Note:
            This returns an AsyncIterator, so implementations should use
            'async def' with 'yield' (async generator function).
            The abstract method signature does NOT use 'async def' because
            it declares the return type AsyncIterator directly.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if backend is reachable and healthy"""
        pass

    @abstractmethod
    def get_backend_name(self) -> str:
        """Return backend name (e.g., 'Ollama', 'vLLM', 'llama.cpp')"""
        pass

    @abstractmethod
    async def get_backend_info(self) -> Dict:
        """
        Return backend information (async method)

        Returns:
            Dict with: version, gpu_available, memory_info, etc.

        Note:
            This is an async method because it may need to query
            the backend API for version/model information.
        """
        pass

    @abstractmethod
    async def get_model_context_limit(self, model: str) -> tuple[int, int]:
        """
        Get the context window size and model size for a specific model.

        This method queries the backend for model metadata and extracts
        the maximum context length and VRAM size. Implementation is backend-specific:
        - Ollama: Use /api/show + /api/ps endpoints
        - vLLM: Use /v1/models endpoint (size estimation)
        - TabbyAPI: Use /v1/models endpoint (size unavailable)

        Args:
            model: Model name/ID

        Returns:
            tuple[int, int]: (context_limit, model_size_bytes)
                - context_limit: Context limit in tokens (e.g., 4096, 8192, 40960)
                - model_size_bytes: Model size in VRAM (0 if unavailable)

        Raises:
            RuntimeError: If model not found or context limit cannot be determined
        """
        pass

    @abstractmethod
    async def is_model_loaded(self, model: str) -> bool:
        """
        Check if a model is currently loaded in VRAM.

        Used for VRAM-based context calculation to determine if model size
        should be subtracted from free VRAM or not.

        Implementation is backend-specific:
        - Ollama: Query /api/ps endpoint for loaded models
        - vLLM: Model is always loaded (server started with specific model)
        - TabbyAPI: Model is always loaded (server started with specific model)

        Args:
            model: Model name/ID

        Returns:
            bool: True if model is currently loaded in VRAM, False otherwise
        """
        pass

    @abstractmethod
    async def preload_model(self, model: str, num_ctx: Optional[int] = None) -> tuple[bool, float]:
        """
        Preload a model into VRAM by sending a minimal request.
        This warms up the model so future requests are faster.

        IMPORTANT for Ollama Multi-GPU:
        num_ctx MUST be passed during preload so Ollama loads the model
        with the correct KV-Cache and distributes across multiple GPUs if needed.

        Correct order:
        1. calculate_practical_context() or calculate_dynamic_num_ctx() → num_ctx
        2. preload_model(model, num_ctx=num_ctx) → Load model with KV-Cache

        Args:
            model: Model name to preload
            num_ctx: Optional context size for KV-cache allocation (Ollama-specific)

        Returns:
            Tuple of (success: bool, load_time: float in seconds)
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> Dict[str, bool]:
        """
        Return backend capabilities and behavior flags.

        This method defines backend-specific behavior to eliminate
        scattered 'if backend_type ==' conditionals throughout the codebase.

        Returns:
            Dict with capability flags:
                - "dynamic_models": Can load/unload models at runtime
                - "dynamic_context": Context can be recalculated at runtime
                - "supports_streaming": Supports streaming responses
                - "requires_preload": Needs model preloading before use

        Examples:
            Ollama:   {"dynamic_models": True, "dynamic_context": True, ...}
            vLLM:     {"dynamic_models": False, "dynamic_context": False, ...}
            TabbyAPI: {"dynamic_models": False, "dynamic_context": False, ...}
        """
        pass

    @abstractmethod
    async def calculate_practical_context(self, model: str) -> tuple[int, list[str]]:
        """
        Calculate maximum practical context window for a model.

        This method MUST be backend-specific because different backends handle
        context calculation differently:

        - **Ollama**: Dynamic calculation based on current VRAM availability
                     (can change based on loaded models)
        - **vLLM**: FIXED at server startup, cannot be recalculated
                    (returns cached value from startup)
        - **TabbyAPI**: FIXED at server startup, cannot be recalculated
                       (returns cached value from startup)

        Args:
            model: Model name/ID

        Returns:
            tuple[int, list[str]]: (context_limit, debug_messages)
                - context_limit: Maximum practical context in tokens
                - debug_messages: List of debug messages for UI console (via yield)

        Raises:
            RuntimeError: If context calculation fails

        Examples:
            Ollama:   Queries current VRAM, calculates fresh value
            vLLM:     Returns self._startup_context (set in start_with_model)
            TabbyAPI: Returns self._startup_context (set at server start)
        """
        pass

    def set_startup_context(self, context: int, debug_messages: List[str]) -> None:
        """
        Cache startup context for backends with fixed context (vLLM, TabbyAPI).

        Called after server startup to cache the calculated context limit.
        This value is returned by calculate_practical_context() for fixed-context backends.

        Args:
            context: The calculated context limit in tokens
            debug_messages: Debug messages from startup (for UI display)

        Note:
            Default implementation does nothing. Override in fixed-context backends.
        """
        pass  # Default: no-op for dynamic backends like Ollama

    async def close(self) -> None:
        """
        Close any open connections or resources.

        Called when switching backends or shutting down.
        Default implementation does nothing.
        """
        pass  # Default: no-op


class BackendError(Exception):
    """Base exception for backend errors"""
    pass


class BackendConnectionError(BackendError):
    """Backend not reachable"""
    pass


class BackendModelNotFoundError(BackendError):
    """Requested model not available"""
    pass


class BackendInferenceError(BackendError):
    """Error during inference"""
    pass
