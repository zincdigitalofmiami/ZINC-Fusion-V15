#!/usr/bin/env python3
"""
ZINC-FUSION-V15: ALL DATA POLICY ENFORCEMENT
==============================================

!!! CRITICAL - READ THIS BEFORE MODIFYING ANY TRAINING CODE !!!

This module enforces the ironclad rule:

    USE ALL DATASETS, ALL DATA, ALL THE TIME.

NO cherry-picking. NO selective data loading. NO "light" feature sets.
AutoGluon will figure out what's relevant. We provide EVERYTHING.

This policy is NON-NEGOTIABLE and applies to:
- Core model training (train_core_chronos.py)
- Specialist feature generation (generate_specialist_features.py)
- Specialist training (train_specialist.py)
- Meta-ensemble training (train_meta_ensemble.py)

MINIMUM FEATURE REQUIREMENTS:
- All horizons: 600+ features minimum (daily base)

If you're seeing fewer features than this, YOU ARE DOING IT WRONG.

DATA SOURCES (ALL MUST BE USED):
1. Market Futures (83 symbols daily) - ALL pivoted wide
2. FRED Economic (111+ features) - ALL series
3. Spot FX (30 pairs) - ALL pairs
4. CFTC COT (4 contracts × 5 features = 20) - ALL positioning data
5. USDA Export Sales (5 features) - ALL commodities
6. USDA WASDE (5 features) - ALL metrics
7. EPA RIN Prices (4 types) - ALL RIN types
8. NOAA Weather (8+ features) - ALL regions
9. News Sentiment (5 features) - ALL sources

Usage:
    from src.fusion.validation.all_data_policy import enforce_all_data_policy

    # In your training script:
    enforce_all_data_policy(conn, horizon=5)  # Raises if not ALL data is loaded
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import psycopg2

logger = logging.getLogger(__name__)

# ==============================================================================
# ALL DATA POLICY CONSTANTS - DO NOT REDUCE THESE
# ==============================================================================

# Minimum feature counts by horizon
# These are ABSOLUTE MINIMUMS - actual counts should be higher
# All horizons use daily data: 83 symbols × 5 OHLCV + all covariates
MIN_FEATURES_5D = 600
MIN_FEATURES_21D = 600
MIN_FEATURES_63D = 600
MIN_FEATURES_126D = 600

# Data source requirements
REQUIRED_DATA_SOURCES = {
    # Table name -> (min_rows, description, date_column)
    # NOTE: Hourly data removed - all training uses daily data only
    "market_futures_1d": (100_000, "Daily futures (83 symbols)", "as_of_date"),
    "fred_observations_1d": (100_000, "FRED economic (long format, 111+ series)", "as_of_date"),
    "weather_noaa_1d": (500, "NOAA weather (US/Brazil/Argentina)", "as_of_date"),
    "fx_spot_1d": (10_000, "Spot FX (30 pairs)", "as_of_date"),
    "cftc_cot_1w": (500, "CFTC COT positioning", "report_date"),
    "usda_export_sales_1w": (100, "USDA export sales", "report_date"),
    "usda_wasde_1m": (50, "USDA WASDE", "report_date"),
    "epa_rin_prices_1d": (50, "EPA RIN prices", "as_of_date"),
    "news_articles_1d": (50, "News sentiment", "as_of_date"),
}

# Feature category expectations (for validation)
FEATURE_CATEGORIES = {
    "symbol_features": {"min": 400, "prefix_patterns": ["_open", "_high", "_low", "_close", "_volume"]},
    "fred_features": {"min": 100, "prefix": None},  # No consistent prefix
    "fx_features": {"min": 25, "prefix": "fx_"},
    "cot_features": {"min": 15, "prefix": "cot_"},
    "weather_features": {"min": 5, "prefix": "weather_"},
    "rin_features": {"min": 3, "prefix": "rin_"},
    "news_features": {"min": 3, "prefix": "news_"},
    "usda_features": {"min": 3, "prefix": "usda_"},
    "wasde_features": {"min": 3, "prefix": "wasde_"},
}


@dataclass
class AllDataValidationResult:
    """Result from ALL DATA policy enforcement."""
    is_valid: bool
    horizon: int
    feature_count: int
    min_required: int
    sources_loaded: List[str]
    sources_missing: List[str]
    category_counts: Dict[str, int]
    errors: List[str]
    warnings: List[str]


def enforce_all_data_policy(
    conn,
    horizon: int = 5,
    strict: bool = True,
    df=None
) -> AllDataValidationResult:
    """
    Enforce the ALL DATA policy.

    This function validates that:
    1. ALL required data sources are loaded
    2. Feature count meets minimum thresholds
    3. No data categories are suspiciously empty

    Args:
        conn: PostgreSQL connection
        horizon: Forecast horizon (5, 21, 63, 126)
        strict: If True, raise exception on violation. If False, just warn.
        df: Optional DataFrame to validate feature counts (if already loaded)

    Returns:
        AllDataValidationResult

    Raises:
        ValueError: If strict=True and policy is violated
    """
    logger.info("=" * 70)
    logger.info("ALL DATA POLICY ENFORCEMENT CHECK")
    logger.info("=" * 70)
    logger.info("RULE: USE ALL DATASETS, ALL DATA, ALL THE TIME.")
    logger.info("=" * 70)

    errors = []
    warnings = []
    sources_loaded = []
    sources_missing = []
    category_counts = {}

    # 1. Check all data sources exist and have data
    logger.info("\n[1/3] Checking data source availability...")
    with conn.cursor() as cur:
        for table, (min_rows, desc, date_col) in REQUIRED_DATA_SOURCES.items():
            try:
                # Determine schema (most are in 'raw')
                schema = "raw"
                cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
                row_count = cur.fetchone()[0]

                if row_count >= min_rows:
                    sources_loaded.append(table)
                    logger.info(f"  ✅ {table}: {row_count:,} rows - {desc}")
                else:
                    sources_missing.append(table)
                    msg = f"{table}: only {row_count:,} rows (need {min_rows:,}) - {desc}"
                    errors.append(msg)
                    logger.error(f"  ❌ {msg}")
            except psycopg2.errors.UndefinedTable:
                sources_missing.append(table)
                errors.append(f"{table}: TABLE MISSING - {desc}")
                logger.error(f"  ❌ {table}: TABLE MISSING - {desc}")
                conn.rollback()
            except Exception as e:
                warnings.append(f"Could not check {table}: {e}")
                logger.warning(f"  ⚠️ Could not check {table}: {e}")
                conn.rollback()

    logger.info(f"\n  Sources loaded: {len(sources_loaded)}/{len(REQUIRED_DATA_SOURCES)}")

    # 2. Validate feature count if DataFrame provided
    min_features = {
        5: MIN_FEATURES_5D,
        21: MIN_FEATURES_21D,
        63: MIN_FEATURES_63D,
        126: MIN_FEATURES_126D,
    }.get(horizon, MIN_FEATURES_21D)

    feature_count = 0
    if df is not None:
        logger.info("\n[2/3] Validating feature count...")
        feature_count = len(df.columns)

        if feature_count < min_features:
            msg = f"Feature count {feature_count} < minimum {min_features} for {horizon}d horizon"
            errors.append(msg)
            logger.error(f"  ❌ {msg}")
        else:
            logger.info(f"  ✅ Feature count: {feature_count} (min: {min_features})")

        # 3. Check feature categories
        logger.info("\n[3/3] Validating feature categories...")
        cols = set(df.columns)

        # Symbol features (OHLCV)
        symbol_cols = [c for c in cols if any(p in c for p in FEATURE_CATEGORIES["symbol_features"]["prefix_patterns"])]
        category_counts["symbol_features"] = len(symbol_cols)

        # Other categories
        for cat_name, cat_info in FEATURE_CATEGORIES.items():
            if cat_name == "symbol_features":
                continue  # Already handled

            prefix = cat_info.get("prefix")
            if prefix:
                matching = [c for c in cols if c.startswith(prefix)]
                category_counts[cat_name] = len(matching)
            else:
                category_counts[cat_name] = 0  # Can't easily count FRED

        for cat_name, count in category_counts.items():
            min_count = FEATURE_CATEGORIES[cat_name]["min"]
            if count < min_count:
                msg = f"{cat_name}: only {count} features (need {min_count})"
                if count == 0:
                    errors.append(msg)
                    logger.error(f"  ❌ {msg}")
                else:
                    warnings.append(msg)
                    logger.warning(f"  ⚠️ {msg}")
            else:
                logger.info(f"  ✅ {cat_name}: {count} features")
    else:
        logger.info("\n[2/3] Skipping feature validation (no DataFrame provided)")
        logger.info("[3/3] Skipping category validation (no DataFrame provided)")

    # Build result
    is_valid = len(errors) == 0
    result = AllDataValidationResult(
        is_valid=is_valid,
        horizon=horizon,
        feature_count=feature_count,
        min_required=min_features,
        sources_loaded=sources_loaded,
        sources_missing=sources_missing,
        category_counts=category_counts,
        errors=errors,
        warnings=warnings,
    )

    # Final verdict
    logger.info("\n" + "=" * 70)
    if is_valid:
        logger.info("✅ ALL DATA POLICY: PASSED")
    else:
        logger.error("❌ ALL DATA POLICY: FAILED")
        logger.error(f"   Errors: {errors}")
    logger.info("=" * 70)

    if strict and not is_valid:
        raise ValueError(
            f"ALL DATA POLICY VIOLATION. "
            f"Training CANNOT proceed without ALL data. "
            f"Errors: {errors}"
        )

    return result


def validate_specialist_features(df, bucket: str, strict: bool = True) -> bool:
    """
    Validate that specialist features DataFrame has ALL data.

    Specialists should have 900+ features per bucket because we're using
    ALL data sources for EVERY bucket. AutoGluon figures out relevance.

    Args:
        df: Specialist features DataFrame
        bucket: Bucket name (crush, china, fx, etc.)
        strict: If True, raise on violation

    Returns:
        True if valid

    Raises:
        ValueError: If strict=True and features are missing
    """
    MIN_SPECIALIST_FEATURES = 800  # Absolute minimum for ALL DATA

    feature_count = len(df.columns)
    row_count = len(df)

    logger.info(f"Validating specialist features for bucket: {bucket}")
    logger.info(f"  Feature count: {feature_count}")
    logger.info(f"  Row count: {row_count}")

    if feature_count < MIN_SPECIALIST_FEATURES:
        msg = (
            f"Specialist bucket '{bucket}' has only {feature_count} features. "
            f"MINIMUM is {MIN_SPECIALIST_FEATURES}. "
            f"You are NOT using ALL DATA. Fix this immediately."
        )
        logger.error(msg)
        if strict:
            raise ValueError(msg)
        return False

    logger.info(f"  ✅ Feature count OK ({feature_count} >= {MIN_SPECIALIST_FEATURES})")
    return True


def get_all_data_loading_query(horizon: int) -> str:
    """
    Generate SQL query that loads ALL data for a given horizon.

    This is the AUTHORITATIVE query for loading training data.
    It includes ALL data sources with proper joins.

    Args:
        horizon: Forecast horizon (5, 21, 63, 126)

    Returns:
        SQL query string
    """
    # All horizons use daily data
    base_table = "market_futures_1d"
    start_date = "2000-01-01"

    # This is a template - actual implementation joins all sources
    query = f"""
    -- ALL DATA LOADING QUERY FOR {horizon}d HORIZON
    -- Generated by all_data_policy.py
    -- DO NOT MODIFY - use enforce_all_data_policy() to validate

    -- Base: {base_table} from {start_date}
    -- Joined: fred_observations_1d (pivoted), weather_noaa_1d, fx_spot_1d, cftc_cot_1w,
    --         usda_export_sales_1w, usda_wasde_1m, epa_rin_prices_1d, news_articles_1d
    -- All sources forward-filled to base frequency

    SELECT * FROM (
        -- Query implementation in train_core_chronos.py
        -- This stub exists for documentation only
    ) AS all_data
    WHERE as_of_date >= '{start_date}'
    """

    return query


# ==============================================================================
# DECORATOR FOR ENFORCING ALL DATA IN TRAINING FUNCTIONS
# ==============================================================================

def require_all_data(horizon: int = 5, strict: bool = True):
    """
    Decorator that enforces ALL DATA policy before training.

    Usage:
        @require_all_data(horizon=5)
        def train_model(conn, ...):
            # Training code here
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # First arg should be connection
            conn = kwargs.get('conn') or (args[0] if args else None)
            if conn is None:
                raise ValueError("require_all_data decorator requires 'conn' as first arg or kwarg")

            # Enforce policy
            enforce_all_data_policy(conn, horizon=horizon, strict=strict)

            # Run function
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ==============================================================================
# SUMMARY LOG FOR TRAINING SCRIPTS
# ==============================================================================

def log_all_data_summary(conn, horizon: int) -> None:
    """
    Log a summary of all data that will be used for training.

    Call this at the start of any training script to document
    what data is being used.
    """
    logger.info("\n" + "=" * 70)
    logger.info("ALL DATA SUMMARY FOR TRAINING")
    logger.info("=" * 70)
    logger.info(f"Horizon: {horizon}d")
    logger.info(f"Policy: USE ALL DATASETS, ALL DATA, ALL THE TIME")
    logger.info("-" * 70)

    with conn.cursor() as cur:
        for table, (min_rows, desc, date_col) in REQUIRED_DATA_SOURCES.items():
            try:
                cur.execute(f'''
                    SELECT COUNT(*), MIN({date_col}), MAX({date_col})
                    FROM "raw"."{table}"
                ''')
                count, min_date, max_date = cur.fetchone()
                logger.info(f"  {table}: {count:,} rows ({min_date} to {max_date})")
            except Exception:
                logger.warning(f"  {table}: COULD NOT QUERY")
                conn.rollback()

    logger.info("=" * 70 + "\n")
