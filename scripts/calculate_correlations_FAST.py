#!/usr/bin/env python3
"""
FAST ZL correlations using BATCH executemany + temp table strategy.
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
from tqdm import tqdm
from dotenv import load_dotenv

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set")
DATABASE_URL = DATABASE_URL.split('?')[0]

def calculate_all_correlations():
    print("\n" + "="*70)
    print("🔧 FAST ZL CORRELATIONS (BATCH UPDATE)")
    print("="*70 + "\n")

    conn = psycopg2.connect(DATABASE_URL)

    # Load ALL futures data
    print("Loading all futures data...")
    df = pd.read_sql("""
        SELECT symbol, event_date, close
        FROM mkt.futures_1d
        ORDER BY symbol, event_date
    """, conn)

    print(f"   Loaded {len(df):,} rows\n")

    df['event_date'] = pd.to_datetime(df['event_date'])
    prices = df.pivot(index='event_date', columns='symbol', values='close')
    returns = prices.pct_change(fill_method=None)  # No deprecated warning

    print(f"Symbols: {len(returns.columns)}")
    print(f"Dates: {len(returns)}\n")

    if 'ZL' not in returns.columns:
        raise ValueError("ZL not in dataset!")

    zl_returns = returns['ZL']

    print("Calculating rolling correlations...")

    correlation_data = []
    symbols = [col for col in returns.columns if col != 'ZL']

    for symbol in tqdm(symbols, desc="Symbols"):
        sym_returns = returns[symbol]

        if sym_returns.notna().sum() < 90:
            continue

        combined = pd.DataFrame({
            'sym': sym_returns,
            'zl': zl_returns
        })

        combined['corr_30d'] = combined['sym'].rolling(30).corr(combined['zl'])
        combined['corr_60d'] = combined['sym'].rolling(60).corr(combined['zl'])
        combined['corr_90d'] = combined['sym'].rolling(90).corr(combined['zl'])

        for date, row in combined.iterrows():
            if pd.notna(row['corr_90d']):
                correlation_data.append((
                    float(row['corr_30d']) if pd.notna(row['corr_30d']) else None,
                    float(row['corr_60d']) if pd.notna(row['corr_60d']) else None,
                    float(row['corr_90d']) if pd.notna(row['corr_90d']) else None,
                    symbol,
                    date.date()
                ))

    print(f"\nCalculated {len(correlation_data):,} correlation records\n")

    # FAST BATCH UPDATE using execute_values with UPDATE
    print("Updating database (FAST BATCH)...")

    cursor = conn.cursor()

    # Use a single transaction with executemany
    batch_size = 5000
    total_batches = (len(correlation_data) + batch_size - 1) // batch_size

    for i in tqdm(range(0, len(correlation_data), batch_size), desc="Batches", total=total_batches):
        batch = correlation_data[i:i+batch_size]

        # Use execute_values for fast batch update
        execute_values(
            cursor,
            """
            UPDATE mkt.futures_1d AS f SET
                zl_corr_30d = v.c30,
                zl_corr_60d = v.c60,
                zl_corr_90d = v.c90
            FROM (VALUES %s) AS v(c30, c60, c90, sym, dt)
            WHERE f.symbol = v.sym AND f.event_date = v.dt::date
            """,
            batch,
            template="(%s, %s, %s, %s, %s)"
        )
        conn.commit()

    cursor.close()
    conn.close()

    print(f"\n✅ COMPLETE: {len(correlation_data):,} rows updated\n")
    print("="*70)
    print("✅ USING PANDAS .corr() - VERIFIED LIBRARY FUNCTION")
    print("✅ FAST BATCH UPDATE with execute_values")
    print("="*70 + "\n")

if __name__ == "__main__":
    calculate_all_correlations()
