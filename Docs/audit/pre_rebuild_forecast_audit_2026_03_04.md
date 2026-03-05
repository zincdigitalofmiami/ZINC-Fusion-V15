# Pre-Rebuild Forecast Audit (2026-03-04)

## Scope / Freeze
- This report is intentionally pre-rebuild.
- Per instruction, no matrix rebuild or core retrain was executed in this phase.
- A specialist signal generation run was started and then interrupted; state verification confirms key production timestamps remained unchanged.

## Executive Summary
- Current dashboard forecasts are updated through 2026-03-04 in `forecasts.production_1d`.
- Those forecasts are derived from an older matrix/specialist snapshot:
  - `training.matrix_1d` max date: 2026-03-01
  - `training.specialist_signals_1d` max date: 2026-03-01
- Monte Carlo outputs are populated and live in production.
- Pinball metrics are not currently persisted through the active pipeline path.
- Forecast intervals at 63d/126d are very wide on P10/P90 (about 14-15% of spot), matching stakeholder concern.

## What Was Executed (No Rebuild Phase)
1. `scripts/data_gate_specialists.py --strict` -> 11/11 pass.
2. `scripts/generate_specialist_features.py --bucket all --start-date 2025-01-01` -> completed.
3. `scripts/generate_specialist_signals.py --bucket all --start-date 2025-01-01` -> interrupted by user.
4. Post-interrupt verification:
   - `training.specialist_signals_1d` max date remained 2026-03-01.
   - `training.matrix_1d` max date remained 2026-03-01.

## Core Model Configuration (Current)
Source files:
- `src/fusion/core_training/config.py`
- `src/fusion/core_training/train_models.py`

Core settings:
- Target: `target_price_{h}d` (future price level, not return)
- Horizons: `5, 21, 63, 126`
- Validation: `num_val_windows = 4` (expanding windows)
- Metric: `MAE`
- Frequency: `B` (business-day)
- Time limit: `None`
- Presets: `None` (explicit model allowlist)
- Known covariates: seasonal calendar features (`SEASONAL_FEATURES`)
- Other covariates: observed/past covariates

Active model zoo (`MODEL_ZOO_FROZEN`, 19 models):
- Baselines: `Naive`, `SeasonalNaive`, `Average`, `SeasonalAverage`, `Zero`
- Statistical: `ETS`, `AutoETS`, `AutoARIMA`, `AutoCES`, `Theta`, `DynamicOptimizedTheta`, `NPTS`, `ADIDA`, `Croston`, `IMAPA`
- Tabular: `DirectTabular`, `PerStepTabular`, `RecursiveTabular`
- Foundation: `Chronos2`
- Deep models are intentionally disabled on current runtime.

## Forecast Widths (Latest Production Date = 2026-03-04)
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

Interpretation: P10/P90 is statistically defensible as a risk envelope, but visually too wide for a default decision zone at long horizons.

## Monte Carlo and Pinball Status
Monte Carlo:
- Latest production rows include `prob_enter_zone`, `prob_touch_p10`, `prob_touch_p90`, `mc_runs=10000`.
- MC pipeline path is writing successfully.

Pinball:
- `model.model_registry` contains pinball columns (`pinball_loss_p10`, `pinball_loss_p50`, `pinball_loss_p90`).
- Active horizon rows are currently pending/null.
- `training.model_runs_event` has no rows, so dashboard-side MAE/pinball provenance is under-instrumented.

## Deterministic Signal Value Snapshot
From `scripts/diagnostic_signal_report.py`:
- Signals analyzed: 22
- Signals with `|IC_21d| > 0.02`: 17
- Leakage suspicion count: 1 (`energy/signal_2`)
- Top positive IC examples:
  - `fx/signal_1` around 0.343
  - `china/signal_2` around 0.234
  - `energy/signal_1` around 0.231

Observed weak points:
- `palm` and `substitutes` have frequent low/zero confidence periods.
- Long-horizon interval calibration appears broad, suggesting residual spread or outlier sensitivity in calibration inputs.

## Data Gaps / Freshness Priorities
- `supply.epa_rin_1d` max date: 2026-01-19 (source-limited cadence)
- `supply.eia_biodiesel_1w` / `_1m` max date: 2025-11-01 (stale)
- `supply.uco_prices_1w` max date: 2026-01-01 (stale vs current market)
- Instrumentation gaps:
  - `model.shap_summary` relation missing
  - `training.model_runs_event` empty (no promoted-run trail)

## Dashboard Endpoint Wiring Check
Routes read latest production rows correctly:
- `/api/zl/brief` reads latest `price_p30/p50/p70` per horizon from `forecasts.production_1d`
- `/api/zl/forecast` reads latest per horizon from `forecasts.production_1d`
- `/api/zl/forecast-targets` reads latest per horizon including `prob_enter_zone`
- `brief` route is `force-dynamic`, so it should reflect newly written rows immediately.

## Architecture Sanity Check
Does the current signal path make sense:
- Core path is coherent: matrix features + specialist signals -> core model point forecast (`predicted_price`) -> L2/L3 probability wrapper.
- Probability path is partially complete: Monte Carlo is active, pinball persistence is not.
- Chart output is wired to production rows and should update when new rows land.
- Guarantee statement: architecture is directionally correct, but it does not yet guarantee full provenance signals until pinball and model run metadata are persisted every run.

## Pre-Rebuild Decisions
1. Keep P10/P90 for risk math, but default chart to a tighter decision zone.
2. Add long-horizon calibration controls (outlier handling and shrinkage for display zone).
3. Enforce required run metadata persistence (pinball + model run provenance).
4. Prioritize stale/empty data sources before the next rebuild.

Generated: 2026-03-04 (America/Chicago)
