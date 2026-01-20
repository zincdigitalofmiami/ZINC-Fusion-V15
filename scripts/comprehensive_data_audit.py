#!/usr/bin/env python3
"""
ZINC-FUSION-V15: COMPREHENSIVE DATA QUALITY AUDIT
Find all fake/placeholder/empty data across the entire database
"""
import os
import psycopg2
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

print('='*80)
print('ZINC-FUSION-V15: COMPREHENSIVE DATA QUALITY AUDIT')
print('='*80)

# ============================================================================
# 1. METADATA SCHEMA - Symbol Mapping
# ============================================================================
print('\n' + '='*60)
print('1. METADATA SCHEMA')
print('='*60)

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'metadata'")
meta_tables = [r[0] for r in cur.fetchall()]
print(f'\nTables: {meta_tables}')

for table in meta_tables:
    cur.execute(f'SELECT COUNT(*) FROM metadata."{table}"')
    cnt = cur.fetchone()[0]
    print(f'  metadata.{table}: {cnt} rows')

# Check symbol_mapping specifically
cur.execute("""
    SELECT column_name FROM information_schema.columns 
    WHERE table_schema = 'metadata' AND table_name = 'symbol_mapping'
""")
cols = [r[0] for r in cur.fetchall()]
print(f'\nmetadata.symbol_mapping columns: {cols}')

cur.execute('SELECT * FROM metadata.symbol_mapping LIMIT 20')
rows = cur.fetchall()
print(f'\nmetadata.symbol_mapping contents ({len(rows)} shown):')
for r in rows:
    print(f'  {r}')

# ============================================================================
# 2. MODEL SCHEMA - Check for placeholders/empty
# ============================================================================
print('\n' + '='*60)
print('2. MODEL SCHEMA - Artifact Check')
print('='*60)

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'model' AND table_type = 'BASE TABLE'")
model_tables = [r[0] for r in cur.fetchall()]

for table in sorted(model_tables):
    cur.execute(f'SELECT COUNT(*) FROM model."{table}"')
    cnt = cur.fetchone()[0]
    status = '✅' if cnt > 0 else '❌ EMPTY'
    print(f'  model.{table}: {cnt} rows {status}')

# Check GARCH parameters
print('\n  GARCH Parameters sample:')
cur.execute('SELECT * FROM model.garch_parameters LIMIT 5')
for r in cur.fetchall():
    print(f'    {r}')

# Check Lasso coefficients
print('\n  Lasso Coefficients sample:')
cur.execute('SELECT * FROM model.lasso_coefficients LIMIT 5')
for r in cur.fetchall():
    print(f'    {r}')

# Check meta_weights
print('\n  Meta Weights sample:')
cur.execute('SELECT * FROM model.meta_weights LIMIT 10')
for r in cur.fetchall():
    print(f'    {r}')

# ============================================================================
# 3. FEATURES SCHEMA - Why only trump_effect?
# ============================================================================
print('\n' + '='*60)
print('3. FEATURES SCHEMA - Architecture Question')
print('='*60)

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'features'")
feat_tables = [r[0] for r in cur.fetchall()]
print(f'\nFeatures tables: {feat_tables}')
print(f'Total: {len(feat_tables)} tables')

# What SHOULD be here per architecture?
print('\nExpected per architecture (from project docs):')
expected_features = [
    'crush_1d', 'china_1d', 'fx_1d', 'fed_1d', 'tariff_1d',
    'energy_1d', 'biofuel_1d', 'palm_1d', 'volatility_1d', 
    'substitutes_1d', 'trump_effect_1d', 'core_1d'
]
for f in expected_features:
    exists = f in feat_tables
    status = '✅' if exists else '❌ MISSING'
    print(f'  features.{f}: {status}')

# ============================================================================
# 4. TRAINING SCHEMA - Check specialist_features JSON structure
# ============================================================================
print('\n' + '='*60)
print('4. TRAINING SCHEMA - Specialist Features')
print('='*60)

# Check training.specialist_features (JSON storage)
cur.execute("""
    SELECT bucket, COUNT(*), MIN(as_of_date), MAX(as_of_date)
    FROM training.specialist_features
    GROUP BY bucket
    ORDER BY bucket
""")
print('\ntraining.specialist_features by bucket:')
for r in cur.fetchall():
    print(f'  {r[0]}: {r[1]} rows ({r[2]} to {r[3]})')

# ============================================================================
# 5. CHECK FOR PLACEHOLDER/FAKE DATA PATTERNS
# ============================================================================
print('\n' + '='*60)
print('5. FAKE/PLACEHOLDER DATA DETECTION')
print('='*60)

# Check meta_weights for placeholder values
print('\n5a. model.meta_weights - checking for placeholder weights:')
cur.execute('SELECT COUNT(*) FROM model.meta_weights')
mw_cnt = cur.fetchone()[0]
if mw_cnt == 0:
    print('  ❌ EMPTY - No meta weights')
    rows = []
else:
    cur.execute('SELECT * FROM model.meta_weights LIMIT 30')
    rows = cur.fetchall()
# Check if weights look suspiciously uniform
weights = [r[2] for r in rows if r[2] is not None]
if weights:
    unique_weights = set(weights)
    if len(unique_weights) <= 3:
        print(f'  ⚠️  SUSPICIOUS: Only {len(unique_weights)} unique weight values: {unique_weights}')
    else:
        print(f'  ✅ Diverse weights: {len(unique_weights)} unique values')
for r in rows[:15]:
    print(f'    {r}')

# Check garch_parameters for placeholder
print('\n5b. model.garch_parameters - checking for placeholder:')
cur.execute('SELECT COUNT(*) FROM model.garch_parameters')
garch_cnt = cur.fetchone()[0]
if garch_cnt == 0:
    print('  ❌ EMPTY - No GARCH parameters')
else:
    cur.execute('SELECT * FROM model.garch_parameters LIMIT 5')
    for r in cur.fetchall():
        print(f'    {r}')

# Check lasso_coefficients
print('\n5c. model.lasso_coefficients - checking for placeholder:')
cur.execute('SELECT COUNT(*) FROM model.lasso_coefficients')
lasso_cnt = cur.fetchone()[0]
if lasso_cnt == 0:
    print('  ❌ EMPTY - No Lasso coefficients')
else:
    cur.execute('SELECT * FROM model.lasso_coefficients LIMIT 5')
    for r in cur.fetchall():
        print(f'    {r}')

# Check OOF predictions
print('\n5d. model.oof_predictions - CRITICAL for stacking:')
cur.execute('SELECT COUNT(*) FROM model.oof_predictions')
oof_cnt = cur.fetchone()[0]
if oof_cnt == 0:
    print('  ❌ EMPTY - HARD BLOCKER for L1 Meta-Learner')
else:
    print(f'  ✅ {oof_cnt} rows')

# Check cv_folds
print('\n5e. model.cv_folds:')
cur.execute('SELECT COUNT(*) FROM model.cv_folds')
cv_cnt = cur.fetchone()[0]
if cv_cnt == 0:
    print('  ❌ EMPTY - No CV fold definitions')
else:
    cur.execute('SELECT * FROM model.cv_folds LIMIT 5')
    for r in cur.fetchall():
        print(f'    {r}')

# ============================================================================
# 6. ANALYTICS SCHEMA - Missing tables
# ============================================================================
print('\n' + '='*60)
print('6. ANALYTICS SCHEMA - Missing SoT tables')
print('='*60)

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'analytics'")
analytics_tables = [r[0] for r in cur.fetchall()]
print(f'\nExisting analytics tables: {analytics_tables}')

expected_analytics = [
    'event_probabilities_1d',
    'price_scenarios_bull',
    'price_scenarios_bear', 
    'price_scenarios_base',
    'driver_attribution_1d',
    'regime_state_1d',
    'market_posture',
    'driver_scores',
    'risk_metrics',
    'vol_regimes'
]
print('\nExpected vs Actual:')
for t in expected_analytics:
    exists = t in analytics_tables
    status = '✅' if exists else '❌ MISSING'
    print(f'  analytics.{t}: {status}')

# ============================================================================
# 7. RAW DATA FRESHNESS
# ============================================================================
print('\n' + '='*60)
print('7. LANDING DATA FRESHNESS')
print('='*60)

landing_freshness = [
    # Market data
    ('mkt', 'futures_1d', 'event_date', 'ZL prices'),
    ('mkt', 'fx_1d', 'event_date', 'FX rates'),
    ('mkt', 'options_1d', 'event_date', 'Options'),
    # Economic data
    ('econ', 'rates_1d', 'event_date', 'FRED rates'),
    ('econ', 'vol_indices_1d', 'event_date', 'VIX/OVX'),
    ('econ', 'commodities_1d', 'event_date', 'Commodities'),
    # Positioning
    ('pos', 'cftc_1w', 'event_date', 'CFTC positioning'),
    # Supply data
    ('supply', 'epa_rin_1d', 'event_date', 'RIN prices'),
    # Alternative data
    ('alt', 'weather_1d', 'event_date', 'Weather'),
    ('alt', 'news_1d', 'event_date', 'News'),
    ('alt', 'legislation_1d', 'event_date', 'Legislation'),
]

from datetime import datetime
today = datetime.now().date()

for schema, table, date_col, desc in landing_freshness:
    try:
        cur.execute(f'SELECT COUNT(*), MAX({date_col})::date FROM {schema}."{table}"')
        cnt, max_date = cur.fetchone()
        if max_date:
            days_stale = (today - max_date).days
            status = '✅' if days_stale <= 7 else '⚠️' if days_stale <= 14 else '❌'
            print(f'  {desc:20} ({schema}.{table}): {cnt:,} rows, last {max_date}, {days_stale}d stale {status}')
        else:
            print(f'  {desc:20} ({schema}.{table}): {cnt:,} rows, NO DATE ❌')
    except Exception as e:
        print(f'  {desc:20} ({schema}.{table}): ERROR - {e}')

# ============================================================================
# 8. TRAINING MATRIX TABLES
# ============================================================================
print('\n' + '='*60)
print('8. TRAINING MATRIX TABLES (SoT)')
print('='*60)

cur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'training' AND table_name LIKE '%matrix%'
""")
matrix_tables = [r[0] for r in cur.fetchall()]
print(f'\nExisting matrix tables: {matrix_tables}')

expected_matrix = ['core_matrix_5d', 'core_matrix_21d', 'core_matrix_63d', 'core_matrix_126d',
                   'meta_inputs_5d', 'meta_inputs_21d', 'meta_inputs_63d', 'meta_inputs_126d']
print('\nExpected vs Actual:')
for t in expected_matrix:
    exists = t in matrix_tables
    status = '✅' if exists else '❌ MISSING'
    print(f'  training.{t}: {status}')

conn.close()

print('\n' + '='*80)
print('AUDIT COMPLETE')
print('='*80)
