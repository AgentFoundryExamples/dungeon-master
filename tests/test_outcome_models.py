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
"""Unit tests for DungeonMaster outcome models.

Tests the structured LLM output schema including:
- DungeonMasterOutcome
- IntentsBlock
- QuestIntent, CombatIntent, POIIntent, MetaIntent
- EnemyDescriptor
- Schema generation helpers
"""

import pytest
import json
from pydantic import ValidationError

from app.models import (
    OUTCOME_VERSION,
    EnemyDescriptor,
    QuestIntent,
    CombatIntent,
    POIIntent,
    MetaIntent,
    IntentsBlock,
    DungeonMasterOutcome,
    get_outcome_json_schema,
    get_outcome_schema_example,
)


class TestOutcomeVersion:
    """Tests for outcome version constant."""
    
    def test_outcome_version_exists(self):
        """Test that OUTCOME_VERSION constant is defined."""
        assert OUTCOME_VERSION is not None
        assert isinstance(OUTCOME_VERSION, int)
        assert OUTCOME_VERSION == 1


class TestEnemyDescriptor:
    """Tests for EnemyDescriptor model."""
    
    def test_enemy_descriptor_all_fields(self):
        """Test EnemyDescriptor with all fields populated."""
        enemy = EnemyDescriptor(
            name="Goblin Scout",
            description="A small, cunning creature",
            threat="medium"
        )
        assert enemy.name == "Goblin Scout"
        assert enemy.description == "A small, cunning creature"
        assert enemy.threat == "medium"
    
    def test_enemy_descriptor_minimal(self):
        """Test EnemyDescriptor with no fields (all optional)."""
        enemy = EnemyDescriptor()
        assert enemy.name is None
        assert enemy.description is None
        assert enemy.threat is None
    
    def test_enemy_descriptor_partial(self):
        """Test EnemyDescriptor with some fields."""
        enemy = EnemyDescriptor(name="Shadow", threat="high")
        assert enemy.name == "Shadow"
        assert enemy.description is None
        assert enemy.threat == "high"
    
    def test_enemy_descriptor_null_values(self):
        """Test that None values are handled correctly."""
        enemy = EnemyDescriptor(name=None, description=None, threat=None)
        assert enemy.name is None
        assert enemy.description is None
        assert enemy.threat is None


class TestQuestIntent:
    """Tests for QuestIntent model."""
    
    def test_quest_intent_defaults(self):
        """Test QuestIntent with default action."""
        quest = QuestIntent()
        assert quest.action == "none"
        assert quest.quest_title is None
        assert quest.quest_summary is None
        assert quest.quest_details is None
    
    def test_quest_intent_offer(self):
        """Test QuestIntent with offer action."""
        quest = QuestIntent(
            action="offer",
            quest_title="Rescue Mission",
            quest_summary="Save the village",
            quest_details={"difficulty": "hard"}
        )
        assert quest.action == "offer"
        assert quest.quest_title == "Rescue Mission"
        assert quest.quest_summary == "Save the village"
        assert quest.quest_details == {"difficulty": "hard"}
    
    def test_quest_intent_complete(self):
        """Test QuestIntent with complete action."""
        quest = QuestIntent(action="complete", quest_title="Old Quest")
        assert quest.action == "complete"
        assert quest.quest_title == "Old Quest"
    
    def test_quest_intent_abandon(self):
        """Test QuestIntent with abandon action."""
        quest = QuestIntent(action="abandon")
        assert quest.action == "abandon"
    
    def test_quest_intent_invalid_action(self):
        """Test that invalid action literals are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            QuestIntent(action="invalid")
        assert "action" in str(exc_info.value)


class TestCombatIntent:
    """Tests for CombatIntent model."""
    
    def test_combat_intent_defaults(self):
        """Test CombatIntent with default action."""
        combat = CombatIntent()
        assert combat.action == "none"
        assert combat.enemies is None
        assert combat.combat_notes is None
    
    def test_combat_intent_start_with_enemies(self):
        """Test CombatIntent starting combat with enemies."""
        combat = CombatIntent(
            action="start",
            enemies=[
                EnemyDescriptor(name="Goblin", threat="low"),
                EnemyDescriptor(name="Orc", threat="high")
            ],
            combat_notes="Ambush from the trees"
        )
        assert combat.action == "start"
        assert len(combat.enemies) == 2
        assert combat.enemies[0].name == "Goblin"
        assert combat.enemies[1].name == "Orc"
        assert combat.combat_notes == "Ambush from the trees"
    
    def test_combat_intent_continue(self):
        """Test CombatIntent continuing combat."""
        combat = CombatIntent(action="continue")
        assert combat.action == "continue"
    
    def test_combat_intent_end(self):
        """Test CombatIntent ending combat."""
        combat = CombatIntent(action="end", combat_notes="Victory!")
        assert combat.action == "end"
        assert combat.combat_notes == "Victory!"
    
    def test_combat_intent_empty_enemies_list(self):
        """Test CombatIntent with empty enemies list."""
        combat = CombatIntent(action="start", enemies=[])
        assert combat.enemies == []
    
    def test_combat_intent_invalid_action(self):
        """Test that invalid action literals are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            CombatIntent(action="attack")
        assert "action" in str(exc_info.value)


class TestPOIIntent:
    """Tests for POIIntent model."""
    
    def test_poi_intent_defaults(self):
        """Test POIIntent with default action."""
        poi = POIIntent()
        assert poi.action == "none"
        assert poi.name is None
        assert poi.description is None
        assert poi.reference_tags is None
    
    def test_poi_intent_create(self):
        """Test POIIntent creating a location."""
        poi = POIIntent(
            action="create",
            name="Dark Forest",
            description="A mysterious woodland",
            reference_tags=["forest", "quest_area"]
        )
        assert poi.action == "create"
        assert poi.name == "Dark Forest"
        assert poi.description == "A mysterious woodland"
        assert poi.reference_tags == ["forest", "quest_area"]
    
    def test_poi_intent_reference(self):
        """Test POIIntent referencing existing location."""
        poi = POIIntent(
            action="reference",
            name="The Tavern",
            reference_tags=["town", "safe_zone"]
        )
        assert poi.action == "reference"
        assert poi.name == "The Tavern"
    
    def test_poi_intent_invalid_action(self):
        """Test that invalid action literals are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            POIIntent(action="destroy")
        assert "action" in str(exc_info.value)


class TestMetaIntent:
    """Tests for MetaIntent model."""
    
    def test_meta_intent_all_none(self):
        """Test MetaIntent with all fields None."""
        meta = MetaIntent()
        assert meta.player_mood is None
        assert meta.pacing_hint is None
        assert meta.user_is_wandering is None
        assert meta.user_asked_for_guidance is None
    
    def test_meta_intent_full(self):
        """Test MetaIntent with all fields populated."""
        meta = MetaIntent(
            player_mood="excited",
            pacing_hint="fast",
            user_is_wandering=False,
            user_asked_for_guidance=False
        )
        assert meta.player_mood == "excited"
        assert meta.pacing_hint == "fast"
        assert meta.user_is_wandering is False
        assert meta.user_asked_for_guidance is False
    
    def test_meta_intent_pacing_slow(self):
        """Test MetaIntent with slow pacing."""
        meta = MetaIntent(pacing_hint="slow")
        assert meta.pacing_hint == "slow"
    
    def test_meta_intent_pacing_normal(self):
        """Test MetaIntent with normal pacing."""
        meta = MetaIntent(pacing_hint="normal")
        assert meta.pacing_hint == "normal"
    
    def test_meta_intent_wandering_flag(self):
        """Test MetaIntent with wandering flag."""
        meta = MetaIntent(user_is_wandering=True, player_mood="confused")
        assert meta.user_is_wandering is True
        assert meta.player_mood == "confused"
    
    def test_meta_intent_guidance_flag(self):
        """Test MetaIntent with guidance flag."""
        meta = MetaIntent(user_asked_for_guidance=True)
        assert meta.user_asked_for_guidance is True
    
    def test_meta_intent_invalid_pacing(self):
        """Test that invalid pacing literals are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MetaIntent(pacing_hint="very_fast")
        assert "pacing_hint" in str(exc_info.value)


class TestIntentsBlock:
    """Tests for IntentsBlock model."""
    
    def test_intents_block_empty(self):
        """Test IntentsBlock with all None."""
        intents = IntentsBlock()
        assert intents.quest_intent is None
        assert intents.combat_intent is None
        assert intents.poi_intent is None
        assert intents.meta is None
    
    def test_intents_block_full(self):
        """Test IntentsBlock with all intents populated."""
        intents = IntentsBlock(
            quest_intent=QuestIntent(action="offer", quest_title="Test Quest"),
            combat_intent=CombatIntent(action="start"),
            poi_intent=POIIntent(action="create", name="Test Location"),
            meta=MetaIntent(pacing_hint="normal")
        )
        assert intents.quest_intent.action == "offer"
        assert intents.combat_intent.action == "start"
        assert intents.poi_intent.action == "create"
        assert intents.meta.pacing_hint == "normal"
    
    def test_intents_block_partial(self):
        """Test IntentsBlock with some intents."""
        intents = IntentsBlock(
            quest_intent=QuestIntent(action="complete"),
            meta=MetaIntent(player_mood="satisfied")
        )
        assert intents.quest_intent is not None
        assert intents.combat_intent is None
        assert intents.poi_intent is None
        assert intents.meta is not None


class TestDungeonMasterOutcome:
    """Tests for DungeonMasterOutcome model."""
    
    def test_outcome_minimal(self):
        """Test DungeonMasterOutcome with minimal intents."""
        outcome = DungeonMasterOutcome(
            narrative="You enter the room.",
            intents=IntentsBlock()
        )
        assert outcome.narrative == "You enter the room."
        assert outcome.intents is not None
    
    def test_outcome_full(self):
        """Test DungeonMasterOutcome with full intents."""
        outcome = DungeonMasterOutcome(
            narrative="A goblin jumps out!",
            intents=IntentsBlock(
                quest_intent=QuestIntent(action="none"),
                combat_intent=CombatIntent(
                    action="start",
                    enemies=[EnemyDescriptor(name="Goblin", threat="low")]
                ),
                poi_intent=POIIntent(action="none"),
                meta=MetaIntent(pacing_hint="fast")
            )
        )
        assert outcome.narrative == "A goblin jumps out!"
        assert outcome.intents.combat_intent.action == "start"
        assert len(outcome.intents.combat_intent.enemies) == 1
    
    def test_outcome_missing_narrative(self):
        """Test that narrative is required."""
        with pytest.raises(ValidationError) as exc_info:
            DungeonMasterOutcome(intents=IntentsBlock())
        assert "narrative" in str(exc_info.value)
    
    def test_outcome_empty_narrative(self):
        """Test that empty narrative is rejected (min_length=1)."""
        with pytest.raises(ValidationError) as exc_info:
            DungeonMasterOutcome(narrative="", intents=IntentsBlock())
        assert "narrative" in str(exc_info.value)
    
    def test_outcome_missing_intents(self):
        """Test that intents is required."""
        with pytest.raises(ValidationError) as exc_info:
            DungeonMasterOutcome(narrative="Test")
        assert "intents" in str(exc_info.value)
    
    def test_outcome_from_json(self):
        """Test parsing DungeonMasterOutcome from JSON."""
        json_data = {
            "narrative": "You see a merchant.",
            "intents": {
                "quest_intent": {
                    "action": "offer",
                    "quest_title": "Delivery Quest",
                    "quest_summary": "Deliver a package"
                },
                "combat_intent": {"action": "none"},
                "poi_intent": {
                    "action": "reference",
                    "name": "Market Square"
                },
                "meta": {
                    "player_mood": "curious",
                    "pacing_hint": "normal"
                }
            }
        }
        
        outcome = DungeonMasterOutcome(**json_data)
        assert outcome.narrative == "You see a merchant."
        assert outcome.intents.quest_intent.action == "offer"
        assert outcome.intents.quest_intent.quest_title == "Delivery Quest"
        assert outcome.intents.combat_intent.action == "none"
        assert outcome.intents.poi_intent.name == "Market Square"
        assert outcome.intents.meta.player_mood == "curious"
    
    def test_outcome_to_json(self):
        """Test serializing DungeonMasterOutcome to JSON."""
        outcome = DungeonMasterOutcome(
            narrative="Test narrative",
            intents=IntentsBlock(
                quest_intent=QuestIntent(action="abandon"),
                meta=MetaIntent(pacing_hint="slow")
            )
        )
        
        json_str = outcome.model_dump_json()
        parsed = json.loads(json_str)
        
        assert parsed["narrative"] == "Test narrative"
        assert parsed["intents"]["quest_intent"]["action"] == "abandon"
        assert parsed["intents"]["meta"]["pacing_hint"] == "slow"


class TestSchemaHelpers:
    """Tests for schema generation helper functions."""
    
    def test_get_outcome_json_schema(self):
        """Test that get_outcome_json_schema returns valid JSON Schema."""
        schema = get_outcome_json_schema()
        
        assert isinstance(schema, dict)
        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "narrative" in schema["properties"]
        assert "intents" in schema["properties"]
    
    def test_get_outcome_schema_example(self):
        """Test that get_outcome_schema_example returns valid JSON."""
        example_str = get_outcome_schema_example()
        
        assert isinstance(example_str, str)
        
        # Parse to verify it's valid JSON
        example = json.loads(example_str)
        
        assert "narrative" in example
        assert "intents" in example
        assert isinstance(example["narrative"], str)
        assert isinstance(example["intents"], dict)
        
        # Verify it can be parsed as a valid DungeonMasterOutcome
        outcome = DungeonMasterOutcome(**example)
        assert outcome.narrative
        assert outcome.intents is not None
    
    def test_schema_suitable_for_openai(self):
        """Test that schema is suitable for OpenAI Responses API."""
        schema = get_outcome_json_schema()
        
        # The schema should be usable with OpenAI's text.format parameter
        # Verify it has the required structure
        assert "properties" in schema
        assert "required" in schema
        
        # Check that required fields are listed
        assert "narrative" in schema["required"]
        assert "intents" in schema["required"]
    
    def test_schema_includes_all_intent_types(self):
        """Test that schema includes all intent types."""
        schema = get_outcome_json_schema()
        
        # Navigate to intents properties
        intents_schema = schema["properties"]["intents"]
        
        # Should be a reference or have properties
        if "$ref" in intents_schema:
            # Find the referenced schema in definitions/defs
            ref = intents_schema["$ref"]
            # Schema should have definitions somewhere
            assert "$defs" in schema or "definitions" in schema
        else:
            # Direct properties
            assert "properties" in intents_schema or "allOf" in intents_schema


class TestEdgeCases:
    """Tests for edge cases and validation scenarios."""
    
    def test_quest_intent_unknown_action_rejected(self):
        """Test that unknown quest actions are rejected."""
        with pytest.raises(ValidationError):
            QuestIntent(action="unknown")
    
    def test_enemy_descriptor_empty_arrays(self):
        """Test that empty enemy arrays are handled correctly."""
        combat = CombatIntent(action="start", enemies=[])
        assert combat.enemies == []
        assert isinstance(combat.enemies, list)
    
    def test_optional_text_fields_normalize_none(self):
        """Test that optional text fields properly handle None."""
        quest = QuestIntent(
            action="offer",
            quest_title=None,
            quest_summary=None
        )
        assert quest.quest_title is None
        assert quest.quest_summary is None
        # Pydantic v2 keeps None as None
    
    def test_complex_nested_structure(self):
        """Test complex nested outcome structure."""
        outcome = DungeonMasterOutcome(
            narrative="A complex scenario unfolds...",
            intents=IntentsBlock(
                quest_intent=QuestIntent(
                    action="offer",
                    quest_title="Multi-part Quest",
                    quest_details={
                        "parts": ["part1", "part2", "part3"],
                        "rewards": {"gold": 100, "xp": 500}
                    }
                ),
                combat_intent=CombatIntent(
                    action="start",
                    enemies=[
                        EnemyDescriptor(name="Enemy1", threat="low"),
                        EnemyDescriptor(name="Enemy2", threat="medium"),
                        EnemyDescriptor(name="Boss", threat="high")
                    ],
                    combat_notes="Multi-wave encounter"
                ),
                poi_intent=POIIntent(
                    action="create",
                    name="Complex Location",
                    reference_tags=["tag1", "tag2", "tag3"]
                ),
                meta=MetaIntent(
                    player_mood="excited",
                    pacing_hint="fast",
                    user_is_wandering=False,
                    user_asked_for_guidance=False
                )
            )
        )
        
        # Verify all nested data is preserved
        assert outcome.intents.quest_intent.quest_details["parts"] == ["part1", "part2", "part3"]
        assert len(outcome.intents.combat_intent.enemies) == 3
        assert len(outcome.intents.poi_intent.reference_tags) == 3
