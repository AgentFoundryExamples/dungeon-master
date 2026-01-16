# GOOGLE CLOUD DEPLOYMENT CONTEXT (STRICT)
# Date: January 2026
# Target Stack: Python 3.14+, FastAPI, Cloud Run, Postgres 18

## 1. CORE PHILOSOPHY
- **Compute:** default to **Cloud Run** (Services or Jobs). Do NOT use App Engine or Cloud Functions Gen 1.
- **Functions:** If "Functions" are requested, use **Cloud Run functions** (Gen 2).
- **Registry:** STRICTLY use **Artifact Registry** (`pkg.dev`). `gcr.io` is deprecated/shutdown.
- **Identity:** Use **Workload Identity Federation** (WIF) for CI/CD. NEVER generate JSON Service Account keys.

## 2. INFRASTRUCTURE SPECIFICS

### A. Python 3.14 Runtime
- **Buildpacks:** Google Buildpacks for Python 3.14+ now default to using **`uv`** for dependency resolution.
- **Base Image:** `python:3.14-slim` is the preferred Docker base.
- **Dockerfile Pattern:**
  FROM python:3.14-slim
  COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
  ENV PATH="/app/.venv/bin:$PATH"
  WORKDIR /app
  COPY pyproject.toml .
  RUN uv sync --frozen
  COPY . .
  CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]

### B. Cloud Run (Services)
- **Deploy Command:**
  gcloud run deploy service-name \
    --image LOCATION-docker.pkg.dev/PROJECT_ID/REPO/IMAGE:TAG \
    --region us-central1 \
    --allow-unauthenticated \
    --memory 512Mi --cpu 1
- **Networking:** Use **Direct VPC Egress** (not Serverless VPC Access Connectors) for database connections.
  `--vpc-egress=private-ranges-only --network=default`
- **Secrets:** Mount secrets as volumes for files, or env vars for strings.
  `--set-secrets="/secrets/api_key=my-secret:latest"`

### C. Cloud Run functions (Gen 2)
- **Naming:** Refer to them as "Cloud Run functions".
- **Deploy Command:**
  gcloud functions deploy my-function \
    --gen2 \
    --runtime=python314 \
    --region=us-central1 \
    --source=. \
    --entry-point=main \
    --trigger-http

### D. Artifact Registry
- **Format:** `LOCATION-docker.pkg.dev/PROJECT-ID/REPOSITORY-ID/IMAGE:TAG`
- **Creation:**
  gcloud artifacts repositories create my-repo \
    --repository-format=docker \
    --location=us-central1

### E. PostgreSQL 18 (Cloud SQL)
- **Connection:** Use `cloud_sql_proxy` (v2) or the Python `cloud-sql-python-connector` library.
- **Async Driver:** `asyncpg` is preferred for FastAPI.
