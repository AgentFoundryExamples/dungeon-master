# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 53
- **Intra-repo dependencies**: 167
- **External stdlib dependencies**: 41
- **External third-party dependencies**: 33

## External Dependencies

### Standard Library / Core Modules

Total: 41 unique modules

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
- `random`
- `re`
- ... and 21 more (see JSON for full list)

### Third-Party Packages

Total: 33 unique packages

- `fastapi.APIRouter`
- `fastapi.Depends`
- `fastapi.FastAPI`
- `fastapi.HTTPException`
- `fastapi.Header`
- `fastapi.Request`
- `fastapi.Response`
- `fastapi.Security`
- `fastapi.middleware.cors.CORSMiddleware`
- `fastapi.security.HTTPAuthorizationCredentials`
- `fastapi.security.HTTPBearer`
- `fastapi.status`
- `fastapi.testclient.TestClient`
- `firebase_admin`
- `firebase_admin.auth`
- `firebase_admin.credentials`
- `httpx.AsyncClient`
- `httpx.HTTPStatusError`
- `httpx.Request`
- `httpx.Response`
- ... and 13 more (see JSON for full list)

## Most Depended Upon Files (Intra-Repo)

- `app/models.py` (27 dependents)
- `app/services/journey_log_client.py` (14 dependents)
- `app/services/outcome_parser.py` (14 dependents)
- `app/services/llm_client.py` (13 dependents)
- `app/logging.py` (13 dependents)
- `app/services/policy_engine.py` (13 dependents)
- `app/prompting/prompt_builder.py` (12 dependents)
- `app/config.py` (11 dependents)
- `app/services/turn_orchestrator.py` (11 dependents)
- `app/metrics.py` (10 dependents)

## Files with Most Dependencies (Intra-Repo)

- `app/main.py` (14 dependencies)
- `app/api/routes.py` (12 dependencies)
- `tests/test_api.py` (11 dependencies)
- `tests/conftest.py` (10 dependencies)
- `tests/test_acceptance_criteria.py` (10 dependencies)
- `tests/test_policy_integration.py` (9 dependencies)
- `app/services/turn_orchestrator.py` (8 dependencies)
- `tests/test_turn_integration.py` (8 dependencies)
- `tests/test_combat_integration.py` (7 dependencies)
- `tests/test_poi_memory_sparks.py` (7 dependencies)
