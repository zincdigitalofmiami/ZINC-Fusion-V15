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
- **Prisma Postgres**: Cloud-hosted authoritative database for all training and operations
- **Databento Integration**: Real-time and historical market data from CME Globex

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

**Prisma Postgres** is the authoritative database. Connection via `DATABASE_URL` in `.env`.

```bash
# Pull current schema
npx prisma db pull

# Generate client
npx prisma generate
```

Note: `data/fusion.db` (DuckDB) exists as a read-only archive for historical data extraction only.

## Data Pipeline

All data operations use Prisma Postgres. Key tables:
- `raw_market_futures` - ZL, ZS, ZM, CL futures OHLCV
- `raw_fred_observations` - Economic indicators
- `raw_weather_observations` - Weather data from key growing regions
- `driver_scores` - Normalized specialist driver scores
- `oof_predictions` - Out-of-fold predictions for stacking

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
├── prisma/
│   └── schema.prisma              # Prisma schema (authoritative)
├── scripts/
│   ├── train_*.py                 # Training scripts
│   └── ingest_*.py                # Data ingestion scripts
├── data/
│   └── fusion.db                  # DuckDB archive (read-only)
├── models/                        # Trained model artifacts
├── pyproject.toml                 # Python dependencies
└── README.md                      # This file
```

### Environment Variables

Required environment variables in `.env`:

```bash
# Database (REQUIRED)
DATABASE_URL="postgres://..."      # Prisma Postgres connection

# Market Data
DATABENTO_API_KEY="db-..."         # Databento API key

# Economic Data
FRED_API_KEY="your_fred_api_key"   # FRED API key
```

Load environment variables before running:

```bash
source .env
python -m uvicorn fusion.api.server:app --host 0.0.0.0 --port 8000
```

## Deployment

- **Database**: Prisma Postgres (cloud-hosted, no local setup required)
- **Backend**: FastAPI server connecting to Prisma
- **UI**: Optional Vercel deployment

### Adding Dependencies

```bash
uv pip install -e ".[dev]"
```

## Testing

Run tests using pytest:

```bash
pytest tests/ -v
```

## Documentation

- **Prisma Schema**: `prisma/schema.prisma` - Authoritative database schema
- **Agent Guide**: `AGENTS.md` - Operational rules for AI assistants
- **Prisma Docs**: [https://www.prisma.io/docs](https://www.prisma.io/docs)
- **Databento Docs**: [https://databento.com/docs](https://databento.com/docs)

## License

Proprietary - US Oil Solutions / ZINC Digital of Miami

## Contact

For questions or support, contact the ZINC Fusion development team.
