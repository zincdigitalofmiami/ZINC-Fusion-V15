#!/usr/bin/env python3
"""
ZINC-FUSION-V15: CORE Direction Model Training
===============================================

CORE GETS EVERYTHING.

Data Sources:
1. raw.market_futures_1d - ALL 83 futures symbols
2. raw.fred_observations_1d - ALL 118 FRED series
3. raw.fx_spot_1d - ALL 30 FX pairs
4. raw.cftc_cot_1w - COT positioning data
5. raw.weather_noaa_1d - Weather data
6. Elite indicators computed fresh from ZL OHLCV

Target: Direction classification (UP/DOWN) with probability output.
"""

from __future__ import annotations

import os
import sys
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any

import numpy as np
import pandas as pd
import psycopg2

# Project imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fusion.features.elite_indicators import EliteIndicators

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

HORIZONS = [5, 21, 63, 126]
MODEL_ROOT = PROJECT_ROOT / "models" / "core_direction"


# =============================================================================
# DATABASE
# =============================================================================

def get_connection():
    """Get PostgreSQL connection from .env file."""
    env_path = PROJECT_ROOT / ".env"
    url = None

    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.startswith("DATABASE_URL=") or line.startswith("POSTGRES_URL="):
                    url = line.split("=", 1)[1].strip().strip('"')
                    break

    if not url:
        url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")

    if not url:
        raise ValueError("DATABASE_URL not found in .env or environment")

    return psycopg2.connect(url)


# =============================================================================
# DATA LOADING - LOAD EVERYTHING
# =============================================================================

def load_all_futures(conn) -> pd.DataFrame:
    """Load ALL futures from raw.market_futures_1d."""
    logger.info("Loading ALL futures from raw.market_futures_1d...")

    query = """
        SELECT as_of_date, symbol, open, high, low, close, volume
        FROM "raw"."market_futures_1d"
        ORDER BY as_of_date, symbol
    """

    df = pd.read_sql(query, conn)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])

    # Pivot to wide format - each symbol gets its own columns
    pivoted = df.pivot_table(
        index="as_of_date",
        columns="symbol",
        values=["open", "high", "low", "close", "volume"],
        aggfunc="last"
    )

    # Flatten column names: (close, ZL) -> zl_close
    pivoted.columns = [f"{sym.lower()}_{col}" for col, sym in pivoted.columns]

    logger.info(f"   Loaded {len(pivoted):,} rows, {len(pivoted.columns)} columns")
    logger.info(f"   Date range: {pivoted.index.min().date()} to {pivoted.index.max().date()}")

    return pivoted


def load_all_fred(conn) -> pd.DataFrame:
    """Load ALL FRED series from raw.fred_observations_1d."""
    logger.info("Loading ALL FRED from raw.fred_observations_1d...")

    query = """
        SELECT series_id, as_of_date, value
        FROM "raw"."fred_observations_1d"
        ORDER BY as_of_date
    """

    df = pd.read_sql(query, conn)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.normalize()

    # Pivot to wide format
    pivoted = df.pivot_table(
        index="as_of_date",
        columns="series_id",
        values="value",
        aggfunc="last"
    )

    # Lowercase column names
    pivoted.columns = [c.lower() for c in pivoted.columns]

    # Forward fill gaps
    pivoted = pivoted.ffill()

    logger.info(f"   Loaded {len(pivoted):,} rows, {len(pivoted.columns)} FRED series")

    return pivoted


def load_all_fx_spot(conn) -> pd.DataFrame:
    """Load ALL FX spot from raw.fx_spot_1d."""
    logger.info("Loading ALL FX spot from raw.fx_spot_1d...")

    query = """
        SELECT as_of_date, pair, close
        FROM "raw"."fx_spot_1d"
        ORDER BY as_of_date
    """

    df = pd.read_sql(query, conn)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.normalize()

    # Pivot to wide format
    pivoted = df.pivot_table(
        index="as_of_date",
        columns="pair",
        values="close",
        aggfunc="last"
    )

    # Prefix with fx_
    pivoted.columns = [f"fx_{c.lower()}" for c in pivoted.columns]

    # Forward fill gaps
    pivoted = pivoted.ffill()

    logger.info(f"   Loaded {len(pivoted):,} rows, {len(pivoted.columns)} FX pairs")

    return pivoted


def load_cftc_cot(conn) -> pd.DataFrame:
    """Load CFTC COT data from raw.cftc_cot_1w."""
    logger.info("Loading CFTC COT from raw.cftc_cot_1w...")

    # Check what columns exist
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'raw' AND table_name = 'cftc_cot_1w'
    """)
    columns = [r[0] for r in cur.fetchall()]
    logger.info(f"   COT columns: {columns}")

    query = """
        SELECT * FROM "raw"."cftc_cot_1w"
        ORDER BY as_of_date
    """

    df = pd.read_sql(query, conn)

    if "as_of_date" in df.columns:
        df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.normalize()
        df = df.set_index("as_of_date")

    # Prefix columns with cot_
    df.columns = [f"cot_{c}" if not c.startswith("cot_") else c for c in df.columns]

    # Forward fill weekly data to daily
    df = df.ffill()

    logger.info(f"   Loaded {len(df):,} rows, {len(df.columns)} COT columns")

    return df


def load_weather(conn) -> pd.DataFrame:
    """Load weather data from raw.weather_noaa_1d."""
    logger.info("Loading weather from raw.weather_noaa_1d...")

    # Check what columns exist
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'raw' AND table_name = 'weather_noaa_1d'
    """)
    columns = [r[0] for r in cur.fetchall()]
    logger.info(f"   Weather columns: {columns}")

    query = """
        SELECT * FROM "raw"."weather_noaa_1d"
        ORDER BY as_of_date
    """

    df = pd.read_sql(query, conn)

    if "as_of_date" in df.columns:
        df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.normalize()
        df = df.set_index("as_of_date")

    # Prefix columns with wx_
    df.columns = [f"wx_{c}" if not c.startswith("wx_") else c for c in df.columns]

    logger.info(f"   Loaded {len(df):,} rows, {len(df.columns)} weather columns")

    return df


def compute_elite_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute elite indicators for ZL."""
    logger.info("Computing elite indicators for ZL...")

    # Extract ZL OHLCV
    zl_cols = ["zl_open", "zl_high", "zl_low", "zl_close", "zl_volume"]
    if not all(c in df.columns for c in zl_cols):
        logger.warning("   Missing ZL OHLCV columns, skipping elite indicators")
        return df

    zl_df = df[zl_cols].copy()

    elite = EliteIndicators(zl_df, symbol="zl")
    zl_with_elite = elite.compute_all()

    # Add elite columns back to main df
    elite_cols = [c for c in zl_with_elite.columns if c not in zl_cols]
    for col in elite_cols:
        df[col] = zl_with_elite[col]

    logger.info(f"   Added {len(elite_cols)} elite indicator columns")

    return df


def compute_returns_and_spreads(df: pd.DataFrame) -> pd.DataFrame:
    """Compute returns, spreads, and ratios for key symbols."""
    logger.info("Computing returns and spreads...")

    # Key symbols to compute features for
    key_symbols = ["zl", "zm", "zs", "cl", "ho", "gc", "es", "zc", "zw"]

    added = 0
    for sym in key_symbols:
        close_col = f"{sym}_close"
        if close_col not in df.columns:
            continue

        close = df[close_col]

        # Returns
        for period in [1, 5, 10, 21, 63]:
            df[f"{sym}_ret_{period}d"] = close.pct_change(period) * 100
            added += 1

        # Volatility
        for period in [5, 10, 21, 63]:
            df[f"{sym}_vol_{period}d"] = close.pct_change().rolling(period).std() * np.sqrt(252) * 100
            added += 1

    # Key spreads
    if "zl_close" in df.columns and "zm_close" in df.columns:
        df["zl_zm_ratio"] = df["zl_close"] / df["zm_close"]
        added += 1

    if "zl_close" in df.columns and "zs_close" in df.columns:
        df["zl_zs_ratio"] = df["zl_close"] / df["zs_close"]
        added += 1

    if "cl_close" in df.columns and "ho_close" in df.columns:
        df["cl_ho_spread"] = df["ho_close"] - df["cl_close"]
        added += 1

    # Board crush margin: ZM + ZL - ZS (approximate)
    if all(c in df.columns for c in ["zl_close", "zm_close", "zs_close"]):
        df["board_crush"] = df["zm_close"] * 0.022 + df["zl_close"] * 0.11 - df["zs_close"]
        added += 1

    logger.info(f"   Added {added} return/spread features")

    return df


# =============================================================================
# DATA PREPARATION
# =============================================================================

def prepare_core_dataset(conn, horizon: int, min_date: str = "2000-01-01") -> Tuple[pd.DataFrame, pd.Series, List[str]]:
    """
    Prepare Core dataset with EVERYTHING.
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"PREPARING CORE DATA FOR {horizon}d HORIZON")
    logger.info(f"{'='*60}")

    # Load ALL data sources
    futures_df = load_all_futures(conn)
    fred_df = load_all_fred(conn)
    fx_df = load_all_fx_spot(conn)

    # Start with futures as base (has all trading dates)
    df = futures_df.copy()
    logger.info(f"Base futures: {len(df):,} rows")

    # Join FRED (left join, forward fill)
    df = df.join(fred_df, how="left")
    for col in fred_df.columns:
        if col in df.columns:
            df[col] = df[col].ffill()
    logger.info(f"After FRED join: {len(df.columns)} columns")

    # Join FX (left join, forward fill)
    df = df.join(fx_df, how="left")
    for col in fx_df.columns:
        if col in df.columns:
            df[col] = df[col].ffill()
    logger.info(f"After FX join: {len(df.columns)} columns")

    # Load and join COT
    try:
        cot_df = load_cftc_cot(conn)
        df = df.join(cot_df, how="left")
        for col in cot_df.columns:
            if col in df.columns:
                df[col] = df[col].ffill()
        logger.info(f"After COT join: {len(df.columns)} columns")
    except Exception as e:
        logger.warning(f"   COT load failed: {e}")

    # Load and join weather
    try:
        wx_df = load_weather(conn)
        df = df.join(wx_df, how="left")
        for col in wx_df.columns:
            if col in df.columns:
                df[col] = df[col].ffill()
        logger.info(f"After weather join: {len(df.columns)} columns")
    except Exception as e:
        logger.warning(f"   Weather load failed: {e}")

    # Compute elite indicators
    df = compute_elite_indicators(df)
    logger.info(f"After elite indicators: {len(df.columns)} columns")

    # Compute returns and spreads
    df = compute_returns_and_spreads(df)
    logger.info(f"After returns/spreads: {len(df.columns)} columns")

    # Create target
    logger.info("Creating direction target...")
    if "zl_close" not in df.columns:
        raise ValueError("zl_close not found - cannot create target")

    future_return = (df["zl_close"].shift(-horizon) - df["zl_close"]) / df["zl_close"] * 100
    df["future_return"] = future_return
    df["direction"] = (future_return > 0).astype(int)

    # Filter date range
    df = df[df.index >= min_date]
    logger.info(f"After date filter ({min_date}): {len(df):,} rows")

    # Select feature columns
    exclude_cols = ["direction", "future_return"]
    exclude_patterns = ["_open", "_high", "_low", "_volume"]  # Keep only close and derived

    feature_cols = []
    for c in df.columns:
        if c in exclude_cols:
            continue
        if any(c.endswith(p) for p in exclude_patterns):
            continue
        if df[c].dtype not in ['float64', 'int64', 'float32', 'int32']:
            continue
        feature_cols.append(c)

    logger.info(f"Feature columns before coverage filter: {len(feature_cols)}")

    # Filter by coverage (>50%)
    good_features = []
    for col in feature_cols:
        coverage = df[col].notna().mean()
        if coverage >= 0.5:
            good_features.append(col)

    dropped = len(feature_cols) - len(good_features)
    if dropped > 0:
        logger.info(f"   Dropped {dropped} low-coverage features")

    feature_cols = good_features

    # Drop rows with NaN in target
    subset = feature_cols + ["direction"]
    df_clean = df[subset].dropna(subset=["direction"])

    # For features, fill remaining NaN with 0 (or could use median)
    df_clean[feature_cols] = df_clean[feature_cols].fillna(0)

    logger.info(f"\n--- DATASET SUMMARY ---")
    logger.info(f"Date range: {df_clean.index.min().date()} to {df_clean.index.max().date()}")
    logger.info(f"Samples: {len(df_clean):,}")
    logger.info(f"Features: {len(feature_cols)}")

    # Class balance
    up_pct = df_clean["direction"].mean() * 100
    logger.info(f"Class balance: {up_pct:.1f}% UP / {100-up_pct:.1f}% DOWN")

    X = df_clean[feature_cols]
    y = df_clean["direction"]

    return X, y, feature_cols


# =============================================================================
# TRAINING
# =============================================================================

def train_core_model(
    X: pd.DataFrame,
    y: pd.Series,
    horizon: int,
    time_limit: int = 600,
) -> Dict[str, Any]:
    """Train Core direction classifier."""
    from autogluon.tabular import TabularPredictor

    logger.info(f"\n{'='*50}")
    logger.info(f"TRAINING CORE MODEL - {horizon}d")
    logger.info(f"{'='*50}")

    train_data = X.copy()
    train_data["direction"] = y.values

    # Time-based split (80/20)
    split_idx = int(len(train_data) * 0.8)
    train_df = train_data.iloc[:split_idx]
    val_df = train_data.iloc[split_idx:]

    logger.info(f"Train: {len(train_df):,} ({train_df.index.min().date()} to {train_df.index.max().date()})")
    logger.info(f"Val:   {len(val_df):,} ({val_df.index.min().date()} to {val_df.index.max().date()})")

    model_path = MODEL_ROOT / f"core_{horizon}d"
    model_path.mkdir(parents=True, exist_ok=True)

    predictor = TabularPredictor(
        label="direction",
        path=str(model_path),
        eval_metric="accuracy",
        problem_type="binary",
        verbosity=2,
    )

    predictor.fit(
        train_data=train_df,
        time_limit=time_limit,
        presets="best_quality",
        num_bag_folds=5,
        num_stack_levels=1,
        excluded_model_types=["KNN", "NN_TORCH"],
    )

    val_metrics = predictor.evaluate(val_df)
    val_acc = val_metrics["accuracy"]

    logger.info(f"\n*** VALIDATION ACCURACY: {val_acc:.4f} ({val_acc*100:.2f}%) ***")

    importance = predictor.feature_importance(val_df, num_shuffle_sets=3)
    logger.info(f"\nTop 20 features:")
    for feat, imp in importance.head(20).iterrows():
        logger.info(f"   {feat}: {imp['importance']:.4f}")

    lb = predictor.leaderboard(val_df)
    logger.info(f"\nModel leaderboard:")
    logger.info(lb[["model", "score_val"]].head(10).to_string())

    return {
        "predictor": predictor,
        "accuracy": val_acc,
        "leaderboard": lb,
        "feature_importance": importance,
    }


# =============================================================================
# WALK-FORWARD BACKTEST
# =============================================================================

def walk_forward_backtest(
    conn,
    horizon: int,
    train_years: int = 5,
    test_months: int = 3,
    time_limit: int = 180,
) -> pd.DataFrame:
    """Walk-forward backtest for realistic accuracy."""
    from autogluon.tabular import TabularPredictor

    logger.info(f"\n{'='*60}")
    logger.info(f"WALK-FORWARD BACKTEST - {horizon}d")
    logger.info(f"Train: {train_years} years, Test: {test_months} months")
    logger.info(f"{'='*60}")

    X, y, _ = prepare_core_dataset(conn, horizon, min_date="2000-01-01")

    data = X.copy()
    data["direction"] = y.values

    results = []

    start_date = data.index.min() + pd.DateOffset(years=train_years)
    end_date = data.index.max() - pd.DateOffset(days=horizon)

    current = start_date
    fold = 0

    while current < end_date:
        fold += 1

        train_start = current - pd.DateOffset(years=train_years)
        train_end = current
        test_start = current
        test_end = min(current + pd.DateOffset(months=test_months), end_date)

        train_df = data[(data.index >= train_start) & (data.index < train_end)]
        test_df = data[(data.index >= test_start) & (data.index < test_end)]

        if len(train_df) < 500 or len(test_df) < 20:
            current = test_end
            continue

        logger.info(f"\nFold {fold}: Train {len(train_df)}, Test {len(test_df)}")

        model_path = MODEL_ROOT / "backtest" / f"fold_{fold}_{horizon}d"

        predictor = TabularPredictor(
            label="direction",
            path=str(model_path),
            eval_metric="accuracy",
            problem_type="binary",
            verbosity=0,
        )

        predictor.fit(
            train_data=train_df,
            time_limit=time_limit,
            presets="medium_quality",
            num_bag_folds=3,
        )

        preds = predictor.predict(test_df)
        accuracy = (preds == test_df["direction"]).mean()

        results.append({
            "fold": fold,
            "train_start": train_start,
            "train_end": train_end,
            "test_start": test_start,
            "test_end": test_end,
            "train_size": len(train_df),
            "test_size": len(test_df),
            "accuracy": accuracy,
        })

        logger.info(f"   Accuracy: {accuracy:.4f} ({accuracy*100:.2f}%)")

        current = test_end

    results_df = pd.DataFrame(results)

    mean_acc = results_df["accuracy"].mean()
    std_acc = results_df["accuracy"].std()

    logger.info(f"\n{'='*60}")
    logger.info(f"BACKTEST RESULTS")
    logger.info(f"{'='*60}")
    logger.info(f"Folds: {len(results_df)}")
    logger.info(f"Mean: {mean_acc:.4f} ({mean_acc*100:.2f}%)")
    logger.info(f"Std:  {std_acc:.4f}")
    logger.info(f"Range: {results_df['accuracy'].min():.4f} - {results_df['accuracy'].max():.4f}")

    if mean_acc >= 0.80:
        logger.info(f"\n>>> TARGET MET: {mean_acc*100:.2f}% >= 80%")
    else:
        logger.info(f"\n>>> BELOW TARGET: {mean_acc*100:.2f}% < 80%")

    return results_df


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Train Core Direction Model")
    parser.add_argument("--horizon", type=str, default="63")
    parser.add_argument("--time-limit", type=int, default=600)
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Just prepare data, don't train")

    args = parser.parse_args()

    if args.horizon.lower() == "all":
        horizons = HORIZONS
    else:
        horizons = [int(args.horizon)]

    time_limit = 180 if args.quick else args.time_limit
    bt_time = 120 if args.quick else 180

    logger.info("=" * 60)
    logger.info("ZINC-FUSION-V15: CORE DIRECTION MODEL")
    logger.info("=" * 60)
    logger.info("CORE GETS EVERYTHING")
    logger.info("=" * 60)

    conn = get_connection()

    try:
        for h in horizons:
            if args.dry_run:
                X, y, features = prepare_core_dataset(conn, h)
                logger.info(f"\n[DRY RUN] Data prepared for {h}d horizon")
                logger.info(f"          {len(X):,} samples, {len(features)} features")
                logger.info(f"          Ready for training")
            elif args.backtest:
                results = walk_forward_backtest(conn, h, time_limit=bt_time)
                results_path = MODEL_ROOT / f"backtest_{h}d.csv"
                results_path.parent.mkdir(parents=True, exist_ok=True)
                results.to_csv(results_path, index=False)
            else:
                X, y, features = prepare_core_dataset(conn, h)
                result = train_core_model(X, y, h, time_limit=time_limit)

                logger.info(f"\n{'='*60}")
                logger.info(f"COMPLETE - {h}d: {result['accuracy']*100:.2f}%")
                logger.info(f"{'='*60}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
