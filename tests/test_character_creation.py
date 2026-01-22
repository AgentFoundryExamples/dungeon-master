
from unittest.mock import AsyncMock, Mock, patch
import pytest
from app.models import CharacterCreationRequest, TurnResponse, CharacterCreationResponse
from app.services.turn_orchestrator import TurnOrchestrator
from app.services.journey_log_client import JourneyLogClient
from app.api.routes import create_character
from app.config import Settings

@pytest.mark.asyncio
async def test_journey_log_client_create_character():
    """Test JourneyLogClient.create_character."""
    mock_http_client = AsyncMock()
    client = JourneyLogClient(base_url="http://test", http_client=mock_http_client)
    
    # Mock successful response
    mock_response = AsyncMock() # This makes methods async by default if not specified? 
    # Use Mock for the response object itself but keep in mind it's returned by an async call.
    mock_response = Mock() 
    mock_response.status_code = 201
    mock_response.json.return_value = {"character_id": "char-123"}
    mock_response.raise_for_status = Mock() # Synchronous method
    
    mock_http_client.post.return_value = mock_response
    
    result = await client.create_character(
        name="Hero",
        race="Human",
        class_name="Warrior",
        custom_prompt="Dark world",
        user_id="user-123"
    )
    
    assert result["character_id"] == "char-123"
    mock_http_client.post.assert_called_once()
    call_args = mock_http_client.post.call_args
    assert call_args[1]["json"]["name"] == "Hero"
    assert call_args[1]["headers"]["X-User-Id"] == "user-123"

@pytest.mark.asyncio
async def test_turn_orchestrator_orchestrate_intro():
    """Test TurnOrchestrator.orchestrate_intro."""
    mock_policy_engine = Mock()
    mock_llm_client = AsyncMock()
    mock_journey_log_client = AsyncMock()
    mock_prompt_builder = Mock()
    
    orchestrator = TurnOrchestrator(
        policy_engine=mock_policy_engine,
        llm_client=mock_llm_client,
        journey_log_client=mock_journey_log_client,
        prompt_builder=mock_prompt_builder
    )
    
    # Mock dependencies
    mock_journey_log_client.create_character.return_value = {"character_id": "char-123"}
    mock_prompt_builder.build_intro_prompt.return_value = ("Sys", "User")
    
    mock_parsed_outcome = Mock()
    mock_parsed_outcome.narrative = "Welcome hero..."
    mock_llm_client.generate_narrative.return_value = mock_parsed_outcome
    
    narrative, char_data = await orchestrator.orchestrate_intro(
        name="Hero",
        race="Human",
        class_name="Warrior",
        user_id="user-123"
    )
    
    assert narrative == "Welcome hero..."
    assert char_data["character_id"] == "char-123"
    
    # Verify sequence
    mock_journey_log_client.create_character.assert_awaited_once()
    mock_llm_client.generate_narrative.assert_awaited_once()
    mock_journey_log_client.persist_narrative.assert_awaited_once_with(
        character_id="char-123",
        user_action="Begins their journey.",
        narrative="Welcome hero...",
        user_id="user-123"
    )

@pytest.mark.asyncio
async def test_create_character_route_handler():
    """Test the API route handler logic directly."""
    # Mock dependencies
    request = CharacterCreationRequest(
        name="Hero",
        race="Human",
        class_name="Warrior"
    )
    user_id = "user-123"
    mock_orchestrator = AsyncMock()
    mock_orchestrator.orchestrate_intro.return_value = ("Intro narrative", {"character_id": "char-123"})
    mock_rate_limiter = AsyncMock()
    mock_settings = Mock()
    
    response = await create_character(
        request=request,
        user_id=user_id,
        turn_orchestrator=mock_orchestrator,
        character_rate_limiter=mock_rate_limiter
    )
    
    assert isinstance(response, CharacterCreationResponse)
    assert response.character_id == "char-123"
    assert response.narrative == "Intro narrative"
    mock_rate_limiter.acquire.assert_awaited_once_with("user-123")
