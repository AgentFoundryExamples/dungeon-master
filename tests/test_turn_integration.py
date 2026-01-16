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
    """Test the full turn endpoint flow in stub mode."""
    from httpx import Response, Request
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
        response = client.post(
            "/turn",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I search the ancient temple"
            }
        )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "narrative" in data
        assert len(data["narrative"]) > 0
        # In stub mode, should contain [STUB MODE]
        assert "[STUB MODE]" in data["narrative"]


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
        assert "not found" in data["detail"].lower()


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
        assert "timed out" in data["detail"].lower()


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
        assert "journey-log" in data["detail"].lower()
