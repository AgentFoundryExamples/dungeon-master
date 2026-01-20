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
"""Integration tests for streaming /turn endpoint (DEPRECATED).

The streaming endpoint has been disabled and returns HTTP 410 Gone.
These tests verify that clients receive appropriate error messages.
"""

import pytest


@pytest.mark.asyncio
async def test_turn_stream_endpoint_returns_410_gone(client):
    """Test that streaming endpoint returns 410 Gone with migration guidance."""
    response = client.post(
        "/turn/stream",
        json={
            "character_id": "550e8400-e29b-41d4-a716-446655440000",
            "user_action": "I search the room"
        }
    )
    
    # Should return 410 Gone
    assert response.status_code == 410
    
    # Should have error details with migration guidance
    data = response.json()
    assert "detail" in data
    
    # FastAPI wraps error in "detail" field
    error_detail = data["detail"]
    assert "error" in error_detail
    
    error = error_detail["error"]
    assert error["type"] == "endpoint_removed"
    assert "Please use the synchronous POST /turn endpoint instead" in error["message"]


@pytest.mark.asyncio
async def test_turn_stream_endpoint_any_request_returns_410(client):
    """Test that any streaming request returns 410 Gone with valid payload."""
    # Use valid UUID to pass validation
    response = client.post(
        "/turn/stream",
        json={
            "character_id": "550e8400-e29b-41d4-a716-446655440001",
            "user_action": "test action"
        }
    )
    
    assert response.status_code == 410
    data = response.json()
    error = data["detail"]["error"]
    assert error["type"] == "endpoint_removed"
