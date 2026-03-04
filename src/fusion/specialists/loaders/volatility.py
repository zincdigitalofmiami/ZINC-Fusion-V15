"""Specialist-specific data loader."""

import logging
from datetime import date

import pandas as pd

from .common import get_connection, load_news_for_specialist

logger = logging.getLogger(__name__)


def load_volatility_data(
    start_date: date | None = None, end_date: date | None = None
) -> pd.DataFrame:
    """
    Load ALL data for VOLATILITY specialist.

    ZL + full VIX complex + CBOE cross-asset vol + financial stress +
    credit spreads + EMV policy uncertainty + market benchmarks.

    NO FFILL - missing data is missing.

    Data sources:
    - mkt.futures_1d: ZL for returns
    - econ.vol_indices_1d: VIX complex, CBOE cross-asset, financial stress,
      credit spreads, EMV/EPU uncertainty trackers, market benchmarks

    NOTE: Discontinued series removed:
    - EVZCLS (Euro FX vol) - discontinued March 2025
    - VXFXICLS (discontinued Feb 2022)
    - VIX9DCLS - not available in FRED
    - STLFSI - replaced by STLFSI4
    - TEDRATE - discontinued Jan 2022
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
    # No implicit fill across NaN close rows.
    result["returns_1d"] = result["close"].pct_change(fill_method=None)

    # ==========================================================================
    # VOL INDICES (econ.vol_indices_1d) - Only active series
    # ==========================================================================
    # NOTE: Removed discontinued series:
    # - EVZCLS (Euro FX vol) - last update 2025-03-11
    # - VXFXICLS (discontinued) - last update 2022-02-11
    # - VXGSCLS - not available
    vol_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.vol_indices_1d
    WHERE series_id IN (
        -- Core VIX complex
        'VIXCLS',    -- VIX spot (30-day implied)
        'VXVCLS',    -- VIX 3-month (term structure)
        'OVXCLS',    -- Crude oil volatility
        'GVZCLS',    -- Gold volatility
        'VXEEMCLS',  -- EM volatility
        -- CBOE cross-asset VIX (added 2026-02-24)
        'VXDCLS',    -- DJIA volatility
        'VXNCLS',    -- Nasdaq volatility
        'RVXCLS',    -- Russell 2000 volatility
        'VXEWZCLS',  -- EM ETF volatility
        -- Financial stress indices
        'NFCI',      -- Chicago Fed National Financial Conditions (weekly)
        'ANFCI',     -- Adjusted NFCI (weekly)
        'STLFSI4',   -- St. Louis Financial Stress Index (weekly)
        -- Credit spreads (daily)
        'BAMLC0A0CM',    -- Investment-grade corporate spread
        'BAMLH0A0HYM2',  -- High-yield corporate spread
        -- EMV policy uncertainty (monthly, relevant to vol regimes)
        'EMVCOMMMKT',        -- Commodity market uncertainty
        'EMVFINCRISES',      -- Financial crisis uncertainty
        'EMVMACROINFLATION', -- Inflation uncertainty
        'EMVMACROINTEREST',  -- Interest rate uncertainty
        -- Daily uncertainty + market benchmarks
        'USEPUINDXD',        -- Daily EPU (policy uncertainty)
        'INFECTDISEMVTRACKD', -- Infectious disease EMV tracker
        'SP500',             -- S&P 500 level
        'NASDAQCOM'          -- Nasdaq composite
    )
    ORDER BY event_date, series_id
    """
    vol_df = pd.read_sql(vol_query, conn)
    if not vol_df.empty:
        vol_df["trade_date"] = pd.to_datetime(vol_df["trade_date"])
        pivot = vol_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]

        # Alias VXVCLS -> VIX3M (specialist expects fred_vix3mcls for term structure)
        if "fred_vxvcls" in pivot.columns:
            pivot["fred_vix3mcls"] = pivot["fred_vxvcls"]

        # NO FFILL - raw data only
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

        # Log data quality
        for series in ["fred_vixcls", "fred_vxvcls", "fred_ovxcls", "fred_gvzcls"]:
            if series in result.columns:
                coverage = result[series].notna().sum() / len(result) * 100
                last_valid = result[series].last_valid_index()
                logger.debug(
                    f"  {series}: {coverage:.1f}% coverage, last: {last_valid}"
                )

    conn.close()

    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]

    # Add news data for VOLATILITY specialist
    news_df = load_news_for_specialist("volatility", start_date, end_date)
    if not news_df.empty:
        for col in news_df.columns:
            result[col] = news_df.reindex(result.index)[col]

    # Log summary
    vol_cols = [c for c in result.columns if c.startswith("fred_")]
    logger.info(f"VOLATILITY data: {len(result)} rows, {len(result.columns)} columns")
    logger.info(f"  Vol indices: {vol_cols}")

    return result
