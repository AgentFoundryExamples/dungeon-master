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
"""LLM client for narrative generation using OpenAI Responses API."""

import time
import asyncio
from typing import Optional, Callable, AsyncIterator, Protocol
from openai import AsyncOpenAI
import openai

from app.logging import StructuredLogger, redact_secrets, get_turn_id
from app.models import (
    DungeonMasterOutcome,
    get_outcome_json_schema,
    IntentsBlock,
    QuestIntent,
    CombatIntent,
    POIIntent
)
from app.services.outcome_parser import OutcomeParser, ParsedOutcome
from app.metrics import get_metrics_collector

logger = StructuredLogger(__name__)


class StreamingCallback(Protocol):
    """Protocol for streaming token callbacks.
    
    Callbacks receive individual tokens as they're generated and can be used
    to write tokens to transport layers (SSE, WebSocket, etc.).
    
    Callbacks should not raise exceptions. If they do, the exception will be
    logged and streaming will continue.
    
    Note: Callbacks are async to prevent event loop blocking during I/O operations.
    """
    
    async def __call__(self, token: str) -> None:
        """Process a streaming token.
        
        Args:
            token: A chunk of text from the LLM stream
        """
        ...


class LLMClientError(Exception):
    """Base exception for LLM client errors."""
    pass


class LLMConfigurationError(LLMClientError):
    """Raised when LLM client configuration is invalid."""
    pass


class LLMTimeoutError(LLMClientError):
    """Raised when LLM request times out."""
    pass


class LLMResponseError(LLMClientError):
    """Raised when LLM response is invalid or missing required data."""
    pass


class LLMClient:
    """Client for interacting with OpenAI's Responses API.
    
    This client:
    - Uses the OpenAI Responses API (gpt-5.1)
    - Enforces JSON-only output with DungeonMasterOutcome schema
    - Uses response_format with strict JSON schema validation
    - Returns structured DungeonMasterOutcome objects (or narrative string for backward compatibility)
    - Handles errors and provides fallback mechanisms
    - Supports stub/mock mode for offline development
    
    The client enforces strict JSON output to ensure:
    - LLM only returns valid JSON matching DungeonMasterOutcome schema
    - No prose or explanatory text outside JSON structure
    - Rich narrative text is in the 'narrative' field
    - Concise intents are in structured 'intents' block
    
    Token Usage Considerations:
    - Schema injection adds ~9KB per request (acceptable for GPT-5+ 128K context)
    - History includes up to 20 turns (~5KB)
    - Total overhead: ~14KB per request
    - Monitor token consumption in production; consider fallback strategies
      for cost control or older models with smaller context windows
    
    When models evolve:
    - Update get_outcome_json_schema() in models.py
    - Test with new model to ensure schema compatibility
    - The schema is automatically used in all API calls
    
    STREAMING INTEGRATION NOTES:
    --------------------------
    This synchronous client will be extended by StreamingLLMClient to support
    token streaming while maintaining the existing generate_narrative() interface.
    
    Key extension points for streaming:
    1. generate_narrative_stream(): New async generator yielding tokens as they're generated
    2. Internal buffer: Accumulate tokens during streaming for replay to journey-log
    3. Validation deferred: Schema checking happens after all tokens received (Phase 2)
    4. Backward compatibility: Existing generate_narrative() remains unchanged for /turn endpoint
    
    The DungeonMasterOutcome schema remains authoritative and is enforced in
    Phase 2 (after streaming completes), ensuring no changes to validation logic.
    
    Streaming flow:
    - Phase 1: Stream tokens to client via async generator, buffer internally
    - Phase 2: Finalize buffer, validate against DungeonMasterOutcome, execute subsystem writes
    
    When implementing streaming:
    - Use OpenAI's streaming API (stream=True parameter if supported by Responses API)
    - Buffer tokens internally for later validation and journey-log persistence
    - Preserve existing generate_narrative() for backward compatibility with /turn endpoint
    - Validate complete outcome only after streaming finishes
    - Replay buffered tokens verbatim to journey-log POST /characters/{id}/narrative
    
    See STREAMING_ARCHITECTURE.md for detailed design and event contracts.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5.1",
        timeout: int = 60,
        stub_mode: bool = False,
        max_retries: int = 3,
        retry_delay_base: float = 1.0,
        retry_delay_max: float = 30.0
    ):
        """Initialize LLM client.
        
        Args:
            api_key: OpenAI API key
            model: Model name (default: gpt-5.1)
            timeout: Request timeout in seconds
            stub_mode: If True, returns stub responses without calling API
            max_retries: Maximum retry attempts for transient errors
            retry_delay_base: Base delay for exponential backoff (seconds)
            retry_delay_max: Maximum delay for exponential backoff (seconds)
        """
        if not api_key or api_key.strip() == "":
            raise LLMConfigurationError("API key cannot be empty")

        self.model = model
        self.timeout = timeout
        self.stub_mode = stub_mode
        self.max_retries = max_retries
        self.retry_delay_base = retry_delay_base
        self.retry_delay_max = retry_delay_max
        self.parser = OutcomeParser()

        if not stub_mode:
            self.client = AsyncOpenAI(
                api_key=api_key,
                timeout=timeout
            )
            logger.info(
                f"Initialized LLMClient with model={self.model}, timeout={self.timeout}s, "
                f"max_retries={self.max_retries}"
            )
        else:
            self.client = None
            logger.info("Initialized LLMClient in STUB MODE (no API calls will be made)")

    async def generate_narrative(
        self,
        system_instructions: str,
        user_prompt: str,
        trace_id: Optional[str] = None,
        json_schema: Optional[dict] = None
    ) -> ParsedOutcome:
        """Generate narrative using the LLM with strict JSON enforcement.
        
        This method calls the OpenAI Responses API with the DungeonMasterOutcome
        JSON schema to enforce structured output. The API will reject responses
        that don't match the schema when using strict=True mode.
        
        The prompt (system_instructions) should already include:
        - Instructions to output only valid JSON
        - The DungeonMasterOutcome schema specification
        - Example JSON output
        
        This method implements retry logic with exponential backoff for transient errors:
        - Retries: Timeout, rate limit (429), server errors (500, 502, 503, 504)
        - No retry: Authentication errors (401), bad requests (400), invalid key
        
        Args:
            system_instructions: System-level instructions for the LLM (includes schema)
            user_prompt: The user prompt containing context and action
            trace_id: Optional trace ID for request correlation
            json_schema: Optional pre-generated JSON schema to avoid redundant generation.
                        If not provided, schema will be generated via get_outcome_json_schema().
            
        Returns:
            ParsedOutcome with validated outcome (if successful) and narrative text
            
        Raises:
            LLMTimeoutError: If request times out after all retries
            LLMResponseError: If response is invalid or missing narrative
            LLMClientError: For other errors
            
        Note:
            With strict schema enforcement enabled, the OpenAI API should reject
            non-JSON responses upstream. If a non-JSON response is received, it
            indicates a configuration error or API compatibility issue.
        """
        if self.stub_mode:
            return self._generate_stub_outcome(user_prompt)

        logger.info(
            "Generating narrative with LLM using DungeonMasterOutcome schema",
            model=self.model,
            instructions_length=len(system_instructions),
            prompt_length=len(user_prompt),
            max_retries=self.max_retries,
            turn_id=get_turn_id()
        )

        # Use the provided schema, or generate it if not available
        schema = json_schema or get_outcome_json_schema()

        # Call the internal method with retry logic
        return await self._generate_with_retry(
            system_instructions=system_instructions,
            user_prompt=user_prompt,
            schema=schema,
            trace_id=trace_id
        )
    
    async def _generate_with_retry(
        self,
        system_instructions: str,
        user_prompt: str,
        schema: dict,
        trace_id: Optional[str] = None
    ) -> ParsedOutcome:
        """Internal method to generate narrative with retry logic.
        
        This method wraps the actual API call with exponential backoff retry for
        transient errors. It distinguishes between retryable and non-retryable errors.
        
        Retryable errors (with exponential backoff):
        - APITimeoutError: Request timeout
        - RateLimitError: API rate limit (429)
        - InternalServerError: Server errors (500, 502, 503, 504)
        - APIConnectionError: Network connectivity issues
        
        Non-retryable errors (immediate failure):
        - AuthenticationError: Invalid API key (401)
        - BadRequestError: Invalid request format (400)
        - PermissionDeniedError: Insufficient permissions (403)
        """
        import openai
        
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            start_time = time.time()
            
            try:
                # Use OpenAI Responses API with strict JSON schema enforcement
                response = await self.client.responses.create(
                    model=self.model,
                    instructions=system_instructions,
                    input=user_prompt,
                    max_output_tokens=4000,
                    text={"format": {
                        "type": "json_schema",
                        "name": "dungeon_master_outcome",
                        "strict": True,
                        "schema": schema
                    }}
                )

                # Extract content from Responses API structure
                if not response.output:
                    logger.error("OpenAI API returned empty output", turn_id=get_turn_id())
                    raise LLMResponseError("LLM returned empty output")

                output_item = response.output[0]

                # Extract text content
                if isinstance(output_item.content, str):
                    content = output_item.content
                elif isinstance(output_item.content, list):
                    text_parts = []
                    for content_item in output_item.content:
                        if hasattr(content_item, "text"):
                            text_parts.append(content_item.text)
                        elif isinstance(content_item, dict) and "text" in content_item:
                            text_parts.append(content_item["text"])
                    content = "".join(text_parts)
                else:
                    content = None

                if not content:
                    logger.error("OpenAI API returned empty content", turn_id=get_turn_id())
                    raise LLMResponseError("LLM returned empty content")

                # Parse the response using the outcome parser
                parsed = self.parser.parse(content, trace_id=trace_id)
                
                # Record schema conformance metrics
                if (collector := get_metrics_collector()):
                    if parsed.is_valid:
                        collector.record_error("llm_parse_success")
                    else:
                        collector.record_error(f"llm_parse_failure_{parsed.error_type}")
                
                duration_ms = (time.time() - start_time) * 1000
                
                # Record metrics
                collector = get_metrics_collector()
                if collector:
                    collector.record_latency("llm_call", duration_ms)
                    if attempt > 0:
                        collector.record_error("llm_retry_success")
                
                if parsed.is_valid:
                    logger.info(
                        "Successfully generated narrative with valid schema",
                        narrative_length=len(parsed.narrative),
                        duration_ms=f"{duration_ms:.2f}",
                        attempts=attempt + 1,
                        turn_id=get_turn_id()
                    )
                else:
                    logger.warning(
                        "Generated narrative but schema validation failed - using fallback",
                        narrative_length=len(parsed.narrative),
                        error_type=parsed.error_type,
                        duration_ms=f"{duration_ms:.2f}",
                        attempts=attempt + 1,
                        turn_id=get_turn_id()
                    )
                
                return parsed

            except openai.AuthenticationError as e:
                # Non-retryable: Invalid API key
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    "LLM authentication failed (non-retryable)",
                    duration_ms=f"{duration_ms:.2f}",
                    turn_id=get_turn_id()
                )
                raise LLMConfigurationError("Invalid OpenAI API key") from e

            except openai.BadRequestError as e:
                # Non-retryable: Invalid request format
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    "LLM bad request error (non-retryable)",
                    error=redact_secrets(str(e)),
                    duration_ms=f"{duration_ms:.2f}",
                    turn_id=get_turn_id()
                )
                raise LLMClientError(f"Invalid request to LLM: {e}") from e
            
            except openai.PermissionDeniedError as e:
                # Non-retryable: Insufficient permissions
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    "LLM permission denied (non-retryable)",
                    error=redact_secrets(str(e)),
                    duration_ms=f"{duration_ms:.2f}",
                    turn_id=get_turn_id()
                )
                raise LLMClientError(f"Permission denied: {e}") from e

            except (openai.APITimeoutError, openai.RateLimitError, 
                    openai.InternalServerError, openai.APIConnectionError) as e:
                # Retryable errors
                last_exception = e
                duration_ms = (time.time() - start_time) * 1000
                
                error_type = type(e).__name__
                
                # Check if we've exhausted retries
                if attempt >= self.max_retries:
                    logger.error(
                        f"LLM request failed after {self.max_retries} retries",
                        error_type=error_type,
                        error=redact_secrets(str(e)),
                        total_attempts=attempt + 1,
                        duration_ms=f"{duration_ms:.2f}",
                        turn_id=get_turn_id()
                    )
                    
                    # Record metrics
                    if (collector := get_metrics_collector()):
                        collector.record_error(f"llm_{error_type.lower()}_exhausted")
                    
                    # Convert to appropriate exception type
                    if isinstance(e, openai.APITimeoutError):
                        raise LLMTimeoutError(
                            f"LLM request timed out after {self.timeout}s and {self.max_retries} retries"
                        ) from e
                    else:
                        raise LLMClientError(
                            f"LLM request failed after {self.max_retries} retries: {e}"
                        ) from e
                
                # Calculate retry delay with exponential backoff
                delay = min(
                    self.retry_delay_base * (2 ** attempt),
                    self.retry_delay_max
                )
                
                logger.warning(
                    f"LLM request failed (retryable), retrying in {delay:.2f}s",
                    error_type=error_type,
                    error=redact_secrets(str(e)),
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    retry_delay_seconds=delay,
                    duration_ms=f"{duration_ms:.2f}",
                    turn_id=get_turn_id()
                )
                
                # Record retry metrics
                if (collector := get_metrics_collector()):
                    collector.record_error(f"llm_{error_type.lower()}_retry")
                
                await asyncio.sleep(delay)

            except (LLMResponseError, LLMTimeoutError, LLMConfigurationError):
                # Re-raise our custom exceptions (already logged)
                raise

            except Exception as e:
                # Unexpected error - treat as non-retryable
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    "Unexpected error during LLM generation (non-retryable)",
                    error_type=type(e).__name__,
                    error=redact_secrets(str(e)),
                    duration_ms=f"{duration_ms:.2f}",
                    turn_id=get_turn_id()
                )
                raise LLMClientError(f"Failed to generate narrative: {e}") from e
        
        # Should never reach here, but just in case
        if last_exception:
            raise LLMClientError(
                f"LLM request failed after {self.max_retries} retries: {last_exception}"
            ) from last_exception
        raise LLMClientError("LLM request failed with unknown error")

    async def generate_narrative_stream(
        self,
        system_instructions: str,
        user_prompt: str,
        callback: Optional[StreamingCallback] = None,
        trace_id: Optional[str] = None,
        json_schema: Optional[dict] = None
    ) -> ParsedOutcome:
        """Generate narrative using streaming with two-phase processing.
        
        Phase 1 (Streaming): Stream tokens progressively to callback while buffering
        Phase 2 (Validation): Parse complete buffer against DungeonMasterOutcome schema
        
        This method provides progressive narrative delivery while maintaining the same
        validation guarantees as generate_narrative(). The callback receives tokens
        as they arrive, and the complete validated outcome is returned after streaming.
        
        Token Streaming (Phase 1):
        - Tokens emitted via callback as they're generated
        - All tokens buffered internally for Phase 2 validation
        - Callback exceptions are logged but don't interrupt streaming
        - Stream lifecycle logged (start, token batches, completion)
        
        Outcome Validation (Phase 2):
        - Complete buffer validated against DungeonMasterOutcome schema
        - Same strict validation as generate_narrative()
        - Parse errors logged with detailed context and duration
        - Returns ParsedOutcome with validated outcome or fallback narrative
        
        Args:
            system_instructions: System-level instructions for the LLM (includes schema)
            user_prompt: The user prompt containing context and action
            callback: Optional callback for receiving streaming tokens
            trace_id: Optional trace ID for request correlation
            json_schema: Optional pre-generated JSON schema to avoid redundant generation
            
        Returns:
            ParsedOutcome with validated outcome (if successful) and narrative text
            
        Raises:
            LLMTimeoutError: If request times out
            LLMResponseError: If response is invalid or missing narrative
            LLMClientError: For other errors
            
        Example:
            >>> def on_token(token: str):
            ...     print(token, end='', flush=True)
            ...
            >>> outcome = await client.generate_narrative_stream(
            ...     system_instructions="...",
            ...     user_prompt="...",
            ...     callback=on_token
            ... )
            >>> print(f"\\nFinal outcome: {outcome.is_valid}")
        """
        if self.stub_mode:
            # In stub mode, simulate streaming by yielding the stub narrative
            stub_outcome = self._generate_stub_outcome(user_prompt)
            if callback:
                try:
                    await callback(stub_outcome.narrative)
                except Exception as e:
                    logger.warning(
                        "Callback raised exception during stub streaming",
                        error_type=type(e).__name__,
                        error=redact_secrets(str(e))
                    )
            return stub_outcome

        logger.info(
            "Starting streaming narrative generation",
            model=self.model,
            instructions_length=len(system_instructions),
            prompt_length=len(user_prompt),
            has_callback=callback is not None,
            trace_id=trace_id,
            turn_id=get_turn_id()
        )

        start_time = time.time()
        buffer = []
        token_count = 0
        
        try:
            # Use the provided schema, or generate it if not available
            schema = json_schema or get_outcome_json_schema()
            
            # Log stream start
            logger.debug("Stream started", trace_id=trace_id, turn_id=get_turn_id())
            
            # Use OpenAI Responses API with streaming enabled
            # Note: The Responses API streaming may work differently than Chat API
            # This implementation assumes stream parameter is supported
            stream = await self.client.responses.create(
                model=self.model,
                instructions=system_instructions,
                input=user_prompt,
                max_output_tokens=4000,
                text={"format": {
                    "type": "json_schema",
                    "name": "dungeon_master_outcome",
                    "strict": True,
                    "schema": schema
                }},
                stream=True  # Enable streaming
            )
            
            # Note: If the Responses API does not support streaming, this will raise
            # an exception (BadRequestError) which is caught and handled below.
            # The streaming parameter is passed optimistically based on the pattern
            # used in the Chat API.

            # Phase 1: Stream tokens and buffer
            async for chunk in stream:
                # Extract content from chunk
                # Only process content_delta to avoid duplicating data in the buffer.
                # The 'content' attribute typically contains the full message, not a delta,
                # which would lead to duplicated data when streaming.
                token = None
                
                if hasattr(chunk, 'output') and chunk.output:
                    output_item = chunk.output[0]
                    if hasattr(output_item, 'content_delta'):
                        # Delta format - incremental token
                        if isinstance(output_item.content_delta, str):
                            token = output_item.content_delta
                        elif hasattr(output_item.content_delta, 'text'):
                            token = output_item.content_delta.text
                
                if token:
                    # Buffer the token
                    buffer.append(token)
                    token_count += 1
                    
                    # Emit to callback if provided (async to prevent event loop blocking)
                    if callback:
                        try:
                            await callback(token)
                        except Exception as e:
                            # Log callback errors but don't interrupt streaming
                            # Redact sensitive information from error messages
                            logger.warning(
                                "Callback raised exception during streaming",
                                error_type=type(e).__name__,
                                error=redact_secrets(str(e)),
                                token_number=token_count,
                                trace_id=trace_id,
                                turn_id=get_turn_id()
                            )
                else:
                    # Log when we receive a chunk but can't extract a token
                    # This helps identify API format changes or unhandled structures
                    if hasattr(chunk, 'output') and chunk.output:
                        logger.debug(
                            "Received chunk with no extractable token",
                            chunk_has_output=True,
                            trace_id=trace_id,
                            turn_id=get_turn_id()
                        )
                    
                    # Log token batches periodically to track progress
                    if token_count % 50 == 0:
                        logger.debug(
                            "Streaming progress",
                            tokens_received=token_count,
                            buffer_size=len(''.join(buffer)),
                            trace_id=trace_id,
                            turn_id=get_turn_id()
                        )
            
            # Reconstruct complete text from buffer
            complete_text = ''.join(buffer)
            
            streaming_duration_ms = (time.time() - start_time) * 1000
            logger.info(
                "Stream completed",
                token_count=token_count,
                total_length=len(complete_text),
                streaming_duration_ms=f"{streaming_duration_ms:.2f}",
                trace_id=trace_id,
                turn_id=get_turn_id()
            )
            
            if not complete_text:
                logger.error("Stream completed but buffer is empty", trace_id=trace_id, turn_id=get_turn_id())
                raise LLMResponseError("LLM stream completed with empty content")
            
            # Phase 2: Parse and validate complete outcome
            parse_start_time = time.time()
            logger.debug("Starting outcome parse phase", trace_id=trace_id, turn_id=get_turn_id())
            
            parsed = self.parser.parse(complete_text, trace_id=trace_id)
            
            parse_duration_ms = (time.time() - parse_start_time) * 1000
            total_duration_ms = (time.time() - start_time) * 1000
            
            # Record schema conformance metrics (only record errors)
            if (collector := get_metrics_collector()):
                if not parsed.is_valid:
                    collector.record_error(f"llm_stream_parse_failure_{parsed.error_type}")
            
            # Record metrics
            collector = get_metrics_collector()
            if collector:
                collector.record_latency("llm_call", total_duration_ms)
            
            if parsed.is_valid:
                logger.info(
                    "Stream parse phase completed successfully",
                    narrative_length=len(parsed.narrative),
                    parse_duration_ms=f"{parse_duration_ms:.2f}",
                    total_duration_ms=f"{total_duration_ms:.2f}",
                    trace_id=trace_id,
                    turn_id=get_turn_id()
                )
            else:
                logger.warning(
                    "Stream parse phase failed - using fallback narrative",
                    narrative_length=len(parsed.narrative),
                    error_type=parsed.error_type,
                    parse_duration_ms=f"{parse_duration_ms:.2f}",
                    total_duration_ms=f"{total_duration_ms:.2f}",
                    trace_id=trace_id,
                    turn_id=get_turn_id()
                )
            
            return parsed

        except openai.APITimeoutError as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "LLM streaming request timed out",
                timeout_seconds=self.timeout,
                duration_ms=f"{duration_ms:.2f}",
                tokens_received=token_count,
                trace_id=trace_id,
                turn_id=get_turn_id()
            )
            raise LLMTimeoutError(
                f"LLM streaming request timed out after {self.timeout}s"
            ) from e

        except openai.AuthenticationError as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "LLM streaming authentication failed",
                duration_ms=f"{duration_ms:.2f}",
                trace_id=trace_id,
                turn_id=get_turn_id()
            )
            raise LLMConfigurationError("Invalid OpenAI API key") from e

        except openai.BadRequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "LLM streaming bad request error",
                error=redact_secrets(str(e)),
                duration_ms=f"{duration_ms:.2f}",
                trace_id=trace_id,
                turn_id=get_turn_id()
            )
            raise LLMClientError(f"Invalid streaming request to LLM: {e}") from e

        except (LLMResponseError, LLMTimeoutError, LLMConfigurationError):
            # Re-raise our custom exceptions
            raise

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Unexpected error during LLM streaming generation",
                error_type=type(e).__name__,
                error=redact_secrets(str(e)),
                duration_ms=f"{duration_ms:.2f}",
                tokens_received=token_count,
                buffer_size=len(''.join(buffer)) if buffer else 0,
                trace_id=trace_id,
                turn_id=get_turn_id()
            )
            raise LLMClientError(f"Failed to generate streaming narrative: {e}") from e

    def _generate_stub_outcome(self, user_prompt: str) -> ParsedOutcome:
        """Generate stub outcome for offline development.
        
        Args:
            user_prompt: The user prompt (for extracting action)
            
        Returns:
            ParsedOutcome with stub narrative
        """
        logger.debug("Generating stub outcome (API not called)")

        # Extract a snippet from the prompt to make the stub response more relevant
        prompt_snippet = user_prompt[:100] if len(user_prompt) > 100 else user_prompt

        narrative = (
            f"[STUB MODE] This is a placeholder narrative response. "
            f"In production, this would be generated by {self.model}. "
            f"Based on your prompt: '{prompt_snippet}...'"
        )
        
        # Create a valid outcome for stub mode
        outcome = DungeonMasterOutcome(
            narrative=narrative,
            intents=IntentsBlock(
                quest_intent=QuestIntent(action="none"),
                combat_intent=CombatIntent(action="none"),
                poi_intent=POIIntent(action="none"),
                meta=None
            )
        )
        
        return ParsedOutcome(
            outcome=outcome,
            narrative=narrative,
            is_valid=True
        )
