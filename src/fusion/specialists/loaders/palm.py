"""Specialist-specific data loader."""

import logging
from datetime import date

import pandas as pd

from .common import get_connection, load_news_for_specialist

logger = logging.getLogger(__name__)


def load_palm_data(
    start_date: date | None = None, end_date: date | None = None
) -> pd.DataFrame:
    """
    Load ALL data for PALM specialist.

    ZL + CPO + MYR/USD + IDR/USD.
    """
    conn = get_connection()

    # Futures: ZL, CPO
    query = """
    SELECT event_date as trade_date, symbol, open, high, low, close, volume
    FROM mkt.futures_1d
    WHERE symbol IN ('ZL', 'CPO')
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

    # MYR and IDR from FRED
    fx_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.rates_1d
    WHERE series_id IN ('DEXMAUS', 'DEXINUS')
    ORDER BY event_date, series_id
    """
    fx_df = pd.read_sql(fx_query, conn)
    if not fx_df.empty:
        fx_df["trade_date"] = pd.to_datetime(fx_df["trade_date"])
        pivot = fx_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        # No forward-fill (policy)
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

    # MPOB monthly fundamentals (production, exports, stocks)
    mpob_query = """
    SELECT report_month as trade_date, production_mt, exports_mt,
           stocks_mt, local_consumption_mt
    FROM supply.mpob_palm_1m
    WHERE country = 'Malaysia'
    ORDER BY report_month
    """
    mpob_df = pd.read_sql(mpob_query, conn)
    if not mpob_df.empty:
        mpob_df["trade_date"] = pd.to_datetime(mpob_df["trade_date"])
        mpob_df.set_index("trade_date", inplace=True)
        # Rename for clarity
        mpob_df.columns = [f"palm_{c}" for c in mpob_df.columns]
        # Forward-fill monthly data to daily frequency
        mpob_daily = mpob_df.reindex(result.index, method="ffill")
        for c in mpob_daily.columns:
            result[c] = mpob_daily[c]
        logger.info(f"  MPOB fundamentals: {mpob_df.shape[0]} months joined")

    conn.close()

    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]

    # Add news data for PALM specialist
    news_df = load_news_for_specialist("palm", start_date, end_date)
    if not news_df.empty:
        for col in news_df.columns:
            result[col] = news_df.reindex(result.index)[col]

    logger.info(f"PALM data: {len(result)} rows, {len(result.columns)} columns")
    return result
