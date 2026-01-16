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
"""Tests for PromptBuilder."""

import pytest
from app.prompting.prompt_builder import PromptBuilder
from app.models import JourneyLogContext


@pytest.fixture
def prompt_builder():
    """Fixture providing a PromptBuilder instance."""
    return PromptBuilder()


@pytest.fixture
def sample_context():
    """Fixture providing sample journey-log context."""
    return JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "origin:nexus", "display_name": "The Nexus"},
        active_quest={
            "name": "Find the Ancient Artifact",
            "description": "Locate the lost artifact in the ruins",
            "completion_state": "in_progress",
            "requirements": ["Enter the ruins", "Defeat the guardian"]
        },
        combat_state=None,
        recent_history=[
            {
                "player_action": "I look around",
                "gm_response": "You see a vast hall with pillars",
                "timestamp": "2025-01-15T10:00:00Z"
            }
        ]
    )


def test_build_prompt_structure(prompt_builder, sample_context):
    """Test that build_prompt returns correct structure."""
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=sample_context,
        user_action="I search the room"
    )
    
    # System instructions should be present
    assert isinstance(system_instructions, str)
    assert len(system_instructions) > 0
    assert "narrative engine" in system_instructions.lower()
    
    # User prompt should contain context and action
    assert isinstance(user_prompt, str)
    assert "CHARACTER STATUS: Healthy" in user_prompt
    assert "CURRENT LOCATION: The Nexus" in user_prompt
    assert "PLAYER ACTION:" in user_prompt
    assert "I search the room" in user_prompt


def test_build_prompt_with_quest(prompt_builder, sample_context):
    """Test prompt building with active quest."""
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=sample_context,
        user_action="I continue my quest"
    )
    
    assert "ACTIVE QUEST:" in user_prompt
    assert "Find the Ancient Artifact" in user_prompt
    assert "in_progress" in user_prompt
    assert "Enter the ruins" in user_prompt


def test_build_prompt_without_quest(prompt_builder):
    """Test prompt building without active quest."""
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "origin:nexus", "display_name": "The Nexus"},
        active_quest=None,
        combat_state=None,
        recent_history=[]
    )
    
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=context,
        user_action="I explore"
    )
    
    assert "ACTIVE QUEST:" not in user_prompt


def test_build_prompt_with_combat(prompt_builder):
    """Test prompt building with active combat."""
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Wounded",
        location={"id": "dungeon:cave", "display_name": "Dark Cave"},
        active_quest=None,
        combat_state={
            "combat_id": "combat-123",
            "turn": 3,
            "enemies": [
                {
                    "enemy_id": "goblin-1",
                    "name": "Goblin Scout",
                    "status": "Healthy",
                    "weapon": "Short sword"
                },
                {
                    "enemy_id": "goblin-2",
                    "name": "Goblin Warrior",
                    "status": "Wounded",
                    "weapon": "Axe"
                }
            ]
        },
        recent_history=[]
    )
    
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=context,
        user_action="I attack the wounded goblin"
    )
    
    assert "COMBAT STATE:" in user_prompt
    assert "Turn: 3" in user_prompt
    assert "Goblin Scout: Healthy" in user_prompt
    assert "Goblin Warrior: Wounded" in user_prompt
    assert "Short sword" in user_prompt


def test_build_prompt_with_history(prompt_builder):
    """Test prompt building with recent history."""
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "origin:nexus", "display_name": "The Nexus"},
        active_quest=None,
        combat_state=None,
        recent_history=[
            {
                "player_action": "I enter the temple",
                "gm_response": "The ancient temple looms before you",
                "timestamp": "2025-01-15T10:00:00Z"
            },
            {
                "player_action": "I examine the altar",
                "gm_response": "The altar has mysterious inscriptions",
                "timestamp": "2025-01-15T10:01:00Z"
            }
        ]
    )
    
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=context,
        user_action="I read the inscriptions"
    )
    
    assert "RECENT NARRATIVE HISTORY:" in user_prompt
    assert "I enter the temple" in user_prompt
    assert "I examine the altar" in user_prompt
    assert "ancient temple looms" in user_prompt


def test_format_location_with_dict(prompt_builder):
    """Test location formatting with dict."""
    location = {"id": "origin:nexus", "display_name": "The Nexus"}
    formatted = prompt_builder._format_location(location)
    assert "The Nexus" in formatted
    assert "origin:nexus" in formatted


def test_format_location_with_string(prompt_builder):
    """Test location formatting with string."""
    location = "The Dark Forest"
    formatted = prompt_builder._format_location(location)
    assert formatted == "The Dark Forest"


def test_serialize_context_complete(prompt_builder, sample_context):
    """Test complete context serialization."""
    serialized = prompt_builder._serialize_context(sample_context)
    
    # Should contain all major sections
    assert "CHARACTER STATUS:" in serialized
    assert "CURRENT LOCATION:" in serialized
    assert "ACTIVE QUEST:" in serialized
    assert "RECENT NARRATIVE HISTORY:" in serialized


def test_history_truncation(prompt_builder):
    """Test that long history is truncated properly."""
    # Create context with many history turns
    history = []
    for i in range(10):
        history.append({
            "player_action": f"Action {i}" * 50,  # Long action
            "gm_response": f"Response {i}" * 100,  # Long response
            "timestamp": f"2025-01-15T10:{i:02d}:00Z"
        })
    
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "test:location", "display_name": "Test Location"},
        active_quest=None,
        combat_state=None,
        recent_history=history
    )
    
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=context,
        user_action="I continue"
    )
    
    # Should show only last 5 turns
    assert "Turn 1:" in user_prompt or "Turn 5:" in user_prompt
    # Long texts should be truncated (indicated by ...)
    assert "..." in user_prompt


def test_prompt_includes_json_schema(prompt_builder, sample_context):
    """Test that prompt includes DungeonMasterOutcome JSON schema."""
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=sample_context,
        user_action="I search the room"
    )
    
    # System instructions should include schema
    assert "DungeonMasterOutcome" in system_instructions
    assert "schema" in system_instructions.lower()
    assert '"narrative"' in system_instructions
    assert '"intents"' in system_instructions
    
    # Should have explicit JSON-only instructions
    assert "JSON" in system_instructions
    assert "valid JSON" in system_instructions or "ONLY" in system_instructions


def test_prompt_includes_example_json(prompt_builder, sample_context):
    """Test that prompt includes example JSON output."""
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=sample_context,
        user_action="I search the room"
    )
    
    # Should include example output
    assert "EXAMPLE" in system_instructions or "example" in system_instructions
    # Example should be valid JSON
    assert '"narrative":' in system_instructions
    assert '"intents":' in system_instructions


def test_prompt_clarifies_deterministic_subsystems(prompt_builder, sample_context):
    """Test that prompt clarifies subsystem decisions are deterministic."""
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=sample_context,
        user_action="I search the room"
    )
    
    # Should clarify that LLM doesn't decide subsystem eligibility
    instructions_lower = system_instructions.lower()
    
    # Check for deterministic policy mention
    has_deterministic = "deterministic" in instructions_lower
    
    # Check for game system mention (logic or engine)
    has_game_system = ("game logic" in instructions_lower or 
                       "game engine" in instructions_lower or
                       "game service" in instructions_lower)
    
    assert has_deterministic, "System instructions should mention deterministic behavior"
    assert has_game_system, "System instructions should clarify game system handles decisions"


def test_user_prompt_reminds_json_only(prompt_builder, sample_context):
    """Test that user prompt reminds to output only JSON."""
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=sample_context,
        user_action="I search the room"
    )
    
    # User prompt should remind to output only JSON
    assert "JSON" in user_prompt
    assert "ONLY" in user_prompt or "only" in user_prompt


def test_prompt_includes_policy_hints_when_present(prompt_builder):
    """Test that policy hints are included in prompt when provided."""
    from app.models import PolicyHints, QuestTriggerDecision, POITriggerDecision
    
    # Create context with policy hints
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "origin:nexus", "display_name": "The Nexus"},
        active_quest=None,
        combat_state=None,
        recent_history=[],
        policy_hints=PolicyHints(
            quest_trigger_decision=QuestTriggerDecision(
                eligible=True,
                probability=0.3,
                roll_passed=True
            ),
            poi_trigger_decision=POITriggerDecision(
                eligible=True,
                probability=0.2,
                roll_passed=False
            )
        )
    )
    
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=context,
        user_action="I explore"
    )
    
    # Policy hints should be in the user prompt
    assert "POLICY HINTS:" in user_prompt
    assert "Quest Trigger:" in user_prompt
    assert "POI Creation:" in user_prompt
    # Should show ALLOWED/NOT ALLOWED status
    assert "ALLOWED" in user_prompt
    assert "NOT ALLOWED" in user_prompt


def test_prompt_excludes_policy_hints_when_absent(prompt_builder):
    """Test that policy hints are excluded when not provided."""
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "origin:nexus", "display_name": "The Nexus"},
        active_quest=None,
        combat_state=None,
        recent_history=[],
        policy_hints=None
    )
    
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=context,
        user_action="I explore"
    )
    
    # Policy hints should NOT be in the user prompt
    assert "POLICY HINTS:" not in user_prompt


def test_policy_hints_format_quest_eligible_roll_passed(prompt_builder):
    """Test policy hints formatting when quest is eligible and roll passes."""
    from app.models import PolicyHints, QuestTriggerDecision, POITriggerDecision
    
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "town:square", "display_name": "Town Square"},
        active_quest=None,
        combat_state=None,
        recent_history=[],
        policy_hints=PolicyHints(
            quest_trigger_decision=QuestTriggerDecision(
                eligible=True,
                probability=0.5,
                roll_passed=True
            ),
            poi_trigger_decision=POITriggerDecision(
                eligible=False,
                probability=0.2,
                roll_passed=False
            )
        )
    )
    
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=context,
        user_action="I look around"
    )
    
    # Quest should show ALLOWED
    assert "Quest Trigger: ALLOWED" in user_prompt
    # POI should show NOT ALLOWED
    assert "POI Creation: NOT ALLOWED" in user_prompt
    # Should include a reason for POI not being allowed
    assert "Reason:" in user_prompt


def test_policy_hints_format_all_ineligible(prompt_builder):
    """Test policy hints formatting when both quest and POI are ineligible."""
    from app.models import PolicyHints, QuestTriggerDecision, POITriggerDecision
    
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "dungeon:room", "display_name": "Dark Room"},
        active_quest={"name": "Active Quest", "description": "Ongoing", "completion_state": "in_progress"},
        combat_state=None,
        recent_history=[],
        policy_hints=PolicyHints(
            quest_trigger_decision=QuestTriggerDecision(
                eligible=False,
                probability=0.3,
                roll_passed=False
            ),
            poi_trigger_decision=POITriggerDecision(
                eligible=False,
                probability=0.2,
                roll_passed=False
            )
        )
    )
    
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=context,
        user_action="I continue my quest"
    )
    
    # Both should show NOT ALLOWED
    assert "POLICY HINTS:" in user_prompt
    assert "Quest Trigger: NOT ALLOWED" in user_prompt
    assert "POI Creation: NOT ALLOWED" in user_prompt
    # Should include reasons for ineligibility
    assert "Reason:" in user_prompt


def test_prompt_includes_memory_sparks_when_present(prompt_builder):
    """Test that memory sparks (POIs) are included in prompt when provided."""
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "town:square", "display_name": "Town Square"},
        active_quest=None,
        combat_state=None,
        recent_history=[],
        memory_sparks=[
            {
                "id": "poi-1",
                "name": "The Old Mill",
                "description": "An abandoned mill at the edge of the forest",
                "timestamp_discovered": "2025-01-15T10:00:00Z",
                "tags": ["mill", "forest", "abandoned"]
            },
            {
                "id": "poi-2",
                "name": "Rusty Tavern",
                "description": "A weathered tavern in the town square",
                "timestamp_discovered": "2025-01-15T09:00:00Z",
                "tags": ["tavern", "town"]
            }
        ]
    )
    
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=context,
        user_action="I explore the area"
    )
    
    # Memory sparks should be in the user prompt
    assert "MEMORY SPARKS" in user_prompt
    assert "Previously Discovered Locations" in user_prompt
    assert "The Old Mill" in user_prompt
    assert "Rusty Tavern" in user_prompt
    assert "abandoned mill" in user_prompt
    assert "weathered tavern" in user_prompt
    assert "Tags:" in user_prompt


def test_prompt_excludes_memory_sparks_when_absent(prompt_builder):
    """Test that memory sparks are excluded when not provided."""
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "town:square", "display_name": "Town Square"},
        active_quest=None,
        combat_state=None,
        recent_history=[],
        memory_sparks=[]  # Empty list
    )
    
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=context,
        user_action="I explore"
    )
    
    # Memory sparks should NOT be in the user prompt
    assert "MEMORY SPARKS" not in user_prompt
    assert "Previously Discovered Locations" not in user_prompt


def test_memory_sparks_deterministic_ordering(prompt_builder):
    """Test that memory sparks are formatted with deterministic ordering."""
    # Create memory sparks with different timestamps
    memory_sparks = [
        {
            "id": "poi-3",
            "name": "C Location",
            "description": "Third location",
            "timestamp_discovered": "2025-01-15T08:00:00Z"
        },
        {
            "id": "poi-1",
            "name": "A Location",
            "description": "First location",
            "timestamp_discovered": "2025-01-15T10:00:00Z"
        },
        {
            "id": "poi-2",
            "name": "B Location",
            "description": "Second location",
            "timestamp_discovered": "2025-01-15T09:00:00Z"
        }
    ]
    
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "test:location", "display_name": "Test Location"},
        active_quest=None,
        combat_state=None,
        recent_history=[],
        memory_sparks=memory_sparks
    )
    
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=context,
        user_action="I look around"
    )
    
    # Should be ordered by timestamp descending (newest first)
    # So order should be: A Location, B Location, C Location
    a_pos = user_prompt.index("A Location")
    b_pos = user_prompt.index("B Location")
    c_pos = user_prompt.index("C Location")
    
    assert a_pos < b_pos < c_pos, "Memory sparks should be ordered by timestamp descending"


def test_memory_sparks_truncates_long_descriptions(prompt_builder):
    """Test that long POI descriptions are truncated."""
    memory_sparks = [
        {
            "id": "poi-1",
            "name": "Long Description Location",
            "description": "A" * 250,  # 250 character description (over 200 limit)
            "timestamp_discovered": "2025-01-15T10:00:00Z"
        }
    ]
    
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "test:location", "display_name": "Test Location"},
        active_quest=None,
        combat_state=None,
        recent_history=[],
        memory_sparks=memory_sparks
    )
    
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=context,
        user_action="I explore"
    )
    
    # Description should be truncated with ...
    assert "..." in user_prompt
    # Should not contain all 250 A's
    assert "A" * 250 not in user_prompt
    # Should contain up to 200 A's plus ...
    assert "A" * 200 in user_prompt


def test_memory_sparks_handles_missing_fields(prompt_builder):
    """Test that memory sparks handle missing optional fields gracefully."""
    memory_sparks = [
        {
            "id": "poi-1",
            "name": "Minimal POI",
            # No description, no tags, no timestamp
        },
        {
            "id": "poi-2",
            # No name either
        }
    ]
    
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "test:location", "display_name": "Test Location"},
        active_quest=None,
        combat_state=None,
        recent_history=[],
        memory_sparks=memory_sparks
    )
    
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=context,
        user_action="I explore"
    )
    
    # Should not crash and should include what's available
    assert "MEMORY SPARKS" in user_prompt
    assert "Minimal POI" in user_prompt or "Unknown Location" in user_prompt
