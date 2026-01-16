# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 41
- **Intra-repo dependencies**: 119
- **External stdlib dependencies**: 30
- **External third-party dependencies**: 26

## External Dependencies

### Standard Library / Core Modules

Total: 30 unique modules

- `asyncio`
- `collections.defaultdict`
- `contextlib.asynccontextmanager`
- `contextvars.ContextVar`
- `copy.deepcopy`
- `dataclasses.dataclass`
- `datetime.datetime`
- `datetime.timezone`
- `enum.Enum`
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
- ... and 10 more (see JSON for full list)

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

- `app/models.py` (22 dependents)
- `app/services/journey_log_client.py` (12 dependents)
- `app/services/llm_client.py` (12 dependents)
- `app/services/outcome_parser.py` (12 dependents)
- `app/services/policy_engine.py` (11 dependents)
- `app/prompting/prompt_builder.py` (9 dependents)
- `app/config.py` (8 dependents)
- `app/services/turn_orchestrator.py` (8 dependents)
- `app/logging.py` (8 dependents)
- `app/metrics.py` (6 dependents)

## Files with Most Dependencies (Intra-Repo)

- `app/main.py` (10 dependencies)
- `tests/test_acceptance_criteria.py` (10 dependencies)
- `tests/test_api.py` (10 dependencies)
- `app/api/routes.py` (8 dependencies)
- `tests/conftest.py` (8 dependencies)
- `tests/test_policy_integration.py` (8 dependencies)
- `app/services/turn_orchestrator.py` (7 dependencies)
- `tests/test_combat_integration.py` (7 dependencies)
- `tests/test_quest_integration.py` (7 dependencies)
- `app/services/llm_client.py` (4 dependencies)
