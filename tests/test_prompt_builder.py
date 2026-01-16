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
