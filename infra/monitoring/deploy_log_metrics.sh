#!/bin/bash
# Deploy log-based metrics for Dungeon Master service
#
# This script creates log-based metrics from log_metrics.yaml
# Usage: bash deploy_log_metrics.sh [PROJECT_ID]

set -euo pipefail

# Configuration
PROJECT_ID="${1:-$(gcloud config get-value project)}"

if [[ -z "$PROJECT_ID" ]]; then
    echo "Error: PROJECT_ID not set. Pass as argument or set default project."
    exit 1
fi

echo "Deploying log-based metrics to project: $PROJECT_ID"

# LLM API Errors
echo "Creating metric: llm_api_errors"
gcloud logging metrics create llm_api_errors \
    --project="$PROJECT_ID" \
    --description="Count of OpenAI LLM API errors (rate limits, timeouts, auth failures)" \
    --log-filter='resource.type="cloud_run_revision"
resource.labels.service_name="dungeon-master"
jsonPayload.level="ERROR"
(jsonPayload.logger="llm_client" OR jsonPayload.logger="openai_client")' \
    2>/dev/null && echo "✓ Created llm_api_errors" || echo "⚠ llm_api_errors already exists"

# Journey-Log Service Errors
echo "Creating metric: journey_log_errors"
gcloud logging metrics create journey_log_errors \
    --project="$PROJECT_ID" \
    --description="Count of journey-log service connectivity errors" \
    --log-filter='resource.type="cloud_run_revision"
resource.labels.service_name="dungeon-master"
jsonPayload.level="ERROR"
jsonPayload.logger="journey_log_client"' \
    2>/dev/null && echo "✓ Created journey_log_errors" || echo "⚠ journey_log_errors already exists"

# Turn Processing Duration
echo "Creating metric: turn_processing_duration_ms"
gcloud logging metrics create turn_processing_duration_ms \
    --project="$PROJECT_ID" \
    --description="Duration of turn processing in milliseconds (end-to-end)" \
    --log-filter='resource.type="cloud_run_revision"
resource.labels.service_name="dungeon-master"
jsonPayload.endpoint="/turn"
jsonPayload.duration_ms>0' \
    --value-extractor='EXTRACT(jsonPayload.duration_ms)' \
    2>/dev/null && echo "✓ Created turn_processing_duration_ms" || echo "⚠ turn_processing_duration_ms already exists"

# Policy Engine Quest Triggers
echo "Creating metric: policy_quest_triggers"
gcloud logging metrics create policy_quest_triggers \
    --project="$PROJECT_ID" \
    --description="Count of quest triggers by policy engine" \
    --log-filter='resource.type="cloud_run_revision"
resource.labels.service_name="dungeon-master"
jsonPayload.event="policy_trigger"
jsonPayload.trigger_type="quest"' \
    2>/dev/null && echo "✓ Created policy_quest_triggers" || echo "⚠ policy_quest_triggers already exists"

# Policy Engine POI Triggers
echo "Creating metric: policy_poi_triggers"
gcloud logging metrics create policy_poi_triggers \
    --project="$PROJECT_ID" \
    --description="Count of POI (Point of Interest) triggers by policy engine" \
    --log-filter='resource.type="cloud_run_revision"
resource.labels.service_name="dungeon-master"
jsonPayload.event="policy_trigger"
jsonPayload.trigger_type="poi"' \
    2>/dev/null && echo "✓ Created policy_poi_triggers" || echo "⚠ policy_poi_triggers already exists"

# Cold Starts
echo "Creating metric: cold_starts"
gcloud logging metrics create cold_starts \
    --project="$PROJECT_ID" \
    --description="Count of container cold starts" \
    --log-filter='resource.type="cloud_run_revision"
resource.labels.service_name="dungeon-master"
jsonPayload.message=~"Cold start"' \
    2>/dev/null && echo "✓ Created cold_starts" || echo "⚠ cold_starts already exists"

echo ""
echo "Log-based metrics deployment complete!"
echo ""
echo "Verify with:"
echo "  gcloud logging metrics list --project=$PROJECT_ID --filter='name:llm_api_errors OR name:journey_log_errors'"
