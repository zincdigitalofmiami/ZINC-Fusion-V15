# Naming Contracts

Authoritative naming conventions for ZINC-Fusion-V15. Violation = restart.

## Project Identity

| Attribute | Canonical Value |
|-----------|-----------------|
| Project name | ZINC-Fusion-V15 |
| Repository | github.com/zincdigitalofmiami/ZINC-Fusion-V15 |
| Local path | /Volumes/Satechi Hub/ZINC-FUSION-V15 |
| Database file | fusion.db |
| Database path | /Volumes/Satechi Hub/ZINC-FUSION-V15/data/fusion.db |

## Forbidden Aliases

Never use these—they indicate drift from legacy versions:

| Forbidden | Why |
|-----------|-----|
| CBI-V15 | Legacy project codename |
| CBI | Ambiguous abbreviation |
| zinc_fusion | Underscore variant |
| zinc_fusion_v15.db | Old database name |
| Big-10, Big-8 | Legacy bucket terminology |
| buckets | Ambiguous—use "Specialists" |

## Python Import Conventions

```python
# Correct
from fusion.taxonomy import SPECIALISTS
from fusion.config import HORIZONS
from fusion.autogluon_config import SPECIALIST_CONFIG, get_specialist_fit_kwargs

# Incorrect
from zinc_fusion.taxonomy import ...  # wrong module name
from cbi.config import ...            # legacy name
```

## Dagster Package

The Dagster package is intentionally named `quickstart_etl` (scaffold remnant). This is correct:

```python
# Correct
from quickstart_etl.definitions import defs

# Assets live in
src/quickstart_etl/defs/
```

## Model Terminology

| Term | Use For |
|------|---------|
| Specialists | The 10 TabularPredictor domain models |
| Core | The single TimeSeriesPredictor for ZL |
| L0 | Base layer (Core + 10 Specialists = 11 models) |
| OOF | Out-of-fold predictions from L0 |

Never say "Big-10 buckets" or "specialist buckets"—just "Specialists."

## Table Naming Pattern

```
{schema}.{entity}_{grain}

Grains (ONLY these two exist):
  _1h  → hourly (ts_event PK)
  _1d  → daily (as_of_date PK)

Examples:
raw.market_futures_1h          -- Hourly OHLCV
raw.market_futures_1d          -- Daily OHLCV
training.oof_core_1d           -- Daily OOF (no hourly OOF)
training.oof_crush_1d
features.intraday_volatility   -- Derived from 1h, stored as 1d aggregates
gold.forecasts_ensemble_1d
```

## Column Naming

| Column | Type | Used In | Notes |
|--------|------|---------|-------|
| `as_of_date` | DATE | `_1d` tables | Never TIMESTAMP for daily grain |
| `ts_event` | TIMESTAMP | `_1h` tables | Hourly grain primary key |
| `horizon_steps` | INTEGER | OOF/forecasts | Trading days: 5, 21, 63, 126 |
| `p10, p50, p90` | DOUBLE | OOF/forecasts | Quantile outputs |
| `run_id` | VARCHAR | Training | MLflow run reference (optional) |
| `symbol` | VARCHAR | Market data | Ticker symbol when needed |

## AutoGluon Config Authority

| File | Status | What It Controls |
|------|--------|------------------|
| `src/fusion/autogluon_config.py` | **CANONICAL** | Presets, bagging, time limits |
| `src/fusion/defs/autogluon_training_assets.py` | Dev override | Has `medium_quality` - gate with `FUSION_DEV_MODE` |
