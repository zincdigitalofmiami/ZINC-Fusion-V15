# Schema Audit Report - 2026-01-19

## Executive Summary

**Database is READY for training.** All tables exist and data is populated.

| Item | Status | Count |
|------|--------|-------|
| `training.matrix_1d` | **POPULATED** | 7,808 rows (1980-2026) |
| `features.elite_1d` | **POPULATED** | 7,818 rows |
| `model.cv_folds` | **POPULATED** | 188,140 rows |
| Target columns | **ALL 4 PRESENT** | 5d/21d/63d/126d |

**Issue Found:** Several scripts reference `training.core_matrix_1d` but the actual table is `training.matrix_1d`.

---

## Actual Database Tables (by Schema)

### training (29 tables)
| Table | Purpose | Status |
|-------|---------|--------|
| `matrix_1d` | Core training matrix with targets | 7,808 rows |
| `features_1d` | JSON feature store | |
| `meta_inputs_1d` | L1 meta-learner inputs | |
| `oof_core_1d` | Core model OOF predictions | |
| `oof_biofuel_1d` | Specialist OOF | |
| `oof_china_1d` | Specialist OOF | |
| `oof_crush_1d` | Specialist OOF | |
| `oof_energy_1d` | Specialist OOF | |
| `oof_fed_1d` | Specialist OOF | |
| `oof_fx_1d` | Specialist OOF | |
| `oof_palm_1d` | Specialist OOF | |
| `oof_substitutes_1d` | Specialist OOF | |
| `oof_tariff_1d` | Specialist OOF | |
| `oof_trump_effect_1d` | Specialist OOF | |
| `oof_volatility_1d` | Specialist OOF | |
| `specialist_biofuel_1d` | Specialist features | |
| `specialist_china_1d` | Specialist features | |
| `specialist_crush_1d` | Specialist features | |
| `specialist_energy_1d` | Specialist features | |
| `specialist_fed_1d` | Specialist features | |
| `specialist_palm_1d` | Specialist features | |
| `specialist_substitutes_1d` | Specialist features | |
| `specialist_tariff_1d` | Specialist features | |
| `specialist_trump_effect_1d` | Specialist features | |
| `specialist_volatility_1d` | Specialist features | |
| `specialist_features` | Raw specialist JSON | |
| `realized_volatility` | Vol calculations | |
| `volatility_surface` | Vol surface data | |
| `model_runs` | Training run metadata | |

### features (6 tables)
| Table | Purpose | Status |
|-------|---------|--------|
| `elite_1d` | 27 elite indicators | 7,818 rows |
| `options_1d` | Options features | |
| `weather_1d` | Weather features | |
| `news_sentiment_1d` | News sentiment | |
| `trump_effect_1d` | Trump effect features | |
| `intel_drops` | Intel drops | |

### model (12 tables)
| Table | Purpose | Status |
|-------|---------|--------|
| `cv_folds` | CV fold assignments | 188,140 rows |
| `model_registry` | Champion models | |
| `oof_predictions` | Ensemble OOF | |
| `meta_ensemble` | Meta predictions | |
| `meta_weights` | Specialist weights | |
| `garch_parameters` | GARCH params | |
| `lasso_coefficients` | Lasso coeffs | |
| `shap_summary` | SHAP importance | |
| `shap_values` | SHAP values | |
| `regime_probabilities` | Regime states | |
| `forecast_metrics` | Forecast metrics | |
| `model_leaderboard` | Leaderboard | |

### mkt (6 tables)
| Table | Purpose |
|-------|---------|
| `futures_1d` | Daily futures OHLCV |
| `futures_1h` | Hourly futures |
| `fx_1d` | FX rates |
| `options_1d` | Options chain |
| `options_greeks_1d` | Greeks |
| `etf_1d` | ETF prices |

### econ (7 tables)
| Table | Purpose |
|-------|---------|
| `rates_1d` | Interest rates (FRED) |
| `inflation_1d` | Inflation data |
| `labor_1d` | Labor data |
| `activity_1d` | Economic activity |
| `commodities_1d` | Commodity prices |
| `money_1d` | Money supply |
| `vol_indices_1d` | VIX etc |

### alt (3 tables)
| Table | Purpose |
|-------|---------|
| `news_1d` | Raw news articles |
| `weather_1d` | Weather data |
| `legislation_1d` | Legislative events |

### pos (2 tables)
| Table | Purpose |
|-------|---------|
| `cftc_1w` | CFTC COT weekly |
| `cftc_cits_1w` | CFTC CITs |

### supply (4 tables)
| Table | Purpose |
|-------|---------|
| `usda_wasde_1m` | WASDE monthly |
| `usda_exports_1w` | Export sales |
| `epa_rin_1d` | RIN prices |
| `worldbank_imports_1y` | Import data |

### forecasts (12 tables)
| Table | Purpose |
|-------|---------|
| `production_5d_1d` | 5-day forecasts |
| `production_21d_1d` | 21-day forecasts |
| `production_63d_1d` | 63-day forecasts |
| `production_126d_1d` | 126-day forecasts |
| `forecast_summary_1d` | Summary |
| `forecast_quantiles` | Quantile forecasts |
| `garch_forecasts` | GARCH forecasts |
| `core_cone_1d` | Forecast cones |
| `core_mc_1d` | Monte Carlo |
| `monte_carlo_runs` | MC metadata |
| `probability_distributions` | Fitted distributions |
| `horizon_reconciliation_1d` | Reconciliation |

### ops (10 tables)
| Table | Purpose |
|-------|---------|
| `training_runs` | Training execution |
| `training_run_log` | Training phases |
| `model_core_audit` | Model validation |
| `prediction_accuracy` | Accuracy tracking |
| `data_quality_metrics` | Data freshness |
| `data_quality_log` | Quality history |
| `ingest_run` | Ingestion runs |
| `quarantined_record` | Failed records |
| `data_source_registry` | Source metadata |
| `source_relabel_audit` | Relabeling |

---

## Prisma Model Mappings

| Prisma Model | Actual Table | Schema |
|--------------|--------------|--------|
| TrainingMatrix1d | `matrix_1d` | training |
| TrainingFeatures1d | `features_1d` | training |
| OofCore1d | `oof_core_1d` | training |
| MetaInputs1d | `meta_inputs_1d` | training |
| SpecialistFeatures | `specialist_features` | training |
| CvFolds | `cv_folds` | model |
| ModelRegistry | `model_registry` | model |
| elite_indicators_1d | `elite_1d` | features |

---

## Script Reference Mismatches (NEEDS FIX)

### Critical: `core_matrix_1d` → `matrix_1d`

Scripts referencing **wrong** table name `training.core_matrix_1d`:

| Script | Line | Issue |
|--------|------|-------|
| `populate_core_matrix.py` | 295, 322, 336 | Uses `core_matrix_1d` |
| `pretrain_readiness_audit.py` | multiple | Uses `core_matrix_1d` |
| `audit_training_readiness.py` | multiple | Uses `core_matrix_1d` |
| `validate_db_state.py` | multiple | Uses `core_matrix_1d` |
| `validate_training_tables.py` | multiple | Uses `core_matrix_1d` |
| `audit_db_state.py` | multiple | Uses `core_matrix_1d` (legacy) |

**Correct table name:** `training.matrix_1d`

### Minor: Legacy `gold.elite_indicators_1d` reference

| Script | Issue |
|--------|-------|
| `audit_db_state.py` | References banned `gold` schema |

**Correct table name:** `features.elite_1d`

---

## Current Data State

```sql
-- Training Matrix
SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM training.matrix_1d;
-- Result: 7808 rows, 1980-01-01 to 2026-01-09

-- Targets populated
SELECT COUNT(target_ret_5d), COUNT(target_ret_21d),
       COUNT(target_ret_63d), COUNT(target_ret_126d)
FROM training.matrix_1d;
-- Result: All 7808 rows have all 4 targets

-- Elite indicators
SELECT COUNT(*) FROM features.elite_1d WHERE symbol='ZL';
-- Result: 7818 rows

-- CV folds
SELECT COUNT(*) FROM model.cv_folds;
-- Result: 188140 rows
```

---

## Recommended Actions

1. **Fix script table references** - Update all scripts using `core_matrix_1d` to use `matrix_1d`
2. **Remove legacy references** - Clean up `gold.elite_indicators_1d` references
3. **No data population needed** - Database is already populated and ready

---

## Training Readiness Verdict

**READY TO TRAIN** - All required data is present:
- Training matrix with 4 horizons of targets
- Elite indicators computed
- CV folds generated
- All OOF tables exist (empty, ready for predictions)
