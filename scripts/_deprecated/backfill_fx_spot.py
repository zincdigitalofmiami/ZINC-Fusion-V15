#!/usr/bin/env python3
"""
Backfill mkt.fx_1d from FRED API.

Pulls FX spot rates for major currency pairs used in Core/Specialist models.
Matches schema used by fx-spot-daily.ts Inngest job.

Usage:
    python scripts/backfill_fx_spot.py
    python scripts/backfill_fx_spot.py --start 2020-01-01
    python scripts/backfill_fx_spot.py --dry-run
"""

import os
import sys
import argparse
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional

import requests
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

FRED_API_KEY = os.getenv("FRED_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
BASE_URL = "https://api.stlouisfed.org/fred"

# FX pairs to ingest (matches fx-spot-daily.ts)
FX_PAIRS = [
    {"pair": "AUDUSD", "series_id": "DEXUSAL"},
    {"pair": "EURUSD", "series_id": "DEXUSEU"},
    {"pair": "GBPUSD", "series_id": "DEXUSUK"},
    {"pair": "USDBRL", "series_id": "DEXBZUS"},
    {"pair": "USDCAD", "series_id": "DEXCAUS"},
    {"pair": "USDCNY", "series_id": "DEXCHUS"},
    {"pair": "USDJPY", "series_id": "DEXJPUS"},
    {"pair": "USDKRW", "series_id": "DEXKOUS"},
    {"pair": "USDMXN", "series_id": "DEXMXUS"},
    {"pair": "USDSGD", "series_id": "DEXSIUS"},
]


def compute_row_hash(pair: str, event_date: str, rate: float, series_id: str) -> str:
    """Compute SHA256 hash for deduplication."""
    data = f"{pair}|{event_date}|{rate}|{series_id}"
    return hashlib.sha256(data.encode()).hexdigest()


def get_observations(series_id: str, start_date: str) -> list:
    """Fetch observations from FRED API."""
    if not FRED_API_KEY:
        raise SystemExit("FRED_API_KEY not found in environment")

    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
        "sort_order": "asc",
        "limit": 100000,
    }

    response = requests.get(f"{BASE_URL}/series/observations", params=params)
    if response.status_code == 200:
        return response.json().get("observations", [])
    else:
        print(f"  Error {response.status_code}: {response.text[:100]}")
        return []


def get_max_date(conn, pair: str) -> Optional[str]:
    """Get the latest date for a pair in the database."""
    cur = conn.cursor()
    cur.execute(
        "SELECT MAX(event_date)::date::text FROM mkt.fx_1d WHERE pair = %s",
        (pair,)
    )
    result = cur.fetchone()
    return result[0] if result and result[0] else None


def create_ingest_run(conn, job_name: str) -> int:
    """Create an ingest run record."""
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO ops.ingest_run (job_name, status, started_at)
           VALUES (%s, 'running', NOW()) RETURNING id""",
        (job_name,)
    )
    conn.commit()
    return cur.fetchone()[0]


def update_ingest_run(conn, run_id: int, status: str, attempted: int,
                      inserted: int, skipped: int, quarantined: int,
                      error_message: Optional[str] = None):
    """Update ingest run with final stats."""
    cur = conn.cursor()
    cur.execute(
        """UPDATE ops.ingest_run
           SET status=%s, completed_at=NOW(),
               rows_attempted=%s, rows_inserted=%s,
               rows_skipped=%s, rows_quarantined=%s,
               error_message=%s
           WHERE id=%s""",
        (status, attempted, inserted, skipped, quarantined, error_message, run_id)
    )
    conn.commit()


def backfill_pair(conn, pair: str, series_id: str, start_date: str,
                  run_id: int, dry_run: bool = False) -> tuple:
    """Backfill a single FX pair."""
    # Get max date in DB to avoid duplicates
    max_date = get_max_date(conn, pair)
    if max_date:
        # Start from day after max date
        start = (datetime.strptime(max_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        start = start_date

    print(f"  {pair} ({series_id}): fetching from {start}...")
    observations = get_observations(series_id, start)

    if not observations:
        print(f"  {pair}: no new observations")
        return 0, 0, 0, 0

    attempted = 0
    inserted = 0
    skipped = 0
    quarantined = 0

    cur = conn.cursor()

    for obs in observations:
        event_date = obs.get("date")
        value = obs.get("value")

        if not event_date or value == "." or value == "":
            skipped += 1
            continue

        try:
            rate = float(value)
        except ValueError:
            quarantined += 1
            continue

        attempted += 1

        # Check if already exists
        cur.execute(
            "SELECT 1 FROM mkt.fx_1d WHERE event_date = %s::date AND pair = %s LIMIT 1",
            (event_date, pair)
        )
        if cur.fetchone():
            skipped += 1
            continue

        if dry_run:
            inserted += 1
            continue

        row_hash = compute_row_hash(pair, event_date, rate, series_id)

        cur.execute(
            """INSERT INTO mkt.fx_1d
               (pair, event_date, rate, source, row_hash)
               VALUES (%s, %s::date, %s, %s, %s)""",
            (
                pair,
                event_date,
                rate,
                "fred_api",
                row_hash,
            )
        )
        inserted += 1

    if not dry_run:
        conn.commit()

    print(f"  {pair}: attempted={attempted}, inserted={inserted}, skipped={skipped}")
    return attempted, inserted, skipped, quarantined


def main():
    parser = argparse.ArgumentParser(description="Backfill mkt.fx_1d from FRED")
    parser.add_argument("--start", default="2000-01-01", help="Start date (default: 2000-01-01)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without inserting")
    args = parser.parse_args()

    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL not found in environment")

    print("=" * 60)
    print("BACKFILL FX SPOT RATES")
    print("=" * 60)
    print(f"Start date: {args.start}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")
    print(f"Pairs: {len(FX_PAIRS)}")
    print()

    conn = psycopg2.connect(DATABASE_URL)

    try:
        run_id = create_ingest_run(conn, "backfill_fx_spot") if not args.dry_run else 0

        total_attempted = 0
        total_inserted = 0
        total_skipped = 0
        total_quarantined = 0

        for fx in FX_PAIRS:
            pair = fx["pair"]
            series_id = fx["series_id"]

            attempted, inserted, skipped, quarantined = backfill_pair(
                conn, pair, series_id, args.start, run_id, args.dry_run
            )

            total_attempted += attempted
            total_inserted += inserted
            total_skipped += skipped
            total_quarantined += quarantined

        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Total attempted: {total_attempted:,}")
        print(f"Total inserted:  {total_inserted:,}")
        print(f"Total skipped:   {total_skipped:,}")
        print(f"Total quarantined: {total_quarantined:,}")

        if not args.dry_run and run_id:
            update_ingest_run(
                conn, run_id, "success",
                total_attempted, total_inserted, total_skipped, total_quarantined
            )
            print(f"\nIngest run ID: {run_id}")

    except Exception as e:
        print(f"\nError: {e}")
        conn.rollback()  # Rollback failed transaction
        if not args.dry_run and run_id:
            try:
                update_ingest_run(conn, run_id, "failed", 0, 0, 0, 0, str(e))
            except Exception:
                pass  # Ignore update errors
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
