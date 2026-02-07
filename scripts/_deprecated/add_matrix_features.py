#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Add Calculated Features to Training Matrix

Adds missing features required by specialist models:
1. ZS, ZM close prices (from mkt.futures_1d)
2. Crush spread = (ZM * 0.022 + ZL * 11) - ZS
3. Oil share = (ZL * 11) / (ZL * 11 + ZM * 0.022)
4. WTI-ZL correlation (30d rolling)
5. VIX-ZL correlation (30d rolling)
6. Biodiesel margin = ZL - (WTI * conversion factor)
7. Palm-Soy spread = CPO - ZL
8. RS (Canola) close price and ZL-Canola spread
9. Trump effect features (from features.trump_effect_1d)
10. Additional rolling correlations: HO, RB, NG, HG, GC, DGS10, DGS2

Usage:
    python scripts/add_matrix_features.py --dry-run
    python scripts/add_matrix_features.py --execute
"""

import os
import sys
import argparse
from datetime import datetime

import pandas as pd
import numpy as np
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def add_columns_if_missing(conn, columns: list):
    """Add columns to training.matrix_1d if they don't exist."""
    cur = conn.cursor()

    # Get existing columns
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'training' AND table_name = 'matrix_1d'
    """)
    existing = {r[0] for r in cur.fetchall()}

    for col, dtype in columns:
        if col not in existing:
            print(f"  Adding column: {col} ({dtype})")
            cur.execute(f"ALTER TABLE training.matrix_1d ADD COLUMN {col} {dtype}")
        else:
            print(f"  Column exists: {col}")

    conn.commit()


def compute_features(conn, dry_run: bool = True):
    """Compute and populate features."""
    cur = conn.cursor()

    print("\n" + "=" * 70)
    print("STEP 1: ADD MISSING COLUMNS")
    print("=" * 70)

    new_columns = [
        # Existing
        ("zs_close", "DECIMAL(18,6)"),
        ("zm_close", "DECIMAL(18,6)"),
        ("crush_spread", "DECIMAL(18,6)"),
        ("oil_share", "DECIMAL(18,6)"),
        ("wti_zl_corr_30d", "DECIMAL(18,6)"),
        ("vix_zl_corr_30d", "DECIMAL(18,6)"),
        ("biodiesel_margin", "DECIMAL(18,6)"),
        ("cpo_close", "DECIMAL(18,6)"),
        ("palm_soy_spread", "DECIMAL(18,6)"),
        ("rs_close", "DECIMAL(18,6)"),
        ("zl_canola_spread", "DECIMAL(18,6)"),
        # Trump effect features
        ("trump_total_actions_7d", "INTEGER"),
        ("trump_total_actions_30d", "INTEGER"),
        ("trump_avg_sentiment_7d", "DECIMAL(18,6)"),
        ("trump_avg_sentiment_30d", "DECIMAL(18,6)"),
        ("trump_action_velocity", "DECIMAL(18,6)"),
        ("trump_weighted_action_score", "DECIMAL(18,6)"),
        # Additional correlations (30d rolling)
        ("ho_zl_corr_30d", "DECIMAL(18,6)"),   # Heating Oil
        ("rb_zl_corr_30d", "DECIMAL(18,6)"),   # RBOB Gasoline
        ("ng_zl_corr_30d", "DECIMAL(18,6)"),   # Natural Gas
        ("hg_zl_corr_30d", "DECIMAL(18,6)"),   # Copper
        ("gc_zl_corr_30d", "DECIMAL(18,6)"),   # Gold
        ("dgs10_zl_corr_30d", "DECIMAL(18,6)"),  # 10Y Treasury yield
        ("dgs2_zl_corr_30d", "DECIMAL(18,6)"),   # 2Y Treasury yield
    ]

    if dry_run:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'training' AND table_name = 'matrix_1d'
        """)
        existing = {r[0] for r in cur.fetchall()}
        for col, dtype in new_columns:
            status = "exists" if col in existing else "WOULD ADD"
            print(f"  {col}: {status}")
    else:
        add_columns_if_missing(conn, new_columns)

    print("\n" + "=" * 70)
    print("STEP 2: POPULATE ZS, ZM, CPO, RS CLOSE PRICES")
    print("=" * 70)

    # Load futures data
    cur.execute("""
        SELECT symbol, event_date, close
        FROM mkt.futures_1d
        WHERE symbol IN ('ZS', 'ZM', 'CPO', 'RS')
        ORDER BY event_date, symbol
    """)
    futures = cur.fetchall()
    print(f"  Loaded {len(futures):,} rows of futures data")

    if dry_run:
        print("  [DRY RUN] Would populate zs_close, zm_close, cpo_close, rs_close")
    else:
        # Update ZS close
        cur.execute("""
            UPDATE training.matrix_1d m
            SET zs_close = f.close
            FROM mkt.futures_1d f
            WHERE f.symbol = 'ZS'
              AND m.trade_date = f.event_date
        """)
        print(f"  zs_close: {cur.rowcount:,} rows updated")

        # Update ZM close
        cur.execute("""
            UPDATE training.matrix_1d m
            SET zm_close = f.close
            FROM mkt.futures_1d f
            WHERE f.symbol = 'ZM'
              AND m.trade_date = f.event_date
        """)
        print(f"  zm_close: {cur.rowcount:,} rows updated")

        # Update CPO close
        cur.execute("""
            UPDATE training.matrix_1d m
            SET cpo_close = f.close
            FROM mkt.futures_1d f
            WHERE f.symbol = 'CPO'
              AND m.trade_date = f.event_date
        """)
        print(f"  cpo_close: {cur.rowcount:,} rows updated")

        # Update RS close
        cur.execute("""
            UPDATE training.matrix_1d m
            SET rs_close = f.close
            FROM mkt.futures_1d f
            WHERE f.symbol = 'RS'
              AND m.trade_date = f.event_date
        """)
        print(f"  rs_close: {cur.rowcount:,} rows updated")

        conn.commit()

    print("\n" + "=" * 70)
    print("STEP 3: CALCULATE DERIVED FEATURES")
    print("=" * 70)

    if dry_run:
        print("  [DRY RUN] Would calculate:")
        print("    - crush_spread = (ZM * 0.022 + ZL * 11) - ZS")
        print("    - oil_share = (ZL * 11) / ((ZL * 11) + (ZM * 0.022))")
        print("    - biodiesel_margin = ZL - (WTI * 0.42)")
        print("    - palm_soy_spread = CPO - ZL")
        print("    - zl_canola_spread = ZL - RS")
    else:
        # Crush spread: Standard board crush formula
        # ZM is $/short ton, ZL is cents/lb, ZS is cents/bushel
        # Formula: (ZM * 0.022) + (ZL * 11) - ZS
        cur.execute("""
            UPDATE training.matrix_1d
            SET crush_spread = (zm_close * 0.022) + (close * 11) - zs_close
            WHERE zs_close IS NOT NULL AND zm_close IS NOT NULL
        """)
        print(f"  crush_spread: {cur.rowcount:,} rows updated")

        # Oil share: ZL value as % of total product value
        cur.execute("""
            UPDATE training.matrix_1d
            SET oil_share = (close * 11) / NULLIF((close * 11) + (zm_close * 0.022), 0)
            WHERE zm_close IS NOT NULL
        """)
        print(f"  oil_share: {cur.rowcount:,} rows updated")

        # Biodiesel margin: ZL - (WTI * conversion factor)
        # WTI is $/barrel, ZL is cents/lb, 1 barrel = ~7.5 lbs soy oil equivalent
        cur.execute("""
            UPDATE training.matrix_1d
            SET biodiesel_margin = close - (fred_dcoilwtico * 0.42)
            WHERE fred_dcoilwtico IS NOT NULL
        """)
        print(f"  biodiesel_margin: {cur.rowcount:,} rows updated")

        # Palm-Soy spread
        cur.execute("""
            UPDATE training.matrix_1d
            SET palm_soy_spread = cpo_close - close
            WHERE cpo_close IS NOT NULL
        """)
        print(f"  palm_soy_spread: {cur.rowcount:,} rows updated")

        # ZL-Canola spread
        cur.execute("""
            UPDATE training.matrix_1d
            SET zl_canola_spread = close - rs_close
            WHERE rs_close IS NOT NULL
        """)
        print(f"  zl_canola_spread: {cur.rowcount:,} rows updated")

        conn.commit()

    print("\n" + "=" * 70)
    print("STEP 4: POPULATE TRUMP EFFECT FEATURES")
    print("=" * 70)

    if dry_run:
        print("  [DRY RUN] Would populate trump effect features from features.trump_effect_1d")
        cur.execute("SELECT COUNT(*) FROM features.trump_effect_1d")
        count = cur.fetchone()[0]
        print(f"  Source rows available: {count:,}")
    else:
        # Map trump effect columns from source to target
        trump_mappings = [
            ("total_actions_7d", "trump_total_actions_7d"),
            ("total_actions_30d", "trump_total_actions_30d"),
            ("avg_sentiment_7d", "trump_avg_sentiment_7d"),
            ("avg_sentiment_30d", "trump_avg_sentiment_30d"),
            ("action_velocity", "trump_action_velocity"),
            ("weighted_action_score", "trump_weighted_action_score"),
        ]

        for src_col, tgt_col in trump_mappings:
            cur.execute(f"""
                UPDATE training.matrix_1d m
                SET {tgt_col} = t.{src_col}
                FROM features.trump_effect_1d t
                WHERE m.trade_date = t.as_of_date
            """)
            print(f"  {tgt_col}: {cur.rowcount:,} rows updated")

        conn.commit()

    print("\n" + "=" * 70)
    print("STEP 5: CALCULATE ALL ROLLING CORRELATIONS")
    print("=" * 70)

    if dry_run:
        print("  [DRY RUN] Would calculate 30-day rolling correlations:")
        print("    - wti_zl_corr_30d: WTI vs ZL returns")
        print("    - vix_zl_corr_30d: VIX vs ZL level")
        print("    - ho_zl_corr_30d: Heating Oil vs ZL returns")
        print("    - rb_zl_corr_30d: RBOB Gasoline vs ZL returns")
        print("    - ng_zl_corr_30d: Natural Gas vs ZL returns")
        print("    - hg_zl_corr_30d: Copper vs ZL returns")
        print("    - gc_zl_corr_30d: Gold vs ZL returns")
        print("    - dgs10_zl_corr_30d: 10Y Treasury vs ZL level")
        print("    - dgs2_zl_corr_30d: 2Y Treasury vs ZL level")
    else:
        # Load ZL data
        cur.execute("""
            SELECT trade_date, close, fred_dcoilwtico, fred_vixcls, fred_dgs10, fred_dgs2
            FROM training.matrix_1d
            WHERE close IS NOT NULL
            ORDER BY trade_date
        """)
        data = cur.fetchall()
        df = pd.DataFrame(data, columns=['trade_date', 'zl_close', 'wti', 'vix', 'dgs10', 'dgs2'])
        df = df.set_index('trade_date')

        # Load additional futures for correlations
        futures_to_load = ['HO', 'RB', 'NG', 'HG', 'GC']
        for symbol in futures_to_load:
            cur.execute("""
                SELECT event_date, close
                FROM mkt.futures_1d
                WHERE symbol = %s
                ORDER BY event_date
            """, (symbol,))
            fut_data = cur.fetchall()
            fut_df = pd.DataFrame(fut_data, columns=['trade_date', f'{symbol.lower()}_close'])
            fut_df = fut_df.set_index('trade_date')
            df = df.join(fut_df, how='left')

        # Calculate returns for return-based correlations
        df['zl_ret'] = df['zl_close'].pct_change()
        df['wti_ret'] = df['wti'].pct_change()
        df['ho_ret'] = df['ho_close'].pct_change()
        df['rb_ret'] = df['rb_close'].pct_change()
        df['ng_ret'] = df['ng_close'].pct_change()
        df['hg_ret'] = df['hg_close'].pct_change()
        df['gc_ret'] = df['gc_close'].pct_change()

        # 30-day rolling correlations
        # Return-based correlations (more meaningful for price instruments)
        df['wti_zl_corr_30d'] = df['zl_ret'].rolling(30).corr(df['wti_ret'])
        df['ho_zl_corr_30d'] = df['zl_ret'].rolling(30).corr(df['ho_ret'])
        df['rb_zl_corr_30d'] = df['zl_ret'].rolling(30).corr(df['rb_ret'])
        df['ng_zl_corr_30d'] = df['zl_ret'].rolling(30).corr(df['ng_ret'])
        df['hg_zl_corr_30d'] = df['zl_ret'].rolling(30).corr(df['hg_ret'])
        df['gc_zl_corr_30d'] = df['zl_ret'].rolling(30).corr(df['gc_ret'])

        # Level-based correlations (for rates/vol indicators)
        df['vix_zl_corr_30d'] = df['zl_close'].rolling(30).corr(df['vix'])
        df['dgs10_zl_corr_30d'] = df['zl_close'].rolling(30).corr(df['dgs10'])
        df['dgs2_zl_corr_30d'] = df['zl_close'].rolling(30).corr(df['dgs2'])

        # Batch update all correlations
        corr_cols = [
            'wti_zl_corr_30d', 'vix_zl_corr_30d',
            'ho_zl_corr_30d', 'rb_zl_corr_30d', 'ng_zl_corr_30d',
            'hg_zl_corr_30d', 'gc_zl_corr_30d',
            'dgs10_zl_corr_30d', 'dgs2_zl_corr_30d'
        ]

        update_count = 0
        for idx, row in df.iterrows():
            # Build SET clause for non-null values
            set_parts = []
            values = []
            for col in corr_cols:
                if pd.notna(row.get(col)):
                    set_parts.append(f"{col} = %s")
                    values.append(float(row[col]))

            if set_parts:
                values.append(idx)
                cur.execute(f"""
                    UPDATE training.matrix_1d
                    SET {', '.join(set_parts)}
                    WHERE trade_date = %s
                """, values)
                if cur.rowcount > 0:
                    update_count += 1

        conn.commit()
        print(f"  Updated {update_count:,} rows with correlation data")

    print("\n" + "=" * 70)
    print("STEP 6: VERIFY FEATURE COVERAGE")
    print("=" * 70)

    if dry_run:
        print("  [DRY RUN] Would verify feature coverage after adding columns")
        return

    # Get existing columns
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'training' AND table_name = 'matrix_1d'
    """)
    existing_cols = {r[0] for r in cur.fetchall()}

    feature_cols = [
        # Core crush/spread features
        'zs_close', 'zm_close', 'crush_spread', 'oil_share',
        'biodiesel_margin', 'cpo_close', 'palm_soy_spread',
        'rs_close', 'zl_canola_spread',
        # Trump effect features
        'trump_total_actions_7d', 'trump_total_actions_30d',
        'trump_avg_sentiment_7d', 'trump_avg_sentiment_30d',
        'trump_action_velocity', 'trump_weighted_action_score',
        # Correlations
        'wti_zl_corr_30d', 'vix_zl_corr_30d',
        'ho_zl_corr_30d', 'rb_zl_corr_30d', 'ng_zl_corr_30d',
        'hg_zl_corr_30d', 'gc_zl_corr_30d',
        'dgs10_zl_corr_30d', 'dgs2_zl_corr_30d',
    ]

    cur.execute("SELECT COUNT(*) FROM training.matrix_1d")
    total = cur.fetchone()[0]

    print(f"Total rows: {total:,}")
    print(f"\nFeature coverage:")

    for col in feature_cols:
        if col in existing_cols:
            cur.execute(f"SELECT COUNT({col}) FROM training.matrix_1d WHERE {col} IS NOT NULL")
            count = cur.fetchone()[0]
            pct = (count / total * 100) if total > 0 else 0
            print(f"  {col:25s}: {count:6,} ({pct:5.1f}%)")
        else:
            print(f"  {col:25s}: COLUMN MISSING")


def main():
    parser = argparse.ArgumentParser(description="Add calculated features to matrix")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--execute", action="store_true", help="Execute the changes")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("ERROR: Must specify either --dry-run or --execute")
        sys.exit(1)

    dry_run = args.dry_run

    print("=" * 70)
    print("ZINC-FUSION-V15: ADD CALCULATED FEATURES TO MATRIX")
    print("=" * 70)
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print(f"Time: {datetime.now()}")

    conn = get_connection()

    try:
        compute_features(conn, dry_run)

        print("\n" + "=" * 70)
        if dry_run:
            print("DRY RUN COMPLETE - No changes made")
        else:
            print("✅ ALL FEATURES ADDED SUCCESSFULLY")
        print("=" * 70)

    except Exception as e:
        conn.rollback()
        print(f"\n❌ ERROR: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
