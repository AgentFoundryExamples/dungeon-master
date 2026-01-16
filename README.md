# Dungeon Master Service

AI-powered narrative generation service for dungeon crawling adventures. The Dungeon Master service orchestrates context retrieval from the journey-log service and uses LLM-based generation to create dynamic story responses.

## Overview

This service provides a FastAPI backend that:
- Accepts player turn actions via POST /turn endpoint
- Fetches character context from the journey-log service
- Generates AI narrative responses using OpenAI GPT models
- Provides health check endpoint with optional journey-log connectivity verification

## Quick Start

### Prerequisites

- Python 3.14+ (see `python_dev_versions.txt`)
- Access to a running journey-log service
- OpenAI API key

### Installation

1. Clone the repository:
```bash
git clone https://github.com/AgentFoundryExamples/dungeon-master.git
cd dungeon-master
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env and set required values (see Configuration section below)
```

### Running the Service

Start the development server:
```bash
python -m app.main
```

Or using uvicorn directly:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

The service will be available at:
- API: http://localhost:8080
- Interactive docs (Swagger): http://localhost:8080/docs
- Alternative docs (ReDoc): http://localhost:8080/redoc
- OpenAPI schema: http://localhost:8080/openapi.json

## Configuration

All configuration is managed through environment variables. Copy `.env.example` to `.env` and configure:

### Required Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `JOURNEY_LOG_BASE_URL` | Base URL for journey-log service | `http://localhost:8000` |
| `OPENAI_API_KEY` | OpenAI API key for LLM requests | `sk-...` |

### Optional Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `JOURNEY_LOG_TIMEOUT` | `30` | HTTP timeout for journey-log (1-300 seconds) |
| `JOURNEY_LOG_RECENT_N` | `20` | Number of recent turns to fetch (1-100) |
| `OPENAI_MODEL` | `gpt-5.1` | OpenAI model for narrative generation |
| `OPENAI_TIMEOUT` | `60` | HTTP timeout for OpenAI (1-600 seconds) |
| `OPENAI_STUB_MODE` | `false` | Enable stub mode for offline development |
| `HEALTH_CHECK_JOURNEY_LOG` | `false` | Enable journey-log ping in health checks |
| `SERVICE_NAME` | `dungeon-master` | Service name for logging |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR/CRITICAL) |

### Configuration Validation

The service validates all configuration at startup and will fail fast with actionable error messages if:
- Required variables are missing
- URLs are malformed
- Numeric values are out of range
- Invalid enum values are provided

## API Documentation

### POST /turn

Process a player turn and generate AI-powered narrative response.

**Orchestration Flow:**
1. Validates the turn request
2. Fetches character context from journey-log service (recent_n=20, include_pois=false)
3. Builds a structured prompt with system instructions and context
4. Calls OpenAI Responses API (gpt-5.1) for narrative generation
5. Persists the user_action and generated narrative to journey-log
6. Returns the narrative to the client

**Request:**
```json
{
  "character_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_action": "I search the room for treasure",
  "trace_id": "optional-trace-id"
}
```

**Response:**
```json
{
  "narrative": "You search the dimly lit room and discover a glinting treasure chest..."
}
```

**Status Codes:**
- `200`: Success - narrative generated and persisted
- `400`: Invalid request (malformed UUID, validation error)
- `404`: Character not found in journey-log
- `502`: Journey-log or LLM service error
- `504`: Timeout fetching context or generating narrative

### GET /health

Check service health status with optional journey-log connectivity verification.

**Response (healthy):**
```json
{
  "status": "healthy",
  "service": "dungeon-master",
  "journey_log_accessible": true
}
```

**Response (degraded):**
```json
{
  "status": "degraded",
  "service": "dungeon-master",
  "journey_log_accessible": false
}
```

**Status Codes:**
- `200`: Service is operational (healthy or degraded)

Note: The health endpoint returns 200 even when degraded to avoid restart loops. Use the `status` field to determine actual health.

## Development

### Code Quality

Format code with ruff:
```bash
ruff format .
ruff check . --fix
```

Type check with mypy:
```bash
mypy app/
```

### Testing

Run tests with pytest:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=app tests/
```

## Deployment

### Docker

A Dockerfile following GCP Cloud Run best practices:

```dockerfile
FROM python:3.14-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Set environment for production
ENV LOG_LEVEL=INFO

# Run on port 8080 (Cloud Run default)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Google Cloud Run

Deploy to Cloud Run:

```bash
# Build and push to Artifact Registry
gcloud builds submit --tag us-central1-docker.pkg.dev/PROJECT_ID/dungeon-master/app:latest

# Deploy to Cloud Run
gcloud run deploy dungeon-master \
  --image us-central1-docker.pkg.dev/PROJECT_ID/dungeon-master/app:latest \
  --region us-central1 \
  --platform managed \
  --set-env-vars JOURNEY_LOG_BASE_URL=https://journey-log-xyz.run.app \
  --set-secrets OPENAI_API_KEY=openai-key:latest \
  --allow-unauthenticated
```

See `gcp_deployment_reference.md` for detailed deployment instructions.

## Architecture

The Dungeon Master service orchestrates context retrieval, prompt building, and LLM narrative generation:

```mermaid
graph LR
    A[Client] -->|POST /turn| B[Dungeon Master]
    B -->|1. GET /context| C[Journey-Log]
    C -->|Character State| B
    B -->|2. Build Prompt| D[PromptBuilder]
    D -->|Structured Prompt| B
    B -->|3. Generate| E[OpenAI API]
    E -->|Narrative| B
    B -->|4. POST /narrative| C
    B -->|5. Response| A
```

### Components

#### Core Application
- **app/main.py**: FastAPI application entry point and lifespan management
- **app/api/routes.py**: Route handlers with full orchestration logic
- **app/models.py**: Pydantic models for request/response validation
- **app/config.py**: Configuration loading and validation

#### Services
- **app/services/journey_log_client.py**: Client for journey-log integration
  - Fetches character context (GET /characters/{id}/context)
  - Persists narrative turns (POST /characters/{id}/narrative)
  - Handles errors, timeouts, and retries
- **app/services/llm_client.py**: Client for OpenAI Responses API
  - Uses gpt-5.1 model with JSON schema enforcement
  - Extracts narrative from structured responses
  - Supports stub mode for offline development

#### Prompting
- **app/prompting/prompt_builder.py**: Constructs LLM prompts
  - System instructions define narrative engine role
  - Serializes context (status, location, quest, combat, history)
  - Composes modular prompts for extensibility

### Data Models

**TurnRequest**: Player turn input
- `character_id` (str): UUID of the character
- `user_action` (str): Player's action (1-8000 chars)
- `trace_id` (Optional[str]): Request correlation ID

**TurnResponse**: AI-generated narrative
- `narrative` (str): Generated story response

**JourneyLogContext**: Character state from journey-log
- `character_id` (str): UUID of the character
- `status` (str): Health status (Healthy, Wounded, Dead)
- `location` (dict): Current location with id and display_name
- `active_quest` (Optional[dict]): Active quest information
- `combat_state` (Optional[dict]): Current combat state
- `recent_history` (List[dict]): Recent narrative turns

## Features

### Implemented

✅ **Full Turn Orchestration**: Complete flow from request to response
- Context retrieval from journey-log service
- Structured prompt building with game state
- LLM narrative generation via OpenAI Responses API
- Narrative persistence back to journey-log
- Comprehensive error handling and timeouts

✅ **Journey-Log Integration**:
- GET /characters/{id}/context with configurable recent_n
- POST /characters/{id}/narrative for turn persistence
- Proper error classification (404, timeouts, etc.)
- Trace ID forwarding for observability

✅ **OpenAI Responses API Integration**:
- Uses gpt-5.1 model (configurable)
- JSON schema enforcement for structured responses
- Fallback to plain text for flexible parsing
- Stub mode for offline development

✅ **Modular Prompt Building**:
- System instructions for narrative engine role
- Context serialization (status, location, quest, combat)
- Recent history integration (configurable window)
- Extensible structure for future enhancements

✅ **Comprehensive Testing**:
- 37 unit and integration tests
- Mocked dependencies for isolated testing
- Coverage for error cases and edge cases
- All tests passing

### Development Mode

Enable stub mode for offline development without API costs:
```bash
OPENAI_STUB_MODE=true
```

In stub mode:
- No actual OpenAI API calls are made
- Returns placeholder narratives for testing
- Journey-log integration still requires a running service

## Troubleshooting

### Configuration Errors

**Error:** `journey_log_base_url must start with http:// or https://`
**Solution:** Ensure JOURNEY_LOG_BASE_URL includes the protocol scheme.

**Error:** `openai_api_key cannot be empty`
**Solution:** Set OPENAI_API_KEY in your .env file or environment.

### Connection Issues

**Symptom:** 404 error on POST /turn
**Solution:** Verify character exists in journey-log service. Check character_id is valid UUID.

**Symptom:** 504 timeout error
**Solution:** Increase timeout values (JOURNEY_LOG_TIMEOUT, OPENAI_TIMEOUT) or check network connectivity.

**Symptom:** 502 Bad Gateway error
**Solution:** Verify journey-log service is running and OpenAI API key is valid.

### LLM Issues

**Symptom:** Empty or invalid narrative responses
**Solution:** Check OpenAI API key and model availability. Try stub mode for testing.

**Symptom:** High latency on turns
**Solution:** Reduce JOURNEY_LOG_RECENT_N to fetch fewer narrative turns. Increase OPENAI_TIMEOUT.

## Current Status

✅ **Fully Implemented**: All core functionality is complete and tested
- Journey-log context retrieval and narrative persistence
- OpenAI Responses API integration (gpt-5.1)
- Structured prompt building with game context
- Complete /turn endpoint orchestration
- Comprehensive error handling
- 37 passing tests with >90% coverage



# Permanents (License, Contributing, Author)

Do not change any of the below sections

## License

This Agent Foundry Project is licensed under the Apache 2.0 License - see the LICENSE file for details.

## Contributing

Feel free to submit issues and enhancement requests!

## Author

Created by Agent Foundry and John Brosnihan
