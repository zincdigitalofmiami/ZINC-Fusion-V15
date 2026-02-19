"""Specialist-specific data loader."""

import logging
from datetime import date

import pandas as pd

from .common import get_connection, load_news_for_specialist

logger = logging.getLogger(__name__)


def load_substitutes_data(
    start_date: date | None = None, end_date: date | None = None
) -> pd.DataFrame:
    """
    Load ALL data for SUBSTITUTES specialist.

    ZL + CPO + RS (canola) + sunflower + rapeseed.
    """
    conn = get_connection()

    # Futures: ZL, CPO, RS
    query = """
    SELECT event_date as trade_date, symbol, open, high, low, close, volume
    FROM mkt.futures_1d
    WHERE symbol IN ('ZL', 'CPO', 'RS')
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

    # Sunflower and rapeseed from FRED
    comm_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.commodities_1d
    WHERE series_id IN ('PSUNOUSDM', 'PROILUSDM')
    ORDER BY event_date, series_id
    """
    comm_df = pd.read_sql(comm_query, conn)
    if not comm_df.empty:
        comm_df["trade_date"] = pd.to_datetime(comm_df["trade_date"])
        pivot = comm_df.pivot(index="trade_date", columns="series_id", values="value")
        if "PSUNOUSDM" in pivot.columns:
            result["sunflower_close"] = pivot["PSUNOUSDM"].reindex(
                result.index
            )  # Monthly cadence + 5 day buffer
        if "PROILUSDM" in pivot.columns:
            result["rapeseed_close"] = pivot["PROILUSDM"].reindex(
                result.index
            )  # Monthly cadence + 5 day buffer

    conn.close()

    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]

    # Add news data for SUBSTITUTES specialist
    news_df = load_news_for_specialist("substitutes", start_date, end_date)
    if not news_df.empty:
        for col in news_df.columns:
            result[col] = news_df.reindex(result.index)[col]

    logger.info(f"SUBSTITUTES data: {len(result)} rows, {len(result.columns)} columns")
    return result
