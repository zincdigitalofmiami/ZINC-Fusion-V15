#!/usr/bin/env python3
"""
RIN data refresh: report supply.epa_rin_1d state and how to trigger ingestion.

EPA RIN = weekly volume-weighted avg, updated monthly. TTL 45d (one EPA cycle).
See Docs/RIN_DATA_CONTRACT.md. This script reports staleness; gate uses TTL=45.

Usage:
    python scripts/refresh_epa_rin.py           # Report only
    python scripts/refresh_epa_rin.py --strict  # Exit 1 if stale (for CI)

Ingestion: Inngest epaRinPricesDaily runs every 8 hours. New rows appear
only when EPA updates their Qlik app. To force a pull attempt:
    cd frontend && npx inngest-cli trigger epaRinPricesDaily
"""

import os
import sys
import argparse
from datetime import date

# Add src for DB connection
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(repo_root, "src"))

# Optional: load .env if present
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(repo_root, ".env"))
except ImportError:
    pass


def main():
    parser = argparse.ArgumentParser(
        description="RIN data refresh status and trigger instructions"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if RIN data is stale (max_age > TTL)",
    )
    parser.add_argument(
        "--ttl-days",
        type=int,
        default=45,
        help="TTL in days for EPA weekly-updated-monthly (default 45)",
    )
    args = parser.parse_args()

    if not os.getenv("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set")
        sys.exit(2)

    import psycopg2

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    try:
        cur = conn.cursor()

        # Current state by source
        cur.execute(
            """
            SELECT source, MAX(event_date)::date AS max_date, COUNT(*) AS rows
            FROM supply.epa_rin_1d
            GROUP BY source
            ORDER BY source
        """
        )
        rows = cur.fetchall()

        today = date.today()
        print("supply.epa_rin_1d")
        print("-" * 50)

        max_date_overall = None
        for source, max_date, count in rows:
            age = (today - max_date).days if max_date else 999
            max_date_overall = (
                max(max_date_overall or max_date, max_date)
                if max_date
                else max_date_overall
            )
            status = "OK" if age <= args.ttl_days else "STALE"
            print(
                f"  {source}: max_date={max_date}, rows={count}, age={age}d [{status}]"
            )

        # Primary source for gate is epa_qlik_public
        cur.execute(
            """
            SELECT MAX(event_date)::date FROM supply.epa_rin_1d WHERE source = 'epa_qlik_public'
        """
        )
        qlik_max = cur.fetchone()[0]
        age_days = (today - qlik_max).days if qlik_max else 999

        print()
        print(
            f"Gate check (source=epa_qlik_public): max_date={qlik_max}, max_age_days={age_days}, TTL={args.ttl_days}d (EPA weekly, updated monthly)"
        )
        if age_days <= args.ttl_days:
            print("Result: PASS (within one EPA cycle)")
        else:
            print("Result: FAIL (beyond one EPA cycle - refresh ingestion)")
            print()
            print("Refresh: ingestion runs every 8h (Inngest epaRinPricesDaily).")
            print("New data appears only when EPA updates their Qlik app.")
            print("To force a pull attempt:")
            print("  cd frontend && npx inngest-cli trigger epaRinPricesDaily")
            print()
            print(
                "See: https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information"
            )

        cur.close()

        if args.strict and age_days > args.ttl_days:
            sys.exit(1)
        sys.exit(0)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
