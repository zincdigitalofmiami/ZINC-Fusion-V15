"""Specialist-specific data loader."""

import logging
from datetime import date

import pandas as pd

from .common import get_connection, load_news_for_specialist

logger = logging.getLogger(__name__)


def load_tariff_data(
    start_date: date | None = None, end_date: date | None = None
) -> pd.DataFrame:
    """
    Load ALL data for TARIFF specialist.

    ZL + EPU indices.
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

    # EPU indices (from vol_indices, not activity)
    epu_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.vol_indices_1d
    WHERE series_id IN ('USEPUINDXD', 'USEPUINDXM', 'EPUTRADE', 'EMVTRADEPOLEMV')
    ORDER BY event_date, series_id
    """
    epu_df = pd.read_sql(epu_query, conn)
    if not epu_df.empty:
        epu_df["trade_date"] = pd.to_datetime(epu_df["trade_date"])
        pivot = epu_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        # No forward-fill (policy)
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

    # China trade policy uncertainty from activity
    china_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.activity_1d
    WHERE series_id = 'CHNMAINLANDTPU'
    ORDER BY event_date
    """
    china_df = pd.read_sql(china_query, conn)
    if not china_df.empty:
        china_df["trade_date"] = pd.to_datetime(china_df["trade_date"])
        china_df.set_index("trade_date", inplace=True)
        result["fred_chnmainlandtpu"] = china_df["value"].reindex(
            result.index
        )  # Daily cadence + 2 day buffer

    conn.close()

    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]

    # Add news data for TARIFF specialist
    news_df = load_news_for_specialist("tariff", start_date, end_date)
    if not news_df.empty:
        for col in news_df.columns:
            result[col] = news_df.reindex(result.index)[col]

    logger.info(f"TARIFF data: {len(result)} rows, {len(result.columns)} columns")
    return result
