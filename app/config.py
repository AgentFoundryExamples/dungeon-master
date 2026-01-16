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
"""Configuration module for Dungeon Master service.

This module loads and validates configuration from environment variables.
All settings are validated at startup to fail fast if configuration is invalid.
"""

from functools import lru_cache
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.
    
    All settings can be overridden via environment variables.
    See .env.example for detailed documentation of each setting.
    """

    # Journey Log Service Configuration
    journey_log_base_url: str = Field(
        ...,
        description="Base URL for the journey-log service",
        examples=["http://localhost:8000", "https://journey-log.example.com"]
    )
    journey_log_timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="HTTP timeout for journey-log requests in seconds"
    )

    # OpenAI Configuration
    openai_api_key: str = Field(
        ...,
        description="OpenAI API key for LLM requests"
    )
    openai_model: str = Field(
        default="gpt-5.1",
        description="OpenAI model to use for narrative generation"
    )
    openai_timeout: int = Field(
        default=60,
        ge=1,
        le=600,
        description="HTTP timeout for OpenAI requests in seconds"
    )
    openai_stub_mode: bool = Field(
        default=False,
        description="Enable stub mode for offline development (no actual API calls)"
    )
    journey_log_recent_n: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Default number of recent narrative turns to fetch from journey-log"
    )

    # Health Check Configuration
    health_check_journey_log: bool = Field(
        default=False,
        description="Whether to ping journey-log service during health checks"
    )

    # Service Configuration
    service_name: str = Field(
        default="dungeon-master",
        description="Service name for logging and identification"
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    log_json_format: bool = Field(
        default=False,
        description="Enable JSON structured logging output"
    )

    # Metrics Configuration
    enable_metrics: bool = Field(
        default=False,
        description="Enable metrics collection and /metrics endpoint"
    )
    
    # Debug Configuration
    enable_debug_endpoints: bool = Field(
        default=False,
        description="Enable debug endpoints like /debug/parse_llm (for local development only)"
    )

    # PolicyEngine Configuration
    quest_trigger_prob: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Probability of quest trigger (0.0-1.0)"
    )
    quest_cooldown_turns: int = Field(
        default=5,
        ge=0,
        description="Number of turns between quest triggers (0 or greater)"
    )
    poi_trigger_prob: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Probability of POI trigger (0.0-1.0)"
    )
    poi_cooldown_turns: int = Field(
        default=3,
        ge=0,
        description="Number of turns between POI triggers (0 or greater)"
    )
    rng_seed: Optional[int] = Field(
        default=None,
        description="Optional RNG seed for deterministic debugging (leave unset for secure randomness)"
    )

    @field_validator('journey_log_base_url')
    @classmethod
    def validate_journey_log_url(cls, v: str) -> str:
        """Validate journey-log base URL format."""
        if not v:
            raise ValueError("journey_log_base_url cannot be empty")
        if not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError(
                f"journey_log_base_url must start with http:// or https://, got: {v}"
            )
        # Remove trailing slash for consistency
        return v.rstrip('/')

    @field_validator('openai_api_key')
    @classmethod
    def validate_openai_key(cls, v: str) -> str:
        """Validate OpenAI API key is not empty."""
        if not v or v.strip() == "":
            raise ValueError(
                "openai_api_key cannot be empty. Set OPENAI_API_KEY environment variable."
            )
        return v

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is a recognized value."""
        valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(
                f"log_level must be one of {valid_levels}, got: {v}"
            )
        return v_upper

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )


@lru_cache
def get_settings() -> Settings:
    """Get the settings instance with LRU caching.
    
    Uses functools.lru_cache for thread-safe singleton pattern.
    The cache can be cleared for testing using get_settings.cache_clear().
    
    Returns:
        Settings instance with validated configuration
        
    Raises:
        ValueError: If required configuration is missing or invalid
    """
    try:
        return Settings()
    except Exception as e:
        raise ValueError(
            f"Configuration error: {e}. "
            "Ensure all required environment variables are set. "
            "See .env.example for required configuration."
        ) from e
