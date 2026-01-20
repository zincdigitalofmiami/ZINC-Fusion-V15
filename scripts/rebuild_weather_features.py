#!/usr/bin/env python3
"""
Rebuild features.weather_1d from alt.weather_1d.

Aggregates raw weather station data into regional daily features:
- AR (Argentina), BR (Brazil), US (United States)
- Temperature (avg, min, max), Precipitation, Snow, Humidity, Wind

Usage:
    python scripts/rebuild_weather_features.py
    python scripts/rebuild_weather_features.py --start 2020-01-01
    python scripts/rebuild_weather_features.py --dry-run
"""

import os
import sys
import argparse
from datetime import datetime

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Regions to aggregate
REGIONS = ["AR", "BR", "US"]

# Feature columns to aggregate (mean by default, sum for precipitation/snow)
MEAN_COLS = ["tavg_c", "tmin_c", "tmax_c", "rhav_pct", "awnd_ms"]
SUM_COLS = ["prcp_mm", "snow_mm"]


def load_raw_weather(conn, start_date: str) -> pd.DataFrame:
    """Load raw weather data from alt.weather_1d."""
    query = """
        SELECT
            event_date::date as trade_date,
            CASE
                WHEN country = 'Argentina' THEN 'AR'
                WHEN country = 'Brazil' THEN 'BR'
                WHEN country = 'United States' THEN 'US'
                ELSE country
            END as country,
            tavg_c,
            tmin_c,
            tmax_c,
            prcp_mm,
            snow_mm,
            rhav_pct,
            awnd_ms
        FROM alt.weather_1d
        WHERE event_date >= %s
          AND country IN ('Argentina', 'Brazil', 'United States')
        ORDER BY event_date, country
    """
    df = pd.read_sql(query, conn, params=[start_date])
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    return df


def aggregate_by_region(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate weather data by date and region."""
    if df.empty:
        return pd.DataFrame()

    # Group by date and country
    grouped = df.groupby(['trade_date', 'country'])

    # Aggregate means
    means = grouped[MEAN_COLS].mean()

    # Aggregate sums (regional totals)
    sums = grouped[SUM_COLS].sum()

    # Also compute cumulative precipitation (monthly running total)
    df['month'] = df['trade_date'].dt.to_period('M')
    monthly_prcp = df.groupby(['month', 'country'])['prcp_mm'].cumsum()

    # Combine
    result = pd.concat([means, sums], axis=1).reset_index()

    return result


def pivot_to_features(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot regional data to wide format for features table."""
    if df.empty:
        return pd.DataFrame()

    # Create feature columns: wx_{region}_{metric}
    records = []

    for trade_date, group in df.groupby('trade_date'):
        row = {'trade_date': trade_date}

        for _, r in group.iterrows():
            region = r['country'].lower()

            row[f'wx_{region}_tavg_c'] = r.get('tavg_c')
            row[f'wx_{region}_tmin_c'] = r.get('tmin_c')
            row[f'wx_{region}_tmax_c'] = r.get('tmax_c')
            row[f'wx_{region}_prcp_mm'] = r.get('prcp_mm')
            row[f'wx_{region}_snow_mm'] = r.get('snow_mm')
            row[f'wx_{region}_rhav_pct'] = r.get('rhav_pct')
            row[f'wx_{region}_awnd_ms'] = r.get('awnd_ms')

            # Running total for precipitation (placeholder - compute separately)
            row[f'wx_{region}_prcp_mm_total'] = r.get('prcp_mm')

        records.append(row)

    return pd.DataFrame(records)


def compute_running_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Compute monthly running totals for precipitation."""
    df = df.copy()
    df['month'] = pd.to_datetime(df['trade_date']).dt.to_period('M')

    for region in ['ar', 'br', 'us']:
        prcp_col = f'wx_{region}_prcp_mm'
        total_col = f'wx_{region}_prcp_mm_total'

        if prcp_col in df.columns:
            # Cumulative sum within each month
            df[total_col] = df.groupby('month')[prcp_col].cumsum()

    df = df.drop(columns=['month'])
    return df


def insert_features(conn, df: pd.DataFrame, dry_run: bool = False):
    """Insert features into features.weather_1d."""
    if df.empty:
        print("No data to insert")
        return

    if dry_run:
        print(f"\n[DRY RUN] Would insert {len(df)} rows")
        print(f"Date range: {df['trade_date'].min()} to {df['trade_date'].max()}")
        print(f"\nSample:")
        print(df.head(3).to_string())
        return

    cur = conn.cursor()

    # Get existing columns in features.weather_1d (exclude id and auto-generated)
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'features' AND table_name = 'weather_1d'
        AND column_name NOT IN ('id')
    """)
    existing_cols = {r[0] for r in cur.fetchall()}

    # Filter to only columns that exist in the table
    df_cols = [c for c in df.columns if c in existing_cols]
    df_insert = df[df_cols].copy()

    # Replace NaN with None
    df_insert = df_insert.where(pd.notnull(df_insert), None)

    # Delete existing data in date range
    min_date = df_insert['trade_date'].min()
    max_date = df_insert['trade_date'].max()

    cur.execute(
        "DELETE FROM features.weather_1d WHERE trade_date >= %s AND trade_date <= %s",
        (min_date, max_date)
    )
    deleted = cur.rowcount
    print(f"Deleted {deleted} existing rows in date range")

    # Prepare insert
    columns = df_insert.columns.tolist()
    values = [tuple(row) for row in df_insert.values]

    insert_sql = f"""
        INSERT INTO features.weather_1d ({', '.join(columns)})
        VALUES %s
    """

    execute_values(cur, insert_sql, values, page_size=1000)
    conn.commit()

    print(f"Inserted {len(df_insert)} rows into features.weather_1d")


def main():
    parser = argparse.ArgumentParser(description="Rebuild features.weather_1d from alt.weather_1d")
    parser.add_argument("--start", default="2000-01-01", help="Start date (default: 2000-01-01)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without inserting")
    args = parser.parse_args()

    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL not found in environment")

    print("=" * 60)
    print("REBUILD WEATHER FEATURES")
    print("=" * 60)
    print(f"Start date: {args.start}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")
    print()

    conn = psycopg2.connect(DATABASE_URL)

    try:
        # Load raw weather data
        print("[1/4] Loading raw weather data from alt.weather_1d...")
        raw_df = load_raw_weather(conn, args.start)
        print(f"      Loaded {len(raw_df):,} rows")

        if raw_df.empty:
            print("No weather data found")
            return

        # Aggregate by region
        print("[2/4] Aggregating by region...")
        agg_df = aggregate_by_region(raw_df)
        print(f"      Aggregated to {len(agg_df):,} region-day rows")

        # Pivot to wide format
        print("[3/4] Pivoting to feature format...")
        features_df = pivot_to_features(agg_df)
        features_df = compute_running_totals(features_df)
        print(f"      Created {len(features_df):,} feature rows with {len(features_df.columns)} columns")

        # Insert
        print("[4/4] Inserting features...")
        insert_features(conn, features_df, args.dry_run)

        print()
        print("=" * 60)
        print("COMPLETE")
        print("=" * 60)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
