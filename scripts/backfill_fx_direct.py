#!/usr/bin/env python3
"""
Direct FX options backfill - no Ray, direct database loading.

Usage:
    .venv/bin/python scripts/backfill_fx_direct.py --underlying 6S
"""

import os
import sys
import argparse
from datetime import date, timedelta

import psycopg2
from psycopg2.extras import execute_batch

try:
    import databento as db
except ImportError:
    print("ERROR: databento not installed")
    sys.exit(1)

DATABASE_URL = os.environ.get("DATABASE_URL")
DATABENTO_API_KEY = os.environ.get("DATABENTO_API_KEY")

if not DATABASE_URL or not DATABENTO_API_KEY:
    print("ERROR: Missing DATABASE_URL or DATABENTO_API_KEY")
    sys.exit(1)

DATASET = "GLBX.MDP3"

# Map underlying to parent symbol
SYMBOL_MAP = {
    "6E": "EUU.OPT",
    "6J": "JPU.OPT",
    "6B": "GBU.OPT",
    "6C": "CAU.OPT",
    "6A": "ADU.OPT",
    "6S": "SZU.OPT",  # Swiss Franc
    "6N": "NEU.OPT",  # New Zealand Dollar
    "6M": "MPU.OPT",  # Mexican Peso
    "6L": "BRU.OPT",  # Brazilian Real
    "6Z": "ZRU.OPT",  # South African Rand (try ZRU instead of RAU)
}

# Stat type mapping
STAT_TYPE_MAP = {
    1: "opening_price_stat",
    2: "indicative_opening",
    3: "session_low_stat",
    4: "session_high_stat",
    5: "cleared_volume",
    6: "open_interest",
    7: "fixing_price",
    8: "close_stat",
    9: "vwap",
    10: "bid",
    11: "ask",
    13: "implied_volatility",
    14: "delta",
    17: "premium",
    19: "change",
}


def fetch_and_load_underlying(underlying: str, start_date: date, end_date: date) -> int:
    """Fetch and load all data for one underlying."""
    symbol = SYMBOL_MAP.get(underlying)
    if not symbol:
        print(f"ERROR: Unknown underlying {underlying}")
        return 0

    print(f"Loading {underlying} ({symbol}) from {start_date} to {end_date}")

    client = db.Historical(key=DATABENTO_API_KEY)
    conn = psycopg2.connect(DATABASE_URL)
    total_loaded = 0

    # Process in 6-month chunks
    current = start_date
    while current <= end_date:
        chunk_end = min(current + timedelta(days=180), end_date)

        try:
            # Fetch definitions
            defs = client.timeseries.get_range(
                dataset=DATASET,
                schema="definition",
                symbols=[symbol],
                stype_in="parent",
                start=current.isoformat(),
                end=(chunk_end + timedelta(days=1)).isoformat(),
            )

            def_map = {}
            for row in defs:
                inst_id = getattr(row, "instrument_id", None)
                if inst_id is None:
                    continue

                strike = getattr(row, "strike_price", None)
                if strike is not None:
                    strike = float(strike) / 1e9

                expiration = getattr(row, "expiration", None)
                if expiration is not None:
                    if hasattr(expiration, "date"):
                        expiration = expiration.date()
                    elif isinstance(expiration, int):
                        if expiration > 1000000000:
                            from datetime import datetime

                            expiration = datetime.fromtimestamp(expiration / 1e9).date()
                        else:
                            expiration = date.fromordinal(expiration)

                inst_class = getattr(row, "instrument_class", None)
                if inst_class == "C":
                    opt_type = "call"
                elif inst_class == "P":
                    opt_type = "put"
                else:
                    opt_type = str(inst_class) if inst_class else None

                raw_sym = getattr(row, "raw_symbol", None) or getattr(
                    row, "symbol", None
                )

                def_map[inst_id] = {
                    "strike": strike,
                    "expiration": expiration,
                    "option_type": opt_type,
                    "symbol": str(raw_sym) if raw_sym else None,
                }

            if not def_map:
                current = chunk_end + timedelta(days=1)
                continue

            # Fetch OHLCV
            ohlcv = client.timeseries.get_range(
                dataset=DATASET,
                schema="ohlcv-1d",
                symbols=[symbol],
                stype_in="parent",
                start=current.isoformat(),
                end=(chunk_end + timedelta(days=1)).isoformat(),
            )

            records = {}
            for row in ohlcv:
                inst_id = getattr(row, "instrument_id", None)
                if inst_id not in def_map:
                    continue

                def_info = def_map[inst_id]
                ts = getattr(row, "ts_event", None)
                if ts is None:
                    continue

                event_date = ts.date() if hasattr(ts, "date") else ts
                key = (
                    underlying,
                    event_date,
                    def_info["expiration"],
                    def_info["strike"],
                    def_info["option_type"],
                )

                if key not in records:
                    records[key] = {
                        "underlying": underlying,
                        "event_date": event_date,
                        "expiration": def_info["expiration"],
                        "strike": def_info["strike"],
                        "option_type": def_info["option_type"],
                        "symbol": def_info.get("symbol"),
                        "open": (
                            float(getattr(row, "open", 0)) / 1e9
                            if getattr(row, "open", None)
                            else None
                        ),
                        "high": (
                            float(getattr(row, "high", 0)) / 1e9
                            if getattr(row, "high", None)
                            else None
                        ),
                        "low": (
                            float(getattr(row, "low", 0)) / 1e9
                            if getattr(row, "low", None)
                            else None
                        ),
                        "close": (
                            float(getattr(row, "close", 0)) / 1e9
                            if getattr(row, "close", None)
                            else None
                        ),
                        "volume": (
                            int(getattr(row, "volume", 0))
                            if getattr(row, "volume", None)
                            else None
                        ),
                    }

            # Fetch statistics
            stats = client.timeseries.get_range(
                dataset=DATASET,
                schema="statistics",
                symbols=[symbol],
                stype_in="parent",
                start=current.isoformat(),
                end=(chunk_end + timedelta(days=1)).isoformat(),
            )

            for row in stats:
                inst_id = getattr(row, "instrument_id", None)
                if inst_id not in def_map:
                    continue

                def_info = def_map[inst_id]
                ts = getattr(row, "ts_event", None) or getattr(row, "ts_recv", None)
                if ts is None:
                    continue

                event_date = ts.date() if hasattr(ts, "date") else ts
                stat_type = getattr(row, "stat_type", None)

                if stat_type is None:
                    continue

                # Convert stat_type to int if needed
                if hasattr(stat_type, "value"):
                    stat_type = stat_type.value
                stat_type = int(stat_type)

                if stat_type not in STAT_TYPE_MAP:
                    continue

                col_name = STAT_TYPE_MAP[stat_type]
                price = getattr(row, "price", None)
                quantity = getattr(row, "quantity", None)

                if price is not None and price != 2147483647:  # UNDEFINED
                    value = float(price) / 1e9
                elif quantity is not None:
                    value = int(quantity)
                else:
                    continue

                key = (
                    underlying,
                    event_date,
                    def_info["expiration"],
                    def_info["strike"],
                    def_info["option_type"],
                )

                if key not in records:
                    records[key] = {
                        "underlying": underlying,
                        "event_date": event_date,
                        "expiration": def_info["expiration"],
                        "strike": def_info["strike"],
                        "option_type": def_info["option_type"],
                        "symbol": def_info.get("symbol"),
                        "open": None,
                        "high": None,
                        "low": None,
                        "close": None,
                        "volume": None,
                    }
                records[key][col_name] = value

            # Load to database
            if records:
                cur = conn.cursor()

                rows = []
                for r in records.values():
                    rows.append(
                        (
                            r["underlying"],
                            r["event_date"],
                            r["expiration"],
                            r["strike"],
                            r["option_type"],
                            r["open"],
                            r["high"],
                            r["low"],
                            r["close"],
                            r["volume"],
                            r.get("bid"),
                            r.get("ask"),
                            r.get("change"),
                            r.get("premium"),
                            r.get("opening_price_stat"),
                            r.get("indicative_opening"),
                            r.get("session_low_stat"),
                            r.get("session_high_stat"),
                            r.get("cleared_volume"),
                            r.get("fixing_price"),
                            r.get("close_stat"),
                            r.get("vwap"),
                            r.get("implied_volatility"),
                            r.get("delta"),
                            "databento",
                            f"{r['underlying']}|{r['event_date']}|{r['expiration']}|{r['strike']}|{r['option_type']}",
                        )
                    )

                execute_batch(
                    cur,
                    """
                    INSERT INTO mkt.options_1d
                        (underlying, event_date, expiration, strike, option_type,
                         open, high, low, close, volume,
                         bid, ask, change, premium,
                         opening_price_stat, indicative_opening,
                         session_low_stat, session_high_stat,
                         cleared_volume, fixing_price, close_stat, vwap,
                         implied_volatility, delta,
                         source, row_hash, ingested_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'databento', %s, NOW())
                    ON CONFLICT (underlying, event_date, expiration, strike, option_type) DO UPDATE SET
                        open = COALESCE(EXCLUDED.open, mkt.options_1d.open),
                        high = COALESCE(EXCLUDED.high, mkt.options_1d.high),
                        low = COALESCE(EXCLUDED.low, mkt.options_1d.low),
                        close = COALESCE(EXCLUDED.close, mkt.options_1d.close),
                        volume = COALESCE(EXCLUDED.volume, mkt.options_1d.volume),
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
                    """,
                    rows,
                    page_size=500,
                )

                conn.commit()
                cur.close()

                chunk_loaded = len(rows)
                total_loaded += chunk_loaded
                print(f"  {current} to {chunk_end}: +{chunk_loaded} rows")

        except Exception as e:
            print(f"  ERROR in {current} to {chunk_end}: {e}")

        current = chunk_end + timedelta(days=1)

    conn.close()
    return total_loaded


def main():
    parser = argparse.ArgumentParser(description="Direct FX options backfill")
    parser.add_argument(
        "--underlying", required=True, help="FX underlying (6B, 6C, etc.)"
    )
    parser.add_argument("--start", default="2010-06-06", help="Start date")
    parser.add_argument("--end", default="2026-02-02", help="End date")
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)

    print(f"Direct FX Options Backfill: {args.underlying}")
    print(f"Date range: {start_date} to {end_date}")
    print("-" * 50)

    total_loaded = fetch_and_load_underlying(args.underlying, start_date, end_date)

    print("-" * 50)
    print(f"COMPLETED: {total_loaded:,} rows loaded for {args.underlying}")


if __name__ == "__main__":
    main()
