# Ingestion Runbook (Schema-Safe)

Status: Draft for execution. No schema changes required.

Goal: Align existing Inngest jobs with the specialist signal plan, confirm what is
already covered, and identify safe additions that do not touch schemas.

## Current Inngest Coverage (By Domain)

### Market Prices (mkt.* / analytics.*)

- `yahoo-eod` → `mkt.futures_1d` (core futures: ZL/ZS/ZM/CL/HO/etc).
- `barchart-futures-daily` → `mkt.futures_1d` (softs: CT/OJ/LBR only; Yahoo preferred when available).
- `cpo-daily` / `cpo-trading-economics` → `mkt.futures_1d` (CPO backup).
- `fx-spot-daily` → `mkt.fx_1d` (USD/BRL, USD/CNY, USD/ARS, etc).
- `barchart-etf-daily` → `mkt.etf_1d` (SPY/QQQ/VXX/UVXY).
- `barchart-options-daily` → `mkt.options_greeks_1d` (ZL/ZS/ZM/CL).
- `zl-15m` / `zl-1h` → `analytics.zl_price_15m` / `analytics.zl_price_1h` (dashboard only; not for training).

### Macro / Rates / Volatility (econ.*)

- `fred-daily-*` (segments) → `econ.rates_1d`, `econ.activity_1d`, `econ.vol_indices_1d`, etc.
- `nyfed-daily` → `econ.rates_1d` (SOFR, EFFR).
- `eia-today` / `nass-weekly` / `usda-press` → `econ.rates_1d` (energy/ag stats).

### Supply / Policy (supply.*)

- `usda-wasde-monthly` → `supply.usda_wasde_1m`.
- `usda-export-sales-weekly` → `supply.usda_exports_1w`.
- `epa-rin-prices-daily` → `supply.epa_rin_1d` (RIN prices).

### Positioning (pos.*)

- `cftc-weekly` → `pos.cftc_1w`.

### News / Policy / Alt (alt.*)

- `federal-register` → `alt.legislation_1d`.
- `whitehouse-press`, `conab-news`, `profarmer-daily`, `barchart-zl-news`,
  `farmdoc-rins`, `aei-trade`, `cbp-trade`, `ice-releases` → `alt.news_1d`.
- `noaa-weather-daily`, `openmeteo-weather-daily` → `alt.weather_1d`.
- `weather-features-daily` → `features.weather_1d` (derived; not a schema change).

## Specialist Alignment (Quick Map)

- biofuel: `epa-rin-prices-daily`, `federal-register`, `farmdoc-rins`, `usda-press`
- palm: `barchart-futures-daily` (CPO), `cpo-daily` (backup)
- crush: `yahoo-eod` (ZL/ZS/ZM), `cftc-weekly`, `usda-wasde-monthly`
- fx: `fx-spot-daily`
- fed/volatility: `fred-daily-volatility`, `nyfed-daily`, `barchart-options-daily`
- energy: `yahoo-eod` (CL/HO), `eia-today`
- china: `conab-news`, `cbp-trade`, `usda-export-sales-weekly`, FRED China series
- substitutes: `barchart-futures-daily` (RS/Canola), `yahoo-eod`
- tariff/trump_effect: `federal-register`, `whitehouse-press`, `alt.news_1d`

## Safe Additions (No Schema Changes)

These additions are optional and can be implemented without new tables/columns:

- CVOL data: ingest into `econ.vol_indices_1d` as a new series id (if decided).
- EPA RIN generation CSV: only if we agree on a target table; otherwise defer.
- FCPO contract specs: keep as documentation-only (no ingestion required).

## Execution Checklist (Couple-Hours Window)

1) Confirm Inngest is running and jobs are registered:
   - `frontend/src/inngest/functions.ts` is the authoritative export list.
2) Trigger critical jobs manually in Inngest UI (or wait for cron):
   - `yahoo-eod`, `barchart-futures-daily`, `fx-spot-daily`
   - `epa-rin-prices-daily`, `usda-wasde-monthly`, `usda-export-sales-weekly`
   - `fred-daily-*`, `cftc-weekly`, `federal-register`
3) Validate data coverage:
   - Use `scripts/validate_db_state.py`.
4) Proceed to training once `training.matrix_1d` dependencies are fresh.

## Notes

- Schema is untouched. All additions must target existing tables only.
- Intraday data stays in `analytics.*` and is dashboard-only by contract.
