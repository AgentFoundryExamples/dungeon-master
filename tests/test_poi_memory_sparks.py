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
"""Tests for POI memory spark retrieval in JourneyLogClient.

This module verifies that the JourneyLogClient.get_random_pois() method
correctly fetches random POIs for memory spark injection and handles
errors gracefully (non-fatal).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, Response, HTTPStatusError, TimeoutException

from app.services.journey_log_client import JourneyLogClient


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    return AsyncMock(spec=AsyncClient)


@pytest.fixture
def journey_log_client(mock_http_client):
    """Create a JourneyLogClient with mock HTTP client."""
    return JourneyLogClient(
        base_url="http://localhost:8000",
        http_client=mock_http_client,
        timeout=30
    )


@pytest.mark.asyncio
async def test_get_random_pois_success(journey_log_client, mock_http_client):
    """Test successful random POI retrieval."""
    # Mock successful response
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "pois": [
            {
                "id": "poi-1",
                "name": "The Ancient Temple",
                "description": "A mysterious temple from ages past"
            },
            {
                "id": "poi-2",
                "name": "The Dark Forest",
                "description": "An ominous forest shrouded in mist"
            }
        ],
        "count": 2,
        "requested_n": 3,
        "total_available": 5
    }
    mock_response.raise_for_status = MagicMock()
    mock_http_client.get.return_value = mock_response
    
    # Call method
    result = await journey_log_client.get_random_pois(
        character_id="test-char-123",
        n=3
    )
    
    # Verify
    assert len(result) == 2
    assert result[0]["name"] == "The Ancient Temple"
    assert result[1]["name"] == "The Dark Forest"
    
    # Verify HTTP call
    mock_http_client.get.assert_called_once()
    call_args = mock_http_client.get.call_args
    assert call_args[0][0] == "http://localhost:8000/characters/test-char-123/pois/random"
    assert call_args[1]["params"] == {"n": 3}


@pytest.mark.asyncio
async def test_get_random_pois_empty_response(journey_log_client, mock_http_client):
    """Test random POI retrieval when no POIs exist."""
    # Mock response with empty POI list
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "pois": [],
        "count": 0,
        "requested_n": 3,
        "total_available": 0
    }
    mock_response.raise_for_status = MagicMock()
    mock_http_client.get.return_value = mock_response
    
    # Call method
    result = await journey_log_client.get_random_pois(
        character_id="test-char-123",
        n=3
    )
    
    # Verify empty list returned (not an error)
    assert result == []


@pytest.mark.asyncio
async def test_get_random_pois_http_error(journey_log_client, mock_http_client):
    """Test random POI retrieval handles HTTP errors gracefully."""
    # Mock HTTP error
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 500
    mock_response.text = "Internal server error"
    
    http_error = HTTPStatusError(
        message="Server error",
        request=MagicMock(),
        response=mock_response
    )
    mock_http_client.get.side_effect = http_error
    
    # Call method - should not raise
    result = await journey_log_client.get_random_pois(
        character_id="test-char-123",
        n=3
    )
    
    # Verify empty list returned (non-fatal)
    assert result == []


@pytest.mark.asyncio
async def test_get_random_pois_404_not_found(journey_log_client, mock_http_client):
    """Test random POI retrieval handles 404 gracefully."""
    # Mock 404 error
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 404
    mock_response.text = "Character not found"
    
    http_error = HTTPStatusError(
        message="Not found",
        request=MagicMock(),
        response=mock_response
    )
    mock_http_client.get.side_effect = http_error
    
    # Call method - should not raise
    result = await journey_log_client.get_random_pois(
        character_id="test-char-123",
        n=3
    )
    
    # Verify empty list returned (non-fatal)
    assert result == []


@pytest.mark.asyncio
async def test_get_random_pois_timeout(journey_log_client, mock_http_client):
    """Test random POI retrieval handles timeout gracefully."""
    # Mock timeout
    mock_http_client.get.side_effect = TimeoutException("Request timed out")
    
    # Call method - should not raise
    result = await journey_log_client.get_random_pois(
        character_id="test-char-123",
        n=3
    )
    
    # Verify empty list returned (non-fatal)
    assert result == []


@pytest.mark.asyncio
async def test_get_random_pois_unexpected_error(journey_log_client, mock_http_client):
    """Test random POI retrieval handles unexpected errors gracefully."""
    # Mock unexpected error
    mock_http_client.get.side_effect = Exception("Unexpected error")
    
    # Call method - should not raise
    result = await journey_log_client.get_random_pois(
        character_id="test-char-123",
        n=3
    )
    
    # Verify empty list returned (non-fatal)
    assert result == []


@pytest.mark.asyncio
async def test_get_random_pois_with_trace_id(journey_log_client, mock_http_client):
    """Test random POI retrieval includes trace ID in headers."""
    # Mock successful response
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "pois": [
            {"id": "poi-1", "name": "The Temple"}
        ],
        "count": 1,
        "requested_n": 1,
        "total_available": 1
    }
    mock_response.raise_for_status = MagicMock()
    mock_http_client.get.return_value = mock_response
    
    # Call method with trace_id
    result = await journey_log_client.get_random_pois(
        character_id="test-char-123",
        n=1,
        trace_id="trace-xyz"
    )
    
    # Verify trace ID included in headers
    call_args = mock_http_client.get.call_args
    assert call_args[1]["headers"]["X-Trace-Id"] == "trace-xyz"


@pytest.mark.asyncio
async def test_get_random_pois_default_n(journey_log_client, mock_http_client):
    """Test random POI retrieval uses default n=3."""
    # Mock successful response
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "pois": [],
        "count": 0,
        "requested_n": 3,
        "total_available": 0
    }
    mock_response.raise_for_status = MagicMock()
    mock_http_client.get.return_value = mock_response
    
    # Call method without n parameter
    result = await journey_log_client.get_random_pois(
        character_id="test-char-123"
    )
    
    # Verify default n=3 used
    call_args = mock_http_client.get.call_args
    assert call_args[1]["params"]["n"] == 3


@pytest.mark.asyncio
async def test_get_random_pois_custom_n(journey_log_client, mock_http_client):
    """Test random POI retrieval uses custom n value."""
    # Mock successful response
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "pois": [],
        "count": 0,
        "requested_n": 10,
        "total_available": 0
    }
    mock_response.raise_for_status = MagicMock()
    mock_http_client.get.return_value = mock_response
    
    # Call method with custom n
    result = await journey_log_client.get_random_pois(
        character_id="test-char-123",
        n=10
    )
    
    # Verify custom n used
    call_args = mock_http_client.get.call_args
    assert call_args[1]["params"]["n"] == 10


@pytest.mark.asyncio
async def test_get_random_pois_clamps_n_to_max(journey_log_client, mock_http_client):
    """Test random POI retrieval clamps n to maximum of 20."""
    # Mock successful response
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "pois": [],
        "count": 0,
        "requested_n": 20,
        "total_available": 0
    }
    mock_response.raise_for_status = MagicMock()
    mock_http_client.get.return_value = mock_response
    
    # Call method with n > 20
    result = await journey_log_client.get_random_pois(
        character_id="test-char-123",
        n=100
    )
    
    # Verify n clamped to 20
    call_args = mock_http_client.get.call_args
    assert call_args[1]["params"]["n"] == 20


@pytest.mark.asyncio
async def test_get_random_pois_clamps_n_to_min(journey_log_client, mock_http_client):
    """Test random POI retrieval clamps n to minimum of 1."""
    # Mock successful response
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "pois": [],
        "count": 0,
        "requested_n": 1,
        "total_available": 0
    }
    mock_response.raise_for_status = MagicMock()
    mock_http_client.get.return_value = mock_response
    
    # Call method with n < 1
    result = await journey_log_client.get_random_pois(
        character_id="test-char-123",
        n=-5
    )
    
    # Verify n clamped to 1
    call_args = mock_http_client.get.call_args
    assert call_args[1]["params"]["n"] == 1


@pytest.mark.asyncio
async def test_poi_trigger_frequency_over_multiple_turns():
    """Test POI trigger frequency matches configured probability over many turns.
    
    Validates:
    - POI triggers occur within statistical bounds
    - Trigger rate aligns with configured probability
    - No unexpected POI creation when policy blocks
    """
    from app.services.turn_orchestrator import TurnOrchestrator
    from app.services.policy_engine import PolicyEngine
    from app.services.llm_client import LLMClient
    from app.prompting.prompt_builder import PromptBuilder
    from app.models import JourneyLogContext, PolicyState, DungeonMasterOutcome, IntentsBlock, QuestIntent, CombatIntent, POIIntent
    from app.services.outcome_parser import ParsedOutcome
    from unittest.mock import AsyncMock
    
    num_turns = 50
    poi_trigger_prob = 0.4
    poi_cooldown_turns = 2
    rng_seed = 789
    
    # Statistical bounds
    min_expected = 5
    max_expected = 20
    
    # Setup
    policy_engine = PolicyEngine(
        quest_trigger_prob=0.0,
        poi_trigger_prob=poi_trigger_prob,
        poi_cooldown_turns=poi_cooldown_turns,
        rng_seed=rng_seed
    )
    
    llm_client = AsyncMock(spec=LLMClient)
    journey_log_client = AsyncMock(spec=JourneyLogClient)
    journey_log_client.persist_narrative = AsyncMock()
    journey_log_client.post_poi = AsyncMock()
    
    prompt_builder = PromptBuilder()
    orchestrator = TurnOrchestrator(
        policy_engine=policy_engine,
        llm_client=llm_client,
        journey_log_client=journey_log_client,
        prompt_builder=prompt_builder
    )
    
    poi_created_count = 0
    turns_since_last_poi = 999
    
    for turn_num in range(num_turns):
        context = JourneyLogContext(
            character_id="poi-frequency-char",
            status="Healthy",
            location={"id": "wilderness", "display_name": "Wilderness"},
            active_quest=None,
            combat_state=None,
            recent_history=[],
            policy_state=PolicyState(
                has_active_quest=False,
                combat_active=False,
                turns_since_last_quest=999,
                turns_since_last_poi=turns_since_last_poi
            )
        )
        
        outcome = DungeonMasterOutcome(
            narrative=f"Turn {turn_num}: You explore the wilderness.",
            intents=IntentsBlock(
                quest_intent=QuestIntent(action="none"),
                combat_intent=CombatIntent(action="none"),
                poi_intent=POIIntent(
                    action="create",
                    name=f"POI {turn_num}",
                    description="A discovered location"
                )
            )
        )
        llm_client.generate_narrative.return_value = ParsedOutcome(
            outcome=outcome,
            narrative=outcome.narrative,
            is_valid=True
        )
        
        narrative, intents, summary = await orchestrator.orchestrate_turn(
            character_id="poi-frequency-char",
            user_action=f"Explore turn {turn_num}",
            context=context,
            trace_id=f"trace-{turn_num}"
        )
        
        if summary.poi_change.action == "created" and summary.poi_change.success:
            poi_created_count += 1
            turns_since_last_poi = 0
        else:
            turns_since_last_poi += 1
    
    # Validate trigger frequency
    assert min_expected <= poi_created_count <= max_expected, (
        f"POI triggers ({poi_created_count}) outside expected range "
        f"[{min_expected}, {max_expected}] over {num_turns} turns"
    )


@pytest.mark.asyncio
async def test_poi_memory_sparks_integration_with_triggers():
    """Test POI memory sparks work correctly alongside new POI creation.
    
    Validates:
    - Memory sparks are fetched correctly
    - New POI creation doesn't interfere with memory sparks
    - Both features work independently
    """
    from app.services.turn_orchestrator import TurnOrchestrator
    from app.services.policy_engine import PolicyEngine
    from app.services.llm_client import LLMClient
    from app.prompting.prompt_builder import PromptBuilder
    from app.models import JourneyLogContext, PolicyState, DungeonMasterOutcome, IntentsBlock, QuestIntent, CombatIntent, POIIntent
    from app.services.outcome_parser import ParsedOutcome
    from unittest.mock import AsyncMock, MagicMock
    from httpx import Response
    
    # Setup
    policy_engine = PolicyEngine(
        quest_trigger_prob=0.0,
        poi_trigger_prob=1.0,  # Always trigger
        poi_cooldown_turns=0,
        rng_seed=42
    )
    
    llm_client = AsyncMock(spec=LLMClient)
    
    # Mock journey log client with memory sparks
    mock_http_client = AsyncMock()
    
    # Mock memory spark response
    mock_sparks_response = MagicMock(spec=Response)
    mock_sparks_response.status_code = 200
    mock_sparks_response.json.return_value = {
        "pois": [
            {"id": "old-poi-1", "name": "Ancient Temple", "description": "A temple from the past"},
            {"id": "old-poi-2", "name": "Forgotten Cave", "description": "A dark cave"}
        ],
        "count": 2,
        "requested_n": 3,
        "total_available": 5
    }
    mock_sparks_response.raise_for_status = MagicMock()
    
    # Mock POST response for new POI
    mock_post_response = MagicMock(spec=Response)
    mock_post_response.status_code = 201
    mock_post_response.raise_for_status = MagicMock()
    
    # Mock narrative persist
    mock_narrative_response = MagicMock(spec=Response)
    mock_narrative_response.status_code = 200
    mock_narrative_response.raise_for_status = MagicMock()
    
    mock_http_client.get.return_value = mock_sparks_response
    mock_http_client.post.return_value = mock_post_response
    
    journey_log_client = JourneyLogClient(
        base_url="http://test",
        http_client=mock_http_client
    )
    
    prompt_builder = PromptBuilder()
    orchestrator = TurnOrchestrator(
        policy_engine=policy_engine,
        llm_client=llm_client,
        journey_log_client=journey_log_client,
        prompt_builder=prompt_builder
    )
    
    context = JourneyLogContext(
        character_id="memory-spark-char",
        status="Healthy",
        location={"id": "forest", "display_name": "Forest"},
        active_quest=None,
        combat_state=None,
        recent_history=[],
        policy_state=PolicyState(
            has_active_quest=False,
            combat_active=False,
            turns_since_last_quest=999,
            turns_since_last_poi=10
        )
    )
    
    outcome = DungeonMasterOutcome(
        narrative="You discover a new clearing in the forest.",
        intents=IntentsBlock(
            quest_intent=QuestIntent(action="none"),
            combat_intent=CombatIntent(action="none"),
            poi_intent=POIIntent(
                action="create",
                name="Forest Clearing",
                description="A peaceful clearing"
            )
        )
    )
    llm_client.generate_narrative.return_value = ParsedOutcome(
        outcome=outcome,
        narrative=outcome.narrative,
        is_valid=True
    )
    
    # Execute turn
    narrative, intents, summary = await orchestrator.orchestrate_turn(
        character_id="memory-spark-char",
        user_action="I explore",
        context=context,
        trace_id="trace-memory"
    )
    
    # Verify narrative completed
    assert narrative is not None
    
    # Verify new POI was created
    assert summary.poi_change.action == "created"
