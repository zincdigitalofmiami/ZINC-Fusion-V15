# SoT v2 Training Plan — Best Practices Review (2026-01-14)

This is a **pre-execution review** of the SoT v2 training design (52-model horizon-aligned stack + scenario engine) against time-series / probabilistic forecasting best practices, with **zero tolerance for synthetic/fallback data**.

## What’s Solid (Keep)

- **Horizon-aligned stacks** (`5/21/63/126`) with no recursive horizon mixing: avoids label leakage and compounding error.
- **Quantile-first outputs**: training `p30/p50/p70` everywhere is operationally useful; adding **calibrated** `p10_cal/p90_cal` is the correct way to get an outer envelope without “vibes”.
- **OOF integrity for stacking**: L1 meta models trained on **out-of-fold** base predictions is the correct stacking practice.
- **Independent scenario axes** (EVENTS / TRUMP_EFFECT / VOLATILITY / POLICY): avoids combinatorial explosion and keeps scenario logic explainable.
- **Explicit model IDs + table contracts**: `scripts/v2_training/MODEL_CATALOG.md` gives stable naming and removes “mystery models”.

## Hard Best-Practice Requirements (Must Enforce)

### 1) Point-in-Time (PIT) time keys
- **Raw:** `event_date` / `event_time` is canonical.
- **Derived/training/forecast:** `as_of_date` is canonical.
- When reading raw data to build a daily matrix, it is fine to alias: `event_date AS as_of_date` (so downstream DataFrames stay consistent) **as long as you never pull rows with event_date > as_of_date**.

### 2) Horizon definition must be “trading days”
H ∈ {5,21,63,126} should be interpreted as **next H trading sessions**, not calendar days, otherwise targets drift around holidays and long weekends.

### 3) CV must be time-aware + embargoed
Random K-fold is invalid for this domain.
- Use **blocked / era CV** and **embargo** around fold boundaries.
- Store `fold_id` alongside OOF rows (`training.oof_*` tables already have it).

### 4) Calibration must be time-aware
CQR assumes exchangeability; time series aren’t exchangeable.
Best practice is to calibrate using:
- a **rolling / recent** calibration window, or
- **cross-fit conformal** (calibrate on held-out blocks), per horizon.

### 5) Never synthesize values, never silently “fallback”
Prefer empty outputs or explicit failures over invented numbers.
This applies to:
- feature generation
- ingestion
- scenario engine
- dashboards

## Decisions / Clarifications Needed (Before Training)

1) **Target definition** (already stated in SoT, but needs to be enforced in code):
   - `target_{H}d` = **ZL close price at t+H trading days** (not returns) for each horizon H.
2) **Calibration contract**:
   - define the calibration window policy per horizon (e.g., last 2y for tactical, last 5y for strategic).
3) **Meta model family**:
   - recommended: `TabularPredictor` in quantile mode using base OOF quantiles + minimal regime/calendar features.
4) **Training input sources**:
   - `gold.elite_indicators_1d` is currently stale/legacy; SoT v2 should not depend on it until rebuilt.

## Doable Implementation Path (Matches SoT)

1) Build a daily **`as_of_date` spine** from `raw.market_futures_1d` for symbol `ZL`.
2) Compute `target_{H}d` via trading-day lead (join ZL by row-number/lag), then:
   - write into `training.core_matrix_1d` (and/or a targets table), and
   - write into specialist training inputs (schema change required if storing in `training.specialist_*_1d`).
3) Train L0 base models per horizon:
   - Core TimeSeriesPredictor → OOF to `training.oof_core_{H}d_1d`
   - 11 specialists TabularPredictor → OOF to `training.oof_{bucket}_{H}d_1d`
4) Build `training.meta_inputs_{H}d_1d` by joining 12×3 OOF columns + minimal regime/calendar features + `target_{H}d`.
5) Train L1 meta per horizon, write to `forecasts.production_{H}d_1d` (`p30/p50/p70`).
6) Run L2 CQR calibration per horizon, write `p10_cal/p90_cal` to the same production table.
7) Run L3 risk engine per horizon, then scenario overlays per axis, write to `analytics.price_scenarios_{H}d_1d` and event-prob tables.

## Current Blockers (From PROD Audit)

See `Docs/PRETRAINING_READINESS_2026_01_15.md` for latest live DB state. Key blockers before training:
- multiple **stale** raw inputs (RIN / WASDE)
- `training.core_matrix_1d` is empty
- specialist tables exist but are missing `target_{H}d` columns (requires explicit schema approval)

## Ingestion Ownership Mismatches (Impacting Freshness)

Several “required” raw sources are stale, and not all are currently owned by an Inngest job:
- ✅ `raw.fx_spot_1d` → `frontend/src/inngest/fx-spot-daily.ts` (FRED; insert-only idempotent)
- ✅ `raw.weather_noaa_1d` → `frontend/src/inngest/openmeteo-weather-daily.ts` (Open-Meteo for `OM_*` + `OPENMETEO:*`; insert-only idempotent)
- ✅ `raw.weather_noaa_1d` → `frontend/src/inngest/noaa-weather-daily.ts` (NOAA CDO for `GHCND:*`; insert-only idempotent)
- ✅ `raw.usda_export_sales_1w` → `frontend/src/inngest/usda-export-sales-weekly.ts` (FAS report parser; insert-only idempotent)
- ✅ `raw.cftc_cot_1w` → `frontend/src/inngest/cftc-weekly.ts` (row_hash + event/symbol existence checks; no `ON CONFLICT`)
- ❌ `raw.usda_wasde_1m` has no scheduled Inngest owner today (backfill-only scripts exist; ongoing source needs confirmation)
- ❌ `raw.epa_rin_prices_1d` has no real-time ingestion owner in `frontend/src/inngest/` (must be added or explicitly de-scoped)

Additional drift to resolve before running any backfills:
- Some legacy scripts still reference `report_date` / `as_of_date` against `raw.*`; core pipeline scripts have been standardized on the Prisma contract (`raw` → `event_date`, derived/training → `as_of_date`). Treat `*.backup.*` files as inactive.

## Immediate Next Step (Per current execution order)

Start by fixing **stale inputs** (prefer Inngest where possible), then re-run:
```bash
python3 scripts/pretrain_readiness_audit.py --strict
```
