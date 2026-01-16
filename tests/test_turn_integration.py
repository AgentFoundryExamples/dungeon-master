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
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
import os


@pytest.fixture
def test_env():
    """Fixture providing test environment variables."""
    return {
        "JOURNEY_LOG_BASE_URL": "http://localhost:8000",
        "OPENAI_API_KEY": "sk-test-key-12345",
        "OPENAI_MODEL": "gpt-5.1",
        "OPENAI_STUB_MODE": "true",  # Use stub mode for tests
        "JOURNEY_LOG_TIMEOUT": "30",
        "OPENAI_TIMEOUT": "60",
        "JOURNEY_LOG_RECENT_N": "20",
        "HEALTH_CHECK_JOURNEY_LOG": "false",
        "SERVICE_NAME": "dungeon-master-test",
        "LOG_LEVEL": "INFO"
    }


@pytest.fixture
def client(test_env):
    """Fixture providing FastAPI test client with mocked dependencies."""
    with patch.dict(os.environ, test_env, clear=True):
        # Clear the settings cache
        from app.config import get_settings
        get_settings.cache_clear()
        
        from app.main import app
        from httpx import AsyncClient
        from app.services.journey_log_client import JourneyLogClient
        from app.services.llm_client import LLMClient
        
        # Create test HTTP client
        test_http_client = AsyncClient()
        
        # Create test service clients
        settings = get_settings()
        test_journey_log_client = JourneyLogClient(
            base_url=settings.journey_log_base_url,
            http_client=test_http_client,
            timeout=settings.journey_log_timeout,
            recent_n_default=settings.journey_log_recent_n
        )
        test_llm_client = LLMClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout=settings.openai_timeout,
            stub_mode=True  # Always use stub mode in tests
        )
        
        # Override all dependencies
        from app.api.routes import get_http_client, get_journey_log_client, get_llm_client
        app.dependency_overrides[get_http_client] = lambda: test_http_client
        app.dependency_overrides[get_journey_log_client] = lambda: test_journey_log_client
        app.dependency_overrides[get_llm_client] = lambda: test_llm_client
        
        client = TestClient(app)
        
        yield client
        
        # Cleanup
        app.dependency_overrides.clear()


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
        assert f"/characters/{character_id}/context" in get_call_args[0][0]
        assert get_call_args[1]["params"]["recent_n"] == 20
        assert get_call_args[1]["params"]["include_pois"] is False
        
        # Verify POST narrative was called once with user_action and narrative
        mock_post.assert_called_once()
        post_call_args = mock_post.call_args
        assert f"/characters/{character_id}/narrative" in post_call_args[0][0]
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
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
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
