#!/usr/bin/env python3
"""
Database State Audit - Check current state before Phase 3
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

print("=" * 70)
print("DATABASE STATE AUDIT")
print("=" * 70)

# 1. Check features.elite_1d columns
print("\n### GOLD.ELITE_INDICATORS_1D COLUMNS ###")
cur.execute(
    """
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'gold' AND table_name = 'elite_indicators_1d'
    ORDER BY ordinal_position
    LIMIT 15
"""
)
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

# 2. Check actual data
print("\n### GOLD.ELITE_INDICATORS_1D DATA (ZL) ###")
cur.execute(
    """
    SELECT COUNT(*), MIN(trade_date), MAX(trade_date)
    FROM features.elite_1d WHERE symbol = 'ZL'
"""
)
r = cur.fetchone()
print(f"  ZL rows: {r[0]:,}, range: {r[1]} to {r[2]}")

# 3. Check features.options_1d
print("\n### GOLD.OPTIONS_FEATURES_1D ###")
cur.execute(
    """
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'gold' AND table_name = 'options_features_1d'
    )
"""
)
exists = cur.fetchone()[0]
print(f"  Table exists: {exists}")

# 4. Check training.matrix_1d
print("\n### TRAINING.CORE_MATRIX_CURATED_1D ###")
cur.execute(
    """
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'training' AND table_name = 'matrix_1d'
    )
"""
)
exists = cur.fetchone()[0]
print(f"  Table exists: {exists}")

# 5. Check FRED duplicates detail
print("\n### FRED DUPLICATES (revision tracking) ###")
cur.execute(
    """
    SELECT series_id, event_date, revision_no, value
    FROM raw.fred_observations_1d
    WHERE series_id = 'VIXCLS' AND event_date = '2025-12-29'
    ORDER BY revision_no
"""
)
rows = cur.fetchall()
print(f"  VIXCLS on 2025-12-29:")
for r in rows:
    print(f"    revision {r[2]}: value={r[3]}")

# 6. Check training.core_matrix_1d (legacy)
print("\n### TRAINING.CORE_MATRIX_1D (legacy) ###")
cur.execute(
    """
    SELECT column_name FROM information_schema.columns 
    WHERE table_schema = 'training' AND table_name = 'core_matrix_1d'
    ORDER BY ordinal_position
"""
)
cols = [r[0] for r in cur.fetchall()]
print(f"  Columns ({len(cols)}): {cols[:10]}...")

cur.execute(
    "SELECT COUNT(*), MIN(as_of_date), MAX(as_of_date) FROM training.core_matrix_1d"
)
r = cur.fetchone()
print(f"  Rows: {r[0]:,}, range: {r[1]} to {r[2]}")

conn.close()
print("\n" + "=" * 70)
