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
"""Pydantic models for Dungeon Master API.

This module defines the request/response schemas and context models
used by the Dungeon Master service for communication with clients
and the journey-log service.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from uuid import UUID


class TurnRequest(BaseModel):
    """Request model for a turn in the game.
    
    Attributes:
        character_id: UUID or string identifier for the character
        user_action: The player's action/input for this turn
        trace_id: Optional trace ID for request tracking and correlation
    """
    character_id: str = Field(
        ...,
        description="Character UUID identifier",
        examples=["550e8400-e29b-41d4-a716-446655440000"]
    )
    user_action: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="Player's action or input for this turn",
        examples=["I search the room for treasure"]
    )
    trace_id: Optional[str] = Field(
        None,
        description="Optional trace ID for request correlation",
        examples=["trace-123-456-789"]
    )

    @field_validator('character_id')
    @classmethod
    def validate_character_id(cls, v: str) -> str:
        """Validate character_id is a valid UUID format."""
        try:
            # Try parsing as UUID to validate format
            UUID(v)
            return v
        except ValueError:
            raise ValueError(f"character_id must be a valid UUID, got: {v}")


class TurnResponse(BaseModel):
    """Response model for a turn in the game.
    
    Attributes:
        narrative: The AI-generated narrative response for the player's action
    """
    narrative: str = Field(
        ...,
        description="AI-generated narrative response",
        examples=["You search the dimly lit room and discover a glinting treasure chest..."]
    )


class JourneyLogContext(BaseModel):
    """Context model representing character state from journey-log service.
    
    This model contains pass-through fields that will be fetched from
    the journey-log service and used for LLM context generation.
    
    Attributes:
        character_id: UUID identifier for the character
        status: Character health status (e.g., "Healthy", "Wounded", "Dead")
        location: Current location information
        active_quest: Current active quest information (if any)
        combat_state: Current combat state information (if any)
        recent_history: List of recent narrative turns
    """
    character_id: str = Field(
        ...,
        description="Character UUID identifier"
    )
    status: str = Field(
        ...,
        description="Character health status",
        examples=["Healthy", "Wounded", "Dead"]
    )
    location: dict = Field(
        ...,
        description="Character's current location",
        examples=[{"id": "origin:nexus", "display_name": "The Nexus"}]
    )
    active_quest: Optional[dict] = Field(
        None,
        description="Active quest information, if any"
    )
    combat_state: Optional[dict] = Field(
        None,
        description="Combat state information, if any"
    )
    recent_history: List[dict] = Field(
        default_factory=list,
        description="Recent narrative turns from character history"
    )


class HealthResponse(BaseModel):
    """Response model for health check endpoint.
    
    Attributes:
        status: Service status ("healthy" or "degraded")
        service: Service name
        journey_log_accessible: Whether journey-log service is accessible (optional)
    """
    status: str = Field(
        ...,
        description="Service health status",
        examples=["healthy", "degraded"]
    )
    service: str = Field(
        default="dungeon-master",
        description="Service name"
    )
    journey_log_accessible: Optional[bool] = Field(
        None,
        description="Whether journey-log service is accessible (if health check enabled)"
    )
