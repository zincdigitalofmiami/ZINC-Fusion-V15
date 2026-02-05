#!/usr/bin/env python3
"""
Databento Options Backfill - RESEARCH-BASED CORRECT IMPLEMENTATION

Based on comprehensive research documented in:
  Docs/DATABENTO_OPTIONS_IMPORT_RESEARCH.md

KEY FINDINGS FROM RESEARCH:
1. Statistics schema for options is ENORMOUS (millions of records/month)
2. Streaming API times out on large statistics requests
3. Use OHLCV + Definition only for historical backfill
4. Statistics (OI, bid, ask) can be added later for recent data only

THIS SCRIPT:
- Fetches OHLCV + Definition schemas only (fast, reliable)
- Skips statistics for historical backfill (avoids timeout)
- Matches the approach of the working daily Inngest function
- Statistics can be backfilled separately for recent data (< 1 year)

Usage:
    python scripts/backfill_options_RESEARCH_BASED.py --underlying ZL --start 2010-06-06 --end 2026-02-02
    python scripts/backfill_options_RESEARCH_BASED.py --all --start 2010-06-06 --end 2026-02-02
"""

import os
import sys
import argparse
import hashlib
from datetime import date, datetime, timedelta
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv
import pandas as pd
import time

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABENTO_API_KEY:
    print("ERROR: DATABENTO_API_KEY not set")
    sys.exit(1)

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

import databento as db

# Options configuration
OPTIONS_CONFIG = [
    {"parent": "OZL.OPT", "underlying": "ZL", "name": "Soybean Oil Options"},
    {"parent": "OZS.OPT", "underlying": "ZS", "name": "Soybean Options"},
    {"parent": "OZM.OPT", "underlying": "ZM", "name": "Soybean Meal Options"},
    {"parent": "OZC.OPT", "underlying": "ZC", "name": "Corn Options"},
    {"parent": "OZW.OPT", "underlying": "ZW", "name": "Wheat Options"},
    {"parent": "OKE.OPT", "underlying": "KE", "name": "KC HRW Wheat Options"},
    {"parent": "LO.OPT", "underlying": "CL", "name": "Crude Oil Options"},
    {"parent": "ON.OPT", "underlying": "NG", "name": "Natural Gas Options"},
    {"parent": "OH.OPT", "underlying": "HO", "name": "Heating Oil Options"},
    {"parent": "OB.OPT", "underlying": "RB", "name": "RBOB Gasoline Options"},
    {"parent": "OG.OPT", "underlying": "GC", "name": "Gold Options"},
    {"parent": "SO.OPT", "underlying": "SI", "name": "Silver Options"},
    {"parent": "HXE.OPT", "underlying": "HG", "name": "Copper Options"},
    {"parent": "ES.OPT", "underlying": "ES", "name": "E-mini S&P Options"},
    {"parent": "NQ.OPT", "underlying": "NQ", "name": "E-mini Nasdaq Options"},
    {"parent": "OZN.OPT", "underlying": "ZN", "name": "10Y Treasury Options"},
    {"parent": "OZB.OPT", "underlying": "ZB", "name": "30Y Treasury Options"},
    {"parent": "OZF.OPT", "underlying": "ZF", "name": "5Y Treasury Options"},
    {"parent": "EUU.OPT", "underlying": "6E", "name": "Euro FX Options"},
    {"parent": "JPU.OPT", "underlying": "6J", "name": "Yen FX Options"},
]

DATASET = "GLBX.MDP3"


def compute_row_hash(
    underlying: str, event_date: date, expiration: date, strike: float, option_type: str
) -> str:
    """Compute deterministic hash for deduplication."""
    key = f"{underlying}|{event_date}|{expiration}|{strike}|{option_type}"
    return hashlib.sha256(key.encode()).hexdigest()


def extract_date(ts) -> date | None:
    """Extract date from any timestamp format."""
    if ts is None:
        return None
    if isinstance(ts, pd.Timestamp):
        return ts.date()
    if isinstance(ts, datetime):
        return ts.date()
    if isinstance(ts, date):
        return ts
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts / 1e9).date()
        except:
            return None
    if hasattr(ts, "date"):
        try:
            return ts.date()
        except:
            return None
    return None


def fetch_ohlcv_with_definitions(
    client: db.Historical,
    parent_symbol: str,
    underlying: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """
    Fetch OHLCV + Definition data only (NO statistics - too slow for historical).
    This matches the working Inngest daily function approach.
    """
    start_str = start_date.isoformat()
    end_str = (end_date + timedelta(days=1)).isoformat()

    print(f"    [{start_date} to {end_date}]")

    # Step 1: Fetch definitions (for strike, expiry, option_type)
    print(f"      Fetching definitions...")
    try:
        def_data = client.timeseries.get_range(
            dataset=DATASET,
            schema="definition",
            symbols=[parent_symbol],
            stype_in="parent",
            start=start_str,
            end=end_str,
        )
        def_df = def_data.to_df()
        if def_df.empty:
            print(f"      No definitions")
            return []
        def_df = def_df.reset_index()
        print(f"      Found {len(def_df)} definitions")
    except Exception as e:
        print(f"      Definition error: {e}")
        return []

    # Build definition map: instrument_id -> {strike, expiration, option_type}
    def_map = {}
    for _, row in def_df.iterrows():
        inst_class = str(row.get("instrument_class", ""))
        if inst_class not in ("C", "P"):
            continue

        inst_id = row.get("instrument_id")
        if inst_id is None:
            continue

        # Strike (fixed-point /1e9)
        strike_raw = row.get("strike_price", 0)
        strike = float(strike_raw) / 1e9 if strike_raw else 0
        if strike <= 0:
            continue

        # Expiration
        exp_raw = row.get("expiration")
        expiration = extract_date(exp_raw)
        if not expiration:
            continue

        def_map[inst_id] = {
            "strike": strike,
            "expiration": expiration,
            "option_type": inst_class,
        }

    if not def_map:
        print(f"      No valid option definitions")
        return []
    print(f"      Valid definitions: {len(def_map)}")

    # Step 2: Fetch OHLCV
    print(f"      Fetching OHLCV...")
    try:
        ohlcv_data = client.timeseries.get_range(
            dataset=DATASET,
            schema="ohlcv-1d",
            symbols=[parent_symbol],
            stype_in="parent",
            start=start_str,
            end=end_str,
        )
        ohlcv_df = ohlcv_data.to_df()
        if ohlcv_df.empty:
            print(f"      No OHLCV")
            return []
        ohlcv_df = ohlcv_df.reset_index()
        print(f"      Found {len(ohlcv_df)} OHLCV bars")
    except Exception as e:
        print(f"      OHLCV error: {e}")
        return []

    # Step 3: Join OHLCV with definitions
    records = []
    for _, row in ohlcv_df.iterrows():
        inst_id = row.get("instrument_id")

        def_info = def_map.get(inst_id)
        if not def_info:
            continue

        ts_event = row.get("ts_event")
        event_date = extract_date(ts_event)
        if not event_date or event_date.year < 2010:
            continue  # Never insert bad/epoch dates into mkt.options_1d

        close_val = row.get("close")
        if close_val is None or float(close_val) <= 0:
            continue

        record = {
            "underlying": underlying,
            "event_date": event_date,
            "expiration": def_info["expiration"],
            "strike": def_info["strike"],
            "option_type": def_info["option_type"],
            "open": float(row.get("open", 0)) or None,
            "high": float(row.get("high", 0)) or None,
            "low": float(row.get("low", 0)) or None,
            "close": float(close_val),
            "volume": int(row.get("volume", 0) or 0),
            # NO statistics for historical backfill (too slow)
            # These will be NULL - can be backfilled later for recent data
            "open_interest": None,
            "bid": None,
            "ask": None,
            "change": None,
            "premium": None,
            "row_hash": compute_row_hash(
                underlying,
                event_date,
                def_info["expiration"],
                def_info["strike"],
                def_info["option_type"],
            ),
        }
        records.append(record)

    print(f"      Processed {len(records)} option bars")
    return records


def upsert_options(conn, rows: list[dict]) -> int:
    """Upsert options data to mkt.options_1d."""
    if not rows:
        return 0

    query = """
    INSERT INTO mkt.options_1d
        (underlying, event_date, expiration, strike, option_type, 
         open, high, low, close, volume, open_interest, 
         bid, ask, change, premium,
         source, ingested_at, row_hash)
    VALUES
        (%(underlying)s, %(event_date)s, %(expiration)s, %(strike)s, %(option_type)s,
         %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(open_interest)s,
         %(bid)s, %(ask)s, %(change)s, %(premium)s,
         'databento', NOW(), %(row_hash)s)
    ON CONFLICT (underlying, event_date, expiration, strike, option_type) DO UPDATE SET
        open = COALESCE(EXCLUDED.open, mkt.options_1d.open),
        high = COALESCE(EXCLUDED.high, mkt.options_1d.high),
        low = COALESCE(EXCLUDED.low, mkt.options_1d.low),
        close = EXCLUDED.close,
        volume = COALESCE(EXCLUDED.volume, mkt.options_1d.volume),
        source = 'databento',
        ingested_at = NOW()
    """

    cur = conn.cursor()
    execute_batch(cur, query, rows, page_size=1000)
    conn.commit()
    cur.close()
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Backfill options - OHLCV only (fast)")
    parser.add_argument("--underlying", type=str, help="Specific underlying")
    parser.add_argument("--start", type=str, required=True, help="Start date")
    parser.add_argument("--end", type=str, help="End date")
    parser.add_argument("--all", action="store_true", help="All underlyings")
    parser.add_argument("--batch-months", type=int, default=1, help="Months per batch")
    args = parser.parse_args()

    print("=" * 70)
    print("DATABENTO OPTIONS BACKFILL - RESEARCH-BASED VERSION")
    print("OHLCV + Definition only (NO statistics - too slow for historical)")
    print("Statistics can be backfilled separately for recent data")
    print("=" * 70)

    client = db.Historical(key=DATABENTO_API_KEY)
    conn = psycopg2.connect(DATABASE_URL)

    start_date = date.fromisoformat(args.start)
    end_date = (
        date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)
    )

    print(f"Date range: {start_date} to {end_date}")

    configs = OPTIONS_CONFIG
    if args.underlying and not args.all:
        configs = [
            c for c in OPTIONS_CONFIG if c["underlying"] == args.underlying.upper()
        ]
        if not configs:
            print(f"ERROR: Unknown underlying {args.underlying}")
            sys.exit(1)

    print(f"Underlyings: {len(configs)}")
    print(f"Batch size: {args.batch_months} month(s)")

    # Create monthly batches
    batches = []
    current = start_date
    while current <= end_date:
        month = current.month + args.batch_months
        year = current.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        batch_end = date(year, month, 1) - timedelta(days=1)
        batch_end = min(batch_end, end_date)
        batches.append((current, batch_end))
        current = batch_end + timedelta(days=1)

    print(f"Total batches: {len(batches)}")
    print()

    total_rows = 0

    for config in configs:
        print("=" * 70)
        print(f"[{config['underlying']}] {config['name']}")
        print("=" * 70)

        underlying_total = 0

        for batch_idx, (batch_start, batch_end) in enumerate(batches):
            print(f"\n  Batch {batch_idx + 1}/{len(batches)}:")

            try:
                rows = fetch_ohlcv_with_definitions(
                    client,
                    config["parent"],
                    config["underlying"],
                    batch_start,
                    batch_end,
                )

                if rows:
                    upserted = upsert_options(conn, rows)
                    print(f"      ✓ Upserted {upserted} rows")
                    underlying_total += upserted

                time.sleep(0.5)  # Rate limiting

            except Exception as e:
                print(f"      ERROR: {e}")
                continue

        total_rows += underlying_total
        print(f"\n  [{config['underlying']}] Total: {underlying_total:,} rows")

    conn.close()

    print("\n" + "=" * 70)
    print(f"COMPLETE: {total_rows:,} total rows upserted")
    print()
    print("NOTE: This backfill contains OHLCV data only.")
    print("OI/bid/ask can be added later using the daily Inngest function")
    print("or a separate statistics backfill for recent data (< 1 year).")
    print("=" * 70)


if __name__ == "__main__":
    main()
