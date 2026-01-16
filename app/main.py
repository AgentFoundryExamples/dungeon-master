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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.
    
    Handles startup and shutdown logic:
    - Startup: Initialize HTTP client, validate config
    - Shutdown: Close HTTP client gracefully
    
    Args:
        app: FastAPI application instance
    """
    # Startup
    logger.info("Starting Dungeon Master service...")

    # Validate configuration at startup
    try:
        settings = get_settings()
        logger.info("Configuration loaded successfully")
        logger.info(f"Journey-log base URL: {settings.journey_log_base_url}")
        logger.info(f"OpenAI model: {settings.openai_model}")
        logger.info(f"Health check journey-log: {settings.health_check_journey_log}")
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        raise

    # Initialize HTTP client and store in app state
    app.state.http_client = AsyncClient()
    logger.info("HTTP client initialized")

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


# Use FastAPI's dependency_overrides instead of monkey-patching
from app.api.routes import get_http_client
app.dependency_overrides[get_http_client] = get_http_client_override


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
