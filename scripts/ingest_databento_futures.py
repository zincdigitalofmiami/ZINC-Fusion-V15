#!/usr/bin/env python3
"""
DEPRECATED: Use Inngest job 'databento-futures-daily.ts' instead.

This Python script uses ZL.c.0 (calendar roll) while the Inngest job
uses ZL.n.0 (OI-ranked) which is correct for Crush specialist.

The Inngest job runs on Vercel cron and is the canonical daily ingestion.
This script is kept for reference/manual backfill only.

See: frontend/src/inngest/databento-futures-daily.ts

--- Original Docstring ---
Databento futures data ingestion for ZINC-FUSION-V15.

Ingests daily OHLCV + open interest for crush-required symbols:
- ZL (soybean oil)
- ZS (soybeans)
- ZM (soybean meal)
- CL (crude oil)
- HO (heating oil)
- RB (gasoline)

Writes to: mkt.futures_1d (source='databento')
"""

import warnings

warnings.warn(
    "ingest_databento_futures.py is DEPRECATED. "
    "Use Inngest job 'databento-futures-daily.ts' instead.",
    DeprecationWarning,
    stacklevel=2,
)

import os
import sys

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)
from datetime import date, datetime, timedelta
from pathlib import Path
import hashlib

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

# Symbols to ingest (continuous contracts)
SYMBOLS = [
    "ZL.c.0",  # Soybean oil (calendar roll)
    "ZS.c.0",  # Soybeans
    "ZM.c.0",  # Soybean meal
    "CL.c.0",  # Crude oil
    "HO.c.0",  # Heating oil
    "RB.c.0",  # Gasoline
]

DATASET = "GLBX.MDP3"  # CME Globex
SCHEMA = "ohlcv-1d"  # Daily OHLCV


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


def fetch_databento_ohlcv(
    client: db.Historical, symbol: str, start_date: date, end_date: date
) -> pd.DataFrame:
    """
    Fetch daily OHLCV for a symbol from Databento.

    Returns DataFrame with columns:
    - ts_event (datetime)
    - open, high, low, close (float)
    - volume (int)
    """
    print(f"  Fetching {symbol} from {start_date} to {end_date}...")

    try:
        data = client.timeseries.get_range(
            dataset=DATASET,
            schema=SCHEMA,
            symbols=[symbol],
            stype_in="continuous",  # Required for continuous contract symbols
            start=start_date.isoformat(),
            end=end_date.isoformat(),
        )

        df = data.to_df()

        if df.empty:
            print(f"    No data returned for {symbol}")
            return pd.DataFrame()

        # Databento OHLCV schema has: ts_event, open, high, low, close, volume
        df = df.reset_index()

        print(f"    Received {len(df)} bars")
        return df

    except Exception as e:
        print(f"    ERROR: {e}")
        return pd.DataFrame()


def transform_to_mkt_schema(df: pd.DataFrame, symbol: str) -> list[dict]:
    """
    Transform Databento DataFrame to mkt.futures_1d schema.

    Map continuous symbol (ZL.c.0) to canonical symbol (ZL).
    """
    canonical_symbol = symbol.split(".")[0]  # ZL.c.0 -> ZL

    rows = []
    for _, row in df.iterrows():
        event_date = pd.to_datetime(row["ts_event"]).date()

        record = {
            "symbol": canonical_symbol,
            "event_date": event_date,
            "open": float(row["open"]) if pd.notna(row["open"]) else None,
            "high": float(row["high"]) if pd.notna(row["high"]) else None,
            "low": float(row["low"]) if pd.notna(row["low"]) else None,
            "close": float(row["close"]) if pd.notna(row["close"]) else None,
            "volume": int(row["volume"]) if pd.notna(row["volume"]) else None,
            "open_interest": None,  # OHLCV schema doesn't include OI - need separate statistics schema
            "source": "databento",
            "knowledge_time": datetime.now(),
        }

        record["row_hash"] = compute_row_hash(record)
        rows.append(record)

    return rows


def upsert_to_database(conn, rows: list[dict]) -> int:
    """
    Upsert rows to mkt.futures_1d.

    ON CONFLICT (event_date, symbol):
    - If source is already 'databento', update
    - Otherwise, skip (don't overwrite Yahoo with Databento)
    """
    if not rows:
        return 0

    insert_query = """
    INSERT INTO mkt.futures_1d (
        event_date, symbol, open, high, low, close, volume, open_interest,
        source, ingested_at, knowledge_time, row_hash
    ) VALUES (
        %(event_date)s, %(symbol)s, %(open)s, %(high)s, %(low)s, %(close)s,
        %(volume)s, %(open_interest)s, %(source)s, NOW(), %(knowledge_time)s, %(row_hash)s
    )
    ON CONFLICT (event_date, symbol) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        open_interest = EXCLUDED.open_interest,
        source = EXCLUDED.source,
        ingested_at = NOW(),
        knowledge_time = EXCLUDED.knowledge_time,
        row_hash = EXCLUDED.row_hash
    WHERE mkt.futures_1d.source = 'databento' OR mkt.futures_1d.source IS NULL
    """

    cur = conn.cursor()
    execute_batch(cur, insert_query, rows, page_size=1000)
    conn.commit()
    updated = cur.rowcount
    cur.close()

    return updated


def get_latest_date_in_db(conn, symbol: str) -> date:
    """Get latest date for a symbol with source='databento'."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT MAX(event_date) FROM mkt.futures_1d
        WHERE symbol = %s AND source = 'databento'
        """,
        (symbol,),
    )
    result = cur.fetchone()[0]
    cur.close()

    if result is None:
        return date(2020, 1, 1)  # Default backfill start

    return result


def main():
    """Main ingestion loop."""
    print("=" * 70)
    print("DATABENTO FUTURES INGESTION")
    print("=" * 70)

    client = get_databento_client()
    conn = get_db_connection()

    end_date = date.today()

    total_inserted = 0

    for symbol in SYMBOLS:
        canonical = symbol.split(".")[0]
        print(f"\n[{canonical}] {symbol}")

        # Get latest date in DB
        latest_db_date = get_latest_date_in_db(conn, canonical)
        start_date = (
            latest_db_date + timedelta(days=1) if latest_db_date else date(2020, 1, 1)
        )

        print(f"  Latest in DB: {latest_db_date}")
        print(f"  Fetching from: {start_date}")

        if start_date > end_date:
            print(f"  Up to date (no new data)")
            continue

        # Fetch from Databento
        df = fetch_databento_ohlcv(client, symbol, start_date, end_date)

        if df.empty:
            continue

        # Transform to mkt schema
        rows = transform_to_mkt_schema(df, symbol)
        print(f"  Prepared {len(rows)} rows for upsert")

        # Upsert to database
        inserted = upsert_to_database(conn, rows)
        total_inserted += inserted
        print(f"  Upserted {inserted} rows")

    conn.close()

    print("\n" + "=" * 70)
    print(f"COMPLETE: {total_inserted} total rows upserted")
    print("=" * 70)


if __name__ == "__main__":
    main()
