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
"""Journey-log service client for context retrieval and narrative persistence."""

import time
import asyncio
from typing import Optional, Any
from datetime import datetime
from httpx import AsyncClient, HTTPStatusError, TimeoutException
from app.models import JourneyLogContext, PolicyState
from app.logging import StructuredLogger, redact_secrets, get_turn_id
from app.metrics import get_metrics_collector

logger = StructuredLogger(__name__)


class JourneyLogClientError(Exception):
    """Base exception for journey-log client errors.
    
    Attributes:
        status_code: HTTP status code if available, None otherwise
    """
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class JourneyLogNotFoundError(JourneyLogClientError):
    """Raised when character is not found (404)."""
    pass


class JourneyLogTimeoutError(JourneyLogClientError):
    """Raised when journey-log request times out."""
    pass


class JourneyLogClient:
    """Client for interacting with the journey-log service.
    
    This client handles:
    - Fetching character context for LLM prompting
    - Persisting narrative turns after LLM generation
    - Error handling and retries for transient failures
    """

    def __init__(
        self,
        base_url: str,
        http_client: AsyncClient,
        timeout: int = 30,
        recent_n_default: int = 20,
        max_retries: int = 3,
        retry_delay_base: float = 0.5,
        retry_delay_max: float = 10.0
    ):
        """Initialize journey-log client.
        
        Args:
            base_url: Base URL of journey-log service (e.g., http://localhost:8000)
            http_client: HTTP client for making requests
            timeout: Request timeout in seconds
            recent_n_default: Default number of recent narrative turns to fetch
            max_retries: Maximum retry attempts for GET requests (POST/PUT/DELETE never retried)
            retry_delay_base: Base delay for exponential backoff (seconds)
            retry_delay_max: Maximum delay for exponential backoff (seconds)
        """
        self.base_url = base_url.rstrip('/')
        self.http_client = http_client
        self.timeout = timeout
        self.recent_n_default = recent_n_default
        self.max_retries = max_retries
        self.retry_delay_base = retry_delay_base
        self.retry_delay_max = retry_delay_max

        logger.info(
            f"Initialized JourneyLogClient with base_url={self.base_url}, "
            f"timeout={self.timeout}s, recent_n_default={self.recent_n_default}, "
            f"max_retries={self.max_retries}"
        )

    @staticmethod
    def _validate_timestamp(timestamp: Any, field_name: str) -> Optional[str]:
        """Validate that a value is a valid ISO 8601 timestamp string.
        
        Args:
            timestamp: Value to validate as ISO 8601 timestamp
            field_name: The name of the field for logging purposes
            
        Returns:
            The timestamp string if valid, otherwise None
        """
        if timestamp is None:
            return None
        if not isinstance(timestamp, str):
            logger.warning(
                f"Invalid type for {field_name}: {type(timestamp).__name__}, expected str. "
                f"Defaulting to None."
            )
            return None
        try:
            # Use fromisoformat for basic validation
            # Replace 'Z' with '+00:00' for compatibility
            datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return timestamp
        except (ValueError, TypeError) as e:
            logger.warning(
                f"Invalid ISO 8601 format for {field_name}: {timestamp}. "
                f"Defaulting to None. Error: {e}"
            )
            return None

    def _validate_turn_counter(self, value: Any, field_name: str) -> int:
        """Validate turn counter is a non-negative integer, defaulting to 0.
        
        Args:
            value: Value to validate as turn counter
            field_name: The name of the field for logging purposes
            
        Returns:
            The value if valid non-negative integer, otherwise 0
        """
        if not isinstance(value, int) or value < 0:
            logger.warning(
                f"Invalid {field_name} value: {value}, defaulting to 0"
            )
            return 0
        return value

    @staticmethod
    def _validate_optional_bool(value: Any, field_name: str) -> Optional[bool]:
        """Validate optional boolean flag value.
        
        Args:
            value: Value to validate as optional boolean
            field_name: The name of the field for logging purposes
            
        Returns:
            The value if it's None or bool, otherwise None
        """
        if value is None or isinstance(value, bool):
            return value
        
        logger.warning(
            f"Invalid type for boolean flag '{field_name}': {type(value).__name__}. "
            f"Value was '{value}'. Defaulting to None."
        )
        return None

    def _extract_policy_state(self, data: dict) -> PolicyState:
        """Extract policy-relevant state from journey-log response.
        
        This method parses the journey-log response to extract policy inputs
        for quest and POI trigger evaluation. It handles:
        - Quest presence and timestamps from quest field or additional_fields
        - POI timestamps from additional_fields (since journey-log may not track)
        - Combat active flag from combat envelope
        - Turn counters from additional_fields or defaults to 0
        - Player engagement flags from additional_fields
        
        **Authoritative Sources:**
        - has_active_quest: Derived from journey-log quest field (authoritative)
        - combat_active: Derived from journey-log combat.active field (authoritative)
        - last_quest_offered_at: DM-managed in additional_fields (interim until journey-log support)
        - last_poi_created_at: DM-managed in additional_fields (interim until journey-log support)
        - turns_since_last_quest: DM-managed in additional_fields (interim until journey-log support)
        - turns_since_last_poi: DM-managed in additional_fields (interim until journey-log support)
        - user_is_wandering: DM-managed in additional_fields (may move to journey-log)
        - requested_guidance: DM-managed in additional_fields (may move to journey-log)
        
        **Journey-Log Coordination Plan:**
        The DM service currently manages quest/POI timestamps and turn counters in
        additional_fields as a temporary storage solution. Future journey-log enhancements
        will provide first-class fields for:
        - Quest history timestamps (last_quest_offered_at, quest_completed_at)
        - POI creation timestamps (last_poi_created_at)
        - Turn counter tracking (turns_since_last_quest, turns_since_last_poi)
        
        When journey-log adds these fields, this method will prioritize reading from
        first-class fields while maintaining backward compatibility with additional_fields.
        
        Args:
            data: Raw journey-log response dictionary
            
        Returns:
            PolicyState with extracted and normalized values
        """
        # Extract additional_fields from player_state for DM-managed state
        player_state = data.get("player_state", {})
        additional_fields = player_state.get("additional_fields", {})
        
        # Extract quest state - prioritize explicit has_active_quest flag if present,
        # fall back to quest field presence for backward compatibility
        quest = data.get("quest")
        has_active_quest = data.get("has_active_quest", quest is not None)
        
        # Extract combat state
        combat_data = data.get("combat", {})
        combat_active = combat_data.get("active", False)
        
        # Extract and validate timestamps from additional_fields (DM-managed until journey-log supports)
        last_quest_offered_at = self._validate_timestamp(
            additional_fields.get("last_quest_offered_at"), "last_quest_offered_at"
        )
        last_poi_created_at = self._validate_timestamp(
            additional_fields.get("last_poi_created_at"), "last_poi_created_at"
        )
        
        # Extract and validate turn counters from additional_fields with safe defaults
        turns_since_last_quest = self._validate_turn_counter(
            additional_fields.get("turns_since_last_quest", 0), "turns_since_last_quest"
        )
        turns_since_last_poi = self._validate_turn_counter(
            additional_fields.get("turns_since_last_poi", 0), "turns_since_last_poi"
        )
        
        # Extract player engagement flags from additional_fields
        user_is_wandering = self._validate_optional_bool(
            additional_fields.get("user_is_wandering"), "user_is_wandering"
        )
        requested_guidance = self._validate_optional_bool(
            additional_fields.get("requested_guidance"), "requested_guidance"
        )
        
        return PolicyState(
            last_quest_offered_at=last_quest_offered_at,
            last_poi_created_at=last_poi_created_at,
            turns_since_last_quest=turns_since_last_quest,
            turns_since_last_poi=turns_since_last_poi,
            has_active_quest=has_active_quest,
            combat_active=combat_active,
            user_is_wandering=user_is_wandering,
            requested_guidance=requested_guidance
        )

    async def get_context(
        self,
        character_id: str,
        recent_n: Optional[int] = None,
        trace_id: Optional[str] = None
    ) -> JourneyLogContext:
        """Fetch character context for LLM prompting.
        
        Makes a GET request to /characters/{character_id}/context with:
        - recent_n: Number of recent narrative turns (default: 20)
        - include_pois: false (as specified in requirements)
        
        This method implements retry logic with exponential backoff for transient errors:
        - Retries: Timeout, server errors (500, 502, 503), connection errors
        - No retry: Not found (404), client errors (4xx except 429)
        
        Args:
            character_id: UUID of the character
            recent_n: Number of recent turns to fetch (defaults to recent_n_default)
            trace_id: Optional trace ID for request correlation
            
        Returns:
            JourneyLogContext with character state
            
        Raises:
            JourneyLogNotFoundError: If character not found (404)
            JourneyLogTimeoutError: If request times out after all retries
            JourneyLogClientError: For other errors
        """
        if recent_n is None:
            recent_n = self.recent_n_default

        url = f"{self.base_url}/characters/{character_id}/context"
        params = {
            "recent_n": recent_n,
            "include_pois": False
        }

        headers = {}
        if trace_id:
            headers["X-Trace-Id"] = trace_id

        logger.info(
            "Fetching context from journey-log",
            recent_n=recent_n,
            max_retries=self.max_retries,
            turn_id=get_turn_id()
        )

        # Call with retry logic
        return await self._get_with_retry(
            url=url,
            params=params,
            headers=headers,
            character_id=character_id,
            operation_name="get_context"
        )
    
    async def _get_with_retry(
        self,
        url: str,
        params: dict,
        headers: dict,
        character_id: str,
        operation_name: str
    ) -> JourneyLogContext:
        """Internal method to GET with retry logic.
        
        Implements exponential backoff for transient errors:
        - Retryable: Timeout, 5xx server errors, connection errors, 429 rate limit
        - Non-retryable: 404 not found, other 4xx client errors
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            start_time = time.time()
            
            try:
                response = await self.http_client.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout
                )
                duration_ms = (time.time() - start_time) * 1000
                response.raise_for_status()
                
                # Record metrics
                collector = get_metrics_collector()
                if collector:
                    collector.record_journey_log_latency(operation_name, duration_ms)
                    if attempt > 0:
                        collector.record_error("journey_log_retry_success")

                data = response.json()
                logger.debug(
                    f"{operation_name} successful",
                    status_code=getattr(response, 'status_code', None),
                    duration_ms=f"{duration_ms:.2f}",
                    response_size=len(str(data)),
                    attempts=attempt + 1,
                    turn_id=get_turn_id()
                )

                # Map the journey-log response to our JourneyLogContext model
                player_state = data.get("player_state", {})
                narrative_data = data.get("narrative", {})
                combat_data = data.get("combat", {})

                # Validate required fields
                if not data.get("character_id"):
                    raise JourneyLogClientError("Response missing required 'character_id' field")
                if not player_state.get("status"):
                    raise JourneyLogClientError("Response missing required 'player_state.status' field")
                if not player_state.get("location"):
                    raise JourneyLogClientError("Response missing required 'player_state.location' field")

                # Extract policy state from response
                policy_state = self._extract_policy_state(data)
                
                # Extract additional_fields for DM-managed state
                additional_fields = player_state.get("additional_fields", {})

                context = JourneyLogContext(
                    character_id=data["character_id"],
                    status=player_state["status"],
                    location=player_state["location"],
                    active_quest=data.get("quest"),
                    combat_state=combat_data.get("state"),
                    recent_history=[
                        {
                            "player_action": turn.get("player_action", ""),
                            "gm_response": turn.get("gm_response", ""),
                            "timestamp": turn.get("timestamp", "")
                        }
                        for turn in narrative_data.get("recent_turns", [])
                    ],
                    policy_state=policy_state,
                    additional_fields=additional_fields
                )

                logger.info(
                    f"Successfully fetched context",
                    status=context.status,
                    has_quest=context.active_quest is not None,
                    history_turns=len(context.recent_history),
                    combat_active=policy_state.combat_active,
                    turns_since_last_quest=policy_state.turns_since_last_quest,
                    attempts=attempt + 1
                )

                return context

            except HTTPStatusError as e:
                duration_ms = (time.time() - start_time) * 1000
                status_code = e.response.status_code
                
                # 404 is non-retryable
                if status_code == 404:
                    logger.error(
                        "Character not found in journey-log (non-retryable)",
                        status_code=404,
                        duration_ms=f"{duration_ms:.2f}"
                    )
                    raise JourneyLogNotFoundError(
                        f"Character {character_id} not found",
                        status_code=404
                    ) from e
                
                # 4xx (except 429) are non-retryable
                if 400 <= status_code < 500 and status_code != 429:
                    logger.error(
                        f"{operation_name} client error (non-retryable)",
                        status_code=status_code,
                        duration_ms=f"{duration_ms:.2f}",
                        error=redact_secrets(e.response.text)
                    )
                    raise JourneyLogClientError(
                        f"Journey-log returned {status_code}: {e.response.text}",
                        status_code=status_code
                    ) from e
                
                # 5xx and 429 are retryable
                last_exception = e
                
                # Check if we've exhausted retries
                if attempt >= self.max_retries:
                    logger.error(
                        f"{operation_name} failed after {self.max_retries} retries",
                        status_code=status_code,
                        total_attempts=attempt + 1,
                        duration_ms=f"{duration_ms:.2f}",
                        error=redact_secrets(e.response.text)
                    )
                    
                    if (collector := get_metrics_collector()):
                        collector.record_error("journey_log_retry_exhausted")
                    
                    raise JourneyLogClientError(
                        f"Journey-log returned {status_code} after {self.max_retries} retries: {e.response.text}",
                        status_code=status_code
                    ) from e
                
                # Calculate retry delay
                delay = min(
                    self.retry_delay_base * (2 ** attempt),
                    self.retry_delay_max
                )
                
                logger.warning(
                    f"{operation_name} failed (retryable), retrying in {delay:.2f}s",
                    status_code=status_code,
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    retry_delay_seconds=delay,
                    duration_ms=f"{duration_ms:.2f}",
                    error=redact_secrets(e.response.text[:200])
                )
                
                if (collector := get_metrics_collector()):
                    collector.record_error("journey_log_http_error_retry")
                
                await asyncio.sleep(delay)

            except TimeoutException as e:
                last_exception = e
                duration_ms = (time.time() - start_time) * 1000
                
                # Check if we've exhausted retries
                if attempt >= self.max_retries:
                    logger.error(
                        f"{operation_name} timed out after {self.max_retries} retries",
                        timeout_seconds=self.timeout,
                        total_attempts=attempt + 1,
                        duration_ms=f"{duration_ms:.2f}"
                    )
                    
                    if (collector := get_metrics_collector()):
                        collector.record_error("journey_log_timeout_exhausted")
                    
                    raise JourneyLogTimeoutError(
                        f"Journey-log request timed out after {self.timeout}s and {self.max_retries} retries"
                    ) from e
                
                # Calculate retry delay
                delay = min(
                    self.retry_delay_base * (2 ** attempt),
                    self.retry_delay_max
                )
                
                logger.warning(
                    f"{operation_name} timed out (retryable), retrying in {delay:.2f}s",
                    timeout_seconds=self.timeout,
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    retry_delay_seconds=delay,
                    duration_ms=f"{duration_ms:.2f}"
                )
                
                if (collector := get_metrics_collector()):
                    collector.record_error("journey_log_timeout_retry")
                
                await asyncio.sleep(delay)

            except JourneyLogClientError:
                # Re-raise our custom exceptions (already logged)
                raise

            except Exception as e:
                # Unexpected errors - treat as retryable for resilience
                last_exception = e
                duration_ms = (time.time() - start_time) * 1000
                
                # Check if we've exhausted retries
                if attempt >= self.max_retries:
                    logger.error(
                        f"{operation_name} unexpected error after {self.max_retries} retries",
                        error_type=type(e).__name__,
                        total_attempts=attempt + 1,
                        duration_ms=f"{duration_ms:.2f}"
                    )
                    
                    if (collector := get_metrics_collector()):
                        collector.record_error("journey_log_unexpected_exhausted")
                    
                    raise JourneyLogClientError(
                        f"Failed to {operation_name}: {e}"
                    ) from e
                
                # Calculate retry delay
                delay = min(
                    self.retry_delay_base * (2 ** attempt),
                    self.retry_delay_max
                )
                
                logger.warning(
                    f"{operation_name} unexpected error (retryable), retrying in {delay:.2f}s",
                    error_type=type(e).__name__,
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    retry_delay_seconds=delay,
                    duration_ms=f"{duration_ms:.2f}"
                )
                
                if (collector := get_metrics_collector()):
                    collector.record_error("journey_log_unexpected_retry")
                
                await asyncio.sleep(delay)
        
        # Should never reach here, but just in case
        if last_exception:
            raise JourneyLogClientError(
                f"Failed to {operation_name} after {self.max_retries} retries: {last_exception}"
            ) from last_exception
        raise JourneyLogClientError(f"Failed to {operation_name} with unknown error")

    async def persist_narrative(
        self,
        character_id: str,
        user_action: str,
        narrative: str,
        trace_id: Optional[str] = None
    ) -> None:
        """Persist a narrative turn to journey-log.
        
        Makes a POST request to /characters/{character_id}/narrative with:
        - user_action: The player's action
        - ai_response: The generated narrative
        
        **IMPORTANT**: This method does NOT retry on failure to prevent duplicate
        narrative entries. POST operations are not idempotent.
        
        Args:
            character_id: UUID of the character
            user_action: The player's action text
            narrative: The AI-generated narrative response
            trace_id: Optional trace ID for request correlation
            
        Raises:
            JourneyLogNotFoundError: If character not found (404)
            JourneyLogTimeoutError: If request times out
            JourneyLogClientError: For other errors
        """
        url = f"{self.base_url}/characters/{character_id}/narrative"

        headers = {}
        if trace_id:
            headers["X-Trace-Id"] = trace_id

        payload = {
            "user_action": user_action,
            "ai_response": narrative
        }

        logger.info(
            "Persisting narrative to journey-log",
            action_length=len(user_action),
            narrative_length=len(narrative),
            turn_id=get_turn_id()
        )

        start_time = time.time()
        try:
            response = await self.http_client.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            duration_ms = (time.time() - start_time) * 1000
            response.raise_for_status()
            
            # Record metrics
            collector = get_metrics_collector()
            if collector:
                collector.record_journey_log_latency("persist_narrative", duration_ms)

            logger.info(
                "Successfully persisted narrative",
                status_code=getattr(response, 'status_code', None),
                duration_ms=f"{duration_ms:.2f}",
                turn_id=get_turn_id()
            )

        except HTTPStatusError as e:
            duration_ms = (time.time() - start_time) * 1000
            if e.response.status_code == 404:
                logger.error(
                    "Character not found in journey-log",
                    status_code=404,
                    duration_ms=f"{duration_ms:.2f}"
                )
                raise JourneyLogNotFoundError(
                    f"Character {character_id} not found"
                ) from e
            else:
                logger.error(
                    "HTTP error persisting narrative",
                    status_code=e.response.status_code,
                    duration_ms=f"{duration_ms:.2f}",
                    error=redact_secrets(e.response.text)
                )
                raise JourneyLogClientError(
                    f"Journey-log returned {e.response.status_code}: {e.response.text}",
                    status_code=e.response.status_code
                ) from e

        except TimeoutException as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Timeout persisting narrative",
                timeout_seconds=self.timeout,
                duration_ms=f"{duration_ms:.2f}"
            )
            raise JourneyLogTimeoutError(
                f"Journey-log request timed out after {self.timeout}s"
            ) from e

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Unexpected error persisting narrative",
                error_type=type(e).__name__,
                duration_ms=f"{duration_ms:.2f}"
            )
            raise JourneyLogClientError(
                f"Failed to persist narrative: {e}"
            ) from e
    
    async def put_quest(
        self,
        character_id: str,
        quest_data: Optional[dict],
        trace_id: Optional[str] = None
    ) -> None:
        """Create or update a quest for the character.
        
        Makes a PUT request to /characters/{character_id}/quest with quest data.
        
        **IMPORTANT**: This method does NOT retry on failure to prevent duplicate
        quest modifications. PUT operations are not retried.
        
        Args:
            character_id: UUID of the character
            quest_data: Quest information (title, summary, details)
            trace_id: Optional trace ID for request correlation
            
        Raises:
            JourneyLogNotFoundError: If character not found (404)
            JourneyLogTimeoutError: If request times out
            JourneyLogClientError: For other errors
        """
        url = f"{self.base_url}/characters/{character_id}/quest"
        
        headers = {}
        if trace_id:
            headers["X-Trace-Id"] = trace_id
        
        logger.info(
            "Putting quest to journey-log",
            quest_title=quest_data.get("title") if quest_data else None,
            turn_id=get_turn_id()
        )
        
        start_time = time.time()
        try:
            response = await self.http_client.put(
                url,
                json=quest_data or {},
                headers=headers,
                timeout=self.timeout
            )
            duration_ms = (time.time() - start_time) * 1000
            response.raise_for_status()
            
            # Record metrics
            collector = get_metrics_collector()
            if collector:
                collector.record_journey_log_latency("put_quest", duration_ms)
            
            logger.info(
                "Successfully put quest",
                status_code=getattr(response, 'status_code', None),
                duration_ms=f"{duration_ms:.2f}",
                turn_id=get_turn_id()
            )
        
        except HTTPStatusError as e:
            duration_ms = (time.time() - start_time) * 1000
            if e.response.status_code == 404:
                logger.error(
                    "Character not found in journey-log",
                    status_code=404,
                    duration_ms=f"{duration_ms:.2f}"
                )
                raise JourneyLogNotFoundError(
                    f"Character {character_id} not found"
                ) from e
            else:
                logger.error(
                    "HTTP error putting quest",
                    status_code=e.response.status_code,
                    duration_ms=f"{duration_ms:.2f}",
                    error=redact_secrets(e.response.text)
                )
                raise JourneyLogClientError(
                    f"Journey-log returned {e.response.status_code}: {e.response.text}",
                    status_code=e.response.status_code
                ) from e
        
        except TimeoutException as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Timeout putting quest",
                timeout_seconds=self.timeout,
                duration_ms=f"{duration_ms:.2f}"
            )
            raise JourneyLogTimeoutError(
                f"Journey-log request timed out after {self.timeout}s"
            ) from e
        
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Unexpected error putting quest",
                error_type=type(e).__name__,
                duration_ms=f"{duration_ms:.2f}"
            )
            raise JourneyLogClientError(
                f"Failed to put quest: {e}"
            ) from e
    
    async def delete_quest(
        self,
        character_id: str,
        trace_id: Optional[str] = None
    ) -> None:
        """Delete (complete/abandon) the active quest for the character.
        
        Makes a DELETE request to /characters/{character_id}/quest.
        
        **IMPORTANT**: This method does NOT retry on failure to prevent duplicate
        quest deletions. DELETE operations are not retried.
        
        Args:
            character_id: UUID of the character
            trace_id: Optional trace ID for request correlation
            
        Raises:
            JourneyLogNotFoundError: If character not found (404)
            JourneyLogTimeoutError: If request times out
            JourneyLogClientError: For other errors
        """
        url = f"{self.base_url}/characters/{character_id}/quest"
        
        headers = {}
        if trace_id:
            headers["X-Trace-Id"] = trace_id
        
        logger.info(
            "Deleting quest from journey-log",
            turn_id=get_turn_id()
        )
        
        start_time = time.time()
        try:
            response = await self.http_client.delete(
                url,
                headers=headers,
                timeout=self.timeout
            )
            duration_ms = (time.time() - start_time) * 1000
            response.raise_for_status()
            
            # Record metrics
            collector = get_metrics_collector()
            if collector:
                collector.record_journey_log_latency("delete_quest", duration_ms)
            
            logger.info(
                "Successfully deleted quest",
                status_code=getattr(response, 'status_code', None),
                duration_ms=f"{duration_ms:.2f}",
                turn_id=get_turn_id()
            )
        
        except HTTPStatusError as e:
            duration_ms = (time.time() - start_time) * 1000
            if e.response.status_code == 404:
                logger.error(
                    "Character not found in journey-log",
                    status_code=404,
                    duration_ms=f"{duration_ms:.2f}"
                )
                raise JourneyLogNotFoundError(
                    f"Character {character_id} not found"
                ) from e
            else:
                logger.error(
                    "HTTP error deleting quest",
                    status_code=e.response.status_code,
                    duration_ms=f"{duration_ms:.2f}",
                    error=redact_secrets(e.response.text)
                )
                raise JourneyLogClientError(
                    f"Journey-log returned {e.response.status_code}: {e.response.text}",
                    status_code=e.response.status_code
                ) from e
        
        except TimeoutException as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Timeout deleting quest",
                timeout_seconds=self.timeout,
                duration_ms=f"{duration_ms:.2f}"
            )
            raise JourneyLogTimeoutError(
                f"Journey-log request timed out after {self.timeout}s"
            ) from e
        
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Unexpected error deleting quest",
                error_type=type(e).__name__,
                duration_ms=f"{duration_ms:.2f}"
            )
            raise JourneyLogClientError(
                f"Failed to delete quest: {e}"
            ) from e
    
    async def put_combat(
        self,
        character_id: str,
        combat_data: Optional[dict],
        action_type: str,
        trace_id: Optional[str] = None
    ) -> None:
        """Create, update, or end combat for the character.
        
        Makes a PUT request to /characters/{character_id}/combat with combat_state.
        
        The journey-log PUT /combat endpoint expects:
        {
          "combat_state": <CombatState object or null>
        }
        
        **IMPORTANT**: This method does NOT retry on failure to prevent duplicate
        combat modifications. PUT operations are not retried.
        
        Args:
            character_id: UUID of the character
            combat_data: Combat state object (CombatState schema) or None to clear
            action_type: Type of combat action (start/continue/end) for logging only
            trace_id: Optional trace ID for request correlation
            
        Raises:
            JourneyLogNotFoundError: If character not found (404)
            JourneyLogTimeoutError: If request times out
            JourneyLogClientError: For other errors
        """
        url = f"{self.base_url}/characters/{character_id}/combat"
        
        headers = {}
        if trace_id:
            headers["X-Trace-Id"] = trace_id
        
        logger.info(
            "Putting combat to journey-log",
            action_type=action_type,
            has_combat_data=combat_data is not None,
            turn_id=get_turn_id()
        )
        
        start_time = time.time()
        try:
            # Build request payload per UpdateCombatRequest schema
            # combat_state can be a CombatState object or null
            payload = {
                "combat_state": combat_data
            }
            
            response = await self.http_client.put(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            duration_ms = (time.time() - start_time) * 1000
            response.raise_for_status()
            
            # Record metrics
            collector = get_metrics_collector()
            if collector:
                collector.record_journey_log_latency("put_combat", duration_ms)
            
            logger.info(
                "Successfully put combat",
                status_code=getattr(response, 'status_code', None),
                duration_ms=f"{duration_ms:.2f}",
                action_type=action_type,
                turn_id=get_turn_id()
            )
        
        except HTTPStatusError as e:
            duration_ms = (time.time() - start_time) * 1000
            if e.response.status_code == 404:
                logger.error(
                    "Character not found in journey-log",
                    status_code=404,
                    duration_ms=f"{duration_ms:.2f}"
                )
                raise JourneyLogNotFoundError(
                    f"Character {character_id} not found"
                ) from e
            else:
                logger.error(
                    "HTTP error putting combat",
                    status_code=e.response.status_code,
                    duration_ms=f"{duration_ms:.2f}",
                    error=redact_secrets(e.response.text)
                )
                raise JourneyLogClientError(
                    f"Journey-log returned {e.response.status_code}: {e.response.text}",
                    status_code=e.response.status_code
                ) from e
        
        except TimeoutException as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Timeout putting combat",
                timeout_seconds=self.timeout,
                duration_ms=f"{duration_ms:.2f}"
            )
            raise JourneyLogTimeoutError(
                f"Journey-log request timed out after {self.timeout}s"
            ) from e
        
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Unexpected error putting combat",
                error_type=type(e).__name__,
                duration_ms=f"{duration_ms:.2f}"
            )
            raise JourneyLogClientError(
                f"Failed to put combat: {e}"
            ) from e
    
    async def post_poi(
        self,
        character_id: str,
        poi_data: Optional[dict],
        action_type: str,
        trace_id: Optional[str] = None
    ) -> None:
        """Create or reference a point of interest.
        
        Makes a POST request to /characters/{character_id}/pois with POI data.
        
        **IMPORTANT**: This method does NOT retry on failure to prevent duplicate
        POI entries. POST operations are not retried.
        
        Args:
            character_id: UUID of the character
            poi_data: POI information (name, description, tags)
            action_type: Type of POI action (create/reference)
            trace_id: Optional trace ID for request correlation
            
        Raises:
            JourneyLogNotFoundError: If character not found (404)
            JourneyLogTimeoutError: If request times out
            JourneyLogClientError: For other errors
        """
        url = f"{self.base_url}/characters/{character_id}/pois"
        
        headers = {}
        if trace_id:
            headers["X-Trace-Id"] = trace_id
        
        logger.info(
            "Posting POI to journey-log",
            action_type=action_type,
            poi_name=poi_data.get("name") if poi_data else None,
            turn_id=get_turn_id()
        )
        
        start_time = time.time()
        try:
            # Build request payload - only send name and description per spec
            payload = {}
            if poi_data:
                # Only include fields that journey-log expects
                if "name" in poi_data:
                    payload["name"] = poi_data["name"]
                if "description" in poi_data:
                    payload["description"] = poi_data["description"]
                if "tags" in poi_data:
                    payload["tags"] = poi_data["tags"]
            
            # Validate that required fields are present
            if not payload.get("name") or not payload.get("description"):
                error_msg = "POI POST requires both name and description fields"
                logger.error(
                    "Invalid POI payload - missing required fields",
                    has_name=bool(payload.get("name")),
                    has_description=bool(payload.get("description"))
                )
                raise JourneyLogClientError(error_msg)
            
            response = await self.http_client.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            duration_ms = (time.time() - start_time) * 1000
            response.raise_for_status()
            
            # Record metrics
            collector = get_metrics_collector()
            if collector:
                collector.record_journey_log_latency("post_poi", duration_ms)
            
            logger.info(
                "Successfully posted POI",
                status_code=getattr(response, 'status_code', None),
                duration_ms=f"{duration_ms:.2f}",
                turn_id=get_turn_id()
            )
        
        except HTTPStatusError as e:
            duration_ms = (time.time() - start_time) * 1000
            if e.response.status_code == 404:
                logger.error(
                    "Character not found in journey-log",
                    status_code=404,
                    duration_ms=f"{duration_ms:.2f}"
                )
                raise JourneyLogNotFoundError(
                    f"Character {character_id} not found"
                ) from e
            else:
                logger.error(
                    "HTTP error posting POI",
                    status_code=e.response.status_code,
                    duration_ms=f"{duration_ms:.2f}",
                    error=redact_secrets(e.response.text)
                )
                raise JourneyLogClientError(
                    f"Journey-log returned {e.response.status_code}: {e.response.text}",
                    status_code=e.response.status_code
                ) from e
        
        except TimeoutException as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Timeout posting POI",
                timeout_seconds=self.timeout,
                duration_ms=f"{duration_ms:.2f}"
            )
            raise JourneyLogTimeoutError(
                f"Journey-log request timed out after {self.timeout}s"
            ) from e
        
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Unexpected error posting POI",
                error_type=type(e).__name__,
                duration_ms=f"{duration_ms:.2f}"
            )
            raise JourneyLogClientError(
                f"Failed to post POI: {e}"
            ) from e
    
    async def get_random_pois(
        self,
        character_id: str,
        n: int = 3,
        trace_id: Optional[str] = None
    ) -> list[dict]:
        """Fetch random POIs for memory spark injection.
        
        Makes a GET request to /characters/{character_id}/pois/random.
        Returns empty list if no POIs exist or on error (non-fatal).
        
        This method implements retry logic with exponential backoff for transient errors,
        but failures are non-fatal and return an empty list to avoid blocking turns.
        
        Args:
            character_id: UUID of the character
            n: Number of random POIs to fetch (1-20)
            trace_id: Optional trace ID for request correlation
            
        Returns:
            List of POI dictionaries (may be empty)
        """
        # Clamp n to the valid range [1, 20] as per config validation
        n = max(1, min(n, 20))
        
        url = f"{self.base_url}/characters/{character_id}/pois/random"
        params = {"n": n}
        
        headers = {}
        if trace_id:
            headers["X-Trace-Id"] = trace_id
        
        logger.info(
            "Fetching random POIs from journey-log",
            n=n,
            max_retries=self.max_retries
        )
        
        # Use retry logic but catch all exceptions to maintain non-fatal behavior
        try:
            return await self._get_random_pois_with_retry(
                url=url,
                params=params,
                headers=headers
            )
        except Exception as e:
            # All errors are non-fatal for memory sparks - return empty list
            logger.warning(
                "Failed to fetch random POIs after retries - returning empty list",
                error_type=type(e).__name__,
                error=str(e)
            )
            return []
    
    async def _get_random_pois_with_retry(
        self,
        url: str,
        params: dict,
        headers: dict
    ) -> list[dict]:
        """Internal method to GET random POIs with retry logic.
        
        Implements exponential backoff for transient errors.
        Retries are attempted but failures are ultimately non-fatal.
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            start_time = time.time()
            
            try:
                response = await self.http_client.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout
                )
                duration_ms = (time.time() - start_time) * 1000
                response.raise_for_status()
                
                data = response.json()
                pois = data.get("pois", [])
                
                logger.info(
                    "Successfully fetched random POIs",
                    status_code=getattr(response, 'status_code', None),
                    duration_ms=f"{duration_ms:.2f}",
                    poi_count=len(pois),
                    attempts=attempt + 1
                )
                
                # Record metrics
                if (collector := get_metrics_collector()):
                    collector.record_journey_log_latency("get_random_pois", duration_ms)
                    if attempt > 0:
                        collector.record_error("journey_log_retry_success")
                
                return pois

            except HTTPStatusError as e:
                duration_ms = (time.time() - start_time) * 1000
                status_code = e.response.status_code
                
                # 404 and other 4xx (except 429) are non-retryable
                if 400 <= status_code < 500 and status_code != 429:
                    logger.warning(
                        "get_random_pois client error (non-retryable)",
                        status_code=status_code,
                        duration_ms=f"{duration_ms:.2f}",
                        error=redact_secrets(e.response.text)
                    )
                    raise
                
                # 5xx and 429 are retryable
                last_exception = e
                
                if attempt >= self.max_retries:
                    logger.warning(
                        f"get_random_pois failed after {self.max_retries} retries",
                        status_code=status_code,
                        total_attempts=attempt + 1,
                        duration_ms=f"{duration_ms:.2f}"
                    )
                    
                    if (collector := get_metrics_collector()):
                        collector.record_error("journey_log_retry_exhausted")
                    
                    raise
                
                delay = min(
                    self.retry_delay_base * (2 ** attempt),
                    self.retry_delay_max
                )
                
                logger.debug(
                    f"get_random_pois failed (retryable), retrying in {delay:.2f}s",
                    status_code=status_code,
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    retry_delay_seconds=delay,
                    duration_ms=f"{duration_ms:.2f}"
                )
                
                if (collector := get_metrics_collector()):
                    collector.record_error("journey_log_http_error_retry")
                
                await asyncio.sleep(delay)

            except TimeoutException as e:
                last_exception = e
                duration_ms = (time.time() - start_time) * 1000
                
                if attempt >= self.max_retries:
                    logger.warning(
                        f"get_random_pois timed out after {self.max_retries} retries",
                        timeout_seconds=self.timeout,
                        total_attempts=attempt + 1,
                        duration_ms=f"{duration_ms:.2f}"
                    )
                    
                    if (collector := get_metrics_collector()):
                        collector.record_error("journey_log_timeout_exhausted")
                    
                    raise
                
                delay = min(
                    self.retry_delay_base * (2 ** attempt),
                    self.retry_delay_max
                )
                
                logger.debug(
                    f"get_random_pois timed out (retryable), retrying in {delay:.2f}s",
                    timeout_seconds=self.timeout,
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    retry_delay_seconds=delay,
                    duration_ms=f"{duration_ms:.2f}"
                )
                
                if (collector := get_metrics_collector()):
                    collector.record_error("journey_log_timeout_retry")
                
                await asyncio.sleep(delay)

            except Exception as e:
                # Unexpected errors - non-retryable for simplicity
                duration_ms = (time.time() - start_time) * 1000
                logger.warning(
                    "get_random_pois unexpected error (non-retryable)",
                    error_type=type(e).__name__,
                    duration_ms=f"{duration_ms:.2f}"
                )
                raise
        
        # Should never reach here
        if last_exception:
            raise last_exception
        raise JourneyLogClientError("Failed to get random POIs with unknown error")
