#!/usr/bin/env python3
"""
ZINC-FUSION-V15: NOAA GHCN-Daily Weather Backfill

Fetches historical weather data from NOAA Climate Data Online API for
key agricultural regions relevant to soybean oil forecasting.

REGIONS OF INTEREST (for ZL soybean oil):
1. US Midwest (crush bucket) - Iowa, Illinois, Minnesota, Nebraska, Indiana
2. Brazil (substitutes) - Mato Grosso, Paraná, Rio Grande do Sul
3. Argentina (substitutes) - Buenos Aires, Córdoba, Santa Fe
4. China (china bucket) - Heilongjiang, Jilin, Inner Mongolia
5. Malaysia/Indonesia (palm bucket) - Sabah, Sarawak, Sumatra

DATA ELEMENTS:
- TMAX: Maximum temperature (tenths of degrees C)
- TMIN: Minimum temperature (tenths of degrees C)
- TAVG: Average temperature (tenths of degrees C)
- PRCP: Precipitation (tenths of mm)
- SNOW: Snowfall (mm)
- AWND: Average wind speed (tenths of m/s)

API: https://www.ncei.noaa.gov/cdo-web/api/v2/
Docs: https://www.ncei.noaa.gov/cdo-web/webservices/v2

SETUP:
1. Get free API key from: https://www.ncdc.noaa.gov/cdo-web/token
2. Set NOAA_API_TOKEN in .env

Usage:
    python scripts/backfill_noaa_weather.py --dry-run
    python scripts/backfill_noaa_weather.py --region us_midwest --start 2010-01-01
    python scripts/backfill_noaa_weather.py --all --start 2010-01-01
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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

# NOAA API configuration
NOAA_BASE_URL = "https://www.ncei.noaa.gov/cdo-web/api/v2"
NOAA_DATASET = "GHCND"  # Global Historical Climatology Network - Daily

# Rate limiting: NOAA allows 5 requests per second, 10,000 per day
RATE_LIMIT_DELAY = 0.25  # seconds between requests

# ═══════════════════════════════════════════════════════════════════════════════
# STATION REGISTRY - Key weather stations for soybean oil regions
# ═══════════════════════════════════════════════════════════════════════════════

WEATHER_STATIONS = {
    # US Midwest (crush bucket) - Major soybean growing/crushing regions
    'us_midwest': {
        'description': 'US Midwest - Soybean crush & growing',
        'specialist_bucket': 'crush',
        'stations': [
            # Iowa
            {'id': 'USW00014933', 'name': 'Des Moines Intl AP', 'region': 'Iowa', 'country': 'US'},
            {'id': 'USW00094987', 'name': 'Cedar Rapids AP', 'region': 'Iowa', 'country': 'US'},
            {'id': 'USW00014990', 'name': 'Sioux City AP', 'region': 'Iowa', 'country': 'US'},
            # Illinois
            {'id': 'USW00094846', 'name': 'Chicago OHare', 'region': 'Illinois', 'country': 'US'},
            {'id': 'USW00093822', 'name': 'Springfield AP', 'region': 'Illinois', 'country': 'US'},
            {'id': 'USW00014855', 'name': 'Peoria AP', 'region': 'Illinois', 'country': 'US'},
            # Minnesota
            {'id': 'USW00014922', 'name': 'Minneapolis-St Paul AP', 'region': 'Minnesota', 'country': 'US'},
            {'id': 'USW00014925', 'name': 'Rochester AP', 'region': 'Minnesota', 'country': 'US'},
            # Nebraska
            {'id': 'USW00014942', 'name': 'Omaha Eppley AP', 'region': 'Nebraska', 'country': 'US'},
            {'id': 'USW00014939', 'name': 'Lincoln AP', 'region': 'Nebraska', 'country': 'US'},
            # Indiana
            {'id': 'USW00093819', 'name': 'Indianapolis Intl AP', 'region': 'Indiana', 'country': 'US'},
            {'id': 'USW00014827', 'name': 'Fort Wayne AP', 'region': 'Indiana', 'country': 'US'},
            # Ohio
            {'id': 'USW00014820', 'name': 'Columbus AP', 'region': 'Ohio', 'country': 'US'},
            # Missouri
            {'id': 'USW00013994', 'name': 'Kansas City Intl', 'region': 'Missouri', 'country': 'US'},
            {'id': 'USW00013995', 'name': 'St Louis Lambert', 'region': 'Missouri', 'country': 'US'},
        ]
    },

    # Brazil (substitutes bucket) - Major soybean exporters
    'brazil': {
        'description': 'Brazil - Soybean production regions',
        'specialist_bucket': 'substitutes',
        'stations': [
            # Mato Grosso (largest producer)
            {'id': 'BR000083361', 'name': 'Cuiaba', 'region': 'Mato Grosso', 'country': 'BR'},
            {'id': 'BR000083214', 'name': 'Rondonopolis', 'region': 'Mato Grosso', 'country': 'BR'},
            # Paraná
            {'id': 'BR000083842', 'name': 'Curitiba', 'region': 'Parana', 'country': 'BR'},
            {'id': 'BR000083766', 'name': 'Londrina', 'region': 'Parana', 'country': 'BR'},
            # Rio Grande do Sul
            {'id': 'BR000083967', 'name': 'Porto Alegre', 'region': 'Rio Grande do Sul', 'country': 'BR'},
            # Goiás
            {'id': 'BR000083423', 'name': 'Goiania', 'region': 'Goias', 'country': 'BR'},
            # Mato Grosso do Sul
            {'id': 'BR000083704', 'name': 'Campo Grande', 'region': 'Mato Grosso do Sul', 'country': 'BR'},
        ]
    },

    # Argentina (substitutes bucket)
    'argentina': {
        'description': 'Argentina - Soybean production regions',
        'specialist_bucket': 'substitutes',
        'stations': [
            # Buenos Aires Province
            {'id': 'AR000087576', 'name': 'Buenos Aires Ezeiza', 'region': 'Buenos Aires', 'country': 'AR'},
            # Córdoba
            {'id': 'AR000087344', 'name': 'Cordoba', 'region': 'Cordoba', 'country': 'AR'},
            # Santa Fe
            {'id': 'AR000087497', 'name': 'Rosario', 'region': 'Santa Fe', 'country': 'AR'},
            # Entre Ríos
            {'id': 'AR000087374', 'name': 'Parana', 'region': 'Entre Rios', 'country': 'AR'},
        ]
    },

    # China (china bucket) - Northeast soybean regions
    'china': {
        'description': 'China - Soybean growing regions',
        'specialist_bucket': 'china',
        'stations': [
            # Heilongjiang (largest soybean province)
            {'id': 'CHM00050953', 'name': 'Harbin', 'region': 'Heilongjiang', 'country': 'CN'},
            {'id': 'CHM00050873', 'name': 'Qiqihar', 'region': 'Heilongjiang', 'country': 'CN'},
            # Jilin
            {'id': 'CHM00054161', 'name': 'Changchun', 'region': 'Jilin', 'country': 'CN'},
            # Liaoning
            {'id': 'CHM00054342', 'name': 'Shenyang', 'region': 'Liaoning', 'country': 'CN'},
            # Inner Mongolia
            {'id': 'CHM00053068', 'name': 'Hohhot', 'region': 'Inner Mongolia', 'country': 'CN'},
        ]
    },

    # Malaysia/Indonesia (palm bucket) - Palm oil regions
    'southeast_asia': {
        'description': 'Southeast Asia - Palm oil regions',
        'specialist_bucket': 'palm',
        'stations': [
            # Malaysia
            {'id': 'MYM00048647', 'name': 'Kuala Lumpur', 'region': 'West Malaysia', 'country': 'MY'},
            {'id': 'MYM00096471', 'name': 'Kota Kinabalu', 'region': 'Sabah', 'country': 'MY'},
            {'id': 'MYM00096413', 'name': 'Kuching', 'region': 'Sarawak', 'country': 'MY'},
            # Indonesia
            {'id': 'ID000096745', 'name': 'Medan', 'region': 'North Sumatra', 'country': 'ID'},
            {'id': 'ID000096035', 'name': 'Jakarta', 'region': 'Jakarta', 'country': 'ID'},
            {'id': 'ID000096633', 'name': 'Palembang', 'region': 'South Sumatra', 'country': 'ID'},
        ]
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# NASA POWER API - For regions without GHCN coverage (Paraguay, Uruguay)
# No authentication required, global coverage
# ═══════════════════════════════════════════════════════════════════════════════

NASA_POWER_LOCATIONS = {
    # Paraguay (substitutes bucket) - Critical China hedge supplier
    'paraguay': {
        'description': 'Paraguay - Emerging soybean exporter (China hedge)',
        'specialist_bucket': 'substitutes',
        'locations': [
            # Alto Paraná (largest soy production)
            {'lat': -25.51, 'lon': -54.61, 'name': 'Ciudad del Este', 'region': 'Alto Parana', 'country': 'PY'},
            {'lat': -25.75, 'lon': -55.88, 'name': 'Encarnacion', 'region': 'Itapua', 'country': 'PY'},
            # Canindeyú
            {'lat': -24.05, 'lon': -55.65, 'name': 'Salto del Guaira', 'region': 'Canindeyu', 'country': 'PY'},
            # San Pedro
            {'lat': -24.10, 'lon': -57.07, 'name': 'San Pedro', 'region': 'San Pedro', 'country': 'PY'},
        ]
    },

    # Uruguay (substitutes bucket) - Boutique quality supplier
    'uruguay': {
        'description': 'Uruguay - Premium soybean supplier',
        'specialist_bucket': 'substitutes',
        'locations': [
            # Soriano (core production)
            {'lat': -33.46, 'lon': -57.97, 'name': 'Mercedes', 'region': 'Soriano', 'country': 'UY'},
            # Paysandú
            {'lat': -32.32, 'lon': -58.07, 'name': 'Paysandu', 'region': 'Paysandu', 'country': 'UY'},
            # Río Negro
            {'lat': -33.13, 'lon': -58.30, 'name': 'Fray Bentos', 'region': 'Rio Negro', 'country': 'UY'},
        ]
    },
}


def get_noaa_token() -> str:
    """Get NOAA API token from environment."""
    token = os.getenv('NOAA_API_TOKEN') or os.getenv('NOAA_TOKEN')
    if not token:
        raise ValueError(
            "NOAA API token not found. "
            "Get free token at: https://www.ncdc.noaa.gov/cdo-web/token "
            "Then set NOAA_API_TOKEN in .env"
        )
    return token


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def fetch_station_data(
    station_id: str,
    start_date: str,
    end_date: str,
    token: str
) -> Optional[pd.DataFrame]:
    """Fetch daily weather data for a station from NOAA API.

    Returns DataFrame with columns: date, TMAX, TMIN, TAVG, PRCP, SNOW
    """
    headers = {'token': token}

    # Data elements we want - expanded for granular weather (Top 10)
    datatypes = [
        'TMAX', 'TMIN', 'TAVG', 'PRCP', 'SNOW', 'AWND',  # Existing 6
        'SNWD', 'EVAP', 'RHAV', 'WSFG'  # New 4: snow depth, evap, humidity, gust
    ]

    all_records = []
    offset = 1
    limit = 1000  # Max per request

    while True:
        params = {
            'datasetid': NOAA_DATASET,
            'stationid': f'GHCND:{station_id}',
            'startdate': start_date,
            'enddate': end_date,
            'datatypeid': ','.join(datatypes),
            'units': 'metric',
            'limit': limit,
            'offset': offset,
        }

        try:
            response = requests.get(
                f"{NOAA_BASE_URL}/data",
                headers=headers,
                params=params,
                timeout=30
            )

            if response.status_code == 429:
                logger.warning("Rate limited, waiting 60s...")
                time.sleep(60)
                continue

            response.raise_for_status()
            data = response.json()

            if 'results' not in data:
                break

            all_records.extend(data['results'])

            # Check if more pages
            metadata = data.get('metadata', {}).get('resultset', {})
            total = metadata.get('count', 0)

            if offset + limit > total:
                break

            offset += limit
            time.sleep(RATE_LIMIT_DELAY)

        except requests.exceptions.RequestException as e:
            logger.error(f"API error for {station_id}: {e}")
            return None

    if not all_records:
        return None

    # Convert to DataFrame and pivot
    df = pd.DataFrame(all_records)
    df['date'] = pd.to_datetime(df['date']).dt.date

    # Pivot datatype columns
    df_pivot = df.pivot_table(
        index='date',
        columns='datatype',
        values='value',
        aggfunc='first'
    ).reset_index()

    return df_pivot


def create_weather_table(conn):
    """Create/update weather_noaa table with proper schema in raw schema."""
    with conn.cursor() as cur:
        # Ensure raw schema exists and use it
        cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
        cur.execute("SET search_path TO raw")
        # Add new columns if needed
        cur.execute("""
            CREATE TABLE IF NOT EXISTS raw.weather_noaa_1d (
                id SERIAL PRIMARY KEY,
                station_id VARCHAR(50) NOT NULL,
                as_of_date DATE NOT NULL,
                tavg_c DOUBLE PRECISION,
                tmin_c DOUBLE PRECISION,
                tmax_c DOUBLE PRECISION,
                prcp_mm DOUBLE PRECISION,
                snow_mm DOUBLE PRECISION,
                awnd_ms DOUBLE PRECISION,
                region VARCHAR(100),
                country VARCHAR(10),
                specialist_bucket VARCHAR(50),
                ingested_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(station_id, as_of_date)
            )
        """)

        # Add missing columns if table exists
        for col, dtype in [
            ('awnd_ms', 'DOUBLE PRECISION'),
            ('specialist_bucket', 'VARCHAR(50)'),
            ('country', 'VARCHAR(10)'),
            ('snwd_mm', 'DOUBLE PRECISION'),
            ('evap_mm', 'DOUBLE PRECISION'),
            ('rhav_pct', 'DOUBLE PRECISION'),
            ('wsfg_ms', 'DOUBLE PRECISION'),
        ]:
            try:
                cur.execute(f'ALTER TABLE "raw"."weather_noaa_1d" ADD COLUMN IF NOT EXISTS {col} {dtype}')
            except:
                conn.rollback()

        cur.execute('CREATE INDEX IF NOT EXISTS idx_weather_date ON "raw"."weather_noaa_1d"(as_of_date)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_weather_region ON "raw"."weather_noaa_1d"(region)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_weather_bucket ON "raw"."weather_noaa_1d"(specialist_bucket)')

    conn.commit()
    logger.info("  Weather table ready")


def load_weather_data(
    conn,
    df: pd.DataFrame,
    station_info: Dict,
    specialist_bucket: str,
    dry_run: bool = False
) -> int:
    """Load weather data to Postgres."""
    if df is None or len(df) == 0:
        return 0

    if dry_run:
        logger.info(f"    [DRY RUN] Would insert {len(df):,} rows")
        return len(df)

    insert_query = """
        INSERT INTO "raw"."weather_noaa_1d"
        (station_id, as_of_date, tavg_c, tmin_c, tmax_c, prcp_mm, snow_mm, awnd_ms,
         snwd_mm, evap_mm, rhav_pct, wsfg_ms,
         region, country, specialist_bucket, ingested_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (station_id, as_of_date)
        DO UPDATE SET
            tavg_c = EXCLUDED.tavg_c,
            tmin_c = EXCLUDED.tmin_c,
            tmax_c = EXCLUDED.tmax_c,
            prcp_mm = EXCLUDED.prcp_mm,
            snow_mm = EXCLUDED.snow_mm,
            awnd_ms = EXCLUDED.awnd_ms,
            snwd_mm = EXCLUDED.snwd_mm,
            evap_mm = EXCLUDED.evap_mm,
            rhav_pct = EXCLUDED.rhav_pct,
            wsfg_ms = EXCLUDED.wsfg_ms
    """

    # NOAA scale factors - different elements have different scales
    NOAA_SCALE = {
        'TMAX': 0.1, 'TMIN': 0.1, 'TAVG': 0.1,  # tenths of °C → °C
        'PRCP': 0.1, 'EVAP': 0.1,               # tenths of mm → mm
        'AWND': 0.1, 'WSFG': 0.1,               # tenths of m/s → m/s
        'SNOW': 1.0, 'SNWD': 1.0,               # already in mm
        'RHAV': 1.0,                             # percent (no scale)
    }

    def safe_float(val, element_code='default'):
        if pd.isna(val):
            return None
        scale = NOAA_SCALE.get(element_code, 0.1)
        return float(val) * scale

    batch = []
    for _, row in df.iterrows():
        batch.append((
            station_info['id'],
            row['date'],
            safe_float(row.get('TAVG'), 'TAVG'),
            safe_float(row.get('TMIN'), 'TMIN'),
            safe_float(row.get('TMAX'), 'TMAX'),
            safe_float(row.get('PRCP'), 'PRCP'),
            safe_float(row.get('SNOW'), 'SNOW'),
            safe_float(row.get('AWND'), 'AWND'),
            safe_float(row.get('SNWD'), 'SNWD'),
            safe_float(row.get('EVAP'), 'EVAP'),
            safe_float(row.get('RHAV'), 'RHAV'),
            safe_float(row.get('WSFG'), 'WSFG'),
            station_info['region'],
            station_info['country'],
            specialist_bucket,
            datetime.now()
        ))

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    return len(batch)


def backfill_region(
    region_name: str,
    start_date: str,
    end_date: str,
    token: str,
    conn,
    dry_run: bool = False
) -> Dict:
    """Backfill weather data for a region."""
    if region_name not in WEATHER_STATIONS:
        return {'status': 'error', 'message': f'Unknown region: {region_name}'}

    region = WEATHER_STATIONS[region_name]
    result = {
        'region': region_name,
        'description': region['description'],
        'specialist_bucket': region['specialist_bucket'],
        'stations_processed': 0,
        'rows_loaded': 0,
        'status': 'pending'
    }

    logger.info(f"\n--- {region['description']} ---")
    logger.info(f"  Specialist bucket: {region['specialist_bucket']}")
    logger.info(f"  Stations: {len(region['stations'])}")

    for station in region['stations']:
        logger.info(f"  Fetching {station['name']} ({station['id']})...")

        df = fetch_station_data(station['id'], start_date, end_date, token)

        if df is not None and len(df) > 0:
            rows = load_weather_data(
                conn, df, station, region['specialist_bucket'], dry_run
            )
            result['rows_loaded'] += rows
            result['stations_processed'] += 1
            logger.info(f"    Loaded {rows:,} days")
        else:
            logger.warning(f"    No data available")

        time.sleep(RATE_LIMIT_DELAY)

    result['status'] = 'success'
    return result


def backfill_all(
    start_date: str,
    end_date: str,
    regions: Optional[List[str]] = None,
    dry_run: bool = False
):
    """Backfill weather data for all or selected regions."""
    logger.info("=" * 70)
    logger.info("ZINC-FUSION-V15: NOAA Weather Backfill")
    logger.info("=" * 70)
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info(f"Dry run: {dry_run}")

    try:
        token = get_noaa_token()
    except ValueError as e:
        logger.error(str(e))
        return

    conn = get_postgres_connection()

    try:
        if not dry_run:
            create_weather_table(conn)

        region_list = regions if regions else list(WEATHER_STATIONS.keys())
        results = []

        for region_name in region_list:
            result = backfill_region(
                region_name, start_date, end_date, token, conn, dry_run
            )
            results.append(result)

        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("BACKFILL SUMMARY")
        logger.info("=" * 70)

        total_rows = 0
        for r in results:
            logger.info(f"  {r['region']}: {r['stations_processed']} stations, {r['rows_loaded']:,} rows")
            total_rows += r['rows_loaded']

        logger.info(f"\nTotal rows: {total_rows:,}")

        # Verification
        if not dry_run:
            with conn.cursor() as cur:
                cur.execute('SELECT COUNT(*), MIN(as_of_date), MAX(as_of_date) FROM "raw"."weather_noaa_1d"')
                count, min_date, max_date = cur.fetchone()
                logger.info(f"\nDatabase: {count:,} rows ({min_date} to {max_date})")

                cur.execute('''
                    SELECT specialist_bucket, COUNT(*), COUNT(DISTINCT station_id)
                    FROM "raw"."weather_noaa_1d"
                    GROUP BY specialist_bucket
                ''')
                for bucket, count, stations in cur.fetchall():
                    logger.info(f"  {bucket}: {count:,} rows, {stations} stations")

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill NOAA weather data")
    parser.add_argument("--dry-run", action="store_true", help="Preview without inserting")
    parser.add_argument("--start", type=str, default="2010-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (default: today)")
    parser.add_argument("--region", type=str, help="Specific region to backfill")
    parser.add_argument("--all", action="store_true", help="Backfill all regions")
    parser.add_argument("--list-stations", action="store_true", help="List available stations")

    args = parser.parse_args()

    if args.list_stations:
        print("\nAvailable Weather Stations:")
        print("=" * 70)
        for region_name, region in WEATHER_STATIONS.items():
            print(f"\n{region_name}: {region['description']}")
            print(f"  Specialist bucket: {region['specialist_bucket']}")
            for station in region['stations']:
                print(f"    {station['id']}: {station['name']} ({station['region']}, {station['country']})")
        return

    end_date = args.end or datetime.now().strftime('%Y-%m-%d')

    if args.region:
        regions = [args.region]
    elif args.all:
        regions = None  # All regions
    else:
        parser.print_help()
        print("\nSpecify --region <name> or --all")
        return

    backfill_all(args.start, end_date, regions, args.dry_run)


if __name__ == "__main__":
    main()
