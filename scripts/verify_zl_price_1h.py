#!/usr/bin/env python3
"""Verify analytics.zl_price_1h table contents"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def main():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    cur.execute(
        """
        SELECT 
          COUNT(*) as row_count,
          MIN(timestamp) as earliest,
          MAX(timestamp) as latest,
          ROUND(AVG(close)::numeric, 2) as avg_close,
          ROUND(MIN(close)::numeric, 2) as min_close,
          ROUND(MAX(close)::numeric, 2) as max_close
        FROM analytics.zl_price_1h
    """
    )

    row = cur.fetchone()
    print("\n" + "=" * 60)
    print(" analytics.zl_price_1h - Data Verification")
    print("=" * 60)
    print(f"Row Count:     {row[0]}")
    print(f"Earliest:      {row[1]}")
    print(f"Latest:        {row[2]}")
    print(f"Avg Close:     ${row[3]}")
    print(f"Min Close:     ${row[4]}")
    print(f"Max Close:     ${row[5]}")
    print("=" * 60 + "\n")

    # Show first 5 rows
    cur.execute(
        """
        SELECT timestamp, open, high, low, close, volume
        FROM analytics.zl_price_1h
        ORDER BY timestamp DESC
        LIMIT 5
    """
    )

    print("Latest 5 bars:")
    print("-" * 60)
    for r in cur.fetchall():
        print(f"{r[0]} | O:{r[1]:.4f} H:{r[2]:.4f} L:{r[3]:.4f} C:{r[4]:.4f} V:{r[5]}")

    conn.close()


if __name__ == "__main__":
    main()
