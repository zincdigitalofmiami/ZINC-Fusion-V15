#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Core Model Training with OOF Generation
Enhanced version that implements 8-fold CV and generates out-of-fold predictions

Key Enhancements:
1. 8-fold TimeSeriesSplit cross-validation
2. Out-of-fold prediction generation
3. Saves OOF predictions to model.oof_predictions
4. Calculates and saves metrics to model.model_registry
5. Implements get_oof_pred() pattern

Usage:
    python scripts/v15_core_training/train_core_with_oof.py --horizon 5
    python scripts/v15_core_training/train_core_with_oof.py --horizon all
    python scripts/v15_core_training/train_core_with_oof.py --horizon 21 --dry-run
"""

from __future__ import annotations

import os
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
os.environ["ACCELERATE_USE_MPS_DEVICE"] = "True"
os.environ["TF_USE_LEGACY_KERAS"] = "1"
os.environ["KERAS_BACKEND"] = "tensorflow"

import sys
import logging
import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import uuid

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv
from sklearn.model_selection import TimeSeriesSplit

# Project imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

HORIZONS = [5, 21, 63, 126]
QUANTILE_LEVELS = [0.1, 0.5, 0.9, 0.95]  # P10, P50, P90, P95
N_FOLDS = 8  # 8-fold cross-validation
MODEL_ROOT = PROJECT_ROOT / "models" / "core_v15"
SYMBOL = "ZL"  # Soybean Oil futures

@dataclass(frozen=True)
class HorizonSpec:
    """Specification for a single horizon."""
    name: str
    prediction_length: int
    mode: str  # "tactical" or "strategic"

    @property
    def is_tactical(self) -> bool:
        return self.mode == "tactical"

HORIZON_SPECS = {
    5: HorizonSpec("5d", 5, "tactical"),
    21: HorizonSpec("21d", 21, "tactical"),
    63: HorizonSpec("63d", 63, "strategic"),
    126: HorizonSpec("126d", 126, "strategic"),
}

# =============================================================================
# DATABASE CONNECTION
# =============================================================================

def get_postgres_connection():
    """Get PostgreSQL connection."""
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set in environment")
    return psycopg2.connect(DATABASE_URL)

# =============================================================================
# DATA PREPARATION
# =============================================================================

def load_core_features(conn) -> pd.DataFrame:
    """Load core features from training.core_features."""
    query = """
    SELECT 
        as_of_date,
        features
    FROM training.core_features
    ORDER BY as_of_date;
    """
    df = pd.read_sql(query, conn)
    
    # Expand JSON features into columns
    features_df = pd.DataFrame(df['features'].tolist())
    features_df['as_of_date'] = df['as_of_date']
    
    return features_df

def prepare_timeseries_data(df: pd.DataFrame, spec: HorizonSpec) -> pd.DataFrame:
    """
    Prepare data for AutoGluon TimeSeriesPredictor.
    
    Args:
        df: DataFrame with as_of_date and features
        spec: Horizon specification
    
    Returns:
        DataFrame in AutoGluon format: [item_id, timestamp, target, ...]
    """
    # Ensure we have ZL close price as target
    if 'zl_close' not in df.columns:
        raise ValueError("zl_close not found in features")
    
    # Create TimeSeriesDataFrame format
    ts_df = df.copy()
    ts_df['item_id'] = SYMBOL
    ts_df['timestamp'] = pd.to_datetime(ts_df['as_of_date'])
    ts_df['target'] = ts_df['zl_close']
    
    # Drop unnecessary columns
    ts_df = ts_df.drop(['as_of_date', 'zl_close'], axis=1)
    
    # Sort by timestamp
    ts_df = ts_df.sort_values('timestamp').reset_index(drop=True)
    
    return ts_df

# =============================================================================
# 8-FOLD CROSS-VALIDATION
# =============================================================================

def generate_cv_folds(df: pd.DataFrame, n_folds: int = N_FOLDS) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Generate 8-fold time series cross-validation splits.
    
    Args:
        df: DataFrame with time-sorted data
        n_folds: Number of folds
    
    Returns:
        List of (train_idx, val_idx) tuples
    """
    tscv = TimeSeriesSplit(n_splits=n_folds)
    folds = list(tscv.split(df))
    
    logger.info(f"Generated {n_folds} CV folds")
    for i, (train_idx, val_idx) in enumerate(folds):
        logger.info(f"  Fold {i+1}: Train {len(train_idx)}, Val {len(val_idx)}")
    
    return folds

# =============================================================================
# OOF PREDICTION GENERATION
# =============================================================================

def get_oof_predictions(
    df: pd.DataFrame,
    spec: HorizonSpec,
    folds: List[Tuple[np.ndarray, np.ndarray]],
    model_path: Path,
) -> pd.DataFrame:
    """
    Generate out-of-fold predictions for all folds.
    
    This is the core OOF generation function that:
    1. Trains a model on each fold's training set
    2. Predicts on the fold's validation set
    3. Stores predictions with fold_id
    
    Args:
        df: Full dataset
        spec: Horizon specification  
        folds: List of (train_idx, val_idx) tuples
        model_path: Path to save models
    
    Returns:
        DataFrame with columns: [fold_id, as_of_date, pred_p10, pred_p50, pred_p90, pred_p95, actual]
    """
    from autogluon.timeseries import TimeSeriesDataFrame, TimeSeriesPredictor
    
    oof_results = []
    
    for fold_id, (train_idx, val_idx) in enumerate(folds):
        logger.info(f"")
        logger.info(f"Processing Fold {fold_id + 1}/{len(folds)}")
        logger.info(f"  Train: {len(train_idx)} rows, Val: {len(val_idx)} rows")
        
        # Split data
        train_df = df.iloc[train_idx].copy()
        val_df = df.iloc[val_idx].copy()
        
        # Convert to TimeSeriesDataFrame
        train_ts = TimeSeriesDataFrame.from_data_frame(
            train_df,
            id_column="item_id",
            timestamp_column="timestamp",
        )
        
        val_ts = TimeSeriesDataFrame.from_data_frame(
            val_df,
            id_column="item_id",
            timestamp_column="timestamp",
        )
        
        # Create predictor for this fold
        fold_model_path = model_path / f"fold_{fold_id}"
        fold_model_path.mkdir(parents=True, exist_ok=True)
        
        predictor = TimeSeriesPredictor(
            prediction_length=spec.prediction_length,
            target="target",
            freq="B",  # Business day
            eval_metric="WQL",
            quantile_levels=QUANTILE_LEVELS,
            path=str(fold_model_path),
            verbosity=2,
        )
        
        # Train on fold
        logger.info(f"  Training fold {fold_id + 1}...")
        predictor.fit(
            train_data=train_ts,
            hyperparameters="light",  # Fast training for CV
            enable_ensemble=True,
            num_val_windows=2,
            time_limit=300,  # 5 minutes per fold
        )
        
        # Predict on validation set
        logger.info(f"  Predicting on validation set...")
        predictions = predictor.predict(val_ts, quantile_levels=QUANTILE_LEVELS)
        
        # Extract predictions and actuals
        for idx in range(len(val_df)):
            val_date = val_df.iloc[idx]['timestamp']
            actual = val_df.iloc[idx]['target']
            
            # Get predictions for this date
            pred_row = predictions.loc[predictions.index.get_level_values('timestamp') == val_date]
            
            if len(pred_row) > 0:
                pred_values = pred_row.iloc[0].values  # [p10, p50, p90, p95]
                
                oof_results.append({
                    'fold_id': fold_id,
                    'as_of_date': val_date.date(),
                    'pred_p10': pred_values[0] if len(pred_values) > 0 else None,
                    'pred_p50': pred_values[1] if len(pred_values) > 1 else None,
                    'pred_p90': pred_values[2] if len(pred_values) > 2 else None,
                    'pred_p95': pred_values[3] if len(pred_values) > 3 else None,
                    'actual': actual,
                })
        
        logger.info(f"  Fold {fold_id + 1} complete: {len(oof_results)} predictions")
    
    oof_df = pd.DataFrame(oof_results)
    logger.info(f"")
    logger.info(f"OOF Generation Complete: {len(oof_df)} total predictions across {len(folds)} folds")
    
    return oof_df

# =============================================================================
# SAVE TO DATABASE
# =============================================================================

def save_oof_predictions(conn, oof_df: pd.DataFrame, spec: HorizonSpec, model_version: str):
    """Save OOF predictions to model.oof_predictions table."""
    logger.info(f"Saving {len(oof_df)} OOF predictions to database...")
    
    insert_query = """
    INSERT INTO model.oof_predictions (
        specialist, horizon, as_of_date, symbol,
        pred_p10, pred_p50, pred_p90, actual, fold_id, model_version
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (specialist, horizon, as_of_date, fold_id) 
    DO UPDATE SET
        pred_p10 = EXCLUDED.pred_p10,
        pred_p50 = EXCLUDED.pred_p50,
        pred_p90 = EXCLUDED.pred_p90,
        actual = EXCLUDED.actual,
        model_version = EXCLUDED.model_version;
    """
    
    data = [
        (
            'core',  # specialist
            spec.prediction_length,  # horizon
            row['as_of_date'],
            SYMBOL,
            row['pred_p10'],
            row['pred_p50'],
            row['pred_p90'],
            row['actual'],
            row['fold_id'],
            model_version,
        )
        for _, row in oof_df.iterrows()
    ]
    
    cursor = conn.cursor()
    try:
        execute_batch(cursor, insert_query, data, page_size=1000)
        conn.commit()
        logger.info(f"✓ Saved {len(data)} OOF predictions")
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to save OOF predictions: {e}")
        raise
    finally:
        cursor.close()

def calculate_metrics(oof_df: pd.DataFrame) -> Dict[str, float]:
    """Calculate MASE, RMSE, MAE from OOF predictions."""
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    
    actual = oof_df['actual'].values
    pred = oof_df['pred_p50'].values  # Use median prediction
    
    # Remove NaN values
    mask = ~(np.isnan(actual) | np.isnan(pred))
    actual = actual[mask]
    pred = pred[mask]
    
    if len(actual) == 0:
        return {'mase': None, 'rmse': None, 'mae': None, 'mape': None}
    
    mae = mean_absolute_error(actual, pred)
    rmse = np.sqrt(mean_squared_error(actual, pred))
    mape = np.mean(np.abs((actual - pred) / actual)) * 100
    
    # MASE calculation (scale by naive forecast MAE)
    naive_errors = np.abs(np.diff(actual))
    naive_mae = np.mean(naive_errors) if len(naive_errors) > 0 else 1.0
    mase = mae / naive_mae if naive_mae > 0 else mae
    
    return {
        'mase': float(mase),
        'rmse': float(rmse),
        'mae': float(mae),
        'mape': float(mape),
    }

def save_to_model_registry(conn, spec: HorizonSpec, metrics: Dict[str, float], model_version: str, artifact_path: str):
    """Save model metadata to model.model_registry."""
    logger.info(f"Saving model metadata to registry...")
    
    insert_query = """
    INSERT INTO model.model_registry (
        model_id, model_name, model_type, horizon, version,
        trained_at, status, is_champion,
        mase, rmse, mae, mape,
        best_model, models_trained,
        artifact_path
    ) VALUES (
        %s, %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s,
        %s
    )
    ON CONFLICT (model_id, version)
    DO UPDATE SET
        trained_at = EXCLUDED.trained_at,
        status = EXCLUDED.status,
        mase = EXCLUDED.mase,
        rmse = EXCLUDED.rmse,
        mae = EXCLUDED.mae,
        mape = EXCLUDED.mape;
    """
    
    model_id = f"zinc-fusion-core-{spec.name}-oof"
    
    cursor = conn.cursor()
    try:
        cursor.execute(insert_query, (
            model_id,
            f"Core {spec.name.upper()} with OOF",
            'core',
            spec.prediction_length,
            1,  # version
            datetime.now(),
            'trained',
            False,  # is_champion
            metrics.get('mase'),
            metrics.get('rmse'),
            metrics.get('mae'),
            metrics.get('mape'),
            'TimeSeriesPredictor',
            N_FOLDS,
            artifact_path,
        ))
        conn.commit()
        logger.info(f"✓ Saved model metadata: {model_id}")
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to save model metadata: {e}")
        raise
    finally:
        cursor.close()

# =============================================================================
# MAIN TRAINING FUNCTION
# =============================================================================

def train_horizon_with_oof(
    conn,
    spec: HorizonSpec,
    dry_run: bool = False,
) -> Optional[pd.DataFrame]:
    """
    Train a single horizon with 8-fold CV and OOF prediction generation.
    
    Args:
        conn: Database connection
        spec: Horizon specification
        dry_run: If True, skip actual training
    
    Returns:
        OOF predictions DataFrame
    """
    logger.info("=" * 80)
    logger.info(f"TRAINING {spec.name.upper()} HORIZON WITH OOF GENERATION")
    logger.info("=" * 80)
    logger.info(f"  Mode: {spec.mode}")
    logger.info(f"  Prediction Length: {spec.prediction_length}")
    logger.info(f"  Folds: {N_FOLDS}")
    logger.info(f"  Quantiles: {QUANTILE_LEVELS}")
    
    # 1. Load data
    logger.info("Loading core features...")
    df = load_core_features(conn)
    logger.info(f"  Loaded {len(df)} rows")
    
    # 2. Prepare for time series
    logger.info("Preparing time series data...")
    ts_df = prepare_timeseries_data(df, spec)
    logger.info(f"  Prepared {len(ts_df)} rows")
    
    if dry_run:
        logger.info("[DRY RUN] Skipping training")
        return None
    
    # 3. Generate CV folds
    logger.info("Generating CV folds...")
    folds = generate_cv_folds(ts_df, N_FOLDS)
    
    # 4. Generate OOF predictions
    model_path = MODEL_ROOT / f"{spec.name}_oof"
    logger.info(f"Model path: {model_path}")
    
    oof_df = get_oof_predictions(
        df=ts_df,
        spec=spec,
        folds=folds,
        model_path=model_path,
    )
    
    # 5. Calculate metrics
    logger.info("Calculating metrics...")
    metrics = calculate_metrics(oof_df)
    logger.info(f"  MASE: {metrics['mase']:.4f}")
    logger.info(f"  RMSE: {metrics['rmse']:.4f}")
    logger.info(f"  MAE: {metrics['mae']:.4f}")
    logger.info(f"  MAPE: {metrics['mape']:.2f}%")
    
    # 6. Save to database
    model_version = f"v15-oof-{datetime.now():%Y%m%d}"
    save_oof_predictions(conn, oof_df, spec, model_version)
    save_to_model_registry(conn, spec, metrics, model_version, str(model_path))
    
    logger.info("=" * 80)
    logger.info(f"✓ {spec.name.upper()} TRAINING COMPLETE")
    logger.info("=" * 80)
    
    return oof_df

# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Train V15 Core Models with OOF Generation"
    )
    parser.add_argument(
        "--horizon",
        type=str,
        default="5",
        help="Horizon to train: 5, 21, 63, 126, or 'all'"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare data but skip training"
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("ZINC-FUSION-V15: CORE MODEL TRAINING WITH OOF")
    logger.info("=" * 80)

    # Parse horizons
    if args.horizon.lower() == "all":
        horizons = HORIZONS
    else:
        horizons = [int(args.horizon)]

    logger.info(f"Horizons: {horizons}")
    logger.info(f"Folds: {N_FOLDS}")
    logger.info(f"Dry run: {args.dry_run}")

    # Connect to database
    conn = get_postgres_connection()

    try:
        # Train each horizon
        for h in horizons:
            spec = HORIZON_SPECS[h]
            oof_df = train_horizon_with_oof(
                conn=conn,
                spec=spec,
                dry_run=args.dry_run,
            )
            
            if oof_df is not None:
                logger.info(f"Generated {len(oof_df)} OOF predictions for {spec.name}")

        logger.info("=" * 80)
        logger.info("✓ ALL TRAINING COMPLETE")
        logger.info("=" * 80)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
