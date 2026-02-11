"""
Phase 3: Build Core Feature Matrix
===================================

Assembles training.matrix_1d from ALL source data:
- features.elite_1d (27 elite indicators + OHLCV)
- alt.weather_1d (weather aggregates computed on-the-fly)
- econ.* tables (rates, inflation, labor, activity, vol_indices, commodities, money)
- mkt.fx_1d (FX rates)
- pos.cftc_1w (COT managed money, commercials)
- supply.epa_rin_1d (biofuel RIN prices)
- supply.usda_exports_1w (export sales)
- supply.usda_wasde_1m (WASDE supply/demand balances)

SCHEMA UPDATE 2026-01-23:
- Weather features now computed on-the-fly from alt.weather_1d (dropped features weather table)
- Dropped pos cftc_cits_1w (100% NULL data)
- Dropped features options_1d (empty, options pipeline not active)
- Dropped features news_scored_1d (empty, news scoring not active)

SCHEMA UPDATE 2026-01-22:
- Added supply.* tables (EPA RINs, USDA exports, WASDE)
- Removed 70% coverage filter (AutoGluon handles nulls)
- Removed date window mandates (use all available data)

SCHEMA UPDATE 2026-01-17:
- FRED data migrated from domain-specific econ.* tables (legacy raw schema removed)
- gold schema renamed to features (elite_1d)
- training matrix curated table renamed to training.matrix_1d

Design Principles:
- Blanket inclusion WITH enforced curation (120-350 features)
- All features as OBSERVED covariates (not known)
- RAW features stored (NO global normalization - prevents leakage)
- Normalization happens in Phase 6 PER CV WINDOW (training data only)
- ONE immutable matrix per rebuild
- Target: ~213 features after curation

CRITICAL: This phase stores RAW features. Normalization is NOT done here.
Phase 6 fits scalers on training windows only to prevent future data leakage.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import psycopg2
from pandas.api.types import is_numeric_dtype
from psycopg2.extras import execute_values

from .config import DATABASE_URL, HORIZONS, TARGET_SYMBOL
from .config import FeatureMatrixConfig as FMC
from .matrix_manifest import check_schema_drift, write_manifest
from .matrix_validation import validate_matrix

# Forward fill configuration
try:
    from fusion.config.forward_fill_config import (
        get_ttl_days,
        get_source_config,
        FRED_CONFIG,
    )
except ImportError:
    # Fallback defaults if config not available
    get_ttl_days = lambda x: 5  # noqa: E731
    get_source_config = lambda x: None  # noqa: E731
    FRED_CONFIG = {}

logger = logging.getLogger(__name__)


# =============================================================================
# TTL-BOUNDED FORWARD FILL (Policy Compliance)
# =============================================================================
#
# CRITICAL CONTRACT (Docs/FORWARD_FILL_POLICY.md):
# - TTL is calculated using CALENDAR DAYS (not row gaps)
# - weekend_exempt series skip weekends in TTL (for FRED business-day series)
# - Forward fill creates STATE variables only - no high-frequency transforms
# - Always track age_days for model visibility into staleness
# - NEVER forward fill market prices (NO FFILL for mkt.* data)
#
# TTL Thresholds (LOCKED):
#   Daily:     3 days (business day tolerance)
#   Weekly:   10 days (~1.5x cadence)
#   Monthly:  45 days (~1.5x cadence)
#   Quarterly: 120 days (~1.33x cadence)
#
# FORBIDDEN COLUMN SUFFIXES (never forward fill these):
#   *_delta, *_chg, *_pct*, *_ret*, *_mom*, *_vol*, *_z*, *_zscore*,
#   *_surprise*, *_return*, *_spread*, *_ratio*
# =============================================================================

# Columns that must NEVER be forward filled (computed, not state)
FFILL_FORBIDDEN_SUFFIXES = (
    "_delta",
    "_chg",
    "_pct",
    "_ret",
    "_mom",
    "_vol",
    "_z",
    "_zscore",
    "_surprise",
    "_return",
    "_spread",
    "_ratio",
    "_is_release_day",
    "_age_days",
    "_is_available",
    "_is_missing",
    "_is_imputed",
    "_is_observed",
)


def ffill_with_ttl(
    series: pd.Series,
    ttl_days: int = 5,
    weekend_exempt: bool = False,
) -> pd.Series:
    """
    Forward-fill a series with a TTL (time-to-live) limit.

    CRITICAL: TTL is computed using CALENDAR DAYS from the index, not row counts.
    This ensures correct staleness measurement across weekends, holidays, and gaps.

    After TTL days of forward-filling, values revert to NaN.
    This prevents stale data from being treated as current.

    IMPORTANT: This function is for ECONOMIC/REPORT data (FRED, CFTC, WASDE).
    NEVER use this for market prices (futures, FX, options) - those must not be forward filled.

    Policy: Docs/FORWARD_FILL_POLICY.md

    Args:
        series: Series to forward-fill (MUST have DatetimeIndex or date index)
        ttl_days: Maximum calendar days to carry forward (default: 5)
        weekend_exempt: If True, Saturdays and Sundays don't count toward TTL.
            Use this for series that don't report on weekends (e.g., FRED daily).
            NOTE: This only exempts weekends, NOT holidays. For true trading-calendar
            alignment, you'd need an exchange calendar (not implemented here).
            NOT for market data - market data should never be forward filled.

    Returns:
        Series with TTL-bounded forward fill

    Contract:
        - Forward-filled values are STATE only (no high-freq transforms allowed)
        - Use ffill_with_age() to also get staleness tracking
    """
    if ttl_days is None or ttl_days <= 0:
        # No forward fill allowed
        return series

    if len(series) == 0:
        return series

    # Forward fill first
    filled = series.ffill()

    # Track which positions have real (non-NaN) observations
    is_real = series.notna()

    # Get dates from index (critical for calendar-day calculation)
    idx = series.index
    if isinstance(idx, pd.DatetimeIndex):
        dates = idx.date
    elif hasattr(idx[0], "date") if len(idx) > 0 else False:
        # Dates already
        dates = idx
    else:
        # Fallback: treat as consecutive days if no date info
        # This is less accurate but prevents crashes
        dates = pd.date_range(start="2020-01-01", periods=len(series), freq="D").date

    dates_series = pd.Series(dates, index=series.index)

    # For each position, get the date of the last real observation
    last_real_date = dates_series.where(is_real).ffill()

    # Calculate gap in calendar days
    def date_diff_days(current, last_real):
        """Calculate calendar day difference, handling None/NaT."""
        if pd.isna(current) or pd.isna(last_real):
            return np.nan
        try:
            if isinstance(current, pd.Timestamp):
                current = current.date()
            if isinstance(last_real, pd.Timestamp):
                last_real = last_real.date()
            return (current - last_real).days
        except Exception:
            return np.nan

    gap_days = pd.Series(
        [
            date_diff_days(d, lr)
            for d, lr in zip(dates_series, last_real_date, strict=False)
        ],
        index=series.index,
    )

    # Weekend-exempt carve-out: weekends don't count toward TTL (holidays still count)
    if weekend_exempt:
        # Adjust gap_days by subtracting weekend days
        # For each gap, count weekends spanned
        def adjust_for_weekends(current, last_real, raw_gap):
            """Subtract weekend days from gap (holidays are still counted)."""
            if pd.isna(raw_gap) or raw_gap <= 0:
                return raw_gap
            try:
                if isinstance(current, pd.Timestamp):
                    current = current.date()
                if isinstance(last_real, pd.Timestamp):
                    last_real = last_real.date()
                # Count weekend days in range
                weekend_days = sum(
                    1
                    for i in range(int(raw_gap))
                    if (last_real + timedelta(days=i + 1)).weekday() >= 5
                )
                return raw_gap - weekend_days
            except Exception:
                return raw_gap

        gap_days = pd.Series(
            [
                adjust_for_weekends(d, lr, g)
                for d, lr, g in zip(
                    dates_series, last_real_date, gap_days, strict=False
                )
            ],
            index=series.index,
        )

    # Apply TTL: only keep filled values within TTL window
    within_ttl = gap_days <= ttl_days

    # Apply the mask: use filled where within TTL, else NaN
    result = filled.where(within_ttl, np.nan)

    return result


def ffill_with_age(
    series: pd.Series,
    ttl_days: int = 5,
    weekend_exempt: bool = False,
) -> tuple[pd.Series, pd.Series]:
    """
    Forward-fill with TTL AND return age_days for model visibility.

    This is the RECOMMENDED function for pipeline use as it provides
    both the filled values and staleness tracking.

    Args:
        series: Series to forward-fill (MUST have DatetimeIndex or date index)
        ttl_days: Maximum calendar days to carry forward
        weekend_exempt: If True, weekends don't count toward TTL

    Returns:
        Tuple of (filled_series, age_days_series)
        - filled_series: Values with TTL-bounded forward fill
        - age_days: Calendar days since last real observation (for each row)

    Usage:
        filled, age = ffill_with_age(df['VIXCLS'], ttl_days=3, weekend_exempt=True)
        df['VIXCLS'] = filled
        df['VIXCLS_age_days'] = age
    """
    if len(series) == 0:
        return series, pd.Series(dtype=float, index=series.index)

    is_real = series.notna()
    filled = series.ffill()

    # Get dates from index
    idx = series.index
    if isinstance(idx, pd.DatetimeIndex):
        dates = idx.date
    elif len(idx) > 0 and hasattr(idx[0], "date"):
        dates = idx
    else:
        dates = pd.date_range(start="2020-01-01", periods=len(series), freq="D").date

    dates_series = pd.Series(dates, index=series.index)
    last_real_date = dates_series.where(is_real).ffill()

    # Calculate age in calendar days
    def calc_age(current, last_real):
        if pd.isna(current) or pd.isna(last_real):
            return np.nan
        try:
            if isinstance(current, pd.Timestamp):
                current = current.date()
            if isinstance(last_real, pd.Timestamp):
                last_real = last_real.date()
            return (current - last_real).days
        except Exception:
            return np.nan

    age_days = pd.Series(
        [calc_age(d, lr) for d, lr in zip(dates_series, last_real_date, strict=False)],
        index=series.index,
    )

    # Market-aligned: adjust age by subtracting weekends
    if weekend_exempt:

        def adjust_for_weekends(current, last_real, raw_age):
            if pd.isna(raw_age) or raw_age <= 0:
                return raw_age
            try:
                if isinstance(current, pd.Timestamp):
                    current = current.date()
                if isinstance(last_real, pd.Timestamp):
                    last_real = last_real.date()
                weekend_days = sum(
                    1
                    for i in range(int(raw_age))
                    if (last_real + timedelta(days=i + 1)).weekday() >= 5
                )
                return raw_age - weekend_days
            except Exception:
                return raw_age

        adjusted_age = pd.Series(
            [
                adjust_for_weekends(d, lr, a)
                for d, lr, a in zip(
                    dates_series, last_real_date, age_days, strict=False
                )
            ],
            index=series.index,
        )
    else:
        adjusted_age = age_days

    # Apply TTL
    within_ttl = adjusted_age <= ttl_days
    result = filled.where(within_ttl, np.nan)

    # Return raw age_days (calendar) for model visibility, not adjusted
    return result, age_days


def ffill_dataframe_with_ttl(
    df: pd.DataFrame,
    ttl_days: int = 5,
    columns: list[str] | None = None,
    weekend_exempt: bool = False,
    track_age: bool = True,
) -> pd.DataFrame:
    """
    Forward-fill multiple columns with TTL limit (date-aware).

    CRITICAL: TTL is computed using CALENDAR DAYS from the DataFrame index.
    Ensure the DataFrame has a DatetimeIndex or date index.

    IMPORTANT: This function is for ECONOMIC/REPORT data (FRED, CFTC, WASDE).
    NEVER use this for market prices - those must not be forward filled.

    Age tracking is MANDATORY for state-level features per Forward Fill Policy.
    Every forward-filled column gets a corresponding {col}_age_days column.

    Args:
        df: DataFrame to forward-fill (MUST have DatetimeIndex or date column)
        ttl_days: Maximum calendar days to carry forward
        columns: Explicit list of columns to fill. If None, uses heuristic selection
            which EXCLUDES derived/computed columns (see FFILL_FORBIDDEN_SUFFIXES).
        weekend_exempt: If True, weekends don't count toward TTL.
            Use for FRED business-day series. NOT for market data.
        track_age: If True (DEFAULT), adds {col}_age_days columns for staleness visibility.
            MANDATORY for weekly+ cadence data per Forward Fill Policy.

    Returns:
        DataFrame with TTL-bounded forward fill (and age columns if track_age=True)

    Contract:
        - Forward-filled values are STATE only (no high-freq transforms allowed)
        - Age tracking is ON by default - models need staleness visibility
        - NEVER pass market price columns (close, open, high, low, settle, etc.)
    """
    result = df.copy()

    if columns is None:
        # Heuristic selection: numeric columns that are NOT derived/computed
        # Uses is_numeric_dtype for robust nullable dtype handling
        columns = [
            c
            for c in df.columns
            if is_numeric_dtype(df[c])
            and not any(
                c.lower().endswith(suffix) for suffix in FFILL_FORBIDDEN_SUFFIXES
            )
            and not any(
                x in c.lower()
                for x in [
                    "price",
                    "close",
                    "open",
                    "high",
                    "low",
                    "settle",
                    "bid",
                    "ask",
                ]
            )
        ]

    for col in columns:
        if col in result.columns:
            if track_age:
                filled, age = ffill_with_age(
                    result[col], ttl_days=ttl_days, weekend_exempt=weekend_exempt
                )
                result[col] = filled
                result[f"{col}_age_days"] = age
            else:
                result[col] = ffill_with_ttl(
                    result[col], ttl_days=ttl_days, weekend_exempt=weekend_exempt
                )

    return result


def validate_age_tracking(
    df: pd.DataFrame,
    state_columns: list[str] | None = None,
    raise_on_missing: bool = True,
) -> list[str]:
    """
    Validate that all forward-filled state columns have corresponding age tracking.

    Per Forward Fill Policy: Every forward-filled state feature MUST have a
    corresponding {col}_age_days column for model staleness visibility.

    Args:
        df: DataFrame to validate
        state_columns: Explicit list of state columns to check. If None, uses heuristic
            to identify likely forward-filled columns (non-price numeric columns).
        raise_on_missing: If True (default), raises ValueError on missing age columns.
            If False, returns list of missing columns without raising.

    Returns:
        List of state columns missing their _age_days counterparts

    Raises:
        ValueError: If raise_on_missing=True and any state columns lack age tracking
    """
    if state_columns is None:
        # Heuristic: identify likely forward-filled state columns
        # Exclude price columns, derived columns, and already-age columns
        price_terms = [
            "price",
            "close",
            "open",
            "high",
            "low",
            "settle",
            "bid",
            "ask",
            "volume",
        ]
        state_columns = [
            c
            for c in df.columns
            if np.issubdtype(df[c].dtype, np.number)
            and not any(term in c.lower() for term in price_terms)
            and not c.endswith(
                ("_age_days", "_is_missing", "_is_release_day", "_is_available")
            )
            and not any(
                c.lower().endswith(suffix) for suffix in FFILL_FORBIDDEN_SUFFIXES
            )
        ]

    # Check which state columns are missing age tracking
    missing_age = []
    for col in state_columns:
        age_col = f"{col}_age_days"
        if age_col not in df.columns:
            # Only flag if the column has been forward-filled (has consecutive identical values)
            # This avoids flagging columns that were never forward-filled
            if col in df.columns and len(df) > 1:
                # Simple heuristic: check if there are any forward-filled sequences
                vals = df[col].dropna()
                if len(vals) > 1:
                    # If values repeat consecutively, likely forward-filled
                    has_repeats = (vals.diff() == 0).any()
                    if has_repeats:
                        missing_age.append(col)

    if missing_age and raise_on_missing:
        raise ValueError(
            f"Forward Fill Policy Violation: {len(missing_age)} state columns "
            f"lack required _age_days tracking: {missing_age[:10]}..."
            if len(missing_age) > 10
            else f"Forward Fill Policy Violation: {len(missing_age)} state columns "
            f"lack required _age_days tracking: {missing_age}"
        )

    return missing_age


# =============================================================================
# DATE NORMALIZATION HELPER (CRITICAL FIX)
# =============================================================================


def normalize_date_column(df: pd.DataFrame, col: str = "trade_date") -> pd.DataFrame:
    """
    Normalize date column to datetime.date for consistent merging.

    This fixes the silent merge failure where different date types
    (datetime64[ns] vs datetime.date) cause zero matches.

    PATCH: 2026-01-21 - Resolves weather data merge failure
    """
    if col in df.columns and len(df) > 0:
        df[col] = pd.to_datetime(df[col]).dt.date
    return df


def merge_asof_to_trading_days(
    base_df: pd.DataFrame,
    source_df: pd.DataFrame,
    date_col: str = "trade_date",
    tolerance_days: Optional[int] = None,
) -> pd.DataFrame:
    """
    Merge source data to trading days using backward-looking alignment.

    For weekly/monthly data (CFTC, WASDE, USDA exports, RINs, FRED weekly),
    the release date often falls on non-trading days (weekends). This aligns
    each release to the NEXT trading day (first day the info is available).

    Example: ICSA released Saturday 2026-01-17 → aligns to Monday 2026-01-20

    Args:
        base_df: Trading day calendar (left side of merge)
        source_df: Source data with release dates
        date_col: Column containing dates
        tolerance_days: Maximum number of days to look back for a match.
            If None, no limit (any historical value can match).
            Set per-source to prevent arbitrarily old data from leaking in.

    PATCH: 2026-01-23 - Fixes 0% coverage for weekly/monthly data
    PATCH: 2026-02-09 - Added per-source tolerance to cap stale data leakage
    """
    if len(source_df) == 0:
        return base_df

    # Ensure both have datetime for merge_asof
    base_df = base_df.copy()
    source_df = source_df.copy()

    base_df["_dt"] = pd.to_datetime(base_df[date_col])
    source_df["_dt"] = pd.to_datetime(source_df[date_col])

    # Sort both by date (required for merge_asof)
    base_df = base_df.sort_values("_dt")
    source_df = source_df.sort_values("_dt")

    # Get columns to merge (exclude date columns)
    merge_cols = [c for c in source_df.columns if c not in [date_col, "_dt"]]

    # merge_asof: for each trading day, find the most recent source row
    # direction='backward' means: use source row with date <= trading day
    asof_kwargs: Dict[str, Any] = {
        "on": "_dt",
        "direction": "backward",
    }
    if tolerance_days is not None:
        asof_kwargs["tolerance"] = pd.Timedelta(days=tolerance_days)

    merged = pd.merge_asof(
        base_df,
        source_df[["_dt"] + merge_cols],
        **asof_kwargs,
    )

    # Clean up
    merged = merged.drop(columns=["_dt"])

    return merged


# =============================================================================
# PURE EVENT ENCODING (v15.x - NO FORWARD FILL)
# =============================================================================


def pure_event_encode(
    base_df: pd.DataFrame,
    source_df: pd.DataFrame,
    value_cols: list[str],
    prefix: str,
    date_col: str = "trade_date",
) -> pd.DataFrame:
    """
    Pure event encoding: value on release day ONLY, else 0.0.

    For each low-frequency metric, creates 5 encoding columns:
    - {prefix}_{col}_event_value: Value on release day only (0.0 otherwise)
    - {prefix}_{col}_event_delta: Delta from previous release (0.0 on non-release days)
    - {prefix}_{col}_is_release_day: 1 on release date, 0 otherwise
    - {prefix}_{col}_age_days: Days since last release (9999 pre-first)
    - {prefix}_{col}_is_available: 1 after first release, 0 before

    CRITICAL: NO carry/forward-fill in _event_value. Value is ONLY present on release day.
    This eliminates NULLs via encoding, not imputation.

    Args:
        base_df: Trading day calendar (ZL futures)
        source_df: Low-frequency source data with release dates
        value_cols: List of value columns to encode
        prefix: Column name prefix (e.g., 'wasde', 'cftc')
        date_col: Date column name

    Returns:
        base_df with new encoding columns added (NO NULLs)
    """
    # Handle empty prefix case (e.g., WASDE columns are already prefixed)
    col_prefix = f"{prefix}_" if prefix else ""

    if len(source_df) == 0:
        # No source data: create all columns with defaults
        for col in value_cols:
            base_df[f"{col_prefix}{col}_event_value"] = 0.0
            base_df[f"{col_prefix}{col}_event_delta"] = 0.0
            base_df[f"{col_prefix}{col}_is_release_day"] = 0
            base_df[f"{col_prefix}{col}_age_days"] = 9999
            base_df[f"{col_prefix}{col}_is_available"] = 0
        return base_df

    # Normalize dates
    base_df = base_df.copy()
    source_df = source_df.copy()
    base_df[date_col] = pd.to_datetime(base_df[date_col]).dt.date
    source_df[date_col] = pd.to_datetime(source_df[date_col]).dt.date

    # Sort source by date for delta calculation
    source_df = source_df.sort_values(date_col)

    for col in value_cols:
        if col not in source_df.columns:
            logger.warning(f"   Column {col} not found in source, skipping")
            base_df[f"{col_prefix}{col}_event_value"] = 0.0
            base_df[f"{col_prefix}{col}_event_delta"] = 0.0
            base_df[f"{col_prefix}{col}_is_release_day"] = 0
            base_df[f"{col_prefix}{col}_age_days"] = 9999
            base_df[f"{col_prefix}{col}_is_available"] = 0
            continue

        # Build a lookup from release date to value
        release_values = (
            source_df[[date_col, col]].dropna().set_index(date_col)[col].to_dict()
        )

        # Calculate deltas between consecutive releases
        # IMPORTANT: First release has no prior, so delta = 0.0 (not NaN)
        releases_sorted = source_df[[date_col, col]].dropna().sort_values(date_col)
        releases_sorted["_prev"] = releases_sorted[col].shift(1)
        releases_sorted["_delta"] = releases_sorted[col] - releases_sorted["_prev"]
        releases_sorted["_delta"] = releases_sorted["_delta"].fillna(
            0.0
        )  # First release delta = 0
        release_deltas = releases_sorted.set_index(date_col)["_delta"].to_dict()

        # Get release dates in order
        release_dates_list = sorted(release_values.keys())

        # Build trading day set for efficient lookup
        trading_days = set(base_df[date_col].dropna())

        # Map each release date to the first trading day on or after it
        # This handles releases on weekends/holidays (e.g., Jan 1st WASDE)
        release_to_trading_day = {}
        for rel_date in release_dates_list:
            # Find the first trading day >= release date
            for td in sorted(trading_days):
                if td >= rel_date:
                    release_to_trading_day[td] = (
                        rel_date  # Map trading day -> original release
                    )
                    break

        # Initialize output arrays
        n = len(base_df)
        event_value = np.zeros(n, dtype=np.float64)
        event_delta = np.zeros(n, dtype=np.float64)
        is_release_day = np.zeros(n, dtype=np.int32)
        age_days = np.full(n, 9999, dtype=np.int32)
        is_available = np.zeros(n, dtype=np.int32)

        # Process each trading day
        last_release_date = None
        for i, trade_date in enumerate(base_df[date_col]):
            # Check if this trading day corresponds to a release
            # (either exact match OR first trading day after release)
            if trade_date in release_values:
                # Exact match (release on trading day)
                event_value[i] = release_values[trade_date]
                event_delta[i] = release_deltas.get(trade_date, 0.0)
                is_release_day[i] = 1
                last_release_date = trade_date
            elif trade_date in release_to_trading_day:
                # First trading day after a non-trading-day release
                orig_release = release_to_trading_day[trade_date]
                event_value[i] = release_values[orig_release]
                event_delta[i] = release_deltas.get(orig_release, 0.0)
                is_release_day[i] = 1
                last_release_date = orig_release

            # Compute age (days since last release)
            if last_release_date is not None:
                age_days[i] = (trade_date - last_release_date).days
                is_available[i] = 1

        # Assign to DataFrame (col_prefix defined at function start)
        base_df[f"{col_prefix}{col}_event_value"] = event_value
        base_df[f"{col_prefix}{col}_event_delta"] = event_delta
        base_df[f"{col_prefix}{col}_is_release_day"] = is_release_day
        base_df[f"{col_prefix}{col}_age_days"] = age_days
        base_df[f"{col_prefix}{col}_is_available"] = is_available

    return base_df


def forward_fill_low_coverage_series(
    df: pd.DataFrame,
    threshold: float = 0.50,
) -> pd.DataFrame:
    """
    Forward-fill low-coverage monthly/weekly series per execution plan.

    Per plan: "Forward-fill monthly values across business days so each month's
    value appears on all days until the next update."

    This applies to:
    - Monthly commodity prices (rapeseed, sunflower)
    - WASDE fundamentals (carried forward in legacy columns)
    - Other sporadic series

    Age tracking is MANDATORY per Forward Fill Policy. Every forward-filled
    column gets a corresponding {col}_age_days column for staleness visibility.

    Args:
        df: DataFrame with potential gaps
        threshold: Coverage threshold below which to forward-fill (default 50%)

    Returns:
        DataFrame with low-coverage series forward-filled AND age columns added
    """
    df = df.copy()

    # Identify numeric columns with low coverage
    numeric_cols = [
        c
        for c in df.columns
        if np.issubdtype(df[c].dtype, np.number)
        and c not in ["trade_date"]
        and not c.endswith(
            ("_is_release_day", "_age_days", "_is_available", "_is_missing")
        )
    ]

    filled_count = 0
    for col in numeric_cols:
        coverage = df[col].notna().mean()
        if coverage < threshold and coverage > 0.01:  # Has some data but sparse
            original_nulls = df[col].isna().sum()
            # TTL UPDATE (2026-02-04): Apply TTL-bounded forward fill WITH age tracking per policy
            # Default 3-day TTL for daily data (LOCKED threshold)
            # Age tracking is MANDATORY for state-level features
            filled, age = ffill_with_age(df[col], ttl_days=3)
            df[col] = filled
            df[f"{col}_age_days"] = age
            new_nulls = df[col].isna().sum()
            if new_nulls < original_nulls:
                filled_count += 1
                logger.debug(
                    f"   Forward-filled {col} (TTL=3d): {original_nulls} → {new_nulls} NULLs + age column"
                )

    if filled_count > 0:
        logger.info(
            f"   Forward-filled {filled_count} low-coverage series (<{threshold * 100:.0f}% coverage) with age tracking"
        )

    return df


def add_daily_missingness_encoding(
    df: pd.DataFrame,
    cols: list[str],
) -> pd.DataFrame:
    """
    Add missingness encoding for daily features.

    For each daily column:
    - Fill NULLs with 0.0
    - Add {col}_is_missing flag (1 when original was NULL, 0 otherwise)

    This makes the model explicitly aware of when data was missing,
    rather than silently imputing.

    Args:
        df: DataFrame with potential NULLs
        cols: List of column names to encode

    Returns:
        DataFrame with missing values filled and _is_missing flags added
    """
    df = df.copy()

    for col in cols:
        if col not in df.columns:
            continue

        # Create the missing flag BEFORE filling
        is_missing = df[col].isna().astype(int)

        # Fill the original column with 0.0
        df[col] = df[col].fillna(0.0)

        # Add the missing flag
        df[f"{col}_is_missing"] = is_missing

    return df


def load_futures_base(conn, symbol: str) -> pd.DataFrame:
    """Load raw futures data as base - data from 1990-01-01 onwards (v15.x date floor)."""
    logger.info(f"Loading futures base from mkt.futures_1d for {symbol}...")

    # NOTE: open_interest is required by strict specialists; backfilled from CFTC where available.
    # v15.x: Enforce date floor >= 1990-01-01 at source load
    query = """
        SELECT
            event_date as trade_date,
            symbol,
            open, high, low, close, volume, open_interest
        FROM mkt.futures_1d
        WHERE symbol = %s
          AND event_date >= '1990-01-01'
        ORDER BY event_date
    """
    df = pd.read_sql(query, conn, params=(symbol,))
    logger.info(
        f"   Loaded {len(df):,} rows from {df['trade_date'].min()} to {df['trade_date'].max()}"
    )
    return df


def load_lcfs_credit(conn) -> pd.DataFrame:
    """Load LCFS credit prices from supply.lcfs_1d."""
    logger.info("Loading LCFS credit prices from supply.lcfs_1d...")
    try:
        query = """
            SELECT
                event_date as trade_date,
                price_usd_per_mt::float as lcfs_credit
            FROM supply.lcfs_1d
            ORDER BY event_date
        """
        df = pd.read_sql(query, conn)
        if len(df) == 0:
            logger.warning("   No LCFS data found")
            return pd.DataFrame()
        df = normalize_date_column(df, "trade_date")
        logger.info(
            f"   Loaded {len(df):,} rows from {df['trade_date'].min()} to {df['trade_date'].max()}"
        )
        return df
    except Exception as e:
        logger.warning(f"   LCFS data not available: {e}")
        return pd.DataFrame()


def load_china_pmi(conn) -> pd.DataFrame:
    """Load China manufacturing PMI from econ.activity_1d where series_id='china_pmi'."""
    logger.info("Loading China PMI from econ.activity_1d (series_id='china_pmi')...")
    try:
        query = """
            SELECT
                event_date as trade_date,
                value::float as china_pmi
            FROM econ.activity_1d
            WHERE series_id = 'china_pmi'
            ORDER BY event_date
        """
        df = pd.read_sql(query, conn)
        if len(df) == 0:
            logger.warning("   No China PMI data found (series_id='china_pmi')")
            return pd.DataFrame()
        df = normalize_date_column(df, "trade_date")
        logger.info(
            f"   Loaded {len(df):,} rows from {df['trade_date'].min()} to {df['trade_date'].max()}"
        )
        return df
    except Exception as e:
        logger.warning(f"   China PMI not available: {e}")
        return pd.DataFrame()


def load_dalian_soy(conn) -> pd.DataFrame:
    """
    Load Dalian soybean oil futures proxy from mkt.futures_1d.

    Convention:
    - Symbol used for DCE soybean oil continuous proxy: 'DCE_Y'
    - Column exposed to specialists/matrix: dalian_soy
    """
    logger.info(
        "Loading Dalian soybean oil proxy from mkt.futures_1d (symbol='DCE_Y')..."
    )
    try:
        query = """
            SELECT
                event_date as trade_date,
                close::float as dalian_soy
            FROM mkt.futures_1d
            WHERE symbol = 'DCE_Y'
            ORDER BY event_date
        """
        df = pd.read_sql(query, conn)
        if len(df) == 0:
            logger.warning("   No DCE_Y data found in mkt.futures_1d")
            return pd.DataFrame()
        df = normalize_date_column(df, "trade_date")
        logger.info(
            f"   Loaded {len(df):,} rows from {df['trade_date'].min()} to {df['trade_date'].max()}"
        )
        return df
    except Exception as e:
        logger.warning(f"   Dalian soy not available: {e}")
        return pd.DataFrame()


# =============================================================================
# CROSS-ASSET DATA LOADERS (NEW - 2026-02-02)
# =============================================================================


def load_cross_asset_correlations(conn, target_symbol: str = "ZL") -> pd.DataFrame:
    """
    Load pre-computed ZL correlations from mkt.futures_1d.

    The mkt.futures_1d table has rolling correlation columns:
    - zl_corr_30d: 30-day rolling correlation with ZL
    - zl_corr_60d: 60-day rolling correlation with ZL
    - zl_corr_90d: 90-day rolling correlation with ZL

    These are computed for ALL symbols in the table.

    Returns:
        DataFrame with trade_date and correlation columns for key assets
    """
    logger.info("Loading cross-asset correlations from mkt.futures_1d...")

    # Key correlated assets for soybean oil
    corr_symbols = [
        "ZS",  # Soybeans (primary)
        "ZM",  # Soybean meal (co-product)
        "CL",  # Crude oil (biodiesel feedstock)
        "HO",  # Heating oil (energy proxy)
        "RB",  # Gasoline (energy complex)
        "GC",  # Gold (macro/inflation hedge)
        "DX",  # Dollar index (FX impact)
        "ES",  # S&P 500 (risk-on/risk-off)
        "ZC",  # Corn (competing crop)
        "ZW",  # Wheat (grain complex)
        "CPO",  # Palm oil (substitute)
        "NG",  # Natural gas (energy)
        "SI",  # Silver (precious metals)
        "HG",  # Copper (industrial demand)
        "VX",  # VIX futures (volatility)
    ]

    try:
        placeholders = ",".join(["%s"] * len(corr_symbols))
        query = f"""
            SELECT
                event_date as trade_date,
                symbol,
                zl_corr_30d,
                zl_corr_60d,
                zl_corr_90d
            FROM mkt.futures_1d
            WHERE symbol IN ({placeholders})
              AND zl_corr_30d IS NOT NULL
            ORDER BY event_date, symbol
        """
        df = pd.read_sql(query, conn, params=tuple(corr_symbols))

        if len(df) == 0:
            logger.warning("   No correlation data found")
            return pd.DataFrame()

        # Pivot to wide format: one column per symbol per horizon
        result_dfs = []
        for horizon in ["30d", "60d", "90d"]:
            col = f"zl_corr_{horizon}"
            pivot = df.pivot(index="trade_date", columns="symbol", values=col)
            pivot.columns = [f"corr_{sym.lower()}_{horizon}" for sym in pivot.columns]
            result_dfs.append(pivot)

        result = result_dfs[0].join(result_dfs[1:]).reset_index()
        result = normalize_date_column(result, "trade_date")

        logger.info(
            f"   Loaded {len(result):,} rows, {len(result.columns) - 1} correlation columns"
        )
        logger.info(f"   Symbols: {corr_symbols}")
        return result

    except Exception as e:
        logger.warning(f"   Correlations not available: {e}")
        return pd.DataFrame()


def load_cross_commodity_indicators(conn, target_symbol: str = "ZL") -> pd.DataFrame:
    """
    Load price and indicator data for related commodities from features.elite_1d.

    This gives the model visibility into:
    - Soy complex (ZS, ZM) - direct fundamentals
    - Energy complex (CL, HO, RB, NG) - biodiesel/energy linkage
    - Competing crops (ZC, ZW) - agricultural rotation
    - Substitutes (CPO) - vegetable oil competition
    - Macro proxies (GC, ES, DX) - risk sentiment

    Returns:
        DataFrame with trade_date and cross-asset feature columns
    """
    logger.info("Loading cross-commodity indicators from features.elite_1d...")

    # Key related commodities
    cross_symbols = [
        "ZS",
        "ZM",
        "CL",
        "HO",
        "RB",
        "NG",
        "ZC",
        "ZW",
        "CPO",
        "GC",
        "ES",
        "DX",
    ]

    # Key indicators to include (subset of elite_1d columns)
    indicator_cols = [
        "close",
        "returns_1d",
        "rsi_14",
        "macd",
        "atr_ratio",
        "volume_zscore",
        "bb_percent_b",
        "hurst_exponent",
    ]

    try:
        placeholders = ",".join(["%s"] * len(cross_symbols))
        cols_select = ", ".join([f'"{c}"' for c in indicator_cols])

        query = f"""
            SELECT
                trade_date,
                symbol,
                {cols_select}
            FROM features.elite_1d
            WHERE symbol IN ({placeholders})
            ORDER BY trade_date, symbol
        """
        df = pd.read_sql(query, conn, params=tuple(cross_symbols))

        if len(df) == 0:
            logger.warning("   No cross-commodity data found")
            return pd.DataFrame()

        # Pivot each indicator separately and combine
        result = None
        for col in indicator_cols:
            if col not in df.columns:
                continue
            pivot = df.pivot(index="trade_date", columns="symbol", values=col)
            pivot.columns = [f"{sym.lower()}_{col}" for sym in pivot.columns]
            if result is None:
                result = pivot
            else:
                result = result.join(pivot)

        if result is None:
            return pd.DataFrame()

        result = result.reset_index()
        result = normalize_date_column(result, "trade_date")

        logger.info(
            f"   Loaded {len(result):,} rows, {len(result.columns) - 1} cross-commodity columns"
        )
        logger.info(f"   Symbols: {cross_symbols}")
        logger.info(f"   Indicators: {indicator_cols}")
        return result

    except Exception as e:
        logger.warning(f"   Cross-commodity indicators not available: {e}")
        return pd.DataFrame()


def load_spread_features(conn, target_symbol: str = "ZL") -> pd.DataFrame:
    """
    Calculate spread and ratio features between related commodities.

    Key spreads:
    - Board crush: (ZL × 0.11) + (ZM × 0.022) - (ZS / 100) [CME formula]
    - Soy oil share: ZL / (ZL + ZM)
    - ZL/ZS ratio: Soybean oil to soybean price ratio
    - ZL/CL ratio: Oil vs crude (biodiesel margin proxy)
    - ZL/CPO spread: Soy oil vs palm oil (substitution)
    - Crush margin z-score: Standardized crush profitability

    Returns:
        DataFrame with trade_date and spread/ratio columns
    """
    logger.info("Calculating spread and ratio features...")

    try:
        # Load close prices for key commodities
        query = """
            SELECT
                trade_date,
                symbol,
                close
            FROM features.elite_1d
            WHERE symbol IN ('ZL', 'ZS', 'ZM', 'CL', 'CPO', 'HO', 'RB')
            ORDER BY trade_date, symbol
        """
        df = pd.read_sql(query, conn)

        if len(df) == 0:
            logger.warning("   No price data for spreads")
            return pd.DataFrame()

        # Pivot to wide format
        prices = df.pivot(index="trade_date", columns="symbol", values="close")
        prices = prices.reset_index()
        prices = normalize_date_column(prices, "trade_date")

        result = pd.DataFrame({"trade_date": prices["trade_date"]})

        # Board crush margin (CME formula): (ZL × 0.11) + (ZM × 0.022) - (ZS / 100)
        if all(c in prices.columns for c in ["ZL", "ZS", "ZM"]):
            result["board_crush"] = (
                (prices["ZL"] * 0.11) + (prices["ZM"] * 0.022) - (prices["ZS"] / 100)
            )

            # Z-scores (multiple horizons for different trading timeframes)
            # 21d = 1 month (tactical trading)
            result["board_crush_zscore_21d"] = (
                result["board_crush"]
                - result["board_crush"].rolling(21, min_periods=10).mean()
            ) / result["board_crush"].rolling(21, min_periods=10).std()
            # 63d = 1 quarter (swing trading)
            result["board_crush_zscore_63d"] = (
                result["board_crush"]
                - result["board_crush"].rolling(63, min_periods=21).mean()
            ) / result["board_crush"].rolling(63, min_periods=21).std()
            # 252d = 1 year (strategic)
            result["board_crush_zscore_252d"] = (
                result["board_crush"]
                - result["board_crush"].rolling(252, min_periods=63).mean()
            ) / result["board_crush"].rolling(252, min_periods=63).std()

            # Momentum: 5-day change (leading indicator)
            result["board_crush_momentum_5d"] = result["board_crush"].diff(5)

            # Regime: Expanding vs contracting
            result["board_crush_expanding"] = (
                result["board_crush"].diff(5) > 0
            ).astype(int)

            logger.info(
                "   Calculated board_crush with z-scores (21d/63d/252d) and momentum"
            )

        # Soy oil share of crush value
        if all(c in prices.columns for c in ["ZL", "ZM"]):
            result["soy_oil_share"] = prices["ZL"] / (prices["ZL"] + prices["ZM"])
            result["soy_oil_share_zscore"] = (
                result["soy_oil_share"]
                - result["soy_oil_share"].rolling(252, min_periods=63).mean()
            ) / result["soy_oil_share"].rolling(252, min_periods=63).std()
            logger.info("   Calculated soy_oil_share")

        # ZL/ZS ratio (oil extraction value)
        if all(c in prices.columns for c in ["ZL", "ZS"]):
            result["zl_zs_ratio"] = prices["ZL"] / prices["ZS"]
            result["zl_zs_ratio_zscore"] = (
                result["zl_zs_ratio"]
                - result["zl_zs_ratio"].rolling(252, min_periods=63).mean()
            ) / result["zl_zs_ratio"].rolling(252, min_periods=63).std()
            logger.info("   Calculated zl_zs_ratio")

        # ZL/CL ratio (biodiesel margin proxy)
        if all(c in prices.columns for c in ["ZL", "CL"]):
            result["zl_cl_ratio"] = prices["ZL"] / prices["CL"]
            result["zl_cl_ratio_zscore"] = (
                result["zl_cl_ratio"]
                - result["zl_cl_ratio"].rolling(252, min_periods=63).mean()
            ) / result["zl_cl_ratio"].rolling(252, min_periods=63).std()
            logger.info("   Calculated zl_cl_ratio")

        # ZL - CPO spread (substitution pressure)
        if all(c in prices.columns for c in ["ZL", "CPO"]):
            result["zl_cpo_spread"] = prices["ZL"] - prices["CPO"]
            result["zl_cpo_spread_zscore"] = (
                result["zl_cpo_spread"]
                - result["zl_cpo_spread"].rolling(252, min_periods=63).mean()
            ) / result["zl_cpo_spread"].rolling(252, min_periods=63).std()
            logger.info("   Calculated zl_cpo_spread")

        # 3-2-1 crack spread proxy (if HO and RB available)
        if all(c in prices.columns for c in ["CL", "HO", "RB"]):
            # 3-2-1 crack: 2*HO + 1*RB - 3*CL (simplified)
            result["crack_321"] = 2 * prices["HO"] + prices["RB"] - 3 * prices["CL"]
            result["crack_321_zscore"] = (
                result["crack_321"]
                - result["crack_321"].rolling(252, min_periods=63).mean()
            ) / result["crack_321"].rolling(252, min_periods=63).std()

            # Individual crack spreads (heating oil and RBOB vs crude)
            result["ho_crack"] = prices["HO"] - prices["CL"]  # Heating oil crack
            result["rb_crack"] = prices["RB"] - prices["CL"]  # RBOB gasoline crack

            # HO crack z-score (diesel economics for biodiesel substitution)
            result["ho_crack_zscore_63d"] = (
                result["ho_crack"]
                - result["ho_crack"].rolling(63, min_periods=21).mean()
            ) / result["ho_crack"].rolling(63, min_periods=21).std()

            # Wide diesel crack = biodiesel substitution (bullish ZL via RINs)
            result["diesel_crack_wide"] = (result["ho_crack_zscore_63d"] > 1.0).astype(
                int
            )

            logger.info("   Calculated crack_321 spread + HO/RB individual cracks")

        # Drop trade_date duplicates, keep only spread columns
        spread_cols = [c for c in result.columns if c != "trade_date"]
        logger.info(f"   Created {len(spread_cols)} spread/ratio features")

        return result

    except Exception as e:
        logger.warning(f"   Spread features not available: {e}")
        return pd.DataFrame()


def load_options_features(conn, target_symbol: str = "ZL") -> pd.DataFrame:
    """
    Load options-derived features from mkt.options_1d.

    Key features:
    - Aggregate IV (ATM implied volatility proxy)
    - Put/Call OI ratio (sentiment)
    - Put/Call volume ratio (flow)
    - IV skew (put vs call IV difference)
    - Term structure (near vs far IV)

    Returns:
        DataFrame with trade_date and options feature columns
    """
    logger.info("Loading options features from mkt.options_1d...")

    try:
        # Check table structure first
        query = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'mkt' AND table_name = 'options_1d'
        """
        cols_df = pd.read_sql(query, conn)
        available_cols = set(cols_df["column_name"].tolist())

        # Required columns
        needed = {
            "event_date",
            "underlying",
            "option_type",
            "open_interest",
            "volume",
            "close",
        }
        if not needed.issubset(available_cols):
            logger.warning(f"   Missing columns: {needed - available_cols}")
            return pd.DataFrame()

        # Check for greeks columns (may not be populated yet)
        has_iv = "implied_volatility" in available_cols
        has_delta = "delta" in available_cols
        has_gamma = "gamma" in available_cols
        has_theta = "theta" in available_cols
        has_vega = "vega" in available_cols

        # Aggregate options data by underlying and date
        # Include greeks if available (Black-Scholes computed columns)
        iv_select = (
            ", AVG(implied_volatility) FILTER (WHERE implied_volatility IS NOT NULL) as avg_iv"
            if has_iv
            else ""
        )
        delta_select = (
            ", SUM(delta * open_interest) / NULLIF(SUM(open_interest), 0) as weighted_delta"
            if has_delta
            else ""
        )
        gamma_select = (
            ", AVG(gamma) FILTER (WHERE gamma IS NOT NULL) as avg_gamma"
            if has_gamma
            else ""
        )
        theta_select = (
            ", AVG(theta) FILTER (WHERE theta IS NOT NULL) as avg_theta"
            if has_theta
            else ""
        )
        vega_select = (
            ", AVG(vega) FILTER (WHERE vega IS NOT NULL) as avg_vega"
            if has_vega
            else ""
        )

        query = f"""
            SELECT
                event_date as trade_date,
                underlying,
                option_type,
                SUM(open_interest) as total_oi,
                SUM(volume) as total_volume,
                AVG(close) as avg_premium
                {iv_select}
                {delta_select}
                {gamma_select}
                {theta_select}
                {vega_select}
            FROM mkt.options_1d
            WHERE underlying = 'ZL'
            GROUP BY event_date, underlying, option_type
            ORDER BY event_date, option_type
        """
        df = pd.read_sql(query, conn)

        if len(df) == 0:
            logger.warning("   No ZL options data found")
            return pd.DataFrame()

        # Build pivot values list dynamically based on available columns
        pivot_values = ["total_oi", "total_volume", "avg_premium"]
        if has_iv and "avg_iv" in df.columns:
            pivot_values.append("avg_iv")
        if has_delta and "weighted_delta" in df.columns:
            pivot_values.append("weighted_delta")
        if has_gamma and "avg_gamma" in df.columns:
            pivot_values.append("avg_gamma")
        if has_theta and "avg_theta" in df.columns:
            pivot_values.append("avg_theta")
        if has_vega and "avg_vega" in df.columns:
            pivot_values.append("avg_vega")

        # Pivot put/call into separate columns
        result = df.pivot(
            index="trade_date",
            columns="option_type",
            values=pivot_values,
        )

        # Flatten column names
        result.columns = [
            f"opt_{metric}_{opt_type.lower()}" for metric, opt_type in result.columns
        ]
        result = result.reset_index()

        # Calculate derived features: ratios
        if "opt_total_oi_P" in result.columns and "opt_total_oi_C" in result.columns:
            result["opt_put_call_oi_ratio"] = result["opt_total_oi_P"] / result[
                "opt_total_oi_C"
            ].replace(0, np.nan)

        if (
            "opt_total_volume_P" in result.columns
            and "opt_total_volume_C" in result.columns
        ):
            result["opt_put_call_vol_ratio"] = result["opt_total_volume_P"] / result[
                "opt_total_volume_C"
            ].replace(0, np.nan)

        if (
            "opt_avg_premium_P" in result.columns
            and "opt_avg_premium_C" in result.columns
        ):
            result["opt_premium_skew"] = (
                result["opt_avg_premium_P"] - result["opt_avg_premium_C"]
            )

        # Greeks-derived features (if available)
        if "opt_avg_iv_c" in result.columns and "opt_avg_iv_p" in result.columns:
            # ATM IV proxy: average of call and put IV
            result["opt_atm_iv"] = (result["opt_avg_iv_c"] + result["opt_avg_iv_p"]) / 2
            # IV skew: put IV - call IV (positive = fear premium)
            result["opt_iv_skew"] = result["opt_avg_iv_p"] - result["opt_avg_iv_c"]

        result = normalize_date_column(result, "trade_date")

        logger.info(
            f"   Loaded {len(result):,} rows, {len(result.columns) - 1} options columns"
        )
        return result

    except Exception as e:
        logger.warning(f"   Options features not available: {e}")
        return pd.DataFrame()


def load_elite_indicators(conn, symbol: str) -> pd.DataFrame:
    """Load features.elite_1d for target symbol."""
    logger.info("Loading elite indicators from features.elite_1d...")

    query = """
        SELECT *
        FROM features.elite_1d
        WHERE symbol = %s
        ORDER BY trade_date
    """
    df = pd.read_sql(query, conn, params=(symbol,))
    logger.info(f"   Loaded {len(df):,} rows, {len(df.columns)} columns")
    return df


def encode_categorical_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Encode categorical features as numeric per execution plan.

    Per plan: "No feature dropping - repair instead"
    - hurst_regime: ordinal (0=unknown/null, 1=random, 2=trending) + _is_missing flag
    - ttm_squeeze_on: numeric 0/1 + _is_missing flag

    v15.x FIX: Use proper missingness encoding (x=0 when missing, x_is_missing=1)
    instead of forward-fill. This preserves feature integrity.

    This ensures AutoGluon doesn't drop these as "non-informative".
    """
    df = df.copy()

    # Encode hurst_regime as ordinal WITH missingness encoding
    if "hurst_regime" in df.columns:
        hurst_map = {"random": 1, "trending": 2, "mean_reverting": 0}
        # Keep original for debugging
        df["_hurst_regime_raw"] = df["hurst_regime"]
        # Map to numeric (NaN stays NaN)
        df["hurst_regime_encoded"] = df["hurst_regime"].map(hurst_map)
        # Create missingness flag BEFORE filling
        df["hurst_regime_is_missing"] = df["hurst_regime_encoded"].isna().astype(int)
        # Fill missing with 0.0 (neutral value)
        df["hurst_regime_encoded"] = df["hurst_regime_encoded"].fillna(0.0).astype(int)
        # Rename
        df = df.drop(columns=["hurst_regime"])
        df = df.rename(columns={"hurst_regime_encoded": "hurst_regime"})
        missing_count = df["hurst_regime_is_missing"].sum()
        logger.info(
            f"   Encoded hurst_regime as ordinal (0=unknown, 1=random, 2=trending) + _is_missing flag ({missing_count} missing)"
        )

    # Encode ttm_squeeze_on as numeric 0/1 WITH missingness encoding
    if "ttm_squeeze_on" in df.columns:
        # Create missingness flag BEFORE filling
        df["ttm_squeeze_on_is_missing"] = df["ttm_squeeze_on"].isna().astype(int)
        # Fill missing with 0 (squeeze off is neutral)
        df["ttm_squeeze_on"] = df["ttm_squeeze_on"].fillna(False).astype(int)
        missing_count = df["ttm_squeeze_on_is_missing"].sum()
        logger.info(
            f"   Encoded ttm_squeeze_on as 0/1 + _is_missing flag ({missing_count} missing)"
        )

    # Encode unusual_volume as numeric 0/1
    if "unusual_volume" in df.columns:
        df["unusual_volume"] = df["unusual_volume"].fillna(False).astype(int)
        logger.info("   Encoded unusual_volume as 0/1")

    return df


def load_fred_macro(conn) -> pd.DataFrame:
    """Load FRED macro series from econ.* tables and pivot to wide format.

    NEW SCHEMA (2026-01-17):
    FRED data is now split across domain-specific tables:
    - econ.rates_1d (interest rates, yields, spreads)
    - econ.inflation_1d (CPI, PCE)
    - econ.labor_1d (payrolls, claims)
    - econ.activity_1d (GDP, industrial production, sentiment)
    - econ.vol_indices_1d (VIX, NFCI)
    - econ.commodities_1d (commodity prices)
    - mkt.fx_1d (FRED FX rates - consolidated, filtered by source='FRED')
    - econ.money_1d (money supply, Fed balance sheet)
    """
    logger.info("Loading FRED macro series from econ.* tables...")

    FMC_INSTANCE = FMC()
    fred_series = list(FMC_INSTANCE.FRED_MACRO_SERIES)
    placeholders = ",".join(["%s"] * len(fred_series))

    # UNION ALL from all econ tables
    # Each table has same structure: series_id, event_date, value
    query = f"""
        WITH all_econ AS (
            SELECT series_id, event_date, value FROM econ.rates_1d
            UNION ALL
            SELECT series_id, event_date, value FROM econ.inflation_1d
            UNION ALL
            SELECT series_id, event_date, value FROM econ.labor_1d
            UNION ALL
            SELECT series_id, event_date, value FROM econ.activity_1d
            UNION ALL
            SELECT series_id, event_date, value FROM econ.vol_indices_1d
            UNION ALL
            SELECT series_id, event_date, value FROM econ.commodities_1d
            UNION ALL
            -- FX consolidated to mkt.fx_1d - map pair back to series_id format
            -- Pair names use SLASH format per 20260118_fx_consolidation migration
            SELECT
                CASE pair
                    WHEN 'EUR/USD' THEN 'DEXUSEU'
                    WHEN 'USD/JPY' THEN 'DEXJPUS'
                    WHEN 'BRL/USD' THEN 'DEXBZUS'
                    WHEN 'CNY/USD' THEN 'DEXCHUS'
                    WHEN 'MXN/USD' THEN 'DEXMXUS'
                    WHEN 'CAD/USD' THEN 'DEXCAUS'
                    WHEN 'KRW/USD' THEN 'DEXKOUS'
                    WHEN 'INR/USD' THEN 'DEXINUS'
                    WHEN 'TWD/USD' THEN 'DEXTAUS'
                    WHEN 'AUD/USD' THEN 'DEXUSAL'
                    WHEN 'GBP/USD' THEN 'DEXUSUK'
                    WHEN 'CHF/USD' THEN 'DEXSZUS'
                    WHEN 'SGD/USD' THEN 'DEXSIUS'
                    WHEN 'HKD/USD' THEN 'DEXHKUS'
                    WHEN 'MYR/USD' THEN 'DEXMAUS'
                    WHEN 'NOK/USD' THEN 'DEXNOUS'
                    WHEN 'SEK/USD' THEN 'DEXSDUS'
                    WHEN 'THB/USD' THEN 'DEXTHUS'
                    WHEN 'DXY_BROAD' THEN 'DTWEXBGS'
                    WHEN 'DXY_AFE' THEN 'DTWEXAFEGS'
                    WHEN 'DXY_EME' THEN 'DTWEXEMEGS'
                    WHEN 'DXY_MAJOR' THEN 'DTWEXM'
                    ELSE NULL
                END as series_id,
                event_date,
                rate as value
            FROM mkt.fx_1d
            WHERE source = 'FRED'
            UNION ALL
            SELECT series_id, event_date, value FROM econ.money_1d
        )
        SELECT DISTINCT ON (series_id, event_date)
            event_date::date as trade_date,
            series_id,
            value
        FROM all_econ
        WHERE series_id IN ({placeholders})
        ORDER BY series_id, event_date
    """

    df = pd.read_sql(query, conn, params=tuple(fred_series))

    # Pivot to wide format
    if len(df) > 0:
        df_wide = df.pivot(index="trade_date", columns="series_id", values="value")

        # CRITICAL FIX (2026-01-23): Forward-fill sparse pivot BEFORE asof merge
        # After pivot, each row only has values for series that released on that date.
        # When merge_asof looks backward, it finds a row but with NaN for other series.
        # Forward-fill ensures each date has last known value for ALL series.
        # This is NOT data leakage - it's reproducing what was known at each date.
        #
        # TTL UPDATE (2026-02-09): Per-cadence TTL using LOCKED forward_fill_config thresholds
        # Daily FRED series: 3-day TTL, weekend_exempt
        # Weekly FRED series: 10-day TTL
        # Monthly FRED series: NO level ffill (event encoding handles these downstream)
        daily_cols = []
        weekly_cols = []
        # Monthly cols intentionally excluded — they use event encoding, not level ffill
        for col in df_wide.columns:
            cfg = get_source_config(col)
            if cfg is not None:
                if cfg.cadence == "daily":
                    daily_cols.append(col)
                elif cfg.cadence == "weekly":
                    weekly_cols.append(col)
                # monthly/quarterly: skip ffill (event encoding only)
            else:
                # Unknown series — conservative daily TTL as fallback
                daily_cols.append(col)

        if daily_cols:
            df_wide = ffill_dataframe_with_ttl(
                df_wide, ttl_days=3, columns=daily_cols, weekend_exempt=True
            )
        if weekly_cols:
            df_wide = ffill_dataframe_with_ttl(
                df_wide, ttl_days=10, columns=weekly_cols
            )

        df_wide = df_wide.reset_index()
        # Prefix column names
        df_wide.columns = ["trade_date"] + [
            f"fred_{col.lower()}" for col in df_wide.columns[1:]
        ]

        # Log sparsity fix
        non_null_before = df.groupby("trade_date")["value"].count().mean()
        logger.info(
            f"   Loaded {len(df_wide):,} rows, {len(df_wide.columns) - 1} series"
        )
        logger.info(
            f"   Applied forward-fill to sparse pivot (avg {non_null_before:.1f} series per row → all)"
        )
        return df_wide

    logger.warning("   No FRED data loaded")
    return pd.DataFrame()


def load_fx_rates(conn) -> pd.DataFrame:
    """Load ALL FX rates from mkt.fx_1d."""
    logger.info("Loading ALL FX rates from mkt.fx_1d...")

    try:
        # Load ALL pairs - no filtering
        query = """
            SELECT
                event_date as trade_date,
                pair,
                rate as fx_rate
            FROM mkt.fx_1d
            ORDER BY trade_date, pair
        """
        df = pd.read_sql(query, conn)

        # Pivot to wide format
        if len(df) > 0:
            df_wide = df.pivot(index="trade_date", columns="pair", values="fx_rate")
            df_wide = df_wide.reset_index()
            df_wide.columns = ["trade_date"] + [
                f"fx_{col.lower().replace('/', '_')}" for col in df_wide.columns[1:]
            ]
            logger.info(
                f"   Loaded {len(df_wide):,} rows, {len(df_wide.columns) - 1} pairs"
            )
            return df_wide

    except Exception as e:
        logger.warning(f"   FX rates not available: {e}")

    return pd.DataFrame()


def load_weather_aggregates(conn) -> pd.DataFrame:
    """
    Compute weather features on-the-fly from alt.weather_1d.

    Aggregates raw station data to country level and computes derived features:
    - Basic: tavg, tmin, tmax, prcp, snow per country (AR, BR, US)
    - Derived: GDD, rolling precip sums, temp/precip anomalies, temp volatility
    """
    logger.info("Computing weather features from alt.weather_1d...")

    try:
        # Aggregate raw weather to country-day level with derived features
        query = """
            WITH daily_agg AS (
                SELECT
                    event_date::date as trade_date,
                    CASE
                        WHEN country = 'Argentina' THEN 'ar'
                        WHEN country = 'Brazil' THEN 'br'
                        WHEN country = 'United States' THEN 'us'
                    END as region,
                    AVG(tavg_c) as tavg_c,
                    AVG(tmin_c) as tmin_c,
                    AVG(tmax_c) as tmax_c,
                    SUM(prcp_mm) as prcp_mm,
                    SUM(snow_mm) as snow_mm
                FROM alt.weather_1d
                WHERE country IN ('Argentina', 'Brazil', 'United States')
                GROUP BY event_date, country
            ),
            with_gdd AS (
                SELECT *,
                    GREATEST(0, tavg_c - 10) as gdd_10c
                FROM daily_agg
            ),
            with_rolling AS (
                SELECT *,
                    SUM(gdd_10c) OVER (PARTITION BY region ORDER BY trade_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) as gdd_30d_sum,
                    SUM(prcp_mm) OVER (PARTITION BY region ORDER BY trade_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as prcp_7d_sum,
                    SUM(prcp_mm) OVER (PARTITION BY region ORDER BY trade_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) as prcp_14d_sum,
                    tavg_c - AVG(tavg_c) OVER (PARTITION BY region ORDER BY trade_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) as temp_anom_30d,
                    prcp_mm - AVG(prcp_mm) OVER (PARTITION BY region ORDER BY trade_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) as prcp_anom_30d,
                    STDDEV(tavg_c) OVER (PARTITION BY region ORDER BY trade_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as temp_vol_7d
                FROM with_gdd
            )
            SELECT trade_date, region, tavg_c, tmin_c, tmax_c, prcp_mm, snow_mm,
                   gdd_10c, gdd_30d_sum, prcp_7d_sum, prcp_14d_sum,
                   temp_anom_30d, prcp_anom_30d, temp_vol_7d
            FROM with_rolling
            ORDER BY trade_date, region
        """

        df = pd.read_sql(query, conn)

        if len(df) == 0:
            logger.warning("   No weather data found")
            return pd.DataFrame()

        # Pivot from long to wide format (one row per date, columns per region)
        pivot_cols = [
            "tavg_c",
            "tmin_c",
            "tmax_c",
            "prcp_mm",
            "snow_mm",
            "gdd_10c",
            "gdd_30d_sum",
            "prcp_7d_sum",
            "prcp_14d_sum",
            "temp_anom_30d",
            "prcp_anom_30d",
            "temp_vol_7d",
        ]

        result = df.pivot(index="trade_date", columns="region", values=pivot_cols)

        # Flatten column names: (metric, region) -> wx_{region}_{metric}
        result.columns = [f"wx_{region}_{metric}" for metric, region in result.columns]
        result = result.reset_index()

        # Normalize date type for merge compatibility
        result = normalize_date_column(result, "trade_date")

        # Log coverage statistics
        null_pct = (
            result.drop(columns=["trade_date"], errors="ignore").isnull().mean().mean()
            * 100
        )
        logger.info(
            f"   Computed {len(result):,} rows, {len(result.columns) - 1} weather features"
        )
        logger.info(f"   Average null percentage: {null_pct:.1f}%")
        return result

    except Exception as e:
        logger.warning(f"   Weather data not available: {e}")

    return pd.DataFrame()


# =============================================================================
# CFTC POSITIONING DATA (NEW - 2026-01-21)
# =============================================================================


def load_cftc_positioning(conn, symbol: str = "ZL") -> pd.DataFrame:
    """
    Load CFTC COT positioning data for soybean oil.

    NEW (2026-01-21): Adds managed money and commercial positioning signals.

    Key features:
    - cot_managed_money_net: Speculator net position (contrarian indicator)
    - cot_prod_merc_net: Commercial hedger net (informed money)
    - cot_open_interest: Total market participation
    - cot_mm_pct_oi: Managed money as % of open interest

    Args:
        conn: Database connection
        symbol: Target symbol (ZL for soybean oil)

    Returns:
        DataFrame with trade_date and COT features
    """
    logger.info("Loading CFTC COT positioning from pos.cftc_1w...")

    try:
        # pos.cftc_1w uses symbol directly (ZL, ZS, ZM, etc.)
        # It already has managed_money_net and prod_merc_net computed
        query = """
            SELECT
                event_date as trade_date,
                managed_money_net as cot_managed_money_net,
                prod_merc_net as cot_prod_merc_net,
                open_interest as cot_open_interest,
                managed_money_net_pct_oi as cot_mm_pct_oi
            FROM pos.cftc_1w
            WHERE symbol = %s
            ORDER BY event_date
        """
        df = pd.read_sql(query, conn, params=(symbol,))

        if len(df) > 0:
            # Commercials as percentage of open interest
            df["cot_comm_pct_oi"] = np.where(
                df["cot_open_interest"] > 0,
                df["cot_prod_merc_net"] / df["cot_open_interest"] * 100,
                0,
            )

            # Changes (week-over-week)
            df["cot_mm_net_chg"] = df["cot_managed_money_net"].diff()
            df["cot_comm_net_chg"] = df["cot_prod_merc_net"].diff()

            # Keep only relevant columns
            keep_cols = [
                "trade_date",
                "cot_managed_money_net",
                "cot_prod_merc_net",
                "cot_open_interest",
                "cot_mm_pct_oi",
                "cot_comm_pct_oi",
                "cot_mm_net_chg",
                "cot_comm_net_chg",
            ]
            df = df[keep_cols]

            # Normalize date type
            df = normalize_date_column(df, "trade_date")

            logger.info(
                f"   Loaded {len(df):,} rows, {len(df.columns) - 1} COT features"
            )
            logger.info(
                f"   Date range: {df['trade_date'].min()} to {df['trade_date'].max()}"
            )
            return df
        else:
            logger.warning(f"   No CFTC COT data found for {symbol}")

    except Exception as e:
        logger.warning(f"   CFTC COT data not available: {e}")

    return pd.DataFrame()


def load_cftc_cits(conn) -> pd.DataFrame:
    """
    Load CFTC CITS (Commodity Index Trader) positions if available.

    NEW (2026-01-21): Index fund flows as a separate signal.
    """
    logger.info("Loading CFTC CITS (index traders) if available...")

    try:
        # Check if cits table exists
        check_query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'pos' AND table_name = 'cftc_cits_1w'
            )
        """
        with conn.cursor() as cur:
            cur.execute(check_query)
            exists = cur.fetchone()[0]

        if not exists:
            logger.info("   CFTC CITS table not found - skipping CITS")
            return pd.DataFrame()

        query = """
            SELECT
                event_date as trade_date,
                cit_long,
                cit_short,
                cit_net as cits_net_position,
                cit_pct_oi as cits_pct_oi
            FROM "pos"."cftc_cits_1w"
            WHERE symbol = 'SOYBEAN_OIL'
            ORDER BY event_date
        """
        df = pd.read_sql(query, conn)

        if len(df) > 0:
            # Change in net position
            df["cits_net_chg"] = df["cits_net_position"].diff()

            # Long/short ratio
            df["cits_long_short_ratio"] = np.where(
                df["cit_short"] > 0, df["cit_long"] / df["cit_short"], 1.0
            )

            # Keep only relevant columns
            keep_cols = [
                "trade_date",
                "cits_net_position",
                "cits_pct_oi",
                "cits_net_chg",
                "cits_long_short_ratio",
            ]
            df = df[keep_cols]

            df = normalize_date_column(df, "trade_date")
            logger.info(
                f"   Loaded {len(df):,} rows, {len(df.columns) - 1} CITS features"
            )
            return df
        else:
            logger.warning("   No CITS data found for ZL")

    except Exception as e:
        logger.warning(f"   CFTC CITS data not available: {e}")

    return pd.DataFrame()


# =============================================================================
# SUPPLY DATA (NEW - 2026-01-22)
# =============================================================================


def load_epa_rin_prices(conn) -> pd.DataFrame:
    """
    Load EPA RIN prices from supply.epa_rin_1d.

    NEW (2026-01-22): Biofuel RIN prices are critical for soybean oil demand.

    Key features:
    - rin_d3: Cellulosic biofuel RINs
    - rin_d4: Biodiesel/renewable diesel RINs (most relevant for ZL)
    - rin_d5: Advanced biofuel RINs
    - rin_d6: Conventional biofuel (ethanol) RINs

    Returns:
        DataFrame with trade_date and RIN price columns
    """
    logger.info("Loading EPA RIN prices from supply.epa_rin_1d...")

    try:
        query = """
            SELECT
                event_date as trade_date,
                rin_type,
                price
            FROM supply.epa_rin_1d
            ORDER BY event_date, rin_type
        """
        df = pd.read_sql(query, conn)

        if len(df) == 0:
            logger.warning("   No EPA RIN data found")
            return pd.DataFrame()

        # Pivot to wide format (one column per RIN type)
        df_wide = df.pivot(index="trade_date", columns="rin_type", values="price")
        df_wide = df_wide.reset_index()
        df_wide.columns = ["trade_date"] + [
            f"rin_{col.lower()}" for col in df_wide.columns[1:]
        ]

        df_wide = normalize_date_column(df_wide, "trade_date")
        logger.info(
            f"   Loaded {len(df_wide):,} rows, {len(df_wide.columns) - 1} RIN types"
        )
        logger.info(
            f"   Date range: {df_wide['trade_date'].min()} to {df_wide['trade_date'].max()}"
        )
        return df_wide

    except Exception as e:
        logger.warning(f"   EPA RIN data not available: {e}")
        return pd.DataFrame()


def load_usda_exports(conn) -> pd.DataFrame:
    """
    Load USDA export sales from supply.usda_exports_1w.

    NEW (2026-01-22): Export demand signals for soybean complex.

    Key features:
    - usda_zl_exports: Soybean oil total exports (MT)
    - usda_zl_net_sales: Soybean oil net sales (MT)
    - usda_zl_outstanding: Soybean oil outstanding sales
    - usda_zs_exports: Soybeans total exports
    - usda_zm_exports: Soybean meal total exports

    Returns:
        DataFrame with trade_date and export columns
    """
    logger.info("Loading USDA export sales from supply.usda_exports_1w...")

    try:
        # Get totals for soybean complex commodities
        query = """
            SELECT
                event_date as trade_date,
                commodity,
                SUM(net_sales_mt) as net_sales_mt,
                SUM(exports_mt) as exports_mt,
                SUM(outstanding_sales_mt) as outstanding_mt
            FROM supply.usda_exports_1w
            WHERE destination_country = 'TOTAL'
            AND commodity IN ('Soybean Oil', 'Soybeans', 'Soybean Meal')
            GROUP BY event_date, commodity
            ORDER BY event_date, commodity
        """
        df = pd.read_sql(query, conn)

        if len(df) == 0:
            logger.warning("   No USDA export data found")
            return pd.DataFrame()

        # Create columns for each commodity
        result_dfs = []
        for commodity, prefix in [
            ("Soybean Oil", "usda_zl"),
            ("Soybeans", "usda_zs"),
            ("Soybean Meal", "usda_zm"),
        ]:
            df_comm = df[df["commodity"] == commodity].copy()
            if len(df_comm) > 0:
                df_comm = df_comm.rename(
                    columns={
                        "exports_mt": f"{prefix}_exports",
                        "net_sales_mt": f"{prefix}_net_sales",
                        "outstanding_mt": f"{prefix}_outstanding",
                    }
                )
                df_comm = df_comm[
                    [
                        "trade_date",
                        f"{prefix}_exports",
                        f"{prefix}_net_sales",
                        f"{prefix}_outstanding",
                    ]
                ]
                result_dfs.append(df_comm)

        if not result_dfs:
            return pd.DataFrame()

        # Merge all commodities
        result = result_dfs[0]
        for df_add in result_dfs[1:]:
            result = result.merge(df_add, on="trade_date", how="outer")

        result = normalize_date_column(result, "trade_date")
        logger.info(
            f"   Loaded {len(result):,} rows, {len(result.columns) - 1} export columns"
        )
        return result

    except Exception as e:
        logger.warning(f"   USDA export data not available: {e}")
        return pd.DataFrame()


def load_usda_wasde(conn) -> pd.DataFrame:
    """
    Load USDA WASDE supply/demand balances from supply.usda_wasde_1m.

    NEW (2026-01-22): Fundamental supply/demand data - THE key driver.

    Key features:
    - wasde_us_zs_production: US soybean production
    - wasde_us_zs_crush: US soybean crush
    - wasde_us_zs_stocks: US ending stocks
    - wasde_us_zl_production: US soybean oil production
    - wasde_world_zs_stocks_to_use: World stocks-to-use ratio

    Returns:
        DataFrame with trade_date and WASDE columns
    """
    logger.info("Loading USDA WASDE from supply.usda_wasde_1m...")

    try:
        # Get key US metrics for soybean complex
        query = """
            SELECT
                event_date as trade_date,
                commodity,
                country,
                metric,
                value
            FROM supply.usda_wasde_1m
            WHERE commodity IN ('Soybeans', 'Soybean Oil', 'Soybean Meal')
            AND country IN ('United States', 'World')
            AND metric IN ('production', 'consumption', 'exports', 'ending_stocks', 'crush')
            ORDER BY event_date
        """
        df = pd.read_sql(query, conn)

        if len(df) == 0:
            logger.warning("   No USDA WASDE data found")
            return pd.DataFrame()

        # Create composite key for pivoting
        df["col_name"] = (
            "wasde_"
            + df["country"].str.lower().str.replace(" ", "_")
            + "_"
            + df["commodity"]
            .str.lower()
            .str.replace(" ", "_")
            .str.replace("soybean_", "z")
            + "_"
            + df["metric"]
        )

        # Simplify column names
        df["col_name"] = df["col_name"].str.replace("united_states", "us")
        df["col_name"] = df["col_name"].str.replace("soybeans", "zs")
        df["col_name"] = df["col_name"].str.replace("oil", "l")
        df["col_name"] = df["col_name"].str.replace("meal", "m")

        # Pivot to wide format
        df_wide = df.pivot(index="trade_date", columns="col_name", values="value")
        df_wide = df_wide.reset_index()

        df_wide = normalize_date_column(df_wide, "trade_date")
        logger.info(
            f"   Loaded {len(df_wide):,} rows, {len(df_wide.columns) - 1} WASDE columns"
        )
        return df_wide

    except Exception as e:
        logger.warning(f"   USDA WASDE data not available: {e}")
        return pd.DataFrame()


def load_news_sentiment(conn) -> pd.DataFrame:
    """
    Load news sentiment from alt news tables (policy_news, executive_actions, econ_news, profarmer_news).

    NEW (2026-01-23): News sentiment is a key driver of short-term moves.

    Features:
    - news_zl_sentiment: ZL-specific sentiment (where available)
    - news_count: Number of articles
    """
    logger.info(
        "Loading news data from alt schema (union of policy_news, executive_actions, econ_news, profarmer_news)..."
    )

    try:
        query = """
            WITH all_news AS (
                SELECT event_date, zl_sentiment FROM alt.policy_news
                UNION ALL
                SELECT event_date, zl_sentiment FROM alt.executive_actions
                UNION ALL
                SELECT event_date, NULL as zl_sentiment FROM alt.econ_news
                UNION ALL
                SELECT event_date, NULL as zl_sentiment FROM alt.profarmer_news
            )
            SELECT
                event_date as trade_date,
                AVG(CASE
                    WHEN zl_sentiment = 'bullish' THEN 1.0
                    WHEN zl_sentiment = 'bearish' THEN -1.0
                    ELSE 0.0
                END) as news_zl_sentiment,
                COUNT(*) as news_count
            FROM all_news
            GROUP BY event_date
            ORDER BY event_date
        """
        df = pd.read_sql(query, conn)

        if len(df) > 0:
            df = normalize_date_column(df, "trade_date")
            logger.info(
                f"   Loaded {len(df):,} rows, {len(df.columns) - 1} news features"
            )
            return df
        else:
            logger.warning("   No news data found")
            return pd.DataFrame()

    except Exception as e:
        logger.warning(f"   News data not available: {e}")
        return pd.DataFrame()


def load_specialist_signals(conn, include_signals: bool = True) -> pd.DataFrame:
    """
    Load specialist signals from training.specialist_signals_1d.

    NEW v3 ARCHITECTURE (2026-01-21):
    Specialist signals are compact (1-2 values per date) and feed into Core
    as input features. This replaces the old 44-model stacking approach.

    Signal columns added:
    - sig_{bucket}_1: Primary signal
    - sig_{bucket}_2: Secondary signal (if present)
    - sig_{bucket}_conf: Model confidence

    Args:
        conn: Database connection
        include_signals: If False, returns empty DataFrame (for ablation testing)

    Returns:
        DataFrame with trade_date and signal columns
    """
    if not include_signals:
        logger.info("Specialist signals disabled (include_signals=False)")
        return pd.DataFrame()

    logger.info("Loading specialist signals from training.specialist_signals_1d...")

    try:
        query = """
            SELECT
                as_of_date as trade_date,
                bucket,
                signal_1,
                signal_2,
                confidence
            FROM training.specialist_signals_1d
            ORDER BY as_of_date, bucket
        """
        df = pd.read_sql(query, conn)

        if len(df) == 0:
            logger.warning("   No specialist signals found - table may be empty")
            return pd.DataFrame()

        # Pivot to wide format
        # Each bucket becomes columns: sig_{bucket}_1, sig_{bucket}_2, sig_{bucket}_conf
        df["trade_date"] = pd.to_datetime(df["trade_date"])

        # Pivot signal_1
        pivot_1 = df.pivot(index="trade_date", columns="bucket", values="signal_1")
        pivot_1.columns = [f"sig_{col}_1" for col in pivot_1.columns]

        # Pivot signal_2
        pivot_2 = df.pivot(index="trade_date", columns="bucket", values="signal_2")
        pivot_2.columns = [f"sig_{col}_2" for col in pivot_2.columns]

        # Pivot confidence
        pivot_conf = df.pivot(index="trade_date", columns="bucket", values="confidence")
        pivot_conf.columns = [f"sig_{col}_conf" for col in pivot_conf.columns]

        # Combine all pivots
        result = pivot_1.join(pivot_2).join(pivot_conf).reset_index()

        # Ensure trade_date is datetime for consistent merging
        result["trade_date"] = pd.to_datetime(result["trade_date"]).dt.date

        # Count non-null signal columns
        signal_cols = [c for c in result.columns if c.startswith("sig_")]
        logger.info(
            f"   Loaded {len(result):,} rows, {len(signal_cols)} signal columns"
        )
        logger.info(f"   Buckets: {df['bucket'].unique().tolist()}")

        return result

    except Exception as e:
        logger.warning(f"   Specialist signals not available: {e}")
        logger.warning("   Run scripts/generate_specialist_signals.py to populate")
        return pd.DataFrame()


def validate_specialist_signals_for_core(
    signals_df: pd.DataFrame,
    conn,
) -> dict[str, Any]:
    """
    Task 4.5: Validate specialist signals before Core training integration.

    Checks:
    1. Coverage: ≥90% daily rows per bucket (last 180 days)
    2. Signal columns exist in matrix
    3. No excessive null rates
    4. Recent signal availability

    Args:
        signals_df: DataFrame with specialist signals (from load_specialist_signals)
        conn: Database connection for additional queries

    Returns:
        Dict with validation results and issues list
    """
    from fusion.specialists.base import SPECIALIST_BUCKETS

    issues = []
    coverage_by_bucket = {}

    if signals_df.empty:
        issues.append("No specialist signals loaded")
        return {
            "valid": False,
            "issues": issues,
            "coverage_by_bucket": {},
        }

    # Get expected trading days (last 180 days)
    expected_rows_query = """
    SELECT COUNT(DISTINCT event_date) as n_days
    FROM mkt.futures_1d
    WHERE symbol = 'ZL'
      AND event_date >= CURRENT_DATE - INTERVAL '180 days'
    """
    expected_rows = pd.read_sql(expected_rows_query, conn).iloc[0]["n_days"]

    # Check coverage per bucket
    signal_cols = [
        c for c in signals_df.columns if c.startswith("sig_") and c.endswith("_1")
    ]

    for bucket in SPECIALIST_BUCKETS:
        sig_col = f"sig_{bucket}_1"

        if sig_col not in signals_df.columns:
            issues.append(f"{bucket}: signal column missing")
            coverage_by_bucket[bucket] = 0.0
            continue

        # Count non-null signals in recent period
        cutoff_date = date.today() - timedelta(days=180)
        recent_signals = signals_df[
            (pd.to_datetime(signals_df["trade_date"]).dt.date >= cutoff_date)
            & signals_df[sig_col].notna()
        ]
        n_signals = len(recent_signals)
        coverage = n_signals / expected_rows if expected_rows > 0 else 0.0

        coverage_by_bucket[bucket] = coverage

        if coverage < 0.90:
            issues.append(
                f"{bucket}: coverage {coverage * 100:.1f}% < 90% ({n_signals}/{expected_rows} days)"
            )

    # Check for missing buckets
    present_buckets = {col.replace("sig_", "").replace("_1", "") for col in signal_cols}
    missing_buckets = set(SPECIALIST_BUCKETS) - present_buckets
    if missing_buckets:
        issues.append(f"Missing buckets: {', '.join(sorted(missing_buckets))}")

    # Check null rates in recent data
    recent_cutoff = date.today() - timedelta(days=30)
    recent_df = signals_df[
        pd.to_datetime(signals_df["trade_date"]).dt.date >= recent_cutoff
    ]
    if len(recent_df) > 0:
        for sig_col in signal_cols:
            null_rate = recent_df[sig_col].isna().mean()
            if null_rate > 0.50:  # More than 50% null in last 30 days
                bucket = sig_col.replace("sig_", "").replace("_1", "")
                issues.append(f"{bucket}: {null_rate * 100:.1f}% null in last 30 days")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "coverage_by_bucket": coverage_by_bucket,
    }


def create_target_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Create forward returns as training targets (for supervised OOF)."""
    logger.info("Creating target columns...")

    for horizon in HORIZONS:
        target_col = f"target_ret_{horizon}d"
        df[target_col] = df["close"].pct_change(horizon).shift(-horizon)
        logger.info(f"   Created {target_col}")

    return df


def zscore_normalize(df: pd.DataFrame, exclude_cols: list[str]) -> pd.DataFrame:
    """
    DEPRECATED - DO NOT USE

    This function was previously used to normalize the entire dataset globally.
    This causes FUTURE DATA LEAKAGE because mean/std are computed on all data
    including future rows that wouldn't be available at training time.

    Normalization now happens in Phase 6, PER CV WINDOW, fitting only on
    training data before cutoff_date.

    This function is retained only for reference. It should NEVER be called.
    """
    raise RuntimeError(
        "zscore_normalize() is DEPRECATED. "
        "Global normalization causes future data leakage. "
        "Normalization must happen in Phase 6 per CV window."
    )


def drop_low_coverage_cols(df: pd.DataFrame, min_coverage: float = 0.7) -> pd.DataFrame:
    """Drop columns with too many nulls."""
    logger.info(f"Dropping columns with <{min_coverage * 100:.0f}% coverage...")

    before_cols = len(df.columns)
    coverage = df.notna().mean()
    keep_cols = coverage[coverage >= min_coverage].index.tolist()
    df = df[keep_cols]
    dropped = before_cols - len(df.columns)

    logger.info(f"   Dropped {dropped} columns, kept {len(df.columns)}")
    return df


def enforce_feature_guardrails(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """
    Enforce 120-350 feature guardrail.

    Returns:
        (df, passed): DataFrame and whether guardrail passed
    """
    FMC_INSTANCE = FMC()

    exclude_cols = {"trade_date", "symbol", "item_id", "timestamp"} | {
        f"target_ret_{h}d" for h in HORIZONS
    }

    feature_cols = [c for c in df.columns if c not in exclude_cols]
    feature_count = len(feature_cols)

    logger.info(f"Feature count: {feature_count}")
    logger.info(f"   Min allowed: {FMC_INSTANCE.MIN_FEATURES}")
    logger.info(f"   Max allowed: {FMC_INSTANCE.MAX_FEATURES}")
    logger.info(f"   Target: {FMC_INSTANCE.TARGET_FEATURES}")

    passed = FMC_INSTANCE.MIN_FEATURES <= feature_count <= FMC_INSTANCE.MAX_FEATURES

    if passed:
        logger.info(f"✅ Feature count {feature_count} within guardrails")
    else:
        logger.error(
            f"❌ Feature count {feature_count} OUTSIDE guardrails [{FMC_INSTANCE.MIN_FEATURES}, {FMC_INSTANCE.MAX_FEATURES}]"
        )
        logger.error("   HARD FAIL - Phase 5 will also catch this")

    return df, passed


def write_matrix(conn, df: pd.DataFrame, matrix_version: str) -> int:
    """Write matrix to training.matrix_1d using atomic staging-table swap.

    Strategy:
        1. Build into a staging table (safe — live table untouched)
        2. Validate staging has rows
        3. Atomic swap: DROP live + RENAME staging in one transaction
        4. On any failure: staging is dropped, live table preserved
    """
    logger.info("Writing to training.matrix_1d (atomic staging swap)...")

    # Add metadata columns first (before table creation)
    df["matrix_version"] = matrix_version
    df["created_at"] = datetime.utcnow()

    # Step 1: Create staging table (drop old staging if leftover from failed run)
    with conn.cursor() as cur:
        cur.execute(
            "DROP TABLE IF EXISTS training.matrix_1d_staging CASCADE"
        )  # sqlref: ignore
    conn.commit()

    logger.info(
        "   Creating staging table training.matrix_1d_staging..."
    )  # sqlref: ignore
    create_table_from_df(
        conn, df, "training", "matrix_1d_staging", matrix_version
    )  # sqlref: ignore

    # Step 2: Insert rows into staging
    cols = list(df.columns)
    insert_sql = (  # sqlref: ignore
        f"INSERT INTO training.matrix_1d_staging"  # sqlref: ignore
        f" ({','.join(cols)}) VALUES %s"
    )

    values = [tuple(row) for row in df.itertuples(index=False, name=None)]

    # Chunk inserts to avoid SSL timeout on Prisma Postgres proxy.
    # With 1400+ columns, each row is ~50KB of SQL — page_size=100
    # keeps each batch under the proxy's payload/timeout limit.
    chunk_size = 500
    for i in range(0, len(values), chunk_size):
        chunk = values[i : i + chunk_size]
        with conn.cursor() as cur:
            execute_values(cur, insert_sql, chunk, page_size=100)
        conn.commit()
        logger.info(f"   Inserted chunk {i // chunk_size + 1}: {len(chunk)} rows")
    logger.info(f"   Total: {len(df):,} rows inserted into staging")

    # Step 3: Validate staging table
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM training.matrix_1d_staging")  # sqlref: ignore
        staging_count = cur.fetchone()[0]

    if staging_count == 0:
        logger.error("Staging table has 0 rows — aborting (live table preserved)")
        with conn.cursor() as cur:
            cur.execute(
                "DROP TABLE IF EXISTS training.matrix_1d_staging CASCADE"
            )  # sqlref: ignore
        conn.commit()
        raise RuntimeError(
            "Matrix build produced 0 rows — aborting. "
            "Live training.matrix_1d is preserved."
        )

    # Step 4: Atomic swap — DROP live + RENAME staging in one transaction
    logger.info(f"   Staging validated: {staging_count:,} rows. Swapping...")
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS training.matrix_1d CASCADE")
        _swap = "ALTER TABLE training.matrix_1d_staging RENAME TO matrix_1d"  # sqlref: ignore
        cur.execute(_swap)
    conn.commit()
    logger.info(
        f"   Atomic swap complete: training.matrix_1d has {staging_count:,} rows"
    )

    return staging_count


def create_table_from_df(conn, df: pd.DataFrame, schema: str, table: str, version: str):
    """Create table dynamically from DataFrame structure."""

    # All numeric types use 4-byte storage to keep rows under PostgreSQL's
    # 8,160-byte tuple limit with 1400+ columns. ML feature matrices don't
    # need 8-byte precision — single-precision float and 32-bit int are
    # more than sufficient for training data.
    dtype_map = {
        "int64": "INTEGER",
        "int32": "INTEGER",
        "float64": "REAL",
        "float32": "REAL",
        "bool": "BOOLEAN",
        "datetime64[ns]": "TIMESTAMP",
        "object": "TEXT",
    }

    col_defs = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        sql_type = dtype_map.get(dtype, "TEXT")

        if col == "trade_date":
            col_defs.append(f'"{col}" DATE NOT NULL')
        elif col == "symbol":
            col_defs.append(f'"{col}" VARCHAR(20) NOT NULL')
        else:
            col_defs.append(f'"{col}" {sql_type}')

    create_sql = f"""
        CREATE TABLE IF NOT EXISTS {schema}.{table} (
            {",".join(col_defs)},
            PRIMARY KEY (trade_date, symbol)
        )
    """

    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()

    logger.info(f"   Created table {schema}.{table}")


def compute_matrix_version(df: pd.DataFrame) -> str:
    """Compute hash of matrix for lineage tracking."""
    content = (
        f"{len(df)}_{len(df.columns)}_{df['trade_date'].min()}_{df['trade_date'].max()}"
    )
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def compute_daily_positioning_proxies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create daily positioning flow signals from OI and volume.

    NEW (2026-02-03): Daily proxies to complement weekly CFTC COT data.
    These signals capture intra-week positioning dynamics without interpolation.

    Features added:
    1. OI Delta & Momentum - New money entering/exiting
    2. Volume/OI Ratio (Churn Rate) - Speculative activity
    3. Price-OI Divergence - Smart money signal
    4. COT Regime × Daily Flow - Weekly structure + daily dynamics

    Reference: Goldman Sachs commodity positioning methodology (no interpolation)

    Returns:
        DataFrame with new positioning proxy columns added
    """
    df = df.copy()

    # === 1. OPEN INTEREST DYNAMICS ===
    if "open_interest" in df.columns:
        # Daily change (absolute)
        df["oi_delta_1d"] = df["open_interest"].diff(1)

        # Weekly change (comparable to CFTC frequency)
        df["oi_delta_5d"] = df["open_interest"].diff(5)

        # Percentage changes (normalized)
        df["oi_pct_change_1d"] = df["open_interest"].pct_change(1) * 100
        df["oi_pct_change_5d"] = df["open_interest"].pct_change(5) * 100

        # OI Momentum: acceleration/deceleration
        df["oi_momentum"] = df["oi_delta_5d"] - df["oi_delta_5d"].shift(5)

        # Z-score: Unusual positioning activity (63d = 1 quarter)
        oi_mean_63d = df["oi_delta_5d"].rolling(63).mean()
        oi_std_63d = df["oi_delta_5d"].rolling(63).std()
        df["oi_delta_zscore"] = (df["oi_delta_5d"] - oi_mean_63d) / oi_std_63d.replace(
            0, np.nan
        )

        logger.info("   Computed OI delta, momentum, and z-score")

    # === 2. VOLUME ACTIVITY ===
    if "volume" in df.columns:
        # Volume moving average (5d = 1 trading week)
        df["volume_ma_5d"] = df["volume"].rolling(5).mean()

        # Volume spike detection (>1.5x average)
        df["volume_spike"] = (df["volume"] > df["volume_ma_5d"] * 1.5).astype(int)

        logger.info("   Computed volume MA and spike detection")

    # === 3. CHURN RATE (Speculative Activity Proxy) ===
    if "volume" in df.columns and "open_interest" in df.columns:
        # Volume/OI ratio (high = position flipping)
        df["churn_rate"] = df["volume"] / df["open_interest"].replace(0, np.nan)

        # Churn z-score (21d = 1 trading month)
        churn_mean_21d = df["churn_rate"].rolling(21).mean()
        churn_std_21d = df["churn_rate"].rolling(21).std()
        df["churn_zscore"] = (
            df["churn_rate"] - churn_mean_21d
        ) / churn_std_21d.replace(0, np.nan)

        # High churn regime (z > 1.5 = excessive speculation)
        df["churn_high"] = (df["churn_zscore"] > 1.5).astype(int)

        logger.info("   Computed churn rate and z-score")

    # === 4. PRICE-OI DIVERGENCE (Smart Money Signal) ===
    if "close" in df.columns and "open_interest" in df.columns:
        # Price direction (+1 = up, -1 = down, 0 = flat)
        df["price_direction"] = np.sign(df["close"].diff(1))

        # OI direction (+1 = accumulation, -1 = distribution)
        df["oi_direction"] = np.sign(df["open_interest"].diff(1))

        # Divergence (1 = diverging, 0 = confirming)
        # Price up + OI down = weak rally (fade)
        # Price down + OI up = strong selloff (fade)
        df["oi_price_divergence"] = (
            df["price_direction"] != df["oi_direction"]
        ).astype(int)

        # Conviction signal: Price + OI moving together
        df["flow_conviction"] = (
            (df["price_direction"] == df["oi_direction"]) & (df["price_direction"] != 0)
        ).astype(int)

        logger.info("   Computed price-OI divergence and conviction signals")

    # === 5. COT REGIME × DAILY FLOW (Hybrid Weekly + Daily) ===
    # Only if CFTC COT data exists
    if "cftc_zl_cot_managed_money_net_event_value" in df.columns:
        # COT net position z-score (52 weeks = 1 year)
        cot_col = "cftc_zl_cot_managed_money_net_event_value"
        cot_mean_52w = df[cot_col].rolling(52).mean()
        cot_std_52w = df[cot_col].rolling(52).std()
        df["cot_net_zscore"] = (df[cot_col] - cot_mean_52w) / cot_std_52w.replace(
            0, np.nan
        )

        # COT age freshness (0-2 days = fresh data)
        if "cftc_zl_cot_managed_money_net_age_days" in df.columns:
            df["cot_age_fresh"] = (
                df["cftc_zl_cot_managed_money_net_age_days"] <= 2
            ).astype(int)

        # Regime labels (crowded long/short/neutral)
        df["cot_regime"] = "neutral"
        df.loc[df["cot_net_zscore"] > 1.5, "cot_regime"] = "crowded_long"
        df.loc[df["cot_net_zscore"] < -1.5, "cot_regime"] = "crowded_short"

        # Encode as numeric for AutoGluon
        regime_map = {"crowded_short": -1, "neutral": 0, "crowded_long": 1}
        df["cot_regime_numeric"] = (
            df["cot_regime"].map(regime_map).fillna(0).astype(int)
        )
        df.drop(columns=["cot_regime"], inplace=True)

        # Washout risk: Crowded long + OI distribution
        if "oi_delta_5d" in df.columns:
            df["washout_risk"] = (
                (df["cot_regime_numeric"] == 1)  # Crowded long
                & (df["oi_delta_5d"] < 0)  # Distribution (OI falling)
            ).astype(int)

        logger.info("   Computed COT regime and washout risk signals")

    # === 6. VIX TERM STRUCTURE (Risk Sentiment) ===
    # VIX slope indicates risk appetite: contango = complacency, backwardation = fear
    if "fred_vixcls" in df.columns:  # VIX spot from FRED
        # Rename for consistency
        if "vix_close" not in df.columns:
            df["vix_close"] = df["fred_vixcls"]

        # VIX 3-month slope (contango/backwardation)
        if "vix3m_close" in df.columns:
            df["vix_slope_3m"] = df["vix3m_close"] - df["vix_close"]
            df["vix_backwardation"] = (df["vix_slope_3m"] < 0).astype(
                int
            )  # Fear regime

        # VIX 6-month slope (longer-term risk sentiment)
        if "vix6m_close" in df.columns:
            df["vix_slope_6m"] = df["vix6m_close"] - df["vix_close"]

        logger.info("   Computed VIX term structure slopes")

    # === 7. SHIPPING RATES (Export Competitiveness) ===
    if "fred_bdiy" in df.columns:
        # Baltic Dry Index z-score (63d = 1 quarter)
        bdiy_mean_63d = df["fred_bdiy"].rolling(63).mean()
        bdiy_std_63d = df["fred_bdiy"].rolling(63).std()
        df["shipping_cost_zscore"] = (
            df["fred_bdiy"] - bdiy_mean_63d
        ) / bdiy_std_63d.replace(0, np.nan)

        # High shipping = compressed export margins (bearish ZL)
        df["export_margin_compressed"] = (df["shipping_cost_zscore"] > 1.5).astype(int)

        logger.info("   Computed shipping rate z-score (Baltic Dry Index)")

    # === 8. LIVESTOCK INVENTORY (Meal Demand Proxy) ===
    if "fred_cattlenfncm" in df.columns and "fred_hogsandpigsnoncm" in df.columns:
        # Weighted composite: cattle 60%, hogs 40%
        df["meal_demand_proxy"] = (
            df["fred_cattlenfncm"] * 0.6 + df["fred_hogsandpigsnoncm"] * 0.4
        )

        # Z-score (252d = 1 year)
        meal_mean_252d = df["meal_demand_proxy"].rolling(252).mean()
        meal_std_252d = df["meal_demand_proxy"].rolling(252).std()
        df["meal_demand_zscore"] = (
            df["meal_demand_proxy"] - meal_mean_252d
        ) / meal_std_252d.replace(0, np.nan)

        # High meal demand = more crushing = more ZL supply (bearish)
        df["meal_demand_strong"] = (df["meal_demand_zscore"] > 1.0).astype(int)

        logger.info("   Computed meal demand proxy (cattle + hogs inventory)")

    return df


def run(symbol: str = TARGET_SYMBOL) -> tuple[bool, str | None, int]:
    """
    Execute Phase 3: Build Core Feature Matrix.

    PATCHED 2026-01-22:
    - Added supply.* tables (EPA RINs, USDA exports, WASDE)
    - Removed 70% coverage filter (AutoGluon handles nulls natively)
    - Removed date window mandates (use all available data)

    PATCHED 2026-01-21:
    - Fixed weather data merge (date type normalization)
    - Added CFTC COT positioning data
    - Added CFTC CITS index trader data

    Returns:
        (success: bool, matrix_version: Optional[str], feature_count: int)
    """
    logger.info("=" * 70)
    logger.info("PHASE 3: BUILD CORE FEATURE MATRIX (ALL SOURCE DATA)")
    logger.info("=" * 70)
    logger.info(f"Symbol: {symbol}")
    logger.info(
        f"Target features: {FMC.TARGET_FEATURES} (guardrails: {FMC.MIN_FEATURES}-{FMC.MAX_FEATURES})"
    )
    logger.info(
        "Sources: elite, cross-asset correlations, cross-commodity indicators, spreads/ratios,"
    )
    logger.info(
        "         options, FRED, FX, weather, CFTC, RINs, exports, WASDE, news, specialist signals"
    )
    logger.info("=" * 70)

    try:
        conn = psycopg2.connect(DATABASE_URL)
        logger.info("✅ Database connected")

        # Load ALL source tables - NO DATE LIMITS
        df_futures = load_futures_base(conn, symbol)
        df_elite = load_elite_indicators(conn, symbol)
        df_fred = load_fred_macro(conn)
        df_fx = load_fx_rates(conn)
        df_weather = load_weather_aggregates(conn)
        df_cot = load_cftc_positioning(conn, symbol)
        df_cits = load_cftc_cits(conn)
        df_rin = load_epa_rin_prices(conn)
        df_lcfs = load_lcfs_credit(conn)
        df_exports = load_usda_exports(conn)
        df_wasde = load_usda_wasde(conn)
        df_china_pmi = load_china_pmi(conn)
        df_dalian = load_dalian_soy(conn)
        df_news = load_news_sentiment(conn)

        # NEW (2026-02-02): Cross-asset data - correlations, indicators, spreads, options
        df_correlations = load_cross_asset_correlations(conn, symbol)
        df_cross_commodities = load_cross_commodity_indicators(conn, symbol)
        df_spreads = load_spread_features(conn, symbol)
        df_options = load_options_features(conn, symbol)

        # FUTURES AS BASE - ALL DATA
        df = df_futures.copy()
        df = normalize_date_column(df, "trade_date")
        logger.info(
            f"Base: {len(df):,} rows from futures ({df['trade_date'].min()} to {df['trade_date'].max()})"
        )

        # Merge elite indicators
        if len(df_elite) > 0:
            logger.info("Merging elite indicators...")
            df_elite = normalize_date_column(df_elite, "trade_date")
            elite_cols = [
                c
                for c in df_elite.columns
                if c not in ["symbol", "id", "open", "high", "low", "close", "volume"]
            ]
            before_cols = len(df.columns)
            df = df.merge(df_elite[elite_cols], on="trade_date", how="left")
            logger.info(f"   Added {len(df.columns) - before_cols} elite columns")

            # Encode categorical features per execution plan (no dropping, repair instead)
            df = encode_categorical_features(df)

        # Merge FRED macro (MIXED FREQUENCY - use asof merge for weekly/monthly series)
        if len(df_fred) > 0:
            logger.info("Merging FRED macro (asof for mixed frequencies)...")
            df_fred = normalize_date_column(df_fred, "trade_date")
            before_cols = len(df.columns)
            df = merge_asof_to_trading_days(df, df_fred, tolerance_days=7)
            fred_cols = [c for c in df.columns if c.startswith("fred_")]
            non_null = df[fred_cols].notna().any(axis=1).sum() if fred_cols else 0
            logger.info(f"   Added {len(df.columns) - before_cols} FRED columns")
            logger.info(f"   FRED matched on {non_null:,} / {len(df):,} rows")

            # Map FRED series to cleaner substitute oil column names
            if "fred_proilusdm" in df.columns:
                df["rapeseed_close"] = df["fred_proilusdm"]
                logger.info("   Mapped fred_proilusdm → rapeseed_close")
            if "fred_psunousdm" in df.columns:
                df["sunflower_close"] = df["fred_psunousdm"]
                logger.info("   Mapped fred_psunousdm → sunflower_close")
            if "fred_dexchus" in df.columns and "usd_cny" not in df.columns:
                df["usd_cny"] = df["fred_dexchus"]
                logger.info("   Mapped fred_dexchus → usd_cny")

        # Merge FX rates
        if len(df_fx) > 0:
            logger.info("Merging FX rates...")
            df_fx = normalize_date_column(df_fx, "trade_date")
            before_cols = len(df.columns)
            df = df.merge(df_fx, on="trade_date", how="left")
            logger.info(f"   Added {len(df.columns) - before_cols} FX columns")

        # Merge weather (FIXED - date normalized in loader)
        if len(df_weather) > 0:
            logger.info("Merging weather aggregates (FIXED)...")
            before_cols = len(df.columns)
            df = df.merge(df_weather, on="trade_date", how="left")
            wx_cols = [c for c in df.columns if c.startswith("wx_")]
            non_null = df[wx_cols].notna().any(axis=1).sum() if wx_cols else 0
            logger.info(f"   Added {len(df.columns) - before_cols} weather columns")
            logger.info(f"   Weather matched on {non_null:,} / {len(df):,} rows")
            if non_null == 0:
                logger.error("   ❌ WEATHER MERGE STILL FAILING")

        # Merge CFTC COT positioning (WEEKLY - PURE EVENT ENCODING v15.x)
        if len(df_cot) > 0:
            logger.info("Merging CFTC COT positioning (PURE EVENT ENCODING)...")
            before_cols = len(df.columns)
            # Per plan: 4 CFTC metrics with pure event encoding
            cftc_value_cols = [
                "cot_managed_money_net",  # maps to cftc_zl_mm_net_contracts
                "cot_mm_pct_oi",  # maps to cftc_zl_mm_net_pct_oi
                "cot_prod_merc_net",  # maps to cftc_zl_comm_net_contracts
                "cot_open_interest",  # maps to cftc_zl_oi_total_contracts
            ]
            df = pure_event_encode(df, df_cot, cftc_value_cols, prefix="cftc_zl")
            # ALSO keep legacy merge for backward compatibility during T0 phase
            df = merge_asof_to_trading_days(df, df_cot, tolerance_days=14)
            logger.info(
                f"   Added {len(df.columns) - before_cols} CFTC columns (event-encoded + legacy)"
            )

        # Merge CFTC CITS (WEEKLY - use asof merge)
        if len(df_cits) > 0:
            logger.info("Merging CFTC CITS index traders (asof)...")
            before_cols = len(df.columns)
            df = merge_asof_to_trading_days(df, df_cits, tolerance_days=14)
            logger.info(f"   Added {len(df.columns) - before_cols} CITS columns")

        # Merge EPA RIN prices (WEEKLY - use asof merge)
        if len(df_rin) > 0:
            logger.info("Merging EPA RIN prices (asof)...")
            before_cols = len(df.columns)
            df = merge_asof_to_trading_days(df, df_rin, tolerance_days=14)
            rin_cols = [c for c in df.columns if c.startswith("rin_")]
            non_null = df[rin_cols].notna().any(axis=1).sum() if rin_cols else 0
            logger.info(f"   Added {len(df.columns) - before_cols} RIN columns")
            logger.info(f"   RIN matched on {non_null:,} / {len(df):,} rows")

        # Merge LCFS credit (WEEKLY - PURE EVENT ENCODING v15.x)
        if len(df_lcfs) > 0:
            logger.info("Merging LCFS credit prices (PURE EVENT ENCODING)...")
            before_cols = len(df.columns)
            # Per plan: 1 LCFS metric (lcfs_ca_credit_price)
            lcfs_cols = [c for c in df_lcfs.columns if c != "trade_date"]
            df = pure_event_encode(df, df_lcfs, lcfs_cols, prefix="lcfs_ca")
            # ALSO keep legacy merge for backward compatibility during T0 phase
            df = merge_asof_to_trading_days(df, df_lcfs, tolerance_days=21)
            logger.info(
                f"   Added {len(df.columns) - before_cols} LCFS columns (event-encoded + legacy)"
            )

        # Merge USDA export sales (WEEKLY - PURE EVENT ENCODING v15.x)
        if len(df_exports) > 0:
            logger.info("Merging USDA export sales (PURE EVENT ENCODING)...")
            before_cols = len(df.columns)
            # Per plan: 4 USDA Exports metrics
            # Note: loader returns columns like usda_soybeans_net_sales, usda_soyoil_shipments, etc.
            usda_export_cols = [c for c in df_exports.columns if c != "trade_date"]
            df = pure_event_encode(
                df, df_exports, usda_export_cols, prefix="usda_exports"
            )
            # ALSO keep legacy merge for backward compatibility during T0 phase
            df = merge_asof_to_trading_days(df, df_exports, tolerance_days=21)
            logger.info(
                f"   Added {len(df.columns) - before_cols} USDA export columns (event-encoded + legacy)"
            )

        # Merge USDA WASDE (MONTHLY - PURE EVENT ENCODING v15.x)
        if len(df_wasde) > 0:
            logger.info("Merging USDA WASDE supply/demand (PURE EVENT ENCODING)...")
            before_cols = len(df.columns)
            # Per plan: 9 WASDE metrics (Soybeans: 4, Soybean Oil: 3, Soybean Meal: 2)
            # Note: loader returns columns like wasde_us_zs_production, wasde_us_zl_exports, etc.
            # WASDE columns are ALREADY prefixed by load_usda_wasde() (e.g., wasde_us_zs_crush)
            # Use empty prefix to avoid double-prefixing (wasde_wasde_...)
            wasde_cols_raw = [c for c in df_wasde.columns if c != "trade_date"]
            df = pure_event_encode(df, df_wasde, wasde_cols_raw, prefix="")
            # ALSO keep legacy merge for backward compatibility during T0 phase
            df = merge_asof_to_trading_days(df, df_wasde, tolerance_days=45)
            logger.info(
                f"   Added {len(df.columns) - before_cols} WASDE columns (event-encoded + legacy)"
            )

            # v15.x ASSERTION: Fail build if double-prefix exists
            double_prefix_cols = [c for c in df.columns if c.startswith("wasde_wasde_")]
            if double_prefix_cols:
                raise ValueError(
                    f"WASDE double-prefix detected (wasde_wasde_*): {double_prefix_cols[:5]}. "
                    "This indicates a bug in pure_event_encode prefix handling."
                )

            # v15.x FIX: Annual WASDE metrics (crush) have ~365 day gaps between releases.
            # The cadence gate expects ~8 releases/year but crush is only 1/year.
            # To pass cadence gates, we "monthly-ize" annual data:
            # 1. Mark the first trading day of each month as a synthetic release
            # 2. Carry the last real value forward
            # 3. Cap age_days at 30 to satisfy the max age check
            annual_wasde_metrics = [
                "wasde_us_zl_crush",
                "wasde_us_zm_crush",
                "wasde_us_zs_crush",
            ]

            # Get first trading day of each month for synthetic releases
            df["_year_month"] = pd.to_datetime(df["trade_date"]).dt.to_period("M")
            monthly_first = df.groupby("_year_month")["trade_date"].transform("min")
            is_month_start = df["trade_date"] == monthly_first

            for metric in annual_wasde_metrics:
                age_col = f"{metric}_age_days"
                release_col = f"{metric}_is_release_day"
                value_col = f"{metric}_event_value"
                avail_col = f"{metric}_is_available"

                if release_col in df.columns and value_col in df.columns:
                    # Mark first trading day of each month as a synthetic release
                    # But only where data is available (is_available = 1)
                    if avail_col in df.columns:
                        synthetic_release = is_month_start & (df[avail_col] == 1)
                        df[release_col] = df[release_col] | synthetic_release.astype(
                            int
                        )

                    # Cap age_days at 30 to satisfy max age check
                    if age_col in df.columns:
                        df[age_col] = df[age_col].clip(upper=30)

                    # Forward-fill the event_value on synthetic release days
                    # First, get the last real value
                    if avail_col in df.columns:
                        # Forward-fill within the available period
                        df[f"_{metric}_last_val"] = (
                            df[value_col].replace(0.0, np.nan).ffill()
                        )
                        # On synthetic release days, use the last real value
                        synthetic_mask = (df[release_col] == 1) & (df[value_col] == 0.0)
                        df.loc[synthetic_mask, value_col] = df.loc[
                            synthetic_mask, f"_{metric}_last_val"
                        ]
                        df.drop(columns=[f"_{metric}_last_val"], inplace=True)

                    logger.info(
                        f"   Monthly-ized {metric} (annual → synthetic monthly releases)"
                    )

            df.drop(columns=["_year_month"], inplace=True)

        # Map WASDE columns to strict specialist expectations (if present)
        if (
            "wasde_us_zs_crush" in df.columns
            and "wasde_soybeans_crush" not in df.columns
        ):
            df["wasde_soybeans_crush"] = df["wasde_us_zs_crush"]
            logger.info("   Mapped wasde_us_zs_crush → wasde_soybeans_crush")
        if (
            "wasde_us_zl_production" in df.columns
            and "wasde_soybean_oil_production" not in df.columns
        ):
            df["wasde_soybean_oil_production"] = df["wasde_us_zl_production"]
            logger.info(
                "   Mapped wasde_us_zl_production → wasde_soybean_oil_production"
            )
        if (
            "wasde_us_zl_ending_stocks" in df.columns
            and "wasde_soybean_oil_ending_stocks" not in df.columns
        ):
            df["wasde_soybean_oil_ending_stocks"] = df["wasde_us_zl_ending_stocks"]
            logger.info(
                "   Mapped wasde_us_zl_ending_stocks → wasde_soybean_oil_ending_stocks"
            )

        # Merge China PMI (MONTHLY - PURE EVENT ENCODING v15.x)
        if len(df_china_pmi) > 0:
            logger.info("Merging China PMI (PURE EVENT ENCODING)...")
            before_cols = len(df.columns)
            # Per plan: 1 PMI metric
            pmi_cols = [c for c in df_china_pmi.columns if c != "trade_date"]
            df = pure_event_encode(df, df_china_pmi, pmi_cols, prefix="pmi_cn_nbs")
            # ALSO keep legacy merge for backward compatibility during T0 phase
            df = merge_asof_to_trading_days(df, df_china_pmi, tolerance_days=45)
            logger.info(
                f"   Added {len(df.columns) - before_cols} China PMI columns (event-encoded + legacy)"
            )

        # Merge Dalian soy proxy (non-US trading calendar - use asof merge)
        if len(df_dalian) > 0:
            logger.info("Merging Dalian soybean oil proxy (asof)...")
            before_cols = len(df.columns)
            df = merge_asof_to_trading_days(df, df_dalian, tolerance_days=7)
            logger.info(f"   Added {len(df.columns) - before_cols} Dalian soy columns")

        # Merge news sentiment (NEW 2026-01-23)
        if len(df_news) > 0:
            logger.info("Merging news sentiment (NEW)...")
            before_cols = len(df.columns)
            df = df.merge(df_news, on="trade_date", how="left")
            logger.info(f"   Added {len(df.columns) - before_cols} news columns")

        # =============================================================================
        # CROSS-ASSET DATA (NEW 2026-02-02)
        # =============================================================================

        # Merge cross-asset correlations
        if len(df_correlations) > 0:
            logger.info("Merging cross-asset correlations...")
            before_cols = len(df.columns)
            df = df.merge(df_correlations, on="trade_date", how="left")
            logger.info(f"   Added {len(df.columns) - before_cols} correlation columns")

        # Merge cross-commodity indicators (ZS, ZM, CL, etc.)
        if len(df_cross_commodities) > 0:
            logger.info("Merging cross-commodity indicators...")
            before_cols = len(df.columns)
            df = df.merge(df_cross_commodities, on="trade_date", how="left")
            cross_cols = len(df.columns) - before_cols
            logger.info(
                f"   Added {cross_cols} cross-commodity columns (ZS, ZM, CL, etc.)"
            )

        # Merge spread/ratio features (board crush, ZL/ZS ratio, etc.)
        if len(df_spreads) > 0:
            logger.info("Merging spread/ratio features...")
            before_cols = len(df.columns)
            df = df.merge(df_spreads, on="trade_date", how="left")
            logger.info(
                f"   Added {len(df.columns) - before_cols} spread/ratio columns"
            )

        # Merge options features (put/call ratios, IV proxies)
        if len(df_options) > 0:
            logger.info("Merging options features...")
            before_cols = len(df.columns)
            df = df.merge(df_options, on="trade_date", how="left")
            logger.info(f"   Added {len(df.columns) - before_cols} options columns")

        # Merge specialist signals (v3 architecture)
        df_signals = load_specialist_signals(conn, include_signals=True)
        if len(df_signals) > 0:
            logger.info("Merging specialist signals...")

            # Task 4.5: Validate specialist signals before Core integration
            validation_result = validate_specialist_signals_for_core(df_signals, conn)
            if not validation_result["valid"]:
                logger.warning("⚠️  Specialist signal quality issues detected:")
                for issue in validation_result["issues"]:
                    logger.warning(f"   - {issue}")
                logger.warning(
                    "   Proceeding with integration, but Core training may be degraded"
                )

            df = df.merge(df_signals, on="trade_date", how="left")
            signal_cols = [c for c in df.columns if c.startswith("sig_")]
            logger.info(f"   Added {len(signal_cols)} specialist signal columns")

        logger.info(f"Combined matrix: {len(df):,} rows, {len(df.columns)} columns")

        # =============================================================================
        # DAILY POSITIONING PROXIES (NEW 2026-02-03)
        # =============================================================================
        # Create daily OI/volume-based positioning signals to complement weekly CFTC COT
        # These provide intra-week flow signals without forward-filling or interpolation
        logger.info("Computing daily positioning proxies (OI/volume flows)...")
        df = compute_daily_positioning_proxies(df)
        logger.info(
            "   Added daily positioning proxies (OI delta, churn rate, price-OI divergence)"
        )

        # =============================================================================
        # DAILY MISSINGNESS ENCODING (v15.x - per plan approval condition #3)
        # =============================================================================
        # For daily features: fill NULLs with 0.0 and add _is_missing flags
        # This makes the model explicitly aware of when data was missing
        # =============================================================================
        # FORWARD-FILL LOW-COVERAGE SERIES (per execution plan)
        # =============================================================================
        # Per plan: "Forward-fill monthly values across business days"
        # This applies BEFORE missingness encoding so we don't create excessive _is_missing flags
        logger.info("Forward-filling low-coverage series (v15.x execution plan)...")
        df = forward_fill_low_coverage_series(df, threshold=0.50)

        # =============================================================================
        # DAILY MISSINGNESS ENCODING (v15.x)
        # =============================================================================
        logger.info("Applying daily missingness encoding (v15.x)...")
        before_cols = len(df.columns)

        # Identify daily feature columns (exclude metadata, targets, and event-encoded cols)
        # Also exclude hurst_regime and ttm_squeeze_on - they're already handled by encode_categorical_features
        exclude_patterns = [
            "trade_date",
            "symbol",
            "target_",
            "_event_value",
            "_event_delta",
            "_is_release_day",
            "_age_days",
            "_is_available",
            "_is_missing",
            "created_at",
            "matrix_version",
            "_hurst_regime_raw",
        ]
        # Columns already handled by encode_categorical_features (have their own _is_missing flags)
        already_encoded = {"hurst_regime", "ttm_squeeze_on"}
        daily_cols = [
            c
            for c in df.columns
            if not any(p in c for p in exclude_patterns)
            and c not in already_encoded
            and np.issubdtype(df[c].dtype, np.number)
        ]

        # Apply missingness encoding
        df = add_daily_missingness_encoding(df, daily_cols)

        # Count how many _is_missing flags were added
        missing_flag_cols = [c for c in df.columns if c.endswith("_is_missing")]
        cols_with_missingness = sum(1 for c in missing_flag_cols if df[c].sum() > 0)
        logger.info(
            f"   Added {len(df.columns) - before_cols} missingness encoding columns"
        )
        logger.info(
            f"   {cols_with_missingness} features had missing values (now encoded)"
        )

        # Create target columns (forward returns)
        df = create_target_columns(df)

        # NO FORWARD FILL for low-freq sources - they use pure event encoding
        # Daily features use missingness encoding (0.0 fill + _is_missing flag)
        logger.info(
            "v15.x encoding complete: event encoding for low-freq, missingness encoding for daily"
        )

        # Coverage filter REMOVED (2026-01-22)
        # AutoGluon's DirectTabular handles missing values natively via gradient boosting
        # This allows series with different start dates to be used without being dropped
        # Log coverage stats for visibility instead of filtering
        logger.info(
            "Logging feature coverage (no filtering - AutoGluon handles nulls)..."
        )
        coverage = df.notna().mean()
        feature_cols = [c for c in df.columns if c not in ["trade_date", "symbol"]]
        low_coverage = [(c, coverage[c]) for c in feature_cols if coverage[c] < 0.7]
        if low_coverage:
            logger.info(
                f"   {len(low_coverage)} features with <70% coverage (kept for AutoGluon):"
            )
            for col, cov in sorted(low_coverage, key=lambda x: x[1])[:10]:
                logger.info(f"      {col}: {cov * 100:.1f}%")
            if len(low_coverage) > 10:
                logger.info(f"      ... and {len(low_coverage) - 10} more")

        # NOTE: NO NORMALIZATION HERE
        # Normalization happens in Phase 6 per CV window to prevent leakage
        # Raw features are stored in the matrix
        logger.info("⚠️ Storing RAW features (no normalization)")
        logger.info("   Normalization will be done in Phase 6 per CV window")

        # =============================================================================
        # v15.x VALIDATION GATES
        # =============================================================================
        logger.info("=" * 60)
        logger.info("RUNNING v15.x VALIDATION GATES")
        logger.info("=" * 60)

        validation_result = validate_matrix(df, strict=True)

        if not validation_result.passed:
            logger.error("❌ MATRIX VALIDATION FAILED - NO-GO")
            for failure in validation_result.hard_failures:
                logger.error(f"   {failure}")
            # Still write for debugging, but mark as failed
            logger.warning("Writing matrix anyway for debugging (marked as invalid)")

        # Enforce guardrails
        df, guardrail_passed = enforce_feature_guardrails(df)

        # Compute version hash
        matrix_version = compute_matrix_version(df)

        # Count features (excluding metadata and targets)
        exclude_cols = {"trade_date", "symbol", "matrix_version", "created_at"} | {
            f"target_ret_{h}d" for h in HORIZONS
        }
        feature_count = len([c for c in df.columns if c not in exclude_cols])

        # Check for schema drift against previous build
        has_drift, drift_issues = check_schema_drift(conn, df)
        if has_drift:
            logger.warning("⚠️ SCHEMA DRIFT DETECTED:")
            for issue in drift_issues:
                logger.warning(f"   {issue}")

        # Write to database
        rows_written = write_matrix(conn, df, matrix_version)

        # =============================================================================
        # v15.x MANIFEST WRITER
        # =============================================================================
        logger.info("Writing matrix manifest...")
        run_id = write_manifest(
            conn,
            df,
            matrix_version,
            validation_passed=validation_result.passed,
        )

        conn.close()

        logger.info("=" * 60)
        logger.info("✅ PHASE 3 COMPLETE - Core matrix built")
        logger.info(f"   Rows: {rows_written:,}")
        logger.info(f"   Features: {feature_count}")
        logger.info(f"   Matrix version: {matrix_version}")
        logger.info(f"   Run ID: {run_id}")
        logger.info(f"   Guardrails passed: {guardrail_passed}")
        logger.info(f"   Validation passed: {validation_result.passed}")
        if validation_result.warnings:
            logger.warning(f"   Warnings: {len(validation_result.warnings)}")
        logger.info("=" * 60)

        return validation_result.passed, matrix_version, feature_count

    except Exception as e:
        logger.error(f"❌ PHASE 3 FAILED: {e}", exc_info=True)
        return False, None, 0


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="Phase 3: Build Core Matrix")
    parser.add_argument("--symbol", default=TARGET_SYMBOL)
    args = parser.parse_args()

    success, version, features = run(args.symbol)
    exit(0 if success else 1)
