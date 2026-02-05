#!/usr/bin/env python3
"""
Recalculate indicators using ONLY TA-Lib (proven to work).

For Gavin's testing - get it working first with TA-Lib,
then add Hurst/Schaff separately if needed.
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import numpy as np
import psycopg2
from tqdm import tqdm
from fusion.features.elite_TALIB_ONLY import EliteTALibOnly

# Get DATABASE_URL and strip query params
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Try from .env.local
    env_file = Path(__file__).parent.parent / "frontend" / ".env.local"
    with open(env_file) as f:
        for line in f:
            if line.startswith("DATABASE_URL="):
                DATABASE_URL = line.split("=", 1)[1].strip().strip('"')
                break

# Strip problematic params
DATABASE_URL = DATABASE_URL.split('?')[0] if DATABASE_URL else None

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found")


def main():
    print("\n" + "="*70)
    print("🏦 RECALCULATING WITH TA-LIB ONLY (INDUSTRY STANDARD)")
    print("="*70 + "\n")
    
    conn = psycopg2.connect(DATABASE_URL)
    
    # Get all symbols
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT symbol FROM mkt.futures_1d ORDER BY symbol")
    symbols = [row[0] for row in cursor.fetchall()]
    cursor.close()
    
    print(f"Processing {len(symbols)} symbols with TA-Lib...\n")
    
    total_updated = 0
    
    for symbol in tqdm(symbols, desc="Symbols"):
        try:
            # Load data
            df = pd.read_sql(f"""
                SELECT event_date, open, high, low, close, volume
                FROM mkt.futures_1d
                WHERE symbol = '{symbol}'
                ORDER BY event_date
            """, conn)
            
            if len(df) < 100:
                continue
            
            df['event_date'] = pd.to_datetime(df['event_date'])
            df = df.set_index('event_date')
            
            # Calculate with TA-Lib ONLY
            calc = EliteTALibOnly(df)
            result = calc.calculate_all()
            
            # Update database
            cursor = conn.cursor()
            for date, row in result.iterrows():
                if pd.notna(row.get('rsi_14')):
                    cursor.execute("""
                        UPDATE mkt.futures_1d
                        SET rsi_2=%s, rsi_14=%s, macd=%s, macd_signal=%s, macd_histogram=%s,
                            bb_upper=%s, bb_middle=%s, bb_lower=%s, bb_percent_b=%s,
                            atr_10=%s, atr_14=%s, atr_50=%s, atr_ratio=%s,
                            adx=%s, stoch_k=%s, stoch_d=%s, cci_14=%s, cci_50=%s,
                            kama_10=%s, hma_20=%s, alma_50=%s, mcginley_dynamic=%s,
                            obv=%s, cmf_21=%s, returns_1d=%s, log_returns_1d=%s,
                            range_pct=%s, garman_klass_vol=%s, yang_zhang_vol=%s
                        WHERE symbol=%s AND event_date=%s
                    """, (
                        float(row['rsi_2']) if pd.notna(row.get('rsi_2')) else None,
                        float(row['rsi_14']) if pd.notna(row.get('rsi_14')) else None,
                        float(row['macd']) if pd.notna(row.get('macd')) else None,
                        float(row['macd_signal']) if pd.notna(row.get('macd_signal')) else None,
                        float(row['macd_histogram']) if pd.notna(row.get('macd_histogram')) else None,
                        float(row['bb_upper']) if pd.notna(row.get('bb_upper')) else None,
                        float(row['bb_middle']) if pd.notna(row.get('bb_middle')) else None,
                        float(row['bb_lower']) if pd.notna(row.get('bb_lower')) else None,
                        float(row['bb_percent_b']) if pd.notna(row.get('bb_percent_b')) else None,
                        float(row['atr_10']) if pd.notna(row.get('atr_10')) else None,
                        float(row['atr_14']) if pd.notna(row.get('atr_14')) else None,
                        float(row['atr_50']) if pd.notna(row.get('atr_50')) else None,
                        float(row['atr_ratio']) if pd.notna(row.get('atr_ratio')) else None,
                        float(row['adx']) if pd.notna(row.get('adx')) else None,
                        float(row['stoch_k']) if pd.notna(row.get('stoch_k')) else None,
                        float(row['stoch_d']) if pd.notna(row.get('stoch_d')) else None,
                        float(row['cci_14']) if pd.notna(row.get('cci_14')) else None,
                        float(row['cci_50']) if pd.notna(row.get('cci_50')) else None,
                        float(row['kama_10']) if pd.notna(row.get('kama_10')) else None,
                        float(row['hma_20']) if pd.notna(row.get('hma_20')) else None,
                        float(row['alma_50']) if pd.notna(row.get('alma_50')) else None,
                        float(row['mcginley_dynamic']) if pd.notna(row.get('mcginley_dynamic')) else None,
                        float(row['obv']) if pd.notna(row.get('obv')) else None,
                        float(row['cmf_21']) if pd.notna(row.get('cmf_21')) else None,
                        float(row['returns_1d']) if pd.notna(row.get('returns_1d')) else None,
                        float(row['log_returns_1d']) if pd.notna(row.get('log_returns_1d')) else None,
                        float(row['range_pct']) if pd.notna(row.get('range_pct')) else None,
                        float(row['garman_klass_vol']) if pd.notna(row.get('garman_klass_vol')) else None,
                        float(row['yang_zhang_vol']) if pd.notna(row.get('yang_zhang_vol')) else None,
                        symbol, date
                    ))
                    total_updated += 1
            
            conn.commit()
            cursor.close()
            
        except Exception as e:
            print(f"\n❌ {symbol}: {e}")
            continue
    
    conn.close()
    
    print(f"\n✅ COMPLETE: {total_updated:,} rows with TA-Lib indicators")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
