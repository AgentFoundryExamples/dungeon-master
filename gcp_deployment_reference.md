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
  gcloud logging exclusions create debug-logs \
    --log-filter='severity=DEBUG AND resource.type="cloud_run_revision"' \
    --description="Exclude debug logs to reduce costs"
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
