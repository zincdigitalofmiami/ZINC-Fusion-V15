#!/usr/bin/env python3
"""Create `analytics.zl_price_1h` table (explicit apply required)."""

import argparse
import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()


DDL_TABLE = """
CREATE TABLE analytics.zl_price_1h (
    timestamp TIMESTAMPTZ PRIMARY KEY,
    open NUMERIC(10,4) NOT NULL,
    high NUMERIC(10,4) NOT NULL,
    low NUMERIC(10,4) NOT NULL,
    close NUMERIC(10,4) NOT NULL,
    volume BIGINT NOT NULL DEFAULT 0,
    source VARCHAR(50) NOT NULL DEFAULT 'yahoo',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

DDL_INDEX = "CREATE INDEX idx_zl_price_1h_ts ON analytics.zl_price_1h(timestamp DESC)"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create analytics.zl_price_1h (schema mutation; requires explicit flags)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually create the table/index if missing.",
    )
    parser.add_argument(
        "--yes-really",
        action="store_true",
        help="Confirm you intend to modify the production database schema.",
    )
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not found in environment", file=sys.stderr)
        return 2

    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'analytics' AND table_name = 'zl_price_1h'
            )
            """
        )
        exists = cur.fetchone()[0]

        if exists:
            print("✅ analytics.zl_price_1h already exists")
        else:
            if not (args.apply and args.yes_really):
                print(
                    "❌ analytics.zl_price_1h does not exist. Re-run with `--apply --yes-really` to create it."
                )
                return 1

            print("Creating analytics.zl_price_1h...")
            cur.execute(DDL_TABLE)
            cur.execute(DDL_INDEX)
            conn.commit()
            print("✅ Table created")

        cur.execute("SELECT COUNT(*) FROM analytics.zl_price_1h")
        count = cur.fetchone()[0]
        print(f"Current rows: {count}")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
