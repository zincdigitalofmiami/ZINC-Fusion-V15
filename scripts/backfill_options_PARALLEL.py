#!/usr/bin/env python3
"""
Databento Options Backfill - RAY DISTRIBUTED (across 2 Mac Minis via Thunderbolt)

Uses Ray cluster for distributed processing across Mac A (4 CPUs) + Mac B (10 CPUs).
No need for --worker-index or --worker-total - Ray handles distribution automatically.

Examples:
  # All underlyings, distributed across both Macs:
  python scripts/backfill_options_PARALLEL.py --all --start 2010-06-06 --end 2026-02-02

Stop any existing backfill first: pkill -f backfill_options
"""

import os
import sys
import argparse
import hashlib
from datetime import date, datetime, timedelta
from pathlib import Path
import ray
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv
import pandas as pd
import time

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
    {"parent": "JPU.OPT", "underlying": "6J", "name": "Japanese Yen FX Options"},
    {"parent": "GBU.OPT", "underlying": "6B", "name": "British Pound FX Options"},
    {"parent": "CAU.OPT", "underlying": "6C", "name": "Canadian Dollar FX Options"},
    {"parent": "ADU.OPT", "underlying": "6A", "name": "Australian Dollar FX Options"},
    {"parent": "SFU.OPT", "underlying": "6S", "name": "Swiss Franc FX Options"},
    {"parent": "NEU.OPT", "underlying": "6N", "name": "New Zealand Dollar FX Options"},
    {"parent": "MPU.OPT", "underlying": "6M", "name": "Mexican Peso FX Options"},
    {"parent": "BRU.OPT", "underlying": "6L", "name": "Brazilian Real FX Options"},
    {"parent": "RAU.OPT", "underlying": "6Z", "name": "South African Rand FX Options"},
]
DATASET = "GLBX.MDP3"


def compute_row_hash(
    underlying: str, event_date: date, expiration: date, strike: float, option_type: str
) -> str:
    key = f"{underlying}|{event_date}|{expiration}|{strike}|{option_type}"
    return hashlib.sha256(key.encode()).hexdigest()


def extract_date(ts) -> date | None:
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
        except Exception:
            return None
    if hasattr(ts, "date"):
        try:
            return ts.date()
        except Exception:
            return None
    return None


def fetch_ohlcv_with_definitions(
    client,
    parent_symbol: str,
    underlying: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    start_str = start_date.isoformat()
    end_str = (end_date + timedelta(days=1)).isoformat()

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
            return []
        def_df = def_df.reset_index()
    except Exception:
        return []

    def_map = {}
    for _, row in def_df.iterrows():
        inst_class = str(row.get("instrument_class", ""))
        if inst_class not in ("C", "P"):
            continue
        inst_id = row.get("instrument_id")
        if inst_id is None:
            continue
        strike_raw = row.get("strike_price", 0)
        strike = float(strike_raw) / 1e9 if strike_raw else 0
        if strike <= 0:
            continue
        exp_raw = row.get("expiration")
        expiration = extract_date(exp_raw)
        if not expiration:
            continue
        # Symbol from definition (for joining with statistics); raw_symbol is CME contract symbol
        raw_sym = row.get("raw_symbol") or row.get("symbol")
        def_map[inst_id] = {
            "strike": strike,
            "expiration": expiration,
            "option_type": inst_class,
            "symbol": str(raw_sym) if raw_sym is not None else None,
        }

    if not def_map:
        return []

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
            return []
        ohlcv_df = ohlcv_df.reset_index()
    except Exception:
        return []

    # Fetch statistics from Databento (real API); join by symbol + event_date
    stats_lookup = {}
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
        if not stats_df.empty and "stat_type" in stats_df.columns:
            stats_df = stats_df.reset_index()
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
            for _, srow in stats_df.iterrows():
                symbol = srow.get("symbol")
                stat_type = srow.get("stat_type")
                if symbol is None or stat_type not in STAT_TYPES:
                    continue
                field_name, value_col = STAT_TYPES[stat_type]
                raw_val = srow.get(value_col)
                if raw_val is None:
                    continue
                if value_col == "quantity":
                    if raw_val >= INT32_MAX:
                        continue
                    value = int(raw_val)
                    if value <= 0:
                        continue
                else:
                    value = float(raw_val)
                    if field_name != "change" and value <= 0:
                        continue
                ts_ev = srow.get("ts_event")
                ev_date = extract_date(ts_ev)
                if not ev_date:
                    continue
                key = (symbol, ev_date)
                if key not in stats_lookup:
                    stats_lookup[key] = {}
                stats_lookup[key][field_name] = value
    except Exception:
        pass  # Stats optional; leave stat columns NULL if API fails

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
        # Symbol for stats join: definition raw_symbol or OHLCV symbol (real data only)
        symbol = def_info.get("symbol") or row.get("symbol")
        symbol = str(symbol).strip() if symbol is not None else None
        stats = stats_lookup.get((symbol, event_date), {}) if symbol else {}
        # Only values present in API response; no placeholders
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
                def_info["expiration"],
                def_info["strike"],
                def_info["option_type"],
            ),
        }
        records.append(record)
    return records


def upsert_options(conn, rows: list[dict]) -> int:
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


@ray.remote
def run_one_underlying(args: tuple) -> tuple:
    """Worker: backfill one underlying (all batches). Runs on Ray cluster."""
    import databento as db
    from psycopg2.extras import execute_batch
    import hashlib
    import time
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.fusion.db.ray_pool import get_connection, release_connection

    config, batches, api_key, database_url, progress_file = args
    underlying = config["underlying"]
    client = db.Historical(key=api_key)
    conn = get_connection(database_url)  # Uses pool instead of new connection
    total = 0
    n_batches = len(batches)

    # Define helper functions inline for Ray workers
    def compute_row_hash(
        underlying: str, event_date, expiration, strike: float, option_type: str
    ) -> str:
        key = f"{underlying}|{event_date}|{expiration}|{strike}|{option_type}"
        return hashlib.sha256(key.encode()).hexdigest()

    def fetch_ohlcv_with_definitions(
        client, symbol: str, underlying: str, start_date, end_date
    ) -> list[dict]:
        """Fetch OHLCV data with definitions for one symbol/date range."""
        rows = []

        try:
            # Fetch definitions
            defs = client.timeseries.get_range(
                dataset="GLBX.MDP3",
                schema="definition",
                symbols=[symbol],
                stype_in="parent",
                start=start_date.isoformat(),
                end=(end_date + timedelta(days=1)).isoformat(),
            )
        except Exception:
            return rows

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
                elif isinstance(expiration, int) and expiration > 100000:
                    from datetime import datetime

                    expiration = datetime.fromtimestamp(expiration / 1e9).date()

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

        if not def_map:
            return rows

        # Fetch OHLCV
        try:
            ohlcv = client.timeseries.get_range(
                dataset="GLBX.MDP3",
                schema="ohlcv-1d",
                symbols=[symbol],
                stype_in="parent",
                start=start_date.isoformat(),
                end=(end_date + timedelta(days=1)).isoformat(),
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
                # Ensure event_date is a date object
                if isinstance(event_date, int):
                    from datetime import datetime

                    event_date = datetime.fromtimestamp(event_date / 1e9).date()

                row_dict = {
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
                rows.append(row_dict)
        except Exception:
            pass

        return rows

    def upsert_options(conn, rows: list[dict]) -> int:
        """Upsert option records into mkt.options_1d."""
        if not rows:
            return 0

        query = """
        INSERT INTO mkt.options_1d
            (underlying, event_date, expiration, strike, option_type,
             open, high, low, close, volume,
             source, row_hash, ingested_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'databento', %s, NOW())
        ON CONFLICT (underlying, event_date, expiration, strike, option_type) DO UPDATE SET
            open = COALESCE(EXCLUDED.open, mkt.options_1d.open),
            high = COALESCE(EXCLUDED.high, mkt.options_1d.high),
            low = COALESCE(EXCLUDED.low, mkt.options_1d.low),
            close = COALESCE(EXCLUDED.close, mkt.options_1d.close),
            volume = COALESCE(EXCLUDED.volume, mkt.options_1d.volume),
            source = 'databento',
            ingested_at = NOW()
        """

        cur = conn.cursor()
        values = []
        for r in rows:
            row_hash = compute_row_hash(
                r["underlying"],
                r["event_date"],
                r["expiration"],
                r["strike"],
                r["option_type"],
            )
            values.append(
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
                    row_hash,
                )
            )

        execute_batch(cur, query, values, page_size=1000)
        conn.commit()
        cur.close()
        return len(rows)

    try:
        for i, (batch_start, batch_end) in enumerate(batches):
            rows = fetch_ohlcv_with_definitions(
                client, config["parent"], underlying, batch_start, batch_end
            )
            if rows:
                total += upsert_options(conn, rows)
            if progress_file:
                try:
                    with open(progress_file, "a") as f:
                        f.write(
                            f"[{underlying}] batch {i + 1}/{n_batches} +{len(rows)} rows\n"
                        )
                except Exception:
                    pass
            time.sleep(0.25)
        return (underlying, total, None)
    except Exception as e:
        return (underlying, total, str(e))
    finally:
        release_connection(conn)  # Returns to pool instead of closing


def build_batches(start_date: date, end_date: date, batch_months: int) -> list[tuple]:
    batches = []
    current = start_date
    while current <= end_date:
        month = current.month + batch_months
        year = current.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        batch_end = date(year, month, 1) - timedelta(days=1)
        batch_end = min(batch_end, end_date)
        batches.append((current, batch_end))
        current = batch_end + timedelta(days=1)
    return batches


def main():
    parser = argparse.ArgumentParser(description="Backfill options - parallel")
    parser.add_argument("--underlying", type=str, help="Single underlying")
    parser.add_argument("--start", type=str, required=True)
    parser.add_argument("--end", type=str)
    parser.add_argument("--all", action="store_true")
    parser.add_argument(
        "--batch-months", type=int, default=3, help="Months per API call (default 3)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Parallel workers on this machine (default 8)",
    )
    parser.add_argument(
        "--worker-index",
        type=int,
        default=0,
        help="This machine index (0..worker-total-1)",
    )
    parser.add_argument(
        "--worker-total", type=int, default=1, help="Total machines (default 1)"
    )
    parser.add_argument(
        "--progress-file",
        type=str,
        default="",
        help="Append progress lines here (e.g. /tmp/options_progress.log)",
    )
    args = parser.parse_args()
    progress_file = args.progress_file or None

    start_date = date.fromisoformat(args.start)
    end_date = (
        date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)
    )

    configs = OPTIONS_CONFIG
    if args.underlying and not args.all:
        configs = [
            c for c in OPTIONS_CONFIG if c["underlying"] == args.underlying.upper()
        ]
        if not configs:
            print(f"ERROR: Unknown underlying {args.underlying}")
            sys.exit(1)

    # Split across machines
    configs = [
        c for i, c in enumerate(configs) if i % args.worker_total == args.worker_index
    ]
    if not configs:
        print("No underlyings assigned to this worker. Exiting.")
        return

    batches = build_batches(start_date, end_date, args.batch_months)
    task_args = [
        (config, batches, DATABENTO_API_KEY, DATABASE_URL, progress_file)
        for config in configs
    ]

    print("=" * 70)
    print("DATABENTO OPTIONS BACKFILL - PARALLEL")
    print("=" * 70)
    print(f"Date range: {start_date} to {end_date}")
    print(
        f"Underlyings (this machine): {len(configs)} {[c['underlying'] for c in configs]}"
    )
    print(
        f"Workers: {args.workers}  |  Batches per underlying: {len(batches)}  |  Batch size: {args.batch_months} month(s)"
    )
    if args.worker_total > 1:
        print(f"Machine: worker {args.worker_index + 1} of {args.worker_total}")
    print("=" * 70)

    # Connect to Ray cluster
    ray.init(address="auto", ignore_reinit_error=True)
    cluster_cpus = ray.cluster_resources().get("CPU", 0)
    print(f"Ray cluster: {cluster_cpus:.0f} CPUs available")
    print("=" * 70)

    t0 = time.perf_counter()
    results = []

    # Submit all tasks to Ray cluster
    ray_futures = {run_one_underlying.remote(a): a[0]["underlying"] for a in task_args}
    pending = list(ray_futures.keys())

    while pending:
        done, pending = ray.wait(pending, num_returns=1)
        future = done[0]
        underlying = ray_futures[future]
        try:
            u, total, err = ray.get(future)
            results.append((u, total, err))
            if err:
                print(f"  [{u}] ERROR: {err}")
            else:
                print(f"  [{u}] done  {total:,} rows")
        except Exception as e:
            results.append((underlying, 0, str(e)))
            print(f"  [{underlying}] EXCEPTION: {e}")

    elapsed = time.perf_counter() - t0
    total_rows = sum(r[1] for r in results)
    print("=" * 70)
    print(
        f"COMPLETE: {total_rows:,} rows in {elapsed:.1f}s ({total_rows / elapsed:.0f} rows/s)"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()
