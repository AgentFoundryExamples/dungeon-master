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
"""Integration tests for streaming /turn endpoint."""

import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock


def parse_sse_events(stream_content: bytes) -> list:
    """Parse SSE stream content into individual events."""
    events = []
    lines = stream_content.decode('utf-8').split('\n')
    
    for line in lines:
        if line.startswith('data: '):
            data_str = line[6:]  # Remove 'data: ' prefix
            if data_str == '[DONE]':
                events.append({"type": "done"})
            else:
                try:
                    events.append(json.loads(data_str))
                except json.JSONDecodeError:
                    pass  # Skip malformed events
    
    return events


@pytest.mark.asyncio
async def test_turn_stream_endpoint_basic_flow(client):
    """Test streaming endpoint returns SSE events."""
    from httpx import Response
    
    # Mock journey-log context response
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "status": "Alive",
            "location": {"id": "tavern", "display_name": "The Rusty Tankard"},
            "additional_fields": {}
        },
        "narrative": {"recent_turns": []},
        "combat": {"active": False},
        "quest": None
    }
    mock_context_response.raise_for_status = MagicMock()
    
    # Mock journey-log persist response
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        # Make streaming request
        response = client.post(
            "/turn/stream",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I search the room"
            }
        )
        
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        
        # Parse SSE events
        events = parse_sse_events(response.content)
        
        # Should have at least: some tokens + complete event + done marker
        assert len(events) >= 2
        
        # First events should be tokens
        token_events = [e for e in events if e.get("type") == "token"]
        assert len(token_events) > 0
        
        # Should have exactly one complete event
        complete_events = [e for e in events if e.get("type") == "complete"]
        assert len(complete_events) == 1
        
        # Complete event should have intents and subsystem_summary
        complete_event = complete_events[0]
        assert "intents" in complete_event
        assert "subsystem_summary" in complete_event
        
        # Should have done marker
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1


@pytest.mark.asyncio
async def test_turn_stream_endpoint_preserves_narrative(client):
    """Test that streamed narrative matches stub mode output."""
    from httpx import Response
    
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "status": "Alive",
            "location": {"id": "tavern", "display_name": "The Rusty Tankard"},
            "additional_fields": {}
        },
        "narrative": {"recent_turns": []},
        "combat": {"active": False},
        "quest": None
    }
    mock_context_response.raise_for_status = MagicMock()
    
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        response = client.post(
            "/turn/stream",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I look around"
            }
        )
        
        assert response.status_code == 200
        
        events = parse_sse_events(response.content)
        
        # Reconstruct narrative from token events
        token_events = [e for e in events if e.get("type") == "token"]
        streamed_narrative = "".join([e.get("content", "") for e in token_events])
        
        # Verify narrative was streamed (stub mode creates narrative)
        assert len(streamed_narrative) > 0
        assert "[STUB MODE]" in streamed_narrative


@pytest.mark.asyncio
async def test_turn_stream_endpoint_invalid_character_id(client):
    """Test streaming endpoint validates character_id format."""
    response = client.post(
        "/turn/stream",
        json={
            "character_id": "not-a-valid-uuid",
            "user_action": "I search the room"
        }
    )
    
    # Should return 422 for validation error
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_turn_stream_endpoint_with_trace_id(client):
    """Test streaming endpoint accepts trace_id."""
    from httpx import Response
    
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "status": "Alive",
            "location": {"id": "tavern", "display_name": "The Rusty Tankard"},
            "additional_fields": {}
        },
        "narrative": {"recent_turns": []},
        "combat": {"active": False},
        "quest": None
    }
    mock_context_response.raise_for_status = MagicMock()
    
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        response = client.post(
            "/turn/stream",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I search the room",
                "trace_id": "test-trace-123"
            }
        )
        
        assert response.status_code == 200
        
        events = parse_sse_events(response.content)
        
        # Should have complete event
        complete_events = [e for e in events if e.get("type") == "complete"]
        assert len(complete_events) == 1


@pytest.mark.asyncio
async def test_legacy_turn_endpoint_still_works(client):
    """Test that legacy /turn endpoint is not affected by streaming changes."""
    from httpx import Response
    
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "status": "Alive",
            "location": {"id": "tavern", "display_name": "The Rusty Tankard"},
            "additional_fields": {}
        },
        "narrative": {"recent_turns": []},
        "combat": {"active": False},
        "quest": None
    }
    mock_context_response.raise_for_status = MagicMock()
    
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        # Test legacy endpoint
        response = client.post(
            "/turn",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I search the room"
            }
        )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        
        # Should return standard JSON response (not SSE)
        data = response.json()
        assert "narrative" in data
        assert "intents" in data
        assert "subsystem_summary" in data


@pytest.mark.asyncio
async def test_streaming_endpoint_separate_from_legacy(client):
    """Test that /turn and /turn/stream are separate endpoints."""
    from httpx import Response
    
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "status": "Alive",
            "location": {"id": "tavern", "display_name": "The Rusty Tankard"},
            "additional_fields": {}
        },
        "narrative": {"recent_turns": []},
        "combat": {"active": False},
        "quest": None
    }
    mock_context_response.raise_for_status = MagicMock()
    
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        # Both endpoints should exist
        response_legacy = client.post("/turn", json={
            "character_id": "550e8400-e29b-41d4-a716-446655440000",
            "user_action": "test"
        })
        
        response_stream = client.post("/turn/stream", json={
            "character_id": "550e8400-e29b-41d4-a716-446655440000",
            "user_action": "test"
        })
        
        # Both should return 200
        assert response_legacy.status_code == 200
        assert response_stream.status_code == 200
        
        # Content types should be different
        assert response_legacy.headers["content-type"] == "application/json"
        assert "text/event-stream" in response_stream.headers["content-type"]
