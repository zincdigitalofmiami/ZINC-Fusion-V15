#!/usr/bin/env python3
"""
Train GA-VMD-LSTM on Real ZL Data
=================================

This script trains the GA-VMD-LSTM model on actual soybean oil (ZL) price data
from the matrix_1d table.

Based on: Nature Scientific Reports 2025 - 67.5% MAPE reduction vs standalone LSTM
"""

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import hashlib

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.fusion.forecasting.ga_vmd_lstm import GAVMDLSTMForecaster, GAVMDLSTMConfig

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()

# Configuration
HORIZONS = [63, 126]  # Strategic horizons for GA-VMD-LSTM
QUANTILES = [0.3, 0.5, 0.7]
NUM_VAL_WINDOWS = 4
STRATEGIC_START = "1980-01-01"  # Use full history for strategic models


def load_zl_prices(conn) -> pd.DataFrame:
    """Load ZL price data from database."""
    logger.info("Loading ZL price data from training.matrix_1d...")

    query = """
        SELECT
            trade_date,
            close,
            target_ret_63d,
            target_ret_126d
        FROM training.matrix_1d
        WHERE symbol = 'ZL'
          AND trade_date >= %s
          AND close IS NOT NULL
        ORDER BY trade_date
    """

    df = pd.read_sql(query, conn, params=(STRATEGIC_START,))
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.set_index('trade_date')

    logger.info(f"  Loaded {len(df):,} rows from {df.index.min()} to {df.index.max()}")
    return df


def create_validation_windows(df: pd.DataFrame, horizon: int, num_windows: int = 4) -> list:
    """
    Create expanding validation windows for OOF predictions.

    Each window:
    - Training: all data up to cutoff
    - Validation: horizon days after cutoff
    """
    total_days = len(df)

    # Reserve last horizon*num_windows days for validation
    min_train_size = int(total_days * 0.6)  # At least 60% for first training window
    val_space = horizon * num_windows

    windows = []
    for w in range(num_windows):
        # Expanding window: train on more data each time
        train_end_idx = min_train_size + (w * (total_days - min_train_size - val_space) // num_windows)
        val_start_idx = train_end_idx
        val_end_idx = min(val_start_idx + horizon, total_days)

        cutoff_date = df.index[train_end_idx - 1]

        windows.append({
            'window_id': w + 1,
            'train_end_idx': train_end_idx,
            'val_start_idx': val_start_idx,
            'val_end_idx': val_end_idx,
            'cutoff_date': cutoff_date,
        })

        logger.info(f"  Window {w+1}: train up to {cutoff_date.date()}, validate {val_end_idx - val_start_idx} days")

    return windows


def train_horizon(
    df: pd.DataFrame,
    horizon: int,
    run_hash: str,
    model_dir: Path
) -> pd.DataFrame:
    """
    Train GA-VMD-LSTM for a single horizon with OOF validation.

    Returns DataFrame with OOF predictions.
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"TRAINING HORIZON: {horizon}d")
    logger.info(f"{'='*60}")

    prices = df['close'].values
    target_col = f'target_ret_{horizon}d'

    # Create validation windows
    windows = create_validation_windows(df, horizon, NUM_VAL_WINDOWS)

    all_oof = []

    for window in windows:
        w_id = window['window_id']
        cutoff_date = window['cutoff_date']

        logger.info(f"\n--- Window {w_id}/{NUM_VAL_WINDOWS} (cutoff: {cutoff_date.date()}) ---")

        # Training data: all data up to cutoff
        train_prices = prices[:window['train_end_idx']]

        logger.info(f"  Training samples: {len(train_prices):,}")

        # Initialize and fit model
        config = GAVMDLSTMConfig(horizon=horizon)
        forecaster = GAVMDLSTMForecaster(config=config)

        try:
            # Fit on training window - skip GA optimization for speed (use paper defaults)
            forecaster.fit(
                train_prices,
                optimize_vmd=False,  # Use K=12 from paper (optimal for soybean oil)
                verbose=1
            )

            # Get predictions for validation period
            # Model predicts PRICE LEVELS, we need to convert to RETURNS
            preds = forecaster.predict(train_prices, steps=horizon)

            # Get the last known price (at cutoff) for return calculation
            last_price = train_prices[-1]

            # Convert price predictions to return predictions
            # return = (future_price / current_price) - 1
            pred_returns_mean = (preds['mean'] / last_price) - 1
            pred_returns_p30 = (preds['p30'] / last_price) - 1
            pred_returns_p50 = (preds['p50'] / last_price) - 1
            pred_returns_p70 = (preds['p70'] / last_price) - 1

            # Extract validation targets
            val_start = window['val_start_idx']
            val_end = window['val_end_idx']
            val_dates = df.index[val_start:val_end]
            val_targets = df[target_col].iloc[val_start:val_end].values

            # Create OOF records
            n_preds = min(len(pred_returns_mean), len(val_dates))

            for i in range(n_preds):
                oof_row = {
                    'trade_date': val_dates[i],
                    'horizon_days': horizon,
                    'window_id': w_id,
                    'cutoff_date': cutoff_date,
                    'core_p30': float(pred_returns_p30[i]),
                    'core_p50': float(pred_returns_p50[i]),
                    'core_p70': float(pred_returns_p70[i]),
                    'target_value': float(val_targets[i]) if i < len(val_targets) and not pd.isna(val_targets[i]) else None,
                    'trained_at': datetime.now(timezone.utc),
                    'core_run_hash': run_hash,
                }
                all_oof.append(oof_row)

            logger.info(f"  Generated {n_preds} OOF predictions")

            # Calculate validation metrics (now in return space)
            if len(val_targets) > 0 and not np.all(pd.isna(val_targets[:n_preds])):
                mask = ~pd.isna(val_targets[:n_preds])
                mae = np.mean(np.abs(pred_returns_p50[:n_preds][mask] - val_targets[:n_preds][mask]))
                logger.info(f"  Window {w_id} MAE: {mae:.6f} (in return space)")

        except Exception as e:
            logger.error(f"  Window {w_id} failed: {e}", exc_info=True)
            continue

    # Save model from last window (best trained)
    model_path = model_dir / f"ga_vmd_lstm_{horizon}d"
    model_path.mkdir(parents=True, exist_ok=True)
    forecaster.save(model_path / "model.pkl")
    logger.info(f"  Saved model to {model_path}")

    return pd.DataFrame(all_oof)


def write_oof_to_database(conn, df_oof: pd.DataFrame):
    """Write OOF predictions to training.oof_core_1d."""
    if len(df_oof) == 0:
        logger.warning("No OOF predictions to write")
        return 0

    logger.info(f"Writing {len(df_oof):,} OOF predictions to database...")

    # Enforce monotonic quantiles
    violations = (df_oof['core_p30'] > df_oof['core_p50']) | (df_oof['core_p50'] > df_oof['core_p70'])
    n_violations = violations.sum()
    if n_violations > 0:
        logger.warning(f"  Fixing {n_violations} quantile ordering violations")
        for idx in df_oof[violations].index:
            vals = sorted([df_oof.loc[idx, 'core_p30'], df_oof.loc[idx, 'core_p50'], df_oof.loc[idx, 'core_p70']])
            df_oof.loc[idx, 'core_p30'] = vals[0]
            df_oof.loc[idx, 'core_p50'] = vals[1]
            df_oof.loc[idx, 'core_p70'] = vals[2]

    # Insert with upsert
    cols = ['trade_date', 'horizon_days', 'window_id', 'cutoff_date',
            'core_p30', 'core_p50', 'core_p70', 'target_value',
            'trained_at', 'core_run_hash']

    insert_sql = f"""
        INSERT INTO training.oof_core_1d ({','.join(cols)})
        VALUES %s
        ON CONFLICT (trade_date, horizon_days, window_id)
        DO UPDATE SET
            core_p30 = EXCLUDED.core_p30,
            core_p50 = EXCLUDED.core_p50,
            core_p70 = EXCLUDED.core_p70,
            target_value = EXCLUDED.target_value,
            trained_at = EXCLUDED.trained_at,
            core_run_hash = EXCLUDED.core_run_hash
    """

    values = [tuple(row[col] for col in cols) for _, row in df_oof.iterrows()]

    with conn.cursor() as cur:
        execute_values(cur, insert_sql, values, page_size=1000)

    conn.commit()
    logger.info(f"  Wrote {len(df_oof):,} OOF predictions")
    return len(df_oof)


def main():
    logger.info("="*60)
    logger.info("GA-VMD-LSTM TRAINING ON REAL ZL DATA")
    logger.info("="*60)
    logger.info(f"Horizons: {HORIZONS}")
    logger.info(f"Quantiles: {QUANTILES}")
    logger.info(f"Validation windows: {NUM_VAL_WINDOWS}")
    logger.info("="*60)

    # Generate run hash
    run_hash = hashlib.sha256(
        f"ga_vmd_lstm_{datetime.now(timezone.utc).isoformat()}".encode()
    ).hexdigest()[:16]
    logger.info(f"Run hash: {run_hash}")

    # Model directory
    model_dir = PROJECT_ROOT / "models" / "ga_vmd_lstm"
    model_dir.mkdir(parents=True, exist_ok=True)

    try:
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        logger.info("Database connected")

        # Load data
        df = load_zl_prices(conn)

        if len(df) < 1000:
            logger.error(f"Insufficient data: {len(df)} rows (need 1000+)")
            return False

        all_oof = []
        results = {}

        for horizon in HORIZONS:
            try:
                oof_df = train_horizon(df, horizon, run_hash, model_dir)
                if len(oof_df) > 0:
                    all_oof.append(oof_df)
                    results[horizon] = True
                    logger.info(f"  {horizon}d: {len(oof_df)} OOF predictions")
                else:
                    results[horizon] = False
            except Exception as e:
                logger.error(f"  {horizon}d FAILED: {e}", exc_info=True)
                results[horizon] = False

        # Write all OOF to database
        if all_oof:
            df_all_oof = pd.concat(all_oof, ignore_index=True)
            write_oof_to_database(conn, df_all_oof)

        conn.close()

        # Summary
        logger.info("\n" + "="*60)
        logger.info("TRAINING SUMMARY")
        logger.info("="*60)
        for horizon, success in results.items():
            status = "SUCCESS" if success else "FAILED"
            logger.info(f"  {horizon}d: {status}")

        return all(results.values())

    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
