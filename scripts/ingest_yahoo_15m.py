#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Yahoo Finance 15-Minute Intraday Ingestion (ZL Only)

Ingests 15-minute OHLCV bars for ZL (soybean oil) ONLY into analytics.intraday_prices.
This is the procurement target - no other instruments need intraday tracking.

Data Flow:
    Yahoo (ZL=F) → analytics.intraday_prices → Dashboard

    ❌ NEVER: training.*, features.*, any ML tables
    ✅ Dashboard real-time charts
    ✅ Intraday price displays

Usage:
    # Default: fetch last 7 days of 15m bars
    python scripts/ingest_yahoo_15m.py

    # More history (max 60 days per Yahoo)
    python scripts/ingest_yahoo_15m.py --days-back 30

    # Dry run
    python scripts/ingest_yahoo_15m.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Optional

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

# Constants - ZL ONLY
SYMBOL = "ZL"
YAHOO_TICKER = "ZL=F"
TARGET_TABLE = "analytics.intraday_prices"
SOURCE_VALUE = "yahoo"

# Yahoo limits: 15m data only available for last 60 days
YAHOO_15M_LIMIT_DAYS = 60


def get_connection():
    """Get PostgreSQL connection."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(database_url)


def get_previous_close(conn) -> Optional[float]:
    """Get the most recent daily close for ZL from raw.market_futures_1d."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT close FROM raw.market_futures_1d 
                WHERE symbol = 'ZL' 
                ORDER BY event_date DESC 
                LIMIT 1
            """
            )
            row = cur.fetchone()
            return float(row[0]) if row else None
    except Exception as e:
        logger.warning(f"Could not fetch previous close: {e}")
        return None


def download_zl_15m(days_back: int = 7) -> pd.DataFrame:
    """Download 15-minute OHLCV data for ZL from Yahoo Finance.

    Returns DataFrame with columns: timestamp, open, high, low, close, volume
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed. Run: pip install yfinance")
        sys.exit(1)

    # Enforce Yahoo's limit
    if days_back > YAHOO_15M_LIMIT_DAYS:
        logger.warning(
            f"Yahoo limits 15m data to {YAHOO_15M_LIMIT_DAYS} days. Capping."
        )
        days_back = YAHOO_15M_LIMIT_DAYS

    logger.info(f"Downloading {YAHOO_TICKER} (15m bars, {days_back} days back)")

    # Calculate period
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)

    # Download 15-minute bars
    ticker = yf.Ticker(YAHOO_TICKER)
    df = ticker.history(
        start=start.isoformat(),
        end=end.isoformat(),
        interval="15m",
        auto_adjust=False,
        actions=False,
    )

    if df is None or df.empty:
        logger.warning("No data returned from Yahoo")
        return pd.DataFrame()

    # Process into flat format
    df = df.reset_index()

    # Handle datetime column name
    date_col = "Datetime" if "Datetime" in df.columns else df.columns[0]

    rows = []
    for _, row in df.iterrows():
        try:
            ts = pd.to_datetime(row[date_col])
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")

            o = float(row["Open"]) if pd.notna(row.get("Open")) else None
            h = float(row["High"]) if pd.notna(row.get("High")) else None
            low_val = float(row["Low"]) if pd.notna(row.get("Low")) else None
            c = float(row["Close"]) if pd.notna(row.get("Close")) else None
            v = int(row["Volume"]) if pd.notna(row.get("Volume")) else 0

            # Skip rows without price data
            if c is None:
                continue

            rows.append(
                {
                    "timestamp": ts,
                    "open": o,
                    "high": h,
                    "low": low_val,
                    "close": c,
                    "volume": v,
                }
            )
        except Exception as e:
            logger.warning(f"Error processing row: {e}")
            continue

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    logger.info(f"Downloaded {len(result)} bars for {SYMBOL}")
    return result


def upsert_to_analytics(
    conn, df: pd.DataFrame, previous_close: Optional[float], dry_run: bool = False
) -> int:
    """Upsert 15m data directly to analytics.intraday_prices.

    Matches existing schema:
    - symbol, timestamp, open, high, low, close, volume
    - previous_close, change, change_percent (computed)
    - day_high, day_low (computed per day)
    - source, created_at
    """
    if df.empty:
        return 0

    # Add computed columns
    df["symbol"] = SYMBOL
    df["source"] = SOURCE_VALUE
    df["previous_close"] = previous_close

    # Compute change from previous close
    if previous_close:
        df["change"] = df["close"] - previous_close
        df["change_percent"] = (df["change"] / previous_close) * 100
    else:
        df["change"] = None
        df["change_percent"] = None

    # Compute day_high and day_low per trading day
    df["trade_date"] = df["timestamp"].dt.date
    day_stats = (
        df.groupby("trade_date").agg({"high": "max", "low": "min"}).reset_index()
    )
    day_stats.columns = ["trade_date", "day_high", "day_low"]
    df = df.merge(day_stats, on="trade_date", how="left")

    if dry_run:
        logger.info(f"[DRY RUN] Would upsert {len(df)} bars to {TARGET_TABLE}")
        logger.info(f"  Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        logger.info(f"  Previous close: {previous_close}")
        return 0

    # Upsert matching existing schema (no id column - it's serial)
    upsert_sql = """
        INSERT INTO analytics.intraday_prices
            (symbol, timestamp, open, high, low, close, volume, 
             previous_close, change, change_percent, day_high, day_low, 
             source, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, timestamp)
        DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            previous_close = EXCLUDED.previous_close,
            change = EXCLUDED.change,
            change_percent = EXCLUDED.change_percent,
            day_high = EXCLUDED.day_high,
            day_low = EXCLUDED.day_low,
            created_at = EXCLUDED.created_at
    """

    now = datetime.now(timezone.utc)
    records = [
        (
            row["symbol"],
            row["timestamp"],
            row["open"],
            row["high"],
            row["low"],
            row["close"],
            row["volume"],
            row["previous_close"],
            row["change"],
            row["change_percent"],
            row["day_high"],
            row["day_low"],
            row["source"],
            now,
        )
        for _, row in df.iterrows()
    ]

    with conn.cursor() as cur:
        execute_batch(cur, upsert_sql, records, page_size=1000)

    conn.commit()
    logger.info(f"Upserted {len(records)} bars to {TARGET_TABLE}")
    return len(records)


def main():
    parser = argparse.ArgumentParser(
        description="Ingest Yahoo Finance 15-minute data for ZL (analytics only)"
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=7,
        help=f"Days to look back (max {YAHOO_15M_LIMIT_DAYS})",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without writing"
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ZINC-FUSION-V15: Yahoo 15m Intraday Ingestion (ZL Only)")
    logger.info("=" * 60)
    logger.info(f"Symbol: {SYMBOL} ({YAHOO_TICKER})")
    logger.info(f"Days back: {args.days_back}")
    logger.info(f"Target: {TARGET_TABLE}")
    logger.info("⚠️  ANALYTICS ONLY - This data never touches training!")
    if args.dry_run:
        logger.info("*** DRY RUN MODE ***")

    # Connect
    conn = get_connection()
    try:
        # Get previous close for change calculations
        previous_close = get_previous_close(conn)
        if previous_close:
            logger.info(f"Previous daily close: ${previous_close:.4f}")
        else:
            logger.warning(
                "Could not fetch previous close - change fields will be null"
            )

        # Download data
        df = download_zl_15m(args.days_back)

        if df.empty:
            logger.warning("No data to ingest")
            return 0

        # Upsert directly to analytics
        upserted = upsert_to_analytics(conn, df, previous_close, args.dry_run)

        logger.info(f"✅ Complete: {upserted} bars processed")

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
