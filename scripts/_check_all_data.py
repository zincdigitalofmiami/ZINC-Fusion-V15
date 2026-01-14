#!/usr/bin/env python3
"""Check what ALL DATA actually means."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
c = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = c.cursor()

print("=" * 70)
print('ACTUAL DATA INVENTORY (2020+) - "ALL DATA POLICY"')
print("=" * 70)

# Market futures - ALL symbols
cur.execute(
    "SELECT COUNT(DISTINCT symbol), COUNT(*) FROM raw.market_futures_1d WHERE event_date >= '2020-01-01'"
)
sym_count, row_count = cur.fetchone()
print(f"\n📈 market_futures_1d: {sym_count} symbols, {row_count:,} total rows")

# Get symbol list
cur.execute(
    "SELECT DISTINCT symbol FROM raw.market_futures_1d WHERE event_date >= '2020-01-01' ORDER BY symbol"
)
symbols = [r[0] for r in cur.fetchall()]
print(f'   Symbols: {", ".join(symbols[:20])}{"..." if len(symbols) > 20 else ""}')

# FRED - ALL series
cur.execute(
    "SELECT COUNT(DISTINCT series_id), COUNT(*) FROM raw.fred_observations_1d WHERE event_date >= '2020-01-01'"
)
series_count, fred_rows = cur.fetchone()
print(f"\n📊 fred_observations_1d: {series_count} series, {fred_rows:,} total rows")

# Get top series
cur.execute(
    """
    SELECT series_id, COUNT(*) 
    FROM raw.fred_observations_1d 
    WHERE event_date >= '2020-01-01'
    GROUP BY series_id 
    ORDER BY COUNT(*) DESC 
    LIMIT 10
"""
)
print("   Top 10 series:")
for sid, cnt in cur.fetchall():
    print(f"     - {sid}: {cnt:,} rows")

# FX
cur.execute(
    "SELECT COUNT(DISTINCT pair), COUNT(*) FROM raw.fx_spot_1d WHERE event_date >= '2020-01-01'"
)
fx_pairs, fx_rows = cur.fetchone()
print(f"\n💱 fx_spot_1d: {fx_pairs} pairs, {fx_rows:,} total rows")

# Weather
cur.execute("SELECT COUNT(*) FROM raw.weather_noaa_1d WHERE event_date >= '2020-01-01'")
weather_rows = cur.fetchone()[0]
print(f"\n🌦️  weather_noaa_1d: {weather_rows:,} rows")

# CFTC
cur.execute(
    "SELECT COUNT(DISTINCT symbol), COUNT(*) FROM raw.cftc_cot_1w WHERE event_date >= '2020-01-01'"
)
cftc_sym, cftc_rows = cur.fetchone()
print(f"\n📋 cftc_cot_1w: {cftc_sym} symbols, {cftc_rows:,} total rows")

# News
cur.execute(
    "SELECT COUNT(*) FROM raw.news_articles_1d WHERE event_date >= '2020-01-01'"
)
news_rows = cur.fetchone()[0]
print(f"\n📰 news_articles_1d: {news_rows:,} rows")

# USDA
cur.execute(
    "SELECT COUNT(*) FROM raw.usda_export_sales_1w WHERE event_date >= '2020-01-01'"
)
export_rows = cur.fetchone()[0]
print(f"\n🌾 usda_export_sales_1w: {export_rows:,} rows")

cur.execute("SELECT COUNT(*) FROM raw.usda_wasde_1m WHERE event_date >= '2020-01-01'")
wasde_rows = cur.fetchone()[0]
print(f"   usda_wasde_1m: {wasde_rows:,} rows")

# EPA
cur.execute(
    "SELECT COUNT(*) FROM raw.epa_rin_prices_1d WHERE event_date >= '2020-01-01'"
)
epa_rows = cur.fetchone()[0]
print(f"\n⚡ epa_rin_prices_1d: {epa_rows:,} rows")

print("\n" + "=" * 70)
total = (
    row_count
    + fred_rows
    + fx_rows
    + weather_rows
    + cftc_rows
    + news_rows
    + export_rows
    + wasde_rows
    + epa_rows
)
print(f"TOTAL ROWS (2020+): {total:,}")
print("=" * 70)

c.close()
