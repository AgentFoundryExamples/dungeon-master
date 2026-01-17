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
- POST /turn/stream: Process a turn with streaming narrative delivery (PLANNED - see below)
- GET /health: Service health check with optional journey-log ping
- GET /metrics: Service metrics (optional, requires ENABLE_METRICS=true)
- POST /debug/parse_llm: Debug endpoint for LLM parsing (optional, requires ENABLE_DEBUG_ENDPOINTS=true)

STREAMING ENDPOINT INTEGRATION NOTES (PLANNED):
---------------------------------------------
A future streaming endpoint (POST /turn/stream) will be added to support progressive
narrative delivery via Server-Sent Events (SSE) or WebSocket.

Planned endpoint signature:
    @router.post("/turn/stream")
    async def process_turn_stream(
        request: TurnRequest,
        transport_type: TransportType = TransportType.SSE
    ) -> StreamingResponse | WebSocketConnection

Streaming flow:
1. Accept same TurnRequest as /turn endpoint (backward compatible request model)
2. Fetch context from journey-log (same as /turn)
3. Evaluate policy decisions (same as /turn)
4. Stream narrative tokens to client in real-time via StreamTransport
   - Send "token" events as LLM generates text
   - Buffer tokens internally for validation and journey-log persistence
5. After streaming complete, validate DungeonMasterOutcome schema
6. Execute subsystem writes in deterministic order (quest → combat → POI → narrative)
7. Send "complete" event with intents and subsystem_summary
8. Close transport connection

Key differences from /turn:
- Progressive narrative delivery (tokens streamed in real-time)
- Event-based protocol (token, metadata, complete, error events)
- Long-lived connection (SSE/WebSocket vs single HTTP response)
- Same validation and write logic (deferred to Phase 2 after streaming)

Backward compatibility:
- Existing /turn endpoint remains unchanged
- Legacy clients unaffected
- Same TurnRequest model used
- Same DungeonMasterOutcome schema enforced

When implementing:
- Use StreamTransport abstraction (SSETransport or WebSocketTransport)
- Use NarrativeBuffer to accumulate tokens for replay to journey-log
- Use StreamingLLMClient.generate_narrative_stream() for token streaming
- Reuse existing TurnOrchestrator subsystem write logic (Phase 2)
- Follow event contracts defined in STREAMING_ARCHITECTURE.md

See STREAMING_ARCHITECTURE.md for complete design, event contracts, and failure handling.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from httpx import AsyncClient
import re
import asyncio
import json

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
    get_request_id
)
from app.metrics import get_metrics_collector, MetricsTimer
from app.streaming import StreamEvent, SSETransport, TransportError

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
    turn_orchestrator: TurnOrchestrator = Depends(get_turn_orchestrator),
    settings: Settings = Depends(get_settings)
) -> TurnResponse:
    """Process a player turn and generate narrative response.
    
    Full orchestration flow (delegated to TurnOrchestrator):
    1. Fetch context from journey-log
    2. Evaluate PolicyEngine for quest and POI trigger decisions
    3. Inject policy_hints into context
    4. Build prompt using PromptBuilder
    5. Call LLM for narrative generation
    6. Parse intents and apply policy guardrails
    7. Derive subsystem actions from policy and intents
    8. Execute writes in deterministic order (quest → combat → POI → narrative)
    9. Return TurnResponse with narrative, intents, and subsystem_summary
    
    Args:
        request: Turn request with character_id and user_action
        journey_log_client: JourneyLogClient for journey-log communication (injected)
        turn_orchestrator: TurnOrchestrator for turn processing (injected)
        settings: Application settings (injected)
        
    Returns:
        TurnResponse with generated narrative, intents, and subsystem summary
        
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
        # Step 1: Fetch context from journey-log
        with PhaseTimer("context_fetch", logger), MetricsTimer("journey_log_fetch"):
            logger.debug("Fetching context from journey-log")
            context = await journey_log_client.get_context(
                character_id=request.character_id,
                trace_id=request.trace_id
            )

        # Step 2-9: Delegate to TurnOrchestrator for deterministic processing
        with PhaseTimer("turn_orchestration", logger), MetricsTimer("turn"):
            logger.debug("Orchestrating turn with TurnOrchestrator")
            narrative, intents, subsystem_summary = await turn_orchestrator.orchestrate_turn(
                character_id=request.character_id,
                user_action=request.user_action,
                context=context,
                trace_id=request.trace_id,
                dry_run=False
            )
        
        # Log orchestration results
        logger.info(
            "Successfully processed turn",
            narrative_length=len(narrative),
            has_intents=intents is not None,
            quest_change=subsystem_summary.quest_change.action,
            combat_change=subsystem_summary.combat_change.action,
            poi_change=subsystem_summary.poi_created.action,
            narrative_persisted=subsystem_summary.narrative_persisted
        )
        
        return TurnResponse(
            narrative=narrative,
            intents=intents,
            subsystem_summary=subsystem_summary
        )

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


@router.post(
    "/turn/stream",
    status_code=status.HTTP_200_OK,
    summary="Process a player turn with streaming narrative delivery",
    description=(
        "Process a player's turn action and stream the AI narrative response progressively. "
        "This endpoint streams narrative tokens to the client using Server-Sent Events (SSE) "
        "while buffering tokens internally for validation and persistence. After streaming "
        "completes, the endpoint validates the complete narrative, executes subsystem writes "
        "in deterministic order (quest → combat → POI → narrative), and sends a final "
        "completion event with intents and subsystem summary."
    ),
    responses={
        200: {
            "description": "Streaming narrative generation with SSE",
            "content": {
                "text/event-stream": {
                    "example": (
                        'data: {"type":"token","content":"You ","timestamp":"2025-01-17T..."}\n\n'
                        'data: {"type":"token","content":"enter ","timestamp":"2025-01-17T..."}\n\n'
                        'data: {"type":"complete","intents":{...},"subsystem_summary":{...}}\n\n'
                        'data: [DONE]\n\n'
                    )
                }
            }
        },
        400: {"description": "Invalid request (malformed UUID, etc.)"},
        404: {"description": "Character not found"},
        500: {"description": "Internal server error"},
    }
)
async def process_turn_stream(
    request: TurnRequest,
    journey_log_client: JourneyLogClient = Depends(get_journey_log_client),
    turn_orchestrator: TurnOrchestrator = Depends(get_turn_orchestrator),
    settings: Settings = Depends(get_settings)
) -> StreamingResponse:
    """Process a player turn with streaming narrative delivery.
    
    This endpoint implements the two-phase streaming architecture:
    
    Phase 1 (Token Streaming):
    - Fetch context from journey-log
    - Evaluate PolicyEngine for quest and POI trigger decisions
    - Stream narrative tokens to client via SSE as they're generated
    - Buffer tokens internally for Phase 2 validation
    
    Phase 2 (Validation & Writes):
    - Parse complete narrative against DungeonMasterOutcome schema
    - Normalize intents with quest/POI fallbacks
    - Execute subsystem writes in deterministic order (quest → combat → POI → narrative)
    - Send complete event with intents and subsystem summary
    
    The endpoint maintains the same validation guarantees and subsystem write ordering
    as the synchronous /turn endpoint, but provides progressive narrative delivery for
    improved perceived latency.
    
    Args:
        request: Turn request with character_id and user_action
        journey_log_client: JourneyLogClient for journey-log communication (injected)
        turn_orchestrator: TurnOrchestrator for turn processing (injected)
        settings: Application settings (injected)
        
    Returns:
        StreamingResponse with SSE events (tokens, complete, error)
        
    Raises:
        HTTPException: If request validation fails or processing error occurs
    """
    # Set character_id in context for logging correlation
    set_character_id(request.character_id)
    
    # Sanitize inputs for logging to prevent log injection
    safe_character_id = sanitize_for_log(request.character_id, 36)
    safe_action = sanitize_for_log(request.user_action, 50)

    logger.info(
        "Processing streaming turn request",
        character_id=safe_character_id,
        action_preview=safe_action
    )
    
    # Define the async generator for SSE streaming
    async def event_stream():
        """Async generator that yields SSE-formatted events."""
        # Queue for passing events from callback to generator
        event_queue = asyncio.Queue()
        transport_error = None
        
        # Callback for receiving tokens from LLM streaming
        async def token_callback(token: str):
            """Callback invoked by LLM client for each token."""
            await event_queue.put(("token", token))
        
        # Background task to orchestrate turn and stream events
        async def orchestrate_and_stream():
            nonlocal transport_error
            try:
                # Step 1: Fetch context from journey-log
                with PhaseTimer("context_fetch", logger), MetricsTimer("journey_log_fetch"):
                    logger.debug("Fetching context from journey-log")
                    context = await journey_log_client.get_context(
                        character_id=request.character_id,
                        trace_id=request.trace_id
                    )

                # Step 2: Orchestrate turn with streaming (Phase 1 + Phase 2)
                with PhaseTimer("turn_orchestration_stream", logger), MetricsTimer("turn_stream"):
                    logger.debug("Orchestrating streaming turn with TurnOrchestrator")
                    narrative, intents, subsystem_summary = await turn_orchestrator.orchestrate_turn_stream(
                        character_id=request.character_id,
                        user_action=request.user_action,
                        context=context,
                        callback=token_callback,
                        trace_id=request.trace_id,
                        dry_run=False
                    )
                
                # Log orchestration results
                logger.info(
                    "Successfully processed streaming turn",
                    narrative_length=len(narrative),
                    has_intents=intents is not None,
                    quest_change=subsystem_summary.quest_change.action,
                    combat_change=subsystem_summary.combat_change.action,
                    poi_change=subsystem_summary.poi_created.action,
                    narrative_persisted=subsystem_summary.narrative_persisted
                )
                
                # Send complete event
                await event_queue.put(("complete", {
                    "intents": intents.model_dump() if intents else None,
                    "subsystem_summary": subsystem_summary.model_dump()
                }))
                
            except JourneyLogNotFoundError as e:
                logger.error("Character not found", error=str(e))
                if (collector := get_metrics_collector()):
                    collector.record_error("character_not_found")
                await event_queue.put(("error", {
                    "error_type": "character_not_found",
                    "message": f"Character {request.character_id} not found in journey-log",
                    "recoverable": False
                }))
            except JourneyLogTimeoutError as e:
                logger.error("Journey-log timeout", error=str(e))
                if (collector := get_metrics_collector()):
                    collector.record_error("journey_log_timeout")
                await event_queue.put(("error", {
                    "error_type": "journey_log_timeout",
                    "message": "Journey-log service timed out. Please try again.",
                    "recoverable": True
                }))
            except JourneyLogClientError as e:
                logger.error("Journey-log client error", error=str(e))
                if (collector := get_metrics_collector()):
                    collector.record_error("journey_log_error")
                await event_queue.put(("error", {
                    "error_type": "journey_log_error",
                    "message": f"Failed to communicate with journey-log: {str(e)}",
                    "recoverable": False
                }))
            except LLMTimeoutError as e:
                logger.error("LLM timeout", error=str(e))
                if (collector := get_metrics_collector()):
                    collector.record_error("llm_timeout")
                await event_queue.put(("error", {
                    "error_type": "llm_timeout",
                    "message": "LLM service timed out. Please try again.",
                    "recoverable": True
                }))
            except LLMResponseError as e:
                logger.error("LLM response error", error=str(e))
                if (collector := get_metrics_collector()):
                    collector.record_error("llm_response_error")
                await event_queue.put(("error", {
                    "error_type": "llm_response_error",
                    "message": f"LLM returned invalid response: {str(e)}",
                    "recoverable": False
                }))
            except LLMClientError as e:
                logger.error("LLM client error", error=str(e))
                if (collector := get_metrics_collector()):
                    collector.record_error("llm_error")
                await event_queue.put(("error", {
                    "error_type": "llm_error",
                    "message": f"Failed to generate narrative: {str(e)}",
                    "recoverable": False
                }))
            except Exception as e:
                # Catch-all for unexpected errors
                logger.error(
                    "Unexpected error processing streaming turn",
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True
                )
                if (collector := get_metrics_collector()):
                    collector.record_error("internal_error")
                await event_queue.put(("error", {
                    "error_type": "internal_error",
                    "message": "An unexpected error occurred while processing your turn",
                    "recoverable": False
                }))
            finally:
                # Signal end of stream
                await event_queue.put(None)
        
        # Start background orchestration task
        orchestration_task = asyncio.create_task(orchestrate_and_stream())
        
        try:
            # Yield events from queue as they arrive
            while True:
                event = await event_queue.get()
                
                if event is None:
                    # End of stream
                    break
                
                event_type, event_data = event
                
                if event_type == "token":
                    # Stream token event
                    stream_event = StreamEvent(
                        type="token",
                        data={"content": event_data}
                    )
                    payload = {"type": stream_event.type, "timestamp": stream_event.timestamp}
                    payload.update(stream_event.data)
                    yield f"data: {json.dumps(payload)}\n\n".encode('utf-8')
                    
                elif event_type == "complete":
                    # Stream complete event
                    stream_event = StreamEvent(
                        type="complete",
                        data=event_data
                    )
                    payload = {"type": stream_event.type, "timestamp": stream_event.timestamp}
                    payload.update(stream_event.data)
                    yield f"data: {json.dumps(payload)}\n\n".encode('utf-8')
                    
                elif event_type == "error":
                    # Stream error event
                    stream_event = StreamEvent(
                        type="error",
                        data=event_data
                    )
                    payload = {"type": stream_event.type, "timestamp": stream_event.timestamp}
                    payload.update(stream_event.data)
                    yield f"data: {json.dumps(payload)}\n\n".encode('utf-8')
            
            # Send SSE [DONE] marker
            yield b"data: [DONE]\n\n"
            
        except asyncio.CancelledError:
            # Client disconnected
            logger.info("Client disconnected during streaming turn")
            # Cancel orchestration task if still running
            orchestration_task.cancel()
            try:
                await orchestration_task
            except asyncio.CancelledError:
                pass
            raise
        except Exception as e:
            logger.error(
                "Error in streaming event generator",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            raise
    
    # Return StreamingResponse with SSE content type
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
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
