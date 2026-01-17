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
"""Tests for resilience utilities (retry, rate limiting, semaphore)."""

import pytest
import asyncio
from app.resilience import RetryConfig, RateLimiter, Semaphore


class TestRetryConfig:
    """Tests for RetryConfig."""
    
    def test_calculate_delay_exponential_backoff(self):
        """Test that delay calculation follows exponential backoff."""
        config = RetryConfig(max_retries=3, base_delay=1.0, max_delay=30.0)
        
        # Attempt 1: base_delay * 2^0 = 1.0
        assert config.calculate_delay(1) == 1.0
        
        # Attempt 2: base_delay * 2^1 = 2.0
        assert config.calculate_delay(2) == 2.0
        
        # Attempt 3: base_delay * 2^2 = 4.0
        assert config.calculate_delay(3) == 4.0
    
    def test_calculate_delay_capped_at_max(self):
        """Test that delay is capped at max_delay."""
        config = RetryConfig(max_retries=10, base_delay=1.0, max_delay=5.0)
        
        # Attempt 10: base_delay * 2^9 = 512.0, but capped at 5.0
        assert config.calculate_delay(10) == 5.0
    
    def test_is_retryable_default(self):
        """Test that all exceptions are retryable by default."""
        config = RetryConfig()
        
        assert config.is_retryable(Exception("test"))
        assert config.is_retryable(ValueError("test"))
        assert config.is_retryable(RuntimeError("test"))
    
    def test_is_retryable_specific_exceptions(self):
        """Test that only specific exceptions are retryable."""
        config = RetryConfig(retryable_exceptions=(ValueError, RuntimeError))
        
        assert config.is_retryable(ValueError("test"))
        assert config.is_retryable(RuntimeError("test"))
        assert not config.is_retryable(KeyError("test"))


class TestRateLimiter:
    """Tests for RateLimiter."""
    
    @pytest.mark.asyncio
    async def test_rate_limiter_allows_initial_requests(self):
        """Test that rate limiter allows initial requests."""
        limiter = RateLimiter(max_rate=2.0)  # 2 requests per second
        
        # First request should succeed
        assert await limiter.acquire("user1") is True
    
    @pytest.mark.asyncio
    async def test_rate_limiter_enforces_limit(self):
        """Test that rate limiter enforces rate limit."""
        limiter = RateLimiter(max_rate=1.0)  # 1 request per second
        
        # First request succeeds
        assert await limiter.acquire("user1") is True
        
        # Second request immediately fails (bucket empty)
        assert await limiter.acquire("user1") is False
        
        # Wait for token to refill and retry
        await asyncio.sleep(1.1)
        assert await limiter.acquire("user1") is True
    
    @pytest.mark.asyncio
    async def test_rate_limiter_per_key_isolation(self):
        """Test that rate limiter isolates limits per key."""
        limiter = RateLimiter(max_rate=1.0)
        
        # First request for user1 succeeds
        assert await limiter.acquire("user1") is True
        
        # First request for user2 also succeeds (different bucket)
        assert await limiter.acquire("user2") is True
        
        # Second request for user1 fails (bucket empty)
        assert await limiter.acquire("user1") is False
    
    @pytest.mark.asyncio
    async def test_get_retry_after(self):
        """Test that get_retry_after calculates correct wait time."""
        limiter = RateLimiter(max_rate=1.0)
        
        # Consume token
        await limiter.acquire("user1")
        
        # Check retry_after
        retry_after = limiter.get_retry_after("user1")
        
        # Should be close to 1.0 second (with small tolerance for timing)
        assert 0.9 <= retry_after <= 1.1
    
    @pytest.mark.asyncio
    async def test_rate_limiter_preserves_timestamp_on_reject(self):
        """Test that rate limiter preserves timestamp when rejecting requests.
        
        This verifies the fix for the bug where failed acquire() calls
        would update the timestamp to 'now', preventing proper token refill.
        """
        limiter = RateLimiter(max_rate=1.0)
        
        # First request succeeds
        assert await limiter.acquire("user1") is True
        
        # Get the timestamp after first acquire
        _, first_timestamp = limiter.buckets["user1"]
        
        # Immediately try again (should fail)
        assert await limiter.acquire("user1") is False
        
        # Check that timestamp is preserved (not updated to 'now')
        _, second_timestamp = limiter.buckets["user1"]
        assert second_timestamp == first_timestamp
        
        # Wait for token to refill
        await asyncio.sleep(1.1)
        
        # Should succeed now
        assert await limiter.acquire("user1") is True


class TestSemaphore:
    """Tests for Semaphore."""
    
    @pytest.mark.asyncio
    async def test_semaphore_allows_concurrent_operations(self):
        """Test that semaphore allows operations up to limit."""
        sem = Semaphore(max_concurrent=2)
        
        # Acquire twice should succeed
        async with sem:
            assert sem.active_count == 1
            async with sem:
                assert sem.active_count == 2
        
        # After release, count should be zero
        assert sem.active_count == 0
    
    @pytest.mark.asyncio
    async def test_semaphore_blocks_over_limit(self):
        """Test that semaphore blocks when limit is exceeded."""
        sem = Semaphore(max_concurrent=1)
        
        acquired = []
        
        async def worker(worker_id: int):
            async with sem:
                acquired.append(worker_id)
                await asyncio.sleep(0.1)
                acquired.append(-worker_id)  # Negative to mark release
        
        # Start two workers concurrently
        await asyncio.gather(worker(1), worker(2))
        
        # Both workers should have acquired and released
        # But they should not overlap (enforced by semaphore)
        assert len(acquired) == 4
        
        # Check that acquisitions don't overlap
        # If worker 1 acquires first: [1, -1, 2, -2]
        # If worker 2 acquires first: [2, -2, 1, -1]
        first_acquire = acquired[0]
        first_release = acquired[1]
        assert first_release == -first_acquire
    
    @pytest.mark.asyncio
    async def test_semaphore_active_count(self):
        """Test that active_count tracks concurrent operations."""
        sem = Semaphore(max_concurrent=3)
        
        assert sem.active_count == 0
        
        async with sem:
            assert sem.active_count == 1
            async with sem:
                assert sem.active_count == 2
                async with sem:
                    assert sem.active_count == 3
                assert sem.active_count == 2
            assert sem.active_count == 1
        
        assert sem.active_count == 0
