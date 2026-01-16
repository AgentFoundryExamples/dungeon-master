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
"""Tests for LLMClient service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.llm_client import (
    LLMClient,
    LLMConfigurationError,
    LLMTimeoutError,
    LLMResponseError
)


def test_llm_client_init():
    """Test LLMClient initialization."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        timeout=60,
        stub_mode=False
    )
    
    assert client.model == "gpt-5.1"
    assert client.timeout == 60
    assert not client.stub_mode
    assert client.client is not None


def test_llm_client_init_empty_api_key():
    """Test LLMClient initialization with empty API key."""
    with pytest.raises(LLMConfigurationError, match="API key cannot be empty"):
        LLMClient(api_key="", model="gpt-5.1")


def test_llm_client_stub_mode():
    """Test LLMClient initialization in stub mode."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=True
    )
    
    assert client.stub_mode
    assert client.client is None


@pytest.mark.asyncio
async def test_generate_narrative_stub_mode():
    """Test narrative generation in stub mode."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=True
    )
    
    narrative = await client.generate_narrative(
        system_instructions="You are a game master",
        user_prompt="The player searches the room"
    )
    
    assert "[STUB MODE]" in narrative
    assert "gpt-5.1" in narrative


@pytest.mark.asyncio
async def test_generate_narrative_success():
    """Test successful narrative generation with DungeonMasterOutcome."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    # Mock the OpenAI client response with full DungeonMasterOutcome structure
    mock_output_item = MagicMock()
    mock_output_item.content = '''{
        "narrative": "You discover a hidden treasure chest in the corner.",
        "intents": {
            "quest_intent": {"action": "none"},
            "combat_intent": {"action": "none"},
            "poi_intent": {"action": "none"},
            "meta": null
        }
    }'''
    
    mock_response = MagicMock()
    mock_response.output = [mock_output_item]
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response
        
        narrative = await client.generate_narrative(
            system_instructions="You are a game master",
            user_prompt="The player searches the room"
        )
        
        assert narrative == "You discover a hidden treasure chest in the corner."
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_generate_narrative_empty_output():
    """Test narrative generation with empty output."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    mock_response = MagicMock()
    mock_response.output = []
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response
        
        with pytest.raises(LLMResponseError, match="empty output"):
            await client.generate_narrative(
                system_instructions="You are a game master",
                user_prompt="The player searches the room"
            )


@pytest.mark.asyncio
async def test_generate_narrative_missing_narrative_field():
    """Test narrative generation with missing narrative field."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    mock_output_item = MagicMock()
    mock_output_item.content = '{"other_field": "value"}'
    
    mock_response = MagicMock()
    mock_response.output = [mock_output_item]
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response
        
        with pytest.raises(LLMResponseError, match="validation failed"):
            await client.generate_narrative(
                system_instructions="You are a game master",
                user_prompt="The player searches the room"
            )


@pytest.mark.asyncio
async def test_generate_narrative_timeout():
    """Test narrative generation timeout."""
    import openai
    
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = openai.APITimeoutError(request=MagicMock())
        
        with pytest.raises(LLMTimeoutError, match="timed out"):
            await client.generate_narrative(
                system_instructions="You are a game master",
                user_prompt="The player searches the room"
            )


@pytest.mark.asyncio
async def test_generate_narrative_authentication_error():
    """Test narrative generation with authentication error."""
    import openai
    
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = openai.AuthenticationError(
            message="Invalid API key",
            response=MagicMock(),
            body=None
        )
        
        with pytest.raises(LLMConfigurationError, match="Invalid OpenAI API key"):
            await client.generate_narrative(
                system_instructions="You are a game master",
                user_prompt="The player searches the room"
            )


@pytest.mark.asyncio
async def test_generate_narrative_invalid_json_raises_error():
    """Test narrative generation with invalid JSON response raises error."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    # Mock response with plain text instead of JSON
    # With strict schema enforcement, this should raise an error
    mock_output_item = MagicMock()
    mock_output_item.content = "You discover a hidden treasure chest."
    
    mock_response = MagicMock()
    mock_response.output = [mock_output_item]
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response
        
        # Should raise LLMResponseError since strict schema should prevent non-JSON
        with pytest.raises(LLMResponseError, match="Strict schema enforcement"):
            await client.generate_narrative(
                system_instructions="You are a game master",
                user_prompt="The player searches the room"
            )


@pytest.mark.asyncio
async def test_generate_narrative_uses_dungeon_master_outcome_schema():
    """Test that generate_narrative uses DungeonMasterOutcome schema in API call."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    # Mock successful response
    mock_output_item = MagicMock()
    mock_output_item.content = '''{
        "narrative": "Test narrative",
        "intents": {
            "quest_intent": {"action": "none"},
            "combat_intent": {"action": "none"},
            "poi_intent": {"action": "none"},
            "meta": null
        }
    }'''
    
    mock_response = MagicMock()
    mock_response.output = [mock_output_item]
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response
        
        await client.generate_narrative(
            system_instructions="You are a game master",
            user_prompt="The player searches the room"
        )
        
        # Verify the API call includes the text.format parameter with schema
        call_kwargs = mock_create.call_args.kwargs
        assert "text" in call_kwargs
        assert "format" in call_kwargs["text"]
        assert call_kwargs["text"]["format"]["type"] == "json_schema"
        assert call_kwargs["text"]["format"]["strict"] is True
        assert "schema" in call_kwargs["text"]["format"]
        # Verify schema contains key fields
        schema = call_kwargs["text"]["format"]["schema"]
        assert "narrative" in str(schema)
        assert "intents" in str(schema)


@pytest.mark.asyncio
async def test_generate_narrative_with_full_outcome():
    """Test narrative generation with full DungeonMasterOutcome including intents."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    # Mock response with full outcome including intents
    mock_output_item = MagicMock()
    mock_output_item.content = '''{
        "narrative": "You enter the tavern and meet a grizzled innkeeper.",
        "intents": {
            "quest_intent": {
                "action": "offer",
                "quest_title": "Find My Daughter",
                "quest_summary": "The innkeeper's daughter is missing"
            },
            "combat_intent": {"action": "none"},
            "poi_intent": {
                "action": "create",
                "name": "The Rusty Tankard",
                "description": "A weathered tavern"
            },
            "meta": {
                "player_mood": "curious",
                "pacing_hint": "normal"
            }
        }
    }'''
    
    mock_response = MagicMock()
    mock_response.output = [mock_output_item]
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response
        
        narrative = await client.generate_narrative(
            system_instructions="You are a game master",
            user_prompt="The player enters the tavern"
        )
        
        # Should extract narrative text
        assert narrative == "You enter the tavern and meet a grizzled innkeeper."
        mock_create.assert_called_once()
