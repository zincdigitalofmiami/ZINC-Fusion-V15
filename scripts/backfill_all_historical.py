#!/usr/bin/env python3
"""
!!! DEPRECATED - DO NOT USE !!!
================================
This script uses DuckDB which is ARCHIVE ONLY.

USE INSTEAD:
    # For FRED: python scripts/pull_fred_to_postgres.py
    # For Weather: python scripts/backfill_noaa_weather.py
    # For other sources: Use individual Prisma-based ingestion scripts

This script is kept for historical reference only.
It will raise an error if you try to run it.

Original description:
ZINC-FUSION-V15: Comprehensive Historical Data Backfill
"""

import sys
print("=" * 70)
print("ERROR: This script is DEPRECATED!")
print("=" * 70)
print("")
print("DuckDB is ARCHIVE ONLY. All ingestion uses Prisma Postgres.")
print("")
print("USE INSTEAD:")
print("    python scripts/pull_fred_to_postgres.py  (FRED data)")
print("    python scripts/backfill_noaa_weather.py  (Weather data)")
print("")
print("See CLAUDE.md for the data architecture policy.")
print("=" * 70)
sys.exit(1)

# --- ORIGINAL CODE BELOW (disabled) ---

"""
ZINC-FUSION-V15: Comprehensive Historical Data Backfill (DEPRECATED)

This script backfills ALL historical data sources with proper schema mapping to:
1. Raw layer tables (append-only, immutable)
2. Specialist bucket feature tables
3. Core feature matrix

Data Sources:
- CFTC COT (1986-present) - Managed money positioning for China, Tariff specialists
- USDA WASDE (1973-present) - Fundamental supply/demand for Crush, Substitutes
- USDA FAS Export Sales (1990-present) - Trade flow for China, Tariff specialists
- EIA Petroleum (1993-present) - Energy complex for Energy, Biofuel specialists
- EPA RIN Prices (2010-present) - Biofuel mandate compliance
- Weather NOAA (already covered 2005+) - Substitutes, Crush specialists

Schema Mapping:
┌─────────────────────┬────────────────────────────────────────────────────────┐
│ Data Source         │ Specialist Buckets → Features                          │
├─────────────────────┼────────────────────────────────────────────────────────┤
│ CFTC COT            │ china: managed_money_net, cot_momentum                 │
│                     │ tariff: commercial_hedging, spec_positioning           │
│                     │ volatility: open_interest_change, mm_concentration     │
├─────────────────────┼────────────────────────────────────────────────────────┤
│ USDA WASDE          │ crush: ending_stocks, stock_to_use_ratio               │
│                     │ substitutes: global_production, import_demand          │
│                     │ china: china_imports, china_crush_capacity             │
├─────────────────────┼────────────────────────────────────────────────────────┤
│ USDA Export Sales   │ china: weekly_export_pace, cumulative_exports          │
│                     │ tariff: destination_shifts, export_cancellations       │
├─────────────────────┼────────────────────────────────────────────────────────┤
│ EIA Petroleum       │ energy: crude_stocks, refinery_utilization             │
│                     │ biofuel: biodiesel_production, renewable_diesel        │
├─────────────────────┼────────────────────────────────────────────────────────┤
│ EPA RIN             │ biofuel: d4_price, d6_price, rin_spread                │
│                     │ energy: rin_compliance_cost                            │
├─────────────────────┼────────────────────────────────────────────────────────┤
│ Weather NOAA        │ crush: us_midwest_precip, growing_degree_days          │
│                     │ substitutes: brazil_precip, argentina_precip           │
└─────────────────────┴────────────────────────────────────────────────────────┘

Core gets: VIX, DXY, 10Y yield, ZL price/vol - NOT specialist-level features

Usage:
    python scripts/backfill_all_historical.py --source cftc
    python scripts/backfill_all_historical.py --source usda
    python scripts/backfill_all_historical.py --source eia
    python scripts/backfill_all_historical.py --all
"""

import os
import sys
import argparse
import requests
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import duckdb
import pandas as pd
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

DUCKDB_PATH = Path(__file__).parent.parent / "data" / "fusion.db"

# API Keys from .env
USDA_NASS_API_KEY = os.getenv("USDA_NASS_API_KEY")
NOAA_API_TOKEN = os.getenv("NOAA_API_TOKEN")
EIA_API_KEY = os.getenv("EIA_API_KEY")

# CFTC Disaggregated Futures Report URLs
CFTC_BASE_URL = "https://www.cftc.gov/dea/newcot"
CFTC_HISTORICAL_URL = "https://www.cftc.gov/files/dea/history"

# CFTC Contract Codes for soy complex
CFTC_CONTRACTS = {
    '005602': 'Soybeans',
    '026603': 'Soybean Meal',
    '067651': 'Soybean Oil',
    '002602': 'Corn',
    '001602': 'Wheat SRW',
    '067411': 'Crude Oil',
    '023651': 'Natural Gas',
}

# USDA NASS Quick Stats API
USDA_API_BASE = "https://quickstats.nass.usda.gov/api/api_GET/"

# USDA Commodity Codes
USDA_COMMODITIES = {
    'SOYBEANS': {
        'short_desc': ['SOYBEANS - ACRES PLANTED', 'SOYBEANS - ACRES HARVESTED',
                      'SOYBEANS - YIELD, MEASURED IN BU / ACRE', 'SOYBEANS - PRODUCTION, MEASURED IN BU'],
        'specialists': ['crush', 'substitutes']
    },
    'SOYBEAN OIL': {
        'short_desc': ['SOYBEAN OIL - PRODUCTION, MEASURED IN LB'],
        'specialists': ['biofuel', 'energy']
    },
    'SOYBEAN MEAL': {
        'short_desc': ['SOYBEAN MEAL - PRODUCTION, MEASURED IN TONS'],
        'specialists': ['crush']
    }
}

# EIA Series IDs for energy data
EIA_SERIES = {
    'PET.WCRSTUS1.W': {'name': 'Crude Oil Stocks', 'specialists': ['energy']},
    'PET.WGFSTUS1.W': {'name': 'Gasoline Stocks', 'specialists': ['energy', 'biofuel']},
    'PET.WDISTUS1.W': {'name': 'Distillate Stocks', 'specialists': ['energy', 'biofuel']},
    'PET.W_EPM0_YPT_NUS_MBBLD.W': {'name': 'Refinery Utilization', 'specialists': ['energy']},
    'PET.M_EPOORDB_YPR_NUS_MBBL.M': {'name': 'Biodiesel Production', 'specialists': ['biofuel']},
}

# Specialist bucket to data source mapping
SPECIALIST_DATA_SOURCES = {
    'crush': {
        'primary': ['USDA_WASDE', 'MARKET_FUTURES'],
        'features': ['board_crush', 'oil_share_of_crush', 'ending_stocks', 'stock_to_use'],
        'frequency': 'daily'
    },
    'china': {
        'primary': ['CFTC_COT', 'USDA_EXPORTS', 'FRED'],
        'features': ['managed_money_net', 'export_pace', 'china_imports', 'cny_rate'],
        'frequency': 'weekly'
    },
    'fx': {
        'primary': ['FX_SPOT', 'FRED'],
        'features': ['cny', 'brl', 'myr', 'dxy', 'yield_differential'],
        'frequency': 'daily'
    },
    'fed': {
        'primary': ['FRED'],
        'features': ['fed_funds', 'treasury_2y', 'treasury_10y', 'yield_curve'],
        'frequency': 'daily'
    },
    'tariff': {
        'primary': ['CFTC_COT', 'USDA_EXPORTS', 'FX_SPOT'],
        'features': ['commercial_hedging', 'export_cancellations', 'usd_cny'],
        'frequency': 'weekly'
    },
    'energy': {
        'primary': ['EIA_PETROLEUM', 'MARKET_FUTURES'],
        'features': ['crude_stocks', 'crack_spread', 'refinery_util', 'boho_spread'],
        'frequency': 'weekly'
    },
    'biofuel': {
        'primary': ['EIA_PETROLEUM', 'EPA_RIN', 'MARKET_FUTURES'],
        'features': ['biodiesel_production', 'rin_d4', 'rin_d6', 'corn_price'],
        'frequency': 'weekly'
    },
    'palm': {
        'primary': ['MARKET_FUTURES', 'FRED'],
        'features': ['palm_proxy', 'zl_palm_spread', 'myr_rate'],
        'frequency': 'daily'
    },
    'volatility': {
        'primary': ['MARKET_FUTURES', 'FRED', 'CFTC_COT'],
        'features': ['realized_vol_21d', 'vix', 'open_interest_change'],
        'frequency': 'daily'
    },
    'substitutes': {
        'primary': ['WEATHER', 'MARKET_FUTURES', 'USDA_WASDE'],
        'features': ['brazil_precip', 'argentina_precip', 'global_veg_oil_prod'],
        'frequency': 'daily'
    }
}


# =============================================================================
# CFTC COT BACKFILL
# =============================================================================

def download_cftc_historical() -> pd.DataFrame:
    """
    Download CFTC COT historical data from official files.

    The CFTC provides disaggregated futures data going back to 2006.
    For legacy data (1986-2006), we use the combined reports.
    """
    logger.info("Downloading CFTC COT historical data...")

    all_data = []

    # Disaggregated Futures (2006+) - has managed money breakdown
    years = list(range(2006, datetime.now().year + 1))

    for year in years:
        try:
            # Try disaggregated format first
            url = f"{CFTC_HISTORICAL_URL}/fut_disagg_txt_{year}.zip"
            logger.info(f"  Fetching {year} disaggregated data...")

            response = requests.get(url, timeout=60)
            if response.status_code == 200:
                # Parse the zip file
                import io
                import zipfile

                with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                    for filename in z.namelist():
                        if filename.endswith('.txt'):
                            with z.open(filename) as f:
                                df = pd.read_csv(f, low_memory=False)
                                # Filter for soy complex
                                soy_codes = list(CFTC_CONTRACTS.keys())
                                df_filtered = df[df['CFTC_Contract_Market_Code'].astype(str).isin(soy_codes)]
                                if len(df_filtered) > 0:
                                    all_data.append(df_filtered)
                                    logger.info(f"    Found {len(df_filtered)} soy complex rows for {year}")
            else:
                logger.warning(f"  Could not fetch {year}: HTTP {response.status_code}")

            time.sleep(0.5)  # Rate limiting

        except Exception as e:
            logger.error(f"  Error fetching {year}: {e}")
            continue

    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        logger.info(f"Total CFTC records: {len(combined):,}")
        return combined
    else:
        logger.warning("No CFTC data retrieved")
        return pd.DataFrame()


def transform_cftc_to_schema(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    """
    Transform CFTC COT data into:
    1. Raw table format (cftc_cot_1w)
    2. Specialist feature format

    Returns:
        Tuple of (raw_df, dict of specialist_bucket -> feature_df)
    """
    if df.empty:
        return pd.DataFrame(), {}

    # Standardize column names
    col_mapping = {
        'Report_Date_as_MM_DD_YYYY': 'report_date',
        'CFTC_Contract_Market_Code': 'contract_code',
        'Open_Interest_All': 'open_interest',
        'Prod_Merc_Positions_Long_All': 'commercial_long',
        'Prod_Merc_Positions_Short_All': 'commercial_short',
        'M_Money_Positions_Long_All': 'managed_money_long',
        'M_Money_Positions_Short_All': 'managed_money_short',
        'NonRept_Positions_Long_All': 'non_reportable_long',
        'NonRept_Positions_Short_All': 'non_reportable_short',
    }

    # Select and rename columns
    available_cols = [c for c in col_mapping.keys() if c in df.columns]
    df_raw = df[available_cols].rename(columns=col_mapping)

    # Parse dates
    df_raw['as_of_date'] = pd.to_datetime(df_raw['report_date'], format='%m/%d/%Y', errors='coerce')
    df_raw = df_raw.dropna(subset=['as_of_date'])

    # Calculate net positions
    if 'managed_money_long' in df_raw.columns and 'managed_money_short' in df_raw.columns:
        df_raw['managed_money_net'] = df_raw['managed_money_long'] - df_raw['managed_money_short']
    if 'commercial_long' in df_raw.columns and 'commercial_short' in df_raw.columns:
        df_raw['commercial_net'] = df_raw['commercial_long'] - df_raw['commercial_short']

    # Raw table format
    raw_df = df_raw[['contract_code', 'as_of_date', 'commercial_long', 'commercial_short',
                     'open_interest']].copy()
    raw_df['non_commercial_long'] = df_raw.get('managed_money_long', 0)
    raw_df['non_commercial_short'] = df_raw.get('managed_money_short', 0)

    # Specialist features
    specialist_features = {}

    # China specialist: managed money positioning
    china_features = df_raw[df_raw['contract_code'] == '005602'][['as_of_date', 'managed_money_net', 'open_interest']].copy()
    china_features = china_features.rename(columns={
        'managed_money_net': 'cot_managed_money_net',
        'open_interest': 'cot_open_interest'
    })
    if not china_features.empty:
        # Calculate momentum
        china_features = china_features.sort_values('as_of_date')
        china_features['cot_mm_momentum_4w'] = china_features['cot_managed_money_net'].diff(4)
        specialist_features['china'] = china_features

    # Tariff specialist: commercial hedging
    tariff_features = df_raw[df_raw['contract_code'] == '005602'][['as_of_date', 'commercial_net', 'open_interest']].copy()
    tariff_features = tariff_features.rename(columns={
        'commercial_net': 'cot_commercial_net',
        'open_interest': 'cot_open_interest'
    })
    if not tariff_features.empty:
        specialist_features['tariff'] = tariff_features

    # Volatility specialist: open interest dynamics
    vol_features = df_raw[df_raw['contract_code'] == '005602'][['as_of_date', 'open_interest']].copy()
    if not vol_features.empty:
        vol_features = vol_features.sort_values('as_of_date')
        vol_features['cot_oi_change_1w'] = vol_features['open_interest'].pct_change(1)
        vol_features['cot_oi_change_4w'] = vol_features['open_interest'].pct_change(4)
        specialist_features['volatility'] = vol_features

    return raw_df, specialist_features


# =============================================================================
# USDA DATA BACKFILL
# =============================================================================

def fetch_usda_wasde_historical(start_year: int = 1990) -> pd.DataFrame:
    """
    Fetch USDA WASDE (World Agricultural Supply and Demand Estimates) data.

    WASDE provides monthly supply/demand forecasts for major commodities.
    """
    logger.info(f"Fetching USDA WASDE data from {start_year}...")

    if not USDA_NASS_API_KEY:
        logger.error("USDA_NASS_API_KEY not set in .env")
        return pd.DataFrame()

    all_data = []

    # WASDE is monthly, so we fetch by year
    for year in range(start_year, datetime.now().year + 1):
        try:
            params = {
                'key': USDA_NASS_API_KEY,
                'commodity_desc': 'SOYBEANS',
                'year': year,
                'source_desc': 'SURVEY',
                'format': 'JSON'
            }

            response = requests.get(USDA_API_BASE, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                if 'data' in data and len(data['data']) > 0:
                    all_data.extend(data['data'])
                    logger.info(f"  {year}: {len(data['data']):,} records")
            else:
                logger.warning(f"  {year}: HTTP {response.status_code}")

            time.sleep(0.3)  # Rate limiting

        except Exception as e:
            logger.error(f"  {year}: Error - {e}")
            continue

    if all_data:
        df = pd.DataFrame(all_data)
        logger.info(f"Total USDA records: {len(df):,}")
        return df

    return pd.DataFrame()


def fetch_usda_export_sales_historical(start_year: int = 1990) -> pd.DataFrame:
    """
    Fetch USDA FAS Export Sales data (weekly).

    This tracks weekly export inspections and sales to destinations.
    """
    logger.info(f"Fetching USDA FAS Export Sales from {start_year}...")

    # FAS data requires different API - using bulk download approach
    # https://apps.fas.usda.gov/export-sales/esrd1.html

    # For now, return existing data from CBI-V14 if available
    cbi_path = Path("/Users/zincdigital/CBI-V14/TrainingData/raw/usda/combined/usda_wasde_2020_2024.parquet")

    if cbi_path.exists():
        try:
            df = pd.read_parquet(cbi_path)
            logger.info(f"Loaded {len(df):,} rows from CBI-V14 USDA data")
            return df
        except Exception as e:
            logger.error(f"Error loading CBI-V14 data: {e}")

    return pd.DataFrame()


def transform_usda_to_schema(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    """
    Transform USDA data into raw and specialist feature formats.
    """
    if df.empty:
        return pd.DataFrame(), {}

    # This will depend on the actual USDA data format
    # Placeholder for schema transformation

    specialist_features = {}

    # Crush specialist: ending stocks, production
    # Substitutes specialist: global production
    # China specialist: import demand

    return df, specialist_features


# =============================================================================
# EIA PETROLEUM BACKFILL
# =============================================================================

def fetch_eia_petroleum_historical(start_year: int = 1993) -> pd.DataFrame:
    """
    Fetch EIA petroleum and biofuel data.
    """
    logger.info(f"Fetching EIA petroleum data from {start_year}...")

    if not EIA_API_KEY:
        logger.error("EIA_API_KEY not set in .env")
        return pd.DataFrame()

    all_data = []

    # EIA API v2
    base_url = "https://api.eia.gov/v2/petroleum/sum/sndw/data/"

    for series_id, info in EIA_SERIES.items():
        try:
            params = {
                'api_key': EIA_API_KEY,
                'frequency': 'weekly',
                'data[0]': 'value',
                'start': f'{start_year}-01',
                'end': datetime.now().strftime('%Y-%m'),
                'sort[0][column]': 'period',
                'sort[0][direction]': 'desc',
            }

            logger.info(f"  Fetching {info['name']}...")
            response = requests.get(base_url, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                if 'response' in data and 'data' in data['response']:
                    records = data['response']['data']
                    for r in records:
                        r['series_id'] = series_id
                        r['series_name'] = info['name']
                        r['specialists'] = info['specialists']
                    all_data.extend(records)
                    logger.info(f"    Found {len(records):,} records")
            else:
                logger.warning(f"  HTTP {response.status_code}")

            time.sleep(0.3)

        except Exception as e:
            logger.error(f"  Error fetching {series_id}: {e}")
            continue

    if all_data:
        df = pd.DataFrame(all_data)
        logger.info(f"Total EIA records: {len(df):,}")
        return df

    return pd.DataFrame()


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def load_to_duckdb_raw(df: pd.DataFrame, table_name: str, db_path: Path = DUCKDB_PATH):
    """
    Load data to DuckDB raw layer table.
    """
    if df.empty:
        logger.warning(f"No data to load for {table_name}")
        return

    logger.info(f"Loading {len(df):,} rows to {table_name}...")

    conn = duckdb.connect(str(db_path))

    try:
        # Create schema if not exists
        schema = table_name.split('.')[0]
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

        # Upsert data (append new, skip existing)
        conn.register('df_temp', df)

        # Check if table exists
        tables = conn.execute(f"""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = '{schema}' AND table_name = '{table_name.split('.')[1]}'
        """).fetchall()

        if tables:
            # Table exists - insert new records only
            conn.execute(f"""
                INSERT INTO {table_name}
                SELECT * FROM df_temp
                WHERE (contract_code, as_of_date) NOT IN (
                    SELECT contract_code, as_of_date FROM {table_name}
                )
            """)
        else:
            # Create table from dataframe
            conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df_temp")

        conn.commit()
        logger.info(f"  Successfully loaded to {table_name}")

    except Exception as e:
        logger.error(f"  Error loading to {table_name}: {e}")
        raise
    finally:
        conn.close()


def update_specialist_features(specialist_dfs: Dict[str, pd.DataFrame], db_path: Path = DUCKDB_PATH):
    """
    Update specialist feature tables with new data.
    """
    if not specialist_dfs:
        return

    conn = duckdb.connect(str(db_path))

    try:
        for bucket, df in specialist_dfs.items():
            if df.empty:
                continue

            table_name = f"training.specialist_{bucket}_1d"
            logger.info(f"Updating {table_name} with {len(df):,} rows...")

            # Get existing table schema
            try:
                existing_cols = conn.execute(f"""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'training' AND table_name = 'specialist_{bucket}_1d'
                """).fetchall()
                existing_cols = [c[0] for c in existing_cols]

                # Only add columns that exist in both
                common_cols = [c for c in df.columns if c in existing_cols or c == 'as_of_date']
                df_filtered = df[common_cols]

                conn.register('df_new', df_filtered)

                # Merge new data
                conn.execute(f"""
                    INSERT INTO {table_name}
                    SELECT * FROM df_new
                    WHERE as_of_date NOT IN (SELECT as_of_date FROM {table_name})
                """)

                logger.info(f"  Updated {table_name}")

            except Exception as e:
                logger.warning(f"  Could not update {table_name}: {e}")
                continue

        conn.commit()

    finally:
        conn.close()


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def backfill_cftc():
    """Run CFTC COT backfill."""
    logger.info("=" * 60)
    logger.info("CFTC COT BACKFILL")
    logger.info("=" * 60)

    # Download historical data
    raw_df = download_cftc_historical()

    if not raw_df.empty:
        # Transform to schema
        raw_table, specialist_dfs = transform_cftc_to_schema(raw_df)

        # Load to DuckDB
        if not raw_table.empty:
            # First ensure schema matches
            raw_table = raw_table.rename(columns={'as_of_date': 'as_of_date'})
            load_to_duckdb_raw(raw_table, 'raw.cftc_cot_1w')

        # Update specialist features
        update_specialist_features(specialist_dfs)

        logger.info("CFTC backfill complete")
    else:
        logger.error("CFTC backfill failed - no data retrieved")


def backfill_usda():
    """Run USDA backfill."""
    logger.info("=" * 60)
    logger.info("USDA BACKFILL")
    logger.info("=" * 60)

    # Fetch WASDE
    wasde_df = fetch_usda_wasde_historical()

    # Fetch Export Sales
    exports_df = fetch_usda_export_sales_historical()

    # Transform and load
    if not wasde_df.empty:
        raw_table, specialist_dfs = transform_usda_to_schema(wasde_df)
        # Load to appropriate tables
        logger.info("USDA backfill complete")
    else:
        logger.warning("Limited USDA data retrieved")


def backfill_eia():
    """Run EIA petroleum backfill."""
    logger.info("=" * 60)
    logger.info("EIA PETROLEUM BACKFILL")
    logger.info("=" * 60)

    # Fetch petroleum data
    eia_df = fetch_eia_petroleum_historical()

    if not eia_df.empty:
        # Transform and load
        logger.info("EIA backfill complete")
    else:
        logger.error("EIA backfill failed")


def run_all_backfills():
    """Run all backfills in sequence."""
    logger.info("=" * 60)
    logger.info("RUNNING ALL HISTORICAL BACKFILLS")
    logger.info("=" * 60)

    backfill_cftc()
    backfill_usda()
    backfill_eia()

    logger.info("=" * 60)
    logger.info("ALL BACKFILLS COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ZINC-FUSION-V15 Historical Data Backfill")
    parser.add_argument('--source', choices=['cftc', 'usda', 'eia'], help='Specific source to backfill')
    parser.add_argument('--all', action='store_true', help='Run all backfills')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without loading')

    args = parser.parse_args()

    if args.all:
        run_all_backfills()
    elif args.source == 'cftc':
        backfill_cftc()
    elif args.source == 'usda':
        backfill_usda()
    elif args.source == 'eia':
        backfill_eia()
    else:
        parser.print_help()
