# ZINC Fusion V15 - Soybean Oil Procurement Forecasting

**Institutional-grade quantitative forecasting system for US Oil Solutions**

This project implements a multi-layer ensemble ML pipeline for predicting ZL (Soybean Oil) futures prices across multiple time horizons (1W, 1M, 3M, 6M), enabling strategic procurement decisions for bulk soybean oil purchasing.

_New to Dagster? Learn what Dagster is [in Concepts](https://docs.dagster.io/concepts) or [in the hands-on Tutorials](https://docs.dagster.io/tutorial)._

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

- **Big-8 Bucket Taxonomy**: Domain-specific specialists for Crush, China, FX, Fed, Tariff, Energy+Biofuel, Palm Oil, Volatility
- **AutoGluon 1.4**: State-of-the-art ML framework with Mitra, TabPFNv2, TabICL models
- **DuckDB Storage**: Local SQL database for all data (raw, features, training, forecasts)
- **Dagster Orchestration**: Daily data ingestion from 10+ APIs (FRED, EIA, EPA, USDA, CFTC, Yahoo Finance)
- **MLflow Tracking**: Experiment tracking and model registry

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
│  • 8 Specialists (TabularPredictor) - Big-8 Buckets        │
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

### Running Dagster

Start the Dagster UI web server:

```bash
dagster dev
```

Open http://localhost:3000 with your browser to see the project.

### Database Setup

The DuckDB database is automatically created at `data/zinc_fusion_v15.db` when you first materialize assets.

## Data Pipeline

### Available Assets

The ZINC Fusion V15 pipeline includes the following Dagster assets in the `zinc_fusion_schema` group:

| Asset | Description |
|-------|-------------|
| `create_schemas` | Creates 6 DuckDB schemas (raw, features, training, forecasts, monitoring, metadata) |
| `create_raw_tables` | Creates raw data tables for market, economic, agricultural, weather, trade, sentiment data |
| `create_feature_tables` | Creates Big-8 bucket feature tables (daily-aligned) |
| `create_training_tables` | Creates training matrices for Core + 8 Specialists |
| `create_forecast_tables` | Creates forecast output tables (L0→L1→L2→L3) |

All assets are defined in [`src/quickstart_etl/defs/zinc_fusion_assets.py`](./src/quickstart_etl/defs/zinc_fusion_assets.py).

### Materializing Assets

1. Navigate to http://localhost:3000 in your browser
2. Click on the **Assets** tab in the left navigation
3. Select the `zinc_fusion_schema` asset group
4. Click **Materialize all** to create the database schema

This will create the complete DuckDB database structure with all 50+ tables ready for data ingestion.

### Asset Organization

- **Grouping**: All assets are grouped under `zinc_fusion_schema` for easy navigation
- **Compute Kind**: Each asset is labeled with `DuckDB` to indicate the storage backend
- **Dependencies**: Assets have clear upstream/downstream relationships (schemas → raw tables → feature tables → training tables → forecast tables)

## Model Training

### Training Workflow

The ZINC Fusion V15 training workflow follows a strict sequence:

1. **Prepare Training Data**: Load features from DuckDB into training matrices
2. **Train L0 Models**:
   - Train 8 Specialist TabularPredictors (one per Big-8 bucket)
   - Train 1 Core TimeSeriesPredictor
   - Extract OOF predictions **before** `refit_full`
3. **Build Meta-Ensemble**: Join all OOF predictions into meta-ensemble tables
4. **Train L1 Meta-Learner**: Train on combined OOF predictions
5. **Production Inference**: Generate daily forecasts (L0 → L1 → L2 → L3)

### AutoGluon Configuration

```python
# L0 Specialist (TabularPredictor)
from autogluon.tabular import TabularPredictor

predictor = TabularPredictor(
    label='target_return_Xd',
    problem_type='quantile',
    eval_metric='pinball_loss',
    quantile_levels=[0.1, 0.5, 0.9],
).fit(
    train_data=bucket_df,
    presets='extreme_quality',  # Mitra, TabPFNv2, TabICL
    time_limit=7200,  # 2 hours per bucket
)

# Extract OOF predictions
oof_preds = predictor.predict_proba_oof()
```

See [`QUANT_V15_Complete.ipynb`](./QUANT_V15_Complete.ipynb) for the complete training specification.

## Scheduling

### Daily Data Refresh

The project includes a daily schedule (`daily_refresh_schedule`) defined in [`src/quickstart_etl/definitions.py`](./src/quickstart_etl/definitions.py) that runs at 6:00 AM EST to:

1. Ingest fresh data from all APIs (FRED, EIA, EPA, USDA, CFTC, Yahoo Finance)
2. Update feature tables with latest market data
3. Generate new forecasts for all time horizons (1W, 1M, 3M, 6M)

### Enabling the Schedule

1. Navigate to the **Schedules** tab in the Dagster UI
2. Find `daily_refresh_schedule`
3. Toggle the switch to **ON**

The schedule will now run automatically every day at 6:00 AM EST.

## Development

### Local Development Workflow

1. Make code changes in `src/quickstart_etl/`
2. Click **Reload definitions** in the Dagster UI (top-right corner)
3. Test changes by materializing affected assets
4. Commit changes to Git

### Project Structure

```
ZINC-Fusion-V15/
├── src/
│   └── quickstart_etl/
│       ├── definitions.py          # Dagster definitions, schedules
│       └── defs/
│           ├── zinc_fusion_assets.py  # Schema creation assets
│           └── assets.py           # (Legacy HackerNews example)
├── data/
│   ├── zinc_fusion_v15.db         # DuckDB database (auto-created)
│   └── parquet/                   # Parquet cache (optional)
├── models/
│   └── autogluon/                 # Trained model artifacts
├── mlruns/                        # MLflow experiment tracking
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

Load environment variables before running Dagster:

```bash
source .env
dagster dev
```

See [Using environment variables and secrets](https://docs.dagster.io/guides/dagster/using-environment-variables-and-secrets) for more info.

### Adding Dependencies

Add new Python dependencies to `pyproject.toml`:

```toml
[project]
dependencies = [
    "dagster",
    "duckdb>=0.9.0",
    "pandas",
    "your-new-package",
]
```

Then reinstall:

```bash
uv pip install -e ".[dev]"
```

## Testing

Run tests using pytest:

```bash
pytest tests/ -v
```

Run Dagster definition validation:

```bash
dagster definitions validate -m quickstart_etl.definitions
```

## Documentation

- **System Specification**: [`QUANT_V15_Complete.ipynb`](./QUANT_V15_Complete.ipynb) - Complete DDL and implementation guide
- **Dagster Docs**: [https://docs.dagster.io](https://docs.dagster.io)
- **AutoGluon Docs**: [https://auto.gluon.ai](https://auto.gluon.ai)
- **DuckDB Docs**: [https://duckdb.org](https://duckdb.org)

## License

Proprietary - US Oil Solutions / ZINC Digital of Miami

## Contact

For questions or support, contact the ZINC Fusion development team.
