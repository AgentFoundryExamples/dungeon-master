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
"""Tests for JourneyLogClient service."""

import pytest
from httpx import AsyncClient, Response
from unittest.mock import AsyncMock, Mock

from app.services.journey_log_client import (
    JourneyLogClient,
    JourneyLogNotFoundError
)


@pytest.fixture
def mock_http_client():
    """Fixture providing a mock HTTP client."""
    return AsyncMock(spec=AsyncClient)


@pytest.fixture
def journey_log_client(mock_http_client):
    """Fixture providing a JourneyLogClient instance."""
    return JourneyLogClient(
        base_url="http://localhost:8000",
        http_client=mock_http_client,
        timeout=30,
        recent_n_default=20
    )


@pytest.mark.asyncio
async def test_get_context_success(journey_log_client, mock_http_client):
    """Test successful context retrieval."""
    # Mock response data
    mock_response_data = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"}
        },
        "quest": {
            "name": "Find the Ancient Artifact",
            "description": "Locate the lost artifact in the ruins",
            "completion_state": "in_progress"
        },
        "combat": {"active": False, "state": None},
        "narrative": {
            "recent_turns": [
                {
                    "player_action": "I look around",
                    "gm_response": "You see a vast hall",
                    "timestamp": "2025-01-15T10:00:00Z"
                }
            ]
        }
    }
    
    mock_response = AsyncMock(spec=Response)
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response
    
    # Call get_context
    context = await journey_log_client.get_context(
        character_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    # Verify the result
    assert context.character_id == "550e8400-e29b-41d4-a716-446655440000"
    assert context.status == "Healthy"
    assert context.location == {"id": "origin:nexus", "display_name": "The Nexus"}
    assert context.active_quest is not None
    assert context.active_quest["name"] == "Find the Ancient Artifact"
    assert len(context.recent_history) == 1
    
    # Verify the HTTP call
    mock_http_client.get.assert_called_once()
    call_args = mock_http_client.get.call_args
    assert "550e8400-e29b-41d4-a716-446655440000/context" in call_args[0][0]
    assert call_args[1]["params"]["recent_n"] == 20
    assert not call_args[1]["params"]["include_pois"]


@pytest.mark.asyncio
async def test_get_context_not_found(journey_log_client, mock_http_client):
    """Test context retrieval when character not found."""
    from httpx import HTTPStatusError, Request
    
    # Mock 404 response
    mock_request = AsyncMock(spec=Request)
    mock_response = AsyncMock(spec=Response)
    mock_response.status_code = 404
    mock_response.text = "Character not found"
    
    mock_http_client.get.side_effect = HTTPStatusError(
        "404 Not Found",
        request=mock_request,
        response=mock_response
    )
    
    # Should raise JourneyLogNotFoundError
    with pytest.raises(JourneyLogNotFoundError, match="not found"):
        await journey_log_client.get_context(
            character_id="550e8400-e29b-41d4-a716-446655440000"
        )


@pytest.mark.asyncio
async def test_persist_narrative_success(journey_log_client, mock_http_client):
    """Test successful narrative persistence."""
    mock_response = AsyncMock(spec=Response)
    mock_response.raise_for_status = Mock()
    mock_http_client.post.return_value = mock_response
    
    # Call persist_narrative
    await journey_log_client.persist_narrative(
        character_id="test-char-123",
        user_action="I look around",
        narrative="You see a dark cave.",
        user_id="user-123"
    )
    
    # Verify post call
    mock_http_client.post.assert_called_once()
    call_args = mock_http_client.post.call_args
    assert "test-char-123/narrative" in call_args[0][0]
    assert call_args[1]["json"]["user_action"] == "I look around"
    assert call_args[1]["json"]["ai_response"] == "You see a dark cave."
    assert call_args.kwargs["headers"]["X-User-Id"] == "user-123"


@pytest.mark.asyncio
async def test_persist_narrative_not_found(journey_log_client, mock_http_client):
    """Test narrative persistence when character not found."""
    from httpx import HTTPStatusError, Request
    
    mock_request = AsyncMock(spec=Request)
    mock_response = AsyncMock(spec=Response)
    mock_response.status_code = 404
    mock_response.text = "Character not found"
    
    mock_http_client.post.side_effect = HTTPStatusError(
        "404 Not Found",
        request=mock_request,
        response=mock_response
    )
    
    # Should raise JourneyLogNotFoundError
    with pytest.raises(JourneyLogNotFoundError):
        await journey_log_client.persist_narrative(
            character_id="550e8400-e29b-41d4-a716-446655440000",
            user_action="I search",
            narrative="You find nothing"
        )
