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
"""Narrative buffer for accumulating streamed tokens and replay to journey-log.

**DEPRECATED**: Streaming functionality has been removed to simplify the MVP.
This class is kept for reference but is no longer used by the service.
All clients should use the synchronous POST /turn endpoint instead.

This module provided the NarrativeBuffer class that accumulated tokens during
streaming and provided replay functionality for journey-log persistence.
"""

from typing import List, Optional
import time
from datetime import datetime, timezone


class NarrativeBuffer:
    """Buffers streamed narrative tokens for replay to journey-log.
    
    This buffer serves two purposes:
    1. Accumulate tokens during streaming for client delivery
    2. Provide complete narrative for journey-log POST
    
    The buffer guarantees that the narrative persisted to journey-log
    is EXACTLY the same text streamed to the client, token-for-token.
    
    Example:
        buffer = NarrativeBuffer()
        
        # During streaming
        async for token in llm_client.generate_narrative_stream(...):
            buffer.append(token)
            await transport.send_event(StreamEvent("token", {"content": token}))
        
        # After streaming
        buffer.finalize()
        complete_narrative = buffer.get_complete_narrative()
        await journey_log_client.persist_narrative(character_id, complete_narrative)
    """
    
    # Maximum buffer size in bytes (50KB)
    MAX_BUFFER_SIZE = 50_000
    
    def __init__(self):
        """Initialize an empty narrative buffer."""
        self._tokens: List[str] = []
        self._finalized: bool = False
        # Use monotonic clock for duration (not affected by system clock changes)
        self._start_time_monotonic: float = time.monotonic()
        self._duration_ms: Optional[float] = None
        # Use UTC timestamp for logging
        self._start_time_utc: datetime = datetime.now(timezone.utc)
    
    def append(self, token: str) -> None:
        """Append a token to the buffer.
        
        Args:
            token: Token text from LLM
            
        Raises:
            BufferError: If buffer is already finalized or size limit exceeded
        """
        if self._finalized:
            raise BufferError("Cannot append to finalized buffer")
        
        # Check buffer size limit
        current_size = sum(len(t) for t in self._tokens)
        if current_size + len(token) > self.MAX_BUFFER_SIZE:
            self.finalize()
            raise BufferError(
                f"Buffer size limit exceeded: {current_size + len(token)} bytes "
                f"(max: {self.MAX_BUFFER_SIZE})"
            )
        
        self._tokens.append(token)
    
    def get_complete_narrative(self) -> str:
        """Get the complete narrative text.
        
        Joins all buffered tokens into a single string.
        This is the EXACT text that was streamed to the client.
        
        Returns:
            Complete narrative text
        """
        return "".join(self._tokens)
    
    def finalize(self) -> None:
        """Mark buffer as finalized (no more tokens).
        
        Records end time for duration calculation using monotonic clock.
        This method is idempotent - calling it multiple times is safe.
        """
        if not self._finalized:
            self._duration_ms = (time.monotonic() - self._start_time_monotonic) * 1000
            self._finalized = True
    
    def get_token_count(self) -> int:
        """Get number of tokens buffered.
        
        Returns:
            Number of tokens in buffer
        """
        return len(self._tokens)
    
    def get_duration_ms(self) -> Optional[float]:
        """Get streaming duration in milliseconds.
        
        Returns:
            Duration in ms, or None if not finalized
        """
        return self._duration_ms
    
    def is_finalized(self) -> bool:
        """Check if buffer is finalized.
        
        Returns:
            True if buffer is finalized, False otherwise
        """
        return self._finalized


class BufferError(Exception):
    """Raised when buffer operations fail."""
    pass
