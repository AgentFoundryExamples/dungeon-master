# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 9
- **Intra-repo dependencies**: 9
- **External stdlib dependencies**: 10
- **External third-party dependencies**: 18

## External Dependencies

### Standard Library / Core Modules

Total: 10 unique modules

- `contextlib.asynccontextmanager`
- `functools.lru_cache`
- `logging`
- `os`
- `re`
- `time`
- `typing.List`
- `typing.Optional`
- `unittest.mock.patch`
- `uuid.UUID`

### Third-Party Packages

Total: 18 unique packages

- `fastapi.APIRouter`
- `fastapi.Depends`
- `fastapi.FastAPI`
- `fastapi.HTTPException`
- `fastapi.middleware.cors.CORSMiddleware`
- `fastapi.status`
- `fastapi.testclient.TestClient`
- `httpx.AsyncClient`
- `openai`
- `openai.OpenAI`
- `pydantic.BaseModel`
- `pydantic.Field`
- `pydantic.ValidationError`
- `pydantic.field_validator`
- `pydantic_settings.BaseSettings`
- `pydantic_settings.SettingsConfigDict`
- `pytest`
- `uvicorn`

## Most Depended Upon Files (Intra-Repo)

- `app/config.py` (3 dependents)
- `app/models.py` (2 dependents)
- `app/api/routes.py` (2 dependents)
- `app/__init__.py` (1 dependents)
- `app/main.py` (1 dependents)

## Files with Most Dependencies (Intra-Repo)

- `tests/test_api.py` (4 dependencies)
- `app/api/routes.py` (2 dependencies)
- `app/main.py` (2 dependencies)
- `example_openai_usage.py` (1 dependencies)
