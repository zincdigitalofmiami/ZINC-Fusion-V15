#!/usr/bin/env python3
"""
Compare Prisma schema.prisma models to actual Postgres tables
Detect drift - what's in Prisma but not in DB, and vice versa
"""
import os
import re
import psycopg2
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

print('='*70)
print('PRISMA vs POSTGRES DRIFT CHECK')
print('='*70)

# Parse Prisma schema
prisma_path = 'prisma/schema.prisma'
with open(prisma_path, 'r') as f:
    content = f.read()

# Extract models and their schemas
prisma_models = {}
current_model = None
for line in content.split('\n'):
    model_match = re.match(r'^model\s+(\w+)\s*\{', line)
    if model_match:
        current_model = model_match.group(1)
    schema_match = re.search(r'@@schema\("(\w+)"\)', line)
    if schema_match and current_model:
        schema = schema_match.group(1)
        # Convert PascalCase to snake_case
        table_name = re.sub(r'(?<!^)(?=[A-Z])', '_', current_model).lower()
        prisma_models[f"{schema}.{table_name}"] = current_model
        current_model = None

print(f'\n=== PRISMA MODELS: {len(prisma_models)} ===')

# Get actual Postgres tables
cur.execute("""
    SELECT table_schema, table_name 
    FROM information_schema.tables
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'public')
    ORDER BY table_schema, table_name
""")
postgres_tables = set()
for schema, table in cur.fetchall():
    postgres_tables.add(f"{schema}.{table}")

print(f'=== POSTGRES TABLES: {len(postgres_tables)} ===')

# Find differences
prisma_set = set(prisma_models.keys())

# In Prisma but not in Postgres
missing_in_postgres = prisma_set - postgres_tables
if missing_in_postgres:
    print(f'\n❌ IN PRISMA BUT NOT IN POSTGRES ({len(missing_in_postgres)}):')
    for t in sorted(missing_in_postgres):
        print(f'   {t} (model: {prisma_models[t]})')
else:
    print('\n✅ All Prisma models exist in Postgres')

# In Postgres but not in Prisma
missing_in_prisma = postgres_tables - prisma_set
if missing_in_prisma:
    print(f'\n⚠️  IN POSTGRES BUT NOT IN PRISMA ({len(missing_in_prisma)}):')
    for t in sorted(missing_in_prisma):
        print(f'   {t}')
else:
    print('\n✅ All Postgres tables are in Prisma')

# Summary by schema
print('\n=== TABLE COUNT BY SCHEMA ===')
print(f'{"Schema":<15} {"Prisma":<10} {"Postgres":<10} {"Match":<10}')
print('-'*45)

schemas = set([t.split('.')[0] for t in prisma_set | postgres_tables])
for schema in sorted(schemas):
    prisma_count = len([t for t in prisma_set if t.startswith(f'{schema}.')])
    pg_count = len([t for t in postgres_tables if t.startswith(f'{schema}.')])
    match = '✅' if prisma_count == pg_count else '❌'
    print(f'{schema:<15} {prisma_count:<10} {pg_count:<10} {match:<10}')

# Check RAW schema specifically
print('\n=== RAW SCHEMA DETAILED ===')
raw_prisma = sorted([t for t in prisma_set if t.startswith('raw.')])
raw_pg = sorted([t for t in postgres_tables if t.startswith('raw.')])

print(f'  Prisma RAW tables: {len(raw_prisma)}')
print(f'  Postgres RAW tables: {len(raw_pg)}')

raw_missing_pg = set(raw_prisma) - set(raw_pg)
raw_missing_prisma = set(raw_pg) - set(raw_prisma)

if raw_missing_pg:
    print(f'\n  ❌ RAW tables in Prisma but not Postgres:')
    for t in sorted(raw_missing_pg):
        print(f'     {t}')
        
if raw_missing_prisma:
    print(f'\n  ⚠️  RAW tables in Postgres but not Prisma:')
    for t in sorted(raw_missing_prisma):
        print(f'     {t}')

# Check features schema
print('\n=== FEATURES SCHEMA DETAILED ===')
feat_prisma = sorted([t for t in prisma_set if t.startswith('features.')])
feat_pg = sorted([t for t in postgres_tables if t.startswith('features.')])
print(f'  Prisma: {feat_prisma}')
print(f'  Postgres: {feat_pg}')

conn.close()
