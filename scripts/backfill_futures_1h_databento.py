#!/usr/bin/env python3
"""
Backfill mkt.futures_1h from Databento (ohlcv-1h).

Defaults to ZL-important keepers + MES. Inserts missing bars (no overwrite)
unless --mode replace is used.

Usage:
  .venv/bin/python scripts/backfill_futures_1h_databento.py --days 180
  .venv/bin/python scripts/backfill_futures_1h_databento.py --symbols ZL,ZS,ZM --start 2025-01-01 --end 2025-12-31
  .venv/bin/python scripts/backfill_futures_1h_databento.py --symbols 6J,6M --days 365 --mode replace
"""

import argparse
import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import psycopg2
from psycopg2.extras import execute_batch

try:
    import databento as db
except ImportError:
    print("ERROR: databento not installed. Run: pip install databento")
    sys.exit(1)

DATASET = "GLBX.MDP3"
SCHEMA = "ohlcv-1h"

DEFAULT_KEEPERS = [
    "ZL", "ZS", "ZM", "ZC", "ZW",
    "6B", "6J", "6L", "6M",
    "MES", "ES",
]

SYMBOL_MAP: Dict[str, str] = {
    # Soy complex (OI-ranked)
    "ZL": "ZL.n.0",
    "ZS": "ZS.n.0",
    "ZM": "ZM.n.0",
    # Grains
    "ZC": "ZC.c.0",
    "ZW": "ZW.c.0",
    # Energy
    "CL": "CL.c.0",
    "HO": "HO.c.0",
    "RB": "RB.c.0",
    "NG": "NG.c.0",
    "QM": "QM.c.0",
    # Metals
    "HG": "HG.c.0",
    # Equity indices
    "ES": "ES.c.0",
    "NQ": "NQ.c.0",
    "YM": "YM.c.0",
    "MES": "MES.c.0",
    # Rates
    "ZN": "ZN.c.0",
    # FX futures
    "6A": "6A.c.0",
    "6B": "6B.c.0",
    "6C": "6C.c.0",
    "6J": "6J.c.0",
    "6L": "6L.c.0",
    "6M": "6M.c.0",
    "6S": "6S.c.0",
}


def load_env() -> None:
    p = Path(".env")
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if (not line) or line.startswith("#") or ("=" not in line):
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if v and v[0] in ('"', "'") and v[-1] == v[0]:
            v = v[1:-1]
        if k and (k not in os.environ):
            os.environ[k] = v


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill mkt.futures_1h from Databento")
    parser.add_argument("--symbols", type=str, default=None,
                        help="Comma-separated symbols (default: ZL-important keepers + MES)")
    parser.add_argument("--start", type=str, default=None, help="Start datetime (YYYY-MM-DD or ISO)")
    parser.add_argument("--end", type=str, default=None, help="End datetime (YYYY-MM-DD or ISO)")
    parser.add_argument("--days", type=int, default=180, help="Days back from end if --start not provided")
    parser.add_argument("--chunk-days", type=int, default=30, help="Fetch window size in days")
    parser.add_argument("--mode", choices=["insert", "replace"], default="insert",
                        help="insert=missing only, replace=overwrite existing bars")
    parser.add_argument("--full-history", action="store_true",
                        help="Use earliest event_time in DB per symbol as start")
    parser.add_argument("--purge-non-databento", action="store_true",
                        help="After load, delete rows for symbol where source != 'databento'")
    parser.add_argument("--dry-run", action="store_true", help="Fetch + count rows, no DB writes")
    return parser.parse_args()


def ensure_symbols(symbols: Iterable[str]) -> List[str]:
    out = []
    for sym in symbols:
        sym = sym.strip().upper()
        if not sym:
            continue
        if sym not in SYMBOL_MAP:
            raise SystemExit(f"Unknown symbol '{sym}' (no Databento mapping).")
        out.append(sym)
    if not out:
        raise SystemExit("No symbols provided.")
    return out


def parse_dt(value: str, end_default: bool = False) -> datetime:
    if value is None:
        raise ValueError("datetime required")
    if len(value) == 10:
        dt = datetime.fromisoformat(value)
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    # For end dates supplied as date, use end of day
    if len(value) == 10 and end_default:
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=0)
    return dt


def row_hash(symbol: str, event_time: datetime, open_p, high_p, low_p, close_p, volume) -> str:
    key = f"{symbol}|{event_time.isoformat()}|{open_p}|{high_p}|{low_p}|{close_p}|{volume}"
    return hashlib.sha256(key.encode()).hexdigest()


def get_db_conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not set")
    return psycopg2.connect(url)


def fetch_bars(client: db.Historical, continuous: str, start: datetime, end: datetime):
    data = client.timeseries.get_range(
        dataset=DATASET,
        schema=SCHEMA,
        symbols=[continuous],
        stype_in="continuous",
        start=start.isoformat(),
        end=end.isoformat(),
    )
    df = data.to_df()
    if df.empty:
        return []
    df = df.reset_index()
    rows = []
    for _, r in df.iterrows():
        ts = r.get("ts_event")
        if ts is None:
            continue
        try:
            if hasattr(ts, "to_pydatetime"):
                ts = ts.to_pydatetime()
        except Exception:
            pass
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
        else:
            # Fallback: attempt ISO parse
            ts = datetime.fromisoformat(str(ts)).replace(tzinfo=timezone.utc)
        ts = ts.replace(minute=0, second=0, microsecond=0)
        rows.append(
            {
                "event_time": ts.replace(tzinfo=None),
                "open": float(r.get("open")) if r.get("open") is not None else None,
                "high": float(r.get("high")) if r.get("high") is not None else None,
                "low": float(r.get("low")) if r.get("low") is not None else None,
                "close": float(r.get("close")) if r.get("close") is not None else None,
                "volume": int(r.get("volume")) if r.get("volume") is not None else None,
            }
        )
    return rows


def insert_rows(conn, rows: List[dict], mode: str) -> int:
    if not rows:
        return 0
    if mode == "insert":
        sql = """
        INSERT INTO mkt.futures_1h
          (symbol, event_time, open, high, low, close, volume, source, ingested_at, knowledge_time, row_hash)
        VALUES
          (%(symbol)s, %(event_time)s, %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s,
           %(source)s, NOW(), %(knowledge_time)s, %(row_hash)s)
        ON CONFLICT (symbol, event_time) DO NOTHING
        """
    else:
        sql = """
        INSERT INTO mkt.futures_1h
          (symbol, event_time, open, high, low, close, volume, source, ingested_at, knowledge_time, row_hash)
        VALUES
          (%(symbol)s, %(event_time)s, %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s,
           %(source)s, NOW(), %(knowledge_time)s, %(row_hash)s)
        ON CONFLICT (symbol, event_time) DO UPDATE SET
          open = EXCLUDED.open,
          high = EXCLUDED.high,
          low = EXCLUDED.low,
          close = EXCLUDED.close,
          volume = EXCLUDED.volume,
          source = EXCLUDED.source,
          ingested_at = NOW(),
          knowledge_time = EXCLUDED.knowledge_time,
          row_hash = EXCLUDED.row_hash
        """
    cur = conn.cursor()
    execute_batch(cur, sql, rows, page_size=1000)
    conn.commit()
    count = cur.rowcount
    cur.close()
    return count


def get_min_event_time(conn, symbol: str):
    cur = conn.cursor()
    cur.execute(
        "SELECT MIN(event_time) FROM mkt.futures_1h WHERE symbol = %s",
        (symbol,),
    )
    value = cur.fetchone()[0]
    cur.close()
    return value


def purge_non_databento(conn, symbol: str) -> int:
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM mkt.futures_1h WHERE symbol = %s AND (source IS NULL OR source <> 'databento')",
        (symbol,),
    )
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    return deleted


def main():
    args = parse_args()
    load_env()

    api_key = os.getenv("DATABENTO_API_KEY")
    if not api_key:
        raise SystemExit("DATABENTO_API_KEY not set")

    if args.symbols:
        symbols = ensure_symbols(args.symbols.split(","))
    else:
        symbols = ensure_symbols(DEFAULT_KEEPERS)

    if args.end:
        end_global = parse_dt(args.end, end_default=True)
    else:
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        end_global = now - timedelta(hours=1)

    if args.start and args.full_history:
        raise SystemExit("Use either --start or --full-history (not both)")

    client = db.Historical(key=api_key)
    conn = get_db_conn() if not args.dry_run else None
    if args.full_history and conn is None:
        raise SystemExit("--full-history requires DATABASE_URL")

    print(f"End time: {end_global.isoformat()} | mode={args.mode}")
    print(f"Symbols: {symbols}")

    total_inserted = 0
    for sym in symbols:
        continuous = SYMBOL_MAP[sym]
        print(f"\n=== {sym} ({continuous}) ===")

        if args.full_history:
            min_ts = get_min_event_time(conn, sym) if conn else None
            if min_ts is None:
                start = datetime(2000, 1, 1, tzinfo=timezone.utc)
            else:
                start = min_ts.replace(tzinfo=timezone.utc)
        elif args.start:
            start = parse_dt(args.start)
        else:
            start = end_global - timedelta(days=args.days)

        if start >= end_global:
            print("  Skipping: start >= end")
            continue

        print(f"  Window: {start.isoformat()} -> {end_global.isoformat()}")

        cursor = start
        while cursor < end_global:
            chunk_end = min(cursor + timedelta(days=args.chunk_days), end_global)
            print(f"  Fetching {cursor.isoformat()} -> {chunk_end.isoformat()}")
            try:
                bars = fetch_bars(client, continuous, cursor, chunk_end)
            except Exception as e:
                print(f"  ERROR fetching {sym}: {e}")
                cursor = chunk_end
                continue

            if not bars:
                print("  No bars returned")
                cursor = chunk_end
                continue

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            rows = []
            for bar in bars:
                rows.append(
                    {
                        "symbol": sym,
                        "event_time": bar["event_time"],
                        "open": bar["open"],
                        "high": bar["high"],
                        "low": bar["low"],
                        "close": bar["close"],
                        "volume": bar["volume"],
                        "source": "databento",
                        "knowledge_time": now,
                        "row_hash": row_hash(sym, bar["event_time"], bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]),
                    }
                )

            if args.dry_run:
                print(f"  Bars fetched: {len(rows)} (dry-run)")
            else:
                inserted = insert_rows(conn, rows, args.mode)
                total_inserted += inserted
                print(f"  Rows written: {inserted}")

            cursor = chunk_end

        if (not args.dry_run) and args.purge_non_databento:
            deleted = purge_non_databento(conn, sym)
            print(f"  Purged non-databento rows: {deleted}")

    if conn:
        conn.close()
    print(f"\nDone. Total rows written: {total_inserted}")


if __name__ == "__main__":
    main()
