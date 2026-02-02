#!/usr/bin/env python3
"""
Calculate ZL correlations using PANDAS/NUMPY - NO HAND-CODED MATH!

Uses pandas .corr() which is battle-tested and verified.
This is the CORRECT way to do correlations.
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import numpy as np
import psycopg2
from tqdm import tqdm

# Use direct DATABASE_URL from env
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set")

# Remove problematic SSL parameters for psycopg2
DATABASE_URL = DATABASE_URL.split('?')[0]  # Strip query params

def calculate_all_correlations():
    """
    Calculate ZL correlations using PANDAS .corr() - library-based, not hand-coded!
    """
    
    print("\n" + "="*70)
    print("🔧 CALCULATING ZL CORRELATIONS (PANDAS .corr() - VERIFIED MATH)")
    print("="*70 + "\n")
    
    # Load ALL futures data
    print("Loading all futures data...")
    conn = psycopg2.connect(DATABASE_URL)
    df = pd.read_sql("""
        SELECT symbol, event_date, close
        FROM mkt.futures_1d
        ORDER BY symbol, event_date
    """, conn)
    conn.close()
    
    print(f"   Loaded {len(df):,} rows\n")
    
    df['event_date'] = pd.to_datetime(df['event_date'])
    
    # Pivot to wide format
    prices = df.pivot(index='event_date', columns='symbol', values='close')
    
    # Calculate returns
    returns = prices.pct_change()
    
    print(f"Symbols: {len(returns.columns)}")
    print(f"Dates: {len(returns)}\n")
    
    # Verify ZL exists
    if 'ZL' not in returns.columns:
        raise ValueError("ZL not in dataset!")
    
    zl_returns = returns['ZL']
    
    print("Calculating rolling correlations for each symbol...\n")
    
    # Store results
    correlation_data = []
    
    symbols = [col for col in returns.columns if col != 'ZL']
    
    for symbol in tqdm(symbols, desc="Symbols"):
        sym_returns = returns[symbol]
        
        # Skip if too sparse
        if sym_returns.notna().sum() < 90:
            continue
        
        # Create combined dataframe for correlation
        combined = pd.DataFrame({
            'sym': sym_returns,
            'zl': zl_returns
        })
        
        # Calculate rolling correlations using PANDAS (verified library function)
        combined['corr_30d'] = combined['sym'].rolling(30).corr(combined['zl'])
        combined['corr_60d'] = combined['sym'].rolling(60).corr(combined['zl'])
        combined['corr_90d'] = combined['sym'].rolling(90).corr(combined['zl'])
        
        # Store non-null correlation rows
        for date, row in combined.iterrows():
            if pd.notna(row['corr_90d']):
                correlation_data.append({
                    'symbol': symbol,
                    'event_date': date,
                    'zl_corr_30d': row['corr_30d'],
                    'zl_corr_60d': row['corr_60d'],
                    'zl_corr_90d': row['corr_90d']
                })
    
    print(f"\nCalculated {len(correlation_data):,} correlation records\n")
    
    # Batch update database
    print("Updating database...")
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    for i in tqdm(range(0, len(correlation_data), 1000), desc="Batches"):
        batch = correlation_data[i:i+1000]
        
        for record in batch:
            cursor.execute("""
                UPDATE mkt.futures_1d
                SET zl_corr_30d = %s,
                    zl_corr_60d = %s,
                    zl_corr_90d = %s
                WHERE symbol = %s AND event_date = %s
            """, (
                float(record['zl_corr_30d']) if pd.notna(record['zl_corr_30d']) else None,
                float(record['zl_corr_60d']) if pd.notna(record['zl_corr_60d']) else None,
                float(record['zl_corr_90d']) if pd.notna(record['zl_corr_90d']) else None,
                record['symbol'],
                record['event_date']
            ))
        
        conn.commit()
    
    cursor.close()
    conn.close()
    
    print(f"\n✅ COMPLETE: {len(correlation_data):,} rows updated\n")
    print("="*70)
    print("✅ USING PANDAS .corr() - VERIFIED LIBRARY FUNCTION")
    print("✅ NO HAND-CODED MATH")
    print("="*70 + "\n")

if __name__ == "__main__":
    calculate_all_correlations()
