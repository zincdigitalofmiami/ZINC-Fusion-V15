#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Core Model Training (V15 Quant Standard)

Implements the Cascading Horizon Strategy:
- Tactical (5d/21d): Chronos-Bolt (univariate) + Tabular ensemble
- Strategic (63d/126d): Chronos-2 (LoRA fine-tuned) + Statistical ensemble

Architecture:
- MPS-first hardware abstraction for Apple Silicon
- WQL metric with asymmetric quantiles [0.1, 0.5, 0.9, 0.95]
- Rolling 7-year window for tactical, full history for strategic
- Covariate split: known (calendar) vs past (technicals, fundamentals)

Usage:
    python scripts/train_core_v15.py --horizon 5
    python scripts/train_core_v15.py --horizon all
    python scripts/train_core_v15.py --horizon 21 --dry-run
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
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Project imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from src.fusion.validation.all_data_policy import (
    enforce_all_data_policy,
    log_all_data_summary,
)

# =============================================================================
# LOGGING SETUP
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()
load_dotenv(".env.vercel")

# =============================================================================
# V15 CONFIGURATION (QUANT STANDARD)
# =============================================================================

# Horizons
HORIZONS = [5, 21, 63, 126]

# Quantiles - P95 is procurement ceiling (tail risk)
QUANTILE_LEVELS = [0.1, 0.5, 0.9, 0.95]

# Model paths
MODEL_ROOT = PROJECT_ROOT / "models" / "core_v15"

# Data windows
TACTICAL_ROLLING_YEARS = 7  # 5d/21d use last 7 years
STRATEGIC_START_DATE = "2000-01-01"  # 63d/126d use full history

# Known covariates (deterministic future values)
KNOWN_COVARIATES = [
    "day_of_week",
    "month",
    "quarter",
    "is_month_end",
    "is_quarter_end",
    "days_to_expiry",
]

# Tactical past covariates (technicals - for tabular models)
TACTICAL_PAST_COVARIATES = [
    # Elite technicals
    "rsi_14", "rsi_7", "macd", "macd_signal", "macd_hist",
    "bb_upper", "bb_lower", "bb_pct", "atr_14",
    "adx_14", "cci_20", "willr_14", "mfi_14",
    "obv", "vwap", "keltner_upper", "keltner_lower",
    # Volatility proxies
    "intraday_range", "garman_klass_vol", "parkinson_vol",
    "close_to_close_vol", "overnight_gap",
]

# Strategic past covariates (fundamentals + technicals)
STRATEGIC_PAST_COVARIATES = [
    # Fundamentals
    "crush_spread", "bopo_spread", "rin_d4_price",
    "wasde_ending_stocks", "wasde_production",
    "export_sales_net", "cot_managed_money_net",
    # Weather
    "precip_anom", "temp_anom",
    # Macro
    "dxy_index", "wti_crude", "vix",
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
# HYPERPARAMETER FACTORIES
# =============================================================================

def get_tactical_hyperparameters(device: str) -> Dict:
    """
    Hyperparameters for tactical horizons (5d/21d).

    Model portfolio:
    - Chronos-Bolt: Univariate speed anchor (no covariates)
    - DirectTabular: Non-linear covariate reasoning
    - RecursiveTabular: Autoregressive features
    - ETS, Theta, SeasonalNaive: Statistical diversity

    WeightedEnsemble is automatic via enable_ensemble=True.
    """
    return {
        # Chronos-Bolt (univariate anchor - no covariate support)
        "Chronos": {
            "model_path": "autogluon/chronos-bolt-small",
            "context_length": 64,
            "device": device,
        },
        # Tabular models handle covariates
        "DirectTabular": {},
        "RecursiveTabular": {},
        # Statistical suite
        "ETS": {},
        "Theta": {},
        "SeasonalNaive": {},
    }


def get_strategic_hyperparameters(device: str) -> Dict:
    """
    Hyperparameters for strategic horizons (63d/126d).

    Model portfolio:
    - Chronos-2: LoRA fine-tuned, 8192 context, native covariate support
    - DirectTabular: Robust non-linear backup
    - ETS, Theta, SeasonalNaive: Statistical anchors

    No RecursiveTabular - prevents error propagation at long range.
    WeightedEnsemble is automatic via enable_ensemble=True.
    """
    return {
        # Chronos-2 with LoRA fine-tuning
        "Chronos2": {
            # model_path defaults to autogluon/chronos-2
            "fine_tune": True,
            "fine_tune_mode": "lora",
            "fine_tune_lr": 1e-4,
            "fine_tune_steps": 1500,
            "fine_tune_batch_size": 32,
            "fine_tune_context_length": 8192,  # CRITICAL: must match inference
            "context_length": 8192,
            "device": device,
        },
        # Tabular backup
        "DirectTabular": {},
        # Statistical suite
        "ETS": {},
        "Theta": {},
        "SeasonalNaive": {},
    }


# =============================================================================
# DATA LOADING
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
        cur.execute("""
            SELECT
                as_of_date as timestamp,
                open, high, low, close, volume
            FROM "raw"."market_futures_1d"
            WHERE symbol = 'ZL'
              AND as_of_date >= %s
            ORDER BY as_of_date
        """, (start_date,))
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=columns)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["item_id"] = "ZL"

    # Target is close price
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

    # Days to expiry (simplified - assume monthly expiry on 15th)
    days_in_month = ts.dt.daysinmonth
    day = ts.dt.day
    df["days_to_expiry"] = (15 - day).clip(lower=0)

    return df


def add_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicator features (past covariates for tactical)."""
    df = df.copy()

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"].fillna(0)

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    gain7 = delta.where(delta > 0, 0).rolling(7).mean()
    loss7 = (-delta.where(delta < 0, 0)).rolling(7).mean()
    rs7 = gain7 / loss7.replace(0, np.nan)
    df["rsi_7"] = 100 - (100 / (1 + rs7))

    # MACD
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # Bollinger Bands
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df["bb_upper"] = sma20 + 2 * std20
    df["bb_lower"] = sma20 - 2 * std20
    df["bb_pct"] = (close - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

    # ATR
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean()

    # Volatility proxies
    df["intraday_range"] = (high - low) / close
    df["garman_klass_vol"] = np.sqrt(
        0.5 * np.log(high / low) ** 2 -
        (2 * np.log(2) - 1) * np.log(close / close.shift()) ** 2
    ).rolling(20).mean()
    df["parkinson_vol"] = np.sqrt(
        np.log(high / low) ** 2 / (4 * np.log(2))
    ).rolling(20).mean()
    df["close_to_close_vol"] = close.pct_change().rolling(20).std() * np.sqrt(252)
    df["overnight_gap"] = (df["open"] / close.shift() - 1).abs()

    # Additional indicators (simplified)
    df["adx_14"] = 50.0  # Placeholder - would need full DI+/DI- calc
    df["cci_20"] = (close - sma20) / (0.015 * close.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean()))
    df["willr_14"] = -100 * (high.rolling(14).max() - close) / (high.rolling(14).max() - low.rolling(14).min())
    df["mfi_14"] = 50.0  # Placeholder - needs typical price * volume
    df["obv"] = (np.sign(close.diff()) * volume).cumsum()
    df["vwap"] = (close * volume).cumsum() / volume.cumsum()
    df["keltner_upper"] = close.ewm(span=20).mean() + 2 * df["atr_14"]
    df["keltner_lower"] = close.ewm(span=20).mean() - 2 * df["atr_14"]

    return df


def add_fundamental_features(conn, df: pd.DataFrame) -> pd.DataFrame:
    """Add fundamental features (past covariates for strategic)."""
    df = df.copy()

    # Load FRED data
    with conn.cursor() as cur:
        cur.execute("""
            SELECT series_id, as_of_date, value
            FROM "raw"."fred_observations_1d"
            WHERE series_id IN ('DCOILWTICO', 'VIXCLS', 'DTWEXBGS')
            ORDER BY as_of_date
        """)
        fred_rows = cur.fetchall()

    if fred_rows:
        fred_df = pd.DataFrame(fred_rows, columns=["series_id", "timestamp", "value"])
        fred_df["timestamp"] = pd.to_datetime(fred_df["timestamp"])
        fred_pivot = fred_df.pivot(index="timestamp", columns="series_id", values="value")
        fred_pivot = fred_pivot.rename(columns={
            "DCOILWTICO": "wti_crude",
            "VIXCLS": "vix",
            "DTWEXBGS": "dxy_index",
        })
        df = df.merge(fred_pivot, left_on="timestamp", right_index=True, how="left")

    # Load COT data
    with conn.cursor() as cur:
        cur.execute("""
            SELECT report_date, managed_money_net
            FROM "raw"."cftc_cot_1w"
            WHERE symbol = 'ZL'
            ORDER BY report_date
        """)
        cot_rows = cur.fetchall()

    if cot_rows:
        cot_df = pd.DataFrame(cot_rows, columns=["timestamp", "cot_managed_money_net"])
        cot_df["timestamp"] = pd.to_datetime(cot_df["timestamp"])
        df = pd.merge_asof(
            df.sort_values("timestamp"),
            cot_df.sort_values("timestamp"),
            on="timestamp",
            direction="backward"
        )

    # Calculate crush spread (ZS - ZL - ZM proxy)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT as_of_date, symbol, close
            FROM "raw"."market_futures_1d"
            WHERE symbol IN ('ZS', 'ZM')
            ORDER BY as_of_date
        """)
        soy_rows = cur.fetchall()

    if soy_rows:
        soy_df = pd.DataFrame(soy_rows, columns=["timestamp", "symbol", "close"])
        soy_df["timestamp"] = pd.to_datetime(soy_df["timestamp"])
        soy_pivot = soy_df.pivot(index="timestamp", columns="symbol", values="close")
        soy_pivot["crush_spread"] = soy_pivot.get("ZS", 0) * 0.022 - soy_pivot.get("ZM", 0) * 0.011
        df = df.merge(
            soy_pivot[["crush_spread"]],
            left_on="timestamp",
            right_index=True,
            how="left"
        )

    # Fill placeholders for missing fundamentals
    for col in ["bopo_spread", "rin_d4_price", "wasde_ending_stocks",
                "wasde_production", "export_sales_net", "precip_anom", "temp_anom"]:
        if col not in df.columns:
            df[col] = np.nan

    return df


def slice_rolling_window(df: pd.DataFrame, years: int) -> pd.DataFrame:
    """Slice data to rolling window of last N years."""
    end_date = df["timestamp"].max()
    start_date = end_date - pd.DateOffset(years=years)
    return df[df["timestamp"] >= start_date].copy()


def prepare_training_data(
    conn,
    spec: HorizonSpec,
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Prepare training data for a specific horizon.

    Returns:
        df: DataFrame ready for TimeSeriesDataFrame conversion
        known_covariates: List of known covariate column names
    """
    from autogluon.timeseries import TimeSeriesDataFrame

    logger.info("=" * 60)
    logger.info(f"PREPARING DATA FOR {spec.name} ({spec.mode.upper()})")
    logger.info("=" * 60)

    # Determine start date
    if spec.is_tactical:
        # Load full history then slice to rolling window
        start_date = "1990-01-01"
    else:
        start_date = STRATEGIC_START_DATE

    # Load base data
    df = load_base_data(conn, start_date)

    # Add calendar features (known covariates)
    df = add_calendar_features(df)

    # Add technical features
    df = add_technical_features(df)

    # Add fundamental features (for strategic)
    if spec.is_strategic:
        df = add_fundamental_features(conn, df)

    # Apply rolling window for tactical
    if spec.is_tactical:
        original_len = len(df)
        df = slice_rolling_window(df, TACTICAL_ROLLING_YEARS)
        logger.info(f"   Rolling window: {original_len:,} -> {len(df):,} rows ({TACTICAL_ROLLING_YEARS}y)")

    # Forward-fill and back-fill NaNs
    df = df.ffill().bfill()

    # Report
    logger.info(f"   Final dataset: {len(df):,} rows")
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
    """Train a single horizon model."""
    from autogluon.timeseries import TimeSeriesDataFrame, TimeSeriesPredictor

    logger.info("=" * 60)
    logger.info(f"TRAINING {spec.name} HORIZON ({spec.mode.upper()} ENGINE)")
    logger.info("=" * 60)

    # Prepare data
    df, known_cov_names = prepare_training_data(conn, spec)

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

    # Get hyperparameters
    if spec.is_tactical:
        hyperparameters = get_tactical_hyperparameters(device)
        num_val_windows = 3
    else:
        hyperparameters = get_strategic_hyperparameters(device)
        num_val_windows = 4

    # Model path
    model_path = MODEL_ROOT / f"horizon_{spec.name}"
    model_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"   Model path: {model_path}")
    logger.info(f"   Prediction length: {spec.prediction_length}")
    logger.info(f"   Metric: WQL")
    logger.info(f"   Quantiles: {QUANTILE_LEVELS}")
    logger.info(f"   Validation windows: {num_val_windows}")
    logger.info(f"   Device: {device}")

    # Log hyperparameters
    for model_name, params in hyperparameters.items():
        logger.info(f"   {model_name}: {params}")

    # Create predictor
    # freq="B" = business day (excludes weekends, handles market holidays)
    predictor = TimeSeriesPredictor(
        prediction_length=spec.prediction_length,
        target="target",
        freq="B",  # Business day frequency for futures data
        known_covariates_names=known_cov_names,
        eval_metric="WQL",
        quantile_levels=QUANTILE_LEVELS,
        path=str(model_path),
    )

    # Train
    logger.info("   Starting training...")
    start_time = datetime.now()

    predictor.fit(
        train_data=ts_df,
        hyperparameters=hyperparameters,
        enable_ensemble=True,
        num_val_windows=num_val_windows,
        time_limit=time_limit,
    )

    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(f"   Training complete in {elapsed:.1f}s")

    # Log leaderboard
    logger.info("   Leaderboard:")
    lb = predictor.leaderboard()
    logger.info(f"\n{lb.to_string()}")

    return predictor


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Train V15 Core Models (Quant Standard)"
    )
    parser.add_argument(
        "--horizon",
        type=str,
        default="all",
        help="Horizon to train: 5, 21, 63, 126, or 'all'"
    )
    parser.add_argument(
        "--time-limit",
        type=int,
        default=None,
        help="Time limit per horizon in seconds"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare data but skip training"
    )

    args = parser.parse_args()

    # Setup logging to file
    log_file = PROJECT_ROOT / "logs" / f"train_v15_{datetime.now():%Y%m%d_%H%M%S}.log"
    log_file.parent.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(file_handler)

    logger.info("=" * 60)
    logger.info("ZINC-FUSION-V15: CORE MODEL TRAINING (QUANT STANDARD)")
    logger.info("=" * 60)

    # Detect device
    device = detect_device()

    # Parse horizons
    if args.horizon.lower() == "all":
        horizons = HORIZONS
    else:
        horizons = [int(args.horizon)]

    logger.info(f"Horizons: {horizons}")
    logger.info(f"Device: {device}")
    logger.info(f"Time limit: {args.time_limit}s per horizon" if args.time_limit else "No time limit")
    logger.info(f"Dry run: {args.dry_run}")

    # Connect to database
    conn = get_postgres_connection()

    try:
        # Preflight check
        logger.info("Running preflight checks...")
        enforce_all_data_policy(conn, horizon=horizons[0], strict=True)
        log_all_data_summary(conn, horizon=horizons[0])

        # Train each horizon
        predictors = {}
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

        logger.info("=" * 60)
        logger.info("TRAINING COMPLETE")
        logger.info("=" * 60)
        for name, pred in predictors.items():
            logger.info(f"   {name}: {pred.path}")

    finally:
        conn.close()

    return predictors


if __name__ == "__main__":
    main()
