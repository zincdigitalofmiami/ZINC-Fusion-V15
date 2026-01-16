#!/usr/bin/env python3
"""
ZINC-FUSION-V15 Database State Validation
Direct verification against Prisma PostgreSQL
"""

import os
import sys
from datetime import datetime, timedelta

# Add project to path
sys.path.insert(0, "/Volumes/Satechi Hub/ZINC-FUSION-V15/src")

import pandas as pd
from dotenv import load_dotenv

# Load environment
load_dotenv("/Volumes/Satechi Hub/ZINC-FUSION-V15/.env")

from fusion.db.connection import get_read_engine

def main():
    engine = get_read_engine()
    
    print("=" * 80)
    print("🔍 ZINC-FUSION-V15 DATABASE STATE VALIDATION")
    print(f"   Timestamp: {datetime.now().isoformat()}")
    print("=" * 80)
    
    # =========================================================================
    # 1. RAW TABLES - Row counts and freshness
    # =========================================================================
    print("\n📊 RAW TABLES STATUS")
    print("-" * 60)
    
    raw_tables = [
        ("raw", "market_futures_1h"),
        ("raw", "market_futures_1d"),
        ("raw", "fred_observations_1d"),
        ("raw", "weather_noaa_1d"),
        ("raw", "fx_spot_1d"),
        ("raw", "options_futures_1d"),
        ("raw", "usda_wasde_1m"),
        ("raw", "usda_export_sales_1w"),
        ("raw", "cftc_cot_1w"),
        ("raw", "news_articles_1d"),
        ("raw", "epa_rin_prices_1d"),
    ]
    
    for schema, table in raw_tables:
        try:
            # Count rows
            count_q = f'SELECT COUNT(*) as cnt FROM "{schema}"."{table}"'
            cnt = pd.read_sql(count_q, engine).iloc[0]['cnt']
            
            # Get latest date (try common date column names)
            latest = "N/A"
            for date_col in ['as_of_date', 'date', 'timestamp', 'created_at']:
                try:
                    latest_q = f'SELECT MAX("{date_col}")::date as latest FROM "{schema}"."{table}"'
                    result = pd.read_sql(latest_q, engine).iloc[0]['latest']
                    if result:
                        latest = str(result)
                        break
                except:
                    continue
            
            # Calculate staleness
            stale = ""
            if latest != "N/A":
                try:
                    latest_dt = pd.to_datetime(latest)
                    days_old = (datetime.now() - latest_dt).days
                    if days_old > 7:
                        stale = f" ⚠️ {days_old}d old"
                    elif days_old > 1:
                        stale = f" ({days_old}d)"
                except:
                    pass
            
            print(f"  {schema}.{table:<30} | {cnt:>10,} rows | Latest: {latest}{stale}")
        except Exception as e:
            print(f"  {schema}.{table:<30} | ❌ ERROR: {e}")
    
    # =========================================================================
    # 2. TRAINING TABLES - Core matrix and specialist features
    # =========================================================================
    print("\n📊 TRAINING TABLES STATUS")
    print("-" * 60)
    
    training_tables = [
        "core_matrix_1d",
        "specialist_crush_1d",
        "specialist_china_1d",
        "specialist_fx_1d",
        "specialist_fed_1d",
        "specialist_tariff_1d",
        "specialist_energy_1d",
        "specialist_biofuel_1d",
        "specialist_palm_1d",
        "specialist_volatility_1d",
        "specialist_substitutes_1d",
        "specialist_trump_effect_1d",
    ]
    
    for table in training_tables:
        try:
            count_q = f'SELECT COUNT(*) as cnt FROM "training"."{table}"'
            cnt = pd.read_sql(count_q, engine).iloc[0]['cnt']
            
            # Check for target columns
            cols_q = f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = 'training' 
                AND table_name = '{table}'
                AND column_name LIKE 'target_%'
            """
            target_cols = pd.read_sql(cols_q, engine)['column_name'].tolist()
            
            target_status = ""
            if "core_matrix" in table:
                expected = ["target_5d", "target_21d", "target_63d", "target_126d"]
                missing = [t for t in expected if t not in target_cols]
                if missing:
                    target_status = f" ❌ MISSING: {missing}"
                else:
                    target_status = f" ✅ targets: {len(target_cols)}"
            elif "specialist_" in table:
                expected = ["target_5d", "target_21d", "target_63d", "target_126d"]
                missing = [t for t in expected if t not in target_cols]
                if missing:
                    target_status = f" ❌ MISSING TARGETS: {missing}"
                elif len(target_cols) >= 4:
                    target_status = f" ✅ targets: {len(target_cols)}"
                else:
                    target_status = f" ⚠️ targets: {target_cols}"
            
            print(f"  training.{table:<35} | {cnt:>8,} rows{target_status}")
        except Exception as e:
            print(f"  training.{table:<35} | ❌ ERROR: {e}")
    
    # =========================================================================
    # 3. OOF TABLES - Check if populated or empty
    # =========================================================================
    print("\n📊 OOF TABLES STATUS (training schema)")
    print("-" * 60)
    
    # Check for OOF tables
    oof_q = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'training' 
        AND table_name LIKE 'oof_%'
        ORDER BY table_name
    """
    try:
        oof_tables = pd.read_sql(oof_q, engine)['table_name'].tolist()
        
        if not oof_tables:
            print("  ❌ NO OOF TABLES FOUND IN training SCHEMA")
        else:
            print(f"  Found {len(oof_tables)} OOF tables:")
            for table in oof_tables:
                try:
                    cnt_q = f'SELECT COUNT(*) as cnt FROM "training"."{table}"'
                    cnt = pd.read_sql(cnt_q, engine).iloc[0]['cnt']
                    
                    # Check columns for quantiles
                    cols_q = f"""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_schema = 'training' 
                        AND table_name = '{table}'
                    """
                    cols = pd.read_sql(cols_q, engine)['column_name'].tolist()
                    
                    # Check quantile naming
                    has_p10 = any('p10' in c or 'p_10' in c for c in cols)
                    has_p30 = any('p30' in c or 'p_30' in c for c in cols)
                    has_p50 = any('p50' in c or 'p_50' in c for c in cols)
                    has_p70 = any('p70' in c or 'p_70' in c for c in cols)
                    has_p90 = any('p90' in c or 'p_90' in c for c in cols)
                    
                    quant_info = []
                    if has_p10: quant_info.append("p10")
                    if has_p30: quant_info.append("p30")
                    if has_p50: quant_info.append("p50")
                    if has_p70: quant_info.append("p70")
                    if has_p90: quant_info.append("p90")
                    
                    status = "✅" if cnt > 0 else "⬜ empty"
                    quant_str = f" quantiles: {quant_info}" if quant_info else ""
                    print(f"    {table:<40} | {cnt:>6,} rows {status}{quant_str}")
                except Exception as e:
                    print(f"    {table:<40} | ❌ ERROR: {e}")
    except Exception as e:
        print(f"  ❌ ERROR listing OOF tables: {e}")
    
    # =========================================================================
    # 4. MODEL SCHEMA - Check for old model.oof_predictions
    # =========================================================================
    print("\n📊 MODEL SCHEMA (Legacy Check)")
    print("-" * 60)
    
    model_q = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'model'
        ORDER BY table_name
    """
    try:
        model_tables = pd.read_sql(model_q, engine)['table_name'].tolist()
        if model_tables:
            print(f"  Found {len(model_tables)} tables in 'model' schema:")
            for table in model_tables:
                try:
                    cnt_q = f'SELECT COUNT(*) as cnt FROM "model"."{table}"'
                    cnt = pd.read_sql(cnt_q, engine).iloc[0]['cnt']
                    print(f"    model.{table:<35} | {cnt:>8,} rows")
                except Exception as e:
                    print(f"    model.{table:<35} | ❌ ERROR: {e}")
        else:
            print("  No tables in 'model' schema")
    except Exception as e:
        print(f"  ⚠️ 'model' schema may not exist: {e}")
    
    # =========================================================================
    # 5. FORECASTS SCHEMA - Production outputs
    # =========================================================================
    print("\n📊 FORECASTS SCHEMA")
    print("-" * 60)
    
    forecasts_q = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'forecasts'
        ORDER BY table_name
    """
    try:
        forecast_tables = pd.read_sql(forecasts_q, engine)['table_name'].tolist()
        if forecast_tables:
            print(f"  Found {len(forecast_tables)} tables in 'forecasts' schema:")
            for table in forecast_tables:
                try:
                    cnt_q = f'SELECT COUNT(*) as cnt FROM "forecasts"."{table}"'
                    cnt = pd.read_sql(cnt_q, engine).iloc[0]['cnt']
                    print(f"    forecasts.{table:<32} | {cnt:>8,} rows")
                except Exception as e:
                    print(f"    forecasts.{table:<32} | ❌ ERROR: {e}")
        else:
            print("  No tables in 'forecasts' schema")
    except Exception as e:
        print(f"  ⚠️ 'forecasts' schema may not exist: {e}")
    
    # =========================================================================
    # 6. META INPUTS - Check for stacking tables
    # =========================================================================
    print("\n📊 META INPUT TABLES (for L1 stacking)")
    print("-" * 60)
    
    meta_q = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'training' 
        AND table_name LIKE 'meta_%'
        ORDER BY table_name
    """
    try:
        meta_tables = pd.read_sql(meta_q, engine)['table_name'].tolist()
        if meta_tables:
            for table in meta_tables:
                try:
                    cnt_q = f'SELECT COUNT(*) as cnt FROM "training"."{table}"'
                    cnt = pd.read_sql(cnt_q, engine).iloc[0]['cnt']
                    
                    # Check column count
                    cols_q = f"""
                        SELECT COUNT(*) as col_cnt 
                        FROM information_schema.columns 
                        WHERE table_schema = 'training' 
                        AND table_name = '{table}'
                    """
                    col_cnt = pd.read_sql(cols_q, engine).iloc[0]['col_cnt']
                    
                    status = "✅" if cnt > 0 else "⬜ empty"
                    print(f"    training.{table:<30} | {cnt:>6,} rows | {col_cnt} cols {status}")
                except Exception as e:
                    print(f"    training.{table:<30} | ❌ ERROR: {e}")
        else:
            print("  No meta_* tables found (expected: meta_inputs_{H}d_1d)")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
    
    # =========================================================================
    # 7. CHECK FOR PLACEHOLDER/FAKE DATA
    # =========================================================================
    print("\n🔍 PLACEHOLDER DATA CHECK")
    print("-" * 60)
    
    # Check core_matrix for suspicious patterns
    try:
        # Check if all target values are identical (placeholder pattern)
        check_q = """
            SELECT 
                COUNT(DISTINCT target_5d) as unique_5d,
                COUNT(DISTINCT target_21d) as unique_21d,
                AVG(target_5d) as avg_5d,
                STDDEV(target_5d) as std_5d,
                MIN(target_5d) as min_5d,
                MAX(target_5d) as max_5d
            FROM "training"."core_matrix_1d"
            WHERE target_5d IS NOT NULL
        """
        stats = pd.read_sql(check_q, engine).iloc[0]
        
        print(f"  Core Matrix target_5d stats:")
        print(f"    Unique values: {stats['unique_5d']}")
        print(f"    Range: {stats['min_5d']:.4f} to {stats['max_5d']:.4f}")
        print(f"    Mean: {stats['avg_5d']:.4f}, Std: {stats['std_5d']:.4f}")
        
        if stats['unique_5d'] < 10:
            print(f"    ⚠️ WARNING: Only {stats['unique_5d']} unique target values - possible placeholder!")
        elif stats['std_5d'] < 0.0001:
            print(f"    ⚠️ WARNING: Near-zero variance - possible placeholder!")
        else:
            print(f"    ✅ Target data looks real (sufficient variance)")
            
    except Exception as e:
        print(f"  ❌ ERROR checking targets: {e}")
    
    # Check for any weights columns
    print("\n  Checking for weight columns across training tables...")
    weight_q = """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'training'
        AND (column_name LIKE '%weight%' OR column_name LIKE '%contrib%')
        ORDER BY table_name, column_name
    """
    try:
        weight_cols = pd.read_sql(weight_q, engine)
        if len(weight_cols) > 0:
            print(f"  Found {len(weight_cols)} weight/contribution columns:")
            for _, row in weight_cols.iterrows():
                # Check if values are placeholders
                try:
                    val_q = f"""
                        SELECT 
                            COUNT(*) as cnt,
                            COUNT(DISTINCT "{row['column_name']}") as unique_vals,
                            AVG("{row['column_name']}")::numeric(10,4) as avg_val
                        FROM "training"."{row['table_name']}"
                        WHERE "{row['column_name']}" IS NOT NULL
                    """
                    val_stats = pd.read_sql(val_q, engine).iloc[0]
                    
                    status = ""
                    if val_stats['unique_vals'] == 1:
                        status = f" ⚠️ PLACEHOLDER? (all same value: {val_stats['avg_val']})"
                    elif val_stats['unique_vals'] < 5:
                        status = f" ⚠️ Low variance ({val_stats['unique_vals']} unique)"
                    else:
                        status = f" ✅ ({val_stats['unique_vals']} unique values)"
                    
                    print(f"    {row['table_name']}.{row['column_name']}{status}")
                except Exception as e:
                    print(f"    {row['table_name']}.{row['column_name']} - check failed: {e}")
        else:
            print("  ✅ No weight columns found in training schema")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
    
    # =========================================================================
    # 8. SPECIALIST SCHEMA CHECK
    # =========================================================================
    print("\n📊 SPECIALIST SCHEMA (if exists)")
    print("-" * 60)
    
    specialist_q = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'specialist'
        ORDER BY table_name
    """
    try:
        spec_tables = pd.read_sql(specialist_q, engine)['table_name'].tolist()
        if spec_tables:
            print(f"  Found {len(spec_tables)} tables in 'specialist' schema:")
            for table in spec_tables:
                try:
                    cnt_q = f'SELECT COUNT(*) as cnt FROM "specialist"."{table}"'
                    cnt = pd.read_sql(cnt_q, engine).iloc[0]['cnt']
                    print(f"    specialist.{table:<30} | {cnt:>8,} rows")
                except Exception as e:
                    print(f"    specialist.{table:<30} | ❌ ERROR: {e}")
        else:
            print("  No tables in 'specialist' schema")
    except Exception as e:
        print(f"  ⚠️ 'specialist' schema may not exist")
    
    # =========================================================================
    # 9. ALL SCHEMAS SUMMARY
    # =========================================================================
    print("\n📊 ALL SCHEMAS IN DATABASE")
    print("-" * 60)
    
    schemas_q = """
        SELECT schema_name, 
               (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = schema_name) as table_count
        FROM information_schema.schemata
        WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        ORDER BY schema_name
    """
    try:
        schemas = pd.read_sql(schemas_q, engine)
        for _, row in schemas.iterrows():
            print(f"  {row['schema_name']:<20} | {row['table_count']:>3} tables")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
    
    print("\n" + "=" * 80)
    print("✅ VALIDATION COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()
