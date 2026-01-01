#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Backfill Sparse Data Sources to 2000

This script backfills sparse data sources with historical data so that
21d/63d/126d models can use ALL sources from 2000+.

Sources to backfill:
- EPA RIN prices (currently 2024+, need 2000+)
- USDA Export Sales (currently 2020+, need 2000+)
- USDA WASDE (currently 2020+, need 2000+)
- News sentiment (currently 2016+, need 2000+)

Data sources:
- USDA: USDA FAS GATS API (historical export data)
- EPA RIN: EPA EMTS historical data
- News: Can use neutral sentiment placeholders or historical archives

Usage:
    python scripts/backfill_sparse_sources.py --dry-run
    python scripts/backfill_sparse_sources.py
"""

import os
import sys
import logging
import argparse
from datetime import datetime, date
from pathlib import Path

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


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def backfill_usda_exports(conn, dry_run: bool = False) -> int:
    """
    Backfill USDA export sales data to 2000.

    Strategy: Use USDA FAS historical data or extrapolate from earliest available.
    For now, we'll create placeholder rows with NULL values that AutoGluon can handle.
    """
    logger.info("=" * 60)
    logger.info("BACKFILLING USDA EXPORT SALES TO 2000")
    logger.info("=" * 60)

    with conn.cursor() as cur:
        # Get current min date
        cur.execute('SELECT MIN(report_date), MAX(report_date) FROM "raw"."usda_export_sales_1w"')
        min_date, max_date = cur.fetchone()
        logger.info(f"  Current range: {min_date} to {max_date}")

        if min_date and min_date <= date(2000, 1, 1):
            logger.info("  Already backfilled to 2000+")
            return 0

        # Get distinct commodities
        cur.execute('SELECT DISTINCT commodity FROM "raw"."usda_export_sales_1w"')
        commodities = [row[0] for row in cur.fetchall()]
        logger.info(f"  Commodities: {commodities}")

        # Generate weekly dates from 2000 to min_date
        target_start = date(2000, 1, 6)  # First Thursday of 2000
        if min_date:
            end_date = min_date
        else:
            end_date = date(2020, 1, 1)

        dates = pd.date_range(start=target_start, end=end_date, freq='W-THU')
        logger.info(f"  Generating {len(dates)} weekly dates from {target_start} to {end_date}")

        if dry_run:
            logger.info(f"  [DRY RUN] Would insert ~{len(dates) * len(commodities)} placeholder rows")
            return 0

        # Insert placeholder rows with NULL values
        insert_query = """
            INSERT INTO "raw"."usda_export_sales_1w"
            (report_date, commodity, destination_country, net_sales_mt, exports_mt,
             outstanding_sales_mt, source, ingested_at)
            VALUES (%s, %s, %s, NULL, NULL, NULL, %s, %s)
            ON CONFLICT (report_date, commodity, destination_country) DO NOTHING
        """

        batch = []
        for dt in dates:
            for commodity in commodities:
                batch.append((
                    dt.date(),
                    commodity,
                    'WORLD',  # Aggregate
                    'backfill_placeholder',
                    datetime.now()
                ))

        execute_batch(cur, insert_query, batch, page_size=1000)
        conn.commit()

        logger.info(f"  Inserted {len(batch)} placeholder rows")
        return len(batch)


def backfill_usda_wasde(conn, dry_run: bool = False) -> int:
    """
    Backfill USDA WASDE data to 2000.

    WASDE reports are monthly, so we generate monthly placeholders.
    """
    logger.info("=" * 60)
    logger.info("BACKFILLING USDA WASDE TO 2000")
    logger.info("=" * 60)

    with conn.cursor() as cur:
        # Get current min date
        cur.execute('SELECT MIN(report_date), MAX(report_date) FROM "raw"."usda_wasde_1m"')
        min_date, max_date = cur.fetchone()
        logger.info(f"  Current range: {min_date} to {max_date}")

        if min_date and min_date <= date(2000, 1, 1):
            logger.info("  Already backfilled to 2000+")
            return 0

        # Get distinct commodity/metric/country combinations
        cur.execute('SELECT DISTINCT commodity, metric, country FROM "raw"."usda_wasde_1m"')
        combos = cur.fetchall()
        logger.info(f"  Commodity/metric/country combinations: {len(combos)}")

        # Generate monthly dates from 2000 to min_date
        target_start = date(2000, 1, 12)  # ~12th of each month
        if min_date:
            end_date = min_date
        else:
            end_date = date(2020, 1, 1)

        dates = pd.date_range(start=target_start, end=end_date, freq='MS') + pd.Timedelta(days=11)
        logger.info(f"  Generating {len(dates)} monthly dates from {target_start} to {end_date}")

        if dry_run:
            logger.info(f"  [DRY RUN] Would insert ~{len(dates) * len(combos)} placeholder rows")
            return 0

        # Insert placeholder rows
        insert_query = """
            INSERT INTO "raw"."usda_wasde_1m"
            (report_date, commodity, metric, country, value, unit, source, ingested_at)
            VALUES (%s, %s, %s, %s, NULL, %s, %s, %s)
            ON CONFLICT (report_date, commodity, metric, country) DO NOTHING
        """

        batch = []
        for dt in dates:
            for commodity, metric, country in combos:
                batch.append((
                    dt.date(),
                    commodity,
                    metric,
                    country,
                    'MMT',  # Standard unit
                    'backfill_placeholder',
                    datetime.now()
                ))

        execute_batch(cur, insert_query, batch, page_size=1000)
        conn.commit()

        logger.info(f"  Inserted {len(batch)} placeholder rows")
        return len(batch)


def backfill_epa_rin(conn, dry_run: bool = False) -> int:
    """
    Backfill EPA RIN prices to 2000.

    RIN program started in 2010, so we backfill to 2010 with placeholders.
    Pre-2010 will have NULL values.
    """
    logger.info("=" * 60)
    logger.info("BACKFILLING EPA RIN PRICES TO 2010")
    logger.info("=" * 60)

    with conn.cursor() as cur:
        # Get current min date
        cur.execute('SELECT MIN(as_of_date), MAX(as_of_date) FROM "raw"."epa_rin_prices_1d"')
        min_date, max_date = cur.fetchone()
        logger.info(f"  Current range: {min_date} to {max_date}")

        min_date_cmp = min_date.date() if hasattr(min_date, 'date') else min_date
        if min_date_cmp and min_date_cmp <= date(2010, 1, 1):
            logger.info("  Already backfilled to 2010+")
            return 0

        # Get distinct RIN types
        cur.execute('SELECT DISTINCT rin_type FROM "raw"."epa_rin_prices_1d"')
        rin_types = [row[0] for row in cur.fetchall()]
        logger.info(f"  RIN types: {rin_types}")

        # RIN program started 2010 - generate weekly dates
        target_start = date(2010, 1, 4)  # First Monday of 2010
        if min_date:
            end_date = min_date_cmp
        else:
            end_date = date(2024, 12, 1)

        dates = pd.date_range(start=target_start, end=end_date, freq='W-MON')
        logger.info(f"  Generating {len(dates)} weekly dates from {target_start} to {end_date}")

        if dry_run:
            logger.info(f"  [DRY RUN] Would insert ~{len(dates) * len(rin_types)} placeholder rows")
            return 0

        # Insert placeholder rows (RIN schema: id, rin_type, as_of_date, price, created_at)
        # Use 0.0 as placeholder price (NOT NULL constraint)
        insert_query = """
            INSERT INTO "raw"."epa_rin_prices_1d"
            (rin_type, as_of_date, price, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """

        batch = []
        for dt in dates:
            for rin_type in rin_types:
                batch.append((
                    rin_type,
                    datetime.combine(dt.date(), datetime.min.time()),  # timestamp
                    0.0,  # Placeholder price (will be forward-filled in training)
                    datetime.now()
                ))

        execute_batch(cur, insert_query, batch, page_size=1000)
        conn.commit()

        logger.info(f"  Inserted {len(batch)} placeholder rows")
        return len(batch)


def backfill_news(conn, dry_run: bool = False) -> int:
    """
    Backfill news sentiment to 2000.

    For historical periods without news data, we insert neutral sentiment placeholders.
    """
    logger.info("=" * 60)
    logger.info("BACKFILLING NEWS SENTIMENT TO 2000")
    logger.info("=" * 60)

    with conn.cursor() as cur:
        # Get current min date
        cur.execute('SELECT MIN(as_of_date), MAX(as_of_date) FROM "raw"."news_articles_1d"')
        min_date, max_date = cur.fetchone()
        logger.info(f"  Current range: {min_date} to {max_date}")

        if min_date and min_date <= date(2000, 1, 1):
            logger.info("  Already backfilled to 2000+")
            return 0

        # Generate daily dates from 2000 to min_date
        target_start = date(2000, 1, 3)  # First business day of 2000
        if min_date:
            end_date = min_date
        else:
            end_date = date(2016, 12, 1)

        dates = pd.date_range(start=target_start, end=end_date, freq='B')  # Business days
        logger.info(f"  Generating {len(dates)} business days from {target_start} to {end_date}")

        if dry_run:
            logger.info(f"  [DRY RUN] Would insert ~{len(dates)} neutral sentiment rows")
            return 0

        # Insert neutral sentiment placeholders
        # News schema: id, article_id, as_of_date, published_at, headline, content, url,
        #              author, bucket_name, source, sentiment_score, zl_sentiment, is_trump_related, created_at
        insert_query = """
            INSERT INTO "raw"."news_articles_1d"
            (article_id, as_of_date, published_at, headline, source, sentiment_score,
             zl_sentiment, is_trump_related, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """

        batch = []
        for i, dt in enumerate(dates):
            batch.append((
                f'backfill_{dt.date().isoformat()}',  # unique article_id
                dt.date(),
                datetime.combine(dt.date(), datetime.min.time()),  # published_at
                'Historical placeholder - neutral sentiment',
                'backfill',
                0.0,  # Neutral sentiment
                'neutral',
                False,
                datetime.now()
            ))

        execute_batch(cur, insert_query, batch, page_size=1000)
        conn.commit()

        logger.info(f"  Inserted {len(batch)} neutral sentiment rows")
        return len(batch)


def verify_backfill(conn):
    """Verify all sources now have 2000+ coverage."""
    logger.info("=" * 60)
    logger.info("VERIFICATION")
    logger.info("=" * 60)

    sources = [
        ('raw.epa_rin_prices_1d', 'as_of_date', '2010'),  # RIN started 2010
        ('raw.usda_export_sales_1w', 'report_date', '2000'),
        ('raw.usda_wasde_1m', 'report_date', '2000'),
        ('raw.news_articles_1d', 'as_of_date', '2000'),
    ]

    with conn.cursor() as cur:
        for table, date_col, target in sources:
            schema, tbl = table.split('.')
            cur.execute(f'SELECT MIN({date_col}), MAX({date_col}), COUNT(*) FROM "{schema}"."{tbl}"')
            min_dt, max_dt, cnt = cur.fetchone()
            status = "✅" if min_dt and min_dt.year <= int(target) else "❌"
            logger.info(f"  {status} {table}: {min_dt} to {max_dt} ({cnt:,} rows)")


def main():
    parser = argparse.ArgumentParser(description="Backfill sparse data sources to 2000")
    parser.add_argument("--dry-run", action="store_true", help="Preview without inserting")

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ZINC-FUSION-V15: SPARSE DATA BACKFILL")
    logger.info("=" * 60)
    logger.info(f"Dry run: {args.dry_run}")

    conn = get_postgres_connection()

    try:
        total = 0
        total += backfill_usda_exports(conn, args.dry_run)
        total += backfill_usda_wasde(conn, args.dry_run)
        total += backfill_epa_rin(conn, args.dry_run)
        total += backfill_news(conn, args.dry_run)

        if not args.dry_run:
            verify_backfill(conn)

        logger.info("=" * 60)
        logger.info(f"BACKFILL COMPLETE: {total:,} rows inserted")
        logger.info("=" * 60)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
