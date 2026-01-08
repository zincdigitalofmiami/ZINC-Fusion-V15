#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Migration 001 - Create Forecasts Schema & Tables
Executed with caution - validates before and after each step
"""

import os
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL)

def execute_ddl(conn, statement, description):
    """Execute a DDL statement with validation"""
    print(f"\n{'='*60}")
    print(f"EXECUTING: {description}")
    print(f"{'='*60}")
    try:
        with conn.cursor() as cur:
            cur.execute(statement)
        conn.commit()
        print(f"✅ SUCCESS: {description}")
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ FAILED: {description}")
        print(f"   Error: {e}")
        return False

def verify_schema_exists(conn, schema_name):
    """Check if schema exists"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT schema_name FROM information_schema.schemata 
            WHERE schema_name = %s
        """, (schema_name,))
        result = cur.fetchone()
        return result is not None

def verify_table_exists(conn, schema_name, table_name):
    """Check if table exists"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = %s AND table_name = %s
        """, (schema_name, table_name))
        result = cur.fetchone()
        return result is not None

def main():
    print("\n" + "="*70)
    print("ZINC-FUSION-V15: MIGRATION 001 - CREATE FORECASTS SCHEMA")
    print("="*70)
    
    conn = get_connection()
    print("✅ Connected to database")
    
    # =========================================================================
    # STEP 1: Create schemas
    # =========================================================================
    
    schemas_to_create = ['forecasts', 'features']
    
    for schema in schemas_to_create:
        if verify_schema_exists(conn, schema):
            print(f"⚠️  Schema '{schema}' already exists - skipping")
        else:
            execute_ddl(conn, f"CREATE SCHEMA {schema}", f"Create schema: {schema}")
            if verify_schema_exists(conn, schema):
                print(f"   ✓ Verified: schema '{schema}' created")
            else:
                print(f"   ✗ ERROR: schema '{schema}' not found after creation!")
                return
    
    # =========================================================================
    # STEP 2: Create forecasts.core_cone_1d
    # =========================================================================
    
    if verify_table_exists(conn, 'forecasts', 'core_cone_1d'):
        print("⚠️  Table 'forecasts.core_cone_1d' already exists - skipping")
    else:
        ddl = """
        CREATE TABLE forecasts.core_cone_1d (
            id SERIAL PRIMARY KEY,
            forecast_date DATE NOT NULL,
            horizon_days INTEGER NOT NULL,
            target_date DATE NOT NULL,
            p10 DOUBLE PRECISION NOT NULL,
            p50 DOUBLE PRECISION NOT NULL,
            p90 DOUBLE PRECISION NOT NULL,
            model_version VARCHAR(50) DEFAULT 'chronos2-v1',
            config_hash VARCHAR(64),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(forecast_date, horizon_days)
        )
        """
        execute_ddl(conn, ddl, "Create table: forecasts.core_cone_1d")
    
    # =========================================================================
    # STEP 3: Create forecasts.core_mc_1d
    # =========================================================================
    
    if verify_table_exists(conn, 'forecasts', 'core_mc_1d'):
        print("⚠️  Table 'forecasts.core_mc_1d' already exists - skipping")
    else:
        ddl = """
        CREATE TABLE forecasts.core_mc_1d (
            id SERIAL PRIMARY KEY,
            forecast_date DATE NOT NULL,
            horizon_days INTEGER NOT NULL,
            s0 DOUBLE PRECISION NOT NULL,
            q10 DOUBLE PRECISION NOT NULL,
            q50 DOUBLE PRECISION NOT NULL,
            q90 DOUBLE PRECISION NOT NULL,
            mu_annual DOUBLE PRECISION,
            sigma_annual DOUBLE PRECISION,
            mc_p10_final DOUBLE PRECISION,
            mc_p50_final DOUBLE PRECISION,
            mc_p90_final DOUBLE PRECISION,
            mc_min_p10 DOUBLE PRECISION,
            mc_max_p90 DOUBLE PRECISION,
            opp DOUBLE PRECISION,
            ruin DOUBLE PRECISION,
            var_95 DOUBLE PRECISION,
            cvar_95 DOUBLE PRECISION,
            runs INTEGER DEFAULT 5000,
            seed INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(forecast_date, horizon_days)
        )
        """
        execute_ddl(conn, ddl, "Create table: forecasts.core_mc_1d")
    
    # =========================================================================
    # STEP 4: Create forecasts.ai_decision_1d
    # =========================================================================
    
    if verify_table_exists(conn, 'forecasts', 'ai_decision_1d'):
        print("⚠️  Table 'forecasts.ai_decision_1d' already exists - skipping")
    else:
        ddl = """
        CREATE TABLE forecasts.ai_decision_1d (
            id SERIAL PRIMARY KEY,
            forecast_date DATE NOT NULL,
            horizon_days INTEGER NOT NULL,
            opp DOUBLE PRECISION,
            ruin DOUBLE PRECISION,
            calibrated_p10 DOUBLE PRECISION,
            calibrated_p90 DOUBLE PRECISION,
            coverage_error DOUBLE PRECISION,
            regime VARCHAR(20),
            regime_multiplier DOUBLE PRECISION DEFAULT 1.0,
            urgency_score DOUBLE PRECISION,
            posture_label VARCHAR(20),
            posture_message TEXT,
            narrative TEXT,
            top_driver_1 VARCHAR(50),
            top_driver_2 VARCHAR(50),
            top_driver_3 VARCHAR(50),
            recommended_pace VARCHAR(20),
            model_version VARCHAR(50),
            ai_model VARCHAR(50),
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(forecast_date, horizon_days)
        )
        """
        execute_ddl(conn, ddl, "Create table: forecasts.ai_decision_1d")
    
    # =========================================================================
    # STEP 5: Create forecasts.horizon_reconciliation_1d
    # =========================================================================
    
    if verify_table_exists(conn, 'forecasts', 'horizon_reconciliation_1d'):
        print("⚠️  Table 'forecasts.horizon_reconciliation_1d' already exists - skipping")
    else:
        ddl = """
        CREATE TABLE forecasts.horizon_reconciliation_1d (
            id SERIAL PRIMARY KEY,
            forecast_date DATE NOT NULL UNIQUE,
            tactical_posture VARCHAR(20),
            short_posture VARCHAR(20),
            medium_posture VARCHAR(20),
            strategic_posture VARCHAR(20),
            conflict_flag BOOLEAN DEFAULT FALSE,
            reconciled_guidance TEXT,
            priority_horizon INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        execute_ddl(conn, ddl, "Create table: forecasts.horizon_reconciliation_1d")
    
    # =========================================================================
    # STEP 6: Create analytics.regime_state_1d
    # =========================================================================
    
    if verify_table_exists(conn, 'analytics', 'regime_state_1d'):
        print("⚠️  Table 'analytics.regime_state_1d' already exists - skipping")
    else:
        ddl = """
        CREATE TABLE analytics.regime_state_1d (
            id SERIAL PRIMARY KEY,
            forecast_date DATE NOT NULL UNIQUE,
            regime VARCHAR(20) NOT NULL,
            vix_contribution DOUBLE PRECISION,
            policy_contribution DOUBLE PRECISION,
            news_contribution DOUBLE PRECISION,
            confidence DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        execute_ddl(conn, ddl, "Create table: analytics.regime_state_1d")
    
    # =========================================================================
    # STEP 7: Create analytics.driver_attribution_1d
    # =========================================================================
    
    if verify_table_exists(conn, 'analytics', 'driver_attribution_1d'):
        print("⚠️  Table 'analytics.driver_attribution_1d' already exists - skipping")
    else:
        ddl = """
        CREATE TABLE analytics.driver_attribution_1d (
            id SERIAL PRIMARY KEY,
            forecast_date DATE NOT NULL,
            horizon_days INTEGER NOT NULL,
            driver_name VARCHAR(50) NOT NULL,
            shap_value DOUBLE PRECISION,
            direction VARCHAR(10),
            rank INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(forecast_date, horizon_days, driver_name)
        )
        """
        execute_ddl(conn, ddl, "Create table: analytics.driver_attribution_1d")
    
    # =========================================================================
    # STEP 8: Create features.trump_effect_1d
    # =========================================================================
    
    if verify_table_exists(conn, 'features', 'trump_effect_1d'):
        print("⚠️  Table 'features.trump_effect_1d' already exists - skipping")
    else:
        ddl = """
        CREATE TABLE features.trump_effect_1d (
            id SERIAL PRIMARY KEY,
            as_of_date DATE NOT NULL UNIQUE,
            eo_count_7d INTEGER DEFAULT 0,
            eo_count_30d INTEGER DEFAULT 0,
            proclamation_count_7d INTEGER DEFAULT 0,
            proclamation_count_30d INTEGER DEFAULT 0,
            nomination_count_7d INTEGER DEFAULT 0,
            nomination_count_30d INTEGER DEFAULT 0,
            memorandum_count_7d INTEGER DEFAULT 0,
            memorandum_count_30d INTEGER DEFAULT 0,
            total_actions_7d INTEGER DEFAULT 0,
            total_actions_30d INTEGER DEFAULT 0,
            avg_sentiment_7d DOUBLE PRECISION,
            avg_sentiment_30d DOUBLE PRECISION,
            action_velocity DOUBLE PRECISION,
            action_acceleration DOUBLE PRECISION,
            weighted_action_score DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        execute_ddl(conn, ddl, "Create table: features.trump_effect_1d")
    
    # =========================================================================
    # STEP 9: Create raw.whitehouse_actions_event (for future live scraping)
    # =========================================================================
    
    if verify_table_exists(conn, 'raw', 'whitehouse_actions_event'):
        print("⚠️  Table 'raw.whitehouse_actions_event' already exists - skipping")
    else:
        ddl = """
        CREATE TABLE raw.whitehouse_actions_event (
            id SERIAL PRIMARY KEY,
            action_date DATE NOT NULL,
            action_type VARCHAR(50) NOT NULL,
            title TEXT,
            url TEXT,
            summary TEXT,
            tags JSONB,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(action_date, action_type, title)
        )
        """
        execute_ddl(conn, ddl, "Create table: raw.whitehouse_actions_event")
    
    # =========================================================================
    # CREATE INDEXES
    # =========================================================================
    
    indexes = [
        ("idx_core_cone_forecast_date", "forecasts.core_cone_1d", "forecast_date"),
        ("idx_core_mc_forecast_date", "forecasts.core_mc_1d", "forecast_date"),
        ("idx_ai_decision_forecast_date", "forecasts.ai_decision_1d", "forecast_date"),
        ("idx_regime_state_forecast_date", "analytics.regime_state_1d", "forecast_date"),
        ("idx_driver_attr_forecast_date", "analytics.driver_attribution_1d", "forecast_date"),
        ("idx_trump_effect_as_of_date", "features.trump_effect_1d", "as_of_date"),
    ]
    
    print("\n" + "="*60)
    print("CREATING INDEXES")
    print("="*60)
    
    for idx_name, table, column in indexes:
        ddl = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})"
        execute_ddl(conn, ddl, f"Create index: {idx_name}")
    
    # =========================================================================
    # FINAL VERIFICATION
    # =========================================================================
    
    print("\n" + "="*70)
    print("FINAL VERIFICATION")
    print("="*70)
    
    tables_to_verify = [
        ('forecasts', 'core_cone_1d'),
        ('forecasts', 'core_mc_1d'),
        ('forecasts', 'ai_decision_1d'),
        ('forecasts', 'horizon_reconciliation_1d'),
        ('analytics', 'regime_state_1d'),
        ('analytics', 'driver_attribution_1d'),
        ('features', 'trump_effect_1d'),
        ('raw', 'whitehouse_actions_event'),
    ]
    
    all_verified = True
    for schema, table in tables_to_verify:
        exists = verify_table_exists(conn, schema, table)
        status = "✅" if exists else "❌"
        print(f"  {status} {schema}.{table}")
        if not exists:
            all_verified = False
    
    conn.close()
    
    print("\n" + "="*70)
    if all_verified:
        print("🎉 MIGRATION 001 COMPLETE - ALL TABLES CREATED SUCCESSFULLY")
    else:
        print("⚠️  MIGRATION 001 INCOMPLETE - SOME TABLES MISSING")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
