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
"""Turn orchestrator for deterministic subsystem action execution.

This module provides the TurnOrchestrator class that enforces the
deterministic sequence for turn processing:
1. Compute policy decisions
2. Call LLM
3. Parse intents
4. Map to subsystem actions (with policy gating)
5. Apply journey-log writes (quest → combat → POI → narrative)
6. Return response with summary

The orchestrator ensures:
- Deterministic write order
- Policy gating for all subsystem actions
- Context state validation
- Structured error logging
- Failure handling (continue narrative, no retry for destructive calls)
- Dry-run/simulation mode support
"""

from typing import Optional
from dataclasses import dataclass

from app.models import (
    JourneyLogContext,
    PolicyHints,
    IntentsBlock,
    TurnSubsystemSummary,
    SubsystemActionType,
    QuestChangeType,
    CombatChangeType,
    POIChangeType,
)
from app.services.policy_engine import PolicyEngine
from app.services.llm_client import LLMClient
from app.services.outcome_parser import ParsedOutcome
from app.services.journey_log_client import (
    JourneyLogClient,
    JourneyLogClientError,
)
from app.prompting.prompt_builder import PromptBuilder
from app.logging import StructuredLogger

logger = StructuredLogger(__name__)


@dataclass
class SubsystemAction:
    """Represents a derived subsystem action to execute.
    
    Attributes:
        subsystem: Name of the subsystem (quest/combat/poi)
        action_type: Type of action (offer/start/create/etc)
        intent_data: Optional data from LLM intent
        should_execute: Whether action should be executed (after policy gating)
    """
    subsystem: str
    action_type: str
    intent_data: Optional[dict]
    should_execute: bool


class TurnOrchestrator:
    """Orchestrator for deterministic turn processing.
    
    The TurnOrchestrator enforces a strict sequence of operations for each
    turn, ensuring deterministic behavior and consistent logging of all
    subsystem changes.
    
    Key Responsibilities:
    - Enforce policy → LLM → parse → derive → execute sequence
    - Gate subsystem actions based on policy decisions and context state
    - Execute writes in deterministic order (quest → combat → POI → narrative)
    - Log all operations for analytics
    - Handle failures gracefully (continue narrative, no retry for DELETE)
    - Support dry-run mode for simulations
    
    The orchestrator does NOT make GET calls for missing state - it relies
    on the context provided in the request.
    """
    
    def __init__(
        self,
        policy_engine: PolicyEngine,
        llm_client: LLMClient,
        journey_log_client: JourneyLogClient,
        prompt_builder: PromptBuilder
    ):
        """Initialize the turn orchestrator.
        
        Args:
            policy_engine: PolicyEngine for quest/POI trigger decisions
            llm_client: LLMClient for narrative generation
            journey_log_client: JourneyLogClient for subsystem writes
            prompt_builder: PromptBuilder for prompt construction
        """
        self.policy_engine = policy_engine
        self.llm_client = llm_client
        self.journey_log_client = journey_log_client
        self.prompt_builder = prompt_builder
        # Import and instantiate parser once to avoid repeated instantiation
        from app.services.outcome_parser import OutcomeParser
        self.outcome_parser = OutcomeParser()
    
    async def orchestrate_turn(
        self,
        character_id: str,
        user_action: str,
        context: JourneyLogContext,
        trace_id: Optional[str] = None,
        dry_run: bool = False
    ) -> tuple[str, Optional[IntentsBlock], TurnSubsystemSummary]:
        """Orchestrate a complete turn with deterministic sequencing.
        
        Enforces the sequence:
        1. Compute policy decisions
        2. Call LLM
        3. Parse intents
        4. Derive subsystem actions (with policy gating)
        5. Execute writes in order (quest → combat → POI → narrative)
        6. Build summary
        7. Return (narrative, intents, summary)
        
        Args:
            character_id: Character UUID
            user_action: Player's action text
            context: Character context from journey-log
            trace_id: Optional trace ID for correlation
            dry_run: If True, skip actual writes but produce summary
            
        Returns:
            Tuple of (narrative, intents, subsystem_summary)
        """
        logger.info("Starting turn orchestration", character_id=character_id, dry_run=dry_run)
        
        summary = TurnSubsystemSummary()
        
        # Step 1: Compute policy decisions
        logger.debug("Step 1: Computing policy decisions")
        quest_decision = self.policy_engine.evaluate_quest_trigger(
            character_id=character_id,
            turns_since_last_quest=context.policy_state.turns_since_last_quest,
            has_active_quest=context.policy_state.has_active_quest
        )
        
        poi_decision = self.policy_engine.evaluate_poi_trigger(
            character_id=character_id,
            turns_since_last_poi=context.policy_state.turns_since_last_poi
        )
        
        policy_hints = PolicyHints(
            quest_trigger_decision=quest_decision,
            poi_trigger_decision=poi_decision
        )
        
        # Inject policy hints into context
        context.policy_hints = policy_hints
        
        logger.info(
            "Policy decisions evaluated",
            quest_eligible=quest_decision.eligible,
            quest_roll_passed=quest_decision.roll_passed,
            poi_eligible=poi_decision.eligible,
            poi_roll_passed=poi_decision.roll_passed
        )
        
        # Step 2: Build prompt and call LLM
        logger.debug("Step 2: Building prompt and calling LLM")
        system_instructions, user_prompt = self.prompt_builder.build_prompt(
            context=context,
            user_action=user_action
        )
        
        parsed_outcome: ParsedOutcome = await self.llm_client.generate_narrative(
            system_instructions=system_instructions,
            user_prompt=user_prompt,
            trace_id=trace_id
        )
        
        narrative = parsed_outcome.narrative
        intents = None
        if parsed_outcome.is_valid and parsed_outcome.outcome:
            intents = parsed_outcome.outcome.intents
        
        logger.info(
            "LLM generation complete",
            narrative_length=len(narrative),
            intents_valid=intents is not None
        )
        
        # Step 2b: Normalize quest intent with fallbacks
        if intents:
            normalized_quest = self.outcome_parser.normalize_quest_intent(
                quest_intent=intents.quest_intent,
                policy_triggered=quest_decision.roll_passed
            )
            if normalized_quest != intents.quest_intent:
                logger.info(
                    "Quest intent normalized",
                    original_action=intents.quest_intent.action if intents.quest_intent else "none",
                    normalized_action=normalized_quest.action if normalized_quest else "none"
                )
                # Update intents with normalized quest intent
                intents.quest_intent = normalized_quest
        
        # Step 3: Derive subsystem actions
        logger.debug("Step 3: Deriving subsystem actions from policy and intents")
        actions = self._derive_subsystem_actions(
            context=context,
            intents=intents,
            quest_decision=quest_decision,
            poi_decision=poi_decision
        )
        
        logger.info(
            "Subsystem actions derived",
            quest_action=actions["quest"].action_type if actions["quest"].should_execute else "none",
            combat_action=actions["combat"].action_type if actions["combat"].should_execute else "none",
            poi_action=actions["poi"].action_type if actions["poi"].should_execute else "none"
        )
        
        # Step 4: Execute writes in deterministic order
        logger.debug("Step 4: Executing subsystem writes")
        
        if not dry_run:
            # Quest writes (PUT/DELETE)
            if actions["quest"].should_execute:
                await self._execute_quest_action(
                    character_id=character_id,
                    action=actions["quest"],
                    summary=summary,
                    trace_id=trace_id
                )
            
            # Combat writes (PUT)
            if actions["combat"].should_execute:
                await self._execute_combat_action(
                    character_id=character_id,
                    action=actions["combat"],
                    summary=summary,
                    trace_id=trace_id
                )
            
            # POI writes (POST)
            if actions["poi"].should_execute:
                await self._execute_poi_action(
                    character_id=character_id,
                    action=actions["poi"],
                    summary=summary,
                    trace_id=trace_id
                )
            
            # Narrative write (POST) - always attempt
            await self._persist_narrative(
                character_id=character_id,
                user_action=user_action,
                narrative=narrative,
                summary=summary,
                trace_id=trace_id
            )
        else:
            # Dry-run mode: populate summary without executing
            logger.info("Dry-run mode: skipping actual writes")
            if actions["quest"].should_execute:
                summary.quest_change = SubsystemActionType(
                    action=actions["quest"].action_type,
                    success=True,
                    error=None
                )
            if actions["combat"].should_execute:
                summary.combat_change = SubsystemActionType(
                    action=actions["combat"].action_type,
                    success=True,
                    error=None
                )
            if actions["poi"].should_execute:
                summary.poi_created = SubsystemActionType(
                    action=actions["poi"].action_type,
                    success=True,
                    error=None
                )
            summary.narrative_persisted = True
        
        logger.info(
            "Turn orchestration complete",
            quest_change=summary.quest_change.action,
            combat_change=summary.combat_change.action,
            poi_change=summary.poi_created.action,
            narrative_persisted=summary.narrative_persisted
        )
        
        return narrative, intents, summary
    
    def _derive_subsystem_actions(
        self,
        context: JourneyLogContext,
        intents: Optional[IntentsBlock],
        quest_decision: "QuestTriggerDecision",
        poi_decision: "POITriggerDecision"
    ) -> dict[str, SubsystemAction]:
        """Derive subsystem actions from policy decisions and LLM intents.
        
        This method applies policy gating and context state validation to
        determine which subsystem actions should be executed:
        
        - Quest actions require: policy roll passed AND intent suggests action
          AND context state is valid (e.g., no active quest for "offer")
        - Combat actions require: intent suggests action AND context state is valid
        - POI actions require: policy roll passed AND intent suggests action
        
        Args:
            context: Character context with state information
            intents: Parsed intents from LLM (may be None if parsing failed)
            quest_decision: QuestTriggerDecision from policy engine
            poi_decision: POITriggerDecision from policy engine
            
        Returns:
            Dictionary mapping subsystem name to SubsystemAction
        """
        actions = {
            "quest": SubsystemAction("quest", "none", None, False),
            "combat": SubsystemAction("combat", "none", None, False),
            "poi": SubsystemAction("poi", "none", None, False),
        }
        
        # No intents - no actions (except narrative which is always attempted)
        if not intents:
            logger.debug("No valid intents - skipping subsystem actions")
            return actions
        
        # Derive quest action
        if intents.quest_intent and intents.quest_intent.action != "none":
            intent_action = intents.quest_intent.action
            
            # Gate by policy for "offer" action
            # Logic: BOTH policy roll AND context state must allow the action
            if intent_action == "offer":
                # Check policy roll first
                if not quest_decision.roll_passed:
                    # Policy denied - skip regardless of context state
                    logger.info("Quest offer skipped - policy roll failed")
                # Policy passed - now check context state
                elif context.policy_state.has_active_quest:
                    # Context state invalid (already has quest) - skip
                    logger.info("Quest offer skipped - already has active quest")
                else:
                    # Both policy AND context state allow - execute
                    actions["quest"] = SubsystemAction(
                        subsystem="quest",
                        action_type=intent_action,
                        intent_data={
                            "title": intents.quest_intent.quest_title,
                            "summary": intents.quest_intent.quest_summary,
                            "details": intents.quest_intent.quest_details,
                        },
                        should_execute=True
                    )
                    logger.debug("Quest offer action derived", title=intents.quest_intent.quest_title)
            
            # Other quest actions don't require policy roll, only context state
            elif intent_action in ["complete", "abandon"]:
                # Validation: must have active quest
                if context.policy_state.has_active_quest:
                    actions["quest"] = SubsystemAction(
                        subsystem="quest",
                        action_type=intent_action,
                        intent_data=None,
                        should_execute=True
                    )
                    logger.debug(f"Quest {intent_action} action derived")
                else:
                    logger.info(f"Quest {intent_action} skipped - no active quest")
        
        # Derive combat action
        if intents.combat_intent and intents.combat_intent.action != "none":
            intent_action = intents.combat_intent.action
            
            # Validation based on action type
            valid = False
            if intent_action == "start":
                # Can only start if not already in combat
                valid = not context.policy_state.combat_active
                if not valid:
                    logger.info("Combat start skipped - already in combat")
            elif intent_action in ["continue", "end"]:
                # Can only continue/end if in combat
                valid = context.policy_state.combat_active
                if not valid:
                    logger.info(f"Combat {intent_action} skipped - not in combat")
            else:
                valid = True  # Unknown action, let it through for now
            
            if valid:
                actions["combat"] = SubsystemAction(
                    subsystem="combat",
                    action_type=intent_action,
                    intent_data={
                        "enemies": intents.combat_intent.enemies,
                        "notes": intents.combat_intent.combat_notes,
                    } if intent_action == "start" else None,
                    should_execute=True
                )
                logger.debug(f"Combat {intent_action} action derived")
        
        # Derive POI action
        if intents.poi_intent and intents.poi_intent.action != "none":
            intent_action = intents.poi_intent.action
            
            # Gate by policy for "create" action
            if intent_action == "create":
                if poi_decision.roll_passed:
                    actions["poi"] = SubsystemAction(
                        subsystem="poi",
                        action_type=intent_action,
                        intent_data={
                            "name": intents.poi_intent.name,
                            "description": intents.poi_intent.description,
                            "reference_tags": intents.poi_intent.reference_tags,
                        },
                        should_execute=True
                    )
                    logger.debug("POI create action derived", name=intents.poi_intent.name)
                else:
                    logger.info("POI create skipped - policy roll failed")
            
            # Reference action doesn't require policy roll
            elif intent_action == "reference":
                actions["poi"] = SubsystemAction(
                    subsystem="poi",
                    action_type=intent_action,
                    intent_data={
                        "name": intents.poi_intent.name,
                        "reference_tags": intents.poi_intent.reference_tags,
                    },
                    should_execute=True
                )
                logger.debug("POI reference action derived", name=intents.poi_intent.name)
        
        return actions
    
    async def _execute_quest_action(
        self,
        character_id: str,
        action: SubsystemAction,
        summary: TurnSubsystemSummary,
        trace_id: Optional[str]
    ) -> None:
        """Execute quest subsystem action.
        
        Handles: PUT (offer), DELETE (complete/abandon)
        On failure: logs error, continues, updates summary
        
        Error Handling:
        - Catches JourneyLogClientError and all subclasses (NotFound, Timeout)
        - Continues execution without retrying (including for DELETE operations)
        - Logs structured error and updates summary with failure details
        - HTTP 409 conflicts are logged and marked as skipped without crash
        - This allows narrative to complete even if quest write fails
        
        Args:
            character_id: Character UUID
            action: SubsystemAction to execute
            summary: TurnSubsystemSummary to update
            trace_id: Optional trace ID
        """
        logger.info(f"Executing quest {action.action_type} action", character_id=character_id)
        
        try:
            if action.action_type == "offer":
                # Build payload matching journey-log Quest schema
                # Map from intent_data {title, summary, details} to API {name, description, requirements, rewards, completion_state, updated_at}
                from datetime import datetime, timezone
                
                # Parser already applied fallbacks, so these should always be present
                title = action.intent_data["title"]
                summary_text = action.intent_data["summary"]
                details = action.intent_data["details"]
                
                # Validate and extract requirements (must be list of strings)
                requirements = details.get("requirements", [])
                if not isinstance(requirements, list):
                    logger.warning("Invalid requirements type, using empty list", type=type(requirements).__name__)
                    requirements = []
                
                # Validate and extract reward items (must be list)
                reward_items = details.get("reward_items", [])
                if not isinstance(reward_items, list):
                    logger.warning("Invalid reward_items type, using empty list", type=type(reward_items).__name__)
                    reward_items = []
                
                # Validate and extract reward currency (must be dict)
                reward_currency = details.get("reward_currency", {})
                if not isinstance(reward_currency, dict):
                    logger.warning("Invalid reward_currency type, using empty dict", type=type(reward_currency).__name__)
                    reward_currency = {}
                
                # Validate and extract reward experience (must be int or None)
                reward_experience = details.get("reward_experience")
                if reward_experience is not None and not isinstance(reward_experience, int):
                    logger.warning("Invalid reward_experience type, setting to None", type=type(reward_experience).__name__)
                    reward_experience = None
                
                quest_payload = {
                    "name": title,
                    "description": summary_text,
                    "requirements": requirements,
                    "rewards": {
                        "items": reward_items,
                        "currency": reward_currency,
                        "experience": reward_experience
                    },
                    "completion_state": "not_started",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                
                logger.debug(
                    "Built quest payload",
                    quest_name=quest_payload["name"],
                    quest_description_length=len(quest_payload["description"])
                )
                
                await self.journey_log_client.put_quest(
                    character_id=character_id,
                    quest_data=quest_payload,
                    trace_id=trace_id
                )
                summary.quest_change = SubsystemActionType(
                    action="offered",
                    success=True,
                    error=None
                )
                logger.info("Quest offer successful", quest_name=title)
            
            elif action.action_type in ["complete", "abandon"]:
                # DELETE operation - no retry on failure per design
                await self.journey_log_client.delete_quest(
                    character_id=character_id,
                    trace_id=trace_id
                )
                summary.quest_change = SubsystemActionType(
                    action="completed" if action.action_type == "complete" else "abandoned",
                    success=True,
                    error=None
                )
                logger.info(f"Quest {action.action_type} successful")
        
        except JourneyLogClientError as e:
            # Check for HTTP 409 Conflict using status_code attribute
            if getattr(e, 'status_code', None) == 409:
                # HTTP 409: Active quest already exists
                logger.warning(
                    "Quest PUT skipped - active quest already exists (HTTP 409)",
                    action=action.action_type,
                    error=str(e)
                )
                summary.quest_change = SubsystemActionType(
                    action="skipped",
                    success=False,
                    error="Active quest already exists (HTTP 409 Conflict)"
                )
            else:
                # Other journey-log errors: NotFound, Timeout, Client errors
                # Continue without retry (including for DELETE operations)
                error_msg = f"Quest {action.action_type} failed: {str(e)}"
                logger.error(
                    "Quest action failed - continuing with narrative",
                    action=action.action_type,
                    error=str(e),
                    is_destructive=action.action_type in ["complete", "abandon"]
                )
                summary.quest_change = SubsystemActionType(
                    action=action.action_type,
                    success=False,
                    error=error_msg
                )
    
    async def _execute_combat_action(
        self,
        character_id: str,
        action: SubsystemAction,
        summary: TurnSubsystemSummary,
        trace_id: Optional[str]
    ) -> None:
        """Execute combat subsystem action.
        
        Handles: PUT (start/continue/end)
        On failure: logs error, continues, updates summary
        
        Error Handling:
        - Catches JourneyLogClientError and all subclasses (NotFound, Timeout)
        - Continues execution without retrying
        - Logs structured error and updates summary with failure details
        
        Args:
            character_id: Character UUID
            action: SubsystemAction to execute
            summary: TurnSubsystemSummary to update
            trace_id: Optional trace ID
        """
        logger.info(f"Executing combat {action.action_type} action", character_id=character_id)
        
        try:
            await self.journey_log_client.put_combat(
                character_id=character_id,
                combat_data=action.intent_data,
                action_type=action.action_type,
                trace_id=trace_id
            )
            summary.combat_change = SubsystemActionType(
                action=action.action_type,
                success=True,
                error=None
            )
            logger.info(f"Combat {action.action_type} successful")
        
        except JourneyLogClientError as e:
            # Catches all journey-log errors: NotFound, Timeout, Client errors
            error_msg = f"Combat {action.action_type} failed: {str(e)}"
            logger.error(
                "Combat action failed - continuing with narrative",
                action=action.action_type,
                error=str(e)
            )
            summary.combat_change = SubsystemActionType(
                action=action.action_type,
                success=False,
                error=error_msg
            )
    
    async def _execute_poi_action(
        self,
        character_id: str,
        action: SubsystemAction,
        summary: TurnSubsystemSummary,
        trace_id: Optional[str]
    ) -> None:
        """Execute POI subsystem action.
        
        Handles: POST (create/reference)
        On failure: logs error, continues, updates summary
        
        Error Handling:
        - Catches JourneyLogClientError and all subclasses (NotFound, Timeout)
        - Continues execution without retrying
        - Logs structured error and updates summary with failure details
        
        Args:
            character_id: Character UUID
            action: SubsystemAction to execute
            summary: TurnSubsystemSummary to update
            trace_id: Optional trace ID
        """
        logger.info(f"Executing POI {action.action_type} action", character_id=character_id)
        
        try:
            await self.journey_log_client.post_poi(
                character_id=character_id,
                poi_data=action.intent_data,
                action_type=action.action_type,
                trace_id=trace_id
            )
            summary.poi_created = SubsystemActionType(
                action=action.action_type,
                success=True,
                error=None
            )
            logger.info(f"POI {action.action_type} successful")
        
        except JourneyLogClientError as e:
            # Catches all journey-log errors: NotFound, Timeout, Client errors
            error_msg = f"POI {action.action_type} failed: {str(e)}"
            logger.error(
                "POI action failed - continuing with narrative",
                action=action.action_type,
                error=str(e)
            )
            summary.poi_created = SubsystemActionType(
                action=action.action_type,
                success=False,
                error=error_msg
            )
    
    async def _persist_narrative(
        self,
        character_id: str,
        user_action: str,
        narrative: str,
        summary: TurnSubsystemSummary,
        trace_id: Optional[str]
    ) -> None:
        """Persist narrative to journey-log.
        
        This is always attempted, even if subsystem actions failed.
        On failure: logs error, updates summary (but doesn't raise)
        
        Error Handling:
        - Catches JourneyLogClientError and all subclasses (NotFound, Timeout)
        - Does not raise exception - narrative failure is captured in summary
        - This allows the turn to complete with a response even if persistence fails
        
        Args:
            character_id: Character UUID
            user_action: Player's action text
            narrative: Generated narrative text
            summary: TurnSubsystemSummary to update
            trace_id: Optional trace ID
        """
        logger.info("Persisting narrative to journey-log", character_id=character_id)
        
        try:
            await self.journey_log_client.persist_narrative(
                character_id=character_id,
                user_action=user_action,
                narrative=narrative,
                trace_id=trace_id
            )
            summary.narrative_persisted = True
            logger.info("Narrative persistence successful")
        
        except JourneyLogClientError as e:
            error_msg = f"Narrative persistence failed: {str(e)}"
            logger.error(
                "Narrative persistence failed",
                error=str(e)
            )
            summary.narrative_persisted = False
            summary.narrative_error = error_msg
