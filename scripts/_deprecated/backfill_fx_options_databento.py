#!/usr/bin/env python3
"""
Backfill FX options from Databento into mkt.options_1d.

FX futures options on CME:
- 6E (Euro), 6J (Yen), 6B (Pound), 6C (CAD), 6A (AUD), 6S (CHF), 6N (NZD), 6M (MXN)

Pulls all 15 stat schemas from 2010-01-01 to 2026-02-02.

Usage:
    .venv/bin/python scripts/backfill_fx_options_databento.py
"""

import os
import sys
import hashlib
from datetime import date, timedelta
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values

try:
    import databento as db
except ImportError:
    print("ERROR: databento not installed. Run: pip install databento")
    sys.exit(1)

DATABASE_URL = os.environ.get("DATABASE_URL")
DATABENTO_API_KEY = os.environ.get("DATABENTO_API_KEY")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)
if not DATABENTO_API_KEY:
    print("ERROR: DATABENTO_API_KEY not set")
    sys.exit(1)

# FX options parent symbols
FX_OPTIONS = [
    "O6E.OPT",  # Euro FX options
    "O6J.OPT",  # Japanese Yen options
    "O6B.OPT",  # British Pound options
    "O6C.OPT",  # Canadian Dollar options
    "O6A.OPT",  # Australian Dollar options
    "O6S.OPT",  # Swiss Franc options
    "O6N.OPT",  # New Zealand Dollar options
    "O6M.OPT",  # Mexican Peso options
]

DATASET = "GLBX.MDP3"
START_DATE = date(2010, 6, 6)  # CME options data starts ~2010
END_DATE = date(2026, 2, 2)
BATCH_MONTHS = 3  # Process in 3-month batches

# Stat type mapping (Databento stat_type -> column name)
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


def compute_row_hash(record: dict) -> str:
    """Compute deterministic hash for a record."""
    key = f"{record['underlying']}|{record['event_date']}|{record['expiration']}|{record['strike']}|{record['option_type']}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def fetch_and_process_batch(
    client: db.Historical,
    symbol: str,
    start: date,
    end: date,
) -> list[dict]:
    """
    Fetch definitions, OHLCV, and statistics for a symbol/date range.
    Returns list of record dicts ready for upsert.
    """
    records = {}  # Key: (underlying, event_date, expiration, strike, option_type)

    # 1. Fetch definitions to get contract metadata
    try:
        defs = client.timeseries.get_range(
            dataset=DATASET,
            schema="definition",
            symbols=[symbol],
            stype_in="parent",
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
        )

        def_map = {}  # instrument_id -> metadata
        for row in defs:
            inst_id = getattr(row, "instrument_id", None)
            if inst_id is None:
                continue

            # Extract contract info
            strike = getattr(row, "strike_price", None)
            if strike is not None:
                strike = float(strike) / 1e9  # Databento uses fixed-point

            expiration = getattr(row, "expiration", None)
            if expiration is not None:
                expiration = (
                    expiration.date() if hasattr(expiration, "date") else expiration
                )

            inst_class = getattr(row, "instrument_class", None)
            if inst_class == "C":
                opt_type = "call"
            elif inst_class == "P":
                opt_type = "put"
            else:
                opt_type = str(inst_class) if inst_class else None

            raw_sym = getattr(row, "raw_symbol", None) or getattr(row, "symbol", None)

            def_map[inst_id] = {
                "strike": strike,
                "expiration": expiration,
                "option_type": opt_type,
                "symbol": str(raw_sym) if raw_sym else None,
            }
    except Exception as e:
        print(f"    Definition fetch failed: {e}")
        return []

    if not def_map:
        return []

    # Underlying symbol (e.g., "6E" from "O6E.OPT")
    underlying = symbol.replace("O", "").replace(".OPT", "")

    # 2. Fetch OHLCV
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

            # Fill OHLCV
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
        print(f"    OHLCV fetch failed: {e}")

    # 3. Fetch statistics (all 15 stat types)
    try:
        stats = client.timeseries.get_range(
            dataset=DATASET,
            schema="statistics",
            symbols=[symbol],
            stype_in="parent",
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
        )

        # Build stats lookup by (symbol, date)
        stats_lookup = {}
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

            if stat_type is None or stat_type not in STAT_TYPE_MAP:
                continue

            col_name = STAT_TYPE_MAP[stat_type]
            key = (
                underlying,
                event_date,
                def_info["expiration"],
                def_info["strike"],
                def_info["option_type"],
            )

            # Get the value
            price = getattr(row, "price", None)
            quantity = getattr(row, "quantity", None)

            if price is not None and price != 2147483647:  # UNDEFINED sentinel
                value = float(price) / 1e9
            elif quantity is not None:
                value = int(quantity)
            else:
                continue

            if key in records:
                records[key][col_name] = value
            elif key not in records:
                # Create new record if we have stats but no OHLCV
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
        print(f"    Statistics fetch failed: {e}")

    return list(records.values())


def upsert_options(conn, records: list[dict]) -> int:
    """Upsert option records into mkt.options_1d."""
    if not records:
        return 0

    cur = conn.cursor()

    rows = []
    for r in records:
        row_hash = compute_row_hash(r)
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
    return len(rows)


def main():
    print("=" * 70)
    print("FX Options Backfill from Databento")
    print(f"Date range: {START_DATE} to {END_DATE}")
    print(f"Symbols: {', '.join(FX_OPTIONS)}")
    print("=" * 70)

    client = db.Historical(key=DATABENTO_API_KEY)
    conn = psycopg2.connect(DATABASE_URL)

    total_rows = 0

    for symbol in FX_OPTIONS:
        underlying = symbol.replace("O", "").replace(".OPT", "")
        print(f"\n[{underlying}] Processing {symbol}...")

        # Process in monthly batches
        current = START_DATE
        symbol_rows = 0

        while current < END_DATE:
            batch_end = min(current + timedelta(days=BATCH_MONTHS * 30), END_DATE)

            try:
                records = fetch_and_process_batch(client, symbol, current, batch_end)
                if records:
                    count = upsert_options(conn, records)
                    symbol_rows += count
                    print(f"  {current} to {batch_end}: +{count} rows")
                else:
                    print(f"  {current} to {batch_end}: no data")
            except Exception as e:
                print(f"  {current} to {batch_end}: ERROR - {e}")

            current = batch_end + timedelta(days=1)

        total_rows += symbol_rows
        print(f"  Total for {underlying}: {symbol_rows} rows")

    conn.close()

    print("\n" + "=" * 70)
    print(f"DONE: {total_rows:,} total rows upserted")
    print("=" * 70)


if __name__ == "__main__":
    main()
