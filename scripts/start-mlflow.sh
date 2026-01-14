#!/bin/bash
# =============================================================================
# ZINC-FUSION-V15: Start MLflow Stack
# =============================================================================
# Starts PostgreSQL, MinIO, and MLflow Tracking Server via Docker Compose
# =============================================================================

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo ""
echo "=========================================="
echo "🚀 Starting ZINC-FUSION MLflow Stack"
echo "=========================================="
echo ""

# Check Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop first."
    exit 1
fi

# Start MLflow services only (not fusion-api which requires DATABASE_URL)
echo "📦 Starting MLflow containers..."
docker compose -f docker/docker-compose.yml up -d mlflow-postgres minio mlflow

echo ""
echo "⏳ Waiting for services to be ready (15s)..."
sleep 15

# Health checks
echo ""
echo "🔍 Checking service health..."

# PostgreSQL
if docker exec mlflow-postgres pg_isready -U mlflow > /dev/null 2>&1; then
    echo "  ✅ PostgreSQL (mlflow-postgres:5432)"
else
    echo "  ❌ PostgreSQL - not ready"
    echo "     Check logs: docker logs mlflow-postgres"
    exit 1
fi

# MinIO
if curl -sf http://localhost:9000/minio/health/live > /dev/null 2>&1; then
    echo "  ✅ MinIO (localhost:9000)"
else
    echo "  ❌ MinIO - not ready"
    echo "     Check logs: docker logs mlflow-minio"
    exit 1
fi

# MLflow
if curl -sf http://localhost:5001/api/2.0/mlflow/experiments/list > /dev/null 2>&1; then
    echo "  ✅ MLflow (localhost:5001)"
else
    # Give MLflow a bit more time
    echo "  ⏳ MLflow starting up, waiting 10 more seconds..."
    sleep 10
    if curl -sf http://localhost:5001/api/2.0/mlflow/experiments/list > /dev/null 2>&1; then
        echo "  ✅ MLflow (localhost:5001)"
    else
        echo "  ❌ MLflow - not ready"
        echo "     Check logs: docker logs mlflow-server"
        exit 1
    fi
fi

echo ""
echo "=========================================="
echo "🎉 MLflow Stack Running!"
echo "=========================================="
echo ""
echo "  MLflow UI:      http://localhost:5001"
echo "  MinIO Console:  http://localhost:9001"
echo "                  (user: mlflow, pass: mlflow123)"
echo "  PostgreSQL:     localhost:5432/mlflow"
echo "                  (user: mlflow, pass: mlflow)"
echo ""
echo "  View logs:      docker compose -f docker/docker-compose.yml logs -f mlflow"
echo "  Stop:           docker compose -f docker/docker-compose.yml down"
echo ""
echo "=========================================="
echo ""
