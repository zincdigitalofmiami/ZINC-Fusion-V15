# ML Schema Consistency Rationale

**Status**: LOCKED - Reference Document  
**Date**: January 11, 2026  
**Author**: Claude + Kirk  

---

## Why Schema Consistency is Load-Bearing Infrastructure

This document explains **why** the Bronze naming contract exists and why every raw table must have identical Bronze columns. This is not bureaucracy—it's the foundation that makes ML reproducible.

---

## The Core Problem

Machine learning models, particularly tree-based ensembles (XGBoost, LightGBM, CatBoost), require **identical feature schemas** at training and inference time.

### What Happens Without Schema Consistency

| Failure Mode | Model | Behavior |
|--------------|-------|----------|
| Missing column | XGBoost | **HARD ERROR**: `feature_names mismatch` |
| Missing column | LightGBM | **Silent wrong predictions** (numerical only) |
| Missing column | CatBoost | Error on categorical, silent on numerical |
| Missing column | Neural Net | Shape mismatch error |
| Extra column | All | Silently ignored (safe) |

**AutoGluon uses ALL of these models in ensemble.** If your raw tables have inconsistent schemas, the feature engineering step produces DataFrames with different columns across runs, causing:

1. Training fails if columns differ between folds
2. Inference fails if production data differs from training
3. Variable importance is meaningless if feature sets differ
4. OOF predictions are non-comparable across specialists

---

## AutoGluon's Explicit Requirements

From AutoGluon documentation:

> "The data passed to the `predict`/`predict_proba` methods must contain the same column names and follow the same format as the training data."

> "If your prediction DataFrame has different column names or missing columns, AutoGluon will raise an error."

> "To ensure consistent column names as input to avoid errors."

**Translation**: Your schema IS your pipeline. Inconsistent schema = inconsistent pipeline = garbage ML.

---

## XGBoost Feature Name Validation

XGBoost explicitly validates feature names at prediction time:

```python
ValueError: feature_names mismatch: 
  ['age', 'fnlwgt', 'educational-num', 'capital-gain', 'capital-loss', 'hours-per-week'] 
  ['age', 'capital-gain'] 
expected fnlwgt, capital-loss, educational-num, hours-per-week in input data
```

From XGBoost documentation:

> "To ensure the correct result from XGBoost, users need to keep the pipeline for transforming data consistent across training and testing data."

---

## Permutation Importance Requires Consistency

Permutation variable importance measures prediction error change when a feature is shuffled. This **requires** the same features to be present across runs.

From H2O documentation:

> "Permutation variable importance is obtained by measuring the distance between prediction errors before and after a feature is permuted; only one feature at a time is permuted."

If you compute permutation importance on Run A with columns `[a, b, c]` and Run B has `[a, b, d]`, the importance scores are **not comparable**. You can't track "what matters" across time.

---

## How Our Contract Solves This

### The Bronze Contract

Every `raw.*` table has **exactly 12 Bronze columns**:

```python
BRONZE_COLUMNS = {
    "knowledge_time",      # When we learned this
    "revision_no",         # Version tracking
    "supersedes_id",       # Links revisions
    "is_preliminary",      # Data maturity flag
    "validation_status",   # QA status
    "quality_score",       # Numeric quality metric
    "anomaly_flags",       # Array of detected issues
    "source_url",          # Data provenance
    "raw_payload",         # Original JSON
    "ingestion_batch_id",  # Links to ops.ingest_run
    "row_hash",            # Idempotency key
    "specialist_tags",     # Which specialists care
}
```

### What This Guarantees

```python
# Every specialist gets the same column contract
df = pd.read_sql("SELECT * FROM raw.fred_observations_1d", conn)
assert set(BRONZE_COLUMNS).issubset(df.columns)  # Always true

df2 = pd.read_sql("SELECT * FROM raw.cftc_cot_1w", conn)
assert set(BRONZE_COLUMNS).issubset(df2.columns)  # Always true

# Feature engineering produces deterministic output
features = build_features([df, df2])  # Same columns every time
```

---

## Risk Mitigation Matrix

| Risk | Without Contract | With Contract |
|------|------------------|---------------|
| Missing columns | Silent prediction corruption | Impossible - all tables have same structure |
| Feature importance drift | Rankings change randomly | Deterministic across runs |
| OOF reproducibility | Different folds see different features | Same features guaranteed |
| Training/inference skew | `feature_names mismatch` error | Eliminated by design |
| Schema migrations | Break everything downstream | Coordinated, versioned changes |

---

## The Naming Contract

Beyond columns, table **names** are executable metadata:

| Suffix | Meaning | PIT Join Strategy |
|--------|---------|-------------------|
| `_1h` | Hourly | ASOF join, 1h tolerance |
| `_1d` | Daily | ASOF join, 24h tolerance |
| `_1w` | Weekly | ASOF join, 7d tolerance |
| `_1m` | Monthly | ASOF join, 31d tolerance |
| `_event` | Irregular | ASOF join, variable tolerance |
| `_static` | Reference | Latest value only |

The suffix drives:
- Point-in-time join logic
- Data freshness validators
- Automated alerting thresholds
- Aggregation pipeline behavior

---

## Validation Enforcement

Pre-training validators ensure compliance:

```bash
# Run before every training run
python -m src.fusion.validators.run_all
```

Exit codes:
- `0` = All checks passed
- `1` = Critical failures (schema violations) - **DO NOT TRAIN**
- `2` = Warnings only (stale data) - proceed with caution

---

## References

1. AutoGluon TabularPredictor Documentation - Feature consistency requirements
2. XGBoost Feature Names Validation - `_validate_features` implementation
3. H2O Permutation Variable Importance - Requirements for consistent feature sets
4. LightGBM Issue #2396 - Silent prediction with missing features
5. ZINC-FUSION-V15 `BRONZE_NAMING_CONTRACT_LOCKED.md` - Authoritative naming rules

---

## Conclusion

The Bronze contract is not optional. It's the **load-bearing infrastructure** that makes:

1. Training reproducible
2. Inference reliable  
3. Feature importance meaningful
4. OOF predictions comparable

**Every raw table. Same 12 columns. No exceptions.**
