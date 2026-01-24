# GOOGLE CLOUD DEPLOYMENT CONTEXT (STRICT)
# Date: January 2026
# Target Stack: Python 3.14+, FastAPI, Cloud Run, Postgres 18

## 1. CORE PHILOSOPHY
- **Compute:** default to **Cloud Run** (Services or Jobs). Do NOT use App Engine or Cloud Functions Gen 1.
- **Functions:** If "Functions" are requested, use **Cloud Run functions** (Gen 2).
- **Registry:** STRICTLY use **Artifact Registry** (`pkg.dev`). `gcr.io` is deprecated/shutdown.
- **Identity:** Use **Workload Identity Federation** (WIF) for CI/CD. NEVER generate JSON Service Account keys.

## 2. DUNGEON MASTER DEPLOYMENT ARCHITECTURE

### A. Architecture Overview

**Service Type**: Cloud Run Service (fully managed, autoscaling HTTP service)

**Rationale**:
- **Cloud Run Services** chosen for:
  - HTTP-based request/response pattern (POST /turn endpoints)
  - Automatic scaling from 0 to handle variable player load
  - Pay-per-use pricing model (cost-effective for bursty game traffic)
  - Built-in HTTPS termination and load balancing
  - Seamless integration with Secret Manager and Cloud Monitoring
  - Fast cold start times (<1s) suitable for gameplay latency requirements

**Alternative Considered**: Cloud Run Jobs were considered but rejected because:
- Jobs are for batch/scheduled workloads, not interactive HTTP services
- Lack of automatic HTTP endpoint management
- No built-in load balancing for concurrent requests

### B. Resource Configuration Recommendations

#### CPU and Memory Allocation

**Recommended Configuration**:
```bash
--memory 1Gi --cpu 2
```

**Rationale**:
- **1 GiB Memory**: 
  - LLM client libraries and HTTP clients consume ~200-300 MB baseline
  - Turn context data (narrative history, POIs, quests) can be 100-500 KB per request
  - In-memory turn storage (up to 10,000 turns) requires ~200-500 MB
  - Headroom for request spikes and garbage collection
  - **Alternative**: 512 MiB works for low-traffic dev environments but may cause OOM under load

- **2 vCPU**: 
  - FastAPI async handling benefits from multiple cores for concurrent requests
  - LLM API calls are I/O-bound but JSON parsing/validation is CPU-intensive
  - Policy engine RNG and context building require CPU
  - **Alternative**: 1 vCPU acceptable for dev, but limits throughput to ~5-10 req/s

**Scaling for Production**:
- **Low Traffic** (< 100 daily active users): 512 MiB / 1 vCPU
- **Medium Traffic** (100-1000 daily active users): 1 GiB / 2 vCPU (recommended)
- **High Traffic** (> 1000 daily active users): 2 GiB / 4 vCPU + increase max-instances

#### Concurrency

**Recommended Configuration**:
```bash
--concurrency 80
```

**Rationale**:
- **80 concurrent requests per instance**:
  - LLM calls are async I/O-bound (awaiting OpenAI API responses)
  - Each request holds minimal memory (~5-10 MB) while waiting
  - Higher concurrency reduces cold starts and improves cost efficiency
  - Tested safe range: 50-100 (depends on LLM API latency)

- **When to Lower Concurrency**:
  - If LLM API latency spikes (> 5s), reduce to 40-50 to prevent request queuing
  - If memory usage approaches limits, reduce concurrency or increase memory

- **Rate Limiting Interaction**:
  - Service-level: `MAX_TURNS_PER_CHARACTER_PER_SECOND=2.0` (env var)
  - Instance-level: `--concurrency 80` (Cloud Run config)
  - Global: `MAX_CONCURRENT_LLM_CALLS=10` (env var, semaphore limit)
  - These work together to prevent abuse and control costs

#### Autoscaling

**Recommended Configuration**:
```bash
--min-instances 0
--max-instances 100
```

**Rationale**:
- **Min Instances = 0**: 
  - Cost optimization for dev/staging (scale to zero when idle)
  - Production may use `--min-instances 1` to eliminate cold starts for first request

- **Max Instances = 100**:
  - Caps maximum cost and prevents runaway scaling
  - At 80 concurrency: supports 8,000 concurrent requests
  - Adjust based on expected peak load and budget constraints

- **Autoscaling Metrics**:
  - Cloud Run autoscales based on CPU utilization and concurrency
  - Target: Keep CPU < 80%, concurrency < 80% of limit
  - Cold start time: < 1 second (minimal impact on gameplay)

#### Timeout

**Recommended Configuration**:
```bash
--timeout 300s
```

**Rationale**:
- **5-minute timeout** accounts for:
  - LLM generation: typically 2-10s, but can spike to 30-60s under load
  - Journey-log fetches: typically < 1s, but retries can extend this
  - Policy engine + context building: < 1s
  - Retry logic for transient failures (exponential backoff)
  - Safety margin for slow network conditions

- **When to Adjust**:
  - Reduce to 60s for dev/staging if LLM calls are consistently fast
  - Increase beyond 300s is NOT recommended (indicates deeper issues)

### C. Network Configuration

#### VPC and Egress

**Default (Public Internet Egress)**:
```bash
# No VPC flags needed for public endpoints
gcloud run deploy dungeon-master \
  --image ... \
  --allow-unauthenticated
```

**Use Case**: Dungeon Master → OpenAI API (public) + Journey-Log (public Cloud Run)

**Private VPC Egress** (if journey-log uses Cloud SQL or private IPs):
```bash
--vpc-egress=private-ranges-only \
--network=projects/PROJECT_ID/global/networks/default
```

**Rationale**:
- **Public egress** is sufficient when all dependencies are public HTTP services
- **Private egress** required only if:
  - Journey-log service uses Cloud SQL with private IP
  - Connecting to internal services on VPC
  - Compliance requires traffic to stay within GCP network

**Network Latency Expectations**:
- OpenAI API: 50-200ms (depends on region, typically US West Coast)
- Journey-log (same region): 5-50ms (Cloud Run to Cloud Run)
- Journey-log (cross-region): 50-150ms (add RTT for region distance)

#### Ingress Control

**Development/Staging**:
```bash
--allow-unauthenticated
```

**Production** (with authentication):
```bash
--no-allow-unauthenticated
--ingress=internal-and-cloud-load-balancing
```

Then configure:
- Cloud Load Balancer with Identity-Aware Proxy (IAP) for user authentication
- Or API Gateway for API key-based auth
- Or service-to-service authentication with service accounts

### D. Prerequisite Resources

Before deploying Dungeon Master to GCP, ensure the following resources exist:

#### 1. GCP Project
```bash
# Create a new project (if needed)
gcloud projects create PROJECT_ID --name="Dungeon Master Game"

# Set as active project
gcloud config set project PROJECT_ID
```

#### 2. Enable Required APIs
```bash
# Enable Cloud Run API
gcloud services enable run.googleapis.com

# Enable Artifact Registry API
gcloud services enable artifactregistry.googleapis.com

# Enable Secret Manager API (for production secrets)
gcloud services enable secretmanager.googleapis.com

# Enable Cloud Build API (for CI/CD)
gcloud services enable cloudbuild.googleapis.com

# Optional: Cloud Monitoring for metrics
gcloud services enable monitoring.googleapis.com
```

#### 3. Create Artifact Registry Repository
```bash
# Create Docker repository
gcloud artifacts repositories create dungeon-master \
  --repository-format=docker \
  --location=us-central1 \
  --description="Dungeon Master service container images"

# Configure Docker authentication
gcloud auth configure-docker us-central1-docker.pkg.dev
```

#### 4. Create Service Account (for Cloud Run)
```bash
# Create service account
gcloud iam service-accounts create dungeon-master-sa \
  --display-name="Dungeon Master Cloud Run Service Account"

# Grant minimal permissions (see IAM section below)
# Note: Cloud Run automatically grants the service account certain permissions
```

#### 5. Store Secrets in Secret Manager
```bash
# Create secret for OpenAI API key
# IMPORTANT: Replace 'YOUR_ACTUAL_API_KEY' with your real OpenAI API key
echo -n "YOUR_ACTUAL_API_KEY" | gcloud secrets create openai-api-key \
  --data-file=- \
  --replication-policy="automatic"

# Grant service account access to secret
# Replace PROJECT_ID with your actual GCP project ID
gcloud secrets add-iam-policy-binding openai-api-key \
  --member="serviceAccount:dungeon-master-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

#### 6. Configure Workload Identity Federation (for CI/CD)
```bash
# Create Workload Identity Pool for GitHub Actions
gcloud iam workload-identity-pools create github-pool \
  --location=global \
  --display-name="GitHub Actions Pool"

# Create provider
# IMPORTANT: Replace 'YOUR_GITHUB_ORG' with your GitHub organization name
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global \
  --workload-identity-pool=github-pool \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository_owner=='YOUR_GITHUB_ORG'"

# Grant permissions to deploy
# Replace PROJECT_ID, PROJECT_NUMBER, YOUR_GITHUB_ORG, and YOUR_REPO_NAME with actual values
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/YOUR_GITHUB_ORG/YOUR_REPO_NAME" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/YOUR_GITHUB_ORG/YOUR_REPO_NAME" \
  --role="roles/artifactregistry.writer"
```

### E. Required IAM Roles and Permissions

#### Service Account Roles (dungeon-master-sa)

**Minimal Production Permissions**:
```bash
# 1. Secret Manager Secret Accessor (for OpenAI API key)
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:dungeon-master-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# 2. Cloud Monitoring Metric Writer (for metrics endpoint)
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:dungeon-master-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/monitoring.metricWriter"

# 3. Cloud Logging Writer (for structured logs)
# Note: Cloud Run automatically grants this via default service account permissions
```

**Additional Roles (if needed)**:
```bash
# If journey-log uses Cloud SQL
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:dungeon-master-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"

# If service-to-service authentication required
gcloud run services add-iam-policy-binding journey-log \
  --member="serviceAccount:dungeon-master-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --region=us-central1
```

#### Developer/CI Deployment Roles

**For manual deployment** (developer workstation):
```bash
# Grant developer deploy permissions
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:developer@example.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:developer@example.com" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:developer@example.com" \
  --role="roles/iam.serviceAccountUser"
```

**For CI/CD** (via Workload Identity Federation):
- See "Prerequisite Resources" section above for WIF setup
- Grants: `roles/run.admin`, `roles/artifactregistry.writer`
- **Never use JSON service account keys** in CI/CD

### F. Multi-Environment Deployment Strategy

#### Environment Isolation Options

**Option 1: Separate GCP Projects** (Recommended)
```bash
# Development
GCP_PROJECT_ID=dungeon-master-dev
CLOUD_RUN_SERVICE=dungeon-master
ARTIFACT_REPO=dungeon-master

# Staging
GCP_PROJECT_ID=dungeon-master-staging
CLOUD_RUN_SERVICE=dungeon-master
ARTIFACT_REPO=dungeon-master

# Production
GCP_PROJECT_ID=dungeon-master-prod
CLOUD_RUN_SERVICE=dungeon-master
ARTIFACT_REPO=dungeon-master
```

**Benefits**:
- Complete resource isolation (secrets, billing, IAM)
- Clear security boundaries
- Independent billing and cost tracking

**Option 2: Single Project with Service Name Suffixes**
```bash
# All environments in same project
GCP_PROJECT_ID=dungeon-master-game

# Development
CLOUD_RUN_SERVICE=dungeon-master-dev
ARTIFACT_REPO=dungeon-master
ENVIRONMENT=development

# Staging
CLOUD_RUN_SERVICE=dungeon-master-staging
ARTIFACT_REPO=dungeon-master
ENVIRONMENT=staging

# Production
CLOUD_RUN_SERVICE=dungeon-master-prod
ARTIFACT_REPO=dungeon-master
ENVIRONMENT=production
```

**Benefits**:
- Simpler project setup
- Shared Artifact Registry (cost savings)
- Easier cross-environment testing

**Drawbacks**:
- Shared IAM policies (less security isolation)
- Risk of accidental production access from dev

#### Environment-Specific Configuration

**Development**:
```bash
# .env.development
ENVIRONMENT=development
LOG_LEVEL=DEBUG
ENABLE_DEBUG_ENDPOINTS=true
OPENAI_STUB_MODE=false  # Use real API for integration testing
ENABLE_METRICS=false
MIN_INSTANCES=0
MAX_INSTANCES=5
```

**Staging**:
```bash
# .env.staging
ENVIRONMENT=staging
LOG_LEVEL=INFO
ENABLE_DEBUG_ENDPOINTS=false
OPENAI_STUB_MODE=false
ENABLE_METRICS=true
MIN_INSTANCES=0
MAX_INSTANCES=20
```

**Production**:
```bash
# .env.production
ENVIRONMENT=production
LOG_LEVEL=INFO
ENABLE_DEBUG_ENDPOINTS=false
ADMIN_ENDPOINTS_ENABLED=false
OPENAI_STUB_MODE=false
ENABLE_METRICS=true
LOG_JSON_FORMAT=true
MIN_INSTANCES=1  # Eliminate cold starts
MAX_INSTANCES=100
SECRET_MANAGER_CONFIG=env_vars  # Use Secret Manager
```

### G. Secret Manager Integration

#### Fallback for Projects Without Secret Manager

**Option 1: Environment Variables Only** (Development/Testing)
```bash
# .env file (NOT committed to git)
SECRET_MANAGER_CONFIG=disabled
OPENAI_API_KEY=sk-your-api-key-here
```

**Risks**:
- Secrets in plaintext environment variables
- Harder to rotate secrets (requires redeployment)
- Not suitable for production

**Option 2: Manual Secret Injection** (Cloud Run without Secret Manager API)
```bash
# Deploy with secrets as environment variables (less secure)
gcloud run deploy dungeon-master \
  --set-env-vars="OPENAI_API_KEY=sk-your-api-key-here"

# WARNING: Secrets visible in deployment configs, audit logs
# Only use for non-sensitive dev environments
```

**Requirement Callout**:
```
⚠️  PRODUCTION REQUIREMENT: Secret Manager is REQUIRED for production deployments.
    
    Rationale:
    - Secrets stored encrypted at rest with automatic key rotation
    - Secret access logged in Cloud Audit Logs
    - Granular IAM controls for secret access
    - Supports secret versioning and rollback
    - Eliminates plaintext secrets in deployment configs
    
    If your project cannot enable Secret Manager:
    1. Request API enablement from your GCP admin
    2. Use a different GCP project with Secret Manager enabled
    3. Consider non-GCP deployment (Docker Compose, Kubernetes with external secrets)
```

#### Recommended Secret Manager Setup

**Store Secrets**:
```bash
# OpenAI API Key
# IMPORTANT: Replace 'YOUR_ACTUAL_API_KEY' with your real OpenAI API key
echo -n "YOUR_ACTUAL_API_KEY" | gcloud secrets create openai-api-key --data-file=-

# Optional: Journey-log service credentials (if using service accounts)
# Replace 'YOUR_ACTUAL_TOKEN' with your real journey-log token
echo -n "YOUR_ACTUAL_TOKEN" | gcloud secrets create journey-log-token --data-file=-
```

**Deploy with Secrets**:
```bash
gcloud run deploy dungeon-master \
  --set-secrets="OPENAI_API_KEY=openai-api-key:latest" \
  --set-secrets="JOURNEY_LOG_TOKEN=journey-log-token:latest" \
  --service-account=dungeon-master-sa@PROJECT_ID.iam.gserviceaccount.com
```

**Environment Variable Configuration**:
```bash
# Tell the app to expect secrets from Secret Manager
SECRET_MANAGER_CONFIG=env_vars
```

## 3. INFRASTRUCTURE SPECIFICS

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

## 4. OBSERVABILITY & MONITORING

### A. Cloud Monitoring (Metrics)
The Dungeon Master service exposes metrics via the `/metrics` endpoint that can be integrated with Cloud Monitoring.

**Enable Metrics:**
```bash
# Set environment variable
ENABLE_METRICS=true
ENVIRONMENT=production  # Label metrics by environment
```

**Metrics Export Options:**

1. **OpenCensus Exporter** (Recommended for Cloud Run):
   ```python
   # Install: pip install opencensus-ext-stackdriver
   from opencensus.ext.stackdriver import stats_exporter
   exporter = stats_exporter.new_stats_exporter()
   ```

2. **Cloud Monitoring API** (Direct integration):
   ```python
   from google.cloud import monitoring_v3
   client = monitoring_v3.MetricServiceClient()
   # Write time series data to Cloud Monitoring
   ```

3. **Prometheus Scraping** (via Managed Service for Prometheus):
   - Deploy Prometheus agent on Cloud Run
   - Configure scraping of `/metrics` endpoint
   - Metrics automatically appear in Cloud Monitoring

**Key Metrics to Monitor:**

| Metric | Type | Description | Alert Threshold |
|--------|------|-------------|-----------------|
| `turns.by_label.outcome:error` | Counter | Failed turns | > 5% of total turns |
| `latencies.llm_call.avg_ms` | Histogram | LLM latency | > 3000ms (p95) |
| `journey_log_latencies.get_context.avg_ms` | Histogram | Context fetch latency | > 500ms (p95) |
| `policy_triggers.quest:triggered` | Counter | Quest triggers | < 10/hour (too low) |
| `subsystem_deltas.narrative_persisted` | Counter | Successful persists | Should match turn count |
| `schema_conformance.conformance_rate` | Gauge | Parse success rate | < 0.95 (95%) |

**Cloud Monitoring Dashboard Example:**
```bash
# Create dashboard via gcloud CLI
gcloud monitoring dashboards create --config-from-file=dashboard.json
```

**dashboard.json:**
```json
{
  "displayName": "Dungeon Master - Production",
  "mosaicLayout": {
    "columns": 12,
    "tiles": [
      {
        "width": 6,
        "height": 4,
        "widget": {
          "title": "Turn Processing Rate",
          "xyChart": {
            "dataSets": [{
              "timeSeriesQuery": {
                "timeSeriesFilter": {
                  "filter": "metric.type=\"custom.googleapis.com/dungeon_master/turns_processed\" resource.type=\"cloud_run_revision\"",
                  "aggregation": {"alignmentPeriod": "60s", "perSeriesAligner": "ALIGN_RATE"}
                }
              }
            }]
          }
        }
      },
      {
        "xPos": 6,
        "width": 6,
        "height": 4,
        "widget": {
          "title": "LLM Latency (p95)",
          "xyChart": {
            "dataSets": [{
              "timeSeriesQuery": {
                "timeSeriesFilter": {
                  "filter": "metric.type=\"custom.googleapis.com/dungeon_master/llm_latency\" resource.type=\"cloud_run_revision\"",
                  "aggregation": {"alignmentPeriod": "60s", "perSeriesAligner": "ALIGN_PERCENTILE_95"}
                }
              }
            }]
          }
        }
      }
    ]
  }
}
```

### B. Cloud Logging (Structured Logs)
The service emits structured JSON logs compatible with Cloud Logging.

**Enable JSON Logging:**
```bash
LOG_JSON_FORMAT=true
```

**Log Router Sinks:**

Create log sinks for specific log types:

```bash
# Sink for turn logs (analytics)
gcloud logging sinks create turn-logs-sink \
  bigquery.googleapis.com/projects/PROJECT_ID/datasets/turn_logs \
  --log-filter='jsonPayload.log_type="turn" AND resource.type="cloud_run_revision"'

# Sink for error logs (alerting)
gcloud logging sinks create error-logs-sink \
  pubsub.googleapis.com/projects/PROJECT_ID/topics/error-alerts \
  --log-filter='severity>=ERROR AND resource.type="cloud_run_revision"'
```

**Query Patterns:**

1. **Find all logs for a specific turn:**
```
resource.type="cloud_run_revision"
jsonPayload.turn_id="f47ac10b-58cc-4372-a567-0e02b2c3d479"
```

2. **Find all failed turns:**
```
resource.type="cloud_run_revision"
jsonPayload.log_type="turn"
jsonPayload.outcome="error"
```

3. **Find turns with subsystem failures:**
```
resource.type="cloud_run_revision"
jsonPayload.log_type="turn"
jsonPayload.subsystem_actions.narrative="failed"
```

4. **Find high-latency turns (> 2 seconds):**
```
resource.type="cloud_run_revision"
jsonPayload.log_type="turn"
jsonPayload.latencies_ms.total_ms>2000
```

5. **Trace a character's turns:**
```
resource.type="cloud_run_revision"
jsonPayload.character_id="550e8400-e29b-41d4-a716-446655440000"
timestamp>="2026-01-17T00:00:00Z"
```

**Log-Based Metrics:**

Create metrics from logs for alerting:

```bash
# Metric for failed turns
gcloud logging metrics create failed_turns \
  --description="Count of failed turns" \
  --log-filter='jsonPayload.log_type="turn" AND jsonPayload.outcome="error"' \
  --value-extractor='EXTRACT(jsonPayload.outcome)'

# Metric for high-latency turns
gcloud logging metrics create high_latency_turns \
  --description="Count of turns exceeding 2s latency" \
  --log-filter='jsonPayload.log_type="turn" AND jsonPayload.latencies_ms.total_ms>2000'
```

**Log Sampling:**

Control log volume with sampling:

```bash
# Log only 10% of successful turns (high-volume environments)
TURN_LOG_SAMPLING_RATE=0.1
```

Note: Error logs are always emitted regardless of sampling rate.

**Cost Optimization:**

- **Log Exclusion:** Exclude verbose debug logs in production
  ```bash
  # Exclude high-volume debug logs (keep important error/warning debug logs)
  gcloud logging exclusions create verbose-debug-logs \
    --log-filter='severity=DEBUG AND resource.type="cloud_run_revision" AND NOT (jsonPayload.error_type OR jsonPayload.log_type="turn")' \
    --description="Exclude verbose debug logs while keeping error/turn debug logs"
  ```

- **Log Retention:** Set retention periods per log type
  ```bash
  # Set 30-day retention for turn logs
  gcloud logging buckets update _Default --location=global --retention-days=30
  ```

- **Bounded Labels:** Character IDs are truncated to 8 chars in metrics to prevent cardinality explosion

### C. Cloud Trace (Distributed Tracing)
For request tracing across services:

```python
# Install: pip install google-cloud-trace
from google.cloud import trace_v2
tracer = trace_v2.TraceServiceClient()
# Trace context propagated via X-Trace-Id header
```

**Trace Context Propagation:**
- `turn_id` used as trace context ID
- Propagated to journey-log via `X-Trace-Id` header
- Propagated to LLM client for end-to-end tracing

### D. Error Reporting
Integrate with Cloud Error Reporting:

```python
# Install: pip install google-cloud-error-reporting
from google.cloud import error_reporting
client = error_reporting.Client()
# Errors automatically reported from structured logs
```

**Automatic Error Grouping:**
- Errors grouped by `error_type` field
- Stack traces extracted from logs
- Alerts triggered on new error types or volume spikes

## 5. DEPLOYMENT CHECKLIST

### Pre-Deployment Preparation

**A. Dependency and Version Verification**
- [ ] Verify Python version matches `python_dev_versions.txt` (Python 3.14+)
- [ ] Verify infrastructure versions match `infrastructure_versions.txt`
- [ ] Review and pin all dependencies in `requirements.txt`
- [ ] Generate/update lockfile (`pip freeze > requirements.lock.txt`)
- [ ] Test build locally with production dependencies

**B. Environment Configuration**
- [ ] Copy `.env.example` to `.env` and configure all required variables
- [ ] Set `JOURNEY_LOG_BASE_URL` to production journey-log service
- [ ] Set `OPENAI_API_KEY` (or other LLM provider API key)
- [ ] Configure `OPENAI_MODEL` (must match `infrastructure_versions.txt`: gpt-5.1+)
- [ ] Configure `ENVIRONMENT` label (production/staging/development)
- [ ] Set appropriate timeouts (`JOURNEY_LOG_TIMEOUT`, `OPENAI_TIMEOUT`)
- [ ] Configure rate limits (`MAX_TURNS_PER_CHARACTER_PER_SECOND`, `MAX_CONCURRENT_LLM_CALLS`)
- [ ] Configure retry policies (`LLM_MAX_RETRIES`, `JOURNEY_LOG_MAX_RETRIES`)
- [ ] Configure policy engine parameters (`QUEST_TRIGGER_PROB`, `POI_TRIGGER_PROB`, etc.)
- [ ] Enable metrics and logging (`ENABLE_METRICS=true`, `LOG_JSON_FORMAT=true`, `LOG_LEVEL=INFO`)
- [ ] DISABLE debug endpoints (`ENABLE_DEBUG_ENDPOINTS=false`)

**C. Secrets Management**
- [ ] Store API keys in Google Secret Manager (do NOT use JSON service account keys)
- [ ] Grant Cloud Run service account access to secrets
- [ ] Configure secrets as environment variables or volume mounts in Cloud Run
- [ ] Document secret rotation procedures
- [ ] Set up alerts for secret expiration (if applicable)

**D. Cloud Infrastructure Setup**
- [ ] Create Artifact Registry repository (docker format)
- [ ] Configure Workload Identity Federation for CI/CD (no JSON keys)
- [ ] Set up Cloud Run service with appropriate resources (memory, CPU, concurrency)
- [ ] Configure VPC egress for journey-log connectivity (if needed)
- [ ] Set up Cloud SQL connection (if journey-log uses Cloud SQL)
- [ ] Configure IAM roles for service account (minimal permissions)

### Build and Push

**E. Build Docker Image**
```bash
# Build image locally (testing)
docker build -t dungeon-master:local .

# Build and tag for Artifact Registry
docker build -t us-central1-docker.pkg.dev/PROJECT_ID/dungeon-master/app:v1.0.0 .

# Test image locally
docker run -p 8080:8080 --env-file .env dungeon-master:local
curl http://localhost:8080/health
```

**F. Push to Artifact Registry**
```bash
# Authenticate docker to Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev

# Push image
docker push us-central1-docker.pkg.dev/PROJECT_ID/dungeon-master/app:v1.0.0
```

### Deployment

**G. Deploy to Cloud Run**
```bash
# Deploy service
gcloud run deploy dungeon-master \
  --image us-central1-docker.pkg.dev/PROJECT_ID/dungeon-master/app:v1.0.0 \
  --region us-central1 \
  --platform managed \
  --memory 1Gi \
  --cpu 2 \
  --concurrency 80 \
  --max-instances 100 \
  --timeout 300s \
  --set-env-vars "JOURNEY_LOG_BASE_URL=https://journey-log-xyz.a.run.app" \
  --set-secrets "OPENAI_API_KEY=openai-api-key:latest" \
  --set-env-vars "ENVIRONMENT=production,ENABLE_METRICS=true,LOG_JSON_FORMAT=true" \
  --allow-unauthenticated \
  --service-account dungeon-master@PROJECT_ID.iam.gserviceaccount.com
```

**H. Traffic Management**
```bash
# Deploy with gradual rollout (50% traffic to new revision)
gcloud run services update-traffic dungeon-master \
  --to-revisions LATEST=50 \
  --region us-central1

# Monitor metrics for 10-15 minutes, then complete rollout
gcloud run services update-traffic dungeon-master \
  --to-latest \
  --region us-central1
```

### Post-Deployment Validation

**I. Health and Smoke Tests**
```bash
# Check service health
curl https://dungeon-master-xyz.a.run.app/health

# Expected response:
# {"status":"healthy","service":"dungeon-master","journey_log_accessible":true}

# Test turn endpoint (smoke test with test character)
curl -X POST https://dungeon-master-xyz.a.run.app/turn \
  -H "Content-Type: application/json" \
  -d '{
    "character_id": "test-character-uuid",
    "user_action": "I look around."
  }'

# Test streaming endpoint (if applicable)
curl -N https://dungeon-master-xyz.a.run.app/turn/stream \
  -H "Content-Type: application/json" \
  -d '{
    "character_id": "test-character-uuid",
    "user_action": "I explore the dungeon."
  }'
```

**J. Metrics Verification**
```bash
# Check metrics endpoint (if enabled)
curl https://dungeon-master-xyz.a.run.app/metrics

# Verify key metrics are present:
# - uptime_seconds
# - turns_processed (by outcome)
# - latencies (avg, min, max for turn, llm_call, journey_log_fetch)
# - errors (by type)
```

**K. Log Verification**
```bash
# View recent logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=dungeon-master" \
  --limit 50 \
  --format json

# Check for structured turn logs
gcloud logging read "resource.type=cloud_run_revision AND jsonPayload.log_type=turn" \
  --limit 10 \
  --format json

# Check for errors
gcloud logging read "resource.type=cloud_run_revision AND severity>=ERROR" \
  --limit 20 \
  --format json
```

### Ongoing Operations

**L. Monitoring and Alerts**
- [ ] Set up Cloud Monitoring dashboard for key metrics (turn rate, latency, errors)
- [ ] Configure alerting policies for:
  - Turn error rate > 5%
  - LLM latency p95 > 3000ms
  - Journey-log latency p95 > 500ms
  - Service availability < 99.5%
- [ ] Set up log-based metrics for subsystem failures
- [ ] Configure error reporting alerts for new error types

**M. Secret Rotation**
```bash
# Rotate OpenAI API key (example)
# 1. Generate new API key in OpenAI dashboard
# 2. Add new secret version to Secret Manager
gcloud secrets versions add openai-api-key --data-file=new-key.txt

# 3. Update Cloud Run to use new secret version
gcloud run services update dungeon-master \
  --update-secrets "OPENAI_API_KEY=openai-api-key:latest" \
  --region us-central1

# 4. Verify service health after rotation
curl https://dungeon-master-xyz.a.run.app/health

# 5. Delete old secret version after verification period
gcloud secrets versions destroy VERSION_ID --secret openai-api-key
```

**N. Rollback Procedures**
```bash
# List recent revisions
gcloud run revisions list --service dungeon-master --region us-central1

# Rollback to previous revision
gcloud run services update-traffic dungeon-master \
  --to-revisions REVISION_NAME=100 \
  --region us-central1

# Or rollback to specific tag
gcloud run services update-traffic dungeon-master \
  --to-tags stable=100 \
  --region us-central1
```

### Deployment Environment Variables Reference

**Critical Environment Variables for Production:**
```bash
# Required
JOURNEY_LOG_BASE_URL=https://journey-log-xyz.a.run.app
OPENAI_API_KEY=<from-secret-manager>
OPENAI_MODEL=gpt-5.1

# Recommended
ENVIRONMENT=production
LOG_LEVEL=INFO
LOG_JSON_FORMAT=true
ENABLE_METRICS=true
MAX_TURNS_PER_CHARACTER_PER_SECOND=2.0
MAX_CONCURRENT_LLM_CALLS=10

# Security
ENABLE_DEBUG_ENDPOINTS=false
ADMIN_ENDPOINTS_ENABLED=false  # Unless needed with proper IAM

# Timeouts and Retries
JOURNEY_LOG_TIMEOUT=30
OPENAI_TIMEOUT=60
LLM_MAX_RETRIES=3
JOURNEY_LOG_MAX_RETRIES=3

# Policy Engine (adjust per game design)
QUEST_TRIGGER_PROB=0.3
QUEST_COOLDOWN_TURNS=5
POI_TRIGGER_PROB=0.2
POI_COOLDOWN_TURNS=3
POI_MEMORY_SPARK_ENABLED=false  # Optional feature
```

### Streaming Mode Considerations

When deploying with streaming endpoint support:
- [ ] Ensure client infrastructure supports Server-Sent Events (SSE)
- [ ] Configure appropriate timeouts (streaming can take longer than synchronous)
- [ ] Monitor client disconnect rates and incomplete streams
- [ ] Test with various network conditions (slow connections, intermittent disconnects)
- [ ] Document client-side SSE implementation requirements

**Streaming-Specific Metrics:**
- `stream_starts`: Total streaming requests started
- `stream_completions`: Streams successfully completed
- `stream_client_disconnects`: Streams interrupted by client
- `stream_parse_failures`: Phase 2 validation failures

### Character Status and Game Over Logic

The system enforces strict status transitions (Healthy → Wounded → Dead) with game over logic embedded in the LLM system prompt:

- [ ] Verify status transition rules are present in system prompt (`app/prompting/prompt_builder.py`)
- [ ] Test that LLM generates conclusive narratives on character death
- [ ] Test that LLM sets all intents to "none" when character status is Dead
- [ ] Document client-side handling of Dead status (prevent further turns)
- [ ] Monitor for instances where LLM violates status rules (manual review)

**No configuration variables are needed** - status rules are embedded in the system prompt and enforced by LLM instruction compliance.

### Troubleshooting Common Deployment Issues

**Issue: Service fails to start**
- Check Cloud Run logs for startup errors
- Verify all required environment variables are set
- Verify secrets are accessible to service account
- Check journey-log connectivity from Cloud Run

**Issue: High latency (> 3s per turn)**
- Check LLM API latency metrics
- Check journey-log latency metrics
- Verify network connectivity between services
- Consider increasing Cloud Run CPU allocation
- Review concurrent request patterns

**Issue: LLM generation failures**
- Verify OpenAI API key is valid and has quota
- Check LLM model name matches supported models (gpt-5.1+)
- Review LLM error logs for specific error types
- Verify schema compatibility with current model

**Issue: Journey-log connectivity errors**
- Verify journey-log service is running and healthy
- Check VPC egress configuration (if applicable)
- Verify service account has necessary IAM permissions
- Test journey-log connectivity from Cloud Shell

**Issue: Rate limiting errors**
- Review rate limit configuration (`MAX_TURNS_PER_CHARACTER_PER_SECOND`)
- Check LLM API rate limits and quotas
- Monitor concurrent request patterns
- Consider increasing limits for high-traffic characters

**Issue: Secret rotation causing errors**
- Verify new secret version is active in Secret Manager
- Check Cloud Run service is using latest secret version
- Allow propagation time (1-2 minutes) after secret update
- Verify old secret version was not deleted prematurely

---

**Deployment Checklist Summary:**
1. ✅ Verify dependencies and versions
2. ✅ Configure environment variables and secrets
3. ✅ Set up Cloud infrastructure (Artifact Registry, Cloud Run)
4. ✅ Build and push Docker image
5. ✅ Deploy to Cloud Run with gradual rollout
6. ✅ Run health and smoke tests
7. ✅ Verify metrics and logs
8. ✅ Set up monitoring and alerts
9. ✅ Document secret rotation procedures
10. ✅ Test rollback procedures

## 7. SERVICE DISCOVERY AND NETWORKING

### A. Service Discovery Strategies

The Dungeon Master service supports multiple discovery strategies based on deployment requirements.

#### Cloud Run Default Domain (Recommended for Dev/Staging)

Every Cloud Run service receives an automatic HTTPS domain:
```
https://SERVICE_NAME-HASH-REGION_CODE.a.run.app
```

**Benefits:**
- Zero configuration required
- Automatic SSL/TLS certificates
- Global load balancing
- High availability built-in

**Get Service URL:**
```bash
gcloud run services describe dungeon-master \
  --region us-central1 \
  --format 'value(status.url)'
```

#### Custom Domain Mapping (Production)

For production deployments with branded domains:

```bash
# Map custom domain
gcloud run domain-mappings create \
  --service dungeon-master \
  --domain api.yourgame.com \
  --region us-central1

# Configure DNS (CNAME record)
# Type:  CNAME
# Name:  api
# Value: ghs.googlehosted.com
```

**SSL Certificate:** Automatically provisioned and renewed by Google (15-60 minutes after DNS propagation).

#### API Gateway (Production with Rate Limiting)

For public APIs requiring authentication and rate limiting:

```bash
# Deploy API Gateway
gcloud api-gateway api-configs create dungeon-master-config \
  --api=dungeon-master-api \
  --openapi-spec=infra/networking/api_gateway.yaml \
  --backend-auth-service-account=dungeon-master-sa@PROJECT_ID.iam.gserviceaccount.com

gcloud api-gateway gateways create dungeon-master-gateway \
  --api=dungeon-master-api \
  --api-config=dungeon-master-config \
  --location=us-central1
```

See `infra/networking/README.md` for detailed setup instructions.

### B. VPC and Private Networking

For private deployments requiring VPC connectivity (e.g., Cloud SQL with private IP):

#### Create VPC Connector

```bash
gcloud compute networks vpc-access connectors create dungeon-master-connector \
  --region=us-central1 \
  --network=default \
  --range=10.8.0.0/28 \
  --min-instances=2 \
  --max-instances=10
```

#### Configure Cloud Run Service

```bash
gcloud run services update dungeon-master \
  --vpc-connector dungeon-master-connector \
  --vpc-egress private-ranges-only \
  --region us-central1
```

Or use Terraform configuration: `infra/networking/vpc_connector.tf`

**VPC Egress Options:**
- `private-ranges-only`: Only private IP ranges through VPC (recommended)
- `all-traffic`: All egress through VPC (for compliance requirements)

### C. Multi-Region Deployment

For global availability and reduced latency:

#### Active-Active Strategy

Deploy to multiple regions with Cloud Load Balancer:

```bash
# Deploy to multiple regions
for REGION in us-central1 us-east1 europe-west1; do
  gcloud run deploy dungeon-master \
    --image us-central1-docker.pkg.dev/PROJECT_ID/dungeon-master/dungeon-master:latest \
    --region ${REGION} \
    --no-allow-unauthenticated
done

# Configure Cloud Load Balancer with Network Endpoint Groups (NEGs)
```

#### DNS Conflict Prevention

Use region-specific service names:
```
dungeon-master-us-central1
dungeon-master-us-east1
dungeon-master-europe-west1
```

Or Cloud Run traffic tags:
```
https://primary---dungeon-master-HASH-uc.a.run.app
https://failover---dungeon-master-HASH-ue.a.run.app
```

### D. Preview Environments

For PR testing and feature branches:

```bash
# Deploy preview environment
PREVIEW_NAME="dungeon-master-pr-${PR_NUMBER}"

gcloud run deploy ${PREVIEW_NAME} \
  --image us-central1-docker.pkg.dev/PROJECT_ID/dungeon-master/dungeon-master:pr-${PR_NUMBER} \
  --region us-central1 \
  --no-traffic \
  --tag pr-${PR_NUMBER}

# Get preview URL
gcloud run services describe ${PREVIEW_NAME} \
  --region us-central1 \
  --format 'value(status.url)'
```

**Auto-Cleanup:** Delete preview environments after PR merge to avoid resource waste.

## 8. AUTOSCALING AND TRAFFIC MANAGEMENT

### A. Autoscaling Configuration

Cloud Run autoscales based on:
1. **Concurrent requests** per instance (containerConcurrency)
2. **CPU utilization** (target: < 80%)
3. **Memory utilization** (target: < 80%)

#### Recommended Settings

```bash
--min-instances 0      # Cost optimization (scale to zero when idle)
--max-instances 100    # Cap costs and prevent quota exhaustion
--concurrency 80       # 80 concurrent requests per instance
```

#### Production Adjustments

**Low Traffic** (< 100 daily active users):
```bash
--min-instances 0
--max-instances 10
--concurrency 50
```

**Medium Traffic** (100-1000 daily active users):
```bash
--min-instances 1      # Eliminate first cold start
--max-instances 100
--concurrency 80
```

**High Traffic** (> 1000 daily active users):
```bash
--min-instances 5      # Always-warm instances
--max-instances 200    # Higher capacity
--concurrency 100
--cpu 4                # More CPU per instance
--memory 2Gi           # More memory per instance
```

### B. Cold Start Mitigation

**Problem:** First request to a scaled-to-zero service experiences 1-3 second delay.

**Solutions:**

#### 1. Set min-instances > 0 (Simple, Costs $$$)

```bash
gcloud run services update dungeon-master \
  --min-instances 1 \
  --region us-central1
```

**Cost Impact:** ~$20-30/month per instance at 1 GiB RAM, 2 vCPU

#### 2. Enable Startup CPU Boost (Free, Limited Impact)

Already enabled in `infra/cloudrun/service.yaml`:
```yaml
annotations:
  run.googleapis.com/startup-cpu-boost: "true"
```

**Impact:** Reduces cold start from ~2s to ~1s

#### 3. Scheduled Traffic (Free, Periodic)

Use Cloud Scheduler to ping service periodically:

```bash
# Create Cloud Scheduler job to keep service warm
gcloud scheduler jobs create http keep-warm-dungeon-master \
  --schedule="*/10 * * * *" \
  --uri="https://dungeon-master-SERVICE_ID-uc.a.run.app/health" \
  --http-method=GET \
  --location=us-central1
```

**Impact:** Keeps at least one instance warm during business hours

#### 4. Optimize Container Startup (Free, Engineering Effort)

- Minimize dependencies loaded at startup
- Use lazy imports for heavy libraries
- Pre-compile Python bytecode in Docker image

### C. Traffic Rollout Strategies

Cloud Run supports gradual traffic migration for safe deployments.

#### Blue/Green Deployment (Zero-Downtime)

Deploy new revision with 0% traffic, then shift all traffic instantly:

```bash
# Deploy new revision (0% traffic)
gcloud run deploy dungeon-master \
  --image IMAGE_URL \
  --no-traffic \
  --region us-central1

# Get new revision name
NEW_REVISION=$(gcloud run services describe dungeon-master \
  --region us-central1 \
  --format 'value(status.latestReadyRevisionName)')

# Test new revision via tagged URL
curl https://${NEW_REVISION}---dungeon-master-SERVICE_ID-uc.a.run.app/health

# Shift 100% traffic if tests pass
gcloud run services update-traffic dungeon-master \
  --to-revisions ${NEW_REVISION}=100 \
  --region us-central1
```

#### Canary Deployment (Gradual Rollout)

Gradually shift traffic to new revision:

```bash
# Deploy new revision (0% traffic)
gcloud run deploy dungeon-master \
  --image IMAGE_URL \
  --no-traffic \
  --region us-central1

NEW_REVISION=$(gcloud run services describe dungeon-master \
  --region us-central1 \
  --format 'value(status.latestReadyRevisionName)')

# Shift 10% traffic to new revision
gcloud run services update-traffic dungeon-master \
  --to-revisions ${NEW_REVISION}=10 \
  --region us-central1

# Monitor metrics for 15-30 minutes
# If metrics look good, shift to 50%
gcloud run services update-traffic dungeon-master \
  --to-revisions ${NEW_REVISION}=50 \
  --region us-central1

# Finally, shift to 100%
gcloud run services update-traffic dungeon-master \
  --to-revisions ${NEW_REVISION}=100 \
  --region us-central1
```

#### A/B Testing (Split Traffic)

Route specific percentage to each revision:

```bash
# Split traffic 50/50 between two revisions
gcloud run services update-traffic dungeon-master \
  --to-revisions REVISION_A=50,REVISION_B=50 \
  --region us-central1
```

### D. Rollback Procedures

#### Fast Rollback (Shift Traffic)

If new revision has issues, instantly shift traffic back:

```bash
# List recent revisions
gcloud run revisions list \
  --service dungeon-master \
  --region us-central1 \
  --limit 5

# Shift 100% traffic to previous working revision
gcloud run services update-traffic dungeon-master \
  --to-revisions PREVIOUS_REVISION=100 \
  --region us-central1
```

**Recovery Time:** < 30 seconds

#### Complete Rollback (Redeploy)

If traffic shift isn't enough (e.g., bad database migration):

```bash
# Redeploy previous known-good image
gcloud run deploy dungeon-master \
  --image us-central1-docker.pkg.dev/PROJECT_ID/dungeon-master/dungeon-master:PREVIOUS_SHA \
  --region us-central1
```

## 9. MONITORING AND OBSERVABILITY

### A. Native Cloud Monitoring Stack

**Philosophy:** Use native GCP monitoring tools (Cloud Monitoring, Cloud Logging). Do NOT introduce third-party stacks (Prometheus, Datadog) unless explicitly required.

### B. Monitoring Artifacts

All monitoring configurations are in `infra/monitoring/`:

| File | Purpose |
|------|---------|
| `alert_policies.yaml` | Alert policies for critical conditions |
| `log_metrics.yaml` | Custom metrics from application logs |
| `dashboard.json` | Service health dashboard |
| `deploy_log_metrics.sh` | Script to deploy log-based metrics |
| `deploy_uptime_checks.sh` | Script to deploy uptime checks |

### C. Key Metrics Monitored

#### 1. Error Rate (5xx Responses)

**Metric:** `run.googleapis.com/request_count` (filtered by response_code_class=5xx)

**Threshold:** > 5% of total requests over 5-minute window

**Alert:** Critical (PagerDuty on-call)

**Dashboard Widget:** Error rate gauge

#### 2. Request Latency (P95)

**Metric:** `run.googleapis.com/request_latencies` (95th percentile)

**Threshold:** > 5 seconds over 10-minute window

**Alert:** Warning (Slack #alerts)

**Dashboard Widget:** Latency distribution heatmap

#### 3. Instance Count

**Metric:** `run.googleapis.com/container/instance_count`

**Threshold:** > 90 instances (90% of max-instances=100)

**Alert:** Warning (Email capacity-planning)

**Dashboard Widget:** Instance count time series

#### 4. LLM API Errors (Log-Based)

**Log Filter:**
```
resource.type="cloud_run_revision"
resource.labels.service_name="dungeon-master"
jsonPayload.level="ERROR"
jsonPayload.logger="llm_client"
```

**Threshold:** > 10 errors/minute over 5-minute window

**Alert:** Critical (PagerDuty on-call)

**Dashboard Widget:** LLM error rate time series

#### 5. Deployment Failures

**Metric:** `cloudbuild.googleapis.com/build/status` (filtered by status=FAILURE)

**Threshold:** Any failure

**Alert:** High (Slack #deployments)

**Purpose:** Detect CI/CD pipeline issues

#### 6. Service Availability (Uptime Check)

**Endpoint:** `https://SERVICE_URL/health`

**Frequency:** Every 1 minute

**Success Criteria:** HTTP 200 + response body contains "healthy"

**Threshold:** 2 consecutive failures

**Alert:** Critical (PagerDuty on-call)

### D. Deploying Monitoring Artifacts

#### Prerequisites

```bash
# Enable APIs
gcloud services enable monitoring.googleapis.com logging.googleapis.com

# Grant permissions
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:dungeon-master-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/monitoring.metricWriter"
```

#### Deploy Log-Based Metrics

```bash
cd infra/monitoring
bash deploy_log_metrics.sh PROJECT_ID
```

#### Deploy Alert Policies

```bash
gcloud alpha monitoring policies create \
  --policy-from-file=alert_policies.yaml
```

#### Deploy Dashboard

Import `dashboard.json` via Cloud Console:
1. Navigate to: https://console.cloud.google.com/monitoring/dashboards
2. Click "Create Dashboard"
3. Click "JSON" tab
4. Paste contents of `dashboard.json`
5. Click "Save"

#### Deploy Uptime Checks

```bash
SERVICE_URL=$(gcloud run services describe dungeon-master \
  --region us-central1 \
  --format 'value(status.url)')

bash deploy_uptime_checks.sh PROJECT_ID "$SERVICE_URL"
```

### E. Verifying Health Endpoints

The service exposes health check endpoints:

```bash
# Basic health check
curl https://SERVICE_URL/health

# Expected response:
# {"status": "healthy", "service": "dungeon-master"}

# Health check with journey-log ping (if HEALTH_CHECK_JOURNEY_LOG=true)
# This verifies connectivity to journey-log service
curl https://SERVICE_URL/health
```

### F. Updating Monitoring Configs Post-Deploy

#### Update Alert Thresholds

```bash
# Edit alert_policies.yaml
# Change thresholdValue: 0.05 to 0.10 (allow 10% error rate)

# Reapply
gcloud alpha monitoring policies update POLICY_ID \
  --policy-from-file=alert_policies.yaml
```

#### Add Notification Channels

```bash
# Add email channel
gcloud alpha monitoring channels create \
  --display-name="Deploy Team Email" \
  --type=email \
  --channel-labels=email_address=deploy-team@example.com

# Link to alert policy
gcloud alpha monitoring policies update POLICY_ID \
  --add-notification-channels=CHANNEL_ID
```

#### Update Log Metrics

```bash
# Update metric filter to include new log patterns
gcloud logging metrics update llm_api_errors \
  --log-filter='UPDATED_FILTER_QUERY'
```

### G. Integration with On-Call Tools

#### PagerDuty

```bash
# Create PagerDuty notification channel
gcloud alpha monitoring channels create \
  --display-name="PagerDuty On-Call" \
  --type=pagerduty \
  --channel-labels=service_key=YOUR_PAGERDUTY_INTEGRATION_KEY

# Link to critical alert policies
gcloud alpha monitoring policies update POLICY_ID \
  --add-notification-channels=PAGERDUTY_CHANNEL_ID
```

#### Slack

```bash
# Create Slack notification channel
gcloud alpha monitoring channels create \
  --display-name="Slack #incidents" \
  --type=slack \
  --channel-labels=url=SLACK_WEBHOOK_URL

# Link to alert policies
gcloud alpha monitoring policies update POLICY_ID \
  --add-notification-channels=SLACK_CHANNEL_ID
```

## 10. UPDATING CONFIGURATIONS POST-DEPLOY

### A. Updating Scaling Configuration

#### Increase Max Instances (Traffic Spike)

```bash
gcloud run services update dungeon-master \
  --max-instances 200 \
  --region us-central1
```

#### Add Minimum Instances (Eliminate Cold Starts)

```bash
gcloud run services update dungeon-master \
  --min-instances 2 \
  --region us-central1
```

**Cost Impact:** Each always-on instance costs ~$20-30/month at 1Gi/2vCPU

#### Adjust Concurrency (Performance Tuning)

```bash
# Lower concurrency if instances are CPU-bound
gcloud run services update dungeon-master \
  --concurrency 50 \
  --region us-central1

# Raise concurrency if instances are I/O-bound
gcloud run services update dungeon-master \
  --concurrency 100 \
  --region us-central1
```

### B. Updating Resource Limits

#### Increase Memory (OOM Errors)

```bash
gcloud run services update dungeon-master \
  --memory 2Gi \
  --region us-central1
```

#### Increase CPU (High CPU Utilization)

```bash
gcloud run services update dungeon-master \
  --cpu 4 \
  --region us-central1
```

### C. Updating Environment Variables

#### Update Single Environment Variable

```bash
gcloud run services update dungeon-master \
  --set-env-vars LOG_LEVEL=DEBUG \
  --region us-central1
```

#### Update Multiple Environment Variables

```bash
gcloud run services update dungeon-master \
  --set-env-vars QUEST_TRIGGER_PROB=0.5,POI_TRIGGER_PROB=0.3 \
  --region us-central1
```

#### Remove Environment Variable

```bash
gcloud run services update dungeon-master \
  --remove-env-vars ENABLE_DEBUG_ENDPOINTS \
  --region us-central1
```

### D. Updating Secrets

#### Rotate OpenAI API Key

```bash
# Create new secret version
echo -n "NEW_API_KEY" | gcloud secrets versions add openai-api-key \
  --data-file=-

# Cloud Run automatically picks up latest version on next cold start
# Or force restart:
gcloud run services update dungeon-master \
  --region us-central1
```

### E. Applying Service YAML Changes

After editing `infra/cloudrun/service.yaml`:

```bash
# Replace service with updated YAML
gcloud run services replace infra/cloudrun/service.yaml \
  --region us-central1
```

**Warning:** This replaces the entire service configuration. Use `gcloud run services update` for incremental changes.

## 11. TROUBLESHOOTING COMMON ISSUES

### A. Cold Start Performance

**Symptom:** First request after idle period takes 2-5 seconds

**Solutions:**
1. Set `--min-instances 1` to keep at least one instance warm
2. Enable startup CPU boost (already enabled in service.yaml)
3. Use Cloud Scheduler to ping `/health` every 10 minutes
4. Optimize container startup (lazy imports, pre-compiled bytecode)

### B. 5xx Errors After Deployment

**Symptom:** High error rate immediately after deployment

**Troubleshooting:**
```bash
# Check recent logs
gcloud logging read 'resource.type="cloud_run_revision"
  resource.labels.service_name="dungeon-master"
  severity>=ERROR' \
  --limit=50 \
  --format=json

# Check service status
gcloud run services describe dungeon-master \
  --region us-central1

# Rollback to previous revision
gcloud run services update-traffic dungeon-master \
  --to-revisions PREVIOUS_REVISION=100 \
  --region us-central1
```

### C. Memory Limit Exceeded (OOM)

**Symptom:** Service crashes with "Memory limit exceeded" error

**Solutions:**
```bash
# Increase memory limit
gcloud run services update dungeon-master \
  --memory 2Gi \
  --region us-central1

# Or reduce concurrency to lower memory pressure
gcloud run services update dungeon-master \
  --concurrency 40 \
  --region us-central1
```

### D. Request Timeout (504 Gateway Timeout)

**Symptom:** Requests fail with 504 error after 5 minutes

**Cause:** Cloud Run timeout reached (default 300s)

**Solutions:**
```bash
# Increase timeout (max 60 minutes for HTTP/1)
gcloud run services update dungeon-master \
  --timeout 600s \
  --region us-central1

# Or optimize request processing (async patterns, streaming responses)
```

### E. VPC Connector Errors

**Symptom:** "VPC connector not found" or "VPC access denied"

**Troubleshooting:**
```bash
# Check connector status
gcloud compute networks vpc-access connectors describe dungeon-master-connector \
  --region us-central1

# Check service account permissions
gcloud projects get-iam-policy PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:dungeon-master-sa@PROJECT_ID.iam.gserviceaccount.com"
```

## 12. COST OPTIMIZATION

### A. Scaling to Zero

**Default Configuration:**
```bash
--min-instances 0
```

**Savings:** No charges when service is idle (no requests)

**Trade-off:** First request after idle experiences 1-3 second cold start

### B. Right-Sizing Resources

Start with minimal resources and scale up based on metrics:

```bash
# Start small
--memory 512Mi --cpu 1 --concurrency 50

# Monitor CPU and memory utilization
# Scale up only if:
# - CPU utilization consistently > 70%
# - Memory utilization consistently > 70%
# - Request latency > 2 seconds
```

### C. Request-Based Pricing

Cloud Run charges based on:
1. **Request count** ($0.40 per million requests)
2. **Compute time** (vCPU-seconds and GiB-seconds)

**Optimization Tips:**
- Cache responses when possible (reduce LLM API calls)
- Enable request batching for bulk operations
- Use high concurrency to maximize instance utilization

### D. Monitoring Costs

View Cloud Run costs in Cloud Console:
```
https://console.cloud.google.com/billing/reports?project=PROJECT_ID
```

Filter by:
- **SKU:** Cloud Run Requests
- **SKU:** Cloud Run CPU Allocation Time
- **SKU:** Cloud Run Memory Allocation Time

## 13. SECURITY BEST PRACTICES

### A. Service Account Permissions (Least Privilege)

Only grant required IAM roles to Cloud Run service account:

```bash
# Required for basic functionality
roles/secretmanager.secretAccessor    # Access secrets
roles/monitoring.metricWriter         # Write metrics
roles/logging.logWriter               # Write logs (auto-granted)

# Optional (only if needed)
roles/cloudsql.client                 # Cloud SQL access
roles/run.invoker                     # Invoke other Cloud Run services
```

### B. Authentication and Authorization

**Development/Staging:**
```bash
--allow-unauthenticated
```

**Production:**
```bash
--no-allow-unauthenticated

# Grant access to specific clients
gcloud run services add-iam-policy-binding dungeon-master \
  --member="serviceAccount:client-app@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

**Or use API Gateway** for API key-based authentication and rate limiting.

### C. Secret Rotation

Rotate secrets regularly (quarterly or after exposure):

```bash
# Add new secret version
echo -n "NEW_SECRET_VALUE" | gcloud secrets versions add SECRET_NAME \
  --data-file=-

# Disable old version after verification
gcloud secrets versions disable VERSION_ID \
  --secret=SECRET_NAME
```

### D. Network Security

**Ingress Control:**
```bash
# Allow only Cloud Load Balancing and internal traffic
--ingress=internal-and-cloud-load-balancing
```

**VPC Service Controls** (for highly sensitive data):
```bash
# Create VPC Service Perimeter
gcloud access-context-manager perimeters create dungeon-master-perimeter \
  --resources=projects/PROJECT_NUMBER \
  --restricted-services=run.googleapis.com,secretmanager.googleapis.com
```

---

**End of GCP Deployment Reference**

For additional details, see:
- `infra/cloudrun/service.yaml` - Service configuration
- `infra/networking/README.md` - Service discovery and networking
- `infra/monitoring/README.md` - Monitoring and alerting
- `infra/README.md` - Infrastructure deployment guide
