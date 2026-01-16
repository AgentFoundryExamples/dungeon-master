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
