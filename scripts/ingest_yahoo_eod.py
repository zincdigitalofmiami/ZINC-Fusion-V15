#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Yahoo Finance Daily EOD Ingestion

Ingests daily OHLCV data from Yahoo Finance into mkt.futures_1d.
Uses the A+ conditional upsert pattern:
  - NEVER overwrites historical backfill data (pre-2025-12-29)
  - CAN refresh existing Yahoo rows (for late corrections)
  - Fills gaps for new dates

Data Sources:
  - Historical backfill: 1990 → 2025-12-29 (COMPLETE, LOCKED)
  - Yahoo Finance: 2025-12-30 → future (daily updates)

Usage:
    # Default: fetch last 7 days
    python scripts/ingest_yahoo_eod.py

    # Specific date range
    python scripts/ingest_yahoo_eod.py --start 2026-01-01 --end 2026-01-05

    # Dry run (no writes)
    python scripts/ingest_yahoo_eod.py --dry-run

    # Custom ticker subset
    python scripts/ingest_yahoo_eod.py --symbols ZL ZS ZM CL
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

# Constants
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "yahoo_tickers.json"
TARGET_TABLE = "mkt.futures_1d"
SOURCE_VALUE = "yahoo"

# Handoff cutoff - Yahoo only handles dates AFTER this
# Historical backfill completed 2025-12-29, Yahoo topfills from 2025-12-30+
HISTORICAL_CUTOFF = date(2025, 12, 29)


def load_ticker_mapping(config_path: Path) -> Dict[str, str]:
    """Load canonical → Yahoo ticker mapping from JSON config."""
    if not config_path.exists():
        raise FileNotFoundError(f"Ticker config not found: {config_path}")

    with open(config_path, "r") as f:
        config = json.load(f)

    # Flatten all categories into single mapping
    mapping = {}
    for category, tickers in config.items():
        if category.startswith("_"):
            continue  # Skip comments
        if isinstance(tickers, dict):
            for canonical, yahoo in tickers.items():
                if not canonical.startswith("_"):
                    mapping[canonical] = yahoo

    return mapping


def get_connection():
    """Get PostgreSQL connection."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(database_url)


def download_yahoo_data(
    mapping: Dict[str, str],
    start_date: date,
    end_date: date,
    symbols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Download OHLCV data from Yahoo Finance.

    Returns DataFrame with columns: symbol, event_date, open, high, low, close, volume
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed. Run: pip install yfinance")
        sys.exit(1)

    # Filter to requested symbols if specified
    if symbols:
        mapping = {k: v for k, v in mapping.items() if k in symbols}

    if not mapping:
        logger.warning("No symbols to fetch")
        return pd.DataFrame()

    # Build reverse mapping: yahoo → canonical
    yahoo_to_canonical = {v: k for k, v in mapping.items()}
    yahoo_tickers = list(mapping.values())

    logger.info(
        f"Downloading {len(yahoo_tickers)} tickers from Yahoo: {start_date} to {end_date}"
    )

    # yfinance end is exclusive, add 1 day
    end_exclusive = end_date + timedelta(days=1)

    # Download with auto_adjust=False to get raw OHLC
    df = yf.download(
        tickers=yahoo_tickers,
        start=start_date.isoformat(),
        end=end_exclusive.isoformat(),
        interval="1d",
        auto_adjust=False,
        actions=False,
        progress=False,
        group_by="ticker",
        threads=False,
    )

    if df is None or df.empty:
        logger.warning("No data returned from Yahoo")
        return pd.DataFrame()

    # Process into flat format
    rows = []

    if isinstance(df.columns, pd.MultiIndex):
        # Multiple tickers: columns are (ticker, field)
        tickers_in_df = sorted({c[0] for c in df.columns})
        for yahoo_ticker in tickers_in_df:
            if yahoo_ticker not in yahoo_to_canonical:
                continue
            canonical = yahoo_to_canonical[yahoo_ticker]
            sub = df[yahoo_ticker].copy()
            rows.extend(_process_ticker_df(canonical, sub))
    else:
        # Single ticker
        if len(yahoo_tickers) == 1:
            canonical = yahoo_to_canonical[yahoo_tickers[0]]
            rows.extend(_process_ticker_df(canonical, df))

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    logger.info(
        f"Downloaded {len(result)} rows for {result['symbol'].nunique()} symbols"
    )
    return result


def _process_ticker_df(canonical: str, df: pd.DataFrame) -> List[dict]:
    """Process single ticker DataFrame into row dicts."""
    df = df.reset_index()

    # Handle different date column names
    date_col = None
    for col in ["Date", "Datetime", "index"]:
        if col in df.columns:
            date_col = col
            break

    if date_col is None:
        date_col = df.columns[0]

    rows = []
    for _, row in df.iterrows():
        try:
            event_date = pd.to_datetime(row[date_col]).date()
            o = float(row["Open"]) if pd.notna(row.get("Open")) else None
            h = float(row["High"]) if pd.notna(row.get("High")) else None
            l = float(row["Low"]) if pd.notna(row.get("Low")) else None
            c = float(row["Close"]) if pd.notna(row.get("Close")) else None
            v = int(row["Volume"]) if pd.notna(row.get("Volume")) else 0

            # Skip rows without price data
            if c is None:
                continue

            rows.append(
                {
                    "symbol": canonical,
                    "event_date": event_date,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": v,
                }
            )
        except Exception as e:
            logger.warning(f"Error processing row for {canonical}: {e}")
            continue

    return rows


def upsert_data(conn, df: pd.DataFrame, dry_run: bool = False) -> Tuple[int, int]:
    """Upsert data using A+ conditional pattern.

    Returns (inserted, updated) counts.
    """
    if df.empty:
        return 0, 0

    # Filter to only dates after historical cutoff
    df = df[df["event_date"] > HISTORICAL_CUTOFF].copy()

    if df.empty:
        logger.info(f"No rows after cutoff date {HISTORICAL_CUTOFF}")
        return 0, 0

    df["source"] = SOURCE_VALUE
    df["ingested_at"] = datetime.now(timezone.utc)

    if dry_run:
        logger.info(f"[DRY RUN] Would upsert {len(df)} rows")
        for symbol in df["symbol"].unique():
            count = len(df[df["symbol"] == symbol])
            logger.info(f"  {symbol}: {count} rows")
        return 0, 0

    # A+ conditional upsert:
    # - Insert new rows
    # - Update existing Yahoo rows (for corrections)
    # - Skip existing non-Yahoo rows (preserve historical backfill)
    upsert_sql = """
        INSERT INTO mkt.futures_1d
            (event_date, symbol, open, high, low, close, volume, source, ingested_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (event_date, symbol)
        DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            source = EXCLUDED.source,
            ingested_at = EXCLUDED.ingested_at
        WHERE mkt.futures_1d.source = 'yahoo'
    """

    records = [
        (
            row["event_date"],
            row["symbol"],
            row["open"],
            row["high"],
            row["low"],
            row["close"],
            row["volume"],
            row["source"],
            row["ingested_at"],
        )
        for _, row in df.iterrows()
    ]

    with conn.cursor() as cur:
        execute_batch(cur, upsert_sql, records, page_size=1000)
        affected = cur.rowcount

    conn.commit()

    # Note: rowcount for ON CONFLICT doesn't distinguish insert vs update
    logger.info(f"Upserted {len(records)} rows ({affected} affected)")
    return len(records), 0


def main():
    parser = argparse.ArgumentParser(description="Ingest Yahoo Finance daily EOD data")
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Start date (YYYY-MM-DD). Default: 7 days ago",
    )
    parser.add_argument(
        "--end", type=str, default=None, help="End date (YYYY-MM-DD). Default: today"
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=7,
        help="Days to look back if start/end not specified",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Specific symbols to fetch (canonical names)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(CONFIG_PATH),
        help="Path to ticker mapping JSON",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without writing"
    )
    args = parser.parse_args()

    # Compute date range
    today = datetime.now(timezone.utc).date()
    if args.start and args.end:
        start_date = date.fromisoformat(args.start)
        end_date = date.fromisoformat(args.end)
    else:
        end_date = today
        start_date = today - timedelta(days=args.days_back)

    # Enforce cutoff
    if start_date <= HISTORICAL_CUTOFF:
        logger.warning(f"Start date {start_date} is before cutoff {HISTORICAL_CUTOFF}")
        start_date = HISTORICAL_CUTOFF + timedelta(days=1)
        logger.info(f"Adjusted start date to {start_date}")

    logger.info("=" * 60)
    logger.info("ZINC-FUSION-V15: Yahoo EOD Ingestion")
    logger.info("=" * 60)
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info(f"Cutoff (historical backfill ends): {HISTORICAL_CUTOFF}")
    logger.info(f"Source tag: {SOURCE_VALUE}")
    if args.dry_run:
        logger.info("*** DRY RUN MODE ***")

    # Load ticker mapping
    mapping = load_ticker_mapping(Path(args.config))
    logger.info(f"Loaded {len(mapping)} ticker mappings")

    # Download data
    df = download_yahoo_data(mapping, start_date, end_date, args.symbols)

    if df.empty:
        logger.warning("No data to ingest")
        return 0

    # Upsert to database
    conn = get_connection()
    try:
        inserted, updated = upsert_data(conn, df, args.dry_run)
        logger.info(f"✅ Complete: {inserted} rows processed")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
