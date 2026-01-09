# ZINC-FUSION-V15: CORE TRAINING SPECIFICATION
## LOCKED - January 9, 2026
## Do Not Modify Without Architect Approval

---

## 🎯 PURPOSE

This document is the **single source of truth** for Core model training configuration.
It combines verified model limits, data requirements, and training settings that have been
tested to run successfully on Mac M4 Pro without mid-train crashes.

---

## 🖥️ HARDWARE CONSTRAINTS (Mac M4 Pro)

| Constraint | Value | Notes |
|------------|-------|-------|
| RAM | 16GB | Shared with system |
| GPU | MPS | **NOT SUPPORTED by Chronos-2** |
| Device | `"cpu"` | Explicit - don't rely on auto-detect |
| Parallelism | Limited | One horizon at a time recommended |

**CRITICAL**: Chronos-2 only checks for CUDA, falls back to CPU. MPS is never used.

---

## 📊 HORIZON STRATEGY

### Tactical vs Strategic Split

| Horizon | Mode | Data Window | Model | RecursiveTabular |
|---------|------|-------------|-------|------------------|
| **5d** | Tactical | 2020-01-01+ (5yr) | Chronos-Bolt-Small | ✅ INCLUDE |
| **21d** | Tactical | 2020-01-01+ (5yr) | Chronos-Bolt-Small | ✅ INCLUDE |
| **63d** | Strategic | 2000-01-01+ (25yr) | Chronos-2 (LoRA) | ❌ EXCLUDE |
| **126d** | Strategic | 2000-01-01+ (25yr) | Chronos-2 (LoRA) | ❌ EXCLUDE |

**Rationale**: 
- RecursiveTabular causes error propagation at longer horizons
- Tactical needs speed (Chronos-Bolt), Strategic needs depth (Chronos-2)

---

## ⚙️ MODEL CONFIGURATIONS (VERIFIED SAFE)

### Tactical Horizons (5d, 21d) - Chronos-Bolt

```python
CONFIG_TACTICAL = {
    "Chronos": {
        "model_path": "autogluon/chronos-bolt-small",
        # No fine-tuning for Chronos-Bolt
    },
    "DirectTabular": {},
    "RecursiveTabular": {},  # INCLUDED for tactical
    "AutoETS": {},
    "Theta": {},
    "SeasonalNaive": {},
}
```

### Strategic 63d - Chronos-2 (Light Fine-tune)

```python
CONFIG_63D = {
    "Chronos2": {
        # Model - use default (no model_path needed)
        "context_length": 1024,
        "batch_size": 16,
        "device": "cpu",  # EXPLICIT - MPS not supported
        
        # Fine-tuning
        "fine_tune": True,
        "fine_tune_mode": "lora",
        "fine_tune_lr": 5e-5,
        "fine_tune_steps": 300,           # Light
        "fine_tune_batch_size": 4,        # SEPARATE from inference batch_size
        "fine_tune_context_length": 512,
        "fine_tune_lora_config": {
            "r": 4,
            "lora_alpha": 8,
        },
    },
    "DirectTabular": {},
    # NO RecursiveTabular
    "AutoETS": {},
    "Theta": {},
    "SeasonalNaive": {},
}
```

### Strategic 126d - Chronos-2 (Fuller Fine-tune)

```python
CONFIG_126D = {
    "Chronos2": {
        "context_length": 2048,           # More context for strategic
        "batch_size": 8,                  # Smaller for memory
        "device": "cpu",
        
        "fine_tune": True,
        "fine_tune_mode": "lora",
        "fine_tune_lr": 5e-5,
        "fine_tune_steps": 500,
        "fine_tune_batch_size": 2,        # Very small for 126d
        "fine_tune_context_length": 1024,
        "fine_tune_lora_config": {
            "r": 8,
            "lora_alpha": 16,
        },
    },
    "DirectTabular": {},
    # NO RecursiveTabular
    "AutoETS": {},
    "Theta": {},
    "SeasonalNaive": {},
}
```

---

## 📈 TRAINING SETTINGS (LIGHT TRAIN)

### AutoGluon TimeSeriesPredictor Settings

| Parameter | Value | Notes |
|-----------|-------|-------|
| `eval_metric` | `"WQL"` | Weighted Quantile Loss |
| `quantile_levels` | `[0.10, 0.50, 0.90]` | P10/P50/P90 |
| `freq` | `"B"` | Business daily |
| `presets` | `"medium_quality"` | Was "best_quality" - lighter |
| `time_limit` | `3600` | 1 hour (was 14400 = 4hr) |
| `num_val_windows` | `4` | Was 8 - lighter |

### Full Predictor Initialization

```python
from autogluon.timeseries import TimeSeriesPredictor

predictor = TimeSeriesPredictor(
    prediction_length=horizon,
    target="target",
    freq="B",  # Business daily
    eval_metric="WQL",
    quantile_levels=[0.10, 0.50, 0.90],
    path=f"models/core_chronos2/horizon_{horizon}d/{mode}/",
)

predictor.fit(
    train_data=ts_data,
    presets="medium_quality",
    time_limit=3600,
    num_val_windows=4,
    hyperparameters=CONFIG_FOR_HORIZON,
)
```

---

## 📦 DATA REQUIREMENTS (ALL DATA POLICY)

### Required Sources (ALL must be loaded)

| Source | Table | Rows Required | Columns |
|--------|-------|---------------|---------|
| Market Futures | `raw.market_futures_1d` | 100,000+ | ALL 103 symbols pivoted wide |
| FRED Economic | `raw.fred_observations_1d` | 100,000+ | ALL 159 series |
| Weather | `raw.weather_noaa_1d` | 500+ | 57 stations × 10 vars |
| FX Spot | `raw.fx_spot_1d` | 10,000+ | 9 Yahoo pairs |
| CFTC COT | `raw.cftc_cot_1w` | 500+ | ALL 24 symbols |
| USDA Exports | `raw.usda_export_sales_1w` | 100+ | 3 commodities |
| USDA WASDE | `raw.usda_wasde_1m` | 50+ | 3 commodities |
| EPA RIN | `raw.epa_rin_prices_1d` | 50+ | 4 RIN types |
| News Sentiment | `raw.news_articles_1d` | 50+ | With computed sentiment |

### Feature Requirements

| Category | Minimum Features | Source |
|----------|------------------|--------|
| Symbol features | 400+ | Market futures pivoted wide |
| FRED features | 100+ | Economic indicators |
| FX features | 25+ | Currency rates |
| COT features | 15+ | Positioning data |
| Weather features | 5+ | NOAA stations |
| RIN features | 3+ | EPA RIN prices |
| News features | 3+ | Sentiment aggregates |
| USDA features | 3+ | Export sales |
| WASDE features | 3+ | Supply/demand |
| **TOTAL** | **600+** | Combined |

### Elite Technical Indicators (27)

From `src/fusion/features/elite_indicators.py`:

**Tier 1 - Institutional Gems:**
- Hurst Exponent, Connors RSI, Ehlers Fisher Transform
- McGinley Dynamic, TTM Squeeze, Schaff Trend Cycle
- Relative Vigor Index, Elder Force Index

**Tier 2 - Optimized Staples:**
- KAMA, HMA, ALMA (horizon-matched MAs)
- RSI(2), RSI(14), Cumulative RSI
- MACD, MACD Signal, MACD Histogram
- CCI(14), CCI(50)

**Tier 3 - Volatility Regime:**
- ATR Ratio, Garman-Klass, Yang-Zhang, BB %B

**Tier 4 - Volume/Flow:**
- CMF, Volume Z-Score

### Calendar Event Features

```python
# REQUIRED calendar features
CALENDAR_FEATURES = [
    "day_of_week",      # 0-4 (Mon-Fri)
    "month",            # 1-12
    "quarter",          # 1-4
    "day_of_month",     # 1-31
    "is_wasde_week",    # WASDE release (7th-14th)
    "is_fomc_week",     # Fed meeting weeks
    "is_expiry_week",   # Futures expiry (3rd week)
    "is_month_end",     # Last business day
    "is_quarter_end",   # Last day of quarter
]
```

---

## 🔄 DATA MERGE STRATEGY

### Frequency Handling

| Source | Frequency | Merge Method |
|--------|-----------|--------------|
| Market futures | Daily | Base table |
| FRED (Daily) | Daily | Direct join |
| FRED (Weekly) | Weekly | `merge_asof(direction='backward')` |
| FRED (Monthly) | Monthly | `merge_asof(direction='backward')` |
| FRED (Quarterly) | Quarterly | `merge_asof(direction='backward')` |
| CFTC COT | Weekly | `merge_asof(direction='backward')` |
| USDA Exports | Weekly | `merge_asof(direction='backward')` |
| USDA WASDE | Monthly | `merge_asof(direction='backward')` |
| Weather | Daily | Forward-fill + backward-fill |
| RIN | Daily | Forward-fill + backward-fill |
| News | Daily | Aggregate by date (mean/sum/std) |

### NaN Handling

1. Apply `merge_asof` for lower-frequency data
2. Apply `ffill()` then `bfill()` for remaining NaNs
3. **VALIDATE**: Final dataset must have ZERO NaNs
4. If NaNs remain, fail loudly - don't train on garbage

---

## 📁 OUTPUT STRUCTURE

### Model Artifacts

```
models/core_chronos2/
├── horizon_5d/
│   └── tactical/           # Chronos-Bolt
│       ├── predictor.pkl
│       ├── learner.pkl
│       └── models/
├── horizon_21d/
│   └── tactical/           # Chronos-Bolt
├── horizon_63d/
│   └── strategic/          # Chronos-2
├── horizon_126d/
│   └── strategic/          # Chronos-2
```

### Database Output

OOF predictions written to `model.oof_predictions`:

```sql
(specialist, horizon, as_of_date, symbol, pred_p10, pred_p50, pred_p90, actual, fold_id, created_at)
```

Where `specialist = 'core'` for Core model predictions.

---

## ⏱️ ESTIMATED TRAINING TIMES (Mac M4 Pro)

| Horizon | Mode | Fine-tune | Estimated Time |
|---------|------|-----------|----------------|
| 5d | Tactical | No | ~15 min |
| 21d | Tactical | No | ~20 min |
| 63d | Strategic | 300 steps | ~45 min |
| 126d | Strategic | 500 steps | ~90 min |
| **Total** | | | **~3 hours** |

*Note: Times assume LIGHT TRAIN settings (4 val windows, 3600s limit)*

---

## ✅ PRE-FLIGHT CHECKLIST

Before training, verify:

### Model Config
- [ ] `device="cpu"` is explicit (MPS NOT supported)
- [ ] No `optimization_strategy` parameter (invalid for Chronos-2)
- [ ] `fine_tune_batch_size` is set (separate from `batch_size`)
- [ ] Tactical uses Chronos-Bolt, Strategic uses Chronos-2
- [ ] RecursiveTabular INCLUDED for tactical, EXCLUDED for strategic

### Data Loading
- [ ] ALL 103 market symbols loaded and pivoted wide
- [ ] ALL 159 FRED series loaded
- [ ] Weather, COT, WASDE, RIN, News all loaded
- [ ] Elite indicators computed (27 features)
- [ ] Calendar event features added
- [ ] Final feature count ≥ 600
- [ ] Final NaN count = 0

### Training Settings
- [ ] `num_val_windows = 4` (not 8)
- [ ] `time_limit = 3600` (not 14400)
- [ ] `presets = "medium_quality"` (not best_quality)
- [ ] `quantile_levels = [0.10, 0.50, 0.90]`

### Output
- [ ] Model path uses correct tactical/strategic subfolder
- [ ] OOF predictions will write to `model.oof_predictions`
- [ ] MLflow tracking enabled

---

## 🚫 KNOWN ISSUES TO AVOID

| Issue | Symptom | Prevention |
|-------|---------|------------|
| MPS fallback | Slow training, wrong device | Explicit `device="cpu"` |
| OOM crash | Training dies mid-run | Use verified batch sizes |
| Wrong model | Chronos-Bolt vs Chronos-2 | Check horizon → model mapping |
| Thin data | Bad predictions | Enforce ALL DATA POLICY |
| NaN explosion | Model fails | Validate zero NaNs before fit |
| RecursiveTabular at 126d | Error propagation | Exclude for strategic |

---

## 📜 CHANGE LOG

| Date | Change | Author |
|------|--------|--------|
| 2026-01-09 | Initial locked spec from V3_FIXED + LIGHT_TRAIN | Kirk/Claude |

---

*This document is LOCKED. Any changes require architect approval and must be documented in the change log.*
