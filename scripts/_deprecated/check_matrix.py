import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_schema = 'training' 
    AND table_name = 'matrix_1d'
    ORDER BY ordinal_position
""")
cols = [r[0] for r in cur.fetchall()]

print('=== MATRIX TRUTH ===')
print(f'Total columns: {len(cols)}')

fred = [c for c in cols if c.startswith('fred_')]
fx = [c for c in cols if c.startswith('fx_')]
weather = [c for c in cols if 'weather' in c or c.startswith('wx_')]
ohlcv = [c for c in cols if '_open' in c or '_high' in c or '_low' in c or '_close' in c or '_volume' in c]
elite = [c for c in cols if any(x in c for x in ['hurst', 'rsi', 'macd', 'fisher', 'kama', 'cci', 'atr'])]

print(f'\nFRED: {len(fred)} columns')
print(f'FX: {len(fx)} columns')
print(f'Weather: {len(weather)} columns')
print(f'Commodity OHLCV: {len(ohlcv)} columns')
print(f'Elite indicators: {len(elite)} columns')

print(f'\nALL {len(cols)} COLUMNS:')
for i, c in enumerate(cols, 1):
    print(f'{i}. {c}')

conn.close()
