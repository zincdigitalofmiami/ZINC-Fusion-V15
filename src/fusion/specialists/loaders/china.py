"""Specialist-specific data loader."""

import logging
from datetime import date

import pandas as pd

from .common import get_connection, load_news_for_specialist

logger = logging.getLogger(__name__)


def load_china_data(
    start_date: date | None = None, end_date: date | None = None
) -> pd.DataFrame:
    """
    Load ALL data for CHINA specialist.

    ZL + HG (copper) + ZS (soybeans) + CNY + shipping ETFs + China ETFs.
    """
    conn = get_connection()

    # Futures: ZL, HG, ZS (soybeans for China import context)
    query = """
    SELECT event_date as trade_date, symbol, open, high, low, close, volume
    FROM mkt.futures_1d
    WHERE symbol IN ('ZL', 'HG', 'ZS')
    ORDER BY event_date, symbol
    """
    df = pd.read_sql(query, conn)
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    result = df.pivot(index="trade_date", columns="symbol", values="close")
    result.columns = [f"{c.lower()}_close" for c in result.columns]
    result = result.reset_index()
    result["close"] = result["zl_close"]
    result.set_index("trade_date", inplace=True)

    # Add OHLV
    for col_type in ["open", "high", "low", "volume"]:
        pivot = df.pivot(index="trade_date", columns="symbol", values=col_type)
        pivot.columns = [f"{c.lower()}_{col_type}" for c in pivot.columns]
        for c in pivot.columns:
            result[c] = pivot[c].values

    # ETFs: Databento (FXI, KWEB, MCHI, BDRY, SBLK)
    etf_query = """
    SELECT event_date as trade_date, symbol, close
    FROM mkt.etf_1d
    WHERE symbol IN ('FXI', 'KWEB', 'MCHI', 'BDRY', 'SBLK')
    ORDER BY event_date, symbol
    """
    etf_df = pd.read_sql(etf_query, conn)
    if not etf_df.empty:
        etf_df["trade_date"] = pd.to_datetime(etf_df["trade_date"])
        etf_pivot = etf_df.pivot(index="trade_date", columns="symbol", values="close")
        etf_pivot.columns = [f"{c.lower()}_close" for c in etf_pivot.columns]
        for c in etf_pivot.columns:
            result[c] = etf_pivot.reindex(result.index)[c]

    # CNY from FRED
    fx_query = """
    SELECT event_date as trade_date, value as usd_cny
    FROM econ.rates_1d
    WHERE series_id = 'DEXCHUS'
    ORDER BY event_date
    """
    fx_df = pd.read_sql(fx_query, conn)
    if not fx_df.empty:
        fx_df["trade_date"] = pd.to_datetime(fx_df["trade_date"])
        fx_df.set_index("trade_date", inplace=True)
        result["usd_cny"] = fx_df["usd_cny"].reindex(
            result.index
        )  # Daily cadence + 2 day buffer

    # BRL from FRED
    brl_query = """
    SELECT event_date as trade_date, value as fred_dexbzus
    FROM econ.rates_1d
    WHERE series_id = 'DEXBZUS'
    ORDER BY event_date
    """
    brl_df = pd.read_sql(brl_query, conn)
    if not brl_df.empty:
        brl_df["trade_date"] = pd.to_datetime(brl_df["trade_date"])
        brl_df.set_index("trade_date", inplace=True)
        result["fred_dexbzus"] = brl_df["fred_dexbzus"].reindex(
            result.index
        )  # Daily cadence + 2 day buffer

    # China PMI from activity table
    # NOTE: CHNPRINTO01IXPYM removed 2026-01-31 - discontinued series (822 days stale)
    china_macro_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.activity_1d
    WHERE series_id = 'china_pmi'
    ORDER BY event_date
    """
    china_macro_df = pd.read_sql(china_macro_query, conn)
    if not china_macro_df.empty:
        china_macro_df["trade_date"] = pd.to_datetime(china_macro_df["trade_date"])
        china_macro_df.set_index("trade_date", inplace=True)
        result["china_pmi"] = china_macro_df["value"].reindex(
            result.index
        )  # Monthly cadence

    conn.close()

    # ETF data quality check removed - ETFs active via Databento

    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]

    # Add news data for CHINA specialist
    news_df = load_news_for_specialist("china", start_date, end_date)
    if not news_df.empty:
        for col in news_df.columns:
            result[col] = news_df.reindex(result.index)[col]

    logger.info(f"CHINA data: {len(result)} rows, {len(result.columns)} columns")
    return result
