# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 18
- **Intra-repo dependencies**: 29
- **External stdlib dependencies**: 14
- **External third-party dependencies**: 23

## External Dependencies

### Standard Library / Core Modules

Total: 14 unique modules

- `contextlib.asynccontextmanager`
- `functools.lru_cache`
- `json`
- `logging`
- `os`
- `re`
- `time`
- `typing.List`
- `typing.Optional`
- `typing.Tuple`
- `unittest.mock.AsyncMock`
- `unittest.mock.MagicMock`
- `unittest.mock.patch`
- `uuid.UUID`

### Third-Party Packages

Total: 23 unique packages

- `fastapi.APIRouter`
- `fastapi.Depends`
- `fastapi.FastAPI`
- `fastapi.HTTPException`
- `fastapi.middleware.cors.CORSMiddleware`
- `fastapi.status`
- `fastapi.testclient.TestClient`
- `httpx.AsyncClient`
- `httpx.HTTPStatusError`
- `httpx.Request`
- `httpx.Response`
- `httpx.TimeoutException`
- `openai`
- `openai.AsyncOpenAI`
- `openai.OpenAI`
- `pydantic.BaseModel`
- `pydantic.Field`
- `pydantic.ValidationError`
- `pydantic.field_validator`
- `pydantic_settings.BaseSettings`
- ... and 3 more (see JSON for full list)

## Most Depended Upon Files (Intra-Repo)

- `app/services/llm_client.py` (6 dependents)
- `app/models.py` (5 dependents)
- `app/services/journey_log_client.py` (5 dependents)
- `app/config.py` (4 dependents)
- `app/api/routes.py` (3 dependents)
- `app/prompting/prompt_builder.py` (2 dependents)
- `app/main.py` (2 dependents)
- `app/__init__.py` (1 dependents)
- `app/services/__init__.py` (1 dependents)

## Files with Most Dependencies (Intra-Repo)

- `tests/test_api.py` (6 dependencies)
- `app/api/routes.py` (5 dependencies)
- `tests/test_turn_integration.py` (5 dependencies)
- `app/main.py` (4 dependencies)
- `example_openai_usage.py` (3 dependencies)
- `tests/test_prompt_builder.py` (2 dependencies)
- `app/prompting/prompt_builder.py` (1 dependencies)
- `app/services/journey_log_client.py` (1 dependencies)
- `tests/test_journey_log_client.py` (1 dependencies)
- `tests/test_llm_client.py` (1 dependencies)
