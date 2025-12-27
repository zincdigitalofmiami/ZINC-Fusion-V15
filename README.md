# ZINC Fusion V15 - Soybean Oil Procurement Forecasting

**Institutional-grade quantitative forecasting system for US Oil Solutions**

This project implements a multi-layer ensemble ML pipeline for predicting ZL (Soybean Oil) futures prices across multiple time horizons (1W, 1M, 3M, 6M), enabling strategic procurement decisions for bulk soybean oil purchasing.

## ✅ Latest Update (Dec 21, 2025): Weather Data Consolidation Complete

**Production-grade weather infrastructure with 20 years of historical data**

- **215,320 weather observations** from 57 stations across key soybean regions
- **5 regional schemas**: `weather.us_cornbelt`, `weather.brazil_cerrado`, `weather.brazil_south`, `weather.argentina_pampas`, `weather.argentina_north`
- **Enhanced variables**: Temperature (max/min/avg), precipitation (rain/snow), wind (speed/gusts), coordinates
- **Geographic coverage**: Iowa, Illinois, Indiana, Minnesota, Nebraska, Missouri, Brazil (MT/MS/MG/PR/RS/SP), Argentina (BA/CO/SF/ER/CH/FO/SE)

## Table of Contents

- [Introduction](#introduction)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Data Pipeline](#data-pipeline)
- [Model Training](#model-training)
- [Development](#development)
- [Testing](#testing)

## Introduction

**ZINC Fusion V15** is a 4-layer hierarchical ensemble forecasting system:

- **L0 Layer**: 9 base models (1 Core TimeSeriesPredictor + 8 Specialist TabularPredictors)
- **L1 Layer**: Meta-learner combining OOF predictions from L0 models
- **L2 Layer**: Ensemble fusion producing probabilistic forecasts (P10-P90)
- **L3 Layer**: Monte Carlo simulation for risk metrics (VaR, CVaR)

### Key Features

- **Big-10 Bucket Taxonomy**: Domain-specific specialists for Crush, China, FX, Fed, Tariff, Energy+Biofuel, Palm Oil, Volatility
- **DuckDB Storage**: Local SQL database for all data (raw, features, training, forecasts)

### Business Impact

- **Client**: US Oil Solutions (Las Vegas, NV)
- **Product**: Bulk soybean oil for restaurant/casino fryers
- **Proven Results**: $250K cost avoidance achieved through strategic timing
- **Decision Support**: WHEN to lock in futures, HOW MUCH to buy

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    L3: RISK LAYER                           │
│  Monte Carlo Simulation → VaR/CVaR → Procurement Signals   │
└─────────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────────┐
│              L2: ENSEMBLE LAYER (Production)                │
│    Weighted Fusion → Probabilistic Forecasts (P10-P90)     │
└─────────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────────┐
│           L1: META-LEARNER (Stacking Layer)                 │
│  TabularPredictor combining OOF predictions from L0 models  │
└─────────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────────┐
│              L0: BASE MODELS (9 Predictors)                 │
│  • 1 Core (TimeSeriesPredictor) - ZL price action          │
│  • 8 Specialists (TabularPredictor) - Big-10 Buckets        │
└─────────────────────────────────────────────────────────────┘
```

## Getting Started

### Prerequisites

- Python 3.10-3.14
- [uv](https://docs.astral.sh/uv/) package manager (recommended)

### Installation

```bash
# Clone the repository
git clone https://github.com/zincdigitalofmiami/ZINC-Fusion-V15.git
cd ZINC-Fusion-V15

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv pip install -e ".[dev]"
```

### Running the API

Start the FastAPI server:

```bash
python -m uvicorn fusion.api.server:app --host 0.0.0.0 --port 8000
```

### Database Setup

The DuckDB database is automatically created at `data/fusion.db` when you first materialize assets.

## Data Pipeline

Data lives in DuckDB at `data/fusion.db` and is accessed via the API.

## Model Training

### Training Workflow

The ZINC Fusion V15 training workflow follows a strict sequence:

1. **Canonical Features (Gold)**: Use `features.driver_scores_1d` as the canonical feature matrix.
2. **Train L0 Specialists (Per-Bucket)**:
    - Train each of the 10 specialist buckets with its own unique model family (independent pipelines).
    - Extract OOF predictions per bucket (before any refit_full).
    - Apply per‑bucket bagging to reduce variance.
3. **Join & Stack**: Horizontally stack all specialist OOF/bagged outputs.
4. **Train L1 Meta‑Learner**: Stacking model over specialist outputs.
5. **L2 Fusion**: Probabilistic fusion with uncertainty quantification (quantiles).
6. **L3 Risk**: Monte Carlo VaR/CVaR and risk metrics.

See [`QUANT_V15_Complete.ipynb`](./QUANT_V15_Complete.ipynb) for the complete training specification.

Canonical Feature Table
- The canonical features table is `features.driver_scores_1d` which provides normalized 0-100 scores for all 10 specialist drivers.
- Training tables follow the pattern `training.specialist_{bucket}_1d` where bucket is one of: crush, china, fx, fed, tariff, energy, biofuel, palm, volatility, substitutes.

## Scheduling

Scheduling/orchestration has been removed from this repository.

## Development

### Local Development Workflow

1. Make code changes in `src/fusion/`
2. Restart the API server
3. Commit changes to Git

### Project Structure

```
ZINC-Fusion-V15/
├── src/
│   └── fusion/
│       ├── api/                    # FastAPI service
├── data/
│   ├── fusion.db                  # DuckDB database (auto-created)
│   └── parquet/                   # Parquet cache (optional)
├── QUANT_V15_Complete.ipynb       # Complete system specification
├── pyproject.toml                 # Python dependencies
└── README.md                      # This file
```

### Environment Variables

API keys and credentials should be stored in environment variables:

```bash
# Create .env file (not committed to Git)
export FRED_API_KEY="your_fred_api_key"
export EIA_API_KEY="your_eia_api_key"
export EPA_API_KEY="your_epa_api_key"
# ... other API keys
```

Load environment variables before running the API:

```bash
source .env
python -m uvicorn fusion.api.server:app --host 0.0.0.0 --port 8000
```

## Deployment (No MotherDuck)

This repo supports a split deployment:

- **UI**: deploy `client/` to Vercel (repo root has `vercel.json` to build `client/`).
- **Backend**: run FastAPI on a host with persistent storage (DuckDB is a local file).

### Backend (Docker Compose)

- Start services: `docker compose up -d --build`
- FastAPI base URL: `http://<host>:8000` (or `http://<host>:8080/api/...` if you use the Nginx proxy)

Environment variables to set on the host:
- `FUSION_DB_PATH` (default in containers: `/app/data/fusion.db`)
- `FUSION_CORS_ORIGINS` (comma-separated; include your Vercel domain, e.g. `https://<your-app>.vercel.app`)

### UI (Vercel)

Set `FUSION_API_BASE` in Vercel Environment Variables to your FastAPI base URL (e.g. `https://api.yourdomain.com`).

### Adding Dependencies

Dependency management is repo-specific; see existing project config.

## Testing

Run tests using pytest:

```bash
pytest tests/ -v
```

## Documentation

- **System Specification**: [`QUANT_V15_Complete.ipynb`](./QUANT_V15_Complete.ipynb) - Complete DDL and implementation guide
- **DuckDB Docs**: [https://duckdb.org](https://duckdb.org)

## License

Proprietary - US Oil Solutions / ZINC Digital of Miami

## Contact

For questions or support, contact the ZINC Fusion development team.
