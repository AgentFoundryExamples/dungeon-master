# Cloud Monitoring Configuration for Dungeon Master Service

This directory contains monitoring configurations including alert policies, log-based metrics, dashboards, and uptime checks for the Dungeon Master Cloud Run service.

## Table of Contents

1. [Overview](#overview)
2. [Alert Policies](#alert-policies)
3. [Log-Based Metrics](#log-based-metrics)
4. [Dashboards](#dashboards)
5. [Uptime Checks](#uptime-checks)
6. [Deployment](#deployment)
7. [Verification](#verification)

## Overview

The monitoring stack for Dungeon Master uses native Google Cloud Monitoring (formerly Stackdriver) and includes:

- **Alert Policies**: Automated notifications for service degradation
- **Log-Based Metrics**: Custom metrics derived from application logs
- **Dashboards**: Visual representations of service health and performance
- **Uptime Checks**: Synthetic monitoring of service availability

### Key Metrics Monitored

| Metric | Type | Threshold | Action |
|--------|------|-----------|--------|
| **Error Rate (5xx)** | Cloud Run metric | > 5% of requests | Alert on-call |
| **Request Latency (p95)** | Cloud Run metric | > 5 seconds | Alert on-call |
| **Container Instance Count** | Cloud Run metric | > 90 instances | Alert capacity team |
| **LLM API Errors** | Log-based metric | > 10 errors/min | Alert on-call |
| **Deployment Failures** | Cloud Build metric | Any failure | Alert deploy team |
| **Service Availability** | Uptime check | < 99% uptime | Alert on-call |

## Alert Policies

Alert policies define conditions that trigger notifications when service health degrades.

### Files

- [`alert_policies.yaml`](./alert_policies.yaml) - All alert policy definitions
- [`notification_channels.yaml`](./notification_channels.yaml) - Email, PagerDuty, Slack channels

### Alert Policy Summary

#### 1. High Error Rate (5xx Responses)

**Condition**: Error rate > 5% of total requests over 5-minute window

**Severity**: Critical

**Notification**: PagerDuty on-call + Slack #incidents

**Purpose**: Detect service outages or backend failures

#### 2. High Request Latency (P95)

**Condition**: 95th percentile latency > 5 seconds over 10-minute window

**Severity**: Warning

**Notification**: Slack #alerts

**Purpose**: Detect LLM API slowdowns or resource contention

#### 3. Instance Count Near Limit

**Condition**: Running instances > 90 (90% of max-instances=100)

**Severity**: Warning

**Notification**: Email capacity-planning@team

**Purpose**: Capacity planning and quota management

#### 4. LLM API Error Spike

**Condition**: LLM errors > 10/minute over 5-minute window

**Severity**: Critical

**Notification**: PagerDuty on-call

**Purpose**: Detect OpenAI API issues or authentication failures

#### 5. Deployment Failure

**Condition**: Cloud Build status = FAILURE

**Severity**: High

**Notification**: Slack #deployments + Email deploy-team@team

**Purpose**: Detect CI/CD pipeline issues

#### 6. Service Unavailable (Uptime Check)

**Condition**: Health endpoint returns non-200 status

**Severity**: Critical

**Notification**: PagerDuty on-call + Slack #incidents

**Purpose**: Detect complete service outages

See [`alert_policies.yaml`](./alert_policies.yaml) for complete definitions.

## Log-Based Metrics

Log-based metrics extract structured data from application logs to create custom metrics.

### Files

- [`log_metrics.yaml`](./log_metrics.yaml) - All log-based metric definitions

### Log Metric Summary

1. **LLM API Errors**: Track OpenAI API failures, rate limits, timeouts
2. **Journey-Log Service Errors**: Track journey-log service connectivity issues
3. **Turn Processing Duration**: Track turn processing performance
4. **Policy Engine Triggers**: Track quest/POI trigger rates

See [`log_metrics.yaml`](./log_metrics.yaml) for complete definitions and filters.

## Dashboards

Pre-built dashboards provide visual monitoring of service health.

### Files

- [`dashboard.json`](./dashboard.json) - Main service health dashboard
- [`llm_dashboard.json`](./llm_dashboard.json) - LLM-specific metrics

### Main Dashboard Widgets

1. **Request Rate**: Requests per second over time
2. **Error Rate**: Current 5xx error percentage
3. **Request Latency**: P50, P95, P99 latencies
4. **Instance Count**: Active container instances
5. **LLM API Errors**: Total LLM errors
6. **Memory Usage**: Container memory consumption
7. **CPU Utilization**: Container CPU usage
8. **Cold Starts**: Number of cold starts

## Uptime Checks

Synthetic monitoring from Google's global probe network.

### Files

- [`uptime_checks.yaml`](./uptime_checks.yaml) - Uptime check definitions

### Configuration

- **Endpoint**: `/health`
- **Frequency**: Every 1 minute
- **Locations**: 6 global locations
- **Timeout**: 10 seconds
- **Failure Threshold**: 2 consecutive failures

## Deployment

### Prerequisites

```bash
# Enable Cloud Monitoring API
gcloud services enable monitoring.googleapis.com

# Enable Cloud Logging API
gcloud services enable logging.googleapis.com
```

### Deploy Alert Policies

```bash
cd infra/monitoring
gcloud alpha monitoring policies create --policy-from-file=alert_policies.yaml
```

### Deploy Log-Based Metrics

```bash
bash deploy_log_metrics.sh
```

### Deploy Dashboards

Import `dashboard.json` via Cloud Console or Terraform.

### Deploy Uptime Checks

```bash
bash deploy_uptime_checks.sh
```

## Verification

```bash
# Verify alert policies
gcloud alpha monitoring policies list --filter="displayName:Dungeon Master"

# Verify log metrics
gcloud logging metrics list --filter="name:llm_api_errors"

# Verify dashboards
gcloud monitoring dashboards list --filter="displayName:Dungeon Master"

# Verify uptime checks
gcloud monitoring uptime list-configs
```

## Updating Configs Post-Deploy

### Update Alert Thresholds

```bash
# Edit alert_policies.yaml
# Then reapply
gcloud alpha monitoring policies update POLICY_ID \
  --policy-from-file=alert_policies.yaml
```

### Update Notification Channels

```bash
# Add new channel
gcloud alpha monitoring channels create \
  --display-name="New Channel" \
  --type=email \
  --channel-labels=email_address=team@example.com
```

See full documentation above for detailed instructions on verification and troubleshooting.

## References

- [Cloud Monitoring Documentation](https://cloud.google.com/monitoring/docs)
- [Cloud Logging Documentation](https://cloud.google.com/logging/docs)
- [Log-Based Metrics](https://cloud.google.com/logging/docs/logs-based-metrics)
- [Alert Policies](https://cloud.google.com/monitoring/alerts)
- [Uptime Checks](https://cloud.google.com/monitoring/uptime-checks)
