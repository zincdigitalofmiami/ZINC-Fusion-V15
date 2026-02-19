"""
Specialist Data Loaders - Each specialist gets its OWN data.

NO SHARED MATRIX. Each specialist loads EXACTLY what it needs.

IMPORTANT: ALL specialists now automatically include news/alt data articles
tagged for them from ANY table with specialist_tags column.
"""

import logging
from datetime import date
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from fusion.db.connection import get_write_connection

logger = logging.getLogger(__name__)

# Allowlist of valid specialist buckets (Big-11 + extras)
VALID_SPECIALIST_BUCKETS = frozenset(
    {
        "crush",
        "china",
        "energy",
        "fx",
        "fed",
        "volatility",
        "substitutes",
        "palm",
        "biofuel",
        "tariff",
        "trump_effect",
    }
)

# Allowlist of schemas that may contain specialist-tagged news tables
_ALLOWED_NEWS_SCHEMAS = frozenset({"alt", "econ", "features"})


def load_news_for_specialist(
    specialist_bucket: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    """
    Load ALL news articles tagged for this specialist from ALL tables.

    Scans all tables with specialist_tags column and returns articles
    where this specialist is in the tags array.

    New table structure (2026-01-31):
    - alt.econ_news_event: FRED blog (Federal Reserve economic research)
    - alt.executive_actions_event: WhiteHouse presidential documents
    - alt.policy_news_event: Other policy sources (ICE, CBP, AEI, FarmDoc)
    - alt.profarmer_news_event: ProFarmer premium ag news
    - alt.legislation_1d: Federal Register legislation

    Returns:
        DataFrame indexed by trade_date with:
        - news_article_count: count of articles for this specialist on this date
        - news_headline_text: concatenated headlines for NLP features
    """
    # Validate specialist_bucket against allowlist
    if specialist_bucket not in VALID_SPECIALIST_BUCKETS:
        logger.warning(
            f"Invalid specialist_bucket '{specialist_bucket}', "
            f"must be one of {sorted(VALID_SPECIALIST_BUCKETS)}"
        )
        return pd.DataFrame(
            columns=["trade_date", "news_article_count", "news_headline_text"]
        ).set_index("trade_date")

    conn = get_connection()

    # Dynamically find all tables with specialist_tags
    tables_query = """
    SELECT DISTINCT table_schema || '.' || table_name as full_name
    FROM information_schema.columns
    WHERE column_name = 'specialist_tags'
      AND table_schema IN ('alt', 'econ', 'features')
      AND table_name NOT IN ('news_1d')  -- Skip deprecated table
    """
    tables_df = pd.read_sql(tables_query, conn)

    all_news = []

    for full_name in tables_df["full_name"]:
        try:
            # Validate schema.table from DB against allowlist
            schema, table = full_name.split(".")
            if schema not in _ALLOWED_NEWS_SCHEMAS:
                logger.warning(f"Skipping table in disallowed schema: {full_name}")
                continue

            # Use parameterized query for column discovery
            cols_query = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
              AND column_name IN ('event_date', 'published_at', 'headline',
                                  'content', 'summary')
            """
            cols_df = pd.read_sql(cols_query, conn, params=[schema, table])
            available = set(cols_df["column_name"])

            # Determine date column (allowlisted values only)
            date_col = "event_date" if "event_date" in available else "published_at"
            if date_col not in available:
                continue

            # Build query with allowlisted column names and parameterized bucket
            _ALLOWED_COLS = {"event_date", "published_at", "headline", "summary"}
            select_parts = [f"{date_col} as trade_date"]
            for col in ("headline", "summary"):
                if col in available and col in _ALLOWED_COLS:
                    select_parts.append(col)

            # table name comes from information_schema (trusted) + schema allowlist
            query = f"""
            SELECT {", ".join(select_parts)}
            FROM {full_name}
            WHERE %s = ANY(specialist_tags)
            """

            df = pd.read_sql(query, conn, params=[specialist_bucket])
            if not df.empty:
                df["trade_date"] = pd.to_datetime(df["trade_date"])
                df["source_table"] = full_name
                all_news.append(df)

        except Exception as e:
            logger.warning(f"Could not load from {full_name}: {e}")
            continue

    conn.close()

    if not all_news:
        # Return empty structure
        return pd.DataFrame(
            columns=[
                "trade_date",
                "news_article_count",
                "news_headline_text",
            ]
        ).set_index("trade_date")

    # Combine all sources
    combined = pd.concat(all_news, ignore_index=True)

    # Apply date filters
    if start_date:
        combined = combined[combined["trade_date"] >= pd.Timestamp(start_date)]
    if end_date:
        combined = combined[combined["trade_date"] <= pd.Timestamp(end_date)]

    # Aggregate by date
    agg_dict = {}
    if "headline" in combined.columns:
        agg_dict["headline"] = lambda x: " | ".join(
            [str(h) for h in x if pd.notna(h)][:10]
        )
    if "summary" in combined.columns:
        agg_dict["summary"] = lambda x: " | ".join(
            [str(s) for s in x if pd.notna(s)][:5]
        )
    result = combined.groupby("trade_date").agg(agg_dict)
    result["news_article_count"] = combined.groupby("trade_date").size()

    # Rename
    rename_map = {}
    if "headline" in result.columns:
        rename_map["headline"] = "news_headline_text"
    if "summary" in result.columns:
        rename_map["summary"] = "news_summary_text"

    result = result.rename(columns=rename_map)

    logger.info(
        f"  News for {specialist_bucket}: {len(result)} days, "
        f"{result['news_article_count'].sum():.0f} articles"
    )

    return result


def ffill_with_real_mask(
    series: pd.Series, limit: Optional[int] = None
) -> Tuple[pd.Series, pd.Series]:
    """
    Forward-fill with real observation mask tracking.

    Args:
        series: Time series to forward-fill
        limit: Maximum number of consecutive NaN values to fill

    Returns:
        Tuple of (filled_series, is_real_mask)
        - filled_series: Forward-filled series
        - is_real_mask: Boolean Series (True where raw had data, False where filled)
    """
    # Create mask: True where original data exists, False where NaN
    is_real = series.notna().copy()

    # Apply forward-fill
    if limit is not None:
        filled = series.ffill(limit=limit)
    else:
        filled = series.ffill()

    # is_real mask remains unchanged (True = real, False = filled/NaN)
    return filled, is_real


def get_connection():
    """Get database connection from standardized URL resolution."""
    return get_write_connection()


def load_crush_data(
    start_date: Optional[date] = None, end_date: Optional[date] = None
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


def load_china_data(
    start_date: Optional[date] = None, end_date: Optional[date] = None
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


def load_energy_data(
    start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    """
    Load ALL data for ENERGY specialist.

    ZL + CL + HO + RB + NG + BZ (full petroleum complex).
    """
    conn = get_connection()

    query = """
    SELECT event_date as trade_date, symbol, open, high, low, close, volume
    FROM mkt.futures_1d
    WHERE symbol IN ('ZL', 'CL', 'HO', 'RB', 'NG', 'BZ')
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

    conn.close()

    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]

    # Add news data for ENERGY specialist
    news_df = load_news_for_specialist("energy", start_date, end_date)
    if not news_df.empty:
        for col in news_df.columns:
            result[col] = news_df.reindex(result.index)[col]

    logger.info(f"ENERGY data: {len(result)} rows, {len(result.columns)} columns")
    return result


def load_fx_data(
    start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    """
    Load ALL data for FX specialist.

    ZL + ALL FX pairs from FRED + interest rates + carry trade inputs.

    CARRY TRADE REQUIRED SERIES:
    - T10Y2Y: Yield curve slope (10Y - 2Y spread)
    - TEDRATE: TED spread (3M LIBOR - T-Bill, credit risk)
    - BAMLH0A0HYM2: ICE BofA US High Yield OAS (EM risk proxy)
    - IR3TIB01CNM156N: China 3-Month Interbank Rate
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

    # ALL FRED FX, rates, and CARRY TRADE series
    # NOTE: Query from multiple econ tables to get all required series
    fred_query = """
    SELECT event_date as trade_date, series_id, value
    FROM (
        SELECT event_date, series_id, value FROM econ.rates_1d
        UNION ALL
        SELECT event_date, series_id, value FROM econ.vol_indices_1d
        UNION ALL
        SELECT event_date, series_id, value FROM econ.activity_1d
    ) t
    WHERE series_id IN (
        -- FX Spot Rates (major pairs)
        'DEXBZUS', 'ARGCCUSMA02STM', 'DEXCHUS', 'DEXMXUS', 'DEXCAUS', 'DEXUSAL', 'DEXJPUS', 'DEXKOUS',
        'DEXINUS', 'DEXMAUS', 'DEXTAUS', 'DEXTHUS', 'DEXSIUS', 'DEXHKUS',
        'DEXUSEU', 'DEXUSUK', 'DEXSFUS', 'DEXNOUS', 'DEXSZUS',
        -- Dollar Indices
        'DTWEXBGS', 'DTWEXAFEGS', 'DTWEXEMEGS',
        -- Treasury Rates (yield curve components)
        'FEDFUNDS', 'DGS2', 'DGS10', 'DGS3MO', 'DGS30', 'DGS5', 'DGS7', 'DGS20',
        -- Yield Curve Spreads (CRITICAL for carry trade)
        'T10Y2Y', 'T10Y3M', 'T5YIE', 'T10YIE',
        -- Credit/Risk Spreads (CRITICAL for carry trade proxy)
        'TEDRATE', 'BAMLH0A0HYM2', 'BAMLC0A0CM',
        -- Financial Conditions
        'NFCI', 'VIXCLS',
        -- Foreign Interest Rates (for direct carry calc)
        'IR3TIB01CNM156N', 'IR3TIB01BRM156N', 'IR3TIB01MXM156N', 'IR3TIB01JPM156N'
    )
    ORDER BY event_date, series_id
    """
    fred_df = pd.read_sql(fred_query, conn)
    if not fred_df.empty:
        fred_df["trade_date"] = pd.to_datetime(fred_df["trade_date"])
        fred_df = fred_df.drop_duplicates(
            subset=["trade_date", "series_id"], keep="last"
        )
        pivot = fred_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        # No forward-fill (policy)
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

        # Log what carry trade series we actually got
        carry_series = [
            "fred_t10y2y",
            "fred_tedrate",
            "fred_bamlh0a0hym2",
            "fred_ir3tib01cnm156n",
        ]
        found = [
            s
            for s in carry_series
            if s in result.columns and result[s].notna().sum() > 0
        ]
        missing = [s for s in carry_series if s not in found]
        if found:
            logger.info(f"FX carry trade series loaded: {found}")
        if missing:
            logger.warning(f"FX carry trade series NOT in database: {missing}")

    # DXY (Dollar Index) - Use 'DX' symbol (Databento), not 'DXY'
    dxy_query = """
    SELECT event_date as trade_date, close as fred_dxy
    FROM mkt.futures_1d
    WHERE symbol = 'DX'
    ORDER BY event_date
    """
    dxy_df = pd.read_sql(dxy_query, conn)
    if not dxy_df.empty:
        dxy_df["trade_date"] = pd.to_datetime(dxy_df["trade_date"])
        dxy_df.set_index("trade_date", inplace=True)
        # NO FFILL - missing data is missing
        result["fred_dxy"] = dxy_df["fred_dxy"].reindex(result.index)

    # DATABENTO FX FUTURES - CME currency futures with volume/OI
    # These complement FRED spot rates with tradeable futures data
    fx_futures_query = """
    SELECT event_date as trade_date, symbol, close, volume, open_interest
    FROM mkt.futures_1d
    WHERE symbol IN ('6E', '6J', '6B', '6A', '6C', '6M', '6S', '6L')
    ORDER BY event_date, symbol
    """
    fx_futures_df = pd.read_sql(fx_futures_query, conn)
    if not fx_futures_df.empty:
        fx_futures_df["trade_date"] = pd.to_datetime(fx_futures_df["trade_date"])
        # Pivot to wide format - one column per symbol
        for col_type in ["close", "volume", "open_interest"]:
            if col_type in fx_futures_df.columns:
                pivot = fx_futures_df.pivot(
                    index="trade_date", columns="symbol", values=col_type
                )
                # Name columns: fx_6e_close, fx_6e_volume, etc.
                pivot.columns = [
                    f"fx_{sym.lower()}_{col_type}" for sym in pivot.columns
                ]
                # NO FFILL - raw data only
                for c in pivot.columns:
                    result[c] = pivot.reindex(result.index)[c]
        logger.info(f"  Databento FX futures loaded: 6E, 6J, 6B, 6A, 6C, 6M, 6S, 6L")

    conn.close()

    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]

    # Add news data for FX specialist
    news_df = load_news_for_specialist("fx", start_date, end_date)
    if not news_df.empty:
        for col in news_df.columns:
            result[col] = news_df.reindex(result.index)[col]

    logger.info(f"FX data: {len(result)} rows, {len(result.columns)} columns")
    return result


def load_fed_data(
    start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    """
    Load ALL data for FED specialist.

    ZL + full yield curve + NFCI + breakevens.

    NO FFILL - missing data is missing. Weekly series (NFCI) will have NaN on non-release days.

    Data sources:
    - econ.rates_1d: DFF (daily fed funds), Treasury yields, yield curve spreads
    - econ.inflation_1d: Breakeven inflation (T5YIE, T10YIE), TIPS real yields (DFII*)
    - econ.vol_indices_1d: NFCI, credit spreads (BAMLH0A0HYM2)
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
    # 1. RATES (econ.rates_1d) - Daily Treasury yields and Fed Funds
    # ==========================================================================
    # NOTE: Using DFF (daily) instead of FEDFUNDS (monthly, 61d stale)
    # NOTE: Removed T10YIE, T5YIE (in inflation_1d), TEDRATE (discontinued 2022)
    rates_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.rates_1d
    WHERE series_id IN (
        'DFF',      -- Daily Fed Funds (replaces monthly FEDFUNDS)
        'DGS1MO', 'DGS3MO', 'DGS6MO',  -- Short-term Treasury
        'DGS1', 'DGS2', 'DGS5', 'DGS7', 'DGS10', 'DGS20', 'DGS30',  -- Full curve
        'T10Y2Y', 'T10Y3M',  -- Yield curve spreads
        'SOFR'      -- Secured overnight rate
    )
    ORDER BY event_date, series_id
    """
    rates_df = pd.read_sql(rates_query, conn)
    if not rates_df.empty:
        rates_df["trade_date"] = pd.to_datetime(rates_df["trade_date"])
        pivot = rates_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        # NO FFILL - raw data only
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

        # Log data quality
        for c in pivot.columns:
            coverage = result[c].notna().sum() / len(result) * 100
            last_valid = result[c].last_valid_index()
            logger.debug(f"  {c}: {coverage:.1f}% coverage, last: {last_valid}")

    # ==========================================================================
    # 2. INFLATION EXPECTATIONS (econ.inflation_1d) - Breakevens and TIPS yields
    # ==========================================================================
    inflation_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.inflation_1d
    WHERE series_id IN (
        'T5YIE', 'T10YIE', 'T5YIFR',  -- Breakeven inflation expectations
        'DFII5', 'DFII7', 'DFII10', 'DFII20', 'DFII30'  -- TIPS real yields
    )
    ORDER BY event_date, series_id
    """
    inflation_df = pd.read_sql(inflation_query, conn)
    if not inflation_df.empty:
        inflation_df["trade_date"] = pd.to_datetime(inflation_df["trade_date"])
        pivot = inflation_df.pivot(
            index="trade_date", columns="series_id", values="value"
        )
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        # NO FFILL - raw data only
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

        logger.info(f"  Inflation expectations loaded: {list(pivot.columns)}")

    # ==========================================================================
    # 3. FINANCIAL CONDITIONS (econ.vol_indices_1d) - NFCI, credit spreads
    # ==========================================================================
    # NOTE: NFCI is weekly (released Thursdays) - will have NaN on non-release days
    # NOTE: BAMLH0A0HYM2 (HY spread) replaces discontinued TEDRATE
    vol_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.vol_indices_1d
    WHERE series_id IN (
        'NFCI', 'ANFCI', 'STLFSI4',  -- Financial stress (weekly)
        'BAMLH0A0HYM2', 'BAMLC0A0CM'  -- Credit spreads (daily)
    )
    ORDER BY event_date, series_id
    """
    vol_df = pd.read_sql(vol_query, conn)
    if not vol_df.empty:
        vol_df["trade_date"] = pd.to_datetime(vol_df["trade_date"])
        pivot = vol_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        # NO FFILL - weekly NFCI will have NaN on non-release days (this is correct)
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

        # Log weekly series coverage (expected to be ~20% for weekly data)
        if "fred_nfci" in result.columns:
            nfci_coverage = result["fred_nfci"].notna().sum() / len(result) * 100
            logger.info(
                f"  NFCI coverage: {nfci_coverage:.1f}% (weekly release - expected ~20%)"
            )

    conn.close()

    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]

    # Add news data for FED specialist
    news_df = load_news_for_specialist("fed", start_date, end_date)
    if not news_df.empty:
        for col in news_df.columns:
            result[col] = news_df.reindex(result.index)[col]

    # Log final data quality summary
    rate_cols = [
        c for c in result.columns if c.startswith("fred_dgs") or c == "fred_dff"
    ]
    inflation_cols = [
        c for c in result.columns if "yie" in c or "dfii" in c or "yifr" in c
    ]
    vol_cols = [
        c for c in result.columns if "nfci" in c or "baml" in c or "stlfsi" in c
    ]

    logger.info(f"FED data: {len(result)} rows, {len(result.columns)} columns")
    logger.info(f"  Rates: {len(rate_cols)} series")
    logger.info(f"  Inflation: {len(inflation_cols)} series")
    logger.info(f"  Vol/Credit: {len(vol_cols)} series")

    return result


def load_volatility_data(
    start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    """
    Load ALL data for VOLATILITY specialist.

    ZL + full VIX complex + OVX + GVZ + VXEEM.

    NO FFILL - missing data is missing.

    Data sources:
    - mkt.futures_1d: ZL for returns
    - econ.vol_indices_1d: VIX complex, commodity vol, EM vol

    NOTE: Discontinued series removed:
    - EVZCLS (Euro FX vol) - discontinued March 2025
    - VXFXICLS (China FXI vol) - discontinued Feb 2022
    - VIX9DCLS - not available in FRED
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
    # No implicit fill across NaN close rows.
    result["returns_1d"] = result["close"].pct_change(fill_method=None)

    # ==========================================================================
    # VOL INDICES (econ.vol_indices_1d) - Only active series
    # ==========================================================================
    # NOTE: Removed discontinued series:
    # - EVZCLS (Euro FX vol) - last update 2025-03-11
    # - VXFXICLS (China FXI vol) - last update 2022-02-11
    # - VXGSCLS - not available
    vol_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.vol_indices_1d
    WHERE series_id IN (
        'VIXCLS',   -- VIX spot (30-day implied)
        'VXVCLS',   -- VIX 3-month (for term structure)
        'OVXCLS',   -- Crude oil volatility
        'GVZCLS',   -- Gold volatility
        'VXEEMCLS'  -- EM volatility
    )
    ORDER BY event_date, series_id
    """
    vol_df = pd.read_sql(vol_query, conn)
    if not vol_df.empty:
        vol_df["trade_date"] = pd.to_datetime(vol_df["trade_date"])
        pivot = vol_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]

        # Alias VXVCLS -> VIX3M (specialist expects fred_vix3mcls for term structure)
        if "fred_vxvcls" in pivot.columns:
            pivot["fred_vix3mcls"] = pivot["fred_vxvcls"]

        # NO FFILL - raw data only
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]

        # Log data quality
        for series in ["fred_vixcls", "fred_vxvcls", "fred_ovxcls", "fred_gvzcls"]:
            if series in result.columns:
                coverage = result[series].notna().sum() / len(result) * 100
                last_valid = result[series].last_valid_index()
                logger.debug(
                    f"  {series}: {coverage:.1f}% coverage, last: {last_valid}"
                )

    # ==========================================================================
    # ETFs (Databento): GLD, SLV for precious metals regime
    # ==========================================================================
    etf_query = """
    SELECT event_date as trade_date, symbol, close
    FROM mkt.etf_1d
    WHERE symbol IN ('GLD', 'SLV')
    ORDER BY event_date, symbol
    """
    etf_df = pd.read_sql(etf_query, conn)
    if not etf_df.empty:
        etf_df["trade_date"] = pd.to_datetime(etf_df["trade_date"])
        etf_pivot = etf_df.pivot(index="trade_date", columns="symbol", values="close")
        etf_pivot.columns = [f"{c.lower()}_close" for c in etf_pivot.columns]
        for c in etf_pivot.columns:
            result[c] = etf_pivot.reindex(result.index)[c]

    conn.close()

    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]

    # Add news data for VOLATILITY specialist
    news_df = load_news_for_specialist("volatility", start_date, end_date)
    if not news_df.empty:
        for col in news_df.columns:
            result[col] = news_df.reindex(result.index)[col]

    # Log summary
    vol_cols = [c for c in result.columns if c.startswith("fred_")]
    logger.info(f"VOLATILITY data: {len(result)} rows, {len(result.columns)} columns")
    logger.info(f"  Vol indices: {vol_cols}")

    return result


def load_substitutes_data(
    start_date: Optional[date] = None, end_date: Optional[date] = None
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


def load_palm_data(
    start_date: Optional[date] = None, end_date: Optional[date] = None
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


def load_biofuel_data(
    start_date: Optional[date] = None, end_date: Optional[date] = None
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


def load_tariff_data(
    start_date: Optional[date] = None, end_date: Optional[date] = None
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


def load_trump_effect_data(
    start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    """
    Load ALL data for TRUMP_EFFECT specialist — THICK DATA VERSION.

    Enhanced 2026-01-30: Added Fed rates, financial conditions, credit spreads,
    FX futures, treasury futures, tariff deadlines, Trump Effect features.

    Data Sources:
    - Futures: ZL, HG + FX futures (6E, 6J, 6M, 6B, 6A, 6C) + Treasury (ZB, ZN, ZF)
    - ETFs: FXI, KWEB, VXX, UUP, MCHI
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
    # 2. ETFs (Databento): FXI, KWEB, MCHI, UUP, SPY, QQQ
    # ==========================================================================
    etf_query = """
    SELECT event_date as trade_date, symbol, close
    FROM mkt.etf_1d
    WHERE symbol IN ('FXI', 'KWEB', 'MCHI', 'UUP', 'SPY', 'QQQ')
    ORDER BY event_date, symbol
    """
    etf_df = pd.read_sql(etf_query, conn)
    if not etf_df.empty:
        etf_df["trade_date"] = pd.to_datetime(etf_df["trade_date"])
        etf_pivot = etf_df.pivot(index="trade_date", columns="symbol", values="close")
        etf_pivot.columns = [f"{c.lower()}_close" for c in etf_pivot.columns]
        for c in etf_pivot.columns:
            result[c] = etf_pivot.reindex(result.index)[c]

    # ==========================================================================
    # 3. Volatility + Uncertainty + Financial Conditions (ALL INDICES)
    # ==========================================================================
    vol_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.vol_indices_1d
    WHERE series_id IN (
        'VIXCLS', 'OVXCLS', 'GVZCLS', 'VXVCLS',
        'USEPUINDXD', 'USEPUINDXM', 'EPUTRADE', 'EMVTRADEPOLEMV',
        'NFCI', 'ANFCI', 'STLFSI4',
        'BAMLC0A0CM', 'BAMLH0A0HYM2'
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
    # 4. Fed Rates: DFF, DGS2, DGS10, T10Y2Y, SOFR
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
    # 5. FX Rates + Dollar Indices: All major USD pairs + trade-weighted USD indices
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
    # 6. China Activity/Trade Policy
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
    # 7. Trump Effect Features (from specialist payload)
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
    # 8. Options Greeks (VIX IV, ZL IV, FX IV where available)
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
    # 9. Executive Orders / Presidential Documents (daily count)
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
    # 10. Tariff Deadlines (expand to daily indicators)
    # ==========================================================================
    tariff_query = """
    SELECT deadline_name, deadline_date, days_to_expiry, renewal_probability, is_active
    FROM alt.tariff_deadlines_static
    WHERE is_active = true
    ORDER BY deadline_date
    """
    tariff_df = pd.read_sql(tariff_query, conn)
    if not tariff_df.empty:
        # Create daily tariff risk indicator
        result["tariff_deadline_count"] = 0
        result["tariff_renewal_risk"] = 0.0
        for _, row in tariff_df.iterrows():
            deadline = pd.to_datetime(row["deadline_date"])
            # Mark days leading up to deadline
            mask = (result.index <= deadline) & (
                result.index >= deadline - pd.Timedelta(days=90)
            )
            result.loc[mask, "tariff_deadline_count"] += 1
            renewal_prob = row.get("renewal_probability")
            if renewal_prob is None:
                renewal_prob = 0.5
            result.loc[mask, "tariff_renewal_risk"] = max(
                result.loc[mask, "tariff_renewal_risk"].max(), float(renewal_prob)
            )

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


# Registry mapping bucket name to loader function
DATA_LOADERS = {
    "crush": load_crush_data,
    "china": load_china_data,
    "energy": load_energy_data,
    "fx": load_fx_data,
    "fed": load_fed_data,
    "volatility": load_volatility_data,
    "substitutes": load_substitutes_data,
    "palm": load_palm_data,
    "biofuel": load_biofuel_data,
    "tariff": load_tariff_data,
    "trump_effect": load_trump_effect_data,
}


def load_specialist_data(
    bucket: str, start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    """Load data for a specific specialist bucket."""
    if bucket not in DATA_LOADERS:
        raise ValueError(f"Unknown bucket: {bucket}")
    df = DATA_LOADERS[bucket](start_date, end_date)

    # Normalize to ZL trading calendar for all specialists.
    # Some "thick" loaders can introduce dates where non-ZL symbols trade but
    # ZL is missing; those rows inflate coverage and create off-calendar signals.
    if "close" in df.columns:
        df = df[df["close"].notna()]

    if not df.index.is_monotonic_increasing:
        df = df.sort_index()

    return df
