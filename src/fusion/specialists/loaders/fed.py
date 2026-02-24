"""Specialist-specific data loader."""

import logging
from datetime import date

import pandas as pd

from .common import get_connection, load_news_for_specialist

logger = logging.getLogger(__name__)


def load_fed_data(
    start_date: date | None = None, end_date: date | None = None
) -> pd.DataFrame:
    """
    Load ALL data for FED specialist.

    ZL + full yield curve + NFCI + breakevens.

    NO FFILL - missing data is missing. Weekly series (NFCI) will have NaN on non-release days.

    Data sources:
    - econ.rates_1d: DFF (daily fed funds), Treasury yields, yield curve spreads
    - econ.inflation_1d: Breakeven inflation (T5YIE, T10YIE), TIPS real yields (DFII*)
    - econ.vol_indices_1d: NFCI, credit spreads (BAMLH0A0HYM2)
    """
    conn = get_connection()

    # ZL base
    zl_query = """
    SELECT event_date as trade_date, open, high, low, close, volume
    FROM mkt.futures_1d
    WHERE symbol = 'ZL'
    ORDER BY event_date
    """
    result = pd.read_sql(zl_query, conn)
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    result.set_index("trade_date", inplace=True)

    # ==========================================================================
    # 1. RATES (econ.rates_1d) - Daily Treasury yields and Fed Funds
    # ==========================================================================
    # NOTE: Using DFF (daily) instead of FEDFUNDS (monthly, 61d stale)
    # NOTE: Removed T10YIE, T5YIE (in inflation_1d), TEDRATE (discontinued 2022)
    rates_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.rates_1d
    WHERE series_id IN (
        'DFF',      -- Daily Fed Funds (replaces monthly FEDFUNDS)
        'DGS1MO', 'DGS3MO', 'DGS6MO',  -- Short-term Treasury
        'DGS1', 'DGS2', 'DGS5', 'DGS7', 'DGS10', 'DGS20', 'DGS30',  -- Full curve
        'T10Y2Y', 'T10Y3M',  -- Yield curve spreads
        'SOFR'      -- Secured overnight rate
    )
    ORDER BY event_date, series_id
    """
    rates_df = pd.read_sql(rates_query, conn)
    if not rates_df.empty:
        rates_df["trade_date"] = pd.to_datetime(rates_df["trade_date"])
        pivot = rates_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        # NO FFILL - raw data only
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

        # Log data quality
        for c in pivot.columns:
            coverage = result[c].notna().sum() / len(result) * 100
            last_valid = result[c].last_valid_index()
            logger.debug(f"  {c}: {coverage:.1f}% coverage, last: {last_valid}")

    # ==========================================================================
    # 2. INFLATION EXPECTATIONS (econ.inflation_1d) - Breakevens and TIPS yields
    # ==========================================================================
    inflation_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.inflation_1d
    WHERE series_id IN (
        'T5YIE', 'T10YIE', 'T5YIFR',  -- Breakeven inflation expectations
        'DFII5', 'DFII7', 'DFII10', 'DFII20', 'DFII30'  -- TIPS real yields
    )
    ORDER BY event_date, series_id
    """
    inflation_df = pd.read_sql(inflation_query, conn)
    if not inflation_df.empty:
        inflation_df["trade_date"] = pd.to_datetime(inflation_df["trade_date"])
        pivot = inflation_df.pivot(
            index="trade_date", columns="series_id", values="value"
        )
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        # NO FFILL - raw data only
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

        logger.info(f"  Inflation expectations loaded: {list(pivot.columns)}")

    # ==========================================================================
    # 3. FINANCIAL CONDITIONS (econ.vol_indices_1d) - NFCI, credit spreads, EMV
    # ==========================================================================
    # NOTE: NFCI is weekly (released Thursdays) - will have NaN on non-release days
    # NOTE: BAMLH0A0HYM2 (HY spread) replaces discontinued TEDRATE
    vol_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.vol_indices_1d
    WHERE series_id IN (
        'NFCI', 'ANFCI', 'STLFSI4',  -- Financial stress (weekly)
        'BAMLH0A0HYM2', 'BAMLC0A0CM',  -- Credit spreads (daily)
        'VIXCLS',                       -- Market volatility (daily)
        -- EMV monetary policy trackers (directly relevant to Fed specialist)
        'EMVMONETARYPOL',    -- Monetary policy uncertainty
        'EMVMACROINTEREST',  -- Interest rate macro uncertainty
        'EMVMACROINFLATION', -- Inflation macro uncertainty
        'EMVFISCALPOL',      -- Fiscal policy uncertainty
        'EMVFINCRISES',      -- Financial crises uncertainty
        -- EPU subcategories
        'USEPUINDXD',        -- US EPU daily
        'USEPUINDXM',        -- US EPU monthly
        'EPUFINREG'          -- Financial regulation uncertainty
    )
    ORDER BY event_date, series_id
    """
    vol_df = pd.read_sql(vol_query, conn)
    if not vol_df.empty:
        vol_df["trade_date"] = pd.to_datetime(vol_df["trade_date"])
        pivot = vol_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        # NO FFILL - weekly NFCI will have NaN on non-release days (this is correct)
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

        # Log weekly series coverage (expected to be ~20% for weekly data)
        if "fred_nfci" in result.columns:
            nfci_coverage = result["fred_nfci"].notna().sum() / len(result) * 100
            logger.info(
                f"  NFCI coverage: {nfci_coverage:.1f}% (weekly release - expected ~20%)"
            )

    # ==========================================================================
    # 4. LABOR MARKET (econ.labor_1d) - Fed dual mandate inputs
    # ==========================================================================
    labor_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.labor_1d
    WHERE series_id IN (
        'UNRATE',      -- Unemployment rate (monthly)
        'PAYEMS',      -- Total nonfarm payrolls (monthly)
        'ICSA',        -- Initial jobless claims (weekly)
        'CCSA',        -- Continued jobless claims (weekly)
        'AWHMAN',      -- Avg weekly hours manufacturing (monthly)
        'CES0500000003' -- Avg hourly earnings (monthly)
    )
    ORDER BY event_date, series_id
    """
    try:
        labor_df = pd.read_sql(labor_query, conn)
        if not labor_df.empty:
            labor_df["trade_date"] = pd.to_datetime(labor_df["trade_date"])
            pivot = labor_df.pivot(
                index="trade_date", columns="series_id", values="value"
            )
            pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
            for c in pivot.columns:
                result[c] = pivot.reindex(result.index)[c]
            logger.info(f"  Labor market: {len(pivot.columns)} series loaded")
    except Exception as e:
        logger.warning(f"Labor data unavailable: {e}")

    conn.close()

    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]

    # Add news data for FED specialist
    news_df = load_news_for_specialist("fed", start_date, end_date)
    if not news_df.empty:
        for col in news_df.columns:
            result[col] = news_df.reindex(result.index)[col]

    # Log final data quality summary
    rate_cols = [
        c for c in result.columns if c.startswith("fred_dgs") or c == "fred_dff"
    ]
    inflation_cols = [
        c for c in result.columns if "yie" in c or "dfii" in c or "yifr" in c
    ]
    vol_cols = [
        c for c in result.columns if "nfci" in c or "baml" in c or "stlfsi" in c
    ]

    logger.info(f"FED data: {len(result)} rows, {len(result.columns)} columns")
    logger.info(f"  Rates: {len(rate_cols)} series")
    logger.info(f"  Inflation: {len(inflation_cols)} series")
    logger.info(f"  Vol/Credit: {len(vol_cols)} series")

    return result
