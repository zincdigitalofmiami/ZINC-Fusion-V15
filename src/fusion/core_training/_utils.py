"""
Shared date utilities for core training pipeline.

Functions here are used by loaders, features, and the orchestrator.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)


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

    Example: ICSA released Saturday 2026-01-17 -> aligns to Monday 2026-01-20

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
