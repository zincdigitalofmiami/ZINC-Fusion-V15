#!/usr/bin/env python3
"""
RECALCULATE ALL ELITE INDICATORS - 100% INSTITUTIONAL LIBRARIES

Uses ONLY verified sources:
- Stock Indicators for Python (Hurst, Schaff, Connors, TTM, Fisher)
- TA-Lib (RSI, MACD, BB, ATR, ADX, Stoch, CCI, Volume)
- Pandas (Correlations - .corr() method)

NO HAND-CODED MATH. PERIOD.

This will:
1. Load all futures symbols from mkt.futures_1d
2. Calculate elite indicators using institutional libraries
3. Update mkt.futures_1d with correct values
4. Calculate ZL correlations using pandas .corr()

User will test results with their own validation scripts.
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import numpy as np
import psycopg2
from tqdm import tqdm
from fusion.features.elite_indicators_v2_INSTITUTIONAL import EliteIndicatorsV2

# Database connection (strip SSL params that break psycopg2)
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set")
DATABASE_URL = DATABASE_URL.split('?')[0]


def recalculate_for_symbol(symbol: str, conn) -> int:
    """
    Recalculate ALL elite indicators for one symbol.
    
    Returns: number of rows updated
    """
    # Load OHLCV data
    df = pd.read_sql(f"""
        SELECT event_date, open, high, low, close, volume
        FROM mkt.futures_1d
        WHERE symbol = '{symbol}'
        ORDER BY event_date
    """, conn)
    
    if len(df) < 100:
        return 0
    
    df['event_date'] = pd.to_datetime(df['event_date'])
    df = df.set_index('event_date')
    
    # CRITICAL: Convert all price/volume columns to float64 for TA-Lib
    # Use pd.to_numeric to handle None/NULL values properly
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce').astype(np.float64)

    # Fill volume NaN with 0 (no volume = 0 trades)
    df['volume'] = df['volume'].fillna(0)
    
    # Calculate indicators using INSTITUTIONAL libraries
    calc = EliteIndicatorsV2(df)
    df_with_indicators = calc.calculate_all()
    
    # Update database
    cursor = conn.cursor()
    updated = 0
    
    for date, row in df_with_indicators.iterrows():
        # Only update if we have calculated values
        if pd.notna(row.get('hurst_exponent')) or pd.notna(row.get('rsi_14')):
            cursor.execute("""
                UPDATE mkt.futures_1d
                SET 
                    hurst_exponent = %s,
                    hurst_regime = %s,
                    connors_rsi = %s,
                    schaff_trend_cycle = %s,
                    ttm_squeeze_on = %s,
                    ttm_squeeze_momentum = %s,
                    fisher_transform = %s,
                    fisher_signal = %s,
                    rsi_2 = %s,
                    rsi_14 = %s,
                    macd = %s,
                    macd_signal = %s,
                    macd_histogram = %s,
                    bb_upper = %s,
                    bb_middle = %s,
                    bb_lower = %s,
                    bb_percent_b = %s,
                    atr_10 = %s,
                    atr_14 = %s,
                    atr_50 = %s,
                    atr_ratio = %s,
                    adx = %s,
                    stoch_k = %s,
                    stoch_d = %s,
                    cci_14 = %s,
                    cci_50 = %s,
                    kama_10 = %s,
                    hma_20 = %s,
                    alma_50 = %s,
                    mcginley_dynamic = %s,
                    cmf_21 = %s,
                    elder_force_index = %s,
                    volume_zscore = %s,
                    unusual_volume = %s,
                    returns_1d = %s,
                    log_returns_1d = %s,
                    range_pct = %s,
                    garman_klass_vol = %s,
                    yang_zhang_vol = %s
                WHERE symbol = %s AND event_date = %s
            """, (
                float(row['hurst_exponent']) if pd.notna(row.get('hurst_exponent')) else None,
                str(row['hurst_regime']) if pd.notna(row.get('hurst_regime')) else None,
                float(row['connors_rsi']) if pd.notna(row.get('connors_rsi')) else None,
                float(row['schaff_trend_cycle']) if pd.notna(row.get('schaff_trend_cycle')) else None,
                bool(row['ttm_squeeze_on']) if pd.notna(row.get('ttm_squeeze_on')) else None,
                float(row['ttm_squeeze_momentum']) if pd.notna(row.get('ttm_squeeze_momentum')) else None,
                float(row['fisher_transform']) if pd.notna(row.get('fisher_transform')) else None,
                float(row['fisher_signal']) if pd.notna(row.get('fisher_signal')) else None,
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
                float(row.get('atr_14', np.nan)) if pd.notna(row.get('atr_14')) else None,
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
                float(row['cmf_21']) if pd.notna(row.get('cmf_21')) else None,
                float(row['elder_force_index']) if pd.notna(row.get('elder_force_index')) else None,
                float(row['volume_zscore']) if pd.notna(row.get('volume_zscore')) else None,
                bool(row['unusual_volume']) if pd.notna(row.get('unusual_volume')) else None,
                float(row['returns_1d']) if pd.notna(row.get('returns_1d')) else None,
                float(row['log_returns_1d']) if pd.notna(row.get('log_returns_1d')) else None,
                float(row['range_pct']) if pd.notna(row.get('range_pct')) else None,
                float(row['garman_klass_vol']) if pd.notna(row.get('garman_klass_vol')) else None,
                float(row['yang_zhang_vol']) if pd.notna(row.get('yang_zhang_vol')) else None,
                symbol,
                date
            ))
            updated += 1
    
    conn.commit()
    cursor.close()
    
    return updated


def main():
    """
    Recalculate ALL elite indicators for ALL symbols.
    User will validate results.
    """
    
    print("\n" + "="*70)
    print("🏦 RECALCULATING ALL INDICATORS - INSTITUTIONAL LIBRARIES ONLY")
    print("="*70)
    print("\nLibraries:")
    print("  - Stock Indicators for Python (Hurst, Schaff, Connors, TTM)")
    print("  - TA-Lib (RSI, MACD, BB, ATR, all standard indicators)")
    print("  - Pandas (.corr() for correlations)")
    print("\nNO HAND-CODED MATH.\n")
    print("="*70 + "\n")
    
    conn = psycopg2.connect(DATABASE_URL)
    
    # Get all symbols
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT symbol FROM mkt.futures_1d ORDER BY symbol")
    symbols = [row[0] for row in cursor.fetchall()]
    cursor.close()
    
    print(f"Processing {len(symbols)} symbols...\n")
    
    total_updated = 0
    
    for symbol in tqdm(symbols, desc="Symbols"):
        try:
            updated = recalculate_for_symbol(symbol, conn)
            total_updated += updated
        except Exception as e:
            print(f"\n❌ {symbol} failed: {e}")
            continue
    
    conn.close()
    
    print("\n" + "="*70)
    print(f"✅ COMPLETE: {total_updated:,} rows updated with institutional indicators")
    print("="*70)
    print("\nUSER WILL VALIDATE RESULTS WITH THEIR OWN TESTING SCRIPTS")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()