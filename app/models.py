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

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from enum import Enum


# Internal version constant for outcome schema evolution
# Do NOT include this in LLM outputs; it's for internal tracking only
OUTCOME_VERSION = 1


class TurnRequest(BaseModel):
    """Request model for a turn in the game.
    
    Attributes:
        character_id: UUID or string identifier for the character
        user_action: The player's action/input for this turn
        user_id: Optional user ID for request tracking and correlation (passed as X-User-Id to journey-log)
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


class CharacterCreationRequest(BaseModel):
    """Request model for creating a new character.
    
    Attributes:
        name: Name of the character.
        race: Race of the character.
        class_name: Class of the character (e.g., "Warrior", "Mage").
        custom_prompt: Optional user-provided prompt to shape the world/setting.
    """
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Character name",
        examples=["Aelthor", "Grom"]
    )
    race: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Character race",
        examples=["Human", "Elf", "Dwarf"]
    )
    class_name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Character class",
        examples=["Warrior", "Rogue", "Wizard"]
    )
    custom_prompt: Optional[str] = Field(
        None,
        max_length=2000,
        description="Optional prompt to customize the world setting or opening scene",
        examples=["A dark fantasy world where the sun has vanished."]
    )


class CharacterCreationResponse(BaseModel):
    """Response model for character creation.
    
    Attributes:
        character_id: The UUID of the created character.
        narrative: The introductory narrative scene.
    """
    character_id: str = Field(
        ...,
        description="UUID of the created character"
    )
    narrative: str = Field(
        ...,
        description="Introductory narrative scene"
    )


class PolicyState(BaseModel):
    """Policy-relevant state for quest and POI trigger evaluation.
    
    This model captures all state necessary for PolicyEngine to evaluate
    quest and POI eligibility, including timestamps, turn counters, combat flags,
    and player engagement metadata.
    
    **Field Authoritative Sources:**
    
    Journey-log managed (authoritative):
    - has_active_quest: Derived from quest field in CharacterContextResponse
    - combat_active: Derived from combat.active field in CharacterContextResponse
    
    DM-managed via additional_fields (interim storage until journey-log support):
    - last_quest_offered_at: Timestamp when DM last offered a quest
    - last_quest_completed_at: Timestamp when DM last completed/abandoned a quest
    - last_poi_created_at: Timestamp when DM last created a POI
    - turns_since_last_quest: Turn counter incremented by DM per narrative turn
    - turns_since_last_poi: Turn counter incremented by DM per narrative turn
    - user_is_wandering: Flag set by DM based on LLM meta intents
    - requested_guidance: Flag set by DM when player explicitly asks for help
    
    **Coordination with Journey-Log:**
    
    The DM service currently stores quest/POI timestamps and turn counters in
    journey-log's player_state.additional_fields as a temporary solution. These
    fields enable policy decisions without waiting for journey-log schema evolution.
    
    Future journey-log enhancements will provide first-class fields for quest/POI
    history, at which point the DM service will migrate to reading from those
    authoritative sources. The additional_fields storage mechanism ensures forward
    compatibility and allows policy logic to work today.
    
    **State Write Pattern (Not Implemented Yet):**
    
    When the DM service makes policy decisions (e.g., offer quest, create POI),
    it will eventually write back to journey-log to update:
    - Quest history timestamps (via future journey-log endpoints)
    - POI creation timestamps (via future journey-log endpoints)
    - Turn counters (incremented on each narrative append)
    
    The write-back mechanism is deliberately not implemented yet to avoid coupling
    with journey-log schema changes. For now, the DM service reads state from
    additional_fields and can mock writes locally for testing.
    
    Attributes:
        last_quest_offered_at: Timestamp when last quest was offered (ISO 8601 or None)
        last_quest_completed_at: Timestamp when last quest was completed/abandoned (ISO 8601 or None)
        last_poi_created_at: Timestamp when last POI was created (ISO 8601 or None)
        turns_since_last_quest: Number of turns since last quest trigger (0 if no quest history)
        turns_since_last_poi: Number of turns since last POI trigger (0 if no POI history)
        has_active_quest: Whether character has an active quest
        combat_active: Whether character is currently in combat
        user_is_wandering: Optional flag indicating player seems directionless
        requested_guidance: Optional flag indicating player requested help
    """
    last_quest_offered_at: Optional[str] = Field(
        None,
        description="ISO 8601 timestamp when last quest was offered, or None if no quest history"
    )
    last_quest_completed_at: Optional[str] = Field(
        None,
        description="ISO 8601 timestamp when last quest was completed/abandoned, or None if no completion history"
    )
    last_poi_created_at: Optional[str] = Field(
        None,
        description="ISO 8601 timestamp when last POI was created, or None if no POI history"
    )
    turns_since_last_quest: int = Field(
        0,
        ge=0,
        description="Number of turns since last quest trigger (0 if no quest history)"
    )
    turns_since_last_poi: int = Field(
        0,
        ge=0,
        description="Number of turns since last POI trigger (0 if no POI history)"
    )
    has_active_quest: bool = Field(
        False,
        description="Whether character has an active quest"
    )
    combat_active: bool = Field(
        False,
        description="Whether character is currently in combat"
    )
    user_is_wandering: Optional[bool] = Field(
        None,
        description="Optional flag indicating player seems directionless"
    )
    requested_guidance: Optional[bool] = Field(
        None,
        description="Optional flag indicating player requested help or guidance"
    )

    @field_validator('last_quest_offered_at', 'last_quest_completed_at', 'last_poi_created_at')
    @classmethod
    def validate_timestamp(cls, v: Optional[str]) -> Optional[str]:
        """Validate timestamp is None or valid ISO 8601 format.
        
        Args:
            v: Timestamp value to validate
            
        Returns:
            The timestamp if valid, otherwise None
            
        Note:
            Validation errors are logged but do not raise exceptions to ensure
            graceful degradation. Invalid timestamps default to None.
        """
        if v is None:
            return None
        if not isinstance(v, str):
            # This shouldn't happen due to type hints, but be defensive
            return None
        try:
            # Use fromisoformat for basic validation
            # Replace 'Z' with '+00:00' for compatibility
            from datetime import datetime
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except (ValueError, TypeError):
            # Return None for invalid timestamps - validation happens at extraction time
            # with proper logging, so we don't need to log again here
            return None


class TurnResponse(BaseModel):
    """Response model for a turn in the game.
    
    Attributes:
        narrative: The AI-generated narrative response for the player's action
        intents: Optional structured intents from the LLM (informational only, not persisted)
        subsystem_summary: Optional summary of subsystem changes made during this turn
    """
    narrative: str = Field(
        ...,
        description="AI-generated narrative response",
        examples=["You search the dimly lit room and discover a glinting treasure chest..."]
    )
    intents: Optional["IntentsBlock"] = Field(
        None,
        description=(
            "Structured intents from LLM output (informational only). "
            "Only available when LLM response is valid. "
            "Note: Only narrative is persisted to journey-log; intents are descriptive."
        )
    )
    subsystem_summary: Optional["TurnSubsystemSummary"] = Field(
        None,
        description=(
            "Summary of subsystem changes made during this turn. "
            "Includes quest, combat, and POI actions with success/failure status. "
            "Only available when orchestrator is used."
        )
    )


class JourneyLogContext(BaseModel):
    """Context model representing character state from journey-log service.
    
    This model contains pass-through fields that will be fetched from
    the journey-log service and used for LLM context generation, including
    enriched policy state for quest and POI trigger evaluation.
    
    **Data Flow:**
    
    1. Journey-log provides authoritative character state (status, location, quest, combat)
    2. DM extracts policy state from journey-log response and additional_fields
    3. PolicyEngine uses policy_state for deterministic quest/POI decisions
    4. PromptBuilder serializes full context for LLM narrative generation
    
    **Field Sources:**
    
    From journey-log first-class fields:
    - character_id: CharacterContextResponse.character_id
    - status: CharacterContextResponse.player_state.status
    - location: CharacterContextResponse.player_state.location
    - active_quest: CharacterContextResponse.quest
    - combat_state: CharacterContextResponse.combat.state
    - recent_history: CharacterContextResponse.narrative.recent_turns
    
    From journey-log additional_fields (DM-managed interim storage):
    - policy_state fields: Extracted from player_state.additional_fields
    - additional_fields: Pass-through of player_state.additional_fields
    
    **Coordination Notes:**
    
    The additional_fields dictionary serves as forward-compatible storage for
    DM-managed state that journey-log doesn't yet track. As journey-log adds
    first-class fields for quest/POI history, the extraction logic in
    journey_log_client._extract_policy_state() will migrate to read from those
    authoritative sources while maintaining backward compatibility.
    
    Attributes:
        character_id: UUID identifier for the character
        status: Character health status (e.g., "Healthy", "Wounded", "Dead")
        location: Current location information
        active_quest: Current active quest information (if any)
        combat_state: Current combat state information (if any)
        recent_history: List of recent narrative turns
        policy_state: Policy-relevant state for quest/POI trigger evaluation
        additional_fields: Generic map for extensible DM-managed state
    """
    character_id: str = Field(
        ...,
        description="Character UUID identifier"
    )
    adventure_prompt: Optional[str] = Field(
        None,
        description="Custom world/setting prompt that shapes the narrative tone and setting"
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
    policy_state: PolicyState = Field(
        default_factory=PolicyState,
        description=(
            "Policy-relevant state for quest and POI trigger evaluation. "
            "Includes timestamps, turn counters, combat flags, and player engagement metadata. "
            "Derived from journey-log data and DM-managed additional_fields."
        )
    )
    policy_hints: Optional["PolicyHints"] = Field(
        None,
        description=(
            "Policy hints containing PolicyEngine decisions to inform LLM narrative generation. "
            "Includes quest and POI trigger decisions with eligibility and roll results. "
            "Added during turn orchestration after PolicyEngine evaluation."
        )
    )
    additional_fields: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Generic map for extensible DM-managed state. "
            "Fields here may be used for policy evaluation until journey-log "
            "provides first-class support. Forward-compatible with unexpected keys."
        )
    )
    memory_sparks: List[dict] = Field(
        default_factory=list,
        description=(
            "Random POIs fetched as memory sparks for prompt injection. "
            "Cached from GET /characters/{id}/pois/random when enabled by config. "
            "Helps LLM recall and reference previously discovered locations."
        )
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


class DebugParseRequest(BaseModel):
    """Request model for debug parse endpoint.
    
    Attributes:
        llm_response: Raw JSON string from LLM to parse
        user_id: Optional user ID for request correlation
    """
    llm_response: str = Field(
        ...,
        description="Raw JSON string from LLM to validate",
        min_length=1
    )
    user_id: Optional[str] = Field(
        default="debug-request",
        description="Optional user ID for request tracking"
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
    
    QUEST PHILOSOPHY:
    - Quests are driving narrative elements, not optional offers
    - When policy allows, quests START immediately as part of the story
    - LLM should focus on ADVANCING quests when player actions align
    - completion_state tracks progress: 'not_started', 'in_progress', 'completed'
    
    Attributes:
        action: Quest action type - "none", "start", "advance", "complete", or "abandon"
        quest_title: Optional title of the quest
        quest_summary: Optional brief summary of the quest objective
        quest_details: Optional dictionary of additional quest metadata
        progress_update: Optional description of quest progress when action='advance'
    """
    action: Literal["none", "start", "advance", "complete", "abandon"] = Field(
        default="none",
        description="Quest action: 'start' (begin new quest), 'advance' (progress active quest), 'complete' (finish quest), 'abandon' (give up)"
    )
    quest_title: Optional[str] = Field(
        None,
        description="Title of the quest (required for 'start' action)",
        examples=["Rescue the Innkeeper's Daughter"]
    )
    quest_summary: Optional[str] = Field(
        None,
        description="Brief summary of the quest objective (required for 'start' action)",
        examples=["Find the missing girl last seen near the old mill"]
    )
    quest_details: Optional[dict] = Field(
        None,
        description="Additional quest metadata and details"
    )
    progress_update: Optional[str] = Field(
        None,
        description="Description of progress made when action='advance' (e.g., 'Found a clue at the mill', 'Defeated the bandits')",
        examples=["Discovered the hideout location", "Convinced the guard to help"]
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
    
    POI MODEL:
    - POIs are named, significant locations (towns, dungeons, taverns, etc.)
    - Characters can be IN a POI (location_id set) or have NO POI (traveling)
    - 'create' action: Character enters/discovers a new named location
    - 'reference' action: Mention an existing POI without entering it
    - minor_location (in LocationIntent) is ALWAYS present for precise positioning
    - Leaving a POI is handled via LocationIntent with action='leave_poi'
    
    Attributes:
        action: POI action type - "none", "create", or "reference"
        name: Name of the point of interest
        description: Description of the location
        reference_tags: Tags for referencing this POI later
    """
    action: Literal["none", "create", "reference"] = Field(
        default="none",
        description="POI action: 'create' (enter/discover new location), 'reference' (mention existing location)"
    )
    name: Optional[str] = Field(
        None,
        description="Name of the point of interest",
        examples=["The Old Mill", "Shadowfen Swamp", "The Rusty Tankard Inn"]
    )
    description: Optional[str] = Field(
        None,
        description="Description of the location",
        examples=["An abandoned mill at the edge of the forest", "A mysterious tavern filled with shady characters"]
    )
    reference_tags: Optional[List[str]] = Field(
        None,
        description="Tags for referencing this POI in future context",
        examples=[["mill", "forest", "quest_location"], ["tavern", "town", "social_hub"]]
    )


class LocationIntent(BaseModel):
    """Location intent for setting or updating character location.
    
    LOCATION MODEL:
    - Characters can be IN a POI (major named location) or have NO POI (traveling/between)
    - minor_location is ALWAYS present - describes where they are right now
    - When in a POI: minor_location is position within that POI (e.g., 'at the bar')
    - When not in a POI: minor_location describes the transitional state (e.g., 'on the road to town')
    
    Used during character creation to establish starting location (with origin POI),
    and during gameplay to track movement and transitions.
    
    Attributes:
        location_id: Machine-readable POI identifier (null when between locations)
        location_display_name: Human-readable POI name (null when between locations)
        minor_location: ALWAYS present - precise current position (within POI or between POIs)
        action: Action type - 'none', 'update_minor', 'leave_poi'
    """
    location_id: Optional[str] = Field(
        None,
        description="Machine-readable POI identifier when IN a location (null when traveling between POIs)",
        examples=["town:rivendell", "forest:darkwood", "dungeon:shadowkeep", "tavern:prancing_pony"]
    )
    location_display_name: Optional[str] = Field(
        None,
        description="Human-readable POI name when IN a location (null when traveling between POIs)",
        examples=["The Town of Rivendell", "Darkwood Forest", "Shadowkeep Dungeon", "The Prancing Pony"]
    )
    minor_location: Optional[str] = Field(
        None,
        description="ALWAYS provide - precise current position (within POI or between POIs)",
        examples=["at the bar counter", "in the town square", "on the road between towns", "entering the forest"]
    )
    action: Literal["none", "update_minor", "leave_poi"] = Field(
        default="none",
        description="Location action: 'none' (no change), 'update_minor' (update minor_location), 'leave_poi' (exit current POI)"
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
        location_intent: Optional location intent for setting character location
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
    location_intent: Optional[LocationIntent] = Field(
        None,
        description="Location intent for setting character location (used primarily during character creation)"
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
                "location_intent": {
                    "location_id": "tavern:rusty_tankard",
                    "location_display_name": "The Rusty Tankard Inn"
                },
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
    or with other LLMs that support JSON Schema validation. The schema is
    configured with strict validation to prevent additional properties.
    
    OpenAI strict mode requirements:
    1. All object types must have additionalProperties: false
    2. All properties must be in required array (no optional fields at object level)
    3. $ref cannot have sibling keywords (like description) - must be the only key
    4. Nullable fields must use anyOf with explicit null type
    5. No recursive $defs references
    
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
    schema = DungeonMasterOutcome.model_json_schema()
    
    # Configure schema for OpenAI's strict mode requirements
    def set_strict_mode(obj, path=""):
        """Recursively process schema to meet OpenAI strict mode requirements."""
        if isinstance(obj, dict):
            # CRITICAL: $ref cannot have sibling keys - if $ref exists, only keep $ref
            if "$ref" in obj:
                # Extract the ref and remove all other keys
                ref_value = obj["$ref"]
                obj.clear()
                obj["$ref"] = ref_value
                return  # Don't process further, $ref must be standalone
            
            # Handle objects with type="object"
            if obj.get("type") == "object":
                obj["additionalProperties"] = False
                if "properties" in obj:
                    # For OpenAI strict mode, all properties must be required
                    if "required" not in obj:
                        obj["required"] = []
                    # Add all property keys to required if not already there
                    for prop_key in obj["properties"].keys():
                        if prop_key not in obj["required"]:
                            obj["required"].append(prop_key)
            
            # Handle anyOf/allOf/oneOf - process each branch
            for key in ["anyOf", "allOf", "oneOf"]:
                if key in obj:
                    for item in obj[key]:
                        set_strict_mode(item, f"{path}.{key}")
            
            # Recursively process all other nested structures
            for key, value in list(obj.items()):
                if key not in ["anyOf", "allOf", "oneOf", "$ref"]:
                    set_strict_mode(value, f"{path}.{key}" if path else key)
                    
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                set_strict_mode(item, f"{path}[{i}]")
    
    # Apply strict mode transformations
    set_strict_mode(schema)
    
    # Inline all $defs to avoid reference issues with descriptions
    if "$defs" in schema:
        defs = schema.pop("$defs")
        
        def inline_refs(obj):
            """Replace all $ref with actual definition content."""
            if isinstance(obj, dict):
                if "$ref" in obj:
                    # Extract ref path
                    ref_path = obj["$ref"]
                    if ref_path.startswith("#/$defs/"):
                        def_name = ref_path.split("/")[-1]
                        if def_name in defs:
                            # Replace $ref with actual definition
                            obj.clear()
                            obj.update(defs[def_name])
                            # Process the inlined content
                            inline_refs(obj)
                else:
                    for value in obj.values():
                        inline_refs(value)
            elif isinstance(obj, list):
                for item in obj:
                    inline_refs(item)
        
        inline_refs(schema)
        # Apply strict mode again after inlining
        set_strict_mode(schema)
    
    return schema


def get_outcome_schema_example() -> str:
    """Get a JSON string example of DungeonMasterOutcome.
    
    Returns a formatted JSON example of the outcome schema suitable for
    including in prompts as a reference. This example is generated from
    actual model instances to ensure it matches the schema validation.
    
    Returns:
        JSON string with formatted example
    """
    example_model = DungeonMasterOutcome(
        narrative="You push open the heavy oak door and step into the dimly lit tavern. "
                  "The smell of ale and smoke fills the air. Behind the bar, a grizzled "
                  "innkeeper looks up at you with worried eyes. 'Thank the gods you're here,' "
                  "he says urgently. 'My daughter vanished in the forest last night. Please, you must help me find her!'",
        intents=IntentsBlock(
            quest_intent=QuestIntent(
                action="start",
                quest_title="Find the Missing Daughter",
                quest_summary="The innkeeper's daughter hasn't returned from the forest",
                quest_details={
                    "difficulty": "medium",
                    "suggested_level": 3
                }
            ),
            combat_intent=CombatIntent(action="none"),
            poi_intent=POIIntent(
                action="create",
                name="The Rusty Tankard Inn",
                description="A weathered tavern at the edge of town",
                reference_tags=["inn", "town", "quest_hub"]
            ),
            location_intent=LocationIntent(
                location_id="inn:rusty_tankard",
                location_display_name="The Rusty Tankard Inn",
                minor_location="standing at the bar",
                action="update_minor"
            ),
            meta=MetaIntent(
                player_mood="curious",
                pacing_hint="normal",
                user_is_wandering=False,
                user_asked_for_guidance=False
            )
        )
    )
    
    return example_model.model_dump_json(indent=2)


# ============================================================================
# PolicyEngine Decision Models
# ============================================================================
# These models define the structured decisions returned by the PolicyEngine
# for quest and POI trigger evaluation.


class QuestTriggerDecision(BaseModel):
    """Decision model for quest trigger evaluation.
    
    Represents the result of evaluating whether to trigger a quest for a
    character, including eligibility, probability, and roll outcome.
    
    Attributes:
        eligible: Whether the character is eligible for quest trigger
        probability: The probability used for the roll (0.0-1.0)
        roll_passed: Whether the probabilistic roll succeeded
    """
    eligible: bool = Field(
        ...,
        description="Whether the character is eligible for quest trigger"
    )
    probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="The probability used for the roll"
    )
    roll_passed: bool = Field(
        ...,
        description="Whether the probabilistic roll succeeded"
    )


class POITriggerDecision(BaseModel):
    """Decision model for POI (Point of Interest) trigger evaluation.
    
    Represents the result of evaluating whether to trigger a POI for a
    character, including eligibility, probability, and roll outcome.
    
    Attributes:
        eligible: Whether the character is eligible for POI trigger
        probability: The probability used for the roll (0.0-1.0)
        roll_passed: Whether the probabilistic roll succeeded
    """
    eligible: bool = Field(
        ...,
        description="Whether the character is eligible for POI trigger"
    )
    probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="The probability used for the roll"
    )
    roll_passed: bool = Field(
        ...,
        description="Whether the probabilistic roll succeeded"
    )


class MemorySparkDecision(BaseModel):
    """Decision model for memory spark trigger evaluation.
    
    Represents the result of evaluating whether to fetch memory sparks
    (random POIs) for a character, including eligibility, probability,
    and roll outcome.
    
    Attributes:
        eligible: Whether the character is eligible for memory spark trigger
        probability: The probability used for the roll (0.0-1.0)
        roll_passed: Whether the probabilistic roll succeeded
    """
    eligible: bool = Field(
        ...,
        description="Whether the character is eligible for memory spark trigger"
    )
    probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="The probability used for the roll"
    )
    roll_passed: bool = Field(
        ...,
        description="Whether the probabilistic roll succeeded"
    )


class QuestPOIReferenceDecision(BaseModel):
    """Decision model for quest POI reference trigger evaluation.
    
    Represents the result of evaluating whether a triggered quest should
    reference a prior POI, including probability and roll outcome.
    
    Attributes:
        probability: The probability used for the roll (0.0-1.0)
        roll_passed: Whether the probabilistic roll succeeded
        selected_poi: Optional POI selected for reference (if roll passed)
    """
    probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="The probability used for the roll"
    )
    roll_passed: bool = Field(
        ...,
        description="Whether the probabilistic roll succeeded"
    )
    selected_poi: Optional[dict] = Field(
        None,
        description="Optional POI selected for reference (if roll passed)"
    )


class PolicyHints(BaseModel):
    """Policy hints containing policy decisions to inform LLM narrative generation.
    
    This model carries PolicyEngine decisions into the prompt so the LLM
    knows when it may propose quests or POIs. The LLM should respect these
    hints when generating narrative and intents.
    
    Attributes:
        quest_trigger_decision: Decision about whether to trigger a quest
        poi_trigger_decision: Decision about whether to trigger a POI
        memory_spark_decision: Optional decision about whether to fetch memory sparks
        quest_poi_reference_decision: Optional decision about whether quest references a POI
    """
    quest_trigger_decision: QuestTriggerDecision = Field(
        ...,
        description="Quest trigger decision from PolicyEngine"
    )
    poi_trigger_decision: POITriggerDecision = Field(
        ...,
        description="POI trigger decision from PolicyEngine"
    )
    memory_spark_decision: Optional["MemorySparkDecision"] = Field(
        None,
        description="Memory spark trigger decision from PolicyEngine (optional)"
    )
    quest_poi_reference_decision: Optional["QuestPOIReferenceDecision"] = Field(
        None,
        description="Quest POI reference decision from PolicyEngine (optional)"
    )


# ============================================================================
# Turn Orchestration and Subsystem Summary Models
# ============================================================================


class SubsystemActionType(BaseModel):
    """Base class for subsystem action types with success/failure tracking.
    
    Attributes:
        action: The action performed (e.g., "offer", "complete", "none")
        success: Whether the action succeeded (None if not attempted)
        error: Error message if action failed (None if success or not attempted)
    """
    action: str = Field(
        ...,
        description="Action performed or 'none' if no action"
    )
    success: Optional[bool] = Field(
        None,
        description="Whether the action succeeded (None if not attempted)"
    )
    error: Optional[str] = Field(
        None,
        description="Error message if action failed"
    )


class QuestChangeType(str, Enum):
    """Quest change type constants."""
    NONE = "none"
    OFFERED = "offered"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class CombatChangeType(str, Enum):
    """Combat change type constants."""
    NONE = "none"
    STARTED = "started"
    CONTINUED = "continued"
    ENDED = "ended"


class POIChangeType(str, Enum):
    """POI change type constants."""
    NONE = "none"
    CREATED = "created"
    REFERENCED = "referenced"


class TurnSubsystemSummary(BaseModel):
    """Summary of subsystem changes made during a turn.
    
    This model captures all subsystem actions (quest, combat, POI) that were
    attempted during turn processing, along with their success/failure status.
    It enables:
    - Analytics on subsystem engagement rates
    - Debugging of failed writes
    - Verification of orchestration order
    - Dry-run simulation results
    
    All fields default to 'none' action with no success/error, representing
    no attempted action for that subsystem.
    
    Attributes:
        quest_change: Quest action summary (offered/completed/abandoned/none)
        combat_change: Combat action summary (started/continued/ended/none)
        poi_change: POI action summary (created/referenced/none)
        narrative_persisted: Whether narrative was successfully persisted
        narrative_error: Error message if narrative persistence failed
    """
    quest_change: SubsystemActionType = Field(
        default_factory=lambda: SubsystemActionType(action="none"),
        description="Quest action performed and its result"
    )
    combat_change: SubsystemActionType = Field(
        default_factory=lambda: SubsystemActionType(action="none"),
        description="Combat action performed and its result"
    )
    poi_change: SubsystemActionType = Field(
        default_factory=lambda: SubsystemActionType(action="none"),
        description="POI action performed and its result"
    )
    narrative_persisted: bool = Field(
        False,
        description="Whether narrative was successfully persisted to journey-log"
    )
    narrative_error: Optional[str] = Field(
        None,
        description="Error message if narrative persistence failed"
    )

# ============================================================================
# Admin Endpoint Models
# ============================================================================
# These models define the structured responses for admin introspection
# endpoints that allow operators to inspect turn state for debugging.


class AdminTurnDetail(BaseModel):
    """Admin turn detail for introspection endpoint.
    
    Provides comprehensive turn state for debugging including inputs,
    decisions, LLM outputs, and journey-log writes. Returned by
    GET /admin/turns/{turn_id} endpoint.
    
    Attributes:
        turn_id: Unique turn identifier
        character_id: Character UUID
        timestamp: ISO 8601 timestamp of turn start
        user_action: Player's input action
        context_snapshot: Redacted character context at turn time
        policy_decisions: Policy engine decisions (quest/POI eligibility, rolls)
        llm_narrative: Generated narrative text (may be truncated)
        llm_intents: Structured intents from LLM output
        journey_log_writes: Summary of subsystem writes (quest, combat, POI, narrative)
        errors: List of errors encountered during turn processing
        latency_ms: Total turn processing time in milliseconds
        redacted: Whether sensitive data was redacted from response
    """
    turn_id: str = Field(
        ...,
        description="Unique turn identifier"
    )
    character_id: str = Field(
        ...,
        description="Character UUID"
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp of turn start"
    )
    user_action: str = Field(
        ...,
        description="Player's input action"
    )
    context_snapshot: Dict[str, Any] = Field(
        ...,
        description="Character context snapshot at turn time (redacted)"
    )
    policy_decisions: Dict[str, Any] = Field(
        ...,
        description="Policy engine decisions for quest/POI triggers"
    )
    llm_narrative: Optional[str] = Field(
        None,
        description="Generated narrative text (may be truncated)"
    )
    llm_intents: Optional[Dict[str, Any]] = Field(
        None,
        description="Structured intents from LLM output"
    )
    journey_log_writes: Dict[str, Any] = Field(
        ...,
        description="Summary of subsystem writes (quest, combat, POI, narrative)"
    )
    errors: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of errors encountered during turn processing"
    )
    latency_ms: Optional[float] = Field(
        None,
        description="Total turn processing time in milliseconds"
    )
    redacted: bool = Field(
        default=True,
        description="Whether sensitive data was redacted from response"
    )


class AdminRecentTurnsResponse(BaseModel):
    """Response for admin recent turns endpoint.
    
    Returns a list of recent turns for a character in reverse chronological
    order. Returned by GET /admin/characters/{id}/recent_turns endpoint.
    
    Attributes:
        character_id: Character UUID
        turns: List of turn details (most recent first)
        total_count: Total number of turns returned
        limit: Maximum number of turns requested
    """
    character_id: str = Field(
        ...,
        description="Character UUID"
    )
    turns: List[AdminTurnDetail] = Field(
        ...,
        description="List of turn details in reverse chronological order"
    )
    total_count: int = Field(
        ...,
        description="Total number of turns returned"
    )
    limit: int = Field(
        ...,
        description="Maximum number of turns requested"
    )


class PolicyConfigResponse(BaseModel):
    """Response for policy config inspection endpoint.
    
    Returns current policy configuration parameters.
    
    Attributes:
        quest_trigger_prob: Current quest trigger probability
        quest_cooldown_turns: Current quest cooldown in turns
        poi_trigger_prob: Current POI trigger probability
        poi_cooldown_turns: Current POI cooldown in turns
        memory_spark_probability: Current memory spark trigger probability
        quest_poi_reference_probability: Current quest POI reference probability
        last_updated: ISO 8601 timestamp of last config change
    """
    quest_trigger_prob: float = Field(
        ...,
        description="Current quest trigger probability (0.0-1.0)"
    )
    quest_cooldown_turns: int = Field(
        ...,
        description="Current quest cooldown in turns"
    )
    poi_trigger_prob: float = Field(
        ...,
        description="Current POI trigger probability (0.0-1.0)"
    )
    poi_cooldown_turns: int = Field(
        ...,
        description="Current POI cooldown in turns"
    )
    memory_spark_probability: float = Field(
        ...,
        description="Current memory spark trigger probability (0.0-1.0)"
    )
    quest_poi_reference_probability: float = Field(
        ...,
        description="Current quest POI reference probability (0.0-1.0)"
    )
    last_updated: Optional[str] = Field(
        None,
        description="ISO 8601 timestamp of last config change"
    )


class PolicyConfigReloadRequest(BaseModel):
    """Request for policy config reload endpoint.
    
    Triggers manual reload of policy configuration from file or provided values.
    
    Attributes:
        config: Optional new config values to apply (overrides file)
        actor: Optional actor identity for audit log
    """
    config: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional new config values to apply (overrides file)"
    )
    actor: Optional[str] = Field(
        None,
        description="Optional actor identity for audit log"
    )


class PolicyConfigReloadResponse(BaseModel):
    """Response for policy config reload endpoint.
    
    Returns success/failure status and error details if reload failed.
    
    Attributes:
        success: Whether config reload succeeded
        message: Human-readable status message
        error: Error details if reload failed
        config: Current config after reload attempt
    """
    success: bool = Field(
        ...,
        description="Whether config reload succeeded"
    )
    message: str = Field(
        ...,
        description="Human-readable status message"
    )
    error: Optional[str] = Field(
        None,
        description="Error details if reload failed"
    )
    config: Optional[PolicyConfigResponse] = Field(
        None,
        description="Current config after reload attempt"
    )


# Resolve forward references for TurnResponse
TurnResponse.model_rebuild()
AdminTurnDetail.model_rebuild()
AdminRecentTurnsResponse.model_rebuild()
