"""
LLM Provider Adapter Layer

Abstracts away specific LLM implementations to allow for easy swapping
between providers (NIM, OpenAI, Gemini, etc.).

This follows the adapter pattern for clean, maintainable code.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional
from app.services.llm.nim_client import NIMClient

logger = logging.getLogger(__name__)


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Generate response from LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Provider-specific arguments

        Returns:
            Dict with 'content', 'reasoning', and metadata
        """
        pass

    @abstractmethod
    async def generate_async(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Async version of generate."""
        pass


class NIMProvider(BaseLLMProvider):
    """
    NVIDIA NIM LLM Provider.

    Uses the NIMClient to interact with NVIDIA's language models.
    """

    def __init__(self):
        """Initialize with NIM client."""
        self.client = NIMClient()
        logger.info("Initialized NIMProvider")

    def generate(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Generate response using NVIDIA NIM.

        Args:
            messages: Chat messages
            temperature: Optional temperature override
            max_tokens: Optional max tokens override
            top_p: Optional top_p override
            **kwargs: Additional arguments (ignored)

        Returns:
            Response dict with content and reasoning
        """
        return self.client.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
        )

    async def generate_async(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Async version using NVIDIA NIM.

        Args:
            messages: Chat messages
            temperature: Optional temperature override
            max_tokens: Optional max tokens override
            top_p: Optional top_p override
            **kwargs: Additional arguments (ignored)

        Returns:
            Response dict with content and reasoning
        """
        return await self.client.chat_async(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
        )


class LLMProvider:
    """
    Factory and facade for LLM providers.

    Provides a single interface to different LLM backends.
    Easily extensible for new providers.
    """

    def __init__(self, provider: str = "nim"):
        """
        Initialize LLM provider.

        Args:
            provider: Provider name ('nim', 'openai', 'gemini', etc.)

        Raises:
            ValueError: If provider is not supported
        """
        if provider.lower() == "nim":
            self._provider = NIMProvider()
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

        self.provider_name = provider.lower()
        logger.info(f"LLMProvider initialized with: {self.provider_name}")

    def generate(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Generate response from configured provider.

        Args:
            messages: Chat messages
            **kwargs: Provider-specific arguments

        Returns:
            Response dict with content and metadata
        """
        return self._provider.generate(messages, **kwargs)

    async def generate_async(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Async version of generate.

        Args:
            messages: Chat messages
            **kwargs: Provider-specific arguments

        Returns:
            Response dict with content and metadata
        """
        return await self._provider.generate_async(messages, **kwargs)


# Singleton instance
_llm_provider: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    """
    Get or create LLM provider singleton.

    Returns:
        LLMProvider instance
    """
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = LLMProvider(provider="nim")
    return _llm_provider
