#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Sync Cloud Data to Local for Training

This script syncs data from Prisma Cloud to local parquet files for training.
Training runs locally to avoid cloud compute costs and latency.

Architecture:
    Prisma Cloud (mkt.*, econ.*, training.*) → Local parquet files → Training → Results back to cloud

Usage:
    python scripts/sync_cloud_to_local.py --tables all
    python scripts/sync_cloud_to_local.py --tables mkt.futures_1d training.matrix_1d
    python scripts/sync_cloud_to_local.py --dry-run
"""

import os
import sys
import logging
import argparse
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Local data directory
LOCAL_DATA_DIR = Path(__file__).parent.parent / "data" / "training_cache"

# Tables to sync for training
# =============================================================================
# DEPRECATED: specialist_*_1d/1h OHLCV tables are DUPLICATES of mkt.futures_1d
# They have been REMOVED from this sync list. Training uses:
#   - mkt.futures_1d (filter by symbol for each specialist bucket)
#   - training.specialist_features (computed JSON blob per specialist)
#   - training.specialist_trump_effect_1d (has signal/confidence columns)
# =============================================================================
TRAINING_TABLES = {
    # Market data for feature engineering (CANONICAL SOURCE)
    "mkt.futures_1d": {"key": "event_date", "incremental": True},
    "mkt.futures_1h": {"key": "event_time", "incremental": True},
    "mkt.fx_1d": {"key": "event_date", "incremental": True},
    # Economic indicators (all 7 econ.* tables)
    "econ.rates_1d": {"key": "event_date", "incremental": True},
    "econ.inflation_1d": {"key": "event_date", "incremental": True},
    "econ.labor_1d": {"key": "event_date", "incremental": True},
    "econ.activity_1d": {"key": "event_date", "incremental": True},
    "econ.vol_indices_1d": {"key": "event_date", "incremental": True},
    "econ.commodities_1d": {"key": "event_date", "incremental": True},
    "econ.money_1d": {"key": "event_date", "incremental": True},
    # Training tables
    "training.matrix_1d": {"key": "trade_date", "incremental": True},
    "training.specialist_features": {"key": "as_of_date", "incremental": True},
    "training.specialist_trump_effect_1d": {"key": "as_of_date", "incremental": True},
    # Features
    "features.elite_1d": {"key": "as_of_date", "incremental": True},
}


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")
    return psycopg2.connect(database_url)


def sync_table(conn, table_name: str, config: dict, dry_run: bool = False) -> dict:
    """Sync a single table from cloud to local parquet."""
    schema, table = table_name.split(".")
    local_path = LOCAL_DATA_DIR / schema / f"{table}.parquet"

    # Ensure directory exists
    local_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if we have existing local data for incremental sync
    last_key = None
    if config.get("incremental") and local_path.exists():
        try:
            existing_df = pd.read_parquet(local_path)
            if config["key"] in existing_df.columns:
                last_key = existing_df[config["key"]].max()
                logger.info(f"  Incremental sync from {last_key}")
        except Exception as e:
            logger.warning(f"  Could not read existing file: {e}")

    # Build query
    query = f'SELECT * FROM "{schema}"."{table}"'
    if last_key is not None:
        query += f" WHERE {config['key']} > '{last_key}'"
    query += f" ORDER BY {config['key']}"

    if dry_run:
        # Just get count
        count_query = f'SELECT COUNT(*) FROM "{schema}"."{table}"'
        if last_key is not None:
            count_query += f" WHERE {config['key']} > '{last_key}'"

        with conn.cursor() as cur:
            cur.execute(count_query)
            count = cur.fetchone()[0]

        return {
            "table": table_name,
            "rows_to_sync": count,
            "local_path": str(local_path),
            "incremental": last_key is not None,
            "status": "dry_run",
        }

    # Fetch data
    logger.info(f"  Fetching from {table_name}...")
    df = pd.read_sql(query, conn)

    if len(df) == 0:
        logger.info(f"  No new rows to sync")
        return {
            "table": table_name,
            "rows_synced": 0,
            "local_path": str(local_path),
            "status": "up_to_date",
        }

    # If incremental, merge with existing
    if last_key is not None and local_path.exists():
        existing_df = pd.read_parquet(local_path)
        df = pd.concat([existing_df, df], ignore_index=True)
        df = df.drop_duplicates(
            subset=(
                [config["key"], "symbol"] if "symbol" in df.columns else [config["key"]]
            )
        )

    # Save to parquet
    df.to_parquet(local_path, index=False)

    logger.info(f"  ✅ Synced {len(df):,} rows to {local_path}")

    return {
        "table": table_name,
        "rows_synced": len(df),
        "local_path": str(local_path),
        "status": "success",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Sync cloud data to local for training"
    )
    parser.add_argument(
        "--tables", nargs="+", default=["all"], help="Tables to sync (default: all)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without syncing",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ZINC-FUSION-V15: Cloud → Local Sync")
    logger.info("=" * 60)

    # Determine tables to sync
    if args.tables == ["all"]:
        tables_to_sync = TRAINING_TABLES
    else:
        tables_to_sync = {
            t: TRAINING_TABLES[t] for t in args.tables if t in TRAINING_TABLES
        }
        if not tables_to_sync:
            logger.error(
                f"No valid tables specified. Available: {list(TRAINING_TABLES.keys())}"
            )
            sys.exit(1)

    logger.info(f"Tables to sync: {len(tables_to_sync)}")
    logger.info(f"Local cache dir: {LOCAL_DATA_DIR}")
    if args.dry_run:
        logger.info("DRY RUN - no changes will be made")
    logger.info("")

    # Connect to cloud
    try:
        conn = get_postgres_connection()
        logger.info("✅ Connected to Prisma Cloud")
    except Exception as e:
        logger.error(f"❌ Failed to connect: {e}")
        sys.exit(1)

    # Sync each table
    results = []
    for table_name, config in tables_to_sync.items():
        logger.info(f"\n📦 {table_name}")
        try:
            result = sync_table(conn, table_name, config, dry_run=args.dry_run)
            results.append(result)
        except Exception as e:
            logger.error(f"  ❌ Failed: {e}")
            results.append({"table": table_name, "status": "error", "error": str(e)})

    conn.close()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("SYNC SUMMARY")
    logger.info("=" * 60)

    total_rows = 0
    for r in results:
        status_icon = (
            "✅" if r["status"] in ("success", "up_to_date", "dry_run") else "❌"
        )
        rows = r.get("rows_synced", r.get("rows_to_sync", 0))
        total_rows += rows
        logger.info(f"{status_icon} {r['table']}: {rows:,} rows")

    logger.info(f"\nTotal rows: {total_rows:,}")
    logger.info(f"Local cache: {LOCAL_DATA_DIR}")


if __name__ == "__main__":
    main()
