#!/usr/bin/env python3
"""
Data Freshness Check - Read-only validation of data pipeline
Does NOT modify any data or schema
"""
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

import psycopg2


def main():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    # Check data freshness for key tables
    tables = [
        ("raw.market_futures_1d", "event_date"),
        ("raw.fred_observations_1d", "event_date"),
        ("raw.cftc_cot_1w", "event_date"),
        ("raw.news_articles_1d", "event_date"),
        ("raw.legislation_federal_register_1d", "event_date"),
        ("raw.fx_spot_1d", "event_date"),
        ("raw.epa_rin_prices_1d", "event_date"),
        ("analytics.zl_live", "updated_at"),
    ]

    print("=== DATA FRESHNESS CHECK ===")
    print(f"Run at: {datetime.now()}")
    print()

    for table, date_col in tables:
        try:
            cur.execute(f"SELECT MAX({date_col}), COUNT(*) FROM {table}")
            row = cur.fetchone()
            latest = row[0]
            count = row[1]
            if latest:
                if hasattr(latest, "date"):
                    age = (datetime.now().date() - latest.date()).days
                else:
                    age = (datetime.now().date() - latest).days
            else:
                age = 999

            status = "✅ FRESH" if age <= 1 else "⚠️ STALE" if age <= 7 else "❌ OLD"
            print(f"{table}:")
            print(f"  Latest: {latest}")
            print(f"  Age: {age} days | Rows: {count} | {status}")
            print()
        except Exception as e:
            print(f"{table}: ERROR - {e}")
            print()

    # Check ops.ingest_run for recent runs
    print("=== RECENT INNGEST RUNS ===")
    cur.execute(
        """
        SELECT job_name, status, started_at, rows_inserted, rows_skipped, error_message
        FROM ops.ingest_run
        ORDER BY started_at DESC
        LIMIT 15
    """
    )
    for row in cur.fetchall():
        job, status, started, inserted, skipped, error = row
        err_msg = error[:40] + "..." if error and len(error) > 40 else error
        print(f"{job}: {status} @ {started}")
        print(f"  inserted={inserted} skipped={skipped} error={err_msg}")

    conn.close()


if __name__ == "__main__":
    main()
