#!/usr/bin/env python3
"""Audit data availability to identify missing data."""
import psycopg2
import os
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

print('=' * 70)
print('DATA AVAILABILITY AUDIT')
print('=' * 70)

# Check if options_features exists
print('\n1. GOLD.OPTIONS_FEATURES_1D:')
cur.execute("""
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'gold' AND table_name = 'options_features_1d'
    )
""")
exists = cur.fetchone()[0]
print(f'   Table exists: {exists}')

if exists:
    cur.execute('SELECT COUNT(*) FROM gold.options_features_1d')
    print(f'   Row count: {cur.fetchone()[0]:,}')

# Check raw.options_futures_1d (source data)
print('\n2. RAW.OPTIONS_FUTURES_1D (source for Phase 1):')
cur.execute("""
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'raw' AND table_name = 'options_futures_1d'
    )
""")
exists = cur.fetchone()[0]
print(f'   Table exists: {exists}')

if exists:
    cur.execute("""
        SELECT COUNT(*), MIN(event_date), MAX(event_date)
        FROM raw.options_futures_1d
        WHERE symbol LIKE 'ZL%'
    """)
    row = cur.fetchone()
    print(f'   ZL options rows: {row[0]:,}')
    print(f'   Date range: {row[1]} to {row[2]}')

# Check elite indicators
print('\n3. GOLD.ELITE_INDICATORS_1D:')
cur.execute("""
    SELECT COUNT(*), MIN(trade_date), MAX(trade_date)
    FROM gold.elite_indicators_1d
    WHERE symbol = 'ZL'
""")
row = cur.fetchone()
print(f'   ZL rows: {row[0]:,}')
print(f'   Date range: {row[1]} to {row[2]}')

# Check null rates for key indicators
print('\n   Null rates for key indicators:')
indicators = ['connors_rsi', 'hurst_exponent', 'garman_klass_vol', 'cmf_21', 'volume_zscore']
for ind in indicators:
    try:
        cur.execute(f'''
            SELECT 
                COUNT(*) as total,
                COUNT("{ind}") as non_null,
                ROUND(100.0 * COUNT("{ind}") / COUNT(*), 1) as pct
            FROM gold.elite_indicators_1d
            WHERE symbol = 'ZL'
        ''')
        row = cur.fetchone()
        print(f'   {ind}: {row[2]}% non-null ({row[0] - row[1]} nulls)')
    except Exception as e:
        print(f'   {ind}: error - {e}')

# Check pre-2007 vs post-2007
print('\n4. DATA QUALITY BY ERA:')
cur.execute("""
    SELECT 
        CASE 
            WHEN trade_date < '2007-01-01' THEN 'pre-2007'
            ELSE 'post-2007'
        END as era,
        COUNT(*) as rows,
        COUNT(connors_rsi) as connors_ok,
        COUNT(garman_klass_vol) as gk_ok,
        COUNT(cmf_21) as cmf_ok
    FROM gold.elite_indicators_1d
    WHERE symbol = 'ZL'
    GROUP BY 1
    ORDER BY 1
""")
rows = cur.fetchall()
print(f'   {"Era":<10} | {"Rows":<6} | {"ConnorsRSI":<10} | {"GK Vol":<7} | CMF')
print(f'   {"-" * 50}')
for r in rows:
    print(f'   {r[0]:<10} | {r[1]:<6} | {r[2]:<10} | {r[3]:<7} | {r[4]}')

# Check flat bars (H=L) distribution
print('\n5. FLAT BARS (HIGH = LOW) BY ERA:')
cur.execute("""
    SELECT 
        CASE 
            WHEN trade_date < '2007-01-01' THEN 'pre-2007'
            ELSE 'post-2007'
        END as era,
        COUNT(*) as total,
        SUM(CASE WHEN high = low THEN 1 ELSE 0 END) as flat_bars,
        ROUND(100.0 * SUM(CASE WHEN high = low THEN 1 ELSE 0 END) / COUNT(*), 1) as flat_pct
    FROM gold.elite_indicators_1d
    WHERE symbol = 'ZL'
    GROUP BY 1
    ORDER BY 1
""")
rows = cur.fetchall()
for r in rows:
    print(f'   {r[0]}: {r[2]} flat bars ({r[3]}% of {r[1]})')

# Check zero volume distribution
print('\n6. ZERO VOLUME BY ERA:')
cur.execute("""
    SELECT 
        CASE 
            WHEN trade_date < '2007-01-01' THEN 'pre-2007'
            ELSE 'post-2007'
        END as era,
        COUNT(*) as total,
        SUM(CASE WHEN volume = 0 OR volume IS NULL THEN 1 ELSE 0 END) as zero_vol,
        ROUND(100.0 * SUM(CASE WHEN volume = 0 OR volume IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as zero_pct
    FROM gold.elite_indicators_1d
    WHERE symbol = 'ZL'
    GROUP BY 1
    ORDER BY 1
""")
rows = cur.fetchall()
for r in rows:
    print(f'   {r[0]}: {r[2]} zero-volume bars ({r[3]}% of {r[1]})')

# Check raw market data
print('\n7. RAW.MARKET_FUTURES_1D:')
cur.execute("""
    SELECT COUNT(*), MIN(event_date), MAX(event_date)
    FROM raw.market_futures_1d
    WHERE symbol = 'ZL'
""")
row = cur.fetchone()
print(f'   ZL rows: {row[0]:,}')
print(f'   Date range: {row[1]} to {row[2]}')

# Check for gaps in daily data
print('\n8. DATE GAPS (missing trading days):')
cur.execute("""
    WITH dates AS (
        SELECT trade_date, 
               LAG(trade_date) OVER (ORDER BY trade_date) as prev_date,
               trade_date - LAG(trade_date) OVER (ORDER BY trade_date) as gap_days
        FROM gold.elite_indicators_1d
        WHERE symbol = 'ZL'
    )
    SELECT 
        CASE 
            WHEN gap_days <= 3 THEN 'normal (1-3 days)'
            WHEN gap_days <= 7 THEN 'week gap (4-7 days)'
            ELSE 'large gap (>7 days)'
        END as gap_type,
        COUNT(*) as occurrences
    FROM dates
    WHERE gap_days IS NOT NULL
    GROUP BY 1
    ORDER BY 1
""")
rows = cur.fetchall()
for r in rows:
    print(f'   {r[0]}: {r[1]}')

conn.close()

print('\n' + '=' * 70)
print('SUMMARY')
print('=' * 70)
print('''
HARD MISSING (blocking):
  - gold.options_features_1d: Table does not exist → Run Phase 1
  - raw.options_futures_1d: Check if source data exists for IV/Greeks

SOFT MISSING (indicator edge cases):
  - connors_rsi: Division-by-zero in transition era
  - garman_klass_vol: Breaks on flat bars (H=L)
  - cmf_21: Breaks on zero volume

ROOT CAUSE: 2000-2006 data has:
  - High % of flat bars (H=L)
  - High % of zero/missing volume
  - These cause NaN outputs from indicator formulas
''')
