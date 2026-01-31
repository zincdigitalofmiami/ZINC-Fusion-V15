#!/usr/bin/env python3
"""
Calculate ZL correlations for ALL symbols in mkt.futures_1d

This pre-calculates 30d, 60d, and 90d correlations with ZL (soybean oil)
so they're ready for training without real-time calculation.

CRITICAL for FX specialist - currency/commodity correlations drive carry trade signals.
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import numpy as np
from fusion.db import get_read_engine, get_write_connection
from tqdm import tqdm

def calculate_correlations():
    """Calculate and update ZL correlations for all symbols."""
    
    print("\n" + "="*70)
    print("🔧 CALCULATING ZL CORRELATIONS FOR ALL FUTURES")
    print("="*70 + "\n")
    
    engine = get_read_engine()
    
    # Load ZL returns
    print("Loading ZL returns...")
    zl_df = pd.read_sql("""
        SELECT event_date, close
        FROM mkt.futures_1d
        WHERE symbol = 'ZL'
        ORDER BY event_date
    """, engine)
    zl_df['event_date'] = pd.to_datetime(zl_df['event_date'])
    zl_df = zl_df.set_index('event_date')
    zl_df['returns'] = zl_df['close'].pct_change()
    
    print(f"   ZL: {len(zl_df)} days\n")
    
    # Get all symbols
    symbols_df = pd.read_sql("""
        SELECT DISTINCT symbol 
        FROM mkt.futures_1d
        WHERE symbol != 'ZL'
        ORDER BY symbol
    """, engine)
    
    symbols = symbols_df['symbol'].tolist()
    print(f"Calculating correlations for {len(symbols)} symbols...\n")
    
    conn = get_write_connection()
    cursor = conn.cursor()
    
    updated_count = 0
    
    for symbol in tqdm(symbols, desc="Symbols"):
        # Load symbol data
        sym_df = pd.read_sql(f"""
            SELECT event_date, close
            FROM mkt.futures_1d
            WHERE symbol = '{symbol}'
            ORDER BY event_date
        """, engine)
        
        if len(sym_df) < 90:
            continue
            
        sym_df['event_date'] = pd.to_datetime(sym_df['event_date'])
        sym_df = sym_df.set_index('event_date')
        sym_df['returns'] = sym_df['close'].pct_change()
        
        # Merge with ZL
        merged = sym_df[['returns']].join(zl_df[['returns']], how='inner', rsuffix='_zl')
        
        if len(merged) < 90:
            continue
        
        # Calculate rolling correlations
        merged['corr_30d'] = merged['returns'].rolling(30).corr(merged['returns_zl'])
        merged['corr_60d'] = merged['returns'].rolling(60).corr(merged['returns_zl'])
        merged['corr_90d'] = merged['returns'].rolling(90).corr(merged['returns_zl'])
        
        # Update database
        for date, row in merged.iterrows():
            if pd.notna(row['corr_90d']):  # Only update if we have 90d (longest window)
                cursor.execute("""
                    UPDATE mkt.futures_1d
                    SET zl_corr_30d = %s,
                        zl_corr_60d = %s,
                        zl_corr_90d = %s
                    WHERE symbol = %s AND event_date = %s
                """, (
                    float(row['corr_30d']) if pd.notna(row['corr_30d']) else None,
                    float(row['corr_60d']) if pd.notna(row['corr_60d']) else None,
                    float(row['corr_90d']) if pd.notna(row['corr_90d']) else None,
                    symbol,
                    date
                ))
                updated_count += 1
        
        conn.commit()
    
    cursor.close()
    conn.close()
    
    print(f"\n✅ Updated {updated_count} rows with ZL correlations")
    print("="*70 + "\n")

if __name__ == "__main__":
    calculate_correlations()
