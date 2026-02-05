#!/usr/bin/env python3
"""
Simple FX options backfill - no Ray, direct processing.

Usage:
    .venv/bin/python scripts/backfill_fx_options_simple.py --underlying 6B
"""

import os
import sys
import argparse
import hashlib
from datetime import date, timedelta

import psycopg2
from psycopg2.extras import execute_values

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


def compute_row_hash(
    underlying: str, event_date: date, expiration: date, strike: float, option_type: str
) -> str:
    key = f"{underlying}|{event_date}|{expiration}|{strike}|{option_type}"
    return hashlib.sha256(key.encode()).hexdigest()


def process_batch(client, symbol: str, underlying: str, start: date, end: date) -> int:
    """Process one batch and return rows loaded."""
    print(f"  Processing {start} to {end}...")

    # Fetch definitions
    try:
        defs = client.timeseries.get_range(
            dataset=DATASET,
            schema="definition",
            symbols=[symbol],
            stype_in="parent",
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
        )
    except Exception as e:
        print(f"    Definitions failed: {e}")
        return 0

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
            elif isinstance(expiration, int) and expiration > 100000:  # Timestamp
                from datetime import datetime

                expiration = datetime.fromtimestamp(expiration / 1e9).date()
            else:
                expiration = expiration

        inst_class = getattr(row, "instrument_class", None)
        if inst_class == "C":
            opt_type = "call"
        elif inst_class == "P":
            opt_type = "put"
        else:
            opt_type = None

        raw_sym = getattr(row, "raw_symbol", None) or getattr(row, "symbol", None)

        def_map[inst_id] = {
            "strike": strike,
            "expiration": expiration,
            "option_type": opt_type,
            "symbol": str(raw_sym) if raw_sym else None,
        }

    if not def_map:
        return 0

    # Fetch OHLCV
    records = {}
    try:
        ohlcv = client.timeseries.get_range(
            dataset=DATASET,
            schema="ohlcv-1d",
            symbols=[symbol],
            stype_in="parent",
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
        )

        for row in ohlcv:
            inst_id = getattr(row, "instrument_id", None)
            if inst_id not in def_map:
                continue

            def_info = def_map[inst_id]
            ts = getattr(row, "ts_event", None)
            if ts is None:
                continue

            event_date = ts.date()
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
                    "open_interest": None,
                    "bid": None,
                    "ask": None,
                    "change": None,
                    "premium": None,
                    "opening_price_stat": None,
                    "indicative_opening": None,
                    "session_low_stat": None,
                    "session_high_stat": None,
                    "cleared_volume": None,
                    "fixing_price": None,
                    "close_stat": None,
                    "vwap": None,
                    "implied_volatility": None,
                    "delta": None,
                }

            records[key]["open"] = (
                float(getattr(row, "open", 0)) / 1e9
                if getattr(row, "open", None)
                else None
            )
            records[key]["high"] = (
                float(getattr(row, "high", 0)) / 1e9
                if getattr(row, "high", None)
                else None
            )
            records[key]["low"] = (
                float(getattr(row, "low", 0)) / 1e9
                if getattr(row, "low", None)
                else None
            )
            records[key]["close"] = (
                float(getattr(row, "close", 0)) / 1e9
                if getattr(row, "close", None)
                else None
            )
            records[key]["volume"] = (
                int(getattr(row, "volume", 0)) if getattr(row, "volume", None) else None
            )
    except Exception as e:
        print(f"    OHLCV failed: {e}")

    # Fetch statistics
    try:
        stats = client.timeseries.get_range(
            dataset=DATASET,
            schema="statistics",
            symbols=[symbol],
            stype_in="parent",
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
        )

        for row in stats:
            inst_id = getattr(row, "instrument_id", None)
            if inst_id not in def_map:
                continue

            def_info = def_map[inst_id]
            ts = getattr(row, "ts_event", None) or getattr(row, "ts_recv", None)
            if ts is None:
                continue

            event_date = ts.date()
            stat_type = getattr(row, "stat_type", None)

            if stat_type is None or stat_type not in STAT_TYPE_MAP:
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
                    "open_interest": None,
                    "bid": None,
                    "ask": None,
                    "change": None,
                    "premium": None,
                    "opening_price_stat": None,
                    "indicative_opening": None,
                    "session_low_stat": None,
                    "session_high_stat": None,
                    "cleared_volume": None,
                    "fixing_price": None,
                    "close_stat": None,
                    "vwap": None,
                    "implied_volatility": None,
                    "delta": None,
                }
            records[key][col_name] = value
    except Exception as e:
        print(f"    Statistics failed: {e}")

    # Upsert to database
    if not records:
        return 0

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    rows = []
    for r in list(records.values()):
        row_hash = compute_row_hash(
            r["underlying"],
            r["event_date"],
            r["expiration"],
            r["strike"],
            r["option_type"],
        )
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
                r["open_interest"],
                r["bid"],
                r["ask"],
                r["change"],
                r["premium"],
                r["opening_price_stat"],
                r["indicative_opening"],
                r["session_low_stat"],
                r["session_high_stat"],
                r["cleared_volume"],
                r["fixing_price"],
                r["close_stat"],
                r["vwap"],
                r["implied_volatility"],
                r["delta"],
                "databento",
                row_hash,
            )
        )

    execute_values(
        cur,
        """
        INSERT INTO mkt.options_1d
            (underlying, event_date, expiration, strike, option_type,
             open, high, low, close, volume, open_interest,
             bid, ask, change, premium,
             opening_price_stat, indicative_opening,
             session_low_stat, session_high_stat,
             cleared_volume, fixing_price, close_stat, vwap,
             implied_volatility, delta,
             source, row_hash, ingested_at)
        VALUES %s
        ON CONFLICT (underlying, event_date, expiration, strike, option_type) DO UPDATE SET
            open = COALESCE(EXCLUDED.open, mkt.options_1d.open),
            high = COALESCE(EXCLUDED.high, mkt.options_1d.high),
            low = COALESCE(EXCLUDED.low, mkt.options_1d.low),
            close = COALESCE(EXCLUDED.close, mkt.options_1d.close),
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
        """,
        rows,
        template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())",
        page_size=500,
    )

    conn.commit()
    conn.close()
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Simple FX options backfill")
    parser.add_argument(
        "--underlying", required=True, help="FX underlying (6B, 6C, etc.)"
    )
    parser.add_argument("--start", default="2010-06-06", help="Start date")
    parser.add_argument("--end", default="2026-02-02", help="End date")
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)

    print(f"FX Options Backfill: {args.underlying}")
    print(f"Date range: {start_date} to {end_date}")

    client = db.Historical(key=DATABENTO_API_KEY)
    # Map underlying to correct CME parent symbol
    symbol_map = {
        "6E": "EUU.OPT",
        "6J": "JPU.OPT",
        "6B": "GBU.OPT",
        "6C": "CAU.OPT",
        "6A": "ADU.OPT",
        "6S": "SFU.OPT",
        "6N": "NEU.OPT",
        "6M": "MPU.OPT",
        "6L": "BRU.OPT",
        "6Z": "RAU.OPT",
    }
    symbol = symbol_map.get(args.underlying, f"{args.underlying}.OPT")

    # Process in monthly batches
    current = start_date
    total_rows = 0

    while current < end_date:
        batch_end = min(current + timedelta(days=90), end_date)  # 3-month batches
        rows = process_batch(client, symbol, args.underlying, current, batch_end)
        total_rows += rows
        print(f"  Batch: {rows} rows")
        current = batch_end + timedelta(days=1)

    print(f"DONE: {total_rows:,} total rows loaded for {args.underlying}")


if __name__ == "__main__":
    main()
