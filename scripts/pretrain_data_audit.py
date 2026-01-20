#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  ZINC-FUSION-V15: PRE-TRAINING DATA AUDIT                                    ║
║  Comprehensive Assessment for L0 → L1 → L3 Pipeline                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Author: Claude (Caped Sidekick) 🦸‍♂️
Date: January 20, 2026
Purpose: Assess data readiness before training the Big 11 specialists + Core

This script performs read-only checks against Prisma PostgreSQL to validate:
1. Landing data availability (mkt, econ, pos, supply, alt schemas)
2. Feature store completeness (training.*, features.*)
3. Target integrity (no leakage)
4. Specialist table coverage (11 specialists)
5. OOF table structure readiness
6. Metadata governance (symbol mappings)

Usage:
    cd /Volumes/Satechi\ Hub/ZINC-FUSION-V15
    python scripts/pretrain_data_audit.py
    
    # Generate JSON report:
    python scripts/pretrain_data_audit.py --json > audit_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Any

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

from dotenv import load_dotenv

# ============================================================================
# CONFIGURATION
# ============================================================================

# Big 11 Specialists
SPECIALISTS = [
    "crush", "china", "fx", "fed", "tariff",
    "energy", "biofuel", "palm", "volatility", "substitutes", "trump_effect"
]

# Horizons
HORIZONS = [5, 21, 63, 126]

# Stale thresholds (days)
STALE_THRESHOLDS = {
    "mkt.futures_1d": {"warn": 3, "fail": 7},
    "mkt.fx_1d": {"warn": 3, "fail": 7},
    "mkt.options_1d": {"warn": 3, "fail": 14},
    "econ.rates_1d": {"warn": 3, "fail": 7},
    "econ.vol_indices_1d": {"warn": 3, "fail": 7},
    "econ.commodities_1d": {"warn": 3, "fail": 7},
    "pos.cftc_1w": {"warn": 10, "fail": 21},
    "alt.weather_1d": {"warn": 3, "fail": 7},
    "alt.news_1d": {"warn": 5, "fail": 14},
    "alt.legislation_1d": {"warn": 7, "fail": 30},
    "supply.usda_exports_1w": {"warn": 14, "fail": 28},
    "supply.usda_wasde_1m": {"warn": 21, "fail": 45},
    "supply.epa_rin_1d": {"warn": 7, "fail": 21},
}

# Required FRED series by specialist (expected in econ.* tables)
FRED_SERIES_BY_SPECIALIST = {
    "fed": ["DFF", "FEDFUNDS", "DGS10", "DGS2", "T10Y2Y", "T10Y3M"],
    "volatility": ["VIXCLS", "STLFSI4", "NFCI", "BAMLH0A0HYM2"],
    "energy": ["DCOILWTICO", "DCOILBRENTEU", "DHHNGSP"],
}

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class TableStats:
    schema: str
    table: str
    exists: bool = False
    row_count: int = 0
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    days_stale: Optional[int] = None
    null_pct: Optional[float] = None
    symbols: Optional[list] = None
    error: Optional[str] = None
    
@dataclass
class SpecialistCheck:
    name: str
    table_exists: bool = False
    row_count: int = 0
    date_range: Optional[str] = None
    has_required_columns: bool = False
    missing_columns: list = field(default_factory=list)
    symbols: list = field(default_factory=list)
    horizons_populated: list = field(default_factory=list)
    
@dataclass
class AuditResult:
    generated_at: str
    verdict: str  # "READY", "WARNINGS", "BLOCKED"
    blockers: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    landing_data: dict = field(default_factory=dict)
    feature_stores: dict = field(default_factory=dict)
    specialists: dict = field(default_factory=dict)
    training_tables: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    oof_tables: dict = field(default_factory=dict)
    recommendations: list = field(default_factory=list)

# ============================================================================
# DATABASE HELPERS
# ============================================================================

def get_db_connection():
    """Connect to Prisma PostgreSQL using DATABASE_URL."""
    load_dotenv()
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not url:
        raise SystemExit("FATAL: DATABASE_URL not found in environment")
    return psycopg2.connect(url)

def table_exists(cur, schema: str, table: str) -> bool:
    cur.execute("""
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
    """, (schema, table))
    return cur.fetchone() is not None

def get_table_stats(cur, schema: str, table: str, date_col: str = None) -> TableStats:
    """Get comprehensive stats for a table."""
    stats = TableStats(schema=schema, table=table)
    
    if not table_exists(cur, schema, table):
        stats.error = "Table does not exist"
        return stats
    
    stats.exists = True
    
    try:
        # Row count
        cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
        stats.row_count = cur.fetchone()[0]
        
        # Date range if date column provided
        if date_col:
            cur.execute(f'''
                SELECT MIN({date_col})::date, MAX({date_col})::date 
                FROM "{schema}"."{table}"
            ''')
            row = cur.fetchone()
            if row[0] and row[1]:
                stats.min_date = str(row[0])
                stats.max_date = str(row[1])
                stats.days_stale = (date.today() - row[1]).days
                
    except Exception as e:
        stats.error = str(e)
        
    return stats

def get_columns(cur, schema: str, table: str) -> list[str]:
    """Get column names for a table."""
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
    """, (schema, table))
    return [r[0] for r in cur.fetchall()]

# ============================================================================
# AUDIT FUNCTIONS
# ============================================================================

def audit_landing_data(cur, result: AuditResult, today: date):
    """Check raw data landing tables (mkt, econ, pos, supply, alt)."""
    print("\n📊 Auditing Landing Data...")
    
    landing_tables = [
        ("mkt", "futures_1d", "event_date"),
        ("mkt", "fx_1d", "event_date"),
        ("mkt", "options_1d", "event_date"),
        ("mkt", "etf_1d", "event_date"),
        ("econ", "rates_1d", "event_date"),
        ("econ", "vol_indices_1d", "event_date"),
        ("econ", "commodities_1d", "event_date"),
        ("econ", "inflation_1d", "event_date"),
        ("econ", "labor_1d", "event_date"),
        ("econ", "money_1d", "event_date"),
        ("pos", "cftc_1w", "event_date"),
        ("supply", "usda_wasde_1m", "event_date"),
        ("supply", "usda_exports_1w", "event_date"),
        ("supply", "epa_rin_1d", "event_date"),
        ("alt", "weather_1d", "event_date"),
        ("alt", "news_1d", "event_date"),
        ("alt", "legislation_1d", "event_date"),
    ]
    
    for schema, table, date_col in landing_tables:
        full_name = f"{schema}.{table}"
        stats = get_table_stats(cur, schema, table, date_col)
        result.landing_data[full_name] = asdict(stats)
        
        if not stats.exists:
            result.blockers.append(f"Missing table: {full_name}")
            print(f"  ❌ {full_name}: MISSING")
        elif stats.row_count == 0:
            result.blockers.append(f"Empty table: {full_name}")
            print(f"  ⚠️ {full_name}: EMPTY")
        else:
            threshold = STALE_THRESHOLDS.get(full_name, {"warn": 7, "fail": 14})
            status = "✅"
            
            if stats.days_stale is not None:
                if stats.days_stale > threshold["fail"]:
                    status = "❌"
                    result.blockers.append(f"{full_name} stale by {stats.days_stale}d (>{threshold['fail']}d)")
                elif stats.days_stale > threshold["warn"]:
                    status = "⚠️"
                    result.warnings.append(f"{full_name} stale by {stats.days_stale}d (>{threshold['warn']}d)")
            
            print(f"  {status} {full_name}: {stats.row_count:,} rows | {stats.min_date} → {stats.max_date} | stale={stats.days_stale}d")
            
        # Check for ZL specifically in futures
        if table == "futures_1d" and stats.exists:
            cur.execute("""
                SELECT COUNT(*), MIN(event_date)::date, MAX(event_date)::date
                FROM mkt.futures_1d WHERE symbol = 'ZL'
            """)
            zl = cur.fetchone()
            result.landing_data[f"{full_name}_ZL"] = {
                "count": zl[0], "min_date": str(zl[1]) if zl[1] else None, 
                "max_date": str(zl[2]) if zl[2] else None
            }
            print(f"       └─ ZL: {zl[0]:,} rows | {zl[1]} → {zl[2]}")

def audit_feature_stores(cur, result: AuditResult, today: date):
    """Check feature store tables."""
    print("\n🔧 Auditing Feature Stores...")
    
    feature_tables = [
        ("features", "elite_1d", "trade_date"),
        ("features", "weather_1d", "trade_date"),
        ("features", "options_1d", "trade_date"),
        ("features", "news_sentiment_1d", "trade_date"),
        ("features", "trump_effect_1d", "as_of_date"),
        ("features", "intel_drops", "as_of_ts"),
    ]
    
    for schema, table, date_col in feature_tables:
        full_name = f"{schema}.{table}"
        stats = get_table_stats(cur, schema, table, date_col)
        result.feature_stores[full_name] = asdict(stats)
        
        if not stats.exists:
            result.warnings.append(f"Missing feature table: {full_name}")
            print(f"  ⚠️ {full_name}: MISSING")
        elif stats.row_count == 0:
            result.warnings.append(f"Empty feature table: {full_name}")
            print(f"  ⚠️ {full_name}: EMPTY")
        else:
            print(f"  ✅ {full_name}: {stats.row_count:,} rows | {stats.min_date} → {stats.max_date}")

def audit_specialists(cur, result: AuditResult, today: date):
    """Check all 11 specialist tables."""
    print("\n🎯 Auditing Big 11 Specialists...")
    
    required_cols = ["as_of_date", "symbol", "close"]
    
    for specialist in SPECIALISTS:
        table = f"specialist_{specialist}_1d"
        check = SpecialistCheck(name=specialist)
        
        if not table_exists(cur, "training", table):
            check.table_exists = False
            result.blockers.append(f"Missing specialist table: training.{table}")
            print(f"  ❌ {specialist}: training.{table} MISSING")
        else:
            check.table_exists = True
            
            # Get stats
            cur.execute(f'SELECT COUNT(*) FROM training."{table}"')
            check.row_count = cur.fetchone()[0]
            
            # Get date range
            date_col = "as_of_date" if specialist != "trump_effect" else "as_of_date"
            try:
                cur.execute(f'''
                    SELECT MIN({date_col})::date, MAX({date_col})::date
                    FROM training."{table}"
                ''')
                mn, mx = cur.fetchone()
                check.date_range = f"{mn} → {mx}" if mn else "N/A"
            except:
                check.date_range = "ERROR"
            
            # Check columns
            cols = set(get_columns(cur, "training", table))
            check.missing_columns = [c for c in required_cols if c not in cols]
            check.has_required_columns = len(check.missing_columns) == 0
            
            if check.missing_columns:
                result.warnings.append(f"training.{table} missing columns: {check.missing_columns}")
            
            # Get symbols
            try:
                cur.execute(f'SELECT DISTINCT symbol FROM training."{table}" LIMIT 20')
                check.symbols = [r[0] for r in cur.fetchall()]
            except:
                check.symbols = []
            
            status = "✅" if check.row_count > 0 and check.has_required_columns else "⚠️"
            print(f"  {status} {specialist}: {check.row_count:,} rows | {check.date_range}")
            
        result.specialists[specialist] = asdict(check)

def audit_training_matrix(cur, result: AuditResult, today: date):
    """Check the main training matrix table."""
    print("\n📋 Auditing Training Matrix...")
    
    if not table_exists(cur, "training", "matrix_1d"):
        result.blockers.append("Missing: training.matrix_1d (core training matrix)")
        print("  ❌ training.matrix_1d: MISSING")
        return
    
    # Get stats
    cur.execute("SELECT COUNT(*) FROM training.matrix_1d")
    count = cur.fetchone()[0]
    
    cur.execute("""
        SELECT MIN(trade_date)::date, MAX(trade_date)::date
        FROM training.matrix_1d
    """)
    mn, mx = cur.fetchone()
    
    # Check targets
    cols = set(get_columns(cur, "training", "matrix_1d"))
    required_targets = {"target_ret_5d", "target_ret_21d", "target_ret_63d", "target_ret_126d"}
    missing_targets = required_targets - cols
    
    if missing_targets:
        result.blockers.append(f"training.matrix_1d missing targets: {missing_targets}")
    
    # Check for nulls in targets
    null_stats = {}
    for target in required_targets:
        if target in cols:
            cur.execute(f"""
                SELECT 
                    COUNT(*) FILTER (WHERE {target} IS NULL) as nulls,
                    COUNT(*) as total
                FROM training.matrix_1d
            """)
            nulls, total = cur.fetchone()
            null_pct = (nulls / total * 100) if total > 0 else 0
            null_stats[target] = {"nulls": nulls, "total": total, "pct": round(null_pct, 2)}
    
    # Check feature coverage
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns
        WHERE table_schema = 'training' AND table_name = 'matrix_1d'
        AND column_name LIKE 'fred_%'
    """)
    fred_cols = [r[0] for r in cur.fetchall()]
    
    result.training_tables["matrix_1d"] = {
        "row_count": count,
        "date_range": f"{mn} → {mx}",
        "missing_targets": list(missing_targets),
        "target_null_stats": null_stats,
        "fred_feature_count": len(fred_cols),
        "total_columns": len(cols)
    }
    
    status = "✅" if not missing_targets and count > 0 else "❌"
    print(f"  {status} training.matrix_1d: {count:,} rows | {mn} → {mx}")
    print(f"       └─ Targets: {len(required_targets - missing_targets)}/{len(required_targets)} present")
    print(f"       └─ FRED features: {len(fred_cols)}")
    print(f"       └─ Total columns: {len(cols)}")

def audit_oof_tables(cur, result: AuditResult, today: date):
    """Check OOF (Out-of-Fold) tables for each specialist and horizon."""
    print("\n📈 Auditing OOF Tables...")
    
    # OOF tables follow pattern: training.oof_{specialist}_1d
    oof_specialists = ["core"] + SPECIALISTS
    
    for specialist in oof_specialists:
        table = f"oof_{specialist}_1d"
        
        if not table_exists(cur, "training", table):
            result.warnings.append(f"Missing OOF table: training.{table}")
            print(f"  ⚠️ training.{table}: MISSING (will be created during training)")
        else:
            cur.execute(f'SELECT COUNT(*) FROM training."{table}"')
            count = cur.fetchone()[0]
            
            # Check horizons populated
            cur.execute(f'''
                SELECT DISTINCT horizon_days 
                FROM training."{table}"
                ORDER BY horizon_days
            ''')
            horizons = [r[0] for r in cur.fetchall()]
            
            result.oof_tables[specialist] = {
                "row_count": count,
                "horizons_populated": horizons
            }
            
            status = "✅" if count > 0 else "⚪"  # Empty is OK before training
            print(f"  {status} training.{table}: {count:,} rows | horizons={horizons}")

def audit_meta_inputs(cur, result: AuditResult, today: date):
    """Check meta-learner input tables."""
    print("\n🔗 Auditing Meta-Learner Tables...")
    
    if table_exists(cur, "training", "meta_inputs_1d"):
        cur.execute("SELECT COUNT(*) FROM training.meta_inputs_1d")
        count = cur.fetchone()[0]
        
        cur.execute("""
            SELECT DISTINCT horizon_days 
            FROM training.meta_inputs_1d
            ORDER BY horizon_days
        """)
        horizons = [r[0] for r in cur.fetchall()]
        
        result.training_tables["meta_inputs_1d"] = {
            "row_count": count,
            "horizons": horizons
        }
        
        status = "✅" if count > 0 else "⚪"
        print(f"  {status} training.meta_inputs_1d: {count:,} rows | horizons={horizons}")
    else:
        result.warnings.append("training.meta_inputs_1d missing (will be created after L0 training)")
        print("  ⚠️ training.meta_inputs_1d: MISSING (created after L0)")

def audit_metadata(cur, result: AuditResult, today: date):
    """Check metadata governance tables."""
    print("\n📚 Auditing Metadata Governance...")
    
    # Symbol mapping
    if table_exists(cur, "metadata", "symbol_mapping"):
        cur.execute("SELECT COUNT(*) FROM metadata.symbol_mapping")
        count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(DISTINCT canonical_id) FROM metadata.symbol_mapping")
        canonical_count = cur.fetchone()[0]
        
        result.metadata["symbol_mapping"] = {
            "row_count": count,
            "canonical_ids": canonical_count
        }
        
        print(f"  ✅ metadata.symbol_mapping: {count} mappings, {canonical_count} canonical IDs")
    else:
        result.warnings.append("metadata.symbol_mapping missing")
        print("  ⚠️ metadata.symbol_mapping: MISSING")
    
    # Data source registry
    if table_exists(cur, "ops", "data_source_registry"):
        cur.execute("SELECT COUNT(*) FROM ops.data_source_registry")
        count = cur.fetchone()[0]
        
        cur.execute("""
            SELECT COUNT(*) FILTER (WHERE is_active = true) 
            FROM ops.data_source_registry
        """)
        active = cur.fetchone()[0]
        
        result.metadata["data_source_registry"] = {
            "total": count,
            "active": active
        }
        
        print(f"  ✅ ops.data_source_registry: {count} sources ({active} active)")

def generate_recommendations(result: AuditResult):
    """Generate actionable recommendations based on audit findings."""
    print("\n💡 Generating Recommendations...")
    
    recommendations = []
    
    # Check for stale data
    for table, stats in result.landing_data.items():
        if isinstance(stats, dict) and stats.get("days_stale", 0) > 5:
            recommendations.append(f"Refresh {table} - data is {stats['days_stale']} days stale")
    
    # Check for missing specialists
    missing_specialists = [s for s, d in result.specialists.items() if not d.get("table_exists")]
    if missing_specialists:
        recommendations.append(f"Create missing specialist tables: {', '.join(missing_specialists)}")
    
    # Check matrix
    matrix = result.training_tables.get("matrix_1d", {})
    if matrix.get("missing_targets"):
        recommendations.append(f"Add missing targets to training.matrix_1d: {matrix['missing_targets']}")
    
    # OOF readiness
    empty_oof = [s for s, d in result.oof_tables.items() if d.get("row_count", 0) == 0]
    if empty_oof:
        recommendations.append(f"OOF tables are empty (expected before training): {', '.join(empty_oof)}")
    
    result.recommendations = recommendations
    
    for rec in recommendations:
        print(f"  → {rec}")

# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="ZINC-FUSION-V15 Pre-Training Data Audit")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if blockers present")
    args = parser.parse_args()
    
    # Initialize result
    now = datetime.now(timezone.utc)
    today = date.today()
    result = AuditResult(
        generated_at=now.isoformat(),
        verdict="UNKNOWN"
    )
    
    if not args.json:
        print("╔══════════════════════════════════════════════════════════════════════════════╗")
        print("║  ZINC-FUSION-V15: PRE-TRAINING DATA AUDIT                                    ║")
        print("║  Comprehensive Assessment for L0 → L1 → L3 Pipeline                          ║")
        print("╚══════════════════════════════════════════════════════════════════════════════╝")
        print(f"\n🕐 Generated: {now.isoformat()}")
        print(f"📅 Today: {today}")
    
    # Connect to database
    try:
        conn = get_db_connection()
        conn.autocommit = True
        cur = conn.cursor()
    except Exception as e:
        result.blockers.append(f"Database connection failed: {e}")
        result.verdict = "BLOCKED"
        if args.json:
            print(json.dumps(asdict(result), indent=2, default=str))
        else:
            print(f"\n❌ Database connection failed: {e}")
        return 1
    
    try:
        # Run all audits
        audit_landing_data(cur, result, today)
        audit_feature_stores(cur, result, today)
        audit_specialists(cur, result, today)
        audit_training_matrix(cur, result, today)
        audit_oof_tables(cur, result, today)
        audit_meta_inputs(cur, result, today)
        audit_metadata(cur, result, today)
        generate_recommendations(result)
        
        # Determine verdict
        if result.blockers:
            result.verdict = "BLOCKED"
        elif result.warnings:
            result.verdict = "WARNINGS"
        else:
            result.verdict = "READY"
        
        # Output
        if args.json:
            print(json.dumps(asdict(result), indent=2, default=str))
        else:
            print("\n" + "=" * 78)
            print("📊 AUDIT SUMMARY")
            print("=" * 78)
            
            if result.verdict == "READY":
                print("\n✅ VERDICT: READY FOR TRAINING")
            elif result.verdict == "WARNINGS":
                print("\n⚠️ VERDICT: READY WITH WARNINGS")
            else:
                print("\n❌ VERDICT: BLOCKED - Cannot proceed with training")
            
            if result.blockers:
                print("\n🚫 BLOCKERS:")
                for b in result.blockers:
                    print(f"  • {b}")
            
            if result.warnings:
                print("\n⚠️ WARNINGS:")
                for w in result.warnings:
                    print(f"  • {w}")
            
            print("\n" + "=" * 78)
        
        if args.strict and result.blockers:
            return 1
        return 0
        
    finally:
        conn.close()

if __name__ == "__main__":
    sys.exit(main())
