#!/bin/bash
# Deploy uptime checks for Dungeon Master service
#
# This script creates synthetic monitoring uptime checks
# Usage: bash deploy_uptime_checks.sh PROJECT_ID SERVICE_URL

set -euo pipefail

# Configuration
PROJECT_ID="${1:-}"
SERVICE_URL="${2:-}"

if [[ -z "$PROJECT_ID" ]]; then
    echo "Error: PROJECT_ID is required as first argument"
    echo "Usage: bash deploy_uptime_checks.sh PROJECT_ID SERVICE_URL"
    echo "Example: bash deploy_uptime_checks.sh my-project https://dungeon-master-abc123-uc.a.run.app"
    exit 1
fi

if [[ -z "$SERVICE_URL" ]]; then
    echo "Error: SERVICE_URL is required as second argument"
    echo "Usage: bash deploy_uptime_checks.sh PROJECT_ID SERVICE_URL"
    echo "Example: bash deploy_uptime_checks.sh my-project https://dungeon-master-abc123-uc.a.run.app"
    exit 1
fi

# Extract hostname from URL (remove protocol and path)
# Example: https://service-abc123-uc.a.run.app/path -> service-abc123-uc.a.run.app
SERVICE_HOST=$(echo "$SERVICE_URL" | sed -e 's|^[^/]*//||' -e 's|/.*$||')

echo "Deploying uptime checks for Dungeon Master service"
echo "Project: $PROJECT_ID"
echo "Service URL: $SERVICE_URL"
echo "Service Host: $SERVICE_HOST"
echo ""

# Create secure temporary file for uptime check configuration
TEMP_CONFIG=$(mktemp /tmp/uptime_check_XXXXXX.json)
trap "rm -f $TEMP_CONFIG" EXIT  # Ensure cleanup even if script fails

# Create uptime check configuration file
cat > "$TEMP_CONFIG" << EOF
{
  "displayName": "Dungeon Master Health Check",
  "monitoredResource": {
    "type": "uptime_url",
    "labels": {
      "project_id": "$PROJECT_ID",
      "host": "$SERVICE_HOST"
    }
  },
  "httpCheck": {
    "path": "/health",
    "port": 443,
    "useSsl": true,
    "validateSsl": true,
    "requestMethod": "GET"
  },
  "period": "60s",
  "timeout": "10s",
  "contentMatchers": [
    {
      "content": "healthy",
      "matcher": "CONTAINS_STRING"
    }
  ],
  "checkerType": "STATIC_IP_CHECKERS"
}
EOF

echo "Creating uptime check..."
gcloud monitoring uptime-check-configs create \
    --project="$PROJECT_ID" \
    --config-from-file="$TEMP_CONFIG" \
    && echo "✓ Uptime check created successfully" || echo "⚠ Uptime check may already exist"

echo ""
echo "Uptime check deployment complete!"
echo ""
echo "Verify with:"
echo "  gcloud monitoring uptime-check-configs list --project=$PROJECT_ID"
echo ""
echo "View in Cloud Console:"
echo "  https://console.cloud.google.com/monitoring/uptime?project=$PROJECT_ID"
