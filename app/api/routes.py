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
- POST /turn: Process a player turn and generate narrative response (synchronous)
- GET /health: Service health check with optional journey-log ping
- GET /metrics: Service metrics (optional, requires ENABLE_METRICS=true)
- POST /debug/parse_llm: Debug endpoint for LLM parsing (optional, requires ENABLE_DEBUG_ENDPOINTS=true)

Note: Streaming endpoints have been removed to simplify the MVP.
The service now operates in synchronous mode only.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from httpx import AsyncClient
import re
import time
import math

from app.models import TurnRequest, TurnResponse, HealthResponse, DebugParseRequest
from app.config import get_settings, Settings
from app.services.journey_log_client import (
    JourneyLogClient,
    JourneyLogNotFoundError,
    JourneyLogTimeoutError,
    JourneyLogClientError
)
from app.services.llm_client import (
    LLMTimeoutError,
    LLMResponseError,
    LLMClientError
)
from app.services.outcome_parser import OutcomeParser
from app.services.turn_orchestrator import TurnOrchestrator
from app.logging import (
    StructuredLogger,
    PhaseTimer,
    set_character_id,
    set_turn_id,
    get_request_id,
    get_turn_id,
    TurnLogger,
    sanitize_for_log as sanitize_text
)
from app.metrics import get_metrics_collector, MetricsTimer

logger = StructuredLogger(__name__)

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


def create_error_response(
    error_type: str,
    message: str,
    status_code: int
) -> HTTPException:
    """Create a structured error response.
    
    Args:
        error_type: Machine-readable error type
        message: Human-readable error message
        status_code: HTTP status code
        
    Returns:
        HTTPException with structured error detail
    """
    # Get request_id from context; use None if not available
    # This ensures the error response structure is consistent
    request_id = get_request_id()
    
    error_detail = {
        "error": {
            "type": error_type,
            "message": message,
            "request_id": request_id if request_id else None
        }
    }
    
    return HTTPException(
        status_code=status_code,
        detail=error_detail
    )


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


def get_journey_log_client():
    """Dependency that provides a JourneyLogClient for journey-log requests.
    
    This is a placeholder that must be overridden by the application.
    The application lifespan in main.py provides the actual implementation.
    
    Raises:
        NotImplementedError: If not overridden by the application
    """
    raise NotImplementedError(
        "get_journey_log_client dependency must be overridden. "
        "This should be configured in app.main module."
    )


def get_llm_client():
    """Dependency that provides an LLMClient for LLM requests.
    
    This is a placeholder that must be overridden by the application.
    The application lifespan in main.py provides the actual implementation.
    
    Raises:
        NotImplementedError: If not overridden by the application
    """
    raise NotImplementedError(
        "get_llm_client dependency must be overridden. "
        "This should be configured in app.main module."
    )


def get_policy_engine():
    """Dependency that provides a PolicyEngine for policy decisions.
    
    This is a placeholder that must be overridden by the application.
    The application lifespan in main.py provides the actual implementation.
    
    Raises:
        NotImplementedError: If not overridden by the application
    """
    raise NotImplementedError(
        "get_policy_engine dependency must be overridden. "
        "This should be configured in app.main module."
    )




def get_turn_orchestrator():
    """Dependency that provides a TurnOrchestrator for turn processing.
    
    This is a placeholder that must be overridden by the application.
    The application lifespan in main.py provides the actual implementation.
    
    Raises:
        NotImplementedError: If not overridden by the application
    """
    raise NotImplementedError(
        "get_turn_orchestrator dependency must be overridden. "
        "This should be configured in app.main module."
    )


def get_character_rate_limiter():
    """Dependency that provides a RateLimiter for per-character rate limiting.
    
    This is a placeholder that must be overridden by the application.
    The application lifespan in main.py provides the actual implementation.
    
    Raises:
        NotImplementedError: If not overridden by the application
    """
    raise NotImplementedError(
        "get_character_rate_limiter dependency must be overridden. "
        "This should be configured in app.main module."
    )


def get_llm_semaphore():
    """Dependency that provides a Semaphore for global LLM concurrency limiting.
    
    This is a placeholder that must be overridden by the application.
    The application lifespan in main.py provides the actual implementation.
    
    Raises:
        NotImplementedError: If not overridden by the application
    """
    raise NotImplementedError(
        "get_llm_semaphore dependency must be overridden. "
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
                        "narrative": "You enter the ancient temple. Torches flicker along the walls...",
                        "intents": {
                            "quest_intent": {"action": "none"},
                            "combat_intent": {"action": "none"},
                            "poi_intent": {"action": "create", "name": "Ancient Temple"},
                            "meta": None
                        }
                    }
                }
            }
        },
        400: {"description": "Invalid request (malformed UUID, etc.)"},
        404: {"description": "Character not found"},
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "error": "rate_limit_exceeded",
                            "message": "Too many requests for this character. Please wait 0.5 seconds.",
                            "retry_after_seconds": 0.5,
                            "character_id": "550e8400-e29b-41d4-a716-446655440000"
                        }
                    }
                }
            },
            "headers": {
                "Retry-After": {
                    "description": "Seconds to wait before retrying",
                    "schema": {"type": "string"}
                }
            }
        },
        500: {"description": "Internal server error"},
    }
)
async def process_turn(
    request: TurnRequest,
    journey_log_client: JourneyLogClient = Depends(get_journey_log_client),
    turn_orchestrator: TurnOrchestrator = Depends(get_turn_orchestrator),
    character_rate_limiter = Depends(get_character_rate_limiter),
    llm_semaphore = Depends(get_llm_semaphore),
    settings: Settings = Depends(get_settings)
) -> TurnResponse:
    """Process a player turn and generate narrative response.
    
    Full orchestration flow (delegated to TurnOrchestrator):
    0. Check per-character rate limit (429 if exceeded)
    1. Fetch context from journey-log
    2. Evaluate PolicyEngine for quest and POI trigger decisions
    3. Inject policy_hints into context
    4. Build prompt using PromptBuilder
    5. Call LLM for narrative generation (with global concurrency limit)
    6. Parse intents and apply policy guardrails
    7. Derive subsystem actions from policy and intents
    8. Execute writes in deterministic order (quest → combat → POI → narrative)
    9. Return TurnResponse with narrative, intents, and subsystem_summary
    
    Args:
        request: Turn request with character_id and user_action
        journey_log_client: JourneyLogClient for journey-log communication (injected)
        turn_orchestrator: TurnOrchestrator for turn processing (injected)
        character_rate_limiter: RateLimiter for per-character throttling (injected)
        llm_semaphore: Semaphore for global LLM concurrency control (injected)
        settings: Application settings (injected)
        
    Returns:
        TurnResponse with generated narrative, intents, and subsystem summary
        
    Raises:
        HTTPException: If request validation fails or processing error occurs
    """
    # Generate unique turn_id for this request
    import uuid
    turn_id = str(uuid.uuid4())
    set_turn_id(turn_id)
    
    # Set character_id in context for logging correlation
    set_character_id(request.character_id)
    
    # Initialize turn logger
    turn_logger = TurnLogger(
        logger=logger,
        sampling_rate=settings.turn_log_sampling_rate,
        redact_narrative=True
    )
    
    # Sanitize inputs for logging to prevent log injection
    safe_character_id = sanitize_for_log(request.character_id, 36)
    safe_action = sanitize_for_log(request.user_action, 50)

    # Step 0: Check per-character rate limit
    from app.resilience import RateLimiter
    if not await character_rate_limiter.acquire(request.character_id):
        # Rate limit exceeded
        retry_after = character_rate_limiter.get_retry_after(request.character_id)
        
        logger.warning(
            "Rate limit exceeded for character",
            turn_id=turn_id,
            character_id=safe_character_id,
            retry_after_seconds=retry_after
        )
        
        # Record metrics
        collector = get_metrics_collector()
        if collector:
            collector.record_error("rate_limit_exceeded")
            collector.record_turn_processed(
                environment=settings.environment,
                character_id=request.character_id,
                outcome="rate_limited"
            )
        
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Too many requests for this character. Please wait {retry_after:.1f} seconds.",
                "retry_after_seconds": round(retry_after, 1),
                "character_id": request.character_id
            },
            headers={"Retry-After": str(math.ceil(retry_after))}
        )

    logger.info(
        "Processing turn request",
        turn_id=turn_id,
        character_id=safe_character_id,
        action_preview=safe_action
    )
    
    # Track latencies for turn logging
    latencies = {}
    turn_start_time = time.time()
    outcome = "unknown"
    errors = []
    
    # Initialize these variables for error paths
    subsystem_summary = None
    intents = None
    policy_decisions = {}
    context = None
    narrative = None

    try:
        # Step 1: Fetch context from journey-log
        context_start = time.time()
        with PhaseTimer("context_fetch", logger), MetricsTimer("journey_log_fetch"):
            logger.debug("Fetching context from journey-log")
            context = await journey_log_client.get_context(
                character_id=request.character_id,
                trace_id=request.trace_id
            )
        latencies['context_fetch_ms'] = (time.time() - context_start) * 1000

        # Step 2-9: Delegate to TurnOrchestrator for deterministic processing
        orchestration_start = time.time()
        with PhaseTimer("turn_orchestration", logger), MetricsTimer("turn"):
            logger.debug("Orchestrating turn with TurnOrchestrator")
            
            # Acquire LLM semaphore to enforce global concurrency limit
            async with llm_semaphore:
                logger.debug(
                    "Acquired LLM semaphore",
                    active_llm_calls=llm_semaphore.active_count
                )
                
                narrative, intents, subsystem_summary = await turn_orchestrator.orchestrate_turn(
                    character_id=request.character_id,
                    user_action=request.user_action,
                    context=context,
                    trace_id=request.trace_id,
                    dry_run=False
                )
        latencies['orchestration_ms'] = (time.time() - orchestration_start) * 1000
        latencies['total_ms'] = (time.time() - turn_start_time) * 1000
        
        # Build policy decisions for logging
        policy_decisions = {
            "quest_eligible": (
                context.policy_hints.quest_trigger_decision.eligible 
                if context.policy_hints and context.policy_hints.quest_trigger_decision 
                else False
            ),
            "quest_triggered": (
                context.policy_hints.quest_trigger_decision.roll_passed 
                if context.policy_hints and context.policy_hints.quest_trigger_decision 
                else False
            ),
            "poi_eligible": (
                context.policy_hints.poi_trigger_decision.eligible 
                if context.policy_hints and context.policy_hints.poi_trigger_decision 
                else False
            ),
            "poi_triggered": (
                context.policy_hints.poi_trigger_decision.roll_passed 
                if context.policy_hints and context.policy_hints.poi_trigger_decision 
                else False
            )
        }
        
        # Log orchestration results
        logger.info(
            "Successfully processed turn",
            turn_id=turn_id,
            narrative_length=len(narrative),
            has_intents=intents is not None,
            quest_change=subsystem_summary.quest_change.action,
            combat_change=subsystem_summary.combat_change.action,
            poi_change=subsystem_summary.poi_change.action,
            narrative_persisted=subsystem_summary.narrative_persisted
        )
        
        # Record turn metrics
        collector = get_metrics_collector()
        if collector:
            collector.record_turn_processed(
                environment=settings.environment,
                character_id=request.character_id,
                outcome="success"
            )
        
        # Mark as success for finally block
        outcome = "success"
        
        return TurnResponse(
            narrative=narrative,
            intents=intents,
            subsystem_summary=subsystem_summary
        )

    except JourneyLogNotFoundError as e:
        outcome = "error"
        errors.append({"type": "character_not_found", "message": str(e)})
        logger.error("Character not found", turn_id=turn_id, error=str(e))
        if (collector := get_metrics_collector()):
            collector.record_error("character_not_found")
        raise create_error_response(
            error_type="character_not_found",
            message=f"Character {request.character_id} not found in journey-log",
            status_code=status.HTTP_404_NOT_FOUND
        ) from e
    except JourneyLogTimeoutError as e:
        outcome = "error"
        errors.append({"type": "journey_log_timeout", "message": str(e)})
        logger.error("Journey-log timeout", turn_id=turn_id, error=str(e))
        if (collector := get_metrics_collector()):
            collector.record_error("journey_log_timeout")
        raise create_error_response(
            error_type="journey_log_timeout",
            message="Journey-log service timed out. Please try again.",
            status_code=status.HTTP_504_GATEWAY_TIMEOUT
        ) from e
    except JourneyLogClientError as e:
        outcome = "error"
        errors.append({"type": "journey_log_error", "message": str(e)})
        logger.error("Journey-log client error", turn_id=turn_id, error=str(e))
        if (collector := get_metrics_collector()):
            collector.record_error("journey_log_error")
        raise create_error_response(
            error_type="journey_log_error",
            message=f"Failed to communicate with journey-log: {str(e)}",
            status_code=status.HTTP_502_BAD_GATEWAY
        ) from e
    except LLMTimeoutError as e:
        outcome = "error"
        errors.append({"type": "llm_timeout", "message": str(e)})
        logger.error("LLM timeout", turn_id=turn_id, error=str(e))
        if (collector := get_metrics_collector()):
            collector.record_error("llm_timeout")
        raise create_error_response(
            error_type="llm_timeout",
            message="LLM service timed out. Please try again.",
            status_code=status.HTTP_504_GATEWAY_TIMEOUT
        ) from e
    except LLMResponseError as e:
        outcome = "error"
        errors.append({"type": "llm_response_error", "message": str(e)})
        logger.error("LLM response error", turn_id=turn_id, error=str(e))
        if (collector := get_metrics_collector()):
            collector.record_error("llm_response_error")
        raise create_error_response(
            error_type="llm_response_error",
            message=f"LLM returned invalid response: {str(e)}",
            status_code=status.HTTP_502_BAD_GATEWAY
        ) from e
    except LLMClientError as e:
        outcome = "error"
        errors.append({"type": "llm_error", "message": str(e)})
        logger.error("LLM client error", turn_id=turn_id, error=str(e))
        if (collector := get_metrics_collector()):
            collector.record_error("llm_error")
        raise create_error_response(
            error_type="llm_error",
            message=f"Failed to generate narrative: {str(e)}",
            status_code=status.HTTP_502_BAD_GATEWAY
        ) from e
    except Exception as e:
        # Catch-all for unexpected errors
        outcome = "error"
        errors.append({"type": "internal_error", "message": str(e)})
        logger.error(
            "Unexpected error processing turn",
            turn_id=turn_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        if (collector := get_metrics_collector()):
            collector.record_error("internal_error")
        raise create_error_response(
            error_type="internal_error",
            message="An unexpected error occurred while processing your turn",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        ) from e
    finally:
        # Always emit structured turn log and record metrics, even on errors
        if outcome != "success":
            latencies['total_ms'] = (time.time() - turn_start_time) * 1000
            if (collector := get_metrics_collector()):
                collector.record_turn_processed(
                    environment=settings.environment,
                    character_id=request.character_id,
                    outcome="error"
                )
        
        # Emit structured turn log
        turn_logger.log_turn(
            turn_id=turn_id,
            character_id=request.character_id,
            subsystem_actions={
                "quest": subsystem_summary.quest_change.action if subsystem_summary else "none",
                "combat": subsystem_summary.combat_change.action if subsystem_summary else "none",
                "poi": subsystem_summary.poi_change.action if subsystem_summary else "none",
                "narrative": "persisted" if subsystem_summary and subsystem_summary.narrative_persisted else "failed"
            },
            policy_decisions=policy_decisions,
            intent_summary=turn_logger.create_intent_summary(intents) if intents else None,
            latencies=latencies,
            errors=errors if errors else None,
            outcome=outcome
        )
        
        # Store turn detail for admin introspection (if admin endpoints enabled)
        if settings.admin_endpoints_enabled and outcome == "success":
            try:
                from app.turn_storage import TurnDetail
                from datetime import datetime, timezone
                
                # Get turn storage
                from app.main import get_turn_storage
                turn_storage = get_turn_storage()
                
                # Build context snapshot (redacted)
                context_snapshot = {}
                if context:
                    context_snapshot = {
                        "status": context.status,
                        "location": context.location,
                        "has_active_quest": context.policy_state.has_active_quest if context.policy_state else False,
                        "combat_active": context.policy_state.combat_active if context.policy_state else False,
                        "turns_since_last_quest": context.policy_state.turns_since_last_quest if context.policy_state else 0,
                        "turns_since_last_poi": context.policy_state.turns_since_last_poi if context.policy_state else 0
                    }
                
                # Build journey-log writes summary
                journey_log_writes = {}
                if subsystem_summary:
                    journey_log_writes = {
                        "quest": {
                            "action": subsystem_summary.quest_change.action,
                            "success": subsystem_summary.quest_change.success
                        },
                        "combat": {
                            "action": subsystem_summary.combat_change.action,
                            "success": subsystem_summary.combat_change.success
                        },
                        "poi": {
                            "action": subsystem_summary.poi_change.action,
                            "success": subsystem_summary.poi_change.success
                        },
                        "narrative": {
                            "persisted": subsystem_summary.narrative_persisted
                        }
                    }
                
                # Create and store turn detail
                turn_detail = TurnDetail(
                    turn_id=turn_id,
                    character_id=request.character_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    user_action=request.user_action,
                    context_snapshot=context_snapshot,
                    policy_decisions=policy_decisions,
                    llm_narrative=narrative,
                    llm_intents=intents.model_dump() if intents else None,
                    journey_log_writes=journey_log_writes,
                    errors=errors if errors else [],
                    latency_ms=latencies.get('total_ms')
                )
                
                turn_storage.store_turn(turn_detail)
                
                logger.debug(
                    "Turn detail stored for admin introspection",
                    turn_id=turn_id,
                    character_id=request.character_id
                )
            except Exception as e:
                # Don't fail the request if turn storage fails
                logger.warning(
                    "Failed to store turn detail for admin introspection",
                    turn_id=turn_id,
                    error=str(e)
                )


@router.post(
    "/turn/stream",
    status_code=status.HTTP_410_GONE,
    summary="Streaming endpoint removed",
    description=(
        "The streaming narrative endpoint has been removed to simplify the MVP. "
        "All clients should use the synchronous POST /turn endpoint instead. "
        "This endpoint returns HTTP 410 Gone to indicate permanent removal."
    ),
    responses={
        410: {
            "description": "Streaming endpoint permanently removed",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "error": {
                                "type": "endpoint_removed",
                                "message": "Streaming endpoints have been removed. Use POST /turn instead.",
                                "request_id": None
                            }
                        }
                    }
                }
            }
        }
    }
)
async def process_turn_stream_removed(
    request: TurnRequest,
    settings: Settings = Depends(get_settings)
):
    """Streaming endpoint removed - returns 410 Gone.
    
    The streaming narrative endpoint has been disabled to maintain a synchronous
    MVP architecture. All clients should migrate to the POST /turn endpoint which
    provides the same functionality with a simpler, synchronous response model.
    
    Migration:
    - Replace POST /turn/stream calls with POST /turn
    - Expect a single JSON response with narrative, intents, and subsystem_summary
    - Remove SSE/EventSource client code
    
    Args:
        request: Turn request (same model as /turn endpoint)
        settings: Application settings (injected)
        
    Returns:
        HTTPException with 410 Gone status
        
    Raises:
        HTTPException: Always raises 410 Gone with migration guidance
    """
    logger.info(
        "Streaming endpoint called but disabled",
        character_id=request.character_id,
        action_preview=sanitize_for_log(request.user_action, 50)
    )
    
    # Record metrics for monitoring deprecated endpoint usage
    if (collector := get_metrics_collector()):
        collector.record_error("streaming_endpoint_called_after_removal")
    
    raise create_error_response(
        error_type="endpoint_removed",
        message=(
            "Streaming endpoints have been removed to simplify the MVP. "
            "Please use the synchronous POST /turn endpoint instead. "
            "See migration guide in response for details."
        ),
        status_code=status.HTTP_410_GONE
    )


@router.get(
    "/admin/turns/{turn_id}",
    response_model=None,  # We'll return AdminTurnDetail from models
    status_code=status.HTTP_200_OK,
    summary="Get turn details for introspection",
    description=(
        "Admin endpoint to inspect specific turn state for debugging. "
        "Returns comprehensive turn details including input, context snapshot, "
        "policy decisions, LLM output, and journey-log writes. "
        "Requires ADMIN_ENDPOINTS_ENABLED=true. "
        "Relies on Cloud IAM/service-to-service auth (no custom auth)."
    ),
    responses={
        200: {
            "description": "Turn details retrieved successfully",
            "model": "AdminTurnDetail"
        },
        404: {
            "description": "Turn not found or admin endpoints disabled",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "type": "turn_not_found",
                            "message": "Turn not found or has expired",
                            "request_id": None
                        }
                    }
                }
            }
        }
    }
)
async def get_turn_details(
    turn_id: str,
    settings: Settings = Depends(get_settings)
):
    """Get turn details for admin introspection.
    
    Retrieves comprehensive turn state for debugging including:
    - User action input
    - Context snapshot at turn time
    - Policy engine decisions
    - LLM narrative and intents
    - Journey-log writes summary
    - Errors and latency metrics
    
    Args:
        turn_id: Unique turn identifier
        settings: Application settings (injected)
        
    Returns:
        AdminTurnDetail with comprehensive turn state
        
    Raises:
        HTTPException: If admin endpoints disabled or turn not found
    """
    if not settings.admin_endpoints_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin endpoints are disabled. Set ADMIN_ENDPOINTS_ENABLED=true to enable."
        )
    
    # Get turn storage from app state (will be injected via dependency)
    from app.main import get_turn_storage
    turn_storage = get_turn_storage()
    
    # Retrieve turn detail
    turn_detail = turn_storage.get_turn(turn_id)
    
    if turn_detail is None:
        logger.warning(
            "Admin turn lookup failed - not found",
            turn_id=turn_id
        )
        raise create_error_response(
            error_type="turn_not_found",
            message="Turn not found or has expired",
            status_code=status.HTTP_404_NOT_FOUND
        )
    
    logger.info(
        "Admin turn introspection",
        turn_id=turn_id,
        character_id=turn_detail.character_id
    )
    
    # Import AdminTurnDetail here to avoid circular imports
    from app.models import AdminTurnDetail
    
    # Convert to response model with redaction
    turn_dict = turn_detail.to_dict(redact_sensitive=True)
    return AdminTurnDetail(**turn_dict)


@router.get(
    "/admin/characters/{character_id}/recent_turns",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Get recent turns for a character",
    description=(
        "Admin endpoint to list recent turns for a specific character. "
        "Returns turns in reverse chronological order with comprehensive state. "
        "Requires ADMIN_ENDPOINTS_ENABLED=true. "
        "Relies on Cloud IAM/service-to-service auth (no custom auth)."
    ),
    responses={
        200: {
            "description": "Recent turns retrieved successfully",
            "model": "AdminRecentTurnsResponse"
        },
        404: {
            "description": "Admin endpoints disabled"
        }
    }
)
async def get_character_recent_turns(
    character_id: str,
    limit: int = 20,
    settings: Settings = Depends(get_settings)
):
    """Get recent turns for a character.
    
    Retrieves recent turn history for debugging and analysis.
    
    Args:
        character_id: Character UUID
        limit: Maximum number of turns to return (default: 20, max: 100)
        settings: Application settings (injected)
        
    Returns:
        AdminRecentTurnsResponse with list of recent turns
        
    Raises:
        HTTPException: If admin endpoints disabled
    """
    if not settings.admin_endpoints_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin endpoints are disabled. Set ADMIN_ENDPOINTS_ENABLED=true to enable."
        )
    
    # Validate limit
    if limit < 1 or limit > 100:
        raise create_error_response(
            error_type="invalid_limit",
            message="Limit must be between 1 and 100",
            status_code=status.HTTP_400_BAD_REQUEST
        )
    
    # Get turn storage from app state
    from app.main import get_turn_storage
    turn_storage = get_turn_storage()
    
    # Retrieve recent turns
    turn_details = turn_storage.get_character_recent_turns(
        character_id=character_id,
        limit=limit
    )
    
    logger.info(
        "Admin character recent turns lookup",
        character_id=character_id,
        limit=limit,
        found_count=len(turn_details)
    )
    
    # Import models
    from app.models import AdminTurnDetail, AdminRecentTurnsResponse
    
    # Convert to response models with redaction
    turns_list = [
        AdminTurnDetail(**turn.to_dict(redact_sensitive=True))
        for turn in turn_details
    ]
    
    return AdminRecentTurnsResponse(
        character_id=character_id,
        turns=turns_list,
        total_count=len(turns_list),
        limit=limit
    )


@router.get(
    "/admin/policy/config",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Get current policy configuration",
    description=(
        "Admin endpoint to inspect current policy configuration. "
        "Returns quest/POI probabilities and cooldowns. "
        "Requires ADMIN_ENDPOINTS_ENABLED=true."
    ),
    responses={
        200: {
            "description": "Policy config retrieved successfully",
            "model": "PolicyConfigResponse"
        },
        404: {"description": "Admin endpoints disabled"}
    }
)
async def get_policy_config(
    settings: Settings = Depends(get_settings)
):
    """Get current policy configuration.
    
    Returns current policy parameters for inspection.
    
    Args:
        settings: Application settings (injected)
        
    Returns:
        PolicyConfigResponse with current config
        
    Raises:
        HTTPException: If admin endpoints disabled
    """
    if not settings.admin_endpoints_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin endpoints are disabled. Set ADMIN_ENDPOINTS_ENABLED=true to enable."
        )
    
    # Get policy config manager from app state
    from app.main import get_policy_config_manager
    config_manager = get_policy_config_manager()
    
    current_config = config_manager.get_current_config()
    
    # Import model
    from app.models import PolicyConfigResponse
    
    if current_config is None:
        # No config loaded yet - return defaults from settings
        return PolicyConfigResponse(
            quest_trigger_prob=settings.quest_trigger_prob,
            quest_cooldown_turns=settings.quest_cooldown_turns,
            poi_trigger_prob=settings.poi_trigger_prob,
            poi_cooldown_turns=settings.poi_cooldown_turns,
            memory_spark_probability=settings.memory_spark_probability,
            quest_poi_reference_probability=settings.quest_poi_reference_probability,
            last_updated=None
        )
    
    # Get last audit log for timestamp
    audit_logs = config_manager.get_audit_logs(limit=1)
    last_updated = audit_logs[0].timestamp if audit_logs else None
    
    return PolicyConfigResponse(
        quest_trigger_prob=current_config.quest_trigger_prob,
        quest_cooldown_turns=current_config.quest_cooldown_turns,
        poi_trigger_prob=current_config.poi_trigger_prob,
        poi_cooldown_turns=current_config.poi_cooldown_turns,
        memory_spark_probability=current_config.memory_spark_probability,
        quest_poi_reference_probability=current_config.quest_poi_reference_probability,
        last_updated=last_updated
    )


@router.post(
    "/admin/policy/reload",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Reload policy configuration",
    description=(
        "Admin endpoint to manually reload policy configuration from file "
        "or provided values. Validates config before applying and rolls back "
        "on errors. Requires ADMIN_ENDPOINTS_ENABLED=true."
    ),
    responses={
        200: {
            "description": "Policy config reloaded successfully",
            "model": "PolicyConfigReloadResponse"
        },
        400: {
            "description": "Invalid config values",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "type": "config_validation_failed",
                            "message": "Validation error details...",
                            "request_id": None
                        }
                    }
                }
            }
        },
        404: {"description": "Admin endpoints disabled"}
    }
)
async def reload_policy_config(
    request_body: "PolicyConfigReloadRequest",
    settings: Settings = Depends(get_settings)
):
    """Reload policy configuration from file or provided values.
    
    Triggers runtime config reload with validation and rollback on errors.
    Updates PolicyEngine with new values if successful.
    
    Args:
        request_body: Request with optional config values and actor identity
        settings: Application settings (injected)
        
    Returns:
        PolicyConfigReloadResponse with success status and current config
        
    Raises:
        HTTPException: If admin endpoints disabled or validation fails
    """
    if not settings.admin_endpoints_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin endpoints are disabled. Set ADMIN_ENDPOINTS_ENABLED=true to enable."
        )
    
    # Import models
    from app.models import PolicyConfigReloadRequest, PolicyConfigReloadResponse, PolicyConfigResponse
    
    # Get managers from app state
    from app.main import get_policy_config_manager, get_policy_engine
    config_manager = get_policy_config_manager()
    policy_engine = get_policy_engine()
    
    # Determine actor (use provided or default)
    actor = request_body.actor or "admin_api"
    
    # Load config (from dict or file)
    success, error = config_manager.load_config(
        actor=actor,
        config_dict=request_body.config
    )
    
    if not success:
        logger.error(
            "Policy config reload failed",
            actor=actor,
            error=error
        )
        raise create_error_response(
            error_type="config_validation_failed",
            message=error or "Config validation failed",
            status_code=status.HTTP_400_BAD_REQUEST
        )
    
    # Update PolicyEngine with new config
    current_config = config_manager.get_current_config()
    if current_config:
        policy_engine.update_config(
            quest_trigger_prob=current_config.quest_trigger_prob,
            quest_cooldown_turns=current_config.quest_cooldown_turns,
            poi_trigger_prob=current_config.poi_trigger_prob,
            poi_cooldown_turns=current_config.poi_cooldown_turns,
            memory_spark_probability=current_config.memory_spark_probability,
            quest_poi_reference_probability=current_config.quest_poi_reference_probability
        )
    
    logger.info(
        "Policy config reloaded successfully",
        actor=actor
    )
    
    # Get last audit log for timestamp
    audit_logs = config_manager.get_audit_logs(limit=1)
    last_updated = audit_logs[0].timestamp if audit_logs else None
    
    # Build response
    config_response = None
    if current_config:
        config_response = PolicyConfigResponse(
            quest_trigger_prob=current_config.quest_trigger_prob,
            quest_cooldown_turns=current_config.quest_cooldown_turns,
            poi_trigger_prob=current_config.poi_trigger_prob,
            poi_cooldown_turns=current_config.poi_cooldown_turns,
            memory_spark_probability=current_config.memory_spark_probability,
            quest_poi_reference_probability=current_config.quest_poi_reference_probability,
            last_updated=last_updated
        )
    
    return PolicyConfigReloadResponse(
        success=True,
        message="Policy configuration reloaded successfully",
        error=None,
        config=config_response
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
            logger.debug("Pinging journey-log service")
            response = await http_client.get(
                f"{settings.journey_log_base_url}/health",
                timeout=5.0  # Short timeout for health checks
            )
            journey_log_accessible = response.status_code == 200

            if not journey_log_accessible:
                logger.warning(
                    "Journey-log health check returned non-200 status",
                    status_code=response.status_code
                )
                service_status = "degraded"
        except Exception as e:
            logger.warning("Journey-log health check failed", error=str(e))
            journey_log_accessible = False
            service_status = "degraded"

    return HealthResponse(
        status=service_status,
        service=settings.service_name,
        journey_log_accessible=journey_log_accessible
    )


@router.get(
    "/metrics",
    status_code=status.HTTP_200_OK,
    summary="Metrics endpoint",
    description=(
        "Get service metrics including request counts, error rates, and latencies. "
        "Only available when ENABLE_METRICS is true. Returns 404 if metrics are disabled."
    ),
    responses={
        200: {
            "description": "Metrics collected",
            "content": {
                "application/json": {
                    "example": {
                        "uptime_seconds": 3600.0,
                        "requests": {
                            "total": 150,
                            "success": 145,
                            "errors": 5,
                            "by_status_code": {
                                "200": 145,
                                "404": 3,
                                "502": 2
                            }
                        },
                        "errors": {
                            "by_type": {
                                "character_not_found": 3,
                                "llm_error": 2
                            }
                        },
                        "latencies": {
                            "turn": {
                                "count": 145,
                                "avg_ms": 1250.5,
                                "min_ms": 800.2,
                                "max_ms": 3200.8
                            },
                            "llm_call": {
                                "count": 145,
                                "avg_ms": 950.3,
                                "min_ms": 600.1,
                                "max_ms": 2500.5
                            }
                        }
                    }
                }
            }
        },
        404: {"description": "Metrics disabled"}
    }
)
async def get_metrics(settings: Settings = Depends(get_settings)):
    """Get service metrics.
    
    Returns collected metrics including request counts, error rates, and latencies.
    Only available when ENABLE_METRICS configuration is enabled.
    
    Args:
        settings: Application settings (injected)
        
    Returns:
        Dictionary with metrics data
        
    Raises:
        HTTPException: If metrics are disabled
    """
    if not settings.enable_metrics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metrics endpoint is disabled. Set ENABLE_METRICS=true to enable."
        )
    
    collector = get_metrics_collector()
    if not collector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metrics collector not initialized"
        )
    
    return collector.get_metrics()


@router.post(
    "/debug/parse_llm",
    status_code=status.HTTP_200_OK,
    summary="Debug endpoint to test LLM response parsing",
    description=(
        "Test the outcome parser with raw LLM response JSON. "
        "Only available when ENABLE_DEBUG_ENDPOINTS is true. "
        "This endpoint is intended for local development and debugging only. "
        "It validates the response against the DungeonMasterOutcome schema and "
        "returns detailed parsing results including any validation errors."
    ),
    responses={
        200: {
            "description": "Parse results with validation status",
            "content": {
                "application/json": {
                    "example": {
                        "is_valid": True,
                        "narrative": "You discover a treasure chest...",
                        "has_outcome": True,
                        "error_type": None,
                        "error_details": None,
                        "intents_summary": {
                            "has_quest_intent": False,
                            "has_combat_intent": False,
                            "has_poi_intent": True,
                            "has_meta_intent": True
                        }
                    }
                }
            }
        },
        404: {"description": "Debug endpoints disabled"}
    }
)
async def debug_parse_llm(
    request: DebugParseRequest,
    settings: Settings = Depends(get_settings)
):
    """Debug endpoint to test LLM response parsing.
    
    Accepts raw JSON that would be returned from the LLM and validates it
    against the DungeonMasterOutcome schema. Returns detailed parsing results
    including validation status, extracted narrative, and any errors.
    
    Only available when ENABLE_DEBUG_ENDPOINTS configuration is enabled.
    This endpoint should NOT be enabled in production environments.
    
    Args:
        request: Pydantic model with "llm_response" and optional "trace_id"
        settings: Application settings (injected)
        
    Returns:
        Dictionary with parsing results and validation details
        
    Raises:
        HTTPException: If debug endpoints are disabled
    """
    if not settings.enable_debug_endpoints:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Debug endpoints are disabled. Set ENABLE_DEBUG_ENDPOINTS=true to enable."
        )
    
    # Parse the response using the outcome parser
    parser = OutcomeParser()
    parsed = parser.parse(request.llm_response, trace_id=request.trace_id)
    
    # Build summary of intents if outcome is valid
    intents_summary = None
    if parsed.is_valid and parsed.outcome and parsed.outcome.intents:
        intents_summary = {
            "has_quest_intent": parsed.outcome.intents.quest_intent is not None,
            "has_combat_intent": parsed.outcome.intents.combat_intent is not None,
            "has_poi_intent": parsed.outcome.intents.poi_intent is not None,
            "has_meta_intent": parsed.outcome.intents.meta is not None
        }
    
    return {
        "is_valid": parsed.is_valid,
        "narrative": parsed.narrative,
        "has_outcome": parsed.outcome is not None,
        "error_type": parsed.error_type,
        "error_details": parsed.error_details,
        "intents_summary": intents_summary,
        "schema_version": parser.schema_version
    }
