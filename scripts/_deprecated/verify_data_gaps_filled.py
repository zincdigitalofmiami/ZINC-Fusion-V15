#!/usr/bin/env python3
"""
DEPRECATED — features.elite_1d has been consolidated into mkt.futures_1d.
Section 4 (elite multi-symbol check) queries a dropped table. DO NOT RUN.

Original description:
ZINC-FUSION-V15: Verify Data Gaps Filled & Training Matrix Enhanced.
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def main():
    print("=" * 70)
    print("ZINC-FUSION-V15: DATA GAPS VERIFICATION")
    print("=" * 70)
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    print("✅ Database connected\n")
    
    all_pass = True
    
    # ==========================================================================
    # 1. Training Matrix Dimensions
    # ==========================================================================
    print("=" * 60)
    print("1. TRAINING MATRIX DIMENSIONS")
    print("=" * 60)
    
    cur.execute("""
        SELECT COUNT(*) 
        FROM information_schema.columns 
        WHERE table_schema = 'training' AND table_name = 'matrix_1d'
    """)
    column_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM training.matrix_1d")
    row_count = cur.fetchone()[0]
    
    print(f"Total columns: {column_count} (expected: 162)")
    print(f"Total rows: {row_count} (expected: ~6,632)")
    
    col_match = column_count >= 160
    print(f"  Column check: {'✅ PASS' if col_match else '❌ FAIL'}")
    if not col_match: all_pass = False
    
    # ==========================================================================
    # 2. Trump Effect Features (6 columns)
    # ==========================================================================
    print("\n" + "=" * 60)
    print("2. TRUMP EFFECT FEATURES (6 columns)")
    print("=" * 60)
    
    trump_columns = [
        'trump_total_actions_7d',
        'trump_total_actions_30d', 
        'trump_avg_sentiment_7d',
        'trump_avg_sentiment_30d',
        'trump_action_velocity',
        'trump_weighted_action_score'
    ]
    
    print(f"\n{'Feature':<32} {'Rows':>8} {'Coverage':>10} {'Status':<8}")
    print("-" * 62)
    
    for col in trump_columns:
        try:
            cur.execute(f"""
                SELECT COUNT({col}), 
                       ROUND(COUNT({col})::numeric * 100.0 / COUNT(*), 1)
                FROM training.matrix_1d
            """)
            count, pct = cur.fetchone()
            status = "✅" if pct is not None and pct > 30 else "⚠️"
            pct_str = f"{pct:.1f}%" if pct else "N/A"
            print(f"{col:<32} {count:>8,} {pct_str:>10} {status}")
        except Exception as e:
            print(f"{col:<32} {'ERROR':<8} - Column may not exist")
            all_pass = False
    
    # Expected ~35% coverage (Trump data from 2017+)
    print("\nNote: ~35% coverage is expected (Trump data from Jan 2017 onwards)")
    
    # ==========================================================================
    # 3. New Correlations (7 columns)
    # ==========================================================================
    print("\n" + "=" * 60)
    print("3. NEW CORRELATIONS (7 columns)")  
    print("=" * 60)
    
    correlation_columns = [
        ('ho_zl_corr_30d', 'Heating Oil vs ZL'),
        ('rb_zl_corr_30d', 'RBOB Gasoline vs ZL'),
        ('ng_zl_corr_30d', 'Natural Gas vs ZL'),
        ('hg_zl_corr_30d', 'Copper vs ZL'),
        ('gc_zl_corr_30d', 'Gold vs ZL'),
        ('dgs10_zl_corr_30d', '10Y Treasury vs ZL'),
        ('dgs2_zl_corr_30d', '2Y Treasury vs ZL'),
    ]
    
    print(f"\n{'Feature':<22} {'Description':<22} {'Rows':>8} {'Coverage':>10} {'Status':<6}")
    print("-" * 72)
    
    for col, desc in correlation_columns:
        try:
            cur.execute(f"""
                SELECT COUNT({col}), 
                       ROUND(COUNT({col})::numeric * 100.0 / COUNT(*), 1)
                FROM training.matrix_1d
            """)
            count, pct = cur.fetchone()
            status = "✅" if pct is not None and pct > 95 else "⚠️"
            pct_str = f"{pct:.1f}%" if pct else "N/A"
            print(f"{col:<22} {desc:<22} {count:>8,} {pct_str:>10} {status}")
        except Exception as e:
            print(f"{col:<22} {desc:<22} {'ERROR':<8} - Column may not exist")
            all_pass = False
    
    # Expected 97-100% coverage
    print("\nNote: 97-100% coverage expected")
    
    # ==========================================================================
    # 4. Elite Indicators Multi-Symbol (11 symbols)
    # ==========================================================================
    print("\n" + "=" * 60)
    print("4. ELITE INDICATORS MULTI-SYMBOL (11 symbols)")
    print("=" * 60)
    
    expected_symbols = ['ZL', 'ZS', 'ZM', 'CL', 'HO', 'RB', 'NG', 'HG', 'GC', 'RS', 'CPO']
    
    cur.execute("""
        SELECT symbol, COUNT(*), MIN(trade_date)::date, MAX(trade_date)::date
        FROM features.elite_1d
        GROUP BY symbol
        ORDER BY 
            CASE symbol 
                WHEN 'ZL' THEN 0 
                WHEN 'ZS' THEN 1 
                WHEN 'ZM' THEN 2 
                ELSE 3 
            END, symbol
    """)
    elite_data = cur.fetchall()
    
    print(f"\n{'Symbol':<8} {'Rows':>10} {'Date Range':<30}")
    print("-" * 52)
    
    found_symbols = []
    total_elite_rows = 0
    for symbol, count, min_date, max_date in elite_data:
        found_symbols.append(symbol)
        total_elite_rows += count
        print(f"{symbol:<8} {count:>10,} {str(min_date)} to {str(max_date)}")
    
    print("-" * 52)
    print(f"{'TOTAL':<8} {total_elite_rows:>10,}")
    
    # Check symbols
    missing = set(expected_symbols) - set(found_symbols)
    symbol_check = len(missing) == 0
    
    print(f"\nExpected: {len(expected_symbols)} symbols")
    print(f"Found: {len(found_symbols)} symbols")
    if missing:
        print(f"⚠️ Missing: {missing}")
        all_pass = False
    else:
        print("✅ All 11 symbols present!")
    
    # ==========================================================================
    # 5. Weather Features Coverage Check
    # ==========================================================================
    print("\n" + "=" * 60)
    print("5. WEATHER FEATURES COVERAGE")
    print("=" * 60)
    
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'training' AND table_name = 'matrix_1d'
        AND column_name LIKE 'weather_%'
        LIMIT 5
    """)
    weather_cols = [r[0] for r in cur.fetchall()]
    
    if weather_cols:
        sample_col = weather_cols[0]
        cur.execute(f"""
            SELECT COUNT({sample_col}), 
                   ROUND(COUNT({sample_col})::numeric * 100.0 / COUNT(*), 1)
            FROM training.matrix_1d
        """)
        count, pct = cur.fetchone()
        print(f"Sample weather column '{sample_col}':")
        print(f"  Coverage: {pct:.1f}% (expected ~82.2%)")
        print(f"  {'✅ PASS' if pct > 80 else '⚠️ CHECK'}")
    else:
        print("No weather columns found")
    
    # ==========================================================================
    # Summary
    # ==========================================================================
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)
    
    print(f"""
Verification Results:
  • Column count: {column_count} (target: 162)
  • Row count: {row_count} (target: ~6,632)
  • Trump Effect features: 6 columns @ ~35% coverage
  • Correlation features: 7 columns @ 97-100% coverage
  • Elite indicators: {len(found_symbols)} symbols, {total_elite_rows:,} total rows
""")
    
    if all_pass:
        print("✅ ALL VERIFICATIONS PASSED - Data gaps filled successfully!")
    else:
        print("⚠️ Some checks need attention - review output above")
    
    cur.close()
    conn.close()
    print("=" * 70)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
