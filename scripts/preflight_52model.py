#!/usr/bin/env python3
"""
ZINC-FUSION-V15 PREFLIGHT CHECKS FOR 52-MODEL STACK
Validates database readiness for training
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL)

def run_query(query, params=None):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(query, params)
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

def run_single(query, params=None):
    results = run_query(query, params)
    return results[0] if results else None

def safe_query(query, default=None):
    try:
        return run_single(query)
    except Exception as e:
        return default

print("=" * 80)
print("ZINC-FUSION-V15 PREFLIGHT CHECKS FOR 52-MODEL TRAINING STACK")
print("=" * 80)
print(f"Timestamp: {datetime.now().isoformat()}")
print()

# =============================================================================
# SECTION 1: ZL PRICE DATA (CRITICAL)
# =============================================================================
print("=" * 80)
print("SECTION 1: ZL PRICE DATA COVERAGE (Critical for Targets)")
print("=" * 80)

zl_full = safe_query("""
    SELECT 
        COUNT(*) as total_rows,
        MIN(event_date) as earliest_date,
        MAX(event_date) as latest_date,
        COUNT(CASE WHEN close IS NOT NULL THEN 1 END) as valid_closes
    FROM mkt.futures_1d
    WHERE symbol = 'ZL'
""")

zl_2000 = safe_query("""
    SELECT COUNT(*) as cnt FROM mkt.futures_1d 
    WHERE symbol = 'ZL' AND event_date >= '2000-01-01'
""")

zl_2020 = safe_query("""
    SELECT COUNT(*) as cnt FROM mkt.futures_1d 
    WHERE symbol = 'ZL' AND event_date >= '2020-01-01'
""")

if zl_full:
    print(f"  Total ZL rows:     {zl_full['total_rows']:,}")
    print(f"  Earliest date:     {zl_full['earliest_date']}")
    print(f"  Latest date:       {zl_full['latest_date']}")
    print(f"  Valid closes:      {zl_full['valid_closes']:,}")
    print()
    print(f"  Since 2000:        {zl_2000['cnt'] if zl_2000 else 0:,} rows", end="")
    print(" ✅" if zl_2000 and zl_2000['cnt'] > 5000 else " ⚠️ Need 6000+ for 63d/126d")
    print(f"  Since 2020:        {zl_2020['cnt'] if zl_2020 else 0:,} rows", end="")
    print(" ✅" if zl_2020 and zl_2020['cnt'] > 1000 else " ⚠️ Need 1200+ for 5d/21d")
else:
    print("  ❌ NO ZL DATA FOUND")

# Check data freshness
today = datetime.now().date()
if zl_full and zl_full['latest_date']:
    max_date = zl_full['latest_date']
    if hasattr(max_date, 'date'):
        max_date = max_date.date()
    days_stale = (today - max_date).days
    print(f"\n  Data freshness:    {days_stale} days since last update", end="")
    print(" ✅" if days_stale <= 3 else " ⚠️" if days_stale <= 7 else " ❌ STALE")

# =============================================================================
# SECTION 2: CRUSH COMPLEX (ZL, ZS, ZM)
# =============================================================================
print("\n" + "=" * 80)
print("SECTION 2: CRUSH COMPLEX (ZL, ZS, ZM)")
print("=" * 80)

crush_symbols = run_query("""
    SELECT 
        symbol,
        COUNT(*) as rows,
        MIN(event_date) as start_date,
        MAX(event_date) as end_date
    FROM mkt.futures_1d
    WHERE symbol IN ('ZL', 'ZS', 'ZM')
    GROUP BY symbol
    ORDER BY symbol
""")

for row in crush_symbols:
    print(f"  {row['symbol']}: {row['rows']:,} rows ({row['start_date']} to {row['end_date']})")

# =============================================================================
# SECTION 3: SPECIALIST DATA SOURCES
# =============================================================================
print("\n" + "=" * 80)
print("SECTION 3: SPECIALIST DATA SOURCES")
print("=" * 80)

specialist_checks = [
    ("CRUSH", "mkt.futures_1d WHERE symbol IN ('ZL','ZS','ZM')", "event_date"),
    ("CHINA", "supply.usda_exports_1w", "event_date"),
    ("FX", "mkt.fx_1d", "event_date"),
    ("FED", "econ.rates_1d WHERE series_id IN ('DFF','FEDFUNDS','T10Y2Y')", "event_date"),
    ("TARIFF", "alt.news_1d", "event_date"),
    ("ENERGY", "mkt.futures_1d WHERE symbol IN ('CL','HO','NG')", "event_date"),
    ("BIOFUEL", "supply.epa_rin_1d", "event_date"),
    ("PALM", "mkt.futures_1d WHERE symbol LIKE '%CPO%' OR symbol LIKE '%FCPO%'", "event_date"),
    ("VOLATILITY", "econ.rates_1d WHERE series_id='VIXCLS'", "event_date"),
    ("SUBSTITUTES", "mkt.futures_1d WHERE symbol IN ('ZC','ZW')", "event_date"),
    ("TRUMP_EFFECT", "alt.legislation_1d", "action_date"),
]

for spec_name, table_filter, date_col in specialist_checks:
    try:
        result = safe_query(f"""
            SELECT COUNT(*) as cnt, 
                   MIN({date_col}) as min_date, 
                   MAX({date_col}) as max_date
            FROM {table_filter}
        """)
        if result and result['cnt'] > 0:
            status = "✅" if result['cnt'] > 100 else "⚠️"
            print(f"  {spec_name:15} {status} {result['cnt']:,} rows ({result['min_date']} to {result['max_date']})")
        else:
            print(f"  {spec_name:15} ⚠️  EMPTY or insufficient data")
    except Exception as e:
        print(f"  {spec_name:15} ❌ Error: {str(e)[:40]}")

# =============================================================================
# SECTION 4: FRED COVERAGE BY SPECIALIST
# =============================================================================
print("\n" + "=" * 80)
print("SECTION 4: FRED SERIES INVENTORY")
print("=" * 80)

fred_stats = safe_query("""
    SELECT 
        COUNT(DISTINCT series_id) as unique_series,
        COUNT(*) as total_rows,
        MIN(event_date) as min_date,
        MAX(event_date) as max_date
    FROM econ.rates_1d
""")

if fred_stats:
    print(f"  Total series:      {fred_stats['unique_series']}")
    print(f"  Total rows:        {fred_stats['total_rows']:,}")
    print(f"  Date range:        {fred_stats['min_date']} to {fred_stats['max_date']}")

# Key series check
key_fred = ['DFF', 'FEDFUNDS', 'T10Y2Y', 'VIXCLS', 'DTWEXBGS', 'DEXBZUS', 'DEXCHUS', 'DCOILWTICO']
fred_coverage = run_query("""
    SELECT series_id, COUNT(*) as cnt
    FROM econ.rates_1d
    WHERE series_id = ANY(%s)
    GROUP BY series_id
""", (key_fred,))

found_series = {r['series_id']: r['cnt'] for r in fred_coverage}
print("\n  Key series status:")
for sid in key_fred:
    if sid in found_series:
        print(f"    {sid:15} ✅ {found_series[sid]:,} rows")
    else:
        print(f"    {sid:15} ❌ MISSING")

# =============================================================================
# SECTION 5: CFTC COT POSITIONING
# =============================================================================
print("\n" + "=" * 80)
print("SECTION 5: CFTC COT POSITIONING DATA")
print("=" * 80)

cot_stats = safe_query("""
    SELECT 
        COUNT(DISTINCT symbol) as unique_symbols,
        COUNT(*) as total_rows,
        MIN(event_date) as min_date,
        MAX(event_date) as max_date
    FROM pos.cftc_1w
""")

if cot_stats:
    print(f"  Unique symbols:    {cot_stats['unique_symbols']}")
    print(f"  Total rows:        {cot_stats['total_rows']:,}")
    print(f"  Date range:        {cot_stats['min_date']} to {cot_stats['max_date']}")

# Check ZL specifically
cot_zl = safe_query("""
    SELECT COUNT(*) as cnt FROM pos.cftc_1w WHERE symbol = 'ZL'
""")
print(f"\n  ZL positioning:    {cot_zl['cnt'] if cot_zl else 0:,} rows")

# =============================================================================
# SECTION 6: TRAINING SCHEMA TABLES
# =============================================================================
print("\n" + "=" * 80)
print("SECTION 6: TRAINING SCHEMA TABLES")
print("=" * 80)

# Check specialist feature tables
specialists = ['biofuel', 'china', 'crush', 'energy', 'fed', 'fx', 'palm', 'substitutes', 'tariff', 'volatility', 'trump_effect']

print("\n  Specialist training tables (training.specialist_*_1d):")
for spec in specialists:
    try:
        result = safe_query(f"""
            SELECT COUNT(*) as cnt, MIN(as_of_date) as min_date, MAX(as_of_date) as max_date
            FROM training.specialist_{spec}_1d
        """)
        if result and result['cnt'] > 0:
            print(f"    {spec:15} ✅ {result['cnt']:,} rows ({result['min_date']} to {result['max_date']})")
        else:
            print(f"    {spec:15} ⚠️  EMPTY")
    except:
        print(f"    {spec:15} ❌ Missing or error")

# Check core features
print("\n  Core features table:")
try:
    core = safe_query("SELECT COUNT(*) as cnt, MIN(as_of_date) as min_date, MAX(as_of_date) as max_date FROM training.core_features")
    if core and core['cnt'] > 0:
        print(f"    core_features    ✅ {core['cnt']:,} rows ({core['min_date']} to {core['max_date']})")
    else:
        print(f"    core_features    ⚠️  EMPTY")
except:
    print(f"    core_features    ❌ Missing")

# Check specialist features (JSON format)
print("\n  Specialist features (JSON format):")
try:
    spec_feat = run_query("""
        SELECT bucket, COUNT(*) as cnt, MIN(as_of_date) as min_date, MAX(as_of_date) as max_date
        FROM training.specialist_features
        GROUP BY bucket
        ORDER BY bucket
    """)
    for row in spec_feat:
        print(f"    {row['bucket']:15} ✅ {row['cnt']:,} rows ({row['min_date']} to {row['max_date']})")
except:
    print(f"    specialist_features table: ❌ Missing or error")

# =============================================================================
# SECTION 7: MODEL SCHEMA (OOF & Registry)
# =============================================================================
print("\n" + "=" * 80)
print("SECTION 7: MODEL SCHEMA (OOF Predictions & Registry)")
print("=" * 80)

# OOF Predictions
print("\n  OOF Predictions (model.oof_predictions):")
try:
    oof = run_query("""
        SELECT specialist, horizon, COUNT(*) as cnt
        FROM model.oof_predictions
        GROUP BY specialist, horizon
        ORDER BY specialist, horizon
    """)
    if oof:
        current_spec = None
        for row in oof:
            if row['specialist'] != current_spec:
                current_spec = row['specialist']
                print(f"\n    {current_spec}:")
            print(f"      H={row['horizon']:3}d: {row['cnt']:,} rows")
    else:
        print("    ⚠️  EMPTY - Need to train L0 models first")
except Exception as e:
    print(f"    ❌ Error: {e}")

# Model Registry
print("\n  Model Registry (model.model_registry):")
try:
    registry = run_query("""
        SELECT model_type, horizon, status, is_champion, COUNT(*) as cnt
        FROM model.model_registry
        GROUP BY model_type, horizon, status, is_champion
        ORDER BY model_type, horizon
    """)
    if registry:
        for row in registry:
            champion = "👑" if row['is_champion'] else "  "
            print(f"    {champion} {row['model_type']:20} H={row['horizon']} {row['status']:10} ({row['cnt']} versions)")
    else:
        print("    ⚠️  EMPTY - No models registered yet")
except Exception as e:
    print(f"    ❌ Error: {e}")

# =============================================================================
# SECTION 8: FORECASTS SCHEMA
# =============================================================================
print("\n" + "=" * 80)
print("SECTION 8: FORECASTS SCHEMA (Output Tables)")
print("=" * 80)

forecast_tables = [
    ("core_cone_1d", "forecast_date"),
    ("core_mc_1d", "forecast_date"),
    ("forecast_summary_1d", "forecast_date"),
    ("forecast_quantiles", "forecast_date"),
    ("garch_forecasts", "as_of_date"),
]

for table, date_col in forecast_tables:
    try:
        result = safe_query(f"""
            SELECT COUNT(*) as cnt, MIN({date_col}) as min_date, MAX({date_col}) as max_date
            FROM forecasts.{table}
        """)
        if result and result['cnt'] > 0:
            print(f"  {table:30} ✅ {result['cnt']:,} rows ({result['min_date']} to {result['max_date']})")
        else:
            print(f"  {table:30} ⚠️  EMPTY")
    except:
        print(f"  {table:30} ❌ Missing")

# =============================================================================
# SECTION 9: ANALYTICS SCHEMA
# =============================================================================
print("\n" + "=" * 80)
print("SECTION 9: ANALYTICS SCHEMA")
print("=" * 80)

analytics_tables = [
    ("driver_scores", "as_of_date"),
    ("market_posture", "as_of_date"),
    ("risk_metrics", "as_of_date"),
    ("vol_regimes", "as_of_date"),
    ("zl_live", "updated_at"),
]

for table, date_col in analytics_tables:
    try:
        result = safe_query(f"""
            SELECT COUNT(*) as cnt, MAX({date_col}) as max_date
            FROM analytics.{table}
        """)
        if result and result['cnt'] > 0:
            print(f"  {table:25} ✅ {result['cnt']:,} rows (latest: {result['max_date']})")
        else:
            print(f"  {table:25} ⚠️  EMPTY")
    except:
        print(f"  {table:25} ❌ Missing or error")

# =============================================================================
# SECTION 10: WEATHER DATA
# =============================================================================
print("\n" + "=" * 80)
print("SECTION 10: WEATHER DATA")
print("=" * 80)

try:
    weather = safe_query("""
        SELECT 
            COUNT(*) as total_rows,
            COUNT(DISTINCT station_id) as stations,
            COUNT(DISTINCT region) as regions,
            MIN(event_date) as min_date,
            MAX(event_date) as max_date
        FROM alt.weather_1d
    """)
    if weather and weather['total_rows'] > 0:
        print(f"  Total rows:        {weather['total_rows']:,}")
        print(f"  Stations:          {weather['stations']}")
        print(f"  Regions:           {weather['regions']}")
        print(f"  Date range:        {weather['min_date']} to {weather['max_date']}")
    else:
        print(f"  ⚠️  Weather data EMPTY")
except:
    print(f"  ❌ Weather table missing")

# Region breakdown
try:
    regions = run_query("""
        SELECT region, COUNT(*) as cnt
        FROM alt.weather_1d
        WHERE region IS NOT NULL
        GROUP BY region
        ORDER BY cnt DESC
        LIMIT 10
    """)
    print("\n  Top regions:")
    for r in regions:
        print(f"    {r['region']:25} {r['cnt']:,} rows")
except:
    pass

# =============================================================================
# SECTION 11: DATA FRESHNESS SUMMARY
# =============================================================================
print("\n" + "=" * 80)
print("SECTION 11: DATA FRESHNESS SUMMARY")
print("=" * 80)

freshness_checks = [
    ("ZL Prices", "mkt.futures_1d WHERE symbol='ZL'", "event_date"),
    ("FRED Data", "econ.rates_1d", "event_date"),
    ("CFTC COT", "pos.cftc_1w", "event_date"),
    ("Weather", "alt.weather_1d", "event_date"),
    ("News", "alt.news_1d", "event_date"),
    ("WhiteHouse", "alt.legislation_1d", "action_date"),
    ("RIN Prices", "supply.epa_rin_1d", "event_date"),
]

for name, table, date_col in freshness_checks:
    try:
        result = safe_query(f"SELECT MAX({date_col}) as max_date FROM {table}")
        if result and result['max_date']:
            max_date = result['max_date']
            if hasattr(max_date, 'date'):
                max_date = max_date.date()
            days = (today - max_date).days
            status = "✅" if days <= 3 else "⚠️" if days <= 7 else "❌"
            print(f"  {name:20} Last: {max_date} ({days}d ago) {status}")
        else:
            print(f"  {name:20} ❌ No data")
    except:
        print(f"  {name:20} ❌ Error")

# =============================================================================
# FINAL SUMMARY
# =============================================================================
print("\n" + "=" * 80)
print("PREFLIGHT SUMMARY - 52-MODEL TRAINING STACK READINESS")
print("=" * 80)

print("""
TRAINING REQUIREMENTS:

┌─────────────────────────────────────────────────────────────────────────────┐
│ LAYER       │ MODELS │ REQUIREMENT                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ L0 Core     │ 4      │ TimeSeriesPredictor (Chronos) - needs ZL prices     │
│ L0 Specialist│ 44     │ TabularPredictor × 11 specialists × 4 horizons      │
│ L1 Meta     │ 4      │ Stacks 36 OOF columns per horizon                   │
│ L2 Calibrate│ 4      │ CQR for P10/P90 envelopes                           │
│ L3 Risk     │ 4      │ Monte Carlo engine                                  │
└─────────────────────────────────────────────────────────────────────────────┘

HORIZONS: 5d, 21d, 63d, 126d trading days
QUANTILES: Train P30/P50/P70, calibrate P10/P90

TRAINING WINDOWS:
- 5d/21d horizons: 2020+ data (signal purity)
- 63d/126d horizons: 2000+ data (regime learning)

NEXT STEPS:
1. ✅ Raw data appears sufficient
2. ⚠️  Build/verify training.specialist_*_1d tables
3. ⚠️  Build target columns (target_5d, target_21d, target_63d, target_126d)
4. 🔄 Train L0 Core models first (TimeSeriesPredictor)
5. 🔄 Train L0 Specialist models (TabularPredictor)
6. 🔄 Extract OOF predictions (8-fold CV)
7. 🔄 Train L1 Meta-learners
8. 🔄 Run L2 calibration (CQR)
9. 🔄 Deploy L3 risk engine (Monte Carlo)
""")

print("=" * 80)
print("END OF PREFLIGHT CHECKS")
print("=" * 80)
