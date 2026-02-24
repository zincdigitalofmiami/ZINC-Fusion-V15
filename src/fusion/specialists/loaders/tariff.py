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

    ZL + EPU/EMV uncertainty indices + China TPU + USDA export flows +
    tariff deadlines + EU uncertainty.

    Data sources:
    - mkt.futures_1d: ZL for returns
    - econ.vol_indices_1d: EPU/EMV trade/fiscal/ag policy uncertainty
    - econ.activity_1d: China trade policy uncertainty
    - supply.usda_exports_1w: Trade flow shifts from tariff impacts
    - alt.tariff_deadlines_static: Upcoming policy deadlines
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
    # EPU/EMV uncertainty indices (expanded 2026-02-24)
    # ==========================================================================
    epu_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.vol_indices_1d
    WHERE series_id IN (
        -- Core trade/policy uncertainty (existing)
        'USEPUINDXD', 'USEPUINDXM', 'EPUTRADE', 'EMVTRADEPOLEMV',
        -- EMV trackers relevant to tariff policy (added 2026-02-24)
        'EMVAGRPOLICY',    -- Agricultural policy uncertainty
        'EMVCOMMMKT',      -- Commodity market uncertainty
        'EMVNATSEC',       -- National security (steel/aluminum tariffs = national security)
        'EMVFISCALPOL',    -- Fiscal policy (tariffs are fiscal tools)
        'EMVTAXESEMV',     -- Tax uncertainty (tariffs = import taxes)
        'EMVGOVTSPEND',    -- Government spending uncertainty
        -- EPU subcategories (monthly)
        'EPUTAXES',        -- Tax EPU
        'EPUFISCAL',       -- Fiscal EPU
        -- International uncertainty
        'EUEPUINDXM',      -- EU uncertainty (EU tariff negotiations)
        'CHNMAINLANDEPU',  -- China economic policy uncertainty
        -- Credit/financial context
        'BAMLH0A0HYM2'    -- HY spread (risk appetite proxy)
    )
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
        result["fred_chnmainlandtpu"] = china_df["value"].reindex(result.index)

    # ==========================================================================
    # USDA export flows — tariff impact shows in trade flow shifts (added 2026-02-24)
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
                result[f"usda_{slug}_total_sales"] = c_df["total_sales"].reindex(
                    result.index
                )
                result[f"usda_{slug}_china_sales"] = c_df["china_sales"].reindex(
                    result.index
                )
                result[f"usda_{slug}_total_exports"] = c_df["total_exports"].reindex(
                    result.index
                )
                result[f"usda_{slug}_china_exports"] = c_df["china_exports"].reindex(
                    result.index
                )
                # China share of total (tariff barometer)
                total = c_df["total_sales"].reindex(result.index)
                china = c_df["china_sales"].reindex(result.index)
                result[f"usda_{slug}_china_share"] = china / total.replace(0, pd.NA)
        logger.info("  USDA export flows loaded for tariff impact analysis")

    # ==========================================================================
    # Tariff deadlines (added 2026-02-24)
    # ==========================================================================
    tariff_query = """
    SELECT deadline_name, deadline_date, renewal_probability, policy_type
    FROM alt.tariff_deadlines_static
    WHERE is_active = true
    ORDER BY deadline_date
    """
    try:
        tariff_df = pd.read_sql(tariff_query, conn)
        if not tariff_df.empty:
            result["tariff_deadline_count"] = 0
            result["tariff_renewal_risk"] = 0.0
            for _, row in tariff_df.iterrows():
                deadline = pd.to_datetime(row["deadline_date"])
                mask = (result.index <= deadline) & (
                    result.index >= deadline - pd.Timedelta(days=90)
                )
                result.loc[mask, "tariff_deadline_count"] += 1
                renewal_prob = row.get("renewal_probability")
                if renewal_prob is None:
                    renewal_prob = 0.5
                result.loc[mask, "tariff_renewal_risk"] = max(
                    result.loc[mask, "tariff_renewal_risk"].max(),
                    float(renewal_prob),
                )
            logger.info(
                f"  Tariff deadlines: {len(tariff_df)} active deadlines expanded"
            )
    except Exception as e:
        logger.warning(f"Tariff deadlines unavailable: {e}")

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
