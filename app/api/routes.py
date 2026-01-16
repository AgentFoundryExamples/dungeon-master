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
import re

from app.models import TurnRequest, TurnResponse, HealthResponse, DebugParseRequest, PolicyHints
from app.config import get_settings, Settings
from app.services.journey_log_client import (
    JourneyLogClient,
    JourneyLogNotFoundError,
    JourneyLogTimeoutError,
    JourneyLogClientError
)
from app.services.llm_client import (
    LLMClient,
    LLMTimeoutError,
    LLMResponseError,
    LLMClientError
)
from app.services.policy_engine import PolicyEngine
from app.services.outcome_parser import OutcomeParser
from app.prompting.prompt_builder import PromptBuilder
from app.logging import (
    StructuredLogger,
    PhaseTimer,
    set_character_id,
    get_request_id
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
        500: {"description": "Internal server error"},
    }
)
async def process_turn(
    request: TurnRequest,
    journey_log_client: JourneyLogClient = Depends(get_journey_log_client),
    llm_client: LLMClient = Depends(get_llm_client),
    policy_engine: PolicyEngine = Depends(get_policy_engine),
    settings: Settings = Depends(get_settings)
) -> TurnResponse:
    """Process a player turn and generate narrative response.
    
    Full orchestration flow:
    1. Validate request
    2. Fetch context from journey-log
    3. Evaluate PolicyEngine for quest and POI trigger decisions
    4. Inject policy_hints into context
    5. Build prompt using PromptBuilder
    6. Call LLM for narrative generation
    7. Apply policy guardrails to intents
    8. Persist user_action + narrative to journey-log
    9. Return TurnResponse
    
    Args:
        request: Turn request with character_id and user_action
        journey_log_client: JourneyLogClient for journey-log communication (injected)
        llm_client: LLMClient for LLM communication (injected)
        policy_engine: PolicyEngine for policy decisions (injected)
        settings: Application settings (injected)
        
    Returns:
        TurnResponse with generated narrative
        
    Raises:
        HTTPException: If request validation fails or processing error occurs
    """
    # Set character_id in context for logging correlation
    set_character_id(request.character_id)
    
    # Sanitize inputs for logging to prevent log injection
    safe_character_id = sanitize_for_log(request.character_id, 36)
    safe_action = sanitize_for_log(request.user_action, 50)

    logger.info(
        "Processing turn request",
        character_id=safe_character_id,
        action_preview=safe_action
    )

    try:
        prompt_builder = PromptBuilder()

        # Step 1: Fetch context from journey-log
        with PhaseTimer("context_fetch", logger), MetricsTimer("journey_log_fetch"):
            logger.debug("Fetching context from journey-log")
            context = await journey_log_client.get_context(
                character_id=request.character_id,
                trace_id=request.trace_id
            )

        # Step 2: Evaluate PolicyEngine for quest and POI trigger decisions
        with PhaseTimer("policy_evaluation", logger), MetricsTimer("policy_evaluation"):
            logger.debug("Evaluating policy decisions")
            
            # Evaluate quest trigger
            quest_decision = policy_engine.evaluate_quest_trigger(
                character_id=request.character_id,
                turns_since_last_quest=context.policy_state.turns_since_last_quest,
                has_active_quest=context.policy_state.has_active_quest
            )
            
            # Evaluate POI trigger
            poi_decision = policy_engine.evaluate_poi_trigger(
                character_id=request.character_id,
                turns_since_last_poi=context.policy_state.turns_since_last_poi
            )
            
            # Create policy hints
            policy_hints = PolicyHints(
                quest_trigger_decision=quest_decision,
                poi_trigger_decision=poi_decision
            )
            
            # Inject policy hints into context
            context.policy_hints = policy_hints
            
            # Log policy decisions for observability
            logger.info(
                "Policy decisions evaluated",
                quest_eligible=quest_decision.eligible,
                quest_roll_passed=quest_decision.roll_passed,
                poi_eligible=poi_decision.eligible,
                poi_roll_passed=poi_decision.roll_passed
            )
            
            # Metrics for policy evaluations are recorded by the MetricsTimer

        # Step 3: Build prompt
        with PhaseTimer("prompt_build", logger):
            logger.debug("Building prompt from context and user action")
            system_instructions, user_prompt = prompt_builder.build_prompt(
                context=context,
                user_action=request.user_action
            )

        # Step 4: Call LLM for narrative generation
        with PhaseTimer("llm_call", logger), MetricsTimer("llm_call"):
            logger.debug("Generating narrative with LLM")
            parsed_outcome = await llm_client.generate_narrative(
                system_instructions=system_instructions,
                user_prompt=user_prompt,
                trace_id=request.trace_id
            )
        
        # Extract narrative from parsed outcome (always available even if invalid)
        narrative = parsed_outcome.narrative
        
        # Log if we're using fallback narrative
        if not parsed_outcome.is_valid:
            logger.warning(
                "Using fallback narrative due to validation failure",
                error_type=parsed_outcome.error_type,
                error_count=len(parsed_outcome.error_details) if parsed_outcome.error_details else 0
            )

        # Step 5: Apply policy guardrails to intents
        intents = None
        if parsed_outcome.is_valid and parsed_outcome.outcome and parsed_outcome.outcome.intents:
            intents = parsed_outcome.outcome.intents
            
            # Enforce quest guardrail: ignore quest intent if roll didn't pass
            if intents.quest_intent and intents.quest_intent.action == "offer":
                if not quest_decision.roll_passed:
                    logger.info(
                        "Ignoring quest intent due to policy guardrail",
                        quest_eligible=quest_decision.eligible,
                        quest_roll_passed=quest_decision.roll_passed
                    )
                    # Set quest intent to "none" to enforce guardrail
                    intents.quest_intent.action = "none"
            
            # Enforce POI guardrail: ignore POI creation if roll didn't pass
            if intents.poi_intent and intents.poi_intent.action == "create":
                if not poi_decision.roll_passed:
                    logger.info(
                        "Ignoring POI intent due to policy guardrail",
                        poi_eligible=poi_decision.eligible,
                        poi_roll_passed=poi_decision.roll_passed
                    )
                    # Set POI intent to "none" to enforce guardrail
                    intents.poi_intent.action = "none"

        # Step 6: Persist to journey-log
        with PhaseTimer("narrative_save", logger), MetricsTimer("journey_log_persist"):
            logger.debug("Persisting narrative to journey-log")
            await journey_log_client.persist_narrative(
                character_id=request.character_id,
                user_action=request.user_action,
                narrative=narrative,
                trace_id=request.trace_id
            )

        # Step 7: Return response with narrative and intents
        logger.info(
            "Successfully processed turn",
            narrative_length=len(narrative),
            has_intents=intents is not None
        )
        return TurnResponse(narrative=narrative, intents=intents)

    except JourneyLogNotFoundError as e:
        logger.error("Character not found", error=str(e))
        if (collector := get_metrics_collector()):
            collector.record_error("character_not_found")
        raise create_error_response(
            error_type="character_not_found",
            message=f"Character {request.character_id} not found in journey-log",
            status_code=status.HTTP_404_NOT_FOUND
        ) from e
    except JourneyLogTimeoutError as e:
        logger.error("Journey-log timeout", error=str(e))
        if (collector := get_metrics_collector()):
            collector.record_error("journey_log_timeout")
        raise create_error_response(
            error_type="journey_log_timeout",
            message="Journey-log service timed out. Please try again.",
            status_code=status.HTTP_504_GATEWAY_TIMEOUT
        ) from e
    except JourneyLogClientError as e:
        logger.error("Journey-log client error", error=str(e))
        if (collector := get_metrics_collector()):
            collector.record_error("journey_log_error")
        raise create_error_response(
            error_type="journey_log_error",
            message=f"Failed to communicate with journey-log: {str(e)}",
            status_code=status.HTTP_502_BAD_GATEWAY
        ) from e
    except LLMTimeoutError as e:
        logger.error("LLM timeout", error=str(e))
        if (collector := get_metrics_collector()):
            collector.record_error("llm_timeout")
        raise create_error_response(
            error_type="llm_timeout",
            message="LLM service timed out. Please try again.",
            status_code=status.HTTP_504_GATEWAY_TIMEOUT
        ) from e
    except LLMResponseError as e:
        logger.error("LLM response error", error=str(e))
        if (collector := get_metrics_collector()):
            collector.record_error("llm_response_error")
        raise create_error_response(
            error_type="llm_response_error",
            message=f"LLM returned invalid response: {str(e)}",
            status_code=status.HTTP_502_BAD_GATEWAY
        ) from e
    except LLMClientError as e:
        logger.error("LLM client error", error=str(e))
        if (collector := get_metrics_collector()):
            collector.record_error("llm_error")
        raise create_error_response(
            error_type="llm_error",
            message=f"Failed to generate narrative: {str(e)}",
            status_code=status.HTTP_502_BAD_GATEWAY
        ) from e
    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(
            "Unexpected error processing turn",
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
