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
    """
    
    def __init__(self):
        """Initialize outcome parser."""
        self.schema_version = OUTCOME_VERSION
    
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
