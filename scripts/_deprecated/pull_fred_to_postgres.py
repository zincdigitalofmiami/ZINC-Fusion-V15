#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Pull Missing FRED Series to Prisma Postgres

Pulls the 16 missing indirect driver FRED series identified during audit.
These series provide macro context for specialist models.

NON-NEGOTIABLES (per CLAUDE.md):
- All data goes to Prisma Postgres (DATABASE_URL)
- Validate before asserting

Usage:
    python scripts/pull_fred_to_postgres.py --dry-run
    python scripts/pull_fred_to_postgres.py
    python scripts/pull_fred_to_postgres.py --series CHNPRINTO01IXPYM
"""

import os
import sys
import ssl
import logging
import argparse
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Fix SSL certificate verification for macOS
import certifi

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()
load_dotenv(".env.vercel")

# Check for fredapi
try:
    from fredapi import Fred
except ImportError:
    logger.error("fredapi not installed. Run: pip install fredapi")
    sys.exit(1)

# FRED API key
FRED_API_KEY = os.environ.get("FRED_API_KEY")
if not FRED_API_KEY:
    # Try to find in .env files
    for f in [".env", "../.env", os.path.expanduser("~/.fred_api_key")]:
        try:
            with open(f) as fh:
                for line in fh:
                    if "FRED_API_KEY" in line:
                        FRED_API_KEY = line.split("=")[1].strip().strip("\"'")
                        break
        except:
            pass

if not FRED_API_KEY:
    logger.error("FRED_API_KEY not found. Set it in environment or .env file")
    logger.error("Get your key at: https://fred.stlouisfed.org/docs/api/api_key.html")
    sys.exit(1)

# The 16 missing indirect drivers (verified available from previous audit)
MISSING_FRED_SERIES = {
    # China Economic Indicators (for China specialist)
    "CHNPRINTO01IXPYM": "China Industrial Production Index",
    "CHNGDPNQDSMEI": "China Real GDP",
    "XTEXVA01CNM667S": "China Exports Value",
    "XTIMVA01CNM667S": "China Imports Value",
    # Freight/Shipping (for logistics costs)
    "FRGSHPUSM649NCIS": "Cass Freight Index: Shipments",
    # Agricultural PPIs (for substitute/crush spreads)
    "WPU0183": "PPI Oilseeds and Grains",
    "WPU01830141": "PPI Soybean Meal",
    "WPU01830142": "PPI Soybean Oil",
    "WPU01830161": "PPI Sunflower Oil",
    "WPU01830171": "PPI Canola Oil",
    # Trade Policy
    "EPUTRADE": "Economic Policy Uncertainty - Trade Policy",
    # Energy (for biofuel economics)
    "PNGASEUUSDM": "Natural Gas EU Price",
    # Additional FX (for trade-weighted calculations)
    "DEXINUS": "India Rupee per USD",
    "DEXMAUS": "Malaysia Ringgit per USD",
    # Agricultural Commodities (global prices)
    "PRICENPQUSDM": "Rice Global Price",
    # Financial Stress
    "STLFSI4": "St Louis Financial Stress Index",
}


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def ensure_fred_table_exists(conn):
    """Create fred_observations_1d table if it doesn't exist."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS fred_observations_1d (
                id SERIAL PRIMARY KEY,
                series_id VARCHAR(50) NOT NULL,
                as_of_date DATE NOT NULL,
                value DOUBLE PRECISION,
                source VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(series_id, as_of_date)
            )
        """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_fred_series ON fred_observations_1d(series_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_fred_date ON fred_observations_1d(as_of_date)"
        )
    conn.commit()
    logger.info("Ensured fred_observations_1d table exists")


def get_existing_fred_series(conn) -> set:
    """Get set of FRED series already in Postgres."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT series_id FROM fred_observations_1d")
        return {row[0] for row in cur.fetchall()}


def pull_fred_series(
    fred, series_id: str, description: str, conn, dry_run: bool = False
) -> int:
    """Pull a single FRED series and insert into Postgres.

    Returns number of rows inserted.
    """
    logger.info(f"Pulling {series_id}: {description}")

    try:
        data = fred.get_series(series_id)

        if data is None or len(data) == 0:
            logger.warning(f"  No data returned for {series_id}")
            return 0

        # Convert to list of tuples
        rows = []
        for date, value in data.items():
            if value is not None and not (
                isinstance(value, float) and str(value) == "nan"
            ):
                rows.append(
                    (series_id, date.date(), float(value), "fred_api", datetime.now())
                )

        if not rows:
            logger.warning(f"  No valid observations for {series_id}")
            return 0

        min_date = min(r[1] for r in rows)
        max_date = max(r[1] for r in rows)
        logger.info(f"  Found {len(rows)} observations: {min_date} to {max_date}")

        if dry_run:
            logger.info(f"  [DRY RUN] Would insert {len(rows)} rows")
            return 0

        # Insert with ON CONFLICT to upsert
        insert_query = """
            INSERT INTO fred_observations_1d (series_id, as_of_date, value, source, created_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (series_id, as_of_date)
            DO UPDATE SET value = EXCLUDED.value, source = EXCLUDED.source
        """

        with conn.cursor() as cur:
            execute_batch(cur, insert_query, rows, page_size=1000)
        conn.commit()

        logger.info(f"  Inserted/updated {len(rows)} rows")
        return len(rows)

    except Exception as e:
        logger.error(f"  Error pulling {series_id}: {e}")
        conn.rollback()
        return 0


def verify_series(conn, series_ids: list):
    """Verify inserted series in Postgres."""
    logger.info("\n" + "=" * 60)
    logger.info("VERIFICATION")
    logger.info("=" * 60)

    with conn.cursor() as cur:
        for series_id in series_ids:
            cur.execute(
                """
                SELECT
                    COUNT(*) as rows,
                    MIN(as_of_date) as first_date,
                    MAX(as_of_date) as last_date
                FROM fred_observations_1d
                WHERE series_id = %s
            """,
                (series_id,),
            )
            result = cur.fetchone()

            if result[0] > 0:
                logger.info(
                    f"  {series_id}: {result[0]:,} rows ({result[1]} to {result[2]})"
                )
            else:
                logger.warning(f"  {series_id}: No data found")


def main():
    parser = argparse.ArgumentParser(description="Pull missing FRED series to Postgres")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without inserting"
    )
    parser.add_argument("--series", type=str, help="Pull specific series only")
    parser.add_argument(
        "--all-missing", action="store_true", help="Pull only series not yet in DB"
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ZINC-FUSION-V15: Pull Missing FRED Series")
    logger.info("=" * 60)
    logger.info(f"FRED API Key: {FRED_API_KEY[:8]}...")
    logger.info(f"Dry run: {args.dry_run}")

    # Initialize FRED client
    fred = Fred(api_key=FRED_API_KEY)

    # Connect to Postgres
    conn = get_postgres_connection()
    logger.info("Connected to Postgres")

    try:
        # Ensure table exists first
        ensure_fred_table_exists(conn)

        # Determine which series to pull
        if args.series:
            if args.series in MISSING_FRED_SERIES:
                series_to_pull = {args.series: MISSING_FRED_SERIES[args.series]}
            else:
                logger.warning(
                    f"Series {args.series} not in missing list, pulling anyway"
                )
                series_to_pull = {args.series: args.series}
        elif args.all_missing:
            existing = get_existing_fred_series(conn)
            series_to_pull = {
                k: v for k, v in MISSING_FRED_SERIES.items() if k not in existing
            }
            logger.info(
                f"Found {len(existing)} existing series, {len(series_to_pull)} missing"
            )
        else:
            series_to_pull = MISSING_FRED_SERIES

        if not series_to_pull:
            logger.info("No series to pull - all already in database!")
            return

        logger.info(f"\nPulling {len(series_to_pull)} FRED series...")

        # Pull each series
        total_rows = 0
        success_count = 0
        fail_count = 0

        for series_id, description in series_to_pull.items():
            rows = pull_fred_series(fred, series_id, description, conn, args.dry_run)
            total_rows += rows
            if rows > 0:
                success_count += 1
            else:
                fail_count += 1

        # Verify
        if not args.dry_run:
            verify_series(conn, list(series_to_pull.keys()))

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("PULL COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Success: {success_count}/{len(series_to_pull)}")
        logger.info(f"Failed: {fail_count}/{len(series_to_pull)}")
        logger.info(f"Total rows: {total_rows:,}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
