# Pre-Rebuild Forecast Audit (2026-03-04)

## Scope / Freeze
- This report is intentionally **pre-rebuild**.
- Per instruction, no matrix rebuild or core retrain was executed in this phase.
- A specialist signal generation run was started and then interrupted; state verification below confirms key production timestamps remain unchanged.

## Executive Summary
- Current dashboard forecasts are updated through **2026-03-04** in `forecasts.production_1d`.
- Those forecasts are derived from a matrix/specialist snapshot that is older:
  - `training.matrix_1d` max date: **2026-03-01**
  - `training.specialist_signals_1d` max date: **2026-03-01**
  - `training.oof_core_1d` latest trade dates are horizon-lagged (expected), but latest `trained_at` values are recent.
- Monte Carlo outputs are populated and live in production.
- Pinball metrics are not currently persisted through the active pipeline path (registry fields are null/pending).
- Forecast intervals at 63d/126d are very wide on P10/P90 (roughly 14-15% of spot), matching stakeholder concern.

## What Was Executed (No Rebuild Phase)
1. `scripts/data_gate_specialists.py --strict` → **11/11 pass**.
2. `scripts/generate_specialist_features.py --bucket all --start-date 2025-01-01` → completed.
3. `scripts/generate_specialist_signals.py --bucket all --start-date 2025-01-01` → interrupted by user.
4. Post-interrupt verification:
   - `training.specialist_signals_1d` max date remains **2026-03-01**.
   - `training.matrix_1d` max date remains **2026-03-01**.

## Core Model Configuration (Current)
Source files:
- `src/fusion/core_training/config.py`
- `src/fusion/core_training/train_models.py`

### Core settings
- Target: `target_price_{h}d` (future price level, not return)
- Horizons: `5, 21, 63, 126`
- Validation: `num_val_windows = 4` (expanding windows)
- Metric: `MAE`
- Frequency: `B` (business-day)
- Time limit: `None`
- Presets: `None` (explicit model allowlist)
- Known covariates: seasonal calendar features (`SEASONAL_FEATURES`)
- Other covariates: observed/past covariates

### Active model zoo (`MODEL_ZOO_FROZEN`, 19 models)
- Baselines: `Naive`, `SeasonalNaive`, `Average`, `SeasonalAverage`, `Zero`
- Statistical: `ETS`, `AutoETS`, `AutoARIMA`, `AutoCES`, `Theta`, `DynamicOptimizedTheta`, `NPTS`, `ADIDA`, `Croston`, `IMAPA`
- Tabular: `DirectTabular`, `PerStepTabular`, `RecursiveTabular`
- Foundation: `Chronos2`
- Deep models are intentionally disabled on current runtime.

## Current Data/Training State Snapshot
- `mkt.futures_1d` (ZL) max: **2026-03-03/04** depending on query timing
- `training.matrix_1d` max: **2026-03-01**
- `training.specialist_signals_1d` max: **2026-03-01**
- `training.oof_core_1d` max `trained_at`: recent (2026-03-04), max trade date horizon-lagged
- `forecasts.production_1d` max `as_of_date`: **2026-03-04**

## Forecast Widths (Latest Production Date = 2026-03-04)
Using `forecasts.production_1d` latest rows:

- 5d:
  - P10-P90 width: `2.5732` (4.09% of spot)
  - P30-P70 width: `1.2521` (1.99% of spot)
- 21d:
  - P10-P90 width: `6.3738` (10.13%)
  - P30-P70 width: `1.5450` (2.46%)
- 63d:
  - P10-P90 width: `8.7883` (13.97%)
  - P30-P70 width: `4.7257` (7.51%)
- 126d:
  - P10-P90 width: `9.6484` (15.34%)
  - P30-P70 width: `3.5476` (5.64%)

Interpretation: P10/P90 is statistically defensible as a risk envelope, but visually too wide for a “decision zone” at long horizons.

## Monte Carlo and Pinball Status

### Monte Carlo
- Production rows for latest date include:
  - `prob_enter_zone`, `prob_touch_p10`, `prob_touch_p90`, `mc_runs=10000`
- MC pipeline path is functioning and writing successfully.

### Pinball
- `model.model_registry` has columns:
  - `pinball_loss_p10`, `pinball_loss_p50`, `pinball_loss_p90`
- Current rows for active horizons are `pending`/null in these fields.
- `training.model_runs_event` currently has no rows, so dashboard-side MAE/pinball provenance is under-instrumented.

## Deterministic “What Worked / What Didn’t” (Current Evidence)
From `scripts/diagnostic_signal_report.py`:
- Signals analyzed: 22
- Signals with `|IC_21d| > 0.02`: 17
- Leakage suspicions: 1 (`energy/signal_2`)
- Top positive IC examples:
  - `fx/signal_1` ~ 0.343
  - `china/signal_2` ~ 0.234
  - `energy/signal_1` ~ 0.231

Observed weak points:
- `palm` and `substitutes` recent confidence shows frequent low/zero confidence periods.
- Long-horizon interval calibration is broad, suggesting residual spread or outlier sensitivity in calibration inputs.

## Data Gaps / Freshness Gaps Worth Prioritizing
- `supply.epa_rin_1d` max date: 2026-01-19 (source-limited cadence)
- `supply.eia_biodiesel_1w` / `_1m` max date: 2025-11-01 (stale)
- `supply.uco_prices_1w` max date: 2026-01-01 (stale vs current market)
- Instrumentation gaps:
  - `model.shap_summary` relation missing
  - `training.model_runs_event` empty (no promoted-run trail)

## Dashboard Endpoint Wiring Check
Routes do read latest production rows correctly:
- `/api/zl/brief` reads latest `price_p30/p50/p70` per horizon from `forecasts.production_1d`
- `/api/zl/forecast` reads latest per horizon from `forecasts.production_1d`
- `/api/zl/forecast-targets` reads latest per horizon including `prob_enter_zone`
- `brief` route is `force-dynamic`, so it should reflect newly written rows immediately.

## Where To Push for Better Results (Before Any Rebuild)
1. Keep P10/P90 for risk math, but chart a tighter decision band.
   - Recommended display zone: calibrated central band (e.g., P35-P65 or P40-P60) with P10/P90 shown as optional “risk envelope”.
   - Maintain MC probability annotations on the displayed band.

2. Tighten long-horizon calibration logic.
   - Add residual outlier controls (winsorization / regime-conditioned residual pools).
   - Add horizon-specific shrinkage toward P50 for display band only.

3. Improve deterministic value reporting.
   - Promote `diagnostic_signal_report` output into a required artifact in pipeline/reporting.
   - Reintroduce non-deprecated ablation/marginal-value test path for dataset-level usefulness.

4. Fix provenance/metrics persistence.
   - Ensure run metadata writes into `training.model_runs_event`.
   - Persist pinball metrics for the active promoted runs.

5. Address stale/weak data blocks.
   - Prioritize EIA biodiesel refresh and UCO price freshness.
   - Review low-confidence specialists (`palm`, `substitutes`) for missingness and source cadence.

## Pre-Rebuild Decision Checklist
Before rerunning full rebuild/training, decide:
- Display-zone policy (keep P10/P90 hidden unless expanded, show tighter band by default).
- Calibration policy (outlier handling + horizon shrinkage behavior).
- Required reporting outputs (IC/leakage table + data freshness + pinball/MAE provenance).
- Data source priorities (EIA/UCO refresh sequence).

---
Generated: 2026-03-04 (America/Chicago)
