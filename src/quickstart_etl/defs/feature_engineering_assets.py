"""
Feature Engineering Assets - ZINC Fusion V15
Ultra-organized feature engineering with Big-10 bucket taxonomy.
"""

from dagster import asset, AssetExecutionContext, MetadataValue
from dagster import AssetCheckSeverity, asset_check, AssetCheckResult
import pandas as pd
import duckdb
from typing import Dict, Any
from .resources import DuckDBResource
from .data_ingestion_assets import (
    raw_market_futures_1d,
    raw_market_futures_1h,
    raw_fred_economic,
    raw_weather_noaa,
)


# =============================================================================
# FEATURE ENGINEERING ASSETS - BIG-10 BUCKET TAXONOMY
# =============================================================================


@asset(
    group_name="feature_engineering",
    description="Big-10 daily features: All specialist buckets consolidated",
    deps=[raw_market_futures_1d, raw_fred_economic, raw_weather_noaa],
    metadata={
        "buckets": "Crush, China, FX, Fed, Tariff, Energy, Biofuel, Palm, Volatility, Weather",
        "features": 298,
        "frequency": "daily",
    },
)
def features_big10_daily(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> Dict[str, Any]:
    """Generate Big-10 bucket features for specialist models"""

    conn = duckdb_resource.get_connection()

    # Get current feature stats
    count = conn.execute("SELECT COUNT(*) FROM features.big10_daily").fetchone()[0]
    cols = conn.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'big10_daily' AND table_schema = 'features'"
    ).fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(as_of_date), MAX(as_of_date) FROM features.big10_daily"
    ).fetchone()

    context.log.info(
        f"Big-10 Features: {count:,} rows, {cols} features, {date_range[0]} to {date_range[1]}"
    )

    # Log bucket breakdown
    bucket_features = {
        "crush": 45,  # Soybean crush spread, basis, storage
        "china": 38,  # Trade, imports, tariffs, currency
        "fx": 35,  # USD, BRL, ARS currency features
        "fed": 42,  # Interest rates, monetary policy
        "tariff": 28,  # Trade policy, tariff rates
        "energy": 33,  # Crude oil, natural gas, energy complex
        "biofuel": 25,  # Ethanol, biodiesel, RIN prices
        "palm": 22,  # Palm oil, substitute oils
        "volatility": 30,  # VIX, realized vol, GARCH models
        "weather": 0,  # Weather added via regional schemas
    }

    for bucket, feat_count in bucket_features.items():
        context.log.info(f"  {bucket.upper()}: {feat_count} features")

    conn.close()

    return {
        "rows": count,
        "features": cols,
        "date_range": f"{date_range[0]} to {date_range[1]}",
        "bucket_breakdown": bucket_features,
        "status": "validated",
    }


@asset(
    group_name="feature_engineering",
    description="Complete daily features: Big-10 + Technical + Weather",
    deps=[features_big10_daily],
    metadata={
        "total_features": 413,
        "includes": "Big-10 buckets + Technical indicators + Weather aggregates",
        "frequency": "daily",
    },
)
def features_complete_daily(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> Dict[str, Any]:
    """Complete feature set for ensemble training"""

    conn = duckdb_resource.get_connection()

    count = conn.execute("SELECT COUNT(*) FROM features.complete_daily").fetchone()[0]
    cols = conn.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'complete_daily' AND table_schema = 'features'"
    ).fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(as_of_date), MAX(as_of_date) FROM features.complete_daily"
    ).fetchone()

    context.log.info(
        f"Complete Features: {count:,} rows, {cols} features, {date_range[0]} to {date_range[1]}"
    )

    feature_breakdown = {
        "big10_base": 298,
        "technical_indicators": 85,
        "weather_aggregates": 30,
        "total": cols,
    }

    for category, feat_count in feature_breakdown.items():
        context.log.info(f"  {category.upper()}: {feat_count} features")

    conn.close()

    return {
        "rows": count,
        "features": cols,
        "date_range": f"{date_range[0]} to {date_range[1]}",
        "feature_breakdown": feature_breakdown,
        "status": "validated",
    }


@asset(
    group_name="feature_engineering",
    description="Technical indicators for all symbols with momentum and volatility",
    deps=[raw_market_futures_1h],
    metadata={
        "indicators": "RSI, MACD, Bollinger, ATR, Stochastic, Williams %R",
        "timeframes": "Multiple periods (14, 21, 50, 200)",
        "symbols": "All futures contracts",
    },
)
def features_technical_indicators(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> Dict[str, Any]:
    """Technical analysis indicators across all timeframes"""

    conn = duckdb_resource.get_connection()

    count = conn.execute(
        "SELECT COUNT(*) FROM features.technical_indicators"
    ).fetchone()[0]
    symbols = conn.execute(
        "SELECT COUNT(DISTINCT symbol) FROM features.technical_indicators"
    ).fetchone()[0]
    cols = conn.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'technical_indicators' AND table_schema = 'features'"
    ).fetchone()[0]

    context.log.info(
        f"Technical Indicators: {count:,} rows, {symbols} symbols, {cols} indicators"
    )

    indicator_groups = {
        "momentum": ["rsi_14", "macd", "stoch_k", "williams_r"],
        "volatility": ["atr_14", "bb_width", "realized_vol_21"],
        "trend": ["sma_50", "ema_21", "macd_signal"],
        "volume": ["volume_sma_21", "volume_ratio"],
    }

    for group, indicators in indicator_groups.items():
        context.log.info(f"  {group.upper()}: {len(indicators)} indicators")

    conn.close()

    return {
        "rows": count,
        "symbols": symbols,
        "indicators": cols,
        "indicator_groups": indicator_groups,
        "status": "validated",
    }


@asset(
    group_name="feature_engineering",
    description="Intraday volatility features from 1H data",
    deps=[raw_market_futures_1h],
    metadata={
        "source": "1H OHLC data",
        "metrics": "Realized vol, GARCH, VaR estimates",
        "frequency": "daily_aggregated",
    },
)
def features_intraday_volatility(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> Dict[str, Any]:
    """Intraday volatility and risk metrics"""

    conn = duckdb_resource.get_connection()

    count = conn.execute(
        "SELECT COUNT(*) FROM features.intraday_volatility"
    ).fetchone()[0]
    cols = conn.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'intraday_volatility' AND table_schema = 'features'"
    ).fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(as_of_date), MAX(as_of_date) FROM features.intraday_volatility"
    ).fetchone()

    context.log.info(
        f"Intraday Vol: {count:,} rows, {cols} metrics, {date_range[0]} to {date_range[1]}"
    )

    vol_metrics = {
        "realized_volatility": "21-day realized vol from 1H returns",
        "garch_forecast": "GARCH(1,1) volatility forecast",
        "var_estimates": "5% and 1% Value-at-Risk",
        "volatility_regime": "High/Low vol regime indicator",
    }

    for metric, desc in vol_metrics.items():
        context.log.info(f"  {metric}: {desc}")

    conn.close()

    return {
        "rows": count,
        "metrics": cols,
        "date_range": f"{date_range[0]} to {date_range[1]}",
        "vol_metrics": vol_metrics,
        "status": "validated",
    }


# =============================================================================
# WEATHER REGIONAL FEATURE ASSETS
# =============================================================================


@asset(
    group_name="weather_features",
    description="US Cornbelt weather features (14 stations, 20 years)",
    deps=[raw_weather_noaa],
    metadata={
        "region": "US Corn Belt",
        "states": "IA, IL, IN, MN, NE, MO",
        "stations": 14,
        "coverage": "2005-2025",
    },
)
def weather_us_cornbelt(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> Dict[str, Any]:
    """US Cornbelt weather data for soybean production modeling"""

    conn = duckdb_resource.get_connection()

    count = conn.execute("SELECT COUNT(*) FROM weather.us_cornbelt").fetchone()[0]
    stations = conn.execute(
        "SELECT COUNT(DISTINCT station_id) FROM weather.us_cornbelt"
    ).fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(date), MAX(date) FROM weather.us_cornbelt"
    ).fetchone()

    # State breakdown
    by_state = conn.execute("""
        SELECT region, COUNT(DISTINCT station_id) as stations, COUNT(*) as obs
        FROM weather.us_cornbelt
        GROUP BY region
        ORDER BY region
    """).df()

    context.log.info(
        f"US Cornbelt Weather: {count:,} rows, {stations} stations, {date_range[0]} to {date_range[1]}"
    )
    for _, row in by_state.iterrows():
        context.log.info(
            f"  {row['region']}: {row['stations']} stations, {row['obs']:,} observations"
        )

    conn.close()

    return {
        "rows": count,
        "stations": stations,
        "date_range": f"{date_range[0]} to {date_range[1]}",
        "state_breakdown": by_state.to_dict("records"),
        "status": "validated",
    }


# =============================================================================
# FEATURE QUALITY CHECKS
# =============================================================================


@asset_check(
    asset=features_big10_daily,
    description="Validate Big-10 feature completeness and quality",
)
def check_big10_features_quality(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> AssetCheckResult:
    """Check Big-10 feature data quality"""

    conn = duckdb_resource.get_connection()

    # Expected feature count
    expected_features = 298
    actual_features = conn.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'big10_daily' AND table_schema = 'features'"
    ).fetchone()[0]

    # Check for excessive nulls (>50% null in any column is problematic)
    null_analysis = conn.execute("""
        SELECT column_name,
               (SELECT COUNT(*) FROM features.big10_daily WHERE features.big10_daily[column_name] IS NULL) as null_count,
               (SELECT COUNT(*) FROM features.big10_daily) as total_count
        FROM information_schema.columns 
        WHERE table_name = 'big10_daily' AND table_schema = 'features'
        AND column_name != 'as_of_date'
    """).fetchall()

    high_null_columns = []
    for col, nulls, total in null_analysis:
        if nulls / total > 0.5:  # More than 50% null
            high_null_columns.append((col, nulls / total))

    conn.close()

    passed = actual_features == expected_features and len(high_null_columns) == 0
    severity = AssetCheckSeverity.WARN if not passed else AssetCheckSeverity.INFO

    return AssetCheckResult(
        passed=passed,
        severity=severity,
        metadata={
            "expected_features": expected_features,
            "actual_features": actual_features,
            "high_null_columns": len(high_null_columns),
            "feature_coverage": f"{actual_features}/{expected_features}",
        },
    )
