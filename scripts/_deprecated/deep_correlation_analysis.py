#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Deep Correlation Analysis
- Regime-specific correlations (bull/bear/high-vol)
- Lagged correlations (lead/lag relationships)
- Rolling window analysis
"""
import os
import psycopg2
import pandas as pd
import numpy as np
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.getenv('DATABASE_URL'))

print('='*70)
print('DEEP CORRELATION ANALYSIS: ZL RELATIONSHIPS')
print('='*70)

# Get all symbols we need
query = """
SELECT 
    event_date,
    symbol,
    close
FROM mkt.futures_1d
WHERE symbol IN ('ZL', 'ZS', 'ZM', 'ZC', 'HE', 'LE', 'GF', 'SI', 'HG', 'GC', 'CL')
AND close IS NOT NULL
AND event_date >= '2010-01-01'
ORDER BY event_date, symbol
"""

df = pd.read_sql(query, conn, parse_dates=['event_date'])
pivot = df.pivot(index='event_date', columns='symbol', values='close')
pivot = pivot.dropna()

print(f'\nData range: {pivot.index.min()} to {pivot.index.max()}')
print(f'Trading days: {len(pivot)}')

# Calculate returns
returns = pivot.pct_change().dropna()

# 1. SIMPLE CORRELATIONS WITH ZL
print('\n' + '='*70)
print('1. SIMPLE CORRELATIONS WITH ZL (2010-present)')
print('='*70)
print(f'{"Symbol":<8} {"Corr":>8} {"Abs":>8}')
print('-'*30)
for col in sorted(returns.columns):
    if col != 'ZL':
        corr = returns['ZL'].corr(returns[col])
        print(f"{col:<8} {corr:>8.4f} {abs(corr):>8.4f}")

# 2. LAGGED CORRELATIONS (does one lead the other?)
print('\n' + '='*70)
print('2. LAGGED CORRELATIONS (positive lag = symbol leads ZL)')
print('='*70)

def lagged_corr(s1, s2, max_lag=5):
    """Calculate correlations at different lags"""
    results = {}
    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            corr = s1.iloc[-lag:].reset_index(drop=True).corr(s2.iloc[:lag].reset_index(drop=True))
        elif lag > 0:
            corr = s1.iloc[:-lag].reset_index(drop=True).corr(s2.iloc[lag:].reset_index(drop=True))
        else:
            corr = s1.corr(s2)
        results[lag] = corr
    return results

key_symbols = ['ZS', 'ZM', 'HE', 'LE', 'HG', 'SI', 'CL', 'ZC']
print(f'{"Symbol":<8} {"Lag-3":>8} {"Lag-2":>8} {"Lag-1":>8} {"Lag 0":>8} {"Lag+1":>8} {"Lag+2":>8} {"Lag+3":>8} {"Best":>8}')
print('-'*80)

for sym in key_symbols:
    if sym in returns.columns:
        lags = lagged_corr(returns['ZL'], returns[sym], max_lag=3)
        best_lag = max(lags, key=lambda x: abs(lags[x]))
        print(f"{sym:<8} {lags[-3]:>8.4f} {lags[-2]:>8.4f} {lags[-1]:>8.4f} {lags[0]:>8.4f} {lags[1]:>8.4f} {lags[2]:>8.4f} {lags[3]:>8.4f} Lag={best_lag}")

# 3. REGIME-SPECIFIC CORRELATIONS
print('\n' + '='*70)
print('3. REGIME-SPECIFIC CORRELATIONS')
print('='*70)

# Calculate ZL volatility regime
returns['zl_vol'] = returns['ZL'].rolling(21).std()
vol_threshold = returns['zl_vol'].quantile(0.75)
high_vol = returns[returns['zl_vol'] > vol_threshold]
low_vol = returns[returns['zl_vol'] <= vol_threshold]

# Bull/Bear regime
returns['zl_trend'] = pivot['ZL'].pct_change(21)  # 1-month return
bull = returns[returns['zl_trend'] > 0.02]  # Up more than 2%
bear = returns[returns['zl_trend'] < -0.02]  # Down more than 2%

print(f'\nHigh Vol periods: {len(high_vol)} days')
print(f'Low Vol periods: {len(low_vol)} days')
print(f'Bull periods: {len(bull)} days')
print(f'Bear periods: {len(bear)} days')

print(f'\n{"Symbol":<8} {"All":>8} {"HiVol":>8} {"LoVol":>8} {"Bull":>8} {"Bear":>8}')
print('-'*50)

for sym in key_symbols:
    if sym in returns.columns:
        all_corr = returns['ZL'].corr(returns[sym])
        hv_corr = high_vol['ZL'].corr(high_vol[sym]) if len(high_vol) > 30 else np.nan
        lv_corr = low_vol['ZL'].corr(low_vol[sym]) if len(low_vol) > 30 else np.nan
        bull_corr = bull['ZL'].corr(bull[sym]) if len(bull) > 30 else np.nan
        bear_corr = bear['ZL'].corr(bear[sym]) if len(bear) > 30 else np.nan
        print(f"{sym:<8} {all_corr:>8.4f} {hv_corr:>8.4f} {lv_corr:>8.4f} {bull_corr:>8.4f} {bear_corr:>8.4f}")

# 4. ROLLING CORRELATION ANALYSIS
print('\n' + '='*70)
print('4. ROLLING CORRELATION STABILITY (252-day window)')
print('='*70)

print(f'\n{"Symbol":<8} {"Mean":>8} {"Std":>8} {"Min":>8} {"Max":>8} {"Recent":>8} {"Stable?":>10}')
print('-'*70)

for sym in key_symbols:
    if sym in returns.columns:
        rolling = returns['ZL'].rolling(252).corr(returns[sym])
        rolling = rolling.dropna()
        if len(rolling) > 100:
            mean_corr = rolling.mean()
            std_corr = rolling.std()
            min_corr = rolling.min()
            max_corr = rolling.max()
            recent = rolling.iloc[-1]
            stable = 'YES' if std_corr < 0.1 else 'VARIABLE'
            print(f"{sym:<8} {mean_corr:>8.4f} {std_corr:>8.4f} {min_corr:>8.4f} {max_corr:>8.4f} {recent:>8.4f} {stable:>10}")

# 5. GRANGER CAUSALITY PROXY (simple version)
print('\n' + '='*70)
print('5. PREDICTIVE RELATIONSHIPS (does X help predict ZL?)')
print('='*70)

from scipy import stats

# Simple: does yesterday's return of X predict today's ZL return?
print(f'\n{"Symbol":<8} {"Beta":>8} {"t-stat":>8} {"p-value":>8} {"Predictive?":>12}')
print('-'*55)

for sym in key_symbols:
    if sym in returns.columns:
        # Regress ZL_t on X_{t-1}
        X = returns[sym].shift(1).dropna()
        Y = returns['ZL'].loc[X.index]
        
        # Simple OLS
        slope, intercept, r, p, se = stats.linregress(X, Y)
        t_stat = slope / se
        predictive = 'YES' if p < 0.05 else 'no'
        print(f"{sym:<8} {slope:>8.4f} {t_stat:>8.2f} {p:>8.4f} {predictive:>12}")

conn.close()

print('\n' + '='*70)
print('SUMMARY & TAGGING RECOMMENDATIONS')
print('='*70)
