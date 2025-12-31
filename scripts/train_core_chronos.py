#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Core Model Training with AutoGluon 1.5 TimeSeriesPredictor

Trains the Core baseline model using AutoGluon 1.5 TimeSeriesPredictor.
Uses FULL multi-symbol hourly data from Prisma Postgres.

Modes:
    quick - Chronos-2 only, 10 min (development)
    full  - Full AutoML ensemble, 4 hours (production)

Usage:
    python scripts/train_core_chronos.py --horizon 21 --mode quick --dry-run
    python scripts/train_core_chronos.py --horizon 21 --mode quick
    python scripts/train_core_chronos.py --horizon 21 --mode full
    python scripts/train_core_chronos.py --horizon all --mode full
"""

import os

os.environ["TF_USE_LEGACY_KERAS"] = "1"
os.environ["KERAS_BACKEND"] = "tensorflow"

import sys
import logging
import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
load_dotenv(".env.vercel")

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
MODEL_PATH = PROJECT_ROOT / "models" / "core_chronos2"

# Horizons
HORIZONS = [5, 21, 63, 126]

# Quantile levels
QUANTILE_LEVELS = [0.1, 0.5, 0.9]

# Minimum data requirements
MIN_ROWS = 1_000_000
MIN_SYMBOLS = 50

# Core covariates from FRED
CORE_COVARIATES = [
    "VIXCLS",  # VIX volatility index
    "DTWEXBGS",  # Trade-weighted dollar index
    "DCOILWTICO",  # WTI crude oil
]


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def preflight_check(conn) -> bool:
    """Verify data requirements before training."""
    logger.info("Running pre-flight data check...")

    with conn.cursor() as cur:
        # Check hourly data volume
        cur.execute(
            """
            SELECT COUNT(*) as rows, COUNT(DISTINCT symbol) as symbols
            FROM "raw"."market_futures_1h"
        """
        )
        row = cur.fetchone()
        total_rows, total_symbols = row[0], row[1]

        logger.info(f"  Hourly data: {total_rows:,} rows, {total_symbols} symbols")

        if total_rows < MIN_ROWS:
            logger.error(
                f"  ❌ Insufficient rows: {total_rows:,} < {MIN_ROWS:,} required"
            )
            return False

        if total_symbols < MIN_SYMBOLS:
            logger.error(
                f"  ❌ Insufficient symbols: {total_symbols} < {MIN_SYMBOLS} required"
            )
            return False

        # Check FRED data
        cur.execute(
            """
            SELECT COUNT(*) as rows
            FROM "raw"."fred_economic_wide_1d"
        """
        )
        fred_rows = cur.fetchone()[0]

        logger.info(f"  FRED data: {fred_rows:,} rows")

        if fred_rows < 1000:
            logger.error(f"  ❌ Insufficient FRED data: {fred_rows:,} rows")
            return False

    logger.info("  ✅ Pre-flight check passed")
    return True


def load_training_data(conn) -> pd.DataFrame:
    """Load ALL training data from Prisma Postgres - EVERY TABLE."""
    from autogluon.timeseries import TimeSeriesDataFrame

    logger.info("=" * 60)
    logger.info("LOADING ALL DATA FROM PRISMA")
    logger.info("=" * 60)

    # =========================================================================
    # 1. BASE: Hourly market futures (4.97M rows)
    # =========================================================================
    logger.info("1. Loading hourly market futures...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                symbol,
                ts_event,
                close as target,
                open,
                high,
                low,
                volume,
                open_interest
            FROM "raw"."market_futures_1h"
            ORDER BY symbol, ts_event
        """)
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=columns)
    df["ts_event"] = pd.to_datetime(df["ts_event"])
    df["trade_date"] = df["ts_event"].dt.date
    logger.info(f"   Loaded {len(df):,} rows, {df['symbol'].nunique()} symbols")

    # =========================================================================
    # 2. FRED Economic Data (91 columns, 27K rows)
    # =========================================================================
    logger.info("2. Loading FRED economic data...")
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM "raw"."fred_economic_wide_1d"')
        fred_cols = [desc[0] for desc in cur.description]
        fred_rows = cur.fetchall()
    fred_df = pd.DataFrame(fred_rows, columns=fred_cols)
    fred_df["trade_date"] = pd.to_datetime(fred_df["trade_date"]).dt.date
    fred_features = [c for c in fred_cols if c != "trade_date"]
    logger.info(f"   Loaded {len(fred_df):,} rows, {len(fred_features)} features")

    # =========================================================================
    # 3. WEATHER Data (215K rows) - aggregate by date for soy regions
    # =========================================================================
    logger.info("3. Loading NOAA weather data...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                as_of_date,
                AVG(tavg_c) as weather_tavg_global,
                AVG(tmin_c) as weather_tmin_global,
                AVG(tmax_c) as weather_tmax_global,
                AVG(prcp_mm) as weather_prcp_global,
                AVG(CASE WHEN country = 'Brazil' THEN tavg_c END) as weather_tavg_brazil,
                AVG(CASE WHEN country = 'Brazil' THEN prcp_mm END) as weather_prcp_brazil,
                AVG(CASE WHEN country = 'United States' THEN tavg_c END) as weather_tavg_us,
                AVG(CASE WHEN country = 'United States' THEN prcp_mm END) as weather_prcp_us,
                AVG(CASE WHEN country = 'Argentina' THEN tavg_c END) as weather_tavg_argentina,
                AVG(CASE WHEN country = 'Argentina' THEN prcp_mm END) as weather_prcp_argentina
            FROM "raw"."weather_noaa"
            GROUP BY as_of_date
            ORDER BY as_of_date
        """)
        weather_cols = [desc[0] for desc in cur.description]
        weather_rows = cur.fetchall()
    weather_df = pd.DataFrame(weather_rows, columns=weather_cols)
    weather_df["trade_date"] = pd.to_datetime(weather_df["as_of_date"]).dt.date
    weather_df = weather_df.drop(columns=["as_of_date"])
    logger.info(f"   Loaded {len(weather_df):,} daily aggregates, 10 weather features")

    # =========================================================================
    # 4. SPOT FX Data (140K rows) - pivot to wide format
    # =========================================================================
    logger.info("4. Loading spot FX data...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT pair, as_of_date, rate
            FROM "raw"."raw_fx_spot"
            ORDER BY as_of_date
        """)
        fx_rows = cur.fetchall()
    fx_df = pd.DataFrame(fx_rows, columns=["pair", "as_of_date", "rate"])
    fx_df["trade_date"] = pd.to_datetime(fx_df["as_of_date"]).dt.date
    # Pivot: each FX pair becomes a column
    fx_wide = fx_df.pivot_table(index="trade_date", columns="pair", values="rate", aggfunc="last")
    fx_wide.columns = [f"fx_{c}" for c in fx_wide.columns]
    fx_wide = fx_wide.reset_index()
    logger.info(f"   Loaded {len(fx_wide):,} dates, {len(fx_wide.columns)-1} FX pairs")

    # =========================================================================
    # 5. CFTC COT Positioning (6K rows) - ZL positioning signals
    # =========================================================================
    logger.info("5. Loading CFTC COT positioning...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                report_date,
                symbol as cot_symbol,
                open_interest as cot_oi,
                managed_money_net as cot_mm_net,
                managed_money_net_pct_oi as cot_mm_pct,
                prod_merc_net as cot_prod_net,
                prod_merc_net_pct_oi as cot_prod_pct
            FROM "raw"."cftc_cot"
            WHERE symbol IN ('ZL', 'ZS', 'ZM', 'CL')
            ORDER BY report_date, symbol
        """)
        cot_rows = cur.fetchall()
    cot_df = pd.DataFrame(cot_rows, columns=["report_date", "cot_symbol", "cot_oi", "cot_mm_net", "cot_mm_pct", "cot_prod_net", "cot_prod_pct"])
    cot_df["trade_date"] = pd.to_datetime(cot_df["report_date"]).dt.date
    # Pivot by symbol
    cot_features = []
    for sym in ["ZL", "ZS", "ZM", "CL"]:
        sym_df = cot_df[cot_df["cot_symbol"] == sym].copy()
        for col in ["cot_oi", "cot_mm_net", "cot_mm_pct", "cot_prod_net", "cot_prod_pct"]:
            sym_df = sym_df.rename(columns={col: f"{col}_{sym}"})
            cot_features.append(f"{col}_{sym}")
        if sym == "ZL":
            cot_wide = sym_df[["trade_date"] + [c for c in sym_df.columns if c.startswith("cot_") and c.endswith(f"_{sym}")]]
        else:
            sym_cols = ["trade_date"] + [c for c in sym_df.columns if c.startswith("cot_") and c.endswith(f"_{sym}")]
            cot_wide = cot_wide.merge(sym_df[sym_cols], on="trade_date", how="outer")
    logger.info(f"   Loaded {len(cot_wide):,} dates, {len(cot_features)} COT features")

    # =========================================================================
    # 6. USDA Export Sales (6K rows)
    # =========================================================================
    logger.info("6. Loading USDA export sales...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                report_date,
                SUM(CASE WHEN commodity = 'Soybeans' THEN net_sales_mt END) as usda_soy_net_sales,
                SUM(CASE WHEN commodity = 'Soybeans' THEN exports_mt END) as usda_soy_exports,
                SUM(CASE WHEN commodity = 'Soybean Oil' THEN net_sales_mt END) as usda_zl_net_sales,
                SUM(CASE WHEN commodity = 'Soybean Oil' THEN exports_mt END) as usda_zl_exports,
                SUM(CASE WHEN commodity = 'Soybean Meal' THEN net_sales_mt END) as usda_zm_net_sales
            FROM "raw"."usda_export_sales"
            GROUP BY report_date
            ORDER BY report_date
        """)
        usda_rows = cur.fetchall()
    usda_df = pd.DataFrame(usda_rows, columns=["report_date", "usda_soy_net_sales", "usda_soy_exports", "usda_zl_net_sales", "usda_zl_exports", "usda_zm_net_sales"])
    usda_df["trade_date"] = pd.to_datetime(usda_df["report_date"]).dt.date
    usda_df = usda_df.drop(columns=["report_date"])
    logger.info(f"   Loaded {len(usda_df):,} dates, 5 USDA export features")

    # =========================================================================
    # 7. USDA WASDE (4K rows) - fundamentals
    # =========================================================================
    logger.info("7. Loading USDA WASDE fundamentals...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                report_date,
                SUM(CASE WHEN commodity = 'Soybeans' AND metric = 'production' THEN value END) as wasde_soy_production,
                SUM(CASE WHEN commodity = 'Soybeans' AND metric = 'exports' THEN value END) as wasde_soy_exports,
                SUM(CASE WHEN commodity = 'Soybeans' AND metric = 'ending_stocks' THEN value END) as wasde_soy_stocks,
                SUM(CASE WHEN commodity = 'Soybean Oil' AND metric = 'production' THEN value END) as wasde_zl_production,
                SUM(CASE WHEN commodity = 'Soybean Oil' AND metric = 'exports' THEN value END) as wasde_zl_exports
            FROM "raw"."usda_wasde"
            GROUP BY report_date
            ORDER BY report_date
        """)
        wasde_rows = cur.fetchall()
    wasde_df = pd.DataFrame(wasde_rows, columns=["report_date", "wasde_soy_production", "wasde_soy_exports", "wasde_soy_stocks", "wasde_zl_production", "wasde_zl_exports"])
    wasde_df["trade_date"] = pd.to_datetime(wasde_df["report_date"]).dt.date
    wasde_df = wasde_df.drop(columns=["report_date"])
    logger.info(f"   Loaded {len(wasde_df):,} dates, 5 WASDE features")

    # =========================================================================
    # 8. EPA RIN Prices (208 rows) - biofuel mandate pricing
    # =========================================================================
    logger.info("8. Loading EPA RIN prices...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT as_of_date, rin_type, price
            FROM "raw"."raw_epa_rin_prices"
            ORDER BY as_of_date
        """)
        rin_rows = cur.fetchall()
    rin_df = pd.DataFrame(rin_rows, columns=["as_of_date", "rin_type", "price"])
    rin_df["trade_date"] = pd.to_datetime(rin_df["as_of_date"]).dt.date
    # Pivot RIN types to columns
    rin_wide = rin_df.pivot_table(index="trade_date", columns="rin_type", values="price", aggfunc="last")
    rin_wide.columns = [f"rin_{c}" for c in rin_wide.columns]
    rin_wide = rin_wide.reset_index()
    logger.info(f"   Loaded {len(rin_wide):,} dates, {len(rin_wide.columns)-1} RIN prices")

    # =========================================================================
    # 9. NEWS Sentiment (288 rows) - aggregated daily sentiment
    # =========================================================================
    logger.info("9. Loading news sentiment...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                as_of_date,
                AVG(sentiment_score) as news_sentiment_avg,
                COUNT(*) as news_article_count,
                SUM(CASE WHEN zl_sentiment = 'bullish' THEN 1 ELSE 0 END) as news_bullish_count,
                SUM(CASE WHEN zl_sentiment = 'bearish' THEN 1 ELSE 0 END) as news_bearish_count,
                SUM(CASE WHEN is_trump_related THEN 1 ELSE 0 END) as news_trump_count
            FROM "raw"."news_articles"
            GROUP BY as_of_date
            ORDER BY as_of_date
        """)
        news_rows = cur.fetchall()
    news_df = pd.DataFrame(news_rows, columns=["as_of_date", "news_sentiment_avg", "news_article_count", "news_bullish_count", "news_bearish_count", "news_trump_count"])
    news_df["trade_date"] = pd.to_datetime(news_df["as_of_date"]).dt.date
    news_df = news_df.drop(columns=["as_of_date"])
    logger.info(f"   Loaded {len(news_df):,} dates, 5 news sentiment features")

    # =========================================================================
    # JOIN ALL DATA TO BASE HOURLY DATA
    # =========================================================================
    logger.info("=" * 60)
    logger.info("JOINING ALL FEATURES TO HOURLY BASE")
    logger.info("=" * 60)

    # Start with base hourly data
    logger.info(f"  Base: {len(df):,} hourly rows")

    # Join FRED
    df = df.merge(fred_df, on="trade_date", how="left")
    logger.info(f"  + FRED: {len(fred_features)} features")

    # Join Weather
    df = df.merge(weather_df, on="trade_date", how="left")
    logger.info(f"  + Weather: 10 features")

    # Join Spot FX
    df = df.merge(fx_wide, on="trade_date", how="left")
    logger.info(f"  + Spot FX: {len(fx_wide.columns)-1} features")

    # Join CFTC COT
    df = df.merge(cot_wide, on="trade_date", how="left")
    logger.info(f"  + CFTC COT: {len(cot_features)} features")

    # Join USDA Exports
    df = df.merge(usda_df, on="trade_date", how="left")
    logger.info(f"  + USDA Exports: 5 features")

    # Join USDA WASDE
    df = df.merge(wasde_df, on="trade_date", how="left")
    logger.info(f"  + USDA WASDE: 5 features")

    # Join EPA RINs
    df = df.merge(rin_wide, on="trade_date", how="left")
    logger.info(f"  + EPA RINs: {len(rin_wide.columns)-1} features")

    # Join News
    df = df.merge(news_df, on="trade_date", how="left")
    logger.info(f"  + News: 5 features")

    # Drop trade_date helper column
    df = df.drop(columns=["trade_date"])

    # Sort and forward-fill within each symbol
    df = df.sort_values(["symbol", "ts_event"])
    logger.info("  Forward-filling all features per symbol...")
    df = df.set_index("symbol").groupby(level=0, group_keys=False).apply(lambda g: g.ffill()).reset_index()

    # Drop rows with no target
    df = df.dropna(subset=["target"])

    # Count total features
    feature_cols = [c for c in df.columns if c not in ["symbol", "ts_event", "target"]]

    logger.info("=" * 60)
    logger.info(f"FINAL DATASET: {len(df):,} rows, {df['symbol'].nunique()} symbols, {len(feature_cols)} features")
    logger.info("=" * 60)

    # Convert to TimeSeriesDataFrame
    ts_df = TimeSeriesDataFrame.from_data_frame(
        df, id_column="symbol", timestamp_column="ts_event"
    )

    return ts_df


def train_chronos2_model(ts_data, horizon: int, model_path: Path, mode: str = "quick"):
    """Train with AutoGluon 1.5 TimeSeriesPredictor."""
    from autogluon.timeseries import TimeSeriesPredictor

    # Time limits by mode
    time_limits = {
        "ultrafast": 2400,   # 40 minutes (needed for large dataset + Chronos-2)
        "quick": 3600,       # 1 hour
        "full": 14400,       # 4 hours
    }
    time_limit = time_limits.get(mode, 3600)
    is_full = mode == "full"

    logger.info(f"Training AutoGluon TimeSeriesPredictor for {horizon}d horizon")
    logger.info(f"  Mode: {mode}")
    logger.info(f"  Dataset: {len(ts_data):,} rows, {ts_data.num_items} series")
    logger.info(f"  Time limit: {time_limit // 60} minutes")
    logger.info(f"  Preset: best_quality")

    if is_full:
        logger.info(f"  Models: Full AutoML ensemble (DeepAR, PatchTST, Chronos-2, etc.)")
    else:
        logger.info(f"  Models: Chronos-2 only ({mode} mode)")

    model_path.mkdir(parents=True, exist_ok=True)

    # Configure TimeSeriesPredictor
    predictor = TimeSeriesPredictor(
        prediction_length=horizon,
        path=str(model_path),
        target="target",
        eval_metric="MASE",
        quantile_levels=QUANTILE_LEVELS,
        freq="H",  # Hourly data
        verbosity=2,
    )

    # Training config based on mode
    fit_kwargs = {
        "train_data": ts_data,
        "time_limit": time_limit,
        "presets": "best_quality",
    }

    # Ultrafast mode: minimize validation overhead
    if mode == "ultrafast":
        fit_kwargs["num_val_windows"] = 1  # Single validation window for speed
        fit_kwargs["hyperparameters"] = {
            "Chronos2": {"model_path": "autogluon/chronos-2"},
        }
    # Quick mode: Chronos-2 only (using correct AutoGluon 1.5 key)
    elif not is_full:
        fit_kwargs["hyperparameters"] = {
            "Chronos2": {"model_path": "autogluon/chronos-2"},
        }

    # Train
    predictor.fit(**fit_kwargs)

    # Log results
    leaderboard = predictor.leaderboard()
    logger.info(f"\n{'='*60}")
    logger.info("MODEL LEADERBOARD")
    logger.info(f"{'='*60}")
    logger.info(f"\n{leaderboard}")

    if len(leaderboard) == 0:
        raise ValueError("No models completed training. Increase time_limit or reduce dataset size.")

    logger.info(f"\nBest model: {predictor.model_best}")

    return predictor


def save_predictions(conn, predictor, ts_data, horizon: int, model_version: str):
    """Generate and save predictions to model.oof_predictions."""
    logger.info("Generating predictions")

    predictions = predictor.predict(ts_data)
    logger.info(
        f"  Generated {len(predictions):,} predictions across {predictions.num_items} series"
    )

    # Clear existing core predictions for this horizon
    with conn.cursor() as cur:
        cur.execute(
            'DELETE FROM "model"."oof_predictions" WHERE specialist = %s AND horizon = %s',
            ("core", horizon),
        )
    conn.commit()
    logger.info(f"  Cleared existing core predictions for {horizon}d")

    # Extract quantile columns from AutoGluon output
    p10_col = "0.1" if "0.1" in predictions.columns else "mean"
    p50_col = "0.5" if "0.5" in predictions.columns else "mean"
    p90_col = "0.9" if "0.9" in predictions.columns else "mean"

    created_at = datetime.now()
    batch = []

    for idx, row in predictions.iterrows():
        # idx is (item_id, timestamp) tuple from TimeSeriesDataFrame
        symbol = idx[0] if isinstance(idx, tuple) else "ZL"
        timestamp = idx[1] if isinstance(idx, tuple) else idx

        batch.append(
            (
                "core",  # specialist
                horizon,  # horizon
                timestamp,  # as_of_date
                symbol,  # symbol
                float(row[p10_col]),  # pred_p10
                float(row[p50_col]),  # pred_p50
                float(row[p90_col]),  # pred_p90
                None,  # actual (filled during evaluation)
                0,  # fold_id (0 for non-CV predictions)
                created_at,  # created_at
            )
        )

    # Columns match model.oof_predictions schema - use UPSERT to handle duplicates
    insert_query = """
        INSERT INTO "model"."oof_predictions"
            (specialist, horizon, as_of_date, symbol, pred_p10, pred_p50, pred_p90, actual, fold_id, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (specialist, horizon, as_of_date, fold_id)
        DO UPDATE SET
            symbol = EXCLUDED.symbol,
            pred_p10 = EXCLUDED.pred_p10,
            pred_p50 = EXCLUDED.pred_p50,
            pred_p90 = EXCLUDED.pred_p90,
            created_at = EXCLUDED.created_at
    """

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    logger.info(f"  Saved {len(batch):,} predictions to model.oof_predictions")
    return len(batch)


def train_core_chronos2(horizon: int, mode: str = "quick", dry_run: bool = False):
    """Train core model with Chronos-2 + AutoGluon 1.5."""
    logger.info("=" * 60)
    logger.info(f"TRAINING CORE MODEL (CHRONOS-2 + AUTOGLUON 1.5) @ {horizon}d")
    logger.info(f"Mode: {mode}")
    logger.info("=" * 60)

    conn = get_postgres_connection()

    try:
        # Preflight check
        if not preflight_check(conn):
            logger.error("Preflight check failed - insufficient data for training")
            sys.exit(1)

        # Load FULL training data from Prisma
        ts_data = load_training_data(conn)

        model_version = f"chronos2_ag15_{mode}_h{horizon}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        model_path = MODEL_PATH / f"horizon_{horizon}d"

        if dry_run:
            logger.info(f"\n[DRY RUN] Would train model in {mode} mode")
            logger.info(
                f"[DRY RUN] Data: {len(ts_data):,} rows, {ts_data.num_items} series"
            )
            logger.info(f"[DRY RUN] Output: {model_path}")
            return

        # Train model
        predictor = train_chronos2_model(ts_data, horizon, model_path, mode=mode)

        # Save predictions
        saved = save_predictions(conn, predictor, ts_data, horizon, model_version)

        logger.info(
            f"\n✅ Completed {mode} training @ {horizon}d ({saved:,} predictions)"
        )

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Train core model with Chronos-2 + AutoGluon 1.5"
    )
    parser.add_argument(
        "--horizon",
        type=str,
        required=True,
        help="Horizon in days (5, 21, 63, 126) or 'all'",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["ultrafast", "quick", "full"],
        default="quick",
        help="Training mode: 'ultrafast' (10min), 'quick' (1hr), or 'full' (4hrs AutoML)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without training"
    )

    args = parser.parse_args()

    if args.horizon.lower() == "all":
        horizons = HORIZONS
    else:
        horizon = int(args.horizon)
        if horizon not in HORIZONS:
            logger.error(f"Invalid horizon: {horizon}. Must be one of {HORIZONS}")
            sys.exit(1)
        horizons = [horizon]

    for horizon in horizons:
        try:
            train_core_chronos2(horizon, mode=args.mode, dry_run=args.dry_run)
        except Exception as e:
            logger.error(f"Failed to train core @ {horizon}d: {e}")
            raise

    logger.info("\n" + "=" * 60)
    logger.info(f"CORE {args.mode.upper()} TRAINING COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
