#!/usr/bin/env python3
"""
Rebuild Elite Indicators using pandas_ta ONLY.

NO CUSTOM CODE - every indicator is a direct pandas_ta call.
Garman-Klass, Yang-Zhang, Hurst excluded (require custom wrappers).
"""
import pandas as pd
import pandas_ta as ta
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

DATABASE_URL = os.getenv('DATABASE_URL')


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute('''
        SELECT symbol, COUNT(*) as rows
        FROM mkt.futures_1d
        GROUP BY symbol
        HAVING COUNT(*) >= 100
        ORDER BY rows DESC
    ''')
    symbols = [r[0] for r in cur.fetchall()]
    conn.close()

    print(f"Processing {len(symbols)} symbols with pandas_ta ONLY...", flush=True)
    print("=" * 70, flush=True)

    results = []

    for symbol in symbols:
        conn = psycopg2.connect(DATABASE_URL)

        query = '''
            SELECT event_date as trade_date, open, high, low, close, volume
            FROM mkt.futures_1d
            WHERE symbol = %s
            ORDER BY event_date
        '''
        cur = conn.cursor()
        cur.execute(query, (symbol,))
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=['trade_date', 'open', 'high', 'low', 'close', 'volume'])
        df = df.set_index('trade_date')

        if len(df) < 100:
            print(f"{symbol:8s} SKIP - only {len(df)} rows", flush=True)
            results.append({'symbol': symbol, 'status': 'skipped', 'rows': len(df)})
            conn.close()
            continue

        df['volume'] = df['volume'].replace(0, np.nan)

        # =================================================================
        # PANDAS_TA INDICATORS - Direct library calls only
        # =================================================================

        # RSI
        df.ta.rsi(length=2, append=True)
        df.ta.rsi(length=14, append=True)

        # MACD
        df.ta.macd(append=True)

        # Bollinger Bands
        df.ta.bbands(length=20, append=True)

        # ATR
        df.ta.atr(length=10, append=True)
        df.ta.atr(length=50, append=True)

        # CCI
        df.ta.cci(length=14, append=True)
        df.ta.cci(length=50, append=True)

        # Adaptive Moving Averages
        df.ta.kama(append=True)
        df.ta.hma(length=20, append=True)
        df.ta.alma(length=50, append=True)

        # Fisher Transform
        df.ta.fisher(append=True)

        # Connors RSI
        df.ta.crsi(append=True)

        # McGinley Dynamic
        df.ta.mcgd(append=True)

        # TTM Squeeze
        df.ta.squeeze(append=True)

        # Schaff Trend Cycle
        df.ta.stc(append=True)

        # RVGI (Relative Vigor Index - momentum with signal)
        df.ta.rvgi(append=True)

        # RVI (Relative Volatility Index - volatility measure)
        df.ta.rvi(append=True)

        # Elder Force Index
        df.ta.efi(append=True)

        # CMF
        df.ta.cmf(length=20, append=True)

        # Volume Z-Score
        vol_zscore = ta.zscore(df['volume'], length=30)
        if vol_zscore is not None:
            df['volume_zscore'] = vol_zscore

        # =================================================================
        # DERIVED (simple pandas, not indicator math)
        # =================================================================

        df['returns_1d'] = df['close'].pct_change()
        df['log_returns_1d'] = np.log(df['close'] / df['close'].shift(1))
        df['range_pct'] = (df['high'] - df['low']) / df['close'].shift(1)

        if 'ATRr_10' in df.columns and 'ATRr_50' in df.columns:
            df['atr_ratio'] = df['ATRr_10'] / df['ATRr_50']

        if 'RSI_14' in df.columns:
            df['cumulative_rsi'] = df['RSI_14'].rolling(14).sum()

        if 'volume_zscore' in df.columns:
            df['unusual_volume'] = df['volume_zscore'].abs() > 2.0

        df['symbol'] = symbol
        df = df.reset_index()

        # Lowercase all columns
        df.columns = [c.lower().replace('.', '_').replace(' ', '_') for c in df.columns]

        # Map pandas_ta names to DB schema
        column_mapping = {
            'rsi_2': 'rsi_2',
            'rsi_14': 'rsi_14',
            'macd_12_26_9': 'macd',
            'macdh_12_26_9': 'macd_histogram',
            'macds_12_26_9': 'macd_signal',
            'bbp_20_2_0_2_0': 'bb_percent_b',
            'atrr_10': 'atr_10',
            'atrr_50': 'atr_50',
            'cci_14_0_015': 'cci_14',
            'cci_50_0_015': 'cci_50',
            'kama_10_2_30': 'kama_10',
            'hma_20': 'hma_20',
            'alma_50_6_0_0_85': 'alma_50',
            'fishert_9_1': 'fisher_transform',
            'fisherts_9_1': 'fisher_signal',
            'crsi_3_2_100': 'connors_rsi',
            'mcgd_10': 'mcginley_dynamic',
            'sqz_on': 'ttm_squeeze_on',
            'sqz_20_2_0_20_1_5': 'ttm_squeeze_momentum',
            'stc_10_12_26_0_5': 'schaff_trend_cycle',
            'rvgi_14_4': 'rvi',
            'rvgis_14_4': 'rvi_signal',
            'rvi_14': 'rvi_volatility',  # separate volatility RVI
            'efi_13': 'elder_force_index',
            'cmf_20': 'cmf_21',
        }
        df = df.rename(columns=column_mapping)

        # =================================================================
        # DATABASE INSERT
        # =================================================================

        df['created_at'] = datetime.now(timezone.utc)

        cur = conn.cursor()
        cur.execute("DELETE FROM features.elite_1d WHERE symbol = %s", (symbol,))
        deleted = cur.rowcount

        cur.execute('''
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'features' AND table_name = 'elite_1d'
        ''')
        db_cols = {r[0] for r in cur.fetchall()}

        valid_cols = [c for c in df.columns if c in db_cols]
        df_out = df[valid_cols].copy()

        indicator_cols = [c for c in valid_cols if c not in ['trade_date', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'created_at', 'id']]

        for bool_col in ['ttm_squeeze_on', 'unusual_volume']:
            if bool_col in df_out.columns:
                df_out[bool_col] = df_out[bool_col].astype(bool)

        values = []
        for row in df_out.itertuples(index=False, name=None):
            row_clean = tuple(None if pd.isna(v) else v for v in row)
            values.append(row_clean)

        cols = list(df_out.columns)
        insert_sql = f"INSERT INTO features.elite_1d ({','.join(cols)}) VALUES %s"

        try:
            execute_values(cur, insert_sql, values, page_size=1000)
            conn.commit()
            print(f"{symbol:8s} ✅ {len(values):>8,} rows, {len(indicator_cols)} indicators (was {deleted:,})", flush=True)
            results.append({'symbol': symbol, 'status': 'success', 'rows': len(values)})
        except Exception as e:
            conn.rollback()
            print(f"{symbol:8s} ❌ ERROR: {str(e)[:60]}", flush=True)
            results.append({'symbol': symbol, 'status': 'error', 'error': str(e)})

        conn.close()

    print("=" * 70, flush=True)
    success = sum(1 for r in results if r['status'] == 'success')
    total_rows = sum(r.get('rows', 0) for r in results if r['status'] == 'success')
    print(f"DONE: {success}/{len(symbols)} symbols, {total_rows:,} total rows", flush=True)
    return success == len([r for r in results if r['status'] != 'skipped'])


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
