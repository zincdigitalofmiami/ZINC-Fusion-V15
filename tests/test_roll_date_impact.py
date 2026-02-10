#!/usr/bin/env python3
# sqlref: ignore-file
"""
Test 7: Roll Date Impact Analysis

Analyze when/why symbols diverge:
- Identify roll dates for both symbols (last 90 days)
- Compare prices on roll dates
- Measure impact on:
  - Daily aggregates
  - Technical indicators
  - Chart appearance
"""

from __future__ import annotations

__test__ = False  # Pytest should not collect integration scripts.

import json
from datetime import datetime
from typing import Dict, List

import pandas as pd
from fusion.db import get_read_engine


def identify_roll_dates(engine, symbol_type: str, days: int = 90) -> List[Dict]:
    """Identify potential roll dates based on price jumps."""
    # This would ideally use actual contract roll data
    # For now, we'll detect large intraday price changes

    table = (
        f"analytics.zl_price_15m_test_{symbol_type}"
        if symbol_type in ["c", "n"]
        else "analytics.zl_price_15m"
    )

    query = f"""
    WITH daily_stats AS (
        SELECT
            DATE_TRUNC('day', timestamp) as day,
            MIN(close) as day_low,
            MAX(close) as day_high,
            FIRST_VALUE(close) OVER (PARTITION BY DATE_TRUNC('day', timestamp) ORDER BY timestamp) as day_open,
            LAST_VALUE(close) OVER (PARTITION BY DATE_TRUNC('day', timestamp) ORDER BY timestamp ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as day_close,
            COUNT(*) as bar_count
        FROM {table}
        WHERE timestamp >= NOW() - INTERVAL '{days} days'
        GROUP BY DATE_TRUNC('day', timestamp)
    ),
    daily_changes AS (
        SELECT
            day,
            day_open,
            day_close,
            day_high,
            day_low,
            ABS(day_close - day_open) / NULLIF(day_open, 0) * 100 as intraday_pct_change,
            day_close - LAG(day_close) OVER (ORDER BY day) as day_to_day_change,
            ABS(day_close - LAG(day_close) OVER (ORDER BY day)) / NULLIF(LAG(day_close) OVER (ORDER BY day), 0) * 100 as day_to_day_pct_change,
            bar_count
        FROM daily_stats
    )
    SELECT *
    FROM daily_changes
    WHERE intraday_pct_change > 2.0 OR day_to_day_pct_change > 2.0
    ORDER BY day DESC
    """

    df = pd.read_sql(query, engine)
    return df.to_dict("records")


def compare_roll_dates(engine) -> Dict:
    """Compare roll dates between ZL.c.0 and ZL.n.0."""
    roll_dates_c = identify_roll_dates(engine, "c", days=90)
    roll_dates_n = identify_roll_dates(engine, "n", days=90)

    # Extract dates
    dates_c = {
        r["day"].date() if isinstance(r["day"], datetime) else r["day"]
        for r in roll_dates_c
    }
    dates_n = {
        r["day"].date() if isinstance(r["day"], datetime) else r["day"]
        for r in roll_dates_n
    }

    common_dates = dates_c & dates_n
    c_only = dates_c - dates_n
    n_only = dates_n - dates_c

    return {
        "roll_dates_c": len(roll_dates_c),
        "roll_dates_n": len(roll_dates_n),
        "common_roll_dates": len(common_dates),
        "c_only_dates": len(c_only),
        "n_only_dates": len(n_only),
        "roll_date_offset_days": abs(len(roll_dates_c) - len(roll_dates_n))
        if roll_dates_c and roll_dates_n
        else 0,
    }


def analyze_daily_impact(engine) -> Dict:
    """Analyze impact on daily aggregates."""
    query = """
    WITH c_daily AS (
        SELECT
            DATE_TRUNC('day', timestamp)::date as day,
            MIN(close) as low,
            MAX(close) as high,
            FIRST_VALUE(close) OVER (PARTITION BY DATE_TRUNC('day', timestamp) ORDER BY timestamp) as open,
            LAST_VALUE(close) OVER (PARTITION BY DATE_TRUNC('day', timestamp) ORDER BY timestamp ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as close,
            SUM(volume) as volume
        FROM analytics.zl_price_15m_test_c  -- sqlref: ignore
        WHERE timestamp >= NOW() - INTERVAL '90 days'
        GROUP BY DATE_TRUNC('day', timestamp)
    ),
    n_daily AS (
        SELECT
            DATE_TRUNC('day', timestamp)::date as day,
            MIN(close) as low,
            MAX(close) as high,
            FIRST_VALUE(close) OVER (PARTITION BY DATE_TRUNC('day', timestamp) ORDER BY timestamp) as open,
            LAST_VALUE(close) OVER (PARTITION BY DATE_TRUNC('day', timestamp) ORDER BY timestamp ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as close,
            SUM(volume) as volume
        FROM analytics.zl_price_15m_test_n
        WHERE timestamp >= NOW() - INTERVAL '90 days'
        GROUP BY DATE_TRUNC('day', timestamp)
    ),
    merged AS (
        SELECT
            COALESCE(c.day, n.day) as day,
            c.close as c_close,
            n.close as n_close,
            ABS(c.close - n.close) / NULLIF(c.close, 0) * 100 as close_diff_pct
        FROM c_daily c
        FULL OUTER JOIN n_daily n ON c.day = n.day
    )
    SELECT
        COUNT(*) as total_days,
        AVG(close_diff_pct) as avg_close_diff_pct,
        MAX(close_diff_pct) as max_close_diff_pct,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY close_diff_pct) as p95_close_diff_pct,
        COUNT(*) FILTER (WHERE close_diff_pct > 0.1) as days_gt_0_1_pct,
        COUNT(*) FILTER (WHERE close_diff_pct > 1.0) as days_gt_1_pct
    FROM merged
    WHERE c_close IS NOT NULL AND n_close IS NOT NULL
    """

    df = pd.read_sql(query, engine)
    if len(df) == 0:
        return {"error": "No data found for comparison"}

    return df.iloc[0].to_dict()


def generate_report(engine) -> str:
    """Generate markdown report."""
    roll_comparison = compare_roll_dates(engine)
    daily_impact = analyze_daily_impact(engine)

    report = f"""# Roll Date Impact Analysis Report

Generated: {datetime.now().isoformat()}

## Roll Date Comparison

- ZL.c.0 roll dates: {roll_comparison.get("roll_dates_c", 0)}
- ZL.n.0 roll dates: {roll_comparison.get("roll_dates_n", 0)}
- Common roll dates: {roll_comparison.get("common_roll_dates", 0)}
- Calendar-only dates: {roll_comparison.get("c_only_dates", 0)}
- OI-ranked-only dates: {roll_comparison.get("n_only_dates", 0)}
- Roll date offset: {roll_comparison.get("roll_date_offset_days", 0)} days

## Daily Aggregate Impact

"""

    if "error" not in daily_impact:
        report += f"""
- Total days analyzed: {daily_impact.get("total_days", 0)}
- Average close difference: {daily_impact.get("avg_close_diff_pct", 0):.4f}%
- Maximum close difference: {daily_impact.get("max_close_diff_pct", 0):.4f}%
- P95 close difference: {daily_impact.get("p95_close_diff_pct", 0):.4f}%
- Days with >0.1% difference: {daily_impact.get("days_gt_0_1_pct", 0)}
- Days with >1.0% difference: {daily_impact.get("days_gt_1_pct", 0)}
"""
    else:
        report += f"\n{daily_impact['error']}\n"

    report += """
## Impact Assessment

### Chart Appearance
- Price differences <0.1%: Minimal visual impact
- Price differences 0.1-1.0%: Slight visual differences
- Price differences >1.0%: Noticeable visual differences

### Technical Indicators
- Small differences (<0.1%) have minimal impact on most indicators
- Larger differences (>1.0%) may affect:
  - Moving averages
  - Bollinger Bands
  - Support/Resistance levels

### Daily Aggregates
- Daily OHLC values may differ slightly on roll dates
- Volume aggregation should be similar
- Impact depends on roll date offset

## Recommendations

1. Monitor roll date differences closely
2. Use OI-ranked symbol (ZL.n.0) for Crush specialist (as per plan)
3. Consider roll date alignment for chart consistency
4. Document roll date behavior for future reference
"""

    return report


def main():
    """Run roll date impact analysis."""
    print("=" * 80)
    print("Roll Date Impact Analysis")
    print("=" * 80)
    print()

    engine = get_read_engine()

    # Check if test tables exist
    query = """
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'analytics'
      AND table_name IN ('zl_price_15m_test_c', 'zl_price_15m_test_n')
    """
    df = pd.read_sql(query, engine)

    if len(df) < 2:
        print("ERROR: Test tables not found. Run test_parallel_symbols.py first.")
        return 1

    print("Analyzing roll dates...")
    roll_comparison = compare_roll_dates(engine)

    print("Analyzing daily impact...")
    daily_impact = analyze_daily_impact(engine)

    print("Generating report...")
    report = generate_report(engine)

    # Save report
    output_file = "roll_date_impact_report.md"
    with open(output_file, "w") as f:
        f.write(report)

    # Save JSON data
    json_file = "roll_date_impact_data.json"
    with open(json_file, "w") as f:
        json.dump(
            {"roll_comparison": roll_comparison, "daily_impact": daily_impact},
            f,
            indent=2,
            default=str,
        )

    print()
    print("=" * 80)
    print("Results")
    print("=" * 80)
    print(report)
    print()
    print(f"Report saved to {output_file}")
    print(f"Data saved to {json_file}")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
