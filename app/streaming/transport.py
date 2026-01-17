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
"""Streaming transport abstractions for SSE and WebSocket delivery.

This module provides transport layer abstractions for streaming narrative tokens
to clients via Server-Sent Events (SSE) or WebSocket connections.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import json

from app.logging import StructuredLogger

logger = StructuredLogger(__name__)


@dataclass
class StreamEvent:
    """Represents a streaming event sent to the client.
    
    Attributes:
        type: Event type (token, metadata, complete, error)
        data: Event payload (token text, metadata, final outcome)
        timestamp: Event timestamp (ISO 8601 format)
    """
    type: str
    data: Dict[str, Any]
    timestamp: Optional[str] = None
    
    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class StreamTransport(ABC):
    """Abstract base class for streaming transports.
    
    This interface allows swapping between SSE, WebSocket, or other
    transports without changing orchestrator logic.
    
    Implementations must handle:
    - Event serialization (JSON encoding)
    - Transport-specific framing (SSE format, WebSocket messages)
    - Connection lifecycle (open, close, error)
    - Backpressure and buffering
    """
    
    @abstractmethod
    async def send_event(self, event: StreamEvent) -> None:
        """Send a streaming event to the client.
        
        Args:
            event: StreamEvent to send
            
        Raises:
            TransportError: If send fails (client disconnect, etc.)
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close the transport connection gracefully.
        
        Flushes any pending events and releases resources.
        """
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the transport is still connected.
        
        Returns:
            True if client is connected, False otherwise
        """
        pass


class SSETransport(StreamTransport):
    """Server-Sent Events transport implementation.
    
    SSE Format:
        data: {"type":"token","content":"Hello"}\\n\\n
        data: {"type":"complete","intents":{...}}\\n\\n
    
    Features:
    - HTTP-based (works through firewalls/proxies)
    - Server → client only (no client → server messages)
    - Automatic reconnection support
    - Simple JSON-over-HTTP protocol
    """
    
    def __init__(self, event_generator_callback):
        """Initialize SSE transport.
        
        Args:
            event_generator_callback: Async generator callback that yields formatted SSE strings
        """
        self._event_callback = event_generator_callback
        self._connected = True
    
    async def send_event(self, event: StreamEvent) -> None:
        """Send event in SSE format: data: {json}\\n\\n
        
        Args:
            event: StreamEvent to send
            
        Raises:
            TransportError: If transport is not connected or send fails
        """
        if not self._connected:
            raise TransportError("Transport not connected")
        
        try:
            # Build event payload
            payload = {"type": event.type, "timestamp": event.timestamp}
            payload.update(event.data)
            
            # Format as SSE event
            data = json.dumps(payload)
            sse_event = f"data: {data}\n\n"
            
            # Yield to async generator
            await self._event_callback(sse_event)
            
        except Exception as e:
            # Client disconnected or write failed
            self._connected = False
            logger.warning(
                "Failed to send SSE event - client may have disconnected",
                error_type=type(e).__name__,
                error=str(e)
            )
            raise TransportError(f"Failed to send SSE event: {e}") from e
    
    async def close(self) -> None:
        """Send SSE [DONE] marker and close stream."""
        if self._connected:
            try:
                await self._event_callback("data: [DONE]\n\n")
            except Exception as e:
                logger.warning("Failed to send SSE done marker", error=str(e))
            finally:
                self._connected = False
    
    def is_connected(self) -> bool:
        """Check if transport is connected.
        
        Returns:
            True if connected, False otherwise
        """
        return self._connected


class TransportError(Exception):
    """Raised when transport operations fail."""
    pass
