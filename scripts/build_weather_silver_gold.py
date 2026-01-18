# DEPRECATED: This script builds legacy medallion tables (silver/gold).
# The v2 architecture uses features.* tables directly.
# See: alt.weather_1d, features.weather_1d
# TODO: Remove after 2026-03-01 if no issues.

#!/usr/bin/env python3
"""
Build Weather Silver and Gold Tables

Transforms raw.weather_noaa_1d → silver.weather_agg_1d → gold.weather_features_1d

Flow:
1. Silver: Aggregate daily observations by region (deduplicate stations)
2. Gold: Create derived features (anomalies, rolling stats, growing season indicators)
"""

import os
import sys
from datetime import datetime

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

# Regions relevant for soybean/crush:
# US Corn Belt: IA, IL, IN, MN, MO, NE (primary US soy production)
# Brazil: PR, RS, MT, MS, MG, SP, PA (major soy states)
# Argentina: BA, SF, CO, ER, CR, CH, LP, SE, FO, MZ (pampas region)

REGIONS_US = ["US_IA", "US_IL", "US_IN", "US_MN", "US_MO", "US_NE"]
REGIONS_BR = ["BR_PR", "BR_RS", "BR_MT", "BR_MS", "BR_MG", "BR_SP", "BR_PA", "BR_NE"]
REGIONS_AR = [
    "AR_BA",
    "AR_SF",
    "AR_CO",
    "AR_ER",
    "AR_CR",
    "AR_CH",
    "AR_LP",
    "AR_SE",
    "AR_FO",
    "AR_MZ",
]
ALL_REGIONS = REGIONS_US + REGIONS_BR + REGIONS_AR


def get_connection():
    """Get database connection."""
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def build_silver(conn) -> int:
    """
    Build silver.weather_agg_1d from raw.weather_noaa_1d.

    Aggregates multiple stations per region into a single daily observation.
    """
    print("\n" + "=" * 60)
    print("BUILDING silver.weather_agg_1d")
    print("=" * 60)

    # Aggregate raw data by region and date
    query = """
        SELECT 
            event_date,
            region,
            AVG(tavg_c) as tavg_c,
            AVG(tmin_c) as tmin_c,
            AVG(tmax_c) as tmax_c,
            AVG(prcp_mm) as prcp_mm,
            SUM(prcp_mm) as prcp_mm_total,
            AVG(snow_mm) as snow_mm,
            AVG(rhav_pct) as rhav_pct,
            AVG(awnd_ms) as awnd_ms,
            COUNT(DISTINCT station_id) as station_count
        FROM raw.weather_noaa_1d
        WHERE region IS NOT NULL
        GROUP BY event_date, region
        ORDER BY event_date, region
    """

    print("   Loading raw weather data...")
    df = pd.read_sql(query, conn)
    print(
        f"   Loaded {len(df):,} aggregated rows from {df['region'].nunique()} regions"
    )

    # Create silver table
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS silver.weather_agg_1d CASCADE")
        cur.execute(
            """
            CREATE TABLE silver.weather_agg_1d (
                id SERIAL PRIMARY KEY,
                event_date DATE NOT NULL,
                region VARCHAR(20) NOT NULL,
                tavg_c FLOAT,
                tmin_c FLOAT,
                tmax_c FLOAT,
                prcp_mm FLOAT,
                prcp_mm_total FLOAT,
                snow_mm FLOAT,
                rhav_pct FLOAT,
                awnd_ms FLOAT,
                station_count INT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(event_date, region)
            )
        """
        )
        cur.execute(
            "CREATE INDEX idx_silver_weather_date ON silver.weather_agg_1d(event_date)"
        )
        cur.execute(
            "CREATE INDEX idx_silver_weather_region ON silver.weather_agg_1d(region)"
        )

    # Insert data
    cols = [
        "event_date",
        "region",
        "tavg_c",
        "tmin_c",
        "tmax_c",
        "prcp_mm",
        "prcp_mm_total",
        "snow_mm",
        "rhav_pct",
        "awnd_ms",
        "station_count",
    ]
    insert_sql = f"""
        INSERT INTO silver.weather_agg_1d ({','.join(cols)})
        VALUES %s
        ON CONFLICT (event_date, region) DO UPDATE SET
            tavg_c = EXCLUDED.tavg_c,
            tmin_c = EXCLUDED.tmin_c,
            tmax_c = EXCLUDED.tmax_c,
            prcp_mm = EXCLUDED.prcp_mm,
            prcp_mm_total = EXCLUDED.prcp_mm_total,
            snow_mm = EXCLUDED.snow_mm,
            rhav_pct = EXCLUDED.rhav_pct,
            awnd_ms = EXCLUDED.awnd_ms,
            station_count = EXCLUDED.station_count
    """

    values = [tuple(row[col] for col in cols) for _, row in df.iterrows()]

    with conn.cursor() as cur:
        execute_values(cur, insert_sql, values, page_size=1000)

    conn.commit()
    print(f"   ✅ Inserted {len(df):,} rows into silver.weather_agg_1d")

    return len(df)


def build_gold(conn) -> int:
    """
    Build gold.weather_features_1d from silver.weather_agg_1d.

    Creates derived features for ML training:
    - Regional aggregates (US, BR, AR)
    - Temperature anomalies (deviation from 30-day rolling mean)
    - Precipitation anomalies
    - Growing degree days (GDD)
    - Rolling statistics (7d, 14d, 30d)
    """
    print("\n" + "=" * 60)
    print("BUILDING gold.weather_features_1d")
    print("=" * 60)

    # Load silver data
    query = """
        SELECT event_date, region, tavg_c, tmin_c, tmax_c, prcp_mm, prcp_mm_total, 
               snow_mm, rhav_pct, awnd_ms, station_count
        FROM silver.weather_agg_1d
        ORDER BY event_date, region
    """

    print("   Loading silver weather data...")
    df = pd.read_sql(query, conn)
    print(f"   Loaded {len(df):,} rows")

    # Pivot to wide format: one row per date, columns for each region
    print("   Pivoting to wide format...")

    # We'll create regional aggregates for US, BR, AR
    df["country"] = df["region"].str[:2]

    # Aggregate by country
    country_agg = (
        df.groupby(["event_date", "country"])
        .agg(
            {
                "tavg_c": "mean",
                "tmin_c": "mean",
                "tmax_c": "mean",
                "prcp_mm": "mean",
                "prcp_mm_total": "sum",
                "snow_mm": "mean",
                "rhav_pct": "mean",
                "awnd_ms": "mean",
                "station_count": "sum",
            }
        )
        .reset_index()
    )

    # Pivot countries to columns
    features = country_agg.pivot(index="event_date", columns="country")
    features.columns = [f"wx_{col[1].lower()}_{col[0]}" for col in features.columns]
    features = features.reset_index()

    print(f"   Created {len(features.columns)-1} base features")

    # Add derived features
    print("   Computing derived features...")

    # Temperature anomalies (deviation from 30-day rolling mean)
    for country in ["us", "br", "ar"]:
        col = f"wx_{country}_tavg_c"
        if col in features.columns:
            features[f"wx_{country}_temp_anom_30d"] = (
                features[col] - features[col].rolling(30, min_periods=7).mean()
            )
            # Temperature volatility (7-day rolling std)
            features[f"wx_{country}_temp_vol_7d"] = (
                features[col].rolling(7, min_periods=3).std()
            )

    # Precipitation anomalies
    for country in ["us", "br", "ar"]:
        col = f"wx_{country}_prcp_mm"
        if col in features.columns:
            # Precip anomaly vs 30-day rolling mean
            features[f"wx_{country}_prcp_anom_30d"] = (
                features[col] - features[col].rolling(30, min_periods=7).mean()
            )
            # 7-day cumulative precip
            features[f"wx_{country}_prcp_7d_sum"] = (
                features[col].rolling(7, min_periods=3).sum()
            )
            # 14-day cumulative precip
            features[f"wx_{country}_prcp_14d_sum"] = (
                features[col].rolling(14, min_periods=7).sum()
            )

    # Growing Degree Days (base 10°C for soybeans)
    for country in ["us", "br", "ar"]:
        tavg_col = f"wx_{country}_tavg_c"
        if tavg_col in features.columns:
            # GDD = max(0, Tavg - 10)
            features[f"wx_{country}_gdd_10c"] = (features[tavg_col] - 10).clip(lower=0)
            # Cumulative GDD (30-day rolling sum)
            features[f"wx_{country}_gdd_30d_sum"] = (
                features[f"wx_{country}_gdd_10c"].rolling(30, min_periods=7).sum()
            )

    # Drop rows with too many nulls (before 2005)
    features = features.dropna(thresh=len(features.columns) * 0.5)

    print(f"   Final feature count: {len(features.columns)-1}")
    print(
        f"   Date range: {features['event_date'].min()} → {features['event_date'].max()}"
    )

    # Rename event_date to trade_date for consistency
    features = features.rename(columns={"event_date": "trade_date"})

    # Create gold table
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS gold.weather_features_1d CASCADE")

        # Build CREATE TABLE dynamically
        col_defs = ["id SERIAL PRIMARY KEY", "trade_date DATE NOT NULL UNIQUE"]
        for col in features.columns:
            if col != "trade_date":
                col_defs.append(f"{col} FLOAT")
        col_defs.append("created_at TIMESTAMP DEFAULT NOW()")

        create_sql = f"CREATE TABLE gold.weather_features_1d ({', '.join(col_defs)})"
        cur.execute(create_sql)
        cur.execute(
            "CREATE INDEX idx_gold_weather_date ON gold.weather_features_1d(trade_date)"
        )

    # Insert data
    cols = [c for c in features.columns]
    insert_sql = f"""
        INSERT INTO gold.weather_features_1d ({','.join(cols)})
        VALUES %s
    """

    values = [tuple(row) for row in features.itertuples(index=False, name=None)]

    with conn.cursor() as cur:
        execute_values(cur, insert_sql, values, page_size=1000)

    conn.commit()
    print(f"   ✅ Inserted {len(features):,} rows into gold.weather_features_1d")

    return len(features)


def main():
    """Build weather silver and gold tables."""
    print("=" * 60)
    print("WEATHER DATA PIPELINE: raw → silver → gold")
    print("=" * 60)

    conn = get_connection()
    print("✅ Database connected")

    try:
        # Build silver
        silver_rows = build_silver(conn)

        # Build gold
        gold_rows = build_gold(conn)

        print("\n" + "=" * 60)
        print("✅ WEATHER PIPELINE COMPLETE")
        print(f"   Silver rows: {silver_rows:,}")
        print(f"   Gold rows: {gold_rows:,}")
        print("=" * 60)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
