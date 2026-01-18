# ⚠️ MIGRATION NOTICE: This script references raw.* tables.
# TODO: Migrate to v2 schema tables (mkt/econ/alt/pos/supply) if still needed.

#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Sparse Source Coverage Audit (READ ONLY)

This script previously inserted synthetic rows into raw tables to "extend" history.
Per the repo's zero-tolerance policy for fake data and fallbacks, all write paths
have been removed and this script is now audit-only.

Use real ingestion/backfill scripts for each source instead.

Usage:
    python scripts/backfill_sparse_sources.py
    python scripts/backfill_sparse_sources.py --strict
"""

import os
import logging
import argparse

import psycopg2
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
load_dotenv(".env.vercel")


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")
    return psycopg2.connect(database_url)


def backfill_usda_exports(conn, dry_run: bool = False) -> int:
    """Disabled. This script is audit-only (no synthetic inserts)."""
    raise SystemExit(
        "Disabled: backfill_sparse_sources is read-only. Use real ingestion to populate raw.usda_export_sales_1w."
    )


def backfill_usda_wasde(conn, dry_run: bool = False) -> int:
    """Disabled. This script is audit-only (no synthetic inserts)."""
    raise SystemExit(
        "Disabled: backfill_sparse_sources is read-only. Use real ingestion to populate raw.usda_wasde_1m."
    )


def backfill_epa_rin(conn, dry_run: bool = False) -> int:
    """Disabled. This script is audit-only (no synthetic inserts)."""
    raise SystemExit(
        "Disabled: backfill_sparse_sources is read-only. Use real ingestion to populate raw.epa_rin_prices_1d."
    )


def backfill_news(conn, dry_run: bool = False) -> int:
    """Disabled. This script is audit-only (no synthetic inserts)."""
    raise SystemExit(
        "Disabled: backfill_sparse_sources is read-only. Use real ingestion to populate raw.news_articles_1d."
    )


def verify_backfill(conn, strict: bool = False) -> int:
    """Read-only coverage audit for sparse sources."""
    logger.info("=" * 60)
    logger.info("SPARSE SOURCE COVERAGE AUDIT (READ ONLY)")
    logger.info("=" * 60)

    sources = [
        ('raw.epa_rin_prices_1d', 'event_date', '2010'),  # RIN started 2010
        ('raw.usda_export_sales_1w', 'event_date', '2000'),
        ('raw.usda_wasde_1m', 'event_date', '2000'),
        ('raw.news_articles_1d', 'event_date', '2000'),
    ]

    exit_code = 0
    with conn.cursor() as cur:
        for table, date_col, target in sources:
            schema, tbl = table.split('.')
            cur.execute(f'SELECT MIN({date_col}), MAX({date_col}), COUNT(*) FROM "{schema}"."{tbl}"')
            min_dt, max_dt, cnt = cur.fetchone()
            ok = bool(min_dt and min_dt.year <= int(target))
            status = "✅" if ok else "⚠️"
            logger.info(f"  {status} {table}: {min_dt} to {max_dt} ({cnt:,} rows)")
            if strict and not ok:
                exit_code = 1

    return exit_code


def main():
    parser = argparse.ArgumentParser(description="Audit sparse source coverage (read-only).")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if coverage does not meet target start years.",
    )

    args = parser.parse_args()

    conn = get_postgres_connection()

    try:
        exit_code = verify_backfill(conn, strict=args.strict)
        raise SystemExit(exit_code)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
