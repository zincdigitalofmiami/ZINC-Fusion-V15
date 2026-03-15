#!/usr/bin/env python3
"""
One-time migration: Fix WASDE 'Crushings' rows stored as metric='consumption'.

Background:
  The Inngest WASDE ingestion pipeline mapped "Crushings" → "consumption" instead
  of "crush". This means soybean crush volume was mixed with total domestic use.

  For Soybeans, WASDE reports contain BOTH:
    - "Domestic Total" (total domestic use = crushings + exports + seed + residual)
    - "Crushings" (soybean volume processed into oil + meal)

  Both were stored as metric='consumption', creating duplicate rows per report date.
  The correct mapping is:
    - "Domestic Total" → metric='consumption'
    - "Crushings"      → metric='crush'

Strategy:
  For each (event_date, commodity='Soybeans', country) with 2+ consumption rows,
  the SMALLER value is "Crushings" (it's a subset of Domestic Total).
  Update that row to metric='crush'.

  For dates with only 1 consumption row, we can't distinguish — leave as-is.
  Future ingestion (with the fixed mapMetric) will create proper 'crush' rows.

Usage:
  python scripts/migrate_wasde_crush_metric.py          # dry-run (default)
  python scripts/migrate_wasde_crush_metric.py --apply  # apply changes
"""

import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()
load_dotenv("frontend/.env.local")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: No DATABASE_URL found")
    sys.exit(1)
if DATABASE_URL.startswith("prisma+postgres://"):
    print("ERROR: DATABASE_URL must be a direct postgres:// or postgresql:// URL")
    sys.exit(1)


def main():
    dry_run = "--apply" not in sys.argv

    if dry_run:
        print("DRY RUN — pass --apply to execute changes\n")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Step 1: Find duplicate consumption rows for Soybeans
    cur.execute("""
        SELECT event_date, commodity, country, COUNT(*) as n,
               MIN(value) as min_val, MAX(value) as max_val
        FROM supply.usda_wasde_1m
        WHERE commodity = 'Soybeans'
          AND metric = 'consumption'
        GROUP BY event_date, commodity, country
        HAVING COUNT(*) > 1
        ORDER BY event_date DESC
    """)
    duplicates = cur.fetchall()
    print(
        f"Found {len(duplicates)} (date, commodity, country) groups with duplicate consumption rows"
    )

    if duplicates:
        for row in duplicates[:5]:
            print(
                f"  {row[0]} | {row[2]:15s} | {row[3]} rows | min={row[4]:.1f} max={row[5]:.1f}"
            )
        if len(duplicates) > 5:
            print(f"  ... and {len(duplicates) - 5} more")

    # Step 2: Update the smaller-value row to metric='crush' for each duplicate group
    # The smaller value is "Crushings" (subset of Domestic Total)
    update_sql = """
        WITH ranked AS (
            SELECT id, event_date, commodity, country, metric, value,
                   ROW_NUMBER() OVER (
                       PARTITION BY event_date, commodity, country
                       ORDER BY value ASC
                   ) as rn,
                   COUNT(*) OVER (
                       PARTITION BY event_date, commodity, country
                   ) as group_count
            FROM supply.usda_wasde_1m
            WHERE commodity = 'Soybeans'
              AND metric = 'consumption'
        )
        UPDATE supply.usda_wasde_1m
        SET metric = 'crush'
        WHERE id IN (
            SELECT id FROM ranked
            WHERE rn = 1 AND group_count > 1
        )
    """

    if dry_run:
        # Count affected rows without changing
        cur.execute("""
            WITH ranked AS (
                SELECT id, event_date, commodity, country, metric, value,
                       ROW_NUMBER() OVER (
                           PARTITION BY event_date, commodity, country
                           ORDER BY value ASC
                       ) as rn,
                       COUNT(*) OVER (
                           PARTITION BY event_date, commodity, country
                       ) as group_count
                FROM supply.usda_wasde_1m
                WHERE commodity = 'Soybeans'
                  AND metric = 'consumption'
            )
            SELECT COUNT(*) FROM ranked WHERE rn = 1 AND group_count > 1
        """)
        would_update = cur.fetchone()[0]
        print(f"\nWould update {would_update} rows from consumption → crush")
    else:
        cur.execute(update_sql)
        updated = cur.rowcount
        print(f"\nUpdated {updated} rows from consumption → crush")

    # Step 3: Check for single consumption rows (Soybeans only, no duplicate)
    cur.execute("""
        SELECT event_date, country, value
        FROM supply.usda_wasde_1m
        WHERE commodity = 'Soybeans'
          AND metric = 'consumption'
          AND (event_date, commodity, country) NOT IN (
              SELECT event_date, commodity, country
              FROM supply.usda_wasde_1m
              WHERE commodity = 'Soybeans' AND metric = 'crush'
          )
        ORDER BY event_date DESC
        LIMIT 10
    """)
    singles = cur.fetchall()
    if singles:
        print(
            f"\nNote: {len(singles)}+ Soybeans dates have only 1 consumption row (ambiguous)."
        )
        print(
            "  These will be resolved when WASDE ingestion re-runs with the fixed mapper."
        )

    # Step 4: Final count check
    cur.execute("""
        SELECT metric, COUNT(*)
        FROM supply.usda_wasde_1m
        WHERE commodity = 'Soybeans'
        GROUP BY metric
        ORDER BY metric
    """)
    print("\nSoybeans metric distribution:")
    for metric, count in cur.fetchall():
        print(f"  {metric:20s}: {count:5d} rows")

    if not dry_run:
        conn.commit()
        print("\nChanges committed.")
    else:
        conn.rollback()
        print("\nNo changes made (dry run).")

    conn.close()


if __name__ == "__main__":
    main()
