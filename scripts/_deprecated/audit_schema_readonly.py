#!/usr/bin/env python3
"""Schema audit - READ ONLY inspection"""
import os
import psycopg2
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

print('='*70)
print('SCHEMA AUDIT - READ ONLY')
print('='*70)

# 1. Check all schemas
print('\n=== ALL SCHEMAS ===')
cur.execute("""
    SELECT schema_name 
    FROM information_schema.schemata 
    WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
    ORDER BY schema_name
""")
for r in cur.fetchall():
    print(f'  {r[0]}')

# 2. Count tables per schema
print('\n=== TABLES PER SCHEMA ===')
cur.execute("""
    SELECT table_schema, COUNT(*) as cnt
    FROM information_schema.tables
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
    GROUP BY table_schema
    ORDER BY table_schema
""")
for r in cur.fetchall():
    print(f'  {r[0]}: {r[1]} tables')

# 3. RAW schema tables (full list)
print('\n=== RAW SCHEMA TABLES ===')
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'raw'
    ORDER BY table_name
""")
raw_tables = [r[0] for r in cur.fetchall()]
for t in raw_tables:
    print(f'  {t}')
print(f'  TOTAL: {len(raw_tables)} tables')

# 4. FEATURES schema tables
print('\n=== FEATURES SCHEMA TABLES ===')
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'features'
    ORDER BY table_name
""")
feat_tables = [r[0] for r in cur.fetchall()]
for t in feat_tables:
    print(f'  {t}')
print(f'  TOTAL: {len(feat_tables)} tables')

# 5. TRAINING schema tables
print('\n=== TRAINING SCHEMA TABLES ===')
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'training'
    ORDER BY table_name
""")
train_tables = [r[0] for r in cur.fetchall()]
for t in train_tables:
    print(f'  {t}')
print(f'  TOTAL: {len(train_tables)} tables')

# 6. Check for potential synthetic/fake data
print('\n=== FAKE DATA CHECK ===')

# Check trump_effect_1d - is it synthetic?
cur.execute("""
    SELECT 
        MIN(as_of_date) as min_date,
        MAX(as_of_date) as max_date,
        COUNT(*) as total,
        SUM(CASE WHEN eo_count_7d > 0 THEN 1 ELSE 0 END) as days_with_eos
    FROM features.trump_effect_1d
""")
r = cur.fetchone()
print(f'  features.trump_effect_1d:')
print(f'    Date range: {r[0]} to {r[1]}')
print(f'    Total rows: {r[2]}')
print(f'    Days with EO counts: {r[3]}')

# Check if EO counts look synthetic (hash-based = same pattern)
cur.execute("""
    SELECT as_of_date, eo_count_7d, eo_count_30d, total_actions_7d
    FROM features.trump_effect_1d
    WHERE as_of_date >= '2025-01-01'
    ORDER BY as_of_date DESC
    LIMIT 15
""")
print('\n    Recent trump_effect_1d data:')
for r in cur.fetchall():
    print(f'      {r[0]}: EO_7d={r[1]}, EO_30d={r[2]}, Total_7d={r[3]}')

# Check whitehouse_actions_event (REAL data)
cur.execute("""
    SELECT COUNT(*), MIN(action_date), MAX(action_date)
    FROM raw.whitehouse_actions_event
""")
r = cur.fetchone()
print(f'\n  raw.whitehouse_actions_event:')
print(f'    Total rows: {r[0]}')
print(f'    Date range: {r[1]} to {r[2]}')

# Compare - do the counts match?
print('\n=== REAL vs SYNTHETIC CHECK ===')
cur.execute("""
    SELECT action_type, COUNT(*) 
    FROM raw.whitehouse_actions_event
    GROUP BY action_type
""")
print('  Real WhiteHouse actions by type:')
for r in cur.fetchall():
    print(f'    {r[0]}: {r[1]}')

conn.close()
