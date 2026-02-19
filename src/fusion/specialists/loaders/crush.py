"""Specialist-specific data loader."""

import logging
from datetime import date

import numpy as np
import pandas as pd

from .common import get_connection, load_news_for_specialist

logger = logging.getLogger(__name__)


def load_crush_data(
    start_date: date | None = None, end_date: date | None = None
) -> pd.DataFrame:
    """
    Load ALL data for CRUSH specialist.

    ZL, ZS, ZM futures with OHLCV + WASDE + CFTC positioning.
    """
    conn = get_connection()

    # ZL, ZS, ZM futures
    query = """
    SELECT event_date as trade_date, symbol, open, high, low, close, volume, open_interest
    FROM mkt.futures_1d
    WHERE symbol IN ('ZL', 'ZS', 'ZM')
    ORDER BY event_date, symbol
    """
    df = pd.read_sql(query, conn)
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    # Pivot to wide
    result = df.pivot(index="trade_date", columns="symbol", values="close")
    result.columns = [f"{c.lower()}_close" for c in result.columns]
    result = result.reset_index()

    # Add OHLV for each
    for col_type in ["open", "high", "low", "volume", "open_interest"]:
        pivot = df.pivot(index="trade_date", columns="symbol", values=col_type)
        pivot.columns = [f"{c.lower()}_{col_type}" for c in pivot.columns]
        for c in pivot.columns:
            result[c] = pivot[c].values

    result["close"] = result["zl_close"]
    # Alias ZL volume/OI for Crush specialist (expects unprefixed names)
    result["volume"] = result["zl_volume"]
    result["open_interest"] = result["zl_open_interest"]
    result.set_index("trade_date", inplace=True)

    # WASDE
    wasde_query = """
    SELECT event_date as trade_date, commodity, metric, value
    FROM supply.usda_wasde_1m
    WHERE commodity IN ('Soybeans', 'Soybean Oil', 'Soybean Meal')
      AND country = 'United States'
    ORDER BY event_date
    """
    wasde_df = pd.read_sql(wasde_query, conn)
    if not wasde_df.empty:
        wasde_df["trade_date"] = pd.to_datetime(wasde_df["trade_date"])
        wasde_df["col"] = (
            "wasde_"
            + wasde_df["commodity"].str.replace(" ", "_").str.lower()
            + "_"
            + wasde_df["metric"]
        )
        wasde_pivot = wasde_df.pivot(index="trade_date", columns="col", values="value")
        # No forward-fill (policy)
        for c in wasde_pivot.columns:
            result[c] = wasde_pivot.reindex(result.index)[c]

    # CFTC
    cftc_query = """
    SELECT event_date as trade_date, managed_money_net as cftc_zl_net_spec, open_interest as cftc_oi
    FROM pos.cftc_1w
    WHERE symbol = 'ZL'
    ORDER BY event_date
    """
    cftc_df = pd.read_sql(cftc_query, conn)
    if not cftc_df.empty:
        cftc_df["trade_date"] = pd.to_datetime(cftc_df["trade_date"])
        cftc_df.set_index("trade_date", inplace=True)
        # No forward-fill (policy)
        for c in cftc_df.columns:
            result[c] = cftc_df.reindex(result.index)[c]

    # Options data for crush complex (ZL, ZS, ZM) - NO GREEKS, raw OHLCV only
    options_query = """
    SELECT
        event_date as trade_date,
        underlying,
        option_type,
        SUM(volume) as total_volume,
        SUM(open_interest) as total_oi,
        AVG(close) as avg_premium,
        COUNT(*) as num_strikes
    FROM mkt.options_1d
    WHERE underlying IN ('ZL', 'ZS', 'ZM')
      AND source = 'databento'
    GROUP BY event_date, underlying, option_type
    ORDER BY event_date, underlying, option_type
    """
    options_df = pd.read_sql(options_query, conn)
    if not options_df.empty:
        options_df["trade_date"] = pd.to_datetime(options_df["trade_date"])
        for ul in ["ZL", "ZS", "ZM"]:
            ul_lower = ul.lower()
            ul_data = options_df[options_df["underlying"] == ul]
            if ul_data.empty:
                continue

            calls = ul_data[ul_data["option_type"] == "C"].set_index("trade_date")
            puts = ul_data[ul_data["option_type"] == "P"].set_index("trade_date")

            if not calls.empty:
                result[f"{ul_lower}_call_volume"] = calls["total_volume"].reindex(
                    result.index
                )
                result[f"{ul_lower}_call_oi"] = calls["total_oi"].reindex(result.index)
                result[f"{ul_lower}_call_premium"] = calls["avg_premium"].reindex(
                    result.index
                )
            if not puts.empty:
                result[f"{ul_lower}_put_volume"] = puts["total_volume"].reindex(
                    result.index
                )
                result[f"{ul_lower}_put_oi"] = puts["total_oi"].reindex(result.index)
                result[f"{ul_lower}_put_premium"] = puts["avg_premium"].reindex(
                    result.index
                )

            # Put/Call ratio (only if both have data)
            if not calls.empty and not puts.empty:
                call_vol = calls["total_volume"].reindex(result.index)
                put_vol = puts["total_volume"].reindex(result.index)
                pc_ratio = put_vol / call_vol.replace(0, np.nan)
                result[f"{ul_lower}_put_call_ratio"] = pc_ratio

    conn.close()

    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]

    # Add news data for CRUSH specialist
    news_df = load_news_for_specialist("crush", start_date, end_date)
    if not news_df.empty:
        for col in news_df.columns:
            result[col] = news_df.reindex(result.index)[col]

    logger.info(f"CRUSH data: {len(result)} rows, {len(result.columns)} columns")
    return result
