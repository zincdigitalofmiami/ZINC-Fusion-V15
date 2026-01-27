#!/usr/bin/env python3
"""
DEPRECATED: Use Inngest job 'databento-statistics-daily.ts' instead.

This Python script uses ZL.c.0 (calendar roll) while the Inngest job
uses ZL.n.0 (OI-ranked) which is correct for Crush specialist.

The Inngest job runs on Vercel cron and is the canonical OI ingestion.
This script is kept for reference/manual backfill only.

See: frontend/src/inngest/databento-statistics-daily.ts

--- Original Docstring ---
Databento statistics ingestion for open interest.

Fetches daily open interest for futures and updates mkt.futures_1d.
"""

import warnings
warnings.warn(
    "ingest_databento_statistics.py is DEPRECATED. "
    "Use Inngest job 'databento-statistics-daily.ts' instead.",
    DeprecationWarning,
    stacklevel=2
)

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

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
    "ZL.c.0",  # Soybean oil
    "ZS.c.0",  # Soybeans
    "ZM.c.0",  # Soybean meal
    "CL.c.0",  # Crude oil
    "HO.c.0",  # Heating oil
    "RB.c.0",  # Gasoline
]

DATASET = "GLBX.MDP3"
SCHEMA = "statistics"  # For open interest


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


def fetch_databento_statistics(
    client: db.Historical,
    symbol: str,
    start_date: date,
    end_date: date
) -> pd.DataFrame:
    """
    Fetch daily statistics (open interest) for a symbol.
    
    Returns DataFrame with:
    - ts_event
    - open_interest
    """
    print(f"  Fetching statistics for {symbol} from {start_date} to {end_date}...")
    
    try:
        data = client.timeseries.get_range(
            dataset=DATASET,
            schema=SCHEMA,
            symbols=[symbol],
            stype_in='continuous',  # Required for continuous contract symbols
            start=start_date.isoformat(),
            end=end_date.isoformat(),
        )
        
        df = data.to_df()
        
        if df.empty:
            print(f"    No data returned")
            return pd.DataFrame()
        
        df = df.reset_index()
        
        # Filter for open_interest records (statistics schema has multiple stat types)
        if 'stat_type' in df.columns:
            df = df[df['stat_type'] == 1]  # 1 = open_interest in Databento
        
        print(f"    Received {len(df)} records")
        return df
        
    except Exception as e:
        print(f"    ERROR: {e}")
        return pd.DataFrame()


def update_open_interest(conn, symbol: str, oi_data: pd.DataFrame) -> int:
    """
    Update open_interest in mkt.futures_1d for existing Databento rows.
    
    Only updates rows where source='databento'.
    """
    canonical_symbol = symbol.split(".")[0]
    
    rows = []
    for _, row in oi_data.iterrows():
        event_date = pd.to_datetime(row["ts_event"]).date()
        oi = int(row["open_interest"]) if pd.notna(row.get("open_interest")) else None
        
        if oi is not None:
            rows.append({"event_date": event_date, "symbol": canonical_symbol, "open_interest": oi})
    
    if not rows:
        return 0
    
    update_query = """
    UPDATE mkt.futures_1d
    SET open_interest = %(open_interest)s,
        ingested_at = NOW()
    WHERE event_date = %(event_date)s
      AND symbol = %(symbol)s
      AND source = 'databento'
    """
    
    cur = conn.cursor()
    execute_batch(cur, update_query, rows, page_size=1000)
    conn.commit()
    updated = cur.rowcount
    cur.close()
    
    return updated


def get_latest_oi_date_in_db(conn, symbol: str) -> date:
    """Get latest date with OI data for a symbol."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT MAX(event_date) FROM mkt.futures_1d 
        WHERE symbol = %s AND source = 'databento' AND open_interest IS NOT NULL
        """,
        (symbol,)
    )
    result = cur.fetchone()[0]
    cur.close()
    
    if result is None:
        return date(2020, 1, 1)
    
    return result


def main():
    """Main ingestion loop."""
    print("=" * 70)
    print("DATABENTO STATISTICS (OPEN INTEREST) INGESTION")
    print("=" * 70)
    
    client = get_databento_client()
    conn = get_db_connection()
    
    end_date = date.today()
    
    total_updated = 0
    
    for symbol in SYMBOLS:
        canonical = symbol.split(".")[0]
        print(f"\n[{canonical}] {symbol}")
        
        # Get latest OI date in DB
        latest_oi_date = get_latest_oi_date_in_db(conn, canonical)
        start_date = latest_oi_date + timedelta(days=1) if latest_oi_date else date(2020, 1, 1)
        
        print(f"  Latest OI in DB: {latest_oi_date}")
        print(f"  Fetching from: {start_date}")
        
        if start_date > end_date:
            print(f"  Up to date")
            continue
        
        # Fetch statistics
        df = fetch_databento_statistics(client, symbol, start_date, end_date)
        
        if df.empty:
            continue
        
        # Update OI in database
        updated = update_open_interest(conn, symbol, df)
        total_updated += updated
        print(f"  Updated {updated} rows with OI")
    
    conn.close()
    
    print("\n" + "=" * 70)
    print(f"COMPLETE: {total_updated} rows updated with open_interest")
    print("=" * 70)


if __name__ == "__main__":
    main()
