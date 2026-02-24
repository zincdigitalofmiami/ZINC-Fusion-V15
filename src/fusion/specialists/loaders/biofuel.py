"""Specialist-specific data loader."""

import logging
from datetime import date

import numpy as np
import pandas as pd

from .common import get_connection, load_news_for_specialist

logger = logging.getLogger(__name__)


def load_biofuel_data(
    start_date: date | None = None, end_date: date | None = None
) -> pd.DataFrame:
    """
    Load ALL data for BIOFUEL specialist.

    ZL + HO + RIN prices + LCFS credits.
    """
    conn = get_connection()

    # Futures: ZL, HO, CL, RB, ZC, ETH, ZM (CME energy/ag for RIN pressure index)
    query = """
    SELECT event_date as trade_date, symbol, open, high, low, close, volume
    FROM mkt.futures_1d
    WHERE symbol IN ('ZL', 'HO', 'CL', 'RB', 'ZC', 'ETH', 'ZM')
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

    # RIN prices
    rin_query = """
    SELECT event_date as trade_date, rin_type, price
    FROM supply.epa_rin_1d
    ORDER BY event_date, rin_type
    """
    rin_df = pd.read_sql(rin_query, conn)
    rin_max_date = None
    if not rin_df.empty:
        rin_df["trade_date"] = pd.to_datetime(rin_df["trade_date"])
        rin_max_date = rin_df["trade_date"].max()
        pivot = rin_df.pivot(index="trade_date", columns="rin_type", values="price")
        pivot.columns = [f"rin_{c.lower()}_price" for c in pivot.columns]
        # No forward-fill (policy). Track last observation dates for staleness.
        for c in pivot.columns:
            series = pivot.reindex(result.index)[c]
            result[c] = series
            last_obs = pd.Series(pd.NaT, index=result.index)
            last_obs.loc[series.notna()] = series.index[series.notna()]
            result[f"{c}_last_obs"] = last_obs.ffill()

    # Daily RIN pressure index (CME energy/ag complex) - no new cost, Databento inputs
    # Always computed. When EPA fresh: specialist blends EPA + index (stronger signal). When EPA stale: index only.
    today = pd.Timestamp.now().normalize()
    rin_staleness = (today - rin_max_date).days if rin_max_date else 999
    win = 63
    min_periods = 30

    def _zscore(series: pd.Series) -> pd.Series:
        m = series.rolling(win, min_periods=min_periods).mean()
        s = series.rolling(win, min_periods=min_periods).std()
        return (series - m) / s

    components = []
    # 1) Biodiesel pressure: ZL (feedstock) vs HO (diesel proxy)
    if "zl_close" in result.columns and "ho_close" in result.columns:
        bd_margin = result["zl_close"] - result["ho_close"]
        result["biodiesel_margin_proxy"] = bd_margin
        components.append(("biodiesel", _zscore(bd_margin)))
    # 2) Ethanol pressure: ETH vs ZC (corn) - D6 RIN
    if "eth_close" in result.columns and "zc_close" in result.columns:
        eth_z = _zscore(result["eth_close"])
        zc_z = _zscore(result["zc_close"])
        components.append(("ethanol", eth_z - zc_z))  # high ethanol vs corn = margin up
    # 3) Crack/energy: 3-2-1 style (2*HO + RB - 3*CL) - refining margin
    if (
        "ho_close" in result.columns
        and "rb_close" in result.columns
        and "cl_close" in result.columns
    ):
        crack = 2 * result["ho_close"] + result["rb_close"] - 3 * result["cl_close"]
        components.append(("crack", _zscore(crack)))

    if components:
        # Equal-weight composite (NaN-safe: only average available)
        rin_index = pd.DataFrame({n: c for n, c in components}).mean(axis=1)
        result["rin_pressure_index"] = rin_index
        result["rin_pressure_index_zscore"] = _zscore(rin_index)
        logger.info(
            f"  RIN pressure index: {len(components)} components ({', '.join(n for n, _ in components)}), "
            f"{rin_index.notna().sum()} days"
        )

    # When EPA RIN is beyond one monthly cycle (45d), specialist uses daily RIN pressure index
    # EPA = weekly series updated monthly; TTL 45d (see RIN_DATA_CONTRACT.md)
    if rin_staleness > 45 and "rin_pressure_index_zscore" in result.columns:
        logger.warning(
            f"RIN data beyond EPA cycle ({rin_staleness}d); using daily RIN pressure index (EPA remains anchor when fresh)"
        )

    # LCFS
    lcfs_query = """
    SELECT event_date as trade_date, price_usd_per_mt as lcfs_credit
    FROM supply.lcfs_1d
    ORDER BY event_date
    """
    try:
        lcfs_df = pd.read_sql(lcfs_query, conn)
        if not lcfs_df.empty:
            lcfs_df["trade_date"] = pd.to_datetime(lcfs_df["trade_date"])
            lcfs_df.set_index("trade_date", inplace=True)
            # No forward-fill (policy). Track last observation dates for staleness.
            lcfs_series = lcfs_df["lcfs_credit"].reindex(result.index)
            result["lcfs_credit"] = lcfs_series
            lcfs_last_obs = pd.Series(pd.NaT, index=result.index)
            lcfs_last_obs.loc[lcfs_series.notna()] = lcfs_series.index[
                lcfs_series.notna()
            ]
            result["lcfs_credit_last_obs"] = lcfs_last_obs.ffill()
    except Exception as e:
        logger.warning(f"LCFS data unavailable: {e}")
        result["lcfs_credit"] = np.nan  # Explicit NaN, not silent skip

    # ==========================================================================
    # EIA biodiesel production (monthly, added 2026-02-24)
    # ==========================================================================
    eia_query = """
    SELECT report_month as trade_date, biodiesel_production_mgal, feedstock_soybean_oil_pct
    FROM supply.eia_biodiesel_1m
    ORDER BY report_month
    """
    try:
        eia_df = pd.read_sql(eia_query, conn)
        if not eia_df.empty:
            eia_df["trade_date"] = pd.to_datetime(eia_df["trade_date"])
            eia_df.set_index("trade_date", inplace=True)
            for c in eia_df.columns:
                result[f"eia_{c}"] = eia_df[c].reindex(result.index)
            logger.info(f"  EIA biodiesel: {eia_df.shape[0]} months loaded")
    except Exception as e:
        logger.warning(f"EIA biodiesel data unavailable: {e}")

    # ==========================================================================
    # Energy regulation uncertainty (added 2026-02-24)
    # ==========================================================================
    vol_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.vol_indices_1d
    WHERE series_id IN (
        'EMVENRGYENVREG',  -- Energy/environment regulation uncertainty
        'OVXCLS'           -- Crude oil volatility
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
    # Tariff deadlines relevant to biofuel (RFS, SRE, LCFS, added 2026-02-24)
    # ==========================================================================
    tariff_query = """
    SELECT deadline_name, deadline_date, renewal_probability
    FROM alt.tariff_deadlines_static
    WHERE is_active = true AND policy_type = 'BIOFUEL'
    ORDER BY deadline_date
    """
    try:
        tariff_df = pd.read_sql(tariff_query, conn)
        if not tariff_df.empty:
            result["biofuel_deadline_count"] = 0
            result["biofuel_renewal_risk"] = 0.0
            for _, row in tariff_df.iterrows():
                deadline = pd.to_datetime(row["deadline_date"])
                mask = (result.index <= deadline) & (
                    result.index >= deadline - pd.Timedelta(days=90)
                )
                result.loc[mask, "biofuel_deadline_count"] += 1
                renewal_prob = row.get("renewal_probability")
                if renewal_prob is None:
                    renewal_prob = 0.5
                result.loc[mask, "biofuel_renewal_risk"] = max(
                    result.loc[mask, "biofuel_renewal_risk"].max(), float(renewal_prob)
                )
    except Exception as e:
        logger.warning(f"Tariff deadlines unavailable: {e}")

    conn.close()

    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]

    # Add news data for BIOFUEL specialist
    news_df = load_news_for_specialist("biofuel", start_date, end_date)
    if not news_df.empty:
        for col in news_df.columns:
            result[col] = news_df.reindex(result.index)[col]

    logger.info(f"BIOFUEL data: {len(result)} rows, {len(result.columns)} columns")
    return result
