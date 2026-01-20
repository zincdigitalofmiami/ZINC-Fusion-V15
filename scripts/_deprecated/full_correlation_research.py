#!/usr/bin/env python3
"""
ZINC-FUSION-V15: COMPREHENSIVE CORRELATION RESEARCH
Run full correlation analysis on ALL symbols vs ZL (Soybean Oil)
This is the definitive tagging reference.
"""
import os
import psycopg2
import pandas as pd
import numpy as np
from scipy import stats
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.getenv('DATABASE_URL'))

print('='*80)
print('ZINC-FUSION-V15: COMPREHENSIVE CORRELATION RESEARCH')
print('ZL (Soybean Oil) vs ALL Futures Symbols')
print('='*80)

# Get ALL symbols from market_futures_1d
query = """
SELECT DISTINCT symbol FROM raw.market_futures_1d 
WHERE close IS NOT NULL
ORDER BY symbol
"""
all_symbols = pd.read_sql(query, conn)['symbol'].tolist()
print(f'\nTotal symbols in database: {len(all_symbols)}')

# Get ZL data
zl_query = """
SELECT event_date, close as zl_close
FROM raw.market_futures_1d
WHERE symbol = 'ZL' AND close IS NOT NULL AND event_date >= '2010-01-01'
ORDER BY event_date
"""
zl_df = pd.read_sql(zl_query, conn, parse_dates=['event_date'])
zl_df.set_index('event_date', inplace=True)
print(f'ZL data: {len(zl_df)} rows ({zl_df.index.min().date()} to {zl_df.index.max().date()})')

# Calculate ZL returns and volatility regime
zl_df['zl_ret'] = zl_df['zl_close'].pct_change()
zl_df['zl_vol'] = zl_df['zl_ret'].rolling(21).std()
vol_threshold = zl_df['zl_vol'].quantile(0.75)

# Results storage
results = []

print(f'\nAnalyzing {len(all_symbols)} symbols...')
print('-'*80)

for i, sym in enumerate(all_symbols):
    if sym == 'ZL':
        continue
    
    try:
        query = f"""
        SELECT event_date, close
        FROM raw.market_futures_1d
        WHERE symbol = '{sym}' AND close IS NOT NULL AND event_date >= '2010-01-01'
        ORDER BY event_date
        """
        df = pd.read_sql(query, conn, parse_dates=['event_date'])
        df.set_index('event_date', inplace=True)
        df.columns = ['close']
        
        # Merge with ZL
        merged = zl_df[['zl_close', 'zl_ret', 'zl_vol']].join(df, how='inner')
        
        if len(merged) < 100:
            continue
        
        # Calculate returns
        merged['ret'] = merged['close'].pct_change()
        merged = merged.dropna()
        
        if len(merged) < 100:
            continue
        
        # === CORRELATIONS ===
        
        # 1. Simple correlation
        corr = merged['zl_ret'].corr(merged['ret'])
        
        # 2. Price correlation
        price_corr = merged['zl_close'].corr(merged['close'])
        
        # 3. High vol correlation
        high_vol = merged[merged['zl_vol'] > vol_threshold]
        hv_corr = high_vol['zl_ret'].corr(high_vol['ret']) if len(high_vol) > 30 else np.nan
        
        # 4. Low vol correlation
        low_vol = merged[merged['zl_vol'] <= vol_threshold]
        lv_corr = low_vol['zl_ret'].corr(low_vol['ret']) if len(low_vol) > 30 else np.nan
        
        # 5. Rolling correlation stats
        rolling = merged['zl_ret'].rolling(252).corr(merged['ret']).dropna()
        if len(rolling) > 100:
            roll_mean = rolling.mean()
            roll_std = rolling.std()
            roll_recent = rolling.iloc[-1]
        else:
            roll_mean = roll_std = roll_recent = np.nan
        
        # 6. Predictive power (lagged regression)
        X = merged['ret'].shift(1).dropna()
        Y = merged['zl_ret'].loc[X.index]
        if len(X) > 50:
            slope, intercept, r, p, se = stats.linregress(X, Y)
            predictive = p < 0.05
            pred_pval = p
            pred_beta = slope
        else:
            predictive = False
            pred_pval = np.nan
            pred_beta = np.nan
        
        results.append({
            'symbol': sym,
            'n_days': len(merged),
            'corr': corr,
            'abs_corr': abs(corr),
            'price_corr': price_corr,
            'hv_corr': hv_corr,
            'lv_corr': lv_corr,
            'roll_mean': roll_mean,
            'roll_std': roll_std,
            'roll_recent': roll_recent,
            'predictive': predictive,
            'pred_pval': pred_pval,
            'pred_beta': pred_beta,
        })
        
        if (i + 1) % 20 == 0:
            print(f'  Processed {i+1}/{len(all_symbols)} symbols...')
            
    except Exception as e:
        pass

print(f'\nAnalysis complete: {len(results)} symbols with sufficient data')

# Convert to DataFrame
results_df = pd.DataFrame(results)
results_df = results_df.sort_values('abs_corr', ascending=False)

# === OUTPUT RESULTS ===

print('\n' + '='*80)
print('TOP 30 CORRELATIONS WITH ZL (sorted by absolute correlation)')
print('='*80)
print(f'{"Sym":<8} {"N":>6} {"Corr":>8} {"Price":>8} {"HiVol":>8} {"LoVol":>8} {"RollAvg":>8} {"Pred?":>6} {"p-val":>8}')
print('-'*80)

for _, row in results_df.head(30).iterrows():
    pred_str = 'YES' if row['predictive'] else ''
    pval_str = f"{row['pred_pval']:.4f}" if not pd.isna(row['pred_pval']) else ''
    print(f"{row['symbol']:<8} {row['n_days']:>6} {row['corr']:>8.4f} {row['price_corr']:>8.4f} "
          f"{row['hv_corr']:>8.4f} {row['lv_corr']:>8.4f} {row['roll_mean']:>8.4f} {pred_str:>6} {pval_str:>8}")

print('\n' + '='*80)
print('PREDICTIVE SYMBOLS (p < 0.05)')
print('='*80)
predictive_df = results_df[results_df['predictive'] == True].sort_values('pred_pval')
print(f'{"Sym":<8} {"N":>6} {"Corr":>8} {"Beta":>8} {"p-value":>10} {"Direction":>10}')
print('-'*60)
for _, row in predictive_df.iterrows():
    direction = 'POSITIVE' if row['pred_beta'] > 0 else 'NEGATIVE'
    print(f"{row['symbol']:<8} {row['n_days']:>6} {row['corr']:>8.4f} {row['pred_beta']:>8.4f} {row['pred_pval']:>10.6f} {direction:>10}")

print('\n' + '='*80)
print('CORRELATION BY CATEGORY')
print('='*80)

# Define categories
categories = {
    'SOY_COMPLEX': ['ZS', 'ZM', 'ZL'],
    'GRAINS': ['ZC', 'ZW', 'KE', 'ZO', 'ZR', 'MWE'],
    'ENERGY': ['CL', 'HO', 'RB', 'NG', 'QG', 'BZ'],
    'METALS_PRECIOUS': ['GC', 'SI', 'PA', 'PL', 'MGC'],
    'METALS_INDUSTRIAL': ['HG', 'ALI', 'CU'],
    'LIVESTOCK': ['HE', 'LE', 'GF'],
    'SOFTS': ['CC', 'KC', 'SB', 'CT', 'OJ', 'LBR'],
    'EQUITY_INDEX': ['ES', 'NQ', 'YM', 'RTY', 'EMD', 'MES', 'MNQ', 'MYM', 'M2K'],
    'FX': ['6E', '6J', '6B', '6A', '6C', '6S', '6N', '6M', 'DX'],
    'RATES': ['ZN', 'ZB', 'ZF', 'ZT', 'GE', 'ZQ'],
    'CRYPTO': ['BTC', 'ETH', 'MBT', 'MET'],
    'VOLATILITY': ['VX'],
}

for cat, symbols in categories.items():
    cat_df = results_df[results_df['symbol'].isin(symbols)]
    if len(cat_df) > 0:
        avg_corr = cat_df['corr'].mean()
        max_sym = cat_df.loc[cat_df['abs_corr'].idxmax(), 'symbol']
        max_corr = cat_df['abs_corr'].max()
        pred_count = cat_df['predictive'].sum()
        print(f'\n{cat}:')
        print(f'  Avg Corr: {avg_corr:.4f}, Max: {max_sym} ({max_corr:.4f}), Predictive: {pred_count}/{len(cat_df)}')
        for _, row in cat_df.sort_values('abs_corr', ascending=False).iterrows():
            pred_mark = '*' if row['predictive'] else ''
            print(f'    {row["symbol"]:<8} corr={row["corr"]:>7.4f} hv={row["hv_corr"]:>7.4f} {pred_mark}')

print('\n' + '='*80)
print('HIGH VOLATILITY REGIME MOVERS')
print('='*80)
print('Symbols with correlation change > 0.05 in high vol:')
results_df['hv_delta'] = results_df['hv_corr'] - results_df['lv_corr']
hv_movers = results_df[abs(results_df['hv_delta']) > 0.05].sort_values('hv_delta', ascending=False)
print(f'{"Sym":<8} {"LowVol":>8} {"HiVol":>8} {"Delta":>8} {"Interpretation":<30}')
print('-'*70)
for _, row in hv_movers.head(20).iterrows():
    if row['hv_delta'] > 0:
        interp = 'Stronger in crisis'
    else:
        interp = 'Weaker in crisis'
    print(f"{row['symbol']:<8} {row['lv_corr']:>8.4f} {row['hv_corr']:>8.4f} {row['hv_delta']:>+8.4f} {interp:<30}")

print('\n' + '='*80)
print('STABLE VS VARIABLE CORRELATIONS')
print('='*80)
stable = results_df[results_df['roll_std'] < 0.10].sort_values('abs_corr', ascending=False)
variable = results_df[results_df['roll_std'] >= 0.10].sort_values('abs_corr', ascending=False)
print(f'\nSTABLE correlations (std < 0.10): {len(stable)} symbols')
for _, row in stable.head(15).iterrows():
    print(f'  {row["symbol"]:<8} corr={row["corr"]:>7.4f} std={row["roll_std"]:>6.4f}')
print(f'\nVARIABLE correlations (std >= 0.10): {len(variable)} symbols')
for _, row in variable.head(15).iterrows():
    print(f'  {row["symbol"]:<8} corr={row["corr"]:>7.4f} std={row["roll_std"]:>6.4f}')

# Save results
results_df.to_csv('/Volumes/Satechi Hub/ZINC-FUSION-V15/docs/correlation_results_all_symbols.csv', index=False)
print(f'\n\nResults saved to: docs/correlation_results_all_symbols.csv')

conn.close()

print('\n' + '='*80)
print('ANALYSIS COMPLETE')
print('='*80)
