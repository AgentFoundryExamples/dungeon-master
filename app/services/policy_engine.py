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

from app.models import QuestTriggerDecision, POITriggerDecision
from app.logging import StructuredLogger

logger = StructuredLogger(__name__)

# Constants for RNG seeding
_SEED_HASH_DIGEST_LENGTH = 8  # Number of hex characters to use from hash for seed generation


class PolicyEngine:
    """Deterministic policy engine for quest and POI trigger evaluation.
    
    The PolicyEngine enforces probabilistic rolls once per evaluation and
    provides structured decisions for quest and POI triggers. It supports
    optional deterministic seeding per character for debugging while
    defaulting to secure randomness.
    
    This engine is designed to be extended with future subsystems without
    referencing the LLM stack.
    """

    def __init__(
        self,
        quest_trigger_prob: float = 0.3,
        quest_cooldown_turns: int = 5,
        poi_trigger_prob: float = 0.2,
        poi_cooldown_turns: int = 3,
        rng_seed: Optional[int] = None
    ):
        """Initialize the PolicyEngine.
        
        Args:
            quest_trigger_prob: Probability of quest trigger (0.0-1.0)
            quest_cooldown_turns: Number of turns between quest triggers
            poi_trigger_prob: Probability of POI trigger (0.0-1.0)
            poi_cooldown_turns: Number of turns between POI triggers
            rng_seed: Optional global RNG seed for deterministic behavior
        """
        # Clamp probabilities to valid range [0, 1]
        self.quest_trigger_prob = max(0.0, min(1.0, quest_trigger_prob))
        self.poi_trigger_prob = max(0.0, min(1.0, poi_trigger_prob))
        
        # Cooldown turns (allow zero or negative - they skip waiting periods)
        self.quest_cooldown_turns = quest_cooldown_turns
        self.poi_cooldown_turns = poi_cooldown_turns
        
        # RNG seed (optional)
        self.rng_seed = rng_seed
        
        # Character-specific RNG instances (for deterministic debugging)
        self._character_rngs: Dict[str, random.Random] = {}
        
        logger.info(
            f"Initialized PolicyEngine with quest_prob={self.quest_trigger_prob}, "
            f"quest_cooldown={self.quest_cooldown_turns}, "
            f"poi_prob={self.poi_trigger_prob}, "
            f"poi_cooldown={self.poi_cooldown_turns}, "
            f"rng_seed={'<set>' if rng_seed is not None else '<none>'}"
        )

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
        
        Args:
            character_id: Character UUID for tracking
            turns_since_last_quest: Number of turns since last quest trigger
            has_active_quest: Whether character already has an active quest
            seed_override: Optional seed for deterministic debugging
            
        Returns:
            QuestTriggerDecision with eligibility, probability, and roll result
        """
        # Check eligibility
        eligible = True
        reasons = []
        
        if has_active_quest:
            eligible = False
            reasons.append("already_has_active_quest")
        
        if turns_since_last_quest < self.quest_cooldown_turns:
            eligible = False
            reasons.append(f"cooldown_not_met (turns={turns_since_last_quest}, required={self.quest_cooldown_turns})")
        
        # Perform roll if eligible
        roll_passed = False
        if eligible:
            roll_passed = self._roll(self.quest_trigger_prob, character_id, seed_override)
        
        decision = QuestTriggerDecision(
            eligible=eligible,
            probability=self.quest_trigger_prob,
            roll_passed=roll_passed
        )
        
        logger.debug(
            f"Quest trigger evaluation: character_id={character_id}, "
            f"eligible={eligible}, roll_passed={roll_passed}, "
            f"reasons={reasons if not eligible else 'none'}"
        )
        
        return decision

    def evaluate_poi_trigger(
        self,
        character_id: str,
        turns_since_last_poi: int,
        seed_override: Optional[int] = None
    ) -> POITriggerDecision:
        """Evaluate whether to trigger a POI for the character.
        
        Args:
            character_id: Character UUID for tracking
            turns_since_last_poi: Number of turns since last POI trigger
            seed_override: Optional seed for deterministic debugging
            
        Returns:
            POITriggerDecision with eligibility, probability, and roll result
        """
        # Check eligibility
        eligible = True
        reasons = []
        
        if turns_since_last_poi < self.poi_cooldown_turns:
            eligible = False
            reasons.append(f"cooldown_not_met (turns={turns_since_last_poi}, required={self.poi_cooldown_turns})")
        
        # Perform roll if eligible
        roll_passed = False
        if eligible:
            roll_passed = self._roll(self.poi_trigger_prob, character_id, seed_override)
        
        decision = POITriggerDecision(
            eligible=eligible,
            probability=self.poi_trigger_prob,
            roll_passed=roll_passed
        )
        
        logger.debug(
            f"POI trigger evaluation: character_id={character_id}, "
            f"eligible={eligible}, roll_passed={roll_passed}, "
            f"reasons={reasons if not eligible else 'none'}"
        )
        
        return decision

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
            "rng_seed_set": self.rng_seed is not None,
            "character_rngs_count": len(self._character_rngs)
        }
