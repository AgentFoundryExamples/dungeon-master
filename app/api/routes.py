"""API route handlers for Dungeon Master service.

This module defines the HTTP endpoints for the Dungeon Master service:
- POST /turn: Process a player turn and generate narrative response
- GET /health: Service health check with optional journey-log ping

All handlers are stubbed for now and will be implemented in a future issue.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from httpx import AsyncClient
import logging

from app.models import TurnRequest, TurnResponse, HealthResponse
from app.config import get_settings, Settings

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_http_client() -> AsyncClient:
    """Dependency that provides an HTTP client for external requests.
    
    This is a placeholder for proper dependency injection that will be
    implemented with application lifespan management in main.py.
    
    Yields:
        AsyncClient instance for making HTTP requests
    """
    async with AsyncClient() as client:
        yield client


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
    logger.info(
        f"Processing turn for character {request.character_id}: {request.user_action[:50]}..."
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
