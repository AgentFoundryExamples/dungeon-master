# Copyright 2025 John Brosnihan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Resilience utilities for retry and backoff logic.

This module provides reusable retry decorators and utilities for handling
transient failures in external service calls (LLM, journey-log).

Key Features:
- Exponential backoff with configurable base and max delays
- Selective retry based on exception type
- Retry attempt tracking and logging
- Thread-safe operation counting for concurrency control
"""

import asyncio
import time
from typing import Callable, TypeVar, ParamSpec, Optional, Type
from functools import wraps
from app.logging import StructuredLogger

logger = StructuredLogger(__name__)

T = TypeVar('T')
P = ParamSpec('P')


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        retryable_exceptions: Optional[tuple[Type[Exception], ...]] = None
    ):
        """Initialize retry configuration.
        
        Args:
            max_retries: Maximum number of retry attempts (0 disables retries)
            base_delay: Base delay in seconds for exponential backoff
            max_delay: Maximum delay in seconds (caps exponential growth)
            retryable_exceptions: Tuple of exception types that should trigger retries.
                                 If None, all exceptions are retryable.
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.retryable_exceptions = retryable_exceptions or (Exception,)
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate retry delay using exponential backoff.
        
        Args:
            attempt: Current attempt number (1-indexed)
            
        Returns:
            Delay in seconds, capped at max_delay
        """
        # Exponential: base_delay * 2^(attempt-1)
        delay = self.base_delay * (2 ** (attempt - 1))
        return min(delay, self.max_delay)
    
    def is_retryable(self, exception: Exception) -> bool:
        """Check if an exception should trigger a retry.
        
        Args:
            exception: The exception to check
            
        Returns:
            True if the exception is retryable, False otherwise
        """
        return isinstance(exception, self.retryable_exceptions)


def with_retry(config: RetryConfig, operation_name: str):
    """Decorator to add retry logic to async functions.
    
    This decorator implements exponential backoff retry for transient failures.
    It logs each retry attempt and tracks metrics for observability.
    
    Args:
        config: RetryConfig specifying retry behavior
        operation_name: Human-readable name for the operation (for logging)
        
    Returns:
        Decorator function
        
    Example:
        >>> retry_config = RetryConfig(max_retries=3, base_delay=1.0)
        >>> @with_retry(retry_config, "fetch_data")
        >>> async def fetch_data():
        ...     # Your async function here
        ...     pass
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception = None
            
            for attempt in range(config.max_retries + 1):
                try:
                    # Attempt the operation
                    return await func(*args, **kwargs)
                    
                except Exception as e:
                    last_exception = e
                    
                    # Check if this exception is retryable
                    if not config.is_retryable(e):
                        logger.warning(
                            f"{operation_name} failed with non-retryable exception",
                            error_type=type(e).__name__,
                            error=str(e),
                            attempt=attempt + 1
                        )
                        raise
                    
                    # Check if we've exhausted retries
                    if attempt >= config.max_retries:
                        logger.error(
                            f"{operation_name} failed after {config.max_retries} retries",
                            error_type=type(e).__name__,
                            error=str(e),
                            total_attempts=attempt + 1
                        )
                        raise
                    
                    # Calculate delay and retry
                    delay = config.calculate_delay(attempt + 1)
                    logger.warning(
                        f"{operation_name} failed, retrying in {delay:.2f}s",
                        error_type=type(e).__name__,
                        error=str(e),
                        attempt=attempt + 1,
                        max_retries=config.max_retries,
                        retry_delay_seconds=delay
                    )
                    
                    await asyncio.sleep(delay)
            
            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError(f"{operation_name} failed with unknown error")
        
        return wrapper
    return decorator


class Semaphore:
    """Thread-safe semaphore for limiting concurrent operations.
    
    This class provides a context manager for enforcing concurrency limits.
    It tracks the current number of active operations and blocks new operations
    when the limit is reached.
    """
    
    def __init__(self, max_concurrent: int):
        """Initialize semaphore.
        
        Args:
            max_concurrent: Maximum number of concurrent operations allowed
        """
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_count = 0
    
    async def __aenter__(self):
        """Acquire semaphore (async context manager)."""
        await self._semaphore.acquire()
        self._active_count += 1
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Release semaphore (async context manager)."""
        self._active_count -= 1
        self._semaphore.release()
    
    @property
    def active_count(self) -> int:
        """Get current number of active operations."""
        return self._active_count


class RateLimiter:
    """Simple token bucket rate limiter for per-character throttling.
    
    This class implements a token bucket algorithm to limit the rate of operations
    per character. Each character has its own bucket that refills at a configured rate.
    """
    
    def __init__(self, max_rate: float):
        """Initialize rate limiter.
        
        Args:
            max_rate: Maximum operations per second per key
        """
        self.max_rate = max_rate
        self.buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_update)
    
    async def acquire(self, key: str) -> bool:
        """Try to acquire a token for the given key.
        
        Args:
            key: Unique identifier (e.g., character_id)
            
        Returns:
            True if token acquired, False if rate limit exceeded
        """
        now = time.time()
        
        if key not in self.buckets:
            # Initialize bucket and consume one token
            # Start with (max_rate - 1) tokens after consuming one
            self.buckets[key] = (self.max_rate - 1.0, now)
            return True
        
        tokens, last_update = self.buckets[key]
        
        # Refill tokens based on time elapsed
        elapsed = now - last_update
        tokens = min(self.max_rate, tokens + (elapsed * self.max_rate))
        
        # Try to consume a token
        if tokens >= 1.0:
            self.buckets[key] = (tokens - 1.0, now)
            return True
        else:
            # Update timestamp but don't consume
            self.buckets[key] = (tokens, now)
            return False
    
    def get_retry_after(self, key: str) -> float:
        """Calculate seconds until next token is available.
        
        Args:
            key: Unique identifier
            
        Returns:
            Seconds until next token available (minimum 0.1)
        """
        if key not in self.buckets:
            return 0.0
        
        tokens, last_update = self.buckets[key]
        now = time.time()
        elapsed = now - last_update
        
        # Calculate how many tokens we have now
        current_tokens = min(self.max_rate, tokens + (elapsed * self.max_rate))
        
        if current_tokens >= 1.0:
            return 0.0
        
        # Calculate time needed to reach 1.0 tokens
        needed_tokens = 1.0 - current_tokens
        seconds_needed = needed_tokens / self.max_rate
        
        return max(0.1, seconds_needed)
