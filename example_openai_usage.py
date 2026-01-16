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
"""OpenAI-based LLM client implementation.

This module provides a concrete implementation of BaseLLMClient using OpenAI's API.
It uses the official OpenAI Python SDK and implements retry logic for transient failures.
This is a demo, not meant for plugin use but just a demonstration on how to set up synchronous openai usage
This can also be adapted to be used asyncrhonously

Key features:
- Uses OpenAI Responses API (recommended for GPT-5+ models)
- Configurable retry logic with exponential backoff for transient errors
- Structured logging without exposing secrets
- Proper error classification and handling
"""

import logging
import time
from typing import Optional

import openai
from openai import OpenAI

from app.services.llm_client import (
    BaseLLMClient,
    LLMConfigurationError,
    LLMRequestError,
    LLMResponseError,
)

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0  # seconds
MAX_BACKOFF = 10.0  # seconds
BACKOFF_MULTIPLIER = 2.0

# JSON schema for response format enforcement
# This schema matches the expected output structure for software specifications
# With strict=True, ALL fields must be in required array
# open_questions and assumptions will always be returned (may be empty arrays)
# For Responses API, use the 'text' parameter with 'format' property
RESPONSE_JSON_SCHEMA = {
    "format": {
        "type": "json_schema",
        "name": "software_specifications",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "specs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "purpose": {"type": "string"},
                            "vision": {"type": "string"},
                            "must": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "dont": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "nice": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "open_questions": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "assumptions": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "purpose",
                            "vision",
                            "must",
                            "dont",
                            "nice",
                            "open_questions",
                            "assumptions",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["specs"],
            "additionalProperties": False,
        },
    }
}


class OpenAIClient(BaseLLMClient):
    """OpenAI implementation of the LLM client.

    This client uses the OpenAI Responses API to generate specifications.
    It implements retry logic for transient failures and provides structured logging.

    **Important**: This client uses synchronous calls with blocking sleep for retry backoff.
    If using in async contexts (e.g., FastAPI async endpoints), consider running the
    client calls in a thread pool executor to avoid blocking the event loop:

        >>> import asyncio
        >>> from concurrent.futures import ThreadPoolExecutor
        >>> executor = ThreadPoolExecutor()
        >>> result = await asyncio.get_event_loop().run_in_executor(
        ...     executor, client.generate_specs, "Build a REST API"
        ... )

    Attributes:
        client: OpenAI SDK client instance.
        max_retries: Maximum number of retry attempts for transient errors.
        initial_backoff: Initial backoff delay in seconds.
        max_backoff: Maximum backoff delay in seconds.
        backoff_multiplier: Multiplier for exponential backoff.

    Example:
        >>> client = OpenAIClient(
        ...     api_key="sk-...",
        ...     model="gpt-5.1",
        ...     timeout=60
        ... )
        >>> result = client.generate_specs("Build a REST API")
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = MAX_RETRIES,
        initial_backoff: float = INITIAL_BACKOFF,
        max_backoff: float = MAX_BACKOFF,
        backoff_multiplier: float = BACKOFF_MULTIPLIER,
    ):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key.
            model: Model identifier (e.g., 'gpt-5.1', 'gpt-4').
            base_url: Optional base URL for custom endpoints.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts.
            initial_backoff: Initial backoff delay in seconds.
            max_backoff: Maximum backoff delay in seconds.
            backoff_multiplier: Multiplier for exponential backoff.

        Raises:
            LLMConfigurationError: If configuration is invalid.
        """
        # Initialize base class (validates api_key, model, timeout)
        super().__init__(api_key, model, base_url, timeout)

        # Validate retry configuration
        if max_retries < 0:
            raise LLMConfigurationError("max_retries must be non-negative")
        if initial_backoff <= 0:
            raise LLMConfigurationError("initial_backoff must be positive")
        if max_backoff < initial_backoff:
            raise LLMConfigurationError("max_backoff must be >= initial_backoff")
        if backoff_multiplier < 1.0:
            raise LLMConfigurationError("backoff_multiplier must be >= 1.0")

        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_multiplier = backoff_multiplier

        # Initialize OpenAI client
        try:
            client_kwargs = {
                "api_key": api_key,
                "timeout": timeout,
            }
            if base_url:
                client_kwargs["base_url"] = base_url

            self.client = OpenAI(**client_kwargs)

            logger.info(
                "OpenAI client initialized",
                extra={
                    "model": model,
                    "has_base_url": bool(base_url),
                    "timeout": timeout,
                    "max_retries": max_retries,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to initialize OpenAI client",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            raise LLMConfigurationError(f"Failed to initialize OpenAI client: {e}")

    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error is retryable.

        Retryable errors include:
        - Timeout errors
        - Network errors (connection errors, etc.)
        - 5xx server errors
        - Rate limit errors (429)

        Non-retryable errors include:
        - Authentication errors (401)
        - Invalid request errors (400)
        - Resource not found (404)
        - Permission errors (403)

        Args:
            error: The exception to check.

        Returns:
            True if the error should be retried, False otherwise.
        """
        # Check for OpenAI-specific error types that are documented as retryable
        return isinstance(
            error,
            (
                openai.APITimeoutError,
                openai.RateLimitError,
                openai.APIConnectionError,
                openai.InternalServerError,
            ),
        )

    def _call_llm_api(self, description: str, system_prompt: str) -> str:
        """Call OpenAI API with retry logic.

        This method implements exponential backoff retry logic for transient failures.
        It uses OpenAI's Responses API with the configured model.

        Args:
            description: User's project description.
            system_prompt: System prompt to guide LLM behavior (mapped to instructions).

        Returns:
            Raw response text from the LLM.

        Raises:
            LLMConfigurationError: If API key is invalid or missing.
            LLMRequestError: If the API request fails after retries.
        """
        retry_count = 0
        backoff = self.initial_backoff
        last_error = None

        start_time = time.time()

        # Log LLM request start
        from app.utils.logging_helpers import log_llm_request

        log_llm_request(
            logger=logger, provider="openai", model=self.model, description_length=len(description)
        )

        while retry_count <= self.max_retries:
            try:
                # Log attempt (not on first try to avoid log spam)
                if retry_count > 0:
                    logger.info(
                        "Retrying OpenAI API call",
                        extra={
                            "retry_count": retry_count,
                            "max_retries": self.max_retries,
                            "backoff": backoff,
                        },
                    )

                # Make the API call using Responses API with JSON schema enforcement
                # The Responses API uses 'instructions' for system context
                # and 'input' for the user message
                # Note: GPT-5 models do not support the temperature parameter.
                # Use reasoning_effort and verbosity for output control instead.
                #
                # text.format enforces strict JSON output according to the schema
                response = self.client.responses.create(
                    model=self.model,
                    instructions=system_prompt,
                    input=description,
                    max_output_tokens=15000,  # Reasonable limit for spec generation
                    text=RESPONSE_JSON_SCHEMA,
                )

                # Extract response content from Responses API structure
                # The response has an 'output' array instead of 'choices'
                if not response.output:
                    logger.error("OpenAI API returned empty output")
                    raise LLMResponseError("OpenAI API returned empty output")

                # Get the first output item's content
                output_item = response.output[0]

                # Content can be a string or an array of content items
                if isinstance(output_item.content, str):
                    content = output_item.content
                elif isinstance(output_item.content, list):
                    # Extract text from content array
                    text_parts = []
                    for content_item in output_item.content:
                        if hasattr(content_item, "text"):
                            text_parts.append(content_item.text)
                        elif isinstance(content_item, dict) and "text" in content_item:
                            text_parts.append(content_item["text"])
                    content = "".join(text_parts)
                else:
                    # Handle unexpected content types gracefully
                    if output_item.content is not None:
                        logger.warning(
                            "Unsupported content type in OpenAI response",
                            extra={"content_type": type(output_item.content).__name__},
                        )
                    content = None

                if not content:
                    logger.error("OpenAI API returned empty content")
                    raise LLMResponseError("OpenAI API returned empty content")

                # Log successful response metadata
                elapsed = time.time() - start_time

                # Extract token usage - Responses API has similar usage structure
                prompt_tokens = None
                completion_tokens = None
                total_tokens = None

                if hasattr(response, "usage") and response.usage:
                    if hasattr(response.usage, "total_tokens"):
                        total_tokens = response.usage.total_tokens
                    if hasattr(response.usage, "input_tokens"):
                        prompt_tokens = response.usage.input_tokens
                    if hasattr(response.usage, "output_tokens"):
                        completion_tokens = response.usage.output_tokens

                    # Calculate total if individual tokens available but total is not
                    if (
                        total_tokens is None
                        and prompt_tokens is not None
                        and completion_tokens is not None
                    ):
                        total_tokens = prompt_tokens + completion_tokens

                    if total_tokens is None:
                        logger.debug(
                            "Token usage information unavailable or in unexpected format",
                            extra={"usage_attrs": dir(response.usage) if response.usage else None},
                        )

                # Record metrics
                from app.services.metrics import get_metrics_collector
                from app.utils.logging_helpers import log_llm_response

                metrics = get_metrics_collector()
                metrics.record_llm_request(
                    provider="openai",
                    model=self.model,
                    status="success",
                    duration=elapsed,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )

                # Log structured response
                log_llm_response(
                    logger=logger,
                    provider="openai",
                    model=self.model,
                    duration=elapsed,
                    status="success",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )

                logger.info(
                    "OpenAI API call succeeded",
                    extra={
                        "model": self.model,
                        "retry_count": retry_count,
                        "latency_ms": int(elapsed * 1000),
                        "response_length": len(content),
                        "total_tokens": total_tokens,
                    },
                )

                return content

            except openai.AuthenticationError as e:
                # Authentication errors are not retryable
                logger.error(
                    "OpenAI authentication failed",
                    extra={"error": str(e), "retry_count": retry_count},
                )
                raise LLMConfigurationError(
                    f"OpenAI authentication failed: {e}. Please check your API key."
                )

            except openai.NotFoundError as e:
                # Model not found or endpoint not found - not retryable
                logger.error(
                    "OpenAI resource not found", extra={"error": str(e), "model": self.model}
                )
                raise LLMConfigurationError(
                    f"OpenAI resource not found: {e}. Please check your model name or endpoint."
                )

            except openai.BadRequestError as e:
                # Invalid request - check if it's a schema validation error
                error_msg = str(e)
                if "json_schema" in error_msg.lower() or "schema" in error_msg.lower():
                    logger.error(
                        "OpenAI JSON schema validation failed",
                        extra={"error": str(e), "retry_count": retry_count},
                    )
                    raise LLMResponseError(
                        f"OpenAI rejected response due to JSON schema violation: {e}. "
                        f"The model output did not match the required structure."
                    )
                else:
                    logger.error(
                        "OpenAI invalid request",
                        extra={"error": str(e), "retry_count": retry_count},
                    )
                    raise LLMRequestError(
                        f"OpenAI invalid request: {e}. Please check your request parameters."
                    )

            except Exception as e:
                last_error = e

                # Check if this is an LLMResponseError (don't retry response parsing errors)
                if isinstance(e, LLMResponseError):
                    logger.error("OpenAI API returned invalid response", extra={"error": str(e)})
                    raise

                # Check if error is retryable
                if not self._is_retryable_error(e):
                    logger.error(
                        "OpenAI API call failed with non-retryable error",
                        extra={
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "retry_count": retry_count,
                        },
                    )
                    raise LLMRequestError(f"OpenAI API request failed: {e}")

                # If we've exhausted retries, raise the error
                if retry_count >= self.max_retries:
                    elapsed = time.time() - start_time

                    # Record failure metrics
                    from app.services.metrics import get_metrics_collector
                    from app.utils.logging_helpers import log_llm_response

                    metrics = get_metrics_collector()
                    metrics.record_llm_request(
                        provider="openai", model=self.model, status="error", duration=elapsed
                    )

                    # Log structured error
                    log_llm_response(
                        logger=logger,
                        provider="openai",
                        model=self.model,
                        duration=elapsed,
                        status="error",
                        error_type=type(e).__name__,
                    )

                    logger.error(
                        "OpenAI API call failed after all retries",
                        extra={
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "retry_count": retry_count,
                            "total_latency_ms": int(elapsed * 1000),
                        },
                    )
                    raise LLMRequestError(
                        f"OpenAI API request failed after {retry_count} retries: {e}"
                    )

                # Log retry attempt
                logger.warning(
                    "OpenAI API call failed, will retry",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "retry_count": retry_count,
                        "backoff": backoff,
                    },
                )

                # Wait before retrying
                time.sleep(backoff)

                # Update backoff for next retry
                backoff = min(backoff * self.backoff_multiplier, self.max_backoff)
                retry_count += 1

        # Should never reach here, but just in case
        raise LLMRequestError(
            f"OpenAI API request failed after {retry_count} retries: {last_error}"
        )
