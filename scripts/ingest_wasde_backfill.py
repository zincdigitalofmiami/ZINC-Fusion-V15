#!/usr/bin/env python3
"""
WASDE Backfill Ingestion Script

Ingests historical WASDE data (2010-2019) into supply.usda_wasde_1m
Careful mapping from downloaded CSV format to DB schema.

RUNS ONE TIME ONLY - for backfill.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Configuration - exact mappings based on current DB values
RELEVANT_COMMODITIES = ["Soybeans", "Soybean Oil", "Soybean Meal"]

# Map downloaded 'region' → DB 'country'
REGION_TO_COUNTRY = {
    "United States": "United States",
    "Argentina": "Argentina",
    "Brazil": "Brazil",
    "China": "China",
    "World 2/": "World",
    "World  2/": "World",
}

# Map downloaded 'item' → DB 'metric'
ITEM_TO_METRIC = {
    "Production": "production",
    "Production 3/": "production",
    "Production 4/": "production",
    "Exports": "exports",
    "Imports": "imports",  # New metric if needed
    "Ending Stocks": "ending_stocks",
    "Ending stocks": "ending_stocks",
    "Ending\r\nStocks": "ending_stocks",
    "Crushings": "crush",
    "Domestic Total": "consumption",
    "Domestic\r\nTotal": "consumption",
    "Domestic Disappearance": "consumption",
    "Use, Total (Crushings+Exports+Seed+Residual)": "consumption",
    "Use, Total (Domestic Disappearance+Exports)": "consumption",
}


def load_wasde_csv(filepath: str) -> pd.DataFrame:
    """Load and filter WASDE CSV to relevant data."""
    print(f"Loading {filepath}...")
    df = pd.read_csv(filepath)
    print(f"  Total rows: {len(df)}")

    # Filter to relevant commodities
    df = df[df["commodity"].isin(RELEVANT_COMMODITIES)]
    print(f"  After commodity filter: {len(df)}")

    # Filter to relevant regions
    df = df[df["region"].isin(REGION_TO_COUNTRY.keys())]
    print(f"  After region filter: {len(df)}")

    # Filter to relevant items/metrics
    df = df[df["item"].isin(ITEM_TO_METRIC.keys())]
    print(f"  After item filter: {len(df)}")

    # CRITICAL: Keep only current-year projections (Proj.) not historical
    # Each WASDE report has multiple years - we want the forward-looking one
    df = df[df["year"].str.contains("Proj", na=False)]
    print(f"  After Proj-only filter: {len(df)}")

    # Take only the latest period within each report (e.g., Dec not Nov)
    # Group by report_month, commodity, region, item, year and take last period
    df = (
        df.sort_values("period")
        .groupby(
            ["report_month", "commodity", "region", "item", "year"], as_index=False
        )
        .last()
    )
    print(f"  After latest-period filter: {len(df)}")

    return df


def transform_row(row: pd.Series) -> dict:
    """Transform one CSV row to DB format."""
    # Parse report_month (YYYY-MM) to date (first of month)
    event_date = datetime.strptime(row["report_month"], "%Y-%m").date()

    return {
        "event_date": event_date,
        "commodity": row["commodity"],
        "country": REGION_TO_COUNTRY[row["region"]],
        "metric": ITEM_TO_METRIC[row["item"]],
        "value": float(row["value"]) if pd.notna(row["value"]) else None,
        "unit": "MMT",  # Standard unit for WASDE
        "source": "usda_wasde_backfill",
    }


def get_existing_dates(conn, cutoff_date: str = "2020-01-01") -> set:
    """Get dates already in DB before cutoff."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT event_date
        FROM supply.usda_wasde_1m
        WHERE event_date < %s
    """,
        (cutoff_date,),
    )
    return {row[0] for row in cur.fetchall()}


def insert_rows(conn, rows: list, batch_size: int = 1000) -> int:
    """Insert rows in batches."""
    if not rows:
        return 0

    cur = conn.cursor()
    inserted = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]

        # Build INSERT with ON CONFLICT DO NOTHING to skip duplicates
        values_list = []
        params = []
        for row in batch:
            values_list.append("(%s, %s, %s, %s, %s, %s, %s, NOW())")
            params.extend(
                [
                    row["event_date"],
                    row["commodity"],
                    row["country"],
                    row["metric"],
                    row["value"],
                    row["unit"],
                    row["source"],
                ]
            )

        sql = f"""
            INSERT INTO supply.usda_wasde_1m
            (event_date, commodity, country, metric, value, unit, source, ingested_at)
            VALUES {", ".join(values_list)}
            ON CONFLICT DO NOTHING
        """

        try:
            cur.execute(sql, params)
            inserted += cur.rowcount
        except Exception as e:
            print(f"Error inserting batch {i // batch_size}: {e}")
            conn.rollback()
            raise

    conn.commit()
    return inserted


def main():
    # Find the WASDE data file
    data_dir = Path(__file__).parent.parent / "data" / "downloads"
    wasde_files = list(data_dir.glob("WASDE_DATA_*.csv"))

    if not wasde_files:
        print("ERROR: No WASDE_DATA_*.csv found in data/downloads/")
        sys.exit(1)

    csv_path = wasde_files[0]

    # Connect to database
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))

    # Check current state BEFORE
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*), MIN(event_date), MAX(event_date) FROM supply.usda_wasde_1m"
    )
    before = cur.fetchone()
    print(f"\nBEFORE: {before[0]} rows, {before[1]} to {before[2]}")

    # Load and filter CSV
    df = load_wasde_csv(str(csv_path))

    # Get unique years to understand what we're backfilling
    df["year_month"] = pd.to_datetime(df["report_month"])
    print(
        f"\nDownloaded data date range: {df['year_month'].min()} to {df['year_month'].max()}"
    )

    # Only process pre-2020 data (backfill period)
    df_backfill = df[df["year_month"] < "2020-01-01"]
    print(f"Rows in backfill period (pre-2020): {len(df_backfill)}")

    if len(df_backfill) == 0:
        print("No backfill data found!")
        conn.close()
        return

    # Transform rows
    print("\nTransforming rows...")
    rows = []
    errors = 0
    for _, row in df_backfill.iterrows():
        try:
            transformed = transform_row(row)
            if transformed["value"] is not None:  # Skip null values
                rows.append(transformed)
        except Exception as e:
            errors += 1
            if errors < 5:
                print(f"  Transform error: {e}")

    print(f"  Transformed: {len(rows)} rows, {errors} errors")

    # Remove duplicates (same date/commodity/country/metric)
    seen = set()
    unique_rows = []
    for row in rows:
        key = (row["event_date"], row["commodity"], row["country"], row["metric"])
        if key not in seen:
            seen.add(key)
            unique_rows.append(row)

    print(f"  After dedup: {len(unique_rows)} unique rows")

    # Insert
    print("\nInserting into database...")
    inserted = insert_rows(conn, unique_rows)
    print(f"  Inserted: {inserted} rows")

    # Check state AFTER
    cur.execute(
        "SELECT COUNT(*), MIN(event_date), MAX(event_date) FROM supply.usda_wasde_1m"
    )
    after = cur.fetchone()
    print(f"\nAFTER: {after[0]} rows, {after[1]} to {after[2]}")
    print(f"Net change: +{after[0] - before[0]} rows")

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
