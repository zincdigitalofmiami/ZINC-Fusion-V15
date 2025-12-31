#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Historical Data Ingestion Script

Loads historical data from parquet files in the Historical Data directory
into Postgres tables.

Data Sources:
- USDA Export Sales (6,412 rows)
- CFTC COT Positioning (4,506 rows)
- Databento Futures OHLCV (235,647 rows - extended dataset)

Usage:
    python scripts/ingest_historical_data.py --dry-run
    python scripts/ingest_historical_data.py
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
load_dotenv(".env.vercel")

# Historical data paths - use env var, no hardcoded paths
HIST_DATA_PATH = Path(os.getenv("HISTORICAL_DATA_PATH", ""))
if not HIST_DATA_PATH or not HIST_DATA_PATH.exists():
    logger.warning(
        "HISTORICAL_DATA_PATH not set or doesn't exist. "
        "Set HISTORICAL_DATA_PATH env var to run ingestion."
    )

# Data source mappings
DATA_SOURCES = {
    "usda_export_sales": {
        "parquet": HIST_DATA_PATH / "All Other/raw/usda_export_sales.parquet",
        "table": "usda_export_sales",
    },
    "cftc_cot": {
        "parquet": HIST_DATA_PATH / "All Other/raw/cftc_cot.parquet",
        "table": "cftc_cot",
    },
    "databento_extended": {
        "parquet": HIST_DATA_PATH
        / "Databricks Historical Databento/raw/databento_futures_ohlcv_1d_full_2010_plus.parquet",
        "table": "raw_market_futures",
        "merge": True,  # Merge with existing data
    },
}


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def create_usda_table(conn):
    """Create USDA export sales table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS usda_export_sales (
                id SERIAL PRIMARY KEY,
                report_date DATE NOT NULL,
                commodity VARCHAR(100) NOT NULL,
                destination_country VARCHAR(100),
                net_sales_mt DOUBLE PRECISION,
                exports_mt DOUBLE PRECISION,
                outstanding_sales_mt DOUBLE PRECISION,
                source VARCHAR(50),
                ingested_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(report_date, commodity, destination_country)
            )
        """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_usda_date ON usda_export_sales(report_date)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_usda_commodity ON usda_export_sales(commodity)"
        )
    conn.commit()
    logger.info("  Created usda_export_sales table")


def create_cftc_table(conn):
    """Create CFTC COT table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS cftc_cot (
                id SERIAL PRIMARY KEY,
                report_date DATE NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                open_interest BIGINT,
                prod_merc_long BIGINT,
                prod_merc_short BIGINT,
                swap_long BIGINT,
                swap_short BIGINT,
                managed_money_long BIGINT,
                managed_money_short BIGINT,
                other_rept_long BIGINT,
                other_rept_short BIGINT,
                nonrept_long BIGINT,
                nonrept_short BIGINT,
                prod_merc_net BIGINT,
                swap_net BIGINT,
                managed_money_net BIGINT,
                other_rept_net BIGINT,
                nonrept_net BIGINT,
                managed_money_net_pct_oi DOUBLE PRECISION,
                prod_merc_net_pct_oi DOUBLE PRECISION,
                source VARCHAR(50),
                ingested_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(report_date, symbol)
            )
        """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cftc_date ON cftc_cot(report_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cftc_symbol ON cftc_cot(symbol)")
    conn.commit()
    logger.info("  Created cftc_cot table")


def load_usda_data(conn, df: pd.DataFrame, dry_run: bool = False) -> int:
    """Load USDA export sales data."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would insert {len(df):,} USDA rows")
        return 0

    insert_query = """
        INSERT INTO usda_export_sales
        (report_date, commodity, destination_country, net_sales_mt, exports_mt,
         outstanding_sales_mt, source, ingested_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (report_date, commodity, destination_country)
        DO UPDATE SET
            net_sales_mt = EXCLUDED.net_sales_mt,
            exports_mt = EXCLUDED.exports_mt,
            outstanding_sales_mt = EXCLUDED.outstanding_sales_mt,
            ingested_at = EXCLUDED.ingested_at
    """

    batch = []
    for _, row in df.iterrows():
        batch.append(
            (
                row["report_date"],
                row["commodity"],
                row.get("destination_country", "Unknown"),
                float(row["net_sales_mt"]) if pd.notna(row["net_sales_mt"]) else None,
                float(row["exports_mt"]) if pd.notna(row["exports_mt"]) else None,
                (
                    float(row["outstanding_sales_mt"])
                    if pd.notna(row["outstanding_sales_mt"])
                    else None
                ),
                row.get("source", "usda"),
                datetime.now(),
            )
        )

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    return len(batch)


def load_cftc_data(conn, df: pd.DataFrame, dry_run: bool = False) -> int:
    """Load CFTC COT data."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would insert {len(df):,} CFTC rows")
        return 0

    insert_query = """
        INSERT INTO cftc_cot
        (report_date, symbol, open_interest, prod_merc_long, prod_merc_short,
         swap_long, swap_short, managed_money_long, managed_money_short,
         other_rept_long, other_rept_short, nonrept_long, nonrept_short,
         prod_merc_net, swap_net, managed_money_net, other_rept_net, nonrept_net,
         managed_money_net_pct_oi, prod_merc_net_pct_oi, source, ingested_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (report_date, symbol)
        DO UPDATE SET
            open_interest = EXCLUDED.open_interest,
            managed_money_net = EXCLUDED.managed_money_net,
            managed_money_net_pct_oi = EXCLUDED.managed_money_net_pct_oi,
            ingested_at = EXCLUDED.ingested_at
    """

    def safe_int(val):
        if pd.isna(val):
            return None
        return int(val)

    def safe_float(val):
        if pd.isna(val):
            return None
        return float(val)

    batch = []
    for _, row in df.iterrows():
        batch.append(
            (
                row["report_date"],
                row["symbol"],
                safe_int(row.get("open_interest")),
                safe_int(row.get("prod_merc_long")),
                safe_int(row.get("prod_merc_short")),
                safe_int(row.get("swap_long")),
                safe_int(row.get("swap_short")),
                safe_int(row.get("managed_money_long")),
                safe_int(row.get("managed_money_short")),
                safe_int(row.get("other_rept_long")),
                safe_int(row.get("other_rept_short")),
                safe_int(row.get("nonrept_long")),
                safe_int(row.get("nonrept_short")),
                safe_int(row.get("prod_merc_net")),
                safe_int(row.get("swap_net")),
                safe_int(row.get("managed_money_net")),
                safe_int(row.get("other_rept_net")),
                safe_int(row.get("nonrept_net")),
                safe_float(row.get("managed_money_net_pct_oi")),
                safe_float(row.get("prod_merc_net_pct_oi")),
                row.get("source", "cftc"),
                datetime.now(),
            )
        )

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    return len(batch)


def load_extended_futures(conn, df: pd.DataFrame, dry_run: bool = False) -> int:
    """Merge extended futures data with existing raw_market_futures."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would merge {len(df):,} futures rows")
        return 0

    insert_query = """
        INSERT INTO raw_market_futures
        (symbol, as_of_date, open, high, low, close, volume, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, as_of_date) DO NOTHING
    """

    batch = []
    for _, row in df.iterrows():
        batch.append(
            (
                row["symbol"],
                row["as_of_date"],
                float(row["open"]) if pd.notna(row["open"]) else None,
                float(row["high"]) if pd.notna(row["high"]) else None,
                float(row["low"]) if pd.notna(row["low"]) else None,
                float(row["close"]) if pd.notna(row["close"]) else None,
                int(row["volume"]) if pd.notna(row["volume"]) else None,
                datetime.now(),
            )
        )

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    return len(batch)


def ingest_all(dry_run: bool = False):
    """Run full data ingestion."""
    logger.info("=" * 60)
    logger.info("ZINC-FUSION-V15: Historical Data Ingestion")
    logger.info("=" * 60)
    logger.info(f"Dry run: {dry_run}")

    conn = get_postgres_connection()

    try:
        # 1. USDA Export Sales
        logger.info("\n--- USDA Export Sales ---")
        usda_path = DATA_SOURCES["usda_export_sales"]["parquet"]
        if usda_path.exists():
            df = pd.read_parquet(usda_path)
            logger.info(f"  Loaded {len(df):,} rows from parquet")

            if not dry_run:
                create_usda_table(conn)

            inserted = load_usda_data(conn, df, dry_run)
            logger.info(f"  Inserted {inserted:,} rows")
        else:
            logger.warning(f"  File not found: {usda_path}")

        # 2. CFTC COT
        logger.info("\n--- CFTC COT Positioning ---")
        cftc_path = DATA_SOURCES["cftc_cot"]["parquet"]
        if cftc_path.exists():
            df = pd.read_parquet(cftc_path)
            logger.info(f"  Loaded {len(df):,} rows from parquet")

            if not dry_run:
                create_cftc_table(conn)

            inserted = load_cftc_data(conn, df, dry_run)
            logger.info(f"  Inserted {inserted:,} rows")
        else:
            logger.warning(f"  File not found: {cftc_path}")

        # 3. Extended Futures (merge with existing)
        logger.info("\n--- Extended Futures Data ---")
        futures_path = DATA_SOURCES["databento_extended"]["parquet"]
        if futures_path.exists():
            df = pd.read_parquet(futures_path)
            logger.info(f"  Loaded {len(df):,} rows from parquet")

            # Only insert rows that don't exist
            inserted = load_extended_futures(conn, df, dry_run)
            logger.info(f"  Merged {inserted:,} rows (ON CONFLICT DO NOTHING)")
        else:
            logger.warning(f"  File not found: {futures_path}")

        # Verify
        if not dry_run:
            logger.info("\n--- Verification ---")
            with conn.cursor() as cur:
                for table in ["usda_export_sales", "cftc_cot", "raw_market_futures"]:
                    try:
                        cur.execute(f"SELECT COUNT(*) FROM {table}")
                        count = cur.fetchone()[0]
                        logger.info(f"  {table}: {count:,} rows")
                    except Exception as e:
                        logger.error(f"  {table}: {e}")
                        conn.rollback()

        logger.info("\n" + "=" * 60)
        logger.info("INGESTION COMPLETE")
        logger.info("=" * 60)

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Ingest historical data into Postgres")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without inserting"
    )

    args = parser.parse_args()
    ingest_all(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
