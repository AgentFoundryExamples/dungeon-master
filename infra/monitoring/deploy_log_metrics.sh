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

# Function to create or update a log metric
create_or_update_metric() {
    local metric_name=$1
    local description=$2
    local log_filter=$3
    local value_extractor=${4:-""}
    
    echo "Processing metric: $metric_name"
    
    # Try to update first (metric already exists)
    local update_cmd="gcloud logging metrics update $metric_name \
        --project=\"$PROJECT_ID\" \
        --description=\"$description\" \
        --log-filter='$log_filter'"
    
    if [[ -n "$value_extractor" ]]; then
        update_cmd="$update_cmd --value-extractor='$value_extractor'"
    fi
    
    if eval "$update_cmd" 2>/dev/null; then
        echo "✓ Updated $metric_name"
        return 0
    fi
    
    # If update failed, try to create (metric doesn't exist)
    local create_cmd="gcloud logging metrics create $metric_name \
        --project=\"$PROJECT_ID\" \
        --description=\"$description\" \
        --log-filter='$log_filter'"
    
    if [[ -n "$value_extractor" ]]; then
        create_cmd="$create_cmd --value-extractor='$value_extractor'"
    fi
    
    if eval "$create_cmd" 2>&1 | tee /tmp/metric_create_error.log; then
        echo "✓ Created $metric_name"
        return 0
    else
        # Check if it's a permissions error or other serious issue
        if grep -q "PERMISSION_DENIED" /tmp/metric_create_error.log; then
            echo "✗ Permission denied for $metric_name. Check IAM roles."
            return 1
        elif grep -q "already exists" /tmp/metric_create_error.log; then
            echo "⚠ $metric_name already exists (no changes needed)"
            return 0
        else
            echo "✗ Failed to create $metric_name. See error above."
            return 1
        fi
    fi
}

# LLM API Errors
create_or_update_metric "llm_api_errors" \
    "Count of OpenAI LLM API errors (rate limits, timeouts, auth failures)" \
    'resource.type="cloud_run_revision"
resource.labels.service_name="dungeon-master"
jsonPayload.level="ERROR"
(jsonPayload.logger="llm_client" OR jsonPayload.logger="openai_client")'

# Journey-Log Service Errors
create_or_update_metric "journey_log_errors" \
    "Count of journey-log service connectivity errors" \
    'resource.type="cloud_run_revision"
resource.labels.service_name="dungeon-master"
jsonPayload.level="ERROR"
jsonPayload.logger="journey_log_client"'

# Turn Processing Duration
create_or_update_metric "turn_processing_duration_ms" \
    "Duration of turn processing in milliseconds (end-to-end)" \
    'resource.type="cloud_run_revision"
resource.labels.service_name="dungeon-master"
jsonPayload.endpoint="/turn"
jsonPayload.duration_ms>0' \
    'EXTRACT(jsonPayload.duration_ms)'

# Policy Engine Quest Triggers
create_or_update_metric "policy_quest_triggers" \
    "Count of quest triggers by policy engine" \
    'resource.type="cloud_run_revision"
resource.labels.service_name="dungeon-master"
jsonPayload.event="policy_trigger"
jsonPayload.trigger_type="quest"'

# Policy Engine POI Triggers
create_or_update_metric "policy_poi_triggers" \
    "Count of POI (Point of Interest) triggers by policy engine" \
    'resource.type="cloud_run_revision"
resource.labels.service_name="dungeon-master"
jsonPayload.event="policy_trigger"
jsonPayload.trigger_type="poi"'

# Cold Starts
create_or_update_metric "cold_starts" \
    "Count of container cold starts" \
    'resource.type="cloud_run_revision"
resource.labels.service_name="dungeon-master"
jsonPayload.message=~"Cold start"'

# Clean up temp file
rm -f /tmp/metric_create_error.log

echo ""
echo "Log-based metrics deployment complete!"
echo ""
echo "Verify with:"
echo "  gcloud logging metrics list --project=$PROJECT_ID --filter='name:llm_api_errors OR name:journey_log_errors'"
