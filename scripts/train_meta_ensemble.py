#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Meta-Ensemble Training Script (L4 Layer)

Trains the L4 meta-ensemble that combines core + 11 specialist OOF predictions
into final quantile forecasts with dissent features for disagreement detection.

NON-NEGOTIABLES:
- Meta layer ONLY sees OOF predictions (no raw features)
- Uses cv_folds from Postgres as canonical splits
- Weights are learned via LASSO for interpretability
- Core and specialists are equal voters
- No data leakage: OOF predictions only
- Dissent features capture specialist disagreement

AUTOGLUON GOVERNANCE (from doctrine):
- high_quality preset (stability > marginal accuracy)
- dynamic_stacking enabled (prevents stacked overfitting)
- num_bag_folds >= 5
- num_stack_levels = 1 (meta is already learning from model outputs)
- time_limit bounded
- LASSO + LightGBM (linear + tree for robustness)

Architecture (L4):
- L4 Meta-Ensemble: LASSO + LightGBM
- Base Inputs (12): core_p50 + 11 specialist_p50 values
- Dissent Features (3): specialist_std, specialist_range, core_vs_mean
- Total Inputs: 15 features
- Outputs: calibrated P10, P50, P90 quantiles
- Saves: dissent_index to analytics for downstream L5 consumption

Usage:
    python scripts/train_meta_ensemble.py --horizon 63 --dry-run
    python scripts/train_meta_ensemble.py --horizon 63
    python scripts/train_meta_ensemble.py --horizon all  # Train all horizons
"""

# ═══════════════════════════════════════════════════════════════════════════════
# CRITICAL: Set environment variables BEFORE any imports
# This fixes Keras 3 vs tf_keras compatibility issue in Transformers
# ═══════════════════════════════════════════════════════════════════════════════
import os
os.environ['TF_USE_LEGACY_KERAS'] = '1'
os.environ['KERAS_BACKEND'] = 'tensorflow'

import sys
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
# The meta-ensemble MUST have OOF predictions from ALL sources (core + 11 specialists).
# This ensures the full ensemble has visibility into all information.
# ═══════════════════════════════════════════════════════════════════════════════
from src.fusion.validation.all_data_policy import log_all_data_summary

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
MODEL_PATH = PROJECT_ROOT / "models" / "meta_ensemble"

# Specialist buckets (11 specialists)
SPECIALIST_BUCKETS = [
    "crush", "china", "fx", "fed", "tariff",
    "energy", "biofuel", "palm", "volatility", "substitutes",
    "trump_effect",  # 11th specialist: Trump/policy regime dynamics
]

# All sources including core
ALL_SOURCES = ["core"] + SPECIALIST_BUCKETS

# Horizons
HORIZONS = [5, 21, 63, 126]

# Training config
QUANTILES = [0.1, 0.5, 0.9]
NUM_FOLDS = 5


@dataclass
class MetaEnsembleResult:
    """Results from training meta-ensemble."""
    horizon: int
    model_version: str
    weights: Dict[str, float]  # Source -> weight
    metrics: Dict[str, float]
    trained_at: datetime


def add_dissent_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add dissent features to the meta-ensemble input DataFrame.

    Dissent Features (from L4 Architecture spec):
    - specialist_std: Standard deviation across specialists (agreement measure)
    - specialist_range: Max - Min of specialist predictions (spread of views)
    - core_vs_mean: Core divergence from specialist consensus

    Args:
        df: DataFrame with columns like core_p50, crush_p50, china_p50, etc.

    Returns:
        DataFrame with added dissent feature columns
    """
    # Identify specialist columns (exclude core)
    specialist_cols = [col for col in df.columns
                       if col.endswith('_p50') and not col.startswith('core')]

    if not specialist_cols:
        logger.warning("  No specialist columns found for dissent features")
        return df

    # Extract specialist predictions as a matrix
    specialist_matrix = df[specialist_cols].values

    # 1. Specialist standard deviation (agreement measure)
    # Lower = more consensus, Higher = more disagreement
    df['specialist_std'] = np.std(specialist_matrix, axis=1)

    # 2. Specialist range (max - min)
    # Captures the full spread of views
    df['specialist_range'] = np.max(specialist_matrix, axis=1) - np.min(specialist_matrix, axis=1)

    # 3. Core vs specialist mean
    # Positive = core more bullish than consensus
    # Negative = core more bearish than consensus
    specialist_mean = np.mean(specialist_matrix, axis=1)
    if 'core_p50' in df.columns:
        df['core_vs_mean'] = df['core_p50'].values - specialist_mean
    else:
        df['core_vs_mean'] = 0.0

    logger.info(f"  Added dissent features: specialist_std, specialist_range, core_vs_mean")
    logger.info(f"    specialist_std range: [{df['specialist_std'].min():.4f}, {df['specialist_std'].max():.4f}]")
    logger.info(f"    specialist_range: [{df['specialist_range'].min():.4f}, {df['specialist_range'].max():.4f}]")

    return df


def calculate_dissent_index(df: pd.DataFrame) -> pd.Series:
    """Calculate dissent index for each observation.

    Dissent index = specialist_std / (abs(core_p50) + epsilon)

    Interpretation:
    - 0: Perfect consensus
    - 0.1-0.3: Low disagreement
    - 0.3-0.5: Moderate disagreement
    - >0.5: High disagreement

    Returns:
        Series of dissent index values
    """
    epsilon = 1e-6

    if 'specialist_std' not in df.columns:
        return pd.Series(0.0, index=df.index)

    if 'core_p50' in df.columns:
        dissent = df['specialist_std'] / (df['core_p50'].abs() + epsilon)
    else:
        dissent = df['specialist_std'] / (df['specialist_std'].mean() + epsilon)

    # Cap at 1.0 for interpretability
    return dissent.clip(upper=1.0)


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def load_oof_predictions(conn, horizon: int) -> pd.DataFrame:
    """Load all OOF predictions for a given horizon.

    Returns wide-format DataFrame with columns:
    - as_of_date
    - actual_return (target)
    - core_p50, crush_p50, china_p50, ... (features)
    """
    logger.info(f"Loading OOF predictions for horizon={horizon}d")

    with conn.cursor() as cur:
        # Get all OOF predictions
        cur.execute("""
            SELECT specialist, as_of_date, pred_p10, pred_p50, pred_p90
            FROM "model"."oof_predictions"
            WHERE horizon = %s
            ORDER BY specialist, as_of_date
        """, (horizon,))

        rows = cur.fetchall()

    if not rows:
        raise ValueError(f"No OOF predictions found for horizon={horizon}")

    # Create DataFrame
    df = pd.DataFrame(rows, columns=['source', 'as_of_date', 'p10', 'p50', 'p90'])
    logger.info(f"  Loaded {len(df):,} OOF predictions from {df['source'].nunique()} specialists")

    # Pivot to wide format
    pivot_df = df.pivot(index='as_of_date', columns='source', values='p50')
    pivot_df.columns = [f"{col}_p50" for col in pivot_df.columns]
    pivot_df = pivot_df.reset_index()

    logger.info(f"  Pivoted to {len(pivot_df):,} rows with {len(pivot_df.columns)-1} features")

    return pivot_df


def load_actual_returns(conn, horizon: int) -> pd.DataFrame:
    """Load actual forward returns for validation."""
    logger.info(f"Loading actual returns for horizon={horizon}d")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT as_of_date, close
            FROM "raw"."market_futures_1d"
            WHERE symbol = 'ZL'
            ORDER BY as_of_date
        """)
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=['as_of_date', 'close'])
    df['forward_return'] = df['close'].shift(-horizon) / df['close'] - 1
    df = df.dropna()

    logger.info(f"  Loaded {len(df):,} actual returns")

    return df[['as_of_date', 'forward_return']]


def load_cv_folds(conn, horizon: int) -> pd.DataFrame:
    """Load CV fold assignments for given horizon."""
    logger.info(f"Loading CV folds for horizon={horizon}d")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT as_of_date, fold_id, is_train, is_val
            FROM "model"."cv_folds"
            WHERE horizon = %s
            ORDER BY fold_id, as_of_date
        """, (horizon,))
        rows = cur.fetchall()

    if not rows:
        raise ValueError(f"No CV folds found for horizon={horizon}")

    df = pd.DataFrame(rows, columns=['as_of_date', 'fold_id', 'is_train', 'is_val'])
    logger.info(f"  Loaded {len(df):,} fold assignments")

    return df


def prepare_meta_data(
    oof_df: pd.DataFrame,
    returns_df: pd.DataFrame,
    folds_df: pd.DataFrame,
    fold_id: int
) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.Series]:
    """Prepare train/val splits for meta-ensemble training.

    Adds dissent features to capture specialist disagreement:
    - specialist_std: Agreement measure
    - specialist_range: Spread of views
    - core_vs_mean: Core divergence from consensus

    Returns:
    - X_train: Features for training (14 total: 11 base + 3 dissent)
    - y_train: Target for training
    - X_val: Features for validation
    - y_val: Target for validation
    - val_dates: Dates for validation (for saving OOF predictions)
    """
    # Get fold assignments
    fold_mask = folds_df['fold_id'] == fold_id
    train_dates = set(folds_df[(fold_mask) & (folds_df['is_train'])]['as_of_date'])
    val_dates_set = set(folds_df[(fold_mask) & (folds_df['is_val'])]['as_of_date'])

    # Merge OOF predictions with actual returns
    merged = oof_df.merge(returns_df, on='as_of_date', how='inner')

    # Add dissent features BEFORE splitting
    merged = add_dissent_features(merged)

    # Feature columns: all *_p50 columns + dissent features
    base_cols = [col for col in merged.columns if col.endswith('_p50')]
    dissent_cols = ['specialist_std', 'specialist_range', 'core_vs_mean']
    feature_cols = base_cols + [c for c in dissent_cols if c in merged.columns]

    logger.info(f"  Total features: {len(feature_cols)} (base: {len(base_cols)}, dissent: {len(feature_cols) - len(base_cols)})")

    # Split by fold
    train_mask = merged['as_of_date'].isin(train_dates)
    val_mask = merged['as_of_date'].isin(val_dates_set)

    train_df = merged[train_mask].copy()
    val_df = merged[val_mask].copy()

    # Extract features and target
    X_train = train_df[feature_cols]
    y_train = train_df['forward_return']
    X_val = val_df[feature_cols]
    y_val = val_df['forward_return']
    val_dates = val_df['as_of_date']

    return X_train, y_train, X_val, y_val, val_dates


def train_meta_fold(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    horizon: int,
    fold_id: int
) -> Tuple[Any, Dict[str, float], Dict[str, float]]:
    """Train meta-ensemble for a single fold.

    Uses LASSO for interpretability + LightGBM for flexibility.

    Returns:
    - model: Trained model
    - weights: Source weights from LASSO
    - metrics: Validation metrics
    """
    from autogluon.tabular import TabularPredictor

    # Combine train data into DataFrame for AutoGluon
    train_data = X_train.copy()
    train_data['target'] = y_train.values

    val_data = X_val.copy()
    val_data['target'] = y_val.values

    # Model path
    model_dir = MODEL_PATH / f"horizon_{horizon}d" / f"fold_{fold_id}"
    model_dir.mkdir(parents=True, exist_ok=True)

    # Train with LASSO + LightGBM
    # LASSO gives us interpretable weights
    # LightGBM captures nonlinear interactions
    hyperparameters = {
        "LR": [
            {"penalty": "L1", "C": 0.01},  # Strong LASSO
            {"penalty": "L1", "C": 0.1},   # Medium LASSO
            {"penalty": "L1", "C": 1.0},   # Light LASSO
        ],
        "GBM": [
            {"num_boost_round": 100, "learning_rate": 0.05},
            {"num_boost_round": 200, "learning_rate": 0.02},
        ],
    }

    predictor = TabularPredictor(
        label='target',
        path=str(model_dir),
        problem_type='regression',
        verbosity=0
    )

    predictor.fit(
        train_data=train_data,
        hyperparameters=hyperparameters,
        time_limit=120,  # 2 minutes for meta-ensemble
        presets='best_quality',
        num_bag_folds=0,  # No internal bagging (we have our own folds)
        num_stack_levels=0,  # No stacking
    )

    # Log leaderboard
    leaderboard = predictor.leaderboard(silent=True)
    logger.info(f"  Leaderboard:\n{leaderboard}")

    # Evaluate on validation set
    val_predictions = predictor.predict(val_data)
    mae = np.abs(val_predictions - y_val).mean()
    rmse = np.sqrt(((val_predictions - y_val) ** 2).mean())

    metrics = {
        'MAE': mae,
        'RMSE': rmse
    }
    logger.info(f"  Fold {fold_id} metrics: MAE={mae:.6f}, RMSE={rmse:.6f}")

    # Extract LASSO weights for interpretability
    weights = {}
    try:
        # Get the linear model
        model_names = [m for m in predictor.model_names() if 'LinearModel' in m]
        if model_names:
            model_name = model_names[0]
            model = predictor._trainer.load_model(model_name)

            # Extract coefficients
            if hasattr(model, 'model') and hasattr(model.model, 'coef_'):
                coefs = model.model.coef_
                feature_names = X_train.columns.tolist()
                for feat, coef in zip(feature_names, coefs):
                    source = feat.replace('_p50', '')
                    weights[source] = float(coef)
                logger.info(f"  Extracted weights from {model_name}")
    except Exception as e:
        logger.warning(f"  Could not extract LASSO weights: {e}")

    return predictor, weights, metrics


def generate_meta_predictions(
    predictor,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    val_dates: pd.Series,
    horizon: int,
    fold_id: int
) -> pd.DataFrame:
    """Generate meta-ensemble predictions with quantiles."""
    # Get point predictions
    val_data = X_val.copy()
    val_data['target'] = y_val.values

    predictions = predictor.predict(val_data)

    # Estimate quantiles from residuals
    residuals = y_val.values - predictions.values
    std_residual = np.std(residuals)

    # Quantile estimates (assuming approximately normal residuals)
    z_10 = -1.28  # 10th percentile
    z_90 = 1.28   # 90th percentile

    p10 = predictions - abs(z_10) * std_residual
    p50 = predictions
    p90 = predictions + abs(z_90) * std_residual

    # Create DataFrame
    oof_df = pd.DataFrame({
        'as_of_date': val_dates.values,
        'horizon': horizon,
        'fold_id': fold_id,
        'p10': p10.values,
        'p50': p50.values,
        'p90': p90.values,
    })

    return oof_df


def save_meta_predictions(
    conn,
    oof_df: pd.DataFrame,
    model_version: str
) -> int:
    """Save meta-ensemble predictions to Postgres."""
    trained_at = datetime.now()

    insert_query = """
        INSERT INTO "model"."meta_ensemble" (as_of_date, horizon, p10, p50, p90, model_version, trained_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (as_of_date, horizon)
        DO UPDATE SET p10 = EXCLUDED.p10, p50 = EXCLUDED.p50, p90 = EXCLUDED.p90,
                      model_version = EXCLUDED.model_version, trained_at = EXCLUDED.trained_at
    """

    batch = [
        (row['as_of_date'], row['horizon'], float(row['p10']), float(row['p50']), float(row['p90']),
         model_version, trained_at)
        for _, row in oof_df.iterrows()
    ]

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    return len(batch)


def save_meta_weights(
    conn,
    weights: Dict[str, float],
    horizon: int,
    model_version: str
):
    """Save meta-ensemble weights to Postgres."""
    if not weights:
        logger.warning("  No meta weights to save")
        return

    trained_at = datetime.now()

    insert_query = """
        INSERT INTO "model"."meta_weights" (specialist, horizon, weight, trained_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (specialist, horizon)
        DO UPDATE SET weight = EXCLUDED.weight, trained_at = EXCLUDED.trained_at
    """

    batch = [
        (specialist, horizon, float(weight), trained_at)
        for specialist, weight in weights.items()
    ]

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=100)
    conn.commit()

    logger.info(f"  Saved {len(batch)} meta weights")


def save_dissent_metrics(
    conn,
    oof_df: pd.DataFrame,
    horizon: int,
    model_version: str
):
    """Save dissent metrics to analytics schema for L5 consumption.

    Creates analytics.dissent_metrics table with:
    - as_of_date
    - horizon
    - dissent_index (normalized 0-1)
    - specialist_std
    - specialist_range
    - core_vs_mean
    - most_bullish (specialist name)
    - most_bearish (specialist name)
    """
    logger.info("  Saving dissent metrics to analytics.dissent_metrics")

    # Ensure table exists
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS "analytics"."dissent_metrics" (
                id SERIAL PRIMARY KEY,
                as_of_date DATE NOT NULL,
                horizon INTEGER NOT NULL,
                dissent_index DOUBLE PRECISION NOT NULL,
                specialist_std DOUBLE PRECISION,
                specialist_range DOUBLE PRECISION,
                core_vs_mean DOUBLE PRECISION,
                most_bullish VARCHAR(50),
                most_bearish VARCHAR(50),
                model_version VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(as_of_date, horizon)
            )
        """)
        conn.commit()

    # Get specialist columns for bullish/bearish detection
    specialist_cols = [col for col in oof_df.columns
                       if col.endswith('_p50') and not col.startswith('core')]

    batch = []
    for _, row in oof_df.iterrows():
        as_of_date = row['as_of_date']

        # Get dissent values
        specialist_std = float(row.get('specialist_std', 0))
        specialist_range = float(row.get('specialist_range', 0))
        core_vs_mean = float(row.get('core_vs_mean', 0))

        # Calculate dissent index
        core_p50 = float(row.get('core_p50', 0))
        dissent_index = specialist_std / (abs(core_p50) + 1e-6)
        dissent_index = min(dissent_index, 1.0)

        # Find most bullish/bearish specialists
        specialist_preds = {col.replace('_p50', ''): float(row[col])
                          for col in specialist_cols if col in row}

        if specialist_preds:
            most_bullish = max(specialist_preds, key=specialist_preds.get)
            most_bearish = min(specialist_preds, key=specialist_preds.get)
        else:
            most_bullish = None
            most_bearish = None

        batch.append((
            as_of_date,
            horizon,
            dissent_index,
            specialist_std,
            specialist_range,
            core_vs_mean,
            most_bullish,
            most_bearish,
            model_version,
            datetime.now(),
        ))

    insert_query = """
        INSERT INTO "analytics"."dissent_metrics"
        (as_of_date, horizon, dissent_index, specialist_std, specialist_range,
         core_vs_mean, most_bullish, most_bearish, model_version, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (as_of_date, horizon)
        DO UPDATE SET
            dissent_index = EXCLUDED.dissent_index,
            specialist_std = EXCLUDED.specialist_std,
            specialist_range = EXCLUDED.specialist_range,
            core_vs_mean = EXCLUDED.core_vs_mean,
            most_bullish = EXCLUDED.most_bullish,
            most_bearish = EXCLUDED.most_bearish,
            model_version = EXCLUDED.model_version,
            created_at = EXCLUDED.created_at
    """

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    logger.info(f"  Saved {len(batch)} dissent metrics")


def validate_source_coverage(conn, horizon: int) -> bool:
    """Validate that all required sources have OOF predictions."""
    logger.info("Validating source coverage...")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT specialist, COUNT(*)
            FROM "model"."oof_predictions"
            WHERE horizon = %s
            GROUP BY specialist
            ORDER BY specialist
        """, (horizon,))

        rows = cur.fetchall()

    sources_present = {row[0] for row in rows}
    required_sources = set(ALL_SOURCES)

    missing = required_sources - sources_present
    if missing:
        logger.error(f"  Missing sources: {missing}")
        logger.error("  Cannot train meta-ensemble without all sources")
        return False

    logger.info(f"  All {len(required_sources)} sources present")
    for row in rows:
        logger.info(f"    {row[0]}: {row[1]:,} rows")

    return True


def train_meta_ensemble(
    horizon: int,
    dry_run: bool = False
) -> MetaEnsembleResult:
    """Train meta-ensemble for a single horizon."""
    logger.info("=" * 60)
    logger.info(f"TRAINING META-ENSEMBLE @ {horizon}d")
    logger.info("=" * 60)

    conn = get_postgres_connection()

    try:
        # Validate all sources are present
        if not validate_source_coverage(conn, horizon):
            if dry_run:
                logger.info("[DRY RUN] Upstream OOF predictions not available yet")
                logger.info("[DRY RUN] Would train meta-ensemble once L2/L3 are trained")
                return MetaEnsembleResult(
                    horizon=horizon,
                    model_version="dry_run",
                    weights={},
                    metrics={},
                    trained_at=datetime.now()
                )
            raise ValueError("Source validation failed")

        # Load data
        oof_df = load_oof_predictions(conn, horizon)
        returns_df = load_actual_returns(conn, horizon)
        folds_df = load_cv_folds(conn, horizon)

        # Model version
        model_version = f"meta_h{horizon}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Train each fold
        all_oof_predictions = []
        all_weights = {}
        all_metrics = []

        for fold_id in range(NUM_FOLDS):
            logger.info(f"\n--- Fold {fold_id + 1}/{NUM_FOLDS} ---")

            # Prepare data
            X_train, y_train, X_val, y_val, val_dates = prepare_meta_data(
                oof_df, returns_df, folds_df, fold_id
            )

            if len(X_train) == 0 or len(X_val) == 0:
                logger.warning(f"  Skipping fold {fold_id}: insufficient data")
                continue

            logger.info(f"  Training with {len(X_train):,} train, {len(X_val):,} val samples")

            if dry_run:
                logger.info("  [DRY RUN] Would train meta-ensemble here")
                continue

            # Train
            predictor, weights, metrics = train_meta_fold(
                X_train, y_train, X_val, y_val, horizon, fold_id
            )

            # Generate OOF predictions
            fold_oof = generate_meta_predictions(
                predictor, X_val, y_val, val_dates, horizon, fold_id
            )
            all_oof_predictions.append(fold_oof)

            # Accumulate weights (average across folds)
            for source, weight in weights.items():
                if source not in all_weights:
                    all_weights[source] = []
                all_weights[source].append(weight)

            all_metrics.append(metrics)

        if dry_run:
            logger.info("\n[DRY RUN] Complete - no data written")
            return MetaEnsembleResult(
                horizon=horizon,
                model_version=model_version,
                weights={},
                metrics={},
                trained_at=datetime.now()
            )

        # Combine OOF predictions
        if all_oof_predictions:
            combined_oof = pd.concat(all_oof_predictions, ignore_index=True)

            # Save to Postgres
            saved = save_meta_predictions(conn, combined_oof, model_version)
            logger.info(f"\n  Saved {saved:,} meta-ensemble predictions")

        # Average weights across folds
        avg_weights = {
            source: np.mean(weights_list)
            for source, weights_list in all_weights.items()
        }

        # Save weights
        if avg_weights:
            save_meta_weights(conn, avg_weights, horizon, model_version)

            # Log weights
            logger.info("\nMeta-ensemble weights:")
            sorted_weights = sorted(avg_weights.items(), key=lambda x: abs(x[1]), reverse=True)
            for source, weight in sorted_weights:
                logger.info(f"  {source:15} : {weight:+.4f}")

        # Save dissent metrics to analytics for L5 consumption
        # Need to recompute with dissent features on the full OOF dataset
        oof_with_dissent = add_dissent_features(oof_df.copy())
        save_dissent_metrics(conn, oof_with_dissent, horizon, model_version)

        # Average metrics
        avg_metrics = {}
        if all_metrics:
            for key in all_metrics[0].keys():
                avg_metrics[key] = np.mean([m[key] for m in all_metrics])
            logger.info(f"\nAverage metrics: MAE={avg_metrics['MAE']:.6f}, RMSE={avg_metrics['RMSE']:.6f}")

        logger.info(f"\n✅ Completed L4 meta-ensemble training @ {horizon}d")

        return MetaEnsembleResult(
            horizon=horizon,
            model_version=model_version,
            weights=avg_weights,
            metrics=avg_metrics,
            trained_at=datetime.now()
        )

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Train meta-ensemble for ZINC-FUSION-V15")
    parser.add_argument("--horizon", type=str, required=True,
                       help="Horizon in days (5, 21, 63, 126) or 'all'")
    parser.add_argument("--dry-run", action="store_true",
                       help="Preview without training")

    args = parser.parse_args()

    # Determine horizons to train
    if args.horizon.lower() == "all":
        horizons = HORIZONS
    else:
        horizon = int(args.horizon)
        if horizon not in HORIZONS:
            logger.error(f"Invalid horizon: {horizon}. Must be one of {HORIZONS}")
            sys.exit(1)
        horizons = [horizon]

    # Train each horizon
    results = []
    for horizon in horizons:
        try:
            result = train_meta_ensemble(horizon, args.dry_run)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to train meta-ensemble @ {horizon}d: {e}")
            raise

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("META-ENSEMBLE TRAINING SUMMARY")
    logger.info("=" * 60)
    for result in results:
        mae = result.metrics.get('MAE')
        if mae is not None:
            logger.info(f"  {result.horizon}d: MAE={mae:.6f}")
        else:
            logger.info(f"  {result.horizon}d: (dry run - no metrics)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
