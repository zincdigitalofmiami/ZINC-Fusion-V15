#!/usr/bin/env python3
"""
Test 1: Database State Audit

Audits current database state for Databento live integration:
- Source distribution (databento vs databento_live vs yahoo)
- Price distribution analysis (detect discontinuities)
- Date coverage gaps
- Volume/OI consistency
- Roll date analysis (detect price jumps >5% on same day)
"""


from __future__ import annotations

__test__ = False  # Pytest should not collect integration scripts.

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pandas as pd
from fusion.db import get_read_engine


def run_query(engine, query: str) -> pd.DataFrame:
    """Run SQL query and return DataFrame."""
    return pd.read_sql(query, engine)


def audit_source_distribution(engine) -> Dict[str, Any]:
    """Check source tag distribution across all ZL price tables."""
    results = {}
    
    for table in ["zl_price_15m", "zl_price_1h", "zl_price_1d"]:
        query = f"""
        SELECT 
            source, 
            COUNT(*) as count, 
            MIN(timestamp) as min_ts, 
            MAX(timestamp) as max_ts
        FROM analytics.{table}
        GROUP BY source
        ORDER BY count DESC
        """
        df = run_query(engine, query)
        results[table] = df.to_dict("records")
    
    return results


def detect_price_discontinuities(engine, days: int = 7) -> List[Dict[str, Any]]:
    """Detect price jumps >5% between consecutive bars."""
    query = f"""
    SELECT 
        timestamp,
        close,
        LAG(close) OVER (ORDER BY timestamp) as prev_close,
        ABS(close - LAG(close) OVER (ORDER BY timestamp)) / LAG(close) OVER (ORDER BY timestamp) * 100 as pct_change,
        source
    FROM analytics.zl_price_15m
    WHERE timestamp >= NOW() - INTERVAL '{days} days'
    ORDER BY ABS(close - LAG(close) OVER (ORDER BY timestamp)) / NULLIF(LAG(close) OVER (ORDER BY timestamp), 0) DESC NULLS LAST
    LIMIT 20
    """
    df = run_query(engine, query)
    
    # Filter for jumps >5%
    discontinuities = df[df["pct_change"] > 5.0].to_dict("records")
    return discontinuities


def check_volume_consistency(engine, days: int = 7) -> Dict[str, Any]:
    """Check volume consistency per day."""
    query = f"""
    SELECT 
        DATE_TRUNC('day', timestamp) as day,
        COUNT(*) as bars_per_day,
        SUM(volume) as total_volume,
        AVG(volume) as avg_volume,
        MIN(volume) as min_volume,
        MAX(volume) as max_volume
    FROM analytics.zl_price_15m
    WHERE timestamp >= NOW() - INTERVAL '{days} days'
    GROUP BY DATE_TRUNC('day', timestamp)
    ORDER BY day DESC
    """
    df = run_query(engine, query)
    return df.to_dict("records")


def check_date_coverage(engine) -> Dict[str, Any]:
    """Check for gaps in date coverage."""
    results = {}
    
    for table, ts_col in [("zl_price_15m", "timestamp"), ("zl_price_1h", "timestamp"), ("zl_price_1d", "event_date")]:
        query = f"""
        SELECT 
            {ts_col} as ts,
            LAG({ts_col}) OVER (ORDER BY {ts_col}) as prev_ts,
            {ts_col} - LAG({ts_col}) OVER (ORDER BY {ts_col}) as gap
        FROM analytics.{table}
        ORDER BY {ts_col} DESC
        LIMIT 1000
        """
        df = run_query(engine, query)
        
        # Find gaps > expected interval
        if table == "zl_price_15m":
            expected_gap = timedelta(minutes=15)
        elif table == "zl_price_1h":
            expected_gap = timedelta(hours=1)
        else:
            expected_gap = timedelta(days=1)
        
        gaps = df[df["gap"] > expected_gap * 2].to_dict("records")
        results[table] = {
            "total_rows": len(df),
            "gaps": gaps[:10],  # Top 10 gaps
            "latest": df["ts"].max().isoformat() if len(df) > 0 else None,
            "earliest": df["ts"].min().isoformat() if len(df) > 0 else None,
        }
    
    return results


def analyze_roll_dates(engine, days: int = 90) -> List[Dict[str, Any]]:
    """Detect potential roll dates (price jumps >5% on same day)."""
    query = f"""
    WITH daily_stats AS (
        SELECT 
            DATE_TRUNC('day', timestamp) as day,
            MIN(close) as day_low,
            MAX(close) as day_high,
            FIRST_VALUE(close) OVER (PARTITION BY DATE_TRUNC('day', timestamp) ORDER BY timestamp) as day_open,
            LAST_VALUE(close) OVER (PARTITION BY DATE_TRUNC('day', timestamp) ORDER BY timestamp ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as day_close,
            COUNT(*) as bar_count
        FROM analytics.zl_price_15m
        WHERE timestamp >= NOW() - INTERVAL '{days} days'
        GROUP BY DATE_TRUNC('day', timestamp)
    )
    SELECT 
        day,
        day_open,
        day_close,
        day_high,
        day_low,
        ABS(day_close - day_open) / NULLIF(day_open, 0) * 100 as intraday_pct_change,
        bar_count
    FROM daily_stats
    WHERE ABS(day_close - day_open) / NULLIF(day_open, 0) * 100 > 5.0
    ORDER BY ABS(day_close - day_open) / NULLIF(day_open, 0) DESC
    """
    df = run_query(engine, query)
    return df.to_dict("records")


def check_symbol_metadata(engine) -> Dict[str, Any]:
    """Check if we can determine what symbol was used for existing data."""
    # Check if there's any metadata table or source tags that indicate symbol
    query = """
    SELECT DISTINCT source
    FROM analytics.zl_price_15m
    ORDER BY source
    """
    df = run_query(engine, query)
    
    # Check latest data timestamps
    query2 = """
    SELECT 
        source,
        COUNT(*) as count,
        MIN(timestamp) as earliest,
        MAX(timestamp) as latest
    FROM analytics.zl_price_15m
    GROUP BY source
    ORDER BY latest DESC
    """
    df2 = run_query(engine, query2)
    
    return {
        "sources": df["source"].tolist() if len(df) > 0 else [],
        "source_stats": df2.to_dict("records"),
    }


def main():
    """Run all audit checks and generate report."""
    engine = get_read_engine()
    
    print("=" * 80)
    print("Databento Current State Audit")
    print("=" * 80)
    print()
    
    results = {}
    
    # 1. Source distribution
    print("1. Checking source distribution...")
    results["source_distribution"] = audit_source_distribution(engine)
    for table, data in results["source_distribution"].items():
        print(f"   {table}:")
        for row in data:
            print(f"     {row['source']}: {row['count']} rows ({row['min_ts']} to {row['max_ts']})")
    print()
    
    # 2. Symbol metadata
    print("2. Checking symbol metadata...")
    results["symbol_metadata"] = check_symbol_metadata(engine)
    print(f"   Sources found: {results['symbol_metadata']['sources']}")
    print()
    
    # 3. Price discontinuities
    print("3. Detecting price discontinuities (last 7 days)...")
    discontinuities = detect_price_discontinuities(engine, days=7)
    results["price_discontinuities"] = discontinuities
    if discontinuities:
        print(f"   Found {len(discontinuities)} discontinuities >5%:")
        for disc in discontinuities[:5]:
            print(f"     {disc['timestamp']}: {disc['pct_change']:.2f}% change ({disc['prev_close']:.2f} -> {disc['close']:.2f})")
    else:
        print("   No major discontinuities found")
    print()
    
    # 4. Volume consistency
    print("4. Checking volume consistency (last 7 days)...")
    volume_stats = check_volume_consistency(engine, days=7)
    results["volume_consistency"] = volume_stats
    if volume_stats:
        print(f"   Analyzed {len(volume_stats)} days")
        for day in volume_stats[:3]:
            print(f"     {day['day']}: {day['bars_per_day']} bars, {day['total_volume']:.0f} total volume")
    print()
    
    # 5. Date coverage
    print("5. Checking date coverage gaps...")
    coverage = check_date_coverage(engine)
    results["date_coverage"] = coverage
    for table, data in coverage.items():
        print(f"   {table}:")
        print(f"     Total rows: {data['total_rows']}")
        print(f"     Latest: {data['latest']}")
        print(f"     Earliest: {data['earliest']}")
        if data["gaps"]:
            print(f"     Found {len(data['gaps'])} gaps")
        else:
            print("     No significant gaps found")
    print()
    
    # 6. Roll date analysis
    print("6. Analyzing roll dates (last 90 days)...")
    roll_dates = analyze_roll_dates(engine, days=90)
    results["roll_dates"] = roll_dates
    if roll_dates:
        print(f"   Found {len(roll_dates)} days with >5% intraday change:")
        for roll in roll_dates[:5]:
            print(f"     {roll['day']}: {roll['intraday_pct_change']:.2f}% change ({roll['day_open']:.2f} -> {roll['day_close']:.2f})")
    else:
        print("   No significant roll date patterns detected")
    print()
    
    # Save results
    output_file = "test_results_current_state.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved to {output_file}")
    
    # Summary
    print()
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"✓ Source distribution analyzed")
    print(f"✓ Price discontinuities: {len(discontinuities)} found")
    print(f"✓ Volume consistency: {len(volume_stats)} days analyzed")
    print(f"✓ Date coverage: {len(coverage)} tables checked")
    print(f"✓ Roll dates: {len(roll_dates)} potential roll dates")
    print()
    print("Next steps:")
    print("1. Review test_results_current_state.json for details")
    print("2. Run test_databento_symbol_comparison.py to compare ZL.c.0 vs ZL.n.0")


if __name__ == "__main__":
    main()
