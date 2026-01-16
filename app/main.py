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


# Global HTTP client for dependency injection
http_client: AsyncClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.
    
    Handles startup and shutdown logic:
    - Startup: Initialize HTTP client, validate config
    - Shutdown: Close HTTP client gracefully
    
    Args:
        app: FastAPI application instance
    """
    global http_client
    
    # Startup
    logger.info("Starting Dungeon Master service...")
    
    # Validate configuration at startup
    try:
        settings = get_settings()
        logger.info(f"Configuration loaded successfully")
        logger.info(f"Journey-log base URL: {settings.journey_log_base_url}")
        logger.info(f"OpenAI model: {settings.openai_model}")
        logger.info(f"Health check journey-log: {settings.health_check_journey_log}")
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        raise
    
    # Initialize HTTP client
    http_client = AsyncClient(
        timeout=settings.journey_log_timeout
    )
    logger.info("HTTP client initialized")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Dungeon Master service...")
    if http_client:
        await http_client.aclose()
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(router, tags=["game"])

logger.info("FastAPI application configured")


# Dependency override for HTTP client
def get_http_client() -> AsyncClient:
    """Dependency that provides the global HTTP client.
    
    Returns:
        Global AsyncClient instance
    """
    return http_client


# Override the placeholder dependency in routes
from app.api import routes
routes.get_http_client = get_http_client


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
