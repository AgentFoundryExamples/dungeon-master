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
from app.services.outcome_parser import ParsedOutcome


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
    
    result = await client.generate_narrative(
        system_instructions="You are a game master",
        user_prompt="The player searches the room"
    )
    
    assert isinstance(result, ParsedOutcome)
    assert result.is_valid
    assert result.outcome is not None
    assert "[STUB MODE]" in result.narrative
    assert "gpt-5.1" in result.narrative


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
        
        result = await client.generate_narrative(
            system_instructions="You are a game master",
            user_prompt="The player searches the room"
        )
        
        assert isinstance(result, ParsedOutcome)
        assert result.is_valid
        assert result.outcome is not None
        assert result.narrative == "You discover a hidden treasure chest in the corner."
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
    """Test narrative generation with missing narrative field returns fallback."""
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
        
        result = await client.generate_narrative(
            system_instructions="You are a game master",
            user_prompt="The player searches the room"
        )
        
        # Should return ParsedOutcome with fallback narrative
        assert isinstance(result, ParsedOutcome)
        assert not result.is_valid
        assert result.outcome is None
        assert result.error_type == "validation_error"
        assert result.narrative  # Fallback narrative should be present


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
    """Test narrative generation with invalid JSON returns fallback."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    # Mock response with plain text instead of JSON
    mock_output_item = MagicMock()
    mock_output_item.content = "You discover a hidden treasure chest."
    
    mock_response = MagicMock()
    mock_response.output = [mock_output_item]
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response
        
        result = await client.generate_narrative(
            system_instructions="You are a game master",
            user_prompt="The player searches the room"
        )
        
        # Should return ParsedOutcome with fallback narrative
        assert isinstance(result, ParsedOutcome)
        assert not result.is_valid
        assert result.outcome is None
        assert result.error_type == "json_decode_error"
        assert "You discover a hidden treasure chest." in result.narrative


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
        
        result = await client.generate_narrative(
            system_instructions="You are a game master",
            user_prompt="The player enters the tavern"
        )
        
        # Should return valid ParsedOutcome with full intents
        assert isinstance(result, ParsedOutcome)
        assert result.is_valid
        assert result.outcome is not None
        assert result.narrative == "You enter the tavern and meet a grizzled innkeeper."
        assert result.outcome.intents.quest_intent is not None
        assert result.outcome.intents.quest_intent.action == "offer"
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_generate_narrative_with_provided_schema():
    """Test that generate_narrative uses provided schema instead of regenerating."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    # Mock successful response
    mock_output_item = MagicMock()
    mock_output_item.content = '''{
        "narrative": "Test narrative with provided schema",
        "intents": {
            "quest_intent": {"action": "none"},
            "combat_intent": {"action": "none"},
            "poi_intent": {"action": "none"},
            "meta": null
        }
    }'''
    
    mock_response = MagicMock()
    mock_response.output = [mock_output_item]
    
    # Pre-generate schema once
    from app.models import get_outcome_json_schema
    pre_generated_schema = get_outcome_json_schema()
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response
        
        # Call with provided schema
        result = await client.generate_narrative(
            system_instructions="You are a game master",
            user_prompt="The player searches",
            json_schema=pre_generated_schema
        )
        
        # Verify narrative extracted correctly
        assert isinstance(result, ParsedOutcome)
        assert result.is_valid
        assert result.narrative == "Test narrative with provided schema"
        
        # Verify the provided schema was used in the API call
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["text"]["format"]["schema"] == pre_generated_schema


# ============================================================================
# Streaming Tests
# ============================================================================


@pytest.mark.asyncio
async def test_generate_narrative_stream_stub_mode():
    """Test streaming narrative generation in stub mode."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=True
    )
    
    tokens = []
    
    def callback(token: str):
        tokens.append(token)
    
    result = await client.generate_narrative_stream(
        system_instructions="You are a game master",
        user_prompt="The player searches the room",
        callback=callback
    )
    
    assert isinstance(result, ParsedOutcome)
    assert result.is_valid
    assert result.outcome is not None
    assert "[STUB MODE]" in result.narrative
    assert len(tokens) == 1
    assert tokens[0] == result.narrative


@pytest.mark.asyncio
async def test_generate_narrative_stream_success():
    """Test successful streaming narrative generation."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    tokens = []
    
    def callback(token: str):
        tokens.append(token)
    
    # Mock streaming response
    async def mock_stream():
        # Simulate streaming chunks that form valid JSON
        chunks = [
            '{"narrative": "You discover ',
            'a hidden treasure chest ',
            'in the corner.", ',
            '"intents": {"quest_intent": {"action": "none"}, ',
            '"combat_intent": {"action": "none"}, ',
            '"poi_intent": {"action": "none"}, ',
            '"meta": null}}'
        ]
        
        for chunk in chunks:
            mock_chunk = MagicMock()
            mock_output_item = MagicMock()
            mock_output_item.content_delta = chunk
            mock_chunk.output = [mock_output_item]
            yield mock_chunk
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_stream()
        
        result = await client.generate_narrative_stream(
            system_instructions="You are a game master",
            user_prompt="The player searches the room",
            callback=callback
        )
        
        # Verify ParsedOutcome
        assert isinstance(result, ParsedOutcome)
        assert result.is_valid
        assert result.outcome is not None
        assert result.narrative == "You discover a hidden treasure chest in the corner."
        
        # Verify tokens were received - should be 7 chunks total
        assert len(tokens) == 7
        assert ''.join(tokens) == '{"narrative": "You discover a hidden treasure chest in the corner.", "intents": {"quest_intent": {"action": "none"}, "combat_intent": {"action": "none"}, "poi_intent": {"action": "none"}, "meta": null}}'


@pytest.mark.asyncio
async def test_generate_narrative_stream_no_callback():
    """Test streaming without callback still buffers and returns outcome."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    # Mock streaming response
    async def mock_stream():
        chunks = [
            '{"narrative": "Test narrative", ',
            '"intents": {"quest_intent": {"action": "none"}, ',
            '"combat_intent": {"action": "none"}, ',
            '"poi_intent": {"action": "none"}, ',
            '"meta": null}}'
        ]
        
        for chunk in chunks:
            mock_chunk = MagicMock()
            mock_output_item = MagicMock()
            mock_output_item.content_delta = chunk
            mock_chunk.output = [mock_output_item]
            yield mock_chunk
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_stream()
        
        result = await client.generate_narrative_stream(
            system_instructions="You are a game master",
            user_prompt="The player searches the room"
        )
        
        assert isinstance(result, ParsedOutcome)
        assert result.is_valid
        assert result.narrative == "Test narrative"


@pytest.mark.asyncio
async def test_generate_narrative_stream_callback_exception():
    """Test that callback exceptions are logged but don't interrupt streaming."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    call_count = [0]
    
    def faulty_callback(token: str):
        call_count[0] += 1
        if call_count[0] == 2:
            raise ValueError("Callback error")
    
    # Mock streaming response
    async def mock_stream():
        chunks = [
            '{"narrative": "Test narrative", ',
            '"intents": {"quest_intent": {"action": "none"}, ',
            '"combat_intent": {"action": "none"}, ',
            '"poi_intent": {"action": "none"}, ',
            '"meta": null}}'
        ]
        
        for chunk in chunks:
            mock_chunk = MagicMock()
            mock_output_item = MagicMock()
            mock_output_item.content_delta = chunk
            mock_chunk.output = [mock_output_item]
            yield mock_chunk
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_stream()
        
        # Should complete successfully despite callback error
        result = await client.generate_narrative_stream(
            system_instructions="You are a game master",
            user_prompt="The player searches the room",
            callback=faulty_callback
        )
        
        assert isinstance(result, ParsedOutcome)
        assert result.is_valid
        # Verify callback was called multiple times
        assert call_count[0] >= 2


@pytest.mark.asyncio
async def test_generate_narrative_stream_empty_response():
    """Test streaming with empty response."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    # Mock empty streaming response
    async def mock_stream():
        # Empty generator that yields nothing
        if False:
            yield  # Make it a generator but never execute
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_stream()
        
        with pytest.raises(LLMResponseError, match="empty content"):
            await client.generate_narrative_stream(
                system_instructions="You are a game master",
                user_prompt="The player searches the room"
            )


@pytest.mark.asyncio
async def test_generate_narrative_stream_invalid_json():
    """Test streaming with invalid JSON returns fallback."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    # Mock streaming response with invalid JSON
    async def mock_stream():
        chunks = ["This is not ", "valid JSON ", "at all"]
        
        for chunk in chunks:
            mock_chunk = MagicMock()
            mock_output_item = MagicMock()
            mock_output_item.content_delta = chunk
            mock_chunk.output = [mock_output_item]
            yield mock_chunk
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_stream()
        
        result = await client.generate_narrative_stream(
            system_instructions="You are a game master",
            user_prompt="The player searches the room"
        )
        
        # Should return ParsedOutcome with fallback narrative
        assert isinstance(result, ParsedOutcome)
        assert not result.is_valid
        assert result.outcome is None
        assert result.error_type == "json_decode_error"
        assert "This is not valid JSON at all" in result.narrative


@pytest.mark.asyncio
async def test_generate_narrative_stream_missing_narrative_field():
    """Test streaming with missing narrative field uses fallback."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    # Mock streaming response missing narrative field
    async def mock_stream():
        chunks = [
            '{"intents": {"quest_intent": {"action": "none"}, ',
            '"combat_intent": {"action": "none"}, ',
            '"poi_intent": {"action": "none"}}}'
        ]
        
        for chunk in chunks:
            mock_chunk = MagicMock()
            mock_output_item = MagicMock()
            mock_output_item.content_delta = chunk
            mock_chunk.output = [mock_output_item]
            yield mock_chunk
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_stream()
        
        result = await client.generate_narrative_stream(
            system_instructions="You are a game master",
            user_prompt="The player searches the room"
        )
        
        # Should return ParsedOutcome with fallback narrative
        assert isinstance(result, ParsedOutcome)
        assert not result.is_valid
        assert result.outcome is None
        assert result.error_type == "validation_error"
        assert result.narrative  # Fallback narrative should be present


@pytest.mark.asyncio
async def test_generate_narrative_stream_timeout():
    """Test streaming timeout."""
    import openai
    
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = openai.APITimeoutError(request=MagicMock())
        
        with pytest.raises(LLMTimeoutError, match="timed out"):
            await client.generate_narrative_stream(
                system_instructions="You are a game master",
                user_prompt="The player searches the room"
            )


@pytest.mark.asyncio
async def test_generate_narrative_stream_authentication_error():
    """Test streaming with authentication error."""
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
            await client.generate_narrative_stream(
                system_instructions="You are a game master",
                user_prompt="The player searches the room"
            )


@pytest.mark.asyncio
async def test_generate_narrative_stream_with_full_outcome():
    """Test streaming with full DungeonMasterOutcome including intents."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    # Mock streaming response with full outcome
    async def mock_stream():
        chunks = [
            '{"narrative": "You enter the tavern and meet a grizzled innkeeper.", ',
            '"intents": {',
            '"quest_intent": {"action": "offer", "quest_title": "Find My Daughter", ',
            '"quest_summary": "The innkeeper\'s daughter is missing"}, ',
            '"combat_intent": {"action": "none"}, ',
            '"poi_intent": {"action": "create", "name": "The Rusty Tankard", ',
            '"description": "A weathered tavern"}, ',
            '"meta": {"player_mood": "curious", "pacing_hint": "normal"}}}'
        ]
        
        for chunk in chunks:
            mock_chunk = MagicMock()
            mock_output_item = MagicMock()
            mock_output_item.content_delta = chunk
            mock_chunk.output = [mock_output_item]
            yield mock_chunk
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_stream()
        
        result = await client.generate_narrative_stream(
            system_instructions="You are a game master",
            user_prompt="The player enters the tavern"
        )
        
        # Should return valid ParsedOutcome with full intents
        assert isinstance(result, ParsedOutcome)
        assert result.is_valid
        assert result.outcome is not None
        assert result.narrative == "You enter the tavern and meet a grizzled innkeeper."
        assert result.outcome.intents.quest_intent is not None
        assert result.outcome.intents.quest_intent.action == "offer"
        assert result.outcome.intents.poi_intent is not None
        assert result.outcome.intents.poi_intent.action == "create"


@pytest.mark.asyncio
async def test_generate_narrative_stream_with_trace_id():
    """Test streaming with trace_id for correlation."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    # Mock streaming response
    async def mock_stream():
        chunks = [
            '{"narrative": "Test with trace", ',
            '"intents": {"quest_intent": {"action": "none"}, ',
            '"combat_intent": {"action": "none"}, ',
            '"poi_intent": {"action": "none"}, ',
            '"meta": null}}'
        ]
        
        for chunk in chunks:
            mock_chunk = MagicMock()
            mock_output_item = MagicMock()
            mock_output_item.content_delta = chunk
            mock_chunk.output = [mock_output_item]
            yield mock_chunk
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_stream()
        
        result = await client.generate_narrative_stream(
            system_instructions="You are a game master",
            user_prompt="The player searches",
            trace_id="test-trace-123"
        )
        
        assert isinstance(result, ParsedOutcome)
        assert result.is_valid
        assert result.narrative == "Test with trace"


@pytest.mark.asyncio
async def test_generate_narrative_stream_handles_content_format():
    """Test streaming handles different content formats (delta vs full)."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    # Mock streaming response with 'content' field instead of 'content_delta'
    async def mock_stream():
        chunks = [
            '{"narrative": "Test narrative", ',
            '"intents": {"quest_intent": {"action": "none"}, ',
            '"combat_intent": {"action": "none"}, ',
            '"poi_intent": {"action": "none"}, ',
            '"meta": null}}'
        ]
        
        for chunk in chunks:
            mock_chunk = MagicMock()
            # Create a simple object with only 'content' attribute
            mock_output_item = type('OutputItem', (), {'content': chunk})()
            mock_chunk.output = [mock_output_item]
            yield mock_chunk
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_stream()
        
        result = await client.generate_narrative_stream(
            system_instructions="You are a game master",
            user_prompt="The player searches the room"
        )
        
        assert isinstance(result, ParsedOutcome)
        assert result.is_valid
