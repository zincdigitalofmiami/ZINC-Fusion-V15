# Training Prep Checklist - January 15, 2026

**Goal:** Prepare SoT v2 (52-model architecture) for first training run TODAY

---

## ✅ **COMPLETED (Pre-Prep)**
- [x] Legacy scripts moved to `scripts/legacy/`
- [x] 65 old models archived in registry
- [x] Training matrix populated: **6,622 rows** in `training.core_matrix_1d`
- [x] All 4 targets present: `target_5d`, `target_21d`, `target_63d`, `target_126d`
- [x] Specialist features generated: **6,627 rows** per bucket (11 buckets)
- [x] 48 OOF tables exist (empty, as expected)
- [x] OOF schema verified: Each OOF table has ALL 4 targets (not just its horizon)

---

## 🔴 **CRITICAL BLOCKE~~ ✅ VERIFIED AT SOURCE
**Database reality (verified via psql):**

```sql
-- training.core_matrix_1d: 6,622 rows
-- Columns: target_5d, target_21d, target_63d, target_126d ✅

-- training.oof_core_5d_1d (and all 48 OOF tables):
-- Columns: {model}_p30, {model}_p50, {model}_p70, 
--          target_5d, target_21d, target_63d, target_126d,
--          fold_id, model_version, created_at ✅

-- Specialist feature source:
-- training.specialist_features: JSON blob per (bucket, as_of_date)
-- Legacy script: Loads features from JSON, JOINs targets from core_matrix
```

**Training data flow (verified from legacy/train_specialist.py):**
1. Load specialist features from `training.specialist_features` (JSON)
2. Load ZL prices from `raw.market_futures_1d` 
3. Calculate forward returns: `(price_t+h / price_t) - 1`
4. Merge features + returns + fold assignments
5. Train AutoGluon model
6. Write OOF predictions with ALL 4 targets to `training.oof_*_{H}d_1d`

**No blockers** - All target infrastructure exis

**No action required** - training scripts will JOIN specialist features to core targets

---

### 2. EPA RIN Data Stale (31 days) ⚠️
**Status:** `raw.epa_rin_prices_1d` last update: 2025-12-15 (31 days old)

**Fix options:**
- Skip biofuel specialist for first run (train other 10 specialists)
- OR refresh EPA data via Inngest job
- OR use last known values (forward-fill acceptable for monthly EPA data)

**Decision:** Can train without this for first run

---

## 🟡 **MEDIUM PRIORITY (Nice to Have)**

### 3. Market Data Freshness (6 days stale)
- `raw.market_futures_1d` latest: 2026-01-09 (today is 2026-01-15)
- Missing 6 trading days of data

**Impact:** Training will use data through Jan 9 instead of Jan 15

**Fix:**
```bash
python scripts/ingest_yahoo_eod.py  # Backfill last 6 days
```

**Decision:** Can train with current data, refresh after first run

---

### 4. Symbol Mapping Incomplete
- 97 of 104 symbols not in `metadata.symbol_mapping`
- Core training uses ZL only, so not blocking

**Decision:** Skip for now

---

## 🎯 **TRAINING EXECUTION PLAN**

### Phase 1: Build SoT v2 Training Scripts (TODAY)

**Required scripts** (must write to proper tables with p30/p50/p70):

```bash
scripts/v2_training/
├── train_l0_core.py          # → training.oof_core_{H}d_1d
├── train_l0_specialist.py    # → training.oof_{bucket}_{H}d_1d
└── train_l1_meta.py          # → forecasts.production_{H}d_1d
```

**Key requirements:**
- Write to `training.oof_*` tables (NOT `model.oof_predictions`)
- Use quantiles: `p30, p50, p70` (NOT p10/p50/p90)
- No `-v2-` naming prefix in model IDs
- Each specialist bucket writes to its own table

---

### Phase 2: Quick Smoke Test (1 hour)

**Test sequence:**
```bash
# 1. Train L0 Core (1 horizon, quick mode)
python scripts/v2_training/train_l0_core.py --horizon 21 --mode quick

# 2. Verify OOF table populated
# Check: training.oof_core_21d_1d has rows with p30/p50/p70

# 3. Train 1 specialist (crush, quick mode)
python scripts/v2_training/train_l0_specialist.py --bucket crush --horizon 21 --mode quick

# 4. Verify specialist OOF
# Check: training.oof_crush_21d_1d has rows

# 5. Build meta inputs
python scripts/v2_training/build_meta_inputs.py --horizon 21

# 6. Train L1 meta
python scripts/v2_training/train_l1_meta.py --horizon 21 --mode quick
```

**Success criteria:**
- ✅ training.oof_core_21d_1d: 100+ rows with p30/p50/p70
- ✅ training.oof_crush_21d_1d: 100+ rows
- ✅ training.meta_inputs_21d_1d: 100+ rows (12 OOF quantile columns)
- ✅ forecasts.production_21d_1d: 100+ rows

---

### Phase 3: Full Training (8-12 hours)

**If smoke test passes:**
```bash
# Train all 48 L0 models (4 horizons × 12 models)
./scripts/v2_training/train_all_l0.sh

# Train all 4 L1 meta models
./scripts/v2_training/train_all_l1.sh
```

---

## 📋 **IMMEDIATE TODO (Next 2 Hours)**

### Priority 1: Fix Specialist Target Columns
- [ ] Verify if `populate_core_matrix.py` adds targets to specialist tables
- [ ] If not, create script to add target columns
- [ ] Test on one specialist table first (crush)
- [ ] Apply to all 11 specialists

### Priority 2: Create Training Scripts
- [ ] Copy useful code from `scripts/legacy/train_core_tactical.py`
- [ ] Adapt to write to `training.oof_core_{H}d_1d` 
- [ ] Change quantiles from 0.1/0.5/0.9 → 0.3/0.5/0.7
- [ ] Test with dry-run mode first

### Priority 3: Validation Script
- [ ] Create `scripts/v2_training/validate_oof_output.py`
- [ ] Check quantile ordering (p30 < p50 < p70)
- [ ] Check coverage rates
- [ ] Verify table schema matches spec

---

## 🚀 **GO/NO-GO DECISION POINTS**

### Can Start Training When:
✅ Specialist tables have target columns  
✅ At least 1 training script writes to correct OOF table structure  
✅ Dry-run validation passes  

### Can Skip for First Run:
⚠️ EPA RIN data refresh (train 10 specialists, skip biofuel)  
⚠️ Last 6 days of market data (use Jan 9 cutoff)  
⚠️ Symbol mapping completion  

---

## 📊 **SUCCESS METRICS (End of Day)**

**Minimum viable success:**
- [ ] 1 L0 core model trained → `training.oof_core_21d_1d` populated
- [ ] 1 specialist trained → `training.oof_crush_21d_1d` populated
- [ ] Tables validated (quantiles ordered correctly)

**Stretch goal:**
- [ ] All 12 L0 models trained for horizon=21d
- [ ] 1 L1 meta model trained
- [ ] `forecasts.production_21d_1d` has predictions

---

**Start time:** 2026-01-15 14:00  
**Target completion:** 2026-01-15 22:00  
**Current blockers:** Target columns in specialist tables
