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
"""FastAPI application entry point for Dungeon Master service.

This module creates and configures the FastAPI application with:
- Route registration
- CORS middleware (for web client access)
- Lifespan management for HTTP client
- OpenAPI/Swagger documentation
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import AsyncClient
import logging

from app.api.routes import router
from app.config import get_settings
from app.middleware import RequestCorrelationMiddleware
from app.logging import configure_logging
from app.metrics import init_metrics_collector, disable_metrics_collector

# Will be configured in lifespan
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.
    
    Handles startup and shutdown logic:
    - Startup: Initialize HTTP client, validate config, create service clients
    - Shutdown: Close HTTP client gracefully
    
    Args:
        app: FastAPI application instance
    """
    # Startup
    logger.info("Starting Dungeon Master service...")

    # Validate configuration at startup
    try:
        settings = get_settings()
        
        # Configure logging with settings
        configure_logging(
            level=settings.log_level,
            json_format=settings.log_json_format,
            service_name=settings.service_name
        )
        
        logger.info("Configuration loaded successfully")
        logger.info(f"Journey-log base URL: {settings.journey_log_base_url}")
        logger.info(f"OpenAI model: {settings.openai_model}")
        logger.info(f"Health check journey-log: {settings.health_check_journey_log}")
        logger.info(f"Metrics enabled: {settings.enable_metrics}")
        
        # Initialize metrics collector if enabled
        if settings.enable_metrics:
            init_metrics_collector()
            logger.info("Metrics collector initialized")
        else:
            disable_metrics_collector()
            logger.info("Metrics collection disabled")
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        raise

    # Initialize HTTP client and store in app state
    app.state.http_client = AsyncClient()
    logger.info("HTTP client initialized")

    # Initialize shared service clients and store in app state
    from app.services.llm_client import LLMClient
    from app.services.journey_log_client import JourneyLogClient
    from app.services.policy_engine import PolicyEngine
    from app.services.turn_orchestrator import TurnOrchestrator
    from app.prompting.prompt_builder import PromptBuilder

    app.state.llm_client = LLMClient(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        timeout=settings.openai_timeout,
        stub_mode=settings.openai_stub_mode
    )
    logger.info(f"LLM client initialized (model={settings.openai_model}, stub_mode={settings.openai_stub_mode})")

    app.state.journey_log_client = JourneyLogClient(
        base_url=settings.journey_log_base_url,
        http_client=app.state.http_client,
        timeout=settings.journey_log_timeout,
        recent_n_default=settings.journey_log_recent_n
    )
    logger.info(f"Journey-log client initialized (base_url={settings.journey_log_base_url})")

    app.state.policy_engine = PolicyEngine(
        quest_trigger_prob=settings.quest_trigger_prob,
        quest_cooldown_turns=settings.quest_cooldown_turns,
        poi_trigger_prob=settings.poi_trigger_prob,
        poi_cooldown_turns=settings.poi_cooldown_turns,
        rng_seed=settings.rng_seed
    )
    logger.info(f"Policy engine initialized (quest_prob={settings.quest_trigger_prob}, poi_prob={settings.poi_trigger_prob})")
    
    app.state.prompt_builder = PromptBuilder()
    logger.info("Prompt builder initialized")
    
    app.state.turn_orchestrator = TurnOrchestrator(
        policy_engine=app.state.policy_engine,
        llm_client=app.state.llm_client,
        journey_log_client=app.state.journey_log_client,
        prompt_builder=app.state.prompt_builder,
        poi_memory_spark_enabled=settings.poi_memory_spark_enabled,
        poi_memory_spark_count=settings.poi_memory_spark_count
    )
    logger.info("Turn orchestrator initialized")

    yield

    # Shutdown
    logger.info("Shutting down Dungeon Master service...")
    if hasattr(app.state, 'http_client'):
        await app.state.http_client.aclose()
        logger.info("HTTP client closed")


# Create FastAPI application
app = FastAPI(
    title="Dungeon Master API",
    description=(
        "AI-powered narrative generation service for dungeon crawling adventures. "
        "Orchestrates journey-log context retrieval and LLM-based story generation."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configure CORS for web client access
# NOTE: Unrestricted CORS is acceptable for this service as it's designed
# to be accessed by web clients. In production, configure allow_origins
# to match your specific domain(s) or use environment variables.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Consider restricting in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add request correlation middleware
app.add_middleware(RequestCorrelationMiddleware)

# Register routes
app.include_router(router, tags=["game"])

logger.info("FastAPI application configured")


# Dependency override for HTTP client using FastAPI's dependency system
def get_http_client_override() -> AsyncClient:
    """Dependency override that provides the HTTP client from app state.
    
    This function is used to override the placeholder dependency in routes.
    It accesses the HTTP client stored in app.state during lifespan startup.
    
    Returns:
        AsyncClient instance from app state
        
    Raises:
        RuntimeError: If HTTP client is not initialized in app state
    """
    if not hasattr(app.state, 'http_client'):
        raise RuntimeError(
            "HTTP client not initialized. "
            "Ensure the application lifespan has started."
        )
    return app.state.http_client


def get_journey_log_client_override():
    """Dependency override that provides the JourneyLogClient from app state.
    
    Returns:
        JourneyLogClient instance from app state
        
    Raises:
        RuntimeError: If journey_log_client is not initialized in app state
    """
    if not hasattr(app.state, 'journey_log_client'):
        raise RuntimeError(
            "Journey-log client not initialized. "
            "Ensure the application lifespan has started."
        )
    return app.state.journey_log_client


def get_llm_client_override():
    """Dependency override that provides the LLMClient from app state.
    
    Returns:
        LLMClient instance from app state
        
    Raises:
        RuntimeError: If llm_client is not initialized in app state
    """
    if not hasattr(app.state, 'llm_client'):
        raise RuntimeError(
            "LLM client not initialized. "
            "Ensure the application lifespan has started."
        )
    return app.state.llm_client


def get_policy_engine_override():
    """Dependency override that provides the PolicyEngine from app state.
    
    Returns:
        PolicyEngine instance from app state
        
    Raises:
        RuntimeError: If policy_engine is not initialized in app state
    """
    if not hasattr(app.state, 'policy_engine'):
        raise RuntimeError(
            "Policy engine not initialized. "
            "Ensure the application lifespan has started."
        )
    return app.state.policy_engine


def get_turn_orchestrator_override():
    """Dependency override that provides the TurnOrchestrator from app state.
    
    Returns:
        TurnOrchestrator instance from app state
        
    Raises:
        RuntimeError: If turn_orchestrator is not initialized in app state
    """
    if not hasattr(app.state, 'turn_orchestrator'):
        raise RuntimeError(
            "Turn orchestrator not initialized. "
            "Ensure the application lifespan has started."
        )
    return app.state.turn_orchestrator


# Use FastAPI's dependency_overrides instead of monkey-patching
from app.api.routes import (
    get_http_client,
    get_journey_log_client,
    get_llm_client,
    get_policy_engine,
    get_turn_orchestrator
)  # noqa: E402
app.dependency_overrides[get_http_client] = get_http_client_override
app.dependency_overrides[get_journey_log_client] = get_journey_log_client_override
app.dependency_overrides[get_llm_client] = get_llm_client_override
app.dependency_overrides[get_policy_engine] = get_policy_engine_override
app.dependency_overrides[get_turn_orchestrator] = get_turn_orchestrator_override


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    # Configure log level from settings
    logging.getLogger().setLevel(settings.log_level)

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level=settings.log_level.lower()
    )
