#!/usr/bin/env python3
"""Direct training schema validation"""
import pandas as pd
from dotenv import load_dotenv
import sys
sys.path.insert(0, '/Volumes/Satechi Hub/ZINC-FUSION-V15/src')
load_dotenv('/Volumes/Satechi Hub/ZINC-FUSION-V15/.env')
from fusion.db.connection import get_read_engine

engine = get_read_engine()

# List all training tables with row counts
print("=" * 80)
print("TRAINING SCHEMA - ALL TABLES")
print("=" * 80)

q = """
SELECT table_name
FROM information_schema.tables 
WHERE table_schema = 'training'
ORDER BY table_name
"""
tables = pd.read_sql(q, engine)['table_name'].tolist()

for table in tables:
    try:
        cnt_q = f'SELECT COUNT(*) as cnt FROM "training"."{table}"'
        cnt = pd.read_sql(cnt_q, engine).iloc[0]['cnt']
        
        # Get column list
        cols_q = f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'training' AND table_name = '{table}'
            ORDER BY ordinal_position
        """
        cols = pd.read_sql(cols_q, engine)['column_name'].tolist()
        
        # Check for target columns
        target_cols = [c for c in cols if 'target' in c]
        
        status = ""
        if cnt == 0:
            status = " ⬜ EMPTY"
        elif 'specialist_' in table and not target_cols:
            status = " ❌ NO TARGETS"
        elif target_cols:
            status = f" ✅ targets: {target_cols}"
        
        print(f"  {table:<50} | {cnt:>8,} rows | {len(cols):>3} cols{status}")
    except Exception as e:
        print(f"  {table:<50} | ERROR: {e}")

# Check for weight/placeholder columns specifically
print("\n" + "=" * 80)
print("WEIGHT/CONTRIBUTION COLUMNS CHECK")
print("=" * 80)

weight_q = """
SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'training'
AND (column_name LIKE '%weight%' OR column_name LIKE '%contrib%' OR column_name LIKE '%coefficient%')
ORDER BY table_name, column_name
"""
weight_cols = pd.read_sql(weight_q, engine)

if len(weight_cols) > 0:
    print(f"Found {len(weight_cols)} weight/contribution columns:")
    for _, row in weight_cols.iterrows():
        tbl = row['table_name']
        col = row['column_name']
        
        # Sample values
        try:
            sample_q = f'SELECT DISTINCT "{col}" FROM "training"."{tbl}" WHERE "{col}" IS NOT NULL LIMIT 10'
            samples = pd.read_sql(sample_q, engine)[col].tolist()
            print(f"  {tbl}.{col}: {samples}")
        except Exception as e:
            print(f"  {tbl}.{col}: ERROR - {e}")
else:
    print("✅ No weight/contribution columns found")

# Check OOF tables specifically
print("\n" + "=" * 80)
print("OOF TABLES DETAIL")
print("=" * 80)

oof_tables = [t for t in tables if 'oof_' in t]
if oof_tables:
    for table in oof_tables:
        cols_q = f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'training' AND table_name = '{table}'
        """
        cols = pd.read_sql(cols_q, engine)['column_name'].tolist()
        cnt_q = f'SELECT COUNT(*) as cnt FROM "training"."{table}"'
        cnt = pd.read_sql(cnt_q, engine).iloc[0]['cnt']
        
        print(f"\n{table}:")
        print(f"  Rows: {cnt}")
        print(f"  Columns: {cols}")
else:
    print("❌ NO OOF TABLES FOUND")

# Check core_matrix_1d for target columns
print("\n" + "=" * 80)
print("CORE MATRIX TARGET VALIDATION")
print("=" * 80)

try:
    stats_q = """
    SELECT 
        COUNT(*) as total_rows,
        COUNT(target_5d) as non_null_5d,
        COUNT(target_21d) as non_null_21d,
        COUNT(target_63d) as non_null_63d,
        COUNT(target_126d) as non_null_126d,
        MIN(target_5d) as min_5d,
        MAX(target_5d) as max_5d,
        AVG(target_5d) as avg_5d
    FROM "training"."core_matrix_1d"
    """
    stats = pd.read_sql(stats_q, engine).iloc[0]
    print(f"Total rows: {stats['total_rows']:,}")
    print(f"target_5d:   {stats['non_null_5d']:,} non-null | range: {stats['min_5d']:.2f} to {stats['max_5d']:.2f}")
    print(f"target_21d:  {stats['non_null_21d']:,} non-null")
    print(f"target_63d:  {stats['non_null_63d']:,} non-null")
    print(f"target_126d: {stats['non_null_126d']:,} non-null")
except Exception as e:
    print(f"❌ ERROR: {e}")

# Check specialist tables for targets
print("\n" + "=" * 80)
print("SPECIALIST TABLES TARGET CHECK")
print("=" * 80)

specialists = ['crush', 'china', 'fx', 'fed', 'tariff', 'energy', 'biofuel', 'palm', 'volatility', 'substitutes', 'trump_effect']

for spec in specialists:
    table = f"specialist_{spec}_1d"
    try:
        # Check if table exists and has target columns
        cols_q = f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'training' AND table_name = '{table}'
            AND column_name LIKE 'target_%'
        """
        target_cols = pd.read_sql(cols_q, engine)['column_name'].tolist()
        
        cnt_q = f'SELECT COUNT(*) as cnt FROM "training"."{table}"'
        cnt = pd.read_sql(cnt_q, engine).iloc[0]['cnt']
        
        if target_cols:
            print(f"  {table:<40} | {cnt:>6,} rows | ✅ {target_cols}")
        else:
            print(f"  {table:<40} | {cnt:>6,} rows | ❌ NO TARGET COLUMNS")
    except Exception as e:
        print(f"  {table:<40} | ❌ TABLE NOT FOUND or ERROR: {e}")

print("\n" + "=" * 80)
print("VALIDATION COMPLETE")
print("=" * 80)
