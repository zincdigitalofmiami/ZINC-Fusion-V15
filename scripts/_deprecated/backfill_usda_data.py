#!/usr/bin/env python3
"""
ZINC-FUSION-V15: USDA NASS Quick Stats Backfill

Fetches historical USDA data from the NASS Quick Stats API for
soybean-related commodities relevant to ZL forecasting.

DATA CATEGORIES:
1. Crop Progress - Weekly soybean planting/emergence/harvest progress
2. Crop Condition - Weekly condition ratings (Excellent to Very Poor)
3. Production - Acreage, yield, production estimates
4. Stocks - Quarterly/Annual stocks reports
5. Crush - Soybean oil and meal crush data

API: https://quickstats.nass.usda.gov/api
Docs: https://www.nass.usda.gov/developer/index.php

SETUP:
1. Get free API key from: https://quickstats.nass.usda.gov/api
2. Set USDA_NASS_API_KEY in .env

Usage:
    python scripts/backfill_usda_data.py --dry-run
    python scripts/backfill_usda_data.py --category crop_progress --start-year 2010
    python scripts/backfill_usda_data.py --all --start-year 2010
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests
import pandas as pd
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

# USDA NASS API configuration
NASS_BASE_URL = "https://quickstats.nass.usda.gov/api/api_GET"

# Rate limiting: Be respectful of the API
RATE_LIMIT_DELAY = 1.0  # seconds between requests

# ═══════════════════════════════════════════════════════════════════════════════
# QUERY CONFIGURATIONS
# ═══════════════════════════════════════════════════════════════════════════════

USDA_QUERIES = {
    'crop_progress': {
        'description': 'Weekly soybean planting/emergence/harvest progress',
        'table': 'usda_crop_progress',
        'params': {
            'source_desc': 'SURVEY',
            'sector_desc': 'CROPS',
            'group_desc': 'FIELD CROPS',
            'commodity_desc': 'SOYBEANS',
            'statisticcat_desc': 'PROGRESS',
            'agg_level_desc': 'STATE',
            'freq_desc': 'WEEKLY',
        }
    },
    'crop_condition': {
        'description': 'Weekly soybean condition ratings',
        'table': 'usda_crop_condition',
        'params': {
            'source_desc': 'SURVEY',
            'sector_desc': 'CROPS',
            'group_desc': 'FIELD CROPS',
            'commodity_desc': 'SOYBEANS',
            'statisticcat_desc': 'CONDITION',
            'agg_level_desc': 'STATE',
            'freq_desc': 'WEEKLY',
        }
    },
    'production_acreage': {
        'description': 'Soybean acreage planted/harvested',
        'table': 'usda_production',
        'params': {
            'source_desc': 'SURVEY',
            'sector_desc': 'CROPS',
            'commodity_desc': 'SOYBEANS',
            'statisticcat_desc': 'AREA',
            'agg_level_desc': 'STATE',
        }
    },
    'production_yield': {
        'description': 'Soybean yield per acre',
        'table': 'usda_production',
        'params': {
            'source_desc': 'SURVEY',
            'sector_desc': 'CROPS',
            'commodity_desc': 'SOYBEANS',
            'statisticcat_desc': 'YIELD',
            'agg_level_desc': 'STATE',
        }
    },
    'production_total': {
        'description': 'Soybean total production',
        'table': 'usda_production',
        'params': {
            'source_desc': 'SURVEY',
            'sector_desc': 'CROPS',
            'commodity_desc': 'SOYBEANS',
            'statisticcat_desc': 'PRODUCTION',
            'agg_level_desc': 'STATE',
        }
    },
    'stocks': {
        'description': 'Soybean stocks (quarterly)',
        'table': 'usda_stocks',
        'params': {
            'source_desc': 'SURVEY',
            'sector_desc': 'CROPS',
            'commodity_desc': 'SOYBEANS',
            'statisticcat_desc': 'STOCKS',
            'agg_level_desc': 'NATIONAL',
        }
    },
    'crush_soybeans': {
        'description': 'Soybeans crushed for oil/meal',
        'table': 'usda_crush',
        'params': {
            'source_desc': 'SURVEY',
            'commodity_desc': 'SOYBEANS',
            'statisticcat_desc': 'CRUSH',
        }
    },
    'soybean_oil': {
        'description': 'Soybean oil production & stocks',
        'table': 'usda_soybean_oil',
        'params': {
            'source_desc': 'SURVEY',
            'commodity_desc': 'OIL, SOYBEAN',
        }
    },
    'soybean_meal': {
        'description': 'Soybean meal production & stocks',
        'table': 'usda_soybean_meal',
        'params': {
            'source_desc': 'SURVEY',
            'commodity_desc': 'MEAL, SOYBEAN',
        }
    },
}


def get_nass_api_key() -> str:
    """Get USDA NASS API key from environment."""
    key = os.getenv('USDA_NASS_API_KEY') or os.getenv('NASS_API_KEY')
    if not key:
        raise ValueError(
            "USDA NASS API key not found. "
            "Get free key at: https://quickstats.nass.usda.gov/api "
            "Then set USDA_NASS_API_KEY in .env"
        )
    return key


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def fetch_nass_data(
    api_key: str,
    params: Dict,
    start_year: int,
    end_year: int
) -> Optional[pd.DataFrame]:
    """Fetch data from USDA NASS Quick Stats API."""
    query_params = {
        'key': api_key,
        'year__GE': str(start_year),
        'year__LE': str(end_year),
        'format': 'JSON',
        **params
    }

    try:
        response = requests.get(
            NASS_BASE_URL,
            params=query_params,
            timeout=60
        )

        if response.status_code == 401:
            logger.error("Invalid API key")
            return None

        if response.status_code == 400:
            error = response.json().get('error', {})
            if 'exceeds limit' in str(error):
                logger.warning("Query exceeds 50,000 row limit, need to split")
            logger.error(f"API error: {error}")
            return None

        response.raise_for_status()
        data = response.json()

        if 'data' not in data:
            return None

        df = pd.DataFrame(data['data'])
        return df

    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        return None


def create_crop_progress_table(conn):
    """Create usda_crop_progress table."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usda_crop_progress (
                id SERIAL PRIMARY KEY,
                report_date DATE NOT NULL,
                state VARCHAR(50) NOT NULL,
                commodity VARCHAR(100),
                unit_desc VARCHAR(100),
                short_desc VARCHAR(500),
                value DOUBLE PRECISION,
                week_ending DATE,
                year INT,
                source VARCHAR(50),
                ingested_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(report_date, state, short_desc)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_crop_progress_date ON usda_crop_progress(report_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_crop_progress_state ON usda_crop_progress(state)")
    conn.commit()


def create_crop_condition_table(conn):
    """Create usda_crop_condition table."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usda_crop_condition (
                id SERIAL PRIMARY KEY,
                report_date DATE NOT NULL,
                state VARCHAR(50) NOT NULL,
                commodity VARCHAR(100),
                condition VARCHAR(50),
                value DOUBLE PRECISION,
                week_ending DATE,
                year INT,
                source VARCHAR(50),
                ingested_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(report_date, state, condition)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_crop_condition_date ON usda_crop_condition(report_date)")
    conn.commit()


def create_production_table(conn):
    """Create usda_production table."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usda_production (
                id SERIAL PRIMARY KEY,
                report_date DATE NOT NULL,
                state VARCHAR(50),
                commodity VARCHAR(100),
                statisticcat VARCHAR(100),
                short_desc VARCHAR(500),
                value DOUBLE PRECISION,
                unit_desc VARCHAR(100),
                year INT,
                source VARCHAR(50),
                ingested_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(report_date, state, short_desc)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_production_date ON usda_production(report_date)")
    conn.commit()


def create_stocks_table(conn):
    """Create usda_stocks table."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usda_stocks (
                id SERIAL PRIMARY KEY,
                report_date DATE NOT NULL,
                commodity VARCHAR(100),
                short_desc VARCHAR(500),
                value DOUBLE PRECISION,
                unit_desc VARCHAR(100),
                reference_period VARCHAR(50),
                year INT,
                source VARCHAR(50),
                ingested_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(report_date, short_desc)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stocks_date ON usda_stocks(report_date)")
    conn.commit()


def create_crush_table(conn):
    """Create usda_crush table."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usda_crush (
                id SERIAL PRIMARY KEY,
                report_date DATE NOT NULL,
                commodity VARCHAR(100),
                short_desc VARCHAR(500),
                value DOUBLE PRECISION,
                unit_desc VARCHAR(100),
                reference_period VARCHAR(50),
                year INT,
                source VARCHAR(50),
                ingested_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(report_date, short_desc)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_crush_date ON usda_crush(report_date)")
    conn.commit()


def create_soybean_oil_table(conn):
    """Create usda_soybean_oil table."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usda_soybean_oil (
                id SERIAL PRIMARY KEY,
                report_date DATE NOT NULL,
                statisticcat VARCHAR(100),
                short_desc VARCHAR(500),
                value DOUBLE PRECISION,
                unit_desc VARCHAR(100),
                reference_period VARCHAR(50),
                year INT,
                source VARCHAR(50),
                ingested_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(report_date, short_desc)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_soybean_oil_date ON usda_soybean_oil(report_date)")
    conn.commit()


def create_soybean_meal_table(conn):
    """Create usda_soybean_meal table."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usda_soybean_meal (
                id SERIAL PRIMARY KEY,
                report_date DATE NOT NULL,
                statisticcat VARCHAR(100),
                short_desc VARCHAR(500),
                value DOUBLE PRECISION,
                unit_desc VARCHAR(100),
                reference_period VARCHAR(50),
                year INT,
                source VARCHAR(50),
                ingested_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(report_date, short_desc)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_soybean_meal_date ON usda_soybean_meal(report_date)")
    conn.commit()


TABLE_CREATORS = {
    'usda_crop_progress': create_crop_progress_table,
    'usda_crop_condition': create_crop_condition_table,
    'usda_production': create_production_table,
    'usda_stocks': create_stocks_table,
    'usda_crush': create_crush_table,
    'usda_soybean_oil': create_soybean_oil_table,
    'usda_soybean_meal': create_soybean_meal_table,
}


def parse_value(val) -> Optional[float]:
    """Parse USDA value field (may contain commas, text like 'D')."""
    if pd.isna(val):
        return None
    val_str = str(val).strip()
    if val_str in ['', '(D)', '(NA)', '(S)', '(Z)', '(X)']:
        return None
    try:
        # Remove commas
        return float(val_str.replace(',', ''))
    except:
        return None


def parse_date(row) -> Optional:
    """Parse date from USDA row (uses load_time, reference_period_desc, or year)."""
    # Try load_time first (when data was published)
    if 'load_time' in row and pd.notna(row['load_time']):
        try:
            return pd.to_datetime(row['load_time']).date()
        except:
            pass

    # Try to construct from week_ending if available
    if 'week_ending' in row and pd.notna(row['week_ending']):
        try:
            return pd.to_datetime(row['week_ending']).date()
        except:
            pass

    # Fallback to year + reference period
    year = row.get('year')
    if pd.notna(year):
        return datetime(int(year), 12, 31).date()

    return None


def load_crop_progress(conn, df: pd.DataFrame, dry_run: bool = False) -> int:
    """Load crop progress data."""
    if df is None or len(df) == 0:
        return 0

    if dry_run:
        logger.info(f"    [DRY RUN] Would insert {len(df):,} rows")
        return len(df)

    insert_query = """
        INSERT INTO usda_crop_progress
        (report_date, state, commodity, unit_desc, short_desc, value, week_ending, year, source, ingested_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (report_date, state, short_desc)
        DO UPDATE SET value = EXCLUDED.value
    """

    batch = []
    for _, row in df.iterrows():
        report_date = parse_date(row)
        if not report_date:
            continue

        week_ending = None
        if 'week_ending' in row and pd.notna(row['week_ending']):
            try:
                week_ending = pd.to_datetime(row['week_ending']).date()
            except:
                pass

        batch.append((
            report_date,
            str(row.get('state_name', row.get('state_alpha', 'US'))),
            str(row.get('commodity_desc', 'SOYBEANS')),
            str(row.get('unit_desc', '')),
            str(row.get('short_desc', ''))[:500],
            parse_value(row.get('Value', row.get('value'))),
            week_ending,
            int(row['year']) if pd.notna(row.get('year')) else None,
            'USDA_NASS',
            datetime.now()
        ))

    if batch:
        with conn.cursor() as cur:
            execute_batch(cur, insert_query, batch, page_size=1000)
        conn.commit()

    return len(batch)


def load_generic_usda(conn, df: pd.DataFrame, table: str, dry_run: bool = False) -> int:
    """Generic loader for USDA data."""
    if df is None or len(df) == 0:
        return 0

    if dry_run:
        logger.info(f"    [DRY RUN] Would insert {len(df):,} rows to {table}")
        return len(df)

    # Determine columns based on table
    if table == 'usda_crop_condition':
        return load_crop_condition(conn, df)
    elif table == 'usda_crop_progress':
        return load_crop_progress(conn, df, dry_run=False)

    # Generic insert for production/stocks/crush tables
    insert_query = f"""
        INSERT INTO {table}
        (report_date, short_desc, value, unit_desc, year, source, ingested_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (report_date, short_desc)
        DO UPDATE SET value = EXCLUDED.value
    """

    batch = []
    for _, row in df.iterrows():
        report_date = parse_date(row)
        if not report_date:
            continue

        batch.append((
            report_date,
            str(row.get('short_desc', ''))[:500],
            parse_value(row.get('Value', row.get('value'))),
            str(row.get('unit_desc', '')),
            int(row['year']) if pd.notna(row.get('year')) else None,
            'USDA_NASS',
            datetime.now()
        ))

    if batch:
        with conn.cursor() as cur:
            execute_batch(cur, insert_query, batch, page_size=1000)
        conn.commit()

    return len(batch)


def load_crop_condition(conn, df: pd.DataFrame) -> int:
    """Load crop condition data."""
    if df is None or len(df) == 0:
        return 0

    insert_query = """
        INSERT INTO usda_crop_condition
        (report_date, state, commodity, condition, value, week_ending, year, source, ingested_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (report_date, state, condition)
        DO UPDATE SET value = EXCLUDED.value
    """

    batch = []
    for _, row in df.iterrows():
        report_date = parse_date(row)
        if not report_date:
            continue

        # Extract condition from short_desc (e.g., "SOYBEANS - CONDITION, MEASURED IN PCT EXCELLENT")
        short_desc = str(row.get('short_desc', ''))
        condition = 'UNKNOWN'
        for cond in ['EXCELLENT', 'GOOD', 'FAIR', 'POOR', 'VERY POOR']:
            if cond in short_desc.upper():
                condition = cond
                break

        week_ending = None
        if 'week_ending' in row and pd.notna(row['week_ending']):
            try:
                week_ending = pd.to_datetime(row['week_ending']).date()
            except:
                pass

        batch.append((
            report_date,
            str(row.get('state_name', row.get('state_alpha', 'US'))),
            str(row.get('commodity_desc', 'SOYBEANS')),
            condition,
            parse_value(row.get('Value', row.get('value'))),
            week_ending,
            int(row['year']) if pd.notna(row.get('year')) else None,
            'USDA_NASS',
            datetime.now()
        ))

    if batch:
        with conn.cursor() as cur:
            execute_batch(cur, insert_query, batch, page_size=1000)
        conn.commit()

    return len(batch)


def backfill_category(
    category: str,
    api_key: str,
    start_year: int,
    end_year: int,
    conn,
    dry_run: bool = False
) -> Dict:
    """Backfill a single USDA data category."""
    if category not in USDA_QUERIES:
        return {'status': 'error', 'message': f'Unknown category: {category}'}

    config = USDA_QUERIES[category]
    result = {
        'category': category,
        'description': config['description'],
        'table': config['table'],
        'rows_loaded': 0,
        'status': 'pending'
    }

    logger.info(f"\n--- {config['description']} ---")

    # Create table if needed
    if not dry_run and config['table'] in TABLE_CREATORS:
        TABLE_CREATORS[config['table']](conn)

    # Fetch data
    logger.info(f"  Fetching {start_year}-{end_year}...")
    df = fetch_nass_data(api_key, config['params'], start_year, end_year)

    if df is not None and len(df) > 0:
        logger.info(f"  Retrieved {len(df):,} records")

        rows = load_generic_usda(conn, df, config['table'], dry_run)
        result['rows_loaded'] = rows
        result['status'] = 'success'
        logger.info(f"  Loaded {rows:,} rows")
    else:
        logger.warning(f"  No data returned")
        result['status'] = 'no_data'

    time.sleep(RATE_LIMIT_DELAY)
    return result


def backfill_all(
    start_year: int,
    end_year: int,
    categories: Optional[List[str]] = None,
    dry_run: bool = False
):
    """Backfill all or selected USDA data categories."""
    logger.info("=" * 70)
    logger.info("ZINC-FUSION-V15: USDA NASS Backfill")
    logger.info("=" * 70)
    logger.info(f"Year range: {start_year} to {end_year}")
    logger.info(f"Dry run: {dry_run}")

    try:
        api_key = get_nass_api_key()
    except ValueError as e:
        logger.error(str(e))
        return

    conn = get_postgres_connection()

    try:
        category_list = categories if categories else list(USDA_QUERIES.keys())
        results = []

        for category in category_list:
            result = backfill_category(
                category, api_key, start_year, end_year, conn, dry_run
            )
            results.append(result)

        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("BACKFILL SUMMARY")
        logger.info("=" * 70)

        total_rows = 0
        for r in results:
            logger.info(f"  {r['category']}: {r['rows_loaded']:,} rows ({r['status']})")
            total_rows += r['rows_loaded']

        logger.info(f"\nTotal rows: {total_rows:,}")

        # Verification
        if not dry_run:
            logger.info("\n--- Database Verification ---")
            with conn.cursor() as cur:
                for table in set(c['table'] for c in USDA_QUERIES.values()):
                    try:
                        cur.execute(f"SELECT COUNT(*), MIN(report_date), MAX(report_date) FROM {table}")
                        count, min_date, max_date = cur.fetchone()
                        logger.info(f"  {table}: {count:,} rows ({min_date} to {max_date})")
                    except Exception as e:
                        logger.debug(f"  {table}: {e}")

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill USDA NASS data")
    parser.add_argument("--dry-run", action="store_true", help="Preview without inserting")
    parser.add_argument("--start-year", type=int, default=2010, help="Start year")
    parser.add_argument("--end-year", type=int, default=None, help="End year (default: current)")
    parser.add_argument("--category", type=str, help="Specific category to backfill")
    parser.add_argument("--all", action="store_true", help="Backfill all categories")
    parser.add_argument("--list", action="store_true", help="List available categories")

    args = parser.parse_args()

    if args.list:
        print("\nAvailable USDA Data Categories:")
        print("=" * 70)
        for name, config in USDA_QUERIES.items():
            print(f"  {name:20s} - {config['description']}")
            print(f"                       Table: {config['table']}")
        return

    end_year = args.end_year or datetime.now().year

    if args.category:
        categories = [args.category]
    elif args.all:
        categories = None
    else:
        parser.print_help()
        print("\nSpecify --category <name> or --all")
        return

    backfill_all(args.start_year, end_year, categories, args.dry_run)


if __name__ == "__main__":
    main()
