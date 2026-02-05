"""
Matrix Manifest Writer (v15.x)
==============================

Writes manifest and column-level stats for each matrix build.
Enables drift detection and inference parity via deterministic schema hashing.

LOCKED: 2026-02-01
"""

from __future__ import annotations

import json
import hashlib
import logging
import uuid
from datetime import date, datetime
from typing import Dict, List, Tuple, Any, Optional
import subprocess

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values

from .config import DATABASE_URL

logger = logging.getLogger(__name__)


def get_commit_hash() -> str:
    """Get current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()[:64]
    except Exception:
        return "unknown"


def compute_schema_hash(df: pd.DataFrame) -> str:
    """
    Compute deterministic hash of schema (ordered columns + dtypes).

    Uses stable JSON serialization with sorted keys.
    """
    # Get ordered column list
    columns = sorted(df.columns.tolist())

    # Build dtype mapping
    dtype_map = {col: str(df[col].dtype) for col in columns}

    # Create stable JSON representation
    schema_repr = json.dumps(
        {"columns": columns, "dtypes": dtype_map},
        sort_keys=True,
        separators=(",", ":"),
    )

    # Hash it
    return hashlib.sha256(schema_repr.encode()).hexdigest()[:64]


def compute_column_stats(df: pd.DataFrame, col: str) -> Dict[str, Any]:
    """Compute statistics for a single column."""
    series = df[col]
    dtype = str(series.dtype)

    stats = {
        "column_name": col,
        "dtype": dtype,
        "p01": None,
        "p05": None,
        "p50": None,
        "p95": None,
        "p99": None,
        "mean": None,
        "std": None,
        "min_val": None,
        "max_val": None,
        "zero_rate": None,
        "missing_flag_rate": None,
        "age_days_p95": None,
        "release_day_rate": None,
    }

    # Skip non-numeric columns
    if not np.issubdtype(series.dtype, np.number):
        return stats

    # Drop NaNs for numeric stats
    valid = series.dropna()
    if len(valid) == 0:
        return stats

    try:
        stats["p01"] = float(np.percentile(valid, 1))
        stats["p05"] = float(np.percentile(valid, 5))
        stats["p50"] = float(np.percentile(valid, 50))
        stats["p95"] = float(np.percentile(valid, 95))
        stats["p99"] = float(np.percentile(valid, 99))
        stats["mean"] = float(valid.mean())
        stats["std"] = float(valid.std())
        stats["min_val"] = float(valid.min())
        stats["max_val"] = float(valid.max())
        stats["zero_rate"] = float((valid == 0).sum() / len(valid))

        # Special stats for missingness flags
        if col.endswith("_is_missing"):
            stats["missing_flag_rate"] = float(valid.mean())

        # Special stats for age columns
        if col.endswith("_age_days"):
            stats["age_days_p95"] = int(np.percentile(valid, 95))

        # Special stats for release day flags
        if col.endswith("_is_release_day"):
            stats["release_day_rate"] = float(valid.mean())

    except Exception as e:
        logger.warning(f"Error computing stats for {col}: {e}")

    return stats


def compute_raw_observed_rate(
    df: pd.DataFrame,
    col: str,
    trading_calendar: Optional[pd.DataFrame] = None,
) -> float:
    """
    Compute raw observed rate on ZL trading calendar.

    Per plan: raw_observed_rate is measured on the canonical ZL trading-day calendar,
    not calendar days.

    Args:
        df: Matrix DataFrame
        col: Column name
        trading_calendar: Optional DataFrame with trade_date column (ZL calendar)

    Returns:
        Float between 0 and 1 representing observed rate
    """
    if col not in df.columns:
        return 0.0

    # Count non-NULL values
    non_null = df[col].notna().sum()
    total = len(df)

    if total == 0:
        return 0.0

    return non_null / total


def write_manifest(
    conn,
    df: pd.DataFrame,
    matrix_version: str,
    validation_passed: bool = True,
) -> uuid.UUID:
    """
    Write manifest and stats for a matrix build.

    Args:
        conn: Database connection
        df: Matrix DataFrame
        matrix_version: Hash version string
        validation_passed: Whether validation gates passed

    Returns:
        run_id UUID
    """
    run_id = uuid.uuid4()
    commit_hash = get_commit_hash()
    schema_hash = compute_schema_hash(df)

    # Prepare column metadata
    columns = sorted(df.columns.tolist())
    column_metadata = {}

    for col in columns:
        dtype = str(df[col].dtype)

        # Determine source family based on column prefix
        source_family = "unknown"
        if col.startswith("wasde_"):
            source_family = "wasde"
        elif col.startswith("cftc_") or col.startswith("cot_"):
            source_family = "cftc"
        elif col.startswith("pmi_"):
            source_family = "pmi"
        elif col.startswith("lcfs_"):
            source_family = "lcfs"
        elif col.startswith("usda_"):
            source_family = "usda_exports"
        elif col.startswith("fred_"):
            source_family = "fred"
        elif col.startswith("wx_"):
            source_family = "weather"
        elif col.startswith("sig_"):
            source_family = "specialist"
        elif col in ["open", "high", "low", "close", "volume", "open_interest"]:
            source_family = "ohlcv"
        elif col.startswith("target_"):
            source_family = "target"

        # Determine fill policy
        fill_policy = "none"
        if col.endswith("_event_value") or col.endswith("_event_delta"):
            fill_policy = "zero_on_non_release"
        elif col.endswith("_is_missing"):
            fill_policy = "missingness_flag"
        elif col.endswith("_age_days"):
            fill_policy = "9999_pre_first"

        column_metadata[col] = {
            "dtype": dtype,
            "required": not col.startswith("target_"),
            "source_family": source_family,
            "fill_policy": fill_policy,
        }

    # Get required columns (all non-target columns)
    required_columns = [c for c in columns if not c.startswith("target_")]

    # Get date range
    trade_dates = pd.to_datetime(df["trade_date"])
    min_date = trade_dates.min().date()
    max_date = trade_dates.max().date()

    cur = conn.cursor()

    try:
        # Insert manifest
        cur.execute(
            """
            INSERT INTO training.matrix_manifest_1d (
                run_id, matrix_version, commit_hash, data_cutoff_date,
                schema_hash, column_list, column_metadata, required_columns,
                feature_count, row_count, min_date, max_date, validation_passed
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(run_id),
                matrix_version,
                commit_hash,
                max_date,
                schema_hash,
                json.dumps(columns),
                json.dumps(column_metadata),
                required_columns,
                len(required_columns),
                len(df),
                min_date,
                max_date,
                validation_passed,
            ),
        )

        # Compute and insert column stats
        logger.info(f"Computing stats for {len(columns)} columns...")
        stats_rows = []
        for col in columns:
            stats = compute_column_stats(df, col)
            stats_rows.append(
                (
                    str(run_id),
                    stats["column_name"],
                    stats["dtype"],
                    stats["p01"],
                    stats["p05"],
                    stats["p50"],
                    stats["p95"],
                    stats["p99"],
                    stats["mean"],
                    stats["std"],
                    stats["min_val"],
                    stats["max_val"],
                    stats["zero_rate"],
                    stats["missing_flag_rate"],
                    stats["age_days_p95"],
                    stats["release_day_rate"],
                )
            )

        execute_values(
            cur,
            """
            INSERT INTO training.matrix_feature_stats_1d (
                run_id, column_name, dtype, p01, p05, p50, p95, p99,
                mean, std, min_val, max_val, zero_rate, missing_flag_rate,
                age_days_p95, release_day_rate
            ) VALUES %s
            """,
            stats_rows,
        )

        conn.commit()
        logger.info(f"Wrote manifest {run_id} with {len(columns)} column stats")
        logger.info(f"   Schema hash: {schema_hash}")
        logger.info(f"   Date range: {min_date} to {max_date}")
        logger.info(f"   Rows: {len(df):,}, Features: {len(required_columns)}")

        return run_id

    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to write manifest: {e}")
        raise


def check_schema_drift(
    conn,
    current_df: pd.DataFrame,
    reference_run_id: Optional[str] = None,
) -> Tuple[bool, List[str]]:
    """
    Check for schema drift against a reference manifest.

    Args:
        conn: Database connection
        current_df: Current matrix DataFrame
        reference_run_id: Optional specific run_id to compare against
                         (defaults to most recent)

    Returns:
        Tuple of (has_drift, list of drift issues)
    """
    cur = conn.cursor()

    # Get reference manifest
    if reference_run_id:
        cur.execute(
            """
            SELECT schema_hash, column_list
            FROM training.matrix_manifest_1d
            WHERE run_id = %s
            """,
            (reference_run_id,),
        )
    else:
        cur.execute(
            """
            SELECT schema_hash, column_list
            FROM training.matrix_manifest_1d
            ORDER BY created_at DESC
            LIMIT 1
            """
        )

    result = cur.fetchone()
    if not result:
        return False, ["No reference manifest found (first build)"]

    ref_schema_hash, ref_column_list = result
    # psycopg2 returns JSONB as Python objects, not strings
    if isinstance(ref_column_list, str):
        ref_columns = set(json.loads(ref_column_list))
    else:
        ref_columns = set(ref_column_list)

    # Compute current schema
    current_hash = compute_schema_hash(current_df)
    current_columns = set(current_df.columns.tolist())

    issues = []

    # Check for hash match
    if current_hash != ref_schema_hash:
        issues.append(f"Schema hash changed: {ref_schema_hash[:16]}... → {current_hash[:16]}...")

    # Check for added columns
    added = current_columns - ref_columns
    if added:
        issues.append(f"Added columns: {sorted(added)[:10]}")

    # Check for removed columns
    removed = ref_columns - current_columns
    if removed:
        issues.append(f"Removed columns: {sorted(removed)[:10]}")

    has_drift = len(issues) > 0
    return has_drift, issues


def validate_inference_parity(
    conn,
    inference_df: pd.DataFrame,
    training_run_id: str,
) -> Tuple[bool, List[str]]:
    """
    Validate that inference matrix matches training schema.

    Args:
        conn: Database connection
        inference_df: Inference-time matrix
        training_run_id: The run_id of the training manifest to match

    Returns:
        Tuple of (is_valid, list of issues)
    """
    cur = conn.cursor()

    cur.execute(
        """
        SELECT schema_hash, required_columns
        FROM training.matrix_manifest_1d
        WHERE run_id = %s
        """,
        (training_run_id,),
    )

    result = cur.fetchone()
    if not result:
        return False, [f"Training manifest {training_run_id} not found"]

    ref_schema_hash, required_columns = result
    issues = []

    # Check that all required columns are present
    inference_cols = set(inference_df.columns)
    required_set = set(required_columns)
    missing = required_set - inference_cols
    if missing:
        issues.append(f"Missing required columns: {sorted(missing)[:10]}")

    # Check schema hash
    current_hash = compute_schema_hash(inference_df)
    if current_hash != ref_schema_hash:
        issues.append(f"Schema hash mismatch: expected {ref_schema_hash[:16]}..., got {current_hash[:16]}...")

    is_valid = len(issues) == 0
    return is_valid, issues
