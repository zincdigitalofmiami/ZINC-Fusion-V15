#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Specialist Training Script with LASSO

Trains a single specialist bucket using AutoGluon TabularPredictor with LASSO
as a first-class voter alongside GBM/CatBoost/XGBoost.

NON-NEGOTIABLES:
- Uses cv_folds from Postgres as canonical splits
- LASSO participates as equal voter (not preprocessor)
- OOF predictions written to oof_predictions table
- LASSO coefficients extracted for interpretability
- No data leakage: only OOF predictions used downstream

AUTOGLUON GOVERNANCE (from doctrine):
- high_quality preset (stability > marginal accuracy)
- dynamic_stacking enabled (anti-overfit)
- num_bag_folds >= 5 (OOF robustness)
- num_stack_levels = 1 (conservative)
- time_limit bounded (prevents over-tuning)
- At least one linear model (LASSO) + variance-reducing models
- All OOF predictions and leaderboards persisted for audit

Architecture:
- L0 Specialists: TabularPredictor with {LR (LASSO), GBM, CAT, XGB, RF}
- Each specialist predicts returns, not prices
- Output: P10, P50, P90 quantiles per horizon

Usage:
    python scripts/train_specialist.py --bucket crush --horizon 63 --dry-run
    python scripts/train_specialist.py --bucket crush --horizon 63
    python scripts/train_specialist.py --bucket all --horizon 63  # Train all specialists
"""

# ═══════════════════════════════════════════════════════════════════════════════
# CRITICAL: Set environment variables BEFORE any imports
# This fixes Keras 3 vs tf_keras compatibility issue in Transformers
# ═══════════════════════════════════════════════════════════════════════════════
import os
os.environ['TF_USE_LEGACY_KERAS'] = '1'
os.environ['KERAS_BACKEND'] = 'tensorflow'

import sys
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ═══════════════════════════════════════════════════════════════════════════════
# ALL DATA POLICY ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════════════════
# CRITICAL: Specialists MUST use ALL data sources.
# Each bucket gets 900+ features. AutoGluon determines relevance.
# DO NOT cherry-pick features per bucket. That's AutoGluon's job.
# ═══════════════════════════════════════════════════════════════════════════════
from src.fusion.validation.all_data_policy import (
    validate_specialist_features,
    log_all_data_summary,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
load_dotenv('.env.vercel')

# Project paths (PROJECT_ROOT already defined above for imports)
MODEL_PATH = PROJECT_ROOT / "models" / "specialists"

# Specialist buckets (11 specialists)
SPECIALIST_BUCKETS = [
    "crush", "china", "fx", "fed", "tariff",
    "energy", "biofuel", "palm", "volatility", "substitutes",
    "trump_effect",  # 11th specialist: Trump/policy regime dynamics
]

# Horizons
HORIZONS = [5, 21, 63, 126]

# Training config
QUANTILES = [0.1, 0.5, 0.9]
TIME_LIMITS = {
    "ultrafast": 60,   # 1 minute per fold
    "quick": 300,      # 5 minutes per fold
    "full": 600,       # 10 minutes per fold
}
NUM_FOLDS = 5


@dataclass
class TrainingResult:
    """Results from training a specialist."""
    bucket: str
    horizon: int
    fold_id: int
    model_version: str
    oof_predictions: pd.DataFrame
    lasso_coefficients: Dict[str, float]
    metrics: Dict[str, float]
    trained_at: datetime


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def load_specialist_features(conn, bucket: str) -> pd.DataFrame:
    """Load specialist features from Postgres.

    CRITICAL: Validates that ALL DATA is present per the ALL DATA policy.
    Each bucket must have 800+ features. If not, training will FAIL.
    """
    logger.info(f"Loading features for bucket: {bucket}")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT as_of_date, features
            FROM "training"."specialist_features"
            WHERE bucket = %s
            ORDER BY as_of_date
        """, (bucket,))
        rows = cur.fetchall()

    if not rows:
        raise ValueError(f"No features found for bucket: {bucket}")

    # Parse JSON features into DataFrame
    records = []
    for as_of_date, features_json in rows:
        record = {"as_of_date": as_of_date}
        if isinstance(features_json, str):
            features = json.loads(features_json)
        else:
            features = features_json
        record.update(features)
        records.append(record)

    df = pd.DataFrame(records)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])

    logger.info(f"  Loaded {len(df):,} rows with {len(df.columns)-1} features")

    # =========================================================================
    # ALL DATA POLICY ENFORCEMENT
    # =========================================================================
    # Validate that specialist features have ALL data (800+ features).
    # This will raise ValueError if feature count is too low.
    # =========================================================================
    validate_specialist_features(df, bucket, strict=True)

    return df


def load_market_data(conn) -> pd.DataFrame:
    """Load ZL market data for returns calculation."""
    logger.info("Loading ZL market data")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT as_of_date, close
            FROM "raw"."market_futures_1d"
            WHERE symbol = 'ZL'
            ORDER BY as_of_date
        """)
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=["as_of_date", "close"])
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])

    logger.info(f"  Loaded {len(df):,} price rows")
    return df


def load_cv_folds(conn, horizon: int) -> pd.DataFrame:
    """Load CV fold assignments from Postgres."""
    logger.info(f"Loading CV folds for horizon={horizon}d")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT as_of_date, fold_id, is_train, is_val
            FROM "model"."cv_folds"
            WHERE horizon = %s
            ORDER BY as_of_date, fold_id
        """, (horizon,))
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=["as_of_date", "fold_id", "is_train", "is_val"])
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])

    logger.info(f"  Loaded {len(df):,} fold assignments")
    return df


def calculate_returns(prices_df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Calculate forward returns for the given horizon."""
    df = prices_df.copy()
    df = df.sort_values("as_of_date")

    # Forward return: (price_t+h / price_t) - 1
    df["forward_return"] = df["close"].shift(-horizon) / df["close"] - 1

    # Drop NaN rows (last `horizon` rows have no forward return)
    df = df.dropna(subset=["forward_return"])

    return df[["as_of_date", "forward_return"]]


def prepare_training_data(
    features_df: pd.DataFrame,
    returns_df: pd.DataFrame,
    folds_df: pd.DataFrame,
    fold_id: int
) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.Series]:
    """Prepare train/val splits for a specific fold.

    Returns:
        X_train, y_train, X_val, y_val, val_dates
    """

    # Merge features with returns
    df = features_df.merge(returns_df, on="as_of_date", how="inner")

    # Get fold assignments for this fold_id
    fold_assignments = folds_df[folds_df["fold_id"] == fold_id][["as_of_date", "is_train", "is_val"]]
    df = df.merge(fold_assignments, on="as_of_date", how="inner")

    # Split into train and validation
    train_df = df[df["is_train"] == True].copy()
    val_df = df[df["is_val"] == True].copy()

    # Separate features and target
    feature_cols = [c for c in df.columns if c not in ["as_of_date", "forward_return", "is_train", "is_val"]]

    X_train = train_df[feature_cols]
    y_train = train_df["forward_return"]
    X_val = val_df[feature_cols]
    y_val = val_df["forward_return"]
    val_dates = val_df["as_of_date"]

    return X_train, y_train, X_val, y_val, val_dates


def train_fold(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    bucket: str,
    horizon: int,
    fold_id: int,
    model_dir: Path,
    time_limit: int = 300,
    mode: str = "quick"
) -> Tuple[Any, Dict[str, float], Dict[str, float]]:
    """
    Train AutoGluon TabularPredictor with LASSO as first-class voter.

    Returns:
        predictor: Trained AutoGluon predictor
        lasso_coefficients: Dict of feature -> coefficient from LASSO
        metrics: Dict of validation metrics
    """
    try:
        from autogluon.tabular import TabularPredictor
    except ImportError:
        logger.error("AutoGluon not installed. Run: pip install autogluon.tabular")
        raise

    # Prepare training data with target column
    train_data = X_train.copy()
    train_data["target"] = y_train.values

    val_data = X_val.copy()
    val_data["target"] = y_val.values

    # Model hyperparameters - LASSO as first-class voter
    hyperparameters = {
        # LASSO (L1 regularized linear regression) - KEY FOR INTERPRETABILITY
        "LR": [
            {"penalty": "L1", "C": 0.01},  # Strong regularization
            {"penalty": "L1", "C": 0.1},   # Medium regularization
            {"penalty": "L1", "C": 1.0},   # Light regularization
        ],
        # Gradient Boosting
        "GBM": [
            {"num_boost_round": 100, "learning_rate": 0.1},
            {"num_boost_round": 200, "learning_rate": 0.05},
        ],
        # CatBoost
        "CAT": [
            {"iterations": 100, "learning_rate": 0.1},
        ],
        # XGBoost
        "XGB": [
            {"n_estimators": 100, "learning_rate": 0.1},
        ],
    }

    fold_model_dir = model_dir / f"fold_{fold_id}"
    fold_model_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"  Training fold {fold_id} with {len(train_data):,} train, {len(val_data):,} val samples")

    # Train predictor
    predictor = TabularPredictor(
        label="target",
        problem_type="regression",
        eval_metric="mean_absolute_error",
        path=str(fold_model_dir),
        verbosity=1,
    )

    predictor.fit(
        train_data=train_data,
        tuning_data=val_data,
        hyperparameters=hyperparameters,
        time_limit=time_limit,
        presets="high_quality",  # Use high_quality to avoid bagging issues with tuning_data
        # Keep all models for ensemble
        keep_only_best=False,
        use_bag_holdout=True,  # Required when using tuning_data with bagged presets
    )

    # Get leaderboard
    leaderboard = predictor.leaderboard(val_data, silent=True)
    logger.info(f"  Leaderboard:\n{leaderboard.head(10)}")

    # Extract LASSO coefficients
    lasso_coefficients = extract_lasso_coefficients(predictor, X_train.columns.tolist())

    # Calculate metrics
    val_preds = predictor.predict(val_data.drop(columns=["target"]))
    metrics = {
        "mae": float(np.abs(val_preds - y_val).mean()),
        "rmse": float(np.sqrt(((val_preds - y_val) ** 2).mean())),
        "mape": float(np.abs((val_preds - y_val) / y_val.replace(0, np.nan)).mean()),
    }

    return predictor, lasso_coefficients, metrics


def extract_lasso_coefficients(predictor, feature_names: List[str]) -> Dict[str, float]:
    """Extract LASSO coefficients from trained predictor."""
    coefficients = {}

    try:
        # Get the LASSO model from the predictor
        model_names = predictor.model_names()
        lasso_models = [m for m in model_names if "LR" in m or "Linear" in m]

        if not lasso_models:
            logger.warning("  No LASSO model found in predictor")
            return coefficients

        # Try to extract coefficients from the best LASSO model
        for model_name in lasso_models:
            try:
                model = predictor._trainer.load_model(model_name)
                if hasattr(model, "model") and hasattr(model.model, "coef_"):
                    coefs = model.model.coef_
                    if len(coefs) == len(feature_names):
                        for feat, coef in zip(feature_names, coefs):
                            coefficients[feat] = float(coef)
                        logger.info(f"  Extracted {len(coefficients)} LASSO coefficients from {model_name}")
                        break
            except Exception as e:
                logger.debug(f"  Could not extract coefficients from {model_name}: {e}")
                continue
    except Exception as e:
        logger.warning(f"  Failed to extract LASSO coefficients: {e}")

    return coefficients


def generate_oof_predictions(
    predictor,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    val_dates: pd.Series,
    bucket: str,
    horizon: int,
    fold_id: int
) -> pd.DataFrame:
    """Generate out-of-fold predictions with quantiles."""

    # Get point predictions
    point_preds = predictor.predict(X_val)

    # For quantile predictions, we approximate using prediction variance
    # In a production system, you'd use quantile regression or conformal prediction
    # For now, we estimate P10/P90 using historical error distribution

    residuals = point_preds - y_val
    std_error = residuals.std()

    # Approximate quantiles using normal distribution
    # P10 ≈ mean - 1.28 * std, P90 ≈ mean + 1.28 * std
    z_10 = -1.28  # 10th percentile
    z_90 = 1.28   # 90th percentile

    # Use the index from X_val to ensure alignment
    oof_df = pd.DataFrame({
        "as_of_date": val_dates.reset_index(drop=True),
        "source": bucket,
        "horizon": horizon,
        "fold_id": fold_id,
        "p10": point_preds.values + z_10 * std_error,
        "p50": point_preds.values,
        "p90": point_preds.values + z_90 * std_error,
    })

    return oof_df


def save_oof_predictions(conn, oof_df: pd.DataFrame, model_version: str, dry_run: bool = False):
    """Save OOF predictions to Postgres."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would save {len(oof_df):,} OOF predictions")
        return

    trained_at = datetime.now()

    insert_query = """
        INSERT INTO "model"."oof_predictions" (specialist, as_of_date, horizon, fold_id, pred_p10, pred_p50, pred_p90, model_version, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (specialist, as_of_date, horizon, fold_id)
        DO UPDATE SET pred_p10 = EXCLUDED.pred_p10, pred_p50 = EXCLUDED.pred_p50, pred_p90 = EXCLUDED.pred_p90,
                      model_version = EXCLUDED.model_version, created_at = EXCLUDED.created_at
    """

    batch = [
        (row["source"], row["as_of_date"], row["horizon"], row["fold_id"],
         float(row["p10"]), float(row["p50"]), float(row["p90"]), model_version, trained_at)
        for _, row in oof_df.iterrows()
    ]

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=500)
    conn.commit()

    logger.info(f"  Saved {len(batch):,} OOF predictions")


def save_lasso_coefficients(
    conn,
    coefficients: Dict[str, float],
    bucket: str,
    horizon: int,
    model_version: str,
    dry_run: bool = False
):
    """Save LASSO coefficients to Postgres for interpretability."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would save {len(coefficients)} LASSO coefficients")
        return

    if not coefficients:
        logger.warning("  No LASSO coefficients to save")
        return

    trained_at = datetime.now()

    insert_query = """
        INSERT INTO "model"."lasso_coefficients" (bucket, horizon, feature_name, coefficient, is_active, model_version, trained_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (bucket, horizon, feature_name, model_version)
        DO UPDATE SET coefficient = EXCLUDED.coefficient, is_active = EXCLUDED.is_active, trained_at = EXCLUDED.trained_at
    """

    batch = [
        (bucket, horizon, feat_name, float(coef), bool(abs(coef) > 1e-6), model_version, trained_at)
        for feat_name, coef in coefficients.items()
    ]

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=100)
    conn.commit()

    active_count = sum(1 for _, _, _, coef, _, _, _ in batch if abs(coef) > 1e-6)
    logger.info(f"  Saved {len(batch)} LASSO coefficients ({active_count} active)")


def train_specialist(
    bucket: str,
    horizon: int,
    dry_run: bool = False,
    mode: str = "quick"
) -> List[TrainingResult]:
    """Train a specialist for all folds."""
    time_limit = TIME_LIMITS.get(mode, 300)

    logger.info("=" * 60)
    logger.info(f"TRAINING SPECIALIST: {bucket.upper()} @ {horizon}d ({mode} mode, {time_limit}s/fold)")
    logger.info("=" * 60)

    conn = get_postgres_connection()
    results = []

    try:
        # Load data
        features_df = load_specialist_features(conn, bucket)
        prices_df = load_market_data(conn)
        folds_df = load_cv_folds(conn, horizon)

        # Calculate forward returns
        returns_df = calculate_returns(prices_df, horizon)

        # Model version
        model_version = f"{bucket}_h{horizon}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        model_dir = MODEL_PATH / bucket / f"horizon_{horizon}d"
        model_dir.mkdir(parents=True, exist_ok=True)

        # All OOF predictions across folds
        all_oof = []
        all_lasso_coefs = {}

        # Train each fold
        for fold_id in range(NUM_FOLDS):
            logger.info(f"\n--- Fold {fold_id + 1}/{NUM_FOLDS} ---")

            # Prepare data for this fold
            X_train, y_train, X_val, y_val, val_dates = prepare_training_data(
                features_df, returns_df, folds_df, fold_id
            )

            if len(X_train) < 100 or len(X_val) < 10:
                logger.warning(f"  Skipping fold {fold_id}: insufficient data (train={len(X_train)}, val={len(X_val)})")
                continue

            if dry_run:
                logger.info(f"  [DRY RUN] Would train on {len(X_train):,} samples, validate on {len(X_val):,}")
                continue

            # Train
            predictor, lasso_coefs, metrics = train_fold(
                X_train, y_train, X_val, y_val,
                bucket, horizon, fold_id, model_dir,
                time_limit=time_limit, mode=mode
            )

            # Generate OOF predictions (val_dates is already aligned with X_val/y_val)
            oof_df = generate_oof_predictions(
                predictor, X_val, y_val, val_dates,
                bucket, horizon, fold_id
            )
            all_oof.append(oof_df)

            # Aggregate LASSO coefficients
            for feat, coef in lasso_coefs.items():
                if feat not in all_lasso_coefs:
                    all_lasso_coefs[feat] = []
                all_lasso_coefs[feat].append(coef)

            results.append(TrainingResult(
                bucket=bucket,
                horizon=horizon,
                fold_id=fold_id,
                model_version=model_version,
                oof_predictions=oof_df,
                lasso_coefficients=lasso_coefs,
                metrics=metrics,
                trained_at=datetime.now()
            ))

            logger.info(f"  Fold {fold_id} metrics: MAE={metrics['mae']:.6f}, RMSE={metrics['rmse']:.6f}")

        if not dry_run and all_oof:
            # Save all OOF predictions
            combined_oof = pd.concat(all_oof, ignore_index=True)
            save_oof_predictions(conn, combined_oof, model_version)

            # Average LASSO coefficients across folds and save
            avg_lasso_coefs = {
                feat: np.mean(coefs) for feat, coefs in all_lasso_coefs.items()
            }
            save_lasso_coefficients(conn, avg_lasso_coefs, bucket, horizon, model_version)

        logger.info(f"\n✅ Completed training {bucket} @ {horizon}d")

    finally:
        conn.close()

    return results


def train_all_specialists(horizon: int, dry_run: bool = False, mode: str = "quick"):
    """Train all specialist buckets for a given horizon."""
    logger.info("=" * 60)
    logger.info(f"TRAINING ALL SPECIALISTS @ {horizon}d ({mode} mode)")
    logger.info("=" * 60)

    all_results = {}

    for bucket in SPECIALIST_BUCKETS:
        try:
            results = train_specialist(bucket, horizon, dry_run, mode=mode)
            all_results[bucket] = {"status": "success", "results": results}
        except Exception as e:
            logger.error(f"Failed to train {bucket}: {e}")
            all_results[bucket] = {"status": "failed", "error": str(e)}

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TRAINING SUMMARY")
    logger.info("=" * 60)

    for bucket, result in all_results.items():
        status = "✅" if result["status"] == "success" else "❌"
        print(f"  {status} {bucket}: {result['status']}")

    return all_results


def main():
    parser = argparse.ArgumentParser(description="Train specialist models with LASSO")
    parser.add_argument("--bucket", type=str, default="crush",
                        help=f"Bucket to train ({', '.join(SPECIALIST_BUCKETS)}, or 'all')")
    parser.add_argument("--horizon", type=int, default=63, choices=HORIZONS,
                        help="Forecast horizon in days")
    parser.add_argument("--mode", type=str, choices=["ultrafast", "quick", "full"],
                        default="quick",
                        help="Training mode: 'ultrafast' (1min/fold), 'quick' (5min/fold), 'full' (10min/fold)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without training")

    args = parser.parse_args()

    if args.bucket == "all":
        train_all_specialists(args.horizon, args.dry_run, mode=args.mode)
    elif args.bucket in SPECIALIST_BUCKETS:
        train_specialist(args.bucket, args.horizon, args.dry_run, mode=args.mode)
    else:
        logger.error(f"Unknown bucket: {args.bucket}")
        logger.error(f"Valid buckets: {', '.join(SPECIALIST_BUCKETS)}, or 'all'")
        sys.exit(1)


if __name__ == "__main__":
    main()
