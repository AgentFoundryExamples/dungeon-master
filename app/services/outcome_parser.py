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
"""Parser for LLM responses with validation and fallback behavior.

This module provides defensive parsing of LLM outputs against the
DungeonMasterOutcome schema. It logs detailed validation errors while
ensuring narrative text is always preserved for persistence.
"""

import json
import re
from typing import Optional, Tuple, List
from dataclasses import dataclass
from pydantic import ValidationError

from app.models import (
    DungeonMasterOutcome,
    IntentsBlock,
    QuestIntent,
    CombatIntent,
    POIIntent,
    MetaIntent,
    OUTCOME_VERSION
)
from app.logging import StructuredLogger, redact_secrets

logger = StructuredLogger(__name__)

# Maximum payload size to log (to prevent log flooding and secret leakage)
MAX_PAYLOAD_LOG_LENGTH = 500


@dataclass
class ParsedOutcome:
    """Result of parsing an LLM response.
    
    Contains both the validated outcome (if successful) and a fallback
    narrative that can always be used for persistence.
    
    Attributes:
        outcome: Validated DungeonMasterOutcome if parsing succeeded, None otherwise
        narrative: The narrative text extracted from the response (always available)
        is_valid: Whether the response passed validation
        error_type: Type of error if parsing failed (e.g., "json_decode", "validation")
        error_details: List of specific validation errors if any
    """
    outcome: Optional[DungeonMasterOutcome]
    narrative: str
    is_valid: bool
    error_type: Optional[str] = None
    error_details: Optional[List[str]] = None


class OutcomeParser:
    """Parser for LLM responses with defensive validation and fallback.
    
    This parser:
    - Attempts to parse JSON and validate against DungeonMasterOutcome
    - Logs detailed errors with schema version and truncated payloads
    - Always extracts narrative text as fallback
    - Returns ParsedOutcome with both typed object and raw narrative
    - Tracks metrics for schema conformance rate
    - Normalizes QuestIntent with deterministic fallbacks
    """
    
    def __init__(self):
        """Initialize outcome parser."""
        self.schema_version = OUTCOME_VERSION
    
    def normalize_poi_intent(
        self,
        poi_intent: Optional[POIIntent],
        policy_triggered: bool = False,
        location_name: Optional[str] = None
    ) -> Optional[POIIntent]:
        """Normalize POIIntent with deterministic fallbacks for missing fields.
        
        When the policy engine triggers a POI opportunity but the LLM intent
        is missing or incomplete, this method provides deterministic fallback
        values to ensure a valid POI can still be created.
        
        Fallback rules:
        - If poi_intent is None and policy_triggered=True, create minimal "create" intent
        - If name is missing and action="create", use location_name or generic fallback
        - If description is missing and action="create", provide generic fallback
        - Trim name to max 200 characters, description to max 2000 characters
        
        Note: The action field is validated by Pydantic as a Literal type, so
        invalid values cannot reach this method.
        
        Args:
            poi_intent: POIIntent from LLM (may be None or incomplete)
            policy_triggered: Whether policy engine triggered POI opportunity
            location_name: Optional location name from context for fallback
            
        Returns:
            Normalized POIIntent with fallbacks applied, or None if not applicable
        """
        # If no intent and policy didn't trigger, nothing to normalize
        if poi_intent is None and not policy_triggered:
            return None
        
        # If no intent but policy triggered, create minimal create intent
        if poi_intent is None and policy_triggered:
            fallback_name = location_name if location_name else "A Notable Location"
            logger.info(
                "POI policy triggered but no LLM intent - using fallback",
                action="create",
                fallback_name=fallback_name
            )
            return POIIntent(
                action="create",
                name=fallback_name,
                description="An interesting location worth remembering.",
                reference_tags=[]
            )
        
        # Get validated action (Pydantic ensures it's valid)
        action = poi_intent.action
        
        # If action is "none", no normalization needed
        if action == "none":
            return poi_intent
        
        # If action is "reference", minimal normalization (just name)
        if action == "reference":
            name = poi_intent.name
            if not name or not isinstance(name, str) or len(name.strip()) == 0:
                # Reference actions need a name - if missing, use fallback
                fallback_name = location_name if location_name else "Unknown Location"
                logger.info("POI reference missing name - using fallback", fallback_name=fallback_name)
                return POIIntent(
                    action="reference",
                    name=fallback_name,
                    description=poi_intent.description,
                    reference_tags=poi_intent.reference_tags
                )
            # Trim name if too long
            if len(name) > 200:
                logger.info("POI reference name too long - trimming", original_length=len(name))
                name = name[:200]
            return POIIntent(
                action="reference",
                name=name,
                description=poi_intent.description,
                reference_tags=poi_intent.reference_tags
            )
        
        # Normalize "create" action fields
        if action == "create":
            name = poi_intent.name
            description = poi_intent.description
            reference_tags = poi_intent.reference_tags
            
            # Apply fallbacks for missing/invalid name
            if not name or not isinstance(name, str) or len(name.strip()) == 0:
                # Try location name first, then generic fallback
                fallback_name = location_name if location_name else "A Notable Location"
                logger.info("POI create missing name - using fallback", fallback_name=fallback_name)
                name = fallback_name
            
            # Trim name if too long (max 200 characters per journey-log spec)
            if len(name) > 200:
                logger.info("POI create name too long - trimming", original_length=len(name))
                name = name[:200]
            
            # Apply fallbacks for missing/invalid description
            if not description or not isinstance(description, str) or len(description.strip()) == 0:
                logger.info("POI create missing description - using fallback")
                description = "An interesting location worth remembering."
            
            # Trim description if too long (max 2000 characters per journey-log spec)
            if len(description) > 2000:
                logger.info("POI create description too long - trimming", original_length=len(description))
                description = description[:2000]
            
            # Normalize reference_tags (ensure list)
            if reference_tags is None:
                reference_tags = []
                logger.debug("POI create missing tags - using empty list")
            elif not isinstance(reference_tags, list):
                logger.warning("POI create tags was non-list, using empty list", original_type=type(poi_intent.reference_tags).__name__)
                reference_tags = []
            
            return POIIntent(
                action="create",
                name=name,
                description=description,
                reference_tags=reference_tags
            )
        
        # For any other action, return as-is
        return poi_intent
    
    def normalize_quest_intent(
        self,
        quest_intent: Optional[QuestIntent],
        policy_triggered: bool = False
    ) -> Optional[QuestIntent]:
        """Normalize QuestIntent with deterministic fallbacks for missing fields.
        
        When the policy engine triggers a quest opportunity but the LLM intent
        is missing or incomplete, this method provides deterministic fallback
        values to ensure a valid quest can still be offered.
        
        Fallback rules:
        - If quest_intent is None and policy_triggered=True, create minimal "offer" intent
        - If title is missing and action="offer", provide generic fallback title
        - If summary is missing and action="offer", provide generic fallback summary
        - If details is missing and action="offer", provide empty dict
        
        Note: The action field is validated by Pydantic as a Literal type, so
        invalid values cannot reach this method.
        
        Args:
            quest_intent: QuestIntent from LLM (may be None or incomplete)
            policy_triggered: Whether policy engine triggered quest opportunity
            
        Returns:
            Normalized QuestIntent with fallbacks applied, or None if not applicable
        """
        # If no intent and policy didn't trigger, nothing to normalize
        if quest_intent is None and not policy_triggered:
            return None
        
        # If no intent but policy triggered, create minimal offer intent
        if quest_intent is None and policy_triggered:
            logger.info(
                "Quest policy triggered but no LLM intent - using fallback",
                action="offer"
            )
            return QuestIntent(
                action="offer",
                quest_title="A New Opportunity",
                quest_summary="An opportunity for adventure presents itself.",
                quest_details={}
            )
        
        # Get validated action (Pydantic ensures it's valid)
        action = quest_intent.action
        
        # If action is "none", no normalization needed
        if action == "none":
            return quest_intent
        
        # Normalize "offer" action fields
        if action == "offer":
            title = quest_intent.quest_title
            summary = quest_intent.quest_summary
            details = quest_intent.quest_details
            
            # Apply fallbacks for missing/invalid fields with type checking
            # Convert to string if possible, otherwise use fallback
            if not title or not isinstance(title, str) or len(title.strip()) == 0:
                # Try to convert to string if it's not None
                if title is not None and not isinstance(title, str):
                    try:
                        title = str(title)
                        if len(title.strip()) == 0:
                            title = "A New Opportunity"
                            logger.info("Quest offer title was non-string empty, using fallback")
                        else:
                            logger.info("Quest offer title was non-string, converted to string", original_type=type(quest_intent.quest_title).__name__)
                    except Exception:
                        title = "A New Opportunity"
                        logger.warning("Quest offer title type conversion failed, using fallback", original_type=type(quest_intent.quest_title).__name__)
                else:
                    title = "A New Opportunity"
                    logger.info("Quest offer missing title - using fallback")
            
            if not summary or not isinstance(summary, str) or len(summary.strip()) == 0:
                # Try to convert to string if it's not None
                if summary is not None and not isinstance(summary, str):
                    try:
                        summary = str(summary)
                        if len(summary.strip()) == 0:
                            summary = "An opportunity for adventure presents itself."
                            logger.info("Quest offer summary was non-string empty, using fallback")
                        else:
                            logger.info("Quest offer summary was non-string, converted to string", original_type=type(quest_intent.quest_summary).__name__)
                    except Exception:
                        summary = "An opportunity for adventure presents itself."
                        logger.warning("Quest offer summary type conversion failed, using fallback", original_type=type(quest_intent.quest_summary).__name__)
                else:
                    summary = "An opportunity for adventure presents itself."
                    logger.info("Quest offer missing summary - using fallback")
            
            if details is None:
                details = {}
                logger.debug("Quest offer missing details - using empty dict")
            elif not isinstance(details, dict):
                logger.warning("Quest offer details was non-dict, using empty dict", original_type=type(quest_intent.quest_details).__name__)
                details = {}
            
            return QuestIntent(
                action="offer",
                quest_title=title,
                quest_summary=summary,
                quest_details=details
            )
        
        # For "complete" and "abandon" actions, return as-is
        return quest_intent
    
    def parse(
        self,
        response_text: str,
        trace_id: Optional[str] = None
    ) -> ParsedOutcome:
        """Parse LLM response text into DungeonMasterOutcome with fallback.
        
        Attempts to:
        1. Parse response as JSON
        2. Validate against DungeonMasterOutcome schema
        3. Extract narrative text
        
        On any failure:
        - Logs detailed error with schema version, truncated payload, error list
        - Attempts to extract narrative from partial JSON
        - Falls back to raw response text as narrative
        - Returns ParsedOutcome with is_valid=False but narrative present
        
        Args:
            response_text: Raw text response from LLM
            trace_id: Optional trace ID for correlation
            
        Returns:
            ParsedOutcome with outcome (if valid) and narrative (always present)
        """
        # Truncate payload for logging to prevent secrets leakage
        truncated_payload = self._truncate_for_log(response_text)
        
        # Try to parse JSON
        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            # JSON parsing failed - use raw text as narrative fallback
            error_msg = f"JSON decode error at line {e.lineno}, column {e.colno}: {e.msg}"
            
            logger.error(
                "Failed to parse LLM response as JSON",
                schema_version=self.schema_version,
                error_type="json_decode_error",
                error_details=error_msg,
                payload_preview=truncated_payload,
                trace_id=trace_id
            )
            
            # Attempt to extract any text that looks like narrative from raw response
            fallback_narrative = self._extract_fallback_narrative(response_text)
            
            return ParsedOutcome(
                outcome=None,
                narrative=fallback_narrative,
                is_valid=False,
                error_type="json_decode_error",
                error_details=[error_msg]
            )
        
        # Try to validate against DungeonMasterOutcome schema
        try:
            outcome = DungeonMasterOutcome.model_validate(response_data)
            
            # Successful validation
            logger.info(
                "Successfully parsed and validated LLM response",
                schema_version=self.schema_version,
                narrative_length=len(outcome.narrative),
                has_quest_intent=outcome.intents.quest_intent is not None,
                has_combat_intent=outcome.intents.combat_intent is not None,
                has_poi_intent=outcome.intents.poi_intent is not None,
                has_meta_intent=outcome.intents.meta is not None,
                trace_id=trace_id
            )
            
            return ParsedOutcome(
                outcome=outcome,
                narrative=outcome.narrative,
                is_valid=True
            )
            
        except ValidationError as e:
            # Validation failed - extract narrative from partial JSON and log errors
            error_list = self._extract_validation_errors(e)
            
            logger.error(
                "LLM response failed schema validation",
                schema_version=self.schema_version,
                error_type="validation_error",
                error_count=len(error_list),
                error_details=error_list,
                payload_preview=truncated_payload,
                trace_id=trace_id
            )
            
            # Try to extract narrative from partial JSON
            fallback_narrative = self._extract_narrative_from_json(response_data, response_text)
            
            return ParsedOutcome(
                outcome=None,
                narrative=fallback_narrative,
                is_valid=False,
                error_type="validation_error",
                error_details=error_list
            )
        
        except Exception as e:
            # Unexpected error during validation
            error_list = [f"{type(e).__name__}: {str(e)}"]
            
            logger.error(
                "Unexpected error during LLM response validation",
                schema_version=self.schema_version,
                error_type="unexpected_error",
                error_details=error_list,
                payload_preview=truncated_payload,
                trace_id=trace_id
            )
            
            # Try to extract narrative from partial JSON
            fallback_narrative = self._extract_narrative_from_json(response_data, response_text)
            
            return ParsedOutcome(
                outcome=None,
                narrative=fallback_narrative,
                is_valid=False,
                error_type="unexpected_error",
                error_details=error_list
            )
    
    def _truncate_for_log(self, text: str) -> str:
        """Truncate text for safe logging.
        
        Prevents log flooding and reduces risk of logging secrets.
        
        Args:
            text: Text to truncate
            
        Returns:
            Truncated and redacted text
        """
        # First redact any secrets
        redacted = redact_secrets(text)
        
        # Then truncate
        if len(redacted) > MAX_PAYLOAD_LOG_LENGTH:
            return redacted[:MAX_PAYLOAD_LOG_LENGTH] + "... (truncated)"
        
        return redacted
    
    def _extract_validation_errors(self, error: ValidationError) -> List[str]:
        """Extract human-readable error messages from ValidationError.
        
        Args:
            error: Pydantic ValidationError
            
        Returns:
            List of error descriptions
        """
        error_list = []
        for err in error.errors():
            # Format: "field.path: error_type - message"
            field_path = ".".join(str(loc) for loc in err["loc"])
            error_type = err["type"]
            message = err["msg"]
            error_list.append(f"{field_path}: {error_type} - {message}")
        
        return error_list
    
    def _extract_narrative_from_json(
        self,
        json_data: dict,
        raw_text: str
    ) -> str:
        """Extract narrative text from partially valid JSON.
        
        Attempts to find the narrative field even if the full structure
        is invalid. Falls back to raw text if narrative cannot be found.
        
        Args:
            json_data: Parsed JSON dictionary (may be partially valid)
            raw_text: Original raw response text
            
        Returns:
            Narrative text or fallback
        """
        # Try to get narrative field directly
        if isinstance(json_data, dict):
            narrative = json_data.get("narrative")
            if narrative and isinstance(narrative, str) and len(narrative) > 0:
                return narrative
        
        # Fallback to raw text extraction
        return self._extract_fallback_narrative(raw_text)
    
    def _extract_fallback_narrative(self, raw_text: str) -> str:
        """Extract narrative text from raw response as last resort.
        
        This is used when JSON parsing completely fails. It attempts to
        find any prose text in the response that could serve as narrative.
        
        Args:
            raw_text: Raw response text
            
        Returns:
            Best-effort narrative text
        """
        # Clean up the text
        text = raw_text.strip()
        
        # If the text looks like it might contain JSON, try to extract narrative field
        if "{" in text and "narrative" in text:
            # Try to find text after "narrative": or "narrative":"
            match = re.search(r'"narrative"\s*:\s*"([^"]+)"', text)
            if match:
                return match.group(1)
        
        # If text is too short or looks like an error, return a safe default
        if len(text) < 10 or text.startswith("Error") or text.startswith("{"):
            return "[Unable to generate narrative - LLM response was invalid]"
        
        # Otherwise, use the raw text as narrative (truncate if too long)
        max_narrative_length = 5000
        if len(text) > max_narrative_length:
            return text[:max_narrative_length] + "..."
        
        return text
