#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Fix Specialist Tables

Fixes:
1. SUBSTITUTES - Replace meat/protein data with proper vegetable oil data
2. TRUMP_EFFECT - Populate specialist table from features table
3. FX - Create missing table and populate with FX data
4. CHINA - Verify and fix any missing data

Usage:
    python scripts/fix_specialist_tables.py --dry-run
    python scripts/fix_specialist_tables.py --execute
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from typing import Dict, List

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def fix_substitutes_specialist(conn, dry_run: bool = True):
    """
    Fix specialist_substitutes_1d table.

    Problem: Table was populated with meat/protein futures (HE, LE, GF, DC)
    instead of vegetable oil substitutes (RS=canola, CPO=palm).

    Fix: Clear table and repopulate with correct oil data:
    - RS (Canola/Rapeseed) from mkt.futures_1d
    - CPO (Crude Palm Oil) from mkt.futures_1d
    - ZL (Soybean Oil) for spread calculations
    """
    print("\n" + "=" * 70)
    print("FIX #1: SUBSTITUTES SPECIALIST")
    print("=" * 70)

    cur = conn.cursor()

    # Check current state
    cur.execute("""
        SELECT symbol, COUNT(*) as rows
        FROM training.specialist_substitutes_1d
        GROUP BY symbol ORDER BY symbol
    """)
    current = cur.fetchall()
    print("Current data (WRONG):")
    for row in current:
        print(f"  {row[0]}: {row[1]:,} rows")

    if dry_run:
        print("\n[DRY RUN] Would clear table and repopulate with RS, CPO, ZL")

        # Show what would be inserted
        cur.execute("""
            SELECT symbol, COUNT(*), MIN(event_date), MAX(event_date)
            FROM mkt.futures_1d
            WHERE symbol IN ('RS', 'CPO', 'ZL')
            GROUP BY symbol
        """)
        for row in cur.fetchall():
            print(f"  Would insert {row[0]}: {row[1]:,} rows ({row[2]} to {row[3]})")
        return

    # Clear existing (wrong) data
    print("\nClearing incorrect data...")
    cur.execute("TRUNCATE TABLE training.specialist_substitutes_1d RESTART IDENTITY")
    conn.commit()

    # Insert correct vegetable oil data
    print("Inserting correct vegetable oil data...")
    cur.execute("""
        INSERT INTO training.specialist_substitutes_1d
        (symbol, as_of_date, open, high, low, close, volume, open_interest,
         contract_month, bucket_name, granularity, created_at)
        SELECT
            symbol,
            event_date as as_of_date,
            open, high, low, close, volume,
            COALESCE(open_interest, 0) as open_interest,
            NULL as contract_month,
            'substitutes' as bucket_name,
            '1d' as granularity,
            NOW() as created_at
        FROM mkt.futures_1d
        WHERE symbol IN ('RS', 'CPO', 'ZL')
        ORDER BY event_date, symbol
    """)
    inserted = cur.rowcount
    conn.commit()

    # Verify
    cur.execute("""
        SELECT symbol, COUNT(*), MIN(as_of_date), MAX(as_of_date)
        FROM training.specialist_substitutes_1d
        GROUP BY symbol ORDER BY symbol
    """)
    print(f"\n✅ Inserted {inserted:,} rows:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,} rows ({row[2]} to {row[3]})")


def fix_trump_effect_specialist(conn, dry_run: bool = True):
    """
    Fix specialist_trump_effect_1d table.

    Problem: Table has only 2 sentiment rows but features.trump_effect_1d
    has 3,294 rows of executive order counts.

    Fix: Generate specialist signals from the features table data.
    Signal = weighted_action_score normalized to [-1, 1]
    Confidence = based on action velocity and data quality
    """
    print("\n" + "=" * 70)
    print("FIX #2: TRUMP EFFECT SPECIALIST")
    print("=" * 70)

    cur = conn.cursor()

    # Check current state
    cur.execute("SELECT COUNT(*) FROM training.specialist_trump_effect_1d")
    specialist_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM features.trump_effect_1d")
    features_count = cur.fetchone()[0]

    print(f"Current state:")
    print(f"  specialist_trump_effect_1d: {specialist_count:,} rows")
    print(f"  features.trump_effect_1d: {features_count:,} rows")

    if dry_run:
        print(f"\n[DRY RUN] Would generate ~{features_count} specialist rows from features")
        return

    # Clear existing data
    print("\nClearing existing specialist data...")
    cur.execute("TRUNCATE TABLE training.specialist_trump_effect_1d RESTART IDENTITY")
    conn.commit()

    # Generate specialist data from features
    print("Generating specialist signals from features...")
    cur.execute("""
        INSERT INTO training.specialist_trump_effect_1d
        (as_of_date, symbol, signal, confidence, features, created_at)
        SELECT
            as_of_date,
            'ZL' as symbol,
            -- Signal: normalized weighted score, positive = bullish, negative = bearish
            CASE
                WHEN weighted_action_score > 0
                THEN LEAST(1.0, weighted_action_score / 2.0)
                ELSE 0.0
            END as signal,
            -- Confidence: based on action velocity and total actions
            CASE
                WHEN total_actions_7d = 0 THEN 0.3
                WHEN action_velocity > 1.0 THEN 0.9
                WHEN action_velocity > 0.5 THEN 0.7
                ELSE 0.5
            END as confidence,
            -- Features as JSONB
            jsonb_build_object(
                'eo_count_7d', eo_count_7d,
                'eo_count_30d', eo_count_30d,
                'total_actions_7d', total_actions_7d,
                'total_actions_30d', total_actions_30d,
                'action_velocity', action_velocity,
                'action_acceleration', action_acceleration,
                'weighted_action_score', weighted_action_score,
                'era', CASE
                    WHEN as_of_date < '2017-01-20' THEN 'pre_trump'
                    WHEN as_of_date <= '2021-01-20' THEN 'trump1'
                    WHEN as_of_date < '2025-01-20' THEN 'gap'
                    ELSE 'trump2'
                END
            ) as features,
            NOW() as created_at
        FROM features.trump_effect_1d
        ORDER BY as_of_date
    """)
    inserted = cur.rowcount
    conn.commit()

    # Verify
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE signal > 0) as positive_signals,
            AVG(confidence) as avg_confidence
        FROM training.specialist_trump_effect_1d
    """)
    result = cur.fetchone()
    print(f"\n✅ Inserted {inserted:,} rows:")
    print(f"  Positive signals: {result[1]:,}")
    print(f"  Avg confidence: {result[2]:.2f}")


def fix_fx_specialist(conn, dry_run: bool = True):
    """
    Fix specialist_fx_1d table.

    Problem: Table doesn't exist!

    Fix: Create table and populate with FX data from mkt.fx_1d.
    """
    print("\n" + "=" * 70)
    print("FIX #3: FX SPECIALIST")
    print("=" * 70)

    cur = conn.cursor()

    # Check if table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'training' AND table_name = 'specialist_fx_1d'
        )
    """)
    exists = cur.fetchone()[0]

    if exists:
        cur.execute("SELECT COUNT(*) FROM training.specialist_fx_1d")
        count = cur.fetchone()[0]
        print(f"Table exists with {count:,} rows")
    else:
        print("Table DOES NOT EXIST - needs creation")

    # Check what FX data we have
    cur.execute("""
        SELECT pair, COUNT(*), MIN(event_date), MAX(event_date)
        FROM mkt.fx_1d
        GROUP BY pair ORDER BY pair
    """)
    fx_data = cur.fetchall()
    print("\nAvailable FX data:")
    for row in fx_data:
        print(f"  {row[0]}: {row[1]:,} rows ({row[2]} to {row[3]})")

    if dry_run:
        print(f"\n[DRY RUN] Would create table and populate with FX data")
        return

    # Create table if not exists (using same schema as other specialists)
    if not exists:
        print("\nCreating specialist_fx_1d table...")
        cur.execute("""
            CREATE TABLE training.specialist_fx_1d (
                id BIGSERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                as_of_date DATE NOT NULL,
                open DECIMAL(18,8),
                high DECIMAL(18,8),
                low DECIMAL(18,8),
                close DECIMAL(18,8) NOT NULL,
                volume BIGINT,
                open_interest BIGINT,
                contract_month VARCHAR(10),
                expiration_date DATE,
                bucket_name VARCHAR(50) DEFAULT 'fx',
                granularity VARCHAR(10) DEFAULT '1d',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(symbol, as_of_date)
            )
        """)
        conn.commit()
        print("  ✅ Table created")

    # Populate from mkt.fx_1d
    print("Populating FX specialist table...")
    cur.execute("""
        INSERT INTO training.specialist_fx_1d
        (symbol, as_of_date, close, bucket_name, granularity, created_at)
        SELECT
            pair as symbol,
            event_date as as_of_date,
            rate as close,
            'fx' as bucket_name,
            '1d' as granularity,
            NOW() as created_at
        FROM mkt.fx_1d
        ORDER BY event_date, pair
        ON CONFLICT (symbol, as_of_date) DO NOTHING
    """)
    inserted = cur.rowcount
    conn.commit()

    # Verify
    cur.execute("""
        SELECT symbol, COUNT(*), MIN(as_of_date), MAX(as_of_date)
        FROM training.specialist_fx_1d
        GROUP BY symbol ORDER BY symbol
    """)
    print(f"\n✅ Inserted {inserted:,} rows:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,} rows ({row[2]} to {row[3]})")


def fix_china_specialist(conn, dry_run: bool = True):
    """
    Verify and fix China specialist.

    Check:
    - specialist_china_1d data
    - China-related columns in training.matrix_1d
    - Add HG (copper) as China demand proxy
    """
    print("\n" + "=" * 70)
    print("FIX #4: CHINA SPECIALIST")
    print("=" * 70)

    cur = conn.cursor()

    # Check current specialist data
    cur.execute("""
        SELECT symbol, COUNT(*), MIN(as_of_date), MAX(as_of_date)
        FROM training.specialist_china_1d
        GROUP BY symbol ORDER BY symbol
    """)
    china_data = cur.fetchall()
    print("Current specialist_china_1d data:")
    for row in china_data:
        print(f"  {row[0]}: {row[1]:,} rows ({row[2]} to {row[3]})")

    # Check if HG (copper) is missing
    cur.execute("""
        SELECT COUNT(*) FROM training.specialist_china_1d WHERE symbol = 'HG'
    """)
    hg_count = cur.fetchone()[0]

    # Check FRED China data
    cur.execute("""
        SELECT COUNT(fred_chnmainlandtpu) as china_tpu
        FROM training.matrix_1d
        WHERE fred_chnmainlandtpu IS NOT NULL
    """)
    china_tpu_count = cur.fetchone()[0]
    print(f"\nFRED China Trade Policy Uncertainty: {china_tpu_count:,} rows populated")

    print(f"\nCopper (HG) as China demand proxy: {hg_count:,} rows")

    # Check what HG data we have
    cur.execute("""
        SELECT COUNT(*), MIN(event_date), MAX(event_date)
        FROM mkt.futures_1d WHERE symbol = 'HG'
    """)
    hg_available = cur.fetchone()
    print(f"  Available in mkt.futures_1d: {hg_available[0]:,} rows ({hg_available[1]} to {hg_available[2]})")

    if dry_run:
        if hg_count == 0:
            print(f"\n[DRY RUN] Would add {hg_available[0]:,} rows of HG (copper) to China specialist")
        print("\n⚠️  STILL MISSING (requires external data):")
        print("  1. China soybean import volumes (monthly)")
        print("  2. Dalian soybean oil futures (DCE)")
        return

    # Add HG (copper) to China specialist if missing
    if hg_count == 0:
        print("\nAdding HG (copper) to China specialist...")
        cur.execute("""
            INSERT INTO training.specialist_china_1d
            (symbol, as_of_date, open, high, low, close, volume, open_interest,
             bucket_name, granularity, created_at)
            SELECT
                symbol,
                event_date as as_of_date,
                open, high, low, close, volume,
                COALESCE(open_interest, 0) as open_interest,
                'china' as bucket_name,
                '1d' as granularity,
                NOW() as created_at
            FROM mkt.futures_1d
            WHERE symbol = 'HG'
            ON CONFLICT DO NOTHING
        """)
        inserted = cur.rowcount
        conn.commit()
        print(f"  ✅ Added {inserted:,} rows of HG (copper)")

    # Verify final state
    cur.execute("""
        SELECT symbol, COUNT(*) FROM training.specialist_china_1d
        GROUP BY symbol ORDER BY symbol
    """)
    print("\nFinal China specialist data:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,} rows")

    print("\n⚠️  STILL MISSING (requires external data):")
    print("  1. China soybean import volumes (monthly)")
    print("  2. Dalian soybean oil futures (DCE)")


def check_duplicate_symbols(conn):
    """Check for duplicate symbols across specialist tables."""
    print("\n" + "=" * 70)
    print("CHECK: DUPLICATE SYMBOLS ACROSS SPECIALISTS")
    print("=" * 70)

    cur = conn.cursor()

    specialists = [
        'biofuel', 'china', 'crush', 'energy', 'fed', 'palm',
        'substitutes', 'tariff', 'trump_effect', 'volatility'
    ]

    symbol_map = {}

    for specialist in specialists:
        table = f"training.specialist_{specialist}_1d"
        try:
            cur.execute(f"SELECT DISTINCT symbol FROM {table}")
            symbols = [r[0] for r in cur.fetchall()]
            for sym in symbols:
                if sym not in symbol_map:
                    symbol_map[sym] = []
                symbol_map[sym].append(specialist)
        except:
            conn.rollback()
            continue

    # Find symbols in multiple specialists
    print("\nSymbols shared across specialists (intentional overlap):")
    for sym, specialists in sorted(symbol_map.items()):
        if len(specialists) > 1:
            print(f"  {sym}: {', '.join(specialists)}")

    # Check for ZL specifically - it should be in most specialists
    zl_specialists = symbol_map.get('ZL', [])
    print(f"\nZL appears in {len(zl_specialists)} specialists: {', '.join(zl_specialists)}")


def main():
    parser = argparse.ArgumentParser(description="Fix specialist tables")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    parser.add_argument("--execute", action="store_true", help="Execute the fixes")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("ERROR: Must specify either --dry-run or --execute")
        sys.exit(1)

    dry_run = args.dry_run

    print("=" * 70)
    print("ZINC-FUSION-V15: FIX SPECIALIST TABLES")
    print("=" * 70)
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print(f"Time: {datetime.now()}")

    conn = get_connection()

    try:
        # Fix each specialist
        fix_substitutes_specialist(conn, dry_run)
        fix_trump_effect_specialist(conn, dry_run)
        fix_fx_specialist(conn, dry_run)
        fix_china_specialist(conn, dry_run)

        # Check for duplicate symbols
        check_duplicate_symbols(conn)

        print("\n" + "=" * 70)
        if dry_run:
            print("DRY RUN COMPLETE - No changes made")
        else:
            print("✅ ALL FIXES APPLIED SUCCESSFULLY")
        print("=" * 70)

    except Exception as e:
        conn.rollback()
        print(f"\n❌ ERROR: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
