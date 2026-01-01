#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Fix Naming Contract Violations

NAMING CONTRACT:
- Schema = tier (raw, curated, features, training, forecasts, monitoring, specialist, archive)
- Table = entity + frequency suffix (_1d, _1h, _1w, _1m) or _static for reference tables
- NO doubled prefixes (raw.raw_* is WRONG)
- NO cross-contamination (public.raw_* is WRONG)
- NO version suffixes (_v2, _new, _old)

Usage:
    python scripts/fix_naming_contract.py --dry-run
    python scripts/fix_naming_contract.py
"""

import os
import sys
import logging
import argparse

import psycopg2
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()
load_dotenv('.env.vercel')


# RENAMES: (old_schema, old_table) -> (new_schema, new_table)
RENAMES = [
    # Fix doubled prefixes
    (("raw", "raw_fx_spot"), ("raw", "fx_spot_1d")),
    (("raw", "raw_epa_rin_prices"), ("raw", "epa_rin_prices_1d")),
    (("raw", "raw_fred_observations"), ("raw", "fred_observations_1d")),
    (("raw", "raw_options_futures"), ("raw", "options_futures_1d")),
    # Add missing cadence suffixes
    (("raw", "cftc_cot"), ("raw", "cftc_cot_1w")),
    (("raw", "weather_noaa"), ("raw", "weather_noaa_1d")),
    (("raw", "usda_export_sales"), ("raw", "usda_export_sales_1w")),
    (("raw", "usda_wasde"), ("raw", "usda_wasde_1m")),
    (("raw", "news_articles"), ("raw", "news_articles_1d")),
]

# DROPS: Tables to remove
DROPS = [
    ("raw", "raw_cftc_cot"),           # Legacy format, cftc_cot has better schema
    ("raw", "raw_market_futures"),      # Duplicate, open_interest all NULL
    ("raw", "raw_weather_observations"), # Sparse, weather_noaa has region/country
    ("public", "raw_fred_observations"), # Misplaced in wrong schema
]


def get_postgres_connection():
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def table_exists(conn, schema: str, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
            )
        """, (schema, table))
        return cur.fetchone()[0]


def get_row_count(conn, schema: str, table: str) -> int:
    try:
        with conn.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
            return cur.fetchone()[0]
    except:
        return 0


def rename_table(conn, old_schema: str, old_table: str, new_schema: str, new_table: str, dry_run: bool) -> bool:
    if not table_exists(conn, old_schema, old_table):
        logger.warning(f"  SKIP: {old_schema}.{old_table} does not exist")
        return False

    if table_exists(conn, new_schema, new_table):
        logger.error(f"  ERROR: Target {new_schema}.{new_table} already exists!")
        return False

    row_count = get_row_count(conn, old_schema, old_table)
    logger.info(f"  RENAME: {old_schema}.{old_table} -> {new_schema}.{new_table} ({row_count:,} rows)")

    if not dry_run:
        with conn.cursor() as cur:
            if old_schema == new_schema:
                cur.execute(f'ALTER TABLE "{old_schema}"."{old_table}" RENAME TO "{new_table}"')
            else:
                cur.execute(f'ALTER TABLE "{old_schema}"."{old_table}" SET SCHEMA "{new_schema}"')
                cur.execute(f'ALTER TABLE "{new_schema}"."{old_table}" RENAME TO "{new_table}"')
        conn.commit()

    return True


def drop_table(conn, schema: str, table: str, dry_run: bool) -> bool:
    if not table_exists(conn, schema, table):
        logger.info(f"  SKIP: {schema}.{table} does not exist")
        return False

    row_count = get_row_count(conn, schema, table)
    logger.info(f"  DROP: {schema}.{table} ({row_count:,} rows)")

    if not dry_run:
        with conn.cursor() as cur:
            cur.execute(f'DROP TABLE "{schema}"."{table}" CASCADE')
        conn.commit()

    return True


def audit_final_state(conn):
    logger.info("\n" + "=" * 60)
    logger.info("FINAL STATE")
    logger.info("=" * 60)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema IN ('public', 'raw')
            AND table_type = 'BASE TABLE'
            ORDER BY table_schema, table_name
        """)

        violations = []

        for schema, table in cur.fetchall():
            full_name = f'{schema}.{table}'
            cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
            count = cur.fetchone()[0]

            # Check for violations
            is_violation = False
            reason = ""

            if schema == 'raw' and table.startswith('raw_'):
                is_violation = True
                reason = "doubled prefix"
            elif schema == 'public' and table.startswith('raw_'):
                is_violation = True
                reason = "cross-contamination"
            elif schema == 'public' and table != '_prisma_migrations':
                is_violation = True
                reason = "should be in raw schema"

            if is_violation:
                violations.append((full_name, reason))
                logger.error(f"  ❌ {full_name}: {count:,} rows - {reason}")
            else:
                logger.info(f"  ✅ {full_name}: {count:,} rows")

        if violations:
            logger.error(f"\n❌ {len(violations)} VIOLATIONS REMAIN")
            return False
        else:
            logger.info(f"\n✅ ALL TABLES COMPLIANT")
            return True


def main():
    parser = argparse.ArgumentParser(description="Fix naming contract violations")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ZINC-FUSION-V15: Fix Naming Contract Violations")
    logger.info("=" * 60)
    logger.info(f"Dry run: {args.dry_run}")

    conn = get_postgres_connection()

    try:
        # Phase 1: Renames
        logger.info("\n--- PHASE 1: RENAMES ---")
        for (old_schema, old_table), (new_schema, new_table) in RENAMES:
            rename_table(conn, old_schema, old_table, new_schema, new_table, args.dry_run)

        # Phase 2: Drops
        logger.info("\n--- PHASE 2: DROPS ---")
        for schema, table in DROPS:
            drop_table(conn, schema, table, args.dry_run)

        # Phase 3: Audit
        if not args.dry_run:
            audit_final_state(conn)
        else:
            logger.info("\n[DRY RUN] No changes made")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
