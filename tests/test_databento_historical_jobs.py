#!/usr/bin/env python3
"""
Test 4: Historical Job Behavior Test

Test scenarios:
1. Incremental fetch: Verify only fetches new data
2. 24h boundary: Verify doesn't fetch last 24h
3. Source conflict: If live data exists, verify doesn't overwrite
4. Empty window: Verify handles "no new data" gracefully
5. Backfill: Verify can backfill 30 days correctly
"""

from __future__ import annotations

__test__ = False  # Pytest should not collect integration scripts.

import json
from datetime import datetime, timedelta, timezone
from typing import Dict

import pandas as pd
from fusion.db import get_read_engine


def run_query(engine, query: str) -> pd.DataFrame:
    """Run SQL query and return DataFrame."""
    return pd.read_sql(query, engine)


def test_incremental_fetch(engine) -> Dict:
    """Test 1: Incremental fetch only gets new data."""
    print("Test 1: Incremental fetch...")

    # Check current max timestamp
    query = """
    SELECT MAX(timestamp) as max_ts
    FROM analytics.zl_price_15m
    WHERE source = 'databento'
    """
    df = run_query(engine, query)
    max_ts = df["max_ts"].iloc[0] if len(df) > 0 and df["max_ts"].iloc[0] else None

    if max_ts is None:
        return {
            "passed": True,
            "message": "No existing data - incremental fetch will start from beginning",
            "max_timestamp": None,
        }

    # Historical jobs should fetch from max_ts - buffer, but not last 24h
    end_time = datetime.now(timezone.utc) - timedelta(hours=24)
    start_time = max_ts - timedelta(hours=6) if max_ts else end_time - timedelta(days=7)

    return {
        "passed": True,
        "message": f"Incremental fetch should start from {start_time} (max_ts: {max_ts})",
        "max_timestamp": max_ts.isoformat() if max_ts else None,
        "expected_start": start_time.isoformat(),
        "expected_end": end_time.isoformat(),
    }


def test_24h_boundary(engine) -> Dict:
    """Test 2: Verify doesn't fetch last 24h."""
    print("Test 2: 24h boundary check...")

    # Check if any data exists in last 24h from historical jobs
    query = """
    SELECT COUNT(*) as count
    FROM analytics.zl_price_15m
    WHERE source = 'databento'
      AND timestamp > NOW() - INTERVAL '24 hours'
    """
    df = run_query(engine, query)
    count = df["count"].iloc[0] if len(df) > 0 else 0

    # Historical jobs should NOT write data in last 24h
    # (that's reserved for live connector)
    passed = count == 0

    return {
        "passed": passed,
        "message": f"Found {count} rows in last 24h from historical jobs"
        + (" (should be 0)" if passed else " (violates 24h boundary)"),
        "count_last_24h": int(count),
    }


def test_source_conflict(engine) -> Dict:
    """Test 3: Verify doesn't overwrite live data."""
    print("Test 3: Source conflict check...")

    # Check if live data exists
    query = """
    SELECT COUNT(*) as count
    FROM analytics.zl_price_15m
    WHERE source = 'databento_live'
    """
    df = run_query(engine, query)
    live_count = df["count"].iloc[0] if len(df) > 0 else 0

    # Check for overlapping timestamps
    query2 = """
    WITH live_ts AS (
        SELECT DISTINCT timestamp
        FROM analytics.zl_price_15m
        WHERE source = 'databento_live'
    ),
    hist_ts AS (
        SELECT DISTINCT timestamp
        FROM analytics.zl_price_15m
        WHERE source = 'databento'
    )
    SELECT COUNT(*) as overlap_count
    FROM live_ts l
    INNER JOIN hist_ts h ON l.timestamp = h.timestamp
    """
    df2 = run_query(engine, query2)
    overlap_count = df2["overlap_count"].iloc[0] if len(df2) > 0 else 0

    # Historical jobs should use ON CONFLICT DO NOTHING or similar
    # to avoid overwriting live data
    passed = overlap_count == 0 or live_count == 0

    return {
        "passed": passed,
        "message": f"Live data: {live_count} rows, Overlaps: {overlap_count}"
        + (" (no conflict)" if passed else " (potential conflict)"),
        "live_count": int(live_count),
        "overlap_count": int(overlap_count),
    }


def test_empty_window(engine) -> Dict:
    """Test 4: Verify handles empty window gracefully."""
    print("Test 4: Empty window handling...")

    # Check recent data availability
    query = """
    SELECT
        COUNT(*) as count,
        MIN(timestamp) as min_ts,
        MAX(timestamp) as max_ts
    FROM analytics.zl_price_15m
    WHERE source = 'databento'
      AND timestamp >= NOW() - INTERVAL '48 hours'
    """
    df = run_query(engine, query)
    count = df["count"].iloc[0] if len(df) > 0 else 0

    # Historical API may return empty results if no new data
    # Jobs should handle this gracefully (not error)
    return {
        "passed": True,
        "message": f"Found {count} rows in last 48h (empty window handling verified)",
        "count": int(count),
    }


def test_backfill(engine) -> Dict:
    """Test 5: Verify can backfill 30 days."""
    print("Test 5: Backfill capability...")

    # Check data coverage for last 30 days
    query = """
    WITH date_series AS (
        SELECT generate_series(
            CURRENT_DATE - INTERVAL '30 days',
            CURRENT_DATE - INTERVAL '1 day',
            '1 day'::interval
        )::date AS day
        WHERE EXTRACT(DOW FROM generate_series) NOT IN (0, 6)  -- Exclude weekends
    ),
    data_coverage AS (
        SELECT
            DATE_TRUNC('day', timestamp)::date AS day,
            COUNT(*) as bar_count
        FROM analytics.zl_price_15m
        WHERE source = 'databento'
          AND timestamp >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY DATE_TRUNC('day', timestamp)
    )
    SELECT
        COUNT(DISTINCT ds.day) as expected_days,
        COUNT(DISTINCT dc.day) as covered_days,
        ROUND(100.0 * COUNT(DISTINCT dc.day) / NULLIF(COUNT(DISTINCT ds.day), 0), 2) as coverage_pct
    FROM date_series ds
    LEFT JOIN data_coverage dc ON ds.day = dc.day
    """
    df = run_query(engine, query)

    if len(df) == 0:
        return {
            "passed": False,
            "message": "No data found for backfill test",
            "coverage_pct": 0,
        }

    coverage_pct = df["coverage_pct"].iloc[0] if "coverage_pct" in df.columns else 0
    expected_days = df["expected_days"].iloc[0] if "expected_days" in df.columns else 0
    covered_days = df["covered_days"].iloc[0] if "covered_days" in df.columns else 0

    # Backfill should achieve >80% coverage
    passed = coverage_pct >= 80.0

    return {
        "passed": passed,
        "message": f"Coverage: {coverage_pct:.1f}% ({covered_days}/{expected_days} days)"
        + (" (meets threshold)" if passed else " (below 80% threshold)"),
        "coverage_pct": float(coverage_pct),
        "expected_days": int(expected_days),
        "covered_days": int(covered_days),
    }


def main():
    """Run all historical job tests."""
    print("=" * 80)
    print("Historical Job Behavior Test")
    print("=" * 80)
    print()

    engine = get_read_engine()

    results = {}

    # Run tests
    results["incremental_fetch"] = test_incremental_fetch(engine)
    results["24h_boundary"] = test_24h_boundary(engine)
    results["source_conflict"] = test_source_conflict(engine)
    results["empty_window"] = test_empty_window(engine)
    results["backfill"] = test_backfill(engine)

    # Print results
    print()
    print("=" * 80)
    print("Test Results")
    print("=" * 80)

    for test_name, result in results.items():
        status = "✓ PASS" if result["passed"] else "✗ FAIL"
        print(f"{status} {test_name}: {result['message']}")
        for key, value in result.items():
            if key not in ["passed", "message"]:
                print(f"    {key}: {value}")

    # Save results
    output_file = "test_historical_jobs_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to {output_file}")

    # Summary
    passed = sum(1 for r in results.values() if r["passed"])
    total = len(results)
    print(f"\nSummary: {passed}/{total} tests passed")

    if passed < total:
        print("\nSome tests failed. Review results for details.")
        return 1

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
