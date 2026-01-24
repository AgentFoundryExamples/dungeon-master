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

import re
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
    environment: str = Field(
        default="development",
        description="Environment name for metrics labeling (e.g., production, staging, development)"
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
    turn_log_sampling_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Sampling rate for turn logs (0.0-1.0, where 1.0 logs all turns)"
    )
    
    # Debug Configuration
    enable_debug_endpoints: bool = Field(
        default=False,
        description="Enable debug endpoints like /debug/parse_llm (for local development only)"
    )
    dev_bypass_auth: bool = Field(
        default=False,
        description="Enable development bypass for authentication (allows X-Dev-User-Id header instead of Firebase token)"
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
        description="Number of turns between quest triggers (0 or greater, negative values skip waiting periods)"
    )
    poi_trigger_prob: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Probability of POI trigger (0.0-1.0)"
    )
    poi_cooldown_turns: int = Field(
        default=3,
        description="Number of turns between POI triggers (0 or greater, negative values skip waiting periods)"
    )
    rng_seed: Optional[int] = Field(
        default=None,
        description="Optional RNG seed for deterministic debugging (leave unset for secure randomness)"
    )

    # POI Memory Spark Configuration
    poi_memory_spark_enabled: bool = Field(
        default=False,
        description="Enable fetching random POIs as memory sparks for prompts"
    )
    poi_memory_spark_count: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Number of random POIs to fetch as memory sparks (1-20)"
    )
    memory_spark_probability: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Probability of memory spark trigger per eligible turn (0.0-1.0)"
    )
    quest_poi_reference_probability: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Probability that a triggered quest references a prior POI (0.0-1.0)"
    )

    # Admin and Policy Configuration
    policy_config_file: Optional[str] = Field(
        default=None,
        description="Optional path to JSON file for runtime policy config (probabilities, cooldowns)"
    )
    admin_endpoints_enabled: bool = Field(
        default=False,
        description="Enable admin endpoints for turn introspection and policy management"
    )
    turn_storage_ttl_seconds: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="TTL for turn details in storage (60-86400 seconds, default: 1 hour)"
    )
    turn_storage_max_size: int = Field(
        default=10000,
        ge=100,
        le=100000,
        description="Maximum number of turns to store in memory (100-100000, default: 10000)"
    )

    # Rate Limiting Configuration
    max_turns_per_character_per_second: float = Field(
        default=2.0,
        ge=0.1,
        le=100.0,
        description="Maximum turns per character per second (0.1-100.0). Conservative default to prevent abuse."
    )
    max_concurrent_llm_calls: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum concurrent LLM calls across all characters (1-100). Prevents API rate limit exhaustion."
    )
    
    # Retry and Backoff Configuration
    llm_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts for transient LLM errors (0-10). 0 disables retries."
    )
    llm_retry_delay_base: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Base delay in seconds for LLM retry exponential backoff (0.1-10.0)"
    )
    llm_retry_delay_max: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="Maximum delay in seconds for LLM retry exponential backoff (1.0-300.0)"
    )
    
    journey_log_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts for transient journey-log errors on GET requests (0-10). POST/PUT/DELETE are not retried."
    )
    journey_log_retry_delay_base: float = Field(
        default=0.5,
        ge=0.1,
        le=10.0,
        description="Base delay in seconds for journey-log retry exponential backoff (0.1-10.0)"
    )
    journey_log_retry_delay_max: float = Field(
        default=10.0,
        ge=1.0,
        le=300.0,
        description="Maximum delay in seconds for journey-log retry exponential backoff (1.0-300.0)"
    )

    # Google Cloud Platform (GCP) Deployment Configuration
    gcp_project_id: Optional[str] = Field(
        default=None,
        description="GCP Project ID for Cloud Run deployment and Secret Manager access (optional for local dev)"
    )
    gcp_region: str = Field(
        default="us-central1",
        description="GCP Region for Cloud Run deployment (e.g., us-central1, us-east1)"
    )
    cloud_run_service: str = Field(
        default="dungeon-master",
        description="Cloud Run service name for identification and metrics"
    )
    artifact_repo: str = Field(
        default="dungeon-master",
        description="Artifact Registry repository name for Docker images"
    )
    secret_manager_config: str = Field(
        default="disabled",
        description="Secret Manager configuration mode: disabled, env_vars, or volume"
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

    @field_validator('gcp_project_id')
    @classmethod
    def validate_gcp_project_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate GCP project ID format if provided."""
        if v is None or v.strip() == "":
            # Project ID is optional for local development
            return None
        
        # GCP project IDs must be 6-30 characters, lowercase letters, digits, and hyphens
        # Cannot start with a digit or hyphen, cannot end with hyphen, no consecutive hyphens
        v = v.strip()
        if len(v) < 6 or len(v) > 30:
            raise ValueError(
                f"gcp_project_id must be 6-30 characters, got {len(v)} characters"
            )
        
        if not v[0].isalpha():
            raise ValueError(
                f"gcp_project_id must start with a letter, got: {v[0]}"
            )
        
        if v[-1] == '-':
            raise ValueError(
                "gcp_project_id cannot end with a hyphen"
            )
        
        if '--' in v:
            raise ValueError(
                "gcp_project_id cannot contain consecutive hyphens"
            )
        
        if not all(c.islower() or c.isdigit() or c == '-' for c in v):
            raise ValueError(
                "gcp_project_id must contain only lowercase letters, digits, and hyphens"
            )
        
        return v

    @field_validator('gcp_region')
    @classmethod
    def validate_gcp_region(cls, v: str) -> str:
        """Validate GCP region format."""
        if not v or v.strip() == "":
            raise ValueError("gcp_region cannot be empty")
        
        v = v.strip().lower()
        
        # GCP regions follow pattern: <continent/country>-<area><number>
        # Examples: us-central1, europe-west1, asia-northeast1, northamerica-northeast1
        # More restrictive pattern to match actual GCP region naming conventions
        # Allows multi-word continents (e.g., northamerica) and areas (e.g., northeast)
        if not re.match(r'^[a-z]+(?:-[a-z]+)*-[a-z]+\d+$', v):
            raise ValueError(
                f"gcp_region must be a valid GCP region format (e.g., us-central1, europe-west1), got: {v}"
            )
        
        return v

    @field_validator('cloud_run_service')
    @classmethod
    def validate_cloud_run_service(cls, v: str) -> str:
        """Validate Cloud Run service name format."""
        if not v or v.strip() == "":
            raise ValueError("cloud_run_service cannot be empty")
        
        v = v.strip()
        
        # Cloud Run service names must be lowercase alphanumeric and hyphens, max 63 chars
        if len(v) > 63:
            raise ValueError(
                f"cloud_run_service must be max 63 characters, got {len(v)} characters"
            )
        
        if not all(c.islower() or c.isdigit() or c == '-' for c in v):
            raise ValueError(
                "cloud_run_service must contain only lowercase letters, digits, and hyphens"
            )
        
        return v

    @field_validator('artifact_repo')
    @classmethod
    def validate_artifact_repo(cls, v: str) -> str:
        """Validate Artifact Registry repository name format."""
        if not v or v.strip() == "":
            raise ValueError("artifact_repo cannot be empty")
        
        v = v.strip()
        
        # Artifact Registry repo names must be lowercase alphanumeric and hyphens
        if not all(c.islower() or c.isdigit() or c == '-' for c in v):
            raise ValueError(
                "artifact_repo must contain only lowercase letters, digits, and hyphens"
            )
        
        return v

    @field_validator('secret_manager_config')
    @classmethod
    def validate_secret_manager_config(cls, v: str) -> str:
        """Validate Secret Manager configuration mode."""
        valid_modes = {'disabled', 'env_vars', 'volume'}
        v_lower = v.lower().strip()
        if v_lower not in valid_modes:
            raise ValueError(
                f"secret_manager_config must be one of {valid_modes}, got: {v}"
            )
        return v_lower

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
