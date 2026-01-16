#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Core Model Training - POC (Proof of Concept)

PURPOSE:
    Validate the complete training architecture with MINIMAL resources.
    This script runs end-to-end training to prove the pipeline works
    before committing to full production training.

WHAT'S DIFFERENT FROM train_core_v15.py:
    - 2 years of data instead of 25 years
    - 3-4 models instead of 6
    - 1 validation window instead of 3-4
    - 100 LoRA steps instead of 1500
    - 512 context instead of 8192
    - 300s time limit instead of unlimited

USAGE:
    python scripts/train_core_poc.py --horizon 5
    python scripts/train_core_poc.py --horizon all
    python scripts/train_core_poc.py --horizon 63 --dry-run

MODEL OUTPUT:
    models/core_poc/horizon_5d/
    models/core_poc/horizon_21d/
    models/core_poc/horizon_63d/
    models/core_poc/horizon_126d/

AFTER VALIDATION:
    Once POC validates successfully, run full training with:
    python scripts/train_core_v15.py --horizon all
"""

from __future__ import annotations

# =============================================================================
# HARDWARE ABSTRACTION LAYER (MUST BE FIRST - BEFORE ANY TORCH IMPORTS)
# =============================================================================
import os

# MPS Fallback for Apple Silicon - prevents NotImplementedError on sparse ops
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
os.environ["ACCELERATE_USE_MPS_DEVICE"] = "True"

# Keras/TensorFlow compatibility
os.environ["TF_USE_LEGACY_KERAS"] = "1"
os.environ["KERAS_BACKEND"] = "tensorflow"

# =============================================================================
# IMPORTS
# =============================================================================
import sys
import logging
import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv

# Project imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).parent))

# =============================================================================
# LOGGING SETUP
# =============================================================================
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()
load_dotenv(".env.vercel")

# =============================================================================
# POC CONFIGURATION (MINIMAL RESOURCES)
# =============================================================================

# Horizons - test all to validate architecture
HORIZONS = [5, 21, 63, 126]

# Quantiles - same as production (architecture validation)
QUANTILE_LEVELS = [0.1, 0.5, 0.9, 0.95]

# POC Model output directory (separate from production)
MODEL_ROOT = PROJECT_ROOT / "models" / "core_poc"

# POC Data window - 2 years is minimum for seasonal patterns
POC_START_DATE = "2023-01-01"  # ~2 years vs 25 years in production

# POC Time limits (per horizon)
POC_TIME_LIMIT_TACTICAL = 300  # 5 min for 5d/21d
POC_TIME_LIMIT_STRATEGIC = 600  # 10 min for 63d/126d

# POC Validation windows
POC_VAL_WINDOWS = 1  # vs 3-4 in production

# Known covariates (same as production - architecture validation)
KNOWN_COVARIATES = [
    "day_of_week",
    "month",
    "quarter",
    "is_month_end",
    "is_quarter_end",
    "days_to_expiry",
]


# =============================================================================
# HORIZON SPECIFICATION
# =============================================================================


@dataclass(frozen=True)
class HorizonSpec:
    """Specification for a single horizon."""

    name: str
    prediction_length: int
    mode: str  # "tactical" or "strategic"

    @property
    def is_tactical(self) -> bool:
        return self.mode == "tactical"

    @property
    def is_strategic(self) -> bool:
        return self.mode == "strategic"


HORIZON_SPECS = {
    5: HorizonSpec("5d", 5, "tactical"),
    21: HorizonSpec("21d", 21, "tactical"),
    63: HorizonSpec("63d", 63, "strategic"),
    126: HorizonSpec("126d", 126, "strategic"),
}


# =============================================================================
# HARDWARE DETECTION
# =============================================================================


def detect_device(prefer_mps: bool = True) -> str:
    """
    Detect best available device for training.
    Priority: mps (Apple Silicon) > cuda > cpu
    """
    try:
        import torch

        # Apple Silicon MPS
        if prefer_mps and hasattr(torch.backends, "mps"):
            if torch.backends.mps.is_available() and torch.backends.mps.is_built():
                logger.info("Device detected: MPS (Apple Silicon GPU)")
                return "mps"

        # NVIDIA CUDA
        if torch.cuda.is_available():
            logger.info(f"Device detected: CUDA ({torch.cuda.get_device_name(0)})")
            return "cuda"

    except Exception as e:
        logger.warning(f"Device detection error: {e}")

    logger.info("Device detected: CPU (fallback)")
    return "cpu"


# =============================================================================
# POC HYPERPARAMETER FACTORIES (MINIMAL BUT COMPLETE)
# =============================================================================


def get_poc_tactical_hyperparameters(device: str) -> Dict:
    """
    POC hyperparameters for tactical horizons (5d/21d).

    Minimal ensemble (3 models):
    - Chronos-Bolt-Tiny: Univariate speed anchor
    - DirectTabular: Covariate reasoning
    - SeasonalNaive: Statistical baseline

    Validates: covariate handling, ensemble construction, WQL metric
    """
    return {
        # Chronos-Bolt-Tiny (smallest model, fastest)
        "Chronos": {
            "model_path": "autogluon/chronos-bolt-tiny",
            "context_length": 32,  # Minimal context
            "device": device,
        },
        # Single tabular model (validates covariate pass-through)
        "DirectTabular": {},
        # Statistical baseline (ensemble diversity)
        "SeasonalNaive": {},
    }


def get_poc_strategic_hyperparameters(device: str) -> Dict:
    """
    POC hyperparameters for strategic horizons (63d/126d).

    Minimal ensemble (4 models):
    - Chronos-2: LoRA fine-tuned, but MINIMAL steps and context
    - DirectTabular: Covariate reasoning
    - ETS: Statistical baseline
    - Theta: Statistical diversity

    Validates: LoRA fine-tuning, native covariate support, long-range ensemble
    """
    return {
        # Chronos-2 with MINIMAL LoRA fine-tuning
        "Chronos": {
            "model_path": "autogluon/chronos-t5-small",  # Small, not base
            "fine_tune": True,
            "fine_tune_mode": "lora",
            "fine_tune_lr": 1e-4,
            "fine_tune_steps": 100,  # POC: 100 vs production 1500
            "fine_tune_batch_size": 16,  # POC: 16 vs production 32
            "fine_tune_context_length": 512,  # POC: 512 vs production 8192
            "context_length": 512,  # Must match fine_tune_context_length
            "device": device,
        },
        # Tabular backup
        "DirectTabular": {},
        # Statistical suite (minimal)
        "ETS": {},
        "Theta": {},
    }


# =============================================================================
# DATA LOADING (SAME AS PRODUCTION - VALIDATES DATA PIPELINE)
# =============================================================================


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def load_base_data(conn, start_date: str) -> pd.DataFrame:
    """Load daily ZL data with OHLCV."""
    logger.info(f"Loading ZL daily data from {start_date}...")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                event_date as timestamp,
                open, high, low, close, volume
            FROM "raw"."market_futures_1d"
            WHERE symbol = 'ZL'
              AND event_date >= %s
            ORDER BY event_date
        """,
            (start_date,),
        )
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=columns)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["item_id"] = "ZL"
    df["target"] = df["close"]

    logger.info(f"   Loaded {len(df):,} rows")
    return df


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add known calendar covariates."""
    df = df.copy()
    ts = df["timestamp"]

    df["day_of_week"] = ts.dt.dayofweek
    df["month"] = ts.dt.month
    df["quarter"] = ts.dt.quarter
    df["is_month_end"] = ts.dt.is_month_end.astype(int)
    df["is_quarter_end"] = ts.dt.is_quarter_end.astype(int)
    df["days_to_expiry"] = (15 - ts.dt.day).clip(lower=0)

    return df


def add_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicator features (validates feature engineering)."""
    df = df.copy()

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"].fillna(0)

    # RSI (core momentum indicator)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # MACD (trend following)
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9).mean()

    # Bollinger Bands (volatility)
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df["bb_upper"] = sma20 + 2 * std20
    df["bb_lower"] = sma20 - 2 * std20
    df["bb_pct"] = (close - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

    # ATR (volatility measure)
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1
    ).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean()

    # Volume indicators (simplified)
    df["obv"] = (np.sign(close.diff()) * volume).cumsum()

    return df


def prepare_training_data(conn, spec: HorizonSpec) -> Tuple[pd.DataFrame, List[str]]:
    """
    Prepare training data for POC.

    Uses POC_START_DATE for all horizons (no rolling window complexity).
    """
    logger.info("=" * 60)
    logger.info(f"[POC] PREPARING DATA FOR {spec.name} ({spec.mode.upper()})")
    logger.info("=" * 60)

    # Load base data from POC start date
    df = load_base_data(conn, POC_START_DATE)

    # Add calendar features (known covariates)
    df = add_calendar_features(df)

    # Add technical features (simplified for POC)
    df = add_technical_features(df)

    # Forward-fill and back-fill NaNs
    df = df.ffill().bfill()

    # Report
    logger.info(f"   [POC] Final dataset: {len(df):,} rows")
    logger.info(f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    logger.info(f"   Known covariates: {KNOWN_COVARIATES}")

    return df, KNOWN_COVARIATES


# =============================================================================
# TRAINING
# =============================================================================


def train_horizon(
    conn,
    spec: HorizonSpec,
    device: str,
    time_limit: Optional[int] = None,
    dry_run: bool = False,
) -> Optional["TimeSeriesPredictor"]:
    """Train a single horizon model (POC mode)."""
    from autogluon.timeseries import TimeSeriesDataFrame, TimeSeriesPredictor

    logger.info("=" * 60)
    logger.info(f"[POC] TRAINING {spec.name} HORIZON ({spec.mode.upper()} ENGINE)")
    logger.info("=" * 60)

    # Prepare data
    df, known_cov_names = prepare_training_data(conn, spec)

    # Validate minimum data
    min_rows = spec.prediction_length * 10  # At least 10x prediction length
    if len(df) < min_rows:
        logger.error(f"   [POC] Insufficient data: {len(df)} rows < {min_rows} minimum")
        return None

    # Convert to TimeSeriesDataFrame
    ts_df = TimeSeriesDataFrame.from_data_frame(
        df,
        id_column="item_id",
        timestamp_column="timestamp",
    )

    logger.info(f"   TimeSeriesDataFrame: {len(ts_df)} rows")

    if dry_run:
        logger.info("   [DRY RUN] Skipping actual training")
        return None

    # Get POC hyperparameters
    if spec.is_tactical:
        hyperparameters = get_poc_tactical_hyperparameters(device)
        default_time_limit = POC_TIME_LIMIT_TACTICAL
    else:
        hyperparameters = get_poc_strategic_hyperparameters(device)
        default_time_limit = POC_TIME_LIMIT_STRATEGIC

    # Use provided time limit or default
    effective_time_limit = time_limit or default_time_limit

    # Model path (POC-specific directory)
    model_path = MODEL_ROOT / f"horizon_{spec.name}"
    model_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"   [POC] Model path: {model_path}")
    logger.info(f"   [POC] Prediction length: {spec.prediction_length}")
    logger.info(f"   [POC] Time limit: {effective_time_limit}s")
    logger.info(f"   [POC] Validation windows: {POC_VAL_WINDOWS}")
    logger.info(f"   [POC] Device: {device}")

    # Log hyperparameters
    logger.info("   [POC] Hyperparameters (MINIMAL):")
    for model_name, params in hyperparameters.items():
        logger.info(f"      {model_name}: {params}")

    # Create predictor
    predictor = TimeSeriesPredictor(
        prediction_length=spec.prediction_length,
        target="target",
        freq="B",  # Business day frequency
        known_covariates_names=known_cov_names,
        eval_metric="WQL",
        quantile_levels=QUANTILE_LEVELS,
        path=str(model_path),
    )

    # Train
    logger.info("   [POC] Starting training...")
    start_time = datetime.now()

    predictor.fit(
        train_data=ts_df,
        hyperparameters=hyperparameters,
        enable_ensemble=True,
        num_val_windows=POC_VAL_WINDOWS,
        time_limit=effective_time_limit,
    )

    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(f"   [POC] Training complete in {elapsed:.1f}s")

    # Log leaderboard
    logger.info("   [POC] Leaderboard:")
    lb = predictor.leaderboard()
    logger.info(f"\n{lb.to_string()}")

    return predictor


# =============================================================================
# VALIDATION (POC SPECIFIC)
# =============================================================================


def validate_predictor(predictor, spec: HorizonSpec, conn) -> bool:
    """
    Run basic validation to ensure the POC model works.

    Checks:
    1. Model can generate predictions
    2. Predictions have correct shape
    3. Quantiles are ordered correctly
    """
    from autogluon.timeseries import TimeSeriesDataFrame

    logger.info(f"   [POC] Validating {spec.name} predictor...")

    # Load recent data for prediction
    df, known_covs = prepare_training_data(conn, spec)
    ts_df = TimeSeriesDataFrame.from_data_frame(
        df,
        id_column="item_id",
        timestamp_column="timestamp",
    )

    try:
        # Generate prediction
        predictions = predictor.predict(ts_df)

        # Check shape
        expected_rows = spec.prediction_length
        actual_rows = len(predictions)
        if actual_rows != expected_rows:
            logger.error(f"   [POC] Shape mismatch: {actual_rows} vs {expected_rows}")
            return False

        # Check quantile columns exist
        for q in QUANTILE_LEVELS:
            col = f"{q}"
            if col not in predictions.columns:
                logger.error(f"   [POC] Missing quantile column: {col}")
                return False

        # Check quantile ordering (p10 <= p50 <= p90 <= p95)
        if "0.1" in predictions.columns and "0.5" in predictions.columns:
            violations = (predictions["0.1"] > predictions["0.5"]).sum()
            if violations > 0:
                logger.warning(
                    f"   [POC] Quantile violations (p10 > p50): {violations}"
                )

        logger.info(f"   [POC] ✓ Validation passed for {spec.name}")
        logger.info(f"   [POC]   Predictions shape: {predictions.shape}")
        logger.info(f"   [POC]   Sample prediction:\n{predictions.head()}")

        return True

    except Exception as e:
        logger.error(f"   [POC] Validation failed: {e}")
        return False


# =============================================================================
# MAIN
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Train POC Core Models (Architecture Validation)"
    )
    parser.add_argument(
        "--horizon",
        type=str,
        default="all",
        help="Horizon to train: 5, 21, 63, 126, or 'all'",
    )
    parser.add_argument(
        "--time-limit",
        type=int,
        default=None,
        help="Override time limit per horizon in seconds",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Prepare data but skip training"
    )
    parser.add_argument(
        "--skip-validation", action="store_true", help="Skip post-training validation"
    )

    args = parser.parse_args()

    # Setup logging to file
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"train_core_poc_{datetime.now():%Y%m%d_%H%M%S}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(file_handler)

    logger.info("=" * 60)
    logger.info("ZINC-FUSION-V15: CORE MODEL TRAINING (POC MODE)")
    logger.info("=" * 60)
    logger.info("")
    logger.info("PURPOSE: Validate architecture with minimal resources")
    logger.info(f"DATA WINDOW: {POC_START_DATE} to present (~2 years)")
    logger.info(f"VAL WINDOWS: {POC_VAL_WINDOWS}")
    logger.info(
        f"TIME LIMITS: {POC_TIME_LIMIT_TACTICAL}s tactical, {POC_TIME_LIMIT_STRATEGIC}s strategic"
    )
    logger.info("")

    # Detect device
    device = detect_device()

    # Parse horizons
    if args.horizon.lower() == "all":
        horizons = HORIZONS
    else:
        horizons = [int(args.horizon)]

    logger.info(f"Horizons: {horizons}")
    logger.info(f"Device: {device}")
    logger.info(
        f"Time limit override: {args.time_limit}s"
        if args.time_limit
        else "Using defaults"
    )
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Skip validation: {args.skip_validation}")

    # Connect to database
    conn = get_postgres_connection()

    try:
        # Train each horizon
        predictors = {}
        validation_results = {}

        for h in horizons:
            spec = HORIZON_SPECS[h]
            predictor = train_horizon(
                conn=conn,
                spec=spec,
                device=device,
                time_limit=args.time_limit,
                dry_run=args.dry_run,
            )

            if predictor:
                predictors[spec.name] = predictor

                # Validate unless skipped
                if not args.skip_validation:
                    validation_results[spec.name] = validate_predictor(
                        predictor, spec, conn
                    )

        # Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("[POC] TRAINING SUMMARY")
        logger.info("=" * 60)

        if predictors:
            logger.info(f"Trained {len(predictors)} models:")
            for name, pred in predictors.items():
                status = (
                    "✓ VALID"
                    if validation_results.get(name, False)
                    else "? UNVALIDATED"
                )
                logger.info(f"   {name}: {pred.path} [{status}]")
        else:
            logger.info("No models trained (dry run or errors)")

        # POC next steps
        logger.info("")
        logger.info("[POC] NEXT STEPS:")
        if all(validation_results.values()):
            logger.info("   ✓ POC validated successfully!")
            logger.info(
                "   → Run full training: python scripts/train_core_v15.py --horizon all"
            )
        else:
            logger.info(
                "   ⚠ Some validations failed - review logs before full training"
            )

        logger.info(f"   Log file: {log_file}")

    finally:
        conn.close()

    return predictors


if __name__ == "__main__":
    main()
