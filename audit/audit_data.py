#!/usr/bin/env python3
"""Audit all data sources for strategic training."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv('.env')

import psycopg2

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

print('=' * 70)
print('COMPLETE DATA INVENTORY - PRISMA DATABASE')
print('=' * 70)

# Table name -> (date column, description)
tables = [
    ('raw.market_futures_1d', 'event_date', 'Daily futures OHLCV'),
    ('raw.fred_observations_1d', 'event_date', 'FRED economic indicators'),
    ('raw.weather_noaa_1d', 'event_date', 'NOAA weather data'),
    ('raw.fx_spot_1d', 'event_date', 'FX spot rates'),
    ('raw.cftc_cot_1w', 'event_date', 'CFTC COT positioning'),
    ('raw.usda_export_sales_1w', 'event_date', 'USDA export sales'),
    ('raw.usda_wasde_1m', 'event_date', 'USDA WASDE fundamentals'),
    ('raw.epa_rin_prices_1d', 'event_date', 'EPA RIN prices'),
    ('raw.news_articles_1d', 'event_date', 'News sentiment'),
]

print()
total_rows = 0
for table, date_col, desc in tables:
    try:
        cur.execute(f'SELECT COUNT(*), MIN({date_col}), MAX({date_col}) FROM {table}')
        count, min_date, max_date = cur.fetchone()
        total_rows += count
        print(f'[OK] {table:30} {count:>10,} rows  ({min_date} to {max_date})')
    except Exception as e:
        conn.rollback()
        print(f'[ERR] {table:30} ERROR: {e}')

print()
print(f'TOTAL: {total_rows:,} rows across 9 data sources')
print('=' * 70)
conn.close()
