#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Generate Specialist Features from ALL Raw Data

This script generates comprehensive specialist features using ALL available
data sources, not just a subset.

Data Sources Used:
- Market futures (84 symbols) - OHLCV + technical indicators
- FRED economic (111 features)
- Weather NOAA (10 features)
- FX Spot (30 pairs)
- CFTC COT (20 features)
- USDA Exports (5 features)
- USDA WASDE (5 features)
- EPA RIN (4 features)
- News sentiment (5 features)

For each specialist bucket, we generate:
1. Bucket-specific symbol features (OHLCV for relevant symbols)
2. Technical indicators (SMA, EMA, RSI, MACD, Bollinger, etc.)
3. Cross-asset spreads and ratios
4. Relevant macro features from FRED/FX/COT
5. Forward-filled to daily frequency

Usage:
    python scripts/generate_specialist_features.py --dry-run
    python scripts/generate_specialist_features.py
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List

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
# CRITICAL: Every specialist bucket gets ALL data, not a subset.
# AutoGluon determines what's relevant. We provide EVERYTHING.
#
# MINIMUM FEATURES PER BUCKET: 800+
#
# If you see fewer features, YOU ARE DOING IT WRONG.
# ═══════════════════════════════════════════════════════════════════════════════
from src.fusion.validation.all_data_policy import (
    enforce_all_data_policy,
    validate_specialist_features,
    log_all_data_summary,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
load_dotenv(".env.vercel")

# =============================================================================
# SPECIALIST BUCKET DEFINITIONS
# =============================================================================
# Each bucket has specific symbols and features it focuses on

SPECIALIST_BUCKETS = {
    "crush": {
        "description": "Soybean complex fundamentals",
        "symbols": ["ZL", "ZM", "ZS", "XK"],  # Soybean oil, meal, beans, Malaysian palm
        "fred_series": ["DCOILWTICO", "DTWEXBGS"],
        "fx_pairs": ["USDBRL", "USDARS"],
        "cot_symbols": ["ZL", "ZS", "ZM"],
    },
    "china": {
        "description": "Chinese import demand",
        "symbols": ["ZS", "ZL", "ZM", "HG", "FEF1"],  # Soybeans + copper/iron as China proxies
        "fred_series": ["DTWEXBGS", "DCOILWTICO"],
        "fx_pairs": ["USDCNY", "USDHKD"],
        "cot_symbols": ["ZS", "ZL"],
    },
    "fx": {
        "description": "Currency effects on trade",
        "symbols": ["ZL", "ZS", "DX", "6E", "6J", "6B"],  # Dollar index, major currencies
        "fred_series": ["DTWEXBGS", "DGS10", "FEDFUNDS"],
        "fx_pairs": ["EURUSD", "USDJPY", "GBPUSD", "USDBRL", "USDCNY"],
        "cot_symbols": ["ZL"],
    },
    "fed": {
        "description": "Monetary policy impacts",
        "symbols": ["ZL", "ES", "ZN", "ZB", "GC"],  # S&P, 10Y, 30Y bond, Gold
        "fred_series": ["FEDFUNDS", "DGS10", "DGS2", "T10Y2Y", "VIXCLS", "DTWEXBGS"],
        "fx_pairs": ["EURUSD", "USDJPY"],
        "cot_symbols": ["ZL"],
    },
    "tariff": {
        "description": "Trade policy impacts",
        "symbols": ["ZL", "ZS", "ZM", "ZC", "ZW"],  # Ag complex
        "fred_series": ["DTWEXBGS"],
        "fx_pairs": ["USDCNY", "USDBRL"],
        "cot_symbols": ["ZL", "ZS"],
    },
    "energy": {
        "description": "Petroleum complex",
        "symbols": ["ZL", "CL", "HO", "RB", "NG"],  # Crude, heating oil, gasoline, natgas
        "fred_series": ["DCOILWTICO", "DCOILBRENTEU"],
        "fx_pairs": ["USDCAD", "USDRUB"],
        "cot_symbols": ["ZL", "CL"],
    },
    "biofuel": {
        "description": "Renewable mandates",
        "symbols": ["ZL", "ZS", "CL", "HO", "RB"],  # Soybean oil + energy
        "fred_series": ["DCOILWTICO"],
        "fx_pairs": [],
        "cot_symbols": ["ZL", "CL"],
        "include_rin": True,
    },
    "palm": {
        "description": "Palm oil complex",
        "symbols": ["ZL", "XK", "ZS"],  # Soybean oil vs palm
        "fred_series": ["DCOILWTICO"],
        "fx_pairs": ["USDMYR", "USDIDR"],
        "cot_symbols": ["ZL"],
    },
    "volatility": {
        "description": "Market stress/fear",
        "symbols": ["ZL", "ES", "VX", "GC", "ZN"],  # S&P, VIX futures, Gold, 10Y
        "fred_series": ["VIXCLS", "DGS10", "T10Y2Y", "TEDRATE"],
        "fx_pairs": ["EURUSD", "USDJPY"],
        "cot_symbols": ["ZL"],
    },
    "substitutes": {
        "description": "Competing vegetable oils",
        "symbols": ["ZL", "XK", "RS", "OJ"],  # Soybean oil, palm, canola, OJ as ag proxy
        "fred_series": [],
        "fx_pairs": ["USDCAD", "EURUSD"],  # Canola from Canada, Rapeseed from EU
        "cot_symbols": ["ZL"],
    },
    # =========================================================================
    # TRUMP SPECIALIST - The 11th Specialist
    # =========================================================================
    # Trump is a REGIME unto itself. Not just tariffs - it's the COMBINATION:
    # - Section 301 tariffs + China retaliation
    # - EPA small refinery waivers (crushed biodiesel demand)
    # - MFP payments (artificial price floor)
    # - Tweet-driven volatility
    # - Policy unpredictability
    #
    # Training uses Trump 1.0 (2017-2021) to predict Trump 2.0 (2025+)
    # =========================================================================
    "trump_effect": {
        "description": "Trump/policy regime dynamics - tariffs, EPA waivers, China trade war, tweets",
        "symbols": ["ZL", "ZS", "ZM", "HG", "ES", "DX"],  # Soy complex + copper (China) + S&P + dollar
        "fred_series": [
            "DTWEXBGS",      # Dollar index
            "DEXCHUS",       # USD/CNY
            "FEDFUNDS",      # Fed funds (Trump pressure on Fed)
            "VIXCLS",        # VIX (uncertainty)
            "T10Y2Y",        # Yield curve
            "PCOPPUSDM",     # Copper (China proxy)
        ],
        "fx_pairs": ["USDCNY", "USDBRL", "USDMXN"],  # China, Brazil (competitor), Mexico (NAFTA)
        "cot_symbols": ["ZL", "ZS"],
        "include_rin": True,  # EPA waiver impact on RINs
        "include_trump_features": True,  # Special Trump regime features
    },
}


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def load_all_market_data(conn, start_date: str = "2000-01-01") -> pd.DataFrame:
    """Load all daily market futures data."""
    logger.info(f"Loading daily market futures >= {start_date}...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT symbol, as_of_date, open, high, low, close, volume
            FROM "raw"."market_futures_1d"
            WHERE as_of_date >= %s
            ORDER BY as_of_date, symbol
        """, (start_date,))
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=columns)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    logger.info(f"  Loaded {len(df):,} rows, {df['symbol'].nunique()} symbols")
    return df


def load_fred_data(conn) -> pd.DataFrame:
    """Load FRED economic data (long format → pivot wide)."""
    logger.info("Loading FRED economic data (long → pivot wide)...")

    # Load long format
    fred_long = pd.read_sql("""
        SELECT as_of_date, series_id, value
        FROM "raw"."fred_observations_1d"
        ORDER BY as_of_date, series_id
    """, conn)
    logger.info(f"  Long format: {len(fred_long):,} rows, {fred_long['series_id'].nunique()} series")

    if fred_long.empty:
        raise ValueError("FRED observations query returned 0 rows - check fred_observations_1d table")

    # Pivot to wide format
    df = (
        fred_long.pivot(index="as_of_date", columns="series_id", values="value")
        .sort_index()
        .reset_index()
    )
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])

    # Warn on high sparsity
    feature_cols = [c for c in df.columns if c != "as_of_date"]
    missing_frac = df[feature_cols].isna().mean().mean()
    if missing_frac > 0.50:
        logger.warning(f"  ⚠️ FRED pivot has high missingness: {missing_frac:.1%}")

    logger.info(f"  Wide format: {len(df):,} rows, {len(feature_cols)} FRED features")
    return df


def load_fx_data(conn) -> pd.DataFrame:
    """Load FX spot data and pivot wide."""
    logger.info("Loading FX spot data...")
    with conn.cursor() as cur:
        cur.execute('SELECT pair, as_of_date, rate FROM "raw"."fx_spot_1d" ORDER BY as_of_date')
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["pair", "as_of_date", "rate"])
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    # Pivot wide
    df_wide = df.pivot_table(index="as_of_date", columns="pair", values="rate", aggfunc="last")
    df_wide.columns = [f"fx_{c}" for c in df_wide.columns]
    df_wide = df_wide.reset_index()
    logger.info(f"  Loaded {len(df_wide):,} dates, {len(df_wide.columns)-1} FX pairs")
    return df_wide


def load_cot_data(conn) -> pd.DataFrame:
    """Load CFTC COT data and pivot wide by symbol."""
    logger.info("Loading CFTC COT data...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT report_date, symbol, open_interest, managed_money_net,
                   managed_money_net_pct_oi, prod_merc_net, prod_merc_net_pct_oi
            FROM "raw"."cftc_cot_1w"
            ORDER BY report_date, symbol
        """)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["as_of_date", "symbol", "oi", "mm_net", "mm_pct", "prod_net", "prod_pct"])
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])

    # Pivot by symbol
    result_dfs = []
    for sym in df["symbol"].unique():
        sym_df = df[df["symbol"] == sym][["as_of_date", "oi", "mm_net", "mm_pct", "prod_net", "prod_pct"]].copy()
        sym_df.columns = ["as_of_date"] + [f"cot_{sym}_{c}" for c in ["oi", "mm_net", "mm_pct", "prod_net", "prod_pct"]]
        result_dfs.append(sym_df)

    if result_dfs:
        cot_wide = result_dfs[0]
        for df_r in result_dfs[1:]:
            cot_wide = cot_wide.merge(df_r, on="as_of_date", how="outer")
    else:
        cot_wide = pd.DataFrame(columns=["as_of_date"])

    logger.info(f"  Loaded {len(cot_wide):,} dates, {len(cot_wide.columns)-1} COT features")
    return cot_wide


def load_usda_exports(conn) -> pd.DataFrame:
    """Load USDA export sales data."""
    logger.info("Loading USDA export sales...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT report_date,
                SUM(CASE WHEN commodity = 'Soybeans' THEN net_sales_mt END) as usda_soy_net_sales,
                SUM(CASE WHEN commodity = 'Soybeans' THEN exports_mt END) as usda_soy_exports,
                SUM(CASE WHEN commodity = 'Soybean Oil' THEN net_sales_mt END) as usda_zl_net_sales,
                SUM(CASE WHEN commodity = 'Soybean Oil' THEN exports_mt END) as usda_zl_exports,
                SUM(CASE WHEN commodity = 'Soybean Meal' THEN net_sales_mt END) as usda_zm_net_sales
            FROM "raw"."usda_export_sales_1w"
            GROUP BY report_date
            ORDER BY report_date
        """)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["as_of_date", "usda_soy_net_sales", "usda_soy_exports",
                                       "usda_zl_net_sales", "usda_zl_exports", "usda_zm_net_sales"])
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    logger.info(f"  Loaded {len(df):,} dates")
    return df


def load_wasde_data(conn) -> pd.DataFrame:
    """Load USDA WASDE data."""
    logger.info("Loading USDA WASDE data...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT report_date,
                SUM(CASE WHEN commodity = 'Soybeans' AND metric = 'production' THEN value END) as wasde_soy_production,
                SUM(CASE WHEN commodity = 'Soybeans' AND metric = 'exports' THEN value END) as wasde_soy_exports,
                SUM(CASE WHEN commodity = 'Soybeans' AND metric = 'ending_stocks' THEN value END) as wasde_soy_stocks,
                SUM(CASE WHEN commodity = 'Soybean Oil' AND metric = 'production' THEN value END) as wasde_zl_production,
                SUM(CASE WHEN commodity = 'Soybean Oil' AND metric = 'exports' THEN value END) as wasde_zl_exports
            FROM "raw"."usda_wasde_1m"
            GROUP BY report_date
            ORDER BY report_date
        """)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["as_of_date", "wasde_soy_production", "wasde_soy_exports",
                                       "wasde_soy_stocks", "wasde_zl_production", "wasde_zl_exports"])
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    logger.info(f"  Loaded {len(df):,} dates")
    return df


def load_rin_data(conn) -> pd.DataFrame:
    """Load EPA RIN data."""
    logger.info("Loading EPA RIN data...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT as_of_date, rin_type, price
            FROM "raw"."epa_rin_prices_1d"
            ORDER BY as_of_date
        """)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["as_of_date", "rin_type", "price"])
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    # Pivot by RIN type
    df_wide = df.pivot_table(index="as_of_date", columns="rin_type", values="price", aggfunc="last")
    df_wide.columns = [f"rin_{c}" for c in df_wide.columns]
    df_wide = df_wide.reset_index()
    logger.info(f"  Loaded {len(df_wide):,} dates, {len(df_wide.columns)-1} RIN types")
    return df_wide


def load_weather_data(conn) -> pd.DataFrame:
    """Load NOAA weather data aggregated by date with expanded variables."""
    logger.info("Loading weather data...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT as_of_date,
                -- Core temperature & precipitation (existing)
                AVG(tavg_c) as weather_tavg_global,
                AVG(prcp_mm) as weather_prcp_global,
                AVG(CASE WHEN country = 'Brazil' THEN tavg_c END) as weather_tavg_brazil,
                AVG(CASE WHEN country = 'Brazil' THEN prcp_mm END) as weather_prcp_brazil,
                AVG(CASE WHEN country = 'United States' THEN tavg_c END) as weather_tavg_us,
                AVG(CASE WHEN country = 'United States' THEN prcp_mm END) as weather_prcp_us,
                AVG(CASE WHEN country = 'Argentina' THEN tavg_c END) as weather_tavg_argentina,
                AVG(CASE WHEN country = 'Argentina' THEN prcp_mm END) as weather_prcp_argentina,
                -- NEW: Expanded weather variables (global aggregates)
                AVG(rhav_pct) as weather_humidity_global,
                AVG(snwd_mm) as weather_snow_depth_global,
                MAX(wsfg_ms) as weather_max_gust_global,
                AVG(evap_mm) as weather_evap_global,
                -- NEW: Regional humidity
                AVG(CASE WHEN country = 'United States' THEN rhav_pct END) as weather_humidity_us,
                AVG(CASE WHEN country = 'Brazil' THEN rhav_pct END) as weather_humidity_brazil
            FROM "raw"."weather_noaa_1d"
            GROUP BY as_of_date
            ORDER BY as_of_date
        """)
        rows = cur.fetchall()

    columns = [
        "as_of_date", "weather_tavg_global", "weather_prcp_global",
        "weather_tavg_brazil", "weather_prcp_brazil",
        "weather_tavg_us", "weather_prcp_us",
        "weather_tavg_argentina", "weather_prcp_argentina",
        # New columns
        "weather_humidity_global", "weather_snow_depth_global",
        "weather_max_gust_global", "weather_evap_global",
        "weather_humidity_us", "weather_humidity_brazil"
    ]
    df = pd.DataFrame(rows, columns=columns)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    logger.info(f"  Loaded {len(df):,} dates with {len(columns)-1} weather features")
    return df


def add_weather_staleness(df: pd.DataFrame, time_col: str = 'as_of_date') -> pd.DataFrame:
    """
    Add *_age_days columns for sparse weather variables.
    Tracks days since last fresh (non-null) observation.
    Must be called BEFORE forward-fill.
    """
    sparse_cols = [
        'weather_humidity_global', 'weather_evap_global',
        'weather_snow_depth_global', 'weather_max_gust_global'
    ]

    t = pd.to_datetime(df[time_col])

    for col in sparse_cols:
        if col not in df.columns:
            continue

        fresh = df[col].notna()
        last_fresh_time = t.where(fresh).ffill()
        age = (t - last_fresh_time).dt.total_seconds() / 86400.0
        df[f'{col}_age_days'] = age.fillna(0.0)

    return df


def load_news_data(conn) -> pd.DataFrame:
    """Load news sentiment data aggregated by date."""
    logger.info("Loading news sentiment...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT as_of_date,
                AVG(sentiment_score) as news_sentiment_avg,
                COUNT(*) as news_article_count,
                SUM(CASE WHEN zl_sentiment = 'bullish' THEN 1 ELSE 0 END) as news_bullish_count,
                SUM(CASE WHEN zl_sentiment = 'bearish' THEN 1 ELSE 0 END) as news_bearish_count,
                SUM(CASE WHEN is_trump_related THEN 1 ELSE 0 END) as news_trump_count
            FROM "raw"."news_articles_1d"
            GROUP BY as_of_date
            ORDER BY as_of_date
        """)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["as_of_date", "news_sentiment_avg", "news_article_count",
                                       "news_bullish_count", "news_bearish_count", "news_trump_count"])
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    logger.info(f"  Loaded {len(df):,} dates")
    return df


def calculate_technical_indicators(df: pd.DataFrame, price_col: str = "close") -> pd.DataFrame:
    """Calculate technical indicators for a price series."""
    result = df.copy()

    # Returns
    result["return_1d"] = result[price_col].pct_change(1)
    result["return_5d"] = result[price_col].pct_change(5)
    result["return_21d"] = result[price_col].pct_change(21)

    # Simple Moving Averages
    result["sma_5"] = result[price_col].rolling(5).mean()
    result["sma_21"] = result[price_col].rolling(21).mean()
    result["sma_63"] = result[price_col].rolling(63).mean()

    # Exponential Moving Averages
    result["ema_12"] = result[price_col].ewm(span=12).mean()
    result["ema_26"] = result[price_col].ewm(span=26).mean()

    # MACD
    result["macd"] = result["ema_12"] - result["ema_26"]
    result["macd_signal"] = result["macd"].ewm(span=9).mean()

    # RSI (14-day)
    delta = result[price_col].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    result["rsi_14"] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    result["bb_middle"] = result[price_col].rolling(20).mean()
    bb_std = result[price_col].rolling(20).std()
    result["bb_upper"] = result["bb_middle"] + 2 * bb_std
    result["bb_lower"] = result["bb_middle"] - 2 * bb_std
    result["bb_pct"] = (result[price_col] - result["bb_lower"]) / (result["bb_upper"] - result["bb_lower"])

    # Volatility
    result["volatility_21d"] = result["return_1d"].rolling(21).std() * np.sqrt(252)

    # Price relative to SMAs
    result["price_vs_sma21"] = result[price_col] / result["sma_21"] - 1
    result["price_vs_sma63"] = result[price_col] / result["sma_63"] - 1

    return result


def add_trump_regime_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add Trump regime-specific features.

    Trump is a REGIME - the combination of policies creates unique dynamics:
    - Section 301 tariffs + China retaliation
    - EPA small refinery waivers (crushed biodiesel demand)
    - MFP payments (artificial price floor)
    - Tweet-driven volatility
    - Policy unpredictability

    Training uses Trump 1.0 (2017-2021) to predict Trump 2.0 (2025+)
    """
    df = df.copy()

    # Convert as_of_date to datetime for comparisons
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])

    # ==========================================================================
    # 1. BINARY FLAGS - Is Trump in office?
    # ==========================================================================
    # Trump 1.0: 2017-01-20 to 2021-01-20
    # Trump 2.0: 2025-01-20 onwards
    trump_1_start = pd.Timestamp("2017-01-20")
    trump_1_end = pd.Timestamp("2021-01-20")
    trump_2_start = pd.Timestamp("2025-01-20")

    df["trump_in_office"] = (
        ((df["as_of_date"] >= trump_1_start) & (df["as_of_date"] < trump_1_end)) |
        (df["as_of_date"] >= trump_2_start)
    ).astype(int)

    # Transition periods (60 days before/after inauguration - heightened uncertainty)
    df["trump_transition"] = (
        ((df["as_of_date"] >= trump_1_start - pd.Timedelta(days=60)) &
         (df["as_of_date"] < trump_1_start + pd.Timedelta(days=60))) |
        ((df["as_of_date"] >= trump_1_end - pd.Timedelta(days=60)) &
         (df["as_of_date"] < trump_1_end + pd.Timedelta(days=60))) |
        ((df["as_of_date"] >= trump_2_start - pd.Timedelta(days=60)) &
         (df["as_of_date"] < trump_2_start + pd.Timedelta(days=60)))
    ).astype(int)

    # ==========================================================================
    # 2. TRADE WAR REGIME FEATURES
    # ==========================================================================
    # Key dates in US-China trade war
    trade_war_start = pd.Timestamp("2018-03-22")  # Section 301 announced
    tariff_implemented = pd.Timestamp("2018-07-06")  # 25% tariff active
    phase_one_deal = pd.Timestamp("2020-01-15")  # Phase One signed

    # China tariff active (25% on US soybeans)
    df["china_tariff_active"] = (
        (df["as_of_date"] >= tariff_implemented) &
        (df["as_of_date"] < phase_one_deal + pd.Timedelta(days=365))
    ).astype(int)

    # Phase One active
    df["phase_one_active"] = (
        (df["as_of_date"] >= phase_one_deal) &
        (df["as_of_date"] < trump_1_end)
    ).astype(int)

    # Days since trade war events (for escalation timeline)
    df["days_since_tariff_announce"] = (df["as_of_date"] - trade_war_start).dt.days
    df["days_since_tariff_announce"] = df["days_since_tariff_announce"].clip(lower=0)

    # Trade war regime score (-5 to +5)
    # -5 = full war, 0 = neutral, +5 = deal
    df["trade_war_regime"] = 0.0
    df.loc[df["as_of_date"] >= trade_war_start, "trade_war_regime"] = -2.0
    df.loc[df["as_of_date"] >= tariff_implemented, "trade_war_regime"] = -4.0
    df.loc[df["as_of_date"] >= pd.Timestamp("2019-08-05"), "trade_war_regime"] = -5.0  # CNY breaks 7
    df.loc[df["as_of_date"] >= pd.Timestamp("2019-10-11"), "trade_war_regime"] = -2.0  # Handshake deal
    df.loc[df["as_of_date"] >= phase_one_deal, "trade_war_regime"] = 3.0
    df.loc[df["as_of_date"] >= trump_1_end, "trade_war_regime"] = 0.0  # Biden: neutral

    # ==========================================================================
    # 3. MFP (Market Facilitation Program) REGIME
    # ==========================================================================
    # MFP payments: 2018 and 2019
    mfp_2018_start = pd.Timestamp("2018-09-04")
    mfp_2019_start = pd.Timestamp("2019-05-23")
    mfp_end = pd.Timestamp("2020-01-15")

    df["mfp_active"] = (
        (df["as_of_date"] >= mfp_2018_start) &
        (df["as_of_date"] < mfp_end)
    ).astype(int)

    # ==========================================================================
    # 4. EPA WAIVER REGIME (Small Refinery Exemptions)
    # ==========================================================================
    # High SRE period: 2017-2020 (Trump EPA)
    df["epa_waiver_regime"] = 0.0
    df.loc[(df["as_of_date"] >= trump_1_start) & (df["as_of_date"] < trump_1_end), "epa_waiver_regime"] = -3.0
    df.loc[(df["as_of_date"] >= pd.Timestamp("2018-01-01")) & (df["as_of_date"] < pd.Timestamp("2019-06-01")), "epa_waiver_regime"] = -5.0  # Peak waivers

    # ==========================================================================
    # 5. ELECTION CYCLE FEATURES
    # ==========================================================================
    # Days to next presidential election
    elections = [
        pd.Timestamp("2016-11-08"),
        pd.Timestamp("2020-11-03"),
        pd.Timestamp("2024-11-05"),
        pd.Timestamp("2028-11-03"),  # Projected
    ]

    def days_to_election(date):
        for elec in elections:
            if date < elec:
                return (elec - date).days
        return 0

    df["days_to_election"] = df["as_of_date"].apply(days_to_election)
    df["election_year"] = df["as_of_date"].dt.year.isin([2016, 2020, 2024, 2028]).astype(int)

    # ==========================================================================
    # 6. TRUMP 2.0 ANTICIPATION (2024 election cycle)
    # ==========================================================================
    # Market pricing in Trump 2.0 risk
    df["trump_2_anticipation"] = 0.0
    df.loc[df["as_of_date"] >= pd.Timestamp("2024-06-01"), "trump_2_anticipation"] = 0.3
    df.loc[df["as_of_date"] >= pd.Timestamp("2024-09-01"), "trump_2_anticipation"] = 0.5
    df.loc[df["as_of_date"] >= pd.Timestamp("2024-11-05"), "trump_2_anticipation"] = 1.0  # Election day

    # ==========================================================================
    # 7. COMPOSITE TRUMP REGIME SCORE
    # ==========================================================================
    # Combine all Trump-related risks into single score
    df["trump_regime_score"] = (
        df["trump_in_office"] * 2 +
        df["china_tariff_active"] * -3 +
        df["phase_one_active"] * 2 +
        df["mfp_active"] * 1 +
        df["epa_waiver_regime"] +
        df["trump_transition"] * 1.5
    )

    # Convert as_of_date back to date for consistency
    df["as_of_date"] = df["as_of_date"].dt.date

    return df


def generate_bucket_features(
    bucket_name: str,
    bucket_config: Dict,
    market_df: pd.DataFrame,
    fred_df: pd.DataFrame,
    fx_df: pd.DataFrame,
    cot_df: pd.DataFrame,
    usda_df: pd.DataFrame,
    wasde_df: pd.DataFrame,
    rin_df: pd.DataFrame,
    weather_df: pd.DataFrame,
    news_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Generate features for a specialist bucket.

    CRITICAL: ALL DATA SOURCES ARE INCLUDED FOR EVERY BUCKET.
    No cherry-picking. AutoGluon will figure out what's relevant.
    """
    logger.info(f"  Generating features for bucket: {bucket_name}")

    # ==========================================================================
    # 1. BASE: Start with ZL as base
    # ==========================================================================
    zl_df = market_df[market_df["symbol"] == "ZL"][["as_of_date", "open", "high", "low", "close", "volume"]].copy()
    zl_df = zl_df.rename(columns={
        "open": "zl_open", "high": "zl_high", "low": "zl_low",
        "close": "zl_close", "volume": "zl_volume"
    })
    zl_df = zl_df.sort_values("as_of_date")

    # Add ZL technical indicators
    zl_tech = calculate_technical_indicators(zl_df.rename(columns={"zl_close": "close"}), "close")
    for col in ["return_1d", "return_5d", "return_21d", "sma_5", "sma_21", "sma_63",
                "ema_12", "ema_26", "macd", "macd_signal", "rsi_14",
                "bb_pct", "volatility_21d", "price_vs_sma21", "price_vs_sma63"]:
        if col in zl_tech.columns:
            zl_df[f"zl_{col}"] = zl_tech[col].values

    # ==========================================================================
    # 2. ADD ALL SYMBOLS (pivot wide)
    # ==========================================================================
    all_symbols = market_df["symbol"].unique()
    for sym in all_symbols:
        if sym == "ZL":
            continue
        sym_df = market_df[market_df["symbol"] == sym][["as_of_date", "open", "high", "low", "close", "volume"]].copy()
        if len(sym_df) > 0:
            sym_lower = sym.lower()
            sym_df = sym_df.rename(columns={
                "open": f"{sym_lower}_open",
                "high": f"{sym_lower}_high",
                "low": f"{sym_lower}_low",
                "close": f"{sym_lower}_close",
                "volume": f"{sym_lower}_volume"
            })
            # Add returns
            sym_df[f"{sym_lower}_return_1d"] = sym_df[f"{sym_lower}_close"].pct_change(1)
            sym_df[f"{sym_lower}_return_5d"] = sym_df[f"{sym_lower}_close"].pct_change(5)
            sym_df[f"{sym_lower}_return_21d"] = sym_df[f"{sym_lower}_close"].pct_change(21)
            zl_df = zl_df.merge(sym_df, on="as_of_date", how="left")

    # Calculate soy complex spreads if available
    if "zm_close" in zl_df.columns and "zs_close" in zl_df.columns:
        zl_df["board_crush"] = zl_df.get("zm_close", 0) * 22 + zl_df["zl_close"] * 11 - zl_df.get("zs_close", 0) * 50
        zl_df["oil_share"] = zl_df["zl_close"] * 11 / (zl_df["zl_close"] * 11 + zl_df.get("zm_close", 0) * 22 + 0.001)
        zl_df["zl_zs_ratio"] = zl_df["zl_close"] / (zl_df.get("zs_close", 1) + 0.001)
        zl_df["zm_zs_ratio"] = zl_df.get("zm_close", 0) / (zl_df.get("zs_close", 1) + 0.001)

    # ==========================================================================
    # 3. ADD ALL FRED (111 features)
    # ==========================================================================
    zl_df = zl_df.merge(fred_df, on="as_of_date", how="left")
    logger.info(f"    + FRED: {len(fred_df.columns)-1} features")

    # ==========================================================================
    # 4. ADD ALL FX (30 pairs)
    # ==========================================================================
    zl_df = zl_df.merge(fx_df, on="as_of_date", how="left")
    logger.info(f"    + FX: {len(fx_df.columns)-1} features")

    # ==========================================================================
    # 5. ADD ALL COT
    # ==========================================================================
    zl_df = zl_df.merge(cot_df, on="as_of_date", how="left")
    logger.info(f"    + COT: {len(cot_df.columns)-1} features")

    # ==========================================================================
    # 6. ADD ALL USDA EXPORTS
    # ==========================================================================
    zl_df = zl_df.merge(usda_df, on="as_of_date", how="left")
    logger.info(f"    + USDA Exports: {len(usda_df.columns)-1} features")

    # ==========================================================================
    # 7. ADD ALL WASDE
    # ==========================================================================
    zl_df = zl_df.merge(wasde_df, on="as_of_date", how="left")
    logger.info(f"    + WASDE: {len(wasde_df.columns)-1} features")

    # ==========================================================================
    # 8. ADD ALL RIN
    # ==========================================================================
    zl_df = zl_df.merge(rin_df, on="as_of_date", how="left")
    logger.info(f"    + RIN: {len(rin_df.columns)-1} features")

    # ==========================================================================
    # 9. ADD ALL WEATHER
    # ==========================================================================
    zl_df = zl_df.merge(weather_df, on="as_of_date", how="left")
    logger.info(f"    + Weather: {len(weather_df.columns)-1} features")

    # ==========================================================================
    # 10. ADD ALL NEWS
    # ==========================================================================
    zl_df = zl_df.merge(news_df, on="as_of_date", how="left")
    logger.info(f"    + News: {len(news_df.columns)-1} features")

    # ==========================================================================
    # 11. ADD TRUMP REGIME FEATURES (for all buckets, but especially "trump_effect")
    # ==========================================================================
    # These are binary and continuous features that capture Trump/policy-specific dynamics
    zl_df = add_trump_regime_features(zl_df)
    logger.info(f"    + Trump/policy regime: added")

    # ==========================================================================
    # ADD STALENESS COLUMNS (before forward-fill)
    # ==========================================================================
    zl_df = add_weather_staleness(zl_df, time_col="as_of_date")
    logger.info(f"    + Weather staleness: added age columns for sparse vars")

    # ==========================================================================
    # FORWARD-FILL AND CLEAN
    # ==========================================================================
    zl_df = zl_df.sort_values("as_of_date")
    zl_df = zl_df.ffill()
    zl_df = zl_df.dropna(subset=["zl_close"])

    feature_cols = [c for c in zl_df.columns if c != "as_of_date"]
    logger.info(f"    TOTAL: {len(zl_df):,} rows with {len(feature_cols)} features")

    return zl_df


def save_specialist_features(conn, bucket: str, df: pd.DataFrame, dry_run: bool = False):
    """Save specialist features to Postgres."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would save {len(df):,} rows for bucket {bucket}")
        return

    # Convert to JSON format for storage
    insert_query = """
        INSERT INTO "training"."specialist_features" (bucket, as_of_date, features)
        VALUES (%s, %s, %s)
        ON CONFLICT (bucket, as_of_date) DO UPDATE SET features = EXCLUDED.features
    """

    batch = []
    feature_cols = [c for c in df.columns if c != "as_of_date"]

    for _, row in df.iterrows():
        features = {col: float(row[col]) if pd.notna(row[col]) else None for col in feature_cols}
        batch.append((bucket, row["as_of_date"], json.dumps(features)))

    with conn.cursor() as cur:
        # Clear existing
        cur.execute('DELETE FROM "training"."specialist_features" WHERE bucket = %s', (bucket,))
        # Insert new
        execute_batch(cur, insert_query, batch, page_size=500)

    conn.commit()
    logger.info(f"  Saved {len(batch):,} rows for bucket {bucket}")


def main():
    parser = argparse.ArgumentParser(description="Generate specialist features from ALL data")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--bucket", type=str, default="all", help="Specific bucket or 'all'")
    parser.add_argument("--start-date", type=str, default="2000-01-01", help="Start date for features")

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("ZINC-FUSION-V15: SPECIALIST FEATURE GENERATION")
    logger.info("=" * 70)
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Start date: {args.start_date}")

    conn = get_postgres_connection()

    try:
        # Load ALL data
        logger.info("\n" + "=" * 70)
        logger.info("LOADING ALL DATA SOURCES")
        logger.info("=" * 70)

        market_df = load_all_market_data(conn, args.start_date)
        fred_df = load_fred_data(conn)
        fx_df = load_fx_data(conn)
        cot_df = load_cot_data(conn)
        usda_df = load_usda_exports(conn)
        wasde_df = load_wasde_data(conn)
        rin_df = load_rin_data(conn)
        weather_df = load_weather_data(conn)
        news_df = load_news_data(conn)

        # Generate features for each bucket
        logger.info("\n" + "=" * 70)
        logger.info("GENERATING SPECIALIST FEATURES")
        logger.info("=" * 70)

        buckets = [args.bucket] if args.bucket != "all" else list(SPECIALIST_BUCKETS.keys())

        for bucket_name in buckets:
            if bucket_name not in SPECIALIST_BUCKETS:
                logger.warning(f"Unknown bucket: {bucket_name}")
                continue

            bucket_config = SPECIALIST_BUCKETS[bucket_name]

            bucket_df = generate_bucket_features(
                bucket_name, bucket_config,
                market_df, fred_df, fx_df, cot_df, usda_df, wasde_df, rin_df, weather_df, news_df
            )

            save_specialist_features(conn, bucket_name, bucket_df, args.dry_run)

        logger.info("\n" + "=" * 70)
        logger.info("SPECIALIST FEATURE GENERATION COMPLETE")
        logger.info("=" * 70)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
