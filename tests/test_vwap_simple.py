#!/usr/bin/env python3
"""
Simple VWAP test to debug the issue
"""

__test__ = False  # Pytest should not collect integration scripts.


import os

import psycopg2
import pytest


def test_database_query():
    """Test if database query works"""
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")
    print("Testing database query...")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Simple test query
    cur.execute("SELECT COUNT(*) FROM mkt.options_1d WHERE underlying LIKE '6%'")
    total = cur.fetchone()[0]
    print(f"Total FX options: {total:,}")

    # Test the actual query used in VWAP calculation
    print("Testing VWAP query...")
    cur.execute(
        """
        SELECT underlying, event_date, open, high, low, close, volume
        FROM mkt.options_1d
        WHERE underlying LIKE '6%' AND volume IS NOT NULL AND close IS NOT NULL
        LIMIT 10
    """
    )

    rows = cur.fetchall()
    print(f"Sample query returned {len(rows)} rows")

    if rows:
        print("Sample data:")
        for row in rows[:3]:
            print(
                f"  {row[0]} {row[1]}: O={row[2]} H={row[3]} L={row[4]} C={row[5]} V={row[6]}"
            )

    conn.close()
    print("✅ Database queries work fine")


if __name__ == "__main__":
    test_database_query()
