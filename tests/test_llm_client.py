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
    LLMResponseError,
    LLMClientError
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
    assert client.stub_mode == False
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
    
    assert client.stub_mode == True
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
    """Test successful narrative generation."""
    client = LLMClient(
        api_key="sk-test-key",
        model="gpt-5.1",
        stub_mode=False
    )
    
    # Mock the OpenAI client response
    mock_output_item = MagicMock()
    mock_output_item.content = '{"narrative": "You discover a hidden treasure chest in the corner."}'
    
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
        
        with pytest.raises(LLMResponseError, match="missing narrative"):
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
async def test_generate_narrative_fallback_plain_text():
    """Test narrative generation fallback to plain text."""
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
        
        narrative = await client.generate_narrative(
            system_instructions="You are a game master",
            user_prompt="The player searches the room"
        )
        
        # Should fallback to using the raw content
        assert narrative == "You discover a hidden treasure chest."
