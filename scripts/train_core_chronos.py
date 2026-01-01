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

import time
import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ALL DATA POLICY ENFORCEMENT
# ============================================================================
# CRITICAL: This import enforces that ALL data sources are used.
# Training WILL FAIL if any data source is missing.
# DO NOT remove this import or bypass the enforcement.
# ============================================================================
from src.fusion.validation.all_data_policy import (
    enforce_all_data_policy,
    log_all_data_summary,
)

# MLflow Command Center - use relative import for scripts dir
sys.path.insert(0, str(Path(__file__).parent))
from mlflow_command_center import QuantMLCommandCenter

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
load_dotenv(".env.vercel")

# Project paths (PROJECT_ROOT already defined above for imports)
MODEL_PATH = PROJECT_ROOT / "models" / "core_chronos2"

# Horizons
HORIZONS = [5, 21, 63, 126]

# Quantile levels
QUANTILE_LEVELS = [0.1, 0.5, 0.9]

# =============================================================================
# DATA ALIGNMENT STRATEGY:
# 5d Core + Specialists (hourly): 2020+ with ALL sources
# 21d/63d/126d Core + Specialists (daily): 2000+ with ALL sources (backfilled)
# =============================================================================
# Let AutoGluon handle sparse/missing data - it's designed for this.
# FRED goes back to 1800s - include ALL of it.
# If 2000+ ALL fails, fallback is 2000+ full-coverage only.
CORE_START_DATE_5D = "2020-01-01"      # 5d uses 2020+ hourly
CORE_START_DATE_DAILY = "2000-01-01"   # 21d/63d/126d use 2000+ daily

# ALL sources included for ALL horizons:
# - Market futures (all symbols)
# - FRED economic (111 features, back to 1800s where available)
# - Weather NOAA (from 2005)
# - FX Spot (from 2000)
# - CFTC COT (from 2010)
# - EPA RIN (backfilled to 2010)
# - USDA Exports (backfilled to 2000)
# - USDA WASDE (backfilled to 2000)
# - News (backfilled to 2000)
#
# =============================================================================
# DATA FREQUENCY MAPPING:
# =============================================================================
# 1H (Hourly):  Symbol OHLCV (market hours only)
# 1D (Daily):   FX Spot, RIN, FRED daily series, Weather, News
# 1W (Weekly):  CFTC COT (Tuesday report), USDA Exports (Thursday)
# 1M (Monthly): USDA WASDE (around 12th)
#
# TRAINING STRATEGY:
# 5D MODEL:  Train on 1H base, forward-fill all 1D/1W/1M features
# 21D/63D/126D MODEL: Train on 1D base, forward-fill 1W/1M features

# Minimum data requirements
MIN_ROWS_1H = 50_000  # ~74K rows available from 2010
MIN_ROWS_1D = 5_000   # ~6.5K rows available from 2000
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


def preflight_check(conn, horizon: int = 5) -> bool:
    """Verify data requirements before training.

    CRITICAL: This function enforces the ALL DATA policy.
    Training WILL FAIL if any required data source is missing.
    """
    logger.info("Running pre-flight data check...")

    # =========================================================================
    # ALL DATA POLICY ENFORCEMENT
    # =========================================================================
    # This validates that ALL required data sources are present.
    # If ANY source is missing, training will NOT proceed.
    # =========================================================================
    try:
        enforce_all_data_policy(conn, horizon=horizon, strict=True)
        log_all_data_summary(conn, horizon=horizon)
    except ValueError as e:
        logger.error(f"ALL DATA POLICY VIOLATION: {e}")
        return False

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

        if total_rows < MIN_ROWS_1H:
            logger.error(
                f"  ❌ Insufficient rows: {total_rows:,} < {MIN_ROWS_1H:,} required"
            )
            return False

        if total_symbols < MIN_SYMBOLS:
            logger.error(
                f"  ❌ Insufficient symbols: {total_symbols} < {MIN_SYMBOLS} required"
            )
            return False

        # Check FRED data (long format, needs 100K+ rows)
        cur.execute(
            """
            SELECT COUNT(*) as rows, COUNT(DISTINCT series_id) as n_series
            FROM "raw"."fred_observations_1d"
        """
        )
        fred_rows, n_series = cur.fetchone()

        logger.info(f"  FRED data: {fred_rows:,} rows, {n_series} series")

        if fred_rows < 100_000:
            logger.error(f"  ❌ Insufficient FRED data: {fred_rows:,} rows (need 100K+)")
            return False

    logger.info("  ✅ Pre-flight check passed")
    return True


def load_training_data(conn, horizon: int = 5) -> pd.DataFrame:
    """
    Load training data from Prisma Postgres with horizon-appropriate strategy.

    Architecture:
    - 5d horizon: Uses 1h data from 2020+ with ALL sources (including sparse)
    - 21d/63d/126d horizons: Uses 1d data from 2000+ with ONLY full-coverage sources

    All symbols are pivoted WIDE so each symbol's OHLCV becomes separate columns.
    ZL is the target, other 83 symbols become covariates.
    """
    from autogluon.timeseries import TimeSeriesDataFrame

    logger.info("=" * 60)
    logger.info("LOADING TRAINING DATA FROM PRISMA")
    logger.info("=" * 60)

    # Determine frequency and date cutoff based on horizon
    use_hourly = (horizon == 5)

    if use_hourly:
        start_date = CORE_START_DATE_5D
        freq_label = "1h"
    else:
        start_date = CORE_START_DATE_DAILY
        freq_label = "1d"

    logger.info(f"Horizon: {horizon}d")
    logger.info(f"Base frequency: {freq_label}")
    logger.info(f"Start date: {start_date}")
    logger.info(f"Strategy: ALL sources, forward-fill lower frequencies to base")
    logger.info(f"  - Base: 1H symbols" if use_hourly else "  - Base: 1D symbols")
    logger.info(f"  - Forward-fill: 1D (FX, RIN, FRED, Weather, News)")
    logger.info(f"  - Forward-fill: 1W (COT, USDA Exports)")
    logger.info(f"  - Forward-fill: 1M (WASDE)")

    # =========================================================================
    # 1. BASE: Market futures - PIVOT ALL SYMBOLS WIDE
    # =========================================================================
    if use_hourly:
        logger.info(f"1. Loading hourly market futures >= {start_date}...")
        with conn.cursor() as cur:
            cur.execute("""
                SELECT symbol, ts_event, open, high, low, close, volume
                FROM "raw"."market_futures_1h"
                WHERE ts_event >= %s
                ORDER BY ts_event, symbol
            """, (start_date,))
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
        df_long = pd.DataFrame(rows, columns=columns)
        df_long["ts_event"] = pd.to_datetime(df_long["ts_event"])
        timestamp_col = "ts_event"
    else:
        logger.info(f"1. Loading daily market futures >= {start_date}...")
        with conn.cursor() as cur:
            cur.execute("""
                SELECT symbol, as_of_date as ts_event, open, high, low, close, volume
                FROM "raw"."market_futures_1d"
                WHERE as_of_date >= %s
                ORDER BY as_of_date, symbol
            """, (start_date,))
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
        df_long = pd.DataFrame(rows, columns=columns)
        df_long["ts_event"] = pd.to_datetime(df_long["ts_event"])
        timestamp_col = "ts_event"

    n_symbols = df_long["symbol"].nunique()
    logger.info(f"   Loaded {len(df_long):,} rows, {n_symbols} symbols")

    # Pivot each OHLCV column wide by symbol
    logger.info("   Pivoting symbols to wide format...")

    # Create wide dataframe starting with timestamps from ZL
    zl_data = df_long[df_long["symbol"] == "ZL"][["ts_event", "close"]].copy()
    zl_data = zl_data.rename(columns={"close": "target"})
    zl_data = zl_data.set_index("ts_event")

    # Pivot each price column
    for col in ["open", "high", "low", "close", "volume"]:
        pivot = df_long.pivot(index="ts_event", columns="symbol", values=col)
        pivot.columns = [f"{sym}_{col}" for sym in pivot.columns]
        zl_data = zl_data.join(pivot, how="left")

    df = zl_data.reset_index()
    df["trade_date"] = df["ts_event"].dt.date

    n_features = len([c for c in df.columns if c not in ["ts_event", "target", "trade_date"]])
    logger.info(f"   Wide format: {len(df):,} rows, {n_features} symbol features")

    # =========================================================================
    # 2. FRED Economic Data (long format → pivot wide)
    # =========================================================================
    logger.info("2. Loading FRED economic data (long → pivot wide)...")
    fred_long = pd.read_sql("""
        SELECT as_of_date, series_id, value
        FROM "raw"."fred_observations_1d"
        ORDER BY as_of_date, series_id
    """, conn)
    logger.info(f"   Long format: {len(fred_long):,} rows, {fred_long['series_id'].nunique()} series")

    if fred_long.empty:
        raise ValueError("FRED observations query returned 0 rows - check fred_observations_1d table")

    # Pivot to wide format (each series becomes a column)
    fred_df = (
        fred_long.pivot(index="as_of_date", columns="series_id", values="value")
        .sort_index()
        .reset_index()
    )
    fred_df["trade_date"] = pd.to_datetime(fred_df["as_of_date"]).dt.date
    fred_features = [c for c in fred_df.columns if c not in ("as_of_date", "trade_date")]

    # Warn on high sparsity
    missing_frac = fred_df[fred_features].isna().mean().mean()
    if missing_frac > 0.50:
        logger.warning(f"   ⚠️ FRED pivot has high missingness: {missing_frac:.1%}")

    logger.info(f"   Wide format: {len(fred_df):,} rows, {len(fred_features)} FRED features")

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
            FROM "raw"."weather_noaa_1d"
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
            FROM "raw"."fx_spot_1d"
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
            FROM "raw"."cftc_cot_1w"
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
            FROM "raw"."usda_export_sales_1w"
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
            FROM "raw"."usda_wasde_1m"
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
            FROM "raw"."epa_rin_prices_1d"
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
            FROM "raw"."news_articles_1d"
            GROUP BY as_of_date
            ORDER BY as_of_date
        """)
        news_rows = cur.fetchall()
    news_df = pd.DataFrame(news_rows, columns=["as_of_date", "news_sentiment_avg", "news_article_count", "news_bullish_count", "news_bearish_count", "news_trump_count"])
    news_df["trade_date"] = pd.to_datetime(news_df["as_of_date"]).dt.date
    news_df = news_df.drop(columns=["as_of_date"])
    logger.info(f"   Loaded {len(news_df):,} dates, 5 news sentiment features")

    # =========================================================================
    # JOIN ALL DATA TO BASE (hourly for 5d, daily for 21d+)
    # =========================================================================
    logger.info("=" * 60)
    logger.info(f"JOINING ALL FEATURES TO {freq_label.upper()} BASE")
    logger.info("=" * 60)

    # Start with base data
    logger.info(f"  Base: {len(df):,} {freq_label} rows")

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

    # =========================================================================
    # DATA IS ALREADY PIVOTED WIDE - no symbol column exists
    # ZL close is "target", all other symbols are covariates (e.g., BTC_close)
    # =========================================================================

    # Sort by timestamp and forward-fill all features
    df = df.sort_values("ts_event")
    logger.info("  Forward-filling all features...")
    df = df.ffill()

    # Drop rows with no target (ZL close)
    df = df.dropna(subset=["target"])

    # Count total features (all symbol covariates + FRED + weather + FX + COT + USDA + RIN + news)
    feature_cols = [c for c in df.columns if c not in ["ts_event", "target", "item_id"]]

    # Add item_id for TimeSeriesDataFrame (single item = ZL)
    df["item_id"] = "ZL"

    logger.info("=" * 60)
    logger.info(f"FINAL DATASET: {len(df):,} ZL rows with {len(feature_cols)} covariate features")
    logger.info(f"  Symbol covariates: {len([c for c in feature_cols if any(c.startswith(s+'_') for s in ['BTC','ES','CL','GC','ZS','ZW','ZC'])])}")
    logger.info(f"  FRED features: {len([c for c in feature_cols if c in fred_features])}")
    logger.info(f"  Other features: weather, FX, COT, USDA, RIN, news")
    logger.info("=" * 60)

    # Convert to TimeSeriesDataFrame with single item_id
    ts_df = TimeSeriesDataFrame.from_data_frame(
        df, id_column="item_id", timestamp_column="ts_event"
    )

    # Hardening: Verify we have exactly 1 item (ZL)
    assert ts_df.num_items == 1, f"Expected 1 item_id, got {ts_df.num_items}"
    logger.info(f"✓ TimeSeriesDataFrame: {ts_df.num_items} item, {len(ts_df):,} rows")

    return ts_df


def train_chronos2_model(ts_data, horizon: int, model_path: Path, mode: str = "quick"):
    """Train with AutoGluon 1.5 TimeSeriesPredictor."""
    from autogluon.timeseries import TimeSeriesPredictor

    # Time limits by mode - increased for 9.5M row dataset
    time_limits = {
        "ultrafast": 3600,   # 1 hour - fast statistical models only
        "quick": 7200,       # 2 hours - Chronos-2 needs more time on large data
        "full": 14400,       # 4 hours - full AutoML ensemble
    }
    time_limit = time_limits.get(mode, 7200)
    is_full = mode == "full"

    # Determine frequency based on horizon
    # 5d horizon uses hourly (1h) data, 21d/63d/126d use daily (1d) data
    use_hourly = (horizon == 5)
    freq = "h" if use_hourly else "D"
    freq_label = "hourly" if use_hourly else "daily"

    logger.info(f"Training AutoGluon TimeSeriesPredictor for {horizon}d horizon")
    logger.info(f"  Mode: {mode}")
    logger.info(f"  Frequency: {freq_label} ({freq})")
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
        freq=freq,  # Hourly for 5d, Daily for 21d/63d/126d
        verbosity=2,
    )

    # Training config based on mode
    fit_kwargs = {
        "train_data": ts_data,
        "time_limit": time_limit,
        "presets": "best_quality",
    }

    # Ultrafast mode: fast statistical models only (no deep learning)
    if mode == "ultrafast":
        fit_kwargs["num_val_windows"] = 1
        fit_kwargs["hyperparameters"] = {
            "SeasonalNaive": {},
            "AutoETS": {},
            "DynamicOptimizedTheta": {},
        }
    # Quick mode: Chronos-2 with LoRA fine-tuning + fast models
    elif not is_full:
        fit_kwargs["hyperparameters"] = {
            "Chronos2": {
                "model_path": "autogluon/chronos-2",
                "cross_learning": False,       # Explicit: single item_id
                "fine_tune": True,
                "fine_tune_mode": "lora",      # Stable fine-tuning
                "fine_tune_lr": 1e-5,          # Conservative learning rate
                "fine_tune_steps": 500,
                "fine_tune_batch_size": 16,
                "fine_tune_trainer_kwargs": {
                    "max_grad_norm": 1.0,      # Gradient clipping for stability
                    "warmup_ratio": 0.05,
                },
            },
            "AutoETS": {},  # Fast fallback
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
        # Preflight check with ALL DATA enforcement
        if not preflight_check(conn, horizon=horizon):
            logger.error("Preflight check failed - ALL DATA policy violation or insufficient data")
            sys.exit(1)

        # Load FULL training data from Prisma
        # 5d horizon uses 1h data, 21d/63d/126d use 1d data
        ts_data = load_training_data(conn, horizon=horizon)

        model_version = f"chronos2_ag15_{mode}_h{horizon}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        model_path = MODEL_PATH / f"horizon_{horizon}d"

        if dry_run:
            logger.info(f"\n[DRY RUN] Would train model in {mode} mode")
            logger.info(
                f"[DRY RUN] Data: {len(ts_data):,} rows, {ts_data.num_items} series"
            )
            logger.info(f"[DRY RUN] Output: {model_path}")
            return

        # Initialize MLflow Command Center
        cmd = QuantMLCommandCenter()

        # Use new context manager with hierarchical experiments
        with cmd.training_run("core", horizon=horizon, mode=mode,
                             tags={"model_version": model_version}) as tracker:

            # Log dataset with lineage
            ts_df = ts_data.to_dataframe() if hasattr(ts_data, 'to_dataframe') else ts_data
            tracker.log_dataset(
                ts_df,
                context="training",
                name=f"core_h{horizon}d_training",
                source="prisma://raw.market_futures_1h"
            )

            # Train model with timing
            start_time = time.time()
            predictor = train_chronos2_model(ts_data, horizon, model_path, mode=mode)
            training_time = time.time() - start_time

            # Log complete model with charts
            tracker.log_model_complete(predictor, training_time, generate_charts=True)

            # Save predictions to database
            saved = save_predictions(conn, predictor, ts_data, horizon, model_version)
            tracker.log_live_metric("predictions_saved", saved)

            logger.info(f"\n✅ Completed {mode} training @ {horizon}d ({saved:,} predictions)")

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
