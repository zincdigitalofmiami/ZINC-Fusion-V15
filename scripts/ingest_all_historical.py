#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Comprehensive Historical Data Ingestion

Loads ALL historical data from parquet files in the Historical Data directory
into Postgres tables.

Data Sources (from validation report):
- Market Futures (Databento): 290,174 rows (2010-2025)
- FRED Economic: 342,551 rows (1871-2025!)
- CFTC COT: 4,506 rows (2020-2025)
- USDA Export Sales: 6,412 rows (2020-2025)
- USDA WASDE: 4,320 rows (2020-2025)
- Weather NOAA: 604 rows (2024-2025)

Usage:
    python scripts/ingest_all_historical.py --dry-run
    python scripts/ingest_all_historical.py
    python scripts/ingest_all_historical.py --source fred
    python scripts/ingest_all_historical.py --source futures
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

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

# Historical data base path - use env var, no hardcoded paths
HIST_DATA_PATH = Path(os.getenv("HISTORICAL_DATA_PATH", ""))
if not HIST_DATA_PATH or str(HIST_DATA_PATH) == "":
    logger.warning(
        "HISTORICAL_DATA_PATH not set. Set it to run ingestion from local files.\n"
        "Example: export HISTORICAL_DATA_PATH='/Volumes/Satechi Hub/Historical Data'"
    )
    HIST_DATA_PATH = Path("/tmp/historical_data")  # Placeholder for import to work

MOTHERDUCK_RAW = HIST_DATA_PATH / "MotherDuck/raw"
DATABRICKS_RAW = HIST_DATA_PATH / "Databricks Historical Databento/raw"

# Data sources configuration
DATA_SOURCES = {
    "futures": {
        "files": [
            MOTHERDUCK_RAW / "databento_futures_ohlcv_1d.parquet",
            DATABRICKS_RAW / "databento_futures_ohlcv_1d_full_2010_plus.parquet",
        ],
        "table": "raw_market_futures",
        "priority": 1,
    },
    "fred": {
        "files": [MOTHERDUCK_RAW / "fred_economic.parquet"],
        "table": "raw_fred_observations",
        "priority": 1,
    },
    "cftc": {
        "files": [
            MOTHERDUCK_RAW / "cftc_cot.parquet",
            MOTHERDUCK_RAW / "cftc_cot_tff.parquet",
        ],
        "table": "cftc_cot",
        "priority": 2,
    },
    "usda_exports": {
        "files": [MOTHERDUCK_RAW / "usda_export_sales.parquet"],
        "table": "usda_export_sales",
        "priority": 2,
    },
    "usda_wasde": {
        "files": [MOTHERDUCK_RAW / "usda_wasde.parquet"],
        "table": "usda_wasde",
        "priority": 2,
    },
    "weather": {
        "files": [MOTHERDUCK_RAW / "weather_noaa.parquet"],
        "table": "weather_noaa",
        "priority": 3,
    },
    "options": {
        "files": [MOTHERDUCK_RAW / "databento_options_ohlcv_1d.parquet"],
        "table": "raw_options_futures",
        "priority": 3,
    },
    "fred_metadata": {
        "files": [MOTHERDUCK_RAW / "fred_series_metadata.parquet"],
        "table": "fred_series_metadata",
        "priority": 3,
    },
}


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def safe_float(val):
    """Safely convert to float."""
    if pd.isna(val):
        return None
    try:
        return float(val)
    except:
        return None


def safe_int(val):
    """Safely convert to int."""
    if pd.isna(val):
        return None
    try:
        return int(val)
    except:
        return None


def safe_str(val, max_len: int = 255):
    """Safely convert to string with max length."""
    if pd.isna(val):
        return None
    return str(val)[:max_len]


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE CREATION
# ═══════════════════════════════════════════════════════════════════════════════


def create_futures_table(conn):
    """Create raw_market_futures table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_market_futures (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                as_of_date DATE NOT NULL,
                open DOUBLE PRECISION,
                high DOUBLE PRECISION,
                low DOUBLE PRECISION,
                close DOUBLE PRECISION,
                volume BIGINT,
                open_interest BIGINT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(symbol, as_of_date)
            )
        """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_futures_symbol ON raw_market_futures(symbol)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_futures_date ON raw_market_futures(as_of_date)"
        )
    conn.commit()
    logger.info("  Created raw_market_futures table")


def create_fred_table(conn):
    """Create raw_fred_observations table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_fred_observations (
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
            "CREATE INDEX IF NOT EXISTS idx_fred_series ON raw_fred_observations(series_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_fred_date ON raw_fred_observations(as_of_date)"
        )
    conn.commit()
    logger.info("  Created raw_fred_observations table")


def create_cftc_table(conn):
    """Create cftc_cot table."""
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


def create_usda_exports_table(conn):
    """Create usda_export_sales table."""
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
            "CREATE INDEX IF NOT EXISTS idx_usda_exports_date ON usda_export_sales(report_date)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_usda_exports_commodity ON usda_export_sales(commodity)"
        )
    conn.commit()
    logger.info("  Created usda_export_sales table")


def create_usda_wasde_table(conn):
    """Create usda_wasde table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS usda_wasde (
                id SERIAL PRIMARY KEY,
                report_date DATE NOT NULL,
                commodity VARCHAR(100) NOT NULL,
                country VARCHAR(100),
                metric VARCHAR(200),
                value DOUBLE PRECISION,
                unit VARCHAR(50),
                source VARCHAR(50),
                ingested_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(report_date, commodity, country, metric)
            )
        """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_wasde_date ON usda_wasde(report_date)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_wasde_commodity ON usda_wasde(commodity)"
        )
    conn.commit()
    logger.info("  Created usda_wasde table")


def create_weather_table(conn):
    """Create weather_noaa table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_noaa (
                id SERIAL PRIMARY KEY,
                station_id VARCHAR(50) NOT NULL,
                as_of_date DATE NOT NULL,
                tavg_c DOUBLE PRECISION,
                tmin_c DOUBLE PRECISION,
                tmax_c DOUBLE PRECISION,
                prcp_mm DOUBLE PRECISION,
                snow_mm DOUBLE PRECISION,
                region VARCHAR(100),
                ingested_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(station_id, as_of_date)
            )
        """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_weather_date ON weather_noaa(as_of_date)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_weather_region ON weather_noaa(region)"
        )
    conn.commit()
    logger.info("  Created weather_noaa table")


def create_options_table(conn):
    """Create raw_options_futures table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_options_futures (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(50) NOT NULL,
                as_of_date DATE NOT NULL,
                open DOUBLE PRECISION,
                high DOUBLE PRECISION,
                low DOUBLE PRECISION,
                close DOUBLE PRECISION,
                volume BIGINT,
                open_interest BIGINT,
                expiration DATE,
                strike DOUBLE PRECISION,
                option_type VARCHAR(10),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(symbol, as_of_date)
            )
        """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_options_symbol ON raw_options_futures(symbol)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_options_date ON raw_options_futures(as_of_date)"
        )
    conn.commit()
    logger.info("  Created raw_options_futures table")


def create_fred_metadata_table(conn):
    """Create fred_series_metadata table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS fred_series_metadata (
                id SERIAL PRIMARY KEY,
                series_id VARCHAR(50) NOT NULL UNIQUE,
                title VARCHAR(500),
                observation_start DATE,
                observation_end DATE,
                frequency VARCHAR(50),
                units VARCHAR(200),
                seasonal_adjustment VARCHAR(100),
                last_updated TIMESTAMP,
                source VARCHAR(200),
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """
        )
    conn.commit()
    logger.info("  Created fred_series_metadata table")


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════


def load_futures_data(conn, df: pd.DataFrame, dry_run: bool = False) -> int:
    """Load futures OHLCV data."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would insert {len(df):,} futures rows")
        return 0

    insert_query = """
        INSERT INTO raw_market_futures
        (symbol, as_of_date, open, high, low, close, volume, open_interest, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, as_of_date)
        DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            open_interest = EXCLUDED.open_interest
    """

    # Normalize column names
    df = df.copy()
    if "date" in df.columns and "as_of_date" not in df.columns:
        df["as_of_date"] = df["date"]

    batch = []
    for _, row in df.iterrows():
        batch.append(
            (
                safe_str(row["symbol"], 20),
                row["as_of_date"],
                safe_float(row.get("open")),
                safe_float(row.get("high")),
                safe_float(row.get("low")),
                safe_float(row.get("close")),
                safe_int(row.get("volume")),
                safe_int(row.get("open_interest")),
                datetime.now(),
            )
        )

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=5000)
    conn.commit()

    return len(batch)


def load_fred_data(conn, df: pd.DataFrame, dry_run: bool = False) -> int:
    """Load FRED economic data."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would insert {len(df):,} FRED rows")
        return 0

    insert_query = """
        INSERT INTO raw_fred_observations
        (series_id, as_of_date, value, source, created_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (series_id, as_of_date)
        DO UPDATE SET
            value = EXCLUDED.value,
            source = EXCLUDED.source
    """

    # Normalize column names
    df = df.copy()
    if "date" in df.columns and "as_of_date" not in df.columns:
        df["as_of_date"] = df["date"]

    batch = []
    for _, row in df.iterrows():
        batch.append(
            (
                safe_str(row["series_id"], 50),
                row["as_of_date"],
                safe_float(row.get("value")),
                safe_str(row.get("source", "fred"), 50),
                datetime.now(),
            )
        )

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=5000)
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
            managed_money_net_pct_oi = EXCLUDED.managed_money_net_pct_oi
    """

    batch = []
    for _, row in df.iterrows():
        batch.append(
            (
                row["report_date"],
                safe_str(row["symbol"], 20),
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
                safe_str(row.get("source", "cftc"), 50),
                datetime.now(),
            )
        )

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    return len(batch)


def load_usda_exports_data(conn, df: pd.DataFrame, dry_run: bool = False) -> int:
    """Load USDA export sales data."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would insert {len(df):,} USDA export rows")
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
            outstanding_sales_mt = EXCLUDED.outstanding_sales_mt
    """

    batch = []
    for _, row in df.iterrows():
        batch.append(
            (
                row["report_date"],
                safe_str(row["commodity"], 100),
                safe_str(row.get("destination_country", "Unknown"), 100),
                safe_float(row.get("net_sales_mt")),
                safe_float(row.get("exports_mt")),
                safe_float(row.get("outstanding_sales_mt")),
                safe_str(row.get("source", "usda"), 50),
                datetime.now(),
            )
        )

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    return len(batch)


def load_usda_wasde_data(conn, df: pd.DataFrame, dry_run: bool = False) -> int:
    """Load USDA WASDE data."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would insert {len(df):,} WASDE rows")
        return 0

    insert_query = """
        INSERT INTO usda_wasde
        (report_date, commodity, country, metric, value, unit, source, ingested_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (report_date, commodity, country, metric)
        DO UPDATE SET
            value = EXCLUDED.value,
            unit = EXCLUDED.unit
    """

    batch = []
    for _, row in df.iterrows():
        batch.append(
            (
                row["report_date"],
                safe_str(row["commodity"], 100),
                safe_str(row.get("country", "World"), 100),
                safe_str(row.get("metric"), 200),
                safe_float(row.get("value")),
                safe_str(row.get("unit"), 50),
                safe_str(row.get("source", "usda"), 50),
                datetime.now(),
            )
        )

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    return len(batch)


def load_weather_data(conn, df: pd.DataFrame, dry_run: bool = False) -> int:
    """Load NOAA weather data."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would insert {len(df):,} weather rows")
        return 0

    insert_query = """
        INSERT INTO weather_noaa
        (station_id, as_of_date, tavg_c, tmin_c, tmax_c, prcp_mm, snow_mm, region, ingested_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (station_id, as_of_date)
        DO UPDATE SET
            tavg_c = EXCLUDED.tavg_c,
            tmin_c = EXCLUDED.tmin_c,
            tmax_c = EXCLUDED.tmax_c,
            prcp_mm = EXCLUDED.prcp_mm,
            snow_mm = EXCLUDED.snow_mm
    """

    # Normalize column names
    df = df.copy()
    if "date" in df.columns and "as_of_date" not in df.columns:
        df["as_of_date"] = df["date"]

    batch = []
    for _, row in df.iterrows():
        batch.append(
            (
                safe_str(row["station_id"], 50),
                row["as_of_date"],
                safe_float(row.get("tavg_c")),
                safe_float(row.get("tmin_c")),
                safe_float(row.get("tmax_c")),
                safe_float(row.get("prcp_mm")),
                safe_float(row.get("snow_mm")),
                safe_str(row.get("region"), 100),
                datetime.now(),
            )
        )

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    return len(batch)


def load_options_data(conn, df: pd.DataFrame, dry_run: bool = False) -> int:
    """Load options OHLCV data."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would insert {len(df):,} options rows")
        return 0

    insert_query = """
        INSERT INTO raw_options_futures
        (symbol, as_of_date, open, high, low, close, volume, open_interest, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, as_of_date)
        DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            open_interest = EXCLUDED.open_interest
    """

    df = df.copy()
    if "date" in df.columns and "as_of_date" not in df.columns:
        df["as_of_date"] = df["date"]

    batch = []
    for _, row in df.iterrows():
        batch.append(
            (
                safe_str(row["symbol"], 50),
                row["as_of_date"],
                safe_float(row.get("open")),
                safe_float(row.get("high")),
                safe_float(row.get("low")),
                safe_float(row.get("close")),
                safe_int(row.get("volume")),
                safe_int(row.get("open_interest")),
                datetime.now(),
            )
        )

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=5000)
    conn.commit()

    return len(batch)


def load_fred_metadata(conn, df: pd.DataFrame, dry_run: bool = False) -> int:
    """Load FRED series metadata."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would insert {len(df):,} metadata rows")
        return 0

    insert_query = """
        INSERT INTO fred_series_metadata
        (series_id, title, observation_start, observation_end, frequency, units,
         seasonal_adjustment, last_updated, source, notes, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (series_id)
        DO UPDATE SET
            title = EXCLUDED.title,
            observation_end = EXCLUDED.observation_end,
            last_updated = EXCLUDED.last_updated
    """

    batch = []
    for _, row in df.iterrows():
        batch.append(
            (
                safe_str(row["series_id"], 50),
                safe_str(row.get("title"), 500),
                row.get("observation_start"),
                row.get("observation_end"),
                safe_str(row.get("frequency"), 50),
                safe_str(row.get("units"), 200),
                safe_str(row.get("seasonal_adjustment"), 100),
                row.get("last_updated"),
                safe_str(row.get("source"), 200),
                str(row.get("notes"))[:5000] if row.get("notes") else None,
                datetime.now(),
            )
        )

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    return len(batch)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN INGESTION
# ═══════════════════════════════════════════════════════════════════════════════

LOADERS = {
    "futures": (create_futures_table, load_futures_data),
    "fred": (create_fred_table, load_fred_data),
    "cftc": (create_cftc_table, load_cftc_data),
    "usda_exports": (create_usda_exports_table, load_usda_exports_data),
    "usda_wasde": (create_usda_wasde_table, load_usda_wasde_data),
    "weather": (create_weather_table, load_weather_data),
    "options": (create_options_table, load_options_data),
    "fred_metadata": (create_fred_metadata_table, load_fred_metadata),
}


def ingest_source(conn, source_name: str, dry_run: bool = False) -> Dict:
    """Ingest a single data source."""
    if source_name not in DATA_SOURCES:
        logger.error(f"Unknown source: {source_name}")
        return {"status": "error", "message": f"Unknown source: {source_name}"}

    config = DATA_SOURCES[source_name]
    create_fn, load_fn = LOADERS[source_name]

    result = {
        "source": source_name,
        "table": config["table"],
        "files_processed": 0,
        "rows_loaded": 0,
        "status": "pending",
    }

    try:
        # Create table if not dry run
        if not dry_run:
            create_fn(conn)

        # Load each file
        for file_path in config["files"]:
            if not file_path.exists():
                logger.warning(f"  File not found: {file_path}")
                continue

            logger.info(f"  Loading {file_path.name}...")
            df = pd.read_parquet(file_path)
            logger.info(f"    Read {len(df):,} rows")

            # Normalize date columns
            for col in ["date", "as_of_date", "report_date"]:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col]).dt.date

            rows = load_fn(conn, df, dry_run)
            result["files_processed"] += 1
            result["rows_loaded"] += rows if rows else len(df)

        result["status"] = "success"

    except Exception as e:
        logger.error(f"  Error loading {source_name}: {e}")
        result["status"] = "error"
        result["message"] = str(e)
        conn.rollback()

    return result


def ingest_all(sources: Optional[List[str]] = None, dry_run: bool = False):
    """Run full data ingestion."""
    logger.info("=" * 70)
    logger.info("ZINC-FUSION-V15: Comprehensive Historical Data Ingestion")
    logger.info("=" * 70)
    logger.info(f"Dry run: {dry_run}")

    conn = get_postgres_connection()

    # Determine which sources to ingest
    if sources:
        source_list = sources
    else:
        # Sort by priority
        source_list = sorted(
            DATA_SOURCES.keys(), key=lambda x: DATA_SOURCES[x]["priority"]
        )

    results = []

    try:
        for source_name in source_list:
            logger.info(f"\n--- {source_name.upper()} ---")
            result = ingest_source(conn, source_name, dry_run)
            results.append(result)
            logger.info(f"  Status: {result['status']}")
            logger.info(
                f"  Files: {result['files_processed']}, Rows: {result['rows_loaded']:,}"
            )

        # Verification
        if not dry_run:
            logger.info("\n" + "=" * 70)
            logger.info("VERIFICATION")
            logger.info("=" * 70)

            with conn.cursor() as cur:
                for source_name in source_list:
                    table = DATA_SOURCES[source_name]["table"]
                    try:
                        cur.execute(f"SELECT COUNT(*) FROM {table}")
                        count = cur.fetchone()[0]

                        # Get date range
                        date_col = (
                            "as_of_date"
                            if "futures" in table
                            or "fred" in table
                            or "weather" in table
                            else "report_date"
                        )
                        cur.execute(
                            f"SELECT MIN({date_col}), MAX({date_col}) FROM {table}"
                        )
                        min_date, max_date = cur.fetchone()

                        logger.info(
                            f"  {table}: {count:,} rows ({min_date} to {max_date})"
                        )
                    except Exception as e:
                        logger.error(f"  {table}: {e}")
                        conn.rollback()

        logger.info("\n" + "=" * 70)
        logger.info("INGESTION COMPLETE")
        logger.info("=" * 70)

        # Summary
        total_rows = sum(r["rows_loaded"] for r in results)
        success_count = sum(1 for r in results if r["status"] == "success")
        logger.info(f"Sources: {success_count}/{len(results)} successful")
        logger.info(f"Total rows: {total_rows:,}")

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Ingest all historical data into Postgres"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without inserting"
    )
    parser.add_argument(
        "--source",
        type=str,
        help="Specific source to ingest (futures, fred, cftc, usda_exports, usda_wasde, weather, options, fred_metadata)",
    )

    args = parser.parse_args()

    sources = [args.source] if args.source else None
    ingest_all(sources=sources, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
