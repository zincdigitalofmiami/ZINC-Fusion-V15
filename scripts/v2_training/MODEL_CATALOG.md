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

## L0 Base Models (48)

Each horizon has 12 base models (Core + 11 Specialists). Each base model produces OOF quantiles:

- Output tables: `training.oof_{model}_{H}d_1d`
- Columns: `{model}_p30`, `{model}_p50`, `{model}_p70`, `target_{H}d`, `fold_id`, `model_version`

### Horizon 5d
- `zinc-fusion-v2-core-h5d` → `training.oof_core_5d_1d`
- `zinc-fusion-v2-specialist-crush-h5d` → `training.oof_crush_5d_1d`
- `zinc-fusion-v2-specialist-china-h5d` → `training.oof_china_5d_1d`
- `zinc-fusion-v2-specialist-fx-h5d` → `training.oof_fx_5d_1d`
- `zinc-fusion-v2-specialist-fed-h5d` → `training.oof_fed_5d_1d`
- `zinc-fusion-v2-specialist-tariff-h5d` → `training.oof_tariff_5d_1d`
- `zinc-fusion-v2-specialist-energy-h5d` → `training.oof_energy_5d_1d`
- `zinc-fusion-v2-specialist-biofuel-h5d` → `training.oof_biofuel_5d_1d`
- `zinc-fusion-v2-specialist-palm-h5d` → `training.oof_palm_5d_1d`
- `zinc-fusion-v2-specialist-volatility-h5d` → `training.oof_volatility_5d_1d`
- `zinc-fusion-v2-specialist-substitutes-h5d` → `training.oof_substitutes_5d_1d`
- `zinc-fusion-v2-specialist-trump_effect-h5d` → `training.oof_trump_effect_5d_1d`

### Horizon 21d
- `zinc-fusion-v2-core-h21d` → `training.oof_core_21d_1d`
- `zinc-fusion-v2-specialist-crush-h21d` → `training.oof_crush_21d_1d`
- `zinc-fusion-v2-specialist-china-h21d` → `training.oof_china_21d_1d`
- `zinc-fusion-v2-specialist-fx-h21d` → `training.oof_fx_21d_1d`
- `zinc-fusion-v2-specialist-fed-h21d` → `training.oof_fed_21d_1d`
- `zinc-fusion-v2-specialist-tariff-h21d` → `training.oof_tariff_21d_1d`
- `zinc-fusion-v2-specialist-energy-h21d` → `training.oof_energy_21d_1d`
- `zinc-fusion-v2-specialist-biofuel-h21d` → `training.oof_biofuel_21d_1d`
- `zinc-fusion-v2-specialist-palm-h21d` → `training.oof_palm_21d_1d`
- `zinc-fusion-v2-specialist-volatility-h21d` → `training.oof_volatility_21d_1d`
- `zinc-fusion-v2-specialist-substitutes-h21d` → `training.oof_substitutes_21d_1d`
- `zinc-fusion-v2-specialist-trump_effect-h21d` → `training.oof_trump_effect_21d_1d`

### Horizon 63d
- `zinc-fusion-v2-core-h63d` → `training.oof_core_63d_1d`
- `zinc-fusion-v2-specialist-crush-h63d` → `training.oof_crush_63d_1d`
- `zinc-fusion-v2-specialist-china-h63d` → `training.oof_china_63d_1d`
- `zinc-fusion-v2-specialist-fx-h63d` → `training.oof_fx_63d_1d`
- `zinc-fusion-v2-specialist-fed-h63d` → `training.oof_fed_63d_1d`
- `zinc-fusion-v2-specialist-tariff-h63d` → `training.oof_tariff_63d_1d`
- `zinc-fusion-v2-specialist-energy-h63d` → `training.oof_energy_63d_1d`
- `zinc-fusion-v2-specialist-biofuel-h63d` → `training.oof_biofuel_63d_1d`
- `zinc-fusion-v2-specialist-palm-h63d` → `training.oof_palm_63d_1d`
- `zinc-fusion-v2-specialist-volatility-h63d` → `training.oof_volatility_63d_1d`
- `zinc-fusion-v2-specialist-substitutes-h63d` → `training.oof_substitutes_63d_1d`
- `zinc-fusion-v2-specialist-trump_effect-h63d` → `training.oof_trump_effect_63d_1d`

### Horizon 126d
- `zinc-fusion-v2-core-h126d` → `training.oof_core_126d_1d`
- `zinc-fusion-v2-specialist-crush-h126d` → `training.oof_crush_126d_1d`
- `zinc-fusion-v2-specialist-china-h126d` → `training.oof_china_126d_1d`
- `zinc-fusion-v2-specialist-fx-h126d` → `training.oof_fx_126d_1d`
- `zinc-fusion-v2-specialist-fed-h126d` → `training.oof_fed_126d_1d`
- `zinc-fusion-v2-specialist-tariff-h126d` → `training.oof_tariff_126d_1d`
- `zinc-fusion-v2-specialist-energy-h126d` → `training.oof_energy_126d_1d`
- `zinc-fusion-v2-specialist-biofuel-h126d` → `training.oof_biofuel_126d_1d`
- `zinc-fusion-v2-specialist-palm-h126d` → `training.oof_palm_126d_1d`
- `zinc-fusion-v2-specialist-volatility-h126d` → `training.oof_volatility_126d_1d`
- `zinc-fusion-v2-specialist-substitutes-h126d` → `training.oof_substitutes_126d_1d`
- `zinc-fusion-v2-specialist-trump_effect-h126d` → `training.oof_trump_effect_126d_1d`

## L1 Meta Models (4)

Meta models consume **OOF quantiles only** (hard rule) from the 12 base models for the same horizon.

- Input tables: `training.meta_inputs_{H}d_1d` (join of the 12×3 quantile columns + minimal regime/calendar features)
- Output tables: `forecasts.production_{H}d_1d`

Models:
- `zinc-fusion-v2-meta-h5d` → `training.meta_inputs_5d_1d` → `forecasts.production_5d_1d`
- `zinc-fusion-v2-meta-h21d` → `training.meta_inputs_21d_1d` → `forecasts.production_21d_1d`
- `zinc-fusion-v2-meta-h63d` → `training.meta_inputs_63d_1d` → `forecasts.production_63d_1d`
- `zinc-fusion-v2-meta-h126d` → `training.meta_inputs_126d_1d` → `forecasts.production_126d_1d`

## L2 Calibration Modules (4, non-model)

Calibration writes **outer** `p10_cal`, `p90_cal` into the same `forecasts.production_{H}d_1d` table.

## L3 Risk Engine Modules (4, non-model)

Risk engine derives barrier/touch probabilities and scenario path sampling; its outputs are expected to populate:
- `analytics.risk_metrics` (and/or the SoT v2 scenario tables)

