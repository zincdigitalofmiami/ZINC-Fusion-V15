#!/usr/bin/env python3
"""
Databento Options Backfill

Fetches options on futures data from Databento and writes to mkt.options_1d.
Supports all major CME options: FX, Ag, Metals, Energy, Equity Indices, Treasuries.

Usage:
    python scripts/backfill_databento_options.py
    python scripts/backfill_databento_options.py --underlying ZL --days 30
    python scripts/backfill_databento_options.py --dry-run
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

# Options underlyings from CME Globex (based on user's screenshots)
# Format: {underlying: [option_root_symbols]}
OPTIONS_CONFIG = [
    # Agriculture Options
    {"underlying": "ZL", "name": "Soybean Oil", "patterns": ["OZL"]},
    {"underlying": "ZS", "name": "Soybeans", "patterns": ["OZS"]},
    {"underlying": "ZM", "name": "Soybean Meal", "patterns": ["OZM"]},
    {"underlying": "ZC", "name": "Corn", "patterns": ["OZC"]},
    {"underlying": "ZW", "name": "Wheat", "patterns": ["OZW"]},
    # Energy Options
    {"underlying": "CL", "name": "Crude Oil", "patterns": ["LO"]},
    {"underlying": "NG", "name": "Natural Gas", "patterns": ["ON"]},
    # Metals Options
    {"underlying": "GC", "name": "Gold", "patterns": ["OG"]},
    {"underlying": "SI", "name": "Silver", "patterns": ["SO"]},
    {"underlying": "HG", "name": "Copper", "patterns": ["HXE"]},
    # Equity Index Options
    {"underlying": "ES", "name": "E-mini S&P 500", "patterns": ["EW"]},  # Weekly ES options
    {"underlying": "NQ", "name": "E-mini Nasdaq", "patterns": ["NQE"]},  # NQ options
    {"underlying": "RTY", "name": "E-mini Russell", "patterns": ["RTO"]},
    # Treasury Options
    {"underlying": "ZN", "name": "10-Year Treasury", "patterns": ["OZN"]},
    {"underlying": "ZB", "name": "30-Year Treasury", "patterns": ["OZB"]},
    {"underlying": "ZF", "name": "5-Year Treasury", "patterns": ["OZF"]},
    {"underlying": "ZT", "name": "2-Year Treasury", "patterns": ["OZT"]},
    # FX Options
    {"underlying": "6E", "name": "EUR/USD", "patterns": ["EUU"]},
    {"underlying": "6J", "name": "USD/JPY", "patterns": ["JPU"]},
    {"underlying": "6B", "name": "GBP/USD", "patterns": ["GBU"]},
    {"underlying": "6A", "name": "AUD/USD", "patterns": ["ADU"]},
    {"underlying": "6C", "name": "USD/CAD", "patterns": ["CAU"]},
]

DATASET = "GLBX.MDP3"


def get_databento_client() -> db.Historical:
    """Get Databento client."""
    if not DATABENTO_API_KEY:
        raise ValueError("DATABENTO_API_KEY not set")
    return db.Historical(key=DATABENTO_API_KEY)


def get_db_connection():
    """Get database connection."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL)


def compute_row_hash(underlying: str, event_date: date, expiration: date, 
                     strike: float, option_type: str) -> str:
    """Compute deterministic hash for deduplication."""
    key = f"{underlying}|{event_date}|{expiration}|{strike}|{option_type}"
    return hashlib.sha256(key.encode()).hexdigest()


def parse_option_symbol(symbol: str) -> dict | None:
    """
    Parse CME option symbol into components.
    Example: OZL H26 C 5000 -> {underlying: ZL, expiry: 2026-03, type: C, strike: 50.00}
    """
    # This is a simplified parser - CME option symbols have various formats
    try:
        parts = symbol.split()
        if len(parts) < 3:
            return None
        
        # Extract option type (C/P)
        option_type = None
        strike = None
        
        for part in parts:
            if part in ('C', 'P', 'CALL', 'PUT'):
                option_type = 'C' if part in ('C', 'CALL') else 'P'
            elif part.replace('.', '').isdigit():
                strike = float(part)
        
        if not option_type or strike is None:
            return None
            
        return {
            "option_type": option_type,
            "strike": strike,
        }
    except Exception:
        return None


def fetch_options_ohlcv(
    client: db.Historical,
    config: dict,
    start_date: date,
    end_date: date
) -> pd.DataFrame:
    """Fetch options OHLCV data from Databento."""
    print(f"  Fetching {config['name']} options ({config['underlying']})...")
    
    all_data = []
    
    for pattern in config["patterns"]:
        try:
            # Fetch options using the pattern
            # Use definition schema first to get available symbols
            data = client.timeseries.get_range(
                dataset=DATASET,
                schema="ohlcv-1d",
                symbols=[f"{pattern}*"],
                stype_in="raw_symbol",
                start=start_date.isoformat(),
                end=end_date.isoformat(),
            )
            
            df = data.to_df()
            if not df.empty:
                df = df.reset_index()
                df["underlying"] = config["underlying"]
                all_data.append(df)
                print(f"    {pattern}*: {len(df)} bars")
            else:
                print(f"    {pattern}*: no data")
                
        except Exception as e:
            print(f"    {pattern}*: ERROR - {e}")
    
    if not all_data:
        return pd.DataFrame()
    
    return pd.concat(all_data, ignore_index=True)


def upsert_options(conn, rows: list[dict]) -> int:
    """Upsert options data to mkt.options_1d."""
    if not rows:
        return 0
    
    query = """
    INSERT INTO mkt.options_1d
        (underlying, event_date, expiration, strike, option_type, 
         open, high, low, close, volume, open_interest, source, ingested_at, row_hash)
    VALUES
        (%(underlying)s, %(event_date)s, %(expiration)s, %(strike)s, %(option_type)s,
         %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(open_interest)s, 
         'databento', NOW(), %(row_hash)s)
    ON CONFLICT (underlying, event_date, expiration, strike, option_type) DO UPDATE SET
        open = COALESCE(EXCLUDED.open, mkt.options_1d.open),
        high = COALESCE(EXCLUDED.high, mkt.options_1d.high),
        low = COALESCE(EXCLUDED.low, mkt.options_1d.low),
        close = EXCLUDED.close,
        volume = COALESCE(EXCLUDED.volume, mkt.options_1d.volume),
        open_interest = COALESCE(EXCLUDED.open_interest, mkt.options_1d.open_interest),
        source = 'databento',
        ingested_at = NOW(),
        row_hash = EXCLUDED.row_hash
    """
    
    cur = conn.cursor()
    execute_batch(cur, query, rows, page_size=500)
    conn.commit()
    cur.close()
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Backfill Databento options data")
    parser.add_argument("--underlying", type=str, help="Specific underlying (e.g., ZL, ES)")
    parser.add_argument("--days", type=int, default=30, help="Days to backfill")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = parser.parse_args()
    
    print("=" * 70)
    print("DATABENTO OPTIONS BACKFILL")
    print("=" * 70)
    
    client = get_databento_client()
    conn = get_db_connection()
    
    end_date = date.today() - timedelta(days=1)  # Yesterday
    start_date = end_date - timedelta(days=args.days)
    
    print(f"Date range: {start_date} to {end_date}")
    
    configs = OPTIONS_CONFIG
    if args.underlying:
        configs = [c for c in OPTIONS_CONFIG if c["underlying"] == args.underlying.upper()]
        if not configs:
            print(f"Unknown underlying: {args.underlying}")
            return
    
    print(f"Underlyings to process: {len(configs)}")
    
    if args.dry_run:
        print("\n[DRY RUN] Would fetch options for:")
        for c in configs:
            print(f"  {c['underlying']}: {c['name']} ({c['patterns']})")
        return
    
    total_rows = 0
    
    for config in configs:
        print(f"\n[{config['underlying']}] {config['name']}")
        
        # Fetch options data
        options_df = fetch_options_ohlcv(client, config, start_date, end_date)
        
        if options_df.empty:
            print(f"  No options data found")
            continue
        
        # Process and prepare rows for insertion
        rows = []
        for _, row in options_df.iterrows():
            try:
                event_date = pd.to_datetime(row.get("ts_event", row.get("date"))).date()
                
                # Parse option details from symbol if available
                symbol = str(row.get("symbol", row.get("raw_symbol", "")))
                
                # Extract strike and option type from symbol or data
                strike = float(row.get("strike_price", row.get("strike", 0))) / 1e9  # Databento fixed-point
                if strike == 0:
                    # Try to parse from symbol
                    continue
                
                option_type = str(row.get("option_type", row.get("instrument_class", "C")))
                if option_type not in ("C", "P"):
                    option_type = "C" if "C" in symbol.upper() else "P" if "P" in symbol.upper() else "C"
                
                expiration = pd.to_datetime(row.get("expiration", row.get("expiry"))).date() if row.get("expiration") else event_date + timedelta(days=30)
                
                record = {
                    "underlying": config["underlying"],
                    "event_date": event_date,
                    "expiration": expiration,
                    "strike": strike,
                    "option_type": option_type,
                    "open": float(row.get("open", 0)) / 1e9 if row.get("open") else None,
                    "high": float(row.get("high", 0)) / 1e9 if row.get("high") else None,
                    "low": float(row.get("low", 0)) / 1e9 if row.get("low") else None,
                    "close": float(row.get("close", 0)) / 1e9 if row.get("close") else None,
                    "volume": int(row.get("volume", 0)) if row.get("volume") else None,
                    "open_interest": int(row.get("open_interest", 0)) if row.get("open_interest") else None,
                    "row_hash": compute_row_hash(config["underlying"], event_date, expiration, strike, option_type),
                }
                rows.append(record)
            except Exception as e:
                continue
        
        if rows:
            upserted = upsert_options(conn, rows)
            print(f"  Upserted {upserted} rows")
            total_rows += upserted
        else:
            print(f"  No valid rows to insert")
    
    conn.close()
    
    print("\n" + "=" * 70)
    print(f"COMPLETE: {total_rows} total rows")
    print("=" * 70)


if __name__ == "__main__":
    main()
