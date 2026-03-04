"""Specialist-specific data loader."""

import logging
from datetime import date

import pandas as pd

from .common import get_connection, load_news_for_specialist

logger = logging.getLogger(__name__)


def load_trump_effect_data(
    start_date: date | None = None, end_date: date | None = None
) -> pd.DataFrame:
    """
    Load ALL data for TRUMP_EFFECT specialist — THICK DATA VERSION.

    Enhanced 2026-01-30: Added Fed rates, financial conditions, credit spreads,
    FX futures, treasury futures, tariff deadlines, Trump Effect features.

    Data Sources:
    - Futures: ZL, HG + FX futures (6E, 6J, 6M, 6B, 6A, 6C) + Treasury (ZB, ZN, ZF)
    - No ETF inputs (runtime ETF dependency removed)
    - Volatility: VIX, OVXCLS, GVZCLS, VXVCLS
    - Uncertainty: All EPU indices + Financial Conditions (NFCI, ANFCI, STLFSI4)
    - Credit: BAMLC0A0CM, BAMLH0A0HYM2
    - Fed Rates: DFF, DGS2, DGS10, T10Y2Y, SOFR
    - FX Rates: All major USD pairs
    - Tariff: alt.tariff_deadlines_static
    - Trump Features: training.specialist_features_trump_effect
    """
    conn = get_connection()

    # ==========================================================================
    # 1. Futures: ZL, HG + FX + Treasuries
    # ==========================================================================
    futures_query = """
    SELECT event_date as trade_date, symbol, open, high, low, close, volume, open_interest
    FROM mkt.futures_1d
    WHERE symbol IN (
        'ZL', 'HG',
        '6E', '6J', '6M', '6B', '6A', '6C', '6N', '6S', '6L',
        'ZB', 'ZN', 'ZF', 'ZT',
        'VX', 'ES', 'NQ'
    )
    ORDER BY event_date, symbol
    """
    df = pd.read_sql(futures_query, conn)
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    result = df.pivot(index="trade_date", columns="symbol", values="close")
    result.columns = [f"{c.lower()}_close" for c in result.columns]
    result = result.reset_index()
    if "zl_close" in result.columns:
        result["close"] = result["zl_close"]
    result.set_index("trade_date", inplace=True)

    for col_type in ["open", "high", "low", "volume", "open_interest"]:
        try:
            pivot = df.pivot(index="trade_date", columns="symbol", values=col_type)
            pivot.columns = [f"{c.lower()}_{col_type}" for c in pivot.columns]
            for c in pivot.columns:
                result[c] = pivot[c].values
        except Exception:
            pass  # Skip if column doesn't exist

    # ==========================================================================
    # 2. Volatility + Uncertainty + Financial Conditions (ALL INDICES)
    # ==========================================================================
    vol_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.vol_indices_1d
    WHERE series_id IN (
        -- Core volatility
        'VIXCLS', 'OVXCLS', 'GVZCLS', 'VXVCLS',
        -- EPU/EMV trade & policy (existing)
        'USEPUINDXD', 'USEPUINDXM', 'EPUTRADE', 'EMVTRADEPOLEMV',
        -- Financial conditions (existing)
        'NFCI', 'ANFCI', 'STLFSI4',
        'BAMLC0A0CM', 'BAMLH0A0HYM2',
        -- EMV policy trackers — Trump signature domains (added 2026-02-24)
        'EMVAGRPOLICY',      -- Agricultural policy uncertainty
        'EMVFISCALPOL',      -- Fiscal policy uncertainty
        'EMVGOVTSPEND',      -- Government spending uncertainty
        'EMVTAXESEMV',       -- Tax policy uncertainty
        'EMVNATSEC',         -- National security uncertainty
        'EMVIMMIGRATION',    -- Immigration uncertainty
        'EMVELECTGOVRN',     -- Election/governance uncertainty
        'EMVMONETARYPOL',    -- Monetary policy uncertainty
        'EMVMACROINFLATION', -- Inflation uncertainty
        'EMVMACROINTEREST',  -- Interest rate uncertainty
        'EMVENRGYENVREG',    -- Energy/environment regulation
        'EMVOVERALLEMV',     -- Overall EMV (composite)
        -- EPU subcategories (monthly)
        'EPUFISCAL', 'EPUTAXES', 'EPUNATSEC', 'EPUFINREG', 'EPUGOVTSPEND',
        -- International uncertainty
        'EUEPUINDXM',        -- EU economic policy uncertainty
        'CHNMAINLANDEPU',    -- China economic policy uncertainty
        -- Daily tracker
        'INFECTDISEMVTRACKD'  -- Infectious disease EMV
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
    # 3. Fed Rates: DFF, DGS2, DGS10, T10Y2Y, SOFR
    # ==========================================================================
    rates_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.rates_1d
    WHERE series_id IN (
        'DFF', 'DGS2', 'DGS10', 'T10Y2Y', 'SOFR',
        'DFEDTARL', 'DFEDTARU', 'FEDFUNDS'
    )
    ORDER BY event_date, series_id
    """
    rates_df = pd.read_sql(rates_query, conn)
    if not rates_df.empty:
        rates_df["trade_date"] = pd.to_datetime(rates_df["trade_date"])
        pivot = rates_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        # No forward-fill (policy)
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

    # ==========================================================================
    # 4. FX Rates + Dollar Indices: All major USD pairs + trade-weighted USD indices
    # ==========================================================================
    fx_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.rates_1d
    WHERE series_id IN (
        'DEXBZUS', 'ARGCCUSMA02STM', 'DEXMXUS', 'DEXCHUS', 'DEXJPUS', 'DEXUSEU',
        'DEXCAUS', 'DEXKOUS', 'DEXTAUS', 'DEXINUS',
        'DTWEXAFEGS', 'DTWEXBGS', 'DTWEXEMEGS'
    )
    ORDER BY event_date, series_id
    """
    fx_df = pd.read_sql(fx_query, conn)
    if not fx_df.empty:
        fx_df["trade_date"] = pd.to_datetime(fx_df["trade_date"])
        pivot = fx_df.pivot(index="trade_date", columns="series_id", values="value")
        # Map to friendly names
        rename_map = {
            "DEXBZUS": "usd_brl",
            "ARGCCUSMA02STM": "usd_ars",
            "DEXMXUS": "usd_mxn",
            "DEXCHUS": "usd_cny",
            "DEXJPUS": "usd_jpy",
            "DEXUSEU": "eur_usd",
            "DEXCAUS": "usd_cad",
            "DEXKOUS": "usd_krw",
            "DEXTAUS": "usd_twd",
            "DEXINUS": "usd_inr",
            "DTWEXAFEGS": "dxy_afe",
            "DTWEXBGS": "dxy_broad",
            "DTWEXEMEGS": "dxy_eme",
        }
        pivot.columns = [rename_map.get(c, f"fred_{c.lower()}") for c in pivot.columns]
        # No forward-fill (policy)
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

    # ==========================================================================
    # 5. China Activity/Trade Policy
    # ==========================================================================
    china_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.activity_1d
    WHERE series_id IN ('CHNMAINLANDTPU', 'EXPCH', 'IMPCH', 'china_pmi')
    ORDER BY event_date, series_id
    """
    china_df = pd.read_sql(china_query, conn)
    if not china_df.empty:
        china_df["trade_date"] = pd.to_datetime(china_df["trade_date"])
        pivot = china_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        # No forward-fill (policy)
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

    # ==========================================================================
    # 6. Trump Effect Features (from specialist payload)
    # ==========================================================================
    trump_query = """
    SELECT
           as_of_date as trade_date,
           NULLIF(features->>'eo_count_7d', '')::double precision AS eo_count_7d,
           NULLIF(features->>'eo_count_30d', '')::double precision AS eo_count_30d,
           NULLIF(features->>'proclamation_count_7d', '')::double precision AS proclamation_count_7d,
           NULLIF(features->>'proclamation_count_30d', '')::double precision AS proclamation_count_30d,
           NULLIF(features->>'total_actions_7d', '')::double precision AS total_actions_7d,
           NULLIF(features->>'total_actions_30d', '')::double precision AS total_actions_30d,
           NULLIF(features->>'avg_sentiment_7d', '')::double precision AS avg_sentiment_7d,
           NULLIF(features->>'avg_sentiment_30d', '')::double precision AS avg_sentiment_30d,
           NULLIF(features->>'action_velocity', '')::double precision AS action_velocity,
           NULLIF(features->>'action_acceleration', '')::double precision AS action_acceleration,
           NULLIF(features->>'weighted_action_score', '')::double precision AS weighted_action_score
    FROM training.specialist_features_trump_effect
    ORDER BY as_of_date
    """
    trump_df = pd.read_sql(trump_query, conn)
    if not trump_df.empty:
        trump_df["trade_date"] = pd.to_datetime(trump_df["trade_date"])
        trump_df.set_index("trade_date", inplace=True)
        for c in trump_df.columns:
            result[f"trump_{c}"] = trump_df[c].reindex(result.index)

    # ==========================================================================
    # 7. Options Greeks (VIX IV, ZL IV, FX IV where available)
    # ==========================================================================
    greeks_query = """
    SELECT event_date as trade_date, underlying,
           AVG(implied_volatility) as avg_iv,
           AVG(delta) as avg_delta,
           AVG(iv_skew) as avg_skew
    FROM mkt.options_greeks_1d  -- sqlref: ignore
    WHERE underlying IN ('VIX', 'ZL', '6E', '6J', '6M', '6B')
    GROUP BY event_date, underlying
    ORDER BY event_date, underlying
    """
    try:
        greeks_df = pd.read_sql(greeks_query, conn)
    except Exception:
        greeks_df = pd.DataFrame()
    if not greeks_df.empty:
        greeks_df["trade_date"] = pd.to_datetime(greeks_df["trade_date"])
        for metric in ["avg_iv", "avg_delta", "avg_skew"]:
            try:
                pivot = greeks_df.pivot(
                    index="trade_date", columns="underlying", values=metric
                )
                pivot.columns = [
                    f"{c.lower()}_opt_{metric.replace('avg_', '')}"
                    for c in pivot.columns
                ]
                for c in pivot.columns:
                    result[c] = pivot.reindex(result.index)[c]
            except Exception:
                pass

    # ==========================================================================
    # 8. Executive Orders / Presidential Documents (daily count)
    # ==========================================================================
    eo_query = """
    SELECT event_date as trade_date,
           COUNT(*) FILTER (WHERE document_type = 'Presidential Document') as eo_count,
           COUNT(*) FILTER (WHERE document_type = 'Rule') as rule_count,
           COUNT(*) FILTER (WHERE document_type = 'Proposed Rule') as proposed_rule_count,
           COUNT(*) as total_legislation
    FROM alt.legislation_1d
    GROUP BY event_date
    ORDER BY event_date
    """
    eo_df = pd.read_sql(eo_query, conn)
    if not eo_df.empty:
        eo_df["trade_date"] = pd.to_datetime(eo_df["trade_date"])
        eo_df.set_index("trade_date", inplace=True)
        for c in eo_df.columns:
            result[f"legis_{c}"] = eo_df[c].reindex(result.index).fillna(0)

    # ==========================================================================
    # 9. Tariff Deadlines (expand to daily indicators)
    # ==========================================================================
    tariff_query = """
    SELECT deadline_name, deadline_date, days_to_expiry, renewal_probability, is_active
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
    except Exception as e:
        logger.warning(f"Tariff deadlines unavailable: {e}")

    conn.close()

    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]

    # Add news data for TRUMP_EFFECT specialist
    news_df = load_news_for_specialist("trump_effect", start_date, end_date)
    if not news_df.empty:
        for col in news_df.columns:
            result[col] = news_df.reindex(result.index)[col]

    logger.info(
        f"TRUMP_EFFECT data (THICK): {len(result)} rows, {len(result.columns)} columns"
    )
    return result
