#!/usr/bin/env python3
"""
Run Databento audit queries and generate report.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

import pandas as pd
from fusion.db import get_read_engine


def run_query(engine, query: str, description: str) -> Dict:
    """Run a query and return results."""
    try:
        df = pd.read_sql(query, engine)
        return {
            "description": description,
            "success": True,
            "row_count": len(df),
            "columns": list(df.columns),
            "data": df.to_dict("records")[:100],  # Limit to 100 rows
            "summary": df.describe().to_dict() if len(df) > 0 else {}
        }
    except Exception as e:
        return {
            "description": description,
            "success": False,
            "error": str(e),
            "query": query[:200]  # First 200 chars of query
        }


def main():
    """Run all audit queries."""
    print("=" * 80)
    print("Databento Integration - Comprehensive Audit")
    print("=" * 80)
    print(f"Started: {datetime.now().isoformat()}")
    print()
    
    try:
        engine = get_read_engine()
    except Exception as e:
        print(f"ERROR: Could not connect to database: {e}")
        print("\nPlease ensure DATABASE_URL is set in environment.")
        sys.exit(1)
    
    results = {}
    
    # 1. Source Distribution
    print("1. Checking source distribution...")
    results["source_distribution_15m"] = run_query(
        engine,
        """
        SELECT 
            source, 
            COUNT(*) as count, 
            MIN(timestamp) as min_ts, 
            MAX(timestamp) as max_ts
        FROM analytics.zl_price_15m
        GROUP BY source
        ORDER BY count DESC
        """,
        "Source distribution in zl_price_15m"
    )
    
    results["source_distribution_1h"] = run_query(
        engine,
        """
        SELECT 
            source, 
            COUNT(*) as count, 
            MIN(timestamp) as min_ts, 
            MAX(timestamp) as max_ts
        FROM analytics.zl_price_1h
        GROUP BY source
        ORDER BY count DESC
        """,
        "Source distribution in zl_price_1h"
    )
    
    results["source_distribution_1d"] = run_query(
        engine,
        """
        SELECT 
            source, 
            COUNT(*) as count, 
            MIN(event_date) as min_date, 
            MAX(event_date) as max_date
        FROM analytics.zl_price_1d
        GROUP BY source
        ORDER BY count DESC
        """,
        "Source distribution in zl_price_1d"
    )
    
    # 2. Price Discontinuities
    print("2. Checking price discontinuities...")
    results["price_discontinuities_15m"] = run_query(
        engine,
        """
        SELECT 
            timestamp,
            close,
            LAG(close) OVER (ORDER BY timestamp) as prev_close,
            ABS(close - LAG(close) OVER (ORDER BY timestamp)) / NULLIF(LAG(close) OVER (ORDER BY timestamp), 0) * 100 as pct_change,
            source
        FROM analytics.zl_price_15m
        WHERE timestamp >= NOW() - INTERVAL '7 days'
        ORDER BY ABS(close - LAG(close) OVER (ORDER BY timestamp)) / NULLIF(LAG(close) OVER (ORDER BY timestamp), 0) DESC NULLS LAST
        LIMIT 20
        """,
        "Price discontinuities in zl_price_15m (last 7 days)"
    )
    
    results["price_discontinuities_1d"] = run_query(
        engine,
        """
        SELECT 
            event_date,
            open,
            close,
            ABS(close - open) / NULLIF(open, 0) * 100 as intraday_pct_change,
            source
        FROM analytics.zl_price_1d
        WHERE event_date >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY ABS(close - open) / NULLIF(open, 0) DESC NULLS LAST
        LIMIT 20
        """,
        "Price discontinuities in zl_price_1d (last 30 days)"
    )
    
    # 3. Symbol Usage Check
    print("3. Checking symbol usage in mkt.futures_1d...")
    results["symbol_usage"] = run_query(
        engine,
        """
        SELECT 
            source,
            COUNT(*) as count,
            COUNT(*) FILTER (WHERE open_interest IS NOT NULL) as with_oi,
            MIN(event_date) as earliest,
            MAX(event_date) as latest
        FROM mkt.futures_1d
        WHERE symbol = 'ZL'
        GROUP BY source
        ORDER BY count DESC
        """,
        "ZL symbol usage in mkt.futures_1d"
    )
    
    # 4. Data Coverage Gaps
    print("4. Checking data coverage gaps...")
    results["coverage_gaps_15m"] = run_query(
        engine,
        """
        WITH gaps AS (
            SELECT 
                timestamp,
                LAG(timestamp) OVER (ORDER BY timestamp) as prev_ts,
                timestamp - LAG(timestamp) OVER (ORDER BY timestamp) as gap
            FROM analytics.zl_price_15m
            WHERE timestamp >= NOW() - INTERVAL '7 days'
            ORDER BY timestamp DESC
        )
        SELECT 
            prev_ts as gap_start,
            timestamp as gap_end,
            gap,
            EXTRACT(EPOCH FROM gap) / 60 as gap_minutes
        FROM gaps
        WHERE gap > INTERVAL '30 minutes'
        LIMIT 20
        """,
        "Coverage gaps in zl_price_15m (>30 min)"
    )
    
    results["coverage_gaps_1d"] = run_query(
        engine,
        """
        WITH date_series AS (
            SELECT generate_series(
                CURRENT_DATE - INTERVAL '30 days',
                CURRENT_DATE - INTERVAL '1 day',
                '1 day'::interval
            )::date AS day
        )
        SELECT ds.day as missing_date
        FROM date_series ds
        LEFT JOIN analytics.zl_price_1d z ON ds.day = z.event_date
        WHERE z.event_date IS NULL
          AND EXTRACT(DOW FROM ds.day) NOT IN (0, 6)
        ORDER BY ds.day DESC
        """,
        "Missing dates in zl_price_1d (last 30 days)"
    )
    
    # 5. Source Conflicts
    print("5. Checking source conflicts...")
    results["source_conflicts_15m"] = run_query(
        engine,
        """
        SELECT 
            timestamp,
            array_agg(DISTINCT source) as sources,
            COUNT(*) as count
        FROM analytics.zl_price_15m
        WHERE timestamp >= NOW() - INTERVAL '7 days'
        GROUP BY timestamp
        HAVING COUNT(DISTINCT source) > 1
        ORDER BY timestamp DESC
        LIMIT 20
        """,
        "Source conflicts in zl_price_15m (same timestamp, different sources)"
    )
    
    results["source_conflicts_1d"] = run_query(
        engine,
        """
        SELECT 
            event_date,
            array_agg(DISTINCT source) as sources,
            COUNT(*) as count
        FROM analytics.zl_price_1d
        WHERE event_date >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY event_date
        HAVING COUNT(DISTINCT source) > 1
        ORDER BY event_date DESC
        LIMIT 20
        """,
        "Source conflicts in zl_price_1d (same date, different sources)"
    )
    
    # 6. Volume Consistency
    print("6. Checking volume consistency...")
    results["volume_consistency"] = run_query(
        engine,
        """
        SELECT 
            DATE_TRUNC('day', timestamp) as day,
            COUNT(*) as bars_per_day,
            SUM(volume) as total_volume,
            AVG(volume) as avg_volume,
            MIN(volume) as min_volume,
            MAX(volume) as max_volume,
            source
        FROM analytics.zl_price_15m
        WHERE timestamp >= NOW() - INTERVAL '7 days'
        GROUP BY DATE_TRUNC('day', timestamp), source
        ORDER BY day DESC, source
        """,
        "Volume consistency per day in zl_price_15m"
    )
    
    # 7. Recent Data Check
    print("7. Checking recent data freshness...")
    results["data_freshness"] = run_query(
        engine,
        """
        SELECT 
            '15m' as interval_type,
            MAX(timestamp) as latest_timestamp,
            EXTRACT(EPOCH FROM (NOW() - MAX(timestamp))) / 3600 as age_hours,
            source
        FROM analytics.zl_price_15m
        GROUP BY source
        UNION ALL
        SELECT 
            '1h' as interval_type,
            MAX(timestamp) as latest_timestamp,
            EXTRACT(EPOCH FROM (NOW() - MAX(timestamp))) / 3600 as age_hours,
            source
        FROM analytics.zl_price_1h
        GROUP BY source
        UNION ALL
        SELECT 
            '1d' as interval_type,
            MAX(event_date)::timestamptz as latest_timestamp,
            EXTRACT(EPOCH FROM (NOW() - MAX(event_date)::timestamptz)) / 86400 as age_hours,
            source
        FROM analytics.zl_price_1d
        GROUP BY source
        ORDER BY interval_type, source
        """,
        "Data freshness by source and interval"
    )
    
    # 8. Data Quality Check
    print("8. Checking data quality...")
    results["data_quality_15m"] = run_query(
        engine,
        """
        SELECT 
            COUNT(*) FILTER (WHERE close IS NULL) as null_closes,
            COUNT(*) FILTER (WHERE open IS NULL) as null_opens,
            COUNT(*) FILTER (WHERE high IS NULL) as null_highs,
            COUNT(*) FILTER (WHERE low IS NULL) as null_lows,
            COUNT(*) FILTER (WHERE close <= 0) as invalid_closes,
            COUNT(*) FILTER (WHERE high < low) as invalid_ohlc,
            COUNT(*) as total_rows
        FROM analytics.zl_price_15m
        WHERE timestamp >= NOW() - INTERVAL '7 days'
        """,
        "Data quality issues in zl_price_15m"
    )
    
    # 9. Summary
    print("9. Generating summary...")
    results["summary"] = run_query(
        engine,
        """
        SELECT 
            (SELECT COUNT(*) FROM analytics.zl_price_15m WHERE timestamp >= NOW() - INTERVAL '7 days') as zl_15m_last_7d,
            (SELECT COUNT(*) FROM analytics.zl_price_1h WHERE timestamp >= NOW() - INTERVAL '7 days') as zl_1h_last_7d,
            (SELECT COUNT(*) FROM analytics.zl_price_1d WHERE event_date >= CURRENT_DATE - INTERVAL '30 days') as zl_1d_last_30d,
            (SELECT COUNT(DISTINCT source) FROM analytics.zl_price_15m) as unique_sources_15m,
            (SELECT COUNT(DISTINCT source) FROM analytics.zl_price_1h) as unique_sources_1h,
            (SELECT COUNT(DISTINCT source) FROM analytics.zl_price_1d) as unique_sources_1d,
            (SELECT MAX(timestamp) FROM analytics.zl_price_15m) as latest_15m,
            (SELECT MAX(timestamp) FROM analytics.zl_price_1h) as latest_1h,
            (SELECT MAX(event_date) FROM analytics.zl_price_1d) as latest_1d
        """,
        "Overall summary statistics"
    )
    
    # Save results
    output_file = "audit_results_databento.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    # Print summary
    print()
    print("=" * 80)
    print("Audit Summary")
    print("=" * 80)
    
    for key, result in results.items():
        if result.get("success"):
            print(f"✓ {result['description']}: {result['row_count']} rows")
        else:
            print(f"✗ {result['description']}: ERROR - {result.get('error', 'Unknown')}")
    
    print()
    print(f"Full results saved to: {output_file}")
    print()
    print("=" * 80)
    print("Key Findings")
    print("=" * 80)
    
    # Analyze results
    if results.get("source_distribution_15m", {}).get("success"):
        sources = results["source_distribution_15m"]["data"]
        print(f"\n15m Sources: {', '.join([s['source'] or 'NULL' for s in sources])}")
    
    if results.get("source_conflicts_15m", {}).get("success"):
        conflicts = results["source_conflicts_15m"]["row_count"]
        if conflicts > 0:
            print(f"\n⚠️  WARNING: {conflicts} source conflicts found in 15m data")
        else:
            print(f"\n✓ No source conflicts in 15m data")
    
    if results.get("price_discontinuities_15m", {}).get("success"):
        disc = results["price_discontinuities_15m"]["data"]
        large_jumps = [d for d in disc if d.get("pct_change", 0) > 5.0]
        if large_jumps:
            print(f"\n⚠️  WARNING: {len(large_jumps)} price jumps >5% found")
        else:
            print(f"\n✓ No large price discontinuities found")
    
    if results.get("data_freshness", {}).get("success"):
        freshness = results["data_freshness"]["data"]
        print(f"\nData Freshness:")
        for f in freshness:
            age = f.get("age_hours", 0)
            if age > 24:
                print(f"  ⚠️  {f['interval_type']} ({f.get('source', 'unknown')}): {age:.1f} hours old")
            else:
                print(f"  ✓ {f['interval_type']} ({f.get('source', 'unknown')}): {age:.1f} hours old")
    
    print()
    print("Review audit_results_databento.json for detailed findings.")


if __name__ == "__main__":
    main()
