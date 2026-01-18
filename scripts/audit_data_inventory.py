#!/usr/bin/env python3
"""Data Inventory Audit - What data do we actually have?"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

print("=" * 70)
print("FULL DATA INVENTORY AUDIT")
print("=" * 70)

# ECON series in database
print("\n### ECON SERIES IN DATABASE ###")
cur.execute(
    """
    WITH econ AS (
        SELECT series_id, event_date FROM econ.rates_1d
        UNION ALL
        SELECT series_id, event_date FROM econ.inflation_1d
        UNION ALL
        SELECT series_id, event_date FROM econ.labor_1d
        UNION ALL
        SELECT series_id, event_date FROM econ.activity_1d
        UNION ALL
        SELECT series_id, event_date FROM econ.vol_indices_1d
        UNION ALL
        SELECT series_id, event_date FROM econ.commodities_1d
        UNION ALL
        SELECT pair as series_id, event_date FROM mkt.fx_1d WHERE source = 'FRED'
        UNION ALL
        SELECT series_id, event_date FROM econ.money_1d
    )
    SELECT series_id, COUNT(*) as rows, MIN(event_date)::date, MAX(event_date)::date
    FROM econ
    GROUP BY series_id
    ORDER BY series_id
"""
)
econ_data = cur.fetchall()
print(f"Total econ series: {len(econ_data)}")
for r in econ_data:
    print(f"  {r[0]}: {r[1]:,} rows ({r[2]} to {r[3]})")

# FX pairs in market schema
print("\n### FX PAIRS (mkt.fx_1d) ###")
cur.execute(
    """
    SELECT pair, COUNT(*) as rows, MIN(event_date), MAX(event_date)
    FROM mkt.fx_1d
    GROUP BY pair
    ORDER BY pair
"""
)
fx_mkt = cur.fetchall()
print(f"Total pairs in mkt: {len(fx_mkt)}")
for r in fx_mkt:
    print(f"  {r[0]}: {r[1]:,} rows ({r[2]} to {r[3]})")

# Market futures
print("\n### MARKET FUTURES (mkt.futures_1d) ###")
cur.execute(
    """
    SELECT symbol, COUNT(*) as rows, MIN(event_date)::date, MAX(event_date)::date
    FROM mkt.futures_1d
    GROUP BY symbol
    ORDER BY COUNT(*) DESC
"""
)
market = cur.fetchall()
print(f"Total symbols: {len(market)}")
for r in market:
    print(f"  {r[0]}: {r[1]:,} rows ({r[2]} to {r[3]})")

# Legacy CFTC COT
print("\n### LEGACY CFTC COT (raw.cftc_cot_1w) ###")
try:
    cur.execute(
        "SELECT COUNT(*), MIN(report_date), MAX(report_date) FROM raw.cftc_cot_1w"
    )
    r = cur.fetchone()
    print(f"  {r[0]:,} rows ({r[1]} to {r[2]})")
except Exception as e:
    print(f"  Error: {e}")

# Legacy USDA data
print("\n### LEGACY USDA DATA ###")
usda_tables = ["raw.usda_wasde_1m", "raw.usda_export_sales_1w"]
for table in usda_tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        cnt = cur.fetchone()[0]
        print(f"  {table}: {cnt:,} rows")
    except Exception as e:
        print(f"  {table}: Missing or error")

conn.close()
print("\n" + "=" * 70)
