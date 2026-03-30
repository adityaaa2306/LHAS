"""
NVIDIA NIM Client Module

OpenAI SDK client for NVIDIA's NIM API (OpenAI-compatible endpoints).
Provides a clean interface for communicating with NIM language models using OpenAI client.
"""

import logging
from typing import Optional, Any
from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)


class NIMClient:
    """
    OpenAI-compatible client for NVIDIA NIM API.
    
    Uses the OpenAI Python SDK to communicate with NVIDIA NIM's endpoints.
    NVIDIA NIM API is OpenAI API compatible.
    """

    def __init__(self):
        """Initialize NIM client with environment configuration."""
        api_key = settings.NVIDIA_API_KEY
        
        # In production, API key is required
        if settings.is_production and (not api_key or api_key == "your_nvidia_api_key_here"):
            raise ValueError(
                "NVIDIA_API_KEY must be set in production environment. "
                "Get it from: https://build.nvidia.com/"
            )
        
        # In development, use placeholder if not set
        if not api_key or api_key == "your_nvidia_api_key_here":
            logger.warning(
                "NVIDIA_API_KEY not configured. "
                "API calls will fail unless a valid key is provided. "
                "Get one from: https://build.nvidia.com/"
            )
            api_key = "placeholder-key"  # Allow initialization but calls will fail

        self.api_key = api_key
        self.base_url = settings.NVIDIA_BASE_URL.rstrip('/')
        self.model = settings.NVIDIA_MODEL
        self.temperature = settings.NVIDIA_TEMPERATURE
        self.top_p = settings.NVIDIA_TOP_P
        self.max_tokens = settings.NVIDIA_MAX_TOKENS
        
        # Initialize OpenAI client with NVIDIA NIM endpoint
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key
        )

        logger.info(f"NIM Client initialized with model: {self.model}, base_url: {self.base_url}")

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
    ) -> dict[str, Any]:
        """
        Send a chat completion request to NVIDIA NIM using OpenAI SDK.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            temperature: Override default temperature (0.0 - 2.0)
            max_tokens: Override default max tokens
            top_p: Override default top_p (0.0 - 1.0)

        Returns:
            Dict with 'content' and 'reasoning' (if available)
        """
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                top_p=top_p or self.top_p,
            )
            
            choice = completion.choices[0]
            content = choice.message.content or ""
            
            result = {
                "content": content,
                "reasoning": None,
                "model": completion.model,
                "usage": {
                    "prompt_tokens": completion.usage.prompt_tokens,
                    "completion_tokens": completion.usage.completion_tokens,
                    "total_tokens": completion.usage.total_tokens,
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"NIM API error: {str(e)}")
            raise

    async def chat_async(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
    ) -> dict[str, Any]:
        """
        Async version of chat().
        
        Args:
            messages: Chat messages
            temperature: Optional temperature override
            max_tokens: Optional max tokens override
            top_p: Optional top_p override

        Returns:
            Response dict with content and metadata
        """
        # For now, call the sync method
        # Can be upgraded to true async with aiohttp if needed
        return self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p
        )
