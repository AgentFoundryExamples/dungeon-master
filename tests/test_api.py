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
"""Basic tests for Dungeon Master service.

These tests verify the core functionality of the scaffolded service:
- Configuration loading and validation
- Model validation
- API endpoint availability
- OpenAPI documentation generation
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import os


@pytest.fixture
def test_env():
    """Fixture providing test environment variables."""
    return {
        "JOURNEY_LOG_BASE_URL": "http://localhost:8000",
        "OPENAI_API_KEY": "sk-test-key-12345",
        "OPENAI_MODEL": "gpt-4",
        "OPENAI_STUB_MODE": "true",  # Enable stub mode for tests
        "JOURNEY_LOG_TIMEOUT": "30",
        "OPENAI_TIMEOUT": "60",
        "HEALTH_CHECK_JOURNEY_LOG": "false",
        "SERVICE_NAME": "dungeon-master-test",
        "LOG_LEVEL": "INFO"
    }


@pytest.fixture
def client(test_env):
    """Fixture providing FastAPI test client with valid configuration."""
    with patch.dict(os.environ, test_env, clear=True):
        # Clear the settings cache before importing to ensure fresh config
        from app.config import get_settings
        get_settings.cache_clear()
        
        # Import after setting environment to ensure settings load correctly
        from app.main import app
        from httpx import AsyncClient
        from app.services.journey_log_client import JourneyLogClient
        from app.services.llm_client import LLMClient
        
        # Create a test HTTP client for dependency override
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
        
        # Override all dependencies for testing
        from app.api.routes import get_http_client, get_journey_log_client, get_llm_client
        app.dependency_overrides[get_http_client] = lambda: test_http_client
        app.dependency_overrides[get_journey_log_client] = lambda: test_journey_log_client
        app.dependency_overrides[get_llm_client] = lambda: test_llm_client
        
        client = TestClient(app)
        
        yield client
        
        # Cleanup
        app.dependency_overrides.clear()


def test_config_validation_missing_required():
    """Test that configuration fails fast when required variables are missing."""
    from app.config import Settings, get_settings
    from pydantic import ValidationError
    
    # Clear cache to ensure fresh config
    get_settings.cache_clear()
    
    # Try to create settings without required fields
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValidationError):
            Settings(_env_file=None)


def test_config_validation_invalid_url():
    """Test that invalid URL formats are rejected."""
    from app.config import Settings
    from pydantic import ValidationError
    
    with pytest.raises(ValidationError, match="must start with http"):
        Settings(
            journey_log_base_url="invalid-url",
            openai_api_key="sk-test"
        )


def test_model_validation_invalid_character_id():
    """Test that TurnRequest rejects invalid UUID formats."""
    from app.models import TurnRequest
    from pydantic import ValidationError
    
    with pytest.raises(ValidationError, match="valid UUID"):
        TurnRequest(
            character_id="not-a-uuid",
            user_action="I search the room"
        )


def test_model_validation_valid_uuid():
    """Test that TurnRequest accepts valid UUID."""
    from app.models import TurnRequest
    
    request = TurnRequest(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        user_action="I search the room"
    )
    assert request.character_id == "550e8400-e29b-41d4-a716-446655440000"


def test_health_endpoint(client):
    """Test that health endpoint returns expected response."""
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ["healthy", "degraded"]
    assert "service" in data  # Service name is present


def test_turn_endpoint_validation(client):
    """Test that turn endpoint validates request."""
    from httpx import Response
    from unittest.mock import MagicMock, patch, AsyncMock
    
    # Mock journey-log responses for valid test
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Test", "race": "Human", "class": "Warrior"},
            "status": "Healthy",
            "location": {"id": "test:loc", "display_name": "Test Location"}
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
        
        # Valid request with UUID
        response = client.post(
            "/turn",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I search the room"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "narrative" in data
    
    # Invalid request with bad UUID
    response = client.post(
        "/turn",
        json={
            "character_id": "not-a-uuid",
            "user_action": "I search the room"
        }
    )
    assert response.status_code == 422  # Validation error


def test_openapi_docs_available(client):
    """Test that OpenAPI documentation is accessible."""
    # OpenAPI schema
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "paths" in schema
    assert "/turn" in schema["paths"]
    assert "/health" in schema["paths"]
    
    # Swagger UI
    response = client.get("/docs")
    assert response.status_code == 200
    
    # ReDoc
    response = client.get("/redoc")
    assert response.status_code == 200


def test_turn_request_optional_trace_id():
    """Test that trace_id is optional in TurnRequest."""
    from app.models import TurnRequest
    
    # Without trace_id
    request = TurnRequest(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        user_action="I search"
    )
    assert request.trace_id is None
    
    # With trace_id
    request = TurnRequest(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        user_action="I search",
        trace_id="trace-123"
    )
    assert request.trace_id == "trace-123"


def test_health_response_journey_log_field():
    """Test that HealthResponse properly handles journey_log_accessible field."""
    from app.models import HealthResponse
    
    # Without journey_log check
    response = HealthResponse(
        status="healthy",
        service="test"
    )
    assert response.journey_log_accessible is None
    
    # With journey_log check
    response = HealthResponse(
        status="healthy",
        service="test",
        journey_log_accessible=True
    )
    assert response.journey_log_accessible is True
