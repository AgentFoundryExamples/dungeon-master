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
"""Prompt builder for constructing LLM prompts from game context."""

import json
from typing import Tuple
from app.models import JourneyLogContext, PolicyHints, get_outcome_json_schema, get_outcome_schema_example


class PromptBuilder:
    """Builds structured prompts for LLM narrative generation.
    
    This class composes:
    - System instructions defining the LLM's role and JSON output requirements
    - DungeonMasterOutcome JSON schema for structured output
    - Serialized game context (status, location, quest, combat, history)
    - User action to respond to
    
    The prompt enforces JSON-only output with the DungeonMasterOutcome schema.
    The LLM generates narrative and suggests intents, but does NOT decide
    subsystem eligibility - that's handled by deterministic service logic.
    
    Schema Evolution:
    - When models evolve, update get_outcome_json_schema() in models.py
    - The schema is automatically included in prompts
    - Test with new models to ensure compatibility
    - Consider token limits when schema grows (currently ~9KB)
    
    Token Management:
    - Schema text: ~9KB (acceptable for GPT-5+ context windows)
    - Recent history: Last 20 turns with truncation at 200/300 chars
    - If needed, reduce history window or omit optional schema descriptions
    """

    SYSTEM_INSTRUCTIONS = """You are a narrative engine for a text-based adventure game.

CRITICAL: You MUST respond with valid JSON matching the DungeonMasterOutcome schema provided below.
Do NOT output any prose, explanations, or text outside the JSON object.
Output ONLY valid JSON that conforms exactly to the schema.

Your role:
- Generate engaging, immersive narrative responses to player actions
- Maintain consistency with the character's current state and ongoing story
- Consider active quests, combat situations, and location context
- Suggest intents (quest, combat, POI actions) based on narrative context
- Keep narrative concise but descriptive (aim for 2-4 paragraphs)
- Respond to the player's action in a natural, story-driven way

Guidelines for narrative field:
- Use vivid, atmospheric language appropriate for fantasy adventure
- React to the character's health status and current situation
- Reference recent story events when relevant
- Maintain appropriate tone based on context (tense in combat, relaxed in safe areas)
- Do not make decisions for the player - describe outcomes and present choices

Guidelines for intents field:
- Fill intents based on what happens in the narrative
- Intents are SUGGESTIONS only - the game service makes final decisions
- Subsystem eligibility (can quest be offered? can combat start?) is determined by 
  DETERMINISTIC game logic, NOT by you
- Be concise in intent descriptions - avoid repeating full narrative text
- Use "none" action when no specific intent applies

IMPORTANT: Subsystem decisions are DETERMINISTIC and handled by the game engine:
- You suggest intents based on narrative
- The game engine decides if those intents are eligible/valid
- Do NOT try to decide eligibility yourself - just suggest what fits the story

You will receive:
1. Character context (status, location, quest, combat state, recent history)
2. The player's current action

OUTPUT FORMAT (DungeonMasterOutcome JSON Schema):"""

    def __init__(self):
        """Initialize the prompt builder."""
        pass

    def build_prompt(
        self,
        context: JourneyLogContext,
        user_action: str
    ) -> Tuple[str, str]:
        """Build a complete prompt for LLM narrative generation.
        
        Args:
            context: Character context from journey-log
            user_action: The player's action for this turn
            
        Returns:
            Tuple of (system_instructions, user_prompt)
            System instructions define the LLM's role and include JSON schema
            User prompt contains serialized context, action, and JSON format reminder
        """
        # Get the JSON schema and example for DungeonMasterOutcome
        schema = get_outcome_json_schema()
        schema_json = json.dumps(schema, indent=2)
        example_json = get_outcome_schema_example()
        
        # Build complete system instructions with schema
        complete_system_instructions = f"""{self.SYSTEM_INSTRUCTIONS}

{schema_json}

EXAMPLE OUTPUT:
{example_json}

Remember: Output ONLY valid JSON matching this schema. No additional text before or after the JSON object."""

        # Serialize the context into a structured format
        context_str = self._serialize_context(context)

        # Build the user prompt combining context and action
        user_prompt = f"""{context_str}

PLAYER ACTION:
{user_action}

Generate a DungeonMasterOutcome JSON response to the player's action based on the above context.
Output ONLY the JSON object, no other text."""

        return (complete_system_instructions, user_prompt)

    def _serialize_context(self, context: JourneyLogContext) -> str:
        """Serialize game context into a readable format for the LLM.
        
        Args:
            context: Character context from journey-log
            
        Returns:
            Formatted context string
        """
        sections = []

        # Character Status
        sections.append(f"CHARACTER STATUS: {context.status}")

        # Location
        location_str = self._format_location(context.location)
        sections.append(f"CURRENT LOCATION: {location_str}")

        # Active Quest
        if context.active_quest:
            quest_str = self._format_quest(context.active_quest)
            sections.append(f"ACTIVE QUEST:\n{quest_str}")

        # Combat State
        if context.combat_state:
            combat_str = self._format_combat(context.combat_state)
            sections.append(f"COMBAT STATE:\n{combat_str}")

        # Memory Sparks (POIs) - only show if present
        if context.memory_sparks:
            memory_sparks_str = self._format_memory_sparks(context.memory_sparks)
            sections.append(f"MEMORY SPARKS (Previously Discovered Locations):\n{memory_sparks_str}")

        # Policy Hints (if available)
        if context.policy_hints:
            policy_str = self._format_policy_hints(context.policy_hints)
            sections.append(f"POLICY HINTS:\n{policy_str}")

        # Recent History
        if context.recent_history:
            history_str = self._format_history(context.recent_history)
            sections.append(f"RECENT NARRATIVE HISTORY:\n{history_str}")

        return "\n\n".join(sections)

    def _format_location(self, location: dict) -> str:
        """Format location information.
        
        Args:
            location: Location dict from context
            
        Returns:
            Formatted location string
        """
        if isinstance(location, dict):
            display_name = location.get("display_name", "Unknown Location")
            location_id = location.get("id", "")
            if location_id:
                return f"{display_name} ({location_id})"
            return display_name
        elif isinstance(location, str):
            return location
        else:
            return "Unknown Location"

    def _format_quest(self, quest: dict) -> str:
        """Format quest information.
        
        Args:
            quest: Quest dict from context
            
        Returns:
            Formatted quest string
        """
        name = quest.get("name", "Unknown Quest")
        description = quest.get("description", "")
        completion_state = quest.get("completion_state", "unknown")

        lines = [
            f"  Name: {name}",
            f"  Description: {description}",
            f"  Status: {completion_state}"
        ]

        requirements = quest.get("requirements", [])
        if requirements:
            req_str = ", ".join(requirements)
            lines.append(f"  Requirements: {req_str}")

        return "\n".join(lines)

    def _format_combat(self, combat_state: dict) -> str:
        """Format combat state information.
        
        Args:
            combat_state: Combat state dict from context
            
        Returns:
            Formatted combat string
        """
        if not combat_state:
            return "  No active combat"

        turn = combat_state.get("turn", 1)
        enemies = combat_state.get("enemies", [])

        lines = [f"  Turn: {turn}"]

        if enemies:
            lines.append(f"  Enemies ({len(enemies)}):")
            for enemy in enemies:
                name = enemy.get("name", "Unknown")
                status = enemy.get("status", "Unknown")
                weapon = enemy.get("weapon", "")
                weapon_str = f" (armed with {weapon})" if weapon else ""
                lines.append(f"    - {name}: {status}{weapon_str}")

        return "\n".join(lines)

    def _format_memory_sparks(self, memory_sparks: list) -> str:
        """Format memory sparks (random POIs) for the LLM.
        
        Memory sparks are previously discovered locations that help the LLM
        recall and reference places in the character's journey. They are
        fetched randomly from the character's POI collection.
        
        Args:
            memory_sparks: List of POI dictionaries from journey-log
            
        Returns:
            Formatted memory sparks string with deterministic ordering
        """
        if not memory_sparks:
            return "  (No memory sparks available)"
        
        lines = []
        lines.append(f"  {len(memory_sparks)} previously discovered location(s):")
        
        # Sort by timestamp_discovered descending (newest first) for deterministic order
        # If timestamp not present, sort by name as fallback
        sorted_sparks = sorted(
            memory_sparks,
            key=lambda poi: (
                poi.get("timestamp_discovered", ""),
                poi.get("name", "")
            ),
            reverse=True
        )
        
        for i, poi in enumerate(sorted_sparks, 1):
            name = poi.get("name", "Unknown Location")
            description = poi.get("description", "")
            tags = poi.get("tags", [])
            
            lines.append(f"\n  {i}. {name}")
            if description:
                # Truncate long descriptions to keep prompt manageable
                if len(description) > 200:
                    description = description[:200] + "..."
                lines.append(f"     {description}")
            if tags:
                tags_str = ", ".join(tags[:5])  # Limit to 5 tags
                lines.append(f"     Tags: {tags_str}")
        
        return "\n".join(lines)

    def _format_policy_hints(self, policy_hints: PolicyHints) -> str:
        """Format policy hints information.
        
        Args:
            policy_hints: PolicyHints from context
            
        Returns:
            Formatted policy hints string
        """
        lines = []
        
        # Quest trigger decision
        quest_dec = policy_hints.quest_trigger_decision
        quest_status = "ALLOWED" if quest_dec.roll_passed else "NOT ALLOWED"
        lines.append(f"  Quest Trigger: {quest_status}")
        if not quest_dec.roll_passed:
            if not quest_dec.eligible:
                lines.append("    Reason: Not eligible (cooldown or active quest)")
            else:
                lines.append("    Reason: Roll did not pass")
        
        # POI trigger decision
        poi_dec = policy_hints.poi_trigger_decision
        poi_status = "ALLOWED" if poi_dec.roll_passed else "NOT ALLOWED"
        lines.append(f"  POI Creation: {poi_status}")
        if not poi_dec.roll_passed:
            if not poi_dec.eligible:
                lines.append("    Reason: Not eligible (cooldown)")
            else:
                lines.append("    Reason: Roll did not pass")
        
        lines.append("\n  Note: Only suggest quest offers or POI creation if marked as ALLOWED above.")
        
        return "\n".join(lines)

    def _format_history(self, history: list) -> str:
        """Format recent narrative history.
        
        Displays up to the last 20 turns of narrative history to provide context
        for the LLM while keeping token usage reasonable. Long text is
        truncated to prevent excessive prompt length.
        
        Note: The history list is provided by the journey-log service and may
        contain up to 20 turns (configurable via JOURNEY_LOG_RECENT_N in config).
        This method displays all provided turns.
        
        Args:
            history: List of recent turn dicts from context
            
        Returns:
            Formatted history string
        """
        if not history:
            return "  (No recent history)"

        # Display up to the last 20 turns from history
        # If fewer than 20 turns are provided, all are displayed
        # This provides sufficient story continuity while managing token usage
        recent_turns = history[-20:]

        lines = []
        for i, turn in enumerate(recent_turns, 1):
            player_action = turn.get("player_action", "")
            gm_response = turn.get("gm_response", "")

            # Truncate long responses for context efficiency
            if len(player_action) > 200:
                player_action = player_action[:200] + "..."
            if len(gm_response) > 300:
                gm_response = gm_response[:300] + "..."

            lines.append(f"  Turn {i}:")
            lines.append(f"    Player: {player_action}")
            lines.append(f"    GM: {gm_response}")

        return "\n".join(lines)
