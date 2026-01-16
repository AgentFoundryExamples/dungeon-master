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
"""Integration tests for quest subsystem via turn orchestrator."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.services.turn_orchestrator import TurnOrchestrator
from app.services.policy_engine import PolicyEngine
from app.services.llm_client import LLMClient
from app.services.journey_log_client import JourneyLogClient, JourneyLogClientError
from app.services.outcome_parser import ParsedOutcome
from app.prompting.prompt_builder import PromptBuilder
from app.models import (
    JourneyLogContext,
    PolicyState,
    IntentsBlock,
    QuestIntent,
    CombatIntent,
    POIIntent,
    DungeonMasterOutcome,
    QuestTriggerDecision,
    POITriggerDecision,
)


@pytest.fixture
def policy_engine():
    """Create a policy engine with deterministic settings."""
    return PolicyEngine(
        quest_trigger_prob=1.0,  # Always pass
        quest_cooldown_turns=0,
        poi_trigger_prob=1.0,
        poi_cooldown_turns=0,
        rng_seed=42
    )


@pytest.fixture
def llm_client():
    """Create a mock LLM client."""
    client = AsyncMock(spec=LLMClient)
    return client


@pytest.fixture
def journey_log_client():
    """Create a mock journey log client."""
    client = AsyncMock(spec=JourneyLogClient)
    # Default successful responses
    client.persist_narrative = AsyncMock()
    client.put_quest = AsyncMock()
    client.delete_quest = AsyncMock()
    client.put_combat = AsyncMock()
    client.post_poi = AsyncMock()
    return client


@pytest.fixture
def prompt_builder():
    """Create a prompt builder."""
    return PromptBuilder()


@pytest.fixture
def orchestrator(policy_engine, llm_client, journey_log_client, prompt_builder):
    """Create a turn orchestrator with all dependencies."""
    return TurnOrchestrator(
        policy_engine=policy_engine,
        llm_client=llm_client,
        journey_log_client=journey_log_client,
        prompt_builder=prompt_builder
    )


@pytest.fixture
def base_context():
    """Create a base context without active quest."""
    return JourneyLogContext(
        character_id="char-123",
        status="Healthy",
        location={"id": "town", "display_name": "Town Square"},
        active_quest=None,
        combat_state=None,
        recent_history=[],
        policy_state=PolicyState(
            has_active_quest=False,
            combat_active=False,
            turns_since_last_quest=10,
            turns_since_last_poi=10
        )
    )


@pytest.mark.asyncio
async def test_quest_put_with_valid_intent(orchestrator, llm_client, journey_log_client, base_context):
    """Test that quest PUT is called with valid payload when policy triggers and intent is offer."""
    # Setup: LLM returns valid quest offer
    outcome = DungeonMasterOutcome(
        narrative="A mysterious stranger approaches you with a quest.",
        intents=IntentsBlock(
            quest_intent=QuestIntent(
                action="offer",
                quest_title="Find the Lost Artifact",
                quest_summary="Recover the ancient artifact from the ruins.",
                quest_details={"difficulty": "hard", "reward_experience": 500}
            ),
            combat_intent=CombatIntent(action="none"),
            poi_intent=POIIntent(action="none")
        )
    )
    llm_client.generate_narrative.return_value = ParsedOutcome(
        outcome=outcome,
        narrative=outcome.narrative,
        is_valid=True
    )
    
    # Execute
    narrative, intents, summary = await orchestrator.orchestrate_turn(
        character_id="char-123",
        user_action="I look around for opportunities",
        context=base_context,
        trace_id="test-trace"
    )
    
    # Verify quest PUT was called
    assert journey_log_client.put_quest.called
    call_args = journey_log_client.put_quest.call_args
    assert call_args.kwargs["character_id"] == "char-123"
    
    # Verify payload structure matches journey-log API
    quest_data = call_args.kwargs["quest_data"]
    assert quest_data["name"] == "Find the Lost Artifact"
    assert quest_data["description"] == "Recover the ancient artifact from the ruins."
    assert quest_data["requirements"] == []
    assert "rewards" in quest_data
    assert quest_data["rewards"]["experience"] == 500
    assert quest_data["completion_state"] == "not_started"
    assert "updated_at" in quest_data
    
    # Verify summary reflects success
    assert summary.quest_change.action == "offered"
    assert summary.quest_change.success is True


@pytest.mark.asyncio
async def test_quest_put_with_fallback_payload(orchestrator, llm_client, journey_log_client, base_context):
    """Test quest PUT with fallback payload when intent has missing fields."""
    # Setup: LLM returns quest offer with missing fields
    outcome = DungeonMasterOutcome(
        narrative="A mysterious stranger approaches you.",
        intents=IntentsBlock(
            quest_intent=QuestIntent(
                action="offer",
                quest_title=None,  # Missing title
                quest_summary=None,  # Missing summary
                quest_details=None  # Missing details
            ),
            combat_intent=CombatIntent(action="none"),
            poi_intent=POIIntent(action="none")
        )
    )
    llm_client.generate_narrative.return_value = ParsedOutcome(
        outcome=outcome,
        narrative=outcome.narrative,
        is_valid=True
    )
    
    # Execute
    narrative, intents, summary = await orchestrator.orchestrate_turn(
        character_id="char-123",
        user_action="I look around",
        context=base_context,
        trace_id="test-trace"
    )
    
    # Verify quest PUT was called with fallback values
    assert journey_log_client.put_quest.called
    quest_data = journey_log_client.put_quest.call_args.kwargs["quest_data"]
    assert quest_data["name"] == "A New Opportunity"
    assert quest_data["description"] == "An opportunity for adventure presents itself."
    assert quest_data["requirements"] == []
    assert quest_data["rewards"] == {"items": [], "currency": {}, "experience": None}
    
    # Verify summary
    assert summary.quest_change.action == "offered"
    assert summary.quest_change.success is True


@pytest.mark.asyncio
async def test_quest_put_with_no_intent_but_policy_triggered(orchestrator, llm_client, journey_log_client, base_context):
    """Test quest PUT when policy triggers but LLM provides no quest intent."""
    # Setup: LLM returns no quest intent
    outcome = DungeonMasterOutcome(
        narrative="You continue your journey.",
        intents=IntentsBlock(
            quest_intent=None,  # No quest intent
            combat_intent=CombatIntent(action="none"),
            poi_intent=POIIntent(action="none")
        )
    )
    llm_client.generate_narrative.return_value = ParsedOutcome(
        outcome=outcome,
        narrative=outcome.narrative,
        is_valid=True
    )
    
    # Execute
    narrative, intents, summary = await orchestrator.orchestrate_turn(
        character_id="char-123",
        user_action="I explore",
        context=base_context,
        trace_id="test-trace"
    )
    
    # Quest intent should be normalized to fallback offer
    assert intents.quest_intent is not None
    assert intents.quest_intent.action == "offer"
    assert intents.quest_intent.quest_title == "A New Opportunity"
    
    # Verify quest PUT was called with fallback
    assert journey_log_client.put_quest.called
    quest_data = journey_log_client.put_quest.call_args.kwargs["quest_data"]
    assert quest_data["name"] == "A New Opportunity"


@pytest.mark.asyncio
async def test_quest_put_skipped_when_active_quest_exists(orchestrator, llm_client, journey_log_client, base_context):
    """Test quest PUT is skipped when character already has active quest."""
    # Setup: Context has active quest
    base_context.active_quest = {"name": "Existing Quest"}
    base_context.policy_state.has_active_quest = True
    
    # LLM returns quest offer
    outcome = DungeonMasterOutcome(
        narrative="Another quest opportunity appears.",
        intents=IntentsBlock(
            quest_intent=QuestIntent(
                action="offer",
                quest_title="New Quest",
                quest_summary="A new adventure awaits.",
                quest_details={}
            ),
            combat_intent=CombatIntent(action="none"),
            poi_intent=POIIntent(action="none")
        )
    )
    llm_client.generate_narrative.return_value = ParsedOutcome(
        outcome=outcome,
        narrative=outcome.narrative,
        is_valid=True
    )
    
    # Execute
    narrative, intents, summary = await orchestrator.orchestrate_turn(
        character_id="char-123",
        user_action="I explore",
        context=base_context,
        trace_id="test-trace"
    )
    
    # Verify quest PUT was NOT called
    assert not journey_log_client.put_quest.called
    
    # Verify summary reflects no action
    assert summary.quest_change.action == "none"


@pytest.mark.asyncio
async def test_quest_delete_on_complete(orchestrator, llm_client, journey_log_client, base_context):
    """Test quest DELETE is called when intent is complete and active quest exists."""
    # Setup: Context has active quest
    base_context.active_quest = {"name": "Active Quest"}
    base_context.policy_state.has_active_quest = True
    
    # LLM returns quest complete
    outcome = DungeonMasterOutcome(
        narrative="You complete the quest successfully!",
        intents=IntentsBlock(
            quest_intent=QuestIntent(
                action="complete",
                quest_title=None,
                quest_summary=None,
                quest_details=None
            ),
            combat_intent=CombatIntent(action="none"),
            poi_intent=POIIntent(action="none")
        )
    )
    llm_client.generate_narrative.return_value = ParsedOutcome(
        outcome=outcome,
        narrative=outcome.narrative,
        is_valid=True
    )
    
    # Execute
    narrative, intents, summary = await orchestrator.orchestrate_turn(
        character_id="char-123",
        user_action="I complete the quest",
        context=base_context,
        trace_id="test-trace"
    )
    
    # Verify quest DELETE was called
    assert journey_log_client.delete_quest.called
    call_args = journey_log_client.delete_quest.call_args
    assert call_args.kwargs["character_id"] == "char-123"
    
    # Verify summary reflects completion
    assert summary.quest_change.action == "completed"
    assert summary.quest_change.success is True


@pytest.mark.asyncio
async def test_quest_delete_on_abandon(orchestrator, llm_client, journey_log_client, base_context):
    """Test quest DELETE is called when intent is abandon and active quest exists."""
    # Setup: Context has active quest
    base_context.active_quest = {"name": "Active Quest"}
    base_context.policy_state.has_active_quest = True
    
    # LLM returns quest abandon
    outcome = DungeonMasterOutcome(
        narrative="You decide to abandon this quest.",
        intents=IntentsBlock(
            quest_intent=QuestIntent(
                action="abandon",
                quest_title=None,
                quest_summary=None,
                quest_details=None
            ),
            combat_intent=CombatIntent(action="none"),
            poi_intent=POIIntent(action="none")
        )
    )
    llm_client.generate_narrative.return_value = ParsedOutcome(
        outcome=outcome,
        narrative=outcome.narrative,
        is_valid=True
    )
    
    # Execute
    narrative, intents, summary = await orchestrator.orchestrate_turn(
        character_id="char-123",
        user_action="I abandon the quest",
        context=base_context,
        trace_id="test-trace"
    )
    
    # Verify quest DELETE was called
    assert journey_log_client.delete_quest.called
    
    # Verify summary reflects abandonment
    assert summary.quest_change.action == "abandoned"
    assert summary.quest_change.success is True


@pytest.mark.asyncio
async def test_quest_delete_skipped_when_no_active_quest(orchestrator, llm_client, journey_log_client, base_context):
    """Test quest DELETE is skipped when no active quest exists."""
    # Setup: No active quest
    base_context.active_quest = None
    base_context.policy_state.has_active_quest = False
    
    # LLM returns quest complete (but no quest to complete)
    outcome = DungeonMasterOutcome(
        narrative="You look around but have no quest to complete.",
        intents=IntentsBlock(
            quest_intent=QuestIntent(
                action="complete",
                quest_title=None,
                quest_summary=None,
                quest_details=None
            ),
            combat_intent=CombatIntent(action="none"),
            poi_intent=POIIntent(action="none")
        )
    )
    llm_client.generate_narrative.return_value = ParsedOutcome(
        outcome=outcome,
        narrative=outcome.narrative,
        is_valid=True
    )
    
    # Execute
    narrative, intents, summary = await orchestrator.orchestrate_turn(
        character_id="char-123",
        user_action="I complete the quest",
        context=base_context,
        trace_id="test-trace"
    )
    
    # Verify quest DELETE was NOT called
    assert not journey_log_client.delete_quest.called
    
    # Verify summary reflects no action
    assert summary.quest_change.action == "none"


@pytest.mark.asyncio
async def test_quest_put_409_conflict_handling(orchestrator, llm_client, journey_log_client, base_context):
    """Test HTTP 409 conflict is logged and marked as skipped without crashing."""
    # Setup: LLM returns quest offer
    outcome = DungeonMasterOutcome(
        narrative="A quest appears.",
        intents=IntentsBlock(
            quest_intent=QuestIntent(
                action="offer",
                quest_title="Test Quest",
                quest_summary="Test summary",
                quest_details={}
            ),
            combat_intent=CombatIntent(action="none"),
            poi_intent=POIIntent(action="none")
        )
    )
    llm_client.generate_narrative.return_value = ParsedOutcome(
        outcome=outcome,
        narrative=outcome.narrative,
        is_valid=True
    )
    
    # Mock 409 conflict response
    journey_log_client.put_quest.side_effect = JourneyLogClientError(
        "Journey-log returned 409: Active quest already exists"
    )
    
    # Execute - should not raise exception
    narrative, intents, summary = await orchestrator.orchestrate_turn(
        character_id="char-123",
        user_action="I explore",
        context=base_context,
        trace_id="test-trace"
    )
    
    # Verify summary marks as skipped
    assert summary.quest_change.action == "skipped"
    assert summary.quest_change.success is False
    assert "409" in summary.quest_change.error
    
    # Verify narrative still completed
    assert summary.narrative_persisted is True


@pytest.mark.asyncio
async def test_quest_put_other_error_handling(orchestrator, llm_client, journey_log_client, base_context):
    """Test other journey-log errors are logged and continue without crashing."""
    # Setup: LLM returns quest offer
    outcome = DungeonMasterOutcome(
        narrative="A quest appears.",
        intents=IntentsBlock(
            quest_intent=QuestIntent(
                action="offer",
                quest_title="Test Quest",
                quest_summary="Test summary",
                quest_details={}
            ),
            combat_intent=CombatIntent(action="none"),
            poi_intent=POIIntent(action="none")
        )
    )
    llm_client.generate_narrative.return_value = ParsedOutcome(
        outcome=outcome,
        narrative=outcome.narrative,
        is_valid=True
    )
    
    # Mock generic error response
    journey_log_client.put_quest.side_effect = JourneyLogClientError(
        "Journey-log returned 500: Internal Server Error"
    )
    
    # Execute - should not raise exception
    narrative, intents, summary = await orchestrator.orchestrate_turn(
        character_id="char-123",
        user_action="I explore",
        context=base_context,
        trace_id="test-trace"
    )
    
    # Verify summary marks as failed
    assert summary.quest_change.action == "offer"
    assert summary.quest_change.success is False
    assert "500" in summary.quest_change.error or "Internal Server Error" in summary.quest_change.error
    
    # Verify narrative still completed
    assert summary.narrative_persisted is True
