"""Specialist-specific data loader."""

import logging
from datetime import date

import pandas as pd

from .common import get_connection, load_news_for_specialist

logger = logging.getLogger(__name__)


def load_energy_data(
    start_date: date | None = None, end_date: date | None = None
) -> pd.DataFrame:
    """
    Load ALL data for ENERGY specialist.

    ZL + CL + HO + RB + NG + BZ (full petroleum complex) +
    crude oil volatility + energy regulation uncertainty +
    FRED refined product prices + RIN/LCFS mandate pricing.

    Data sources:
    - mkt.futures_1d: ZL, CL, HO, RB, NG, BZ (OHLCV)
    - econ.vol_indices_1d: OVXCLS, EMVENRGYENVREG, EMVCOMMMKT, VIXCLS
    - econ.commodities_1d: FRED energy commodity prices
    - supply.epa_rin_1d: RIN prices (biodiesel mandate)
    - supply.lcfs_1d: California LCFS credits
    """
    conn = get_connection()

    # ==========================================================================
    # Futures: ZL, CL, HO, RB, NG, BZ
    # ==========================================================================
    query = """
    SELECT event_date as trade_date, symbol, open, high, low, close, volume
    FROM mkt.futures_1d
    WHERE symbol IN ('ZL', 'CL', 'HO', 'RB', 'NG', 'BZ')
    ORDER BY event_date, symbol
    """
    df = pd.read_sql(query, conn)
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    result = df.pivot(index="trade_date", columns="symbol", values="close")
    result.columns = [f"{c.lower()}_close" for c in result.columns]
    result = result.reset_index()
    result["close"] = result["zl_close"]
    result.set_index("trade_date", inplace=True)

    for col_type in ["open", "high", "low", "volume"]:
        pivot = df.pivot(index="trade_date", columns="symbol", values=col_type)
        pivot.columns = [f"{c.lower()}_{col_type}" for c in pivot.columns]
        for c in pivot.columns:
            result[c] = pivot[c].values

    # ==========================================================================
    # Crude oil volatility + energy regulation uncertainty (added 2026-02-24)
    # ==========================================================================
    vol_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.vol_indices_1d
    WHERE series_id IN (
        'OVXCLS',         -- CBOE Crude Oil Volatility Index
        'EMVENRGYENVREG', -- Energy/environment regulation uncertainty (EMV)
        'EMVCOMMMKT',     -- Commodity market uncertainty
        'VIXCLS'          -- VIX (risk-off affects energy complex)
    )
    ORDER BY event_date, series_id
    """
    vol_df = pd.read_sql(vol_query, conn)
    if not vol_df.empty:
        vol_df["trade_date"] = pd.to_datetime(vol_df["trade_date"])
        pivot = vol_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        # No forward-fill (policy)
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

    # ==========================================================================
    # FRED refined product prices (added 2026-02-24)
    # ==========================================================================
    comm_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.commodities_1d
    WHERE series_id IN (
        'DCOILWTICO',    -- WTI crude (FRED daily)
        'DCOILBRENTEU',  -- Brent crude (FRED daily)
        'DHOILNYH',      -- Heating oil NY Harbor (FRED daily)
        'DDFUELUSGULF',  -- No. 2 diesel fuel US Gulf (FRED daily)
        'DJFUELUSGULF',  -- Jet fuel US Gulf (FRED daily)
        'DGASUSGULF',    -- Gasoline US Gulf (FRED daily)
        'DHHNGSP'        -- Henry Hub natural gas (FRED daily)
    )
    ORDER BY event_date, series_id
    """
    comm_df = pd.read_sql(comm_query, conn)
    if not comm_df.empty:
        comm_df["trade_date"] = pd.to_datetime(comm_df["trade_date"])
        pivot = comm_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        # No forward-fill (policy)
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

    # ==========================================================================
    # RIN prices — biodiesel mandates drive soybean oil demand (added 2026-02-24)
    # ==========================================================================
    rin_query = """
    SELECT event_date as trade_date, rin_type, price
    FROM supply.epa_rin_1d
    ORDER BY event_date, rin_type
    """
    rin_df = pd.read_sql(rin_query, conn)
    if not rin_df.empty:
        rin_df["trade_date"] = pd.to_datetime(rin_df["trade_date"])
        pivot = rin_df.pivot(index="trade_date", columns="rin_type", values="price")
        pivot.columns = [f"rin_{c.lower()}_price" for c in pivot.columns]
        # No forward-fill (policy)
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]
        logger.info(f"  RIN prices loaded: {list(pivot.columns)}")

    # ==========================================================================
    # LCFS credits — California carbon (added 2026-02-24)
    # ==========================================================================
    try:
        lcfs_query = """
        SELECT event_date as trade_date, price_usd_per_mt as lcfs_credit
        FROM supply.lcfs_1d
        ORDER BY event_date
        """
        lcfs_df = pd.read_sql(lcfs_query, conn)
        if not lcfs_df.empty:
            lcfs_df["trade_date"] = pd.to_datetime(lcfs_df["trade_date"])
            lcfs_df.set_index("trade_date", inplace=True)
            result["lcfs_credit"] = lcfs_df["lcfs_credit"].reindex(result.index)
    except Exception as e:
        logger.warning(f"LCFS data unavailable: {e}")

    conn.close()

    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]

    # Add news data for ENERGY specialist
    news_df = load_news_for_specialist("energy", start_date, end_date)
    if not news_df.empty:
        for col in news_df.columns:
            result[col] = news_df.reindex(result.index)[col]

    logger.info(f"ENERGY data: {len(result)} rows, {len(result.columns)} columns")
    return result
