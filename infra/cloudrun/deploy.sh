#!/bin/bash
# Reusable Cloud Run deployment script for Dungeon Master service
# This script mirrors the Cloud Build deployment steps for local verification
#
# Usage:
#   ./deploy.sh [OPTIONS]
#
# Environment Variables (can also be passed via .env file):
#   PROJECT_ID        - GCP project ID (required)
#   REGION            - GCP region (default: us-central1)
#   SERVICE_NAME      - Cloud Run service name (default: dungeon-master)
#   ARTIFACT_REPO     - Artifact Registry repo name (default: dungeon-master)
#   IMAGE_TAG         - Docker image tag (default: latest)
#   ENV_FILE          - Path to environment file (optional)
#
# Examples:
#   # Deploy with environment variables
#   PROJECT_ID=my-project ./deploy.sh
#
#   # Deploy with custom settings
#   PROJECT_ID=my-project REGION=us-west1 SERVICE_NAME=dungeon-master-dev ./deploy.sh
#
#   # Deploy with env file
#   PROJECT_ID=my-project ENV_FILE=.env.production ./deploy.sh

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Load environment file if specified
if [[ -n "${ENV_FILE:-}" ]] && [[ -f "$ENV_FILE" ]]; then
    log_info "Loading environment from $ENV_FILE"
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

# Configuration with defaults
PROJECT_ID="${PROJECT_ID:-}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-dungeon-master}"
ARTIFACT_REPO="${ARTIFACT_REPO:-dungeon-master}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Validate required parameters
if [[ -z "$PROJECT_ID" ]]; then
    log_error "PROJECT_ID is required. Set it via environment variable or pass it directly."
    exit 1
fi

# Construct image URL
IMAGE_URL="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/${SERVICE_NAME}:${IMAGE_TAG}"

log_info "Deploying Dungeon Master Service"
log_info "Project ID: $PROJECT_ID"
log_info "Region: $REGION"
log_info "Service Name: $SERVICE_NAME"
log_info "Image URL: $IMAGE_URL"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    log_error "gcloud CLI is not installed. Please install Google Cloud SDK."
    exit 1
fi

# Set active project
log_info "Setting active GCP project..."
gcloud config set project "$PROJECT_ID"

# Deploy to Cloud Run
log_info "Deploying to Cloud Run..."

# Build deployment command with recommended settings from gcp_deployment_reference.md
DEPLOY_CMD=(
    gcloud run deploy "$SERVICE_NAME"
    --image "$IMAGE_URL"
    --region "$REGION"
    --platform managed
    --memory 1Gi
    --cpu 2
    --concurrency 80
    --min-instances 0
    --max-instances 100
    --timeout 300s
    --allow-unauthenticated
)

# Add service account if specified
if [[ -n "${SERVICE_ACCOUNT:-}" ]]; then
    log_info "Using service account: $SERVICE_ACCOUNT"
    DEPLOY_CMD+=(--service-account "$SERVICE_ACCOUNT")
fi

# Add secrets from Secret Manager (if specified)
# Format: SECRET_NAME:ENV_VAR_NAME
if [[ -n "${SECRETS:-}" ]]; then
    log_info "Mounting secrets from Secret Manager..."
    IFS=',' read -ra SECRET_ARRAY <<< "$SECRETS"
    for secret in "${SECRET_ARRAY[@]}"; do
        DEPLOY_CMD+=(--set-secrets "$secret")
    done
fi

# Add environment variables (if specified)
# Format: KEY1=VALUE1,KEY2=VALUE2
if [[ -n "${ENV_VARS:-}" ]]; then
    log_info "Setting environment variables..."
    DEPLOY_CMD+=(--set-env-vars "$ENV_VARS")
fi

# Add VPC configuration (if specified)
if [[ -n "${VPC_CONNECTOR:-}" ]]; then
    log_info "Using VPC connector: $VPC_CONNECTOR"
    DEPLOY_CMD+=(--vpc-connector "$VPC_CONNECTOR")
fi

# Execute deployment
"${DEPLOY_CMD[@]}"

if [[ $? -eq 0 ]]; then
    log_info "Deployment successful!"
    
    # Get service URL
    SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
        --region "$REGION" \
        --format 'value(status.url)')
    
    log_info "Service URL: $SERVICE_URL"
    log_info "Health check: $SERVICE_URL/health"
    
    # Optional: Test health endpoint
    if command -v curl &> /dev/null; then
        log_info "Testing health endpoint..."
        if curl -f -s "$SERVICE_URL/health" > /dev/null; then
            log_info "Health check passed ✓"
        else
            log_warn "Health check failed. Service may still be starting up."
        fi
    fi
else
    log_error "Deployment failed!"
    exit 1
fi
