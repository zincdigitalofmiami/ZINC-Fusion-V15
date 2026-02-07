#!/usr/bin/env python3
"""
Backfill mkt.fx_1d from Databento CME FX Futures.

Pulls continuous front-month FX futures and converts to spot-equivalent rates.
Stores in mkt.fx_1d with standardized pair naming (EURUSD, USDJPY, etc.)

The 30 FX Universe:
- 10 CME FX Futures (from Databento): 6E, 6J, 6B, 6C, 6A, 6S, 6N, 6M, 6L, 6Z
- 11 FRED pairs (existing script): DXY indices, USDKRW, USDSGD, etc.
- 9 Additional FRED pairs: USDINR, USDTHB, USDTWD, etc.

This script handles the Databento portion (10 pairs).

Usage:
    python scripts/backfill_fx_databento.py
    python scripts/backfill_fx_databento.py --start 2010-01-01
    python scripts/backfill_fx_databento.py --pair EURUSD
    python scripts/backfill_fx_databento.py --dry-run
"""

import os
import sys
import argparse
import hashlib
from datetime import datetime, date, timedelta
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)
if not DATABENTO_API_KEY:
    print("ERROR: DATABENTO_API_KEY not set")
    sys.exit(1)

import databento as db

DATASET = "GLBX.MDP3"

# CME FX Futures -> Standard Pair Naming
# Note: CME quotes some pairs inverted vs market convention
FX_FUTURES = [
    # Symbol, Pair Name, Invert (True if CME quotes USD/XXX but we want XXX/USD)
    {"symbol": "6E", "pair": "EURUSD", "invert": False},   # EUR/USD - already correct
    {"symbol": "6J", "pair": "USDJPY", "invert": True},    # CME: JPY/USD, we want USD/JPY
    {"symbol": "6B", "pair": "GBPUSD", "invert": False},   # GBP/USD - already correct
    {"symbol": "6C", "pair": "USDCAD", "invert": True},    # CME: CAD/USD, we want USD/CAD
    {"symbol": "6A", "pair": "AUDUSD", "invert": False},   # AUD/USD - already correct
    {"symbol": "6S", "pair": "USDCHF", "invert": True},    # CME: CHF/USD, we want USD/CHF
    {"symbol": "6N", "pair": "NZDUSD", "invert": False},   # NZD/USD - already correct
    {"symbol": "6M", "pair": "USDMXN", "invert": True},    # CME: MXN/USD, we want USD/MXN
    {"symbol": "6L", "pair": "USDBRL", "invert": True},    # CME: BRL/USD, we want USD/BRL
    {"symbol": "6Z", "pair": "USDZAR", "invert": True},    # CME: ZAR/USD, we want USD/ZAR
]


def compute_row_hash(pair: str, event_date: str, rate: float) -> str:
    """Compute SHA256 hash for deduplication."""
    data = f"{pair}|{event_date}|{rate}|databento"
    return hashlib.sha256(data.encode()).hexdigest()


def get_max_date(conn, pair: str) -> date | None:
    """Get the latest date for a pair in the database."""
    cur = conn.cursor()
    cur.execute(
        "SELECT MAX(event_date)::date FROM mkt.fx_1d WHERE pair = %s AND source = 'databento'",
        (pair,)
    )
    result = cur.fetchone()
    return result[0] if result and result[0] else None


def fetch_fx_data(client, symbol: str, start_date: date, end_date: date) -> list:
    """Fetch OHLCV data from Databento for one FX future."""
    rows = []

    try:
        data = client.timeseries.get_range(
            dataset=DATASET,
            schema="ohlcv-1d",
            symbols=[f"{symbol}.c.0"],  # Front month continuous
            stype_in="continuous",
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
        )

        for row in data:
            ts = getattr(row, "ts_event", None)
            if ts is None:
                continue

            event_date = datetime.fromtimestamp(ts / 1e9).date()

            # Databento stores prices as integers scaled by 1e9
            close = getattr(row, "close", 0) / 1e9

            if close > 0:
                rows.append({
                    "event_date": event_date,
                    "rate": close,
                })

    except Exception as e:
        print(f"  ERROR fetching {symbol}: {e}")

    return rows


def upsert_fx_data(conn, pair: str, rows: list, invert: bool, dry_run: bool = False) -> tuple:
    """Insert FX data into mkt.fx_1d."""
    if not rows:
        return 0, 0

    inserted = 0
    skipped = 0

    cur = conn.cursor()

    for row in rows:
        rate = row["rate"]

        # Invert if needed (convert from XXX/USD to USD/XXX)
        if invert and rate > 0:
            rate = 1.0 / rate

        event_date = row["event_date"]
        row_hash = compute_row_hash(pair, str(event_date), rate)

        if dry_run:
            print(f"    [DRY RUN] {pair} {event_date}: {rate:.6f}")
            inserted += 1
            continue

        try:
            cur.execute("""
                INSERT INTO mkt.fx_1d (pair, event_date, rate, source, row_hash, ingested_at)
                VALUES (%s, %s, %s, 'databento', %s, NOW())
                ON CONFLICT (pair, event_date) DO UPDATE SET
                    rate = EXCLUDED.rate,
                    source = EXCLUDED.source,
                    row_hash = EXCLUDED.row_hash,
                    ingested_at = NOW()
            """, (pair, event_date, rate, row_hash))
            inserted += 1
        except Exception as e:
            print(f"    ERROR inserting {pair} {event_date}: {e}")
            skipped += 1

    if not dry_run:
        conn.commit()

    return inserted, skipped


def main():
    parser = argparse.ArgumentParser(description="Backfill FX from Databento")
    parser.add_argument("--start", default="2000-01-01", help="Start date (default: 2000-01-01)")
    parser.add_argument("--end", help="End date (default: yesterday)")
    parser.add_argument("--pair", help="Single pair to backfill (e.g., EURUSD)")
    parser.add_argument("--incremental", action="store_true", help="Only fetch new data since last date")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually insert")
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)

    # Filter pairs if specified
    pairs_to_process = FX_FUTURES
    if args.pair:
        pairs_to_process = [p for p in FX_FUTURES if p["pair"] == args.pair.upper()]
        if not pairs_to_process:
            print(f"ERROR: Unknown pair {args.pair}")
            print(f"Available: {[p['pair'] for p in FX_FUTURES]}")
            sys.exit(1)

    print("=" * 60)
    print("DATABENTO FX FUTURES BACKFILL")
    print("=" * 60)
    print(f"Start: {start_date}")
    print(f"End: {end_date}")
    print(f"Pairs: {len(pairs_to_process)}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")
    print()

    client = db.Historical(key=DATABENTO_API_KEY)
    conn = psycopg2.connect(DATABASE_URL)

    total_inserted = 0
    total_skipped = 0

    for fx in pairs_to_process:
        symbol = fx["symbol"]
        pair = fx["pair"]
        invert = fx["invert"]

        # Get start date for this pair
        pair_start = start_date
        if args.incremental:
            max_date = get_max_date(conn, pair)
            if max_date:
                pair_start = max_date + timedelta(days=1)
                if pair_start > end_date:
                    print(f"{pair}: Already up to date (last: {max_date})")
                    continue

        print(f"{pair} ({symbol}): {pair_start} to {end_date}...")

        rows = fetch_fx_data(client, symbol, pair_start, end_date)
        print(f"  Fetched {len(rows)} rows")

        if rows:
            inserted, skipped = upsert_fx_data(conn, pair, rows, invert, args.dry_run)
            total_inserted += inserted
            total_skipped += skipped
            print(f"  Inserted: {inserted}, Skipped: {skipped}")

    conn.close()

    print()
    print("=" * 60)
    print(f"TOTAL: {total_inserted} inserted, {total_skipped} skipped")
    print("=" * 60)


if __name__ == "__main__":
    main()
