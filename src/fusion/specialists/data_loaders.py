"""
Specialist Data Loaders - Each specialist gets its OWN data.

NO SHARED MATRIX. Each specialist loads EXACTLY what it needs.
"""

import os
import pandas as pd
import numpy as np
import psycopg2
from typing import Optional
from datetime import date
import logging

logger = logging.getLogger(__name__)


def get_connection():
    """Get database connection - reads DATABASE_URL lazily to avoid import-time capture."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set - ensure .env is loaded (or env var exported)")
    return psycopg2.connect(database_url)


def load_crush_data(start_date: Optional[date] = None, end_date: Optional[date] = None) -> pd.DataFrame:
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
        wasde_df["col"] = "wasde_" + wasde_df["commodity"].str.replace(" ", "_").str.lower() + "_" + wasde_df["metric"]
        wasde_pivot = wasde_df.pivot(index="trade_date", columns="col", values="value")
        wasde_pivot = wasde_pivot.ffill()
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
        cftc_df = cftc_df.ffill()
        for c in cftc_df.columns:
            result[c] = cftc_df.reindex(result.index)[c]
    
    conn.close()
    
    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]
    
    logger.info(f"CRUSH data: {len(result)} rows, {len(result.columns)} columns")
    return result


def load_china_data(start_date: Optional[date] = None, end_date: Optional[date] = None) -> pd.DataFrame:
    """
    Load ALL data for CHINA specialist.
    
    ZL + HG (copper) + CNY + shipping ETFs + China ETFs.
    """
    conn = get_connection()
    
    # Futures: ZL, HG
    query = """
    SELECT event_date as trade_date, symbol, open, high, low, close, volume
    FROM mkt.futures_1d
    WHERE symbol IN ('ZL', 'HG')
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
    
    # ETFs: FXI, KWEB, BDRY, SBLK
    etf_query = """
    SELECT event_date as trade_date, symbol, open, high, low, close, volume
    FROM mkt.etf_1d
    WHERE symbol IN ('FXI', 'KWEB', 'BDRY', 'SBLK', 'MCHI')
    ORDER BY event_date, symbol
    """
    etf_df = pd.read_sql(etf_query, conn)
    if not etf_df.empty:
        etf_df["trade_date"] = pd.to_datetime(etf_df["trade_date"])
        for col_type in ["close", "open", "high", "low", "volume"]:
            pivot = etf_df.pivot(index="trade_date", columns="symbol", values=col_type)
            pivot.columns = [f"{c.lower()}_{col_type}" for c in pivot.columns]
            for c in pivot.columns:
                result[c] = pivot.reindex(result.index)[c]
    
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
        result["usd_cny"] = fx_df["usd_cny"].reindex(result.index).ffill()
    
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
        result["fred_dexbzus"] = brl_df["fred_dexbzus"].reindex(result.index).ffill()
    
    conn.close()
    
    # DATA QUALITY: Drop sparse ETFs (coverage < 50%)
    MIN_COVERAGE = 0.50
    sparse_symbols = []
    for symbol_prefix in ["bdry", "sblk"]:
        close_col = f"{symbol_prefix}_close"
        if close_col in result.columns:
            coverage = result[close_col].notna().mean()
            if coverage < MIN_COVERAGE:
                # Drop all columns for this symbol
                cols_to_drop = [c for c in result.columns if c.startswith(f"{symbol_prefix}_")]
                result = result.drop(columns=cols_to_drop)
                sparse_symbols.append(symbol_prefix.upper())
    
    if sparse_symbols:
        logger.info(f"  Dropped sparse symbols: {', '.join(sparse_symbols)} (coverage < {MIN_COVERAGE*100:.0f}%)")
    
    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]
    
    logger.info(f"CHINA data: {len(result)} rows, {len(result.columns)} columns")
    return result


def load_energy_data(start_date: Optional[date] = None, end_date: Optional[date] = None) -> pd.DataFrame:
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
    
    logger.info(f"ENERGY data: {len(result)} rows, {len(result.columns)} columns")
    return result


def load_fx_data(start_date: Optional[date] = None, end_date: Optional[date] = None) -> pd.DataFrame:
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
        'DEXBZUS', 'DEXCHUS', 'DEXMXUS', 'DEXCAUS', 'DEXUSAL', 'DEXJPUS', 'DEXKOUS',
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
        pivot = fred_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        pivot = pivot.ffill()
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]
        
        # Log what carry trade series we actually got
        carry_series = ['fred_t10y2y', 'fred_tedrate', 'fred_bamlh0a0hym2', 'fred_ir3tib01cnm156n']
        found = [s for s in carry_series if s in result.columns and result[s].notna().sum() > 0]
        missing = [s for s in carry_series if s not in found]
        if found:
            logger.info(f"FX carry trade series loaded: {found}")
        if missing:
            logger.warning(f"FX carry trade series NOT in database: {missing}")
    
    # DXY
    dxy_query = """
    SELECT event_date as trade_date, close as fred_dxy
    FROM mkt.futures_1d
    WHERE symbol = 'DXY'
    ORDER BY event_date
    """
    dxy_df = pd.read_sql(dxy_query, conn)
    if not dxy_df.empty:
        dxy_df["trade_date"] = pd.to_datetime(dxy_df["trade_date"])
        dxy_df.set_index("trade_date", inplace=True)
        result["fred_dxy"] = dxy_df["fred_dxy"].reindex(result.index).ffill()
    
    conn.close()
    
    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]
    
    logger.info(f"FX data: {len(result)} rows, {len(result.columns)} columns")
    return result


def load_fed_data(start_date: Optional[date] = None, end_date: Optional[date] = None) -> pd.DataFrame:
    """
    Load ALL data for FED specialist.
    
    ZL + full yield curve + NFCI + breakevens.
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
    
    # Yield curve data from rates
    rates_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.rates_1d
    WHERE series_id IN (
        'FEDFUNDS', 'DGS3MO', 'DGS1', 'DGS2', 'DGS5', 'DGS7', 'DGS10', 'DGS20', 'DGS30',
        'T10Y2Y', 'T10Y3M', 'T10YIE', 'T5YIE', 'TEDRATE'
    )
    ORDER BY event_date, series_id
    """
    rates_df = pd.read_sql(rates_query, conn)
    if not rates_df.empty:
        rates_df["trade_date"] = pd.to_datetime(rates_df["trade_date"])
        pivot = rates_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        pivot = pivot.ffill()
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]
    
    # Financial conditions from vol_indices (NFCI, ANFCI, STLFSI4, credit spreads)
    vol_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.vol_indices_1d
    WHERE series_id IN ('NFCI', 'ANFCI', 'STLFSI4', 'BAMLH0A0HYM2', 'BAMLC0A0CM')
    ORDER BY event_date, series_id
    """
    vol_df = pd.read_sql(vol_query, conn)
    if not vol_df.empty:
        vol_df["trade_date"] = pd.to_datetime(vol_df["trade_date"])
        pivot = vol_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        pivot = pivot.ffill()
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]
    
    conn.close()
    
    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]
    
    logger.info(f"FED data: {len(result)} rows, {len(result.columns)} columns")
    return result


def load_volatility_data(start_date: Optional[date] = None, end_date: Optional[date] = None) -> pd.DataFrame:
    """
    Load ALL data for VOLATILITY specialist.
    
    ZL + full VIX complex + OVX + GVZ + VVIX.
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
    result["returns_1d"] = result["close"].pct_change()
    
    # ALL vol indices
    vol_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.vol_indices_1d
    WHERE series_id IN ('VIXCLS', 'VXVCLS', 'OVXCLS', 'GVZCLS', 'VXEEMCLS', 'VXFXICLS', 'EVZCLS', 'VXGSCLS')
    ORDER BY event_date, series_id
    """
    vol_df = pd.read_sql(vol_query, conn)
    if not vol_df.empty:
        vol_df["trade_date"] = pd.to_datetime(vol_df["trade_date"])
        pivot = vol_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        # Alias VXVCLS -> VIX3M (specialist expects fred_vix3mcls)
        if "fred_vxvcls" in pivot.columns:
            pivot["fred_vix3mcls"] = pivot["fred_vxvcls"]
        pivot = pivot.ffill()
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]
    
    conn.close()
    
    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]
    
    logger.info(f"VOLATILITY data: {len(result)} rows, {len(result.columns)} columns")
    return result


def load_substitutes_data(start_date: Optional[date] = None, end_date: Optional[date] = None) -> pd.DataFrame:
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
            result["sunflower_close"] = pivot["PSUNOUSDM"].reindex(result.index).ffill()
        if "PROILUSDM" in pivot.columns:
            result["rapeseed_close"] = pivot["PROILUSDM"].reindex(result.index).ffill()
    
    conn.close()
    
    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]
    
    logger.info(f"SUBSTITUTES data: {len(result)} rows, {len(result.columns)} columns")
    return result


def load_palm_data(start_date: Optional[date] = None, end_date: Optional[date] = None) -> pd.DataFrame:
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
        pivot = pivot.ffill()
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]
    
    conn.close()
    
    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]
    
    logger.info(f"PALM data: {len(result)} rows, {len(result.columns)} columns")
    return result


def load_biofuel_data(start_date: Optional[date] = None, end_date: Optional[date] = None) -> pd.DataFrame:
    """
    Load ALL data for BIOFUEL specialist.
    
    ZL + HO + RIN prices + LCFS credits.
    """
    conn = get_connection()
    
    # Futures: ZL, HO
    query = """
    SELECT event_date as trade_date, symbol, open, high, low, close, volume
    FROM mkt.futures_1d
    WHERE symbol IN ('ZL', 'HO', 'CL', 'ZM')
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
    if not rin_df.empty:
        rin_df["trade_date"] = pd.to_datetime(rin_df["trade_date"])
        pivot = rin_df.pivot(index="trade_date", columns="rin_type", values="price")
        pivot.columns = [f"rin_{c.lower()}_price" for c in pivot.columns]
        pivot = pivot.ffill()
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]
    
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
            result["lcfs_credit"] = lcfs_df["lcfs_credit"].reindex(result.index).ffill()
    except:
        pass
    
    conn.close()
    
    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]
    
    logger.info(f"BIOFUEL data: {len(result)} rows, {len(result.columns)} columns")
    return result


def load_tariff_data(start_date: Optional[date] = None, end_date: Optional[date] = None) -> pd.DataFrame:
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
        pivot = pivot.ffill()
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
        result["fred_chnmainlandtpu"] = china_df["value"].reindex(result.index).ffill()
    
    conn.close()
    
    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]
    
    logger.info(f"TARIFF data: {len(result)} rows, {len(result.columns)} columns")
    return result


def load_trump_effect_data(start_date: Optional[date] = None, end_date: Optional[date] = None) -> pd.DataFrame:
    """
    Load ALL data for TRUMP_EFFECT specialist.
    
    ZL + HG + FXI + KWEB + VIX + EPU.
    """
    conn = get_connection()
    
    # Futures: ZL, HG
    query = """
    SELECT event_date as trade_date, symbol, open, high, low, close, volume
    FROM mkt.futures_1d
    WHERE symbol IN ('ZL', 'HG')
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
    
    # ETFs: FXI, KWEB
    etf_query = """
    SELECT event_date as trade_date, symbol, open, high, low, close, volume
    FROM mkt.etf_1d
    WHERE symbol IN ('FXI', 'KWEB')
    ORDER BY event_date, symbol
    """
    etf_df = pd.read_sql(etf_query, conn)
    if not etf_df.empty:
        etf_df["trade_date"] = pd.to_datetime(etf_df["trade_date"])
        for col_type in ["close", "open", "high", "low", "volume"]:
            pivot = etf_df.pivot(index="trade_date", columns="symbol", values=col_type)
            pivot.columns = [f"{c.lower()}_{col_type}" for c in pivot.columns]
            for c in pivot.columns:
                result[c] = pivot.reindex(result.index)[c]
    
    # VIX + EPU
    vol_query = """
    SELECT event_date as trade_date, series_id, value
    FROM (
        SELECT event_date, series_id, value FROM econ.vol_indices_1d
        UNION ALL
        SELECT event_date, series_id, value FROM econ.activity_1d
    ) t
    WHERE series_id IN ('VIXCLS', 'USEPUINDXD', 'USEPUINDXM', 'EPUTRADE', 'EMVTRADEPOLEMV', 'CHNMAINLANDTPU')
    ORDER BY event_date, series_id
    """
    vol_df = pd.read_sql(vol_query, conn)
    if not vol_df.empty:
        vol_df["trade_date"] = pd.to_datetime(vol_df["trade_date"])
        pivot = vol_df.pivot(index="trade_date", columns="series_id", values="value")
        pivot.columns = [f"fred_{c.lower()}" for c in pivot.columns]
        pivot = pivot.ffill()
        for c in pivot.columns:
            result[c] = pivot.reindex(result.index)[c]
    
    # CNY
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
        result["usd_cny"] = fx_df["usd_cny"].reindex(result.index).ffill()
    
    conn.close()
    
    if start_date:
        result = result[result.index >= pd.Timestamp(start_date)]
    if end_date:
        result = result[result.index <= pd.Timestamp(end_date)]
    
    logger.info(f"TRUMP_EFFECT data: {len(result)} rows, {len(result.columns)} columns")
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


def load_specialist_data(bucket: str, start_date: Optional[date] = None, end_date: Optional[date] = None) -> pd.DataFrame:
    """Load data for a specific specialist bucket."""
    if bucket not in DATA_LOADERS:
        raise ValueError(f"Unknown bucket: {bucket}")
    return DATA_LOADERS[bucket](start_date, end_date)
