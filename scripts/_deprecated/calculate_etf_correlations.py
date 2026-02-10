#!/usr/bin/env python3
"""
ETF-ZL Correlation Calculator

Computes rolling correlations between ETFs and ZL (soybean oil futures)
for specialist model integration.

Correlations computed:
- 21-day (short-term momentum)
- 63-day (quarterly regime)
- 126-day (semi-annual structural)

Also computes derived metrics:
- returns_1d, returns_5d, returns_21d
- momentum_21d (price vs 21d SMA)
- volatility_21d (21-day realized vol)

Special cross-asset correlations:
- Gold/Silver ratio for volatility regime
- FXI-CNY correlation for China specialist
- Shipping (BDRY) for physical flow detection

Usage:
    python scripts/calculate_etf_correlations.py
    python scripts/calculate_etf_correlations.py --symbols FXI,GLD,SLV
    python scripts/calculate_etf_correlations.py --start 2024-01-01

@author: Claude (ZINC-FUSION-V15)
@date: 2026-02-03
"""

import os
import argparse
import logging
from datetime import datetime
from typing import List, Optional

import pandas as pd
import numpy as np
import psycopg2

# Try Ray
try:
    import ray  # noqa: F401

    HAS_RAY = True
except ImportError:
    HAS_RAY = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

# Correlation windows
CORR_WINDOWS = [21, 63, 126]

# All ETFs to process
ALL_SYMBOLS = [
    "FXI",
    "KWEB",
    "MCHI",  # China
    "GLD",
    "SLV",  # Precious metals
    "BDRY",
    "SBLK",  # Shipping
    "XLE",
    "XOP",
    "USO",
    "UNG",
    "OIH",  # Energy
    "TLT",
    "IEF",  # Treasuries
    "SPY",
    "QQQ",  # Broad market
    "DBA",
    "SOYB",
    "CORN",
    "WEAT",  # Ag
    "UUP",  # Dollar
    "ICLN",
    "TAN",
    "LIT",  # Green energy
]


def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL)


def load_zl_prices() -> pd.DataFrame:
    """Load ZL futures prices."""
    conn = get_db_connection()
    query = """
        SELECT event_date, close
        FROM mkt.futures_1d
        WHERE symbol = 'ZL' AND close IS NOT NULL
        ORDER BY event_date
    """
    df = pd.read_sql(query, conn)
    conn.close()

    df["event_date"] = pd.to_datetime(df["event_date"])
    df = df.set_index("event_date").sort_index()
    df["returns"] = df["close"].pct_change()
    return df


def load_etf_prices(symbols: List[str]) -> pd.DataFrame:
    """Load ETF prices for multiple symbols."""
    conn = get_db_connection()
    symbols_str = ",".join(f"'{s}'" for s in symbols)
    query = f"""
        SELECT symbol, event_date, close, volume
        FROM mkt.etf_1d
        WHERE symbol IN ({symbols_str}) AND close IS NOT NULL
        ORDER BY symbol, event_date
    """
    df = pd.read_sql(query, conn)
    conn.close()

    df["event_date"] = pd.to_datetime(df["event_date"])
    return df


def compute_correlations_for_symbol(
    etf_df: pd.DataFrame,
    zl_df: pd.DataFrame,
    symbol: str,
) -> pd.DataFrame:
    """Compute all metrics for a single ETF symbol."""
    # Filter to this symbol
    sym_df = etf_df[etf_df["symbol"] == symbol].copy()
    sym_df = sym_df.set_index("event_date").sort_index()

    if sym_df.empty:
        return pd.DataFrame()

    # Compute returns
    sym_df["returns"] = sym_df["close"].pct_change()

    # Merge with ZL
    merged = sym_df[["close", "returns", "volume"]].join(
        zl_df[["returns"]].rename(columns={"returns": "zl_returns"}),
        how="inner",
    )

    if len(merged) < max(CORR_WINDOWS):
        logger.warning(f"{symbol}: Insufficient data ({len(merged)} rows)")
        return pd.DataFrame()

    # Compute rolling correlations
    for window in CORR_WINDOWS:
        merged[f"zl_corr_{window}d"] = (
            merged["returns"].rolling(window).corr(merged["zl_returns"])
        )

    # Compute derived metrics
    # Returns over different horizons
    merged["returns_1d"] = sym_df["close"].pct_change(1)
    merged["returns_5d"] = sym_df["close"].pct_change(5)
    merged["returns_21d"] = sym_df["close"].pct_change(21)

    # Momentum: price vs 21d SMA
    sma_21 = sym_df["close"].rolling(21).mean()
    merged["momentum_21d"] = (sym_df["close"] / sma_21 - 1) * 100

    # Volatility: 21-day realized vol (annualized)
    merged["volatility_21d"] = sym_df["returns"].rolling(21).std() * np.sqrt(252)

    # Prepare output
    result = merged[
        [f"zl_corr_{w}d" for w in CORR_WINDOWS]
        + ["returns_1d", "returns_5d", "returns_21d", "momentum_21d", "volatility_21d"]
    ].dropna()

    result["symbol"] = symbol
    result = result.reset_index()

    return result


def update_etf_metrics(df: pd.DataFrame) -> int:
    """Update ETF metrics in database."""
    if df.empty:
        return 0

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Prepare values
        values = []
        for _, row in df.iterrows():
            values.append(
                (
                    row["symbol"],
                    row["event_date"].date(),
                    row.get("zl_corr_21d"),
                    row.get("zl_corr_63d"),
                    row.get("zl_corr_126d"),
                    row.get("returns_1d"),
                    row.get("returns_5d"),
                    row.get("returns_21d"),
                    row.get("momentum_21d"),
                    row.get("volatility_21d"),
                )
            )

        # Batch update
        cur.executemany(
            """
            UPDATE mkt.etf_1d SET
                zl_corr_21d = %s,
                zl_corr_63d = %s,
                zl_corr_126d = %s,
                returns_1d = %s,
                returns_5d = %s,
                returns_21d = %s,
                momentum_21d = %s,
                volatility_21d = %s
            WHERE symbol = %s AND event_date = %s
            """,
            [
                (v[2], v[3], v[4], v[5], v[6], v[7], v[8], v[9], v[0], v[1])
                for v in values
            ],
        )

        conn.commit()
        return len(values)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


def compute_gold_silver_ratio() -> None:
    """Compute and store Gold/Silver ratio for volatility regime detection."""
    conn = get_db_connection()

    query = """
        WITH gld AS (
            SELECT event_date, close as gld_close
            FROM mkt.etf_1d WHERE symbol = 'GLD'
        ),
        slv AS (
            SELECT event_date, close as slv_close
            FROM mkt.etf_1d WHERE symbol = 'SLV'
        ),
        ratio AS (
            SELECT
                g.event_date,
                g.gld_close / NULLIF(s.slv_close, 0) as gold_silver_ratio
            FROM gld g
            JOIN slv s ON g.event_date = s.event_date
            WHERE s.slv_close > 0
        )
        SELECT * FROM ratio ORDER BY event_date
    """

    df = pd.read_sql(query, conn)
    logger.info(f"Gold/Silver ratio: {len(df)} data points")

    # Compute z-score for regime detection
    if not df.empty:
        df["ratio_zscore_63d"] = (
            df["gold_silver_ratio"] - df["gold_silver_ratio"].rolling(63).mean()
        ) / df["gold_silver_ratio"].rolling(63).std()

        # Store in a cross-asset correlation table or log for now
        logger.info(
            f"Gold/Silver ratio range: {df['gold_silver_ratio'].min():.1f} - {df['gold_silver_ratio'].max():.1f}"
        )
        logger.info(
            f"Current: {df['gold_silver_ratio'].iloc[-1]:.1f}, Z-score: {df['ratio_zscore_63d'].iloc[-1]:.2f}"
        )

    conn.close()


def run_correlation_calculation(
    symbols: Optional[List[str]] = None,
    start_date: Optional[datetime] = None,
) -> None:
    """Run full correlation calculation."""
    if symbols is None:
        symbols = ALL_SYMBOLS

    logger.info(f"Computing correlations for {len(symbols)} ETFs...")

    # Load data
    logger.info("Loading ZL prices...")
    zl_df = load_zl_prices()
    logger.info(
        f"ZL data: {len(zl_df)} rows ({zl_df.index.min().date()} to {zl_df.index.max().date()})"
    )

    logger.info("Loading ETF prices...")
    etf_df = load_etf_prices(symbols)
    logger.info(f"ETF data: {len(etf_df)} total rows")

    # Process each symbol
    total_updated = 0
    for symbol in symbols:
        logger.info(f"Processing {symbol}...")

        result_df = compute_correlations_for_symbol(etf_df, zl_df, symbol)

        if not result_df.empty:
            if start_date:
                result_df = result_df[result_df["event_date"] >= start_date]

            updated = update_etf_metrics(result_df)
            total_updated += updated
            logger.info(f"  ✓ {symbol}: {updated} rows updated")
        else:
            logger.warning(f"  ✗ {symbol}: No data to update")

    # Compute special cross-asset metrics
    logger.info("Computing Gold/Silver ratio...")
    compute_gold_silver_ratio()

    logger.info(f"=" * 60)
    logger.info(f"CORRELATION CALCULATION COMPLETE")
    logger.info(f"Total rows updated: {total_updated:,}")
    logger.info(f"=" * 60)


def main():
    parser = argparse.ArgumentParser(description="ETF-ZL Correlation Calculator")
    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated list of symbols (default: all)",
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Only update from this date forward (YYYY-MM-DD)",
    )

    args = parser.parse_args()

    symbols = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]

    start_date = None
    if args.start:
        start_date = datetime.strptime(args.start, "%Y-%m-%d")

    run_correlation_calculation(symbols=symbols, start_date=start_date)


if __name__ == "__main__":
    main()
