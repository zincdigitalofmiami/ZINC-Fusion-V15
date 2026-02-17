#!/usr/bin/env python3
"""
Verify FRED data depth across all econ.* tables.

Reports MIN(event_date), MAX(event_date), row count, and distinct series
for each domain table. Flags tables with <5 years of history.

Usage:
    .venv/bin/python scripts/verify_fred_depth.py
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    env_local = Path(__file__).parent.parent / "frontend" / ".env.local"
    if env_local.exists():
        for line in env_local.read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                DATABASE_URL = line.split("=", 1)[1].strip().strip('"')
                break

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found")
    sys.exit(1)

ECON_TABLES = [
    "econ.rates_1d",
    "econ.inflation_1d",
    "econ.labor_1d",
    "econ.activity_1d",
    "econ.money_1d",
    "econ.vol_indices_1d",
    "econ.commodities_1d",
]

NEWS_TABLES = [
    "alt.econ_news_event",
    "alt.policy_news_event",
    "alt.profarmer_news_event",
    "alt.executive_actions_event",
    "alt.legislation_1d",
]

FIVE_YEARS_AGO = datetime.now().date() - timedelta(days=5 * 365)


def check_table(cur, table: str, date_col: str = "event_date") -> dict:
    """Check data depth for a single table."""
    schema, tbl = table.split(".")
    try:
        cur.execute(
            f"""
            SELECT
                MIN({date_col}) AS min_date,
                MAX({date_col}) AS max_date,
                COUNT(*) AS row_count,
                COUNT(DISTINCT series_id) AS distinct_series
            FROM {schema}.{tbl}
            """
        )
        row = cur.fetchone()
        return {
            "table": table,
            "min_date": row[0],
            "max_date": row[1],
            "rows": row[2],
            "series": row[3],
            "has_5yr": row[0] is not None and row[0] <= FIVE_YEARS_AGO,
        }
    except psycopg2.errors.UndefinedColumn:
        # News tables don't have series_id
        cur.connection.rollback()
        cur.execute(
            f"""
            SELECT
                MIN({date_col}) AS min_date,
                MAX({date_col}) AS max_date,
                COUNT(*) AS row_count
            FROM {schema}.{tbl}
            """
        )
        row = cur.fetchone()
        return {
            "table": table,
            "min_date": row[0],
            "max_date": row[1],
            "rows": row[2],
            "series": "N/A",
            "has_5yr": row[0] is not None and row[0].date() <= FIVE_YEARS_AGO
            if hasattr(row[0], "date")
            else (row[0] is not None and row[0] <= FIVE_YEARS_AGO),
        }
    except psycopg2.errors.UndefinedTable:
        cur.connection.rollback()
        return {
            "table": table,
            "min_date": None,
            "max_date": None,
            "rows": 0,
            "series": 0,
            "has_5yr": False,
        }


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    print("=" * 80)
    print("ZINC-FUSION FRED & NEWS DATA DEPTH REPORT")
    print(f"5-year threshold: {FIVE_YEARS_AGO}")
    print("=" * 80)

    # FRED/Econ tables
    print("\n--- FRED / ECON TABLES ---\n")
    print(
        f"{'Table':<28} {'Min Date':<14} {'Max Date':<14} {'Rows':>10} {'Series':>8} {'5yr?':>6}"
    )
    print("-" * 80)

    econ_results = []
    for table in ECON_TABLES:
        result = check_table(cur, table)
        econ_results.append(result)
        min_d = str(result["min_date"] or "EMPTY")
        max_d = str(result["max_date"] or "EMPTY")
        flag = "YES" if result["has_5yr"] else "NO"
        print(
            f"{result['table']:<28} {min_d:<14} {max_d:<14} {result['rows']:>10,} {str(result['series']):>8} {flag:>6}"
        )

    # News tables
    print("\n--- NEWS / ARTICLES TABLES ---\n")
    print(f"{'Table':<34} {'Min Date':<14} {'Max Date':<14} {'Rows':>10} {'5yr?':>6}")
    print("-" * 80)

    news_results = []
    for table in NEWS_TABLES:
        result = check_table(cur, table)
        news_results.append(result)
        min_d = str(result["min_date"] or "EMPTY")[:13]
        max_d = str(result["max_date"] or "EMPTY")[:13]
        flag = "YES" if result["has_5yr"] else "NO"
        print(
            f"{result['table']:<34} {min_d:<14} {max_d:<14} {result['rows']:>10,} {flag:>6}"
        )

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    econ_with_5yr = sum(1 for r in econ_results if r["has_5yr"])
    news_with_5yr = sum(1 for r in news_results if r["has_5yr"])
    total_econ_rows = sum(r["rows"] for r in econ_results)
    total_news_rows = sum(r["rows"] for r in news_results)

    print(f"  FRED tables with 5yr+ history: {econ_with_5yr}/{len(ECON_TABLES)}")
    print(f"  News tables with 5yr+ history: {news_with_5yr}/{len(NEWS_TABLES)}")
    print(f"  Total FRED rows: {total_econ_rows:,}")
    print(f"  Total news rows: {total_news_rows:,}")

    # Recommendations
    print("\n--- RECOMMENDED ACTIONS ---\n")

    shallow_econ = [r for r in econ_results if not r["has_5yr"] and r["rows"] > 0]
    empty_econ = [r for r in econ_results if r["rows"] == 0]
    shallow_news = [r for r in news_results if not r["has_5yr"]]

    if empty_econ:
        print("  CRITICAL: Empty FRED tables (run full backfill):")
        for r in empty_econ:
            print(f"    - {r['table']}")
        print("    FIX: .venv/bin/python scripts/refresh_fred_api.py")

    if shallow_econ:
        print("  WARNING: FRED tables with <5yr history (run full backfill):")
        for r in shallow_econ:
            print(f"    - {r['table']} (oldest: {r['min_date']})")
        print("    FIX: .venv/bin/python scripts/refresh_fred_api.py")

    if not empty_econ and not shallow_econ:
        print("  FRED data: All tables have 5+ years of history.")

    if shallow_news:
        print("\n  WARNING: News tables missing 5yr history:")
        for r in shallow_news:
            if r["rows"] > 0:
                print(
                    f"    - {r['table']} (oldest: {str(r['min_date'])[:10]}, {r['rows']:,} rows)"
                )
            else:
                print(f"    - {r['table']} (EMPTY)")
        print("    FIX: Run backfill scripts:")
        print("      .venv/bin/python scripts/backfill_federal_register.py")
        print("      .venv/bin/python scripts/backfill_fomc_history.py")
        print("      .venv/bin/python scripts/backfill_gdelt_sentiment.py")

    print()
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
