"""
ZINC-FUSION-V15: Data Completeness Validator

DEPRECATED: Superseded by all_data_policy.py which uses v2 schema architecture.
Retained for backward compatibility but all_data_policy.py is the authoritative
source for data validation.

This module enforces that ALL available data sources are used before training.
Training will FAIL if any required data source is missing or incomplete.
"""

import logging
import re
from dataclasses import dataclass
import psycopg2

logger = logging.getLogger(__name__)

# SQL identifier allowlist — prevents injection via table names
_VALID_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


def _safe_table_ref(table_path: str) -> str:
    """Validate 'schema.table' and return safe identifier string."""
    parts = table_path.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Expected 'schema.table', got: {table_path!r}")
    for part in parts:
        if not _VALID_IDENTIFIER.match(part):
            raise ValueError(
                f"Invalid SQL identifier: {part!r} — must match [a-z_][a-z0-9_]*"
            )
    return table_path


@dataclass
class DataSourceRequirement:
    """Defines a required data source with minimum thresholds."""

    table: str
    min_rows: int
    description: str
    is_required: bool = True


# All required data sources for training (v2 schema architecture)
REQUIRED_DATA_SOURCES = [
    DataSourceRequirement(
        table="mkt.futures_1d",
        min_rows=100_000,
        description="Daily futures data (83 symbols)",
    ),
    DataSourceRequirement(
        table="mkt.fx_1d",
        min_rows=10_000,
        description="Spot FX rates (30 pairs)",
    ),
    DataSourceRequirement(
        table="econ.rates_1d",
        min_rows=50_000,
        description="FRED rates/treasuries",
    ),
    DataSourceRequirement(
        table="alt.weather_1d",
        min_rows=500,
        description="NOAA weather data (US/Brazil/Argentina)",
    ),
    DataSourceRequirement(
        table="pos.cftc_1w",
        min_rows=500,
        description="CFTC COT positioning data",
    ),
    DataSourceRequirement(
        table="supply.usda_exports_1w",
        min_rows=100,
        description="USDA export sales data",
    ),
    DataSourceRequirement(
        table="supply.usda_wasde_1m",
        min_rows=50,
        description="USDA WASDE fundamentals",
    ),
    DataSourceRequirement(
        table="supply.epa_rin_1d",
        min_rows=50,
        description="EPA RIN biofuel prices",
    ),
]


@dataclass
class ValidationResult:
    """Result of data completeness validation."""

    is_valid: bool
    total_sources: int
    valid_sources: int
    missing_sources: list
    insufficient_sources: list
    details: dict


def validate_data_completeness(conn, strict: bool = True) -> ValidationResult:
    """
    Validate that ALL required data sources are present and have sufficient data.

    Args:
        conn: PostgreSQL connection
        strict: If True, fail on ANY missing data. If False, warn only.

    Returns:
        ValidationResult with detailed status

    Raises:
        ValueError: If strict=True and any data source is missing/insufficient
    """
    logger.info("=" * 70)
    logger.info("DATA COMPLETENESS VALIDATION")
    logger.info("=" * 70)

    missing_sources = []
    insufficient_sources = []
    details = {}

    with conn.cursor() as cur:
        for req in REQUIRED_DATA_SOURCES:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {_safe_table_ref(req.table)}")
                row_count = cur.fetchone()[0]

                status = "✅" if row_count >= req.min_rows else "⚠️"
                details[req.table] = {
                    "rows": row_count,
                    "min_required": req.min_rows,
                    "description": req.description,
                    "status": "OK" if row_count >= req.min_rows else "INSUFFICIENT",
                }

                if row_count < req.min_rows:
                    insufficient_sources.append(
                        f"{req.table}: {row_count:,} rows (need {req.min_rows:,})"
                    )
                    logger.warning(
                        f"  {status} {req.table}: {row_count:,} rows "
                        f"(need {req.min_rows:,}) - {req.description}"
                    )
                else:
                    logger.info(
                        f"  {status} {req.table}: {row_count:,} rows - {req.description}"
                    )

            except psycopg2.errors.UndefinedTable:
                missing_sources.append(req.table)
                details[req.table] = {
                    "rows": 0,
                    "min_required": req.min_rows,
                    "description": req.description,
                    "status": "MISSING",
                }
                logger.error(f"  ❌ {req.table}: TABLE MISSING - {req.description}")
                conn.rollback()  # Clear the error state

    valid_sources = (
        len(REQUIRED_DATA_SOURCES) - len(missing_sources) - len(insufficient_sources)
    )
    is_valid = len(missing_sources) == 0 and len(insufficient_sources) == 0

    logger.info("=" * 70)
    logger.info(
        f"VALIDATION RESULT: {valid_sources}/{len(REQUIRED_DATA_SOURCES)} sources OK"
    )

    if missing_sources:
        logger.error(f"  MISSING: {missing_sources}")
    if insufficient_sources:
        logger.warning(f"  INSUFFICIENT: {insufficient_sources}")

    logger.info("=" * 70)

    result = ValidationResult(
        is_valid=is_valid,
        total_sources=len(REQUIRED_DATA_SOURCES),
        valid_sources=valid_sources,
        missing_sources=missing_sources,
        insufficient_sources=insufficient_sources,
        details=details,
    )

    if strict and not is_valid:
        error_msg = (
            f"Data completeness validation FAILED. "
            f"Missing: {missing_sources}, Insufficient: {insufficient_sources}. "
            f"Training cannot proceed without ALL data sources."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    return result


def get_expected_feature_counts(horizon: int) -> dict:
    """
    Get expected feature counts for a given horizon.

    Args:
        horizon: Forecast horizon (5, 21, 63, 126)

    Returns:
        Dict with expected feature counts by category
    """
    use_hourly = horizon == 5
    n_symbols = 84 if use_hourly else 83  # 1h has 84 symbols, 1d has 83

    return {
        "symbol_features": n_symbols * 5,  # OHLCV per symbol
        "fred_features": 111,
        "weather_features": 10,
        "fx_features": 30,
        "cot_features": 20,  # 5 features × 4 symbols (ZL, ZS, ZM, CL)
        "usda_export_features": 5,
        "wasde_features": 5,
        "rin_features": 4,
        "news_features": 5,
        "total_minimum": n_symbols * 5 + 111 + 10 + 30 + 20 + 5 + 5 + 4 + 5,
    }


def validate_training_data(df, horizon: int, strict: bool = True) -> bool:
    """
    Validate that training DataFrame has all expected features.

    Args:
        df: Training DataFrame (before TimeSeriesDataFrame conversion)
        horizon: Forecast horizon
        strict: If True, fail on missing features

    Returns:
        True if valid

    Raises:
        ValueError: If strict=True and features are missing
    """
    expected = get_expected_feature_counts(horizon)

    # Count actual features by category
    cols = set(df.columns)

    # Symbol features (e.g., BTC_close, ES_high)
    symbol_cols = [
        c
        for c in cols
        if "_" in c and c.split("_")[1] in ["open", "high", "low", "close", "volume"]
    ]

    # FRED features (from fred_observations_1d pivoted wide)
    # These don't have a consistent prefix, so we count non-categorized columns

    # Weather features
    weather_cols = [c for c in cols if c.startswith("weather_")]

    # FX features
    fx_cols = [c for c in cols if c.startswith("fx_")]

    # COT features
    cot_cols = [c for c in cols if c.startswith("cot_")]

    # USDA features
    usda_cols = [c for c in cols if c.startswith("usda_") or c.startswith("wasde_")]

    # RIN features
    rin_cols = [c for c in cols if c.startswith("rin_")]

    # News features
    news_cols = [c for c in cols if c.startswith("news_")]

    logger.info("=" * 70)
    logger.info("TRAINING DATA FEATURE VALIDATION")
    logger.info("=" * 70)
    logger.info(
        f"  Symbol features: {len(symbol_cols)} (expected ~{expected['symbol_features']})"
    )
    logger.info(
        f"  Weather features: {len(weather_cols)} (expected {expected['weather_features']})"
    )
    logger.info(f"  FX features: {len(fx_cols)} (expected {expected['fx_features']})")
    logger.info(
        f"  COT features: {len(cot_cols)} (expected {expected['cot_features']})"
    )
    logger.info(
        f"  USDA/WASDE features: {len(usda_cols)} (expected {expected['usda_export_features'] + expected['wasde_features']})"
    )
    logger.info(
        f"  RIN features: {len(rin_cols)} (expected {expected['rin_features']})"
    )
    logger.info(
        f"  News features: {len(news_cols)} (expected {expected['news_features']})"
    )
    logger.info(f"  Total columns: {len(cols)}")
    logger.info("=" * 70)

    # Check for critical missing categories
    missing = []
    if len(symbol_cols) < expected["symbol_features"] * 0.9:  # Allow 10% tolerance
        missing.append(
            f"symbol_features ({len(symbol_cols)} < {expected['symbol_features']})"
        )
    if len(weather_cols) < expected["weather_features"]:
        missing.append(
            f"weather_features ({len(weather_cols)} < {expected['weather_features']})"
        )
    if len(fx_cols) < expected["fx_features"]:
        missing.append(f"fx_features ({len(fx_cols)} < {expected['fx_features']})")
    if len(cot_cols) < expected["cot_features"]:
        missing.append(f"cot_features ({len(cot_cols)} < {expected['cot_features']})")
    if len(rin_cols) < expected["rin_features"]:
        missing.append(f"rin_features ({len(rin_cols)} < {expected['rin_features']})")
    if len(news_cols) < expected["news_features"]:
        missing.append(
            f"news_features ({len(news_cols)} < {expected['news_features']})"
        )

    if missing and strict:
        error_msg = f"Training data missing features: {missing}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    return len(missing) == 0


def require_all_data(conn, horizon: int = 5):
    """
    Decorator/context manager to require all data before training.

    Usage:
        with require_all_data(conn, horizon=5):
            # Training code here
            pass
    """

    class DataRequirementContext:
        def __enter__(self):
            validate_data_completeness(conn, strict=True)
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    return DataRequirementContext()
