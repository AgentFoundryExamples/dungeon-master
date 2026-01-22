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
from typing import Tuple, Optional
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
- Respond IMMEDIATELY and DIRECTLY to the player's action - don't make them repeat themselves

CRITICAL RESPONSIVENESS RULES:
- When a player states an action, EXECUTE it in the narrative in a way that meaningfully moves the story forward - don't ask for confirmation
- Example: "I enter the tavern" -> Describe them entering and the scene inside, not "You walk up to the door slowly about to enter the tavern"
- Example: "I attack the goblin" -> Describe the attack and result, not "You prepare your sword to swing"
- Example: "I pick up the sword" -> They have it, describe what happens
- MOVE THE STORY FORWARD with each response - the player drives the plot
- Only ask clarifying questions if the action is genuinely ambiguous
- Respect the world setting/adventure prompt if provided - maintain its tone and themes

LOCATION SYSTEM:
- POIs (Points of Interest) are named, significant locations (towns, dungeons, taverns, forests, landmarks)
- minor_location is ALWAYS updated - describes character's exact current position within or between locations

CRITICAL LOCATION TRACKING RULES:
- When character is IN a meaningful named location (POI):
  * Set location_id (e.g., 'tavern:rusty_nail', 'town:willowdale', 'dungeon:shadow_keep')
  * Set location_display_name (e.g., 'The Rusty Nail Tavern', 'Willowdale Village')
  * Set minor_location to describe exact position within (e.g., 'at the bar', 'in the town square')
  * Use action='update_minor' when moving within the same POI
  * Example: location_id='tavern:rusty_nail', location_display_name='The Rusty Nail Tavern', minor_location='at the bar counter'

- When character is BETWEEN locations or in wilderness:
  * Set location_id=null and location_display_name=null
  * Set minor_location to describe the travel path or wilderness area
  * Use action='update_minor'
  * Example: location_id=null, location_display_name=null, minor_location='on the forest road heading north toward the mountains'

- When character ENTERS a new significant location:
  * Create the POI using poi_intent with action='create'
  * Set the location fields (location_id, location_display_name, minor_location)
  * Use action='update_minor' in location_intent

- When character LEAVES a POI to travel:
  * Use action='leave_poi' in location_intent
  * This will set location_id/display_name to null automatically
  * Update minor_location to describe where they're going

KEY PRINCIPLE: Always meaningfully track WHERE the character is. If they're at a named place, fill in location_id and location_display_name. Update minor_location with EVERY movement to show precise position.

STATUS TRANSITIONS AND GAME OVER RULES:
Characters progress through health statuses in strict order: Healthy -> Wounded -> Dead
- Healing can move characters from Wounded back to Healthy
- Healing CANNOT revive characters from Dead status
- Once a character reaches Dead status, the session is OVER
- When a character dies, generate a final narrative describing their demise
- Do NOT continue gameplay, offer new quests, or suggest actions after death
- The Dead status is permanent and marks the end of the character's journey

Guidelines for narrative field:
- Use vivid, atmospheric language appropriate for fantasy adventure
- React to the character's health status and current situation
- Reference recent story events when relevant
- Maintain appropriate tone based on context (tense in combat, relaxed in safe areas)
- Do not make decisions for the player - describe outcomes and present choices
- When character status is Dead, write a concluding narrative and set all intents to "none"

Guidelines for intents field:
- Fill intents based on what happens in the narrative
- Intents are SUGGESTIONS only - the game service makes final decisions
- Subsystem eligibility (can quest be offered? can combat start?) is determined by 
  DETERMINISTIC game logic, NOT by you
- Be concise in intent descriptions - avoid repeating full narrative text
- Use "none" action when no specific intent applies
- ALWAYS use "none" for all intents when character status is Dead

QUEST AND POI TRIGGER INSTRUCTIONS:
- You will receive Policy Hints indicating whether quest starts are ALLOWED
- Quest Trigger: ALLOWED means you SHOULD START a quest as a driving narrative element
- If quest trigger is NOT ALLOWED, DO NOT suggest starting new quests in your intents
- When quest triggers are eligible, you will receive a cooldown period (in turns) since the last quest

QUEST PHILOSOPHY - QUESTS ARE STORY DRIVERS:
- When policy allows, START quests immediately as part of the narrative (not as optional offers)
- Quests should emerge naturally from the story - a problem to solve, a goal to achieve
- Example: "A mysterious figure approaches with urgent news of bandits threatening the village..." then use quest_intent action='start'
- Once a quest is active, FOCUS ON ADVANCING IT when player actions align with the objective
- Use quest_intent action='advance' with progress_update to track meaningful progress
- Example progress updates: "Found the hideout location", "Convinced the guard to help", "Discovered a critical clue"
- The quest should feel like the main storyline, not a side activity
- Complete quests when objectives are achieved, abandon if the player explicitly gives up

POI CREATION (LLM-DRIVEN):
- YOU decide when to create POIs based on narrative coherence
- Create POIs when the character discovers or enters a new significant named location
- POIs should be memorable places: towns, dungeons, taverns, landmarks, significant wilderness areas
- Use poi_intent with action='create' whenever it makes narrative sense
- No cooldowns or restrictions - create POIs as the story demands
- POIs help track the character's journey and can be referenced in future quests

MEMORY SPARKS - LEVERAGING PAST LOCATIONS FOR QUEST DESIGN:
- When a quest trigger is ALLOWED, you may receive "Memory Sparks" in the context
- Memory Sparks are previously discovered locations from the character's journey
- Use these locations to create quests that reference familiar places
- Examples: "Return to the Ancient Library", "Investigate rumors from the Misty Tavern"
- This creates narrative continuity and rewards exploration
- If no Memory Sparks are provided, design quests for new or nearby locations instead

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

        return (complete_system_instructions, user_prompt)

    def build_intro_prompt(
        self,
        name: str,
        race: str,
        class_name: str,
        custom_prompt: Optional[str] = None
    ) -> Tuple[str, str]:
        """Build a prompt for generating the initial character introduction.
        
        Args:
            name: Character name
            race: Character race
            class_name: Character class
            custom_prompt: Optional custom world/setting prompt
            
        Returns:
            Tuple of (system_instructions, user_prompt)
        """
        # Get the JSON schema and example
        schema = get_outcome_json_schema()
        schema_json = json.dumps(schema, indent=2)
        
        # Specialized system instructions for intro
        intro_system_instructions = f"""You are a narrative engine for a text-based adventure game.
Your task is to generate an immersive, atmospheric introduction scene for a new character.

CRITICAL: You MUST respond with valid JSON matching the DungeonMasterOutcome schema provided below.
Do NOT output any prose outside the JSON object.

Your role:
- Set the scene for a new adventure.
- Introduce the character ({name}, a {race} {class_name}) into the world.
- Describe the immediate surroundings and the starting situation.
- Establish a hook or initial goal that fits the character's class/race or the custom prompt.
- If a custom prompt is provided, use it to shape the world setting and tone.
- Keep the narrative engaging and descriptive (2-4 paragraphs).

You will receive:
1. Character details (Name, Race, Class)
2. Optional custom prompt

OUTPUT FORMAT (DungeonMasterOutcome JSON Schema):
{schema_json}

Remember: Output ONLY valid JSON matching this schema."""

        # Build user prompt
        user_prompt_parts = [
            f"CHARACTER: {name} ({race} {class_name})",
        ]
        
        if custom_prompt:
            user_prompt_parts.append(f"CUSTOM SETTING/PROMPT:\n{custom_prompt}")
            
        user_prompt_parts.append("""\nGenerate the opening scene and initial narrative for this character. 

CRITICAL REQUIREMENTS FOR CHARACTER CREATION:
1. LOCATION SYSTEM - You MUST establish the starting location:
   a) Create an ORIGIN POI using poi_intent with action='create':
      - name: Starting location name (e.g., 'The Crossroads Inn', 'Willowdale Village')
      - description: Brief description of this origin point
      - reference_tags: Tags like ['origin', 'starting_location', 'town']
   
   b) Set location using location_intent with ALL THREE FIELDS:
      - location_id: ID matching the POI (e.g., 'inn:crossroads', 'town:willowdale')
      - location_display_name: Full name matching the POI (e.g., 'The Crossroads Inn', 'Willowdale Village')
      - minor_location: REQUIRED - Precise position within the POI (e.g., 'at the entrance', 'in the common room', 'standing in the town square')
      - action: 'update_minor' (setting location)

2. LOCATION TRACKING PRINCIPLE:
   - Always set location_id and location_display_name when character is at a named location
   - Always update minor_location to show exact position
   - This ensures the character's location is properly stored and tracked
   - Start the character IN the origin POI you create

3. quest_intent and combat_intent should be 'none' for character creation.""")
        
        user_prompt = "\n".join(user_prompt_parts)
        
        return (intro_system_instructions, user_prompt)

    def _serialize_context(self, context: JourneyLogContext) -> str:
        """Serialize game context into a readable format for the LLM.
        
        Args:
            context: Character context from journey-log
            
        Returns:
            Formatted context string
        """
        sections = []

        # Adventure Prompt / World Setting (if provided)
        if context.adventure_prompt:
            sections.append(f"WORLD SETTING / ADVENTURE PROMPT:\n{context.adventure_prompt}")

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
        lines = []
        lines.append(f"  {len(memory_sparks)} previously discovered location(s):")
        
        # Sort by timestamp_discovered descending (newest first) for deterministic order
        # POIs without timestamps sort last (using empty string as minimum timestamp)
        # then by name for stable ordering
        sorted_sparks = sorted(
            memory_sparks,
            key=lambda poi: (
                poi.get("timestamp_discovered") or "",  # Empty string sorts last in reverse
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
        
        lines.append("\n  Note: Start new quests (immediately active) only if marked as ALLOWED above.")
        lines.append("  If a quest IS active, focus on ADVANCING it when player actions align with objectives.")
        lines.append("  POI Creation: ALWAYS ALLOWED - Create POIs whenever narratively appropriate.")
        
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
