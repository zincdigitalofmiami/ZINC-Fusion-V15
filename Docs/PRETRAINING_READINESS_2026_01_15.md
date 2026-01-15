# ZINC-FUSION-V15: Pre-Training Readiness Audit (SoT v2)
- Generated at: 2026-01-15T03:35:37.436547+00:00
- Today (local): 2026-01-14

## Metadata Coverage
- metadata.symbol_mapping rows: 20
- metadata.symbol_mapping canonical_id: 15
- raw.market_futures_1d distinct symbols: 104
- missing mappings (raw.market_futures_1d): 97 / 104

## Raw Data Freshness (Inputs)
- Market futures (1d): 432,152 rows | 1968-12-05 → 2026-01-09 | stale=5d
- FRED observations (1d): 513,587 rows | 1866-12-31 → 2026-12-31 | stale=-351d (future-dated)
- FX spot (1d): 59,168 rows | 1971-01-04 → 2026-01-09 | stale=5d
- CFTC COT (1w): 18,372 rows | 2006-06-13 → 2025-12-30 | stale=15d
- NOAA weather (1d): 220,976 rows | 2005-01-01 → 2026-01-14 | stale=0d
- USDA export sales (1w): 9,712 rows | 1998-12-17 → 2025-12-25 | stale=20d
- USDA WASDE (1m): 12,548 rows | 1964-01-01 → 2025-12-12 | stale=33d
- EPA RIN prices (1d): 208 rows | 2024-12-23 → 2025-12-15 | stale=30d
- News (event): 3,218 rows | 2017-05-08 → 2026-01-14 | stale=0d
- White House actions (event): 41 rows | 2025-09-01 → 2026-01-13 | stale=1d

## Feature Tables (Silver/Gold/Features)
- features.trump_effect_1d: 3,294 rows | 2017-01-03 → 2026-01-09
- silver.futures_prices_1d[ZL]: 8,390 rows | 1970-01-01 → 2025-12-29
- gold.elite_indicators_1d[ZL]: 4,000 rows | 1970-01-01 → 2009-02-02 | symbols=1

## Feature Stores
- training.specialist_features buckets: 11
- training.specialist_features[biofuel]: 6,627 rows | 2000-01-03 → 2026-01-09
- training.specialist_features[china]: 6,627 rows | 2000-01-03 → 2026-01-09
- training.specialist_features[crush]: 6,627 rows | 2000-01-03 → 2026-01-09
- training.specialist_features[energy]: 6,627 rows | 2000-01-03 → 2026-01-09
- training.specialist_features[fed]: 6,627 rows | 2000-01-03 → 2026-01-09
- training.specialist_features[fx]: 6,627 rows | 2000-01-03 → 2026-01-09
- training.specialist_features[palm]: 6,627 rows | 2000-01-03 → 2026-01-09
- training.specialist_features[substitutes]: 6,627 rows | 2000-01-03 → 2026-01-09
- training.specialist_features[tariff]: 6,627 rows | 2000-01-03 → 2026-01-09
- training.specialist_features[trump_effect]: 6,627 rows | 2000-01-03 → 2026-01-09
- training.specialist_features[volatility]: 6,627 rows | 2000-01-03 → 2026-01-09
- training.core_features: 6,381 rows | 2000-10-23 → 2025-12-29 (JSON blob, no targets)
- training.core_matrix_1d: 0 rows (SoT v2 matrix)

## Specialist Tables (training.specialist_*_1d)
- training.specialist_crush_1d: 23,487 rows | 2000-03-15 → 2025-12-29 | missing_targets=4
- training.specialist_china_1d: 27,492 rows | 2000-03-15 → 2025-12-29 | missing_targets=4
- training.specialist_fx_1d: 80,165 rows | 2000-05-23 → 2025-12-29 | missing_targets=4
- training.specialist_fed_1d: 48,174 rows | 2000-06-02 → 2025-12-29 | missing_targets=4
- training.specialist_tariff_1d: 42,414 rows | 2000-03-15 → 2025-12-29 | missing_targets=4
- training.specialist_energy_1d: 45,380 rows | 2000-08-23 → 2025-12-29 | missing_targets=4
- training.specialist_biofuel_1d: 42,055 rows | 2000-03-15 → 2025-12-29 | missing_targets=4
- training.specialist_palm_1d: 24,037 rows | 2000-03-15 → 2025-12-29 | missing_targets=4
- training.specialist_volatility_1d: 35,088 rows | 2000-09-18 → 2025-12-29 | missing_targets=4
- training.specialist_substitutes_1d: 42,706 rows | 2000-03-15 → 2025-12-29 | missing_targets=4
- training.specialist_trump_effect_1d: 2,273 rows | 2017-01-20 → 2025-12-29 | missing_targets=4

## SoT v2 Output Tables (expected empty before training)
- training.oof_* table count: 48
- training.meta_inputs_5d_1d: 0 rows
- training.meta_inputs_21d_1d: 0 rows
- training.meta_inputs_63d_1d: 0 rows
- training.meta_inputs_126d_1d: 0 rows
- forecasts.production_5d_1d: 0 rows
- forecasts.production_21d_1d: 0 rows
- forecasts.production_63d_1d: 0 rows
- forecasts.production_126d_1d: 0 rows
- analytics.price_scenarios_5d_1d: 0 rows
- analytics.event_probabilities_5d_1d: 0 rows
- analytics.price_scenarios_21d_1d: 0 rows
- analytics.event_probabilities_21d_1d: 0 rows
- analytics.price_scenarios_63d_1d: 0 rows
- analytics.event_probabilities_63d_1d: 0 rows
- analytics.price_scenarios_126d_1d: 0 rows
- analytics.event_probabilities_126d_1d: 0 rows

## Verdict
- Pre-training ready: NO

### Blockers
- raw.usda_wasde_1m stale 33d (>31d)
- raw.epa_rin_prices_1d stale 30d (>28d)
- training.core_matrix_1d is empty (cannot train L0 core)
- training.specialist_crush_1d missing targets: target_126d, target_21d, target_5d, target_63d
- training.specialist_china_1d missing targets: target_126d, target_21d, target_5d, target_63d
- training.specialist_fx_1d missing targets: target_126d, target_21d, target_5d, target_63d
- training.specialist_fed_1d missing targets: target_126d, target_21d, target_5d, target_63d
- training.specialist_tariff_1d missing targets: target_126d, target_21d, target_5d, target_63d
- training.specialist_energy_1d missing targets: target_126d, target_21d, target_5d, target_63d
- training.specialist_biofuel_1d missing targets: target_126d, target_21d, target_5d, target_63d
- training.specialist_palm_1d missing targets: target_126d, target_21d, target_5d, target_63d
- training.specialist_volatility_1d missing targets: target_126d, target_21d, target_5d, target_63d
- training.specialist_substitutes_1d missing targets: target_126d, target_21d, target_5d, target_63d
- training.specialist_trump_effect_1d missing targets: target_126d, target_21d, target_5d, target_63d

### Warnings
- metadata.symbol_mapping missing 97/104 symbols for raw.market_futures_1d
- raw.fred_observations_1d: has future-dated max 2026-12-31
- raw.cftc_cot_1w stale 15d (>14d)
- raw.usda_export_sales_1w stale 20d (>14d)
- raw.fred_observations_1d has 8 future-dated rows
- features.trump_effect_1d lags raw.whitehouse_actions_event (2026-01-09 < 2026-01-13)
