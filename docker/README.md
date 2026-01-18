# Docker Configuration

## Services

The Docker Compose stack provides:

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| fusion-api | fusion-api | 8000 | FastAPI backend service |

> **Note**: MLflow was removed 2026-01-18. Model registry now uses GrafanaRegistry, writing directly to Prisma.

## Quick Start

```bash
# Start FastAPI (requires DATABASE_URL)
docker compose -f docker/docker-compose.yml --profile api up -d
```

## Files

| File | Description |
|------|-------------|
| `docker-compose.yml` | Service definitions |
| `Dockerfile.api` | FastAPI service (use `--profile api`) |

## Commands

```bash
# Start FastAPI
docker compose -f docker/docker-compose.yml --profile api up -d

# View logs
docker compose -f docker/docker-compose.yml logs -f fusion-api

# Stop all
docker compose -f docker/docker-compose.yml down
```
