#!/usr/bin/env python3
"""
ZINC-FUSION-V15: COMPREHENSIVE DATA QUALITY AUDIT v2
"""
import os
import sys
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

HAD_ERRORS = False


def run_query(cur, query):
    """Run query with error handling (no fallback values)."""
    global HAD_ERRORS
    try:
        cur.execute(query)
        return cur.fetchall()
    except Exception as e:
        HAD_ERRORS = True
        try:
            cur.connection.rollback()
        except Exception:
            pass
        print(f"[ERROR] Query failed: {e}")
        return None


conn = psycopg2.connect(os.getenv("DATABASE_URL"))
conn.autocommit = True  # Prevent transaction blocks
cur = conn.cursor()

print("=" * 80)
print("ZINC-FUSION-V15: COMPREHENSIVE DATA QUALITY AUDIT")
print("=" * 80)

# ============================================================================
# 1. METADATA - Symbol Mapping
# ============================================================================
print("\n" + "=" * 60)
print("1. METADATA - Symbol Mapping")
print("=" * 60)

result = run_query(cur, "SELECT COUNT(*) FROM metadata.symbol_mapping")
print(f'\nmetadata.symbol_mapping: {result[0][0] if result else "ERROR"} rows')

result = run_query(
    cur,
    "SELECT DISTINCT canonical_id FROM metadata.symbol_mapping ORDER BY canonical_id",
)
if isinstance(result, list):
    symbols = [r[0] for r in result]
    print(f"Mapped symbols ({len(symbols)}): {symbols}")
else:
    print(result)

# What symbols are we actually using?
result = run_query(
    cur, "SELECT DISTINCT symbol FROM mkt.futures_1d ORDER BY symbol"
)
if isinstance(result, list):
    actual_symbols = [r[0] for r in result]
    print(f"\nActual symbols in mkt.futures_1d ({len(actual_symbols)}):")
    print(
        f"  {actual_symbols[:20]}..."
        if len(actual_symbols) > 20
        else f"  {actual_symbols}"
    )

# ============================================================================
# 2. MODEL SCHEMA - Empty Tables (CRITICAL)
# ============================================================================
print("\n" + "=" * 60)
print("2. MODEL SCHEMA - Empty/Placeholder Check")
print("=" * 60)

model_tables = [
    "cv_folds",
    "garch_parameters",
    "lasso_coefficients",
    "meta_ensemble",
    "meta_weights",
    "model_leaderboard",
    "model_registry",
    "oof_predictions",
    "regime_probabilities",
    "shap_summary",
    "shap_values",
]

for table in model_tables:
    result = run_query(cur, f'SELECT COUNT(*) FROM model."{table}"')
    if isinstance(result, list):
        cnt = result[0][0]
        status = "✅" if cnt > 0 else "❌ EMPTY"
        print(f"  model.{table}: {cnt:,} rows {status}")
    else:
        print(f"  model.{table}: {result}")

# ============================================================================
# 3. FEATURES SCHEMA - Why only trump_effect?
# ============================================================================
print("\n" + "=" * 60)
print("3. FEATURES SCHEMA - Single Table Issue")
print("=" * 60)

result = run_query(
    cur,
    """
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'features' ORDER BY table_name
""",
)
if isinstance(result, list):
    print(f"Tables in features schema: {[r[0] for r in result]}")
    print(f"Total: {len(result)} table(s)")

# Check what the architecture docs say should be there
print("\nPer ZINC_FUSION_V15 architecture, specialist features go in:")
print("  - training.specialist_features (JSON blob per bucket per day)")
print("  - training.specialist_*_1d tables (denormalized)")
print("  - features schema is for COMPUTED features (trump_effect_1d is special case)")

# ============================================================================
# 4. TRAINING SCHEMA - Data Check
# ============================================================================
print("\n" + "=" * 60)
print("4. TRAINING SCHEMA - Specialist Data")
print("=" * 60)

# Check specialist_features JSON table
result = run_query(
    cur,
    """
    SELECT bucket, COUNT(*), MIN(as_of_date)::date, MAX(as_of_date)::date
    FROM training.specialist_features
    GROUP BY bucket ORDER BY bucket
""",
)
if isinstance(result, list):
    print("\ntraining.specialist_features by bucket:")
    for r in result:
        print(f"  {r[0]}: {r[1]:,} rows ({r[2]} to {r[3]})")

# Check denormalized specialist tables
print("\ntraining.specialist_*_1d tables:")
specialist_tables = [
    "biofuel",
    "china",
    "crush",
    "energy",
    "fed",
    "fx",
    "palm",
    "substitutes",
    "tariff",
    "trump_effect",
    "volatility",
]
for spec in specialist_tables:
    result = run_query(cur, f"SELECT COUNT(*) FROM training.specialist_{spec}_1d")
    if isinstance(result, list):
        print(f"  specialist_{spec}_1d: {result[0][0]:,} rows")

# ============================================================================
# 5. RAW DATA FRESHNESS
# ============================================================================
print("\n" + "=" * 60)
print("5. LANDING DATA FRESHNESS")
print("=" * 60)

today = datetime.now().date()
freshness_checks = [
    ("mkt", "futures_1d", "event_date", "ZL daily"),
    ("mkt", "fx_1d", "event_date", "FX rates"),
    ("pos", "cftc_1w", "event_date", "CFTC COT"),
    ("alt", "weather_1d", "event_date", "Weather"),
    ("supply", "epa_rin_1d", "event_date", "RIN prices"),
    ("alt", "news_1d", "event_date", "News"),
    ("econ", "rates_1d", "event_date", "FRED"),
]

for schema, table, date_col, desc in freshness_checks:
    result = run_query(
        cur, f'SELECT COUNT(*), MAX({date_col})::date FROM {schema}."{table}"'
    )
    if isinstance(result, list) and result[0][1]:
        cnt, max_date = result[0]
        days_stale = (today - max_date).days
        status = "✅" if days_stale <= 7 else "⚠️" if days_stale <= 14 else "❌"
        print(
            f"  {desc:20}: {cnt:>8,} rows, last {max_date}, {days_stale}d stale {status}"
        )
    elif isinstance(result, list):
        print(f"  {desc:20}: {result[0][0]:>8,} rows, NO DATA")
    else:
        print(f"  {desc:20}: ERROR checking")

# ============================================================================
# 6. ANALYTICS SCHEMA
# ============================================================================
print("\n" + "=" * 60)
print("6. ANALYTICS SCHEMA - Output Tables")
print("=" * 60)

result = run_query(
    cur,
    """
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'analytics' ORDER BY table_name
""",
)
if isinstance(result, list):
    print(f"Tables ({len(result)}): {[r[0] for r in result]}")

# Check key tables
analytics_checks = [
    "driver_scores",
    "market_posture",
    "risk_metrics",
    "vol_regimes",
    "regime_state_1d",
    "driver_attribution_1d",
]
for table in analytics_checks:
    result = run_query(cur, f'SELECT COUNT(*) FROM analytics."{table}"')
    if isinstance(result, list):
        status = "✅" if result[0][0] > 0 else "❌ EMPTY"
        print(f"  {table}: {result[0][0]:,} rows {status}")

# ============================================================================
# 7. FORECASTS SCHEMA
# ============================================================================
print("\n" + "=" * 60)
print("7. FORECASTS SCHEMA - Output Tables")
print("=" * 60)

result = run_query(
    cur,
    """
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'forecasts' ORDER BY table_name
""",
)
if isinstance(result, list):
    print(f"Tables ({len(result)}): {[r[0] for r in result]}")
    for table in [r[0] for r in result]:
        cnt_result = run_query(cur, f'SELECT COUNT(*) FROM forecasts."{table}"')
        if isinstance(cnt_result, list):
            status = "✅" if cnt_result[0][0] > 0 else "❌ EMPTY"
            print(f"  {table}: {cnt_result[0][0]:,} rows {status}")

# ============================================================================
# 8. FAKE DATA DETECTION - trump_effect_1d
# ============================================================================
print("\n" + "=" * 60)
print("8. FAKE DATA DETECTION")
print("=" * 60)

# Check if trump_effect EO counts are synthetic (hash-based)
result = run_query(
    cur,
    """
    SELECT as_of_date, eo_count_7d, eo_count_30d, total_actions_7d
    FROM features.trump_effect_1d
    WHERE eo_count_7d > 0 OR total_actions_7d > 0
    ORDER BY as_of_date DESC
    LIMIT 20
""",
)
if isinstance(result, list):
    print("\nfeatures.trump_effect_1d (days with actions):")
    for r in result[:10]:
        print(f"  {r[0]}: EO_7d={r[1]}, EO_30d={r[2]}, Total_7d={r[3]}")
    print(f"  ... showing {len(result)} days with non-zero counts")

# Compare to alt.news_1d whitehouse-sourced news
result = run_query(
    cur,
    """
    SELECT specialist_tags[1], COUNT(*), MIN(event_date), MAX(event_date)
    FROM alt.news_1d
    WHERE source LIKE 'whitehouse%'
    GROUP BY specialist_tags[1]
""",
)
if isinstance(result, list):
    print("\nalt.news_1d whitehouse sources (REAL data):")
    for r in result:
        print(f"  {r[0]}: {r[1]} rows ({r[2]} to {r[3]})")

# ============================================================================
# 9. MISSING SoT TABLES
# ============================================================================
print("\n" + "=" * 60)
print("9. MISSING TABLES (per architecture docs)")
print("=" * 60)

# Check for matrix tables
result = run_query(
    cur,
    """
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'training' AND table_name LIKE '%matrix%'
""",
)
matrix_tables = [r[0] for r in result] if isinstance(result, list) else []
print(f'\ntraining.*matrix* tables: {matrix_tables if matrix_tables else "NONE FOUND"}')

# Check for meta_inputs tables
result = run_query(
    cur,
    """
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'training' AND table_name LIKE '%meta_inputs%'
""",
)
meta_inputs = [r[0] for r in result] if isinstance(result, list) else []
print(f'training.*meta_inputs* tables: {meta_inputs if meta_inputs else "NONE FOUND"}')

# Check for event_probabilities
result = run_query(
    cur,
    """
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'analytics' AND table_name LIKE '%event%prob%'
""",
)
event_probs = [r[0] for r in result] if isinstance(result, list) else []
print(f'analytics.*event*prob* tables: {event_probs if event_probs else "NONE FOUND"}')

# Check for price_scenarios
result = run_query(
    cur,
    """
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'analytics' AND table_name LIKE '%scenario%'
""",
)
scenarios = [r[0] for r in result] if isinstance(result, list) else []
print(f"analytics.*scenario* tables: {scenarios}")

conn.close()

print("\n" + "=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)

sys.exit(1 if HAD_ERRORS else 0)
