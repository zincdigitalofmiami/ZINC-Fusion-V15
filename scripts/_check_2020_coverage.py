#!/usr/bin/env python3
import psycopg2, os
from dotenv import load_dotenv

load_dotenv()
c = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = c.cursor()

print("=" * 70)
print("DATA COVERAGE FROM 2020-01-01")
print("=" * 70)

# Market futures
cur.execute(
    "SELECT COUNT(*), COUNT(DISTINCT symbol) FROM raw.market_futures_1d WHERE event_date >= '2020-01-01'"
)
rows, symbols = cur.fetchone()
print(f"\nmarket_futures_1d: {rows:,} rows, {symbols} symbols")

# FRED
cur.execute(
    "SELECT COUNT(*), COUNT(DISTINCT series_id) FROM raw.fred_observations_1d WHERE event_date >= '2020-01-01'"
)
rows, series = cur.fetchone()
print(f"fred_observations_1d: {rows:,} rows, {series} series")

# FX
cur.execute(
    "SELECT COUNT(*), COUNT(DISTINCT pair) FROM raw.fx_spot_1d WHERE event_date >= '2020-01-01'"
)
rows, pairs = cur.fetchone()
print(f"fx_spot_1d: {rows:,} rows, {pairs} pairs")

# Weather
cur.execute("SELECT COUNT(*) FROM raw.weather_noaa_1d WHERE event_date >= '2020-01-01'")
rows = cur.fetchone()[0]
print(f"weather_noaa_1d: {rows:,} rows")

# CFTC
cur.execute(
    "SELECT COUNT(*), COUNT(DISTINCT symbol) FROM raw.cftc_cot_1w WHERE event_date >= '2020-01-01'"
)
rows, symbols = cur.fetchone()
print(f"cftc_cot_1w: {rows:,} rows, {symbols} symbols")

# USDA Exports
cur.execute(
    "SELECT COUNT(*) FROM raw.usda_export_sales_1w WHERE event_date >= '2020-01-01'"
)
rows = cur.fetchone()[0]
print(f"usda_export_sales_1w: {rows:,} rows")

# USDA WASDE
cur.execute("SELECT COUNT(*) FROM raw.usda_wasde_1m WHERE event_date >= '2020-01-01'")
rows = cur.fetchone()[0]
print(f"usda_wasde_1m: {rows:,} rows")

# EPA RIN
cur.execute(
    "SELECT COUNT(*) FROM raw.epa_rin_prices_1d WHERE event_date >= '2020-01-01'"
)
rows = cur.fetchone()[0]
print(f"epa_rin_prices_1d: {rows:,} rows")

# News
cur.execute(
    "SELECT COUNT(*) FROM raw.news_articles_1d WHERE event_date >= '2020-01-01'"
)
rows = cur.fetchone()[0]
print(f"news_articles_1d: {rows:,} rows")

print("\n" + "=" * 70)
c.close()
