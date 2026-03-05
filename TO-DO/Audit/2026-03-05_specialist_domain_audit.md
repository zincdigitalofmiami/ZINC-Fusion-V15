# Specialist Domain Audit Report

**Date:** 2026-03-05  
**Auditor:** Claude (Code Mode)  
**Type:** READ-ONLY Static Code Audit  
**Scope:** Big-11 specialist signal system — tables, wiring, Inngest jobs, model artifacts, staleness

---

## Executive Summary

The specialist domain is **architecturally sound** with correct schema-to-code parity for all 11 buckets. However, **5/11 specialists have missing model artifacts** (P0), and there are configuration mismatches and monitoring gaps that need attention.

| Severity      | Count | Status                                             |
| ------------- | ----- | -------------------------------------------------- |
| P0 (Critical) | 1     | Missing model artifacts for 5 specialists          |
| P1 (High)     | 2     | Staleness computation bug, model_type mismatch     |
| P2 (Medium)   | 3     | Confidence gap, monitoring gap, prior audit status |
| P3 (Info)     | 4     | Verified correct patterns                          |

---

## P0 - Critical (Must Fix Immediately)

### P0-1: Missing Model Artifacts for 5/11 Specialists

**Severity:** P0 CRITICAL  
**Impact:** These specialists cannot generate ML-based signals; will use fallback or abstain  
**Evidence:**

```
models/specialists/
├── china/     ✓ model.joblib, metadata.joblib, scaler.joblib
├── crush/     ✓ model.joblib, metadata.joblib, scaler.joblib
├── energy/    ✓ var_model.joblib
├── fx/        ✓ ardl_model.joblib
├── palm/      ✓ model.joblib, metadata.joblib, scaler.joblib
├── substitutes/ ✓ model.joblib, metadata.joblib, scaler.joblib
├── fed/       ❌ MISSING
├── tariff/    ❌ MISSING
├── biofuel/   ❌ MISSING
├── volatility/❌ MISSING
├── trump_effect/ ❌ MISSING
```

**Root Cause:** These specialists either:

- Use rule-based/event-based generators (tariff=tree, trump_effect=event_study) that don't persist models
- Were never trained (fed, biofuel, volatility)
- Or lost artifacts during a migration

**Fix:**

```bash
# Verify which need training vs rule-based
# For ML-based: run training script
uv run python scripts/train_specialists.py --buckets fed biofuel volatility

# For rule-based (tariff, trump_effect): verify they generate signals without models
uv run python scripts/verify_specialist_signals.py --bucket tariff
```

---

## P1 - High Priority

### P1-1: Staleness Age Computed at Sync Time, Not Data Generation Time

**Severity:** P1 HIGH  
**Impact:** `max_input_age_days` underreports actual data staleness  
**Evidence:** [`frontend/src/inngest/specialist-signals-sync.ts:215-219`](frontend/src/inngest/specialist-signals-sync.ts:215)

```typescript
const ageDays = Math.max(
  0,
  Math.floor(
    (now.getTime() - new Date(`${dateKey}T00:00:00Z`).getTime()) / 86_400_000,
  ),
);
```

**Problem:** `ageDays` is computed relative to `now` (sync time), not when the underlying data was actually generated. If feature data was created 5 days ago but the sync runs today, the staleness will be recorded as 0.

**Fix:**

```typescript
// Compute age relative to the feature row's generation time, not sync time
const featureCreatedAt = f.created_at
  ? new Date(f.created_at)
  : new Date(dateKey);
const ageDays = Math.max(
  0,
  Math.floor((now.getTime() - featureCreatedAt.getTime()) / 86_400_000),
);
```

---

### P1-2: Model Type Mismatch for Palm Bucket

**Severity:** P1 HIGH  
**Impact:** Inconsistent `model_type` values in database; breaks filtering/auditing  
**Evidence:**

| Source  | Palm Model Type | Location                                                                                                   |
| ------- | --------------- | ---------------------------------------------------------------------------------------------------------- |
| Python  | `ecm_ridge`     | [`src/fusion/specialists/base.py:47`](src/fusion/specialists/base.py:47)                                   |
| Inngest | `ridge`         | [`frontend/src/inngest/specialist-signals-sync.ts:99`](frontend/src/inngest/specialist-signals-sync.ts:99) |

**Root Cause:** Inngest config was not updated when Python registry changed to `ecm_ridge`.

**Fix:** Update Inngest to match Python:

```typescript
// frontend/src/inngest/specialist-signals-sync.ts line 99
{
  bucket: "palm",
  featureTable: "training.specialist_features_palm",
  modelType: "ecm_ridge",  // was: "ridge"
  signalKeys: ["palm_zscore", "zl_palm_spread_zscore"],
  confidenceKey: "palm_bucket_confidence",
  fallbackConfidence: 0.5,
},
```

---

## P2 - Medium Priority

### P2-1: trump_effect Has No Confidence Key

**Severity:** P2 MEDIUM  
**Impact:** Always uses fallback confidence (0.5); no model-derived certainty  
**Evidence:** [`frontend/src/inngest/specialist-signals-sync.ts:121-127`](frontend/src/inngest/specialist-signals-sync.ts:121)

```typescript
{
  bucket: "trump_effect",
  featureTable: "training.specialist_features_trump_effect",
  modelType: "event_study",
  signalKeys: ["trump_bucket_signal", "policy_uncertainty_zscore"],
  confidenceKey: null,  // <-- No confidence key
  fallbackConfidence: 0.5,
},
```

**Fix:** Add confidence key if available in feature JSONB, or document that 0.5 fallback is intentional for event-driven specialists.

---

### P2-2: Per-Bucket Freshness Monitoring Missing

**Severity:** P2 MEDIUM  
**Impact:** A single bucket can be stale for weeks without triggering an alert  
**Evidence:** [`frontend/src/inngest/freshness-monitor.ts:34-126`](frontend/src/inngest/freshness-monitor.ts:34)

Current checks:

- `specialist_signals_any_bucket` — checks MAX(as_of_date) across ALL buckets (3-day SLA)
- `trump_effect_features` — checks trump_effect feature table only (7-day SLA)

**Problem:** If 10 buckets are fresh but 1 bucket (e.g., palm) is 14 days stale, no alert fires because MAX() still returns a recent date.

**Fix:** Add per-bucket freshness checks:

```typescript
const SPECIALIST_BUCKETS = [
  'crush', 'china', 'fx', 'fed', 'tariff', 'energy',
  'biofuel', 'palm', 'volatility', 'substitutes', 'trump_effect'
];

// Add to SLA_CHECKS
...SPECIALIST_BUCKETS.map(bucket => ({
  name: `specialist_${bucket}_freshness`,
  query: `SELECT CURRENT_DATE - MAX(as_of_date)::date AS days_stale
          FROM training.specialist_signals_1d
          WHERE bucket = '${bucket}'`,
  maxStaleDays: bucket === 'trump_effect' ? 7 : 3,
})),
```

---

### P2-3: Prior Audit Remediation Status Unknown

**Severity:** P2 MEDIUM  
**Impact:** Cannot verify if known issues from 2026-02-14 audit were resolved  
**Evidence:** [`docs/audits/SPECIALIST_AUDIT_VALIDATION_20260214.md`](docs/audits/SPECIALIST_AUDIT_VALIDATION_20260214.md)

That audit defined 5 remediation phases:

- **Phase A:** Measurement discipline (Day 0-1)
- **Phase B:** Data freshness enforcement (Day 1-3)
- **Phase C:** Anti-stuck logic (Day 2-5)
- **Phase D:** Quality control for negative IC (Week 2)
- **Phase E:** Operational controls (Week 2)

**Status:** No evidence of completion checkmarks or follow-up reports.

**Fix:** Kirk to confirm which phases are complete; update audit doc with status.

---

## P3 - Info / Verified Correct

### P3-1: All 11 Buckets Present ✓

| Source                      | Count | Evidence                                                                                                                            |
| --------------------------- | ----- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Python `SPECIALIST_BUCKETS` | 11    | [`src/fusion/specialists/base.py:25-37`](src/fusion/specialists/base.py:25)                                                         |
| Inngest `BUCKETS`           | 11    | [`frontend/src/inngest/specialist-signals-sync.ts:39-128`](frontend/src/inngest/specialist-signals-sync.ts:39)                      |
| Migration tables            | 11    | [`prisma/migrations/20260215_split.../migration.sql`](prisma/migrations/20260215_split_specialist_features_by_bucket/migration.sql) |
| Prisma models               | 12    | 11 feature tables + 1 signals table                                                                                                 |

**Verdict:** Big-11 count is consistent across Python, TypeScript, SQL, and Prisma.

---

### P3-2: Signal Column Naming Verified ✓

**Evidence:** [`src/fusion/core_training/build_matrix.py:2177-2194`](src/fusion/core_training/build_matrix.py:2177)

```python
# Pivot signal_1
pivot_1 = df.pivot(index="trade_date", columns="bucket", values="signal_1")
pivot_1.columns = [f"sig_{col}_1" for col in pivot_1.columns]

# Pivot signal_2
pivot_2 = df.pivot(index="trade_date", columns="bucket", values="signal_2")
pivot_2.columns = [f"sig_{col}_2" for col in pivot_2.columns]

# Pivot confidence
pivot_conf = df.pivot(index="trade_date", columns="bucket", values="confidence")
pivot_conf.columns = [f"sig_{col}_conf" for col in pivot_conf.columns]
```

**Verdict:** Generates expected 33 columns: `sig_{bucket}_1`, `sig_{bucket}_2`, `sig_{bucket}_conf` for 11 buckets.

---

### P3-3: Schema-to-Database Parity Verified ✓

| Prisma Model                         | Table                                   | Columns                                   | Indexes                                        |
| ------------------------------------ | --------------------------------------- | ----------------------------------------- | ---------------------------------------------- |
| `specialist_features_{bucket}` (×11) | `training.specialist_features_{bucket}` | id, as_of_date (unique), features (JSONB) | as_of_date DESC                                |
| `specialist_signals_1d`              | `training.specialist_signals_1d`        | 17 columns                                | bucket, date, bucket+date, run_hash, staleness |

**Verdict:** Prisma schema matches migration SQL exactly.

---

### P3-4: Cron Schedule Verified ✓

| Job                     | Schedule                                    | Purpose                       |
| ----------------------- | ------------------------------------------- | ----------------------------- |
| specialist-signals-sync | `0 7 * * *` (7:00 AM UTC)                   | Sync features → signals       |
| freshness-monitor       | `TZ=America/Chicago 0 8 * * *` (8:00 AM CT) | Check staleness, write alerts |

**Verdict:** Monitor runs 1 hour after sync; allows time for sync to complete.

---

## Rollout Order for Fixes

1. **P0-1:** Verify which specialists need models vs are rule-based; train missing ML models
2. **P1-2:** Update palm model_type in Inngest to `ecm_ridge`
3. **P1-1:** Fix staleness age computation to use feature creation time
4. **P2-2:** Add per-bucket freshness checks to monitor
5. **P2-1:** Document trump_effect confidence fallback or add confidence key
6. **P2-3:** Update prior audit doc with phase completion status

---

## Files Reviewed

| File                                                                           | Purpose                                       |
| ------------------------------------------------------------------------------ | --------------------------------------------- |
| `prisma/schema.prisma` (lines 3061-3200)                                       | Specialist Prisma models                      |
| `src/fusion/specialists/base.py`                                               | SPECIALIST_BUCKETS, MODEL_TYPES, SignalOutput |
| `frontend/src/inngest/specialist-signals-sync.ts`                              | Feature → signal sync job                     |
| `frontend/src/inngest/freshness-monitor.ts`                                    | Staleness SLA checks                          |
| `src/fusion/core_training/build_matrix.py`                                     | load_specialist_signals()                     |
| `prisma/migrations/20260215_split_specialist_features_by_bucket/migration.sql` | Table creation                                |
| `docs/audits/SPECIALIST_AUDIT_VALIDATION_20260214.md`                          | Prior audit findings                          |
| `models/specialists/`                                                          | Model artifact directory                      |

---

## Appendix: Model Type Registry

| Bucket       | Python MODEL_TYPES | Inngest modelType | Match |
| ------------ | ------------------ | ----------------- | ----- |
| crush        | gbm                | gbm               | ✓     |
| china        | gbm                | gbm               | ✓     |
| fx           | ardl               | ardl              | ✓     |
| fed          | ridge              | ridge             | ✓     |
| tariff       | tree               | tree              | ✓     |
| energy       | var                | var               | ✓     |
| biofuel      | nlp_ema            | nlp_ema           | ✓     |
| palm         | **ecm_ridge**      | **ridge**         | ❌    |
| volatility   | garch              | garch             | ✓     |
| substitutes  | rf                 | rf                | ✓     |
| trump_effect | event_study        | event_study       | ✓     |

---

_End of Specialist Domain Audit Report_
