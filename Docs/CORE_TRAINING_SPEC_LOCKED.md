NOTE: Production is the dashboard/frontend, not the repo root.
# ZINC-FUSION-V15: CORE TRAINING SPECIFICATION (LOCKED)

**Version:** 1.0
**Date:** January 9, 2026
**Status:** LOCKED - DO NOT MODIFY WITHOUT FULL REVIEW

> NOTE (2026-01-17): Schema v2 replaces raw/gold/silver with mkt/econ/features.
> Table names in this doc are legacy until migration completes.

---

## 🎯 PURPOSE

This document is the SINGLE SOURCE OF TRUTH for Core model training.
It combines verified model limits from `CORE_ARCHITECTURE_V3_FIXED.md` with
the ALL DATA policy and Light Train configuration.

**Any training script MUST implement exactly what's specified here.**

---

## � DATA SOURCES (LOCKED)

### Source Architecture
| Source | Role | Window | Status |
|--------|------|--------|--------|
| **Historical Backfill** | Market OHLCV (1990 → 2025-12-29) | One-time | ✅ COMPLETE, LOCKED |
| **Yahoo Finance** | Daily topfill (2025-12-30 → future) | Daily | ✅ Active |
| **FRED API** | Macro indicators | Daily/Weekly/Monthly | ✅ Active |

**Historical backfill is COMPLETE.** No additional historical data sources are planned or required.

### Ingestion Scripts
- **Yahoo topfill:** `scripts/ingest_yahoo_eod.py` (runs daily)
- **FRED update:** `scripts/ingest_fred_observations.py` (runs daily)

---

## Core Training Policy (CPU-only, Full Model Zoo)

Core runs **CPU-only** and must explicitly try **ALL** AutoGluon-TimeSeries Model Zoo models.
This is a single Core pipeline for all horizons; specialists are unchanged.

### Environment guards (Mac stability)
Set **before** importing torch/autogluon:

```
TOKENIZERS_PARALLELISM=false
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
AUTOGLUON_DISABLE_RAY=1
PYTORCH_ENABLE_MPS_FALLBACK=1
PYTORCH_MPS_ENABLED=0
CUDA_VISIBLE_DEVICES=""
device = "cpu"
```

### Which models are tried (Model Zoo allowlist)
Core must use an **explicit** `hyperparameters={...}` allowlist containing every Model Zoo name.
Per AutoGluon docs, the “Model” suffix can be omitted.

- **Baselines:** Naive, SeasonalNaive, Average, SeasonalAverage, Zero  
- **Statistical:** ETS, AutoETS, AutoARIMA, AutoCES, Theta, NPTS, ADIDA, Croston, IMAPA  
- **Deep/ML:** DeepAR, TemporalFusionTransformer, DLinear, PatchTST, SimpleFeedForward  
- **Neural:** TiDE, WaveNet  
- **Tabular TS:** DirectTabular, PerStepTabular, RecursiveTabular  
- **Pretrained:** Chronos2, Chronos, Toto  

If the installed AutoGluon version exposes additional Model Zoo entries, include them too.

### How AutoGluon selects the final model
AutoGluon trains the full allowlist, evaluates on validation/backtests, and
typically chooses a **WeightedEnsemble** as the best model. This matches the
Quick Start behavior (e.g., models trained include SeasonalNaive, DirectTabular,
RecursiveTabular, ETS, Theta, Chronos2, and a WeightedEnsemble).

### Presets vs explicit allowlist
Presets (e.g., `best_quality`, `chronos2_*`) are convenient, but **do not**
guarantee “ALL models.” Absolute certainty requires the explicit allowlist.

### Time limits
No time limits are used; Core is allowed to run as long as needed.

### Specialists
Specialists are **unchanged** by Core CPU-only policy.

---

## 📦 ALL DATA POLICY (MANDATORY)

### Required Data Sources

Every Core training run MUST load ALL of these sources:

| Source | Table | Min Rows | Features |
|--------|-------|----------|----------|
| Market Futures | `mkt.futures_1d` | 100,000 | 103 symbols × 5 OHLCV = 515 |
| FRED Economic | `econ.rates_1d` | 100,000 | 159 series |
| Weather NOAA | `alt.weather_1d` | 500 | 57 stations × 10 vars |
| FX Spot | `mkt.fx_1d` | 10,000 | 9 pairs |
| CFTC COT | `pos.cftc_1w` | 500 | 24 symbols × 5 metrics |
| USDA Exports | `supply.usda_export_sales_1w` | 100 | 5 features |
| USDA WASDE | `supply.usda_wasde_1m` | 50 | 5 features |
| EPA RIN | `supply.epa_rin_1d` | 50 | 4 types |
| News Sentiment | `alt.news_1d` | 50 | 5+ features |

### Feature Minimums
```python
ALL_DATA_POLICY = {
    "min_total_features": 600,
    "min_symbol_features": 400,    # 103 symbols × OHLCV wide
    "min_fred_features": 100,
    "min_fx_features": 25,
    "min_cot_features": 15,
    "min_weather_features": 5,
    "min_rin_features": 3,
    "min_news_features": 3,
    "min_usda_features": 3,
    "min_wasde_features": 3,
}
```

### Validation Gate
```python
from src.fusion.validation.all_data_policy import enforce_all_data_policy

# MUST pass before training starts
enforce_all_data_policy(conn, horizon=horizon, strict=True)
```

---

## 🧮 FEATURE ENGINEERING

### Elite Technical Indicators (27)

From `src/fusion/features/elite_indicators.py`:

**Tier 1 - Institutional Gems:**
- Hurst Exponent
- Connors RSI (3,2,100)
- Ehlers Fisher Transform
- McGinley Dynamic
- TTM Squeeze
- Schaff Trend Cycle
- Relative Vigor Index
- Elder Force Index

**Tier 2 - Optimized Staples:**
- KAMA, HMA, ALMA (horizon-matched)
- RSI(2), RSI(14), Cumulative RSI
- MACD, MACD Signal, MACD Histogram
- CCI(14), CCI(50)

**Tier 3 - Volatility Regime:**
- ATR Ratio, Garman-Klass, Yang-Zhang, BB %B

**Tier 4 - Volume/Flow:**
- CMF, Volume Z-Score, Elder Force Index

### Volatility Proxy Features (7 key symbols)

For ZL, ZS, ZM, CL, CPO, ES, GC:
```python
volatility_features = [
    "daily_range",        # high - low
    "daily_range_pct",    # (high - low) / close
    "overnight_gap",      # open(t) - close(t-1)
    "overnight_gap_pct",  # gap / close(t-1)
    "close_location",     # (close - low) / (high - low)
    "body_ratio",         # |close - open| / (high - low)
]
```

### Calendar Event Features
```python
calendar_features = [
    "day_of_week",
    "month",
    "quarter",
    "day_of_month",
    "is_wasde_week",      # 7th-14th of month
    "is_fomc_week",       # 3rd week of FOMC months
    "is_expiry_week",     # 3rd week of month
    "is_month_end",
    "is_quarter_end",
]
```

---

## 🔀 DATA MERGE STRATEGY

### Frequency Alignment
```python
# Base: Daily market futures
# All other sources merged via merge_asof(direction='backward')

MERGE_STRATEGY = {
    "daily": ["market_futures", "fred_daily", "fx_spot", "rin_prices", "weather", "news"],
    "weekly": ["cftc_cot", "usda_export_sales"],  # merge_asof backward
    "monthly": ["usda_wasde"],                     # merge_asof backward
}
```

### NaN Handling
```python
# 1. Forward-fill gaps within series
# 2. Backward-fill leading NaNs
# 3. ZERO NaN values in final dataset (enforced)

df = df.ffill().bfill()
assert df.isna().sum().sum() == 0, "NaN values found in final dataset"
```

---

## 📁 OUTPUT STRUCTURE

### Model Artifacts
```
models/core_v2/
├── horizon_5d/
├── horizon_21d/
├── horizon_63d/
└── horizon_126d/
```

### Database Outputs
```sql
-- OOF predictions written to:
INSERT INTO training.oof_core_1d (
    trade_date,
    symbol,
    horizon_days,
    window_id,
    cutoff_date,
    p30,
    p50,
    p70,
    target_value,
    trained_at,
    run_hash,
    matrix_version
)
```

---

## ⏱️ TRAINING TIME ESTIMATES

### CPU-only, no time limit

Training time is **unbounded** and depends on dataset size and the full Model Zoo.
Expect multi-hour runs on CPU.

---

## ✅ PRE-FLIGHT CHECKLIST

Before running training:

### Data Validation
- [ ] `enforce_all_data_policy()` passes
- [ ] 600+ features loaded
- [ ] Zero NaN values
- [ ] Date range covers required window
### Environment Guards
- [ ] `TOKENIZERS_PARALLELISM=false`
- [ ] `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`
- [ ] `AUTOGLUON_DISABLE_RAY=1`
- [ ] `PYTORCH_ENABLE_MPS_FALLBACK=1`
- [ ] `PYTORCH_MPS_ENABLED=0`
- [ ] `CUDA_VISIBLE_DEVICES=""`
- [ ] `device="cpu"`

### Model Zoo Allowlist
- [ ] Explicit `hyperparameters={...}` includes **all** Model Zoo models

---

## Verification checklist (log evidence)

- Run: `python -m fusion.core_training.run_pipeline --skip-matrix --horizons 5`
- Confirm logs list **all models** from the allowlist.
- Confirm a **WeightedEnsemble** is selected as best model.
- Confirm CPU-only execution.

---

## Docs drift vs code

As of 2026-01-24, this spec is aligned with `fusion.core_training`:
- Explicit full Model Zoo allowlist (no presets, no time limits)
- CPU-only environment guards

### Configuration Validation
- [ ] `device="cpu"` only
- [ ] No presets used; explicit allowlist only
- [ ] No time limits
- [ ] Quantile outputs remain p30/p50/p70

### Environment Validation
- [ ] `TOKENIZERS_PARALLELISM=false` set
- [ ] `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` set
- [ ] `AUTOGLUON_DISABLE_RAY=1` set
- [ ] `PYTORCH_ENABLE_MPS_FALLBACK=1` set
- [ ] `PYTORCH_MPS_ENABLED=0` set
- [ ] `CUDA_VISIBLE_DEVICES=""` set
- [ ] Sufficient disk space for full Model Zoo

---

## 🚨 COMMON FAILURES & FIXES

| Failure | Cause | Fix |
|---------|-------|-----|
| Model key error | Model not in installed AutoGluon | Remove or update allowlist entry |
| Missing models in logs | Allowlist incomplete | Add missing Model Zoo entries |
| Ray/GCS errors | Ray enabled on macOS | Set `AUTOGLUON_DISABLE_RAY=1` |
| CPU stalls / long runtime | Full Model Zoo + no time limit | Expect multi-hour run; monitor resources |

---

## 📋 TRAINING COMMAND

```bash
# Single horizon (smoke test)
python -m fusion.core_training.run_pipeline --skip-matrix --horizons 5

# All horizons (production)
python -m fusion.core_training.run_pipeline --skip-matrix
```

---

## 🔒 LOCKED CONFIGURATION

**This specification is LOCKED as of January 9, 2026.**

Any changes require:
1. Full review of impact
2. Smoke test on single horizon
3. Update to this document
4. Commit with clear changelog

---

*Specification by Claude | ZINC Digital of Miami*
*For Kirk, Architect | January 9, 2026*
*Based on verified limits from CORE_ARCHITECTURE_V3_FIXED.md*