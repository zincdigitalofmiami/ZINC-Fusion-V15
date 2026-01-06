#!/usr/bin/env python3
"""
ZINC-FUSION-V15: STRATEGIC Core Model Training (63d, 126d)

Trains the STRATEGIC Core models using AutoGluon 1.5 TimeSeriesPredictor.
Uses FULL multi-symbol business daily data from Prisma Postgres.

STRATEGIC = Full ensemble, maximum accuracy, longer training
TACTICAL = Lighter training for operational forecasts (see train_core_tactical.py)

Horizons:
    63d  - Quarterly strategic
    126d - 6-month strategic

Modes:
    quick - Chronos-2 + TFT, 2 hours
    full  - Full AutoML ensemble, 6 hours (production)

Usage:
    python scripts/train_core_chronos.py --horizon 126 --mode full
    python scripts/train_core_chronos.py --horizon 63 --mode full
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
# All horizons use DAILY data from 2000+ with ALL sources
# =============================================================================
# Let AutoGluon handle sparse/missing data - it's designed for this.
# FRED goes back to 1800s - include ALL of it.
# If 2000+ ALL fails, fallback is 2000+ full-coverage only.
CORE_START_DATE = "2000-01-01"   # All horizons use 2000+ daily

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
# 1D (Daily):   Symbol OHLCV
# 1D (Daily):   FX Spot, RIN, FRED daily series, Weather, News
# 1W (Weekly):  CFTC COT (Tuesday report), USDA Exports (Thursday)
# 1M (Monthly): USDA WASDE (around 12th)
#
# TRAINING STRATEGY:
# ALL MODELS: Train on 1D base, forward-fill 1W/1M features

# Minimum data requirements
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
        # Check daily data volume
        cur.execute(
            """
            SELECT COUNT(*) as rows, COUNT(DISTINCT symbol) as symbols
            FROM "raw"."market_futures_1d"
        """
        )
        row = cur.fetchone()
        total_rows, total_symbols = row[0], row[1]

        logger.info(f"  Daily data: {total_rows:,} rows, {total_symbols} symbols")

        if total_rows < MIN_ROWS_1D:
            logger.error(
                f"  ❌ Insufficient rows: {total_rows:,} < {MIN_ROWS_1D:,} required"
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
    Load training data from Prisma Postgres.

    Architecture (UNIFIED DAILY):
    - ALL horizons (5d/21d/63d/126d) use DAILY data from 2000+
    - No hourly data - ensures training/prediction frequency match
    - Volatility proxy features compensate for lost intraday signal

    All symbols are pivoted WIDE so each symbol's OHLCV becomes separate columns.
    ZL is the target, other 83 symbols become covariates.
    """
    from autogluon.timeseries import TimeSeriesDataFrame

    logger.info("=" * 60)
    logger.info("LOADING TRAINING DATA FROM PRISMA")
    logger.info("=" * 60)

    # ALL horizons use daily data - unified pipeline
    start_date = CORE_START_DATE
    freq_label = "1d"

    logger.info(f"Horizon: {horizon}d")
    logger.info(f"Base frequency: {freq_label} (UNIFIED - all horizons use daily)")
    logger.info(f"Start date: {start_date}")
    logger.info(f"Strategy: Daily base + volatility proxies + merge_asof for lower frequencies")
    logger.info(f"  - Base: 1D symbols with volatility proxy features")
    logger.info(f"  - Forward-fill: 1D (FX, RIN, FRED, Weather, News)")
    logger.info(f"  - Forward-fill: 1W (COT, USDA Exports)")
    logger.info(f"  - Forward-fill: 1M (WASDE)")

    # =========================================================================
    # 1. BASE: Market futures (DAILY) - PIVOT ALL SYMBOLS WIDE
    # =========================================================================
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
    # 1b. VOLATILITY PROXY FEATURES - Compensate for lost intraday signal
    # =========================================================================
    # Since we're using daily data for all horizons (including 5d), we engineer
    # features that capture intraday volatility patterns from OHLC data.
    logger.info("   Engineering volatility proxy features...")

    # Key symbols to create volatility proxies for
    vol_symbols = ["ZL", "ZS", "ZM", "CL", "CPO", "ES", "GC"]  # Soy complex + energy + macro

    vol_features_added = 0
    for sym in vol_symbols:
        open_col = f"{sym}_open"
        high_col = f"{sym}_high"
        low_col = f"{sym}_low"
        close_col = f"{sym}_close"

        # Check if symbol exists in data
        if close_col not in df.columns:
            continue

        # 1. Daily Range: high - low (captures intraday volatility)
        if high_col in df.columns and low_col in df.columns:
            df[f"{sym}_daily_range"] = df[high_col] - df[low_col]
            vol_features_added += 1

        # 2. Daily Range Pct: (high - low) / close (normalized volatility)
        if high_col in df.columns and low_col in df.columns:
            df[f"{sym}_daily_range_pct"] = (df[high_col] - df[low_col]) / df[close_col].replace(0, np.nan)
            vol_features_added += 1

        # 3. Overnight Gap: open(t) - close(t-1) (off-hours news impact)
        if open_col in df.columns:
            df[f"{sym}_overnight_gap"] = df[open_col] - df[close_col].shift(1)
            vol_features_added += 1

        # 4. Overnight Gap Pct: gap / close(t-1) (normalized gap)
        if open_col in df.columns:
            prev_close = df[close_col].shift(1)
            df[f"{sym}_overnight_gap_pct"] = (df[open_col] - prev_close) / prev_close.replace(0, np.nan)
            vol_features_added += 1

        # 5. Close Location: (close - low) / (high - low) (buyer/seller control)
        if high_col in df.columns and low_col in df.columns:
            daily_range = df[high_col] - df[low_col]
            df[f"{sym}_close_location"] = (df[close_col] - df[low_col]) / daily_range.replace(0, np.nan)
            vol_features_added += 1

        # 6. Body Ratio: |close - open| / (high - low) (conviction of move)
        if open_col in df.columns and high_col in df.columns and low_col in df.columns:
            daily_range = df[high_col] - df[low_col]
            df[f"{sym}_body_ratio"] = abs(df[close_col] - df[open_col]) / daily_range.replace(0, np.nan)
            vol_features_added += 1

    logger.info(f"   Added {vol_features_added} volatility proxy features for {len(vol_symbols)} symbols")

    # =========================================================================
    # 1c. ELITE TECHNICAL INDICATORS - 27 curated institutional-grade indicators
    # =========================================================================
    # Based on research of quant desks: Hurst, ConnorsRSI, Fisher Transform,
    # McGinley Dynamic, TTM Squeeze, Schaff Trend Cycle, RVI, Elder Force Index,
    # plus optimized MAs (KAMA, HMA, ALMA), RSI variants, MACD, CCI, volatility
    # (Garman-Klass, Yang-Zhang), and volume flow (CMF, Volume Z-Score).
    logger.info("   Computing elite technical indicators (27 curated)...")

    try:
        from src.fusion.features.elite_indicators import EliteIndicators

        # Compute elite indicators for ZL (primary target)
        elite = EliteIndicators(df, symbol="ZL")
        df = elite.compute_all()

        # Count elite indicators added
        elite_cols = [c for c in df.columns if any(x in c for x in [
            "hurst", "connors", "fisher", "mcginley", "ttm_squeeze", "schaff",
            "rvi", "elder_force", "kama", "hma", "alma", "rsi_2", "rsi_14",
            "cumulative_rsi", "macd", "cci", "atr_ratio", "garman", "yang_zhang",
            "bb_percent", "cmf", "volume_zscore", "unusual_volume", "stc"
        ])]
        logger.info(f"   Added {len(elite_cols)} elite technical indicators for ZL")

        # Also compute for key related symbols (ZS, CL) if time permits
        for related_sym in ["ZS", "CL"]:
            if f"{related_sym}_close" in df.columns:
                try:
                    elite_related = EliteIndicators(df, symbol=related_sym)
                    # Just compute RSI and MACD for related symbols (avoid feature explosion)
                    elite_related.add_rsi_variants()
                    elite_related.add_macd_variants()
                    df = elite_related.df

                    related_cols = [c for c in df.columns if c.startswith(f"{related_sym.lower()}_")]
                    logger.info(f"   Added {len(related_cols)} indicators for {related_sym}")
                except Exception as e:
                    logger.warning(f"   Could not compute indicators for {related_sym}: {e}")

    except ImportError as e:
        logger.warning(f"   Elite indicators module not available: {e}")
    except Exception as e:
        logger.warning(f"   Error computing elite indicators: {e}")

    # =========================================================================
    # 2. FRED Economic Data - MERGE_ASOF by frequency (no artificial NaNs)
    # =========================================================================
    # Instead of pivot → ffill (2.7M artificial NaNs), we:
    # 1. Group series by native frequency (daily/weekly/monthly/quarterly)
    # 2. Pivot each group at its native frequency
    # 3. merge_asof to daily base with direction='backward' (last known value)
    logger.info("2. Loading FRED economic data (merge_asof by frequency)...")

    # Define frequency groups (150 series - includes DB series + future additions)
    # Missing series are handled gracefully - only series present in DB are merged
    #
    # Daily: 59 series (>5000 observations typically)
    FRED_DAILY = [
        # Interest rates & spreads
        "TEDRATE", "SOFR", "DGS10", "DGS2", "DGS1", "DGS5", "DGS7", "DGS20", "DGS30",
        "DGS1MO", "DGS3MO", "DGS6MO", "T10Y2Y", "T10Y3M", "T10YIE",
        "DFII5", "DFII7", "DFII10", "DFII20", "DFII30",
        "DPRIME", "DFF", "DTB3", "DTB6", "DBAA", "DAAA",
        "DFEDTARL", "DFEDTARU",  # Fed target rate bounds
        # Credit spreads
        "BAMLH0A0HYM2", "BAMLC0A0CM",
        # FX rates (18 pairs)
        "DEXCHUS", "DEXUSEU", "DEXJPUS", "DEXUSUK", "DEXCAUS", "DEXMXUS",
        "DEXBZUS", "DEXINUS", "DEXMAUS", "DEXKOUS", "DEXSIUS", "DEXTHUS", "DEXHKUS",
        "DEXSZUS", "DEXSFUS", "DEXTAUS", "DEXUSAL", "DEXNOUS",
        # Dollar indices
        "DTWEXBGS", "DTWEXAFEGS", "DTWEXEMEGS", "DTWEXM",
        # Energy
        "DCOILWTICO", "DCOILBRENTEU", "DHHNGSP", "DHOILNYH",
        # Volatility & equity indices
        "VIXCLS", "NASDAQCOM",
        # Policy uncertainty
        "USEPUINDXD",
    ]
    # Weekly: 14 series (1000-5000 observations typically)
    FRED_WEEKLY = [
        "GASREGW", "GASDESW",  # Gas prices
        "ICSA", "CCSA",  # Unemployment claims
        "NFCI", "STLFSI", "STLFSI4",  # Financial stress indices
        "WALCL", "WRESBAL",  # Fed balance sheet
        "MORTGAGE30US", "RRPONTSYD",  # Rates
        "DDFUELUSGULF",  # Diesel fuel
        "SP500", "SP500_HISTORICAL",  # S&P 500
    ]
    # Monthly: 67 series (200-1000 observations typically)
    FRED_MONTHLY = [
        # CPI / Inflation
        "CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "PCE", "CHNCPIALLMINMEI",
        # PPI / Producer prices
        "PPIACO", "WPSFD49207", "WPSFD49502", "WPUFD49116", "WPUFD49207", "WPUSI012011",
        "WPU06140341", "WPU01830171", "WPU057303",
        "PCU311224311224",  # Soybean oil processing PPI
        # Consumer prices (specific)
        "APU000074714",  # Fats and oils CPI
        "CUSR0000SAF11", "CUSR0000SETA01", "CUSR0000SETA02", "CUSR0000SETB01", "CUSR0000SAH1",
        # Employment
        "UNRATE", "PAYEMS", "MANEMP", "AWHMAN", "CES0500000003", "JTSJOL",
        # Money supply / Fed
        "M2SL", "TOTRESNS", "BOGMBASE", "FEDFUNDS", "BUSLOANS",
        # Industrial / manufacturing
        "INDPRO", "DGORDER", "NEWORDER",
        # Consumer
        "RSAFS", "RSXFS", "DSPIC96", "UMCSENT", "MICH", "PSAVERT",
        # Housing
        "HOUST", "PERMIT", "CSUSHPISA",
        # Trade
        "BOPGSTB", "BOPGTB", "IEABC",
        # China-specific
        "CHNMAINLANDTPU", "MYAGM2CNM189N", "IMPCH",
        "XTEXVA01CNM667S", "XTIMVA01CNM667S",  # China trade
        # Commodity prices (IMF World Bank) - CRITICAL FOR ZL
        "PSOILUSDM",   # Soybean Oil price (USD) - DIRECT ZL indicator
        "PSOYBUSDM",   # Soybean price (USD) - Input cost
        "PPOILUSDM",   # Palm Oil price - Key substitute
        "PROILUSDM",   # Rapeseed Oil price - Substitute
        "PSUNOUSDM",   # Sunflower Oil price - Substitute
        "PCOPPUSDM",   # Copper price - Industrial demand proxy
        "PMAIZMTUSDM", # Maize price - Competing crop
        "PWHEAMTUSDM", # Wheat price - Competing crop
        "PRICENPQUSDM", # Rice price - Food inflation proxy
        "PNGASEUUSDM", # Natural Gas EU price - Energy costs
        # Policy uncertainty
        "USEPUINDXM", "EMVTRADEPOLEMV", "EPUTRADE",
        # Volatility
        "OVXCLS",  # Oil volatility index
    ]
    # Quarterly: 10 series (<200 observations typically)
    FRED_QUARTERLY = [
        "GDPC1", "GDP",  # GDP
        "DRCCLACBS",  # Delinquency rates
        "B235RC1Q027SBEA",  # Farm income
        "CHNGDPNQDSMEI",  # China GDP
        "EXPGS", "IMPGS",  # Trade
        "WPU01830161",  # Farm PPI
        "IR3TIB01CNM156N",  # China 3-month interbank rate
        "PPIFGS",  # PPI finished goods (discontinued 2015)
    ]

    # Load all FRED data
    fred_long = pd.read_sql("""
        SELECT as_of_date, series_id, value
        FROM "raw"."fred_observations_1d"
        ORDER BY as_of_date, series_id
    """, conn)
    fred_long["as_of_date"] = pd.to_datetime(fred_long["as_of_date"])
    logger.info(f"   Long format: {len(fred_long):,} rows, {fred_long['series_id'].nunique()} series")

    if fred_long.empty:
        raise ValueError("FRED observations query returned 0 rows - check fred_observations_1d table")

    # Get daily base dates from market data
    daily_dates = pd.DataFrame({"as_of_date": pd.to_datetime(df["ts_event"].unique())}).sort_values("as_of_date")

    def merge_fred_group(series_list: list, freq_name: str) -> pd.DataFrame:
        """Pivot a frequency group and merge_asof to daily base."""
        group_data = fred_long[fred_long["series_id"].isin(series_list)]
        if group_data.empty:
            return pd.DataFrame()

        # Pivot at native frequency (no artificial NaNs)
        pivoted = group_data.pivot_table(
            index="as_of_date", columns="series_id", values="value", aggfunc="last"
        ).sort_index().reset_index()

        # merge_asof: for each daily date, get last known value (direction='backward')
        merged = pd.merge_asof(
            daily_dates.sort_values("as_of_date"),
            pivoted.sort_values("as_of_date"),
            on="as_of_date",
            direction="backward"
        )
        actual_cols = [c for c in series_list if c in merged.columns]
        logger.info(f"   {freq_name}: {len(actual_cols)} series merged via merge_asof")
        return merged

    # Merge each frequency group
    fred_daily = merge_fred_group(FRED_DAILY, "Daily")
    fred_weekly = merge_fred_group(FRED_WEEKLY, "Weekly")
    fred_monthly = merge_fred_group(FRED_MONTHLY, "Monthly")
    fred_quarterly = merge_fred_group(FRED_QUARTERLY, "Quarterly")

    # Combine all FRED data
    fred_df = daily_dates.copy()
    for freq_df in [fred_daily, fred_weekly, fred_monthly, fred_quarterly]:
        if not freq_df.empty:
            # Drop as_of_date from freq_df to avoid duplication, then merge
            other_cols = [c for c in freq_df.columns if c != "as_of_date"]
            if other_cols:
                fred_df = fred_df.merge(freq_df[["as_of_date"] + other_cols], on="as_of_date", how="left")

    fred_df["trade_date"] = fred_df["as_of_date"].dt.date
    fred_features = [c for c in fred_df.columns if c not in ("as_of_date", "trade_date")]

    # Only bfill for leading NaNs (series that start later than base)
    pre_fill_nans = fred_df[fred_features].isna().sum().sum()
    fred_df[fred_features] = fred_df[fred_features].bfill()
    post_fill_nans = fred_df[fred_features].isna().sum().sum()
    logger.info(f"   Combined: {len(fred_df):,} rows, {len(fred_features)} FRED features")
    logger.info(f"   Leading NaN bfill: {pre_fill_nans:,} → {post_fill_nans:,} (merge_asof approach)")

    # =========================================================================
    # 3. WEATHER Data (215K rows) - pivot by station, ALL 10 weather variables
    # =========================================================================
    logger.info("3. Loading NOAA weather data (pivoted by station)...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                station_id,
                as_of_date,
                tavg_c, tmin_c, tmax_c, prcp_mm, snow_mm,
                awnd_ms, snwd_mm, evap_mm, rhav_pct, wsfg_ms
            FROM "raw"."weather_noaa_1d"
            ORDER BY as_of_date, station_id
        """)
        weather_cols = [desc[0] for desc in cur.description]
        weather_rows = cur.fetchall()
    weather_long = pd.DataFrame(weather_rows, columns=weather_cols)
    weather_long["trade_date"] = pd.to_datetime(weather_long["as_of_date"]).dt.date

    # Pivot: each station × variable becomes a column (57 stations × 10 vars = 570 features)
    weather_vars = ["tavg_c", "tmin_c", "tmax_c", "prcp_mm", "snow_mm",
                    "awnd_ms", "snwd_mm", "evap_mm", "rhav_pct", "wsfg_ms"]
    weather_pivot_dfs = []
    for var in weather_vars:
        pivot = weather_long.pivot_table(
            index="trade_date", columns="station_id", values=var, aggfunc="first"
        )
        pivot.columns = [f"weather_{var}_{c}" for c in pivot.columns]
        weather_pivot_dfs.append(pivot)
    weather_df = pd.concat(weather_pivot_dfs, axis=1).reset_index()
    n_stations = weather_long["station_id"].nunique()

    # Forward-fill weather data (some stations have gaps) - NO NULLs allowed
    weather_features = [c for c in weather_df.columns if c != "trade_date"]
    weather_df[weather_features] = weather_df[weather_features].ffill().bfill()
    logger.info(f"   Loaded {len(weather_long):,} rows → {len(weather_df):,} dates, {len(weather_df.columns)-1} weather features ({n_stations} stations × {len(weather_vars)} vars, ffill+bfill applied)")

    # =========================================================================
    # 4. FX Data - Pull from FRED (complete history) instead of sparse fx_spot_1d
    # =========================================================================
    # FRED has 18 DEX currency series with 6,500-13,800 rows each - complete history
    # Critical pairs: DEXBZUS (Brazil), DEXCHUS (China), DEXMXUS (Mexico), DEXUSEU (Euro)
    logger.info("4. Loading FX data from FRED (complete history)...")
    fx_series = [
        "DEXCAUS", "DEXMAUS", "DEXINUS", "DEXCHUS", "DEXMXUS", "DEXBZUS",
        "DEXUSEU", "DEXUSUK", "DEXJPUS", "DEXNOUS", "DEXSFUS", "DEXUSAL",
        "DEXSZUS", "DEXTHUS", "DEXHKUS", "DEXKOUS", "DEXSIUS", "DEXTAUS"
    ]
    with conn.cursor() as cur:
        cur.execute("""
            SELECT series_id, as_of_date, value
            FROM "raw"."fred_observations_1d"
            WHERE series_id IN %s
            ORDER BY as_of_date, series_id
        """, (tuple(fx_series),))
        fx_rows = cur.fetchall()
    fx_df = pd.DataFrame(fx_rows, columns=["series_id", "as_of_date", "value"])
    fx_df["trade_date"] = pd.to_datetime(fx_df["as_of_date"]).dt.date

    # Pivot: each FX series becomes a column
    fx_wide = fx_df.pivot_table(index="trade_date", columns="series_id", values="value", aggfunc="last")
    fx_wide.columns = [f"fx_{c}" for c in fx_wide.columns]
    fx_wide = fx_wide.reset_index()

    # Fill gaps (ffill for weekends, bfill for leading NaNs) - NO NULLs allowed
    fx_wide = fx_wide.ffill().bfill()
    logger.info(f"   Loaded {len(fx_wide):,} dates, {len(fx_wide.columns)-1} FX pairs from FRED (zero NaN)")

    # =========================================================================
    # 5. CFTC COT Positioning (WEEKLY) - merge_asof to daily base
    # =========================================================================
    logger.info("5. Loading CFTC COT positioning (merge_asof weekly→daily)...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                report_date,
                symbol,
                open_interest,
                managed_money_net,
                managed_money_net_pct_oi,
                prod_merc_net,
                prod_merc_net_pct_oi
            FROM "raw"."cftc_cot_1w"
            ORDER BY report_date, symbol
        """)
        cot_rows = cur.fetchall()
    cot_long = pd.DataFrame(cot_rows, columns=[
        "report_date", "symbol", "open_interest", "managed_money_net",
        "managed_money_net_pct_oi", "prod_merc_net", "prod_merc_net_pct_oi"
    ])
    cot_long["report_date"] = pd.to_datetime(cot_long["report_date"])

    # Pivot at native weekly frequency
    cot_metrics = ["open_interest", "managed_money_net", "managed_money_net_pct_oi",
                   "prod_merc_net", "prod_merc_net_pct_oi"]
    cot_pivot_dfs = []
    for metric in cot_metrics:
        pivot = cot_long.pivot_table(
            index="report_date", columns="symbol", values=metric, aggfunc="first"
        )
        pivot.columns = [f"cot_{metric}_{c}" for c in pivot.columns]
        cot_pivot_dfs.append(pivot)
    cot_native = pd.concat(cot_pivot_dfs, axis=1).reset_index()
    n_symbols = cot_long["symbol"].nunique()

    # merge_asof: for each daily date, get last known COT report (direction='backward')
    cot_wide = pd.merge_asof(
        daily_dates.rename(columns={"as_of_date": "trade_date"}).assign(trade_date=lambda x: pd.to_datetime(x["trade_date"])),
        cot_native.rename(columns={"report_date": "trade_date"}).sort_values("trade_date"),
        on="trade_date",
        direction="backward"
    )
    cot_features = [c for c in cot_wide.columns if c.startswith("cot_")]

    # Only bfill for leading NaNs (before first COT report)
    pre_nans = cot_wide[cot_features].isna().sum().sum()
    cot_wide[cot_features] = cot_wide[cot_features].bfill()
    post_nans = cot_wide[cot_features].isna().sum().sum()
    cot_wide["trade_date"] = cot_wide["trade_date"].dt.date
    logger.info(f"   Loaded {len(cot_long):,} weekly reports → {len(cot_wide):,} daily rows via merge_asof")
    logger.info(f"   COT features: {len(cot_features)} ({n_symbols} symbols × {len(cot_metrics)} metrics), leading bfill: {pre_nans:,} → {post_nans:,}")

    # =========================================================================
    # 6. USDA Export Sales (WEEKLY) - merge_asof to daily base
    # =========================================================================
    logger.info("6. Loading USDA export sales (merge_asof weekly→daily)...")
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
    usda_native = pd.DataFrame(usda_rows, columns=["report_date", "usda_soy_net_sales", "usda_soy_exports", "usda_zl_net_sales", "usda_zl_exports", "usda_zm_net_sales"])
    usda_native["report_date"] = pd.to_datetime(usda_native["report_date"])

    # merge_asof: for each daily date, get last known USDA report
    usda_df = pd.merge_asof(
        daily_dates.rename(columns={"as_of_date": "trade_date"}).assign(trade_date=lambda x: pd.to_datetime(x["trade_date"])),
        usda_native.rename(columns={"report_date": "trade_date"}).sort_values("trade_date"),
        on="trade_date",
        direction="backward"
    )
    usda_features = [c for c in usda_df.columns if c.startswith("usda_")]

    # Only bfill for leading NaNs
    pre_nans = usda_df[usda_features].isna().sum().sum()
    usda_df[usda_features] = usda_df[usda_features].bfill()
    post_nans = usda_df[usda_features].isna().sum().sum()
    usda_df["trade_date"] = usda_df["trade_date"].dt.date
    logger.info(f"   Loaded {len(usda_native):,} weekly reports → {len(usda_df):,} daily rows via merge_asof")
    logger.info(f"   USDA features: {len(usda_features)}, leading bfill: {pre_nans:,} → {post_nans:,}")

    # =========================================================================
    # 7. USDA WASDE (MONTHLY) - merge_asof to daily base
    # =========================================================================
    logger.info("7. Loading USDA WASDE fundamentals (merge_asof monthly→daily)...")
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
    wasde_native = pd.DataFrame(wasde_rows, columns=["report_date", "wasde_soy_production", "wasde_soy_exports", "wasde_soy_stocks", "wasde_zl_production", "wasde_zl_exports"])
    wasde_native["report_date"] = pd.to_datetime(wasde_native["report_date"])

    # merge_asof: for each daily date, get last known WASDE report
    wasde_df = pd.merge_asof(
        daily_dates.rename(columns={"as_of_date": "trade_date"}).assign(trade_date=lambda x: pd.to_datetime(x["trade_date"])),
        wasde_native.rename(columns={"report_date": "trade_date"}).sort_values("trade_date"),
        on="trade_date",
        direction="backward"
    )
    wasde_features = [c for c in wasde_df.columns if c.startswith("wasde_")]

    # Only bfill for leading NaNs
    pre_nans = wasde_df[wasde_features].isna().sum().sum()
    wasde_df[wasde_features] = wasde_df[wasde_features].bfill()
    post_nans = wasde_df[wasde_features].isna().sum().sum()
    wasde_df["trade_date"] = wasde_df["trade_date"].dt.date
    logger.info(f"   Loaded {len(wasde_native):,} monthly reports → {len(wasde_df):,} daily rows via merge_asof")
    logger.info(f"   WASDE features: {len(wasde_features)}, leading bfill: {pre_nans:,} → {post_nans:,}")

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

    # Forward-fill RIN prices (some gaps in reporting) - NO NULLs allowed
    rin_features = [c for c in rin_wide.columns if c != "trade_date"]
    rin_wide[rin_features] = rin_wide[rin_features].ffill().bfill()
    logger.info(f"   Loaded {len(rin_wide):,} dates, {len(rin_wide.columns)-1} RIN prices (ffill+bfill applied)")

    # =========================================================================
    # 9. NEWS Sentiment - Compute REAL sentiment from headlines using classify_article()
    # =========================================================================
    # The sentiment_score column is NULL - we compute it live from headlines
    # using the rule-based classifier in src/fusion/api/news_sentiment.py
    logger.info("9. Loading news articles and computing sentiment...")
    from src.fusion.api.news_sentiment import classify_article

    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                id,
                as_of_date,
                headline,
                content,
                source,
                bucket_name,
                zl_sentiment,
                is_trump_related
            FROM "raw"."news_articles_1d"
            ORDER BY as_of_date
        """)
        news_rows = cur.fetchall()

    # Compute sentiment for each article using classify_article()
    news_records = []
    for row in news_rows:
        article_id, as_of_date, headline, content, source_name, bucket_name, zl_sentiment, is_trump_related = row
        # Build article dict for classifier
        article = {
            "id": article_id,
            "title": headline or "",
            "body": content or "",
            "source": source_name or "",
        }
        result = classify_article(article)
        news_records.append({
            "as_of_date": as_of_date,
            "headline": headline,
            "impact_score": result["impact_score"],  # -1 to +1, computed from rules
            "direction": result["overall_direction"],  # bullish/bearish/uncertain
            "bucket_name": bucket_name,
            "is_trump_related": is_trump_related,
            "num_matches": len(result["matches"]),
            "alert_buckets": result["alert_buckets"],
        })

    news_raw = pd.DataFrame(news_records)
    news_raw["trade_date"] = pd.to_datetime(news_raw["as_of_date"]).dt.date

    # Aggregate by date - multiple articles per day
    news_agg = news_raw.groupby("trade_date").agg({
        "impact_score": ["mean", "sum", "std", "min", "max"],  # Sentiment stats
        "direction": lambda x: (x == "bullish").sum(),  # Count bullish
        "is_trump_related": "sum",  # Trump article count
        "num_matches": "sum",  # Total category matches (signal strength)
        "headline": "count",  # Article count
    })
    news_agg.columns = [
        "news_sentiment_mean", "news_sentiment_sum", "news_sentiment_std",
        "news_sentiment_min", "news_sentiment_max",
        "news_bullish_count", "news_trump_count", "news_signal_strength", "news_article_count"
    ]
    news_agg = news_agg.reset_index()

    # Add bearish count
    bearish_counts = news_raw[news_raw["direction"] == "bearish"].groupby("trade_date").size().reset_index(name="news_bearish_count")
    news_df = news_agg.merge(bearish_counts, on="trade_date", how="left")
    news_df["news_bearish_count"] = news_df["news_bearish_count"].fillna(0).astype(int)

    # Fill NaN std (when only 1 article) with 0
    news_df["news_sentiment_std"] = news_df["news_sentiment_std"].fillna(0)

    logger.info(f"   Computed sentiment for {len(news_raw):,} articles → {len(news_df):,} dates")
    logger.info(f"   Sentiment features: mean={news_df['news_sentiment_mean'].mean():.4f}, bullish={news_df['news_bullish_count'].sum()}, bearish={news_df['news_bearish_count'].sum()}")

    # =========================================================================
    # JOIN ALL DATA TO DAILY BASE
    # =========================================================================
    logger.info("=" * 60)
    logger.info(f"JOINING ALL FEATURES TO {freq_label.upper()} BASE")
    logger.info("=" * 60)

    # Start with base data
    logger.info(f"  Base: {len(df):,} {freq_label} rows")

    # Join FRED
    df = df.merge(fred_df, on="trade_date", how="left")
    logger.info(f"  + FRED: {len(fred_features)} features")

    # Join Weather (lagged by 1 day to avoid look-ahead bias)
    # NOTE: Weather actuals are known at end of day, so we use t-1 weather for t predictions
    weather_features = [c for c in weather_df.columns if c != "trade_date"]
    weather_df_lagged = weather_df.copy()
    weather_df_lagged["trade_date"] = pd.to_datetime(weather_df_lagged["trade_date"]) + pd.Timedelta(days=1)
    weather_df_lagged["trade_date"] = weather_df_lagged["trade_date"].dt.date
    df = df.merge(weather_df_lagged, on="trade_date", how="left")
    logger.info(f"  + Weather: {len(weather_features)} features (lagged 1 day to avoid look-ahead)")

    # Join Spot FX
    df = df.merge(fx_wide, on="trade_date", how="left")
    logger.info(f"  + Spot FX: {len(fx_wide.columns)-1} features")

    # Join CFTC COT
    cot_features = [c for c in cot_wide.columns if c != "trade_date"]
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
    logger.info(f"  + News: {len(news_df.columns)-1} features")

    # Drop trade_date helper column
    df = df.drop(columns=["trade_date"])

    # =========================================================================
    # DATA IS ALREADY PIVOTED WIDE - no symbol column exists
    # ZL close is "target", all other symbols are covariates (e.g., BTC_close)
    # =========================================================================

    # Sort by timestamp and fill all NaNs - NO NULLs allowed
    df = df.sort_values("ts_event")
    logger.info("  Filling all NaN values (forward-fill then backward-fill for leading NaNs)...")
    df = df.ffill()  # Forward fill: carry last known value forward
    df = df.bfill()  # Backward fill: fill leading NaNs with first valid value

    # Log post-fill NaN rates by category
    nan_rate_overall = df.isna().mean().mean()
    logger.info(f"  POST-FILL NaN rate (overall): {nan_rate_overall:.1%}")

    def nan_rate_for(prefix: str) -> float:
        cols = [c for c in df.columns if c.startswith(prefix)]
        return float(df[cols].isna().mean().mean()) if cols else 0.0

    # Market symbols don't have a prefix - count by OHLCV suffix
    market_cols = [c for c in df.columns if c.endswith(('_open', '_high', '_low', '_close', '_volume'))]
    market_nan = df[market_cols].isna().mean().mean() if market_cols else 0.0
    logger.info(f"    market: {market_nan:.1%}")
    logger.info(f"    weather: {nan_rate_for('weather_'):.1%}")
    logger.info(f"    cot: {nan_rate_for('cot_'):.1%}")
    logger.info(f"    fx: {nan_rate_for('fx_'):.1%}")
    logger.info(f"    usda: {nan_rate_for('usda_'):.1%}")
    logger.info(f"    wasde: {nan_rate_for('wasde_'):.1%}")
    logger.info(f"    rin: {nan_rate_for('rin_'):.1%}")
    logger.info(f"    news: {nan_rate_for('news_'):.1%}")

    # CRITICAL: Verify NO NaN values remain
    remaining_nans = df.isna().sum().sum()
    if remaining_nans > 0:
        nan_cols = df.columns[df.isna().any()].tolist()
        logger.error(f"  ❌ {remaining_nans} NaN values remain in columns: {nan_cols[:10]}...")
        # Fill any stragglers with 0 (should not happen after ffill+bfill)
        df = df.fillna(0)
        logger.warning(f"  ⚠️ Filled {remaining_nans} remaining NaNs with 0")
    else:
        logger.info(f"  ✅ Zero NaN values - ALL DATA COMPLETE")

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
    """
    Train with AutoGluon 1.5 TimeSeriesPredictor.

    KEY FEATURES:
    - Weighted Quantile Loss (WQL): Optimizes for probabilistic forecasting
    - Chronos-2 with Group Attention: Learns covariate relationships automatically
      (e.g., crude oil spike → ZL price shift) without manual lag features
    - TemporalFusionTransformer: Variable selection for interpretability

    Group Attention (Chronos-2):
    - Shares information across multiple time series within a group
    - Naturally handles covariates (WASDE reports, crude oil, COT positioning)
    - No need to manually engineer "WASDE_release_lag_3d" type features
    """
    from autogluon.timeseries import TimeSeriesPredictor

    # Time limits by mode - increased for large dataset with many covariates
    time_limits = {
        "ultrafast": 3600,   # 1 hour - fast statistical models only
        "quick": 7200,       # 2 hours - Chronos-2 needs more time on large data
        "full": 21600,       # 6 hours - full AutoML ensemble with TFT + Chronos-2
    }
    time_limit = time_limits.get(mode, 7200)
    is_full = mode == "full"

    # ALL horizons use business daily (futures markets closed weekends)
    freq = "B"
    freq_label = "business daily"

    logger.info(f"Training AutoGluon TimeSeriesPredictor for {horizon}d horizon")
    logger.info(f"  Mode: {mode}")
    logger.info(f"  Frequency: {freq_label} ({freq})")
    logger.info(f"  Dataset: {len(ts_data):,} rows, {ts_data.num_items} series")
    logger.info(f"  Time limit: {time_limit // 60} minutes")
    logger.info(f"  Eval Metric: WQL (Weighted Quantile Loss) - probabilistic")
    logger.info(f"  Quantiles: {QUANTILE_LEVELS}")

    if is_full:
        logger.info(f"  Models: Full ensemble (Chronos-2 + TFT + DeepAR + PatchTST + statistical)")
        logger.info(f"  Features: Group attention for automatic covariate learning")
    else:
        logger.info(f"  Models: Chronos-2 + TFT ({mode} mode)")

    model_path.mkdir(parents=True, exist_ok=True)

    # Configure TimeSeriesPredictor with WQL for probabilistic forecasting
    # WQL = Weighted Quantile Loss - measures accuracy of quantile forecasts
    predictor = TimeSeriesPredictor(
        prediction_length=horizon,
        path=str(model_path),
        target="target",
        eval_metric="WQL",  # Weighted Quantile Loss - better for probabilistic forecasts
        quantile_levels=QUANTILE_LEVELS,  # P10, P25, P50, P75, P90 for procurement decisions
        freq=freq,
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

    # Quick mode: Chronos-2 + TFT for covariate learning
    elif not is_full:
        fit_kwargs["hyperparameters"] = {
            # Chronos-2: Group attention for automatic covariate learning
            # "Group attention shares information across multiple time series within a group,
            #  which may represent sets of related series, variates of a multivariate series,
            #  or targets and covariates in a forecasting task" - Amazon Research
            "Chronos2": {
                "model_path": "amazon/chronos-2",  # Use official Amazon model
                "fine_tune": True,
                "fine_tune_mode": "lora",          # Efficient fine-tuning
                "fine_tune_lr": 1e-5,
                "fine_tune_steps": 500,
                "fine_tune_batch_size": 16,
                "fine_tune_trainer_kwargs": {
                    "max_grad_norm": 1.0,
                    "warmup_ratio": 0.05,
                },
            },
            # TFT: Variable selection networks for interpretability
            # "Variable selection networks select relevant input variables at each time step"
            # Shows which covariates (WASDE, crude oil, COT) drive predictions
            "TemporalFusionTransformer": {
                "context_length": max(64, 2 * horizon),  # Look back at least 2x horizon
            },
            "AutoETS": {},  # Fast statistical fallback
        }

    # Full mode: Complete ensemble with all models
    else:
        fit_kwargs["hyperparameters"] = {
            # Chronos-2 with group attention
            "Chronos2": {
                "model_path": "amazon/chronos-2",
                "fine_tune": True,
                "fine_tune_mode": "lora",
                "fine_tune_lr": 1e-5,
                "fine_tune_steps": 1000,  # More steps for full training
                "fine_tune_batch_size": 32,
            },
            # TFT for variable selection / interpretability
            "TemporalFusionTransformer": {
                "context_length": max(128, 3 * horizon),
                "hidden_size": 64,
                "lstm_layers": 2,
                "num_heads": 4,
                "dropout_rate": 0.1,
            },
            # DeepAR for probabilistic forecasting
            "DeepAR": {
                "context_length": max(64, 2 * horizon),
            },
            # PatchTST for long-range dependencies
            "PatchTST": {
                "context_length": max(128, 3 * horizon),
            },
            # Statistical models for ensemble diversity
            "AutoETS": {},
            "AutoARIMA": {},
            "DynamicOptimizedTheta": {},
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
        # All horizons use daily data
        ts_data = load_training_data(conn, horizon=horizon)

        model_version = f"strategic_chronos2_ag15_{mode}_h{horizon}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # STRATEGIC models - all horizons save to strategic/ subfolder
        model_path = MODEL_PATH / f"horizon_{horizon}d" / "strategic"

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
                source="prisma://raw.market_futures_1d"
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
