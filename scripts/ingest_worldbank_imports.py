#!/usr/bin/env python3
"""
Ingest World Bank Import Trade Data into Prisma Postgres

Source: data/downloads/import_trade.csv
Target: raw.worldbank_imports_1y
Grain: Yearly (1y)

Data: Imports of goods and services as % of GDP by country
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

    # Create as_of_date (Jan 1 of each year)
    df["as_of_date"] = pd.to_datetime(df["year"].astype(str) + "-01-01")

    # Connect to database
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    # Check if table exists
    cur.execute(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'raw' AND table_name = 'worldbank_imports_1y'
        )
    """
    )
    table_exists = cur.fetchone()[0]

    if table_exists:
        cur.execute("SELECT COUNT(*) FROM raw.worldbank_imports_1y")
        existing_count = cur.fetchone()[0]
        print(f"⚠️  Table already exists with {existing_count} rows")
        print("Dropping and recreating...")
        cur.execute("DROP TABLE raw.worldbank_imports_1y")

    # Create table
    cur.execute(
        """
        CREATE TABLE raw.worldbank_imports_1y (
            id SERIAL PRIMARY KEY,
            as_of_date DATE NOT NULL,
            country_code VARCHAR(10) NOT NULL,
            country_name VARCHAR(100),
            region VARCHAR(100),
            sub_region VARCHAR(100),
            intermediate_region VARCHAR(100),
            indicator_code VARCHAR(50),
            indicator_name VARCHAR(200),
            year INTEGER NOT NULL,
            imports_pct_gdp FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    cur.execute(
        "CREATE INDEX idx_wb_imports_date ON raw.worldbank_imports_1y(as_of_date)"
    )
    cur.execute(
        "CREATE INDEX idx_wb_imports_country ON raw.worldbank_imports_1y(country_code)"
    )
    conn.commit()
    print("✅ Created table raw.worldbank_imports_1y")

    # Insert data in batches
    inserted = 0
    batch_size = 1000

    for _, row in df.iterrows():
        cur.execute(
            """
            INSERT INTO raw.worldbank_imports_1y 
            (as_of_date, country_code, country_name, region, sub_region, 
             intermediate_region, indicator_code, indicator_name, year, imports_pct_gdp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
            (
                row["as_of_date"],
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
