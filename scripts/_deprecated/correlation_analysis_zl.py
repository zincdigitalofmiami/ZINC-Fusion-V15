#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Empirical Correlation Analysis
Verify silver, copper, lean hogs vs soybean oil (ZL) correlations
This informs specialist tagging decisions.
"""
import os
import psycopg2
import pandas as pd
import numpy as np
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.getenv('DATABASE_URL'))

print('='*70)
print('EMPIRICAL CORRELATION ANALYSIS: ZL vs METALS & LIVESTOCK')
print('='*70)

# Get ZL (soybean oil) daily prices
zl_query = """
SELECT event_date, close as zl_close
FROM mkt.futures_1d
WHERE symbol = 'ZL' AND close IS NOT NULL
ORDER BY event_date
"""
zl_df = pd.read_sql(zl_query, conn, parse_dates=['event_date'])
zl_df.set_index('event_date', inplace=True)
print(f'\nZL data: {len(zl_df)} rows ({zl_df.index.min()} to {zl_df.index.max()})')

# Get comparison symbols
symbols_to_check = {
    'SI': 'Silver',
    'HG': 'Copper (High Grade)',
    'HE': 'Lean Hogs',
    'LE': 'Live Cattle',
    'GF': 'Feeder Cattle',
    'ZM': 'Soybean Meal',
    'ZS': 'Soybeans',
    'CL': 'Crude Oil',
    'GC': 'Gold',
    'ZC': 'Corn',
}

results = {}

for sym, name in symbols_to_check.items():
    query = f"""
    SELECT event_date, close as {sym.lower()}_close
    FROM mkt.futures_1d
    WHERE symbol = '{sym}' AND close IS NOT NULL
    ORDER BY event_date
    """
    try:
        df = pd.read_sql(query, conn, parse_dates=['event_date'])
        df.set_index('event_date', inplace=True)
        
        # Merge with ZL
        merged = zl_df.join(df, how='inner')
        
        if len(merged) > 100:
            # Calculate returns
            merged['zl_ret'] = merged['zl_close'].pct_change()
            merged[f'{sym.lower()}_ret'] = merged[f'{sym.lower()}_close'].pct_change()
            merged = merged.dropna()
            
            # Price correlation
            price_corr = merged['zl_close'].corr(merged[f'{sym.lower()}_close'])
            
            # Returns correlation
            ret_corr = merged['zl_ret'].corr(merged[f'{sym.lower()}_ret'])
            
            # Rolling correlation (1 year = ~252 trading days)
            if len(merged) > 252:
                rolling_corr = merged['zl_ret'].rolling(252).corr(merged[f'{sym.lower()}_ret'])
                recent_corr = rolling_corr.iloc[-1] if not pd.isna(rolling_corr.iloc[-1]) else ret_corr
            else:
                recent_corr = ret_corr
            
            results[sym] = {
                'name': name,
                'rows': len(merged),
                'price_corr': price_corr,
                'returns_corr': ret_corr,
                'recent_252d_corr': recent_corr
            }
            
    except Exception as e:
        print(f'  {sym} ({name}): ERROR - {e}')

print('\n' + '='*70)
print('CORRELATION RESULTS (sorted by returns correlation)')
print('='*70)
print(f'{"Symbol":<8} {"Name":<20} {"N":>6} {"Price":>8} {"Returns":>8} {"Recent":>8}')
print('-'*70)

# Sort by returns correlation
sorted_results = sorted(results.items(), key=lambda x: abs(x[1]['returns_corr']), reverse=True)

for sym, data in sorted_results:
    print(f"{sym:<8} {data['name']:<20} {data['rows']:>6} {data['price_corr']:>8.3f} {data['returns_corr']:>8.3f} {data['recent_252d_corr']:>8.3f}")

# Analysis groups
print('\n' + '='*70)
print('ANALYSIS BY CATEGORY')
print('='*70)

print('\n=== SOY COMPLEX (expected high correlation) ===')
for sym in ['ZS', 'ZM']:
    if sym in results:
        d = results[sym]
        print(f"  {sym} ({d['name']}): returns_corr={d['returns_corr']:.3f}")

print('\n=== LIVESTOCK (feed demand linkage) ===')
for sym in ['HE', 'LE', 'GF']:
    if sym in results:
        d = results[sym]
        strength = 'STRONG' if abs(d['returns_corr']) > 0.3 else 'MODERATE' if abs(d['returns_corr']) > 0.15 else 'WEAK'
        print(f"  {sym} ({d['name']}): returns_corr={d['returns_corr']:.3f} [{strength}]")

print('\n=== METALS (macro/China proxy) ===')
for sym in ['SI', 'HG', 'GC']:
    if sym in results:
        d = results[sym]
        strength = 'STRONG' if abs(d['returns_corr']) > 0.3 else 'MODERATE' if abs(d['returns_corr']) > 0.15 else 'WEAK'
        print(f"  {sym} ({d['name']}): returns_corr={d['returns_corr']:.3f} [{strength}]")

print('\n=== ENERGY (biodiesel linkage) ===')
for sym in ['CL']:
    if sym in results:
        d = results[sym]
        strength = 'STRONG' if abs(d['returns_corr']) > 0.3 else 'MODERATE' if abs(d['returns_corr']) > 0.15 else 'WEAK'
        print(f"  {sym} ({d['name']}): returns_corr={d['returns_corr']:.3f} [{strength}]")

print('\n=== GRAINS (substitutes) ===')
for sym in ['ZC']:
    if sym in results:
        d = results[sym]
        strength = 'STRONG' if abs(d['returns_corr']) > 0.3 else 'MODERATE' if abs(d['returns_corr']) > 0.15 else 'WEAK'
        print(f"  {sym} ({d['name']}): returns_corr={d['returns_corr']:.3f} [{strength}]")

conn.close()

print('\n' + '='*70)
print('TAGGING IMPLICATIONS')
print('='*70)
