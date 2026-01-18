#!/usr/bin/env python3
"""
Core Training Data Audit - Check all data required for Core model training.
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

print("=" * 70)
print("CORE TRAINING DATA AUDIT")
print("=" * 70)

# 1. Check ZL price data (primary target)
print("\n### 1. ZL PRICE DATA (mkt.futures_1d) ###")
cur.execute(
    """
    SELECT 
        MIN(event_date) as start,
        MAX(event_date) as end,
        COUNT(*) as rows,
        COUNT(*) FILTER (WHERE close IS NULL) as null_close,
        COUNT(*) FILTER (WHERE volume IS NULL OR volume = 0) as zero_vol
    FROM mkt.futures_1d 
    WHERE symbol = 'ZL'
"""
)
r = cur.fetchone()
print(f"  Range: {r[0]} to {r[1]}")
print(f"  Rows: {r[2]:,}")
print(f"  Null close: {r[3]}, Zero volume: {r[4]}")

# 2. Check elite indicators
print("\n### 2. ELITE INDICATORS (features.elite_1d) ###")
cur.execute(
    """
    SELECT 
        MIN(event_date) as start,
        MAX(event_date) as end,
        COUNT(*) as rows
    FROM features.elite_1d 
    WHERE symbol = 'ZL'
"""
)
r = cur.fetchone()
print(f"  Range: {r[0]} to {r[1]}")
print(f"  Rows: {r[2]:,}")

# Check key indicator coverage
indicators = [
    "connors_rsi",
    "garman_klass_vol",
    "cmf_21",
    "hurst_exponent",
    "fisher_transform",
    "ttm_squeeze_on",
]
query = ", ".join([f"COUNT(*) FILTER (WHERE {ind} IS NOT NULL)" for ind in indicators])
cur.execute(
    f"""
    SELECT {query}
    FROM features.elite_1d 
    WHERE symbol = 'ZL'
"""
)
r = cur.fetchone()
print("  Indicator coverage:")
for i, ind in enumerate(indicators):
    print(f"    {ind}: {r[i]:,} rows")

# 3. Check training feature matrix
print("\n### 3. TRAINING MATRIX (training.matrix_1d) ###")
cur.execute(
    """
    SELECT 
        MIN(as_of_date) as start,
        MAX(as_of_date) as end,
        COUNT(*) as rows
    FROM training.matrix_1d
"""
)
r = cur.fetchone()
if r[0]:
    print(f"  Range: {r[0]} to {r[1]}")
    print(f"  Rows: {r[2]:,}")
else:
    print("  ⚠️  TABLE EMPTY OR NOT POPULATED")

# Check target columns
cur.execute(
    """
    SELECT column_name FROM information_schema.columns 
    WHERE table_schema = 'training' AND table_name = 'matrix_1d'
    AND column_name LIKE 'target_%'
    ORDER BY column_name
"""
)
targets = [r[0] for r in cur.fetchall()]
print(f"  Target columns: {targets}")

# 4. Check FRED macro data
print("\n### 4. FRED MACRO DATA (econ.rates_1d) ###")
key_series = ["VIXCLS", "DGS10", "FEDFUNDS", "DCOILWTICO", "DEXUSEU", "USEPUINDXD"]
for series in key_series:
    cur.execute(
        """
        SELECT MIN(event_date), MAX(event_date), COUNT(*)
        FROM econ.rates_1d WHERE series_id = %s
    """,
        (series,),
    )
    r = cur.fetchone()
    if r[0]:
        print(f"  {series}: {r[0]} to {r[1]} ({r[2]:,} rows)")
    else:
        print(f"  {series}: ⚠️  MISSING")

# 5. Check other key raw tables
print("\n### 5. OTHER KEY RAW TABLES ###")
tables = [
    ("mkt.fx_1d", "event_date"),
    ("pos.cftc_1w", "report_date"),
    ("supply.usda_wasde_1m", "report_date"),
    ("supply.usda_exports_1w", "week_ending"),
]
for table, date_col in tables:
    try:
        cur.execute(f"SELECT MIN({date_col}), MAX({date_col}), COUNT(*) FROM {table}")
        r = cur.fetchone()
        if r[0]:
            print(f"  {table}: {r[0]} to {r[1]} ({r[2]:,} rows)")
        else:
            print(f"  {table}: ⚠️  EMPTY")
    except Exception as e:
        print(f"  {table}: ⚠️  ERROR - {str(e)[:50]}")
        conn.rollback()

# 6. Check OOF tables (training outputs)
print("\n### 6. OOF TABLES (training outputs) ###")
oof_tables = ["training.oof_core_1d"]
for table in oof_tables:
    try:
        cur.execute(f"SELECT MIN(as_of_date), MAX(as_of_date), COUNT(*) FROM {table}")
        r = cur.fetchone()
        if r[0]:
            print(f"  {table}: {r[0]} to {r[1]} ({r[2]:,} rows)")
        else:
            print(f"  {table}: Empty (not yet trained)")
    except Exception as e:
        print(f"  {table}: ⚠️  {str(e)[:40]}")
        conn.rollback()

# 7. Check related instruments (for crush spread, etc)
print("\n### 7. RELATED INSTRUMENTS (mkt.futures_1d) ###")
instruments = ["ZS", "ZM", "CL", "HO", "NG"]
for sym in instruments:
    cur.execute(
        """
        SELECT MIN(event_date), MAX(event_date), COUNT(*)
        FROM mkt.futures_1d WHERE symbol = %s
    """,
        (sym,),
    )
    r = cur.fetchone()
    if r[0]:
        print(f"  {sym}: {r[0]} to {r[1]} ({r[2]:,} rows)")
    else:
        print(f"  {sym}: ⚠️  MISSING")

# 8. Check date gaps in ZL
print("\n### 8. ZL DATE GAPS (recent 30 days) ###")
cur.execute(
    """
    WITH dates AS (
        SELECT event_date FROM mkt.futures_1d 
        WHERE symbol = 'ZL' AND event_date > CURRENT_DATE - 60
        ORDER BY event_date DESC LIMIT 30
    )
    SELECT MIN(event_date), MAX(event_date), COUNT(*) FROM dates
"""
)
r = cur.fetchone()
print(f"  Recent range: {r[0]} to {r[1]} ({r[2]} trading days)")

conn.close()
print("\n" + "=" * 70)
print("AUDIT COMPLETE")
print("=" * 70)
