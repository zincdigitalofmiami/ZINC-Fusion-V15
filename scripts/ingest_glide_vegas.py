#!/usr/bin/env python3
"""
ZINC-FUSION-V15 — Glide Vegas Data Ingestion
============================================
Pulls REAL customer/restaurant/fryer data from US Oil Solutions' Glide app.

⚠️  GLIDE IS READ-ONLY ⚠️
- This script ONLY READS from Glide API (never writes back)
- Glide = US Oil Solutions' production system - DO NOT MODIFY
- Data flow: Glide (READ ONLY) → Prisma PostgreSQL → Frontend

Configuration:
- Endpoint: https://api.glideapp.io/api/function/queryTables
- App ID: 6262JQJdNjhra79M25e4
- Bearer Token: Set GLIDE_BEARER_TOKEN env var

Tables synced (8 sources):
1. vegas_restaurants (151 rows) - Restaurant master data
2. vegas_casinos (31 rows) - Casino event data  
3. vegas_fryers (421 rows) - Fryer capacity (FOUNDATION)
4. vegas_export_list (3,176 rows) - Customer exports
5. vegas_scheduled_reports (28 rows) - Report schedules
6. vegas_shifts (148 rows) - Delivery shifts
7. vegas_shift_casinos (440 rows) - Casino shift schedules
8. vegas_shift_restaurants (1,233 rows) - Restaurant shift schedules

Total: ~5,628 rows of real customer data
"""

import os
import sys
import json
import requests
from datetime import datetime
from typing import Any

# Add parent to path for _init_env
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _init_env import get_pg_connection

# =============================================================================
# GLIDE API CONFIGURATION (LOCKED - DO NOT CHANGE)
# =============================================================================

GLIDE_API_ENDPOINT = "https://api.glideapp.io/api/function/queryTables"
GLIDE_APP_ID = "6262JQJdNjhra79M25e4"
GLIDE_BEARER_TOKEN = os.getenv('GLIDE_BEARER_TOKEN', '460c9ee4-edcb-43cc-86b5-929e2bb94351')

# Glide Table IDs (8 data sources - LOCKED CONFIGURATION)
GLIDE_TABLES = {
    'restaurants': 'native-table-ojIjQjDcDAEOpdtZG5Ao',
    'casinos': 'native-table-Gy2xHsC7urEttrz80hS7',
    'fryers': 'native-table-r2BIqSLhezVbOKGeRJj8',
    'export_list': 'native-table-PLujVF4tbbiIi9fzrWg8',
    'scheduled_reports': 'native-table-pF4uWe5mpzoeGZbDQhPK',
    'shifts': 'native-table-K53E3SQsgOUB4wdCJdAN',
    'shift_casinos': 'native-table-G7cMiuqRgWPhS0ICRRyy',
    'shift_restaurants': 'native-table-QgzI2S9pWL584rkOhWBA'
}

# Map Glide tables to Postgres table names
POSTGRES_TABLES = {
    'restaurants': 'vegas_restaurants',
    'casinos': 'vegas_casinos',
    'fryers': 'vegas_fryers',
    'export_list': 'vegas_export_list',
    'scheduled_reports': 'vegas_scheduled_reports',
    'shifts': 'vegas_shifts',
    'shift_casinos': 'vegas_shift_casinos',
    'shift_restaurants': 'vegas_shift_restaurants'
}


def sanitize_column_name(name: str) -> str:
    """
    Sanitize Glide column names for PostgreSQL.
    Glide returns columns like $rowID, $rowIndex which are invalid in Postgres.
    """
    # Replace $ with glide_ prefix
    if name.startswith('$'):
        name = 'glide_' + name[1:]
    # Replace spaces and special chars
    name = name.replace(' ', '_').replace('-', '_').replace('.', '_')
    # Lowercase for Postgres convention
    name = name.lower()
    return name


def query_glide_table(table_id: str) -> list[dict[str, Any]]:
    """
    Query a single Glide table using the locked API format.
    Returns list of row dicts, or empty list on error.
    """
    headers = {
        'Authorization': f'Bearer {GLIDE_BEARER_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        "appID": GLIDE_APP_ID,
        "queries": [
            {
                "tableName": table_id,
                "utc": True
            }
        ]
    }
    
    try:
        response = requests.post(
            GLIDE_API_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=60  # Increased for large tables like export_list
        )
        
        if response.status_code == 200:
            data = response.json()
            # Extract rows from response structure: [{"rows": [...]}]
            if isinstance(data, list) and len(data) > 0 and 'rows' in data[0]:
                rows = data[0]['rows']
                return rows if isinstance(rows, list) else []
            print(f"  ⚠️  Unexpected response structure")
            return []
        else:
            print(f"  ❌ API Error: Status {response.status_code}")
            print(f"     Response: {response.text[:200]}")
            return []
            
    except requests.exceptions.Timeout:
        print(f"  ❌ Timeout querying Glide API")
        return []
    except Exception as e:
        print(f"  ❌ Exception: {str(e)}")
        return []


def create_vegas_schema(conn) -> None:
    """
    Create the raw.vegas_* tables if they don't exist.
    Uses JSONB for flexible schema since Glide columns can vary.
    """
    cursor = conn.cursor()
    
    for table_key, table_name in POSTGRES_TABLES.items():
        # Drop and recreate to handle schema changes
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS raw.{table_name} (
                id SERIAL PRIMARY KEY,
                glide_row_id VARCHAR(255),
                data JSONB NOT NULL,
                source_table_id VARCHAR(255),
                ingested_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        # Create index on glide_row_id for upserts
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_glide_row_id 
            ON raw.{table_name}(glide_row_id)
        """)
    
    conn.commit()
    cursor.close()
    print("✅ Vegas schema created/verified")


def upsert_vegas_data(conn, table_key: str, rows: list[dict[str, Any]]) -> int:
    """
    Upsert Glide data into Postgres.
    Uses JSONB storage for flexibility.
    Returns number of rows upserted.
    """
    if not rows:
        return 0
        
    table_name = POSTGRES_TABLES[table_key]
    source_table_id = GLIDE_TABLES[table_key]
    cursor = conn.cursor()
    
    # Clear existing data (full refresh)
    cursor.execute(f"TRUNCATE raw.{table_name} RESTART IDENTITY")
    
    # Insert all rows
    count = 0
    for row in rows:
        # Extract glide_row_id if present
        glide_row_id = row.get('$rowID', row.get('glide_rowID', None))
        
        # Sanitize all column names in the data
        sanitized_row = {sanitize_column_name(k): v for k, v in row.items()}
        
        cursor.execute(f"""
            INSERT INTO raw.{table_name} (glide_row_id, data, source_table_id)
            VALUES (%s, %s, %s)
        """, (glide_row_id, json.dumps(sanitized_row), source_table_id))
        count += 1
    
    conn.commit()
    cursor.close()
    return count


def ingest_all_vegas_data(dry_run: bool = False) -> dict[str, int]:
    """
    Main ingestion function - pulls from all 8 Glide tables.
    Returns dict of table_name -> row_count.
    """
    print("=" * 60)
    print("GLIDE VEGAS DATA INGESTION — ZINC-FUSION-V15")
    print(f"Mode: {'DRY RUN (no writes)' if dry_run else 'LIVE'}")
    print(f"App ID: {GLIDE_APP_ID}")
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    results = {}
    
    if not dry_run:
        conn = get_pg_connection()
        create_vegas_schema(conn)
    
    for table_key, table_id in GLIDE_TABLES.items():
        print(f"\n📥 Fetching {table_key}...")
        
        rows = query_glide_table(table_id)
        
        if rows:
            print(f"   ✅ Fetched {len(rows)} rows from Glide")
            
            if not dry_run:
                count = upsert_vegas_data(conn, table_key, rows)
                print(f"   ✅ Saved {count} rows to raw.{POSTGRES_TABLES[table_key]}")
                results[table_key] = count
            else:
                # Show sample data in dry run
                print(f"   📋 Sample columns: {list(rows[0].keys())[:5]}...")
                results[table_key] = len(rows)
        else:
            print(f"   ⚠️  No data returned")
            results[table_key] = 0
    
    if not dry_run:
        conn.close()
    
    # Summary
    print("\n" + "=" * 60)
    total = sum(results.values())
    print(f"✅ GLIDE INGESTION COMPLETE")
    print(f"   Total rows: {total:,}")
    for table_key, count in results.items():
        print(f"   • {POSTGRES_TABLES[table_key]}: {count:,} rows")
    print("=" * 60)
    
    return results


def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description='Ingest Vegas data from Glide')
    parser.add_argument('--dry-run', action='store_true', 
                        help='Test API calls without writing to database')
    args = parser.parse_args()
    
    ingest_all_vegas_data(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
