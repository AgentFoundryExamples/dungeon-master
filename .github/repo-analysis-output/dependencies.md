# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 34
- **Intra-repo dependencies**: 84
- **External stdlib dependencies**: 27
- **External third-party dependencies**: 26

## External Dependencies

### Standard Library / Core Modules

Total: 27 unique modules

- `asyncio`
- `collections.defaultdict`
- `contextlib.asynccontextmanager`
- `contextvars.ContextVar`
- `dataclasses.dataclass`
- `datetime.datetime`
- `functools.lru_cache`
- `hashlib`
- `json`
- `logging`
- `os`
- `random`
- `re`
- `threading.Lock`
- `time`
- `typing.Any`
- `typing.Callable`
- `typing.Dict`
- `typing.List`
- `typing.Literal`
- ... and 7 more (see JSON for full list)

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

- `app/models.py` (17 dependents)
- `app/services/llm_client.py` (9 dependents)
- `app/services/policy_engine.py` (9 dependents)
- `app/config.py` (8 dependents)
- `app/services/journey_log_client.py` (8 dependents)
- `app/logging.py` (7 dependents)
- `app/services/outcome_parser.py` (6 dependents)
- `app/metrics.py` (6 dependents)
- `app/api/routes.py` (5 dependents)
- `app/prompting/prompt_builder.py` (3 dependents)

## Files with Most Dependencies (Intra-Repo)

- `app/api/routes.py` (9 dependencies)
- `app/main.py` (8 dependencies)
- `tests/test_acceptance_criteria.py` (8 dependencies)
- `tests/test_api.py` (8 dependencies)
- `tests/test_policy_integration.py` (7 dependencies)
- `tests/conftest.py` (6 dependencies)
- `app/services/llm_client.py` (4 dependencies)
- `example_openai_usage.py` (3 dependencies)
- `tests/test_llm_client.py` (3 dependencies)
- `tests/test_metrics.py` (3 dependencies)
