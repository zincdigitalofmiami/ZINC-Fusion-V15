# MLflow Experiment Tracking Setup

## Overview

ZINC-FUSION-V15 uses MLflow for experiment tracking, model registry, and artifact storage. The setup uses Docker Compose to run:

- **MLflow Tracking Server** - Web UI and API for experiment tracking
- **PostgreSQL** - Backend store for runs, metrics, and parameters
- **MinIO** - S3-compatible object storage for model artifacts

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ZINC-FUSION DASHBOARD (:3000)                         │
│   QuantAdminSidebar → Model Registry → MLflow UI                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     MLflow TRACKING SERVER (:5001)                       │
│   Backend:  postgresql://mlflow-postgres:5432/mlflow                    │
│   Artifacts: s3://mlflow-artifacts (MinIO)                              │
└─────────────────────────────────────────────────────────────────────────┘
         │                                              │
         ▼                                              ▼
┌─────────────────────┐                    ┌─────────────────────────────┐
│   PostgreSQL (:5432)│                    │   MinIO (:9000/:9001)       │
│   mlflow database   │                    │   mlflow-artifacts bucket   │
└─────────────────────┘                    └─────────────────────────────┘
```

## Quick Start

### Start MLflow Stack

```bash
cd "/Volumes/Satechi Hub/ZINC-FUSION-V15"
./scripts/start-mlflow.sh
```

This starts PostgreSQL, MinIO, and MLflow. Health checks verify all services are ready.

### Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| MLflow UI | http://localhost:5001 | None required |
| MinIO Console | http://localhost:9001 | mlflow / mlflow123 |
| PostgreSQL | localhost:5432 | mlflow / mlflow |

### Stop MLflow Stack

```bash
docker compose -f docker/docker-compose.yml down
```

## Experiment Taxonomy

MLflow experiments are organized hierarchically:

```
zinc-fusion/
├── core/                    # L0 Core baseline models
│   ├── h5d                  # 5-day horizon
│   ├── h21d                 # 21-day horizon
│   ├── h63d                 # 63-day horizon
│   └── h126d                # 126-day horizon
├── specialist/              # L1 Domain specialist models
│   ├── trump_effect/h21d
│   ├── palm/h21d
│   ├── energy/h21d
│   ├── fx/h21d
│   └── ... (11 specialists)
├── ensemble/                # L2 Ensemble/stacking models
│   └── fusion-lasso
├── datasets/
│   ├── sources              # Data source registry
│   └── features             # Feature table profiles
└── backtest/                # Historical validation runs
```

## Model Registry

Registered models follow the naming convention:

- `zinc-fusion-core-h5d` - Core 5-day forecast
- `zinc-fusion-core-h21d` - Core 21-day forecast
- `zinc-fusion-specialist-palm` - Palm domain specialist
- `zinc-fusion-specialist-energy` - Energy domain specialist

### Model Tags

Each registered model has tags:
- `model_type`: core, specialist, ensemble
- `horizon`: 5, 21, 63, 126
- `status`: pending, trained, production
- `is_champion`: True/False
- `best_model`: WeightedEnsemble, Chronos2, etc.
- `mase`: Model accuracy score

## Python Integration

### Using QuantMLCommandCenter

```python
from scripts.mlflow_tracking import QuantMLCommandCenter

# Training workflow
cmd = QuantMLCommandCenter()
with cmd.training_run("core", horizon=5, mode="full") as run:
    predictor = TimeSeriesPredictor(...).fit(...)
    cmd.log_autogluon_model(predictor, training_time=3600.0)
```

### Connection Fallback

The `get_tracking_uri()` function automatically:
1. Tries to connect to MLflow server at `http://localhost:5001`
2. Falls back to local SQLite if server unavailable

```python
from scripts.mlflow_tracking import get_tracking_uri

uri = get_tracking_uri()  # Returns server URL or sqlite:///mlruns/mlflow.db
```

## Syncing Prisma Data

To sync existing Prisma database records to MLflow:

```bash
# Set DATABASE_URL environment variable
export DATABASE_URL="postgres://..."

# Run sync script
python scripts/sync_prisma_to_mlflow.py --all
```

### Sync Options

```bash
--all       # Sync everything
--models    # Sync model registry only
--runs      # Sync training runs only
--datasets  # Sync data sources only
--features  # Sync feature tables only
```

### What Gets Synced

| Prisma Table | MLflow Destination |
|--------------|-------------------|
| model.model_registry | Registered Models |
| ops.training_runs | Experiments & Runs |
| ops.data_source_registry | Dataset metadata |
| training.specialist_* | Feature table profiles |

## Docker Configuration

### Files

| File | Purpose |
|------|---------|
| `docker/docker-compose.yml` | Full stack definition |
| `docker/Dockerfile.mlflow` | Custom MLflow image with psycopg2 |
| `scripts/start-mlflow.sh` | Startup script with health checks |

### Environment Variables

Add to `.env`:

```bash
MLFLOW_TRACKING_URI=http://localhost:5001
MLFLOW_S3_ENDPOINT_URL=http://localhost:9000
AWS_ACCESS_KEY_ID=mlflow
AWS_SECRET_ACCESS_KEY=mlflow123
```

Add to `frontend/.env.local`:

```bash
NEXT_PUBLIC_MLFLOW_UI_URL=http://localhost:5001
```

## MinIO Artifact Storage

MinIO provides S3-compatible storage for:
- Trained model files (.pkl, .pt, .onnx)
- Leaderboard JSONs
- Metrics plots and visualizations
- Any artifacts logged during training

### Browse Artifacts

1. Open MinIO Console: http://localhost:9001
2. Login: mlflow / mlflow123
3. Navigate to `mlflow-artifacts` bucket

## Troubleshooting

### MLflow container won't start

Check logs:
```bash
docker logs mlflow-server
```

Common issues:
- Port 5001 in use: Change port in docker-compose.yml
- PostgreSQL not ready: Wait or restart stack

### Connection refused

Ensure MLflow stack is running:
```bash
docker ps | grep mlflow
```

### Sync script errors

Verify DATABASE_URL is set correctly:
```bash
echo $DATABASE_URL
```

## Related Files

- `scripts/mlflow_tracking.py` - QuantMLCommandCenter and ModelRegistry classes
- `scripts/sync_prisma_to_mlflow.py` - Prisma → MLflow sync script
- `docker/docker-compose.yml` - Docker stack definition
- `docker/Dockerfile.mlflow` - Custom MLflow image
- `scripts/start-mlflow.sh` - Startup script
