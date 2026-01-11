#!/usr/bin/env python3
"""
Glide API Integration - Vegas Customer & Restaurant Data
Adapted for ZINC-FUSION-V15 (Prisma PostgreSQL)

🚨 CRITICAL: GLIDE IS READ ONLY 🚨
- This script ONLY READS data from Glide API (no writes back)
- Glide = US Oil Solutions production CRM system - DO NOT TOUCH
- Data flow: Glide (READ ONLY) → Prisma PostgreSQL → Frontend

Original: CBI-V14/cbi-v14-ingestion/ingest_glide_vegas_data.py
Ported by: Claude (2026-01-10)

API Configuration (LOCKED - DO NOT CHANGE):
- Endpoint: https://api.glideapp.io/api/function/queryTables
- App ID: 6262JQJdNjhra79M25e4
- Bearer Token: Set via GLIDE_BEARER_TOKEN env var
"""

import os
import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

from fusion.db import get_write_connection

logger = logging.getLogger(__name__)

# =============================================================================
# GLIDE API CONFIGURATION (LOCKED)
# =============================================================================

GLIDE_API_ENDPOINT = "https://api.glideapp.io/api/function/queryTables"
GLIDE_APP_ID = "6262JQJdNjhra79M25e4"
GLIDE_BEARER_TOKEN = os.getenv("GLIDE_BEARER_TOKEN", "460c9ee4-edcb-43cc-86b5-929e2bb94351")

# Table IDs (8 data sources - LOCKED CONFIGURATION)
GLIDE_TABLES = {
    "restaurants": "native-table-ojIjQjDcDAEOpdtZG5Ao",
    "casinos": "native-table-Gy2xHsC7urEttrz80hS7",
    "fryers": "native-table-r2BIqSLhezVbOKGeRJj8",
    "export_list": "native-table-PLujVF4tbbiIi9fzrWg8",
    "scheduled_reports": "native-table-pF4uWe5mpzoeGZbDQhPK",
    "shifts": "native-table-K53E3SQsgOUB4wdCJdAN",
    "shift_casinos": "native-table-G7cMiuqRgWPhS0ICRRyy",
    "shift_restaurants": "native-table-QgzI2S9pWL584rkOhWBA",
}

# Schema in Prisma PostgreSQL
POSTGRES_SCHEMA = "ops"


# =============================================================================
# GLIDE API CLIENT
# =============================================================================


class GlideAPIClient:
    """
    Client for Glide API - READ ONLY operations.
    
    Never writes back to Glide. Only pulls data into our system.
    """

    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {GLIDE_BEARER_TOKEN}",
            "Content-Type": "application/json",
        }

    def query_table(self, table_id: str) -> list[dict[str, Any]]:
        """
        Query Glide table using exact API format.
        
        Args:
            table_id: Glide native table ID
            
        Returns:
            List of row dictionaries
        """
        payload = {
            "appID": GLIDE_APP_ID,
            "queries": [{"tableName": table_id, "utc": True}],
        }

        try:
            response = requests.post(
                GLIDE_API_ENDPOINT,
                headers=self.headers,
                json=payload,
                timeout=60,  # Longer timeout for large tables
            )

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0 and "rows" in data[0]:
                    rows = data[0]["rows"]
                    logger.info(f"✅ Fetched {len(rows)} rows from {table_id}")
                    return rows if isinstance(rows, list) else []
                logger.warning(f"⚠️ Unexpected response structure for {table_id}")
                return []
            else:
                logger.error(f"❌ API Error: Status {response.status_code}")
                logger.error(f"   Response: {response.text[:200]}")
                return []

        except Exception as e:
            logger.error(f"❌ Exception querying {table_id}: {e}")
            return []

    def get_table(self, table_name: str) -> pd.DataFrame:
        """
        Get table data as DataFrame.
        
        Args:
            table_name: Key from GLIDE_TABLES dict
            
        Returns:
            DataFrame with table data
        """
        if table_name not in GLIDE_TABLES:
            logger.error(f"Unknown table: {table_name}")
            return pd.DataFrame()

        table_id = GLIDE_TABLES[table_name]
        logger.info(f"Fetching {table_name} from Glide API...")
        
        rows = self.query_table(table_id)
        if not rows:
            logger.warning(f"⚠️ No data for {table_name}")
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        logger.info(f"✅ Got {len(df)} rows for {table_name}")
        return df


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================


def sanitize_column_name(col: str) -> str:
    """
    Sanitize column name for PostgreSQL.
    
    - Remove $ prefix (Glide uses $rowID, etc.)
    - Replace spaces and dashes with underscores
    - Lowercase for consistency
    """
    return col.replace("$", "glide_").replace(" ", "_").replace("-", "_").lower()


def save_to_postgres(
    df: pd.DataFrame,
    table_name: str,
    source_table_id: str,
) -> int:
    """
    Save DataFrame to PostgreSQL (ops schema).
    
    Uses TRUNCATE + INSERT pattern for full refresh.
    
    Args:
        df: DataFrame to save
        table_name: Target table name (e.g., 'vegas_restaurants')
        source_table_id: Glide table ID for provenance
        
    Returns:
        Number of rows inserted
    """
    if df.empty:
        logger.warning(f"⚠️ No data to save to {table_name}")
        return 0

    # Sanitize column names
    df = df.copy()
    df.columns = [sanitize_column_name(col) for col in df.columns]

    # Add metadata
    df["ingested_at"] = datetime.now(timezone.utc)
    df["source_table_id"] = source_table_id

    # Build table reference
    full_table = f"{POSTGRES_SCHEMA}.{table_name}"

    conn = get_write_connection()
    try:
        with conn.cursor() as cur:
            # Create table if not exists (auto-detect schema from DataFrame)
            # For now, we'll create simple text columns for all fields
            columns = df.columns.tolist()
            col_defs = ", ".join([f'"{c}" TEXT' for c in columns if c not in ("ingested_at",)])
            col_defs += ', "ingested_at" TIMESTAMPTZ'

            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {full_table} (
                    {col_defs}
                )
            """)

            # Truncate existing data (full refresh)
            cur.execute(f"TRUNCATE TABLE {full_table}")

            # Insert new data
            cols = ", ".join([f'"{c}"' for c in columns])
            placeholders = ", ".join(["%s"] * len(columns))
            insert_sql = f"INSERT INTO {full_table} ({cols}) VALUES ({placeholders})"

            # Convert DataFrame to list of tuples
            records = [tuple(str(v) if pd.notna(v) else None for v in row) for row in df.values]

            from psycopg2.extras import execute_batch
            execute_batch(cur, insert_sql, records, page_size=1000)

        conn.commit()
        logger.info(f"✅ Saved {len(df)} rows to {full_table}")
        return len(df)

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Error saving to {table_name}: {e}")
        raise
    finally:
        conn.close()


# =============================================================================
# MAIN INGESTION FUNCTIONS
# =============================================================================


def ingest_all_vegas_data() -> dict[str, int]:
    """
    Ingest all 8 Glide tables into PostgreSQL.
    
    Returns:
        Dict mapping table name to row count
    """
    logger.info("=" * 60)
    logger.info("GLIDE API INGESTION - VEGAS DATA (8 SOURCES)")
    logger.info("READ ONLY - Data flows: Glide → PostgreSQL → Frontend")
    logger.info(f"App ID: {GLIDE_APP_ID}")
    logger.info("=" * 60)

    client = GlideAPIClient()
    results = {}

    for table_name, table_id in GLIDE_TABLES.items():
        try:
            df = client.get_table(table_name)
            if not df.empty:
                postgres_table = f"vegas_{table_name}"
                row_count = save_to_postgres(df, postgres_table, table_id)
                results[table_name] = row_count
            else:
                results[table_name] = 0
        except Exception as e:
            logger.error(f"❌ Failed to ingest {table_name}: {e}")
            results[table_name] = -1

    logger.info("=" * 60)
    logger.info("GLIDE API INGESTION COMPLETE")
    for name, count in results.items():
        status = "✅" if count > 0 else "❌" if count < 0 else "⚠️"
        logger.info(f"  {status} {name}: {count} rows")
    logger.info("=" * 60)

    return results


def ingest_single_table(table_name: str) -> int:
    """
    Ingest a single Glide table.
    
    Args:
        table_name: Key from GLIDE_TABLES dict
        
    Returns:
        Number of rows inserted
    """
    if table_name not in GLIDE_TABLES:
        logger.error(f"Unknown table: {table_name}")
        return -1

    client = GlideAPIClient()
    df = client.get_table(table_name)

    if df.empty:
        return 0

    postgres_table = f"vegas_{table_name}"
    return save_to_postgres(df, postgres_table, GLIDE_TABLES[table_name])


# =============================================================================
# CLI ENTRY POINT
# =============================================================================


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    if len(sys.argv) > 1:
        # Ingest single table
        table = sys.argv[1]
        ingest_single_table(table)
    else:
        # Ingest all tables
        ingest_all_vegas_data()
