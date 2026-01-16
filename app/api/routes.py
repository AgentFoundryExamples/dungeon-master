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
"""API route handlers for Dungeon Master service.

This module defines the HTTP endpoints for the Dungeon Master service:
- POST /turn: Process a player turn and generate narrative response
- GET /health: Service health check with optional journey-log ping

All handlers are stubbed for now and will be implemented in a future issue.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from httpx import AsyncClient
import logging
import re

from app.models import TurnRequest, TurnResponse, HealthResponse
from app.config import get_settings, Settings

logger = logging.getLogger(__name__)

router = APIRouter()


def sanitize_for_log(text: str, max_length: int = 100) -> str:
    """Sanitize text for safe logging.
    
    Removes newlines, carriage returns, and other control characters
    that could be used for log injection attacks. Also truncates to
    prevent log flooding.
    
    Args:
        text: Text to sanitize
        max_length: Maximum length to truncate to
        
    Returns:
        Sanitized text safe for logging
    """
    # Remove control characters (newlines, carriage returns, etc.)
    sanitized = re.sub(r'[\r\n\t\x00-\x1f\x7f-\x9f]', '', text)
    # Truncate to max length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."
    return sanitized


async def get_http_client() -> AsyncClient:
    """Dependency that provides an HTTP client for external requests.
    
    This is a placeholder that must be overridden by the application.
    The application lifespan in main.py provides the actual implementation.
    
    Raises:
        NotImplementedError: If not overridden by the application
    """
    raise NotImplementedError(
        "get_http_client dependency must be overridden. "
        "This should be configured in app.main module."
    )


@router.post(
    "/turn",
    response_model=TurnResponse,
    status_code=status.HTTP_200_OK,
    summary="Process a player turn",
    description=(
        "Process a player's turn action and generate an AI narrative response. "
        "This endpoint will orchestrate calls to journey-log for context retrieval "
        "and OpenAI for narrative generation. Currently stubbed."
    ),
    responses={
        200: {
            "description": "Successful narrative generation",
            "content": {
                "application/json": {
                    "example": {
                        "narrative": "You enter the ancient temple. Torches flicker along the walls..."
                    }
                }
            }
        },
        400: {"description": "Invalid request (malformed UUID, etc.)"},
        404: {"description": "Character not found"},
        500: {"description": "Internal server error"},
    }
)
async def process_turn(
    request: TurnRequest,
    http_client: AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_settings)
) -> TurnResponse:
    """Process a player turn and generate narrative response.
    
    STUB: This endpoint is currently stubbed and returns a placeholder response.
    Full orchestration logic (journey-log context fetch + LLM generation) will be
    implemented in a future issue.
    
    Args:
        request: Turn request with character_id and user_action
        http_client: HTTP client for external requests (injected)
        settings: Application settings (injected)
        
    Returns:
        TurnResponse with generated narrative
        
    Raises:
        HTTPException: If request validation fails or processing error occurs
    """
    # Sanitize inputs for logging to prevent log injection
    safe_character_id = sanitize_for_log(request.character_id, 36)
    safe_action = sanitize_for_log(request.user_action, 50)
    
    logger.info(
        f"Processing turn for character {safe_character_id}: {safe_action}..."
    )
    
    # STUB: Return placeholder response
    # TODO: Implement journey-log context fetch and LLM orchestration
    return TurnResponse(
        narrative=(
            f"[STUB] Received action: {request.user_action[:100]}. "
            "Full orchestration will be implemented in next issue."
        )
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint",
    description=(
        "Check service health status. Optionally pings journey-log service if "
        "HEALTH_CHECK_JOURNEY_LOG is enabled. Returns 200 with status='healthy' "
        "or 'degraded' based on dependency availability."
    ),
    responses={
        200: {
            "description": "Service is healthy or degraded",
            "content": {
                "application/json": {
                    "examples": {
                        "healthy": {
                            "value": {
                                "status": "healthy",
                                "service": "dungeon-master",
                                "journey_log_accessible": True
                            }
                        },
                        "degraded": {
                            "value": {
                                "status": "degraded",
                                "service": "dungeon-master",
                                "journey_log_accessible": False
                            }
                        }
                    }
                }
            }
        }
    }
)
async def health_check(
    http_client: AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_settings)
) -> HealthResponse:
    """Health check endpoint with optional journey-log ping.
    
    Returns service health status. If HEALTH_CHECK_JOURNEY_LOG is enabled,
    attempts to ping the journey-log service and reports accessibility.
    
    Returns 'healthy' if all checks pass, 'degraded' if journey-log is
    unreachable (when health check is enabled) but service can still start.
    
    Args:
        http_client: HTTP client for external requests (injected)
        settings: Application settings (injected)
        
    Returns:
        HealthResponse with status and optional journey-log accessibility
    """
    logger.debug("Health check requested")
    
    journey_log_accessible = None
    service_status = "healthy"
    
    # Optionally check journey-log service accessibility
    if settings.health_check_journey_log:
        try:
            logger.debug(f"Pinging journey-log service at {settings.journey_log_base_url}")
            response = await http_client.get(
                f"{settings.journey_log_base_url}/health",
                timeout=5.0  # Short timeout for health checks
            )
            journey_log_accessible = response.status_code == 200
            
            if not journey_log_accessible:
                logger.warning(
                    f"Journey-log health check returned status {response.status_code}"
                )
                service_status = "degraded"
        except Exception as e:
            logger.warning(f"Journey-log health check failed: {e}")
            journey_log_accessible = False
            service_status = "degraded"
    
    return HealthResponse(
        status=service_status,
        service=settings.service_name,
        journey_log_accessible=journey_log_accessible
    )
