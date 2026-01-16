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

import logging
from typing import Optional
from httpx import AsyncClient, HTTPStatusError, TimeoutException
from app.models import JourneyLogContext

logger = logging.getLogger(__name__)


class JourneyLogClientError(Exception):
    """Base exception for journey-log client errors."""
    pass


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
        recent_n_default: int = 20
    ):
        """Initialize journey-log client.
        
        Args:
            base_url: Base URL of journey-log service (e.g., http://localhost:8000)
            http_client: HTTP client for making requests
            timeout: Request timeout in seconds
            recent_n_default: Default number of recent narrative turns to fetch
        """
        self.base_url = base_url.rstrip('/')
        self.http_client = http_client
        self.timeout = timeout
        self.recent_n_default = recent_n_default

        logger.info(
            f"Initialized JourneyLogClient with base_url={self.base_url}, "
            f"timeout={self.timeout}s, recent_n_default={self.recent_n_default}"
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
        
        Args:
            character_id: UUID of the character
            recent_n: Number of recent turns to fetch (defaults to recent_n_default)
            trace_id: Optional trace ID for request correlation
            
        Returns:
            JourneyLogContext with character state
            
        Raises:
            JourneyLogNotFoundError: If character not found (404)
            JourneyLogTimeoutError: If request times out
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
            f"Fetching context for character {character_id} "
            f"(recent_n={recent_n}, trace_id={trace_id})"
        )

        try:
            response = await self.http_client.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            logger.debug(f"Received context response: {len(str(data))} bytes")

            # Map the journey-log response to our JourneyLogContext model
            # The journey-log API returns a CharacterContextResponse structure
            # Use defensive .get() to handle optional fields and prevent KeyErrors
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
                ]
            )

            logger.info(
                f"Successfully fetched context for {character_id}: "
                f"status={context.status}, "
                f"has_quest={context.active_quest is not None}, "
                f"history_turns={len(context.recent_history)}"
            )

            return context

        except HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error(f"Character {character_id} not found in journey-log")
                raise JourneyLogNotFoundError(
                    f"Character {character_id} not found"
                ) from e
            else:
                logger.error(
                    f"HTTP error from journey-log: {e.response.status_code} - {e.response.text}"
                )
                raise JourneyLogClientError(
                    f"Journey-log returned {e.response.status_code}: {e.response.text}"
                ) from e

        except TimeoutException as e:
            logger.error(f"Timeout fetching context for {character_id}")
            raise JourneyLogTimeoutError(
                f"Journey-log request timed out after {self.timeout}s"
            ) from e

        except Exception as e:
            logger.error(f"Unexpected error fetching context: {e}")
            raise JourneyLogClientError(
                f"Failed to fetch context: {e}"
            ) from e

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
            f"Persisting narrative for character {character_id} "
            f"(action_len={len(user_action)}, narrative_len={len(narrative)}, "
            f"trace_id={trace_id})"
        )

        try:
            response = await self.http_client.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            logger.info(f"Successfully persisted narrative for {character_id}")

        except HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error(f"Character {character_id} not found in journey-log")
                raise JourneyLogNotFoundError(
                    f"Character {character_id} not found"
                ) from e
            else:
                logger.error(
                    f"HTTP error persisting narrative: {e.response.status_code} - {e.response.text}"
                )
                raise JourneyLogClientError(
                    f"Journey-log returned {e.response.status_code}: {e.response.text}"
                ) from e

        except TimeoutException as e:
            logger.error(f"Timeout persisting narrative for {character_id}")
            raise JourneyLogTimeoutError(
                f"Journey-log request timed out after {self.timeout}s"
            ) from e

        except Exception as e:
            logger.error(f"Unexpected error persisting narrative: {e}")
            raise JourneyLogClientError(
                f"Failed to persist narrative: {e}"
            ) from e
