# DuckDB State Snapshot

Generated: 2025-12-27T02:38:13.075853Z

DB file: `data/fusion.db`
Size: 1,016,082,432 bytes (969.0 MiB)
Last modified (local): 2025-12-26T19:05:56.266919

## Schemas
Count: 14

- archive
- features
- forecasts
- gold
- main
- main
- main
- metadata
- monitoring
- raw
- silver
- specialist
- training
- weather

## Tables per schema

| schema | tables |
|---|---:|
| archive | 16 |
| features | 11 |
| forecasts | 12 |
| gold | 4 |
| metadata | 1 |
| monitoring | 6 |
| raw | 12 |
| specialist | 11 |
| training | 35 |
| weather | 5 |

## Key table row counts

| table | rows | start | end |
|---|---:|---|---|
| raw.market_futures_1d | 385,994 | 1990-01-01 | 2025-12-15 |
| raw.market_futures_1h | 4,967,276 | 2010-06-07 00:00:00 | 2025-12-15 23:00:00 |
| raw.fred_observations_1d | 342,551 | 1871-01-01 | 2025-12-15 |
| raw.fx_spot_1d | 139,617 | 1981-01-02 | 2025-12-12 |
| raw.weather_observations_1d | 1,058,584 | 2005-01-01 | 2025-12-20 |
| features.driver_scores_1d | 47,469 | 2010-06-07 | 2025-12-15 |
| training.core_matrix_full_1d | 6,372 | 2000-10-23 00:00:00 | 2025-12-15 00:00:00 |
| training.oof_core_zl_1d | 19,416 | 2000-10-23 | 2025-12-15 |
| training.oof_specialist_combined_1d | 22,932 | 2010-06-07 | 2022-12-30 |
| forecasts.forecast_quantiles_1d | 0 |  |  |

## Full inventory
Saved to:
- `db_insights/schemas.csv`
- `db_insights/schema_table_counts.csv`
- `db_insights/tables.csv`
- `db_insights/key_table_row_counts.csv`
