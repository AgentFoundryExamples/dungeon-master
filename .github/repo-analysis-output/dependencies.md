# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 53
- **Intra-repo dependencies**: 159
- **External stdlib dependencies**: 43
- **External third-party dependencies**: 27

## External Dependencies

### Standard Library / Core Modules

Total: 43 unique modules

- `abc.ABC`
- `abc.abstractmethod`
- `asyncio`
- `collections.OrderedDict`
- `collections.defaultdict`
- `contextlib.asynccontextmanager`
- `contextvars.ContextVar`
- `copy.deepcopy`
- `dataclasses.dataclass`
- `datetime.datetime`
- `datetime.timezone`
- `enum.Enum`
- `functools.lru_cache`
- `functools.wraps`
- `hashlib`
- `json`
- `logging`
- `math`
- `os`
- `pathlib.Path`
- ... and 23 more (see JSON for full list)

### Third-Party Packages

Total: 27 unique packages

- `fastapi.APIRouter`
- `fastapi.Depends`
- `fastapi.FastAPI`
- `fastapi.HTTPException`
- `fastapi.Request`
- `fastapi.Response`
- `fastapi.middleware.cors.CORSMiddleware`
- `fastapi.responses.StreamingResponse`
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
- ... and 7 more (see JSON for full list)

## Most Depended Upon Files (Intra-Repo)

- `app/models.py` (25 dependents)
- `app/services/journey_log_client.py` (14 dependents)
- `app/services/llm_client.py` (14 dependents)
- `app/services/outcome_parser.py` (14 dependents)
- `app/logging.py` (13 dependents)
- `app/services/policy_engine.py` (13 dependents)
- `app/metrics.py` (11 dependents)
- `app/prompting/prompt_builder.py` (11 dependents)
- `app/services/turn_orchestrator.py` (10 dependents)
- `app/config.py` (8 dependents)

## Files with Most Dependencies (Intra-Repo)

- `app/main.py` (13 dependencies)
- `app/api/routes.py` (12 dependencies)
- `tests/test_acceptance_criteria.py` (10 dependencies)
- `tests/test_api.py` (10 dependencies)
- `tests/test_policy_integration.py` (9 dependencies)
- `app/services/turn_orchestrator.py` (8 dependencies)
- `tests/conftest.py` (8 dependencies)
- `tests/test_turn_integration.py` (8 dependencies)
- `tests/test_combat_integration.py` (7 dependencies)
- `tests/test_poi_memory_sparks.py` (7 dependencies)
