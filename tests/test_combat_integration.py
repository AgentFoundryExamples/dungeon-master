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
"""Integration tests for combat subsystem synchronization."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
import uuid

from app.models import (
    JourneyLogContext,
    PolicyState,
    IntentsBlock,
    CombatIntent,
    EnemyDescriptor,
    QuestIntent,
    POIIntent,
    MetaIntent
)
from app.services.turn_orchestrator import TurnOrchestrator
from app.services.policy_engine import PolicyEngine, QuestTriggerDecision, POITriggerDecision
from app.services.llm_client import LLMClient
from app.services.journey_log_client import JourneyLogClient
from app.services.outcome_parser import ParsedOutcome, OutcomeParser
from app.prompting.prompt_builder import PromptBuilder


@pytest.fixture
def mock_policy_engine():
    """Create a mock policy engine."""
    engine = MagicMock(spec=PolicyEngine)
    engine.evaluate_quest_trigger.return_value = QuestTriggerDecision(
        eligible=False,
        probability=0.0,
        roll_passed=False
    )
    engine.evaluate_poi_trigger.return_value = POITriggerDecision(
        eligible=False,
        probability=0.0,
        roll_passed=False
    )
    return engine


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock(spec=LLMClient)
    return client


@pytest.fixture
def mock_journey_log_client():
    """Create a mock journey-log client."""
    client = MagicMock(spec=JourneyLogClient)
    # Mock async methods
    client.persist_narrative = AsyncMock()
    client.put_combat = AsyncMock()
    client.put_quest = AsyncMock()
    client.delete_quest = AsyncMock()
    client.post_poi = AsyncMock()
    return client


@pytest.fixture
def mock_prompt_builder():
    """Create a mock prompt builder."""
    builder = MagicMock(spec=PromptBuilder)
    builder.build_prompt.return_value = (
        "System instructions",
        "User prompt"
    )
    return builder


@pytest.fixture
def orchestrator(mock_policy_engine, mock_llm_client, mock_journey_log_client, mock_prompt_builder):
    """Create a TurnOrchestrator with mocked dependencies."""
    return TurnOrchestrator(
        policy_engine=mock_policy_engine,
        llm_client=mock_llm_client,
        journey_log_client=mock_journey_log_client,
        prompt_builder=mock_prompt_builder
    )


@pytest.mark.asyncio
async def test_combat_start_creates_combat_state(orchestrator, mock_llm_client, mock_journey_log_client):
    """Test that combat start action creates proper combat_state payload."""
    # Setup context - not in combat
    context = JourneyLogContext(
        character_id="test-char-id",
        status="Healthy",
        location={"id": "origin:nexus", "display_name": "The Nexus"},
        active_quest=None,
        combat_state=None,
        recent_history=[],
        policy_state=PolicyState(
            combat_active=False,
            has_active_quest=False
        )
    )
    
    # Setup LLM response with combat start intent
    enemies = [
        EnemyDescriptor(
            name="Goblin Scout",
            description="A small, cunning creature",
            threat="low"
        ),
        EnemyDescriptor(
            name="Orc Warrior",
            description="A fierce orc wielding an axe",
            threat="high"
        )
    ]
    
    combat_intent = CombatIntent(
        action="start",
        enemies=enemies,
        combat_notes="Ambushed in the forest"
    )
    
    intents = IntentsBlock(
        quest_intent=QuestIntent(action="none"),
        combat_intent=combat_intent,
        poi_intent=POIIntent(action="none"),
        meta=MetaIntent()
    )
    
    parsed_outcome = ParsedOutcome(
        outcome=MagicMock(narrative="Combat begins!", intents=intents),
        narrative="Combat begins!",
        is_valid=True
    )
    
    mock_llm_client.generate_narrative = AsyncMock(return_value=parsed_outcome)
    
    # Execute
    narrative, returned_intents, summary = await orchestrator.orchestrate_turn(
        character_id="test-char-id",
        user_action="I attack the goblins",
        context=context,
        dry_run=False
    )
    
    # Verify put_combat was called
    mock_journey_log_client.put_combat.assert_called_once()
    call_args = mock_journey_log_client.put_combat.call_args
    
    # Verify payload structure
    combat_data = call_args.kwargs["combat_data"]
    assert combat_data is not None
    assert "combat_id" in combat_data
    assert "started_at" in combat_data
    assert "turn" in combat_data
    assert combat_data["turn"] == 1
    assert "enemies" in combat_data
    assert len(combat_data["enemies"]) == 2
    
    # Verify enemy structure
    enemy1 = combat_data["enemies"][0]
    assert "enemy_id" in enemy1
    assert enemy1["name"] == "Goblin Scout"
    assert enemy1["status"] == "Healthy"
    assert "traits" in enemy1
    assert "threat:low" in enemy1["traits"]
    assert enemy1["metadata"]["description"] == "A small, cunning creature"
    
    enemy2 = combat_data["enemies"][1]
    assert enemy2["name"] == "Orc Warrior"
    assert "threat:high" in enemy2["traits"]
    
    # Verify summary
    assert summary.combat_change.action == "started"
    assert summary.combat_change.success is True


@pytest.mark.asyncio
async def test_combat_start_skipped_when_already_in_combat(orchestrator, mock_llm_client, mock_journey_log_client):
    """Test that combat start is skipped when already in combat."""
    # Setup context - already in combat
    context = JourneyLogContext(
        character_id="test-char-id",
        status="Healthy",
        location={"id": "origin:nexus", "display_name": "The Nexus"},
        active_quest=None,
        combat_state={"combat_id": "existing-combat"},
        recent_history=[],
        policy_state=PolicyState(
            combat_active=True,  # Already in combat
            has_active_quest=False
        )
    )
    
    # Setup LLM response with combat start intent
    combat_intent = CombatIntent(
        action="start",
        enemies=[EnemyDescriptor(name="Goblin")]
    )
    
    intents = IntentsBlock(
        quest_intent=QuestIntent(action="none"),
        combat_intent=combat_intent,
        poi_intent=POIIntent(action="none"),
        meta=MetaIntent()
    )
    
    parsed_outcome = ParsedOutcome(
        outcome=MagicMock(narrative="Combat begins!", intents=intents),
        narrative="Combat begins!",
        is_valid=True
    )
    
    mock_llm_client.generate_narrative = AsyncMock(return_value=parsed_outcome)
    
    # Execute
    narrative, returned_intents, summary = await orchestrator.orchestrate_turn(
        character_id="test-char-id",
        user_action="I attack the goblins",
        context=context,
        dry_run=False
    )
    
    # Verify put_combat was NOT called (skipped)
    mock_journey_log_client.put_combat.assert_not_called()
    
    # Verify summary shows no combat change
    assert summary.combat_change.action == "none"


@pytest.mark.asyncio
async def test_combat_continue_updates_state(orchestrator, mock_llm_client, mock_journey_log_client):
    """Test that combat continue action updates combat state with incremented turn."""
    # Setup context - in combat with turn 3
    context = JourneyLogContext(
        character_id="test-char-id",
        status="Healthy",
        location={"id": "origin:nexus", "display_name": "The Nexus"},
        active_quest=None,
        combat_state={
            "combat_id": "existing-combat",
            "turn": 3,
            "started_at": "2026-01-16T20:00:00Z",
            "enemies": [
                {
                    "enemy_id": "enemy-1",
                    "name": "Goblin",
                    "status": "Wounded"
                }
            ],
            "player_conditions": None
        },
        recent_history=[],
        policy_state=PolicyState(
            combat_active=True,  # In combat
            has_active_quest=False
        )
    )
    
    # Setup LLM response with combat continue intent
    combat_intent = CombatIntent(
        action="continue",
        combat_notes="The battle rages on"
    )
    
    intents = IntentsBlock(
        quest_intent=QuestIntent(action="none"),
        combat_intent=combat_intent,
        poi_intent=POIIntent(action="none"),
        meta=MetaIntent()
    )
    
    parsed_outcome = ParsedOutcome(
        outcome=MagicMock(narrative="You strike at the goblin!", intents=intents),
        narrative="You strike at the goblin!",
        is_valid=True
    )
    
    mock_llm_client.generate_narrative = AsyncMock(return_value=parsed_outcome)
    
    # Execute
    narrative, returned_intents, summary = await orchestrator.orchestrate_turn(
        character_id="test-char-id",
        user_action="I attack the goblin",
        context=context,
        dry_run=False
    )
    
    # Verify put_combat was called
    mock_journey_log_client.put_combat.assert_called_once()
    call_args = mock_journey_log_client.put_combat.call_args
    
    # Verify payload has incremented turn counter
    combat_data = call_args.kwargs["combat_data"]
    assert combat_data is not None
    assert combat_data["turn"] == 4  # Incremented from 3
    assert combat_data["combat_id"] == "existing-combat"
    assert len(combat_data["enemies"]) == 1
    
    # Verify summary
    assert summary.combat_change.action == "continued"
    assert summary.combat_change.success is True


@pytest.mark.asyncio
async def test_combat_end_sends_null(orchestrator, mock_llm_client, mock_journey_log_client):
    """Test that combat end action sends combat_state=null."""
    # Setup context - in combat
    context = JourneyLogContext(
        character_id="test-char-id",
        status="Healthy",
        location={"id": "origin:nexus", "display_name": "The Nexus"},
        active_quest=None,
        combat_state={"combat_id": "existing-combat"},
        recent_history=[],
        policy_state=PolicyState(
            combat_active=True,  # In combat
            has_active_quest=False
        )
    )
    
    # Setup LLM response with combat end intent
    combat_intent = CombatIntent(
        action="end",
        combat_notes="Victory!"
    )
    
    intents = IntentsBlock(
        quest_intent=QuestIntent(action="none"),
        combat_intent=combat_intent,
        poi_intent=POIIntent(action="none"),
        meta=MetaIntent()
    )
    
    parsed_outcome = ParsedOutcome(
        outcome=MagicMock(narrative="The enemies are defeated!", intents=intents),
        narrative="The enemies are defeated!",
        is_valid=True
    )
    
    mock_llm_client.generate_narrative = AsyncMock(return_value=parsed_outcome)
    
    # Execute
    narrative, returned_intents, summary = await orchestrator.orchestrate_turn(
        character_id="test-char-id",
        user_action="I finish them off",
        context=context,
        dry_run=False
    )
    
    # Verify put_combat was called with None payload
    mock_journey_log_client.put_combat.assert_called_once()
    call_args = mock_journey_log_client.put_combat.call_args
    
    # Verify null payload for end
    combat_data = call_args.kwargs["combat_data"]
    assert combat_data is None
    
    # Verify summary
    assert summary.combat_change.action == "ended"
    assert summary.combat_change.success is True


@pytest.mark.asyncio
async def test_combat_start_with_no_enemies(orchestrator, mock_llm_client, mock_journey_log_client):
    """Test that combat start with no valid enemies fails with error in summary."""
    # Setup context - not in combat
    context = JourneyLogContext(
        character_id="test-char-id",
        status="Healthy",
        location={"id": "origin:nexus", "display_name": "The Nexus"},
        active_quest=None,
        combat_state=None,
        recent_history=[],
        policy_state=PolicyState(
            combat_active=False,
            has_active_quest=False
        )
    )
    
    # Setup LLM response with combat start intent but empty enemies
    combat_intent = CombatIntent(
        action="start",
        enemies=[],  # Empty list
        combat_notes="Combat starting somehow"
    )
    
    intents = IntentsBlock(
        quest_intent=QuestIntent(action="none"),
        combat_intent=combat_intent,
        poi_intent=POIIntent(action="none"),
        meta=MetaIntent()
    )
    
    parsed_outcome = ParsedOutcome(
        outcome=MagicMock(narrative="Combat begins!", intents=intents),
        narrative="Combat begins!",
        is_valid=True
    )
    
    mock_llm_client.generate_narrative = AsyncMock(return_value=parsed_outcome)
    
    # Execute
    narrative, returned_intents, summary = await orchestrator.orchestrate_turn(
        character_id="test-char-id",
        user_action="I attack",
        context=context,
        dry_run=False
    )
    
    # Verify put_combat was NOT called (failed validation)
    mock_journey_log_client.put_combat.assert_not_called()
    
    # Verify summary shows failed combat start with error
    assert summary.combat_change.action == "start"
    assert summary.combat_change.success is False
    assert "No valid enemies" in summary.combat_change.error


@pytest.mark.asyncio
async def test_combat_respects_max_5_enemies(orchestrator, mock_llm_client, mock_journey_log_client):
    """Test that combat start respects the 5 enemy limit."""
    # Setup context - not in combat
    context = JourneyLogContext(
        character_id="test-char-id",
        status="Healthy",
        location={"id": "origin:nexus", "display_name": "The Nexus"},
        active_quest=None,
        combat_state=None,
        recent_history=[],
        policy_state=PolicyState(
            combat_active=False,
            has_active_quest=False
        )
    )
    
    # Setup LLM response with 7 enemies (should be capped at 5)
    enemies = [
        EnemyDescriptor(name=f"Enemy {i}")
        for i in range(7)
    ]
    
    combat_intent = CombatIntent(
        action="start",
        enemies=enemies
    )
    
    intents = IntentsBlock(
        quest_intent=QuestIntent(action="none"),
        combat_intent=combat_intent,
        poi_intent=POIIntent(action="none"),
        meta=MetaIntent()
    )
    
    parsed_outcome = ParsedOutcome(
        outcome=MagicMock(narrative="Many enemies!", intents=intents),
        narrative="Many enemies!",
        is_valid=True
    )
    
    mock_llm_client.generate_narrative = AsyncMock(return_value=parsed_outcome)
    
    # Execute
    narrative, returned_intents, summary = await orchestrator.orchestrate_turn(
        character_id="test-char-id",
        user_action="I attack",
        context=context,
        dry_run=False
    )
    
    # Verify put_combat was called
    mock_journey_log_client.put_combat.assert_called_once()
    call_args = mock_journey_log_client.put_combat.call_args
    
    # Verify only 5 enemies in payload
    combat_data = call_args.kwargs["combat_data"]
    assert len(combat_data["enemies"]) == 5


@pytest.mark.asyncio
async def test_combat_end_skipped_when_not_in_combat(orchestrator, mock_llm_client, mock_journey_log_client):
    """Test that combat end is skipped when not in combat."""
    # Setup context - not in combat
    context = JourneyLogContext(
        character_id="test-char-id",
        status="Healthy",
        location={"id": "origin:nexus", "display_name": "The Nexus"},
        active_quest=None,
        combat_state=None,
        recent_history=[],
        policy_state=PolicyState(
            combat_active=False,  # Not in combat
            has_active_quest=False
        )
    )
    
    # Setup LLM response with combat end intent
    combat_intent = CombatIntent(
        action="end",
        combat_notes="Victory!"
    )
    
    intents = IntentsBlock(
        quest_intent=QuestIntent(action="none"),
        combat_intent=combat_intent,
        poi_intent=POIIntent(action="none"),
        meta=MetaIntent()
    )
    
    parsed_outcome = ParsedOutcome(
        outcome=MagicMock(narrative="The enemies are defeated!", intents=intents),
        narrative="The enemies are defeated!",
        is_valid=True
    )
    
    mock_llm_client.generate_narrative = AsyncMock(return_value=parsed_outcome)
    
    # Execute
    narrative, returned_intents, summary = await orchestrator.orchestrate_turn(
        character_id="test-char-id",
        user_action="I finish them off",
        context=context,
        dry_run=False
    )
    
    # Verify put_combat was NOT called (skipped)
    mock_journey_log_client.put_combat.assert_not_called()
    
    # Verify summary shows no combat change
    assert summary.combat_change.action == "none"
