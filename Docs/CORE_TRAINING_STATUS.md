# ZINC-FUSION-V15: Core Training Status & Requirements

**Date:** 2026-01-03
**Status:** IN PROGRESS - V15 compliance requirements documented

---

## Current State

### Trained Models (V15 Architecture)

Located at: `models/core_v15/`

| Horizon | Models Present | V15 Compliant |
|---------|----------------|---------------|
| 5d | Chronos-Bolt, DirectTabular, RecursiveTabular, ETS, Theta, SeasonalNaive, WeightedEnsemble | YES |
| 21d | Chronos-Bolt, DirectTabular, RecursiveTabular, ETS, Theta, SeasonalNaive, WeightedEnsemble | YES |
| 63d | Models present but not fully verified | NEEDS VERIFICATION |
| 126d | Not found | NO |

### Database Tables

| Table | Status | Description |
|-------|--------|-------------|
| `model.oof_predictions` | 3,262 rows | OOF backtests (historical) |
| `model.forecast_quantiles` | 0 rows | **EMPTY - Dashboard needs this** |
| `model.garch_forecasts` | 0 rows | Empty |
| `analytics.risk_metrics` | 1,000 rows | Has data |
| `model.model_core_audit` | **NEEDS CREATION** | Added to schema, not pushed |

---

## V15 Core Architecture (Authoritative)

### Horizon-Specific Model Portfolio

**5d (Tactical):**
- Chronos-Bolt (univariate speed anchor)
- DirectTabular (covariate reasoning)
- RecursiveTabular (autoregressive)
- AutoETS, Theta, SeasonalNaive (statistical baselines)
- WeightedEnsemble (OOF only)

**21d (Tactical → Transitional):**
- Same as 5d
- RecursiveTabular with decay

**63d (Strategic):**
- Chronos-2 (LoRA fine-tuned) - DOMINANT
- DirectTabular
- AutoETS, Theta, SeasonalNaive
- NO RecursiveTabular
- NO Chronos-Bolt

**126d (Strategic / Procurement):**
- Same as 63d

### Non-Negotiable Rules

1. **Autoregression cutoff**: ~21 days. RecursiveTabular disabled for 63d/126d.
2. **Monte Carlo**: 10,000+ runs required for P10/P50/P90 output.
3. **WeightedEnsemble**: OOF only, no single model >70% weight.
4. **Audit**: Every run must write to `model_core_audit` table.

---

## Training Scripts

### Primary Script: `scripts/train_core_v15.py`

This is the V15-compliant training script that implements:
- Correct horizon-specific model portfolios
- Cascading horizon strategy (tactical vs strategic)
- Hardware abstraction (MPS/CUDA/CPU)
- ALL DATA policy compliance

### Alternative Scripts (Use with Caution)

- `scripts/train_core_chronos.py` - Chronos-2 + AutoGluon (may not be V15-compliant)
- `scripts/train_core_direction.py` - Direction prediction only (not for quantiles)

---

## Audit Table Schema

Added to `prisma/schema.prisma` but **NOT YET PUSHED** to database.

```sql
-- model.model_core_audit
-- Every Core training run must write exactly one row
-- CI and release gates read from this table

-- HARD GATES (must all be true):
- is_core_run
- cv_purged_walk_forward
- asof_alignment_valid
- Horizon-correct Chronos configuration
- All three statistical baselines present
- weighted_ensemble_used = true
- oof_only = true
- monte_carlo_runs >= 10000
- p10_present AND p50_present AND p90_present
- registry_complete = true

-- FINAL VERDICT:
- hard_gate_pass = true AND narrative_ready = true
  → final_approved = true
```

---

## Steps to Complete Core Training

### 1. Push Prisma Schema
```bash
npx prisma db push
```

### 2. Run V15-Compliant Training
```bash
# For 21d horizon
python scripts/train_core_v15.py --horizon 21

# For all horizons
python scripts/train_core_v15.py --horizon all
```

### 3. Run Monte Carlo Simulation
```bash
# Requires meta-ensemble predictions first
python scripts/run_monte_carlo.py --horizon 21
```

### 4. Generate Forward Forecasts
```bash
# Populates model.forecast_quantiles for dashboard
python scripts/generate_core_forecasts.py --horizon 21
```

### 5. Write Audit Record
Training script should automatically write to `model_core_audit` with:
- All gate checks
- Final approval status
- Training run ID

---

## Blockers

1. **Prisma schema not pushed** - `model_core_audit` table doesn't exist yet
2. **Monte Carlo dependency** - Needs L4 meta-ensemble predictions
3. **Pipeline incomplete** - L2 (Core) → L3 (Specialists) → L4 (Meta) → L5 (MC)

### Workaround for Dashboard

For immediate dashboard needs, we can:
1. Use existing V15 models directly
2. Generate forecasts without full pipeline
3. Defer Monte Carlo and audit compliance

This provides a working dashboard but is **NOT V15 APPROVED** until full audit compliance.

---

## CI/CD Integration

### Merge-Block Rule

No PR may merge unless every referenced Core training run has:
- `final_approved = true` in `model_core_audit`

### GitHub Actions

See `.github/workflows/core-model-gate.yml` for enforcement workflow.

### Branch Protection

- Require status check: "Core Model Approval Gate"
- No admin bypass
- No force-push overrides

---

## Next Actions (Priority Order)

1. Push Prisma schema to create audit table
2. Test existing V15 21d model with forecast generation
3. Validate forecast output format for dashboard
4. Run Monte Carlo for risk metrics
5. Write audit record for training run
6. Full pipeline validation

---

## Data Availability by Horizon (CRITICAL)

**Updated:** 2026-01-05

Strategic training (63d/126d) uses ALL data from 2000+. Only series that fundamentally didn't exist are excluded.

### Classification

| Category | Rule | Examples |
|----------|------|----------|
| **Use for ALL horizons** | Data exists from 2000+ | ZL, VIXCLS, DGS10, FEDFUNDS, M2SL, OVXCLS |
| **Proxy needed** | Data didn't exist before date | SOFR (→FEDFUNDS), VXGSCLS (→VIXCLS) |
| **Backfill needed** | Data exists but not in DB | M2SL, OVXCLS, USDA WASDE |

### Backfill Priorities (URGENT)

| Series | DB Has | FRED Has | Gap |
|--------|--------|----------|-----|
| **M2SL** | 2023-12 | 1959-01 | **64 years** |
| **OVXCLS** | 2023-12 | 2007-05 | **16 years** |
| **USDA WASDE** | 2020-01 | ~2010 | **10 years** |

### Fundamentally Limited (Cannot Backfill)

| Series | Start Date | Reason | Strategic Proxy |
|--------|------------|--------|-----------------|
| **SOFR** | 2018-04-03 | Fed created to replace LIBOR | FEDFUNDS |
| **VXGSCLS** | 2020-07-24 | CBOE Gold VIX launched | VIXCLS |

### Training Script Rule

```python
# Strategic (63d/126d) - use ALL available data from 2000+
# Only apply proxies for series that fundamentally didn't exist

if series == "SOFR" and as_of_date < "2018-04-03":
    use_proxy("FEDFUNDS")  # SOFR didn't exist

# M2SL, OVXCLS - use directly once backfilled (data exists from 1959, 2007)
```

### Reference Document

Full data availability rules: `.claude/skills/zf-pipeline-contracts/references/data_availability_by_horizon.md`

---

## Files Reference

| File | Purpose |
|------|---------|
| `scripts/train_core_v15.py` | V15-compliant Core training |
| `scripts/generate_core_forecasts.py` | Generate forward forecasts |
| `scripts/run_monte_carlo.py` | L5-A Monte Carlo simulation |
| `scripts/run_pipeline.py` | Full L2→L5 pipeline orchestrator |
| `prisma/schema.prisma` | Database schema (includes audit table) |
| `docs/SPECIALIST_TRAINING_STATUS.md` | Specialist training issues (deferred) |
| `.claude/skills/.../data_availability_by_horizon.md` | Data tiering rules |

