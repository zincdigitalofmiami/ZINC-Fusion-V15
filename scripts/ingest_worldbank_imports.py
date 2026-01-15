#!/usr/bin/env python3
"""
Ingest World Bank Import Trade Data into Prisma Postgres

Source: data/downloads/import_trade.csv
Target: raw.worldbank_imports_1y
Grain: Yearly (1y)

Data: Imports of goods and services as % of GDP by country

NOTE (Governance):
- This script MUST NOT create/drop tables or perform any schema DDL.
- If the destination table does not exist (or columns don't match), fail loudly.
"""

import pandas as pd
import psycopg2
import os
from pathlib import Path


def load_env():
    """Load environment variables from .env file"""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip('"')


def main():
    load_env()

    # Load source data
    csv_path = Path(__file__).parent.parent / "data/downloads/import_trade.csv"
    print(f"Loading: {csv_path}")
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} rows")

    # Clean column names
    df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]

    # Raw schema contract: event_date is canonical time key.
    # For yearly data, use Jan 1 of the given year.
    df["event_date"] = pd.to_datetime(df["year"].astype(str) + "-01-01").dt.date

    # Connect to database
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    # Check table exists (no schema changes allowed here).
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'raw' AND table_name = 'worldbank_imports_1y'
        )
        """
    )
    if not cur.fetchone()[0]:
        raise RuntimeError(
            "raw.worldbank_imports_1y does not exist. "
            "Schema/table creation requires explicit approval; this script will not create it."
        )

    # Verify required columns exist (fail loudly on drift).
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'raw' AND table_name = 'worldbank_imports_1y'
        """
    )
    cols = {r[0] for r in cur.fetchall()}
    required_cols = {
        "event_date",
        "country_code",
        "country_name",
        "region",
        "sub_region",
        "intermediate_region",
        "indicator_code",
        "indicator_name",
        "year",
        "imports_pct_gdp",
    }
    missing = sorted(required_cols - cols)
    if missing:
        raise RuntimeError(
            f"raw.worldbank_imports_1y missing required columns: {', '.join(missing)}"
        )

    # Insert data in batches
    inserted = 0
    batch_size = 1000

    for _, row in df.iterrows():
        cur.execute(
            """
            INSERT INTO raw.worldbank_imports_1y 
            (event_date, country_code, country_name, region, sub_region, 
             intermediate_region, indicator_code, indicator_name, year, imports_pct_gdp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """,
            (
                row["event_date"],
                row["country_code"],
                row["country_name"],
                row["region"],
                row["sub_region"],
                row.get("intermediate_region"),
                row["indicator_code"],
                row["indicator_name"],
                row["year"],
                row["imports_of_goods_and_services"],
            ),
        )
        inserted += 1
        if inserted % batch_size == 0:
            conn.commit()
            print(f"  Inserted {inserted} rows...")

    conn.commit()
    print(f"✅ INGESTED {inserted} rows")

    # Verification
    print("\n=== VERIFICATION ===")
    cur.execute("SELECT COUNT(*) FROM raw.worldbank_imports_1y")
    count = cur.fetchone()[0]
    print(f"Total rows in table: {count}")

    cur.execute("SELECT COUNT(DISTINCT country_code) FROM raw.worldbank_imports_1y")
    countries = cur.fetchone()[0]
    print(f"Unique countries: {countries}")

    cur.execute("SELECT MIN(year), MAX(year) FROM raw.worldbank_imports_1y")
    year_range = cur.fetchone()
    print(f"Year range: {year_range[0]} - {year_range[1]}")

    # Key countries for ZL analysis
    cur.execute(
        """
        SELECT country_code, country_name, COUNT(*) as years, 
               ROUND(AVG(imports_pct_gdp)::numeric, 2) as avg_imports_pct
        FROM raw.worldbank_imports_1y 
        WHERE country_code IN ('CHN', 'BRA', 'ARG', 'USA', 'IND', 'IDN', 'MYS')
        GROUP BY country_code, country_name
        ORDER BY avg_imports_pct DESC
    """
    )
    print("\nKey countries for ZL analysis:")
    for row in cur.fetchall():
        print(f"  {row[0]} ({row[1]}): {row[2]} years, avg {row[3]}% imports/GDP")

    cur.close()
    conn.close()
    print("\n✅ COMPLETE")


if __name__ == "__main__":
    main()
