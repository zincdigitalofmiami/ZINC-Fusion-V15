#!/usr/bin/env python3
"""
Databento Top 50 CME backfill script.

Backfills mkt.futures_1d with data from Databento for CME Globex Top 50 symbols.
Uses the same incremental logic as the Inngest job but can be run manually for gap-fill.

Usage:
    # Backfill all stale symbols (>2 days old)
    python scripts/backfill_databento_top50.py

    # Backfill specific symbols
    python scripts/backfill_databento_top50.py --symbols GC SI HG

    # Force full backfill from specific date
    python scripts/backfill_databento_top50.py --symbols GC --from-date 2025-12-20

    # Dry run (check what would be fetched)
    python scripts/backfill_databento_top50.py --dry-run
"""

import os
import sys
import argparse
import hashlib
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

# CME Globex Top 50 symbols - matches Inngest job configuration
DATABENTO_SYMBOLS = [
    # Soybean complex (Crush) - OI-ranked
    {"continuous": "ZL.n.0", "canonical": "ZL", "name": "Soybean Oil"},
    {"continuous": "ZS.n.0", "canonical": "ZS", "name": "Soybeans"},
    {"continuous": "ZM.n.0", "canonical": "ZM", "name": "Soybean Meal"},
    # Grains - calendar-ranked
    {"continuous": "ZC.c.0", "canonical": "ZC", "name": "Corn"},
    {"continuous": "ZW.c.0", "canonical": "ZW", "name": "Wheat"},
    # Energy - calendar-ranked
    {"continuous": "CL.c.0", "canonical": "CL", "name": "Crude Oil"},
    {"continuous": "NG.c.0", "canonical": "NG", "name": "Natural Gas"},
    {"continuous": "HO.c.0", "canonical": "HO", "name": "Heating Oil"},
    {"continuous": "RB.c.0", "canonical": "RB", "name": "RBOB Gasoline"},
    {"continuous": "BZ.c.0", "canonical": "BZ", "name": "Brent Crude"},
    # Metals (COMEX/NYMEX) - calendar-ranked
    {"continuous": "GC.c.0", "canonical": "GC", "name": "Gold"},
    {"continuous": "SI.c.0", "canonical": "SI", "name": "Silver"},
    {"continuous": "HG.c.0", "canonical": "HG", "name": "Copper"},
    {"continuous": "PL.c.0", "canonical": "PL", "name": "Platinum"},
    {"continuous": "PA.c.0", "canonical": "PA", "name": "Palladium"},
    # Equity Indices - calendar-ranked
    {"continuous": "ES.c.0", "canonical": "ES", "name": "E-mini S&P 500"},
    {"continuous": "NQ.c.0", "canonical": "NQ", "name": "E-mini Nasdaq 100"},
    {"continuous": "YM.c.0", "canonical": "YM", "name": "Mini Dow"},
    {"continuous": "RTY.c.0", "canonical": "RTY", "name": "E-mini Russell 2000"},
    # Treasury Futures - calendar-ranked
    {"continuous": "ZN.c.0", "canonical": "ZN", "name": "10-Year Treasury"},
    {"continuous": "ZB.c.0", "canonical": "ZB", "name": "30-Year Treasury"},
    {"continuous": "ZF.c.0", "canonical": "ZF", "name": "5-Year Treasury"},
    {"continuous": "ZT.c.0", "canonical": "ZT", "name": "2-Year Treasury"},
    # Livestock - calendar-ranked
    {"continuous": "HE.c.0", "canonical": "HE", "name": "Lean Hogs"},
    {"continuous": "LE.c.0", "canonical": "LE", "name": "Live Cattle"},
    {"continuous": "GF.c.0", "canonical": "GF", "name": "Feeder Cattle"},
]

DATASET = "GLBX.MDP3"
SCHEMA_OHLCV = "ohlcv-1d"
SCHEMA_STATS = "statistics"


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


def compute_row_hash(symbol: str, event_date: date, open_: float, high: float,
                     low: float, close: float, volume: int) -> str:
    """Compute deterministic hash for deduplication."""
    date_str = event_date.isoformat()
    key = f"{symbol}|{date_str}|{open_ or ''}|{high or ''}|{low or ''}|{close}|{volume}"
    return hashlib.sha256(key.encode()).hexdigest()


def get_max_databento_date(conn, symbol: str) -> date | None:
    """Get max event_date for symbol where source='databento'."""
    cur = conn.cursor()
    cur.execute(
        "SELECT MAX(event_date)::date FROM mkt.futures_1d WHERE symbol = %s AND source = 'databento'",
        (symbol,)
    )
    result = cur.fetchone()[0]
    cur.close()
    return result


def get_all_symbol_freshness(conn) -> dict:
    """Get freshness info for all symbols."""
    cur = conn.cursor()
    cur.execute("""
        SELECT symbol, MAX(event_date)::date as max_date
        FROM mkt.futures_1d
        WHERE source = 'databento'
        GROUP BY symbol
        ORDER BY symbol
    """)
    return {row[0]: row[1] for row in cur.fetchall()}


def fetch_ohlcv(client: db.Historical, symbol_config: dict, start_date: date, end_date: date) -> pd.DataFrame:
    """Fetch daily OHLCV from Databento."""
    print(f"    Fetching OHLCV {symbol_config['continuous']} from {start_date} to {end_date}...")
    try:
        data = client.timeseries.get_range(
            dataset=DATASET,
            schema=SCHEMA_OHLCV,
            symbols=[symbol_config["continuous"]],
            stype_in="continuous",
            start=start_date.isoformat(),
            end=end_date.isoformat(),
        )
        df = data.to_df()
        if df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        print(f"    Received {len(df)} OHLCV bars")
        return df
    except Exception as e:
        print(f"    ERROR fetching OHLCV: {e}")
        return pd.DataFrame()


def fetch_statistics(client: db.Historical, symbol_config: dict, start_date: date, end_date: date) -> pd.DataFrame:
    """Fetch open interest statistics from Databento."""
    print(f"    Fetching OI stats {symbol_config['continuous']}...")
    try:
        data = client.timeseries.get_range(
            dataset=DATASET,
            schema=SCHEMA_STATS,
            symbols=[symbol_config["continuous"]],
            stype_in="continuous",
            start=start_date.isoformat(),
            end=end_date.isoformat(),
        )
        df = data.to_df()
        if df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        # Filter for stat_type=9 (open interest)
        if "stat_type" in df.columns:
            df = df[df["stat_type"] == 9].copy()
        print(f"    Received {len(df)} OI records")
        return df
    except Exception as e:
        print(f"    ERROR fetching OI: {e}")
        return pd.DataFrame()


def upsert_ohlcv(conn, symbol: str, df: pd.DataFrame) -> int:
    """Upsert OHLCV rows to mkt.futures_1d."""
    if df.empty:
        return 0
    
    rows = []
    for _, row in df.iterrows():
        event_date = pd.to_datetime(row["ts_event"]).date()
        open_ = float(row["open"]) if pd.notna(row["open"]) else None
        high = float(row["high"]) if pd.notna(row["high"]) else None
        low = float(row["low"]) if pd.notna(row["low"]) else None
        close = float(row["close"]) if pd.notna(row["close"]) else None
        volume = int(row["volume"]) if pd.notna(row["volume"]) else 0
        
        if close is None:
            continue  # Skip rows without close
            
        row_hash = compute_row_hash(symbol, event_date, open_, high, low, close, volume)
        rows.append({
            "event_date": event_date,
            "symbol": symbol,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "source": "databento",
            "row_hash": row_hash,
        })
    
    if not rows:
        return 0
    
    query = """
    INSERT INTO mkt.futures_1d (event_date, symbol, open, high, low, close, volume, source, ingested_at, row_hash)
    VALUES (%(event_date)s, %(symbol)s, %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(source)s, NOW(), %(row_hash)s)
    ON CONFLICT (event_date, symbol) DO UPDATE SET
        open = COALESCE(EXCLUDED.open, mkt.futures_1d.open),
        high = COALESCE(EXCLUDED.high, mkt.futures_1d.high),
        low = COALESCE(EXCLUDED.low, mkt.futures_1d.low),
        close = EXCLUDED.close,
        volume = COALESCE(EXCLUDED.volume, mkt.futures_1d.volume),
        source = CASE 
            WHEN mkt.futures_1d.source = 'databento' OR mkt.futures_1d.source IS NULL 
            THEN EXCLUDED.source 
            ELSE mkt.futures_1d.source 
        END,
        ingested_at = NOW(),
        row_hash = EXCLUDED.row_hash
    WHERE mkt.futures_1d.source = 'databento' OR mkt.futures_1d.source IS NULL
    """
    
    cur = conn.cursor()
    execute_batch(cur, query, rows, page_size=500)
    conn.commit()
    cur.close()
    return len(rows)


def upsert_open_interest(conn, symbol: str, df: pd.DataFrame) -> int:
    """Upsert open interest to existing rows in mkt.futures_1d."""
    if df.empty:
        return 0
    
    rows = []
    for _, row in df.iterrows():
        event_date = pd.to_datetime(row["ts_event"]).date()
        
        # OI can be in quantity or price field (Databento format)
        oi_value = None
        if "quantity" in row and pd.notna(row["quantity"]):
            oi_value = int(row["quantity"])
        elif "price" in row and pd.notna(row["price"]):
            # Price field is in fixed-point, scale by 1e-9
            oi_value = int(float(row["price"]) * 1e-9)
        
        if oi_value is None or oi_value < 0:
            continue
            
        rows.append({
            "event_date": event_date,
            "symbol": symbol,
            "open_interest": oi_value,
        })
    
    if not rows:
        return 0
    
    query = """
    INSERT INTO mkt.futures_1d (event_date, symbol, open_interest, source, ingested_at)
    VALUES (%(event_date)s, %(symbol)s, %(open_interest)s, 'databento', NOW())
    ON CONFLICT (event_date, symbol) DO UPDATE SET
        open_interest = EXCLUDED.open_interest,
        source = CASE 
            WHEN mkt.futures_1d.source = 'databento' OR mkt.futures_1d.source IS NULL 
            THEN EXCLUDED.source 
            ELSE mkt.futures_1d.source 
        END,
        ingested_at = NOW()
    WHERE mkt.futures_1d.source = 'databento' OR mkt.futures_1d.source IS NULL
    """
    
    cur = conn.cursor()
    execute_batch(cur, query, rows, page_size=500)
    conn.commit()
    cur.close()
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Backfill Databento CME Top 50 symbols")
    parser.add_argument("--symbols", nargs="+", help="Specific symbols to backfill (e.g., GC SI HG)")
    parser.add_argument("--from-date", type=str, help="Force start date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--stale-days", type=int, default=2, help="Backfill symbols older than N days (default: 2)")
    args = parser.parse_args()
    
    print("=" * 70)
    print("DATABENTO CME TOP 50 BACKFILL")
    print("=" * 70)
    
    conn = get_db_connection()
    client = get_databento_client()
    
    # Get current freshness
    freshness = get_all_symbol_freshness(conn)
    today = date.today()
    
    # Determine which symbols to process
    if args.symbols:
        symbols_to_process = [s for s in DATABENTO_SYMBOLS if s["canonical"] in args.symbols]
    else:
        # Find stale symbols (>stale_days old or missing)
        symbols_to_process = []
        for s in DATABENTO_SYMBOLS:
            max_date = freshness.get(s["canonical"])
            if max_date is None:
                symbols_to_process.append(s)
            elif (today - max_date).days > args.stale_days:
                symbols_to_process.append(s)
    
    if not symbols_to_process:
        print("\nNo symbols need backfill (all current within threshold)")
        return
    
    print(f"\nSymbols to backfill: {len(symbols_to_process)}")
    for s in symbols_to_process:
        max_date = freshness.get(s["canonical"], "N/A")
        staleness = (today - max_date).days if isinstance(max_date, date) else "missing"
        print(f"  {s['canonical']:5} ({s['name']:20}) - max_date: {max_date}, staleness: {staleness} days")
    
    if args.dry_run:
        print("\n[DRY RUN] Would fetch and upsert data for above symbols")
        return
    
    # End date is today minus 1 day (Databento historical API lag)
    end_date = today - timedelta(days=1)
    
    total_ohlcv = 0
    total_oi = 0
    
    print("\n" + "-" * 70)
    
    for s in symbols_to_process:
        symbol = s["canonical"]
        print(f"\n[{symbol}] {s['name']}")
        
        # Determine start date
        if args.from_date:
            start_date = date.fromisoformat(args.from_date)
        else:
            max_date = freshness.get(symbol)
            if max_date:
                start_date = max_date + timedelta(days=1)
            else:
                start_date = date(2020, 1, 1)  # Default backfill start
        
        if start_date > end_date:
            print(f"  Already current (max_date >= end_date)")
            continue
        
        print(f"  Fetching from {start_date} to {end_date}")
        
        # Fetch and upsert OHLCV
        ohlcv_df = fetch_ohlcv(client, s, start_date, end_date)
        ohlcv_count = upsert_ohlcv(conn, symbol, ohlcv_df)
        print(f"    Upserted {ohlcv_count} OHLCV rows")
        total_ohlcv += ohlcv_count
        
        # Fetch and upsert OI
        oi_df = fetch_statistics(client, s, start_date, end_date)
        oi_count = upsert_open_interest(conn, symbol, oi_df)
        print(f"    Upserted {oi_count} OI rows")
        total_oi += oi_count
    
    conn.close()
    
    print("\n" + "=" * 70)
    print(f"COMPLETE: {total_ohlcv} OHLCV rows, {total_oi} OI rows")
    print("=" * 70)
    
    # Verification query
    print("\nVerification SQL:")
    print("""
SELECT symbol, source, MAX(event_date) as max_date, COUNT(*) as rows
FROM mkt.futures_1d
WHERE symbol IN ('GC', 'SI', 'HG', 'NG', 'PA', 'PL', 'ZC', 'ZW', 'ES', 'NQ', 'ZN', 'ZB')
AND source = 'databento'
GROUP BY symbol, source
ORDER BY symbol;
    """)


if __name__ == "__main__":
    main()
