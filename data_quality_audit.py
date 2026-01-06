#!/usr/bin/env python3
"""
Comprehensive Data Quality Audit for ZINC-FUSION-V15
Analyzes Prisma Postgres database for data coverage, freshness, and quality issues.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from collections import defaultdict

# Database connection from .env
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in environment")
    sys.exit(1)

def get_connection():
    """Get PostgreSQL connection"""
    return psycopg2.connect(DATABASE_URL)

def execute_query(query: str, params: tuple = None) -> List[Dict]:
    """Execute query and return results as list of dicts"""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            return [dict(row) for row in cur.fetchall()]

def execute_single(query: str, params: tuple = None) -> Dict:
    """Execute query and return single result"""
    results = execute_query(query, params)
    return results[0] if results else {}

def analyze_table_metrics(schema: str, table: str, date_col: str = None) -> Dict[str, Any]:
    """Get row count, date range, and basic metrics for a table"""
    metrics = {
        'schema': schema,
        'table': table,
        'row_count': 0,
        'oldest_date': None,
        'latest_date': None,
        'days_coverage': 0,
        'freshness_days': None
    }

    # Row count
    count_query = f'SELECT COUNT(*) as cnt FROM "{schema}"."{table}"'
    result = execute_single(count_query)
    metrics['row_count'] = result.get('cnt', 0)

    if metrics['row_count'] == 0:
        return metrics

    # Date range if date column provided
    if date_col:
        date_query = f"""
            SELECT
                MIN({date_col}) as oldest,
                MAX({date_col}) as latest,
                MAX({date_col})::date - MIN({date_col})::date as days_span
            FROM "{schema}"."{table}"
        """
        result = execute_single(date_query)
        oldest = result.get('oldest')
        latest = result.get('latest')

        # Convert to date if datetime
        if oldest:
            metrics['oldest_date'] = oldest.date() if hasattr(oldest, 'date') else oldest
        if latest:
            metrics['latest_date'] = latest.date() if hasattr(latest, 'date') else latest

        metrics['days_coverage'] = result.get('days_span', 0)

        if metrics['latest_date']:
            latest_date = metrics['latest_date']
            # Ensure we're comparing dates
            if isinstance(latest_date, datetime):
                latest_date = latest_date.date()
            delta = datetime.now().date() - latest_date
            metrics['freshness_days'] = delta.days

    return metrics

def analyze_null_percentages(schema: str, table: str, columns: List[str]) -> Dict[str, float]:
    """Calculate null percentages for specified columns"""
    total_query = f'SELECT COUNT(*) as total FROM "{schema}"."{table}"'
    total = execute_single(total_query).get('total', 0)

    if total == 0:
        return {col: 100.0 for col in columns}

    null_pcts = {}
    for col in columns:
        null_query = f"""
            SELECT COUNT(*) as null_cnt
            FROM "{schema}"."{table}"
            WHERE {col} IS NULL
        """
        null_cnt = execute_single(null_query).get('null_cnt', 0)
        null_pcts[col] = round((null_cnt / total) * 100, 2)

    return null_pcts

def get_distinct_values(schema: str, table: str, column: str) -> List[str]:
    """Get distinct values for a column"""
    query = f"""
        SELECT DISTINCT {column} as val
        FROM "{schema}"."{table}"
        WHERE {column} IS NOT NULL
        ORDER BY val
    """
    results = execute_query(query)
    return [r['val'] for r in results]

def analyze_market_futures() -> Dict[str, Any]:
    """Analyze market_futures_1d table in raw schema"""
    print("Analyzing raw.market_futures_1d...")

    metrics = analyze_table_metrics('raw', 'market_futures_1d', 'as_of_date')

    # Symbol coverage
    symbols = get_distinct_values('raw', 'market_futures_1d', 'symbol')
    metrics['symbols'] = symbols
    metrics['symbol_count'] = len(symbols)

    # Null percentages for key columns
    null_pcts = analyze_null_percentages('raw', 'market_futures_1d',
                                          ['open', 'high', 'low', 'close', 'volume'])
    metrics['null_percentages'] = null_pcts

    # Per-symbol coverage
    symbol_coverage = {}
    for symbol in symbols:
        query = f"""
            SELECT
                COUNT(*) as records,
                MIN(as_of_date) as start_date,
                MAX(as_of_date) as end_date
            FROM raw.market_futures_1d
            WHERE symbol = %s
        """
        result = execute_single(query, (symbol,))
        symbol_coverage[symbol] = {
            'records': result['records'],
            'start_date': str(result['start_date']) if result['start_date'] else None,
            'end_date': str(result['end_date']) if result['end_date'] else None
        }

    metrics['symbol_coverage'] = symbol_coverage

    return metrics

def analyze_fred_observations() -> Dict[str, Any]:
    """Analyze fred_observations_1d table in raw schema"""
    print("Analyzing raw.fred_observations_1d...")

    metrics = analyze_table_metrics('raw', 'fred_observations_1d', 'as_of_date')

    # Series coverage
    series_list = get_distinct_values('raw', 'fred_observations_1d', 'series_id')
    metrics['series_count'] = len(series_list)
    metrics['series_list'] = series_list

    # Null percentage for value
    null_pcts = analyze_null_percentages('raw', 'fred_observations_1d', ['value'])
    metrics['null_percentages'] = null_pcts

    # Per-series coverage
    series_coverage = {}
    for series_id in series_list:
        query = """
            SELECT
                COUNT(*) as records,
                COUNT(value) as non_null_values,
                MIN(as_of_date) as start_date,
                MAX(as_of_date) as end_date
            FROM raw.fred_observations_1d
            WHERE series_id = %s
        """
        result = execute_single(query, (series_id,))
        coverage_pct = round((result['non_null_values'] / result['records'] * 100), 2) if result['records'] > 0 else 0

        series_coverage[series_id] = {
            'records': result['records'],
            'non_null_values': result['non_null_values'],
            'coverage_pct': coverage_pct,
            'start_date': str(result['start_date']) if result['start_date'] else None,
            'end_date': str(result['end_date']) if result['end_date'] else None
        }

    metrics['series_coverage'] = series_coverage

    # Identify series with good coverage (>80% non-null)
    good_series = [s for s, v in series_coverage.items() if v['coverage_pct'] > 80]
    metrics['good_coverage_series'] = good_series
    metrics['good_coverage_count'] = len(good_series)

    return metrics

def analyze_weather_noaa() -> Dict[str, Any]:
    """Analyze weather_noaa_1d table"""
    print("Analyzing raw.weather_noaa_1d...")

    metrics = analyze_table_metrics('raw', 'weather_noaa_1d', 'as_of_date')

    # Station coverage
    stations = get_distinct_values('raw', 'weather_noaa_1d', 'station_id')
    metrics['station_count'] = len(stations)
    metrics['stations'] = stations[:50]  # Limit to first 50

    # Region coverage
    regions = get_distinct_values('raw', 'weather_noaa_1d', 'region')
    metrics['regions'] = regions
    metrics['region_count'] = len(regions)

    # Null percentages for weather variables
    null_pcts = analyze_null_percentages('raw', 'weather_noaa_1d',
                                          ['tavg_c', 'tmin_c', 'tmax_c', 'prcp_mm',
                                           'awnd_ms', 'rhav_pct'])
    metrics['null_percentages'] = null_pcts

    # Coverage by region
    if regions:
        region_coverage = {}
        for region in regions:
            if region:
                query = """
                    SELECT
                        COUNT(DISTINCT station_id) as station_count,
                        COUNT(*) as records,
                        MIN(as_of_date) as start_date,
                        MAX(as_of_date) as end_date
                    FROM raw.weather_noaa_1d
                    WHERE region = %s
                """
                result = execute_single(query, (region,))
                region_coverage[region] = {
                    'stations': result['station_count'],
                    'records': result['records'],
                    'start_date': str(result['start_date']) if result['start_date'] else None,
                    'end_date': str(result['end_date']) if result['end_date'] else None
                }

        metrics['region_coverage'] = region_coverage

    return metrics

def analyze_cftc_cot() -> Dict[str, Any]:
    """Analyze cftc_cot_1w table in raw schema"""
    print("Analyzing raw.cftc_cot_1w...")

    metrics = analyze_table_metrics('raw', 'cftc_cot_1w', 'report_date')

    # Symbol coverage
    symbols = get_distinct_values('raw', 'cftc_cot_1w', 'symbol')
    metrics['symbols'] = symbols
    metrics['symbol_count'] = len(symbols)

    # Null percentages for key COT fields
    null_pcts = analyze_null_percentages('raw', 'cftc_cot_1w',
                                          ['open_interest', 'managed_money_long', 'managed_money_short',
                                           'managed_money_net', 'prod_merc_net'])
    metrics['null_percentages'] = null_pcts

    # Per-symbol coverage
    symbol_coverage = {}
    for symbol in symbols:
        query = """
            SELECT
                COUNT(*) as records,
                MIN(report_date) as start_date,
                MAX(report_date) as end_date
            FROM raw.cftc_cot_1w
            WHERE symbol = %s
        """
        result = execute_single(query, (symbol,))
        symbol_coverage[symbol] = {
            'records': result['records'],
            'start_date': str(result['start_date']) if result['start_date'] else None,
            'end_date': str(result['end_date']) if result['end_date'] else None
        }

    metrics['symbol_coverage'] = symbol_coverage

    return metrics

def analyze_fred_series_metadata() -> Dict[str, Any]:
    """Analyze fred_series_metadata table"""
    print("Analyzing raw.fred_series_metadata...")

    metrics = {}

    # Count of series
    count_query = 'SELECT COUNT(*) as cnt FROM raw.fred_series_metadata'
    result = execute_single(count_query)
    metrics['total_series'] = result.get('cnt', 0)

    # Get frequency distribution
    freq_query = """
        SELECT frequency, COUNT(*) as cnt
        FROM raw.fred_series_metadata
        GROUP BY frequency
        ORDER BY cnt DESC
    """
    freqs = execute_query(freq_query)
    metrics['frequency_distribution'] = {r['frequency']: r['cnt'] for r in freqs}

    # Get series with observation date ranges
    series_query = """
        SELECT
            series_id,
            title,
            observation_start,
            observation_end,
            frequency,
            units
        FROM raw.fred_series_metadata
        ORDER BY series_id
        LIMIT 100
    """
    series_list = execute_query(series_query)
    metrics['series_sample'] = [
        {
            'series_id': s['series_id'],
            'title': s['title'],
            'start': str(s['observation_start']) if s['observation_start'] else None,
            'end': str(s['observation_end']) if s['observation_end'] else None,
            'frequency': s['frequency']
        }
        for s in series_list
    ]

    return metrics

def analyze_usda_tables() -> Dict[str, Any]:
    """Analyze USDA export sales and WASDE tables"""
    print("Analyzing USDA tables...")

    results = {}

    # Export sales
    export_metrics = analyze_table_metrics('raw', 'usda_export_sales_1w', 'report_date')
    commodities = get_distinct_values('raw', 'usda_export_sales_1w', 'commodity')
    export_metrics['commodities'] = commodities
    export_metrics['commodity_count'] = len(commodities)

    # Null percentages
    null_pcts = analyze_null_percentages('raw', 'usda_export_sales_1w',
                                          ['net_sales_mt', 'exports_mt', 'outstanding_sales_mt'])
    export_metrics['null_percentages'] = null_pcts

    results['export_sales'] = export_metrics

    # WASDE
    wasde_metrics = analyze_table_metrics('raw', 'usda_wasde_1m', 'report_date')
    commodities = get_distinct_values('raw', 'usda_wasde_1m', 'commodity')
    wasde_metrics['commodities'] = commodities
    wasde_metrics['commodity_count'] = len(commodities)

    # Null percentages
    null_pcts = analyze_null_percentages('raw', 'usda_wasde_1m', ['value'])
    wasde_metrics['null_percentages'] = null_pcts

    results['wasde'] = wasde_metrics

    return results

def check_duplicates(schema: str, table: str, key_columns: List[str]) -> int:
    """Check for duplicates based on key columns"""
    key_cols = ', '.join(key_columns)
    query = f"""
        SELECT COUNT(*) as dup_count
        FROM (
            SELECT {key_cols}, COUNT(*) as cnt
            FROM "{schema}"."{table}"
            GROUP BY {key_cols}
            HAVING COUNT(*) > 1
        ) dups
    """
    result = execute_single(query)
    return result.get('dup_count', 0)

def detect_data_gaps(schema: str, table: str, date_col: str, symbol_col: str = None) -> List[Dict]:
    """Detect date gaps in time series data"""
    if symbol_col:
        # Check gaps per symbol
        symbols_query = f'SELECT DISTINCT {symbol_col} as sym FROM "{schema}"."{table}" LIMIT 5'
        symbols = [r['sym'] for r in execute_query(symbols_query)]

        gaps = []
        for symbol in symbols:
            query = f"""
                WITH date_series AS (
                    SELECT
                        {date_col} as curr_date,
                        LEAD({date_col}) OVER (ORDER BY {date_col}) as next_date
                    FROM "{schema}"."{table}"
                    WHERE {symbol_col} = %s
                )
                SELECT
                    curr_date,
                    next_date,
                    next_date::date - curr_date::date as gap_days
                FROM date_series
                WHERE next_date::date - curr_date::date > 7
                ORDER BY gap_days DESC
                LIMIT 5
            """
            results = execute_query(query, (symbol,))
            if results:
                gaps.append({
                    'symbol': symbol,
                    'gaps': results
                })

        return gaps
    else:
        # Check gaps for entire table
        query = f"""
            WITH date_series AS (
                SELECT
                    {date_col} as curr_date,
                    LEAD({date_col}) OVER (ORDER BY {date_col}) as next_date
                FROM "{schema}"."{table}"
            )
            SELECT
                curr_date,
                next_date,
                next_date::date - curr_date::date as gap_days
            FROM date_series
            WHERE next_date::date - curr_date::date > 7
            ORDER BY gap_days DESC
            LIMIT 10
        """
        return execute_query(query)

def generate_markdown_report(audit_results: Dict[str, Any]) -> str:
    """Generate markdown report from audit results"""
    today = datetime.now().strftime('%Y-%m-%d')

    md = f"""# ZINC-FUSION-V15 Data Quality Audit Report
**Generated:** {today}
**Database:** Prisma Postgres (ZINC-FUSION-V15)
**Focus:** Soybean Oil (ZL) Futures Price Prediction

---

## Executive Summary

This audit analyzes data coverage, freshness, quality, and gaps across all raw data sources in the ZINC-FUSION-V15 database.

"""

    # Summary Table
    md += "## Summary Table: All Data Sources\n\n"
    md += "| Data Source | Schema | Table | Row Count | Date Range | Freshness | Status |\n"
    md += "|------------|--------|-------|-----------|------------|-----------|--------|\n"

    sources = []

    # Market Futures
    if 'market_futures' in audit_results:
        mf = audit_results['market_futures']
        freshness = f"{mf['freshness_days']} days" if mf['freshness_days'] is not None else "N/A"
        status = "✓ Good" if mf['freshness_days'] and mf['freshness_days'] < 7 else "⚠ Stale"
        date_range = f"{mf['oldest_date']} to {mf['latest_date']}" if mf['oldest_date'] else "N/A"
        md += f"| Market Futures | raw | market_futures_1d | {mf['row_count']:,} | {date_range} | {freshness} | {status} |\n"
        sources.append(('Market Futures', mf))


    # FRED Observations
    if 'fred_observations' in audit_results:
        fo = audit_results['fred_observations']
        freshness = f"{fo['freshness_days']} days" if fo['freshness_days'] is not None else "N/A"
        status = "✓ Good" if fo['freshness_days'] and fo['freshness_days'] < 7 else "⚠ Stale"
        date_range = f"{fo['oldest_date']} to {fo['latest_date']}" if fo['oldest_date'] else "N/A"
        md += f"| FRED Observations | raw | fred_observations_1d | {fo['row_count']:,} | {date_range} | {freshness} | {status} |\n"

    # Weather
    if 'weather' in audit_results:
        w = audit_results['weather']
        freshness = f"{w['freshness_days']} days" if w['freshness_days'] is not None else "N/A"
        status = "✓ Good" if w['freshness_days'] and w['freshness_days'] < 7 else "⚠ Stale"
        date_range = f"{w['oldest_date']} to {w['latest_date']}" if w['oldest_date'] else "N/A"
        md += f"| Weather (NOAA) | raw | weather_noaa_1d | {w['row_count']:,} | {date_range} | {freshness} | {status} |\n"
        sources.append(('Weather', w))

    # COT
    if 'cot' in audit_results:
        c = audit_results['cot']
        freshness = f"{c['freshness_days']} days" if c['freshness_days'] is not None else "N/A"
        status = "✓ Good" if c['freshness_days'] and c['freshness_days'] < 14 else "⚠ Stale"  # COT is weekly
        date_range = f"{c['oldest_date']} to {c['latest_date']}" if c['oldest_date'] else "N/A"
        md += f"| CFTC COT | raw | cftc_cot_1w | {c['row_count']:,} | {date_range} | {freshness} | {status} |\n"
        sources.append(('COT', c))

    # USDA
    if 'usda' in audit_results:
        usda = audit_results['usda']
        if 'export_sales' in usda:
            es = usda['export_sales']
            freshness = f"{es['freshness_days']} days" if es['freshness_days'] is not None else "N/A"
            status = "✓ Good" if es['freshness_days'] and es['freshness_days'] < 14 else "⚠ Stale"
            date_range = f"{es['oldest_date']} to {es['latest_date']}" if es['oldest_date'] else "N/A"
            md += f"| USDA Export Sales | raw | usda_export_sales_1w | {es['row_count']:,} | {date_range} | {freshness} | {status} |\n"

        if 'wasde' in usda:
            wd = usda['wasde']
            freshness = f"{wd['freshness_days']} days" if wd['freshness_days'] is not None else "N/A"
            status = "✓ Good" if wd['freshness_days'] and wd['freshness_days'] < 60 else "⚠ Stale"  # Monthly report
            date_range = f"{wd['oldest_date']} to {wd['latest_date']}" if wd['oldest_date'] else "N/A"
            md += f"| USDA WASDE | raw | usda_wasde_1m | {wd['row_count']:,} | {date_range} | {freshness} | {status} |\n"

    md += "\n---\n\n"

    # Detailed Analysis Sections

    # 1. Market Futures Detail
    if 'market_futures' in audit_results:
        md += "## 1. Market Futures (raw.market_futures_1d)\n\n"
        mf = audit_results['market_futures']

        md += f"**Total Records:** {mf['row_count']:,}  \n"
        md += f"**Date Range:** {mf['oldest_date']} to {mf['latest_date']}  \n"
        md += f"**Coverage:** {mf['days_coverage']} days  \n"
        md += f"**Freshness:** {mf['freshness_days']} days behind  \n\n"

        md += f"### Symbol Coverage ({mf['symbol_count']} symbols)\n\n"
        md += "| Symbol | Records | Start Date | End Date |\n"
        md += "|--------|---------|------------|----------|\n"

        # Highlight ZL and related symbols
        priority_symbols = ['ZL', 'ZS', 'BO', 'SM']
        symbol_cov = mf.get('symbol_coverage', {})

        for sym in priority_symbols:
            if sym in symbol_cov:
                cov = symbol_cov[sym]
                md += f"| **{sym}** | {cov['records']:,} | {cov['start_date']} | {cov['end_date']} |\n"

        for sym in sorted(mf.get('symbols', [])):
            if sym not in priority_symbols and sym in symbol_cov:
                cov = symbol_cov[sym]
                md += f"| {sym} | {cov['records']:,} | {cov['start_date']} | {cov['end_date']} |\n"

        md += "\n### Null/Missing Value Percentages\n\n"
        null_pcts = mf.get('null_percentages', {})
        md += "| Column | Null % |\n"
        md += "|--------|--------|\n"
        for col, pct in sorted(null_pcts.items()):
            status = "✓" if pct < 5 else "⚠" if pct < 20 else "✗"
            md += f"| {col} | {pct}% {status} |\n"

        md += "\n---\n\n"

    # 2. FRED Observations
    if 'fred_observations' in audit_results:
        md += "## 2. FRED Economic Series (raw.fred_observations_1d)\n\n"
        fo = audit_results['fred_observations']

        md += f"**Total Records:** {fo['row_count']:,}  \n"
        md += f"**Total Series:** {fo['series_count']}  \n"
        md += f"**Date Range:** {fo['oldest_date']} to {fo['latest_date']}  \n"
        md += f"**Good Coverage Series (>80%):** {fo.get('good_coverage_count', 0)}  \n\n"

        if 'series_coverage' in fo:
            md += "### Series Coverage Analysis\n\n"
            md += "| Series ID | Coverage % | Records | First Date | Last Date |\n"
            md += "|-----------|------------|---------|------------|----------|\n"

            # Sort by coverage percentage
            series_cov = fo['series_coverage']
            sorted_series = sorted(series_cov.items(), key=lambda x: x[1]['coverage_pct'], reverse=True)

            for series_id, cov in sorted_series[:30]:  # Show top 30
                status = "✓" if cov['coverage_pct'] > 80 else "⚠" if cov['coverage_pct'] > 50 else "✗"
                md += f"| {series_id} {status} | {cov['coverage_pct']}% | {cov['records']:,} | {cov['start_date']} | {cov['end_date']} |\n"

            if len(sorted_series) > 30:
                md += f"\n*Showing top 30 of {len(sorted_series)} series. See full audit data for complete list.*\n"

        md += "\n---\n\n"

    # 3. Weather Data
    if 'weather' in audit_results:
        md += "## 3. Weather Data (raw.weather_noaa_1d)\n\n"
        w = audit_results['weather']

        md += f"**Total Records:** {w['row_count']:,}  \n"
        md += f"**Total Stations:** {w['station_count']}  \n"
        md += f"**Regions:** {w['region_count']}  \n"
        md += f"**Date Range:** {w['oldest_date']} to {w['latest_date']}  \n\n"

        md += "### Regional Coverage\n\n"
        md += "| Region | Stations | Records | Start Date | End Date |\n"
        md += "|--------|----------|---------|------------|----------|\n"

        if 'region_coverage' in w:
            for region, cov in sorted(w['region_coverage'].items()):
                md += f"| {region or 'NULL'} | {cov['stations']} | {cov['records']:,} | {cov['start_date']} | {cov['end_date']} |\n"

        md += "\n### Weather Variable Completeness\n\n"
        null_pcts = w.get('null_percentages', {})
        md += "| Variable | Null % | Status |\n"
        md += "|----------|--------|--------|\n"
        for var, pct in sorted(null_pcts.items()):
            status = "✓ Good" if pct < 30 else "⚠ Partial" if pct < 60 else "✗ Poor"
            md += f"| {var} | {pct}% | {status} |\n"

        md += "\n---\n\n"

    # 4. CFTC COT Data
    if 'cot' in audit_results:
        md += "## 4. CFTC Commitment of Traders (raw.cftc_cot_1w)\n\n"
        c = audit_results['cot']

        md += f"**Total Records:** {c['row_count']:,}  \n"
        md += f"**Symbols:** {c['symbol_count']}  \n"
        md += f"**Date Range:** {c['oldest_date']} to {c['latest_date']}  \n\n"

        md += "### Symbol Coverage\n\n"
        md += "| Symbol | Records | Start Date | End Date |\n"
        md += "|--------|---------|------------|----------|\n"

        symbol_cov = c.get('symbol_coverage', {})
        for sym in sorted(c.get('symbols', [])):
            if sym in symbol_cov:
                cov = symbol_cov[sym]
                md += f"| {sym} | {cov['records']:,} | {cov['start_date']} | {cov['end_date']} |\n"

        md += "\n### Data Completeness\n\n"
        null_pcts = c.get('null_percentages', {})
        md += "| Field | Null % |\n"
        md += "|-------|--------|\n"
        for field, pct in sorted(null_pcts.items()):
            status = "✓" if pct < 5 else "⚠" if pct < 20 else "✗"
            md += f"| {field} | {pct}% {status} |\n"

        md += "\n---\n\n"

    # 5. FRED Series Metadata
    if 'fred_metadata' in audit_results:
        md += "## 5. FRED Series Metadata (raw.fred_series_metadata)\n\n"
        fm = audit_results['fred_metadata']

        md += f"**Total Series Tracked:** {fm.get('total_series', 0)}  \n\n"

        if 'frequency_distribution' in fm:
            md += "### Frequency Distribution\n\n"
            md += "| Frequency | Count |\n"
            md += "|-----------|-------|\n"
            for freq, cnt in sorted(fm['frequency_distribution'].items(), key=lambda x: x[1], reverse=True):
                md += f"| {freq or 'NULL'} | {cnt} |\n"

        md += "\n---\n\n"

    # Data Quality Issues
    md += "## Data Quality Issues\n\n"

    if 'quality_issues' in audit_results:
        issues = audit_results['quality_issues']

        if issues.get('duplicates'):
            md += "### Duplicate Records\n\n"
            for table, dup_count in issues['duplicates'].items():
                if dup_count > 0:
                    md += f"- **{table}**: {dup_count} duplicate key combinations found ⚠\n"
            md += "\n"

        if issues.get('gaps'):
            md += "### Date Gaps (>7 days)\n\n"
            for source, gaps in issues['gaps'].items():
                if gaps:
                    md += f"**{source}:**\n"
                    if isinstance(gaps, list) and gaps:
                        for gap_info in gaps[:3]:  # Show first 3
                            if 'symbol' in gap_info:
                                md += f"- Symbol {gap_info['symbol']}: Found {len(gap_info['gaps'])} gaps\n"
                            else:
                                md += f"- {gap_info.get('curr_date')} to {gap_info.get('next_date')}: {gap_info.get('gap_days')} days\n"
                    md += "\n"

    md += "---\n\n"

    # Recommendations
    md += "## Recommendations for ZL Futures Forecasting\n\n"

    md += "### Critical Data Sources (Well Covered)\n"
    recommendations = []

    # Check market futures for ZL
    if 'market_futures' in audit_results:
        mf = audit_results['market_futures']
        if 'ZL' in mf.get('symbols', []):
            zl_cov = mf['symbol_coverage'].get('ZL', {})
            if zl_cov.get('records', 0) > 0:
                md += f"- ✓ **ZL Futures Price Data**: {zl_cov['records']:,} records from {zl_cov['start_date']} to {zl_cov['end_date']}\n"

        # Related symbols
        related = ['ZS', 'BO', 'SM']
        for sym in related:
            if sym in mf.get('symbols', []):
                cov = mf['symbol_coverage'].get(sym, {})
                md += f"- ✓ **{sym} (Related)**: {cov.get('records', 0):,} records\n"

    md += "\n### Data Gaps Requiring Attention\n"

    # Identify stale data sources
    if 'market_futures' in audit_results and audit_results['market_futures'].get('freshness_days', 0) > 7:
        md += f"- ⚠ **Market Futures**: {audit_results['market_futures']['freshness_days']} days stale - needs refresh\n"

    if 'fred_observations' in audit_results and audit_results['fred_observations'].get('freshness_days', 0) > 7:
        md += f"- ⚠ **FRED Observations**: {audit_results['fred_observations']['freshness_days']} days stale - needs refresh\n"

    if 'weather' in audit_results and audit_results['weather'].get('freshness_days', 0) > 7:
        md += f"- ⚠ **Weather Data**: {audit_results['weather']['freshness_days']} days stale - needs refresh\n"

    # Check for low coverage FRED series
    if 'fred_observations' in audit_results:
        fo = audit_results['fred_observations']
        low_cov_count = fo['series_count'] - fo.get('good_coverage_count', 0)
        if low_cov_count > 0:
            md += f"- ⚠ **FRED Series Coverage**: {low_cov_count} series have <80% coverage - consider removal or backfill\n"

    md += "\n### Enrichment Opportunities\n"
    md += "- **Options Data**: Volatility surface and Greeks available for enhanced risk modeling\n"
    md += "- **GARCH Forecasts**: Conditional volatility models in place\n"
    md += "- **COT Positioning**: Sentiment indicators from commitment of traders data\n"
    md += "- **USDA Reports**: Export sales and WASDE fundamentals for supply/demand analysis\n"

    md += "\n### Next Steps\n"
    md += "1. Refresh stale data sources (market futures, FRED, weather)\n"
    md += "2. Investigate and fill date gaps in critical time series\n"
    md += "3. Backfill low-coverage FRED series or remove from modeling\n"
    md += "4. Validate duplicate records and implement deduplication\n"
    md += "5. Enhance ZL-specific feature engineering using correlated commodities\n"

    md += "\n---\n\n"
    md += f"*Report generated on {today} for ZINC-FUSION-V15 Procurement Forecasting System*\n"

    return md

def main():
    """Main audit execution"""
    print("=" * 80)
    print("ZINC-FUSION-V15 DATA QUALITY AUDIT")
    print("=" * 80)
    print()

    audit_results = {}

    try:
        # 1. Market Futures
        audit_results['market_futures'] = analyze_market_futures()

        # 2. FRED Observations (long format)
        audit_results['fred_observations'] = analyze_fred_observations()

        # 3. FRED Series Metadata
        audit_results['fred_metadata'] = analyze_fred_series_metadata()

        # 4. Weather
        audit_results['weather'] = analyze_weather_noaa()

        # 5. COT
        audit_results['cot'] = analyze_cftc_cot()

        # 6. USDA
        audit_results['usda'] = analyze_usda_tables()

        # 7. Data Quality Checks
        print("\nChecking data quality issues...")
        quality_issues = {}

        # Duplicates
        duplicates = {}
        duplicates['market_futures'] = check_duplicates('raw', 'market_futures_1d', ['as_of_date', 'symbol'])
        duplicates['cftc_cot'] = check_duplicates('raw', 'cftc_cot_1w', ['report_date', 'symbol'])
        duplicates['fred_observations'] = check_duplicates('raw', 'fred_observations_1d', ['as_of_date', 'series_id'])
        quality_issues['duplicates'] = duplicates

        # Gaps
        gaps = {}
        print("  Detecting date gaps...")
        gaps['market_futures'] = detect_data_gaps('raw', 'market_futures_1d', 'as_of_date', 'symbol')
        gaps['fred_observations'] = detect_data_gaps('raw', 'fred_observations_1d', 'as_of_date')
        quality_issues['gaps'] = gaps

        audit_results['quality_issues'] = quality_issues

        # Generate report
        print("\nGenerating markdown report...")
        report = generate_markdown_report(audit_results)

        # Save report
        report_path = '/Volumes/Satechi Hub/ZINC-FUSION-V15/DATA_QUALITY_AUDIT.md'
        with open(report_path, 'w') as f:
            f.write(report)

        print(f"\n✓ Report saved to: {report_path}")

        # Also save raw JSON
        json_path = '/Volumes/Satechi Hub/ZINC-FUSION-V15/data_quality_audit.json'
        with open(json_path, 'w') as f:
            # Convert dates to strings for JSON serialization
            def convert_dates(obj):
                if isinstance(obj, dict):
                    return {k: convert_dates(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_dates(item) for item in obj]
                elif isinstance(obj, datetime):
                    return obj.isoformat()
                elif hasattr(obj, 'isoformat'):
                    return obj.isoformat()
                else:
                    return obj

            json.dump(convert_dates(audit_results), f, indent=2)

        print(f"✓ Raw data saved to: {json_path}")

        print("\n" + "=" * 80)
        print("AUDIT COMPLETE")
        print("=" * 80)

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
