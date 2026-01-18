#!/usr/bin/env python3
"""Quick data readiness check for 5d core training."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.vercel")

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

print("=" * 60)
print("DATA READINESS CHECK FOR 5D CORE TRAINING")
print("=" * 60)

# Check ZL
cur.execute(
    """
    SELECT COUNT(*), MIN(event_date), MAX(event_date) 
    FROM mkt.futures_1d 
    WHERE symbol='ZL'
"""
)
zl_count, zl_min, zl_max = cur.fetchone()
print(f"\n✅ ZL (target): {zl_count:,} rows")
print(f"   Date range: {zl_min} to {zl_max}")

# Check ZS and ZM for crush spread
cur.execute(
    """
    SELECT symbol, COUNT(*), MIN(event_date), MAX(event_date)
    FROM mkt.futures_1d 
    WHERE symbol IN ('ZS', 'ZM')
    GROUP BY symbol
"""
)
for symbol, count, min_date, max_date in cur.fetchall():
    print(f"\n✅ {symbol} (crush spread): {count:,} rows")
    print(f"   Date range: {min_date} to {max_date}")

# Check FRED series
fred_series = ["DCOILWTICO", "VIXCLS", "DTWEXBGS"]
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
    SELECT series_id, COUNT(*), MIN(event_date), MAX(event_date)
    FROM econ
    WHERE series_id IN %s
    GROUP BY series_id
""",
    (tuple(fred_series),),
)
fred_results = cur.fetchall()
print(f"\n📊 FRED Economic Data:")
for series_id, count, min_date, max_date in fred_results:
    print(f"   ✅ {series_id}: {count:,} rows ({min_date} to {max_date})")

if len(fred_results) < len(fred_series):
    found = {r[0] for r in fred_results}
    missing = set(fred_series) - found
    for m in missing:
        print(f"   ❌ {m}: MISSING")

# Legacy COT (raw.cftc_cot_1w) - optional in schema v2
try:
    cur.execute(
        """
        SELECT COUNT(*), MIN(event_date), MAX(event_date)
        FROM raw.cftc_cot_1w 
        WHERE symbol='ZL'
    """
    )
    cot_count, cot_min, cot_max = cur.fetchone()
    print(f"\n✅ Legacy CFTC COT (ZL): {cot_count:,} rows")
    if cot_count > 0:
        print(f"   Date range: {cot_min} to {cot_max}")
except Exception:
    print("\n⚠️  Legacy CFTC COT check skipped (raw.cftc_cot_1w not available)")

# Check for 7 years of data (tactical requirement)
cur.execute(
    """
    SELECT COUNT(*) 
    FROM mkt.futures_1d 
    WHERE symbol='ZL' 
      AND event_date >= CURRENT_DATE - INTERVAL '7 years'
"""
)
recent_count = cur.fetchone()[0]
print(f"\n📅 Last 7 years (tactical window): {recent_count:,} rows")

# Estimate if we have enough
if recent_count < 252 * 5:  # ~5 years of trading days
    print("   ⚠️  May not have full 7 years (minimum ~1,260 rows)")
else:
    print("   ✅ Sufficient for 7-year tactical window")

print("\n" + "=" * 60)
if zl_count > 1000 and recent_count > 1000:
    print("✅ READY FOR 5D TRAINING")
else:
    print("❌ INSUFFICIENT DATA")
print("=" * 60)

conn.close()
