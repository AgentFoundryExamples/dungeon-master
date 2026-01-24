# Infrastructure Documentation

This directory contains infrastructure-as-code and deployment scripts for the Dungeon Master service on Google Cloud Platform.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Cloud Build Setup](#cloud-build-setup)
4. [Deployment Scripts](#deployment-scripts)
5. [Environment Configuration](#environment-configuration)
6. [Secrets Management](#secrets-management)
7. [Troubleshooting](#troubleshooting)

## Overview

The Dungeon Master service uses **Google Cloud Build** for CI/CD automation and deploys to **Cloud Run** (fully managed). The pipeline includes:

- **Test Phase**: Runs pytest unit and integration tests
- **Build Phase**: Builds Docker container with multi-stage optimization
- **Push Phase**: Pushes to Artifact Registry with commit SHA and latest tags
- **Deploy Phase**: Deploys to Cloud Run with traffic management (canary-safe)

### Architecture

```
GitHub Repository
    ↓ (push/PR trigger)
Cloud Build Pipeline
    ↓
[1] Run Tests (pytest)
    ↓
[2] Build Container Image
    ↓
[3] Push to Artifact Registry
    ↓
[4] Deploy to Cloud Run (0% traffic)
    ↓
Manual Traffic Shift (100% or canary)
```

## Prerequisites

### 1. Required Tools

- **gcloud CLI** (version 551.0.0+)
- **Docker** (version 29.1.4+) - for local testing
- **Git** - for version control

Install gcloud CLI:
```bash
# Linux/macOS
curl https://sdk.cloud.google.com | bash

# Restart shell and initialize
gcloud init
```

### 2. GCP Project Setup

Create a new GCP project or use an existing one:

```bash
# Create project (if needed)
gcloud projects create YOUR_PROJECT_ID --name="Dungeon Master"

# Set active project
gcloud config set project YOUR_PROJECT_ID

# Enable billing (required for Cloud Run)
# Visit: https://console.cloud.google.com/billing
```

### 3. Enable Required APIs

```bash
# Enable all required APIs at once
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  monitoring.googleapis.com
```

### 4. Create Artifact Registry Repository

```bash
# Create Docker repository
gcloud artifacts repositories create dungeon-master \
  --repository-format=docker \
  --location=us-central1 \
  --description="Dungeon Master service container images"

# Configure Docker authentication
gcloud auth configure-docker us-central1-docker.pkg.dev
```

### 5. Create Service Account

```bash
# Create service account for Cloud Run
gcloud iam service-accounts create dungeon-master-sa \
  --display-name="Dungeon Master Cloud Run Service Account"

# Grant minimal permissions
PROJECT_ID=$(gcloud config get-value project)

# Secret Manager access (for API keys)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:dungeon-master-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Cloud Logging
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:dungeon-master-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"

# Cloud Monitoring
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:dungeon-master-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/monitoring.metricWriter"
```

### 6. Grant Permissions to Cloud Build Service Account

```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

# Cloud Run admin (for deployment)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
  --role="roles/run.admin"

# Artifact Registry writer (for pushing images)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

# Service Account User (to assign service account to Cloud Run)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# Secret Manager accessor (if using secrets in build)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## Cloud Build Setup

### Option 1: Manual Trigger (Local Testing)

Test the Cloud Build pipeline manually before setting up automated triggers:

```bash
# Navigate to repository root
cd /path/to/dungeon-master

# Submit build manually
gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions=_PROJECT_ID=$(gcloud config get-value project),_REGION=us-central1,_SERVICE_NAME=dungeon-master
```

### Option 2: Automated Trigger (GitHub Integration)

#### Connect GitHub Repository

1. Go to [Cloud Build Triggers](https://console.cloud.google.com/cloud-build/triggers)
2. Click **"Connect Repository"**
3. Select **GitHub (Cloud Build GitHub App)**
4. Authenticate and select your repository: `AgentFoundryExamples/dungeon-master`
5. Click **"Connect"**

#### Create Build Trigger

**For Production (main branch):**

```bash
gcloud builds triggers create github \
  --name="dungeon-master-prod-deploy" \
  --repo-name="dungeon-master" \
  --repo-owner="AgentFoundryExamples" \
  --branch-pattern="^main$" \
  --build-config="cloudbuild.yaml" \
  --substitutions="_PROJECT_ID=YOUR_PROJECT_ID,_REGION=us-central1,_SERVICE_NAME=dungeon-master,_SERVICE_ACCOUNT=dungeon-master-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com"
```

**For Staging (develop branch):**

```bash
gcloud builds triggers create github \
  --name="dungeon-master-staging-deploy" \
  --repo-name="dungeon-master" \
  --repo-owner="AgentFoundryExamples" \
  --branch-pattern="^develop$" \
  --build-config="cloudbuild.yaml" \
  --substitutions="_PROJECT_ID=YOUR_PROJECT_ID,_REGION=us-central1,_SERVICE_NAME=dungeon-master-staging,_SERVICE_ACCOUNT=dungeon-master-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com"
```

**For Pull Requests (pre-merge validation):**

```bash
gcloud builds triggers create github \
  --name="dungeon-master-pr-tests" \
  --repo-name="dungeon-master" \
  --repo-owner="AgentFoundryExamples" \
  --pull-request-pattern="^main$" \
  --build-config="cloudbuild.yaml" \
  --substitutions="_PROJECT_ID=YOUR_PROJECT_ID,_REGION=us-central1" \
  --comment-control=COMMENTS_ENABLED
```

### Substitution Variables

Configure these in your trigger or pass via `--substitutions`:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `_PROJECT_ID` | GCP project ID | - | **Yes** |
| `_REGION` | GCP region | `us-central1` | No |
| `_SERVICE_NAME` | Cloud Run service name | `dungeon-master` | No |
| `_ARTIFACT_REPO` | Artifact Registry repo | `dungeon-master` | No |
| `_SERVICE_ACCOUNT` | Service account email | - | No |
| `_SECRETS` | Secrets from Secret Manager | - | No |
| `_ENV_VARS` | Environment variables | - | No |

## Deployment Scripts

### `cloudrun/deploy.sh`

Reusable bash script for deploying to Cloud Run. Mirrors Cloud Build steps for local verification.

**Usage:**

```bash
# Deploy to production
PROJECT_ID=your-project-id ./infra/cloudrun/deploy.sh

# Deploy to staging with custom settings
PROJECT_ID=your-project-id \
  REGION=us-west1 \
  SERVICE_NAME=dungeon-master-staging \
  IMAGE_TAG=v1.2.3 \
  ./infra/cloudrun/deploy.sh

# Deploy with secrets
PROJECT_ID=your-project-id \
  SECRETS="OPENAI_API_KEY=openai-api-key:latest" \
  ./infra/cloudrun/deploy.sh
```

**Environment Variables:**

| Variable | Description | Default |
|----------|-------------|---------|
| `PROJECT_ID` | GCP project ID | **Required** |
| `REGION` | GCP region | `us-central1` |
| `SERVICE_NAME` | Cloud Run service name | `dungeon-master` |
| `ARTIFACT_REPO` | Artifact Registry repo | `dungeon-master` |
| `IMAGE_TAG` | Docker image tag | `latest` |
| `SERVICE_ACCOUNT` | Service account email | - |
| `SECRETS` | Comma-separated secrets | - |
| `ENV_VARS` | Comma-separated env vars | - |

## Environment Configuration

### Development Environment

```bash
# .env.development (not committed to git)
ENVIRONMENT=development
LOG_LEVEL=DEBUG
OPENAI_API_KEY=sk-...
JOURNEY_LOG_URL=http://localhost:8081
ENABLE_DEBUG_ENDPOINTS=true
```

Deploy with:
```bash
PROJECT_ID=dungeon-master-dev \
  SERVICE_NAME=dungeon-master-dev \
  ENV_VARS="ENVIRONMENT=development,LOG_LEVEL=DEBUG" \
  ./infra/cloudrun/deploy.sh
```

### Production Environment

**Never commit secrets to git!** Use Secret Manager instead:

```bash
# Store secrets in Secret Manager
echo -n "sk-your-openai-api-key" | gcloud secrets create openai-api-key \
  --data-file=- \
  --replication-policy="automatic"
```

Deploy with secrets:
```bash
PROJECT_ID=dungeon-master-prod \
  SERVICE_NAME=dungeon-master \
  SECRETS="OPENAI_API_KEY=openai-api-key:latest" \
  ENV_VARS="ENVIRONMENT=production,LOG_LEVEL=INFO" \
  ./infra/cloudrun/deploy.sh
```

## Secrets Management

### Storing Secrets

```bash
# Create secret
echo -n "your-secret-value" | gcloud secrets create SECRET_NAME \
  --data-file=- \
  --replication-policy="automatic"

# Update existing secret
echo -n "new-secret-value" | gcloud secrets versions add SECRET_NAME \
  --data-file=-

# List secrets
gcloud secrets list

# View secret versions
gcloud secrets versions list SECRET_NAME
```

### Mounting Secrets in Cloud Run

**Via Cloud Build** (`cloudbuild.yaml`):

```bash
gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions=_PROJECT_ID=my-project,_SECRETS="OPENAI_API_KEY=openai-api-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest"
```

**Via Deploy Script** (`deploy.sh`):

```bash
PROJECT_ID=my-project \
  SECRETS="OPENAI_API_KEY=openai-api-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest" \
  ./infra/cloudrun/deploy.sh
```

**Format:**
```
ENV_VAR_NAME=secret-name:version
```

Example:
```
OPENAI_API_KEY=openai-api-key:latest
```

### KMS Encryption (Optional)

For enhanced security, encrypt secrets with Cloud KMS:

```bash
# Create KMS keyring and key
gcloud kms keyrings create dungeon-master-keyring --location=us-central1
gcloud kms keys create dungeon-master-key \
  --keyring=dungeon-master-keyring \
  --location=us-central1 \
  --purpose=encryption

# Create secret with KMS encryption
gcloud secrets create encrypted-secret \
  --replication-policy="automatic" \
  --kms-key-name="projects/PROJECT_ID/locations/us-central1/keyRings/dungeon-master-keyring/cryptoKeys/dungeon-master-key"
```

## Troubleshooting

### Build Failures

**Tests Fail:**
```bash
# Run tests locally to debug
python -m pytest tests/ -v --tb=short

# Check specific test
python -m pytest tests/test_turn_integration.py -v
```

**Image Build Fails:**
```bash
# Build locally to debug
docker build -t dungeon-master:local .

# Check Dockerfile syntax
docker build --check -t dungeon-master:local .
```

**Permission Denied:**
```bash
# Verify Cloud Build service account has required roles
gcloud projects get-iam-policy PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:PROJECT_NUMBER@cloudbuild.gserviceaccount.com"
```

### Deployment Failures

**Service Account Not Found:**
```bash
# List service accounts
gcloud iam service-accounts list

# Create if missing
gcloud iam service-accounts create dungeon-master-sa \
  --display-name="Dungeon Master Cloud Run Service Account"
```

**Secret Not Found:**
```bash
# List secrets
gcloud secrets list

# Check secret versions
gcloud secrets versions list SECRET_NAME

# Verify service account has access
gcloud secrets get-iam-policy SECRET_NAME
```

**Quota Exceeded:**
```bash
# Check Cloud Run quotas
gcloud compute project-info describe --project=PROJECT_ID

# Request quota increase via:
# https://console.cloud.google.com/iam-admin/quotas
```

### Traffic Management

**Shift Traffic Gradually (Canary Deployment):**

```bash
# Deploy new revision (0% traffic)
# Cloud Build does this automatically with --no-traffic

# Shift 10% traffic to new revision
gcloud run services update-traffic dungeon-master \
  --region us-central1 \
  --to-revisions NEW_REVISION=10

# Monitor metrics, then shift 100%
gcloud run services update-traffic dungeon-master \
  --region us-central1 \
  --to-revisions NEW_REVISION=100
```

**Rollback to Previous Revision:**

```bash
# List revisions
gcloud run revisions list --service dungeon-master --region us-central1

# Shift traffic back to old revision
gcloud run services update-traffic dungeon-master \
  --region us-central1 \
  --to-revisions OLD_REVISION=100
```

### Viewing Logs

```bash
# Cloud Build logs
gcloud builds log BUILD_ID

# Cloud Run logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=dungeon-master" \
  --limit 50 \
  --format json

# Real-time log streaming
gcloud alpha run services logs tail dungeon-master --region us-central1
```

## Additional Resources

- [Cloud Build Documentation](https://cloud.google.com/build/docs)
- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Artifact Registry Documentation](https://cloud.google.com/artifact-registry/docs)
- [Secret Manager Documentation](https://cloud.google.com/secret-manager/docs)
- [GCP Deployment Reference](../gcp_deployment_reference.md)
