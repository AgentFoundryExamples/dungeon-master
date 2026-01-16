# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 24
- **Intra-repo dependencies**: 43
- **External stdlib dependencies**: 24
- **External third-party dependencies**: 26

## External Dependencies

### Standard Library / Core Modules

Total: 24 unique modules

- `asyncio`
- `collections.defaultdict`
- `contextlib.asynccontextmanager`
- `contextvars.ContextVar`
- `dataclasses.dataclass`
- `functools.lru_cache`
- `json`
- `logging`
- `os`
- `re`
- `threading.Lock`
- `time`
- `typing.Any`
- `typing.Callable`
- `typing.Dict`
- `typing.List`
- `typing.Literal`
- `typing.Optional`
- `typing.Tuple`
- `unittest.mock.AsyncMock`
- ... and 4 more (see JSON for full list)

### Third-Party Packages

Total: 26 unique packages

- `fastapi.APIRouter`
- `fastapi.Depends`
- `fastapi.FastAPI`
- `fastapi.HTTPException`
- `fastapi.Request`
- `fastapi.Response`
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
- ... and 6 more (see JSON for full list)

## Most Depended Upon Files (Intra-Repo)

- `app/services/llm_client.py` (7 dependents)
- `app/models.py` (6 dependents)
- `app/config.py` (5 dependents)
- `app/services/journey_log_client.py` (5 dependents)
- `app/logging.py` (5 dependents)
- `app/metrics.py` (4 dependents)
- `app/api/routes.py` (3 dependents)
- `app/main.py` (3 dependents)
- `app/prompting/prompt_builder.py` (2 dependents)
- `app/middleware.py` (1 dependents)

## Files with Most Dependencies (Intra-Repo)

- `app/api/routes.py` (7 dependencies)
- `app/main.py` (7 dependencies)
- `tests/test_api.py` (6 dependencies)
- `tests/conftest.py` (5 dependencies)
- `example_openai_usage.py` (3 dependencies)
- `tests/test_metrics.py` (3 dependencies)
- `app/middleware.py` (2 dependencies)
- `app/services/journey_log_client.py` (2 dependencies)
- `tests/test_prompt_builder.py` (2 dependencies)
- `app/prompting/prompt_builder.py` (1 dependencies)
