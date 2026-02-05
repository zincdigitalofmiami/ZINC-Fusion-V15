#!/usr/bin/env python3
"""
Databento Options Historical Backfill - CORRECT VERSION

Uses the EXACT same CSV approach as the working Inngest daily function.
Fetches: definition (strike/expiry) + ohlcv-1d (prices) + statistics (OI/bid/ask/etc)

ALL 15 stat_types are captured:
  1=OPENING_PRICE, 2=INDICATIVE_OPENING, 3=SETTLEMENT, 4=SESSION_LOW, 5=SESSION_HIGH,
  6=CLEARED_VOLUME, 7=LOWEST_OFFER(ask), 8=HIGHEST_BID(bid), 9=OPEN_INTEREST,
  10=FIXING_PRICE, 11=CLOSE, 12=NET_CHANGE, 13=VWAP, 14=VOLATILITY(IV), 15=DELTA

Usage:
    python scripts/backfill_options_CORRECT.py --underlying ZL --start 2010-06-06 --end 2026-02-02
    python scripts/backfill_options_CORRECT.py --all --start 2010-06-06 --end 2026-02-02
"""

import os
import sys
import argparse
import hashlib
import requests
from datetime import date, datetime, timedelta
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv
import csv
from io import StringIO
from collections import defaultdict
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

# Options configuration - EXACT same as Inngest function
OPTIONS_CONFIG = [
    # AGRICULTURE
    {"parent": "OZL.OPT", "underlying": "ZL", "name": "Soybean Oil Options"},
    {"parent": "OZS.OPT", "underlying": "ZS", "name": "Soybean Options"},
    {"parent": "OZM.OPT", "underlying": "ZM", "name": "Soybean Meal Options"},
    {"parent": "OZC.OPT", "underlying": "ZC", "name": "Corn Options"},
    {"parent": "OZW.OPT", "underlying": "ZW", "name": "Wheat Options"},
    {"parent": "OKE.OPT", "underlying": "KE", "name": "KC HRW Wheat Options"},
    # ENERGY
    {"parent": "LO.OPT", "underlying": "CL", "name": "Crude Oil Options"},
    {"parent": "ON.OPT", "underlying": "NG", "name": "Natural Gas Options"},
    {"parent": "OH.OPT", "underlying": "HO", "name": "Heating Oil Options"},
    {"parent": "OB.OPT", "underlying": "RB", "name": "RBOB Gasoline Options"},
    # METALS
    {"parent": "OG.OPT", "underlying": "GC", "name": "Gold Options"},
    {"parent": "SO.OPT", "underlying": "SI", "name": "Silver Options"},
    {"parent": "HXE.OPT", "underlying": "HG", "name": "Copper Options"},
    # EQUITY INDICES
    {"parent": "ES.OPT", "underlying": "ES", "name": "E-mini S&P Options"},
    {"parent": "NQ.OPT", "underlying": "NQ", "name": "E-mini Nasdaq Options"},
    # TREASURIES
    {"parent": "OZN.OPT", "underlying": "ZN", "name": "10Y Treasury Options"},
    {"parent": "OZB.OPT", "underlying": "ZB", "name": "30Y Treasury Options"},
    {"parent": "OZF.OPT", "underlying": "ZF", "name": "5Y Treasury Options"},
    # FX
    {"parent": "EUU.OPT", "underlying": "6E", "name": "Euro FX Options"},
    {"parent": "JPU.OPT", "underlying": "6J", "name": "Yen FX Options"},
]

DATASET = "GLBX.MDP3"
API_BASE = "https://hist.databento.com/v0/timeseries.get_range"


def fetch_databento_csv(
    dataset: str,
    schema: str,
    symbols: str,
    start: str,
    end: str,
) -> str:
    """Fetch data from Databento API as CSV with pretty formatting."""
    params = {
        "dataset": dataset,
        "schema": schema,
        "symbols": symbols,
        "stype_in": "parent",
        "start": start,
        "end": end,
        "encoding": "csv",
        "pretty_ts": "true",
        "pretty_px": "true",
    }
    
    response = requests.get(
        API_BASE,
        params=params,
        auth=(DATABENTO_API_KEY, ""),
        timeout=300,  # 5 min timeout for large requests
    )
    
    # 200 = complete, 206 = partial content (still valid data)
    if response.status_code not in (200, 206):
        raise Exception(f"API error {response.status_code}: {response.text[:500]}")
    
    return response.text


def parse_timestamp(value: str) -> date | None:
    """Parse timestamp string to date."""
    if not value or not value.strip():
        return None
    value = value.strip()
    
    # Handle nanosecond timestamps (numeric)
    if value.isdigit():
        try:
            ns = int(value)
            return datetime.fromtimestamp(ns / 1e9).date()
        except:
            return None
    
    # Handle ISO format timestamps
    try:
        # Parse datetime string
        if "T" in value:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(value[:10], "%Y-%m-%d")
        return dt.date()
    except:
        return None


def parse_strike_from_symbol(raw_symbol: str) -> float | None:
    """Extract strike price from raw option symbol."""
    import re
    # Pattern: ... C6000 or P4500
    match = re.search(r"[CP](\d+)", raw_symbol)
    if match:
        return float(match.group(1))
    return None


def compute_row_hash(underlying: str, event_date: date, expiration: date, strike: float, option_type: str) -> str:
    """Compute deterministic hash for deduplication."""
    key = f"{underlying}|{event_date}|{expiration}|{strike}|{option_type}"
    return hashlib.sha256(key.encode()).hexdigest()


def parse_definition_csv(csv_text: str) -> dict:
    """
    Parse definition CSV to get strike/expiry/type per instrument_id.
    Returns: {instrument_id: {strike, expiration, option_type}}
    """
    result = {}
    
    lines = [l.strip() for l in csv_text.split("\n") if l.strip() and not l.startswith("#")]
    if len(lines) < 2:
        return result
    
    reader = csv.DictReader(lines)
    for row in reader:
        inst_class = row.get("instrument_class", "").strip()
        if inst_class not in ("C", "P"):
            continue
        
        instrument_id = row.get("instrument_id", "").strip()
        raw_symbol = row.get("raw_symbol", "")
        exp_str = row.get("expiration", "")
        
        strike = parse_strike_from_symbol(raw_symbol)
        if not strike or strike <= 0:
            continue
        
        expiration = parse_timestamp(exp_str)
        if not expiration:
            continue
        
        result[instrument_id] = {
            "strike": strike,
            "expiration": expiration,
            "option_type": inst_class,
        }
    
    return result


def parse_ohlcv_csv(csv_text: str, def_map: dict, underlying: str) -> list[dict]:
    """
    Parse OHLCV CSV and join with definition map.
    Returns list of option bar dicts.
    """
    results = []
    
    lines = [l.strip() for l in csv_text.split("\n") if l.strip() and not l.startswith("#")]
    if len(lines) < 2:
        return results
    
    reader = csv.DictReader(lines)
    for row in reader:
        instrument_id = row.get("instrument_id", "").strip()
        
        # Must have definition for this instrument
        def_info = def_map.get(instrument_id)
        if not def_info:
            continue
        
        # Parse event date
        ts_event = row.get("ts_event", "")
        event_date = parse_timestamp(ts_event)
        if not event_date:
            continue
        
        # Parse prices (already decimal with pretty_px=true)
        try:
            close = float(row.get("close", 0))
            if close <= 0:
                continue
        except:
            continue
        
        try:
            open_p = float(row.get("open", 0)) if row.get("open") else None
            high = float(row.get("high", 0)) if row.get("high") else None
            low = float(row.get("low", 0)) if row.get("low") else None
            volume = int(float(row.get("volume", 0))) if row.get("volume") else 0
        except:
            open_p, high, low, volume = None, None, None, 0
        
        results.append({
            "instrument_id": instrument_id,
            "underlying": underlying,
            "event_date": event_date,
            "expiration": def_info["expiration"],
            "strike": def_info["strike"],
            "option_type": def_info["option_type"],
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })
    
    return results


def parse_statistics_csv(csv_text: str) -> dict:
    """
    Parse statistics CSV to extract all 15 stat_types.
    Returns: {(instrument_id, event_date): {field_name: value, ...}}
    
    stat_type mapping:
      1=opening_price, 2=indicative_opening, 3=settlement, 4=session_low, 5=session_high,
      6=cleared_volume, 7=ask, 8=bid, 9=open_interest, 10=fixing_price, 
      11=close_stat, 12=change, 13=vwap, 14=implied_volatility, 15=delta
    """
    STAT_MAP = {
        1: ("opening_price_stat", "price"),
        2: ("indicative_opening", "price"),
        3: ("settlement_price", "price"),
        4: ("session_low_stat", "price"),
        5: ("session_high_stat", "price"),
        6: ("cleared_volume", "quantity"),
        7: ("ask", "price"),
        8: ("bid", "price"),
        9: ("open_interest", "quantity"),
        10: ("fixing_price", "price"),
        11: ("close_stat", "price"),
        12: ("change", "price"),
        13: ("vwap", "price"),
        14: ("implied_volatility", "price"),
        15: ("delta", "price"),
    }
    
    result = defaultdict(dict)
    
    lines = [l.strip() for l in csv_text.split("\n") if l.strip() and not l.startswith("#")]
    if len(lines) < 2:
        return result
    
    reader = csv.DictReader(lines)
    for row in reader:
        instrument_id = row.get("instrument_id", "").strip()
        if not instrument_id:
            continue
        
        ts_event = row.get("ts_event", "")
        event_date = parse_timestamp(ts_event)
        if not event_date:
            continue
        
        try:
            stat_type = int(row.get("stat_type", 0))
        except:
            continue
        
        if stat_type not in STAT_MAP:
            continue
        
        field_name, value_field = STAT_MAP[stat_type]
        
        # Get value from appropriate column
        try:
            if value_field == "quantity":
                value = float(row.get("quantity", 0))
                # Convert to int for quantity fields
                value = int(value) if value > 0 else None
            else:
                value = float(row.get("price", 0))
                value = value if value > 0 else None
        except:
            value = None
        
        if value is not None:
            key = (instrument_id, event_date)
            result[key][field_name] = value
    
    return result


def fetch_options_data(
    parent_symbol: str,
    underlying: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """
    Fetch complete options data for a symbol and date range.
    Returns list of records ready for DB insert.
    """
    # Databento requires end > start
    end_str = (end_date + timedelta(days=1)).isoformat()
    start_str = start_date.isoformat()
    
    print(f"    Fetching definitions...")
    try:
        def_csv = fetch_databento_csv(DATASET, "definition", parent_symbol, start_str, end_str)
        def_map = parse_definition_csv(def_csv)
        if not def_map:
            print(f"    No definitions found")
            return []
        print(f"    Found {len(def_map)} option definitions")
    except Exception as e:
        print(f"    Definition fetch error: {e}")
        return []
    
    print(f"    Fetching OHLCV...")
    try:
        ohlcv_csv = fetch_databento_csv(DATASET, "ohlcv-1d", parent_symbol, start_str, end_str)
        ohlcv_data = parse_ohlcv_csv(ohlcv_csv, def_map, underlying)
        if not ohlcv_data:
            print(f"    No OHLCV data")
            return []
        print(f"    Found {len(ohlcv_data)} OHLCV bars")
    except Exception as e:
        print(f"    OHLCV fetch error: {e}")
        return []
    
    print(f"    Fetching statistics (ALL 15 types)...")
    stats_map = {}
    try:
        stats_csv = fetch_databento_csv(DATASET, "statistics", parent_symbol, start_str, end_str)
        stats_map = parse_statistics_csv(stats_csv)
        if stats_map:
            print(f"    Found statistics for {len(stats_map)} instrument-date pairs")
            # Count stat types present
            all_fields = set()
            for data in stats_map.values():
                all_fields.update(data.keys())
            print(f"    Fields found: {sorted(all_fields)}")
        else:
            print(f"    No statistics data")
    except Exception as e:
        print(f"    Statistics fetch error: {e}")
    
    # Merge OHLCV with statistics
    records = []
    for bar in ohlcv_data:
        key = (bar["instrument_id"], bar["event_date"])
        stats = stats_map.get(key, {})
        
        record = {
            "underlying": bar["underlying"],
            "event_date": bar["event_date"],
            "expiration": bar["expiration"],
            "strike": bar["strike"],
            "option_type": bar["option_type"],
            "open": bar["open"],
            "high": bar["high"],
            "low": bar["low"],
            "close": bar["close"],
            "volume": bar["volume"],
            # From statistics
            "open_interest": stats.get("open_interest"),
            "bid": stats.get("bid"),
            "ask": stats.get("ask"),
            "change": stats.get("change"),
            "premium": stats.get("settlement_price"),  # Settlement = premium
            # Additional fields we capture but may not store
            # "implied_volatility": stats.get("implied_volatility"),
            # "delta": stats.get("delta"),
            # "vwap": stats.get("vwap"),
            "row_hash": compute_row_hash(
                bar["underlying"],
                bar["event_date"],
                bar["expiration"],
                bar["strike"],
                bar["option_type"],
            ),
        }
        records.append(record)
    
    # Report coverage
    if records:
        oi_count = sum(1 for r in records if r["open_interest"] is not None)
        bid_count = sum(1 for r in records if r["bid"] is not None)
        ask_count = sum(1 for r in records if r["ask"] is not None)
        print(f"    Coverage: OI={100*oi_count/len(records):.1f}%, bid={100*bid_count/len(records):.1f}%, ask={100*ask_count/len(records):.1f}%")
    
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
        open_interest = COALESCE(EXCLUDED.open_interest, mkt.options_1d.open_interest),
        bid = COALESCE(EXCLUDED.bid, mkt.options_1d.bid),
        ask = COALESCE(EXCLUDED.ask, mkt.options_1d.ask),
        change = COALESCE(EXCLUDED.change, mkt.options_1d.change),
        premium = COALESCE(EXCLUDED.premium, mkt.options_1d.premium),
        source = 'databento',
        ingested_at = NOW()
    """
    
    cur = conn.cursor()
    execute_batch(cur, query, rows, page_size=1000)
    conn.commit()
    cur.close()
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Backfill Databento options - CORRECT VERSION")
    parser.add_argument("--underlying", type=str, help="Specific underlying (e.g., ZL)")
    parser.add_argument("--start", type=str, required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD), defaults to yesterday")
    parser.add_argument("--all", action="store_true", help="Backfill all underlyings")
    parser.add_argument("--batch-months", type=int, default=3, help="Months per batch (default: 3)")
    args = parser.parse_args()
    
    print("=" * 70)
    print("DATABENTO OPTIONS BACKFILL - CORRECT VERSION")
    print("Using CSV API (same as working Inngest function)")
    print("Fetching: definition + ohlcv-1d + statistics (all 15 types)")
    print("=" * 70)
    
    conn = psycopg2.connect(DATABASE_URL)
    
    # Parse dates
    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)
    
    print(f"Date range: {start_date} to {end_date}")
    
    # Select configs
    configs = OPTIONS_CONFIG
    if args.underlying and not args.all:
        configs = [c for c in OPTIONS_CONFIG if c["underlying"] == args.underlying.upper()]
        if not configs:
            print(f"ERROR: Unknown underlying {args.underlying}")
            sys.exit(1)
    
    print(f"Underlyings: {len(configs)}")
    print(f"Batch size: {args.batch_months} months")
    
    # Create batches
    batches = []
    current = start_date
    while current <= end_date:
        # End of batch = current + batch_months
        batch_end = date(
            current.year + (current.month + args.batch_months - 1) // 12,
            (current.month + args.batch_months - 1) % 12 + 1,
            1
        ) - timedelta(days=1)
        batch_end = min(batch_end, end_date)
        batches.append((current, batch_end))
        current = batch_end + timedelta(days=1)
    
    print(f"Total batches: {len(batches)}")
    print()
    
    total_rows = 0
    
    for config in configs:
        print("=" * 70)
        print(f"[{config['underlying']}] {config['name']}")
        print(f"Parent symbol: {config['parent']}")
        print("=" * 70)
        
        underlying_total = 0
        
        for batch_idx, (batch_start, batch_end) in enumerate(batches):
            print(f"\n  Batch {batch_idx + 1}/{len(batches)}: {batch_start} to {batch_end}")
            
            try:
                rows = fetch_options_data(
                    config["parent"],
                    config["underlying"],
                    batch_start,
                    batch_end,
                )
                
                if rows:
                    print(f"    Upserting {len(rows)} rows...")
                    upserted = upsert_options(conn, rows)
                    print(f"    ✓ Upserted {upserted} rows")
                    underlying_total += upserted
                else:
                    print(f"    No data for this batch")
                
                # Rate limiting - be nice to API
                time.sleep(1)
                
            except Exception as e:
                print(f"    ERROR: {e}")
                # Continue to next batch
                continue
        
        total_rows += underlying_total
        print(f"\n  [{config['underlying']}] Total: {underlying_total:,} rows")
    
    conn.close()
    
    print("\n" + "=" * 70)
    print(f"COMPLETE: {total_rows:,} total rows upserted")
    print("=" * 70)


if __name__ == "__main__":
    main()
