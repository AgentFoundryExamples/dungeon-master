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
"""Integration tests for Dead status game-over scenarios.

These tests verify that the system properly handles Dead character status,
including:
- LLM instructions to generate conclusive narratives
- LLM instructions to set all intents to "none"
- Documentation of instruction-based vs validation-based enforcement

NOTE ON ENFORCEMENT MECHANISM:
------------------------------
The Dead status game-over logic is INSTRUCTION-BASED, not validated by
deterministic game engine logic. This means:

1. **Instruction Layer (System Prompt):**
   - The system prompt explicitly instructs the LLM to set all intents to "none"
   - The LLM is instructed to generate a conclusive narrative
   - These instructions are in app/prompting/prompt_builder.py

2. **No Hard Validation:**
   - The game engine does NOT validate that intents are "none" for Dead status
   - The game engine does NOT prevent quest/combat/POI actions for Dead characters
   - This is an intentional design decision to rely on LLM compliance

3. **Why Instruction-Based?**
   - Provides maximum flexibility for narrative generation
   - Allows LLM to craft appropriate game-over scenarios
   - Trusts modern LLMs (GPT-5.1+) to follow explicit instructions
   - Avoids rigid deterministic constraints that might limit storytelling

4. **Trade-offs:**
   - Pro: Natural, story-driven game-over experiences
   - Pro: Simpler architecture (no status-based validation layer)
   - Con: Relies on LLM compliance (may occasionally fail to follow rules)
   - Con: Clients must handle edge cases where LLM suggests invalid intents

5. **Client Responsibilities:**
   - Clients should detect Dead status in character context
   - Clients should prevent further turn submissions for Dead characters
   - Clients should display appropriate game-over UI

These integration tests verify the INSTRUCTION-BASED behavior by simulating
Dead status contexts and checking that the LLM (in stub mode) follows the
instructions. In production, LLM compliance depends on prompt quality and
model capabilities.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_dead_status_character_game_over_stub_mode(client):
    """Test that Dead status character receives conclusive narrative in stub mode.
    
    This test verifies:
    - Context with Dead status is accepted
    - LLM (in stub mode) generates a response
    - Response contains narrative (conclusive in stub mode)
    - Intents default to "none" in stub mode
    
    NOTE: This test validates instruction delivery, not LLM compliance.
    In stub mode, the LLM client returns a canned response. To verify actual
    LLM compliance with Dead status instructions, integration tests against
    real LLM API would be needed (not part of unit test suite).
    """
    from httpx import Response
    
    # Mock journey-log context with Dead status
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Dead",  # Character is dead
            "location": {"id": "dungeon:crypt", "display_name": "Dark Crypt"}
        },
        "quest": None,
        "combat": {"active": False, "state": None},
        "narrative": {
            "recent_turns": [
                {
                    "player_action": "I fight the boss",
                    "gm_response": "The boss strikes you down with a fatal blow.",
                    "timestamp": "2025-01-20T10:00:00Z"
                }
            ]
        }
    }
    mock_context_response.raise_for_status = MagicMock()
    
    # Mock persist response
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        # Make request with Dead character
        response = client.post(
            "/turn",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I try to stand up"
            }
        )
        
        # Verify response
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}"
        data = response.json()
        
        # Verify narrative is present
        assert "narrative" in data
        assert len(data["narrative"]) > 0
        assert "[STUB MODE]" in data["narrative"]
        
        # Verify intents (in stub mode, intents default to "none")
        assert "intents" in data
        intents = data["intents"]
        assert intents["quest_intent"]["action"] == "none"
        assert intents["combat_intent"]["action"] == "none"
        assert intents["poi_intent"]["action"] == "none"
        
        # Verify subsystem summary shows no actions taken
        assert "subsystem_summary" in data
        summary = data["subsystem_summary"]
        assert summary["quest_change"]["action"] == "none"
        assert summary["combat_change"]["action"] == "none"
        assert summary["poi_change"]["action"] == "none"


@pytest.mark.asyncio
async def test_dead_status_context_serialization_in_prompt(client):
    """Test that Dead status is correctly serialized in prompt context.
    
    This test verifies:
    - Dead status from journey-log is passed to PromptBuilder
    - PromptBuilder includes "CHARACTER STATUS: Dead" in context
    - System prompt includes Dead status instructions
    
    This validates the INSTRUCTION DELIVERY mechanism, not LLM compliance.
    """
    from httpx import Response
    from app.prompting.prompt_builder import PromptBuilder
    from app.models import JourneyLogContext
    
    # Create context with Dead status
    context = JourneyLogContext(
        character_id="550e8400-e29b-41d4-a716-446655440000",
        status="Dead",
        location={"id": "dungeon:crypt", "display_name": "Dark Crypt"},
        active_quest=None,
        combat_state=None,
        recent_history=[]
    )
    
    # Build prompt
    prompt_builder = PromptBuilder()
    system_instructions, user_prompt = prompt_builder.build_prompt(
        context=context,
        user_action="I try to get up"
    )
    
    # Verify Dead status is in user prompt
    assert "CHARACTER STATUS: Dead" in user_prompt
    
    # Verify system instructions contain Dead status rules
    assert "Dead" in system_instructions
    assert "STATUS TRANSITIONS" in system_instructions
    assert "GAME OVER RULES" in system_instructions
    
    # Verify specific Dead status instructions
    instructions_lower = system_instructions.lower()
    assert "dead status is permanent" in instructions_lower or "dead status, the session is over" in instructions_lower
    assert "none" in instructions_lower  # Instructions to set intents to "none"


@pytest.mark.asyncio  
async def test_dead_status_with_active_quest_context(client):
    """Test Dead status with active quest in context.
    
    Verifies:
    - Dead character with active quest receives conclusive narrative
    - Quest remains in context (journey-log state unchanged)
    - No quest completion or abandonment triggered by game engine
    
    This demonstrates that the game engine does NOT automatically clean up
    quests for Dead characters - it relies on LLM instructions to not suggest
    quest actions.
    """
    from httpx import Response
    
    # Mock context with Dead status AND active quest
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Dead",
            "location": {"id": "dungeon:crypt", "display_name": "Dark Crypt"}
        },
        "quest": {
            "name": "Defeat the Dark Lord",
            "description": "The final battle",
            "completion_state": "in_progress"
        },
        "combat": {"active": False, "state": None},
        "narrative": {"recent_turns": []}
    }
    mock_context_response.raise_for_status = MagicMock()
    
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        response = client.post(
            "/turn",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I try to continue my quest"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify no quest action taken (game engine doesn't auto-abandon)
        assert data["subsystem_summary"]["quest_change"]["action"] == "none"
        
        # In stub mode, intents are "none" by default
        assert data["intents"]["quest_intent"]["action"] == "none"


@pytest.mark.asyncio
async def test_dead_status_with_active_combat_context(client):
    """Test Dead status with active combat in context.
    
    Verifies:
    - Dead character with active combat receives narrative
    - Combat state remains in context (journey-log state unchanged)
    - No combat ending triggered automatically by game engine
    
    This demonstrates that the game engine does NOT validate Dead status
    for combat actions - it relies on LLM compliance with instructions.
    """
    from httpx import Response
    
    # Mock context with Dead status AND active combat
    mock_context_response = MagicMock(spec=Response)
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Dead",
            "location": {"id": "dungeon:crypt", "display_name": "Dark Crypt"}
        },
        "quest": None,
        "combat": {
            "active": True,
            "state": {
                "combat_id": "combat-123",
                "turn": 5,
                "enemies": [
                    {
                        "enemy_id": "boss-1",
                        "name": "Dark Lord",
                        "status": "Healthy",
                        "weapon": "Cursed Blade"
                    }
                ]
            }
        },
        "narrative": {"recent_turns": []}
    }
    mock_context_response.raise_for_status = MagicMock()
    
    mock_persist_response = MagicMock(spec=Response)
    mock_persist_response.raise_for_status = MagicMock()
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        
        mock_get.return_value = mock_context_response
        mock_post.return_value = mock_persist_response
        
        response = client.post(
            "/turn",
            json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I attack"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify no combat action taken (game engine doesn't auto-end combat)
        assert data["subsystem_summary"]["combat_change"]["action"] == "none"
        
        # In stub mode, intents are "none" by default
        assert data["intents"]["combat_intent"]["action"] == "none"


@pytest.mark.asyncio
async def test_prompt_builder_includes_dead_status_instructions():
    """Test that PromptBuilder includes comprehensive Dead status instructions.
    
    This is a documentation test that verifies the instruction-based enforcement
    mechanism is properly configured in the system prompt.
    """
    from app.prompting.prompt_builder import PromptBuilder
    
    # Get system instructions
    system_instructions = PromptBuilder.SYSTEM_INSTRUCTIONS
    
    # Verify Dead status section exists
    assert "STATUS TRANSITIONS AND GAME OVER RULES:" in system_instructions
    
    # Verify specific instructions for Dead status
    assert "Healthy -> Wounded -> Dead" in system_instructions
    assert "Dead status" in system_instructions
    assert "session is OVER" in system_instructions
    
    # Verify healing restrictions
    assert "CANNOT revive" in system_instructions or "cannot revive" in system_instructions.lower()
    
    # Verify intent instructions for Dead status
    assert "none" in system_instructions.lower()
    
    # Verify conclusive narrative instruction
    assert "concluding narrative" in system_instructions or "final narrative" in system_instructions
