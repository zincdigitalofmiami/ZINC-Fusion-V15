# 🎯 ZINC-FUSION-V15 Migration Executive Summary

**Date**: 2026-01-18  
**Status**: PLANNING COMPLETE - AWAITING APPROVAL TO EXECUTE

---

## Critical Findings

### 1. MLflow is Completely Redundant ❌

**Verdict**: Remove immediately.

**Why**:
- `grafana/grafana_registry.py` already writes to Prisma (`model.training_runs`, `model.model_registry`)
- Grafana dashboards query Prisma directly
- MLflow adds operational overhead (PostgreSQL, MinIO, sync scripts)
- No active training scripts use MLflow

**Impact**: 1-2 days to remove, zero functional loss.

---

### 2. Schema Migration Required 🔄

**Current State**: Mixed medallion (`raw.*`, `gold.*`, `silver.*`) and institutional schemas

**Target State**: 100% institutional schemas (mkt/econ/pos/supply/alt/features/training/model)

**Scope**:
- 50+ files need updates (API, ingestion, training, validators)
- ~200+ legacy schema references to migrate
- 11 specialist buckets to validate

**Impact**: 3-5 days, requires careful sequencing.

---

### 3. Training Pipeline is 80% Ready ✅

**What Works**:
- ✅ Feature engineering modules exist
- ✅ Matrix builder operational
- ✅ Core training scripts functional
- ✅ OOF table schemas defined

**What Needs Work**:
- ⚠️ Schema references need migration
- ⚠️ Specialist feature routing needs validation
- ⚠️ Meta-ensemble needs implementation

**Impact**: 2-3 days to validate and test.

---

## Recommended Timeline

**Total**: 8-13 days

| Phase | Duration | Risk |
|-------|----------|------|
| 1. MLflow Removal | 1-2 days | Low |
| 2. API Migration | 1-2 days | Medium |
| 3. Ingestion Migration | 1-2 days | Medium |
| 4. Training Migration | 2-3 days | High |
| 5. Validator Migration | 1 day | Low |
| 6. Production Hardening | 1-2 days | Low |

---

## Key Decisions Needed

### Decision 1: Whitehouse Actions Table

**Issue**: `raw.whitehouse_actions_event` has no V2 equivalent

**Options**:
- A) Migrate to `alt.news_1d` with `source='WHITEHOUSE'` ← **RECOMMENDED**
- B) Create `alt.whitehouse_event` (requires schema approval)

### Decision 2: News Sentiment Scores

**Issue**: `silver.news_scored_1d` must be eliminated (`silver` schema banned) and the target is `alt.news_scored_1d`, which is not currently defined in Prisma.

**Options**:
- A) Create `alt.news_scored_1d` and migrate `silver.news_scored_1d` into it (**requires schema approval**) ← **RECOMMENDED**
- B) Merge into `alt.news_1d` (only if you explicitly override the `alt.news_scored_1d` decision)

### Decision 3: Forecast Output Schema

**Issue**: Code writes to `model.forecast_quantiles`, Prisma defines `forecasts.forecast_quantiles`

**Options**:
- A) Align code to Prisma (`forecasts.*`) ← **RECOMMENDED**
- B) Migrate Prisma to `model.*` (requires schema approval)

---

## Success Criteria (All Must Pass)

- ✅ Zero MLflow dependencies
- ✅ Zero `raw.*`, `gold.*`, `silver.*` references in code
- ✅ All ingestion writes to institutional schemas
- ✅ Training pipeline builds matrices from `features.*`
- ✅ OOF predictions in standardized format (p30/p50/p70)
- ✅ Grafana monitoring operational
- ✅ System ready for 52-model training (4 Core + 44 Specialists + 4 Meta)

---

## Risk Mitigation

**Pre-Migration**:
- Full database backup
- Canary deployment on test database
- Rollback procedure documented

**During Migration**:
- Validation checkpoint after each phase
- Staged rollout (dev → staging → production)
- Real-time monitoring

**Post-Migration**:
- 24-hour monitoring period
- Team training on new architecture
- Documentation updates

---

## Next Steps

1. **Review** this plan and `PRODUCTION_READINESS_PLAN.md`
2. **Approve** key decisions (whitehouse, sentiment, forecast schema)
3. **Schedule** migration window (recommend off-hours)
4. **Execute** Phase 1 (MLflow removal) as proof of concept
5. **Proceed** with remaining phases if Phase 1 successful

---

**Full Details**: See `PRODUCTION_READINESS_PLAN.md` (1400+ lines)

**Questions**: Contact development team before proceeding.

