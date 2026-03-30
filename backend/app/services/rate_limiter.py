"""
Rate Limiting and Retry Logic for API Calls

Implements:
1. Token bucket rate limiting
2. Exponential backoff for retries
3. Proper handling of HTTP 429 (Too Many Requests)
"""

import asyncio
import time
from typing import Optional, Callable, Any
from functools import wraps
import logging

logger = logging.getLogger(__name__)


class TokenBucket:
    """Token bucket rate limiter - allows burst traffic within limits."""
    
    def __init__(self, rate: float, capacity: float):
        """
        Initialize token bucket.
        
        Args:
            rate: Tokens per second (refill rate)
            capacity: Max tokens to hold (burst capacity)
        """
        self.rate = rate  # tokens per second
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self.lock = asyncio.Lock()
    
    async def acquire(self, tokens: float = 1.0) -> None:
        """Wait until tokens are available, then consume them."""
        async with self.lock:
            while self.tokens < tokens:
                # Refill tokens
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(
                    self.capacity,
                    self.tokens + elapsed * self.rate
                )
                self.last_update = now
                
                if self.tokens < tokens:
                    # Need to wait
                    wait_time = (tokens - self.tokens) / self.rate
                    await asyncio.sleep(wait_time)
            
            # Consume tokens
            self.tokens -= tokens


class RateLimitedAPIClient:
    """Generic rate-limited API client with retry logic."""
    
    def __init__(
        self,
        name: str,
        rate: float,
        capacity: float = None,
        max_retries: int = 3,
        base_backoff: float = 1.0
    ):
        """
        Initialize rate-limited client.
        
        Args:
            name: Client name for logging
            rate: Requests per second
            capacity: Burst capacity (defaults to rate)
            max_retries: Max retries on 429
            base_backoff: Base backoff time in seconds
        """
        self.name = name
        self.rate_limiter = TokenBucket(rate, capacity or rate)
        self.max_retries = max_retries
        self.base_backoff = base_backoff
    
    async def request(
        self,
        fn: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute rate-limited request with automatic retry on 429.
        
        Args:
            fn: Async function to call (should raise httpx.HTTPStatusError on error)
            *args: Function arguments
            **kwargs: Function keyword arguments
        
        Returns:
            Function result
        
        Raises:
            Exception: If all retries exhausted
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                # Wait for token availability
                await self.rate_limiter.acquire()
                
                # Execute request
                result = await fn(*args, **kwargs)
                
                if attempt > 0:
                    logger.info(f"{self.name}: Retry succeeded on attempt {attempt + 1}")
                
                return result
                
            except Exception as e:
                last_exception = e
                error_msg = str(e)
                
                # Check if it's a 429 (Too Many Requests)
                if "429" in error_msg or "too many requests" in error_msg.lower():
                    if attempt < self.max_retries:
                        # Exponential backoff: base_backoff * 2^attempt
                        wait_time = self.base_backoff * (2 ** attempt)
                        logger.warning(
                            f"{self.name}: Rate limited (429). "
                            f"Retry {attempt + 1}/{self.max_retries} in {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(
                            f"{self.name}: Rate limited (429) - max retries exceeded"
                        )
                        raise
                
                # For other errors, don't retry
                logger.error(f"{self.name}: Request failed with {type(e).__name__}: {error_msg}")
                raise
        
        # Should not reach here, but raise last exception just in case
        if last_exception:
            raise last_exception
        raise RuntimeError(f"{self.name}: Request failed unexpectedly")


# Pre-configured clients for specific APIs
class SemanticScholarRateLimiter(RateLimitedAPIClient):
    """Rate limiter for Semantic Scholar API.
    
    Unauthenticated: 100 requests per 5 minutes = 0.33 req/sec
    Authenticated: Higher limits (typically 1-5 req/sec with API key)
    
    We use conservative settings for unauthenticated to avoid 429s
    """
    
    def __init__(self, is_authenticated: bool = False):
        if is_authenticated:
            # Conservative authenticated rate: 1 req/sec
            rate = 1.0
            capacity = 5  # Allow bursts of up to 5
        else:
            # Unauthenticated: 100/5min = 0.33 req/sec
            # Use 0.2 req/sec (5 second intervals) for safety
            rate = 0.2
            capacity = 1  # No bursting
        
        super().__init__(
            name="SemanticScholar",
            rate=rate,
            capacity=capacity,
            max_retries=3,
            base_backoff=5.0  # 429 responses include Retry-After, we use 5s baseline
        )


class ArxivRateLimiter(RateLimitedAPIClient):
    """Rate limiter for ArXiv API.
    
    Policy: Make no more than one request every three seconds
    = 0.33 requests/sec
    
    We use 0.25 req/sec for safety (4 second intervals)
    """
    
    def __init__(self):
        super().__init__(
            name="ArXiv",
            rate=0.25,  # 4 seconds per request
            capacity=1,  # No bursting
            max_retries=2,
            base_backoff=10.0  # Conservative backoff for ArXiv
        )


class PubMedRateLimiter(RateLimitedAPIClient):
    """Rate limiter for PubMed API.
    
    Policy: 3 requests per second without API key
    = 3 req/sec
    
    We use 2 req/sec for safety (500ms intervals)
    """
    
    def __init__(self, is_authenticated: bool = False):
        if is_authenticated:
            # With API key: 10 req/sec
            rate = 5.0  # Conservative estimate
            capacity = 10
        else:
            # Without API key: 3 req/sec
            rate = 2.0  # Conservative estimate
            capacity = 3
        
        super().__init__(
            name="PubMed",
            rate=rate,
            capacity=capacity,
            max_retries=2,
            base_backoff=3.0
        )


class ConcurrentRequestQueue:
    """Queue for managing concurrent requests with per-source rate limiting."""
    
    def __init__(self, max_concurrent: int = 5):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.active_requests = 0
        self.lock = asyncio.Lock()
    
    async def submit(
        self,
        fn: Callable,
        *args,
        **kwargs
    ) -> Any:
        """Submit async request with concurrency limiting."""
        async with self.semaphore:
            async with self.lock:
                self.active_requests += 1
            
            try:
                result = await fn(*args, **kwargs)
                return result
            finally:
                async with self.lock:
                    self.active_requests -= 1
