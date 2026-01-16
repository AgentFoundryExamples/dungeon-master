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
from app.models import JourneyLogContext


class PromptBuilder:
    """Builds structured prompts for LLM narrative generation.
    
    This class composes:
    - System instructions defining the LLM's role
    - Serialized game context (status, location, quest, combat, history)
    - User action to respond to
    
    The modular structure allows downstream subsystems to extend prompts
    with additional context or instructions.
    """

    SYSTEM_INSTRUCTIONS = """You are a narrative engine and decision-making system for a text-based adventure game.

Your role:
- Generate engaging, immersive narrative responses to player actions
- Maintain consistency with the character's current state and ongoing story
- Consider active quests, combat situations, and location context
- Keep responses concise but descriptive (aim for 2-4 paragraphs)
- Respond to the player's action in a natural, story-driven way

Guidelines:
- Use vivid, atmospheric language appropriate for fantasy adventure
- React to the character's health status and current situation
- Reference recent story events when relevant
- Maintain appropriate tone based on context (tense in combat, relaxed in safe areas)
- Do not make decisions for the player - describe outcomes and present choices

You will receive:
1. Character context (status, location, quest, combat state, recent history)
2. The player's current action

Generate a narrative response that:
- Directly addresses the player's action
- Advances the story naturally
- Maintains immersion and engagement"""

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
            System instructions define the LLM's role
            User prompt contains serialized context and action
        """
        # Serialize the context into a structured format
        context_str = self._serialize_context(context)

        # Build the user prompt combining context and action
        user_prompt = f"""{context_str}

PLAYER ACTION:
{user_action}

Generate a narrative response to the player's action based on the above context."""

        return (self.SYSTEM_INSTRUCTIONS, user_prompt)

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

    def _format_history(self, history: list) -> str:
        """Format recent narrative history.
        
        Args:
            history: List of recent turn dicts from context
            
        Returns:
            Formatted history string
        """
        if not history:
            return "  (No recent history)"

        # Show last 5 turns for context (most recent last)
        recent_turns = history[-5:]

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
