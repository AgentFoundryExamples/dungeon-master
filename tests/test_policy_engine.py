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
"""Tests for PolicyEngine service."""

import pytest
from app.services.policy_engine import PolicyEngine
from app.models import QuestTriggerDecision, POITriggerDecision


def test_policy_engine_init_default():
    """Test PolicyEngine initialization with default values."""
    engine = PolicyEngine()
    
    assert engine.quest_trigger_prob == 0.3
    assert engine.quest_cooldown_turns == 5
    assert engine.poi_trigger_prob == 0.2
    assert engine.poi_cooldown_turns == 3
    assert engine.rng_seed is None


def test_policy_engine_init_custom():
    """Test PolicyEngine initialization with custom values."""
    engine = PolicyEngine(
        quest_trigger_prob=0.5,
        quest_cooldown_turns=10,
        poi_trigger_prob=0.4,
        poi_cooldown_turns=7,
        rng_seed=42
    )
    
    assert engine.quest_trigger_prob == 0.5
    assert engine.quest_cooldown_turns == 10
    assert engine.poi_trigger_prob == 0.4
    assert engine.poi_cooldown_turns == 7
    assert engine.rng_seed == 42


def test_policy_engine_rejects_invalid_probabilities():
    """Test that probabilities outside [0, 1] range are rejected."""
    import pytest
    
    # Test probability > 1.0
    with pytest.raises(ValueError, match="quest_trigger_prob must be between 0.0 and 1.0"):
        PolicyEngine(quest_trigger_prob=1.5)
    
    # Test probability < 0.0
    with pytest.raises(ValueError, match="poi_trigger_prob must be between 0.0 and 1.0"):
        PolicyEngine(poi_trigger_prob=-0.5)


def test_policy_engine_accepts_zero_cooldown():
    """Test that zero cooldown values are accepted."""
    engine = PolicyEngine(
        quest_cooldown_turns=0,
        poi_cooldown_turns=0
    )
    
    assert engine.quest_cooldown_turns == 0
    assert engine.poi_cooldown_turns == 0


def test_policy_engine_accepts_negative_cooldown():
    """Test that negative cooldown values are accepted."""
    engine = PolicyEngine(
        quest_cooldown_turns=-5,
        poi_cooldown_turns=-3
    )
    
    assert engine.quest_cooldown_turns == -5
    assert engine.poi_cooldown_turns == -3


def test_quest_trigger_eligible_passes_cooldown():
    """Test quest trigger when eligible and passes cooldown."""
    engine = PolicyEngine(
        quest_trigger_prob=1.0,  # Always pass
        quest_cooldown_turns=5
    )
    
    decision = engine.evaluate_quest_trigger(
        character_id="test-char-1",
        turns_since_last_quest=10,  # Well past cooldown
        has_active_quest=False
    )
    
    assert isinstance(decision, QuestTriggerDecision)
    assert decision.eligible is True
    assert decision.probability == 1.0
    assert decision.roll_passed is True


def test_quest_trigger_ineligible_has_active_quest():
    """Test quest trigger when character already has active quest."""
    engine = PolicyEngine(quest_trigger_prob=1.0)
    
    decision = engine.evaluate_quest_trigger(
        character_id="test-char-1",
        turns_since_last_quest=10,
        has_active_quest=True  # Already has quest
    )
    
    assert decision.eligible is False
    assert decision.probability == 1.0
    assert decision.roll_passed is False


def test_quest_trigger_ineligible_cooldown_not_met():
    """Test quest trigger when cooldown period not met."""
    engine = PolicyEngine(
        quest_trigger_prob=1.0,
        quest_cooldown_turns=5
    )
    
    decision = engine.evaluate_quest_trigger(
        character_id="test-char-1",
        turns_since_last_quest=3,  # Not enough turns
        has_active_quest=False
    )
    
    assert decision.eligible is False
    assert decision.probability == 1.0
    assert decision.roll_passed is False


def test_quest_trigger_eligible_roll_fails():
    """Test quest trigger when eligible but roll fails."""
    engine = PolicyEngine(quest_trigger_prob=0.0)  # Always fail
    
    decision = engine.evaluate_quest_trigger(
        character_id="test-char-1",
        turns_since_last_quest=10,
        has_active_quest=False
    )
    
    assert decision.eligible is True
    assert decision.probability == 0.0
    assert decision.roll_passed is False


def test_quest_trigger_zero_cooldown_always_eligible():
    """Test quest trigger with zero cooldown is always eligible."""
    engine = PolicyEngine(
        quest_trigger_prob=1.0,
        quest_cooldown_turns=0
    )
    
    decision = engine.evaluate_quest_trigger(
        character_id="test-char-1",
        turns_since_last_quest=0,  # Zero turns
        has_active_quest=False
    )
    
    assert decision.eligible is True
    assert decision.roll_passed is True


def test_poi_trigger_eligible_passes_cooldown():
    """Test POI trigger when eligible and passes cooldown."""
    engine = PolicyEngine(
        poi_trigger_prob=1.0,  # Always pass
        poi_cooldown_turns=3
    )
    
    decision = engine.evaluate_poi_trigger(
        character_id="test-char-1",
        turns_since_last_poi=5  # Past cooldown
    )
    
    assert isinstance(decision, POITriggerDecision)
    assert decision.eligible is True
    assert decision.probability == 1.0
    assert decision.roll_passed is True


def test_poi_trigger_ineligible_cooldown_not_met():
    """Test POI trigger when cooldown period not met."""
    engine = PolicyEngine(
        poi_trigger_prob=1.0,
        poi_cooldown_turns=3
    )
    
    decision = engine.evaluate_poi_trigger(
        character_id="test-char-1",
        turns_since_last_poi=2  # Not enough turns
    )
    
    assert decision.eligible is False
    assert decision.probability == 1.0
    assert decision.roll_passed is False


def test_poi_trigger_eligible_roll_fails():
    """Test POI trigger when eligible but roll fails."""
    engine = PolicyEngine(poi_trigger_prob=0.0)  # Always fail
    
    decision = engine.evaluate_poi_trigger(
        character_id="test-char-1",
        turns_since_last_poi=10
    )
    
    assert decision.eligible is True
    assert decision.probability == 0.0
    assert decision.roll_passed is False


def test_poi_trigger_zero_cooldown_always_eligible():
    """Test POI trigger with zero cooldown is always eligible."""
    engine = PolicyEngine(
        poi_trigger_prob=1.0,
        poi_cooldown_turns=0
    )
    
    decision = engine.evaluate_poi_trigger(
        character_id="test-char-1",
        turns_since_last_poi=0  # Zero turns
    )
    
    assert decision.eligible is True
    assert decision.roll_passed is True


def test_poi_trigger_allowed_during_active_quest():
    """Test POI trigger is always allowed during active quests, bypassing cooldown."""
    engine = PolicyEngine(
        poi_trigger_prob=1.0,
        poi_cooldown_turns=5  # High cooldown
    )
    
    # Test that POI is allowed even with cooldown not met when quest is active
    decision = engine.evaluate_poi_trigger(
        character_id="test-char-1",
        turns_since_last_poi=1,  # Not enough turns normally
        has_active_quest=True
    )
    
    assert decision.eligible is True, "POI should be eligible during active quest"
    assert decision.roll_passed is True
    
    # Verify it still respects cooldown when no quest
    decision_no_quest = engine.evaluate_poi_trigger(
        character_id="test-char-1",
        turns_since_last_poi=1,
        has_active_quest=False
    )
    
    assert decision_no_quest.eligible is False, "POI should respect cooldown without active quest"


def test_seeded_rng_deterministic():
    """Test that seeded RNG produces deterministic results."""
    # Create two engines with same seed
    engine1 = PolicyEngine(quest_trigger_prob=0.5, rng_seed=42)
    engine2 = PolicyEngine(quest_trigger_prob=0.5, rng_seed=42)
    
    # Run same evaluation multiple times
    results1 = []
    results2 = []
    
    for i in range(10):
        decision1 = engine1.evaluate_quest_trigger(
            character_id="test-char-1",
            turns_since_last_quest=10,
            has_active_quest=False
        )
        decision2 = engine2.evaluate_quest_trigger(
            character_id="test-char-1",
            turns_since_last_quest=10,
            has_active_quest=False
        )
        results1.append(decision1.roll_passed)
        results2.append(decision2.roll_passed)
    
    # Results should be identical
    assert results1 == results2


def test_character_specific_seeding():
    """Test that different characters get different RNG sequences."""
    engine = PolicyEngine(quest_trigger_prob=0.5, rng_seed=42)
    
    # Run evaluation for two different characters
    results_char1 = []
    results_char2 = []
    
    for i in range(10):
        decision1 = engine.evaluate_quest_trigger(
            character_id="char-1",
            turns_since_last_quest=10,
            has_active_quest=False
        )
        decision2 = engine.evaluate_quest_trigger(
            character_id="char-2",
            turns_since_last_quest=10,
            has_active_quest=False
        )
        results_char1.append(decision1.roll_passed)
        results_char2.append(decision2.roll_passed)
    
    # Results should differ (with very high probability)
    # At 0.5 probability, chance of identical sequences is (0.5)^10 = ~0.001
    assert results_char1 != results_char2


def test_seed_override():
    """Test that seed override produces deterministic results."""
    engine = PolicyEngine(quest_trigger_prob=0.5)
    
    # Use seed override for deterministic behavior
    decision1 = engine.evaluate_quest_trigger(
        character_id="test-char-1",
        turns_since_last_quest=10,
        has_active_quest=False,
        seed_override=12345
    )
    
    decision2 = engine.evaluate_quest_trigger(
        character_id="test-char-1",
        turns_since_last_quest=10,
        has_active_quest=False,
        seed_override=12345
    )
    
    # Results should be identical
    assert decision1.roll_passed == decision2.roll_passed


def test_debug_metadata():
    """Test that debug metadata is available."""
    engine = PolicyEngine(
        quest_trigger_prob=0.3,
        quest_cooldown_turns=5,
        poi_trigger_prob=0.2,
        poi_cooldown_turns=3,
        rng_seed=42
    )
    
    metadata = engine.get_debug_metadata()
    
    assert metadata["quest_trigger_prob"] == 0.3
    assert metadata["quest_cooldown_turns"] == 5
    assert metadata["poi_trigger_prob"] == 0.2
    assert metadata["poi_cooldown_turns"] == 3
    assert metadata["rng_seed_set"] is True
    assert metadata["character_rngs_count"] == 0  # No evaluations yet


def test_debug_metadata_no_seed():
    """Test debug metadata when no seed is set."""
    engine = PolicyEngine()
    
    metadata = engine.get_debug_metadata()
    
    assert metadata["rng_seed_set"] is False


def test_probability_edge_cases():
    """Test probability edge cases (0.0, 0.5, 1.0)."""
    # Probability 0.0 should always fail
    engine_zero = PolicyEngine(quest_trigger_prob=0.0)
    for _ in range(10):
        decision = engine_zero.evaluate_quest_trigger(
            character_id="test-char",
            turns_since_last_quest=10,
            has_active_quest=False
        )
        assert decision.roll_passed is False
    
    # Probability 1.0 should always pass
    engine_one = PolicyEngine(quest_trigger_prob=1.0)
    for _ in range(10):
        decision = engine_one.evaluate_quest_trigger(
            character_id="test-char",
            turns_since_last_quest=10,
            has_active_quest=False
        )
        assert decision.roll_passed is True
    
    # Probability 0.5 should have mixed results (with high probability)
    engine_half = PolicyEngine(quest_trigger_prob=0.5, rng_seed=42)
    results = []
    for _ in range(20):
        decision = engine_half.evaluate_quest_trigger(
            character_id="test-char",
            turns_since_last_quest=10,
            has_active_quest=False
        )
        results.append(decision.roll_passed)
    
    # Should have at least some True and some False (very likely)
    assert True in results
    assert False in results


def test_config_integration():
    """Test PolicyEngine initialization from config-like dict."""
    config = {
        "quest_trigger_prob": 0.4,
        "quest_cooldown_turns": 8,
        "poi_trigger_prob": 0.3,
        "poi_cooldown_turns": 5,
        "rng_seed": 999
    }
    
    engine = PolicyEngine(**config)
    
    assert engine.quest_trigger_prob == 0.4
    assert engine.quest_cooldown_turns == 8
    assert engine.poi_trigger_prob == 0.3
    assert engine.poi_cooldown_turns == 5
    assert engine.rng_seed == 999


def test_simultaneous_quest_and_poi_eligibility():
    """Test that quest and POI can both be eligible with independent rolls.
    
    This validates that guardrails use separate random rolls for each subsystem.
    """
    engine = PolicyEngine(
        quest_trigger_prob=1.0,  # Always pass quest roll
        quest_cooldown_turns=0,
        poi_trigger_prob=1.0,    # Always pass POI roll
        poi_cooldown_turns=0,
        rng_seed=42  # Deterministic
    )
    
    # Both should be eligible and pass
    quest_decision = engine.evaluate_quest_trigger(
        character_id="test-char",
        turns_since_last_quest=10,
        has_active_quest=False
    )
    
    poi_decision = engine.evaluate_poi_trigger(
        character_id="test-char",
        turns_since_last_poi=10
    )
    
    # Both should pass independently
    assert quest_decision.eligible is True
    assert quest_decision.roll_passed is True
    assert poi_decision.eligible is True
    assert poi_decision.roll_passed is True


def test_simultaneous_eligibility_different_probabilities():
    """Test simultaneous eligibility with different probabilities for quest and POI.
    
    This ensures that different probability settings don't interfere with each other.
    """
    engine = PolicyEngine(
        quest_trigger_prob=1.0,  # Always pass
        quest_cooldown_turns=0,
        poi_trigger_prob=0.0,    # Always fail
        poi_cooldown_turns=0,
        rng_seed=42
    )
    
    quest_decision = engine.evaluate_quest_trigger(
        character_id="test-char",
        turns_since_last_quest=10,
        has_active_quest=False
    )
    
    poi_decision = engine.evaluate_poi_trigger(
        character_id="test-char",
        turns_since_last_poi=10
    )
    
    # Quest should pass, POI should fail
    assert quest_decision.eligible is True
    assert quest_decision.roll_passed is True
    assert poi_decision.eligible is True
    assert poi_decision.roll_passed is False


def test_cooldown_boundary_exact_threshold():
    """Test cooldown boundary at exact threshold transition."""
    engine = PolicyEngine(
        quest_trigger_prob=1.0,
        quest_cooldown_turns=5,
        rng_seed=42
    )
    
    # At cooldown - 1, should be ineligible
    decision_before = engine.evaluate_quest_trigger(
        character_id="test-char",
        turns_since_last_quest=4,
        has_active_quest=False
    )
    assert decision_before.eligible is False
    assert decision_before.roll_passed is False
    
    # At exact cooldown threshold, should be eligible
    decision_at = engine.evaluate_quest_trigger(
        character_id="test-char",
        turns_since_last_quest=5,
        has_active_quest=False
    )
    assert decision_at.eligible is True
    assert decision_at.roll_passed is True
    
    # After cooldown, should remain eligible
    decision_after = engine.evaluate_quest_trigger(
        character_id="test-char",
        turns_since_last_quest=6,
        has_active_quest=False
    )
    assert decision_after.eligible is True
    assert decision_after.roll_passed is True


def test_poi_cooldown_boundary_exact_threshold():
    """Test POI cooldown boundary at exact threshold transition."""
    engine = PolicyEngine(
        poi_trigger_prob=1.0,
        poi_cooldown_turns=3,
        rng_seed=42
    )
    
    # At cooldown - 1, should be ineligible
    decision_before = engine.evaluate_poi_trigger(
        character_id="test-char",
        turns_since_last_poi=2
    )
    assert decision_before.eligible is False
    assert decision_before.roll_passed is False
    
    # At exact cooldown threshold, should be eligible
    decision_at = engine.evaluate_poi_trigger(
        character_id="test-char",
        turns_since_last_poi=3
    )
    assert decision_at.eligible is True
    assert decision_at.roll_passed is True
    
    # After cooldown, should remain eligible
    decision_after = engine.evaluate_poi_trigger(
        character_id="test-char",
        turns_since_last_poi=4
    )
    assert decision_after.eligible is True
    assert decision_after.roll_passed is True


def test_seed_isolation_between_evaluations():
    """Test that character-specific seeding provides independent RNG sequences.
    
    Each character gets their own RNG sequence derived from the seed,
    ensuring evaluations for different characters don't interfere.
    """
    engine = PolicyEngine(quest_trigger_prob=0.5, rng_seed=42)
    
    # Evaluate for character 1 multiple times consecutively
    results_char1_first = []
    for _ in range(5):
        decision = engine.evaluate_quest_trigger(
            character_id="char-1",
            turns_since_last_quest=10,
            has_active_quest=False
        )
        results_char1_first.append(decision.roll_passed)
    
    # Evaluate for character 2 consecutively
    results_char2 = []
    for _ in range(5):
        decision = engine.evaluate_quest_trigger(
            character_id="char-2",
            turns_since_last_quest=10,
            has_active_quest=False
        )
        results_char2.append(decision.roll_passed)
    
    # Create a fresh engine with the same seed
    engine2 = PolicyEngine(quest_trigger_prob=0.5, rng_seed=42)
    
    # Evaluate character 1 again with fresh engine - should get same sequence
    results_char1_second = []
    for _ in range(5):
        decision = engine2.evaluate_quest_trigger(
            character_id="char-1",
            turns_since_last_quest=10,
            has_active_quest=False
        )
        results_char1_second.append(decision.roll_passed)
    
    # Character 1's sequences should be identical (deterministic per character)
    assert results_char1_first == results_char1_second
    # Character 1 and 2 should have different sequences (independent)
    assert results_char1_first != results_char2


def test_profile_override_high_frequency():
    """Test profile override with high frequency settings."""
    engine = PolicyEngine(
        quest_trigger_prob=0.9,  # High probability
        quest_cooldown_turns=1,  # Short cooldown
        poi_trigger_prob=0.8,
        poi_cooldown_turns=1,
        rng_seed=12345
    )
    
    # With high probability and short cooldown, should trigger frequently
    quest_passes = 0
    poi_passes = 0
    
    for i in range(10):
        quest_decision = engine.evaluate_quest_trigger(
            character_id="test-char",
            turns_since_last_quest=i + 1,
            has_active_quest=False
        )
        poi_decision = engine.evaluate_poi_trigger(
            character_id="test-char",
            turns_since_last_poi=i + 1
        )
        
        if quest_decision.roll_passed:
            quest_passes += 1
        if poi_decision.roll_passed:
            poi_passes += 1
    
    # With a fixed seed=12345, the outcome is deterministic
    # The RNG sequence for this character produces all passes
    assert quest_passes == 10, f"Expected 10 quest passes with seed=12345, got {quest_passes}"
    assert poi_passes == 10, f"Expected 10 POI passes with seed=12345, got {poi_passes}"


def test_profile_override_low_frequency():
    """Test profile override with low frequency settings."""
    engine = PolicyEngine(
        quest_trigger_prob=0.1,  # Low probability
        quest_cooldown_turns=10,  # Long cooldown
        poi_trigger_prob=0.1,
        poi_cooldown_turns=10,
        rng_seed=12345
    )
    
    # With low probability, should rarely trigger
    quest_passes = 0
    poi_passes = 0
    
    for i in range(10):
        quest_decision = engine.evaluate_quest_trigger(
            character_id="test-char",
            turns_since_last_quest=i + 10,  # Past cooldown
            has_active_quest=False
        )
        poi_decision = engine.evaluate_poi_trigger(
            character_id="test-char",
            turns_since_last_poi=i + 10  # Past cooldown
        )
        
        if quest_decision.roll_passed:
            quest_passes += 1
        if poi_decision.roll_passed:
            poi_passes += 1
    
    # With a fixed seed=12345, the outcome is deterministic
    # The RNG sequence for this character produces all failures at 0.1 probability
    assert quest_passes == 0, f"Expected 0 quest passes with seed=12345, got {quest_passes}"
    assert poi_passes == 0, f"Expected 0 POI passes with seed=12345, got {poi_passes}"


def test_deterministic_seed_reproducibility():
    """Test that the same seed produces identical sequences across engine instances."""
    seed = 999
    
    # Create two separate engines with the same seed
    engine1 = PolicyEngine(quest_trigger_prob=0.5, rng_seed=seed)
    engine2 = PolicyEngine(quest_trigger_prob=0.5, rng_seed=seed)
    
    # Run identical evaluations on both
    results1 = []
    results2 = []
    
    for i in range(20):
        decision1 = engine1.evaluate_quest_trigger(
            character_id="test-char",
            turns_since_last_quest=10,
            has_active_quest=False
        )
        decision2 = engine2.evaluate_quest_trigger(
            character_id="test-char",
            turns_since_last_quest=10,
            has_active_quest=False
        )
        results1.append(decision1.roll_passed)
        results2.append(decision2.roll_passed)
    
    # Results should be identical
    assert results1 == results2
    # Verify we got a mix (not all True or all False)
    assert True in results1
    assert False in results1


def test_policy_engine_update_config():
    """Test PolicyEngine config update at runtime."""
    engine = PolicyEngine(
        quest_trigger_prob=0.3,
        quest_cooldown_turns=5,
        poi_trigger_prob=0.2,
        poi_cooldown_turns=3
    )
    
    # Update quest probability
    engine.update_config(quest_trigger_prob=0.7)
    assert engine.quest_trigger_prob == 0.7
    assert engine.quest_cooldown_turns == 5  # Unchanged
    
    # Update multiple params
    engine.update_config(
        quest_cooldown_turns=10,
        poi_trigger_prob=0.5
    )
    assert engine.quest_trigger_prob == 0.7  # Still 0.7
    assert engine.quest_cooldown_turns == 10  # Updated
    assert engine.poi_trigger_prob == 0.5  # Updated


def test_policy_engine_update_config_validation():
    """Test PolicyEngine config update validation."""
    engine = PolicyEngine()
    
    # Invalid probability should raise ValueError
    with pytest.raises(ValueError, match="quest_trigger_prob must be between 0.0 and 1.0"):
        engine.update_config(quest_trigger_prob=1.5)
    
    # Config should remain unchanged after failed update
    assert engine.quest_trigger_prob == 0.3  # Default value
    
    # Invalid cooldown should raise ValueError
    with pytest.raises(ValueError, match="quest_cooldown_turns must be >= 0"):
        engine.update_config(quest_cooldown_turns=-5)
