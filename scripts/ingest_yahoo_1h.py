#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Yahoo Finance 1-Hour Intraday Ingestion (ZL Only)

Fetches 1-hour OHLCV bars for ZL (soybean oil) into analytics.zl_price_1h.
Yahoo supports up to 730 days (2 years) of hourly data.

Data Flow:
    Yahoo (ZL=F, 1h) → analytics.zl_price_1h → Dashboard Chart

Usage:
    # Default: fetch last 7 days
    python scripts/ingest_yahoo_1h.py

    # Max history (2 years)
    python scripts/ingest_yahoo_1h.py --days-back 730

    # Dry run
    python scripts/ingest_yahoo_1h.py --dry-run
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

SYMBOL = "ZL"
YAHOO_TICKER = "ZL=F"
TARGET_TABLE = "analytics.zl_price_1h"
SOURCE_VALUE = "yahoo"
YAHOO_1H_LIMIT_DAYS = 730  # 2 years


def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(database_url)


def download_zl_1h(days_back: int = 7) -> pd.DataFrame:
    """Download 1-hour OHLCV data for ZL from Yahoo Finance."""
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed. Run: pip install yfinance")
        sys.exit(1)

    if days_back > YAHOO_1H_LIMIT_DAYS:
        logger.warning(f"Yahoo limits 1h data to {YAHOO_1H_LIMIT_DAYS} days. Capping.")
        days_back = YAHOO_1H_LIMIT_DAYS

    logger.info(f"Downloading {YAHOO_TICKER} (1h bars, {days_back} days back)")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)

    ticker = yf.Ticker(YAHOO_TICKER)
    df = ticker.history(
        start=start.strftime('%Y-%m-%d'),
        end=end.strftime('%Y-%m-%d'),
        interval="1h",
        auto_adjust=False,
        actions=False,
    )

    if df is None or df.empty:
        logger.warning("No data returned from Yahoo")
        return pd.DataFrame()

    df = df.reset_index()
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

            if c is None:
                continue

            rows.append({
                "timestamp": ts,
                "open": o,
                "high": h,
                "low": low_val,
                "close": c,
                "volume": v,
            })
        except Exception as e:
            logger.warning(f"Error processing row: {e}")
            continue

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    logger.info(f"Downloaded {len(result)} bars for {SYMBOL}")
    return result


def upsert_to_analytics(conn, df: pd.DataFrame, dry_run: bool = False) -> int:
    """Upsert 1h data to analytics.zl_price_1h."""
    if df.empty:
        return 0

    if dry_run:
        logger.info(f"[DRY RUN] Would upsert {len(df)} bars to {TARGET_TABLE}")
        logger.info(f"  Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        return 0

    upsert_sql = """
        INSERT INTO analytics.zl_price_1h
            (timestamp, open, high, low, close, volume, source, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (timestamp)
        DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            created_at = EXCLUDED.created_at
    """

    now = datetime.now(timezone.utc)
    records = [
        (row["timestamp"], row["open"], row["high"], row["low"], 
         row["close"], row["volume"], SOURCE_VALUE, now)
        for _, row in df.iterrows()
    ]

    with conn.cursor() as cur:
        execute_batch(cur, upsert_sql, records, page_size=1000)

    conn.commit()
    logger.info(f"Upserted {len(records)} bars to {TARGET_TABLE}")
    return len(records)


def main():
    parser = argparse.ArgumentParser(description="Ingest Yahoo 1h data for ZL")
    parser.add_argument("--days-back", type=int, default=7, help=f"Days to look back (max {YAHOO_1H_LIMIT_DAYS})")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ZINC-FUSION-V15: Yahoo 1h Intraday Ingestion (ZL Only)")
    logger.info("=" * 60)
    logger.info(f"Symbol: {SYMBOL} ({YAHOO_TICKER})")
    logger.info(f"Days back: {args.days_back}")
    logger.info(f"Target: {TARGET_TABLE}")
    if args.dry_run:
        logger.info("*** DRY RUN MODE ***")

    conn = get_connection()
    try:
        df = download_zl_1h(args.days_back)
        if df.empty:
            logger.warning("No data to ingest")
            return 0

        upserted = upsert_to_analytics(conn, df, args.dry_run)
        logger.info(f"✅ Complete: {upserted} bars processed")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
