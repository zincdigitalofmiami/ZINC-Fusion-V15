#!/usr/bin/env python3
"""
Post-drop verification for features.elite_1d -> mkt.futures_1d migration.

Run after applying migration 20260210_drop_elite_1d to confirm:
  1. features.elite_1d is gone
  2. mkt.futures_1d has all indicator columns with data
  3. No SQL references to features.elite_1d remain in codebase

Usage:
    python scripts/verify_elite_1d_drop.py
"""

import os
import subprocess
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Columns that training depends on (must exist in mkt.futures_1d)
REQUIRED_INDICATOR_COLS = [
    "returns_1d",
    "rsi_14",
    "macd",
    "atr_ratio",
    "volume_zscore",
    "bb_percent_b",
    "hurst_exponent",
    "hurst_regime",
    "connors_rsi",
    "fisher_transform",
    "fisher_signal",
    "mcginley_dynamic",
    "ttm_squeeze_on",
    "ttm_squeeze_momentum",
    "schaff_trend_cycle",
    "rvi",
    "rvi_signal",
    "elder_force_index",
    "kama_10",
    "hma_20",
    "alma_50",
    "rsi_2",
    "cumulative_rsi",
    "macd_signal",
    "macd_histogram",
    "cci_14",
    "cci_50",
    "atr_10",
    "atr_50",
    "garman_klass_vol",
    "yang_zhang_vol",
    "cmf_21",
    "unusual_volume",
    "log_returns_1d",
    "range_pct",
]

# Training symbols that must have indicator coverage
TRAINING_SYMBOLS = ["ZL", "ZS", "ZM", "CL", "HO", "RB"]


def main():
    all_pass = True

    print("=" * 70)
    print("POST-DROP VERIFICATION: features.elite_1d -> mkt.futures_1d")
    print("=" * 70)

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    print("Database connected\n")

    # ── Check 1: features.elite_1d is gone ──
    print("CHECK 1: features.elite_1d table is dropped")
    cur.execute("SELECT to_regclass('features.elite_1d')")
    result = cur.fetchone()[0]
    if result is None:
        print("  PASS - to_regclass('features.elite_1d') IS NULL\n")
    else:
        print(f"  FAIL - table still exists: {result}\n")
        all_pass = False

    # ── Check 2: mkt.futures_1d has all required indicator columns ──
    print("CHECK 2: mkt.futures_1d has all required indicator columns")
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'mkt' AND table_name = 'futures_1d'
    """)
    existing_cols = {r[0] for r in cur.fetchall()}

    missing_cols = []
    for col in REQUIRED_INDICATOR_COLS:
        if col not in existing_cols:
            missing_cols.append(col)

    if not missing_cols:
        print(f"  PASS - all {len(REQUIRED_INDICATOR_COLS)} indicator columns present\n")
    else:
        print(f"  FAIL - missing columns: {missing_cols}\n")
        all_pass = False

    # ── Check 3: Indicator data populated for training symbols ──
    print("CHECK 3: Indicator data populated for training symbols")
    key_cols = ["rsi_14", "macd", "hurst_exponent", "volume_zscore", "bb_percent_b"]
    print(f"  {'Symbol':<8}", end="")
    for col in key_cols:
        print(f"  {col:>16}", end="")
    print()
    print("  " + "-" * 92)

    for symbol in TRAINING_SYMBOLS:
        print(f"  {symbol:<8}", end="")
        for col in key_cols:
            cur.execute(
                f"SELECT COUNT({col}) FROM mkt.futures_1d WHERE symbol = %s",
                (symbol,),
            )
            count = cur.fetchone()[0]
            status = "ok" if count > 0 else "EMPTY"
            print(f"  {count:>12} {status:>3}", end="")
            if count == 0:
                all_pass = False
        print()
    print()

    # ── Check 4: Row/date coverage parity by symbol ──
    print("CHECK 4: Row counts per training symbol in mkt.futures_1d")
    for symbol in TRAINING_SYMBOLS:
        cur.execute(
            """
            SELECT COUNT(*), MIN(event_date)::date, MAX(event_date)::date
            FROM mkt.futures_1d WHERE symbol = %s
            """,
            (symbol,),
        )
        count, min_d, max_d = cur.fetchone()
        print(f"  {symbol}: {count:,} rows  ({min_d} to {max_d})")
    print()

    # ── Check 5: No SQL references in active codebase ──
    print("CHECK 5: No SQL references to features.elite_1d in active code")
    try:
        result = subprocess.run(
            [
                "grep",
                "-r",
                "--include=*.py",
                "--include=*.ts",
                "--include=*.js",
                "--include=*.sql",
                "-l",
                "features.elite_1d",
                "src/",
                "frontend/",
                "scripts/sync_cloud_to_local.py",
                "scripts/calculate_zl_correlations.py",
            ],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        if result.stdout.strip():
            print(f"  FAIL - references found in:\n{result.stdout}")
            all_pass = False
        else:
            print("  PASS - no references in active code\n")
    except FileNotFoundError:
        print("  SKIP - grep not available\n")

    # ── Summary ──
    print("=" * 70)
    if all_pass:
        print("ALL CHECKS PASSED - features.elite_1d migration verified")
    else:
        print("SOME CHECKS FAILED - review output above")
    print("=" * 70)

    cur.close()
    conn.close()
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
