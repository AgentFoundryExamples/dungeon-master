# Dungeon Master Service - Multi-stage Dockerfile
# Base Image: Python 3.14-slim (per infrastructure_versions.txt)

# Stage 1: Builder - Install dependencies
FROM python:3.14-slim AS builder

WORKDIR /app

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime - Minimal production image
FROM python:3.14-slim

WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY app/ ./app/
COPY example_openai_usage.py .

# Copy policy config if it exists, otherwise use example
# Production deployments should mount proper config via Secret Manager or ConfigMap
COPY policy_config.json* ./

# Ensure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Cloud Run requires listening on PORT environment variable
ENV PORT=8080

# Non-root user for security (Cloud Run best practice)
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check (optional, Cloud Run uses /health endpoint)
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=2)" || exit 1

# Start the FastAPI application with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
