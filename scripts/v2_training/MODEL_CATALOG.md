# SoT v2 Model Catalog (Core + Specialists + Meta)

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
├── core_v2/            # ACTIVE - Core (CPU-only, full Model Zoo allowlist)
├── specialists/        # v3 SIGNAL GENERATORS - Custom models per bucket
```

**Retention:** Only `models/core_v2` and `models/specialists` are kept under `models/`.

### Core Training Policy (CPU-only, Full Model Zoo)

Core runs **CPU-only** (no MPS, no CUDA). Set guards **before** importing torch/autogluon:

```
TOKENIZERS_PARALLELISM=false
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
AUTOGLUON_DISABLE_RAY=1
PYTORCH_ENABLE_MPS_FALLBACK=1
device = "cpu"
```

Core must try **ALL** AutoGluon-TimeSeries Model Zoo models via an explicit
`hyperparameters={...}` allowlist (model names may omit the “Model” suffix).
The full allowlist is maintained in `Docs/CORE_TRAINING_SPEC_LOCKED.md`.

AutoGluon trains the full allowlist, ranks models on validation/backtests, and
typically selects a **WeightedEnsemble** as best. No time limits are used.

Verification:
- `python -m fusion.core_training.run_pipeline --skip-matrix --horizons 5`
- `python -m fusion.core_training.run_pipeline --skip-matrix`
- Confirm logs show the full allowlist and a WeightedEnsemble selection

## Specialist Signal Generators (v3 Architecture)

> **CRITICAL**: Specialists are SIGNAL GENERATORS, not forecasters.
> Each has a UNIQUE model architecture. Core owns all horizon forecasting.
> Full details: `docs/SPECIALIST_MODEL_REGISTRY.md`

| Specialist | Class | File | Model Type |
|------------|-------|------|------------|
| `crush` | `CrushSignalGenerator` | `xgb_signals.py` | `xgb` |
| `china` | `ChinaSignalGenerator` | `xgb_signals.py` | `gbm` |
| `substitutes` | `SubstitutesSignalGenerator` | `xgb_signals.py` | `rf` |
| `fx` | `FxSignalGenerator` | `ardl_signals.py` | `ardl` |
| `fed` | `FedSignalGenerator` | `ardl_signals.py` | `ridge` |
| `volatility` | `VolatilitySignalGenerator` | `garch_signals.py` | `garch` |
| `energy` | `EnergySignalGenerator` | `var_signals.py` | `var` |
| `palm` | `PalmSignalGenerator` | `ecm_signals.py` | `ecm` |
| `tariff` | `TariffSignalGenerator` | `event_signals.py` | `tree` |
| `biofuel` | `BiofuelSignalGenerator` | `event_signals.py` | `nlp_ema` |
| `trump_effect` | `TrumpEffectSignalGenerator` | `event_signals.py` | `event_study` |

**Code**: `src/fusion/specialists/` | **Artifacts**: `models/specialists/{bucket}/`

## Model ID Convention (Stable)

All SoT v2 models use a consistent naming convention:

- **L0 core:** `zinc-fusion-v2-core-h{H}d`
- **L0 specialist (signals only):** `zinc-fusion-v2-specialist-{bucket}`
- **L1 meta:** `zinc-fusion-v2-meta-h{H}d`
- **L2 calibration module (non-model):** `zinc-fusion-v2-calibration-cqr-h{H}d`
- **L3 risk engine module (non-model):** `zinc-fusion-v2-risk-mc-h{H}d`

`{bucket}` ∈ `{crush, china, fx, fed, tariff, energy, biofuel, palm, volatility, substitutes, trump_effect}`

## L0 Components (Core OOF + Specialist Signals)

Core produces OOF quantiles per horizon. Specialists produce horizon-agnostic signals.

**Schema Design:** Core OOF uses a single table with `horizon_days`. Specialist outputs
are signals written to `training.specialist_signals_1d`.

### Core OOF Table

| Table | Model IDs (all 4 horizons) |
|-------|---------------------------|
| `training.oof_core_1d` | `zinc-fusion-v2-core-h{5,21,63,126}d` |

### Specialist Signals Table

| Table | Purpose |
|-------|---------|
| `training.specialist_signals_1d` | `signal_1`, `signal_2` (optional), `confidence` (optional) |

### Training Script Pattern

```python
# Core trains all 4 horizons, writes to SAME table
for horizon in [5, 21, 63, 126]:
    model = train_core(horizon=horizon)
    oof_df = model.get_oof_predictions()
    oof_df["horizon_days"] = horizon

    INSERT INTO training.oof_core_1d
    ON CONFLICT (trade_date, symbol, horizon_days, window_id) DO UPDATE

# Specialists write signals (no horizons)
INSERT INTO training.specialist_signals_1d
```

### Querying Core OOF + Signals

```sql
-- Compare all horizons for core model
SELECT horizon_days, AVG(ABS(p50 - target_value)) as mae
FROM training.oof_core_1d
GROUP BY horizon_days;
```

## L1 Meta Models (4)

Meta models consume **Core OOF quantiles + specialist signals** for the same horizon.

- Input table: `training.meta_inputs_1d` (single table with `horizon_days` discriminator, contains core OOF + specialist signals + minimal regime/calendar features)
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
