"""
Phase 3: Build Core Feature Matrix
===================================

Assembles training.matrix_1d from ALL source data:
- features.elite_1d (27 elite indicators + OHLCV)
- alt.weather_1d (weather aggregates computed on-the-fly)
- econ.* tables (rates, inflation, labor, activity, vol_indices, commodities, money)
- mkt.fx_1d (FX rates)
- pos.cftc_1w (COT managed money, commercials)
- supply.epa_rin_1d (biofuel RIN prices)
- supply.usda_exports_1w (export sales)
- supply.usda_wasde_1m (WASDE supply/demand balances)

SCHEMA UPDATE 2026-01-23:
- Weather features now computed on-the-fly from alt.weather_1d (dropped features.weather_1d)
- Dropped pos.cftc_cits_1w (100% NULL data)
- Dropped features.options_1d (empty, options pipeline not active)
- Dropped features.news_scored_1d (empty, news scoring not active)

SCHEMA UPDATE 2026-01-22:
- Added supply.* tables (EPA RINs, USDA exports, WASDE)
- Removed 70% coverage filter (AutoGluon handles nulls)
- Removed date window mandates (use all available data)

SCHEMA UPDATE 2026-01-17:
- FRED data migrated from raw.fred_observations_1d to domain-specific econ.* tables
- gold.* renamed to features.* (elite_1d)
- training.core_matrix_curated_1d renamed to training.matrix_1d

Design Principles:
- Blanket inclusion WITH enforced curation (120-350 features)
- All features as OBSERVED covariates (not known)
- RAW features stored (NO global normalization - prevents leakage)
- Normalization happens in Phase 6 PER CV WINDOW (training data only)
- ONE immutable matrix per rebuild
- Target: ~213 features after curation

CRITICAL: This phase stores RAW features. Normalization is NOT done here.
Phase 6 fits scalers on training windows only to prevent future data leakage.
"""

from __future__ import annotations

import logging
import hashlib
from datetime import datetime, date
from typing import Optional, Tuple, List, Dict, Any
from datetime import date, timedelta

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values

from .config import DATABASE_URL, TARGET_SYMBOL, HORIZONS, FeatureMatrixConfig as FMC

logger = logging.getLogger(__name__)


# =============================================================================
# DATE NORMALIZATION HELPER (CRITICAL FIX)
# =============================================================================


def normalize_date_column(df: pd.DataFrame, col: str = "trade_date") -> pd.DataFrame:
    """
    Normalize date column to datetime.date for consistent merging.

    This fixes the silent merge failure where different date types
    (datetime64[ns] vs datetime.date) cause zero matches.

    PATCH: 2026-01-21 - Resolves weather data merge failure
    """
    if col in df.columns and len(df) > 0:
        df[col] = pd.to_datetime(df[col]).dt.date
    return df


def merge_asof_to_trading_days(
    base_df: pd.DataFrame,
    source_df: pd.DataFrame,
    date_col: str = "trade_date",
) -> pd.DataFrame:
    """
    Merge source data to trading days using backward-looking alignment.

    For weekly/monthly data (CFTC, WASDE, USDA exports, RINs, FRED weekly),
    the release date often falls on non-trading days (weekends). This aligns
    each release to the NEXT trading day (first day the info is available).

    Example: ICSA released Saturday 2026-01-17 → aligns to Monday 2026-01-20

    PATCH: 2026-01-23 - Fixes 0% coverage for weekly/monthly data
    """
    if len(source_df) == 0:
        return base_df

    # Ensure both have datetime for merge_asof
    base_df = base_df.copy()
    source_df = source_df.copy()

    base_df["_dt"] = pd.to_datetime(base_df[date_col])
    source_df["_dt"] = pd.to_datetime(source_df[date_col])

    # Sort both by date (required for merge_asof)
    base_df = base_df.sort_values("_dt")
    source_df = source_df.sort_values("_dt")

    # Get columns to merge (exclude date columns)
    merge_cols = [c for c in source_df.columns if c not in [date_col, "_dt"]]

    # merge_asof: for each trading day, find the most recent source row
    # direction='backward' means: use source row with date <= trading day
    merged = pd.merge_asof(
        base_df,
        source_df[["_dt"] + merge_cols],
        on="_dt",
        direction="backward",
    )

    # Clean up
    merged = merged.drop(columns=["_dt"])

    return merged


def load_futures_base(conn, symbol: str) -> pd.DataFrame:
    """Load raw futures data as base - ALL available data, no date limits."""
    logger.info(f"Loading futures base from mkt.futures_1d for {symbol}...")

    # NOTE: open_interest is required by strict specialists; backfilled from CFTC where available.
    query = """
        SELECT
            event_date as trade_date,
            symbol,
            open, high, low, close, volume, open_interest
        FROM mkt.futures_1d
        WHERE symbol = %s
        ORDER BY event_date
    """
    df = pd.read_sql(query, conn, params=(symbol,))
    logger.info(
        f"   Loaded {len(df):,} rows from {df['trade_date'].min()} to {df['trade_date'].max()}"
    )
    return df


def load_lcfs_credit(conn) -> pd.DataFrame:
    """Load LCFS credit prices from supply.lcfs_1d."""
    logger.info("Loading LCFS credit prices from supply.lcfs_1d...")
    try:
        query = """
            SELECT
                event_date as trade_date,
                price_usd_per_mt::float as lcfs_credit
            FROM supply.lcfs_1d
            ORDER BY event_date
        """
        df = pd.read_sql(query, conn)
        if len(df) == 0:
            logger.warning("   No LCFS data found")
            return pd.DataFrame()
        df = normalize_date_column(df, "trade_date")
        logger.info(
            f"   Loaded {len(df):,} rows from {df['trade_date'].min()} to {df['trade_date'].max()}"
        )
        return df
    except Exception as e:
        logger.warning(f"   LCFS data not available: {e}")
        return pd.DataFrame()


def load_china_pmi(conn) -> pd.DataFrame:
    """Load China manufacturing PMI from econ.activity_1d where series_id='china_pmi'."""
    logger.info("Loading China PMI from econ.activity_1d (series_id='china_pmi')...")
    try:
        query = """
            SELECT
                event_date as trade_date,
                value::float as china_pmi
            FROM econ.activity_1d
            WHERE series_id = 'china_pmi'
            ORDER BY event_date
        """
        df = pd.read_sql(query, conn)
        if len(df) == 0:
            logger.warning("   No China PMI data found (series_id='china_pmi')")
            return pd.DataFrame()
        df = normalize_date_column(df, "trade_date")
        logger.info(
            f"   Loaded {len(df):,} rows from {df['trade_date'].min()} to {df['trade_date'].max()}"
        )
        return df
    except Exception as e:
        logger.warning(f"   China PMI not available: {e}")
        return pd.DataFrame()


def load_dalian_soy(conn) -> pd.DataFrame:
    """
    Load Dalian soybean oil futures proxy from mkt.futures_1d.

    Convention:
    - Symbol used for DCE soybean oil continuous proxy: 'DCE_Y'
    - Column exposed to specialists/matrix: dalian_soy
    """
    logger.info(
        "Loading Dalian soybean oil proxy from mkt.futures_1d (symbol='DCE_Y')..."
    )
    try:
        query = """
            SELECT
                event_date as trade_date,
                close::float as dalian_soy
            FROM mkt.futures_1d
            WHERE symbol = 'DCE_Y'
            ORDER BY event_date
        """
        df = pd.read_sql(query, conn)
        if len(df) == 0:
            logger.warning("   No DCE_Y data found in mkt.futures_1d")
            return pd.DataFrame()
        df = normalize_date_column(df, "trade_date")
        logger.info(
            f"   Loaded {len(df):,} rows from {df['trade_date'].min()} to {df['trade_date'].max()}"
        )
        return df
    except Exception as e:
        logger.warning(f"   Dalian soy not available: {e}")
        return pd.DataFrame()


def load_elite_indicators(conn, symbol: str) -> pd.DataFrame:
    """Load features.elite_1d for target symbol."""
    logger.info("Loading elite indicators from features.elite_1d...")

    query = """
        SELECT *
        FROM features.elite_1d
        WHERE symbol = %s
        ORDER BY trade_date
    """
    df = pd.read_sql(query, conn, params=(symbol,))
    logger.info(f"   Loaded {len(df):,} rows, {len(df.columns)} columns")
    return df


def load_fred_macro(conn) -> pd.DataFrame:
    """Load FRED macro series from econ.* tables and pivot to wide format.

    NEW SCHEMA (2026-01-17):
    FRED data is now split across domain-specific tables:
    - econ.rates_1d (interest rates, yields, spreads)
    - econ.inflation_1d (CPI, PCE)
    - econ.labor_1d (payrolls, claims)
    - econ.activity_1d (GDP, industrial production, sentiment)
    - econ.vol_indices_1d (VIX, NFCI)
    - econ.commodities_1d (commodity prices)
    - mkt.fx_1d (FRED FX rates - consolidated, filtered by source='FRED')
    - econ.money_1d (money supply, Fed balance sheet)
    """
    logger.info("Loading FRED macro series from econ.* tables...")

    FMC_INSTANCE = FMC()
    fred_series = list(FMC_INSTANCE.FRED_MACRO_SERIES)
    placeholders = ",".join(["%s"] * len(fred_series))

    # UNION ALL from all econ tables
    # Each table has same structure: series_id, event_date, value
    query = f"""
        WITH all_econ AS (
            SELECT series_id, event_date, value FROM econ.rates_1d
            UNION ALL
            SELECT series_id, event_date, value FROM econ.inflation_1d
            UNION ALL
            SELECT series_id, event_date, value FROM econ.labor_1d
            UNION ALL
            SELECT series_id, event_date, value FROM econ.activity_1d
            UNION ALL
            SELECT series_id, event_date, value FROM econ.vol_indices_1d
            UNION ALL
            SELECT series_id, event_date, value FROM econ.commodities_1d
            UNION ALL
            -- FX consolidated to mkt.fx_1d - map pair back to series_id format
            SELECT
                CASE pair
                    WHEN 'EUR/USD' THEN 'DEXUSEU'
                    WHEN 'USD/JPY' THEN 'DEXJPUS'
                    WHEN 'BRL/USD' THEN 'DEXBZUS'
                    WHEN 'CNY/USD' THEN 'DEXCHUS'
                    WHEN 'MXN/USD' THEN 'DEXMXUS'
                    WHEN 'CAD/USD' THEN 'DEXCAUS'
                    WHEN 'KRW/USD' THEN 'DEXKOUS'
                    WHEN 'INR/USD' THEN 'DEXINUS'
                    WHEN 'TWD/USD' THEN 'DEXTAUS'
                    WHEN 'AUD/USD' THEN 'DEXUSAL'
                    WHEN 'DXY_BROAD' THEN 'DTWEXBGS'
                    WHEN 'DXY_AFE' THEN 'DTWEXAFEGS'
                    WHEN 'DXY_EME' THEN 'DTWEXEMEGS'
                    WHEN 'DXY_MAJOR' THEN 'DTWEXM'
                    ELSE pair
                END as series_id,
                event_date,
                rate as value
            FROM mkt.fx_1d
            WHERE source = 'FRED'
            UNION ALL
            SELECT series_id, event_date, value FROM econ.money_1d
        )
        SELECT DISTINCT ON (series_id, event_date)
            event_date::date as trade_date,
            series_id,
            value
        FROM all_econ
        WHERE series_id IN ({placeholders})
        ORDER BY series_id, event_date
    """

    df = pd.read_sql(query, conn, params=tuple(fred_series))

    # Pivot to wide format
    if len(df) > 0:
        df_wide = df.pivot(index="trade_date", columns="series_id", values="value")

        # CRITICAL FIX (2026-01-23): Forward-fill sparse pivot BEFORE asof merge
        # After pivot, each row only has values for series that released on that date.
        # When merge_asof looks backward, it finds a row but with NaN for other series.
        # Forward-fill ensures each date has last known value for ALL series.
        # This is NOT data leakage - it's reproducing what was known at each date.
        df_wide = df_wide.ffill()

        df_wide = df_wide.reset_index()
        # Prefix column names
        df_wide.columns = ["trade_date"] + [
            f"fred_{col.lower()}" for col in df_wide.columns[1:]
        ]

        # Log sparsity fix
        non_null_before = df.groupby("trade_date")["value"].count().mean()
        logger.info(f"   Loaded {len(df_wide):,} rows, {len(df_wide.columns)-1} series")
        logger.info(
            f"   Applied forward-fill to sparse pivot (avg {non_null_before:.1f} series per row → all)"
        )
        return df_wide

    logger.warning("   No FRED data loaded")
    return pd.DataFrame()


def load_fx_rates(conn) -> pd.DataFrame:
    """Load ALL FX rates from mkt.fx_1d."""
    logger.info("Loading ALL FX rates from mkt.fx_1d...")

    try:
        # Load ALL pairs - no filtering
        query = """
            SELECT
                event_date as trade_date,
                pair,
                rate as fx_rate
            FROM mkt.fx_1d
            ORDER BY trade_date, pair
        """
        df = pd.read_sql(query, conn)

        # Pivot to wide format
        if len(df) > 0:
            df_wide = df.pivot(index="trade_date", columns="pair", values="fx_rate")
            df_wide = df_wide.reset_index()
            df_wide.columns = ["trade_date"] + [
                f"fx_{col.lower().replace('/', '_')}" for col in df_wide.columns[1:]
            ]
            logger.info(
                f"   Loaded {len(df_wide):,} rows, {len(df_wide.columns)-1} pairs"
            )
            return df_wide

    except Exception as e:
        logger.warning(f"   FX rates not available: {e}")

    return pd.DataFrame()


def load_weather_aggregates(conn) -> pd.DataFrame:
    """
    Compute weather features on-the-fly from alt.weather_1d.

    Aggregates raw station data to country level and computes derived features:
    - Basic: tavg, tmin, tmax, prcp, snow per country (AR, BR, US)
    - Derived: GDD, rolling precip sums, temp/precip anomalies, temp volatility
    """
    logger.info("Computing weather features from alt.weather_1d...")

    try:
        # Aggregate raw weather to country-day level with derived features
        query = """
            WITH daily_agg AS (
                SELECT
                    event_date::date as trade_date,
                    CASE
                        WHEN country = 'Argentina' THEN 'ar'
                        WHEN country = 'Brazil' THEN 'br'
                        WHEN country = 'United States' THEN 'us'
                    END as region,
                    AVG(tavg_c) as tavg_c,
                    AVG(tmin_c) as tmin_c,
                    AVG(tmax_c) as tmax_c,
                    SUM(prcp_mm) as prcp_mm,
                    SUM(snow_mm) as snow_mm
                FROM alt.weather_1d
                WHERE country IN ('Argentina', 'Brazil', 'United States')
                GROUP BY event_date, country
            ),
            with_gdd AS (
                SELECT *,
                    GREATEST(0, tavg_c - 10) as gdd_10c
                FROM daily_agg
            ),
            with_rolling AS (
                SELECT *,
                    SUM(gdd_10c) OVER (PARTITION BY region ORDER BY trade_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) as gdd_30d_sum,
                    SUM(prcp_mm) OVER (PARTITION BY region ORDER BY trade_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as prcp_7d_sum,
                    SUM(prcp_mm) OVER (PARTITION BY region ORDER BY trade_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) as prcp_14d_sum,
                    tavg_c - AVG(tavg_c) OVER (PARTITION BY region ORDER BY trade_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) as temp_anom_30d,
                    prcp_mm - AVG(prcp_mm) OVER (PARTITION BY region ORDER BY trade_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) as prcp_anom_30d,
                    STDDEV(tavg_c) OVER (PARTITION BY region ORDER BY trade_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as temp_vol_7d
                FROM with_gdd
            )
            SELECT trade_date, region, tavg_c, tmin_c, tmax_c, prcp_mm, snow_mm,
                   gdd_10c, gdd_30d_sum, prcp_7d_sum, prcp_14d_sum,
                   temp_anom_30d, prcp_anom_30d, temp_vol_7d
            FROM with_rolling
            ORDER BY trade_date, region
        """

        df = pd.read_sql(query, conn)

        if len(df) == 0:
            logger.warning("   No weather data found")
            return pd.DataFrame()

        # Pivot from long to wide format (one row per date, columns per region)
        pivot_cols = [
            "tavg_c",
            "tmin_c",
            "tmax_c",
            "prcp_mm",
            "snow_mm",
            "gdd_10c",
            "gdd_30d_sum",
            "prcp_7d_sum",
            "prcp_14d_sum",
            "temp_anom_30d",
            "prcp_anom_30d",
            "temp_vol_7d",
        ]

        result = df.pivot(index="trade_date", columns="region", values=pivot_cols)

        # Flatten column names: (metric, region) -> wx_{region}_{metric}
        result.columns = [f"wx_{region}_{metric}" for metric, region in result.columns]
        result = result.reset_index()

        # Normalize date type for merge compatibility
        result = normalize_date_column(result, "trade_date")

        # Log coverage statistics
        null_pct = (
            result.drop(columns=["trade_date"], errors="ignore").isnull().mean().mean()
            * 100
        )
        logger.info(
            f"   Computed {len(result):,} rows, {len(result.columns)-1} weather features"
        )
        logger.info(f"   Average null percentage: {null_pct:.1f}%")
        return result

    except Exception as e:
        logger.warning(f"   Weather data not available: {e}")

    return pd.DataFrame()


# =============================================================================
# CFTC POSITIONING DATA (NEW - 2026-01-21)
# =============================================================================


def load_cftc_positioning(conn, symbol: str = "ZL") -> pd.DataFrame:
    """
    Load CFTC COT positioning data for soybean oil.

    NEW (2026-01-21): Adds managed money and commercial positioning signals.

    Key features:
    - cot_managed_money_net: Speculator net position (contrarian indicator)
    - cot_prod_merc_net: Commercial hedger net (informed money)
    - cot_open_interest: Total market participation
    - cot_mm_pct_oi: Managed money as % of open interest

    Args:
        conn: Database connection
        symbol: Target symbol (ZL for soybean oil)

    Returns:
        DataFrame with trade_date and COT features
    """
    logger.info("Loading CFTC COT positioning from pos.cftc_1w...")

    try:
        # pos.cftc_1w uses symbol directly (ZL, ZS, ZM, etc.)
        # It already has managed_money_net and prod_merc_net computed
        query = """
            SELECT
                event_date as trade_date,
                managed_money_net as cot_managed_money_net,
                prod_merc_net as cot_prod_merc_net,
                open_interest as cot_open_interest,
                managed_money_net_pct_oi as cot_mm_pct_oi
            FROM pos.cftc_1w
            WHERE symbol = %s
            ORDER BY event_date
        """
        df = pd.read_sql(query, conn, params=(symbol,))

        if len(df) > 0:
            # Commercials as percentage of open interest
            df["cot_comm_pct_oi"] = np.where(
                df["cot_open_interest"] > 0,
                df["cot_prod_merc_net"] / df["cot_open_interest"] * 100,
                0,
            )

            # Changes (week-over-week)
            df["cot_mm_net_chg"] = df["cot_managed_money_net"].diff()
            df["cot_comm_net_chg"] = df["cot_prod_merc_net"].diff()

            # Keep only relevant columns
            keep_cols = [
                "trade_date",
                "cot_managed_money_net",
                "cot_prod_merc_net",
                "cot_open_interest",
                "cot_mm_pct_oi",
                "cot_comm_pct_oi",
                "cot_mm_net_chg",
                "cot_comm_net_chg",
            ]
            df = df[keep_cols]

            # Normalize date type
            df = normalize_date_column(df, "trade_date")

            logger.info(f"   Loaded {len(df):,} rows, {len(df.columns)-1} COT features")
            logger.info(
                f"   Date range: {df['trade_date'].min()} to {df['trade_date'].max()}"
            )
            return df
        else:
            logger.warning(f"   No CFTC COT data found for {symbol}")

    except Exception as e:
        logger.warning(f"   CFTC COT data not available: {e}")

    return pd.DataFrame()


def load_cftc_cits(conn) -> pd.DataFrame:
    """
    Load CFTC CITS (Commodity Index Trader) positions if available.

    NEW (2026-01-21): Index fund flows as a separate signal.
    """
    logger.info("Loading CFTC CITS (index traders) if available...")

    try:
        # Check if cits table exists
        check_query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'pos' AND table_name = 'cftc_cits_1w'
            )
        """
        with conn.cursor() as cur:
            cur.execute(check_query)
            exists = cur.fetchone()[0]

        if not exists:
            logger.info("   pos.cftc_cits_1w table not found - skipping CITS")
            return pd.DataFrame()

        query = """
            SELECT
                event_date as trade_date,
                cit_long,
                cit_short,
                cit_net as cits_net_position,
                cit_pct_oi as cits_pct_oi
            FROM pos.cftc_cits_1w
            WHERE symbol = 'SOYBEAN_OIL'
            ORDER BY event_date
        """
        df = pd.read_sql(query, conn)

        if len(df) > 0:
            # Change in net position
            df["cits_net_chg"] = df["cits_net_position"].diff()

            # Long/short ratio
            df["cits_long_short_ratio"] = np.where(
                df["cit_short"] > 0, df["cit_long"] / df["cit_short"], 1.0
            )

            # Keep only relevant columns
            keep_cols = [
                "trade_date",
                "cits_net_position",
                "cits_pct_oi",
                "cits_net_chg",
                "cits_long_short_ratio",
            ]
            df = df[keep_cols]

            df = normalize_date_column(df, "trade_date")
            logger.info(
                f"   Loaded {len(df):,} rows, {len(df.columns)-1} CITS features"
            )
            return df
        else:
            logger.warning("   No CITS data found for ZL")

    except Exception as e:
        logger.warning(f"   CFTC CITS data not available: {e}")

    return pd.DataFrame()


# =============================================================================
# SUPPLY DATA (NEW - 2026-01-22)
# =============================================================================


def load_epa_rin_prices(conn) -> pd.DataFrame:
    """
    Load EPA RIN prices from supply.epa_rin_1d.

    NEW (2026-01-22): Biofuel RIN prices are critical for soybean oil demand.

    Key features:
    - rin_d3: Cellulosic biofuel RINs
    - rin_d4: Biodiesel/renewable diesel RINs (most relevant for ZL)
    - rin_d5: Advanced biofuel RINs
    - rin_d6: Conventional biofuel (ethanol) RINs

    Returns:
        DataFrame with trade_date and RIN price columns
    """
    logger.info("Loading EPA RIN prices from supply.epa_rin_1d...")

    try:
        query = """
            SELECT
                event_date as trade_date,
                rin_type,
                price
            FROM supply.epa_rin_1d
            ORDER BY event_date, rin_type
        """
        df = pd.read_sql(query, conn)

        if len(df) == 0:
            logger.warning("   No EPA RIN data found")
            return pd.DataFrame()

        # Pivot to wide format (one column per RIN type)
        df_wide = df.pivot(index="trade_date", columns="rin_type", values="price")
        df_wide = df_wide.reset_index()
        df_wide.columns = ["trade_date"] + [
            f"rin_{col.lower()}" for col in df_wide.columns[1:]
        ]

        df_wide = normalize_date_column(df_wide, "trade_date")
        logger.info(
            f"   Loaded {len(df_wide):,} rows, {len(df_wide.columns)-1} RIN types"
        )
        logger.info(
            f"   Date range: {df_wide['trade_date'].min()} to {df_wide['trade_date'].max()}"
        )
        return df_wide

    except Exception as e:
        logger.warning(f"   EPA RIN data not available: {e}")
        return pd.DataFrame()


def load_usda_exports(conn) -> pd.DataFrame:
    """
    Load USDA export sales from supply.usda_exports_1w.

    NEW (2026-01-22): Export demand signals for soybean complex.

    Key features:
    - usda_zl_exports: Soybean oil total exports (MT)
    - usda_zl_net_sales: Soybean oil net sales (MT)
    - usda_zl_outstanding: Soybean oil outstanding sales
    - usda_zs_exports: Soybeans total exports
    - usda_zm_exports: Soybean meal total exports

    Returns:
        DataFrame with trade_date and export columns
    """
    logger.info("Loading USDA export sales from supply.usda_exports_1w...")

    try:
        # Get totals for soybean complex commodities
        query = """
            SELECT
                event_date as trade_date,
                commodity,
                SUM(net_sales_mt) as net_sales_mt,
                SUM(exports_mt) as exports_mt,
                SUM(outstanding_sales_mt) as outstanding_mt
            FROM supply.usda_exports_1w
            WHERE destination_country = 'TOTAL'
            AND commodity IN ('Soybean Oil', 'Soybeans', 'Soybean Meal')
            GROUP BY event_date, commodity
            ORDER BY event_date, commodity
        """
        df = pd.read_sql(query, conn)

        if len(df) == 0:
            logger.warning("   No USDA export data found")
            return pd.DataFrame()

        # Create columns for each commodity
        result_dfs = []
        for commodity, prefix in [
            ("Soybean Oil", "usda_zl"),
            ("Soybeans", "usda_zs"),
            ("Soybean Meal", "usda_zm"),
        ]:
            df_comm = df[df["commodity"] == commodity].copy()
            if len(df_comm) > 0:
                df_comm = df_comm.rename(
                    columns={
                        "exports_mt": f"{prefix}_exports",
                        "net_sales_mt": f"{prefix}_net_sales",
                        "outstanding_mt": f"{prefix}_outstanding",
                    }
                )
                df_comm = df_comm[
                    [
                        "trade_date",
                        f"{prefix}_exports",
                        f"{prefix}_net_sales",
                        f"{prefix}_outstanding",
                    ]
                ]
                result_dfs.append(df_comm)

        if not result_dfs:
            return pd.DataFrame()

        # Merge all commodities
        result = result_dfs[0]
        for df_add in result_dfs[1:]:
            result = result.merge(df_add, on="trade_date", how="outer")

        result = normalize_date_column(result, "trade_date")
        logger.info(
            f"   Loaded {len(result):,} rows, {len(result.columns)-1} export columns"
        )
        return result

    except Exception as e:
        logger.warning(f"   USDA export data not available: {e}")
        return pd.DataFrame()


def load_usda_wasde(conn) -> pd.DataFrame:
    """
    Load USDA WASDE supply/demand balances from supply.usda_wasde_1m.

    NEW (2026-01-22): Fundamental supply/demand data - THE key driver.

    Key features:
    - wasde_us_zs_production: US soybean production
    - wasde_us_zs_crush: US soybean crush
    - wasde_us_zs_stocks: US ending stocks
    - wasde_us_zl_production: US soybean oil production
    - wasde_world_zs_stocks_to_use: World stocks-to-use ratio

    Returns:
        DataFrame with trade_date and WASDE columns
    """
    logger.info("Loading USDA WASDE from supply.usda_wasde_1m...")

    try:
        # Get key US metrics for soybean complex
        query = """
            SELECT
                event_date as trade_date,
                commodity,
                country,
                metric,
                value
            FROM supply.usda_wasde_1m
            WHERE commodity IN ('Soybeans', 'Soybean Oil', 'Soybean Meal')
            AND country IN ('United States', 'World')
            AND metric IN ('production', 'consumption', 'exports', 'ending_stocks', 'crush')
            ORDER BY event_date
        """
        df = pd.read_sql(query, conn)

        if len(df) == 0:
            logger.warning("   No USDA WASDE data found")
            return pd.DataFrame()

        # Create composite key for pivoting
        df["col_name"] = (
            "wasde_"
            + df["country"].str.lower().str.replace(" ", "_")
            + "_"
            + df["commodity"]
            .str.lower()
            .str.replace(" ", "_")
            .str.replace("soybean_", "z")
            + "_"
            + df["metric"]
        )

        # Simplify column names
        df["col_name"] = df["col_name"].str.replace("united_states", "us")
        df["col_name"] = df["col_name"].str.replace("soybeans", "zs")
        df["col_name"] = df["col_name"].str.replace("oil", "l")
        df["col_name"] = df["col_name"].str.replace("meal", "m")

        # Pivot to wide format
        df_wide = df.pivot(index="trade_date", columns="col_name", values="value")
        df_wide = df_wide.reset_index()

        df_wide = normalize_date_column(df_wide, "trade_date")
        logger.info(
            f"   Loaded {len(df_wide):,} rows, {len(df_wide.columns)-1} WASDE columns"
        )
        return df_wide

    except Exception as e:
        logger.warning(f"   USDA WASDE data not available: {e}")
        return pd.DataFrame()


def load_news_sentiment(conn) -> pd.DataFrame:
    """
    Load news sentiment from alt.news_1d.

    NEW (2026-01-23): News sentiment is a key driver of short-term moves.

    Features:
    - news_sentiment: Average sentiment score
    - news_zl_sentiment: ZL-specific sentiment
    - news_count: Number of articles
    - news_trump_pct: % of articles that are Trump-related
    """
    logger.info("Loading news sentiment from alt.news_1d...")

    try:
        query = """
            SELECT
                event_date as trade_date,
                AVG(sentiment_score::float) as news_sentiment,
                AVG(zl_sentiment::float) as news_zl_sentiment,
                COUNT(*) as news_count,
                AVG(CASE WHEN is_trump_related THEN 1.0 ELSE 0.0 END) as news_trump_pct
            FROM alt.news_1d
            GROUP BY event_date
            ORDER BY event_date
        """
        df = pd.read_sql(query, conn)

        if len(df) > 0:
            df = normalize_date_column(df, "trade_date")
            logger.info(
                f"   Loaded {len(df):,} rows, {len(df.columns)-1} news features"
            )
            return df
        else:
            logger.warning("   No news data found")
            return pd.DataFrame()

    except Exception as e:
        logger.warning(f"   News data not available: {e}")
        return pd.DataFrame()


def load_specialist_signals(conn, include_signals: bool = True) -> pd.DataFrame:
    """
    Load specialist signals from training.specialist_signals_1d.

    NEW v3 ARCHITECTURE (2026-01-21):
    Specialist signals are compact (1-2 values per date) and feed into Core
    as input features. This replaces the old 44-model stacking approach.

    Signal columns added:
    - sig_{bucket}_1: Primary signal
    - sig_{bucket}_2: Secondary signal (if present)
    - sig_{bucket}_conf: Model confidence

    Args:
        conn: Database connection
        include_signals: If False, returns empty DataFrame (for ablation testing)

    Returns:
        DataFrame with trade_date and signal columns
    """
    if not include_signals:
        logger.info("Specialist signals disabled (include_signals=False)")
        return pd.DataFrame()

    logger.info("Loading specialist signals from training.specialist_signals_1d...")

    try:
        query = """
            SELECT
                as_of_date as trade_date,
                bucket,
                signal_1,
                signal_2,
                confidence
            FROM training.specialist_signals_1d
            ORDER BY as_of_date, bucket
        """
        df = pd.read_sql(query, conn)

        if len(df) == 0:
            logger.warning("   No specialist signals found - table may be empty")
            return pd.DataFrame()

        # Pivot to wide format
        # Each bucket becomes columns: sig_{bucket}_1, sig_{bucket}_2, sig_{bucket}_conf
        df["trade_date"] = pd.to_datetime(df["trade_date"])

        # Pivot signal_1
        pivot_1 = df.pivot(index="trade_date", columns="bucket", values="signal_1")
        pivot_1.columns = [f"sig_{col}_1" for col in pivot_1.columns]

        # Pivot signal_2
        pivot_2 = df.pivot(index="trade_date", columns="bucket", values="signal_2")
        pivot_2.columns = [f"sig_{col}_2" for col in pivot_2.columns]

        # Pivot confidence
        pivot_conf = df.pivot(index="trade_date", columns="bucket", values="confidence")
        pivot_conf.columns = [f"sig_{col}_conf" for col in pivot_conf.columns]

        # Combine all pivots
        result = pivot_1.join(pivot_2).join(pivot_conf).reset_index()

        # Ensure trade_date is datetime for consistent merging
        result["trade_date"] = pd.to_datetime(result["trade_date"]).dt.date

        # Count non-null signal columns
        signal_cols = [c for c in result.columns if c.startswith("sig_")]
        logger.info(
            f"   Loaded {len(result):,} rows, {len(signal_cols)} signal columns"
        )
        logger.info(f"   Buckets: {df['bucket'].unique().tolist()}")

        return result

    except Exception as e:
        logger.warning(f"   Specialist signals not available: {e}")
        logger.warning("   Run scripts/generate_specialist_signals.py to populate")
        return pd.DataFrame()


def validate_specialist_signals_for_core(
    signals_df: pd.DataFrame,
    conn,
) -> Dict[str, Any]:
    """
    Task 4.5: Validate specialist signals before Core training integration.

    Checks:
    1. Coverage: ≥90% daily rows per bucket (last 180 days)
    2. Signal columns exist in matrix
    3. No excessive null rates
    4. Recent signal availability

    Args:
        signals_df: DataFrame with specialist signals (from load_specialist_signals)
        conn: Database connection for additional queries

    Returns:
        Dict with validation results and issues list
    """
    from fusion.specialists.base import SPECIALIST_BUCKETS

    issues = []
    coverage_by_bucket = {}

    if signals_df.empty:
        issues.append("No specialist signals loaded")
        return {
            "valid": False,
            "issues": issues,
            "coverage_by_bucket": {},
        }

    # Get expected trading days (last 180 days)
    expected_rows_query = """
    SELECT COUNT(DISTINCT event_date) as n_days
    FROM mkt.futures_1d
    WHERE symbol = 'ZL'
      AND event_date >= CURRENT_DATE - INTERVAL '180 days'
    """
    expected_rows = pd.read_sql(expected_rows_query, conn).iloc[0]["n_days"]

    # Check coverage per bucket
    signal_cols = [
        c for c in signals_df.columns if c.startswith("sig_") and c.endswith("_1")
    ]

    for bucket in SPECIALIST_BUCKETS:
        sig_col = f"sig_{bucket}_1"

        if sig_col not in signals_df.columns:
            issues.append(f"{bucket}: signal column missing")
            coverage_by_bucket[bucket] = 0.0
            continue

        # Count non-null signals in recent period
        cutoff_date = date.today() - timedelta(days=180)
        recent_signals = signals_df[
            (pd.to_datetime(signals_df["trade_date"]).dt.date >= cutoff_date)
            & signals_df[sig_col].notna()
        ]
        n_signals = len(recent_signals)
        coverage = n_signals / expected_rows if expected_rows > 0 else 0.0

        coverage_by_bucket[bucket] = coverage

        if coverage < 0.90:
            issues.append(
                f"{bucket}: coverage {coverage*100:.1f}% < 90% ({n_signals}/{expected_rows} days)"
            )

    # Check for missing buckets
    present_buckets = {col.replace("sig_", "").replace("_1", "") for col in signal_cols}
    missing_buckets = set(SPECIALIST_BUCKETS) - present_buckets
    if missing_buckets:
        issues.append(f"Missing buckets: {', '.join(sorted(missing_buckets))}")

    # Check null rates in recent data
    recent_cutoff = date.today() - timedelta(days=30)
    recent_df = signals_df[
        pd.to_datetime(signals_df["trade_date"]).dt.date >= recent_cutoff
    ]
    if len(recent_df) > 0:
        for sig_col in signal_cols:
            null_rate = recent_df[sig_col].isna().mean()
            if null_rate > 0.50:  # More than 50% null in last 30 days
                bucket = sig_col.replace("sig_", "").replace("_1", "")
                issues.append(f"{bucket}: {null_rate*100:.1f}% null in last 30 days")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "coverage_by_bucket": coverage_by_bucket,
    }


def create_target_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Create forward returns as training targets (for supervised OOF)."""
    logger.info("Creating target columns...")

    for horizon in HORIZONS:
        target_col = f"target_ret_{horizon}d"
        df[target_col] = df["close"].pct_change(horizon).shift(-horizon)
        logger.info(f"   Created {target_col}")

    return df


def zscore_normalize(df: pd.DataFrame, exclude_cols: List[str]) -> pd.DataFrame:
    """
    DEPRECATED - DO NOT USE

    This function was previously used to normalize the entire dataset globally.
    This causes FUTURE DATA LEAKAGE because mean/std are computed on all data
    including future rows that wouldn't be available at training time.

    Normalization now happens in Phase 6, PER CV WINDOW, fitting only on
    training data before cutoff_date.

    This function is retained only for reference. It should NEVER be called.
    """
    raise RuntimeError(
        "zscore_normalize() is DEPRECATED. "
        "Global normalization causes future data leakage. "
        "Normalization must happen in Phase 6 per CV window."
    )


def drop_low_coverage_cols(df: pd.DataFrame, min_coverage: float = 0.7) -> pd.DataFrame:
    """Drop columns with too many nulls."""
    logger.info(f"Dropping columns with <{min_coverage*100:.0f}% coverage...")

    before_cols = len(df.columns)
    coverage = df.notna().mean()
    keep_cols = coverage[coverage >= min_coverage].index.tolist()
    df = df[keep_cols]
    dropped = before_cols - len(df.columns)

    logger.info(f"   Dropped {dropped} columns, kept {len(df.columns)}")
    return df


def enforce_feature_guardrails(df: pd.DataFrame) -> Tuple[pd.DataFrame, bool]:
    """
    Enforce 120-350 feature guardrail.

    Returns:
        (df, passed): DataFrame and whether guardrail passed
    """
    FMC_INSTANCE = FMC()

    exclude_cols = {"trade_date", "symbol", "item_id", "timestamp"} | {
        f"target_ret_{h}d" for h in HORIZONS
    }

    feature_cols = [c for c in df.columns if c not in exclude_cols]
    feature_count = len(feature_cols)

    logger.info(f"Feature count: {feature_count}")
    logger.info(f"   Min allowed: {FMC_INSTANCE.MIN_FEATURES}")
    logger.info(f"   Max allowed: {FMC_INSTANCE.MAX_FEATURES}")
    logger.info(f"   Target: {FMC_INSTANCE.TARGET_FEATURES}")

    passed = FMC_INSTANCE.MIN_FEATURES <= feature_count <= FMC_INSTANCE.MAX_FEATURES

    if passed:
        logger.info(f"✅ Feature count {feature_count} within guardrails")
    else:
        logger.error(
            f"❌ Feature count {feature_count} OUTSIDE guardrails [{FMC_INSTANCE.MIN_FEATURES}, {FMC_INSTANCE.MAX_FEATURES}]"
        )
        logger.error("   HARD FAIL - Phase 5 will also catch this")

    return df, passed


def write_matrix(conn, df: pd.DataFrame, matrix_version: str) -> int:
    """Write matrix to training.matrix_1d."""
    logger.info("Writing to training.matrix_1d...")

    # Add metadata columns first (before table creation)
    df["matrix_version"] = matrix_version
    df["created_at"] = datetime.utcnow()

    # Always drop and recreate to ensure schema matches
    # This table is rebuilt from scratch each time (immutable rebuild pattern)
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS training.matrix_1d CASCADE")
        logger.info("   Dropped existing table (clean rebuild)")

    # Create table dynamically based on DataFrame columns
    logger.info("   Creating training.matrix_1d table...")
    create_table_from_df(conn, df, "training", "matrix_1d", matrix_version)

    # Insert rows
    cols = list(df.columns)
    insert_sql = f"""
        INSERT INTO training.matrix_1d ({','.join(cols)})
        VALUES %s
    """

    values = [tuple(row) for row in df.itertuples(index=False, name=None)]

    with conn.cursor() as cur:
        execute_values(cur, insert_sql, values, page_size=1000)

    conn.commit()
    logger.info(f"   Inserted {len(df):,} rows")

    return len(df)


def create_table_from_df(conn, df: pd.DataFrame, schema: str, table: str, version: str):
    """Create table dynamically from DataFrame structure."""

    dtype_map = {
        "int64": "BIGINT",
        "int32": "INTEGER",
        "float64": "DOUBLE PRECISION",
        "float32": "REAL",
        "bool": "BOOLEAN",
        "datetime64[ns]": "TIMESTAMP",
        "object": "TEXT",
    }

    col_defs = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        sql_type = dtype_map.get(dtype, "TEXT")

        if col == "trade_date":
            col_defs.append(f'"{col}" DATE NOT NULL')
        elif col == "symbol":
            col_defs.append(f'"{col}" VARCHAR(20) NOT NULL')
        else:
            col_defs.append(f'"{col}" {sql_type}')

    create_sql = f"""
        CREATE TABLE IF NOT EXISTS {schema}.{table} (
            {','.join(col_defs)},
            PRIMARY KEY (trade_date, symbol)
        )
    """

    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()

    logger.info(f"   Created table {schema}.{table}")


def compute_matrix_version(df: pd.DataFrame) -> str:
    """Compute hash of matrix for lineage tracking."""
    content = (
        f"{len(df)}_{len(df.columns)}_{df['trade_date'].min()}_{df['trade_date'].max()}"
    )
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def run(symbol: str = TARGET_SYMBOL) -> Tuple[bool, Optional[str], int]:
    """
    Execute Phase 3: Build Core Feature Matrix.

    PATCHED 2026-01-22:
    - Added supply.* tables (EPA RINs, USDA exports, WASDE)
    - Removed 70% coverage filter (AutoGluon handles nulls natively)
    - Removed date window mandates (use all available data)

    PATCHED 2026-01-21:
    - Fixed weather data merge (date type normalization)
    - Added CFTC COT positioning data
    - Added CFTC CITS index trader data

    Returns:
        (success: bool, matrix_version: Optional[str], feature_count: int)
    """
    logger.info("=" * 70)
    logger.info("PHASE 3: BUILD CORE FEATURE MATRIX (ALL SOURCE DATA)")
    logger.info("=" * 70)
    logger.info(f"Symbol: {symbol}")
    logger.info(
        f"Target features: {FMC.TARGET_FEATURES} (guardrails: {FMC.MIN_FEATURES}-{FMC.MAX_FEATURES})"
    )
    logger.info(
        "Sources: elite, options, FRED, FX, weather, CFTC, RINs, exports, WASDE"
    )
    logger.info("=" * 70)

    try:
        conn = psycopg2.connect(DATABASE_URL)
        logger.info("✅ Database connected")

        # Load ALL source tables - NO DATE LIMITS
        df_futures = load_futures_base(conn, symbol)
        df_elite = load_elite_indicators(conn, symbol)
        df_fred = load_fred_macro(conn)
        df_fx = load_fx_rates(conn)
        df_weather = load_weather_aggregates(conn)
        df_cot = load_cftc_positioning(conn, symbol)
        df_cits = load_cftc_cits(conn)
        df_rin = load_epa_rin_prices(conn)
        df_lcfs = load_lcfs_credit(conn)
        df_exports = load_usda_exports(conn)
        df_wasde = load_usda_wasde(conn)
        df_china_pmi = load_china_pmi(conn)
        df_dalian = load_dalian_soy(conn)
        df_news = load_news_sentiment(conn)

        # FUTURES AS BASE - ALL DATA
        df = df_futures.copy()
        df = normalize_date_column(df, "trade_date")
        logger.info(
            f"Base: {len(df):,} rows from futures ({df['trade_date'].min()} to {df['trade_date'].max()})"
        )

        # Merge elite indicators
        if len(df_elite) > 0:
            logger.info("Merging elite indicators...")
            df_elite = normalize_date_column(df_elite, "trade_date")
            elite_cols = [
                c
                for c in df_elite.columns
                if c not in ["symbol", "id", "open", "high", "low", "close", "volume"]
            ]
            before_cols = len(df.columns)
            df = df.merge(df_elite[elite_cols], on="trade_date", how="left")
            logger.info(f"   Added {len(df.columns) - before_cols} elite columns")

        # Merge FRED macro (MIXED FREQUENCY - use asof merge for weekly/monthly series)
        if len(df_fred) > 0:
            logger.info("Merging FRED macro (asof for mixed frequencies)...")
            df_fred = normalize_date_column(df_fred, "trade_date")
            before_cols = len(df.columns)
            df = merge_asof_to_trading_days(df, df_fred)
            fred_cols = [c for c in df.columns if c.startswith("fred_")]
            non_null = df[fred_cols].notna().any(axis=1).sum() if fred_cols else 0
            logger.info(f"   Added {len(df.columns) - before_cols} FRED columns")
            logger.info(f"   FRED matched on {non_null:,} / {len(df):,} rows")

            # Map FRED series to cleaner substitute oil column names
            if "fred_proilusdm" in df.columns:
                df["rapeseed_close"] = df["fred_proilusdm"]
                logger.info("   Mapped fred_proilusdm → rapeseed_close")
            if "fred_psunousdm" in df.columns:
                df["sunflower_close"] = df["fred_psunousdm"]
                logger.info("   Mapped fred_psunousdm → sunflower_close")
            if "fred_dexchus" in df.columns and "usd_cny" not in df.columns:
                df["usd_cny"] = df["fred_dexchus"]
                logger.info("   Mapped fred_dexchus → usd_cny")

        # Merge FX rates
        if len(df_fx) > 0:
            logger.info("Merging FX rates...")
            df_fx = normalize_date_column(df_fx, "trade_date")
            before_cols = len(df.columns)
            df = df.merge(df_fx, on="trade_date", how="left")
            logger.info(f"   Added {len(df.columns) - before_cols} FX columns")

        # Merge weather (FIXED - date normalized in loader)
        if len(df_weather) > 0:
            logger.info("Merging weather aggregates (FIXED)...")
            before_cols = len(df.columns)
            before_rows = len(df)
            df = df.merge(df_weather, on="trade_date", how="left")
            wx_cols = [c for c in df.columns if c.startswith("wx_")]
            non_null = df[wx_cols].notna().any(axis=1).sum() if wx_cols else 0
            logger.info(f"   Added {len(df.columns) - before_cols} weather columns")
            logger.info(f"   Weather matched on {non_null:,} / {len(df):,} rows")
            if non_null == 0:
                logger.error("   ❌ WEATHER MERGE STILL FAILING")

        # Merge CFTC COT positioning (WEEKLY - use asof merge)
        if len(df_cot) > 0:
            logger.info("Merging CFTC COT positioning (asof)...")
            before_cols = len(df.columns)
            df = merge_asof_to_trading_days(df, df_cot)
            cot_cols = [c for c in df.columns if c.startswith("cot_")]
            non_null = df[cot_cols].notna().any(axis=1).sum() if cot_cols else 0
            logger.info(f"   Added {len(df.columns) - before_cols} COT columns")
            logger.info(f"   COT matched on {non_null:,} / {len(df):,} rows")

        # Merge CFTC CITS (WEEKLY - use asof merge)
        if len(df_cits) > 0:
            logger.info("Merging CFTC CITS index traders (asof)...")
            before_cols = len(df.columns)
            df = merge_asof_to_trading_days(df, df_cits)
            logger.info(f"   Added {len(df.columns) - before_cols} CITS columns")

        # Merge EPA RIN prices (WEEKLY - use asof merge)
        if len(df_rin) > 0:
            logger.info("Merging EPA RIN prices (asof)...")
            before_cols = len(df.columns)
            df = merge_asof_to_trading_days(df, df_rin)
            rin_cols = [c for c in df.columns if c.startswith("rin_")]
            non_null = df[rin_cols].notna().any(axis=1).sum() if rin_cols else 0
            logger.info(f"   Added {len(df.columns) - before_cols} RIN columns")
            logger.info(f"   RIN matched on {non_null:,} / {len(df):,} rows")

        # Merge LCFS credit (WEEKLY/DISCRETE - use asof merge)
        if len(df_lcfs) > 0:
            logger.info("Merging LCFS credit prices (asof)...")
            before_cols = len(df.columns)
            df = merge_asof_to_trading_days(df, df_lcfs)
            logger.info(f"   Added {len(df.columns) - before_cols} LCFS columns")

        # Merge USDA export sales (WEEKLY - use asof merge)
        if len(df_exports) > 0:
            logger.info("Merging USDA export sales (asof)...")
            before_cols = len(df.columns)
            df = merge_asof_to_trading_days(df, df_exports)
            usda_cols = [c for c in df.columns if c.startswith("usda_")]
            non_null = df[usda_cols].notna().any(axis=1).sum() if usda_cols else 0
            logger.info(f"   Added {len(df.columns) - before_cols} USDA export columns")
            logger.info(f"   USDA exports matched on {non_null:,} / {len(df):,} rows")

        # Merge USDA WASDE (MONTHLY - use asof merge)
        if len(df_wasde) > 0:
            logger.info("Merging USDA WASDE supply/demand (asof)...")
            before_cols = len(df.columns)
            df = merge_asof_to_trading_days(df, df_wasde)
            wasde_cols = [c for c in df.columns if c.startswith("wasde_")]
            non_null = df[wasde_cols].notna().any(axis=1).sum() if wasde_cols else 0
            logger.info(f"   Added {len(df.columns) - before_cols} WASDE columns")
            logger.info(f"   WASDE matched on {non_null:,} / {len(df):,} rows")

        # Map WASDE columns to strict specialist expectations (if present)
        if (
            "wasde_us_zs_crush" in df.columns
            and "wasde_soybeans_crush" not in df.columns
        ):
            df["wasde_soybeans_crush"] = df["wasde_us_zs_crush"]
            logger.info("   Mapped wasde_us_zs_crush → wasde_soybeans_crush")
        if (
            "wasde_us_zl_production" in df.columns
            and "wasde_soybean_oil_production" not in df.columns
        ):
            df["wasde_soybean_oil_production"] = df["wasde_us_zl_production"]
            logger.info(
                "   Mapped wasde_us_zl_production → wasde_soybean_oil_production"
            )
        if (
            "wasde_us_zl_ending_stocks" in df.columns
            and "wasde_soybean_oil_ending_stocks" not in df.columns
        ):
            df["wasde_soybean_oil_ending_stocks"] = df["wasde_us_zl_ending_stocks"]
            logger.info(
                "   Mapped wasde_us_zl_ending_stocks → wasde_soybean_oil_ending_stocks"
            )

        # Merge China PMI (MONTHLY - use asof merge)
        if len(df_china_pmi) > 0:
            logger.info("Merging China PMI (asof)...")
            before_cols = len(df.columns)
            df = merge_asof_to_trading_days(df, df_china_pmi)
            logger.info(f"   Added {len(df.columns) - before_cols} China PMI columns")

        # Merge Dalian soy proxy (non-US trading calendar - use asof merge)
        if len(df_dalian) > 0:
            logger.info("Merging Dalian soybean oil proxy (asof)...")
            before_cols = len(df.columns)
            df = merge_asof_to_trading_days(df, df_dalian)
            logger.info(f"   Added {len(df.columns) - before_cols} Dalian soy columns")

        # Merge news sentiment (NEW 2026-01-23)
        if len(df_news) > 0:
            logger.info("Merging news sentiment (NEW)...")
            before_cols = len(df.columns)
            df = df.merge(df_news, on="trade_date", how="left")
            logger.info(f"   Added {len(df.columns) - before_cols} news columns")

        # Merge specialist signals (v3 architecture)
        df_signals = load_specialist_signals(conn, include_signals=True)
        if len(df_signals) > 0:
            logger.info("Merging specialist signals...")

            # Task 4.5: Validate specialist signals before Core integration
            validation_result = validate_specialist_signals_for_core(df_signals, conn)
            if not validation_result["valid"]:
                logger.warning("⚠️  Specialist signal quality issues detected:")
                for issue in validation_result["issues"]:
                    logger.warning(f"   - {issue}")
                logger.warning(
                    "   Proceeding with integration, but Core training may be degraded"
                )

            df = df.merge(df_signals, on="trade_date", how="left")
            signal_cols = [c for c in df.columns if c.startswith("sig_")]
            logger.info(f"   Added {len(signal_cols)} specialist signal columns")

        logger.info(f"Combined matrix: {len(df):,} rows, {len(df.columns)} columns")

        # Create target columns (forward returns)
        df = create_target_columns(df)

        # NO FORWARD FILL - raw data only
        # AutoGluon handles nulls natively
        logger.info("NO forward-filling - raw data preserved")

        # Coverage filter REMOVED (2026-01-22)
        # AutoGluon's DirectTabular handles missing values natively via gradient boosting
        # This allows series with different start dates to be used without being dropped
        # Log coverage stats for visibility instead of filtering
        logger.info(
            "Logging feature coverage (no filtering - AutoGluon handles nulls)..."
        )
        coverage = df.notna().mean()
        feature_cols = [c for c in df.columns if c not in ["trade_date", "symbol"]]
        low_coverage = [(c, coverage[c]) for c in feature_cols if coverage[c] < 0.7]
        if low_coverage:
            logger.info(
                f"   {len(low_coverage)} features with <70% coverage (kept for AutoGluon):"
            )
            for col, cov in sorted(low_coverage, key=lambda x: x[1])[:10]:
                logger.info(f"      {col}: {cov*100:.1f}%")
            if len(low_coverage) > 10:
                logger.info(f"      ... and {len(low_coverage) - 10} more")

        # NOTE: NO NORMALIZATION HERE
        # Normalization happens in Phase 6 per CV window to prevent leakage
        # Raw features are stored in the matrix
        logger.info("⚠️ Storing RAW features (no normalization)")
        logger.info("   Normalization will be done in Phase 6 per CV window")

        # Enforce guardrails
        df, guardrail_passed = enforce_feature_guardrails(df)

        # Compute version hash
        matrix_version = compute_matrix_version(df)

        # Count features (excluding metadata and targets)
        exclude_cols = {"trade_date", "symbol", "matrix_version", "created_at"} | {
            f"target_ret_{h}d" for h in HORIZONS
        }
        feature_count = len([c for c in df.columns if c not in exclude_cols])

        # Write to database
        rows_written = write_matrix(conn, df, matrix_version)

        conn.close()

        logger.info("=" * 60)
        logger.info("✅ PHASE 3 COMPLETE - Core matrix built")
        logger.info(f"   Rows: {rows_written:,}")
        logger.info(f"   Features: {feature_count}")
        logger.info(f"   Matrix version: {matrix_version}")
        logger.info(f"   Guardrails passed: {guardrail_passed}")
        logger.info("=" * 60)

        return True, matrix_version, feature_count

    except Exception as e:
        logger.error(f"❌ PHASE 3 FAILED: {e}", exc_info=True)
        return False, None, 0


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="Phase 3: Build Core Matrix")
    parser.add_argument("--symbol", default=TARGET_SYMBOL)
    args = parser.parse_args()

    success, version, features = run(args.symbol)
    exit(0 if success else 1)
