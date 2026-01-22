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
"""PolicyEngine for deterministic quest and POI trigger evaluation.

This module provides a deterministic policy engine that evaluates quest and POI
triggers using configurable parameters and reproducible randomness. It makes
decisions before the LLM prompt using deterministic inputs and probabilistic
rolls defined by guardrail configs.

Key features:
- Quest trigger evaluation with configurable probability and cooldown
- POI trigger evaluation with configurable probability and cooldown
- Optional seeded RNG per character for deterministic debugging
- Secure randomness by default
- Structured debug metadata for logging
- Extension hooks for future subsystems
"""

import random
import hashlib
from typing import Optional, Dict, Any

from app.models import (
    QuestTriggerDecision,
    POITriggerDecision,
    MemorySparkDecision,
    QuestPOIReferenceDecision,
    PolicyHints,
    PolicyState
)
from app.logging import StructuredLogger, get_turn_id
from app.metrics import get_metrics_collector

logger = StructuredLogger(__name__)

# Constants for RNG seeding
# Using 8 hex characters from SHA-256 provides ~4 billion possible seeds (2^32).
# This is sufficient for most use cases while keeping seed values manageable.
# For larger character spaces requiring higher collision resistance, increase this value.
_SEED_HASH_DIGEST_LENGTH = 8


class PolicyEngine:
    """Deterministic policy engine for quest and POI trigger evaluation.
    
    The PolicyEngine enforces probabilistic rolls once per evaluation and
    provides structured decisions for quest and POI triggers. It supports
    optional deterministic seeding per character for debugging while
    defaulting to secure randomness.
    
    This engine is designed to be extended with future subsystems without
    referencing the LLM stack.
    
    Note on Memory Management:
        The internal _character_rngs dictionary caches RNG instances per character_id
        to maintain deterministic sequences. In long-running services with many unique
        characters, this cache grows unbounded. For production deployments with high
        character turnover, consider:
        - Using stateless RNG (set rng_seed=None) to avoid caching
        - Periodically restarting the service to clear the cache
        - Implementing cache eviction if character count is a concern
    """

    def __init__(
        self,
        quest_trigger_prob: float = 0.3,
        quest_cooldown_turns: int = 5,
        poi_trigger_prob: float = 0.2,
        poi_cooldown_turns: int = 3,
        memory_spark_probability: float = 0.2,
        quest_poi_reference_probability: float = 0.1,
        rng_seed: Optional[int] = None
    ):
        """Initialize the PolicyEngine.
        
        Args:
            quest_trigger_prob: Probability of quest trigger (0.0-1.0)
            quest_cooldown_turns: Number of turns between quest triggers
            poi_trigger_prob: Probability of POI trigger (0.0-1.0)
            poi_cooldown_turns: Number of turns between POI triggers
            memory_spark_probability: Probability of memory spark trigger (0.0-1.0)
            quest_poi_reference_probability: Probability that a quest references a POI (0.0-1.0)
            rng_seed: Optional global RNG seed for deterministic behavior
            
        Raises:
            ValueError: If probabilities are outside [0, 1] range
        """
        # Validate probabilities to fail fast (consistent with config validation)
        if not (0.0 <= quest_trigger_prob <= 1.0):
            raise ValueError(
                f"quest_trigger_prob must be between 0.0 and 1.0, got: {quest_trigger_prob}"
            )
        if not (0.0 <= poi_trigger_prob <= 1.0):
            raise ValueError(
                f"poi_trigger_prob must be between 0.0 and 1.0, got: {poi_trigger_prob}"
            )
        if not (0.0 <= memory_spark_probability <= 1.0):
            raise ValueError(
                f"memory_spark_probability must be between 0.0 and 1.0, got: {memory_spark_probability}"
            )
        if not (0.0 <= quest_poi_reference_probability <= 1.0):
            raise ValueError(
                f"quest_poi_reference_probability must be between 0.0 and 1.0, got: {quest_poi_reference_probability}"
            )
        
        self.quest_trigger_prob = quest_trigger_prob
        self.poi_trigger_prob = poi_trigger_prob
        self.memory_spark_probability = memory_spark_probability
        self.quest_poi_reference_probability = quest_poi_reference_probability
        
        # Cooldown turns (allow zero or negative - they skip waiting periods)
        self.quest_cooldown_turns = quest_cooldown_turns
        self.poi_cooldown_turns = poi_cooldown_turns
        
        # RNG seed (optional)
        self.rng_seed = rng_seed
        
        # Character-specific RNG instances (for deterministic debugging)
        self._character_rngs: Dict[str, random.Random] = {}
        
        # Import lock for thread-safe config updates
        import threading
        self._config_lock = threading.Lock()
        
        logger.info(
            f"Initialized PolicyEngine with quest_prob={self.quest_trigger_prob}, "
            f"quest_cooldown={self.quest_cooldown_turns}, "
            f"poi_prob={self.poi_trigger_prob}, "
            f"poi_cooldown={self.poi_cooldown_turns}, "
            f"memory_spark_prob={self.memory_spark_probability}, "
            f"quest_poi_ref_prob={self.quest_poi_reference_probability}, "
            f"rng_seed={'<set>' if rng_seed is not None else '<none>'}"
        )
    
    def update_config(
        self,
        quest_trigger_prob: Optional[float] = None,
        quest_cooldown_turns: Optional[int] = None,
        poi_trigger_prob: Optional[float] = None,
        poi_cooldown_turns: Optional[int] = None,
        memory_spark_probability: Optional[float] = None,
        quest_poi_reference_probability: Optional[float] = None
    ) -> None:
        """Update policy configuration at runtime.
        
        This method allows hot-reloading policy parameters without restart.
        All parameters are optional - only provided values are updated.
        Validation is performed before applying changes.
        
        Args:
            quest_trigger_prob: Optional new quest trigger probability
            quest_cooldown_turns: Optional new quest cooldown turns
            poi_trigger_prob: Optional new POI trigger probability
            poi_cooldown_turns: Optional new POI cooldown turns
            memory_spark_probability: Optional new memory spark trigger probability
            quest_poi_reference_probability: Optional new quest POI reference probability
            
        Raises:
            ValueError: If any provided parameter fails validation
        """
        with self._config_lock:
            # Validate probabilities if provided
            if quest_trigger_prob is not None and not (0.0 <= quest_trigger_prob <= 1.0):
                raise ValueError(
                    f"quest_trigger_prob must be between 0.0 and 1.0, got: {quest_trigger_prob}"
                )
            if poi_trigger_prob is not None and not (0.0 <= poi_trigger_prob <= 1.0):
                raise ValueError(
                    f"poi_trigger_prob must be between 0.0 and 1.0, got: {poi_trigger_prob}"
                )
            if memory_spark_probability is not None and not (0.0 <= memory_spark_probability <= 1.0):
                raise ValueError(
                    f"memory_spark_probability must be between 0.0 and 1.0, got: {memory_spark_probability}"
                )
            if quest_poi_reference_probability is not None and not (0.0 <= quest_poi_reference_probability <= 1.0):
                raise ValueError(
                    f"quest_poi_reference_probability must be between 0.0 and 1.0, got: {quest_poi_reference_probability}"
                )
            
            # Validate cooldowns if provided (must be non-negative)
            if quest_cooldown_turns is not None and quest_cooldown_turns < 0:
                raise ValueError(
                    f"quest_cooldown_turns must be >= 0, got: {quest_cooldown_turns}"
                )
            if poi_cooldown_turns is not None and poi_cooldown_turns < 0:
                raise ValueError(
                    f"poi_cooldown_turns must be >= 0, got: {poi_cooldown_turns}"
                )
            
            # Build change summary for logging
            changes = []
            if quest_trigger_prob is not None and quest_trigger_prob != self.quest_trigger_prob:
                changes.append(f"quest_prob: {self.quest_trigger_prob} -> {quest_trigger_prob}")
                self.quest_trigger_prob = quest_trigger_prob
            if quest_cooldown_turns is not None and quest_cooldown_turns != self.quest_cooldown_turns:
                changes.append(f"quest_cooldown: {self.quest_cooldown_turns} -> {quest_cooldown_turns}")
                self.quest_cooldown_turns = quest_cooldown_turns
            if poi_trigger_prob is not None and poi_trigger_prob != self.poi_trigger_prob:
                changes.append(f"poi_prob: {self.poi_trigger_prob} -> {poi_trigger_prob}")
                self.poi_trigger_prob = poi_trigger_prob
            if poi_cooldown_turns is not None and poi_cooldown_turns != self.poi_cooldown_turns:
                changes.append(f"poi_cooldown: {self.poi_cooldown_turns} -> {poi_cooldown_turns}")
                self.poi_cooldown_turns = poi_cooldown_turns
            if memory_spark_probability is not None and memory_spark_probability != self.memory_spark_probability:
                changes.append(f"memory_spark_prob: {self.memory_spark_probability} -> {memory_spark_probability}")
                self.memory_spark_probability = memory_spark_probability
            if quest_poi_reference_probability is not None and quest_poi_reference_probability != self.quest_poi_reference_probability:
                changes.append(f"quest_poi_ref_prob: {self.quest_poi_reference_probability} -> {quest_poi_reference_probability}")
                self.quest_poi_reference_probability = quest_poi_reference_probability
            
            if changes:
                logger.info(
                    "PolicyEngine config updated",
                    changes=", ".join(changes)
                )
            else:
                logger.debug("PolicyEngine config update called with no changes")

    def _get_rng(self, character_id: Optional[str] = None, seed_override: Optional[int] = None) -> random.Random:
        """Get RNG instance for the given character or global RNG.
        
        Args:
            character_id: Optional character ID for character-specific seeding
            seed_override: Optional seed override for this specific call
            
        Returns:
            Random instance (character-specific, global seeded, or secure)
        """
        # If seed override is provided, create a temporary RNG
        if seed_override is not None:
            rng = random.Random()
            rng.seed(seed_override)
            return rng
        
        # If character_id is provided and we have a seed, use character-specific RNG
        if character_id is not None and self.rng_seed is not None:
            if character_id not in self._character_rngs:
                # Create character-specific RNG with deterministic combined seed
                # Use SHA-256 for secure deterministic hashing across Python restarts
                seed_str = f"{self.rng_seed}:{character_id}"
                hash_obj = hashlib.sha256(seed_str.encode('utf-8'))
                char_seed = int(hash_obj.hexdigest()[:_SEED_HASH_DIGEST_LENGTH], 16)
                self._character_rngs[character_id] = random.Random(char_seed)
            return self._character_rngs[character_id]
        
        # If global seed is set, use global RNG
        if self.rng_seed is not None:
            if 'global' not in self._character_rngs:
                self._character_rngs['global'] = random.Random(self.rng_seed)
            return self._character_rngs['global']
        
        # Default: use secure randomness (not reproducible)
        return random.SystemRandom()

    def _roll(self, probability: float, character_id: Optional[str] = None, seed_override: Optional[int] = None) -> bool:
        """Perform a probabilistic roll.
        
        Args:
            probability: Success probability (0.0-1.0)
            character_id: Optional character ID for character-specific RNG
            seed_override: Optional seed override for this specific call
            
        Returns:
            True if roll succeeds, False otherwise
        """
        rng = self._get_rng(character_id, seed_override)
        return rng.random() < probability

    def evaluate_quest_trigger(
        self,
        character_id: str,
        turns_since_last_quest: int,
        has_active_quest: bool = False,
        seed_override: Optional[int] = None
    ) -> QuestTriggerDecision:
        """Evaluate whether to trigger a quest for the character.
        
        Uses turn-based cooldown only. A quest can trigger if:
        1. Character doesn't have an active quest
        2. turns_since_last_quest >= quest_cooldown_turns
        3. Probabilistic roll passes
        
        Args:
            character_id: Character UUID for tracking
            turns_since_last_quest: Number of turns since last quest trigger
            has_active_quest: Whether character already has an active quest
            seed_override: Optional seed for deterministic debugging
            
        Returns:
            QuestTriggerDecision with eligibility, probability, and roll result
        """
        # Read config values under lock for thread-safety
        with self._config_lock:
            quest_trigger_prob = self.quest_trigger_prob
            quest_cooldown_turns = self.quest_cooldown_turns
        
        # Check eligibility
        eligible = True
        reasons = []
        
        if has_active_quest:
            eligible = False
            reasons.append("already_has_active_quest")
        
        # Turn-based cooldown check
        if turns_since_last_quest < quest_cooldown_turns:
            eligible = False
            reasons.append(
                f"turn_cooldown_not_met (turns={turns_since_last_quest}, required={quest_cooldown_turns})"
            )
        
        # Perform roll if eligible
        roll_passed = False
        if eligible:
            roll_passed = self._roll(quest_trigger_prob, character_id, seed_override)
        
        decision = QuestTriggerDecision(
            eligible=eligible,
            probability=quest_trigger_prob,
            roll_passed=roll_passed
        )
        
        # Record metrics
        collector = get_metrics_collector()
        if collector:
            if roll_passed:
                collector.record_policy_trigger("quest", "triggered")
            elif not eligible:
                collector.record_policy_trigger("quest", "ineligible")
            else:
                collector.record_policy_trigger("quest", "skipped")
        
        logger.info(
            f"Quest trigger evaluation - "
            f"character_id={character_id}, "
            f"eligible={eligible}, "
            f"roll_passed={roll_passed}, "
            f"probability={quest_trigger_prob}, "
            f"has_active_quest={has_active_quest}, "
            f"turns_since_last_quest={turns_since_last_quest}, "
            f"cooldown_required={quest_cooldown_turns}, "
            f"ineligible_reasons={reasons if not eligible else 'none'}"
        )
        
        return decision

    def evaluate_poi_trigger(
        self,
        character_id: str,
        turns_since_last_poi: int,
        has_active_quest: bool = False,
        seed_override: Optional[int] = None
    ) -> POITriggerDecision:
        """Evaluate whether to trigger a POI for the character.
        
        Uses turn-based cooldown. A POI can trigger if:
        1. turns_since_last_poi >= poi_cooldown_turns
        2. Probabilistic roll passes
        
        Args:
            character_id: Character UUID for tracking
            turns_since_last_poi: Number of turns since last POI trigger
            has_active_quest: Whether character has an active quest (informational)
            seed_override: Optional seed for deterministic debugging
            
        Returns:
            POITriggerDecision with eligibility, probability, and roll result
        """
        # Read config values under lock for thread-safety
        with self._config_lock:
            poi_trigger_prob = self.poi_trigger_prob
            poi_cooldown_turns = self.poi_cooldown_turns
        
        # Check eligibility (only turn-based cooldown)
        eligible = True
        reasons = []
        
        if turns_since_last_poi < poi_cooldown_turns:
            eligible = False
            reasons.append(
                f"turn_cooldown_not_met (turns={turns_since_last_poi}, required={poi_cooldown_turns})"
            )
        
        # Perform roll if eligible
        roll_passed = False
        if eligible:
            roll_passed = self._roll(poi_trigger_prob, character_id, seed_override)
        
        decision = POITriggerDecision(
            eligible=eligible,
            probability=poi_trigger_prob,
            roll_passed=roll_passed
        )
        
        # Record metrics
        collector = get_metrics_collector()
        if collector:
            if roll_passed:
                collector.record_policy_trigger("poi", "triggered")
            elif not eligible:
                collector.record_policy_trigger("poi", "ineligible")
            else:
                collector.record_policy_trigger("poi", "skipped")
        
        logger.info(
            f"POI trigger evaluation - "
            f"character_id={character_id}, "
            f"eligible={eligible}, "
            f"roll_passed={roll_passed}, "
            f"probability={poi_trigger_prob}, "
            f"turns_since_last_poi={turns_since_last_poi}, "
            f"cooldown_required={poi_cooldown_turns}, "
            f"ineligible_reasons={reasons if not eligible else 'none'}"
        )
        
        return decision

    def evaluate_memory_spark_trigger(
        self,
        character_id: str,
        seed_override: Optional[int] = None
    ) -> MemorySparkDecision:
        """Evaluate whether to trigger memory spark fetching for the character.
        
        Memory sparks are always eligible (no cooldown or state requirements).
        The probabilistic roll determines whether random POIs should be fetched
        to provide context to the LLM.
        
        Args:
            character_id: Character UUID for tracking
            seed_override: Optional seed for deterministic debugging
            
        Returns:
            MemorySparkDecision with eligibility, probability, and roll result
        """
        
        # Read config values under lock for thread-safety
        with self._config_lock:
            memory_spark_probability = self.memory_spark_probability
        
        # Memory sparks are always eligible (no state requirements)
        eligible = True
        
        # Perform probabilistic roll
        roll_passed = self._roll(memory_spark_probability, character_id, seed_override)
        
        decision = MemorySparkDecision(
            eligible=eligible,
            probability=memory_spark_probability,
            roll_passed=roll_passed
        )
        
        # Record metrics
        collector = get_metrics_collector()
        if collector:
            if roll_passed:
                collector.record_policy_trigger("memory_spark", "triggered")
            else:
                collector.record_policy_trigger("memory_spark", "skipped")
        
        logger.debug(
            f"Memory spark evaluation: character_id={character_id}, "
            f"eligible={eligible}, roll_passed={roll_passed}",
            turn_id=get_turn_id()
        )
        
        return decision

    def evaluate_quest_poi_reference_trigger(
        self,
        character_id: str,
        available_pois: list,
        seed_override: Optional[int] = None
    ) -> QuestPOIReferenceDecision:
        """Evaluate whether a triggered quest should reference a prior POI.
        
        This is called when a quest is about to be triggered. The probabilistic
        roll determines whether the quest should reference a previously
        discovered POI for additional context.
        
        Args:
            character_id: Character UUID for tracking
            available_pois: List of available POIs to select from
            seed_override: Optional seed for deterministic debugging
            
        Returns:
            QuestPOIReferenceDecision with probability, roll result, and selected POI
        """
        
        # Read config values under lock for thread-safety
        with self._config_lock:
            quest_poi_reference_probability = self.quest_poi_reference_probability
        
        # Get RNG instance once to ensure determinism with seed_override
        rng = self._get_rng(character_id, seed_override)
        
        # Perform probabilistic roll
        roll_passed = rng.random() < quest_poi_reference_probability
        
        # Select a POI if roll passed and POIs are available
        selected_poi = None
        if roll_passed and available_pois:
            # Select a random POI from available ones with equal probability
            # Note: While POIs are sorted by timestamp descending in memory_sparks,
            # random.choice() gives equal probability to all POIs
            selected_poi = rng.choice(available_pois)
            logger.info(
                f"Quest POI reference selected: {selected_poi.get('name', 'Unknown')}",
                poi_id=selected_poi.get('id'),
                turn_id=get_turn_id()
            )
        elif roll_passed and not available_pois:
            logger.debug(
                "Quest POI reference roll passed but no POIs available",
                turn_id=get_turn_id()
            )
        
        decision = QuestPOIReferenceDecision(
            probability=quest_poi_reference_probability,
            roll_passed=roll_passed,
            selected_poi=selected_poi
        )
        
        # Record metrics
        collector = get_metrics_collector()
        if collector:
            if roll_passed and selected_poi:
                collector.record_policy_trigger("quest_poi_reference", "triggered")
            elif roll_passed:
                collector.record_policy_trigger("quest_poi_reference", "no_pois")
            else:
                collector.record_policy_trigger("quest_poi_reference", "skipped")
        
        logger.debug(
            f"Quest POI reference evaluation: character_id={character_id}, "
            f"roll_passed={roll_passed}, selected={selected_poi is not None}",
            turn_id=get_turn_id()
        )
        
        return decision

    def evaluate_triggers(
        self,
        character_id: str,
        policy_state: PolicyState,
        seed_override: Optional[int] = None
    ) -> PolicyHints:
        """Evaluate both quest and POI triggers together.
        
        This is a convenience method that evaluates both quest and POI triggers
        and returns them bundled in a PolicyHints object. It's equivalent to
        calling evaluate_quest_trigger and evaluate_poi_trigger separately.
        
        Args:
            character_id: Unique identifier for character (for per-character RNG)
            policy_state: PolicyState containing turn counters, combat flags, timestamps
            seed_override: Optional seed to override per-character determinism
            
        Returns:
            PolicyHints containing both quest and POI trigger decisions
        """
        
        quest_decision = self.evaluate_quest_trigger(
            character_id=character_id,
            turns_since_last_quest=policy_state.turns_since_last_quest,
            has_active_quest=policy_state.has_active_quest,
            seed_override=seed_override
        )
        
        poi_decision = self.evaluate_poi_trigger(
            character_id=character_id,
            turns_since_last_poi=policy_state.turns_since_last_poi,
            seed_override=seed_override
        )
        
        return PolicyHints(
            quest_trigger_decision=quest_decision,
            poi_trigger_decision=poi_decision
        )

    def get_debug_metadata(self) -> Dict[str, Any]:
        """Get debug metadata about the policy engine state.
        
        Returns:
            Dictionary with policy configuration and state information
        """
        return {
            "quest_trigger_prob": self.quest_trigger_prob,
            "quest_cooldown_turns": self.quest_cooldown_turns,
            "poi_trigger_prob": self.poi_trigger_prob,
            "poi_cooldown_turns": self.poi_cooldown_turns,
            "memory_spark_probability": self.memory_spark_probability,
            "quest_poi_reference_probability": self.quest_poi_reference_probability,
            "rng_seed_set": self.rng_seed is not None,
            "character_rngs_count": len(self._character_rngs)
        }
