# ZINC-FUSION-V15: CORE TRAINING SPECIFICATION (LOCKED)

**Version:** 1.0
**Date:** January 9, 2026
**Status:** LOCKED - DO NOT MODIFY WITHOUT FULL REVIEW

---

## 🎯 PURPOSE

This document is the SINGLE SOURCE OF TRUTH for Core model training.
It combines verified model limits from `CORE_ARCHITECTURE_V3_FIXED.md` with
the ALL DATA policy and Light Train configuration.

**Any training script MUST implement exactly what's specified here.**

---

## 📊 HORIZON STRATEGY

### Tactical vs Strategic Split

| Horizon | Mode | Data Window | Primary Model | RecursiveTabular |
|---------|------|-------------|---------------|------------------|
| **5d** | Tactical | 2020-01-01+ (5 years) | Chronos-Bolt-Small | ✅ INCLUDED |
| **21d** | Tactical | 2020-01-01+ (5 years) | Chronos-Bolt-Small | ✅ INCLUDED |
| **63d** | Strategic | 2000-01-01+ (25 years) | Chronos-2 (LoRA) | ❌ EXCLUDED |
| **126d** | Strategic | 2000-01-01+ (25 years) | Chronos-2 (LoRA) | ❌ EXCLUDED |

### Rationale
- **Tactical (5d/21d)**: Short-term operational forecasts. Chronos-Bolt is faster, 
  RecursiveTabular helps with autoregressive patterns over short horizons.
- **Strategic (63d/126d)**: Long-term procurement planning. Chronos-2 with LoRA 
  fine-tuning captures complex patterns. RecursiveTabular EXCLUDED to prevent 
  error propagation over long horizons.

---

## 🖥️ HARDWARE CONFIGURATION (Mac M4 Pro)

### Critical Constraints
```python
# MPS is NOT supported for Chronos-2
# Code only checks CUDA, falls back to CPU
device = "cpu"  # MUST be explicit

# Memory-safe settings for 16GB RAM
# Reduce batch sizes and context lengths from defaults
```

### Environment Variables
```python
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
os.environ["AUTOGLUON_DISABLE_RAY"] = "1"  # Prevents Ray/GCS failures on macOS
```

---

## 🔧 MODEL CONFIGURATIONS (VERIFIED SAFE)

### Tactical Horizons (5d, 21d) - Chronos-Bolt

```python
TACTICAL_CONFIG = {
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

### Strategic Horizons - Chronos-2 (VERIFIED LIMITS)

#### 63d Configuration
```python
CONFIG_63D = {
    "Chronos2": {
        # Model (default path is autogluon/chronos-2)
        "context_length": 1024,           # Reduced from 2048 for Mac
        "batch_size": 16,                 # Inference batch size
        "device": "cpu",                  # MPS NOT supported
        
        # Fine-tuning
        "fine_tune": True,
        "fine_tune_mode": "lora",
        "fine_tune_lr": 5e-5,
        "fine_tune_steps": 300,           # Light: 300 steps
        "fine_tune_batch_size": 4,        # SEPARATE from inference batch_size
        "fine_tune_context_length": 512,  # Reduced for fine-tune
        "fine_tune_lora_config": {
            "r": 4,
            "lora_alpha": 8,
        },
    },
    "TemporalFusionTransformer": {
        "context_length": 128,            # 2x horizon
    },
    "DirectTabular": {},
    "AutoETS": {},
    "Theta": {},
    "SeasonalNaive": {},
    # NO RecursiveTabular for strategic
}
```

#### 126d Configuration
```python
CONFIG_126D = {
    "Chronos2": {
        "context_length": 2048,           # More context for strategic
        "batch_size": 8,                  # Smaller for memory
        "device": "cpu",
        
        "fine_tune": True,
        "fine_tune_mode": "lora",
        "fine_tune_lr": 5e-5,
        "fine_tune_steps": 500,           # Fuller fine-tune
        "fine_tune_batch_size": 2,        # Very small for 126d
        "fine_tune_context_length": 1024,
        "fine_tune_lora_config": {
            "r": 8,
            "lora_alpha": 16,
        },
    },
    "TemporalFusionTransformer": {
        "context_length": 256,            # 2x horizon
    },
    "DirectTabular": {},
    "AutoETS": {},
    "Theta": {},
    "SeasonalNaive": {},
    # NO RecursiveTabular for strategic
}
```

### INVALID Parameters (DO NOT USE)
```python
# These will cause errors with Chronos-2:
# - optimization_strategy  ❌ (Chronos-Bolt only)
# - device="mps"           ❌ (Not supported)
# - model_path="amazon/chronos-t5-base"  ❌ (Wrong model)
```

---

## ⚡ LIGHT TRAIN SETTINGS

### Predictor Configuration
```python
LIGHT_TRAIN_CONFIG = {
    # Evaluation
    "eval_metric": "WQL",                    # Weighted Quantile Loss
    "quantile_levels": [0.10, 0.50, 0.90],   # P10, P50, P90
    
    # Training limits
    "presets": "medium_quality",             # Was "best_quality"
    "time_limit": 3600,                      # 1 hour (was 4 hours)
    "num_val_windows": 4,                    # Was 8
    
    # Frequency
    "freq": "B",                             # Business daily
}
```

### Unchanged Settings
```python
# These remain at full values:
"monte_carlo_runs": 10000,   # Required for proper P10/P90
```

---

## 📦 ALL DATA POLICY (MANDATORY)

### Required Data Sources

Every Core training run MUST load ALL of these sources:

| Source | Table | Min Rows | Features |
|--------|-------|----------|----------|
| Market Futures | `raw.market_futures_1d` | 100,000 | 103 symbols × 5 OHLCV = 515 |
| FRED Economic | `raw.fred_observations_1d` | 100,000 | 159 series |
| Weather NOAA | `raw.weather_noaa_1d` | 500 | 57 stations × 10 vars |
| FX Spot | `raw.fx_spot_1d` | 10,000 | 9 pairs |
| CFTC COT | `raw.cftc_cot_1w` | 500 | 24 symbols × 5 metrics |
| USDA Exports | `raw.usda_export_sales_1w` | 100 | 5 features |
| USDA WASDE | `raw.usda_wasde_1m` | 50 | 5 features |
| EPA RIN | `raw.epa_rin_prices_1d` | 50 | 4 types |
| News Sentiment | `raw.news_articles_1d` | 50 | 5+ features |

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
models/core_chronos2/
├── horizon_5d/
│   └── tactical/           # Chronos-Bolt + RecursiveTabular
├── horizon_21d/
│   └── tactical/           # Chronos-Bolt + RecursiveTabular
├── horizon_63d/
│   └── strategic/          # Chronos-2 (LoRA)
└── horizon_126d/
    └── strategic/          # Chronos-2 (LoRA)
```

### Database Outputs
```sql
-- OOF predictions written to:
INSERT INTO "model"."oof_predictions" (
    specialist,      -- 'core'
    horizon,         -- 5, 21, 63, 126
    as_of_date,
    symbol,          -- 'ZL'
    pred_p10,
    pred_p50,
    pred_p90,
    actual,
    fold_id,
    created_at
)
```

---

## ⏱️ TRAINING TIME ESTIMATES

### Mac M4 Pro (CPU-only)

| Horizon | Mode | Fine-tune | Est. Time |
|---------|------|-----------|-----------|
| 5d | Tactical | No | ~15 min |
| 21d | Tactical | No | ~15 min |
| 63d | Strategic | 300 steps | ~45 min |
| 126d | Strategic | 500 steps | ~90 min |
| **Total Core** | | | **~2.5-3 hours** |

### Full Pipeline (including specialists)
| Component | Est. Time |
|-----------|-----------|
| Core (all horizons) | ~3 hours |
| 11 Specialists | ~5.5 hours |
| Meta-Learner | ~1.5 hours |
| **Total** | **~10 hours** |

---

## ✅ PRE-FLIGHT CHECKLIST

Before running training:

### Data Validation
- [ ] `enforce_all_data_policy()` passes
- [ ] 600+ features loaded
- [ ] Zero NaN values
- [ ] Date range covers required window

### Configuration Validation
- [ ] `device="cpu"` (not "mps")
- [ ] No `optimization_strategy` parameter
- [ ] `fine_tune_batch_size` set (separate from `batch_size`)
- [ ] Correct horizon → config mapping (tactical/strategic)

### Environment Validation
- [ ] `AUTOGLUON_DISABLE_RAY=1` set
- [ ] `PYTORCH_ENABLE_MPS_FALLBACK=1` set
- [ ] Sufficient disk space (~10GB)
- [ ] Sufficient RAM (~16GB)

---

## 🚨 COMMON FAILURES & FIXES

| Failure | Cause | Fix |
|---------|-------|-----|
| OOM during fine-tune | batch_size too large | Reduce `fine_tune_batch_size` |
| Ray/GCS errors | Ray enabled on macOS | Set `AUTOGLUON_DISABLE_RAY=1` |
| MPS error | Using device="mps" | Change to `device="cpu"` |
| Quantile crossing | Independent quantile models | Post-process to enforce monotonic |
| Empty OOF predictions | Predictions not saved | Check `save_predictions()` call |

---

## 📋 TRAINING COMMAND

```bash
# Single horizon (smoke test)
python scripts/train_core_chronos.py --horizon 21 --mode quick --dry-run

# All horizons (production)
python scripts/train_core_chronos.py --horizon all --mode quick

# Modes:
#   ultrafast: Statistical only, 1 val window (~10 min)
#   quick: Chronos + TFT, 4 val windows (~3 hours)
#   full: Full ensemble, 4 val windows (~6 hours)
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
