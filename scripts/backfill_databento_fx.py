#!/usr/bin/env python3
"""
Databento FX Futures Historical Backfill

Backfills CME FX futures OHLCV + open interest for Trump Effect specialist.
Covers major USD pairs: 6E, 6J, 6B, 6A, 6C, 6M, 6N, 6S, DX

Usage:
    python scripts/backfill_databento_fx.py [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]

Writes to: mkt.futures_1d (source='databento')

@author Agent3
@date 2026-01-30
"""

import os
import sys
import argparse
import hashlib
from datetime import date, timedelta
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

import databento as db
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
load_dotenv(PROJECT_ROOT / ".env")

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# FX Futures symbols - continuous front month (calendar roll)
# All CME Globex (GLBX.MDP3) FX futures
FX_SYMBOLS = [
    # Major USD pairs (CME)
    {"continuous": "6E.c.0", "canonical": "6E", "name": "EUR/USD", "dataset": "GLBX.MDP3"},
    {"continuous": "6J.c.0", "canonical": "6J", "name": "USD/JPY", "dataset": "GLBX.MDP3"},
    {"continuous": "6B.c.0", "canonical": "6B", "name": "GBP/USD", "dataset": "GLBX.MDP3"},
    {"continuous": "6A.c.0", "canonical": "6A", "name": "AUD/USD", "dataset": "GLBX.MDP3"},
    {"continuous": "6C.c.0", "canonical": "6C", "name": "USD/CAD", "dataset": "GLBX.MDP3"},
    # Emerging market pairs (Trump tariff sensitive)
    {"continuous": "6M.c.0", "canonical": "6M", "name": "MXN/USD", "dataset": "GLBX.MDP3"},
    # Other majors
    {"continuous": "6N.c.0", "canonical": "6N", "name": "NZD/USD", "dataset": "GLBX.MDP3"},
    {"continuous": "6S.c.0", "canonical": "6S", "name": "USD/CHF", "dataset": "GLBX.MDP3"},
    # Brazilian Real (critical for soy trade)
    {"continuous": "6L.c.0", "canonical": "6L", "name": "BRL/USD", "dataset": "GLBX.MDP3"},
    # Chinese Renminbi
    {"continuous": "6R.c.0", "canonical": "6R", "name": "CNH/USD", "dataset": "GLBX.MDP3"},
]

# Default dataset
DATASET = "GLBX.MDP3"


def get_databento_client() -> db.Historical:
    """Get Databento client."""
    if not DATABENTO_API_KEY:
        raise ValueError("DATABENTO_API_KEY not set in .env")
    return db.Historical(key=DATABENTO_API_KEY)


def get_db_connection():
    """Get database connection."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set in .env")
    return psycopg2.connect(DATABASE_URL)


def compute_row_hash(row: dict) -> str:
    """Compute deterministic hash for deduplication."""
    key = f"{row['symbol']}|{row['event_date']}|{row['open']}|{row['high']}|{row['low']}|{row['close']}|{row['volume']}"
    return hashlib.md5(key.encode()).hexdigest()


def fetch_ohlcv(
    client: db.Historical,
    symbol: str,
    start_date: date,
    end_date: date,
    dataset: str = DATASET
) -> pd.DataFrame:
    """Fetch daily OHLCV for a symbol from Databento."""
    print(f"    Fetching OHLCV for {symbol} from {start_date} to {end_date}...")

    try:
        data = client.timeseries.get_range(
            dataset=dataset,
            schema="ohlcv-1d",
            symbols=[symbol],
            stype_in="continuous",
            start=start_date.isoformat(),
            end=end_date.isoformat(),
        )

        df = data.to_df()

        if df.empty:
            print(f"      No OHLCV data returned")
            return pd.DataFrame()

        df = df.reset_index()
        print(f"      Received {len(df)} OHLCV records")
        return df

    except Exception as e:
        print(f"      ERROR: {e}")
        return pd.DataFrame()


def fetch_statistics(
    client: db.Historical,
    symbol: str,
    start_date: date,
    end_date: date,
    dataset: str = DATASET
) -> pd.DataFrame:
    """Fetch daily statistics (open interest) for a symbol."""
    print(f"    Fetching statistics for {symbol}...")

    try:
        data = client.timeseries.get_range(
            dataset=dataset,
            schema="statistics",
            symbols=[symbol],
            stype_in="continuous",
            start=start_date.isoformat(),
            end=end_date.isoformat(),
        )

        df = data.to_df()

        if df.empty:
            print(f"      No statistics data returned")
            return pd.DataFrame()

        df = df.reset_index()

        # Filter for open_interest records (stat_type=9)
        if "stat_type" in df.columns:
            df = df[df["stat_type"] == 9]

        print(f"      Received {len(df)} OI records")
        return df

    except Exception as e:
        print(f"      ERROR: {e}")
        return pd.DataFrame()


def upsert_ohlcv(conn, symbol: str, ohlcv_df: pd.DataFrame) -> int:
    """Upsert OHLCV data into mkt.futures_1d."""
    if ohlcv_df.empty:
        return 0

    rows = []
    for _, row in ohlcv_df.iterrows():
        event_date = pd.to_datetime(row["ts_event"]).date()
        ohlcv_row = {
            "event_date": event_date,
            "symbol": symbol,
            "open": float(row["open"]) if pd.notna(row.get("open")) else None,
            "high": float(row["high"]) if pd.notna(row.get("high")) else None,
            "low": float(row["low"]) if pd.notna(row.get("low")) else None,
            "close": float(row["close"]) if pd.notna(row.get("close")) else None,
            "volume": int(row["volume"]) if pd.notna(row.get("volume")) else None,
        }
        ohlcv_row["row_hash"] = compute_row_hash(ohlcv_row)
        rows.append(ohlcv_row)

    if not rows:
        return 0

    upsert_query = """
    INSERT INTO mkt.futures_1d (event_date, symbol, open, high, low, close, volume, source, ingested_at, row_hash)
    VALUES (%(event_date)s, %(symbol)s, %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, 'databento', NOW(), %(row_hash)s)
    ON CONFLICT (event_date, symbol) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        source = 'databento',
        ingested_at = NOW(),
        row_hash = EXCLUDED.row_hash
    WHERE mkt.futures_1d.source = 'databento' OR mkt.futures_1d.source IS NULL
    """

    cur = conn.cursor()
    execute_batch(cur, upsert_query, rows, page_size=1000)
    conn.commit()
    upserted = cur.rowcount
    cur.close()

    return upserted


def update_open_interest(conn, symbol: str, oi_df: pd.DataFrame) -> int:
    """Update open_interest in mkt.futures_1d for existing rows."""
    if oi_df.empty:
        return 0

    rows = []
    for _, row in oi_df.iterrows():
        event_date = pd.to_datetime(row["ts_event"]).date()

        # Extract OI from quantity or price field
        oi = None
        if "quantity" in row and pd.notna(row["quantity"]):
            # Check if it's the sentinel value (INT64_MAX)
            if row["quantity"] < 9223372036854775807:
                oi = int(row["quantity"])

        if oi is None and "price" in row and pd.notna(row["price"]):
            # Price is in fixed-point format
            if row["price"] < 9223372036854775807:
                oi = int(row["price"] * 1e-9) if row["price"] > 1e6 else int(row["price"])

        if oi is not None and oi > 0:
            rows.append({"event_date": event_date, "symbol": symbol, "open_interest": oi})

    if not rows:
        return 0

    update_query = """
    UPDATE mkt.futures_1d
    SET open_interest = %(open_interest)s,
        ingested_at = NOW()
    WHERE event_date = %(event_date)s
      AND symbol = %(symbol)s
      AND (source = 'databento' OR source IS NULL)
    """

    cur = conn.cursor()
    execute_batch(cur, update_query, rows, page_size=1000)
    conn.commit()
    updated = cur.rowcount
    cur.close()

    return updated


def get_latest_date_in_db(conn, symbol: str) -> date:
    """Get latest date with data for a symbol."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT MAX(event_date) FROM mkt.futures_1d
        WHERE symbol = %s AND source = 'databento'
        """,
        (symbol,)
    )
    result = cur.fetchone()[0]
    cur.close()

    if result is None:
        return date(2015, 1, 1)  # Start from 2015 for FX futures

    return result


def main():
    parser = argparse.ArgumentParser(description="Backfill Databento FX futures data")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--symbols", type=str, nargs="+", help="Specific symbols to fetch")
    args = parser.parse_args()

    print("=" * 70)
    print("DATABENTO FX FUTURES HISTORICAL BACKFILL")
    print("=" * 70)

    client = get_databento_client()
    conn = get_db_connection()

    end_date = date.fromisoformat(args.end_date) if args.end_date else date.today() - timedelta(days=1)

    symbols_to_fetch = FX_SYMBOLS
    if args.symbols:
        symbols_to_fetch = [s for s in FX_SYMBOLS if s["canonical"] in args.symbols]

    total_ohlcv = 0
    total_oi = 0

    for config in symbols_to_fetch:
        symbol = config["continuous"]
        canonical = config["canonical"]
        name = config["name"]
        dataset = config.get("dataset", DATASET)

        print(f"\n[{canonical}] {name} ({symbol})")

        # Determine start date
        if args.start_date:
            start_date = date.fromisoformat(args.start_date)
        else:
            latest = get_latest_date_in_db(conn, canonical)
            start_date = latest + timedelta(days=1) if latest else date(2017, 1, 1)  # Trump 1.0 start

        print(f"  Date range: {start_date} to {end_date}")

        if start_date > end_date:
            print(f"  Up to date, skipping")
            continue

        # Fetch in chunks (max 1 year per request to avoid timeouts)
        current_start = start_date
        while current_start <= end_date:
            chunk_end = min(current_start + timedelta(days=365), end_date)

            # Fetch OHLCV
            ohlcv_df = fetch_ohlcv(client, symbol, current_start, chunk_end, dataset=dataset)
            if not ohlcv_df.empty:
                upserted = upsert_ohlcv(conn, canonical, ohlcv_df)
                total_ohlcv += upserted
                print(f"      Upserted {upserted} OHLCV rows")

            # Fetch statistics (OI)
            oi_df = fetch_statistics(client, symbol, current_start, chunk_end, dataset=dataset)
            if not oi_df.empty:
                updated = update_open_interest(conn, canonical, oi_df)
                total_oi += updated
                print(f"      Updated {updated} rows with OI")

            current_start = chunk_end + timedelta(days=1)

    conn.close()

    print("\n" + "=" * 70)
    print(f"COMPLETE: {total_ohlcv} OHLCV rows, {total_oi} OI updates")
    print("=" * 70)


if __name__ == "__main__":
    main()
