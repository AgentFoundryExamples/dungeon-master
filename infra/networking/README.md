# Service Discovery Configuration for Dungeon Master

This directory contains configuration files and documentation for service discovery, networking, and ingress setup for the Dungeon Master Cloud Run service.

## Table of Contents

1. [Service Discovery Overview](#service-discovery-overview)
2. [Cloud Run Default Domain](#cloud-run-default-domain)
3. [Custom Domain Mapping](#custom-domain-mapping)
4. [API Gateway Integration](#api-gateway-integration)
5. [VPC and Private Networking](#vpc-and-private-networking)
6. [Multi-Region Deployment](#multi-region-deployment)
7. [Preview Environments](#preview-environments)

## Service Discovery Overview

The Dungeon Master service supports multiple service discovery strategies depending on your deployment requirements:

| Strategy | Use Case | Authentication | DNS Management |
|----------|----------|----------------|----------------|
| **Cloud Run Default Domain** | Development, staging, internal testing | Optional (IAM-based) | Automatic |
| **Custom Domain Mapping** | Production user-facing service | SSL/TLS + optional IAM | Manual (Cloud DNS or external) |
| **API Gateway** | Public API with rate limiting & API keys | API key-based | Automatic (API Gateway domain) |
| **Internal Load Balancer** | Private services within VPC | IAM-based | VPC DNS |

### Recommended Strategy: Cloud Run Default Domain + Optional API Gateway

**For most deployments:**
- **Development/Staging**: Use Cloud Run default domain (e.g., `https://dungeon-master-abc123-uc.a.run.app`)
- **Production**: Use API Gateway in front of Cloud Run for:
  - API key authentication
  - Rate limiting per client
  - Request/response transformation
  - API versioning

## Cloud Run Default Domain

Every Cloud Run service automatically receives a unique HTTPS domain in the format:

```
https://SERVICE_NAME-HASH-REGION_CODE.a.run.app
```

Example:
```
https://dungeon-master-a3b2c1d4e5-uc.a.run.app
```

### Features

- ✅ **Automatic SSL/TLS**: Managed certificates, no configuration needed
- ✅ **Global anycast**: Traffic routed to nearest healthy region
- ✅ **Zero configuration**: Works immediately after deployment
- ✅ **High availability**: Built-in load balancing and failover

### Getting the Service URL

```bash
# Get service URL after deployment
gcloud run services describe dungeon-master \
  --region us-central1 \
  --format 'value(status.url)'
```

### Example Integration

```python
# Client configuration
DUNGEON_MASTER_URL = "https://dungeon-master-a3b2c1d4e5-uc.a.run.app"

# Make request
import requests
response = requests.post(
    f"{DUNGEON_MASTER_URL}/turn",
    json={"character_id": 123, "action": "attack"},
    headers={"Authorization": f"Bearer {token}"}
)
```

### Authentication

**Development** (unauthenticated):
```bash
gcloud run deploy dungeon-master \
  --allow-unauthenticated
```

**Production** (authenticated):
```bash
gcloud run deploy dungeon-master \
  --no-allow-unauthenticated

# Grant access to specific service account or user
gcloud run services add-iam-policy-binding dungeon-master \
  --member="serviceAccount:client-app@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --region=us-central1
```

## Custom Domain Mapping

For production deployments with a custom domain (e.g., `api.yourgame.com`), use Cloud Run domain mapping.

### Prerequisites

1. **Domain ownership verified** in Google Search Console
2. **DNS provider** (Cloud DNS or external like Cloudflare)
3. **SSL certificate** (automatic with Cloud Run)

### Setup Steps

#### 1. Map Domain to Cloud Run Service

```bash
# Map custom domain to service
gcloud run domain-mappings create \
  --service dungeon-master \
  --domain api.yourgame.com \
  --region us-central1
```

#### 2. Configure DNS Records

Cloud Run will provide DNS records to configure. For Cloud DNS:

```bash
# Get DNS records from domain mapping
gcloud run domain-mappings describe \
  --domain api.yourgame.com \
  --region us-central1

# Add CNAME record to Cloud DNS
gcloud dns record-sets create api.yourgame.com. \
  --zone=yourgame-zone \
  --type=CNAME \
  --ttl=300 \
  --rrdatas="ghs.googlehosted.com."
```

For external DNS providers (Cloudflare, Route53, etc.), add the CNAME record manually:

```
Type:  CNAME
Name:  api
Value: ghs.googlehosted.com
TTL:   300 (or auto)
```

#### 3. Verify Domain Mapping

```bash
# Check domain mapping status
gcloud run domain-mappings describe \
  --domain api.yourgame.com \
  --region us-central1

# Test with curl
curl -v https://api.yourgame.com/health
```

### SSL/TLS Certificate

Cloud Run automatically provisions and renews SSL certificates for custom domains via Google-managed certificates. This process takes 15-60 minutes after DNS propagation.

**Certificate Status:**
```bash
gcloud run domain-mappings describe \
  --domain api.yourgame.com \
  --region us-central1 \
  --format='value(status.certificateStatus)'
```

## API Gateway Integration

For public-facing APIs requiring API key authentication, rate limiting, and request validation, deploy an API Gateway in front of Cloud Run.

See: [`api_gateway.yaml`](./api_gateway.yaml) for OpenAPI specification and deployment instructions.

### Benefits

- ✅ **API Key Authentication**: Managed API keys with rotation
- ✅ **Rate Limiting**: Per-client quotas (e.g., 1000 requests/day)
- ✅ **Request Validation**: Schema validation before reaching service
- ✅ **API Versioning**: Support multiple API versions (v1, v2)
- ✅ **Cost Control**: Block unauthorized traffic before Cloud Run invocation

### Quick Setup

```bash
# Deploy API Gateway configuration
gcloud api-gateway api-configs create dungeon-master-config \
  --api=dungeon-master-api \
  --openapi-spec=api_gateway.yaml \
  --project=PROJECT_ID \
  --backend-auth-service-account=dungeon-master-sa@PROJECT_ID.iam.gserviceaccount.com

# Create API Gateway
gcloud api-gateway gateways create dungeon-master-gateway \
  --api=dungeon-master-api \
  --api-config=dungeon-master-config \
  --location=us-central1 \
  --project=PROJECT_ID
```

**Gateway URL:**
```
https://dungeon-master-gateway-HASH-uc.a.run.app
```

See [`api_gateway.yaml`](./api_gateway.yaml) for full configuration.

## VPC and Private Networking

For private deployments requiring VPC connectivity (e.g., Cloud SQL with private IP, internal services), configure VPC access.

### Use Cases

- Connecting to Cloud SQL instances with private IP
- Accessing services on internal VPC networks
- Compliance requirements (traffic must stay within GCP)

### Setup VPC Connector

```bash
# Create Serverless VPC Access connector
gcloud compute networks vpc-access connectors create dungeon-master-connector \
  --region=us-central1 \
  --network=default \
  --range=10.8.0.0/28 \
  --min-instances=2 \
  --max-instances=10 \
  --machine-type=e2-micro
```

### Configure Cloud Run Service

Update `service.yaml` with VPC annotations:

```yaml
spec:
  template:
    metadata:
      annotations:
        run.googleapis.com/vpc-access-connector: projects/PROJECT_ID/locations/us-central1/connectors/dungeon-master-connector
        run.googleapis.com/vpc-access-egress: private-ranges-only
```

Or via gcloud:

```bash
gcloud run services update dungeon-master \
  --vpc-connector dungeon-master-connector \
  --vpc-egress private-ranges-only \
  --region us-central1
```

### VPC Egress Options

- **`all-traffic`**: Route all egress through VPC (including public IPs)
- **`private-ranges-only`**: Only route private IP ranges through VPC (default for internet access)

**Recommendation**: Use `private-ranges-only` unless you need VPC-based egress filtering.

See: [`vpc_connector.yaml`](./vpc_connector.yaml) for Terraform configuration.

## Multi-Region Deployment

For global availability and reduced latency, deploy Dungeon Master to multiple regions.

### Strategy 1: Active-Active (Load Balanced)

Deploy to multiple regions with Cloud Load Balancer distributing traffic:

```bash
# Deploy to multiple regions
for REGION in us-central1 us-east1 europe-west1; do
  gcloud run deploy dungeon-master-${REGION} \
    --image us-central1-docker.pkg.dev/PROJECT_ID/dungeon-master/dungeon-master:latest \
    --region ${REGION} \
    --no-allow-unauthenticated
done

# Configure Cloud Load Balancer with NEGs (Network Endpoint Groups)
# See: https://cloud.google.com/run/docs/multiple-regions
```

### Strategy 2: Active-Passive (Failover)

Deploy primary region with DNS failover to secondary:

```bash
# Primary region
gcloud run deploy dungeon-master \
  --region us-central1 \
  --tag primary

# Failover region
gcloud run deploy dungeon-master \
  --region us-east1 \
  --tag failover

# Configure Cloud DNS with health checks and failover policies
```

### DNS Conflict Prevention

Use region-specific service names or tags to prevent conflicts:

```
dungeon-master-us-central1
dungeon-master-us-east1
dungeon-master-europe-west1
```

Or use traffic tags:

```
https://primary---dungeon-master-HASH-uc.a.run.app
https://failover---dungeon-master-HASH-ue.a.run.app
```

## Preview Environments

For testing pull requests and feature branches, deploy preview environments with unique service names.

### Naming Convention

```
dungeon-master-pr-{PR_NUMBER}
dungeon-master-{BRANCH_NAME}
dungeon-master-preview-{SHORT_SHA}
```

### Example: GitHub Actions Preview Deployment

```bash
# In Cloud Build or GitHub Actions
PREVIEW_NAME="dungeon-master-pr-${PULL_REQUEST_NUMBER}"

gcloud run deploy ${PREVIEW_NAME} \
  --image us-central1-docker.pkg.dev/PROJECT_ID/dungeon-master/dungeon-master:pr-${PULL_REQUEST_NUMBER} \
  --region us-central1 \
  --no-traffic \
  --tag pr-${PULL_REQUEST_NUMBER}

# Get preview URL
PREVIEW_URL=$(gcloud run services describe ${PREVIEW_NAME} \
  --region us-central1 \
  --format 'value(status.url)')

# Comment on PR with preview URL
echo "Preview environment: ${PREVIEW_URL}"
```

### DNS Conflict Prevention

- Use unique service names per preview environment
- Use Cloud Run traffic tags for routing
- Clean up preview environments after PR merge:

```bash
# Auto-cleanup via GitHub Actions
gcloud run services delete dungeon-master-pr-${PULL_REQUEST_NUMBER} \
  --region us-central1 \
  --quiet
```

## Ingress Control

Control which traffic sources can reach your service.

### Ingress Options

```bash
# Allow all traffic (default, for public services)
--ingress=all

# Allow Cloud Load Balancing and internal traffic only
--ingress=internal-and-cloud-load-balancing

# Allow internal traffic only (VPC and same project)
--ingress=internal
```

### Recommended Settings

| Environment | Ingress | Authentication |
|-------------|---------|----------------|
| **Development** | `all` | `--allow-unauthenticated` |
| **Staging** | `all` | `--no-allow-unauthenticated` (IAM) |
| **Production (public)** | `all` | API Gateway with API keys |
| **Production (private)** | `internal-and-cloud-load-balancing` | IAM or IAP |

## Health Endpoints

The Dungeon Master service exposes health check endpoints for service discovery and monitoring:

```
GET /health         - Basic health check (always returns 200 OK)
GET /readiness      - Readiness check (optional journey-log ping)
```

Configure health checks in load balancers or monitoring:

```bash
# Cloud Run startup/liveness probes (in service.yaml)
startupProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 0
  timeoutSeconds: 5
  periodSeconds: 10
  failureThreshold: 3
```

## Troubleshooting

### "Service not found" errors

```bash
# Verify service exists
gcloud run services list --region us-central1

# Check service status
gcloud run services describe dungeon-master --region us-central1
```

### DNS propagation delays

```bash
# Check DNS resolution
dig api.yourgame.com

# Force DNS cache clear
sudo systemd-resolve --flush-caches  # Linux
sudo dscacheutil -flushcache          # macOS
```

### SSL certificate not provisioning

```bash
# Check certificate status
gcloud run domain-mappings describe \
  --domain api.yourgame.com \
  --region us-central1

# Common issues:
# - DNS records not configured correctly
# - Domain ownership not verified
# - DNS propagation delay (wait 15-60 minutes)
```

### VPC connector errors

```bash
# Check connector status
gcloud compute networks vpc-access connectors describe dungeon-master-connector \
  --region us-central1

# Check service account permissions
gcloud projects get-iam-policy PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:dungeon-master-sa@PROJECT_ID.iam.gserviceaccount.com"
```

## References

- [Cloud Run Domain Mapping](https://cloud.google.com/run/docs/mapping-custom-domains)
- [Cloud Run Traffic Management](https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)
- [API Gateway Documentation](https://cloud.google.com/api-gateway/docs)
- [Serverless VPC Access](https://cloud.google.com/vpc/docs/configure-serverless-vpc-access)
- [Cloud Run Ingress Control](https://cloud.google.com/run/docs/securing/ingress)
