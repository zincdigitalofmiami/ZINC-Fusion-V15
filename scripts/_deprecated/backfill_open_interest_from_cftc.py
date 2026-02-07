#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Backfill futures open_interest from CFTC COT

Problem:
- `mkt.futures_1d.open_interest` exists but is currently all NULL for ZL/ZS/ZM.
- Strict specialists require an `open_interest` column in the matrix window.

Available in-repo data:
- `pos.cftc_1w.open_interest` (weekly) is ingested via `cftc-weekly`.

Approach:
- Copy weekly CFTC open interest onto the matching futures symbols on the report date.
- This is schema-safe (no schema changes) and uses existing official data.

Note:
- This does NOT attempt to invent daily open interest. Matrix building can forward-fill as needed.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime

import psycopg2
from dotenv import load_dotenv


SYMBOLS = ["ZL", "ZS", "ZM"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill mkt.futures_1d.open_interest from pos.cftc_1w")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD), optional")
    args = parser.parse_args()

    load_dotenv("/Volumes/Satechi Hub/ZINC-FUSION-V15/.env")
    load_dotenv("/Volumes/Satechi Hub/ZINC-FUSION-V15/.env.vercel")
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL not set")

    start_clause = ""
    params = []
    if args.start:
        start_clause = "AND event_date >= %s::date"
        params.append(args.start)

    sql = f"""
      WITH cot AS (
        SELECT symbol, event_date::date AS event_date, open_interest
        FROM pos.cftc_1w
        WHERE symbol = ANY(%s)
          AND open_interest IS NOT NULL
          {start_clause}
      )
      UPDATE mkt.futures_1d f
      SET open_interest = cot.open_interest,
          source = COALESCE(f.source, 'yahoo')
      FROM cot
      WHERE f.symbol = cot.symbol
        AND f.event_date::date = cot.event_date
        AND (f.open_interest IS NULL OR f.open_interest = 0)
    """

    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            if args.dry_run:
                cur.execute(
                    f"""
                    SELECT COUNT(*)::int
                    FROM mkt.futures_1d f
                    JOIN pos.cftc_1w c
                      ON c.symbol = f.symbol AND c.event_date::date = f.event_date::date
                    WHERE f.symbol = ANY(%s)
                      AND c.open_interest IS NOT NULL
                      AND (f.open_interest IS NULL OR f.open_interest = 0)
                      {('AND c.event_date >= %s::date' if args.start else '')}
                    """,
                    [SYMBOLS] + params,
                )
                print("rows_to_update", cur.fetchone()[0])
                return 0

            cur.execute(sql, [SYMBOLS] + params)
            updated = cur.rowcount
        conn.commit()
        print("updated_rows", updated)
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

