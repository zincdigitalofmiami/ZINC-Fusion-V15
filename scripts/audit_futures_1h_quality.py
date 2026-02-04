#!/usr/bin/env python3
"""Audit mkt.futures_1h session coverage and quality for key symbols."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

import psycopg2

KEEPERS_DEFAULT = [
    "ZL", "ZS", "ZM", "ZC", "ZW",
    "6B", "6J", "6L", "6M",
    "MES", "ES",
]


def load_env() -> None:
    p = Path(".env")
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if (not line) or line.startswith("#") or ("=" not in line):
                continue
            k, v = line.split("=", 1)
            k = k.strip(); v = v.strip()
            if v and v[0] in ('"', "'") and v[-1] == v[0]:
                v = v[1:-1]
            if k and (k not in os.environ):
                os.environ[k] = v


def get_conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not set")
    return psycopg2.connect(url)


def load_session_map() -> Dict[str, List[int]]:
    path = Path("config/futures_1h_sessions.json")
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    out: Dict[str, List[int]] = {}
    for sym, hours in data.items():
        if not isinstance(hours, list):
            continue
        clean = sorted({int(h) for h in hours})
        out[str(sym).upper()] = clean
    return out


def expected_hours(conn, symbols: List[str]) -> Dict[str, List[int]]:
    cur = conn.cursor()
    cur.execute(
        """
        WITH per_day AS (
          SELECT symbol, event_time::date d, COUNT(*) bars
          FROM mkt.futures_1h
          WHERE symbol = ANY(%s)
          GROUP BY symbol, d
        ), med AS (
          SELECT symbol,
                 GREATEST(1, ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY bars))::int) AS median_bars
          FROM per_day
          GROUP BY symbol
        ), hour_counts AS (
          SELECT symbol, EXTRACT(hour FROM event_time)::int AS hour,
                 COUNT(DISTINCT event_time::date) AS days_with_bar
          FROM mkt.futures_1h
          WHERE symbol = ANY(%s)
          GROUP BY symbol, hour
        ), ranked AS (
          SELECT h.symbol, h.hour, h.days_with_bar, m.median_bars,
                 ROW_NUMBER() OVER (PARTITION BY h.symbol ORDER BY h.days_with_bar DESC, h.hour) AS rn
          FROM hour_counts h
          JOIN med m ON m.symbol = h.symbol
        )
        SELECT symbol, hour
        FROM ranked
        WHERE rn <= median_bars
        ORDER BY symbol, hour
        """,
        (symbols, symbols),
    )
    rows = cur.fetchall()
    cur.close()
    out: Dict[str, List[int]] = {s: [] for s in symbols}
    for sym, hour in rows:
        out[sym].append(int(hour))
    return out


def session_missing_stats(conn, symbols: List[str], hours: Dict[str, List[int]], days_back: int = 180):
    cur = conn.cursor()
    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).date()
    stats = {}
    for sym in symbols:
        exp = hours.get(sym, [])
        if not exp:
            stats[sym] = {"expected_hours": 0, "days": 0, "days_with_missing": 0, "avg_missing": None, "max_missing": None}
            continue
        cur.execute(
            """
            SELECT event_time::date d,
                   COUNT(*) FILTER (WHERE EXTRACT(hour FROM event_time) = ANY(%s)) AS bars_expected
            FROM mkt.futures_1h
            WHERE symbol = %s AND event_time::date >= %s
            GROUP BY d
            """,
            (exp, sym, since),
        )
        rows = cur.fetchall()
        missing = [len(exp) - r[1] for r in rows]
        days = len(rows)
        days_with_missing = sum(1 for m in missing if m > 0)
        avg_missing = (sum(missing) / days) if days else None
        max_missing = max(missing) if days else None
        stats[sym] = {
            "expected_hours": len(exp),
            "days": days,
            "days_with_missing": days_with_missing,
            "avg_missing": round(avg_missing, 2) if avg_missing is not None else None,
            "max_missing": max_missing,
        }
    cur.close()
    return stats


def quality_stats(conn, symbols: List[str], days_back: int = 180):
    cur = conn.cursor()
    since = (datetime.now(timezone.utc) - timedelta(days=days_back))
    out = {}
    for sym in symbols:
        cur.execute(
            """
            WITH lagged AS (
              SELECT event_time, open, high, low, close,
                     LAG(close) OVER (PARTITION BY symbol ORDER BY event_time) AS prev_close
              FROM mkt.futures_1h
              WHERE symbol = %s AND event_time >= %s
            )
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN open=high AND high=low AND low=close THEN 1 ELSE 0 END) AS flat,
                   SUM(CASE WHEN close = prev_close THEN 1 ELSE 0 END) AS stale
            FROM lagged
            """,
            (sym, since),
        )
        total, flat, stale = cur.fetchone()
        flat_rate = (flat / total) if total else None
        stale_rate = (stale / total) if total else None
        out[sym] = {
            "total": total,
            "flat_rate": round(flat_rate, 4) if flat_rate is not None else None,
            "stale_rate": round(stale_rate, 4) if stale_rate is not None else None,
        }
    cur.close()
    return out


def main():
    days_back = int(os.getenv("FUTURES_1H_QA_DAYS", "180"))
    symbols = KEEPERS_DEFAULT
    load_env()
    conn = get_conn()
    session_map = load_session_map()
    hours = dict(session_map)
    dynamic_symbols = [s for s in symbols if s not in session_map]
    if dynamic_symbols:
        hours.update(expected_hours(conn, dynamic_symbols))
    missing = session_missing_stats(conn, symbols, hours, days_back=days_back)
    quality = quality_stats(conn, symbols, days_back=days_back)
    conn.close()

    print("SESSION HOURS (expected):")
    for sym in symbols:
        print(f"  {sym}: {hours.get(sym)}")

    print("\nMISSING HOURS (last %d days):" % days_back)
    for sym in symbols:
        print(f"  {sym}: {missing[sym]}")

    print("\nQUALITY (last %d days):" % days_back)
    for sym in symbols:
        print(f"  {sym}: {quality[sym]}")


if __name__ == "__main__":
    main()
