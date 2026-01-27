NOTE: Production is the dashboard/frontend, not the repo root.
## SoT v2 Training (Code Location)

This folder is the **designated home** for the **SoT v2 (P30/P50/P70 + CQR P10_cal/P90_cal)** training stack.

Goals:
- Keep **SoT v2 model code** isolated from legacy v15 scripts for clarity and safe iteration.
- Use **Prisma Postgres** tables as the system of record (no local-only training outputs).
- Enforce **no synthetic / no fallback** behavior: empty outputs are preferred over invented values.

### Data Sources (LOCKED)
| Source | Role | Status |
|--------|------|--------|
| Historical Backfill | 1990 → 2025-12-29 | ✅ COMPLETE |
| Yahoo Finance | Daily topfill | ✅ Active |
| FRED API | Macro indicators | ✅ Active |

### Active Model Locations
```
models/
├── core_v2/            # ACTIVE - Core (CPU-only, full Model Zoo allowlist)
├── specialists/        # Specialist signal generators
```

**Retention:** Only `models/core_v2` and `models/specialists` are kept under `models/`.

**Note:** Core training uses `fusion.core_training` with an explicit Model Zoo
allowlist and CPU-only execution. Legacy `core_v15` / `core_chronos2` paths are
removed.

### Core Training Policy (CPU-only, Full Model Zoo)

Core runs on CPU. Set guards **before** importing torch/autogluon:

```
TOKENIZERS_PARALLELISM=false
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
AUTOGLUON_DISABLE_RAY=1
PYTORCH_ENABLE_MPS_FALLBACK=1
PYTORCH_MPS_ENABLED=0
CUDA_VISIBLE_DEVICES=""
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

### Model Catalog
See `scripts/v2_training/MODEL_CATALOG.md` for the full list of:
- Core (4 horizons) + 11 specialist signal generators + L1 meta (4 horizons)
- Their **model_id** naming convention
- Their **input/output table contracts** (core OOF → specialist signals → meta_inputs → forecasts.production → analytics scenarios)

### Output Table Families (SoT v2)
These tables already exist in Prisma and are expected to be **empty prior to first training run**:
- `training.oof_*_1d` (12 tables with `horizon_days` column — one per model type, all horizons in same table)
- `training.meta_inputs_1d` (1 table with `horizon_days` column)
- `forecasts.production_{5d,21d,63d,126d}_1d` (4 tables — separate per horizon for production outputs)
- `analytics.event_probabilities_{5d,21d,63d,126d}_1d` (4 tables)
- `analytics.price_scenarios_{5d,21d,63d,126d}_1d` (4 tables)

**Schema Design Note:** Core OOF uses a single table with `horizon_days`. Specialist signals live in `training.specialist_signals_1d`. Production outputs use separate tables per horizon for consumer isolation.

### Pre-Training Readiness
Before running Core training, use:
```bash
python -m fusion.core_training.run_pipeline --skip-matrix --horizons 5
```