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
"""Integration tests for policy state context flow through services."""

from app.models import JourneyLogContext, PolicyState
from app.services.policy_engine import PolicyEngine


def test_policy_engine_with_context_policy_state():
    """Test that PolicyEngine can use policy_state from JourneyLogContext."""
    # Create a JourneyLogContext with policy state
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "origin:nexus", "display_name": "The Nexus"},
        policy_state=PolicyState(
            turns_since_last_quest=10,
            turns_since_last_poi=5,
            has_active_quest=False,
            combat_active=False
        )
    )
    
    # Create PolicyEngine with known config
    engine = PolicyEngine(
        quest_trigger_prob=1.0,  # Always trigger if eligible
        quest_cooldown_turns=5,
        poi_trigger_prob=1.0,
        poi_cooldown_turns=3
    )
    
    # Evaluate quest trigger using data from policy_state
    quest_decision = engine.evaluate_quest_trigger(
        character_id=context.character_id,
        turns_since_last_quest=context.policy_state.turns_since_last_quest,
        has_active_quest=context.policy_state.has_active_quest
    )
    
    # Should be eligible and pass (10 turns >= 5 cooldown, no active quest, prob=1.0)
    assert quest_decision.eligible is True
    assert quest_decision.roll_passed is True
    
    # Evaluate POI trigger using data from policy_state
    poi_decision = engine.evaluate_poi_trigger(
        character_id=context.character_id,
        turns_since_last_poi=context.policy_state.turns_since_last_poi
    )
    
    # Should be eligible and pass (5 turns >= 3 cooldown, prob=1.0)
    assert poi_decision.eligible is True
    assert poi_decision.roll_passed is True


def test_policy_engine_with_context_combat_blocks_quest():
    """Test that combat_active flag from policy_state can be used for decisions."""
    # Create context with active combat
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "dungeon:floor1", "display_name": "Dark Dungeon"},
        policy_state=PolicyState(
            turns_since_last_quest=10,
            turns_since_last_poi=5,
            has_active_quest=False,
            combat_active=True  # Currently in combat
        )
    )
    
    # In a real implementation, you might have logic that checks combat_active
    # before offering quests. This test verifies the data is available.
    assert context.policy_state.combat_active is True
    
    # Future enhancement: PolicyEngine could consider combat_active
    # For now, we verify the data flows correctly
    engine = PolicyEngine(quest_trigger_prob=1.0, quest_cooldown_turns=5)
    
    # Current implementation doesn't check combat, but data is available
    # if future requirements add combat blocking
    quest_decision = engine.evaluate_quest_trigger(
        character_id=context.character_id,
        turns_since_last_quest=context.policy_state.turns_since_last_quest,
        has_active_quest=context.policy_state.has_active_quest
    )
    
    # Currently eligible (combat doesn't block in current implementation)
    assert quest_decision.eligible is True


def test_policy_engine_with_context_meta_flags():
    """Test that meta flags from policy_state are accessible."""
    # Create context with player engagement flags
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "origin:nexus", "display_name": "The Nexus"},
        policy_state=PolicyState(
            turns_since_last_quest=10,
            turns_since_last_poi=5,
            has_active_quest=False,
            combat_active=False,
            user_is_wandering=True,
            requested_guidance=True
        )
    )
    
    # Verify meta flags are accessible for future policy logic
    assert context.policy_state.user_is_wandering is True
    assert context.policy_state.requested_guidance is True
    
    # Future enhancement: PolicyEngine could adjust probabilities based on these flags
    # For example, increase quest probability if user is wandering or requested guidance


def test_policy_engine_with_context_additional_fields():
    """Test that additional_fields are preserved for future extensions."""
    # Create context with custom additional fields
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "origin:nexus", "display_name": "The Nexus"},
        additional_fields={
            "custom_cooldown_multiplier": 2.0,
            "special_event_active": True,
            "last_npc_interaction": "2025-01-15T10:00:00Z"
        }
    )
    
    # Verify additional_fields are preserved
    assert context.additional_fields["custom_cooldown_multiplier"] == 2.0
    assert context.additional_fields["special_event_active"] is True
    assert "last_npc_interaction" in context.additional_fields
    
    # Future enhancement: PolicyEngine or other services could use these fields
    # for custom game logic without changing core models


def test_context_default_policy_state():
    """Test that JourneyLogContext creates default PolicyState if not provided."""
    # Create context without explicit policy_state
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Healthy",
        location={"id": "origin:nexus", "display_name": "The Nexus"}
    )
    
    # Should have default PolicyState with safe defaults
    assert context.policy_state is not None
    assert context.policy_state.turns_since_last_quest == 0
    assert context.policy_state.turns_since_last_poi == 0
    assert context.policy_state.has_active_quest is False
    assert context.policy_state.combat_active is False
    assert context.policy_state.last_quest_offered_at is None
    assert context.policy_state.last_poi_created_at is None
