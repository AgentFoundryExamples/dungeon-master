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

## 3. OBSERVABILITY & MONITORING

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

## 4. DEPLOYMENT CHECKLIST

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
