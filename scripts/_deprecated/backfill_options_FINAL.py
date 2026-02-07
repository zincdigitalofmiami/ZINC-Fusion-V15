#!/usr/bin/env python3
"""
Databento Options Historical Backfill - FINAL CORRECT VERSION

Uses the official Databento Python client library with proper .to_df() conversion.

Key insights from working Inngest function:
1. Use parent symbology (OZL.OPT) with stype_in='parent'
2. Fetch definition schema for strike/expiry/option_type
3. Fetch ohlcv-1d schema for prices
4. Fetch statistics schema for OI, bid, ask, etc.
5. Join on symbol + event_date (not instrument_id; stats use symbol)

stat_type values from Databento (all 15):
  1=opening_price, 2=indicative_opening, 3=settlement, 4=session_low, 5=session_high,
  6=cleared_volume, 7=ask, 8=bid, 9=open_interest, 10=fixing_price,
  11=close_stat, 12=change, 13=vwap, 14=implied_volatility, 15=delta

Usage:
    python scripts/backfill_options_FINAL.py --underlying ZL --start 2024-01-01 --end 2024-01-31
    python scripts/backfill_options_FINAL.py --all --start 2010-06-06 --end 2026-02-02
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

# Import databento AFTER env check
import databento as db

# Options configuration - matching Inngest function
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


def compute_row_hash(
    underlying: str, event_date: date, expiration: date, strike: float, option_type: str
) -> str:
    """Compute deterministic hash for deduplication."""
    key = f"{underlying}|{event_date}|{expiration}|{strike}|{option_type}"
    return hashlib.sha256(key.encode()).hexdigest()


def extract_date_from_timestamp(ts) -> date | None:
    """Extract date from various timestamp formats."""
    if ts is None:
        return None
    # Check pandas Timestamp FIRST (it's a subclass of datetime)
    if isinstance(ts, pd.Timestamp):
        return ts.date()
    # Then check standard date/datetime
    if isinstance(ts, datetime):
        return ts.date()
    if isinstance(ts, date):
        return ts
    # Handle numeric timestamps (nanoseconds)
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts / 1e9).date()
        except:
            return None
    # Try calling .date() on anything else that has it
    if hasattr(ts, "date"):
        try:
            return ts.date()
        except:
            return None
    return None


def parse_option_symbol(symbol: str, underlying: str) -> dict | None:
    """
    Parse CME option symbol to extract strike, expiration, option_type.
    Format: OZL{month}{year} {C|P}{strike} e.g., OZLH4 P0440

    Month codes: F=Jan, G=Feb, H=Mar, J=Apr, K=May, M=Jun,
                 N=Jul, Q=Aug, U=Sep, V=Oct, X=Nov, Z=Dec
    """
    import re

    # Skip virtual/user-defined instruments
    if symbol.startswith("UD:"):
        return None

    # Pattern: {prefix}{month}{year_digit} {C|P}{strike}
    # Examples: OZLH4 P0440, OZLK5 C0525
    match = re.match(r"^O?([A-Z]{2,3})([FGHJKMNQUVXZ])(\d)\s+([CP])(\d+)$", symbol)
    if not match:
        return None

    prefix, month_code, year_digit, opt_type, strike_str = match.groups()

    # Month code to month number
    MONTH_MAP = {
        "F": 1,
        "G": 2,
        "H": 3,
        "J": 4,
        "K": 5,
        "M": 6,
        "N": 7,
        "Q": 8,
        "U": 9,
        "V": 10,
        "X": 11,
        "Z": 12,
    }
    month = MONTH_MAP.get(month_code)
    if not month:
        return None

    # Year (single digit, assume 2020s decade)
    year = 2020 + int(year_digit)
    if year < 2020:
        year += 10  # Handle rollover to 2030s

    # Strike (integer, in cents for ags, dollars for others)
    strike = float(strike_str)

    # Expiration is typically 3rd Friday of contract month
    # For simplicity, use 15th of month as approximation
    try:
        expiration = date(year, month, 15)
    except:
        return None

    return {
        "strike": strike,
        "expiration": expiration,
        "option_type": opt_type,
    }


def fetch_options_batch(
    client: db.Historical,
    parent_symbol: str,
    underlying: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """
    Fetch options data for a single batch using official Databento client.
    Uses SYMBOL-based matching (not instrument_id) for statistics.
    """
    # Databento requires end > start
    start_str = start_date.isoformat()
    end_str = (end_date + timedelta(days=1)).isoformat()

    print(f"    [{start_date} to {end_date}]")

    # Step 1: Fetch OHLCV
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
            print(f"      No OHLCV data")
            return []
        ohlcv_df = ohlcv_df.reset_index()
        print(f"      Found {len(ohlcv_df)} OHLCV bars")
    except Exception as e:
        print(f"      OHLCV error: {e}")
        return []

    # Step 2: Fetch statistics (for OI, bid, ask, etc.)
    print(f"      Fetching statistics...")
    stats_df = pd.DataFrame()
    try:
        stats_data = client.timeseries.get_range(
            dataset=DATASET,
            schema="statistics",
            symbols=[parent_symbol],
            stype_in="parent",
            start=start_str,
            end=end_str,
        )
        stats_df = stats_data.to_df()
        if not stats_df.empty:
            stats_df = stats_df.reset_index()
            print(f"      Found {len(stats_df)} statistics records")
        else:
            print(f"      No statistics data")
    except Exception as e:
        print(f"      Statistics error: {e}")

    # Build statistics lookup by SYMBOL + DATE
    # Key: (symbol, event_date) -> {field: value}
    stats_lookup = {}
    if not stats_df.empty and "stat_type" in stats_df.columns:
        # stat_type mappings - INT32_MAX sentinel = 2147483647
        INT32_MAX = 2147483647

        STAT_TYPES = {
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

        for _, row in stats_df.iterrows():
            symbol = row.get("symbol")
            stat_type = row.get("stat_type")

            if not symbol or stat_type not in STAT_TYPES:
                continue

            field_name, value_col = STAT_TYPES[stat_type]

            # Get value
            raw_val = row.get(value_col)
            if raw_val is None:
                continue

            # Check for sentinel values
            if value_col == "quantity":
                if raw_val >= INT32_MAX:  # Sentinel
                    continue
                value = int(raw_val)
                if value <= 0:
                    continue
            else:
                value = float(raw_val)
                # Allow negative for change (net change); require positive for bid/ask/settlement
                if field_name != "change" and value <= 0:
                    continue

            # Get event date
            ts_event = row.get("ts_event")
            event_date = extract_date_from_timestamp(ts_event)
            if not event_date:
                continue

            key = (symbol, event_date)
            if key not in stats_lookup:
                stats_lookup[key] = {}
            stats_lookup[key][field_name] = value

    print(f"      Statistics lookup has {len(stats_lookup)} symbol-date pairs")

    # Step 3: Process OHLCV rows, parse symbol for strike/expiry, join with stats
    records = []
    skipped_virtual = 0
    skipped_parse = 0

    for _, row in ohlcv_df.iterrows():
        symbol = row.get("symbol")
        if not symbol:
            continue

        # Skip virtual instruments
        if str(symbol).startswith("UD:"):
            skipped_virtual += 1
            continue

        # Parse option info from symbol
        opt_info = parse_option_symbol(str(symbol), underlying)
        if not opt_info:
            skipped_parse += 1
            continue

        # Get event date
        ts_event = row.get("ts_event")
        event_date = extract_date_from_timestamp(ts_event)
        if not event_date or event_date.year < 2010:
            continue  # Never insert bad/epoch dates into mkt.options_1d

        # Get OHLCV values
        close_val = row.get("close")
        if close_val is None or float(close_val) <= 0:
            continue

        # Get statistics by symbol + date
        stats = stats_lookup.get((symbol, event_date), {})

        record = {
            "underlying": underlying,
            "event_date": event_date,
            "expiration": opt_info["expiration"],
            "strike": opt_info["strike"],
            "option_type": opt_info["option_type"],
            "open": float(row.get("open", 0)) or None,
            "high": float(row.get("high", 0)) or None,
            "low": float(row.get("low", 0)) or None,
            "close": float(close_val),
            "volume": int(row.get("volume", 0) or 0),
            "open_interest": stats.get("open_interest"),
            "bid": stats.get("bid"),
            "ask": stats.get("ask"),
            "change": stats.get("change"),
            "premium": stats.get("settlement_price"),
            "opening_price_stat": stats.get("opening_price_stat"),
            "indicative_opening": stats.get("indicative_opening"),
            "session_low_stat": stats.get("session_low_stat"),
            "session_high_stat": stats.get("session_high_stat"),
            "cleared_volume": stats.get("cleared_volume"),
            "fixing_price": stats.get("fixing_price"),
            "close_stat": stats.get("close_stat"),
            "vwap": stats.get("vwap"),
            "implied_volatility": stats.get("implied_volatility"),
            "delta": stats.get("delta"),
            "row_hash": compute_row_hash(
                underlying,
                event_date,
                opt_info["expiration"],
                opt_info["strike"],
                opt_info["option_type"],
            ),
        }
        records.append(record)

    # Report coverage
    if records:
        oi_pct = 100 * sum(1 for r in records if r["open_interest"]) / len(records)
        bid_pct = 100 * sum(1 for r in records if r["bid"]) / len(records)
        print(
            f"      Processed {len(records)} option bars (OI: {oi_pct:.1f}%, bid: {bid_pct:.1f}%)"
        )
        if skipped_virtual:
            print(f"      Skipped {skipped_virtual} virtual instruments")
        if skipped_parse:
            print(f"      Skipped {skipped_parse} unparseable symbols")

    return records


def upsert_options(conn, rows: list[dict]) -> int:
    """Upsert options data to mkt.options_1d."""
    if not rows:
        return 0

    query = """
    INSERT INTO mkt.options_1d
        (underlying, event_date, expiration, strike, option_type,
         open, high, low, close, volume, open_interest, bid, ask, change, premium,
         opening_price_stat, indicative_opening, session_low_stat, session_high_stat,
         cleared_volume, fixing_price, close_stat, vwap, implied_volatility, delta,
         source, ingested_at, row_hash)
    VALUES
        (%(underlying)s, %(event_date)s, %(expiration)s, %(strike)s, %(option_type)s,
         %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(open_interest)s,
         %(bid)s, %(ask)s, %(change)s, %(premium)s,
         %(opening_price_stat)s, %(indicative_opening)s, %(session_low_stat)s, %(session_high_stat)s,
         %(cleared_volume)s, %(fixing_price)s, %(close_stat)s, %(vwap)s, %(implied_volatility)s, %(delta)s,
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
        opening_price_stat = COALESCE(EXCLUDED.opening_price_stat, mkt.options_1d.opening_price_stat),
        indicative_opening = COALESCE(EXCLUDED.indicative_opening, mkt.options_1d.indicative_opening),
        session_low_stat = COALESCE(EXCLUDED.session_low_stat, mkt.options_1d.session_low_stat),
        session_high_stat = COALESCE(EXCLUDED.session_high_stat, mkt.options_1d.session_high_stat),
        cleared_volume = COALESCE(EXCLUDED.cleared_volume, mkt.options_1d.cleared_volume),
        fixing_price = COALESCE(EXCLUDED.fixing_price, mkt.options_1d.fixing_price),
        close_stat = COALESCE(EXCLUDED.close_stat, mkt.options_1d.close_stat),
        vwap = COALESCE(EXCLUDED.vwap, mkt.options_1d.vwap),
        implied_volatility = COALESCE(EXCLUDED.implied_volatility, mkt.options_1d.implied_volatility),
        delta = COALESCE(EXCLUDED.delta, mkt.options_1d.delta),
        source = 'databento',
        ingested_at = NOW()
    """

    cur = conn.cursor()
    execute_batch(cur, query, rows, page_size=1000)
    conn.commit()
    cur.close()
    return len(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Backfill Databento options - FINAL VERSION"
    )
    parser.add_argument("--underlying", type=str, help="Specific underlying (e.g., ZL)")
    parser.add_argument(
        "--start", type=str, required=True, help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true", help="Backfill all underlyings")
    parser.add_argument(
        "--batch-months", type=int, default=1, help="Months per batch (default: 1)"
    )
    args = parser.parse_args()

    print("=" * 70)
    print("DATABENTO OPTIONS BACKFILL - FINAL VERSION")
    print("Using official databento Python client with .to_df()")
    print("=" * 70)

    client = db.Historical(key=DATABENTO_API_KEY)
    conn = psycopg2.connect(DATABASE_URL)

    # Parse dates
    start_date = date.fromisoformat(args.start)
    end_date = (
        date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)
    )

    print(f"Date range: {start_date} to {end_date}")

    # Select configs
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
        # Calculate batch end
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
        print(f"Parent symbol: {config['parent']}")
        print("=" * 70)

        underlying_total = 0

        for batch_idx, (batch_start, batch_end) in enumerate(batches):
            print(f"\n  Batch {batch_idx + 1}/{len(batches)}:")

            try:
                rows = fetch_options_batch(
                    client,
                    config["parent"],
                    config["underlying"],
                    batch_start,
                    batch_end,
                )

                if rows:
                    upserted = upsert_options(conn, rows)
                    print(f"      ✓ Upserted {upserted} rows to database")
                    underlying_total += upserted

                # Rate limiting
                time.sleep(0.5)

            except Exception as e:
                print(f"      ERROR: {e}")
                import traceback

                traceback.print_exc()
                continue

        total_rows += underlying_total
        print(f"\n  [{config['underlying']}] Total: {underlying_total:,} rows")

    conn.close()

    print("\n" + "=" * 70)
    print(f"COMPLETE: {total_rows:,} total rows upserted")
    print("=" * 70)


if __name__ == "__main__":
    main()
