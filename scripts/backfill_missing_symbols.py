#!/usr/bin/env python3
"""
Backfill missing market symbols from local CSV files.

Data sources (from Downloads folder):
- RS (Canola): ICEUS_DLY_RS1!, 1D.csv - 3,512 rows (2011-2025)
- DX (Dollar Index): CAPITALCOM_DXY, 1D.csv - 2,590 rows (2015-2025)
- VX (VIX): TVC_VIX, 1D.csv - 2,590 rows (2015-2025)

Usage:
    python scripts/backfill_missing_symbols.py --dry-run
    python scripts/backfill_missing_symbols.py
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# File mappings: symbol -> (csv_path, date_col, close_col)
BACKFILL_SOURCES = {
    "RS": {
        "path": os.path.expanduser("~/Downloads/ICEUS_DLY_RS1!, 1D.csv"),
        "date_col": "time",
        "description": "ICE Canola Futures",
    },
    "DX": {
        "path": os.path.expanduser("~/Downloads/CAPITALCOM_DXY, 1D.csv"),
        "date_col": "time",
        "description": "US Dollar Index",
    },
    "VX": {
        "path": os.path.expanduser("~/Downloads/VIXCLS.csv"),
        "date_col": "observation_date",
        "value_col": "VIXCLS",  # Single value column, not OHLC
        "description": "CBOE VIX Index (FRED)",
    },
    "GVZ": {
        "path": os.path.expanduser("~/Downloads/CBOE_DLY_GVZ, 1D.csv"),
        "date_col": "time",
        "description": "CBOE Gold VIX",
    },
    "ZC": {
        "path": os.path.expanduser("~/Downloads/CBOT_ZC1!, 1D.csv"),
        "date_col": "time",
        "description": "CBOT Corn Futures",
    },
    "ZS": {
        "path": os.path.expanduser("~/Downloads/CBOT_ZS1!, 1D (1).csv"),
        "date_col": "time",
        "description": "CBOT Soybean Futures",
    },
}


def get_postgres_connection():
    """Get Postgres connection using DATABASE_URL."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        # Try the Prisma Postgres URL
        database_url = "postgres://d687a7ec267e124a21607a1e5dd9a89d60c9a122d219e499e32f3eee42a858c0:sk_NLg8ZV3VJ61FPM0F_QHMe@db.prisma.io:5432/postgres?sslmode=require"
    return psycopg2.connect(database_url)


def load_csv_data(symbol: str, config: dict) -> pd.DataFrame:
    """Load and normalize CSV data for a symbol."""
    path = config["path"]
    date_col = config["date_col"]
    value_col = config.get("value_col")  # For single-value files like VIXCLS

    if not os.path.exists(path):
        logger.error(f"File not found: {path}")
        return pd.DataFrame()

    df = pd.read_csv(path)
    logger.info(f"  Loaded {len(df):,} rows from {Path(path).name}")

    # Normalize column names to lowercase
    df.columns = df.columns.str.lower()

    # Parse date column
    df["as_of_date"] = pd.to_datetime(df[date_col.lower()], errors="coerce")
    df = df.dropna(subset=["as_of_date"])
    df["as_of_date"] = df["as_of_date"].dt.date

    result = pd.DataFrame()
    result["as_of_date"] = df["as_of_date"]
    result["symbol"] = symbol

    # Handle single-value files (like FRED VIXCLS)
    if value_col:
        value_col_lower = value_col.lower()
        if value_col_lower in df.columns:
            val = pd.to_numeric(df[value_col_lower], errors="coerce")
            result["open"] = val
            result["high"] = val
            result["low"] = val
            result["close"] = val
            result["volume"] = 0
        else:
            logger.error(f"Value column {value_col} not found in {path}")
            return pd.DataFrame()
    else:
        # Standardize OHLCV columns
        col_mapping = {
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "last": "close",  # Some sources use 'last' instead of 'close'
            "volume": "volume",
        }

        for target, source in col_mapping.items():
            if source in df.columns:
                result[target] = pd.to_numeric(df[source], errors="coerce")
            elif target != "volume":  # Volume can be missing
                result[target] = None

        # Ensure volume exists (set to 0 if missing)
        if "volume" not in result.columns:
            result["volume"] = 0

    result["source"] = "backfill_csv"
    result["ingested_at"] = datetime.now()

    # Drop duplicates, keep last
    result = result.drop_duplicates(subset=["as_of_date"], keep="last")
    result = result.sort_values("as_of_date")

    return result


def get_existing_dates(conn, symbol: str) -> set:
    """Get existing dates for a symbol in the database."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT as_of_date FROM raw.market_futures_1d
            WHERE symbol = %s
            """,
            (symbol,),
        )
        return {row[0] for row in cur.fetchall()}


def insert_data(conn, df: pd.DataFrame, dry_run: bool = False) -> int:
    """Insert data into market_futures_1d table."""
    if df.empty:
        return 0

    symbol = df["symbol"].iloc[0]
    existing_dates = get_existing_dates(conn, symbol)

    # Filter to only new rows
    df = df[~df["as_of_date"].isin(existing_dates)]

    if df.empty:
        logger.info(f"  No new rows to insert for {symbol}")
        return 0

    if dry_run:
        logger.info(f"  [DRY RUN] Would insert {len(df):,} new rows for {symbol}")
        logger.info(f"    Date range: {df['as_of_date'].min()} to {df['as_of_date'].max()}")
        return len(df)

    # Prepare data for insertion
    columns = ["as_of_date", "symbol", "open", "high", "low", "close", "volume", "source", "ingested_at"]
    values = [
        (
            row["as_of_date"],
            row["symbol"],
            row.get("open"),
            row.get("high"),
            row.get("low"),
            row.get("close"),
            row.get("volume", 0),
            row.get("source", "backfill_csv"),
            row.get("ingested_at", datetime.now()),
        )
        for _, row in df.iterrows()
    ]

    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO raw.market_futures_1d (as_of_date, symbol, open, high, low, close, volume, source, ingested_at)
            VALUES %s
            ON CONFLICT (as_of_date, symbol) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                source = EXCLUDED.source,
                ingested_at = EXCLUDED.ingested_at
            """,
            values,
            page_size=500,
        )

    conn.commit()
    logger.info(f"  Inserted {len(df):,} rows for {symbol}")
    return len(df)


def main():
    parser = argparse.ArgumentParser(description="Backfill missing market symbols")
    parser.add_argument("--dry-run", action="store_true", help="Preview without inserting")
    parser.add_argument("--symbol", type=str, default="all", help="Specific symbol or 'all'")
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("BACKFILL MISSING MARKET SYMBOLS")
    logger.info("=" * 70)
    logger.info(f"Dry run: {args.dry_run}")

    conn = get_postgres_connection()

    symbols = [args.symbol] if args.symbol != "all" else list(BACKFILL_SOURCES.keys())
    total_inserted = 0

    for symbol in symbols:
        if symbol not in BACKFILL_SOURCES:
            logger.warning(f"Unknown symbol: {symbol}")
            continue

        config = BACKFILL_SOURCES[symbol]
        logger.info(f"\nProcessing {symbol} ({config['description']})...")

        # Check current database state
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*), MIN(as_of_date)::text, MAX(as_of_date)::text
                FROM raw.market_futures_1d WHERE symbol = %s
                """,
                (symbol,),
            )
            db_count, db_min, db_max = cur.fetchone()
            logger.info(f"  Database: {db_count:,} rows ({db_min or 'N/A'} to {db_max or 'N/A'})")

        # Load CSV data
        df = load_csv_data(symbol, config)
        if df.empty:
            continue

        logger.info(f"  CSV: {len(df):,} rows ({df['as_of_date'].min()} to {df['as_of_date'].max()})")

        # Insert data
        inserted = insert_data(conn, df, args.dry_run)
        total_inserted += inserted

    logger.info("\n" + "=" * 70)
    logger.info(f"BACKFILL COMPLETE: {total_inserted:,} total rows {'would be ' if args.dry_run else ''}inserted")
    logger.info("=" * 70)

    conn.close()


if __name__ == "__main__":
    main()
