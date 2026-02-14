#!/usr/bin/env python3
"""
Refresh ALL FRED series from the FRED API into econ.* tables.

Fetches full history for every series in FRED_SERIES_ROUTING and upserts
into the correct domain table. Uses the same schema contract as the
Inngest fred-daily.ts jobs (series_id, event_date, value, source,
ingested_at, knowledge_time, row_hash).

Usage:
    .venv/bin/python scripts/refresh_fred_api.py
    .venv/bin/python scripts/refresh_fred_api.py --table econ.activity_1d
    .venv/bin/python scripts/refresh_fred_api.py --series GDP INDPRO
"""

import argparse
import hashlib
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_batch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.fusion.db.fred_routing import FRED_SERIES_ROUTING, get_series_for_table

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# FRED API config
FRED_API_KEY = os.getenv("FRED_API_KEY")
if not FRED_API_KEY:
    # Fall back to frontend env
    env_local = Path(__file__).parent.parent / "frontend" / ".env.local"
    if env_local.exists():
        for line in env_local.read_text().splitlines():
            if line.startswith("FRED_API_KEY="):
                FRED_API_KEY = line.split("=", 1)[1].strip().strip('"')
                break

if not FRED_API_KEY:
    print("ERROR: FRED_API_KEY not found in environment or frontend/.env.local")
    sys.exit(1)

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in environment")
    sys.exit(1)


def fetch_fred_series(series_id: str, limit: int = 100000) -> list[dict]:
    """Fetch all observations for a FRED series."""
    import requests

    url = (
        f"{FRED_BASE_URL}?series_id={series_id}"
        f"&api_key={FRED_API_KEY}&file_type=json"
        f"&sort_order=asc&limit={limit}"
    )

    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "ZincFusion/1.0"})
        resp.raise_for_status()
        data = resp.json()

        observations = data.get("observations", [])
        results = []
        for obs in observations:
            date_str = obs.get("date")
            value_str = obs.get("value", ".")
            if value_str == "." or not date_str:
                continue
            try:
                value = float(value_str)
                results.append({"date": date_str, "value": value})
            except (ValueError, TypeError):
                continue
        return results
    except Exception as e:
        print(f"    ERROR fetching {series_id}: {e}")
        return []


def compute_row_hash(series_id: str, date: str, value: float) -> str:
    """Compute SHA256 row hash matching Inngest contract."""
    content = f"{series_id}|{date}|{value}"
    return hashlib.sha256(content.encode()).hexdigest()


def upsert_series(conn, table: str, series_id: str, observations: list[dict]) -> int:
    """Upsert observations into the target econ.* table."""
    if not observations:
        return 0

    schema, tbl = table.split(".")
    now = datetime.utcnow()

    sql = f"""
        INSERT INTO {schema}.{tbl} (series_id, event_date, value, source, ingested_at, knowledge_time, row_hash)
        VALUES (%(series_id)s, %(event_date)s, %(value)s, 'FRED', %(ingested_at)s, %(knowledge_time)s, %(row_hash)s)
        ON CONFLICT (series_id, event_date)
        DO UPDATE SET
            value = EXCLUDED.value,
            knowledge_time = EXCLUDED.knowledge_time,
            row_hash = EXCLUDED.row_hash
    """

    rows = [
        {
            "series_id": series_id,
            "event_date": obs["date"],
            "value": obs["value"],
            "ingested_at": now,
            "knowledge_time": now,
            "row_hash": compute_row_hash(series_id, obs["date"], obs["value"]),
        }
        for obs in observations
    ]

    with conn.cursor() as cur:
        execute_batch(cur, sql, rows, page_size=500)
    conn.commit()
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Refresh FRED data from API")
    parser.add_argument(
        "--table", help="Only refresh series for this table (e.g. econ.activity_1d)"
    )
    parser.add_argument(
        "--series", nargs="+", help="Only refresh these specific series"
    )
    parser.add_argument(
        "--delay", type=float, default=0.4, help="Delay between API calls (seconds)"
    )
    args = parser.parse_args()

    # Determine which series to fetch
    if args.series:
        series_list = [
            (s, FRED_SERIES_ROUTING.get(s, "econ.activity_1d")) for s in args.series
        ]
    elif args.table:
        series_ids = get_series_for_table(args.table)
        series_list = [(s, args.table) for s in series_ids]
    else:
        series_list = [(s, t) for s, t in FRED_SERIES_ROUTING.items()]

    print(f"FRED API Refresh: {len(series_list)} series to fetch")
    print(f"API delay: {args.delay}s between calls")
    print()

    conn = psycopg2.connect(DATABASE_URL)
    total_rows = 0
    errors = 0
    start = time.time()

    # Group by table for reporting
    by_table: dict[str, int] = {}

    for i, (series_id, table) in enumerate(series_list, 1):
        print(
            f"  [{i}/{len(series_list)}] {series_id} → {table} ... ", end="", flush=True
        )

        observations = fetch_fred_series(series_id)
        if not observations:
            print("NO DATA")
            errors += 1
            time.sleep(args.delay)
            continue

        try:
            rows = upsert_series(conn, table, series_id, observations)
            print(
                f"{rows:,} rows ({observations[0]['date']} to {observations[-1]['date']})"
            )
            total_rows += rows
            by_table[table] = by_table.get(table, 0) + rows
        except Exception as e:
            print(f"ERROR: {e}")
            conn.rollback()
            errors += 1

        time.sleep(args.delay)

    elapsed = time.time() - start
    conn.close()

    print()
    print("=" * 60)
    print(f"FRED Refresh Complete: {total_rows:,} total rows in {elapsed:.0f}s")
    print(f"Errors: {errors}")
    print()
    for table, count in sorted(by_table.items()):
        print(f"  {table}: {count:,} rows")
    print("=" * 60)


if __name__ == "__main__":
    main()
