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
from unittest.mock import patch, MagicMock, AsyncMock
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
        from app.services.policy_engine import PolicyEngine
        from app.services.turn_orchestrator import TurnOrchestrator
        from app.prompting.prompt_builder import PromptBuilder
        
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
        test_policy_engine = PolicyEngine(
            quest_trigger_prob=settings.quest_trigger_prob,
            quest_cooldown_turns=settings.quest_cooldown_turns,
            poi_trigger_prob=settings.poi_trigger_prob,
            poi_cooldown_turns=settings.poi_cooldown_turns,
            rng_seed=settings.rng_seed
        )
        test_prompt_builder = PromptBuilder()
        test_turn_orchestrator = TurnOrchestrator(
            policy_engine=test_policy_engine,
            llm_client=test_llm_client,
            journey_log_client=test_journey_log_client,
            prompt_builder=test_prompt_builder
        )
        
        # Override all dependencies for testing
        from app.api.routes import (
            get_http_client,
            get_journey_log_client,
            get_llm_client,
            get_policy_engine,
            get_http_client,
            get_journey_log_client,
            get_llm_client,
            get_policy_engine,
            get_turn_orchestrator,
            get_character_rate_limiter,
            get_llm_semaphore
        )
        from app.api.deps import get_current_user_id
        app.dependency_overrides[get_http_client] = lambda: test_http_client
        app.dependency_overrides[get_journey_log_client] = lambda: test_journey_log_client
        app.dependency_overrides[get_llm_client] = lambda: test_llm_client
        app.dependency_overrides[get_policy_engine] = lambda: test_policy_engine
        app.dependency_overrides[get_policy_engine] = lambda: test_policy_engine
        app.dependency_overrides[get_turn_orchestrator] = lambda: test_turn_orchestrator
        
        # Mock rate limiter and semaphore
        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock(return_value=True)
        app.dependency_overrides[get_character_rate_limiter] = lambda: mock_rate_limiter
        
        mock_semaphore = MagicMock()
        mock_semaphore.__aenter__ = AsyncMock(return_value=None)
        mock_semaphore.__aexit__ = AsyncMock(return_value=None)
        app.dependency_overrides[get_llm_semaphore] = lambda: mock_semaphore
        
        # Mock auth dependency to bypass Firebase authentication
        app.dependency_overrides[get_current_user_id] = lambda: "test-user-123"
        
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
            headers={"X-User-Id": "user-123"},
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


def test_turn_response_includes_intents(client):
    """Test that /turn endpoint returns intents when LLM response is valid."""
    from httpx import Response
    from unittest.mock import MagicMock, patch, AsyncMock
    
    # Mock journey-log responses
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
        
        # Make request
        response = client.post(
            "/turn",
            headers={"X-User-Id": "user-123"},
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I search the room"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have narrative
        assert "narrative" in data
        assert data["narrative"]
        
        # Should have intents (stub mode generates valid intents)
        assert "intents" in data
        assert data["intents"] is not None
        assert "quest_intent" in data["intents"]
        assert "combat_intent" in data["intents"]
        assert "poi_intent" in data["intents"]


def test_turn_response_intents_null_on_invalid_llm_response(client):
    """Test that /turn endpoint returns null intents when LLM response is invalid."""
    from httpx import Response
    from unittest.mock import MagicMock, patch, AsyncMock
    from app.services.llm_client import LLMClient
    from app.services.policy_engine import PolicyEngine
    from app.services.journey_log_client import JourneyLogClient
    from app.services.turn_orchestrator import TurnOrchestrator
    from app.services.outcome_parser import ParsedOutcome
    from app.prompting.prompt_builder import PromptBuilder
    from httpx import AsyncClient
    
    # Mock journey-log responses
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
    
    # Mock LLM client to return invalid ParsedOutcome
    mock_llm_client = MagicMock(spec=LLMClient)
    mock_llm_client.generate_narrative = AsyncMock(return_value=ParsedOutcome(
        outcome=None,
        narrative="Fallback narrative from invalid JSON",
        is_valid=False,
        error_type="json_decode_error",
        error_details=["Invalid JSON"]
    ))
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        # Create custom orchestrator with mocked LLM client
        from app.config import get_settings
        settings = get_settings()
        
        test_http_client = AsyncClient()
        test_journey_log_client = JourneyLogClient(
            base_url=settings.journey_log_base_url,
            http_client=test_http_client,
            timeout=settings.journey_log_timeout
        )
        test_policy_engine = PolicyEngine(
            quest_trigger_prob=0.5,
            poi_trigger_prob=0.5
        )
        test_prompt_builder = PromptBuilder()
        test_orchestrator = TurnOrchestrator(
            policy_engine=test_policy_engine,
            llm_client=mock_llm_client,  # Use mocked LLM client
            journey_log_client=test_journey_log_client,
            prompt_builder=test_prompt_builder
        )
        
        # Override orchestrator dependency
        from app.api.routes import get_turn_orchestrator, get_http_client, get_journey_log_client
        from app.main import app
        app.dependency_overrides[get_turn_orchestrator] = lambda: test_orchestrator
        app.dependency_overrides[get_http_client] = lambda: test_http_client
        app.dependency_overrides[get_journey_log_client] = lambda: test_journey_log_client
        
        try:
            # Make request
            response = client.post(
                "/turn",
                headers={"X-User-Id": "user-123"},
                json={
                    "character_id": "550e8400-e29b-41d4-a716-446655440000",
                    "user_action": "I search the room"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Should have fallback narrative
            assert "narrative" in data
            assert data["narrative"] == "Fallback narrative from invalid JSON"
            
            # intents should be null when LLM response is invalid
            assert "intents" in data
            assert data["intents"] is None
        finally:
            # Clean up dependency overrides
            app.dependency_overrides.pop(get_turn_orchestrator, None)
            app.dependency_overrides.pop(get_http_client, None)
            app.dependency_overrides.pop(get_journey_log_client, None)

def test_turn_response_model_with_intents():
    """Test that TurnResponse model accepts intents field."""
    from app.models import TurnResponse, IntentsBlock, QuestIntent, CombatIntent, POIIntent
    
    # Response without intents
    response = TurnResponse(
        narrative="Test narrative"
    )
    assert response.narrative == "Test narrative"
    assert response.intents is None
    
    # Response with intents
    intents = IntentsBlock(
        quest_intent=QuestIntent(action="offer", quest_title="Test Quest"),
        combat_intent=CombatIntent(action="none"),
        poi_intent=POIIntent(action="none"),
        meta=None
    )
    response = TurnResponse(
        narrative="Test narrative",
        intents=intents
    )
    assert response.narrative == "Test narrative"
    assert response.intents is not None
    assert response.intents.quest_intent.action == "offer"


def test_debug_parse_llm_endpoint_disabled(client):
    """Test that /debug/parse_llm returns 404 when disabled."""
    response = client.post(
        "/debug/parse_llm",
        json={
            "llm_response": '{"narrative": "test", "intents": {}}'
        }
    )
    assert response.status_code == 404


def test_debug_parse_llm_endpoint_enabled(test_env):
    """Test that /debug/parse_llm works when enabled."""
    import os
    from unittest.mock import patch
    
    # Enable debug endpoints
    test_env["ENABLE_DEBUG_ENDPOINTS"] = "true"
    
    with patch.dict(os.environ, test_env, clear=True):
        from app.config import get_settings
        get_settings.cache_clear()
        
        from app.main import app
        from fastapi.testclient import TestClient
        from httpx import AsyncClient
        from app.services.journey_log_client import JourneyLogClient
        from app.services.llm_client import LLMClient
        
        test_http_client = AsyncClient()
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
            stub_mode=True
        )
        
        from app.api.routes import get_http_client, get_journey_log_client, get_llm_client
        app.dependency_overrides[get_http_client] = lambda: test_http_client
        app.dependency_overrides[get_journey_log_client] = lambda: test_journey_log_client
        app.dependency_overrides[get_llm_client] = lambda: test_llm_client
        
        test_client = TestClient(app)
        
        try:
            # Test with valid JSON
            valid_response = {
                "narrative": "You discover a treasure chest.",
                "intents": {
                    "quest_intent": {"action": "none"},
                    "combat_intent": {"action": "none"},
                    "poi_intent": {"action": "create", "name": "Hidden Room"},
                    "meta": {"player_mood": "excited"}
                }
            }
            
            import json
            response = test_client.post(
                "/debug/parse_llm",
                json={
                    "llm_response": json.dumps(valid_response)
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["is_valid"] is True
            assert data["has_outcome"] is True
            assert data["narrative"] == "You discover a treasure chest."
            assert data["intents_summary"]["has_poi_intent"] is True
            assert data["error_type"] is None
            
            # Test with invalid JSON
            response = test_client.post(
                "/debug/parse_llm",
                json={
                    "llm_response": "not valid json"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["is_valid"] is False
            assert data["has_outcome"] is False
            assert data["error_type"] == "json_decode_error"
            assert data["error_details"] is not None
        finally:
            app.dependency_overrides.clear()


def test_debug_parse_llm_endpoint_missing_field(test_env):
    """Test that /debug/parse_llm requires llm_response field."""
    import os
    from unittest.mock import patch
    
    test_env["ENABLE_DEBUG_ENDPOINTS"] = "true"
    
    with patch.dict(os.environ, test_env, clear=True):
        from app.config import get_settings
        get_settings.cache_clear()
        
        from app.main import app
        from fastapi.testclient import TestClient
        from httpx import AsyncClient
        from app.services.journey_log_client import JourneyLogClient
        from app.services.llm_client import LLMClient
        
        test_http_client = AsyncClient()
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
            stub_mode=True
        )
        
        from app.api.routes import get_http_client, get_journey_log_client, get_llm_client
        app.dependency_overrides[get_http_client] = lambda: test_http_client
        app.dependency_overrides[get_journey_log_client] = lambda: test_journey_log_client
        app.dependency_overrides[get_llm_client] = lambda: test_llm_client
        
        test_client = TestClient(app)
        
        try:
            response = test_client.post(
                "/debug/parse_llm",
                json={}
            )
            
            # Pydantic validation returns 422 for missing required fields
            assert response.status_code == 422
            response_data = response.json()
            # Check that the error details mention llm_response
            assert "detail" in response_data
        finally:
            app.dependency_overrides.clear()
