# ZINC-FUSION-V15: Pre-Training Readiness Audit (SoT v2)
- Generated at: 2026-01-15T05:53:12.944753+00:00
- **Last Updated: 2026-01-15 (Claude Opus 4.5 Final Audit)**

---

## EXECUTIVE SUMMARY

| Status | Item |
|--------|------|
| **READY** | Schema cleanup (SoT v2 quantiles) |
| **READY** | Core matrix populated (6,622 rows) |
| **READY** | Elite indicators regenerated (6,627 rows to Jan 9) |
| **READY** | Model registry (52 pending models) |
| **READY** | Specialist targets (Option B: JOIN at training) |

**VERDICT: PRE-TRAINING READY**

---

## Schema Updates (2026-01-15)

### SoT v2 Quantile Contract
- **Primary quantiles:** pred_p30, pred_p50, pred_p70
- **Calibrated bounds:** pred_p10_cal, pred_p90_cal
- **Legacy removed:** pred_p10, pred_p90

### New Tables Created
- `model.forecast_metrics` - MAE, MASE, WAPE, MSE, RMSE, RMSSE, WQL, coverage

### Migration Applied
- `prisma/migrations/20260115_quantile_schema_cleanup/migration.sql`

---

## Data Freshness Status

### Source Data (v2 + legacy pending migration)
| Table | Rows | Max Date | Days Stale | Status |
|-------|------|----------|------------|--------|
| mkt.futures_1d (ZL) | 8,398 | 2026-01-09 | 6 | OK |
| raw.cftc_cot_1w (legacy) | 18,381 | 2026-01-06 | 9 | OK |
| raw.epa_rin_prices_1d (legacy) | - | 2025-11-24 | 52 | UPSTREAM LAG |

*Note: EPA RIN staleness is upstream data lag, not pipeline issue.*

### Training Tables (v2)
| Table | Rows | Max Date | Status |
|-------|------|----------|--------|
| training.matrix_1d | 6,622 | 2026-01-02 | READY |
| features.elite_1d | 6,627 | 2026-01-09 | READY |

### Specialist Feature Tables
| Table | Rows | Max Date | Status |
|-------|------|----------|--------|
| training.specialist_biofuel_1d | 42,055 | 2025-12-29 | 17d stale |
| training.specialist_china_1d | 27,492 | 2025-12-29 | 17d stale |
| training.specialist_crush_1d | 23,487 | 2025-12-29 | 17d stale |
| training.specialist_energy_1d | 45,380 | 2025-12-29 | 17d stale |
| training.specialist_fed_1d | 48,174 | 2025-12-29 | 17d stale |
| training.specialist_fx_1d | 80,165 | 2025-12-29 | 17d stale |
| training.specialist_palm_1d | 24,037 | 2025-12-29 | 17d stale |
| training.specialist_substitutes_1d | 42,706 | 2025-12-29 | 17d stale |
| training.specialist_tariff_1d | 42,414 | 2025-12-29 | 17d stale |
| training.specialist_trump_effect_1d | 2,273 | 2025-12-29 | 17d stale |
| training.specialist_volatility_1d | 35,088 | 2025-12-29 | 17d stale |

*Note: Specialist tables lag is acceptable for initial training. Can refresh after.*

---

## Elite Indicators Quality (Fixed)

| Indicator | Coverage | Notes |
|-----------|----------|-------|
| cmf_21 | 95.3% | Fixed with min_periods |
| volume_zscore | 98.4% | Fixed with min_periods |
| hurst_exponent | 98.5% | 100-day warmup |
| connors_rsi | 87.4% | Source data gaps |
| garman_klass_vol | 88.6% | Source OHLC gaps |
| All others | 99%+ | Ready |

---

## Model Registry

| Type | Count | Horizons | Status |
|------|-------|----------|--------|
| Specialist | 44 | 5d, 21d, 63d, 126d | Pending |
| Core | 4 | 5d, 21d, 63d, 126d | Pending |
| Meta | 4 | 5d, 21d, 63d, 126d | Pending |
| **Total** | **52** | - | **Pending** |

---

## Target Coverage (training.matrix_1d)

| Target | Rows | Coverage |
|--------|------|----------|
| target_5d | 6,622 | 100% |
| target_21d | 6,606 | 99.8% |
| target_63d | 6,564 | 99.1% |
| target_126d | 6,501 | 98.2% |

---

## Output Tables (Pre-Training - Expected Empty)

| Table | Rows | Status |
|-------|------|--------|
| model.oof_predictions | 0 | READY |
| model.forecast_metrics | 0 | READY |

---

## Security Fixes Applied

- Removed hardcoded `DATABASE_URL` from `scripts/check_core_features.py`
- Now uses `os.getenv("DATABASE_URL")` with validation

---

## Files Created/Modified This Session

### Scripts
- `scripts/register_models.py` - Model registry population
- `scripts/populate_core_matrix.py` - Core matrix builder

### Features (Fixed)
- `src/fusion/features/elite_indicators.py` - Added min_periods for proper null handling

### Migrations
- `prisma/migrations/20260115_quantile_schema_cleanup/migration.sql`

---

## Ready to Train

All blockers resolved:
1. ✅ Elite indicators regenerated (was 17 years stale)
2. ✅ Core matrix populated (6,622 rows)
3. ✅ Model registry populated (52 pending)
4. ✅ Quantile schema updated to SoT v2
5. ✅ Evaluation metrics table created

**Training pipeline can now be executed.**

---

*Document updated: 2026-01-15*
*Auditor: Claude Opus 4.5*
