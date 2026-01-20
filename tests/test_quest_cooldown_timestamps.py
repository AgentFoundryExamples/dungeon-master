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
"""Tests for quest completion timestamp-based cooldowns."""

from datetime import datetime, timezone, timedelta
from app.services.policy_engine import PolicyEngine
from app.turn_storage import TurnStorage


def test_quest_cooldown_with_completion_timestamp():
    """Test quest cooldown uses completion timestamp when available."""
    engine = PolicyEngine(
        quest_trigger_prob=1.0,  # Always pass roll
        quest_cooldown_turns=5,  # 5 turns = 300 seconds
        rng_seed=42
    )
    
    # Quest completed 6 minutes ago (360 seconds) - should be eligible
    completed_at = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
    
    decision = engine.evaluate_quest_trigger(
        character_id="test-char",
        turns_since_last_quest=0,  # Ignored when timestamp available
        has_active_quest=False,
        last_quest_completed_at=completed_at
    )
    
    assert decision.eligible is True, "Should be eligible after cooldown expires"
    assert decision.roll_passed is True


def test_quest_cooldown_not_met_with_completion_timestamp():
    """Test quest cooldown blocks trigger when completion timestamp is recent."""
    engine = PolicyEngine(
        quest_trigger_prob=1.0,  # Always pass roll if eligible
        quest_cooldown_turns=5,  # 5 turns = 300 seconds
        rng_seed=42
    )
    
    # Quest completed 2 minutes ago (120 seconds) - should not be eligible
    completed_at = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    
    decision = engine.evaluate_quest_trigger(
        character_id="test-char",
        turns_since_last_quest=10,  # Ignored when timestamp available
        has_active_quest=False,
        last_quest_completed_at=completed_at
    )
    
    assert decision.eligible is False, "Should not be eligible during cooldown"
    assert decision.roll_passed is False


def test_quest_cooldown_fallback_to_offered_timestamp():
    """Test quest cooldown falls back to offered timestamp when no completion timestamp."""
    engine = PolicyEngine(
        quest_trigger_prob=1.0,
        quest_cooldown_turns=5,  # 5 turns = 300 seconds
        rng_seed=42
    )
    
    # Quest offered 6 minutes ago - should be eligible
    offered_at = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
    
    decision = engine.evaluate_quest_trigger(
        character_id="test-char",
        turns_since_last_quest=0,  # Ignored when timestamp available
        has_active_quest=False,
        last_quest_completed_at=None,  # No completion timestamp
        last_quest_offered_at=offered_at  # Fallback to offered
    )
    
    assert decision.eligible is True, "Should use offered timestamp as fallback"
    assert decision.roll_passed is True


def test_quest_cooldown_completion_takes_precedence_over_offered():
    """Test completion timestamp takes precedence over offered timestamp."""
    engine = PolicyEngine(
        quest_trigger_prob=1.0,
        quest_cooldown_turns=5,  # 5 turns = 300 seconds
        rng_seed=42
    )
    
    # Quest offered 10 minutes ago (old), completed 2 minutes ago (recent)
    offered_at = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    completed_at = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    
    decision = engine.evaluate_quest_trigger(
        character_id="test-char",
        turns_since_last_quest=10,
        has_active_quest=False,
        last_quest_completed_at=completed_at,  # Recent completion
        last_quest_offered_at=offered_at  # Old offer (ignored)
    )
    
    assert decision.eligible is False, "Should use completion timestamp (not offered)"
    assert decision.roll_passed is False


def test_quest_cooldown_fallback_to_turn_counter():
    """Test quest cooldown falls back to turn counter when no timestamps."""
    engine = PolicyEngine(
        quest_trigger_prob=1.0,
        quest_cooldown_turns=5,
        rng_seed=42
    )
    
    # No timestamps - should use turn counter
    decision = engine.evaluate_quest_trigger(
        character_id="test-char",
        turns_since_last_quest=6,  # Past cooldown
        has_active_quest=False,
        last_quest_completed_at=None,
        last_quest_offered_at=None
    )
    
    assert decision.eligible is True, "Should fall back to turn counter"
    assert decision.roll_passed is True


def test_quest_cooldown_invalid_timestamp_falls_back():
    """Test invalid timestamp format falls back to turn counter."""
    engine = PolicyEngine(
        quest_trigger_prob=1.0,
        quest_cooldown_turns=5,
        rng_seed=42
    )
    
    # Invalid timestamp - should fall back to turn counter
    decision = engine.evaluate_quest_trigger(
        character_id="test-char",
        turns_since_last_quest=6,  # Past cooldown
        has_active_quest=False,
        last_quest_completed_at="invalid-timestamp",
        last_quest_offered_at=None
    )
    
    assert decision.eligible is True, "Should fall back to turn counter on invalid timestamp"
    assert decision.roll_passed is True


def test_turn_storage_quest_completion_tracking():
    """Test turn_storage stores and retrieves quest completion timestamps."""
    storage = TurnStorage()
    
    character_id = "test-char-123"
    completed_at = datetime.now(timezone.utc).isoformat()
    
    # Store completion timestamp
    storage.store_quest_completion(character_id, completed_at)
    
    # Retrieve completion timestamp
    retrieved = storage.get_quest_completion(character_id)
    
    assert retrieved == completed_at, "Should retrieve stored completion timestamp"


def test_turn_storage_quest_completion_not_found():
    """Test turn_storage returns None for characters without completion timestamps."""
    storage = TurnStorage()
    
    # Try to retrieve timestamp for character without stored data
    retrieved = storage.get_quest_completion("unknown-char")
    
    assert retrieved is None, "Should return None for unknown character"


def test_turn_storage_quest_completion_overwrite():
    """Test turn_storage overwrites previous completion timestamp."""
    storage = TurnStorage()
    
    character_id = "test-char-123"
    
    # Store first completion
    first_completed = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    storage.store_quest_completion(character_id, first_completed)
    
    # Store second completion (newer)
    second_completed = datetime.now(timezone.utc).isoformat()
    storage.store_quest_completion(character_id, second_completed)
    
    # Should return most recent completion
    retrieved = storage.get_quest_completion(character_id)
    assert retrieved == second_completed, "Should overwrite with newer completion timestamp"


def test_turn_storage_stats_includes_quest_completions():
    """Test turn_storage stats include quest completion count."""
    storage = TurnStorage()
    
    # Store completions for multiple characters
    storage.store_quest_completion("char-1", datetime.now(timezone.utc).isoformat())
    storage.store_quest_completion("char-2", datetime.now(timezone.utc).isoformat())
    storage.store_quest_completion("char-3", datetime.now(timezone.utc).isoformat())
    
    stats = storage.get_storage_stats()
    
    assert "quest_completion_tracked" in stats, "Stats should include quest completion count"
    assert stats["quest_completion_tracked"] == 3, "Should track 3 completion timestamps"
