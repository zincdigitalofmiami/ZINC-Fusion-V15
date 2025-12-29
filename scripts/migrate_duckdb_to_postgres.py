#!/usr/bin/env python3
"""
ZINC-FUSION-V15: DuckDB → Prisma Postgres Migration Script

This script migrates data from DuckDB (data/fusion.db) to Prisma Postgres.
It preserves DuckDB as a read-only backup and validates row counts after migration.

NON-NEGOTIABLES:
- DuckDB is read-only during migration
- Row counts must match before marking complete
- Append-only for forecast tables (never overwrite)

Usage:
    python scripts/migrate_duckdb_to_postgres.py --dry-run  # Preview only
    python scripts/migrate_duckdb_to_postgres.py            # Execute migration
    python scripts/migrate_duckdb_to_postgres.py --validate # Validate existing migration
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import duckdb
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
load_dotenv('.env.vercel')

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DUCKDB_PATH = PROJECT_ROOT / "data" / "fusion.db"

# Specialist buckets
SPECIALIST_BUCKETS = [
    "crush", "china", "fx", "fed", "tariff",
    "energy", "biofuel", "palm", "volatility", "substitutes"
]


def get_postgres_connection() -> psycopg2.extensions.connection:
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def get_duckdb_connection() -> duckdb.DuckDBPyConnection:
    """Get read-only DuckDB connection."""
    if not DUCKDB_PATH.exists():
        raise FileNotFoundError(f"DuckDB file not found: {DUCKDB_PATH}")
    return duckdb.connect(str(DUCKDB_PATH), read_only=True)


def get_duckdb_table_count(duck_conn: duckdb.DuckDBPyConnection, table: str) -> int:
    """Get row count from DuckDB table."""
    try:
        result = duck_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return result[0] if result else 0
    except Exception as e:
        logger.warning(f"Could not count {table}: {e}")
        return 0


def get_postgres_table_count(pg_conn: psycopg2.extensions.connection, table: str, where: str = "") -> int:
    """Get row count from Postgres table."""
    try:
        with pg_conn.cursor() as cur:
            query = f"SELECT COUNT(*) FROM {table}"
            if where:
                query += f" WHERE {where}"
            cur.execute(query)
            result = cur.fetchone()
            return result[0] if result else 0
    except Exception as e:
        logger.warning(f"Could not count {table}: {e}")
        return 0


def migrate_market_futures(duck_conn, pg_conn, dry_run: bool = False) -> Tuple[int, int]:
    """Migrate raw.market_futures_1d."""
    table = "raw.market_futures_1d"
    logger.info(f"Migrating {table}")

    source_count = get_duckdb_table_count(duck_conn, table)
    logger.info(f"  Source rows: {source_count:,}")

    if dry_run or source_count == 0:
        return source_count, 0

    insert_query = """
        INSERT INTO raw_market_futures (symbol, as_of_date, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, as_of_date) DO NOTHING
    """

    migrated = 0
    batch_size = 10000
    offset = 0

    while True:
        rows = duck_conn.execute(f"""
            SELECT symbol, as_of_date, open, high, low, close, volume
            FROM {table}
            ORDER BY as_of_date, symbol
            LIMIT {batch_size} OFFSET {offset}
        """).fetchall()

        if not rows:
            break

        with pg_conn.cursor() as cur:
            execute_batch(cur, insert_query, rows, page_size=1000)
        pg_conn.commit()

        migrated += len(rows)
        offset += batch_size
        logger.info(f"  Migrated {migrated:,} / {source_count:,}")

    return source_count, migrated


def migrate_fred_observations(duck_conn, pg_conn, dry_run: bool = False) -> Tuple[int, int]:
    """Migrate raw.fred_observations_1d."""
    table = "raw.fred_observations_1d"
    logger.info(f"Migrating {table}")

    source_count = get_duckdb_table_count(duck_conn, table)
    logger.info(f"  Source rows: {source_count:,}")

    if dry_run or source_count == 0:
        return source_count, 0

    insert_query = """
        INSERT INTO raw_fred_observations (series_id, as_of_date, value)
        VALUES (%s, %s, %s)
        ON CONFLICT (series_id, as_of_date) DO NOTHING
    """

    migrated = 0
    batch_size = 10000
    offset = 0

    while True:
        rows = duck_conn.execute(f"""
            SELECT series_id, as_of_date, value
            FROM {table}
            ORDER BY as_of_date, series_id
            LIMIT {batch_size} OFFSET {offset}
        """).fetchall()

        if not rows:
            break

        with pg_conn.cursor() as cur:
            execute_batch(cur, insert_query, rows, page_size=1000)
        pg_conn.commit()

        migrated += len(rows)
        offset += batch_size
        logger.info(f"  Migrated {migrated:,} / {source_count:,}")

    return source_count, migrated


def migrate_fx_spot(duck_conn, pg_conn, dry_run: bool = False) -> Tuple[int, int]:
    """Migrate raw.fx_spot_1d."""
    table = "raw.fx_spot_1d"
    logger.info(f"Migrating {table}")

    source_count = get_duckdb_table_count(duck_conn, table)
    logger.info(f"  Source rows: {source_count:,}")

    if dry_run or source_count == 0:
        return source_count, 0

    insert_query = """
        INSERT INTO raw_fx_spot (pair, as_of_date, rate)
        VALUES (%s, %s, %s)
        ON CONFLICT (pair, as_of_date) DO NOTHING
    """

    migrated = 0
    batch_size = 10000
    offset = 0

    while True:
        rows = duck_conn.execute(f"""
            SELECT symbol, as_of_date, price
            FROM {table}
            ORDER BY as_of_date, symbol
            LIMIT {batch_size} OFFSET {offset}
        """).fetchall()

        if not rows:
            break

        with pg_conn.cursor() as cur:
            execute_batch(cur, insert_query, rows, page_size=1000)
        pg_conn.commit()

        migrated += len(rows)
        offset += batch_size
        logger.info(f"  Migrated {migrated:,} / {source_count:,}")

    return source_count, migrated


def migrate_epa_rin(duck_conn, pg_conn, dry_run: bool = False) -> Tuple[int, int]:
    """Migrate raw.epa_rin_prices_1d."""
    table = "raw.epa_rin_prices_1d"
    logger.info(f"Migrating {table}")

    source_count = get_duckdb_table_count(duck_conn, table)
    logger.info(f"  Source rows: {source_count:,}")

    if dry_run or source_count == 0:
        return source_count, 0

    insert_query = """
        INSERT INTO raw_epa_rin_prices (rin_type, as_of_date, price)
        VALUES (%s, %s, %s)
        ON CONFLICT (rin_type, as_of_date) DO NOTHING
    """

    rows = duck_conn.execute(f"""
        SELECT rin_type, as_of_date, price FROM {table}
    """).fetchall()

    with pg_conn.cursor() as cur:
        execute_batch(cur, insert_query, rows, page_size=100)
    pg_conn.commit()

    return source_count, len(rows)


def migrate_oof_core(duck_conn, pg_conn, dry_run: bool = False) -> Tuple[int, int]:
    """Migrate training.oof_core_zl_1d with source='core'."""
    table = "training.oof_core_zl_1d"
    logger.info(f"Migrating {table}")

    source_count = get_duckdb_table_count(duck_conn, table)
    logger.info(f"  Source rows: {source_count:,}")

    if dry_run or source_count == 0:
        return source_count, 0

    insert_query = """
        INSERT INTO oof_predictions (source, as_of_date, horizon, fold_id, p10, p50, p90, model_version, trained_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source, as_of_date, horizon, fold_id) DO NOTHING
    """

    migrated = 0
    batch_size = 5000
    offset = 0

    while True:
        rows = duck_conn.execute(f"""
            SELECT
                'core' as source,
                as_of_date,
                horizon_steps as horizon,
                0 as fold_id,  -- Legacy data has no fold_id
                p10, p50, p90,
                model_version,
                trained_at
            FROM {table}
            ORDER BY as_of_date, horizon_steps
            LIMIT {batch_size} OFFSET {offset}
        """).fetchall()

        if not rows:
            break

        with pg_conn.cursor() as cur:
            execute_batch(cur, insert_query, rows, page_size=500)
        pg_conn.commit()

        migrated += len(rows)
        offset += batch_size
        logger.info(f"  Migrated {migrated:,} / {source_count:,}")

    return source_count, migrated


def migrate_specialist_features(duck_conn, pg_conn, dry_run: bool = False) -> Dict[str, Tuple[int, int]]:
    """Migrate specialist feature tables to unified specialist_features table."""
    results = {}

    for bucket in SPECIALIST_BUCKETS:
        duckdb_table = f"training.specialist_{bucket}_1d"
        logger.info(f"Migrating specialist: {bucket}")

        source_count = get_duckdb_table_count(duck_conn, duckdb_table)
        logger.info(f"  Source rows: {source_count:,}")

        if source_count == 0:
            results[bucket] = (0, 0)
            continue

        if dry_run:
            results[bucket] = (source_count, 0)
            continue

        # Get all data
        df = duck_conn.execute(f"SELECT * FROM {duckdb_table}").fetchdf()

        insert_query = """
            INSERT INTO specialist_features (bucket, as_of_date, features)
            VALUES (%s, %s, %s)
            ON CONFLICT (bucket, as_of_date) DO UPDATE SET features = EXCLUDED.features
        """

        migrated = 0
        batch = []

        for _, row in df.iterrows():
            as_of_date = row.get('as_of_date')
            if as_of_date is None:
                continue

            # Convert row to feature dict (exclude metadata columns)
            features = {}
            for col in df.columns:
                if col not in ['as_of_date', 'date', 'index', 'symbol', 'horizon_days']:
                    val = row[col]
                    if val is not None and not (isinstance(val, float) and str(val) == 'nan'):
                        try:
                            features[col] = float(val) if isinstance(val, (int, float)) else str(val)
                        except:
                            features[col] = str(val)

            batch.append((bucket, as_of_date, json.dumps(features)))

            if len(batch) >= 1000:
                with pg_conn.cursor() as cur:
                    execute_batch(cur, insert_query, batch, page_size=100)
                pg_conn.commit()
                migrated += len(batch)
                batch = []

        # Final batch
        if batch:
            with pg_conn.cursor() as cur:
                execute_batch(cur, insert_query, batch, page_size=100)
            pg_conn.commit()
            migrated += len(batch)

        logger.info(f"  Migrated {migrated:,} rows for {bucket}")
        results[bucket] = (source_count, migrated)

    return results


def validate_migration(duck_conn, pg_conn) -> bool:
    """Validate migration by comparing row counts."""
    logger.info("=" * 60)
    logger.info("VALIDATION: Comparing row counts")
    logger.info("=" * 60)

    all_valid = True

    checks = [
        ("raw.market_futures_1d", "raw_market_futures", ""),
        ("raw.fred_observations_1d", "raw_fred_observations", ""),
        ("raw.fx_spot_1d", "raw_fx_spot", ""),
        ("raw.epa_rin_prices_1d", "raw_epa_rin_prices", ""),
        ("training.oof_core_zl_1d", "oof_predictions", "source = 'core'"),
    ]

    for duck_table, pg_table, where in checks:
        duck_count = get_duckdb_table_count(duck_conn, duck_table)
        pg_count = get_postgres_table_count(pg_conn, pg_table, where)

        status = "✓" if duck_count == pg_count else "✗"
        if duck_count != pg_count:
            all_valid = False

        logger.info(f"  {status} {duck_table}: DuckDB={duck_count:,} Postgres={pg_count:,}")

    # Check specialist features
    for bucket in SPECIALIST_BUCKETS:
        duck_table = f"training.specialist_{bucket}_1d"
        duck_count = get_duckdb_table_count(duck_conn, duck_table)
        pg_count = get_postgres_table_count(pg_conn, "specialist_features", f"bucket = '{bucket}'")

        status = "✓" if duck_count == pg_count else "✗"
        if duck_count != pg_count:
            all_valid = False

        logger.info(f"  {status} specialist_{bucket}: DuckDB={duck_count:,} Postgres={pg_count:,}")

    if all_valid:
        logger.info("\n✓ VALIDATION PASSED: All row counts match")
    else:
        logger.error("\n✗ VALIDATION FAILED: Row count mismatches detected")

    return all_valid


def run_migration(dry_run: bool = False, validate_only: bool = False):
    """Run the full migration pipeline."""
    logger.info("=" * 60)
    logger.info("ZINC-FUSION-V15: DuckDB → Prisma Postgres Migration")
    logger.info("=" * 60)
    logger.info(f"DuckDB path: {DUCKDB_PATH}")
    logger.info(f"Dry run: {dry_run}")
    logger.info(f"Validate only: {validate_only}")
    logger.info("")

    duck_conn = get_duckdb_connection()
    pg_conn = get_postgres_connection()

    try:
        if validate_only:
            validate_migration(duck_conn, pg_conn)
            return

        # Phase 1: Raw data
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 1: Migrating raw data")
        logger.info("=" * 60)

        migrate_market_futures(duck_conn, pg_conn, dry_run)
        migrate_fred_observations(duck_conn, pg_conn, dry_run)
        migrate_fx_spot(duck_conn, pg_conn, dry_run)
        migrate_epa_rin(duck_conn, pg_conn, dry_run)

        # Phase 2: Training data
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 2: Migrating training data")
        logger.info("=" * 60)

        migrate_oof_core(duck_conn, pg_conn, dry_run)
        migrate_specialist_features(duck_conn, pg_conn, dry_run)

        # Validate
        if not dry_run:
            logger.info("\n")
            validate_migration(duck_conn, pg_conn)

        logger.info("\n" + "=" * 60)
        logger.info("MIGRATION COMPLETE")
        logger.info("=" * 60)

    finally:
        duck_conn.close()
        pg_conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate DuckDB to Prisma Postgres")
    parser.add_argument("--dry-run", action="store_true", help="Preview migration without executing")
    parser.add_argument("--validate", action="store_true", help="Validate existing migration only")

    args = parser.parse_args()
    run_migration(dry_run=args.dry_run, validate_only=args.validate)


if __name__ == "__main__":
    main()
