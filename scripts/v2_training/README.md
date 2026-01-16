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
├── core_v15/           # ACTIVE - Core models (5d, 21d, 63d)
├── core_chronos2/      # ACTIVE - Chronos-2 variants (all 4 horizons)
├── specialists/        # NOT YET TRAINED
└── hunters/            # NOT YET TRAINED
```

### Model Catalog
See `scripts/v2_training/MODEL_CATALOG.md` for the full list of:
- 52 horizon-aligned models (L0 core + 11 specialists × 4 horizons + L1 meta × 4 horizons)
- Their **model_id** naming convention
- Their **input/output table contracts** (OOF → meta_inputs → forecasts.production → analytics scenarios)

### Output Table Families (SoT v2)
These tables already exist in Prisma and are expected to be **empty prior to first training run**:
- `training.oof_*_{5d,21d,63d,126d}_1d` (48 tables)
- `training.meta_inputs_{5d,21d,63d,126d}_1d` (4 tables)
- `forecasts.production_{5d,21d,63d,126d}_1d` (4 tables)
- `analytics.event_probabilities_{5d,21d,63d,126d}_1d` (4 tables)
- `analytics.price_scenarios_{5d,21d,63d,126d}_1d` (4 tables)

### Pre-Training Readiness
Before running any v2 training jobs, run:
```bash
python3 scripts/pretrain_readiness_audit.py --strict
```
and resolve blockers (core matrix population, target columns, stale inputs).

### Best-Practices Review
See `Docs/SOT_V2_TRAINING_BEST_PRACTICES_REVIEW_2026_01_14.md` for a pre-execution review of the SoT v2 training plan and the explicit decisions/gates to lock before training.
