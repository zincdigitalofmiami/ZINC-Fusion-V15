#!/usr/bin/env python3
"""Check what tables exist in the database"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

with psycopg2.connect(DATABASE_URL) as conn:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Get all tables
        cur.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema IN ('public', 'raw')
            ORDER BY table_schema, table_name
        """)

        tables = cur.fetchall()

        print("=" * 80)
        print("EXISTING TABLES IN DATABASE")
        print("=" * 80)
        print()

        current_schema = None
        for row in tables:
            schema = row['table_schema']
            table = row['table_name']

            if schema != current_schema:
                print(f"\n{schema.upper()} SCHEMA:")
                print("-" * 40)
                current_schema = schema

            print(f"  - {table}")

        print()
