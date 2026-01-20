#!/usr/bin/env python3
"""
ZINC-FUSION-V15: CFTC COT Historical Backfill

Downloads and loads CFTC Commitment of Traders (Disaggregated Futures)
historical data from 2006-2016 and 2017-present.

Data Source: https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalViewable/index.htm

Usage:
    python scripts/backfill_cftc_cot.py --dry-run
    python scripts/backfill_cftc_cot.py
"""

import os
import sys
import logging
import argparse
import io
import zipfile
from datetime import datetime
from typing import Dict, List, Optional

import requests
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

# CFTC Contract Market Code to Symbol mapping
# These match the symbols used in raw.cftc_cot_1w
CFTC_CODE_TO_SYMBOL = {
    '001602': 'ZW',   # Wheat SRW (W)
    '001612': 'KE',   # Wheat HRW (KC)
    '001626': 'MWE',  # Wheat HRSpring (Minneapolis)
    '002602': 'ZC',   # Corn
    '005602': 'ZS',   # Soybeans
    '007601': 'ZL',   # Soybean Oil
    '026603': 'ZM',   # Soybean Meal
    '023651': 'NG',   # Natural Gas
    '054642': 'HE',   # Lean Hogs
    '057642': 'LE',   # Live Cattle
    '061641': 'GF',   # Feeder Cattle
    '067651': 'CL',   # Crude Oil WTI
    '084691': 'SI',   # Silver
    '085692': 'HG',   # Copper
    '088691': 'GC',   # Gold
    '111659': 'PL',   # Platinum
    '075651': 'HO',   # Heating Oil
    '111659': 'PA',   # Palladium
}

# Historical data URLs
CFTC_URLS = {
    '2006-2016': 'https://www.cftc.gov/files/dea/history/fut_disagg_txt_hist_2006_2016.zip',
}

# Also fetch individual years from 2017 onwards
for year in range(2017, datetime.now().year + 1):
    CFTC_URLS[str(year)] = f'https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip'


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def download_cftc_data(url: str) -> Optional[pd.DataFrame]:
    """Download and parse CFTC data from a URL."""
    logger.info(f"  Downloading: {url}")

    try:
        response = requests.get(url, timeout=120)

        if response.status_code == 404:
            logger.warning(f"  Not found: {url}")
            return None

        response.raise_for_status()
        logger.info(f"    Downloaded: {len(response.content) / 1e6:.1f} MB")

        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            for filename in z.namelist():
                if filename.endswith('.txt'):
                    with z.open(filename) as f:
                        df = pd.read_csv(f, low_memory=False)
                        logger.info(f"    Rows: {len(df):,}")
                        return df

    except Exception as e:
        logger.error(f"  Error downloading {url}: {e}")
        return None

    return None


def transform_cftc_data(df: pd.DataFrame) -> pd.DataFrame:
    """Transform CFTC raw data to match cftc_cot_1w schema."""

    # Filter to contracts we care about
    df = df[df['CFTC_Contract_Market_Code'].astype(str).isin(CFTC_CODE_TO_SYMBOL.keys())].copy()

    if len(df) == 0:
        return pd.DataFrame()

    # Map contract codes to symbols
    df['symbol'] = df['CFTC_Contract_Market_Code'].astype(str).map(CFTC_CODE_TO_SYMBOL)

    # Parse report date
    df['report_date'] = pd.to_datetime(df['Report_Date_as_YYYY-MM-DD']).dt.date

    # Rename columns to match schema
    column_map = {
        'Open_Interest_All': 'open_interest',
        'Prod_Merc_Positions_Long_All': 'prod_merc_long',
        'Prod_Merc_Positions_Short_All': 'prod_merc_short',
        'Swap_Positions_Long_All': 'swap_long',
        'Swap__Positions_Short_All': 'swap_short',  # Note: double underscore in source
        'M_Money_Positions_Long_All': 'managed_money_long',
        'M_Money_Positions_Short_All': 'managed_money_short',
        'Other_Rept_Positions_Long_All': 'other_rept_long',
        'Other_Rept_Positions_Short_All': 'other_rept_short',
        'NonRept_Positions_Long_All': 'nonrept_long',
        'NonRept_Positions_Short_All': 'nonrept_short',
    }

    # Select and rename columns
    result = df[['report_date', 'symbol'] + list(column_map.keys())].copy()
    result = result.rename(columns=column_map)

    # Calculate net positions
    result['prod_merc_net'] = result['prod_merc_long'] - result['prod_merc_short']
    result['swap_net'] = result['swap_long'] - result['swap_short']
    result['managed_money_net'] = result['managed_money_long'] - result['managed_money_short']
    result['other_rept_net'] = result['other_rept_long'] - result['other_rept_short']
    result['nonrept_net'] = result['nonrept_long'] - result['nonrept_short']

    # Calculate percent of OI
    result['managed_money_net_pct_oi'] = (result['managed_money_net'] / result['open_interest']) * 100
    result['prod_merc_net_pct_oi'] = (result['prod_merc_net'] / result['open_interest']) * 100

    # Handle infinities/NaNs
    result['managed_money_net_pct_oi'] = result['managed_money_net_pct_oi'].replace([float('inf'), float('-inf')], None)
    result['prod_merc_net_pct_oi'] = result['prod_merc_net_pct_oi'].replace([float('inf'), float('-inf')], None)

    return result


def load_to_postgres(conn, df: pd.DataFrame, dry_run: bool = False) -> int:
    """Load data to raw.cftc_cot_1w table."""
    if df.empty:
        return 0

    if dry_run:
        logger.info(f"  [DRY RUN] Would insert {len(df):,} rows")
        return 0

    insert_query = """
        INSERT INTO "raw"."cftc_cot_1w"
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
            prod_merc_net = EXCLUDED.prod_merc_net,
            prod_merc_net_pct_oi = EXCLUDED.prod_merc_net_pct_oi
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
        batch.append((
            row['report_date'],
            row['symbol'],
            safe_int(row['open_interest']),
            safe_int(row['prod_merc_long']),
            safe_int(row['prod_merc_short']),
            safe_int(row['swap_long']),
            safe_int(row['swap_short']),
            safe_int(row['managed_money_long']),
            safe_int(row['managed_money_short']),
            safe_int(row['other_rept_long']),
            safe_int(row['other_rept_short']),
            safe_int(row['nonrept_long']),
            safe_int(row['nonrept_short']),
            safe_int(row['prod_merc_net']),
            safe_int(row['swap_net']),
            safe_int(row['managed_money_net']),
            safe_int(row['other_rept_net']),
            safe_int(row['nonrept_net']),
            safe_float(row['managed_money_net_pct_oi']),
            safe_float(row['prod_merc_net_pct_oi']),
            'cftc_backfill',
            datetime.now()
        ))

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    return len(batch)


def verify_backfill(conn):
    """Verify the backfill results."""
    logger.info("\n" + "=" * 60)
    logger.info("VERIFICATION")
    logger.info("=" * 60)

    with conn.cursor() as cur:
        cur.execute('''
            SELECT MIN(report_date), MAX(report_date), COUNT(*), COUNT(DISTINCT symbol)
            FROM "raw"."cftc_cot_1w"
        ''')
        min_dt, max_dt, cnt, symbols = cur.fetchone()
        logger.info(f"  Total: {cnt:,} rows, {symbols} symbols")
        logger.info(f"  Date range: {min_dt} to {max_dt}")

        # Check by year
        cur.execute('''
            SELECT EXTRACT(YEAR FROM report_date) as year, COUNT(*)
            FROM "raw"."cftc_cot_1w"
            GROUP BY year
            ORDER BY year
        ''')
        logger.info("\n  Rows by year:")
        for year, count in cur.fetchall():
            logger.info(f"    {int(year)}: {count:,}")


def main():
    parser = argparse.ArgumentParser(description="Backfill CFTC COT historical data")
    parser.add_argument("--dry-run", action="store_true", help="Preview without inserting")

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ZINC-FUSION-V15: CFTC COT Historical Backfill")
    logger.info("=" * 60)
    logger.info(f"Dry run: {args.dry_run}")

    conn = get_postgres_connection()

    try:
        total_rows = 0

        for period, url in CFTC_URLS.items():
            logger.info(f"\n--- {period} ---")

            df_raw = download_cftc_data(url)

            if df_raw is not None and len(df_raw) > 0:
                df_transformed = transform_cftc_data(df_raw)

                if len(df_transformed) > 0:
                    logger.info(f"  Transformed: {len(df_transformed):,} rows")
                    logger.info(f"  Symbols: {df_transformed['symbol'].unique().tolist()}")
                    logger.info(f"  Date range: {df_transformed['report_date'].min()} to {df_transformed['report_date'].max()}")

                    rows = load_to_postgres(conn, df_transformed, args.dry_run)
                    total_rows += rows if rows else len(df_transformed)

        if not args.dry_run:
            verify_backfill(conn)

        logger.info("\n" + "=" * 60)
        logger.info(f"BACKFILL COMPLETE: {total_rows:,} rows")
        logger.info("=" * 60)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
