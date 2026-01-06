#!/usr/bin/env python3
"""
Ingest CFTC Commitments of Index Traders Supplemental (CITS) data.

CITS is DIFFERENT from standard COT:
- Separates INDEX TRADERS (passive funds) from other categories
- Index traders are LONG-ONLY and price-insensitive (pension funds, ETFs)
- Covers 12 agricultural markets including soybean oil (7601)

This creates raw.cftc_cits_1w table.
"""

import os
import sys
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

# Contract code to symbol mapping
CONTRACT_SYMBOLS = {
    1602: "WHEAT_CBOT",  # Wheat
    1612: "WHEAT_KC",  # KC Wheat
    2602: "CORN",  # Corn
    5602: "SOYBEANS",  # Soybeans
    7601: "SOYBEAN_OIL",  # Soybean Oil (our target!)
    33661: "COTTON",  # Cotton
    54642: "FEEDER_CATTLE",  # Feeder Cattle
    57642: "LIVE_CATTLE",  # Live Cattle
    61641: "LEAN_HOGS",  # Lean Hogs
    73732: "SUGAR_11",  # Sugar No. 11
    80732: "COCOA",  # Cocoa
    83731: "COFFEE",  # Coffee
    26603: "SOYBEAN_MEAL",  # Soybean Meal
}


def create_cits_table(conn):
    """Create the CITS table if it doesn't exist."""
    cur = conn.cursor()

    # Check if table exists
    cur.execute(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'raw' AND table_name = 'cftc_cits_1w'
        )
    """
    )
    exists = cur.fetchone()[0]

    if exists:
        print("Table raw.cftc_cits_1w already exists")
        return False

    # Create table
    cur.execute(
        """
        CREATE TABLE raw.cftc_cits_1w (
            id SERIAL PRIMARY KEY,
            report_date DATE NOT NULL,
            contract_code INTEGER NOT NULL,
            symbol VARCHAR(50) NOT NULL,
            report_type VARCHAR(20) NOT NULL,
            
            -- Position data
            market_participation BIGINT,
            non_commercial_longs BIGINT,
            non_commercial_shorts BIGINT,
            non_commercial_spreads BIGINT,
            commercial_longs BIGINT,
            commercial_shorts BIGINT,
            total_reportable_longs BIGINT,
            total_reportable_shorts BIGINT,
            non_reportable_longs BIGINT,
            non_reportable_shorts BIGINT,
            
            -- Index trader specific (the key differentiator!)
            index_trader_longs BIGINT,
            index_trader_shorts BIGINT,
            
            -- Net positions (calculated)
            index_trader_net BIGINT,
            non_commercial_net BIGINT,
            commercial_net BIGINT,
            
            -- Metadata
            source VARCHAR(50) DEFAULT 'quandl_cits',
            ingested_at TIMESTAMP DEFAULT NOW(),
            
            UNIQUE(report_date, contract_code, report_type)
        )
    """
    )

    # Create indexes
    cur.execute("CREATE INDEX idx_cits_date ON raw.cftc_cits_1w(report_date)")
    cur.execute("CREATE INDEX idx_cits_symbol ON raw.cftc_cits_1w(symbol)")
    cur.execute(
        "CREATE INDEX idx_cits_date_symbol ON raw.cftc_cits_1w(report_date, symbol)"
    )

    conn.commit()
    print("✅ Created table raw.cftc_cits_1w")
    return True


def load_and_transform_cits(csv_path):
    """Load CITS CSV and transform for ingestion."""
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df):,} rows from {csv_path}")

    # Parse date
    df["report_date"] = pd.to_datetime(df["date"]).dt.date

    # Map contract codes to symbols
    df["symbol"] = df["contract_code"].map(CONTRACT_SYMBOLS)

    # Handle any unmapped codes
    unmapped = df[df["symbol"].isna()]["contract_code"].unique()
    if len(unmapped) > 0:
        print(f"⚠️ Unmapped contract codes: {unmapped}")
        df = df[df["symbol"].notna()]

    # The 'longs' and 'shorts' columns are the INDEX TRADER positions
    df["index_trader_longs"] = df["longs"].fillna(0).astype(int)
    df["index_trader_shorts"] = df["shorts"].fillna(0).astype(int)
    df["index_trader_net"] = df["index_trader_longs"] - df["index_trader_shorts"]

    # Calculate other net positions
    df["non_commercial_net"] = (
        df["non_commercial_longs"].fillna(0) - df["non_commercial_shorts"].fillna(0)
    ).astype(int)
    df["commercial_net"] = (
        df["commercial_longs"].fillna(0) - df["commercial_shorts"].fillna(0)
    ).astype(int)

    # Map report type
    df["report_type"] = df["type"]

    # Convert position columns to int
    int_cols = [
        "market_participation",
        "non_commercial_longs",
        "non_commercial_shorts",
        "non_commercial_spreads",
        "commercial_longs",
        "commercial_shorts",
        "total_reportable_longs",
        "total_reportable_shorts",
        "non_reportable_longs",
        "non_reportable_shorts",
    ]
    for col in int_cols:
        df[col] = df[col].fillna(0).astype(int)

    print(f"Transformed {len(df):,} rows")
    print(f"Date range: {df['report_date'].min()} to {df['report_date'].max()}")
    print(f"Symbols: {df['symbol'].nunique()}")

    return df


def ingest_cits(conn, df):
    """Insert CITS data into database."""
    cur = conn.cursor()

    # Prepare data for insertion
    columns = [
        "report_date",
        "contract_code",
        "symbol",
        "report_type",
        "market_participation",
        "non_commercial_longs",
        "non_commercial_shorts",
        "non_commercial_spreads",
        "commercial_longs",
        "commercial_shorts",
        "total_reportable_longs",
        "total_reportable_shorts",
        "non_reportable_longs",
        "non_reportable_shorts",
        "index_trader_longs",
        "index_trader_shorts",
        "index_trader_net",
        "non_commercial_net",
        "commercial_net",
    ]

    data = df[columns].values.tolist()

    # Insert in batches using ON CONFLICT to handle duplicates
    insert_sql = f"""
        INSERT INTO raw.cftc_cits_1w ({', '.join(columns)})
        VALUES %s
        ON CONFLICT (report_date, contract_code, report_type) DO UPDATE SET
            market_participation = EXCLUDED.market_participation,
            non_commercial_longs = EXCLUDED.non_commercial_longs,
            non_commercial_shorts = EXCLUDED.non_commercial_shorts,
            non_commercial_spreads = EXCLUDED.non_commercial_spreads,
            commercial_longs = EXCLUDED.commercial_longs,
            commercial_shorts = EXCLUDED.commercial_shorts,
            total_reportable_longs = EXCLUDED.total_reportable_longs,
            total_reportable_shorts = EXCLUDED.total_reportable_shorts,
            non_reportable_longs = EXCLUDED.non_reportable_longs,
            non_reportable_shorts = EXCLUDED.non_reportable_shorts,
            index_trader_longs = EXCLUDED.index_trader_longs,
            index_trader_shorts = EXCLUDED.index_trader_shorts,
            index_trader_net = EXCLUDED.index_trader_net,
            non_commercial_net = EXCLUDED.non_commercial_net,
            commercial_net = EXCLUDED.commercial_net,
            ingested_at = NOW()
    """

    batch_size = 5000
    total_inserted = 0

    for i in range(0, len(data), batch_size):
        batch = data[i : i + batch_size]
        execute_values(cur, insert_sql, batch, page_size=1000)
        total_inserted += len(batch)
        print(f"  Inserted {total_inserted:,} / {len(data):,} rows...")

    conn.commit()
    print(f"✅ Ingested {total_inserted:,} rows into raw.cftc_cits_1w")
    return total_inserted


def verify_ingestion(conn):
    """Verify the ingestion was successful."""
    cur = conn.cursor()

    print("\n=== Verification ===")

    # Total count
    cur.execute("SELECT COUNT(*) FROM raw.cftc_cits_1w")
    total = cur.fetchone()[0]
    print(f"Total rows: {total:,}")

    # By symbol
    cur.execute(
        """
        SELECT symbol, COUNT(*), MIN(report_date), MAX(report_date)
        FROM raw.cftc_cits_1w
        GROUP BY symbol
        ORDER BY symbol
    """
    )
    print("\nBy symbol:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,} rows | {row[2]} to {row[3]}")

    # ZL (Soybean Oil) specific
    cur.execute(
        """
        SELECT report_date, index_trader_net, non_commercial_net, commercial_net
        FROM raw.cftc_cits_1w
        WHERE symbol = 'SOYBEAN_OIL' AND report_type = 'CITS_ALL'
        ORDER BY report_date DESC
        LIMIT 5
    """
    )
    print("\nSoybean Oil (ZL) recent data:")
    for row in cur.fetchall():
        print(f"  {row[0]}: Index={row[1]:+,} NonComm={row[2]:+,} Comm={row[3]:+,}")


def main():
    # Connect to database
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    conn = psycopg2.connect(database_url)

    try:
        # Find CSV file
        csv_path = "data/downloads/QDL_CITS_93e6c9dacfd888d4275a50939e5b1a36.csv"
        if not os.path.exists(csv_path):
            print(f"ERROR: CSV not found at {csv_path}")
            sys.exit(1)

        # Create table
        create_cits_table(conn)

        # Load and transform data
        df = load_and_transform_cits(csv_path)

        # Ingest
        ingest_cits(conn, df)

        # Verify
        verify_ingestion(conn)

        print("\n✅ CITS ingestion complete!")

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
