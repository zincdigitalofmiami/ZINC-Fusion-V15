# ZINC-FUSION-V15: Specialist Training Status & Issues

**Date:** 2026-01-03
**Status:** BLOCKED - Needs 11 separate training pipelines
**Priority:** DEFERRED - Focus on Core first

> NOTE (2026-01-17): Schema v2 replaces raw/gold/silver with mkt/econ/features.
> Legacy table references below are pending migration.

---

## Critical Finding: Feature Generation Bug

### Root Cause Identified
The `generate_specialist_features.py` script had a **date type mismatch** that caused 86% of features to be NULL:

```
market_futures_1d.as_of_date -> Python `date` object
fred_observations_1d.as_of_date -> Python `datetime` object
```

When merging with `pd.merge(on="as_of_date")`, the left join silently failed because:
- `date(2020,1,1) != Timestamp('2020-01-01')`
- All non-market columns returned as NULL

### Fix Applied
After investigation, we confirmed that when using `pd.to_datetime()` consistently on all date columns, the merges work correctly:
- 997 features generated
- 988 non-null (99.1%)
- Trump regime features properly populated

**File:** `scripts/generate_specialist_features.py`
**Lines 205, 231, 250, 271, etc.:** Each loader already has `pd.to_datetime()` - the fix was ensuring consistency.

---

## Fundamental Architecture Problem

### Current State (BROKEN)
The current `train_specialist.py` and `generate_specialist_features.py` give **identical features to all 11 specialists**. This is wrong.

### Required State
Each of the 11 specialists needs:

1. **Different raw data sources** (as documented in `ZINC_FUSION_V15_BIG11_COMPLETE_SOURCES.md`)
2. **Different feature engineering** (from `src/fusion/features/specialist_buckets.py` Specialist classes)
3. **Different model configurations** (some need GARCH, some need neural networks)

### The 11 Specialists & Their Requirements

| Specialist | Variance | Key Data Sources | Feature Class |
|------------|----------|------------------|---------------|
| crush | 28-35% | ZL/ZM/ZS, NOPA, USDA WASDE | `CrushBucketIndicators` |
| china | 16-22% | HG, FEF1, GACC imports, USD/CNY | `ChinaBucketIndicators` |
| energy | 10-14% | CL/HO/RB/NG, EIA, crack spreads | `EnergyBucketIndicators` |
| palm | 8-12% | XK/FCPO, MPOB, Malaysia inventory | `PalmBucketIndicators` |
| biofuel | 6-10% | RIN D4/D6, EPA, biodiesel production | `BiofuelBucketIndicators` |
| trump_effect | 5-10% | EPU indices, DJT/FXI, event scoring | `TrumpEffectFeatureEngine` |
| substitutes | 4-6% | Canola, sunflower, rapeseed | `SubstitutesBucketIndicators` |
| tariff | 3-5% | USTR, Federal Register, trade policy | `TariffBucketIndicators` |
| fx | 3-5% | FX pairs, DXY, FRED rates | `FXBucketIndicators` |
| fed | 2-4% | Treasuries, yield curves, FOMC | `FedBucketIndicators` |
| volatility | 2-3% | VIX, GARCH, stress indices | `VolatilityBucketIndicators` |

---

## Key Files & Their Purposes

### Feature Engineering (EXISTS - needs to be used properly)
- `src/fusion/features/specialist_buckets.py` - All Specialist indicator classes (83KB)
- `src/fusion/features/trump_effect.py` - Trump-specific feature engine (29KB)
- `src/fusion/features/technical_indicators.py` - 130+ technical indicators (42KB)
- `src/fusion/features/regime_detection.py` - Market regime classification (18KB)

### Current Training (BROKEN - treats all specialists the same)
- `scripts/train_specialist.py` - Single script for all specialists
- `scripts/generate_specialist_features.py` - Gives same 997 features to all

### Data Source Documentation
- `ZINC_FUSION_V15_BIG11_COMPLETE_SOURCES.md` - Complete URL/API registry for all 11 specialists
- `AGENTS.md` (lines 300-370) - Specialist taxonomy and metadata

---

## What Was Tested

### Trump Effect Specialist (2026-01-03)
1. Ran `generate_specialist_features.py --bucket trump_effect` - Generated 997 features
2. Ran `train_specialist.py --bucket trump_effect --horizon 21 --mode full` - Trained successfully
3. Generated 3,239 OOF predictions saved to `model.oof_predictions`
4. **Problem Found:** Top feature importance was Norwegian Krone (DEXNOUS), not Trump-specific features
5. **Root Cause:** All specialists get identical features - AutoGluon picked what it found useful from the generic feature set, not domain-specific features

---

## Work Required (DEFERRED)

To properly implement specialist training, need to create 11 separate scripts:

```
scripts/train_crush.py      # ZL/ZM/ZS, NOPA, USDA, CrushBucketIndicators
scripts/train_china.py      # HG/FEF1, GACC, ChinaBucketIndicators
scripts/train_energy.py     # CL/HO/RB/NG, EIA, EnergyBucketIndicators
scripts/train_biofuel.py    # RIN, EPA, BiofuelBucketIndicators
scripts/train_palm.py       # XK/FCPO, MPOB, PalmBucketIndicators
scripts/train_fx.py         # FX pairs, FXBucketIndicators
scripts/train_fed.py        # Treasuries, FedBucketIndicators
scripts/train_tariff.py     # USTR, TariffBucketIndicators
scripts/train_volatility.py # VIX, GARCH, VolatilityBucketIndicators
scripts/train_substitutes.py # Canola/sunflower, SubstitutesBucketIndicators
scripts/train_trump_effect.py # EPU, Yahoo proxies, TrumpEffectFeatureEngine
```

Each script needs to:
1. Load ONLY relevant raw data for that specialist
2. Apply correct feature engineering from the bucket indicator class
3. Use appropriate model configuration (GARCH for volatility, etc.)
4. Train with proper CV and save to correct tables

---

## Database Tables Status

### Raw Data (GOOD - data exists)
```sql
raw.market_futures_1d     -- 396,602 rows (1990-2025)
raw.fred_observations_1d  -- 437,930 rows (1871-2025)
raw.fx_spot_1d            -- 211,752 rows (1971-2025)
raw.weather_noaa_1d       -- 215,320 rows (2005-2025)
raw.cftc_cot_1w           -- 18,355 rows (2006-2025)
raw.usda_export_sales_1w  -- 6,412 rows (2020-2025)
raw.usda_wasde_1m         -- 4,320 rows (2020-2025)
raw.epa_rin_prices_1d     -- 208 rows (2024-2025)
raw.news_articles_1d      -- 4,884 rows (2008-2026)
```

### Training Tables (PARTIALLY POPULATED)
```sql
training.specialist_features -- 11 Specialists x 6,521 rows each (but with generic features)
training.cv_folds            -- Proper expanding window folds
```

### Model Tables (NEEDS PROPER DATA)
```sql
model.oof_predictions        -- Has trump_effect 21d predictions (from generic features)
model.lasso_coefficients     -- Has trump_effect coefficients
model.cv_folds               -- Populated
```

---

## Next Steps When Resuming

1. Create individual training scripts for each specialist
2. Each script should:
   - Import the correct bucket indicator class
   - Load only relevant raw data
   - Apply domain-specific feature engineering
   - Use appropriate model configuration
   - Save to specialist-specific model tables

3. Consider using the `ZincFusionBucketIndicators.compute_all_buckets()` method but only for the relevant Specialist

4. Reference `ZINC_FUSION_V15_BIG11_COMPLETE_SOURCES.md` for exact data requirements per specialist

---

## Priority: Focus on Core First

The specialist training is complex and requires significant work. The immediate priority is getting **Core** working for the dashboard this month.

Core training uses:
- `scripts/train_core_chronos.py`
- `training.core_matrix_full_1d`
- Outputs to `training.oof_core_zl_1d`

Once Core is working and producing forecasts, specialists can be added incrementally.
