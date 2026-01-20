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
"""Tests for streaming transport classes (DEPRECATED).

These classes are no longer used as streaming functionality has been disabled.
Tests verify that the classes still work for reference purposes.
"""

import pytest
from datetime import datetime, timezone
from app.streaming.transport import StreamEvent, SSETransport, TransportError


def test_stream_event_creation():
    """Test StreamEvent creation with explicit timestamp."""
    event = StreamEvent(
        type="token",
        data={"content": "Hello"},
        timestamp="2025-01-17T10:00:00.000Z"
    )
    
    assert event.type == "token"
    assert event.data == {"content": "Hello"}
    assert event.timestamp == "2025-01-17T10:00:00.000Z"


def test_stream_event_auto_timestamp():
    """Test StreamEvent auto-generates timestamp if not provided."""
    event = StreamEvent(
        type="token",
        data={"content": "Hello"}
    )
    
    assert event.type == "token"
    assert event.data == {"content": "Hello"}
    assert event.timestamp is not None
    
    # Parse timestamp to verify it's valid ISO 8601
    parsed = datetime.fromisoformat(event.timestamp.replace('Z', '+00:00'))
    assert parsed.tzinfo is not None


@pytest.mark.skip(reason="Streaming functionality deprecated")
@pytest.mark.skip(reason="Streaming functionality deprecated")
def test_stream_event_various_types():
    """Test StreamEvent with different event types."""
    types = ["token", "metadata", "complete", "error"]
    
    for event_type in types:
        event = StreamEvent(type=event_type, data={})
        assert event.type == event_type


@pytest.mark.asyncio
@pytest.mark.skip(reason="Streaming functionality deprecated")
async def test_sse_transport_send_token():
    """Test SSETransport sends token event correctly."""
    sent_events = []
    
    async def mock_callback(data):
        sent_events.append(data)
    
    transport = SSETransport(mock_callback)
    
    event = StreamEvent(
        type="token",
        data={"content": "Hello"}
    )
    
    await transport.send_event(event)
    
    assert len(sent_events) == 1
    assert "data: " in sent_events[0]
    assert '"type": "token"' in sent_events[0]
    assert '"content": "Hello"' in sent_events[0]
    assert sent_events[0].endswith("\n\n")


@pytest.mark.asyncio
@pytest.mark.skip(reason="Streaming functionality deprecated")
async def test_sse_transport_send_complete():
    """Test SSETransport sends complete event correctly."""
    sent_events = []
    
    async def mock_callback(data):
        sent_events.append(data)
    
    transport = SSETransport(mock_callback)
    
    event = StreamEvent(
        type="complete",
        data={
            "intents": {"quest_intent": {"action": "none"}},
            "subsystem_summary": {}
        }
    )
    
    await transport.send_event(event)
    
    assert len(sent_events) == 1
    assert '"type": "complete"' in sent_events[0]
    assert '"intents"' in sent_events[0]


@pytest.mark.asyncio
@pytest.mark.skip(reason="Streaming functionality deprecated")
async def test_sse_transport_send_error():
    """Test SSETransport sends error event correctly."""
    sent_events = []
    
    async def mock_callback(data):
        sent_events.append(data)
    
    transport = SSETransport(mock_callback)
    
    event = StreamEvent(
        type="error",
        data={
            "error_type": "llm_timeout",
            "message": "LLM timed out",
            "recoverable": True
        }
    )
    
    await transport.send_event(event)
    
    assert len(sent_events) == 1
    assert '"type": "error"' in sent_events[0]
    assert '"error_type": "llm_timeout"' in sent_events[0]


@pytest.mark.asyncio
@pytest.mark.skip(reason="Streaming functionality deprecated")
async def test_sse_transport_close():
    """Test SSETransport sends [DONE] marker on close."""
    sent_events = []
    
    async def mock_callback(data):
        sent_events.append(data)
    
    transport = SSETransport(mock_callback)
    
    await transport.close()
    
    assert len(sent_events) == 1
    assert sent_events[0] == "data: [DONE]\n\n"
    assert not transport.is_connected()


@pytest.mark.asyncio
@pytest.mark.skip(reason="Streaming functionality deprecated")
async def test_sse_transport_connection_state():
    """Test SSETransport connection state tracking."""
    async def mock_callback(data):
        pass
    
    transport = SSETransport(mock_callback)
    
    assert transport.is_connected()
    
    await transport.close()
    
    assert not transport.is_connected()


@pytest.mark.asyncio
@pytest.mark.skip(reason="Streaming functionality deprecated")
async def test_sse_transport_send_after_close():
    """Test SSETransport raises error when sending after close."""
    async def mock_callback(data):
        pass
    
    transport = SSETransport(mock_callback)
    await transport.close()
    
    event = StreamEvent(type="token", data={"content": "Test"})
    
    with pytest.raises(TransportError, match="Transport not connected"):
        await transport.send_event(event)


@pytest.mark.asyncio
@pytest.mark.skip(reason="Streaming functionality deprecated")
async def test_sse_transport_callback_exception():
    """Test SSETransport handles callback exceptions gracefully."""
    async def failing_callback(data):
        raise ValueError("Callback failed")
    
    transport = SSETransport(failing_callback)
    
    event = StreamEvent(type="token", data={"content": "Test"})
    
    with pytest.raises(TransportError, match="Failed to send SSE event"):
        await transport.send_event(event)
    
    # Transport should be marked as disconnected
    assert not transport.is_connected()


@pytest.mark.asyncio
@pytest.mark.skip(reason="Streaming functionality deprecated")
async def test_sse_transport_multiple_events():
    """Test SSETransport handles multiple events in sequence."""
    sent_events = []
    
    async def mock_callback(data):
        sent_events.append(data)
    
    transport = SSETransport(mock_callback)
    
    # Send multiple token events
    for i in range(5):
        event = StreamEvent(
            type="token",
            data={"content": f"Token{i}"}
        )
        await transport.send_event(event)
    
    # Send complete event
    complete_event = StreamEvent(
        type="complete",
        data={"intents": None}
    )
    await transport.send_event(complete_event)
    
    # Close transport
    await transport.close()
    
    assert len(sent_events) == 7  # 5 tokens + 1 complete + 1 [DONE]
    assert all("data: " in e for e in sent_events[:-1])
    assert sent_events[-1] == "data: [DONE]\n\n"
