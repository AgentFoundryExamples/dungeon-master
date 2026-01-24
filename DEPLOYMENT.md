# Deployment Guide for Dungeon Master Service

This guide provides comprehensive, end-to-end instructions for deploying and operating the Dungeon Master service on Google Cloud Platform.

> **📝 Note on Placeholders**: This guide uses placeholder values (e.g., `YOUR_PROJECT_ID`, `journey-log-xyz.a.run.app`, `test-character-uuid`) that **must be replaced** with your actual project-specific values. These placeholders are marked with `YOUR_` prefix or contain `-xyz` suffixes to make them easy to identify.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Initial Provisioning](#initial-provisioning)
4. [Environment Configuration](#environment-configuration)
5. [Secrets Management](#secrets-management)
6. [Cloud Build Configuration](#cloud-build-configuration)
7. [Deployment Procedures](#deployment-procedures)
8. [Traffic Management and Rollout](#traffic-management-and-rollout)
9. [Service Health Verification](#service-health-verification)
10. [Monitoring and Alerts](#monitoring-and-alerts)
11. [Rollback Procedures](#rollback-procedures)
12. [Troubleshooting](#troubleshooting)
13. [Environment-Specific Guidance](#environment-specific-guidance)
14. [Ongoing Operations](#ongoing-operations)

## Overview

The Dungeon Master service is deployed to **Google Cloud Run** using **Cloud Build** for CI/CD automation. The deployment pipeline includes:

- **Test Phase**: Automated pytest unit and integration tests
- **Build Phase**: Docker container build with multi-stage optimization
- **Push Phase**: Image push to Artifact Registry with SHA and latest tags
- **Deploy Phase**: Zero-downtime deployment to Cloud Run with traffic management

### Architecture Overview

```
GitHub Repository (main/develop branch)
    ↓ (webhook trigger)
Cloud Build Pipeline (cloudbuild.yaml)
    ↓
[1] Run Tests → [2] Build Image → [3] Push to Artifact Registry → [4] Deploy to Cloud Run (0% traffic)
    ↓
Manual Traffic Shift (gradual or instant)
    ↓
Production Traffic Serving
```

### Key References

- **Architecture Details**: [`gcp_deployment_reference.md`](gcp_deployment_reference.md) - Comprehensive deployment architecture, rationale, and advanced configuration
- **Infrastructure Code**: [`infra/`](infra/) directory - IaC configurations, monitoring, and networking
- **CI/CD Pipeline**: [`cloudbuild.yaml`](cloudbuild.yaml) - Cloud Build pipeline definition
- **Environment Template**: [`.env.example`](.env.example) - All configuration options

## Prerequisites

### Tools Required

Before starting, ensure you have the following tools installed:

| Tool | Version | Installation |
|------|---------|--------------|
| **gcloud CLI** | 551.0.0+ | [Install gcloud](https://cloud.google.com/sdk/docs/install) |
| **Docker** | 29.1.4+ | [Install Docker](https://docs.docker.com/get-docker/) |
| **Git** | Latest | System package manager |
| **Python** | 3.14+ | See [`python_dev_versions.txt`](python_dev_versions.txt) |

**Install gcloud CLI:**
```bash
# Linux/macOS
curl https://sdk.cloud.google.com | bash

# Restart shell and initialize
gcloud init
gcloud auth login
```

### GCP Account Setup

1. **Create or Select GCP Project**:
```bash
# Create new project (optional)
gcloud projects create YOUR_PROJECT_ID --name="Dungeon Master"

# Set active project
gcloud config set project YOUR_PROJECT_ID

# Verify billing is enabled
gcloud beta billing accounts list
```

2. **Enable Required APIs**:
```bash
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com
```

**Time to complete**: ~2-3 minutes (API enablement is asynchronous)

## Initial Provisioning

This section walks through provisioning infrastructure from scratch.

### Step 1: Create Artifact Registry Repository

Store Docker images in Artifact Registry (NOT deprecated gcr.io):

```bash
# Set variables
export PROJECT_ID=$(gcloud config get-value project)
export REGION=us-central1
export REPO_NAME=dungeon-master

# Create repository
gcloud artifacts repositories create $REPO_NAME \
  --repository-format=docker \
  --location=$REGION \
  --description="Dungeon Master service container images"

# Configure Docker authentication
gcloud auth configure-docker ${REGION}-docker.pkg.dev
```

**Verification**:
```bash
gcloud artifacts repositories list --location=$REGION
```

### Step 2: Create Service Account

Create a service account for Cloud Run with minimal permissions:

```bash
# Create service account
gcloud iam service-accounts create dungeon-master-sa \
  --display-name="Dungeon Master Cloud Run Service Account" \
  --description="Service account for dungeon-master Cloud Run service"

# Grant Secret Manager access (for API keys)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:dungeon-master-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Grant Cloud Logging permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:dungeon-master-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"

# Grant Cloud Monitoring permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:dungeon-master-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/monitoring.metricWriter"
```

**Verification**:
```bash
gcloud iam service-accounts describe dungeon-master-sa@${PROJECT_ID}.iam.gserviceaccount.com
```

### Step 3: Grant Cloud Build Permissions

Grant Cloud Build service account permissions to deploy:

```bash
# Get Cloud Build service account
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export CLOUD_BUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

# Grant Cloud Run Developer role (for deployment)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${CLOUD_BUILD_SA}" \
  --role="roles/run.developer"

# Grant Artifact Registry writer (for pushing images)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${CLOUD_BUILD_SA}" \
  --role="roles/artifactregistry.writer"

# Grant Service Account User (to assign service account to Cloud Run)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${CLOUD_BUILD_SA}" \
  --role="roles/iam.serviceAccountUser"

# Grant Secret Manager accessor (for using secrets in builds)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${CLOUD_BUILD_SA}" \
  --role="roles/secretmanager.secretAccessor"
```

**Verification**:
```bash
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:${CLOUD_BUILD_SA}"
```

### Step 4: Configure Workload Identity Federation (CI/CD)

**IMPORTANT**: Use Workload Identity Federation (WIF) for CI/CD authentication. NEVER use JSON service account keys.

For GitHub Actions integration:

```bash
# Create Workload Identity Pool
gcloud iam workload-identity-pools create github-pool \
  --location=global \
  --display-name="GitHub Actions Pool"

# Create Workload Identity Provider
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global \
  --workload-identity-pool=github-pool \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository == 'AgentFoundryExamples/dungeon-master'"

# Grant access to Cloud Build service account
gcloud iam service-accounts add-iam-policy-binding $CLOUD_BUILD_SA \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/AgentFoundryExamples/dungeon-master"
```

**Note**: For Cloud Build triggers from GitHub, WIF is configured automatically in the trigger setup.

## Environment Configuration

### Local Development Setup

1. **Clone Repository**:
```bash
git clone https://github.com/AgentFoundryExamples/dungeon-master.git
cd dungeon-master
```

2. **Create Environment File**:
```bash
cp .env.example .env
```

3. **Configure Required Variables**:

Edit `.env` and set the following (see [`.env.example`](.env.example) for all options):

```bash
# Required
JOURNEY_LOG_BASE_URL=https://journey-log-xyz.a.run.app
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_MODEL=gpt-5.1

# Recommended for Production
ENVIRONMENT=production
LOG_LEVEL=INFO
LOG_JSON_FORMAT=true
ENABLE_METRICS=true
MAX_TURNS_PER_CHARACTER_PER_SECOND=2.0
MAX_CONCURRENT_LLM_CALLS=10

# Security
ENABLE_DEBUG_ENDPOINTS=false
ADMIN_ENDPOINTS_ENABLED=false
```

**Local vs Cloud Deployment**: The `.env` file is for LOCAL development ONLY. For cloud deployments, use Secret Manager and environment variables (see next section).

### Cloud Run Environment Variables

For cloud deployments, configure via `gcloud` or `cloudbuild.yaml`:

```bash
# Set environment variables during deployment
gcloud run deploy dungeon-master \
  --set-env-vars "ENVIRONMENT=production" \
  --set-env-vars "LOG_LEVEL=INFO" \
  --set-env-vars "LOG_JSON_FORMAT=true" \
  --set-env-vars "ENABLE_METRICS=true" \
  --set-env-vars "JOURNEY_LOG_BASE_URL=https://journey-log-xyz.a.run.app" \
  --region $REGION
```

Or configure in `cloudbuild.yaml` (see [`cloudbuild.yaml`](cloudbuild.yaml) for full example):

```yaml
substitutions:
  _ENV_VARS: 'ENVIRONMENT=production,LOG_LEVEL=INFO,ENABLE_METRICS=true'
```

## Secrets Management

**CRITICAL**: Store sensitive values (API keys, database passwords) in Secret Manager. NEVER commit secrets to source code or use JSON service account keys.

### Step 1: Store Secrets in Secret Manager

```bash
# Store OpenAI API key
echo -n "sk-your-actual-api-key" | gcloud secrets create openai-api-key \
  --data-file=- \
  --replication-policy=automatic

# Store other secrets as needed
echo -n "your-db-password" | gcloud secrets create db-password \
  --data-file=- \
  --replication-policy=automatic
```

**Verification**:
```bash
gcloud secrets list
gcloud secrets versions list openai-api-key
```

### Step 2: Grant Service Account Access

```bash
# Grant dungeon-master service account access to secrets
gcloud secrets add-iam-policy-binding openai-api-key \
  --member="serviceAccount:dungeon-master-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### Step 3: Mount Secrets in Cloud Run

Secrets can be mounted as environment variables or files:

**Option A: Environment Variables** (recommended for API keys):
```bash
gcloud run deploy dungeon-master \
  --set-secrets "OPENAI_API_KEY=openai-api-key:latest" \
  --region $REGION
```

**Option B: Volume Mounts** (recommended for certificates/key files):
```bash
gcloud run deploy dungeon-master \
  --set-secrets "/secrets/cert.pem=ssl-certificate:latest" \
  --region $REGION
```

### Secret Rotation (Zero-Downtime)

To rotate secrets without downtime:

```bash
# 1. Create new secret version
echo -n "new-api-key" | gcloud secrets versions add openai-api-key --data-file=-

# 2. Cloud Run automatically picks up latest version on next cold start
# Or force restart to pick up immediately:
gcloud run services update dungeon-master \
  --region $REGION

# 3. Verify service health after rotation
SERVICE_URL=$(gcloud run services describe dungeon-master \
  --region $REGION \
  --format 'value(status.url)')
curl $SERVICE_URL/health

# 4. After verification period (24-48 hours), disable old version
OLD_VERSION=1  # Replace with actual old version number
gcloud secrets versions disable $OLD_VERSION --secret openai-api-key
```

**Best Practice**: Keep old secret version enabled for 24-48 hours to ensure no instances are still using it.

## Cloud Build Configuration

### Option 1: Manual Trigger (Testing)

Test the Cloud Build pipeline manually before setting up automated triggers:

```bash
# Navigate to repository root
cd /path/to/dungeon-master

# Submit build manually
gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions=_PROJECT_ID=${PROJECT_ID},_REGION=${REGION},_SERVICE_NAME=dungeon-master,_SERVICE_ACCOUNT=dungeon-master-sa@${PROJECT_ID}.iam.gserviceaccount.com
```

**Expected output**: Build should complete all 4 steps (tests, build, push, deploy) successfully.

### Option 2: Automated GitHub Trigger (Production)

#### Connect GitHub Repository

1. Navigate to [Cloud Build Triggers](https://console.cloud.google.com/cloud-build/triggers)
2. Click **"Connect Repository"**
3. Select **GitHub (Cloud Build GitHub App)**
4. Authenticate with GitHub
5. Select repository: `AgentFoundryExamples/dungeon-master`
6. Click **"Connect"**

#### Create Production Trigger (main branch)

```bash
gcloud builds triggers create github \
  --name="dungeon-master-prod-deploy" \
  --description="Production deployment from main branch" \
  --repo-name="dungeon-master" \
  --repo-owner="AgentFoundryExamples" \
  --branch-pattern="^main$" \
  --build-config="cloudbuild.yaml" \
  --substitutions="_PROJECT_ID=${PROJECT_ID},_REGION=${REGION},_SERVICE_NAME=dungeon-master,_SERVICE_ACCOUNT=dungeon-master-sa@${PROJECT_ID}.iam.gserviceaccount.com,_SECRETS=OPENAI_API_KEY=openai-api-key:latest,_ENV_VARS=ENVIRONMENT=production,LOG_JSON_FORMAT=true,ENABLE_METRICS=true"
```

#### Create Staging Trigger (develop branch)

```bash
gcloud builds triggers create github \
  --name="dungeon-master-staging-deploy" \
  --description="Staging deployment from develop branch" \
  --repo-name="dungeon-master" \
  --repo-owner="AgentFoundryExamples" \
  --branch-pattern="^develop$" \
  --build-config="cloudbuild.yaml" \
  --substitutions="_PROJECT_ID=${PROJECT_ID},_REGION=${REGION},_SERVICE_NAME=dungeon-master-staging,_SERVICE_ACCOUNT=dungeon-master-sa@${PROJECT_ID}.iam.gserviceaccount.com,_SECRETS=OPENAI_API_KEY=openai-api-key:latest,_ENV_VARS=ENVIRONMENT=staging,LOG_JSON_FORMAT=true"
```

**Verification**:
```bash
gcloud builds triggers list
```

### Trigger Testing

Test the trigger by pushing to the configured branch:

```bash
# Push to main (triggers production deploy)
git checkout main
git push origin main

# Monitor build progress
gcloud builds list --ongoing
gcloud builds log BUILD_ID --stream
```

## Deployment Procedures

### Pre-Deployment Checklist

Before deploying, verify:

- [ ] All tests pass locally: `pytest tests/ -v`
- [ ] Dependencies are pinned: Review [`requirements.txt`](requirements.txt)
- [ ] Version alignment: Check [`python_dev_versions.txt`](python_dev_versions.txt), [`infrastructure_versions.txt`](infrastructure_versions.txt)
- [ ] Secrets are up-to-date in Secret Manager
- [ ] Environment variables are configured correctly
- [ ] Journey-log service is accessible and healthy
- [ ] Monitoring dashboards are ready

### Deployment Methods

#### Method A: Automated via Cloud Build (Recommended)

Push to configured branch to trigger automated deployment:

```bash
# Production deployment (main branch)
git checkout main
git pull origin main
# Make changes, commit
git push origin main

# Staging deployment (develop branch)
git checkout develop
git push origin develop
```

**Monitor deployment**:
```bash
# Watch build logs
gcloud builds list --ongoing
gcloud builds log $(gcloud builds list --limit=1 --format='value(id)') --stream
```

#### Method B: Manual Deployment

For testing or emergency hotfixes:

```bash
# Build image locally
docker build -t ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/dungeon-master:manual .

# Push to Artifact Registry
docker push ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/dungeon-master:manual

# Deploy to Cloud Run
gcloud run deploy dungeon-master \
  --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/dungeon-master:manual \
  --region $REGION \
  --platform managed \
  --memory 1Gi \
  --cpu 2 \
  --concurrency 80 \
  --min-instances 0 \
  --max-instances 100 \
  --timeout 300s \
  --service-account dungeon-master-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-secrets "OPENAI_API_KEY=openai-api-key:latest" \
  --set-env-vars "ENVIRONMENT=production,LOG_JSON_FORMAT=true,ENABLE_METRICS=true,JOURNEY_LOG_BASE_URL=https://journey-log-xyz.a.run.app" \
  --allow-unauthenticated \
  --no-traffic
```

**Note**: `--no-traffic` flag deploys new revision with 0% traffic for safe testing before traffic shift.

### Resource Configuration Rationale

The deployment uses the following Cloud Run configuration (see [`gcp_deployment_reference.md`](gcp_deployment_reference.md#b-resource-configuration-recommendations) for detailed rationale):

| Setting | Value | Rationale |
|---------|-------|-----------|
| **Memory** | 1 GiB | LLM client libraries (~200-300 MB), turn storage (~200-500 MB), headroom for GC |
| **CPU** | 2 vCPU | FastAPI async handling, JSON parsing for large LLM responses |
| **Concurrency** | 80 | LLM calls are I/O-bound, high concurrency improves cost efficiency |
| **Min Instances** | 0 (dev/staging), 1 (prod) | Cost optimization vs cold start elimination |
| **Max Instances** | 100 | Caps cost, supports 8,000 concurrent requests at 80 concurrency |
| **Timeout** | 300s | LLM generation can take 30-60s, allows for retries |

**Scaling for Higher Traffic**: See [`gcp_deployment_reference.md`](gcp_deployment_reference.md#scaling-for-production) for recommendations based on daily active users.

## Traffic Management and Rollout

Cloud Build deploys new revisions with `--no-traffic` flag, allowing safe verification before shifting traffic.

### Get Revision Information

```bash
# List recent revisions
gcloud run revisions list \
  --service dungeon-master \
  --region $REGION \
  --limit 5

# Get latest revision name
NEW_REVISION=$(gcloud run services describe dungeon-master \
  --region $REGION \
  --format 'value(status.latestReadyRevisionName)')

echo "Latest revision: $NEW_REVISION"
```

### Strategy 1: Instant Rollout (Blue/Green)

Deploy new revision and instantly shift all traffic:

```bash
# Shift 100% traffic to latest revision
gcloud run services update-traffic dungeon-master \
  --to-revisions $NEW_REVISION=100 \
  --region $REGION
```

**Use when**: Low-risk changes (documentation, logging, configuration updates)

**Recovery time**: < 30 seconds (instant traffic shift back)

### Strategy 2: Gradual Rollout (Canary)

Gradually shift traffic to new revision:

```bash
# Phase 1: Shift 10% traffic to new revision
gcloud run services update-traffic dungeon-master \
  --to-revisions $NEW_REVISION=10 \
  --region $REGION

# Monitor metrics for 15-30 minutes
# Check error rate, latency, LLM failures

# Phase 2: If metrics are good, shift to 50%
gcloud run services update-traffic dungeon-master \
  --to-revisions $NEW_REVISION=50 \
  --region $REGION

# Monitor for another 15-30 minutes

# Phase 3: Complete rollout to 100%
gcloud run services update-traffic dungeon-master \
  --to-revisions $NEW_REVISION=100 \
  --region $REGION
```

**Use when**: High-risk changes (LLM prompt changes, policy engine updates, new features)

**Recovery time**: < 30 seconds (instant traffic shift back)

### Strategy 3: A/B Testing (Split Traffic)

Route specific percentage to each revision for testing:

```bash
# Get previous stable revision
STABLE_REVISION=dungeon-master-00042-abc

# Split traffic 50/50
gcloud run services update-traffic dungeon-master \
  --to-revisions $NEW_REVISION=50,$STABLE_REVISION=50 \
  --region $REGION
```

**Use when**: Testing new LLM models, policy changes, or UX variations

### Testing Specific Revision

Test a specific revision before shifting traffic using tagged URLs:

```bash
# Get revision-specific URL
SERVICE_HOSTNAME=$(gcloud run services describe dungeon-master --region $REGION --format='value(status.url)' | sed 's|https://||')
REVISION_URL="https://${NEW_REVISION}---${SERVICE_HOSTNAME}"

# Test health endpoint
curl $REVISION_URL/health

# Test turn endpoint
curl -X POST $REVISION_URL/turn \
  -H "Content-Type: application/json" \
  -d '{
    "character_id": "test-character-uuid",
    "user_action": "I look around the dungeon."
  }'
```

## Service Health Verification

After deployment, verify service health:

### Basic Health Check

```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe dungeon-master \
  --region $REGION \
  --format 'value(status.url)')

# Check health endpoint
curl $SERVICE_URL/health

# Expected response:
# {"status":"healthy","service":"dungeon-master","journey_log_accessible":true}
```

### Smoke Test (Turn Endpoint)

Test the core /turn endpoint with a test character:

```bash
# Create test character in journey-log first (if not exists)
# Then submit a turn
curl -X POST $SERVICE_URL/turn \
  -H "Content-Type: application/json" \
  -d '{
    "character_id": "test-character-uuid",
    "user_action": "I explore the dungeon entrance."
  }'

# Expected: 200 OK with narrative response
```

### Metrics Verification (if enabled)

```bash
# Check metrics endpoint
curl $SERVICE_URL/metrics

# Verify key metrics are present:
# - uptime_seconds
# - turns.by_label.outcome:success
# - latencies.turn (avg, min, max)
# - llm_calls.total
```

### Log Verification

```bash
# View recent logs
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=dungeon-master" \
  --limit 50 \
  --format json

# Check for structured turn logs
gcloud logging read \
  "resource.type=cloud_run_revision AND jsonPayload.log_type=turn" \
  --limit 10 \
  --format json

# Check for errors
gcloud logging read \
  "resource.type=cloud_run_revision AND severity>=ERROR" \
  --limit 20 \
  --format json
```

## Monitoring and Alerts

### Step 1: Deploy Monitoring Infrastructure

Deploy monitoring artifacts from [`infra/monitoring/`](infra/monitoring/):

```bash
cd infra/monitoring

# Deploy log-based metrics
bash deploy_log_metrics.sh $PROJECT_ID

# Deploy alert policies
gcloud alpha monitoring policies create --policy-from-file=alert_policies.yaml

# Deploy uptime checks
bash deploy_uptime_checks.sh $PROJECT_ID "$SERVICE_URL"
```

**See**: [`infra/monitoring/README.md`](infra/monitoring/README.md) for detailed monitoring setup.

### Step 2: Import Dashboard

1. Navigate to [Cloud Monitoring Dashboards](https://console.cloud.google.com/monitoring/dashboards)
2. Click **"Create Dashboard"**
3. Click **"JSON"** tab
4. Paste contents of [`infra/monitoring/dashboard.json`](infra/monitoring/dashboard.json)
5. Click **"Save"**

### Key Metrics to Monitor

| Metric | Threshold | Alert Level | Action |
|--------|-----------|-------------|--------|
| **Error Rate (5xx)** | > 5% over 5 min | Critical | Page on-call, investigate logs |
| **Request Latency (P95)** | > 5s over 10 min | Warning | Check LLM API latency, scale resources |
| **LLM API Errors** | > 10 errors/min | Critical | Verify API key, check quotas |
| **Instance Count** | > 90 instances | Warning | Review traffic, adjust max-instances |
| **Service Availability** | < 99% uptime | Critical | Check service health, review logs |

### Alert Notification Channels

Configure notification channels for alerts:

```bash
# Email notifications
gcloud alpha monitoring channels create \
  --display-name="DevOps Team Email" \
  --type=email \
  --channel-labels=email_address=devops@example.com

# Slack notifications (requires webhook URL)
gcloud alpha monitoring channels create \
  --display-name="Slack #incidents" \
  --type=slack \
  --channel-labels=url=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# PagerDuty integration (requires integration key)
gcloud alpha monitoring channels create \
  --display-name="PagerDuty On-Call" \
  --type=pagerduty \
  --channel-labels=routing_key=YOUR_PAGERDUTY_KEY
```

### Links to Monitoring Resources

- **Cloud Run Console**: `https://console.cloud.google.com/run/detail/${REGION}/dungeon-master/metrics?project=${PROJECT_ID}`
- **Cloud Monitoring Dashboards**: `https://console.cloud.google.com/monitoring/dashboards?project=${PROJECT_ID}`
- **Cloud Logging**: `https://console.cloud.google.com/logs/query?project=${PROJECT_ID}`
- **Cloud Build History**: `https://console.cloud.google.com/cloud-build/builds?project=${PROJECT_ID}`

## Rollback Procedures

### Fast Rollback (Traffic Shift)

If new revision has issues, instantly shift traffic back to previous revision:

```bash
# List recent revisions
gcloud run revisions list \
  --service dungeon-master \
  --region $REGION \
  --limit 5

# Identify previous stable revision
PREVIOUS_REVISION=dungeon-master-00042-abc  # Replace with actual revision

# Shift 100% traffic back to previous revision
gcloud run services update-traffic dungeon-master \
  --to-revisions $PREVIOUS_REVISION=100 \
  --region $REGION
```

**Recovery Time**: < 30 seconds

**Use when**: New revision has runtime errors, high latency, or LLM failures

### Complete Rollback (Redeploy)

If traffic shift isn't sufficient (e.g., bad database migration):

```bash
# Identify previous working image
PREVIOUS_SHA=abc123def  # Replace with actual commit SHA

# Redeploy previous image
gcloud run deploy dungeon-master \
  --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/dungeon-master:${PREVIOUS_SHA} \
  --region $REGION
```

**Recovery Time**: ~2-5 minutes (includes deployment)

**Use when**: Traffic shift alone doesn't resolve issue

### Rollback Checklist

When rolling back:

- [ ] Identify root cause of failure (logs, metrics, error reports)
- [ ] Document issue and rollback decision
- [ ] Execute rollback (traffic shift or redeploy)
- [ ] Verify service health after rollback
- [ ] Monitor metrics for 30+ minutes post-rollback
- [ ] Create incident report and postmortem
- [ ] Fix root cause before attempting redeploy

## Troubleshooting

### Build Errors

#### Issue: Tests Fail in Cloud Build

**Symptoms**: Cloud Build fails at "run-tests" step

**Diagnosis**:
```bash
# View build logs
gcloud builds log BUILD_ID

# Run tests locally to reproduce
pytest tests/ -v --tb=short
```

**Common causes**:
- Dependency version mismatch (check `requirements.txt`)
- Missing environment variables in test environment
- Journey-log service unavailable during build

**Solution**:
- Fix failing tests locally first
- Ensure dependencies are pinned correctly
- Mock external dependencies in tests (journey-log, OpenAI API)

#### Issue: Docker Build Fails

**Symptoms**: Cloud Build fails at "build-image" step

**Diagnosis**:
```bash
# Build locally to reproduce
docker build -t test .
```

**Common causes**:
- Invalid Dockerfile syntax
- Missing files referenced in Dockerfile
- Build context too large (> 2 GB)

**Solution**:
- Review Dockerfile for errors
- Check `.dockerignore` to exclude unnecessary files
- Test build locally before pushing

### IAM and Permission Issues

#### Issue: "Permission Denied" During Deployment

**Symptoms**: Cloud Build succeeds but deployment fails with IAM error

**Diagnosis**:
```bash
# Check Cloud Build service account permissions
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:${CLOUD_BUILD_SA}"
```

**Common causes**:
- Cloud Build service account missing `roles/run.developer`
- Cloud Build service account missing `roles/iam.serviceAccountUser`
- Service account doesn't have permission to assign service account to Cloud Run

**Solution**:
```bash
# Grant missing permissions (see Initial Provisioning section)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${CLOUD_BUILD_SA}" \
  --role="roles/run.developer"
```

#### Issue: "Secret Not Found" Error

**Symptoms**: Cloud Run deployment fails with secret access error

**Diagnosis**:
```bash
# Check if secret exists
gcloud secrets describe openai-api-key

# Check service account permissions
gcloud secrets get-iam-policy openai-api-key
```

**Solution**:
```bash
# Grant service account access to secret
gcloud secrets add-iam-policy-binding openai-api-key \
  --member="serviceAccount:dungeon-master-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### Unhealthy Revisions

#### Issue: Service Returns 502/503 Errors

**Symptoms**: Health check fails, service returns 5xx errors

**Diagnosis**:
```bash
# Check service logs
gcloud logging read \
  "resource.type=cloud_run_revision AND severity>=ERROR" \
  --limit 50 \
  --format json

# Check revision status
gcloud run revisions describe $NEW_REVISION --region $REGION
```

**Common causes**:
- Service crashing on startup (missing environment variables)
- Health check endpoint not responding within timeout
- Journey-log service unreachable
- Invalid OpenAI API key

**Solution**:
- Review logs for startup errors
- Verify all required environment variables are set
- Test journey-log connectivity: `curl https://journey-log-xyz.a.run.app/health`
- Verify OpenAI API key in Secret Manager

#### Issue: High Latency (> 5s per turn)

**Symptoms**: Turn requests take > 5 seconds to complete

**Diagnosis**:
```bash
# Check metrics for latency breakdown
curl $SERVICE_URL/metrics | grep latencies

# Check logs for slow operations
gcloud logging read \
  "resource.type=cloud_run_revision AND jsonPayload.log_type=turn" \
  --limit 20 \
  --format json
```

**Common causes**:
- LLM API slow (check `latencies.llm_call`)
- Journey-log API slow (check `latencies.journey_log_fetch`)
- Insufficient CPU/memory resources
- High concurrency causing resource contention

**Solution**:
- Check LLM provider status (OpenAI API status page)
- Verify journey-log service performance
- Increase Cloud Run resources: `--memory 2Gi --cpu 4`
- Adjust concurrency: `--concurrency 50` (lower if CPU-bound)

### Network Connectivity Issues

#### Issue: Cannot Reach Journey-Log Service

**Symptoms**: Health check shows `journey_log_accessible: false`, turn requests fail with connection errors

**Diagnosis**:
```bash
# Test from a container with the same network configuration
# 1. Deploy a temporary debug image (e.g., curlimages/curl) with the same network settings
gcloud run deploy debug-curl --image=curlimages/curl \
  --region=$REGION \
  --service-account=dungeon-master-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --vpc-connector=YOUR_VPC_CONNECTOR \  # Add if the main service uses one
  --command -- /bin/sh -c "sleep 3600"

# 2. SSH into the debug container
gcloud run ssh debug-curl --region=$REGION

# 3. From inside the container's shell, test connectivity
# (container) curl https://journey-log-xyz.a.run.app/health

# 4. Clean up the debug service
gcloud run services delete debug-curl --region=$REGION --quiet
```

**Common causes**:
- Journey-log service is down
- Incorrect `JOURNEY_LOG_BASE_URL` configuration
- VPC connector misconfigured (if using private networking)
- Firewall rules blocking egress

**Solution**:
- Verify journey-log service URL is correct
- Check journey-log service health independently
- If using VPC, verify connector configuration: [`infra/networking/vpc_connector.tf`](infra/networking/vpc_connector.tf)
- Check ingress settings on journey-log service

## Environment-Specific Guidance

### Development Environment

**Purpose**: Local testing, rapid iteration

**Configuration**:
```bash
# .env file
ENVIRONMENT=development
OPENAI_STUB_MODE=true  # Use stub responses (no API calls)
ENABLE_DEBUG_ENDPOINTS=true
LOG_LEVEL=DEBUG
HEALTH_CHECK_JOURNEY_LOG=false  # Skip journey-log ping for faster local testing

# Run locally
python -m app.main
```

**Deployment**: Not deployed to Cloud Run (local only)

### Staging Environment

**Purpose**: Pre-production testing, QA validation

**Configuration**:
```bash
# Cloud Run environment variables
ENVIRONMENT=staging
OPENAI_MODEL=gpt-5.1
LOG_LEVEL=INFO
LOG_JSON_FORMAT=true
ENABLE_METRICS=true
ENABLE_DEBUG_ENDPOINTS=false
ALLOW_UNAUTHENTICATED=true  # For easier testing

# Scaling
--min-instances 0
--max-instances 10
--concurrency 50
```

**Deployment**:
- Service name: `dungeon-master-staging`
- Triggered by pushes to `develop` branch
- URL: `https://dungeon-master-staging-xyz.a.run.app`

**Secret Management**: Use separate secrets (e.g., `openai-api-key-staging`)

### Production Environment

**Purpose**: Live player traffic, critical operations

**Configuration**:
```bash
# Cloud Run environment variables
ENVIRONMENT=production
OPENAI_MODEL=gpt-5.1
LOG_LEVEL=INFO
LOG_JSON_FORMAT=true
ENABLE_METRICS=true
ENABLE_DEBUG_ENDPOINTS=false  # MUST be false
ADMIN_ENDPOINTS_ENABLED=false  # Unless needed with IAM protection
ALLOW_UNAUTHENTICATED=false  # Use IAM, API Gateway, or IAP

# Scaling (adjust based on traffic)
--min-instances 1  # Eliminate cold starts
--max-instances 100
--concurrency 80
```

**Deployment**:
- Service name: `dungeon-master`
- Triggered by pushes to `main` branch
- URL: `https://dungeon-master-xyz.a.run.app` (or custom domain)

**Secret Management**: Use production secrets with rotation policy

**Scaling Guidance**:
- **< 100 DAU**: `--min-instances 0`, `--max-instances 10`
- **100-1000 DAU**: `--min-instances 1`, `--max-instances 100` (current config)
- **> 1000 DAU**: `--min-instances 5`, `--max-instances 200`, consider multi-region

**Cross-Environment Mistakes to Avoid**:
- ❌ Using production secrets in staging/dev
- ❌ Deploying debug endpoints to production
- ❌ Using same service name across environments
- ❌ Hardcoding environment-specific URLs

## Ongoing Operations

### Regular Maintenance Tasks

#### Weekly Tasks

- [ ] Review Cloud Monitoring dashboards for anomalies
- [ ] Check error logs for new error patterns
- [ ] Review resource utilization (CPU, memory, instance count)
- [ ] Verify backup and disaster recovery procedures

#### Monthly Tasks

- [ ] Review and update dependencies (security patches)
- [ ] Rotate secrets (API keys, service account keys if used)
- [ ] Review alert policy thresholds and adjust if needed
- [ ] Conduct disaster recovery drill (rollback, failover)
- [ ] Review Cloud Run costs and optimize resources

#### Quarterly Tasks

- [ ] Update Python version (if new version in `python_dev_versions.txt`)
- [ ] Review and update infrastructure IaC files
- [ ] Conduct security audit (IAM permissions, secret access)
- [ ] Review and update monitoring dashboards
- [ ] Performance optimization review

### Scaling Adjustments

As traffic grows, adjust Cloud Run resources:

```bash
# Increase max instances for traffic spikes
gcloud run services update dungeon-master \
  --max-instances 200 \
  --region $REGION

# Add minimum instances to eliminate cold starts
gcloud run services update dungeon-master \
  --min-instances 2 \
  --region $REGION

# Increase resources for high CPU/memory usage
gcloud run services update dungeon-master \
  --memory 2Gi \
  --cpu 4 \
  --region $REGION
```

### Policy Configuration Updates

Update policy engine parameters without redeployment:

```bash
# Update environment variables
gcloud run services update dungeon-master \
  --set-env-vars "QUEST_TRIGGER_PROB=0.5,POI_TRIGGER_PROB=0.3" \
  --region $REGION
```

Or use admin endpoints (if enabled with proper IAM):

```bash
curl -X POST $SERVICE_URL/admin/policy/reload \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{
    "quest_trigger_prob": 0.5,
    "poi_trigger_prob": 0.3
  }'
```

### Cost Optimization

Monitor and optimize Cloud Run costs:

```bash
# View cost breakdown
gcloud billing accounts list
gcloud billing projects describe $PROJECT_ID

# Check resource utilization
gcloud monitoring time-series list \
  --filter='metric.type="run.googleapis.com/container/cpu/utilizations"' \
  --interval-start-time=$(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --interval-end-time=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```

**Optimization tips**:
- Scale to zero (min-instances=0) for dev/staging environments
- Right-size resources (avoid over-provisioning CPU/memory)
- Use canary deployments to test resource changes
- Monitor cold start impact before reducing min-instances

### Disaster Recovery

**Backup Strategy**:
- **Code**: Backed up in GitHub repository (multiple branches)
- **Images**: Stored in Artifact Registry with SHA tags (immutable)
- **Secrets**: Stored in Secret Manager with versioning
- **Configuration**: IaC files in `infra/` directory

**Recovery Procedures**:

1. **Service Failure**: Rollback to previous revision (< 30 seconds)
2. **Region Outage**: Deploy to different region (see [`infra/networking/README.md`](infra/networking/README.md#multi-region-deployment))
3. **Data Loss**: No persistent data in service (stateless)
4. **Secret Compromise**: Rotate secrets immediately (see Secret Rotation section)

## Additional Resources

### Infrastructure as Code (IaC)

- **Cloud Run Service**: [`infra/cloudrun/service.yaml`](infra/cloudrun/service.yaml)
- **Monitoring**: [`infra/monitoring/`](infra/monitoring/)
  - Alert policies: [`alert_policies.yaml`](infra/monitoring/alert_policies.yaml)
  - Log metrics: [`log_metrics.yaml`](infra/monitoring/log_metrics.yaml)
  - Dashboard: [`dashboard.json`](infra/monitoring/dashboard.json)
- **Networking**: [`infra/networking/`](infra/networking/)
  - VPC connector: [`vpc_connector.tf`](infra/networking/vpc_connector.tf)
  - API Gateway: See [`infra/networking/README.md`](infra/networking/README.md#api-gateway-integration)

### Documentation Links

- **Comprehensive Deployment Reference**: [`gcp_deployment_reference.md`](gcp_deployment_reference.md)
- **Implementation Summary**: [`IMPLEMENTATION_SUMMARY.md`](IMPLEMENTATION_SUMMARY.md)
- **Main README**: [`README.md`](README.md)
- **LLM Integration Guide**: [`LLMs.md`](LLMs.md)
- **Environment Variables**: [`.env.example`](.env.example)

### External Resources

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud Build Documentation](https://cloud.google.com/build/docs)
- [Artifact Registry Documentation](https://cloud.google.com/artifact-registry/docs)
- [Secret Manager Documentation](https://cloud.google.com/secret-manager/docs)
- [Cloud Monitoring Documentation](https://cloud.google.com/monitoring/docs)

---

## Quick Reference

### Common Commands

```bash
# Deploy service
gcloud run deploy dungeon-master --image IMAGE_URL --region $REGION

# Update traffic
gcloud run services update-traffic dungeon-master --to-revisions REVISION=100 --region $REGION

# View logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=dungeon-master" --limit 50

# Check service health
curl $(gcloud run services describe dungeon-master --region $REGION --format 'value(status.url)')/health

# Rollback
gcloud run services update-traffic dungeon-master --to-revisions PREVIOUS_REVISION=100 --region $REGION

# Rotate secret
echo -n "new-key" | gcloud secrets versions add SECRET_NAME --data-file=-
gcloud run services update dungeon-master --region $REGION
```

### Service URLs

- **Production**: Set by Cloud Run (e.g., `https://dungeon-master-xyz.a.run.app`)
- **Staging**: `https://dungeon-master-staging-xyz.a.run.app`
- **Cloud Run Console**: `https://console.cloud.google.com/run?project=${PROJECT_ID}`
- **Cloud Build Console**: `https://console.cloud.google.com/cloud-build/builds?project=${PROJECT_ID}`

### Support and Escalation

For deployment issues:
1. Check [Troubleshooting](#troubleshooting) section
2. Review logs: `gcloud logging read "resource.type=cloud_run_revision AND severity>=ERROR" --limit 50`
3. Check monitoring dashboards for anomalies
4. Review recent commits for potential breaking changes
5. Escalate to DevOps team if unresolved
