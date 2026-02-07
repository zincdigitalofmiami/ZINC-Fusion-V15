#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Ablation Testing Framework for Specialist Signals

Tests the contribution of each specialist signal to Core model performance
by comparing:
1. Baseline: Core trained WITHOUT specialist signals
2. With signal: Core trained WITH specialist signals

Acceptance Criteria (from SPECIALIST_SIGNAL_SPEC.md):
- MAE/MASE must not increase
- Quantile coverage (p30-p70) must not decrease
- Stability across regimes (pre-2020, 2020-22, post-2022)

Usage:
    python scripts/ablation_signal_test.py --bucket crush --horizon 21
    python scripts/ablation_signal_test.py --bucket all --horizon all
    python scripts/ablation_signal_test.py --bucket all --horizon 21 --dry-run

@author Claude (ZINC-FUSION-V15)
@version 1.0.0
@date 2026-01-21
"""

import os
import sys
import logging
import argparse
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import hashlib

import pandas as pd
import numpy as np
from dotenv import load_dotenv

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv(PROJECT_ROOT / ".env")


# =============================================================================
# CONSTANTS
# =============================================================================

SPECIALISTS = [
    "crush", "china", "fx", "fed", "tariff",
    "energy", "biofuel", "palm", "volatility",
    "substitutes", "trump_effect",
]

HORIZONS = [5, 21, 63, 126]

# Regime definitions for stability testing
REGIMES = {
    "pre_2020": (date(2015, 1, 1), date(2019, 12, 31)),
    "pandemic": (date(2020, 1, 1), date(2022, 12, 31)),
    "post_2022": (date(2023, 1, 1), date(2025, 12, 31)),
}


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

def get_connection():
    """Get database connection from DATABASE_URL."""
    import psycopg2
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")
    return psycopg2.connect(database_url)


# =============================================================================
# DATA LOADING
# =============================================================================

def load_training_data(
    conn,
    include_signals: bool = False,
    signal_bucket: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load training matrix with optional specialist signals.

    The training.matrix_1d already includes signals from Phase 3.
    This function controls which signal columns are available for training.

    Args:
        conn: Database connection
        include_signals: Whether to include specialist signals
        signal_bucket: If specified, only include signals for this bucket

    Returns:
        DataFrame with features and targets
    """
    base_query = """
    SELECT m.*
    FROM training.matrix_1d m
    WHERE m.symbol = 'ZL'
    ORDER BY m.trade_date
    """

    df = pd.read_sql(base_query, conn)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("trade_date")

    # Signals are already in training.matrix_1d from Phase 3
    # If include_signals=False, drop all signal columns
    # If signal_bucket specified, keep only that bucket's signals

    signal_cols = [c for c in df.columns if c.startswith("sig_")]

    if not include_signals:
        # Drop all signal columns for baseline
        df = df.drop(columns=signal_cols, errors="ignore")
        logger.info("Dropped all signal columns (baseline mode)")
    elif signal_bucket:
        # Keep only specified bucket's signals
        keep_cols = [c for c in signal_cols if f"sig_{signal_bucket}_" in c]
        drop_cols = [c for c in signal_cols if c not in keep_cols]
        df = df.drop(columns=drop_cols, errors="ignore")
        logger.info(f"Keeping only {signal_bucket} signals: {keep_cols}")

    return df


# =============================================================================
# MODEL TRAINING (Simplified for ablation)
# =============================================================================

def train_simple_model(
    train_df: pd.DataFrame,
    target_col: str,
    feature_cols: List[str],
) -> Tuple[object, float]:
    """
    Train a simple GBM model for ablation testing.

    Uses LightGBM for speed; full AutoGluon training is too slow for ablation.

    Returns:
        (model, training_score)
    """
    try:
        import lightgbm as lgb
    except ImportError:
        logger.warning("LightGBM not available; using sklearn GBM")
        from sklearn.ensemble import GradientBoostingRegressor as lgb
        lgb = None

    # Prepare data
    X = train_df[feature_cols].dropna()
    y = train_df.loc[X.index, target_col].dropna()

    # Align
    common_idx = X.index.intersection(y.index)
    X = X.loc[common_idx]
    y = y.loc[common_idx]

    if len(X) < 100:
        raise ValueError(f"Insufficient training data: {len(X)}")

    if lgb is not None:
        # LightGBM
        train_data = lgb.Dataset(X, label=y)
        params = {
            "objective": "regression",
            "metric": "mae",
            "verbosity": -1,
            "num_leaves": 31,
            "learning_rate": 0.05,
            "n_estimators": 100,
        }
        model = lgb.train(params, train_data, num_boost_round=100)
        preds = model.predict(X)
    else:
        # Sklearn fallback
        from sklearn.ensemble import GradientBoostingRegressor
        model = GradientBoostingRegressor(n_estimators=100, max_depth=5)
        model.fit(X, y)
        preds = model.predict(X)

    mae = np.mean(np.abs(y - preds))
    return model, mae


def evaluate_model(
    model,
    test_df: pd.DataFrame,
    target_col: str,
    feature_cols: List[str],
) -> Dict[str, float]:
    """
    Evaluate model on test data.

    Returns:
        Dict with mae, mase, coverage_40
    """
    # Prepare data
    X = test_df[feature_cols].dropna()
    y = test_df.loc[X.index, target_col].dropna()

    common_idx = X.index.intersection(y.index)
    X = X.loc[common_idx]
    y = y.loc[common_idx]

    if len(X) == 0:
        return {"mae": np.nan, "mase": np.nan, "coverage_40": np.nan}

    # Get predictions
    try:
        preds = model.predict(X)
    except Exception:
        preds = model.predict(X.values)

    # MAE
    mae = np.mean(np.abs(y - preds))

    # MASE (relative to naive seasonal)
    naive_errors = np.abs(y.diff(21).dropna())
    mase = mae / (np.mean(naive_errors) + 1e-8)

    # Coverage (simplified: % within 40% of actual)
    # For proper quantile coverage, would need quantile predictions
    pct_error = np.abs((y - preds) / (y + 1e-8))
    coverage_40 = np.mean(pct_error < 0.40) * 100

    return {
        "mae": mae,
        "mase": mase,
        "coverage_40": coverage_40,
    }


# =============================================================================
# ABLATION TEST
# =============================================================================

def run_ablation_test(
    conn,
    bucket: str,
    horizon: int,
    test_size: float = 0.2,
) -> Dict[str, float]:
    """
    Run ablation test for a single specialist signal.

    Compares:
    - Baseline: Model without signal
    - With signal: Model with signal

    Returns:
        Dict with baseline_mae, with_signal_mae, delta_mae, etc.
    """
    target_col = f"target_ret_{horizon}d"

    # Get base feature columns (exclude targets and signals)
    base_data = load_training_data(conn, include_signals=False)
    exclude_patterns = ["target_", "sig_", "id", "symbol", "created_at"]
    base_features = [
        col for col in base_data.columns
        if not any(pat in col for pat in exclude_patterns)
        and base_data[col].dtype in [np.float64, np.float32, np.int64, np.int32]
    ]

    # Filter to non-null targets
    base_data = base_data[base_data[target_col].notna()]

    if len(base_data) < 500:
        logger.warning(f"Insufficient data for {bucket}/{horizon}d: {len(base_data)}")
        return {}

    # Train/test split (temporal)
    split_idx = int(len(base_data) * (1 - test_size))
    train_data = base_data.iloc[:split_idx]
    test_data = base_data.iloc[split_idx:]

    logger.info(f"Train: {len(train_data)}, Test: {len(test_data)}")

    # Baseline model (no signals)
    try:
        baseline_model, _ = train_simple_model(train_data, target_col, base_features)
        baseline_metrics = evaluate_model(baseline_model, test_data, target_col, base_features)
    except Exception as e:
        logger.error(f"Baseline training failed: {e}")
        return {}

    # Model with signal
    signal_data = load_training_data(conn, include_signals=True, signal_bucket=bucket)
    signal_data = signal_data[signal_data[target_col].notna()]

    # Get signal columns
    signal_cols = [col for col in signal_data.columns if col.startswith(f"sig_{bucket}")]
    if not signal_cols:
        logger.warning(f"No signal columns found for {bucket}")
        return {}

    features_with_signal = base_features + signal_cols

    # Filter to rows with signals
    signal_train = signal_data.iloc[:split_idx].dropna(subset=signal_cols)
    signal_test = signal_data.iloc[split_idx:].dropna(subset=signal_cols)

    if len(signal_train) < 100 or len(signal_test) < 20:
        logger.warning(f"Insufficient signal coverage for {bucket}")
        return {}

    try:
        signal_model, _ = train_simple_model(signal_train, target_col, features_with_signal)
        signal_metrics = evaluate_model(signal_model, signal_test, target_col, features_with_signal)
    except Exception as e:
        logger.error(f"Signal model training failed: {e}")
        return {}

    # Compute deltas
    results = {
        "bucket": bucket,
        "horizon_days": horizon,
        "baseline_mae": baseline_metrics["mae"],
        "with_signal_mae": signal_metrics["mae"],
        "delta_mae": signal_metrics["mae"] - baseline_metrics["mae"],
        "baseline_mase": baseline_metrics["mase"],
        "with_signal_mase": signal_metrics["mase"],
        "delta_mase": signal_metrics["mase"] - baseline_metrics["mase"],
        "baseline_coverage_40": baseline_metrics["coverage_40"],
        "with_signal_coverage_40": signal_metrics["coverage_40"],
        "delta_coverage": signal_metrics["coverage_40"] - baseline_metrics["coverage_40"],
    }

    # Recommendation
    # Accept if: MAE decreases or stays same, coverage increases or stays same
    if results["delta_mae"] <= 0 and results["delta_coverage"] >= 0:
        results["recommendation"] = "accept"
    elif results["delta_mae"] > 0.05 or results["delta_coverage"] < -5:
        results["recommendation"] = "reject"
    else:
        results["recommendation"] = "review"

    return results


def run_regime_stability_test(
    conn,
    bucket: str,
    horizon: int,
) -> Dict[str, float]:
    """
    Test signal stability across market regimes.

    Returns:
        Dict with regime-specific metrics and overall stability score
    """
    stability_scores = {}

    for regime_name, (start, end) in REGIMES.items():
        # Load regime data
        query = f"""
        SELECT s.*, m.target_ret_{horizon}d as target
        FROM training.specialist_signals_1d s
        JOIN training.matrix_1d m ON s.as_of_date = m.trade_date AND m.symbol = 'ZL'
        WHERE s.bucket = '{bucket}'
          AND s.as_of_date >= '{start}'
          AND s.as_of_date <= '{end}'
        """
        try:
            regime_df = pd.read_sql(query, conn)
            if len(regime_df) < 50:
                stability_scores[regime_name] = np.nan
                continue

            # Compute signal-target correlation
            corr = regime_df["signal_1"].corr(regime_df["target"])
            stability_scores[regime_name] = corr

        except Exception as e:
            logger.warning(f"Regime test failed for {regime_name}: {e}")
            stability_scores[regime_name] = np.nan

    # Overall stability = consistency of correlation sign across regimes
    valid_scores = [v for v in stability_scores.values() if not np.isnan(v)]
    if len(valid_scores) >= 2:
        signs = [np.sign(v) for v in valid_scores]
        stability = 1.0 if len(set(signs)) == 1 else 0.5
    else:
        stability = 0.0

    stability_scores["overall_stability"] = stability
    return stability_scores


# =============================================================================
# DATABASE WRITING
# =============================================================================

def write_ablation_results(
    conn,
    results: Dict,
    run_id: str,
    dry_run: bool = False,
):
    """Write ablation results to analytics.ablation_results."""
    from psycopg2.extras import execute_values

    if not results or "bucket" not in results:
        return

    # Convert numpy types to Python native types for database insertion
    def to_native(v):
        if v is None:
            return None
        if isinstance(v, (np.floating, np.float64, np.float32)):
            return float(v)
        if isinstance(v, (np.integer, np.int64, np.int32)):
            return int(v)
        return v

    values = [(
        run_id,
        results["bucket"],
        int(results["horizon_days"]),
        to_native(results["baseline_mae"]),
        to_native(results["with_signal_mae"]),
        to_native(results["delta_mae"]),
        to_native(results["baseline_coverage_40"]),
        to_native(results["with_signal_coverage_40"]),
        to_native(results.get("overall_stability")),
        results["recommendation"],
    )]

    if dry_run:
        logger.info(f"[DRY RUN] Would write: {results}")
        return

    query = """
    INSERT INTO analytics.ablation_results
        (run_id, bucket, horizon_days, baseline_mae, with_signal_mae, delta_mae,
         baseline_coverage_40, with_signal_coverage_40, regime_stability_score,
         recommendation)
    VALUES %s
    ON CONFLICT (run_id, bucket, horizon_days)
    DO UPDATE SET
        baseline_mae = EXCLUDED.baseline_mae,
        with_signal_mae = EXCLUDED.with_signal_mae,
        delta_mae = EXCLUDED.delta_mae,
        baseline_coverage_40 = EXCLUDED.baseline_coverage_40,
        with_signal_coverage_40 = EXCLUDED.with_signal_coverage_40,
        regime_stability_score = EXCLUDED.regime_stability_score,
        recommendation = EXCLUDED.recommendation,
        tested_at = NOW()
    """

    try:
        with conn.cursor() as cur:
            execute_values(cur, query, values)
        conn.commit()
        logger.info(f"Wrote ablation result for {results['bucket']}/{results['horizon_days']}d")
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to write ablation result: {e}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Ablation testing for specialist signals"
    )
    parser.add_argument(
        "--bucket",
        choices=SPECIALISTS + ["all"],
        default="all",
        help="Specialist bucket to test (default: all)",
    )
    parser.add_argument(
        "--horizon",
        choices=[str(h) for h in HORIZONS] + ["all"],
        default="all",
        help="Horizon to test (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write to database",
    )
    args = parser.parse_args()

    # Determine what to test
    buckets = SPECIALISTS if args.bucket == "all" else [args.bucket]
    horizons = HORIZONS if args.horizon == "all" else [int(args.horizon)]

    # Generate run ID
    run_id = hashlib.sha256(
        f"{datetime.now().isoformat()}:ablation".encode()
    ).hexdigest()[:16]

    logger.info(f"Run ID: {run_id}")
    logger.info(f"Testing: {buckets} x {horizons}")

    # Connect
    conn = get_connection()

    try:
        all_results = []

        for bucket in buckets:
            for horizon in horizons:
                logger.info(f"\n{'='*60}")
                logger.info(f"Testing {bucket} at {horizon}d horizon")
                logger.info(f"{'='*60}")

                # Run ablation test
                results = run_ablation_test(conn, bucket, horizon)

                if results:
                    # Add regime stability
                    stability = run_regime_stability_test(conn, bucket, horizon)
                    results.update(stability)

                    # Log results
                    logger.info(f"Baseline MAE: {results['baseline_mae']:.4f}")
                    logger.info(f"With Signal MAE: {results['with_signal_mae']:.4f}")
                    logger.info(f"Delta MAE: {results['delta_mae']:.4f}")
                    logger.info(f"Recommendation: {results['recommendation'].upper()}")

                    # Write to DB
                    write_ablation_results(conn, results, run_id, args.dry_run)
                    all_results.append(results)

        # Summary
        logger.info(f"\n{'='*60}")
        logger.info("SUMMARY")
        logger.info(f"{'='*60}")

        if all_results:
            accept_count = sum(1 for r in all_results if r["recommendation"] == "accept")
            review_count = sum(1 for r in all_results if r["recommendation"] == "review")
            reject_count = sum(1 for r in all_results if r["recommendation"] == "reject")

            logger.info(f"Accepted: {accept_count}")
            logger.info(f"Review: {review_count}")
            logger.info(f"Rejected: {reject_count}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
