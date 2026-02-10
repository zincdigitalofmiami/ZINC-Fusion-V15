#!/usr/bin/env python3
"""
Quick script to ingest FRED data from Downloads folder CSVs.

Routes each series to the correct econ.* domain table using the
FRED_SERIES_ROUTING map from src/fusion/db/fred_routing.py.
"""

import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch

# Load environment
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.fusion.db.fred_routing import get_fred_schema_table


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")
    return psycopg2.connect(database_url)


# Mapping from filename to FRED series_id
FILE_MAPPINGS = {
    "VIXCLS 2.csv": ("VIXCLS", "observation_date", "VIXCLS"),
    "FRED_FEDFUNDS, 1D 2.csv": ("FEDFUNDS", "time", "close"),
    "FRED_GDP, 1D 2.csv": ("GDP", "time", "close"),
    "FRED_SP500, 1D 2.csv": ("SP500", "time", "close"),
    "FRED_LVXRNSA, 1D 2.csv": ("LVXRNSA", "time", "close"),
    "VXGSCLS 2.csv": ("VXGSCLS", "observation_date", "VXGSCLS"),
    "VXGSCLS (1) 2.csv": ("VXGSCLS", "observation_date", "VXGSCLS"),
}


def ingest_file(
    conn, filepath: Path, series_id: str, date_col: str, value_col: str
) -> int:
    """Ingest a single CSV file into the database."""
    try:
        df = pd.read_csv(filepath)

        if date_col not in df.columns:
            print(f"  Error: Column '{date_col}' not found in {filepath.name}")
            print(f"  Available columns: {list(df.columns)}")
            return 0

        if value_col not in df.columns:
            print(f"  Error: Column '{value_col}' not found in {filepath.name}")
            return 0

        # Parse dates and values
        df["as_of_date"] = pd.to_datetime(df[date_col], errors="coerce")
        df["value"] = pd.to_numeric(df[value_col], errors="coerce")

        # Drop invalid rows
        df = df.dropna(subset=["as_of_date", "value"])

        if df.empty:
            print(f"  No valid data in {filepath.name}")
            return 0

        # Route to correct econ.* table based on series_id
        schema, table = get_fred_schema_table(series_id)
        qualified_table = f'"{schema}"."{table}"'

        records = [
            (series_id, row["as_of_date"], row["value"], "FRED")
            for _, row in df.iterrows()
        ]

        with conn.cursor() as cur:
            execute_batch(
                cur,
                f"""
                INSERT INTO {qualified_table}
                (series_id, event_date, value, source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (series_id, event_date) DO NOTHING
                """,
                records,
                page_size=500,
            )
            inserted = cur.rowcount

        conn.commit()
        print(f"  Routed to: {qualified_table}")
        return inserted

    except Exception as e:
        print(f"  Error: {e}")
        conn.rollback()
        return 0


def main():
    downloads = Path.home() / "Downloads"

    print("=" * 60)
    print("INGEST FRED CSVs FROM DOWNLOADS")
    print("=" * 60)

    conn = get_postgres_connection()
    total_inserted = 0

    for filename, (series_id, date_col, value_col) in FILE_MAPPINGS.items():
        filepath = downloads / filename

        if not filepath.exists():
            print(f"[SKIP] {filename} - not found")
            continue

        print(f"[{series_id}] {filename}")

        # Count rows
        df = pd.read_csv(filepath)
        print(f"  Rows in file: {len(df):,}")

        inserted = ingest_file(conn, filepath, series_id, date_col, value_col)
        print(f"  Inserted: {inserted:,}")
        total_inserted += inserted

    conn.close()

    print()
    print("=" * 60)
    print(f"TOTAL INSERTED: {total_inserted:,}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
