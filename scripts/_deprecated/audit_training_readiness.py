#!/usr/bin/env python3
"""
ZINC-FUSION-V15 Training Readiness Audit
Validates all prerequisites before training SoT v2 models
"""

import psycopg2
import os
import sys
from datetime import datetime


def audit_training_readiness():
    """Run comprehensive training readiness audit"""

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    print("=" * 80)
    print("ZINC-FUSION-V15 TRAINING READINESS AUDIT")
    print(f"Timestamp: {datetime.now()}")
    print("=" * 80)
    print()

    issues = []

    # 1. Core Training Matrix
    print("✓ 1. CORE TRAINING MATRIX")
    print("-" * 40)
    cur.execute(
        """
        SELECT COUNT(*), COUNT(DISTINCT as_of_date), MIN(as_of_date), MAX(as_of_date)
        FROM training.core_matrix_1d
    """
    )
    rows, dates, min_d, max_d = cur.fetchone()
    print(f"   Rows: {rows:,}")
    print(f"   Unique dates: {dates:,}")
    print(f"   Date range: {min_d} to {max_d}")

    # Check for target columns
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns 
        WHERE table_schema='training' AND table_name='core_matrix_1d' 
        AND column_name LIKE 'target%'
        ORDER BY column_name
    """
    )
    targets = [r[0] for r in cur.fetchall()]
    print(f"   Target columns: {', '.join(targets)}")

    if len(targets) != 4:
        issues.append(f"Core matrix should have 4 target columns, found {len(targets)}")
    if rows == 0:
        issues.append("Core matrix is empty!")
    print()

    # 2. Specialist Features
    print("✓ 2. SPECIALIST FEATURES")
    print("-" * 40)
    cur.execute(
        """
        SELECT bucket, COUNT(*), COUNT(DISTINCT as_of_date)
        FROM training.specialist_features
        GROUP BY bucket ORDER BY bucket
    """
    )
    spec_data = cur.fetchall()
    expected_buckets = [
        "biofuel",
        "china",
        "crush",
        "energy",
        "fed",
        "fx",
        "palm",
        "substitutes",
        "tariff",
        "trump_effect",
        "volatility",
    ]

    found_buckets = [b[0] for b in spec_data]
    for bucket, cnt, dates in spec_data:
        print(f"   {bucket:15s}: {cnt:,} rows, {dates:,} dates")

    missing_buckets = set(expected_buckets) - set(found_buckets)
    if missing_buckets:
        issues.append(f"Missing specialist buckets: {missing_buckets}")
    print()

    # 3. CV Folds
    print("✓ 3. CROSS-VALIDATION FOLDS")
    print("-" * 40)
    cur.execute(
        """
        SELECT COUNT(*), COUNT(DISTINCT as_of_date), COUNT(DISTINCT fold_id)
        FROM model.cv_folds
    """
    )
    result = cur.fetchone()
    total = result[0] if result else 0

    if total:
        total, dates, folds = result
        print(f"   Total rows: {total:,}")
        print(f"   Unique dates: {dates:,}")
        print(f"   Number of folds: {folds}")

        cur.execute(
            """
            SELECT fold_id, COUNT(*), MIN(as_of_date), MAX(as_of_date)
            FROM model.cv_folds
            GROUP BY fold_id ORDER BY fold_id
        """
        )
        print("   Fold distribution:")
        for fold_id, cnt, min_d, max_d in cur.fetchall():
            print(f"      Fold {fold_id}: {cnt:,} rows ({min_d} to {max_d})")
    else:
        print("   ❌ NO CV FOLDS ASSIGNED!")
        issues.append("CRITICAL: No CV folds defined - training cannot proceed")
    print()

    # 4. OOF Tables
    print("✓ 4. OUT-OF-FOLD TABLES")
    print("-" * 40)
    models = [
        "core",
        "crush",
        "china",
        "fx",
        "fed",
        "tariff",
        "energy",
        "biofuel",
        "palm",
        "volatility",
        "substitutes",
        "trump_effect",
    ]
    horizons = [5, 21, 63, 126]

    for model in models[:4]:  # Sample first 4
        counts = []
        for h in horizons:
            try:
                cur.execute(f"SELECT COUNT(*) FROM training.oof_{model}_{h}d_1d")
                cnt = cur.fetchone()[0]
                counts.append(f"{h}d:{cnt}")
            except:
                counts.append(f"{h}d:ERR")
                issues.append(f"OOF table missing or inaccessible: oof_{model}_{h}d_1d")
        print(f"   {model:10s}: {' | '.join(counts)}")
    print(f"   ... (showing 4 of {len(models)} models)")
    print()

    # 5. Raw ZL prices
    print("✓ 5. RAW ZL PRICE DATA")
    print("-" * 40)
    cur.execute(
        """
        SELECT COUNT(*), COUNT(DISTINCT event_date), MIN(event_date), MAX(event_date),
               COUNT(*) FILTER (WHERE close IS NOT NULL),
               COUNT(*) FILTER (WHERE close IS NULL)
        FROM raw.market_futures_1d WHERE symbol = 'ZL'
    """
    )
    total, dates, min_d, max_d, non_null, nulls = cur.fetchone()
    print(f"   Total rows: {total:,}")
    print(f"   Unique dates: {dates:,}")
    print(f"   Date range: {min_d} to {max_d}")
    print(f"   Non-null close: {non_null:,}")
    print(f"   Null close: {nulls:,}")

    if nulls > 0:
        issues.append(f"WARNING: {nulls} ZL price rows have null close values")

    # Check data freshness
    days_stale = (datetime.now().date() - max_d).days if max_d else 999
    print(f"   Data staleness: {days_stale} days")
    if days_stale > 7:
        issues.append(f"WARNING: ZL price data is {days_stale} days stale")
    print()

    # 6. Date Alignment
    print("✓ 6. DATE ALIGNMENT CHECK")
    print("-" * 40)
    cur.execute(
        """
        WITH core_dates AS (SELECT DISTINCT as_of_date FROM training.core_matrix_1d),
             spec_dates AS (SELECT DISTINCT as_of_date FROM training.specialist_features WHERE bucket = 'crush'),
             fold_dates AS (SELECT DISTINCT as_of_date FROM model.cv_folds)
        SELECT 
            (SELECT COUNT(*) FROM core_dates) as core,
            (SELECT COUNT(*) FROM spec_dates) as spec,
            (SELECT COUNT(*) FROM fold_dates) as folds,
            (SELECT COUNT(*) FROM core_dates WHERE as_of_date NOT IN (SELECT as_of_date FROM fold_dates)) as core_no_fold,
            (SELECT COUNT(*) FROM spec_dates WHERE as_of_date NOT IN (SELECT as_of_date FROM core_dates)) as spec_extra
    """
    )
    core, spec, folds, core_no_fold, spec_extra = cur.fetchone()
    print(f"   Core matrix dates: {core:,}")
    print(f"   Specialist dates: {spec:,}")
    print(f"   CV fold dates: {folds if folds else 0:,}")
    print(f"   Core dates without folds: {core_no_fold if core_no_fold else 0:,}")
    print(f"   Specialist extra dates: {spec_extra:,}")

    if core_no_fold and core_no_fold > 0:
        issues.append(
            f"CRITICAL: {core_no_fold} core matrix dates have no fold assignments"
        )
    print()

    # 7. Model Registry
    print("✓ 7. MODEL REGISTRY")
    print("-" * 40)
    cur.execute("SELECT COUNT(*) FROM model.model_registry")
    cnt = cur.fetchone()[0]
    print(f"   Total models registered: {cnt}")
    print()

    # 8. Specialist OHLCV tables
    print("✓ 8. SPECIALIST OHLCV DATA")
    print("-" * 40)
    buckets = [
        "crush",
        "china",
        "fx",
        "fed",
        "tariff",
        "energy",
        "biofuel",
        "palm",
        "volatility",
        "substitutes",
        "trump_effect",
    ]
    for bucket in buckets:
        try:
            cur.execute(
                f"""
                SELECT COUNT(DISTINCT symbol), COUNT(*), COUNT(DISTINCT as_of_date)
                FROM training.specialist_{bucket}_1d
            """
            )
            symbols, rows, dates = cur.fetchone()
            print(
                f"   {bucket:15s}: {symbols:2d} symbols, {rows:6,} rows, {dates:,} dates"
            )
        except Exception as e:
            print(f"   {bucket:15s}: ❌ ERROR or missing table")
            issues.append(
                f"Specialist OHLCV table missing or inaccessible: specialist_{bucket}_1d"
            )
    print()

    # Summary
    print("=" * 80)
    print("AUDIT SUMMARY")
    print("=" * 80)

    if issues:
        print(f"\n❌ FOUND {len(issues)} ISSUE(S):\n")
        for i, issue in enumerate(issues, 1):
            print(f"{i}. {issue}")
        print("\n⚠️  TRAINING NOT READY - RESOLVE ISSUES ABOVE")
        return 1
    else:
        print("\n✅ ALL CHECKS PASSED - READY FOR TRAINING")
        print("\nNext steps:")
        print(
            "  1. Run: python scripts/v2_training/train_l0_core.py --horizons 21 --time-limit 600"
        )
        print("  2. Validate OOF output in training.oof_core_21d_1d")
        print("  3. Scale to all 52 models")
        return 0

    cur.close()
    conn.close()


if __name__ == "__main__":
    sys.exit(audit_training_readiness())
