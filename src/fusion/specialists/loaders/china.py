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

    ZL + HG (copper) + ZS (soybeans) + CNY + BRL + China macro + shipping index.
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

    # Shipping index (FRED BDIY) instead of ETF proxies
    ship_query = """
    SELECT event_date as trade_date, value as fred_bdiy
    FROM econ.commodities_1d
    WHERE series_id = 'BDIY'
    ORDER BY event_date
    """
    ship_df = pd.read_sql(ship_query, conn)
    if not ship_df.empty:
        ship_df["trade_date"] = pd.to_datetime(ship_df["trade_date"])
        ship_df.set_index("trade_date", inplace=True)
        result["fred_bdiy"] = ship_df["fred_bdiy"].reindex(result.index)

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

    # ==========================================================================
    # China macro: PMI + imports/exports + trade policy (expanded 2026-02-24)
    # ==========================================================================
    china_macro_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.activity_1d
    WHERE series_id IN (
        'china_pmi',        -- China PMI (monthly)
        'CHNMAINLANDTPU',   -- China trade policy uncertainty (monthly)
        'EXPCH',            -- China exports (monthly, FRED)
        'IMPCH',            -- China imports (monthly, FRED)
        'XTEXVA01CNM667S',  -- China exports alt (OECD monthly)
        'XTIMVA01CNM667S'   -- China imports alt (OECD monthly)
    )
    ORDER BY event_date, series_id
    """
    china_macro_df = pd.read_sql(china_macro_query, conn)
    if not china_macro_df.empty:
        china_macro_df["trade_date"] = pd.to_datetime(china_macro_df["trade_date"])
        # Pivot all China macro series into columns
        pivot = china_macro_df.pivot(
            index="trade_date", columns="series_id", values="value"
        )
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        # Rename china_pmi for backward compat
        if "fred_china_pmi" in pivot.columns:
            result["china_pmi"] = pivot["fred_china_pmi"].reindex(result.index)
        # Add all others
        for c in pivot.columns:
            if c != "fred_china_pmi":
                result[c] = pivot.reindex(result.index)[c]

    # ==========================================================================
    # Trade policy uncertainty from vol indices (added 2026-02-24)
    # ==========================================================================
    vol_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.vol_indices_1d
    WHERE series_id IN (
        'EMVTRADEPOLEMV',  -- US trade policy uncertainty (EMV)
        'CHNMAINLANDEPU',  -- China economic policy uncertainty
        'EMVAGRPOLICY'     -- Agricultural policy uncertainty
    )
    ORDER BY event_date, series_id
    """
    vol_df = pd.read_sql(vol_query, conn)
    if not vol_df.empty:
        vol_df["trade_date"] = pd.to_datetime(vol_df["trade_date"])
        pivot = vol_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

    # ==========================================================================
    # USDA country-level exports — China's purchase share (added 2026-02-24)
    # Country-level export data = geopolitical signal layer (see AGENTS.md)
    # ==========================================================================
    usda_query = """
    SELECT event_date as trade_date,
           commodity,
           SUM(CASE WHEN destination_country = 'TOTAL' THEN net_sales_mt ELSE 0 END) as total_sales,
           SUM(CASE WHEN destination_country = 'China' THEN net_sales_mt ELSE 0 END) as china_sales,
           SUM(CASE WHEN destination_country = 'TOTAL' THEN exports_mt ELSE 0 END) as total_exports,
           SUM(CASE WHEN destination_country = 'China' THEN exports_mt ELSE 0 END) as china_exports
    FROM supply.usda_exports_1w
    WHERE commodity IN ('Soybeans', 'Soybean Oil', 'Soybean Meal')
      AND destination_country IN ('TOTAL', 'China')
    GROUP BY event_date, commodity
    ORDER BY event_date, commodity
    """
    usda_df = pd.read_sql(usda_query, conn)
    if not usda_df.empty:
        usda_df["trade_date"] = pd.to_datetime(usda_df["trade_date"])
        for commodity in ["Soybeans", "Soybean Oil", "Soybean Meal"]:
            slug = commodity.lower().replace(" ", "_")
            c_df = usda_df[usda_df["commodity"] == commodity].set_index("trade_date")
            if not c_df.empty:
                result[f"usda_{slug}_china_sales"] = c_df["china_sales"].reindex(
                    result.index
                )
                result[f"usda_{slug}_china_exports"] = c_df["china_exports"].reindex(
                    result.index
                )
                result[f"usda_{slug}_total_sales"] = c_df["total_sales"].reindex(
                    result.index
                )
                # China share of total sales (key geopolitical signal)
                total = c_df["total_sales"].reindex(result.index)
                china = c_df["china_sales"].reindex(result.index)
                result[f"usda_{slug}_china_share"] = china / total.replace(0, pd.NA)
        logger.info("  USDA China export share loaded (geopolitical signal layer)")

    conn.close()

    # ETF ingestion removed from runtime for China specialist

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
