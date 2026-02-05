#!/usr/bin/env python3
"""
DEPRECATED: Use scripts/backfill_options_PARALLEL.py or backfill_options_RESEARCH_BASED.py instead.
This script has known issues: statistics join on instrument_id (wrong; use symbol+date)
and may produce bad event_date in edge cases.

Databento Options Historical Backfill

Fetches options data using the EXACT same approach as the Inngest daily job:
1. Fetch definition schema to get strike/expiry/option_type
2. Fetch ohlcv-1d schema for prices
3. Join and insert to mkt.options_1d

Uses parent symbology (e.g., OZL.OPT) matching the working Inngest function.

Usage:
    python scripts/backfill_options_historical.py --underlying ZL --start 2010-01-01 --end 2020-12-31
    python scripts/backfill_options_historical.py --underlying ZL --year 2015
    python scripts/backfill_options_historical.py --all --start 2015-01-01
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

# EXACT config from working Inngest function
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


def fetch_and_process_options(
    client: db.Historical,
    parent_symbol: str,
    underlying: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """
    Fetch options data using definition + ohlcv join approach.
    This matches the Inngest function exactly.
    """
    print(f"\n  Fetching definitions for {parent_symbol}...")
    print(f"    Date range: {start_date} to {end_date}")
    print(f"    Dataset: {DATASET}, Schema: definition, Stype: parent")

    # Step 1: Fetch definitions to get strike/expiry/type
    try:
        print(f"    Calling Databento API...")
        # Databento requires end > start, so add 1 day to end
        end_adjusted = end_date + timedelta(days=1)

        def_data = client.timeseries.get_range(
            dataset=DATASET,
            schema="definition",
            symbols=[parent_symbol],
            stype_in="parent",
            start=start_date.isoformat(),
            end=end_adjusted.isoformat(),
        )
        print(f"    API call complete, processing...")

        def_df = def_data.to_df()
        if def_df.empty:
            print(f"    No definitions found")
            return []

        print(f"    Found {len(def_df)} option definitions")

    except Exception as e:
        print(f"    Definition fetch error: {e}")
        return []

    # Step 2: Fetch OHLCV data
    print(f"  Fetching OHLCV for {parent_symbol}...")
    try:
        ohlcv_data = client.timeseries.get_range(
            dataset=DATASET,
            schema="ohlcv-1d",
            symbols=[parent_symbol],
            stype_in="parent",
            start=start_date.isoformat(),
            end=end_adjusted.isoformat(),
        )

        ohlcv_df = ohlcv_data.to_df()
        if ohlcv_df.empty:
            print(f"    No OHLCV data found")
            return []

        print(f"    Found {len(ohlcv_df)} OHLCV bars")

    except Exception as e:
        print(f"    OHLCV fetch error: {e}")
        return []

    # Step 2b: Fetch ALL statistics (15 stat_types)
    # StatType mapping from databento:
    # 1=OPENING_PRICE, 3=SETTLEMENT_PRICE, 4=TRADING_SESSION_LOW_PRICE, 5=TRADING_SESSION_HIGH_PRICE
    # 6=CLEARED_VOLUME, 7=LOWEST_OFFER(ask), 8=HIGHEST_BID(bid), 9=OPEN_INTEREST, 11=CLOSE_PRICE, 12=NET_CHANGE
    # 13=VWAP, 14=VOLATILITY(IV), 15=DELTA, 10=FIXING_PRICE, 2=INDICATIVE_OPENING_PRICE, 16=UNCROSSING_PRICE
    print(f"  Fetching ALL statistics (15 types) for {parent_symbol}...")
    try:
        stats_data = client.timeseries.get_range(
            dataset=DATASET,
            schema="statistics",
            symbols=[parent_symbol],
            stype_in="parent",
            start=start_date.isoformat(),
            end=end_adjusted.isoformat(),
        )

        stats_df = stats_data.to_df()
        if not stats_df.empty:
            print(f"    Found {len(stats_df)} statistics records")
            print(f"    stat_type breakdown:")
            for st in sorted(stats_df["stat_type"].unique()):
                count = (stats_df["stat_type"] == st).sum()
                print(f"      stat_type={st}: {count:6} records")
        else:
            stats_df = pd.DataFrame()
            print(f"    No statistics data found")

    except Exception as e:
        print(f"    Statistics fetch error: {e}")
        stats_df = pd.DataFrame()

    # Step 3: Join definition, OHLCV, and statistics (open interest)
    ohlcv_df = ohlcv_df.reset_index()
    def_df = def_df.reset_index()

    # Extract fields we need from definition
    if "instrument_id" not in def_df.columns or "instrument_id" not in ohlcv_df.columns:
        print("    ERROR: Missing instrument_id column for join")
        return []

    # Merge definition with OHLCV
    merged = ohlcv_df.merge(
        def_df[["instrument_id", "strike_price", "expiration", "instrument_class"]],
        on="instrument_id",
        how="inner",
    )

    if merged.empty:
        print(f"    No data after join")
        return []

    print(f"    Merged OHLCV+Definition: {len(merged)} option bars")

    # Merge with ALL statistics if available
    if not stats_df.empty and "instrument_id" in stats_df.columns:
        stats_df = stats_df.reset_index()
        # Create event_date from ts_event
        stats_df["event_date"] = pd.to_datetime(stats_df["ts_event"]).dt.date
        merged["event_date"] = pd.to_datetime(
            merged.name if hasattr(merged, "name") else merged["ts_event"]
        ).dt.date

        # Pivot ALL stat_types to extract every field
        # Map stat_types to column names and which field (price or quantity)
        stat_map = {
            9: ("open_interest", "quantity"),  # Open Interest
            8: ("bid", "price"),  # Highest Bid
            7: ("ask", "price"),  # Lowest Offer (ask)
            12: ("change", "price"),  # Net Change
            14: ("implied_volatility", "price"),  # Volatility (IV)
            3: ("settlement_price", "price"),  # Settlement
            1: (
                "opening_price_stat",
                "price",
            ),  # Opening (from stats, different from OHLCV open)
            11: ("close_price_stat", "price"),  # Close (from stats)
            5: ("high_price_stat", "price"),  # Session High
            4: ("low_price_stat", "price"),  # Session Low
            6: ("cleared_volume", "quantity"),  # Cleared Volume
            13: ("vwap", "price"),  # VWAP
            15: ("delta", "price"),  # Delta
            10: ("fixing_price", "price"),  # Fixing Price
            2: ("indicative_opening", "price"),  # Indicative Opening
        }

        for stat_type, (col_name, field) in stat_map.items():
            subset = stats_df[stats_df["stat_type"] == stat_type].copy()
            if len(subset) > 0:
                subset = subset[["instrument_id", "event_date", field]].copy()
                subset.rename(columns={field: col_name}, inplace=True)

                # Merge
                merged = merged.merge(
                    subset, on=["instrument_id", "event_date"], how="left"
                )

        # Report coverage for critical fields
        critical_fields = [
            "open_interest",
            "bid",
            "ask",
            "change",
            "implied_volatility",
        ]
        print(f"    Statistics coverage:")
        for field in critical_fields:
            if field in merged.columns:
                pct = merged[field].notna().sum() / len(merged) * 100
                print(f"      {field}: {pct:.1f}%")

    # Step 4: Transform to database format
    rows = []
    errors = []

    for idx, row in merged.iterrows():
        try:
            # Parse event date - it's in the index
            event_date = pd.to_datetime(
                row.name if hasattr(row, "name") and row.name else row.get("ts_event")
            ).date()
            if event_date.year < 2010:
                continue  # Never insert bad/epoch dates into mkt.options_1d

            # Parse expiration
            exp_ts = row["expiration"]
            if isinstance(exp_ts, int):
                expiration = datetime.fromtimestamp(exp_ts / 1e9).date()
            else:
                expiration = pd.to_datetime(exp_ts).date()

            # Parse strike (Databento uses fixed-point, need to convert)
            strike = float(row["strike_price"]) / 1e9

            # Option type
            option_type = str(row["instrument_class"])
            if option_type not in ("C", "P"):
                continue

            # Parse prices (also fixed-point)
            close_val = float(row["close"]) / 1e9 if row["close"] else None
            if close_val is None or close_val <= 0:
                continue

            record = {
                "underlying": underlying,
                "event_date": event_date,
                "expiration": expiration,
                "strike": strike,
                "option_type": option_type,
                # OHLCV fields
                "open": float(row["open"]) / 1e9 if row.get("open") else None,
                "high": float(row["high"]) / 1e9 if row.get("high") else None,
                "low": float(row["low"]) / 1e9 if row.get("low") else None,
                "close": close_val,
                "volume": int(row["volume"]) if row.get("volume") else None,
                # ALL statistics fields
                "open_interest": (
                    int(row["open_interest"])
                    if pd.notna(row.get("open_interest"))
                    else None
                ),
                "bid": float(row["bid"]) if pd.notna(row.get("bid")) else None,
                "ask": float(row["ask"]) if pd.notna(row.get("ask")) else None,
                "change": float(row["change"]) if pd.notna(row.get("change")) else None,
                "premium": (
                    float(row.get("settlement_price"))
                    if pd.notna(row.get("settlement_price"))
                    else None
                ),
                # Hash for dedup
                "row_hash": compute_row_hash(
                    underlying, event_date, expiration, strike, option_type
                ),
            }
            rows.append(record)

        except Exception as e:
            errors.append(str(e))
            if len(errors) <= 5:  # Only print first 5 errors
                print(f"    Row parse error: {e}")
            continue

    if errors and len(errors) > 5:
        print(f"    ... and {len(errors) - 5} more errors")

    return rows


def upsert_options(conn, rows: list[dict]) -> int:
    """Upsert options data to mkt.options_1d with ALL available fields."""
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
    parser = argparse.ArgumentParser(
        description="Backfill Databento options - MATCH INNGEST FUNCTION"
    )
    parser.add_argument(
        "--underlying", type=str, help="Specific underlying (e.g., ZL, ES)"
    )
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument(
        "--end", type=str, help="End date (YYYY-MM-DD), defaults to yesterday"
    )
    parser.add_argument("--year", type=int, help="Single year to backfill (e.g., 2015)")
    parser.add_argument("--all", action="store_true", help="Backfill all underlyings")
    args = parser.parse_args()

    print("=" * 70)
    print("DATABENTO OPTIONS HISTORICAL BACKFILL")
    print("Matching Inngest function logic exactly")
    print("=" * 70)

    client = db.Historical(key=DATABENTO_API_KEY)
    conn = psycopg2.connect(DATABASE_URL)

    # Determine date range
    if args.year:
        start_date = date(args.year, 1, 1)
        end_date = date(args.year, 12, 31)
    elif args.start:
        start_date = date.fromisoformat(args.start)
        end_date = (
            date.fromisoformat(args.end)
            if args.end
            else date.today() - timedelta(days=1)
        )
    else:
        print("ERROR: Must specify --year or --start")
        sys.exit(1)

    print(f"Date range: {start_date} to {end_date}")

    # Select configs
    configs = OPTIONS_CONFIG
    if args.underlying and not args.all:
        configs = [
            c for c in OPTIONS_CONFIG if c["underlying"] == args.underlying.upper()
        ]
        if not configs:
            print(f"ERROR: Unknown underlying {args.underlying}")
            print(f"Available: {[c['underlying'] for c in OPTIONS_CONFIG]}")
            return

    print(f"Underlyings: {len(configs)}")

    total_rows = 0

    # Batch by month for large ranges (statistics API is slow)
    current = start_date
    batches = []
    while current <= end_date:
        month_end = date(current.year, current.month, 1)
        # Add one month
        if current.month == 12:
            month_end = date(current.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(current.year, current.month + 1, 1) - timedelta(days=1)
        batch_end = min(month_end, end_date)
        batches.append((current, batch_end))
        current = batch_end + timedelta(days=1)

    print(f"Processing in {len(batches)} monthly batches")

    for config in configs:
        print(f"\n{'='*70}")
        print(f"[{config['underlying']}] {config['name']}")
        print(f"Parent symbol: {config['parent']}")
        print(f"{'='*70}")

        underlying_total = 0

        for batch_idx, (batch_start, batch_end) in enumerate(batches):
            print(
                f"\n  Batch {batch_idx+1}/{len(batches)}: {batch_start} to {batch_end}"
            )

            # Fetch and process this batch
            rows = fetch_and_process_options(
                client, config["parent"], config["underlying"], batch_start, batch_end
            )

            if rows:
                print(f"    Upserting {len(rows)} rows...")
                upserted = upsert_options(conn, rows)
                print(f"    ✓ Upserted {upserted} rows")
                underlying_total += upserted
            else:
                print(f"    No data for this batch")

        total_rows += underlying_total
        print(f"\n  [{config['underlying']}] Total: {underlying_total} rows")

    conn.close()

    print("\n" + "=" * 70)
    print(f"COMPLETE: {total_rows} total rows upserted")
    print("=" * 70)


if __name__ == "__main__":
    main()
