# SoT v2 Model Catalog (52 Models)

This is the **explicit registry** of the SoT v2 training stack:
- Horizons: `5d`, `21d`, `63d`, `126d`
- Quantiles trained: `p30`, `p50`, `p70`
- Outer envelope: `p10_cal`, `p90_cal` (CQR / conformal calibration)

## Data Sources (LOCKED)

| Source | Role | Window | Status |
|--------|------|--------|--------|
| Historical Backfill | 1990 → 2025-12-29 | One-time | ✅ COMPLETE |
| Yahoo Finance | Daily topfill | Ongoing | ✅ Active |
| FRED API | Macro indicators | Ongoing | ✅ Active |

## Active Model Locations

```
models/
├── core_v15/           # ACTIVE - Production Core (5d, 21d, 63d trained)
│   ├── horizon_5d/     # learner.pkl, predictor.pkl
│   ├── horizon_21d/
│   └── horizon_63d/
├── core_chronos2/      # ACTIVE - Chronos-2 variants (all 4 horizons)
│   ├── horizon_5d/
│   ├── horizon_21d/
│   ├── horizon_63d/
│   └── horizon_126d/
├── specialists/        # NOT YET TRAINED - Big 11 specialists
└── hunters/            # NOT YET TRAINED - Opportunity hunters
```

## Model ID Convention (Stable)

All SoT v2 models use a consistent, horizon-qualified `model_id`:

- **L0 core:** `zinc-fusion-v2-core-h{H}d`
- **L0 specialist:** `zinc-fusion-v2-specialist-{bucket}-h{H}d`
- **L1 meta:** `zinc-fusion-v2-meta-h{H}d`
- **L2 calibration module (non-model):** `zinc-fusion-v2-calibration-cqr-h{H}d`
- **L3 risk engine module (non-model):** `zinc-fusion-v2-risk-mc-h{H}d`

`{bucket}` ∈ `{crush, china, fx, fed, tariff, energy, biofuel, palm, volatility, substitutes, trump_effect}`

## L0 Base Models (48 model instances → 12 OOF tables)

Each horizon has 12 base models (Core + 11 Specialists). Each base model produces OOF quantiles.

**Schema Design:** All horizons for a given model write to a **single table** with `horizon_days` as discriminator column. This follows institutional patterns for training artifacts (cross-horizon queries, meta-learner aggregation).

- Output tables: `training.oof_{model}_1d` (12 tables total)
- Discriminator: `horizon_days` column (5, 21, 63, 126)
- Columns: `trade_date`, `symbol`, `horizon_days`, `window_id`, `cutoff_date`, `p30`, `p50`, `p70`, `target_value`, `trained_at`, `run_hash`, `matrix_version`
- Unique constraint: `(trade_date, symbol, horizon_days, window_id)`

### OOF Table Inventory (12 tables)

| Table | Model IDs (all 4 horizons) |
|-------|---------------------------|
| `training.oof_core_1d` | `zinc-fusion-v2-core-h{5,21,63,126}d` |
| `training.oof_crush_1d` | `zinc-fusion-v2-specialist-crush-h{5,21,63,126}d` |
| `training.oof_china_1d` | `zinc-fusion-v2-specialist-china-h{5,21,63,126}d` |
| `training.oof_fx_1d` | `zinc-fusion-v2-specialist-fx-h{5,21,63,126}d` |
| `training.oof_fed_1d` | `zinc-fusion-v2-specialist-fed-h{5,21,63,126}d` |
| `training.oof_tariff_1d` | `zinc-fusion-v2-specialist-tariff-h{5,21,63,126}d` |
| `training.oof_energy_1d` | `zinc-fusion-v2-specialist-energy-h{5,21,63,126}d` |
| `training.oof_biofuel_1d` | `zinc-fusion-v2-specialist-biofuel-h{5,21,63,126}d` |
| `training.oof_palm_1d` | `zinc-fusion-v2-specialist-palm-h{5,21,63,126}d` |
| `training.oof_volatility_1d` | `zinc-fusion-v2-specialist-volatility-h{5,21,63,126}d` |
| `training.oof_substitutes_1d` | `zinc-fusion-v2-specialist-substitutes-h{5,21,63,126}d` |
| `training.oof_trump_effect_1d` | `zinc-fusion-v2-specialist-trump_effect-h{5,21,63,126}d` |

### Training Script Pattern

```python
# Each model trains all 4 horizons, writes to SAME table
for horizon in [5, 21, 63, 126]:
    model = train_specialist(horizon=horizon)
    oof_df = model.get_oof_predictions()
    oof_df['horizon_days'] = horizon

    # All horizons → same table
    INSERT INTO training.oof_{specialist}_1d
    ON CONFLICT (trade_date, symbol, horizon_days, window_id) DO UPDATE
```

### Querying OOF by Horizon

```sql
-- Get 21d OOF predictions for crush specialist
SELECT * FROM training.oof_crush_1d WHERE horizon_days = 21;

-- Compare all horizons for core model
SELECT horizon_days, AVG(ABS(p50 - target_value)) as mae
FROM training.oof_core_1d
GROUP BY horizon_days;
```

## L1 Meta Models (4)

Meta models consume **OOF quantiles only** (hard rule) from the 12 base models for the same horizon.

- Input table: `training.meta_inputs_1d` (single table with `horizon_days` discriminator, contains 12×3 quantile columns + minimal regime/calendar features)
- Output tables: `forecasts.production_{H}d_1d`

Models:
- `zinc-fusion-v2-meta-h5d` → `training.meta_inputs_1d WHERE horizon_days=5` → `forecasts.production_5d_1d`
- `zinc-fusion-v2-meta-h21d` → `training.meta_inputs_1d WHERE horizon_days=21` → `forecasts.production_21d_1d`
- `zinc-fusion-v2-meta-h63d` → `training.meta_inputs_1d WHERE horizon_days=63` → `forecasts.production_63d_1d`
- `zinc-fusion-v2-meta-h126d` → `training.meta_inputs_1d WHERE horizon_days=126` → `forecasts.production_126d_1d`

## L2 Calibration Modules (4, non-model)

Calibration writes **outer** `p10_cal`, `p90_cal` into the same `forecasts.production_{H}d_1d` table.

## L3 Risk Engine Modules (4, non-model)

Risk engine derives barrier/touch probabilities and scenario path sampling; its outputs are expected to populate:
- `analytics.risk_metrics` (and/or the SoT v2 scenario tables)

