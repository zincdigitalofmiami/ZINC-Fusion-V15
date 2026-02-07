#!/usr/bin/env python3
"""Investigate options data availability."""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

print("=" * 70)
print("OPTIONS DATA INVESTIGATION")
print("=" * 70)

# Check what underlyings are in mkt.options_1d
print("\nUnderlyings in mkt.options_1d:")
cur.execute(
    """
    SELECT underlying, COUNT(*) as rows, MIN(event_date), MAX(event_date)
    FROM mkt.options_1d
    GROUP BY underlying
    ORDER BY rows DESC
    LIMIT 20
"""
)
rows = cur.fetchall()
if rows:
    for r in rows:
        print(f"  {r[0]}: {r[1]:,} rows ({r[2]} to {r[3]})")
else:
    print("  NO DATA IN TABLE")

# Check total row count
cur.execute("SELECT COUNT(*) FROM mkt.options_1d")
total = cur.fetchone()[0]
print(f"\nTotal rows: {total:,}")

# Check table structure
print("\nTable columns:")
cur.execute(
    """
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'mkt' AND table_name = 'options_1d'
    ORDER BY ordinal_position
"""
)
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

conn.close()
