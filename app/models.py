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

Includes DungeonMasterOutcome models for structured LLM outputs with
strict JSON contracts for narrative and intents.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator
from uuid import UUID

# Internal version constant for outcome schema evolution
# Do NOT include this in LLM outputs; it's for internal tracking only
OUTCOME_VERSION = 1


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


class ErrorDetail(BaseModel):
    """Structured error response model.
    
    Attributes:
        type: Machine-readable error type
        message: Human-readable error message
        request_id: Request correlation ID (if available)
    """
    type: str = Field(
        ...,
        description="Machine-readable error type",
        examples=["character_not_found", "journey_log_timeout", "llm_error"]
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
        examples=["Character not found in journey-log service"]
    )
    request_id: Optional[str] = Field(
        None,
        description="Request correlation ID for tracking"
    )


class ErrorResponse(BaseModel):
    """Error response wrapper.
    
    Attributes:
        error: Error details
    """
    error: ErrorDetail = Field(
        ...,
        description="Error details"
    )


# ============================================================================
# DungeonMaster Outcome Models - Structured LLM Output Schema
# ============================================================================
# These models define strict JSON contracts for LLM outputs.
# The LLM generates narrative and intents, but does NOT decide subsystem
# eligibility - that's handled by the DungeonMaster service logic.


class EnemyDescriptor(BaseModel):
    """Descriptor for an enemy in combat.
    
    Used by CombatIntent to describe enemies encountered in combat.
    
    Attributes:
        name: Optional name of the enemy (e.g., "Goblin Scout")
        description: Optional description of the enemy's appearance or behavior
        threat: Optional threat level or classification (e.g., "low", "medium", "high")
    """
    name: Optional[str] = Field(
        None,
        description="Name of the enemy",
        examples=["Goblin Scout", "Shadow Wraith"]
    )
    description: Optional[str] = Field(
        None,
        description="Description of the enemy's appearance or behavior",
        examples=["A small, cunning creature with sharp teeth"]
    )
    threat: Optional[str] = Field(
        None,
        description="Threat level or classification",
        examples=["low", "medium", "high"]
    )


class QuestIntent(BaseModel):
    """Quest-related intent from LLM output.
    
    Indicates what quest action the narrative implies, if any.
    The LLM only suggests intents; the service decides actual quest operations.
    
    Attributes:
        action: Quest action type - "none", "offer", "complete", or "abandon"
        quest_title: Optional title of the quest
        quest_summary: Optional brief summary of the quest
        quest_details: Optional dictionary of additional quest metadata
    """
    action: Literal["none", "offer", "complete", "abandon"] = Field(
        default="none",
        description="Quest action to perform"
    )
    quest_title: Optional[str] = Field(
        None,
        description="Title of the quest",
        examples=["Rescue the Innkeeper's Daughter"]
    )
    quest_summary: Optional[str] = Field(
        None,
        description="Brief summary of the quest objective",
        examples=["Find the missing girl last seen near the old mill"]
    )
    quest_details: Optional[dict] = Field(
        None,
        description="Additional quest metadata and details"
    )


class CombatIntent(BaseModel):
    """Combat-related intent from LLM output.
    
    Indicates what combat action the narrative implies, if any.
    The LLM only suggests intents; the service decides actual combat operations.
    
    Attributes:
        action: Combat action type - "none", "start", "continue", or "end"
        enemies: Optional list of enemy descriptors
        combat_notes: Optional notes about the combat situation
    """
    action: Literal["none", "start", "continue", "end"] = Field(
        default="none",
        description="Combat action to perform"
    )
    enemies: Optional[List[EnemyDescriptor]] = Field(
        None,
        description="List of enemies in the encounter"
    )
    combat_notes: Optional[str] = Field(
        None,
        description="Additional notes about the combat situation",
        examples=["The goblins are hiding behind barrels"]
    )


class POIIntent(BaseModel):
    """Point-of-Interest intent from LLM output.
    
    Indicates what POI action the narrative implies, if any.
    The LLM only suggests intents; the service decides actual POI operations.
    
    Attributes:
        action: POI action type - "none", "create", or "reference"
        name: Optional name of the point of interest
        description: Optional description of the location
        reference_tags: Optional list of tags for referencing this POI later
    """
    action: Literal["none", "create", "reference"] = Field(
        default="none",
        description="Point-of-interest action to perform"
    )
    name: Optional[str] = Field(
        None,
        description="Name of the point of interest",
        examples=["The Old Mill", "Shadowfen Swamp"]
    )
    description: Optional[str] = Field(
        None,
        description="Description of the location",
        examples=["An abandoned mill at the edge of the forest"]
    )
    reference_tags: Optional[List[str]] = Field(
        None,
        description="Tags for referencing this POI in future context",
        examples=[["mill", "forest", "quest_location"]]
    )


class MetaIntent(BaseModel):
    """Meta-level intent about player engagement and pacing.
    
    Provides hints about player mood and game pacing for the service to consider.
    The LLM observes and reports; the service decides actual pacing adjustments.
    
    Attributes:
        player_mood: Optional assessment of player's emotional state
        pacing_hint: Optional pacing suggestion - "slow", "normal", or "fast"
        user_is_wandering: Optional flag indicating player seems directionless
        user_asked_for_guidance: Optional flag indicating player requested help
    """
    player_mood: Optional[str] = Field(
        None,
        description="Assessment of player's emotional state",
        examples=["excited", "cautious", "frustrated", "engaged"]
    )
    pacing_hint: Optional[Literal["slow", "normal", "fast"]] = Field(
        None,
        description="Suggested pacing for the game flow"
    )
    user_is_wandering: Optional[bool] = Field(
        None,
        description="Flag indicating player seems to lack direction"
    )
    user_asked_for_guidance: Optional[bool] = Field(
        None,
        description="Flag indicating player explicitly requested help or guidance"
    )


class IntentsBlock(BaseModel):
    """Collection of all intent types from LLM output.
    
    Groups all possible intents that the LLM can suggest based on the narrative.
    All fields are optional as the LLM may not suggest any specific intent.
    
    Note: The LLM fills these intents based on narrative content, but the
    DungeonMaster service logic determines actual subsystem eligibility and
    operations based on game state.
    
    Attributes:
        quest_intent: Optional quest-related intent
        combat_intent: Optional combat-related intent
        poi_intent: Optional point-of-interest intent
        meta: Optional meta-level intent about player engagement
    """
    quest_intent: Optional[QuestIntent] = Field(
        None,
        description="Quest-related intent, if any"
    )
    combat_intent: Optional[CombatIntent] = Field(
        None,
        description="Combat-related intent, if any"
    )
    poi_intent: Optional[POIIntent] = Field(
        None,
        description="Point-of-interest intent, if any"
    )
    meta: Optional[MetaIntent] = Field(
        None,
        description="Meta-level intent about player engagement and pacing"
    )


class DungeonMasterOutcome(BaseModel):
    """Structured outcome from LLM for a turn.
    
    This is the top-level schema that the LLM must conform to when generating
    responses. It enforces a strict JSON contract with narrative text and
    structured intents.
    
    The LLM generates narrative and suggests intents, but does NOT decide
    subsystem eligibility or perform state changes - those are handled by
    the DungeonMaster service based on game rules and current state.
    
    Attributes:
        narrative: The narrative text response to the player's action
        intents: Structured intents derived from the narrative content
    
    Example:
        {
            "narrative": "You enter the tavern and see a grizzled innkeeper...",
            "intents": {
                "quest_intent": {
                    "action": "offer",
                    "quest_title": "Find My Daughter",
                    "quest_summary": "The innkeeper's daughter is missing"
                },
                "combat_intent": {"action": "none"},
                "poi_intent": {"action": "create", "name": "The Rusty Tankard Inn"},
                "meta": {"player_mood": "curious", "pacing_hint": "normal"}
            }
        }
    """
    narrative: str = Field(
        ...,
        description="The narrative text response for this turn",
        min_length=1
    )
    intents: IntentsBlock = Field(
        ...,
        description="Structured intents derived from the narrative"
    )


def get_outcome_json_schema() -> dict:
    """Get JSON Schema for DungeonMasterOutcome.
    
    Returns the JSON Schema representation of the DungeonMasterOutcome model
    suitable for embedding in LLM prompts to enforce structured output.
    
    This schema can be used with OpenAI's Responses API text.format parameter,
    or with other LLMs that support JSON Schema validation.
    
    Returns:
        Dictionary containing the JSON Schema for DungeonMasterOutcome
    
    Example:
        >>> schema = get_outcome_json_schema()
        >>> # Use with OpenAI Responses API:
        >>> response = client.responses.create(
        ...     model="gpt-5.1",
        ...     input="...",
        ...     text={"format": {"type": "json_schema", "schema": schema, "strict": True}}
        ... )
    """
    return DungeonMasterOutcome.model_json_schema()


def get_outcome_schema_example() -> str:
    """Get a JSON string example of DungeonMasterOutcome.
    
    Returns a formatted JSON example of the outcome schema suitable for
    including in prompts as a reference.
    
    Returns:
        JSON string with formatted example
    """
    import json
    
    example = {
        "narrative": "You push open the heavy oak door and step into the dimly lit tavern. "
                    "The smell of ale and smoke fills the air. Behind the bar, a grizzled "
                    "innkeeper looks up at you with worried eyes.",
        "intents": {
            "quest_intent": {
                "action": "offer",
                "quest_title": "Find the Missing Daughter",
                "quest_summary": "The innkeeper's daughter hasn't returned from the forest",
                "quest_details": {
                    "difficulty": "medium",
                    "suggested_level": 3
                }
            },
            "combat_intent": {
                "action": "none"
            },
            "poi_intent": {
                "action": "create",
                "name": "The Rusty Tankard Inn",
                "description": "A weathered tavern at the edge of town",
                "reference_tags": ["inn", "town", "quest_hub"]
            },
            "meta": {
                "player_mood": "curious",
                "pacing_hint": "normal",
                "user_is_wandering": False,
                "user_asked_for_guidance": False
            }
        }
    }
    
    return json.dumps(example, indent=2)
