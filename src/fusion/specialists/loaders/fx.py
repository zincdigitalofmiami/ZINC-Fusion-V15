"""Specialist-specific data loader."""

import logging
from datetime import date

import pandas as pd

from .common import get_connection, load_news_for_specialist

logger = logging.getLogger(__name__)


def load_fx_data(
    start_date: date | None = None, end_date: date | None = None
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
        logger.info("  Databento FX futures loaded: 6E, 6J, 6B, 6A, 6C, 6M, 6S, 6L")

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
