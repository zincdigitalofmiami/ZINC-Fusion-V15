#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
ELITE TEAM ALPHA — TRAINING MATRIX DEEP AUDIT
═══════════════════════════════════════════════════════════════════════════════

Mission: Comprehensive scan of all data flowing to training matrices.
         Discover what's trained, what's missing, model configurations.

Sections:
1. LANDING DATA INVENTORY — What raw data exists and date coverage
2. FEATURE PIPELINE STATUS — Elite indicators, weather, news scoring
3. TRAINING MATRIX ANALYSIS — Column inventory, null analysis, target coverage
4. SPECIALIST MODEL INVENTORY — All 11 specialists × 4 horizons
5. CORE MODEL STATUS — L0 core model OOF predictions
6. META-ENSEMBLE READINESS — L1 stacking inputs
7. DATA QUALITY ALERTS — Missing data, staleness, anomalies
8. MODEL CONFIGURATION SCAN — AutoGluon configs, hyperparameters

Run: .venv/bin/python scripts/audit_training_alpha.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import json

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg2
import pandas as pd

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

SPECIALISTS = [
    'biofuel', 'china', 'crush', 'energy', 'fed', 'fx',
    'palm', 'substitutes', 'tariff', 'trump_effect', 'volatility'
]

HORIZONS = [5, 21, 63, 126]  # Days

LANDING_TABLES = {
    'mkt.futures_1d': ('event_date', "symbol = 'ZL'"),
    'mkt.futures_1h': ('event_time', "symbol = 'ZL'"),
    'mkt.fx_1d': ('event_date', '1=1'),
    'mkt.options_1d': ('event_date', '1=1'),
    'econ.rates_1d': ('event_date', '1=1'),
    'econ.activity_1d': ('event_date', '1=1'),
    'econ.commodities_1d': ('event_date', '1=1'),
    'econ.vol_indices_1d': ('event_date', '1=1'),
    'econ.inflation_1d': ('event_date', '1=1'),
    'econ.labor_1d': ('event_date', '1=1'),
    'econ.money_1d': ('event_date', '1=1'),
    'pos.cftc_1w': ('event_date', '1=1'),
    'supply.usda_exports_1w': ('event_date', '1=1'),
    'supply.usda_wasde_1m': ('event_date', '1=1'),
    'supply.epa_rin_1d': ('event_date', '1=1'),
    'alt.news_1d': ('event_date', '1=1'),
    'alt.weather_1d': ('event_date', '1=1'),
    'alt.legislation_1d': ('event_date', '1=1'),
}

FEATURE_TABLES = {
    'features.elite_1d': 'trade_date',
    'features.weather_1d': 'trade_date',
    'features.news_scored_1d': 'published_at',
    'features.news_sentiment_1d': 'trade_date',
    'features.trump_effect_1d': 'as_of_date',
    'features.options_1d': 'trade_date',
}


def get_connection():
    """Get database connection."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found")
    return psycopg2.connect(database_url)


def section_header(title: str):
    """Print formatted section header."""
    print()
    print("═" * 80)
    print(f"  {title}")
    print("═" * 80)


def subsection(title: str):
    """Print subsection header."""
    print()
    print(f"  ┌─ {title} {'─' * (70 - len(title))}")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: LANDING DATA INVENTORY
# ═══════════════════════════════════════════════════════════════════════════════

def audit_landing_data(cur):
    """Scan all landing tables for data inventory."""
    section_header("1. LANDING DATA INVENTORY")

    results = []
    today = datetime.now().date()

    for table, (date_col, where_clause) in LANDING_TABLES.items():
        try:
            cur.execute(f"""
                SELECT
                    COUNT(*) as row_count,
                    MIN({date_col})::date as min_date,
                    MAX({date_col})::date as max_date,
                    COUNT(DISTINCT {date_col}::date) as unique_dates
                FROM {table}
                WHERE {where_clause}
            """)
            row = cur.fetchone()

            staleness = (today - row[2]).days if row[2] else None
            status = "✅" if staleness and staleness <= 7 else "⚠️" if staleness and staleness <= 30 else "🔴"

            results.append({
                'table': table,
                'rows': row[0],
                'min_date': row[1],
                'max_date': row[2],
                'unique_dates': row[3],
                'staleness_days': staleness,
                'status': status
            })

            print(f"  {status} {table:30} | {row[0]:>10,} rows | {row[1]} to {row[2]} | {staleness or 'N/A':>3} days old")

        except Exception as e:
            print(f"  🔴 {table:30} | ERROR: {e}")
            cur.connection.rollback()

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: FEATURE PIPELINE STATUS
# ═══════════════════════════════════════════════════════════════════════════════

def audit_feature_tables(cur):
    """Scan feature tables for pipeline status."""
    section_header("2. FEATURE PIPELINE STATUS")

    results = []
    today = datetime.now().date()

    for table, date_col in FEATURE_TABLES.items():
        try:
            cur.execute(f"""
                SELECT
                    COUNT(*) as row_count,
                    MIN({date_col})::date as min_date,
                    MAX({date_col})::date as max_date
                FROM {table}
            """)
            row = cur.fetchone()

            staleness = (today - row[2]).days if row[2] else None
            status = "✅" if row[0] > 0 and staleness and staleness <= 7 else "⚠️" if row[0] > 0 else "🔴"

            results.append({
                'table': table,
                'rows': row[0],
                'min_date': row[1],
                'max_date': row[2],
                'staleness_days': staleness,
                'status': status
            })

            print(f"  {status} {table:35} | {row[0]:>10,} rows | {row[1] or 'N/A'} to {row[2] or 'N/A'}")

        except Exception as e:
            print(f"  🔴 {table:35} | ERROR: {e}")
            cur.connection.rollback()

    # Special check for news_scored_1d Big 11 flags
    subsection("News Scoring Big 11 Flag Coverage")
    try:
        for spec in SPECIALISTS:
            cur.execute(f"""
                SELECT COUNT(*) FROM features.news_scored_1d
                WHERE affects_{spec} = TRUE
            """)
            count = cur.fetchone()[0]
            status = "✅" if count > 0 else "🔴"
            print(f"    {status} affects_{spec:15} = TRUE: {count:,} articles")
    except Exception as e:
        print(f"    🔴 Error checking Big 11 flags: {e}")
        cur.connection.rollback()

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: TRAINING MATRIX ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def audit_training_matrix(cur):
    """Deep analysis of training.matrix_1d."""
    section_header("3. TRAINING MATRIX ANALYSIS")

    # Basic stats
    subsection("Basic Statistics")
    cur.execute("""
        SELECT
            COUNT(*) as total_rows,
            COUNT(DISTINCT trade_date) as unique_dates,
            MIN(trade_date) as min_date,
            MAX(trade_date) as max_date,
            COUNT(DISTINCT symbol) as unique_symbols
        FROM training.matrix_1d
    """)
    row = cur.fetchone()
    print(f"    Total rows:     {row[0]:,}")
    print(f"    Unique dates:   {row[1]:,}")
    print(f"    Date range:     {row[2]} to {row[3]}")
    print(f"    Unique symbols: {row[4]}")

    # Column inventory
    subsection("Column Inventory by Category")
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'training' AND table_name = 'matrix_1d'
        ORDER BY ordinal_position
    """)
    columns = cur.fetchall()

    categories = defaultdict(list)
    for col_name, data_type in columns:
        if col_name.startswith('fred_'):
            categories['FRED Economic'].append(col_name)
        elif col_name.startswith('fx_'):
            categories['FX Rates'].append(col_name)
        elif col_name.startswith('sig_'):
            categories['Specialist Signals'].append(col_name)
        elif col_name.startswith('target_'):
            categories['Target Variables'].append(col_name)
        elif col_name in ['trade_date', 'symbol', 'id', 'matrix_version', 'created_at']:
            categories['Metadata'].append(col_name)
        else:
            categories['Elite Indicators'].append(col_name)

    for category, cols in sorted(categories.items()):
        print(f"    {category}: {len(cols)} columns")
        if len(cols) <= 10:
            for col in cols:
                print(f"      - {col}")

    # Null analysis
    subsection("Null Value Analysis (Sample of Key Columns)")
    key_columns = ['close', 'volume', 'fred_vixcls', 'fred_dgs10', 'sig_crush_1', 'sig_china_1', 'target_ret_5d']

    for col in key_columns:
        try:
            cur.execute(f"""
                SELECT
                    COUNT(*) as total,
                    COUNT({col}) as non_null,
                    ROUND(100.0 * COUNT({col}) / NULLIF(COUNT(*), 0), 1) as pct_filled
                FROM training.matrix_1d
            """)
            row = cur.fetchone()
            status = "✅" if row[2] and row[2] > 90 else "⚠️" if row[2] and row[2] > 50 else "🔴"
            print(f"    {status} {col:25} | {row[1]:>6,}/{row[0]:>6,} filled ({row[2] or 0}%)")
        except Exception as e:
            print(f"    🔴 {col:25} | Column not found")
            cur.connection.rollback()

    # Target coverage
    subsection("Target Variable Coverage")
    for horizon in HORIZONS:
        target_col = f'target_ret_{horizon}d'
        try:
            cur.execute(f"""
                SELECT
                    COUNT(*) as total,
                    COUNT({target_col}) as non_null,
                    MIN(trade_date) as min_date,
                    MAX(trade_date) as max_date
                FROM training.matrix_1d
                WHERE {target_col} IS NOT NULL
            """)
            row = cur.fetchone()
            print(f"    Horizon {horizon:3}d: {row[1]:>6,} rows with target ({row[2]} to {row[3]})")
        except Exception as e:
            print(f"    Horizon {horizon:3}d: Column {target_col} not found")
            cur.connection.rollback()

    return {'total_columns': len(columns), 'categories': dict(categories)}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: SPECIALIST MODEL INVENTORY
# ═══════════════════════════════════════════════════════════════════════════════

def audit_specialist_models(cur):
    """Inventory of all specialist models and OOF predictions."""
    section_header("4. SPECIALIST MODEL INVENTORY (L0)")

    results = {}

    for specialist in SPECIALISTS:
        subsection(f"{specialist.upper()} Specialist")

        # Check OOF table
        try:
            cur.execute(f"""
                SELECT
                    horizon_days,
                    COUNT(*) as row_count,
                    COUNT(DISTINCT trade_date) as unique_dates,
                    MIN(trade_date) as min_date,
                    MAX(trade_date) as max_date,
                    AVG(p50) as avg_p50,
                    COUNT(DISTINCT run_hash) as run_versions
                FROM training.oof_{specialist}_1d
                GROUP BY horizon_days
                ORDER BY horizon_days
            """)
            rows = cur.fetchall()

            results[specialist] = {'horizons': {}}

            if not rows:
                print(f"    🔴 NO OOF PREDICTIONS FOUND")
            else:
                for row in rows:
                    horizon, count, dates, min_d, max_d, avg_p50, versions = row
                    status = "✅" if count > 100 else "⚠️"
                    print(f"    {status} Horizon {horizon:3}d: {count:>5,} OOF rows | {min_d} to {max_d} | {versions} version(s)")
                    results[specialist]['horizons'][horizon] = {
                        'rows': count,
                        'dates': dates,
                        'versions': versions
                    }

        except Exception as e:
            print(f"    🔴 Error reading OOF table: {e}")
            cur.connection.rollback()

        # Check specialist features
        try:
            cur.execute(f"""
                SELECT COUNT(*), MIN(as_of_date), MAX(as_of_date)
                FROM training.specialist_features
                WHERE bucket = %s
            """, (specialist,))
            row = cur.fetchone()
            print(f"    Features: {row[0]:>6,} rows | {row[1]} to {row[2]}")
        except Exception as e:
            print(f"    Features: Error - {e}")
            cur.connection.rollback()

        # Check specialist signals
        try:
            cur.execute(f"""
                SELECT COUNT(*), MIN(as_of_date), MAX(as_of_date), AVG(signal_1), AVG(confidence)
                FROM training.specialist_signals_1d
                WHERE bucket = %s
            """, (specialist,))
            row = cur.fetchone()
            print(f"    Signals:  {row[0]:>6,} rows | avg_signal={row[3]:.4f if row[3] else 'N/A'} | avg_conf={row[4]:.2f if row[4] else 'N/A'}")
        except Exception as e:
            print(f"    Signals: Error - {e}")
            cur.connection.rollback()

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: CORE MODEL STATUS
# ═══════════════════════════════════════════════════════════════════════════════

def audit_core_model(cur):
    """Check core model OOF predictions."""
    section_header("5. CORE MODEL STATUS (L0)")

    # Check oof_core_1d
    subsection("Core OOF Predictions")
    try:
        cur.execute("""
            SELECT
                horizon_days,
                COUNT(*) as row_count,
                COUNT(DISTINCT trade_date) as unique_dates,
                MIN(trade_date) as min_date,
                MAX(trade_date) as max_date,
                COUNT(DISTINCT run_hash) as run_versions
            FROM training.oof_core_1d
            GROUP BY horizon_days
            ORDER BY horizon_days
        """)
        rows = cur.fetchall()

        if not rows:
            print("    🔴 NO CORE OOF PREDICTIONS - Core model not yet trained!")
            print()
            print("    ACTION REQUIRED:")
            print("    Run: .venv/bin/python scripts/v2_training/train_core_model.py")
        else:
            for row in rows:
                horizon, count, dates, min_d, max_d, versions = row
                status = "✅" if count > 100 else "⚠️"
                print(f"    {status} Horizon {horizon:3}d: {count:>5,} OOF rows | {min_d} to {max_d} | {versions} version(s)")

    except Exception as e:
        print(f"    🔴 Error: {e}")
        cur.connection.rollback()

    # Check model registry for core models
    subsection("Core Models in Registry")
    try:
        cur.execute("""
            SELECT model_name, horizon_days, trained_date, mae, coverage_30_70, status
            FROM training.model_runs
            WHERE model_name LIKE 'core%' OR model_name LIKE 'zinc-fusion-v2-core%'
            ORDER BY trained_date DESC
            LIMIT 10
        """)
        rows = cur.fetchall()

        if not rows:
            print("    🔴 No core models registered in training.model_runs")
        else:
            for row in rows:
                name, horizon, trained, mae, coverage, status = row
                print(f"    {name:40} | H{horizon:>3}d | MAE={mae:.4f if mae else 'N/A':>8} | Cov={coverage:.1f if coverage else 'N/A'}% | {status or 'unknown'}")

    except Exception as e:
        print(f"    🔴 Error reading model registry: {e}")
        cur.connection.rollback()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: META-ENSEMBLE READINESS
# ═══════════════════════════════════════════════════════════════════════════════

def audit_meta_ensemble(cur):
    """Check L1 meta-ensemble inputs."""
    section_header("6. META-ENSEMBLE READINESS (L1)")

    subsection("Meta Inputs Table")
    try:
        cur.execute("""
            SELECT
                horizon_days,
                COUNT(*) as row_count,
                MIN(trade_date) as min_date,
                MAX(trade_date) as max_date
            FROM training.meta_inputs_1d
            GROUP BY horizon_days
            ORDER BY horizon_days
        """)
        rows = cur.fetchall()

        if not rows:
            print("    🔴 NO META INPUTS - L1 ensemble not assembled!")
            print()
            print("    PREREQUISITES:")
            print("    1. Core OOF predictions (training.oof_core_1d)")
            print("    2. All specialist OOF predictions (training.oof_*_1d)")
            print()
            print("    ACTION REQUIRED:")
            print("    Run: .venv/bin/python scripts/v2_training/build_meta_inputs.py")
        else:
            for row in rows:
                horizon, count, min_d, max_d = row
                status = "✅" if count > 100 else "⚠️"
                print(f"    {status} Horizon {horizon:3}d: {count:>5,} meta input rows | {min_d} to {max_d}")

    except Exception as e:
        print(f"    🔴 Error: {e}")
        cur.connection.rollback()

    # Check meta_inputs columns
    subsection("Meta Inputs Column Check")
    try:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'training' AND table_name = 'meta_inputs_1d'
            ORDER BY ordinal_position
        """)
        columns = [r[0] for r in cur.fetchall()]

        # Check for expected specialist columns
        expected_prefixes = ['core_'] + [f'{s}_' for s in SPECIALISTS]
        found = {p: any(c.startswith(p) for c in columns) for p in expected_prefixes}

        for prefix, exists in found.items():
            status = "✅" if exists else "🔴"
            print(f"    {status} {prefix}* columns: {'Found' if exists else 'MISSING'}")

    except Exception as e:
        print(f"    🔴 Error: {e}")
        cur.connection.rollback()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7: DATA QUALITY ALERTS
# ═══════════════════════════════════════════════════════════════════════════════

def audit_data_quality(cur):
    """Generate data quality alerts."""
    section_header("7. DATA QUALITY ALERTS")

    alerts = []
    today = datetime.now().date()

    # Check for stale data
    subsection("Staleness Alerts (>7 days old)")
    stale_tables = [
        ('mkt.futures_1d', 'event_date', "symbol = 'ZL'", 3),
        ('econ.rates_1d', 'event_date', '1=1', 7),
        ('pos.cftc_1w', 'event_date', '1=1', 10),
        ('alt.news_1d', 'event_date', '1=1', 3),
    ]

    for table, date_col, where, threshold in stale_tables:
        try:
            cur.execute(f"SELECT MAX({date_col})::date FROM {table} WHERE {where}")
            max_date = cur.fetchone()[0]
            if max_date:
                staleness = (today - max_date).days
                if staleness > threshold:
                    alert = f"{table}: {staleness} days stale (threshold: {threshold})"
                    alerts.append(alert)
                    print(f"    🔴 {alert}")
        except Exception as e:
            cur.connection.rollback()

    if not alerts:
        print("    ✅ No staleness alerts")

    # Check for gaps in ZL price data
    subsection("ZL Price Data Gaps (last 30 days)")
    try:
        cur.execute("""
            WITH date_series AS (
                SELECT generate_series(
                    CURRENT_DATE - INTERVAL '30 days',
                    CURRENT_DATE,
                    '1 day'::interval
                )::date AS expected_date
            ),
            actual_dates AS (
                SELECT DISTINCT event_date::date as actual_date
                FROM mkt.futures_1d
                WHERE symbol = 'ZL' AND event_date >= CURRENT_DATE - INTERVAL '30 days'
            )
            SELECT d.expected_date
            FROM date_series d
            LEFT JOIN actual_dates a ON d.expected_date = a.actual_date
            WHERE a.actual_date IS NULL
              AND EXTRACT(DOW FROM d.expected_date) NOT IN (0, 6)  -- Exclude weekends
            ORDER BY d.expected_date
        """)
        gaps = [r[0] for r in cur.fetchall()]

        if gaps:
            print(f"    ⚠️ {len(gaps)} missing trading days:")
            for gap in gaps[:10]:
                print(f"       - {gap}")
            if len(gaps) > 10:
                print(f"       ... and {len(gaps) - 10} more")
        else:
            print("    ✅ No gaps in ZL price data")

    except Exception as e:
        print(f"    🔴 Error checking gaps: {e}")
        cur.connection.rollback()

    # Check specialist signal anomalies
    subsection("Specialist Signal Anomalies")
    try:
        cur.execute("""
            SELECT bucket,
                   AVG(signal_1) as avg_sig,
                   STDDEV(signal_1) as std_sig,
                   MIN(signal_1) as min_sig,
                   MAX(signal_1) as max_sig
            FROM training.specialist_signals_1d
            GROUP BY bucket
        """)
        for row in cur.fetchall():
            bucket, avg, std, min_s, max_s = row
            # Flag if signals are out of expected range
            if min_s and min_s < -5 or max_s and max_s > 5:
                print(f"    ⚠️ {bucket:15} | range [{min_s:.2f}, {max_s:.2f}] - potential outliers")

    except Exception as e:
        print(f"    🔴 Error: {e}")
        cur.connection.rollback()

    return alerts


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8: MODEL CONFIGURATION SCAN
# ═══════════════════════════════════════════════════════════════════════════════

def audit_model_configs(cur):
    """Scan for model configuration files."""
    section_header("8. MODEL CONFIGURATION SCAN")

    project_root = Path(__file__).parent.parent

    # Check for AutoGluon configs
    subsection("AutoGluon Configuration Files")
    config_patterns = [
        'scripts/v2_training/*.py',
        'src/fusion/core_training/*.py',
        'src/fusion/specialists/*.py',
    ]

    for pattern in config_patterns:
        matches = list(project_root.glob(pattern))
        if matches:
            print(f"    Found in {pattern}:")
            for f in matches[:5]:
                print(f"      - {f.name}")
            if len(matches) > 5:
                print(f"      ... and {len(matches) - 5} more")

    # Check model catalog
    subsection("Model Catalog")
    catalog_path = project_root / 'scripts' / 'v2_training' / 'MODEL_CATALOG.md'
    if catalog_path.exists():
        print(f"    ✅ Found: {catalog_path}")
        # Read and summarize
        with open(catalog_path) as f:
            content = f.read()
            l0_count = content.count('L0')
            l1_count = content.count('L1')
            print(f"    L0 model references: {l0_count}")
            print(f"    L1 model references: {l1_count}")
    else:
        print(f"    🔴 Not found: {catalog_path}")

    # Check for saved models
    subsection("Saved Model Artifacts")
    model_dirs = [
        project_root / 'models',
        project_root / 'artifacts',
        project_root / 'trained_models',
    ]

    for model_dir in model_dirs:
        if model_dir.exists():
            model_files = list(model_dir.rglob('*.pkl')) + list(model_dir.rglob('*.joblib'))
            print(f"    {model_dir.name}/: {len(model_files)} model files")
        else:
            print(f"    {model_dir.name}/: Not found")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print()
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║        ELITE TEAM ALPHA — TRAINING MATRIX DEEP AUDIT                        ║")
    print("║        Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "                                      ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")

    conn = get_connection()
    cur = conn.cursor()

    try:
        # Run all audits
        landing_results = audit_landing_data(cur)
        feature_results = audit_feature_tables(cur)
        matrix_results = audit_training_matrix(cur)
        specialist_results = audit_specialist_models(cur)
        audit_core_model(cur)
        audit_meta_ensemble(cur)
        alerts = audit_data_quality(cur)
        audit_model_configs(cur)

        # Summary
        section_header("EXECUTIVE SUMMARY")

        print("""
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │ TRAINING READINESS SCORECARD                                                │
  ├─────────────────────────────────────────────────────────────────────────────┤""")

        # Calculate scores
        landing_fresh = sum(1 for r in landing_results if r.get('staleness_days', 999) <= 7)
        features_ready = sum(1 for r in feature_results if r.get('rows', 0) > 0)
        specialists_trained = sum(1 for s in specialist_results.values() if s.get('horizons'))

        print(f"  │ Landing Data:        {landing_fresh}/{len(landing_results)} tables fresh (<7 days)                      │")
        print(f"  │ Feature Tables:      {features_ready}/{len(feature_results)} tables populated                              │")
        print(f"  │ Specialists Trained: {specialists_trained}/11 with OOF predictions                          │")
        print(f"  │ Core Model:          {'✅ Trained' if False else '🔴 NOT TRAINED'}                                           │")
        print(f"  │ Meta-Ensemble:       {'✅ Ready' if False else '🔴 NOT ASSEMBLED'}                                           │")
        print(f"  │ Data Quality Alerts: {len(alerts)} issues                                              │")
        print("  └─────────────────────────────────────────────────────────────────────────────┘")

        print()
        print("  NEXT ACTIONS:")
        print("  1. Populate features.news_scored_1d (run news scoring pipeline)")
        print("  2. Train core model (generates training.oof_core_1d)")
        print("  3. Build meta inputs (assembles training.meta_inputs_1d)")
        print("  4. Train L1 meta-ensemble")
        print()

    finally:
        cur.close()
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
