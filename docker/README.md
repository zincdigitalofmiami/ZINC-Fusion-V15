# Docker Configuration

## MLflow Stack

The Docker Compose stack provides:

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| mlflow | mlflow-server | 5001 | MLflow Tracking Server UI & API |
| mlflow-postgres | mlflow-postgres | 5432 | PostgreSQL backend store |
| minio | mlflow-minio | 9000, 9001 | S3-compatible artifact storage |

## Quick Start

```bash
# From project root
./scripts/start-mlflow.sh

# Or manually
docker compose -f docker/docker-compose.yml up -d mlflow-postgres minio mlflow
```

## Access

- **MLflow UI**: http://localhost:5001
- **MinIO Console**: http://localhost:9001 (mlflow / mlflow123)
- **PostgreSQL**: localhost:5432/mlflow (mlflow / mlflow)

## Files

| File | Description |
|------|-------------|
| `docker-compose.yml` | Service definitions for MLflow stack |
| `Dockerfile.mlflow` | Custom MLflow image with psycopg2-binary |
| `Dockerfile.api` | FastAPI service (optional, use `--profile api`) |

## Commands

```bash
# Start MLflow stack
docker compose -f docker/docker-compose.yml up -d mlflow-postgres minio mlflow

# View logs
docker compose -f docker/docker-compose.yml logs -f mlflow

# Stop all
docker compose -f docker/docker-compose.yml down

# Rebuild MLflow image
docker compose -f docker/docker-compose.yml build mlflow

# Start with FastAPI (requires DATABASE_URL)
docker compose -f docker/docker-compose.yml --profile api up -d
```

## Data Persistence

Docker volumes store persistent data:

- `mlflow-postgres-data` - PostgreSQL database files
- `mlflow-minio-data` - MinIO artifact storage

To reset all data:
```bash
docker compose -f docker/docker-compose.yml down -v
```
