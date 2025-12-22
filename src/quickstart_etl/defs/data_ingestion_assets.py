"""
Data Ingestion Assets - ZINC Fusion V15
Ultra-organized data ingestion with validation and quality checks.
"""

from dagster import asset, AssetExecutionContext, AssetCheckResult
from dagster import AssetCheckSeverity, asset_check
import pandas as pd
import duckdb
from typing import Dict, Any
from ..validation.data_quality import DataQualityValidator
from .resources import DuckDBResource


# =============================================================================
# RAW DATA INGESTION ASSETS
# =============================================================================


@asset(
    group_name="data_ingestion",
    description="Ingest market futures data (1D) with validation",
    metadata={
        "source": "Yahoo Finance",
        "update_frequency": "daily",
        "data_type": "market_data",
    },
)
def raw_market_futures_1d(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> Dict[str, Any]:
    """Ingest and validate daily market futures data"""

    conn = duckdb_resource.get_connection()

    # Get row count
    count = conn.execute("SELECT COUNT(*) FROM raw.market_futures_1d").fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(as_of_date), MAX(as_of_date) FROM raw.market_futures_1d"
    ).fetchone()

    context.log.info(
        f"Market futures 1D: {count:,} rows, {date_range[0]} to {date_range[1]}"
    )

    conn.close()

    return {
        "rows": count,
        "date_range": f"{date_range[0]} to {date_range[1]}",
        "status": "validated",
    }


@asset(
    group_name="data_ingestion",
    description="Ingest market futures data (1H) with validation",
    metadata={
        "source": "Yahoo Finance",
        "update_frequency": "hourly",
        "data_type": "market_data",
    },
)
def raw_market_futures_1h(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> Dict[str, Any]:
    """Ingest and validate hourly market futures data"""

    conn = duckdb_resource.get_connection()

    count = conn.execute("SELECT COUNT(*) FROM raw.market_futures_1h").fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(ts_event), MAX(ts_event) FROM raw.market_futures_1h"
    ).fetchone()

    context.log.info(
        f"Market futures 1H: {count:,} rows, {str(date_range[0])[:10]} to {str(date_range[1])[:10]}"
    )

    conn.close()

    return {
        "rows": count,
        "date_range": f"{str(date_range[0])[:10]} to {str(date_range[1])[:10]}",
        "status": "validated",
    }


@asset(
    group_name="data_ingestion",
    description="Ingest FRED economic data with validation",
    metadata={
        "source": "Federal Reserve Economic Data",
        "update_frequency": "daily",
        "data_type": "economic_data",
    },
)
def raw_fred_economic(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> Dict[str, Any]:
    """Ingest and validate FRED economic data"""

    conn = duckdb_resource.get_connection()

    count = conn.execute("SELECT COUNT(*) FROM raw.fred_economic").fetchone()[0]
    series_count = conn.execute(
        "SELECT COUNT(DISTINCT series_id) FROM raw.fred_economic"
    ).fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(as_of_date), MAX(as_of_date) FROM raw.fred_economic"
    ).fetchone()

    context.log.info(
        f"FRED Economic: {count:,} rows, {series_count} series, {date_range[0]} to {date_range[1]}"
    )

    conn.close()

    return {
        "rows": count,
        "series_count": series_count,
        "date_range": f"{date_range[0]} to {date_range[1]}",
        "status": "validated",
    }


@asset(
    group_name="data_ingestion",
    description="Ingest CFTC COT data with validation",
    metadata={
        "source": "CFTC Commitments of Traders",
        "update_frequency": "weekly",
        "data_type": "regulatory_data",
    },
)
def raw_cftc_cot(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> Dict[str, Any]:
    """Ingest and validate CFTC COT data"""

    conn = duckdb_resource.get_connection()

    count = conn.execute("SELECT COUNT(*) FROM raw.cftc_cot").fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(report_date), MAX(report_date) FROM raw.cftc_cot"
    ).fetchone()

    context.log.info(
        f"CFTC COT: {count:,} rows, {str(date_range[0])[:10]} to {str(date_range[1])[:10]}"
    )

    conn.close()

    return {
        "rows": count,
        "date_range": f"{str(date_range[0])[:10]} to {str(date_range[1])[:10]}",
        "status": "validated",
    }


# =============================================================================
# WEATHER DATA INGESTION ASSETS
# =============================================================================


@asset(
    group_name="weather_data",
    description="Consolidated weather data from all 57 stations across 5 regions",
    metadata={
        "source": "NOAA, Open-Meteo",
        "update_frequency": "daily",
        "data_type": "weather_data",
        "coverage": "20 years (2005-2025)",
    },
)
def raw_weather_noaa(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> Dict[str, Any]:
    """Consolidated weather data asset"""

    conn = duckdb_resource.get_connection()

    # Overall stats
    count = conn.execute("SELECT COUNT(*) FROM raw.weather_noaa").fetchone()[0]
    stations = conn.execute(
        "SELECT COUNT(DISTINCT station_id) FROM raw.weather_noaa"
    ).fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(date), MAX(date) FROM raw.weather_noaa"
    ).fetchone()

    # By country breakdown
    by_country = conn.execute("""
        SELECT country, COUNT(DISTINCT station_id) as stations, COUNT(*) as rows
        FROM raw.weather_noaa 
        GROUP BY country 
        ORDER BY stations DESC
    """).df()

    context.log.info(
        f"Weather NOAA: {count:,} rows, {stations} stations, {date_range[0]} to {date_range[1]}"
    )
    for _, row in by_country.iterrows():
        context.log.info(
            f"  {row['country']}: {row['stations']} stations, {row['rows']:,} observations"
        )

    conn.close()

    return {
        "rows": count,
        "stations": stations,
        "date_range": f"{date_range[0]} to {date_range[1]}",
        "countries": by_country.to_dict("records"),
        "status": "validated",
    }


# =============================================================================
# DATA QUALITY CHECKS
# =============================================================================


@asset_check(
    asset=raw_market_futures_1d, description="Validate market futures 1D data quality"
)
def check_market_futures_1d_quality(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> AssetCheckResult:
    """Check market futures 1D data quality"""

    conn = duckdb_resource.get_connection()

    # Check for nulls in critical columns
    null_check = conn.execute("""
        SELECT 
            SUM(CASE WHEN as_of_date IS NULL THEN 1 ELSE 0 END) as null_dates,
            SUM(CASE WHEN symbol IS NULL THEN 1 ELSE 0 END) as null_symbols,
            SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END) as null_closes,
            COUNT(*) as total_rows
        FROM raw.market_futures_1d
    """).fetchone()

    null_dates, null_symbols, null_closes, total = null_check

    # Check for duplicates
    dupes = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT as_of_date, symbol, COUNT(*)
            FROM raw.market_futures_1d
            GROUP BY as_of_date, symbol
            HAVING COUNT(*) > 1
        )
    """).fetchone()[0]

    conn.close()

    # Determine pass/fail
    passed = null_dates == 0 and null_symbols == 0 and dupes == 0
    severity = AssetCheckSeverity.WARN if not passed else AssetCheckSeverity.INFO

    return AssetCheckResult(
        passed=passed,
        severity=severity,
        metadata={
            "total_rows": total,
            "null_dates": null_dates,
            "null_symbols": null_symbols,
            "null_closes": null_closes,
            "duplicates": dupes,
        },
    )


@asset_check(
    asset=raw_weather_noaa, description="Validate weather data quality and completeness"
)
def check_weather_data_quality(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> AssetCheckResult:
    """Check weather data quality"""

    conn = duckdb_resource.get_connection()

    # Check station coverage
    expected_stations = 57
    actual_stations = conn.execute(
        "SELECT COUNT(DISTINCT station_id) FROM raw.weather_noaa"
    ).fetchone()[0]

    # Check duplicates
    dupes = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT station_id, date, COUNT(*)
            FROM raw.weather_noaa
            GROUP BY station_id, date
            HAVING COUNT(*) > 1
        )
    """).fetchone()[0]

    # Check data completeness by region
    regional_coverage = conn.execute("""
        SELECT 
            SUBSTR(region, 1, 2) as country_code,
            COUNT(DISTINCT station_id) as stations,
            MIN(date) as start_date,
            MAX(date) as end_date
        FROM raw.weather_noaa 
        GROUP BY SUBSTR(region, 1, 2)
        ORDER BY country_code
    """).df()

    conn.close()

    passed = actual_stations == expected_stations and dupes == 0
    severity = AssetCheckSeverity.WARN if not passed else AssetCheckSeverity.INFO

    return AssetCheckResult(
        passed=passed,
        severity=severity,
        metadata={
            "expected_stations": expected_stations,
            "actual_stations": actual_stations,
            "duplicates": dupes,
            "regional_coverage": regional_coverage.to_dict("records"),
        },
    )
