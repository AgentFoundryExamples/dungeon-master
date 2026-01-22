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
"""Tests for policy state extraction from journey-log responses."""

import pytest
from httpx import AsyncClient, Response
from unittest.mock import AsyncMock, Mock

from app.services.journey_log_client import JourneyLogClient


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
async def test_policy_state_extraction_full_data(journey_log_client, mock_http_client):
    """Test policy state extraction with all fields present."""
    mock_response_data = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"},
            "additional_fields": {
                "last_quest_offered_at": "2025-01-15T10:00:00Z",
                "last_poi_created_at": "2025-01-15T09:30:00Z",
                "turns_since_last_quest": 5,
                "turns_since_last_poi": 3,
                "user_is_wandering": False,
                "requested_guidance": True
            }
        },
        "quest": {
            "name": "Find the Ancient Artifact",
            "description": "Locate the lost artifact",
            "completion_state": "in_progress"
        },
        "has_active_quest": True,
        "combat": {"active": True, "state": {"combat_id": "combat-123"}},
        "narrative": {"recent_turns": []},
        "world": {},
        "metadata": {}
    }
    
    mock_response = AsyncMock(spec=Response)
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response
    
    context = await journey_log_client.get_context(
        character_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    # Verify policy state extraction
    assert context.policy_state.last_quest_offered_at == "2025-01-15T10:00:00Z"
    assert context.policy_state.last_poi_created_at == "2025-01-15T09:30:00Z"
    assert context.policy_state.turns_since_last_quest == 5
    assert context.policy_state.turns_since_last_poi == 3
    assert context.policy_state.has_active_quest is True
    assert context.policy_state.combat_active is True
    assert context.policy_state.user_is_wandering is False
    assert context.policy_state.requested_guidance is True


@pytest.mark.asyncio
async def test_policy_state_extraction_defaults(journey_log_client, mock_http_client):
    """Test policy state extraction with missing fields uses safe defaults.
    
    This test verifies that when the journey-log response lacks additional_fields
    or policy-relevant metadata, the extraction logic provides safe default values:
    - Timestamps default to None (no history)
    - Turn counters default to 0 (no previous triggers)
    - State flags (has_active_quest, combat_active) default to False (not present)
    - Meta flags (user_is_wandering, requested_guidance) default to None (not set)
    - No crashes or exceptions occur
    """
    mock_response_data = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"}
            # Missing additional_fields - testing default behavior
        },
        "has_active_quest": False,
        "combat": {"active": False},
        "narrative": {"recent_turns": []},
        "world": {},
        "metadata": {}
    }
    
    mock_response = AsyncMock(spec=Response)
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response
    
    context = await journey_log_client.get_context(
        character_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    # Verify safe defaults
    assert context.policy_state.last_quest_offered_at is None
    assert context.policy_state.last_poi_created_at is None
    assert context.policy_state.turns_since_last_quest == 0
    assert context.policy_state.turns_since_last_poi == 0
    assert context.policy_state.has_active_quest is False
    assert context.policy_state.combat_active is False
    assert context.policy_state.user_is_wandering is None
    assert context.policy_state.requested_guidance is None


@pytest.mark.asyncio
async def test_policy_state_quest_presence_detection(journey_log_client, mock_http_client):
    """Test has_active_quest detection from quest field."""
    mock_response_data = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"}
        },
        "quest": {"name": "Test Quest", "completion_state": "in_progress"},
        "combat": {"active": False},
        "narrative": {"recent_turns": []},
        "world": {},
        "metadata": {}
    }
    
    mock_response = AsyncMock(spec=Response)
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response
    
    context = await journey_log_client.get_context(
        character_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    # has_active_quest should be True because quest is present
    assert context.policy_state.has_active_quest is True


@pytest.mark.asyncio
async def test_policy_state_invalid_turn_counters(journey_log_client, mock_http_client):
    """Test policy state handles invalid turn counter values."""
    mock_response_data = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"},
            "additional_fields": {
                "turns_since_last_quest": -5,  # Invalid negative
                "turns_since_last_poi": "not_a_number"  # Invalid type
            }
        },
        "has_active_quest": False,
        "combat": {"active": False},
        "narrative": {"recent_turns": []},
        "world": {},
        "metadata": {}
    }
    
    mock_response = AsyncMock(spec=Response)
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response
    
    context = await journey_log_client.get_context(
        character_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    # Invalid values should default to 0
    assert context.policy_state.turns_since_last_quest == 0
    assert context.policy_state.turns_since_last_poi == 0


@pytest.mark.asyncio
async def test_policy_state_invalid_boolean_flags(journey_log_client, mock_http_client):
    """Test policy state handles invalid boolean flag values."""
    mock_response_data = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"},
            "additional_fields": {
                "user_is_wandering": "yes",  # Invalid string
                "requested_guidance": 1  # Invalid number
            }
        },
        "has_active_quest": False,
        "combat": {"active": False},
        "narrative": {"recent_turns": []},
        "world": {},
        "metadata": {}
    }
    
    mock_response = AsyncMock(spec=Response)
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response
    
    context = await journey_log_client.get_context(
        character_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    # Invalid boolean values should default to None
    assert context.policy_state.user_is_wandering is None
    assert context.policy_state.requested_guidance is None


@pytest.mark.asyncio
async def test_policy_state_additional_fields_preserved(journey_log_client, mock_http_client):
    """Test that additional_fields are preserved in context."""
    mock_response_data = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"},
            "additional_fields": {
                "custom_field_1": "value1",
                "custom_field_2": 42,
                "turns_since_last_quest": 10
            }
        },
        "has_active_quest": False,
        "combat": {"active": False},
        "narrative": {"recent_turns": []},
        "world": {},
        "metadata": {}
    }
    
    mock_response = AsyncMock(spec=Response)
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response
    
    context = await journey_log_client.get_context(
        character_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    # Verify additional_fields are preserved
    assert context.additional_fields == {
        "custom_field_1": "value1",
        "custom_field_2": 42,
        "turns_since_last_quest": 10
    }


@pytest.mark.asyncio
async def test_policy_state_combat_inactive_no_state(journey_log_client, mock_http_client):
    """Test combat state absent entirely defaults to inactive."""
    mock_response_data = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"}
        },
        "has_active_quest": False,
        "combat": {},  # No active field
        "narrative": {"recent_turns": []},
        "world": {},
        "metadata": {}
    }
    
    mock_response = AsyncMock(spec=Response)
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response
    
    context = await journey_log_client.get_context(
        character_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    # Combat should default to inactive
    assert context.policy_state.combat_active is False


@pytest.mark.asyncio
async def test_policy_state_invalid_timestamps(journey_log_client, mock_http_client):
    """Test policy state handles invalid timestamp values."""
    mock_response_data = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"},
            "additional_fields": {
                "last_quest_offered_at": "not-a-timestamp",  # Invalid format
                "last_poi_created_at": 12345  # Invalid type (number)
            }
        },
        "has_active_quest": False,
        "combat": {"active": False},
        "narrative": {"recent_turns": []},
        "world": {},
        "metadata": {}
    }
    
    mock_response = AsyncMock(spec=Response)
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response
    
    context = await journey_log_client.get_context(
        character_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    # Invalid timestamps should default to None
    assert context.policy_state.last_quest_offered_at is None
    assert context.policy_state.last_poi_created_at is None


@pytest.mark.asyncio
async def test_policy_state_valid_timestamps(journey_log_client, mock_http_client):
    """Test policy state accepts valid ISO 8601 timestamps."""
    mock_response_data = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"},
            "additional_fields": {
                "last_quest_offered_at": "2025-01-15T10:00:00Z",  # Valid with Z
                "last_poi_created_at": "2025-01-15T09:30:00+00:00"  # Valid with timezone
            }
        },
        "has_active_quest": False,
        "combat": {"active": False},
        "narrative": {"recent_turns": []},
        "world": {},
        "metadata": {}
    }
    
    mock_response = AsyncMock(spec=Response)
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response
    
    context = await journey_log_client.get_context(
        character_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    # Valid timestamps should be preserved
    assert context.policy_state.last_quest_offered_at == "2025-01-15T10:00:00Z"
    assert context.policy_state.last_poi_created_at == "2025-01-15T09:30:00+00:00"


@pytest.mark.asyncio
async def test_policy_state_explicit_has_active_quest_flag(journey_log_client, mock_http_client):
    """Test that explicit has_active_quest flag is prioritized over quest presence."""
    # Test case 1: has_active_quest=True but no quest object (edge case)
    mock_response_data = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"}
        },
        "quest": None,
        "has_active_quest": True,  # Explicit flag overrides quest presence
        "combat": {"active": False},
        "narrative": {"recent_turns": []},
        "world": {},
        "metadata": {}
    }
    
    mock_response = AsyncMock(spec=Response)
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response
    
    context = await journey_log_client.get_context(
        character_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    # Should use explicit flag
    assert context.policy_state.has_active_quest is True


@pytest.mark.asyncio
async def test_policy_state_quest_presence_fallback(journey_log_client, mock_http_client):
    """Test that quest presence is used when explicit flag is missing."""
    mock_response_data = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"}
        },
        "quest": {"name": "Test Quest", "completion_state": "in_progress"},
        # No explicit has_active_quest flag - should derive from quest presence
        "combat": {"active": False},
        "narrative": {"recent_turns": []},
        "world": {},
        "metadata": {}
    }
    
    mock_response = AsyncMock(spec=Response)
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response
    
    context = await journey_log_client.get_context(
        character_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    # Should derive from quest presence
    assert context.policy_state.has_active_quest is True
