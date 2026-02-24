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

    # ==========================================================================
    # Competing vegetable oil prices from FRED (expanded 2026-02-24)
    # ==========================================================================
    comm_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.commodities_1d
    WHERE series_id IN (
        'PSUNOUSDM',   -- Sunflower oil (monthly, IMF)
        'PROILUSDM',   -- Rapeseed oil (monthly, IMF)
        'PPOILUSDM',   -- Palm oil (monthly, IMF)
        'POLVOILUSDM', -- Olive oil (monthly, IMF)
        'PSOILUSDM'    -- Soybean oil (monthly, IMF — benchmark reference)
    )
    ORDER BY event_date, series_id
    """
    comm_df = pd.read_sql(comm_query, conn)
    if not comm_df.empty:
        comm_df["trade_date"] = pd.to_datetime(comm_df["trade_date"])
        pivot = comm_df.pivot(index="trade_date", columns="series_id", values="value")
        rename = {
            "PSUNOUSDM": "sunflower_close",
            "PROILUSDM": "rapeseed_close",
            "PPOILUSDM": "palm_oil_imf",
            "POLVOILUSDM": "olive_oil_imf",
            "PSOILUSDM": "soybean_oil_imf",
        }
        for series_id, col_name in rename.items():
            if series_id in pivot.columns:
                result[col_name] = pivot[series_id].reindex(result.index)

    # ==========================================================================
    # MPOB palm fundamentals (monthly, added 2026-02-24)
    # ==========================================================================
    mpob_query = """
    SELECT report_month as trade_date, production_mt, exports_mt, stocks_mt
    FROM supply.mpob_palm_1m
    WHERE country = 'Malaysia'
    ORDER BY report_month
    """
    try:
        mpob_df = pd.read_sql(mpob_query, conn)
        if not mpob_df.empty:
            mpob_df["trade_date"] = pd.to_datetime(mpob_df["trade_date"])
            mpob_df.set_index("trade_date", inplace=True)
            mpob_df.columns = [f"palm_{c}" for c in mpob_df.columns]
            # Forward-fill monthly to daily (same policy as palm loader)
            mpob_daily = mpob_df.reindex(result.index, method="ffill")
            for c in mpob_daily.columns:
                result[c] = mpob_daily[c]
    except Exception as e:
        logger.warning(f"MPOB palm data unavailable: {e}")

    # ==========================================================================
    # USDA export volumes for substitution context (added 2026-02-24)
    # ==========================================================================
    usda_query = """
    SELECT event_date as trade_date, commodity,
           SUM(CASE WHEN destination_country = 'TOTAL' THEN exports_mt ELSE 0 END) as total_exports
    FROM supply.usda_exports_1w
    WHERE commodity IN ('Soybean Oil', 'Soybean Meal')
      AND destination_country = 'TOTAL'
    GROUP BY event_date, commodity
    ORDER BY event_date
    """
    usda_df = pd.read_sql(usda_query, conn)
    if not usda_df.empty:
        usda_df["trade_date"] = pd.to_datetime(usda_df["trade_date"])
        for commodity in ["Soybean Oil", "Soybean Meal"]:
            slug = commodity.lower().replace(" ", "_")
            c_df = usda_df[usda_df["commodity"] == commodity].set_index("trade_date")
            if not c_df.empty:
                result[f"usda_{slug}_exports"] = c_df["total_exports"].reindex(
                    result.index
                )

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
