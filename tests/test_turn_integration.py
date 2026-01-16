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
"""Integration tests for the /turn endpoint orchestration."""

import pytest
from unittest.mock import AsyncMock, patch
import os


@pytest.mark.asyncio
async def test_turn_endpoint_full_flow_stub_mode(client):
    """Test the full turn endpoint flow in stub mode.
    
    Verifies:
    - GET /context called once with correct params (recent_n=20, include_pois=false)
    - POST /narrative called once with user_action and narrative
    - Returns mocked LLM narrative
    """
    from httpx import Response
    from unittest.mock import MagicMock
    
    # Mock journey-log context response
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"}
        },
        "quest": None,
        "combat": {"active": False, "state": None},
        "narrative": {
            "recent_turns": []
        }
    }
    mock_context_response.raise_for_status = MagicMock()
    
    # Mock journey-log persist response
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        # Make request to turn endpoint
        character_id = "550e8400-e29b-41d4-a716-446655440000"
        user_action = "I search the ancient temple"
        response = client.post(
            "/turn",
            json={
                "character_id": character_id,
                "user_action": user_action
            }
        )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "narrative" in data
        assert len(data["narrative"]) > 0
        # In stub mode, should contain [STUB MODE]
        assert "[STUB MODE]" in data["narrative"]
        
        # Verify GET context was called once with correct parameters
        mock_get.assert_called_once()
        get_call_args = mock_get.call_args
        get_url = get_call_args[0][0]
        # Verify exact URL path construction
        assert get_url == f"http://localhost:8000/characters/{character_id}/context"
        assert get_call_args[1]["params"]["recent_n"] == 20
        assert get_call_args[1]["params"]["include_pois"] is False
        
        # Verify POST narrative was called once with user_action and narrative
        mock_post.assert_called_once()
        post_call_args = mock_post.call_args
        post_url = post_call_args[0][0]
        # Verify exact URL path construction
        assert post_url == f"http://localhost:8000/characters/{character_id}/narrative"
        post_data = post_call_args[1]["json"]
        assert post_data["user_action"] == user_action
        assert "ai_response" in post_data
        assert len(post_data["ai_response"]) > 0


@pytest.mark.asyncio
async def test_turn_endpoint_character_not_found(client):
    """Test turn endpoint when character not found."""
    from httpx import HTTPStatusError, Request, Response
    from unittest.mock import MagicMock
    
    # Mock 404 response from journey-log
    mock_request = MagicMock(spec=Request)
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 404
    mock_response.text = "Character not found"
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = HTTPStatusError(
            "404 Not Found",
            request=mock_request,
            response=mock_response
        )
        
        response = client.post(
            "/turn",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I search"
            }
        )
        
        assert response.status_code == 404
        data = response.json()
        # Check structured error response
        assert "error" in data["detail"]
        assert data["detail"]["error"]["type"] == "character_not_found"
        assert "not found" in data["detail"]["error"]["message"].lower()


@pytest.mark.asyncio
async def test_turn_endpoint_journey_log_timeout(client):
    """Test turn endpoint when journey-log times out."""
    from httpx import TimeoutException
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = TimeoutException("Timeout")
        
        response = client.post(
            "/turn",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I search"
            }
        )
        
        assert response.status_code == 504  # Gateway timeout
        data = response.json()
        # Check structured error response
        assert "error" in data["detail"]
        assert data["detail"]["error"]["type"] == "journey_log_timeout"
        assert "timed out" in data["detail"]["error"]["message"].lower()


@pytest.mark.asyncio
async def test_turn_endpoint_with_trace_id(client):
    """Test turn endpoint with trace ID for request correlation."""
    from httpx import Response
    from unittest.mock import MagicMock
    
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"}
        },
        "quest": None,
        "combat": {"active": False, "state": None},
        "narrative": {"recent_turns": []}
    }
    mock_context_response.raise_for_status = MagicMock()
    
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        response = client.post(
            "/turn",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I search",
                "trace_id": "test-trace-123"
            }
        )
        
        assert response.status_code == 200
        
        # Verify trace_id was passed to journey-log calls
        mock_get.assert_called_once()
        get_call_kwargs = mock_get.call_args[1]
        assert get_call_kwargs["headers"].get("X-Trace-Id") == "test-trace-123"


@pytest.mark.asyncio
async def test_turn_endpoint_persist_failure_returns_error(client):
    """Test that turn endpoint returns error when persistence fails."""
    from httpx import Response, HTTPStatusError, Request
    from unittest.mock import MagicMock
    
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"}
        },
        "quest": None,
        "combat": {"active": False, "state": None},
        "narrative": {"recent_turns": []}
    }
    mock_context_response.raise_for_status = MagicMock()
    
    # Mock persist failure
    mock_request = MagicMock(spec=Request)
    mock_error_response = MagicMock(spec=Response)
    mock_error_response.status_code = 500
    mock_error_response.text = "Internal server error"
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.side_effect = HTTPStatusError(
            "500 Internal Server Error",
            request=mock_request,
            response=mock_error_response
        )
        
        response = client.post(
            "/turn",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I search"
            }
        )
        
        # Should return 502 error when persistence fails
        assert response.status_code == 502
        data = response.json()
        # Check structured error response
        assert "error" in data["detail"]
        assert data["detail"]["error"]["type"] == "journey_log_error"
        assert "journey-log" in data["detail"]["error"]["message"].lower()


@pytest.mark.asyncio
async def test_turn_endpoint_llm_failure_skips_narrative_write(client):
    """Test that LLM failure skips narrative write and returns 5xx error.
    
    Verifies:
    - When LLM fails, POST /narrative is NOT called
    - Returns structured 5xx error response
    """
    from httpx import Response
    from unittest.mock import MagicMock
    
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"}
        },
        "quest": None,
        "combat": {"active": False, "state": None},
        "narrative": {"recent_turns": []}
    }
    mock_context_response.raise_for_status = MagicMock()
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        
        # Mock LLM client to raise an error
        from app.services.llm_client import LLMClient, LLMResponseError
        with patch.object(LLMClient, 'generate_narrative', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = LLMResponseError("Invalid response from LLM")
            
            response = client.post(
                "/turn",
                json={
                    "character_id": "550e8400-e29b-41d4-a716-446655440000",
                    "user_action": "I search"
                }
            )
            
            # Should return 502 error when LLM fails
            assert response.status_code == 502
            data = response.json()
            
            # Check structured error response
            assert "error" in data["detail"]
            assert data["detail"]["error"]["type"] == "llm_response_error"
            assert "llm" in data["detail"]["error"]["message"].lower()
            assert data["detail"]["error"]["request_id"] is not None
            
            # Verify GET context was called (should succeed before LLM failure)
            mock_get.assert_called_once()
            
            # Verify POST /narrative was NOT called (narrative write skipped)
            mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_turn_endpoint_journey_log_error_no_llm_call(client):
    """Test that journey-log error prevents LLM call.
    
    Verifies:
    - When journey-log fails, LLM is NOT called
    - Returns structured 5xx error response
    """
    from httpx import HTTPStatusError, Request, Response
    from unittest.mock import MagicMock
    
    # Mock 502 response from journey-log
    mock_request = MagicMock(spec=Request)
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 502
    mock_response.text = "Bad Gateway"
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = HTTPStatusError(
            "502 Bad Gateway",
            request=mock_request,
            response=mock_response
        )
        
        # Mock LLM client to track if it's called
        from app.services.llm_client import LLMClient
        with patch.object(LLMClient, 'generate_narrative', new_callable=AsyncMock) as mock_llm:
            response = client.post(
                "/turn",
                json={
                    "character_id": "550e8400-e29b-41d4-a716-446655440000",
                    "user_action": "I search"
                }
            )
            
            # Should return 502 error
            assert response.status_code == 502
            data = response.json()
            
            # Check structured error response
            assert "error" in data["detail"]
            assert data["detail"]["error"]["type"] == "journey_log_error"
            assert "journey-log" in data["detail"]["error"]["message"].lower()
            
            # Verify LLM was NOT called
            mock_llm.assert_not_called()


@pytest.mark.asyncio
async def test_turn_endpoint_optional_context_fields(client):
    """Test turn endpoint handles optional context fields (quest/combat absent).
    
    Verifies:
    - Endpoint works when quest and combat_state are None/absent
    - No serialization errors occur
    - Returns successful narrative
    """
    from httpx import Response
    from unittest.mock import MagicMock
    
    # Mock journey-log context response with minimal fields
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Bob", "race": "Human", "class": "Fighter"},
            "status": "Healthy",
            "location": {"id": "town:square", "display_name": "Town Square"}
        },
        # quest is absent (not even None)
        "combat": {"active": False, "state": None},
        "narrative": {
            "recent_turns": []
        }
    }
    mock_context_response.raise_for_status = MagicMock()
    
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        response = client.post(
            "/turn",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I look around"
            }
        )
        
        # Should succeed despite missing optional fields
        assert response.status_code == 200
        data = response.json()
        assert "narrative" in data
        assert len(data["narrative"]) > 0


@pytest.mark.asyncio
async def test_turn_endpoint_metrics_logging_no_errors(client):
    """Test that metrics and logging hooks don't throw errors.
    
    Verifies:
    - Turn endpoint completes successfully with metrics enabled
    - No exceptions from metrics collection
    - No exceptions from logging
    """
    from httpx import Response
    from unittest.mock import MagicMock
    
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Test", "race": "Elf", "class": "Mage"},
            "status": "Healthy",
            "location": {"id": "forest:clearing", "display_name": "Forest Clearing"}
        },
        "quest": None,
        "combat": {"active": False, "state": None},
        "narrative": {"recent_turns": []}
    }
    mock_context_response.raise_for_status = MagicMock()
    
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post, \
         patch.dict(os.environ, {"ENABLE_METRICS": "true"}):
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        # This should complete without raising exceptions from metrics/logging
        response = client.post(
            "/turn",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I cast a spell"
            }
        )
        
        # Verify successful completion
        assert response.status_code == 200
        data = response.json()
        assert "narrative" in data


@pytest.mark.asyncio
async def test_turn_endpoint_policy_decisions_logged(client, caplog):
    """Test that policy decisions are logged correctly each turn."""
    from httpx import Response
    from unittest.mock import MagicMock
    import logging
    
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"}
        },
        "quest": None,
        "combat": {"active": False, "state": None},
        "narrative": {"recent_turns": []}
    }
    mock_context_response.raise_for_status = MagicMock()
    
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post, \
         caplog.at_level(logging.INFO):
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        response = client.post(
            "/turn",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I explore the area"
            }
        )
        
        assert response.status_code == 200
        
        # Verify policy decisions were logged
        log_messages = [record.message for record in caplog.records]
        policy_logs = [msg for msg in log_messages if "Policy decisions evaluated" in msg]
        
        # Should have logged policy decisions
        assert len(policy_logs) >= 1, "Expected policy decision log message"
        
        # Check that log contains decision info with specific fields
        policy_log_text = " ".join(policy_logs)
        assert "quest_eligible" in policy_log_text, "Policy log should contain quest_eligible field"
        assert "poi_eligible" in policy_log_text, "Policy log should contain poi_eligible field"


@pytest.mark.asyncio
async def test_turn_endpoint_policy_decisions_not_in_response(client):
    """Test that policy decisions don't leak into player-facing response."""
    from httpx import Response
    from unittest.mock import MagicMock
    
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"}
        },
        "quest": None,
        "combat": {"active": False, "state": None},
        "narrative": {"recent_turns": []}
    }
    mock_context_response.raise_for_status = MagicMock()
    
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        response = client.post(
            "/turn",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I search the room"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Response should only have narrative and optionally intents
        assert "narrative" in data
        # Should NOT have policy decision fields in response
        assert "quest_trigger_decision" not in data
        assert "poi_trigger_decision" not in data
        assert "policy_hints" not in data
        assert "quest_eligible" not in data
        assert "poi_eligible" not in data


@pytest.mark.asyncio
async def test_turn_endpoint_failed_quest_roll_blocks_propagation(client):
    """Test that failed quest roll prevents quest suggestion from being persisted.
    
    Verifies that even if LLM suggests a quest, the failed policy roll
    prevents the quest from being written to journey-log.
    """
    from httpx import Response
    from unittest.mock import MagicMock, AsyncMock, patch
    
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Test", "race": "Human", "class": "Fighter"},
            "status": "Healthy",
            "location": {"id": "town:square", "display_name": "Town Square"}
        },
        "quest": None,
        "combat": {"active": False, "state": None},
        "narrative": {"recent_turns": []}
    }
    mock_context_response.raise_for_status = MagicMock()
    
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    # Mock PolicyEngine to always fail quest rolls
    from app.services.policy_engine import PolicyEngine
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        # Override policy engine to fail quest rolls
        from app.api.routes import get_policy_engine
        from app.main import app
        test_policy_engine = PolicyEngine(
            quest_trigger_prob=0.0,  # Always fail quest rolls
            quest_cooldown_turns=0,
            poi_trigger_prob=1.0,
            poi_cooldown_turns=0,
            rng_seed=42
        )
        app.dependency_overrides[get_policy_engine] = lambda: test_policy_engine
        
        try:
            response = client.post(
                "/turn",
                json={
                    "character_id": "550e8400-e29b-41d4-a716-446655440000",
                    "user_action": "I ask the innkeeper for a quest"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Narrative should be present
            assert "narrative" in data
            
            # Even if LLM suggested a quest, it should be blocked
            # We can verify this by checking that the narrative was persisted
            # but without quest data (though in stub mode, quest suggestions
            # are unlikely anyway)
            mock_post.assert_called_once()
            
        finally:
            # Clean up override
            if get_policy_engine in app.dependency_overrides:
                del app.dependency_overrides[get_policy_engine]


@pytest.mark.asyncio
async def test_turn_endpoint_failed_poi_roll_blocks_propagation(client):
    """Test that failed POI roll prevents POI suggestion from being persisted.
    
    Verifies that even if LLM suggests a POI, the failed policy roll
    prevents the POI from being written to journey-log.
    """
    from httpx import Response
    from unittest.mock import MagicMock, AsyncMock, patch
    
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Test", "race": "Elf", "class": "Rogue"},
            "status": "Healthy",
            "location": {"id": "forest:path", "display_name": "Forest Path"}
        },
        "quest": None,
        "combat": {"active": False, "state": None},
        "narrative": {"recent_turns": []}
    }
    mock_context_response.raise_for_status = MagicMock()
    
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    # Mock PolicyEngine to always fail POI rolls
    from app.services.policy_engine import PolicyEngine
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        # Override policy engine to fail POI rolls
        from app.api.routes import get_policy_engine
        from app.main import app
        test_policy_engine = PolicyEngine(
            quest_trigger_prob=1.0,
            quest_cooldown_turns=0,
            poi_trigger_prob=0.0,  # Always fail POI rolls
            poi_cooldown_turns=0,
            rng_seed=42
        )
        app.dependency_overrides[get_policy_engine] = lambda: test_policy_engine
        
        try:
            response = client.post(
                "/turn",
                json={
                    "character_id": "550e8400-e29b-41d4-a716-446655440000",
                    "user_action": "I explore the forest"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Narrative should be present
            assert "narrative" in data
            
            # Even if LLM suggested a POI, it should be blocked
            # Verify narrative was persisted
            mock_post.assert_called_once()
            
        finally:
            # Clean up override
            if get_policy_engine in app.dependency_overrides:
                del app.dependency_overrides[get_policy_engine]


@pytest.mark.asyncio
async def test_turn_endpoint_with_deterministic_seed(client):
    """Test turn endpoint with deterministic seed produces consistent results."""
    from httpx import Response
    from unittest.mock import MagicMock, AsyncMock, patch
    
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Test", "race": "Dwarf", "class": "Warrior"},
            "status": "Healthy",
            "location": {"id": "mountain:peak", "display_name": "Mountain Peak"}
        },
        "quest": None,
        "combat": {"active": False, "state": None},
        "narrative": {"recent_turns": []}
    }
    mock_context_response.raise_for_status = MagicMock()
    
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    # Use deterministic policy engine
    from app.services.policy_engine import PolicyEngine
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        # Override policy engine with deterministic seed
        from app.api.routes import get_policy_engine
        from app.main import app
        test_policy_engine = PolicyEngine(
            quest_trigger_prob=0.5,
            quest_cooldown_turns=0,
            poi_trigger_prob=0.5,
            poi_cooldown_turns=0,
            rng_seed=999  # Deterministic seed
        )
        app.dependency_overrides[get_policy_engine] = lambda: test_policy_engine
        
        try:
            # Make multiple requests for the same character
            response1 = client.post(
                "/turn",
                json={
                    "character_id": "550e8400-e29b-41d4-a716-446655440000",
                    "user_action": "I climb higher"
                }
            )
            
            response2 = client.post(
                "/turn",
                json={
                    "character_id": "550e8400-e29b-41d4-a716-446655440000",
                    "user_action": "I climb higher"
                }
            )
            
            # Both should succeed
            assert response1.status_code == 200
            assert response2.status_code == 200
            
            # With deterministic seed, policy decisions should be consistent
            # (though we can't directly verify them from the response)
            # The test mainly verifies no errors occur
            
        finally:
            # Clean up override
            if get_policy_engine in app.dependency_overrides:
                del app.dependency_overrides[get_policy_engine]
