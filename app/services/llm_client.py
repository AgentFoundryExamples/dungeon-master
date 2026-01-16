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

import json
import logging
import time
from typing import Optional
from openai import AsyncOpenAI
import openai

from app.logging import StructuredLogger, redact_secrets

logger = StructuredLogger(__name__)


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
    - Extracts narrative text from JSON responses
    - Handles errors and provides fallback mechanisms
    - Supports stub/mock mode for offline development
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5.1",
        timeout: int = 60,
        stub_mode: bool = False
    ):
        """Initialize LLM client.
        
        Args:
            api_key: OpenAI API key
            model: Model name (default: gpt-5.1)
            timeout: Request timeout in seconds
            stub_mode: If True, returns stub responses without calling API
        """
        if not api_key or api_key.strip() == "":
            raise LLMConfigurationError("API key cannot be empty")

        self.model = model
        self.timeout = timeout
        self.stub_mode = stub_mode

        if not stub_mode:
            self.client = AsyncOpenAI(
                api_key=api_key,
                timeout=timeout
            )
            logger.info(
                f"Initialized LLMClient with model={self.model}, timeout={self.timeout}s"
            )
        else:
            self.client = None
            logger.info("Initialized LLMClient in STUB MODE (no API calls will be made)")

    async def generate_narrative(
        self,
        system_instructions: str,
        user_prompt: str,
        trace_id: Optional[str] = None
    ) -> str:
        """Generate narrative using the LLM.
        
        Args:
            system_instructions: System-level instructions for the LLM
            user_prompt: The user prompt containing context and action
            trace_id: Optional trace ID for request correlation
            
        Returns:
            Generated narrative text
            
        Raises:
            LLMTimeoutError: If request times out
            LLMResponseError: If response is invalid or missing narrative
            LLMClientError: For other errors
        """
        if self.stub_mode:
            return self._generate_stub_narrative(user_prompt)

        logger.info(
            f"Generating narrative with LLM",
            model=self.model,
            instructions_length=len(system_instructions),
            prompt_length=len(user_prompt)
        )

        start_time = time.time()
        try:
            # Use OpenAI Responses API as per LLMs.md guidelines
            # The Responses API uses 'instructions' for system context and 'input' for user message
            response = await self.client.responses.create(
                model=self.model,
                instructions=system_instructions,
                input=user_prompt,
                max_output_tokens=4000,  # Reasonable limit for narrative generation
                # Using text format for simple narrative generation
                # For structured outputs, we would use text.format with JSON schema
                text={"format": {"type": "json_schema", "name": "narrative_response", "strict": True, "schema": {
                    "type": "object",
                    "properties": {
                        "narrative": {
                            "type": "string",
                            "description": "The generated narrative response"
                        }
                    },
                    "required": ["narrative"],
                    "additionalProperties": False
                }}}
            )

            # Extract content from Responses API structure
            if not response.output:
                logger.error("OpenAI API returned empty output")
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
                logger.error("OpenAI API returned empty content")
                raise LLMResponseError("LLM returned empty content")

            # Parse the JSON response to extract narrative
            try:
                response_data = json.loads(content)
                narrative = response_data.get("narrative", "").strip()

                if not narrative:
                    logger.error("LLM response missing 'narrative' field or empty")
                    raise LLMResponseError("LLM response missing narrative field")

                duration_ms = (time.time() - start_time) * 1000
                logger.info(
                    f"Successfully generated narrative",
                    narrative_length=len(narrative),
                    duration_ms=f"{duration_ms:.2f}"
                )
                return narrative

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {e}")
                # With strict schema enforcement, we should not receive non-JSON responses
                raise LLMResponseError(
                    f"Failed to parse LLM response as JSON. Strict schema enforcement should prevent this: {e}"
                ) from e

        except openai.APITimeoutError as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"LLM request timed out",
                timeout_seconds=self.timeout,
                duration_ms=f"{duration_ms:.2f}"
            )
            raise LLMTimeoutError(
                f"LLM request timed out after {self.timeout}s"
            ) from e

        except openai.AuthenticationError as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "LLM authentication failed",
                duration_ms=f"{duration_ms:.2f}"
            )
            raise LLMConfigurationError("Invalid OpenAI API key") from e

        except openai.BadRequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"LLM bad request error",
                error=redact_secrets(str(e)),
                duration_ms=f"{duration_ms:.2f}"
            )
            raise LLMClientError(f"Invalid request to LLM: {e}") from e

        except (LLMResponseError, LLMTimeoutError, LLMConfigurationError):
            # Re-raise our custom exceptions
            raise

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Unexpected error during LLM generation",
                error_type=type(e).__name__,
                error=redact_secrets(str(e)),
                duration_ms=f"{duration_ms:.2f}"
            )
            raise LLMClientError(f"Failed to generate narrative: {e}") from e

    def _generate_stub_narrative(self, user_prompt: str) -> str:
        """Generate stub narrative for offline development.
        
        Args:
            user_prompt: The user prompt (for extracting action)
            
        Returns:
            Stub narrative response
        """
        logger.debug("Generating stub narrative (API not called)")

        # Extract a snippet from the prompt to make the stub response more relevant
        prompt_snippet = user_prompt[:100] if len(user_prompt) > 100 else user_prompt

        return (
            f"[STUB MODE] This is a placeholder narrative response. "
            f"In production, this would be generated by {self.model}. "
            f"Based on your prompt: '{prompt_snippet}...'"
        )
