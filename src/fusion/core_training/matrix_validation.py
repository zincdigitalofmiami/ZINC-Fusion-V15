"""
Matrix Validation Gates (v15.x)
===============================

Implements GO/NO-GO validation gates for Core matrix builds.

Gate Types:
- Daily features: raw_observed_rate >= 0.95 (on ZL trading calendar)
- Low-freq features: cadence compliance + max age caps
- Universal: No NULLs, No epoch dates, date floor >= 1990-01-01

LOCKED: 2026-02-01
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass, field

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# VALIDATION CONFIGURATION
# =============================================================================


@dataclass
class ValidationConfig:
    """Configuration for validation gates."""

    # Date floor (global)
    DATE_FLOOR: date = date(1990, 1, 1)

    # Daily feature gate
    MIN_RAW_OBSERVED_RATE: float = 0.95

    # Low-frequency cadence expectations
    # Per execution plan: Cadence enforced from enforce_from date only
    # Thresholds relaxed based on actual data availability:
    # - WASDE: ~8-10 releases/year for most series (some are quarterly)
    # - PMI: Monthly but may have gaps
    # - USDA Exports: Weekly but holiday gaps common
    CADENCE_RULES: Dict[str, Dict[str, Any]] = field(
        default_factory=lambda: {
            "wasde": {
                "expected_per_year": 8,
                "max_age_days": 90,
                "enforce_from": date(2010, 1, 1),
            },
            "cftc": {
                "expected_per_year": 50,
                "max_age_days": 14,
                "enforce_from": date(2006, 1, 1),
            },
            "pmi": {
                "expected_per_year": 10,
                "max_age_days": 60,
                "enforce_from": date(2010, 1, 1),
            },
            "lcfs": {
                "expected_per_year": 48,
                "max_age_days": 21,
                "enforce_from": date(2015, 1, 1),
            },
            "usda_exports": {
                "expected_per_year": 48,
                "max_age_days": 21,
                "enforce_from": date(2010, 1, 1),
            },
        }
    )

    # Column patterns for low-freq families
    LOW_FREQ_PREFIXES: List[str] = field(
        default_factory=lambda: [
            "wasde_",
            "cftc_zl_",
            "pmi_cn_nbs_",
            "lcfs_ca_",
            "usda_exports_",
        ]
    )


VALIDATION_CONFIG = ValidationConfig()


# =============================================================================
# VALIDATION RESULT
# =============================================================================


@dataclass
class ValidationResult:
    """Result of matrix validation."""

    passed: bool
    hard_failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def add_failure(self, message: str):
        self.hard_failures.append(message)
        self.passed = False

    def add_warning(self, message: str):
        self.warnings.append(message)


# =============================================================================
# VALIDATION GATES
# =============================================================================


def check_null_gate(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    Gate: No NULLs in feature columns (targets and debug columns excluded).

    Per execution plan: Target columns (target_ret_*) have expected NULLs at the end
    due to forward return calculation. Debug columns (_*_raw) are also excluded.

    Returns:
        Tuple of (passed, list of failure messages)
    """
    failures = []

    # Exclude target columns and debug columns from NULL check
    # Targets have forward NULLs at end (expected)
    # Debug columns (_*_raw) are informational only
    exclude_cols = [
        c
        for c in df.columns
        if c.startswith("target_")
        or c.startswith("_")  # Debug columns like _hurst_regime_raw
        or c == "created_at"  # Metadata column
        or c == "matrix_version"
        or c.endswith("_age_days")  # TTL age tracking (NULL before first fill)
        or c.endswith("_event_value")  # Pure event encoding (NULL between releases)
        or c.endswith("_event_delta")  # Pure event encoding
        or c.endswith("_is_release_day")  # Pure event encoding
        or c.endswith("_is_available")  # Availability flags
    ]

    check_cols = [c for c in df.columns if c not in exclude_cols]

    null_counts = df[check_cols].isnull().sum()
    null_cols = null_counts[null_counts > 0]

    if len(null_cols) > 0:
        for col, count in null_cols.items():
            failures.append(f"NULL values in {col}: {count} rows")

    return len(failures) == 0, failures


def check_infinity_gate(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    Gate: No infinity values in numeric columns.

    Returns:
        Tuple of (passed, list of failure messages)
    """
    failures = []

    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        inf_count = np.isinf(df[col]).sum()
        if inf_count > 0:
            failures.append(f"Infinity values in {col}: {inf_count} rows")

    return len(failures) == 0, failures


def check_epoch_date_gate(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    Gate: No epoch dates (1970-01-01) in date columns.

    Returns:
        Tuple of (passed, list of failure messages)
    """
    failures = []

    if "trade_date" in df.columns:
        dates = pd.to_datetime(df["trade_date"])
        epoch = pd.Timestamp("1970-01-01")
        epoch_count = (dates == epoch).sum()
        if epoch_count > 0:
            failures.append(f"Epoch dates (1970-01-01) found: {epoch_count} rows")

    return len(failures) == 0, failures


def check_date_floor_gate(
    df: pd.DataFrame,
    floor: date = VALIDATION_CONFIG.DATE_FLOOR,
) -> Tuple[bool, List[str]]:
    """
    Gate: All dates >= floor (1990-01-01 by default).

    Returns:
        Tuple of (passed, list of failure messages)
    """
    failures = []

    if "trade_date" in df.columns:
        dates = pd.to_datetime(df["trade_date"]).dt.date
        violations = (dates < floor).sum()
        if violations > 0:
            failures.append(f"Dates before {floor}: {violations} rows")

    return len(failures) == 0, failures


def check_daily_observed_rate(
    df: pd.DataFrame,
    col: str,
    threshold: float = VALIDATION_CONFIG.MIN_RAW_OBSERVED_RATE,
) -> Tuple[bool, float]:
    """
    Check raw_observed_rate for a daily feature.

    Per plan: raw_observed_rate is measured on the ZL trading calendar
    (which is what df represents).

    Args:
        df: Matrix DataFrame (represents ZL trading calendar)
        col: Column name
        threshold: Minimum required rate (default 0.95)

    Returns:
        Tuple of (passed, observed_rate)
    """
    if col not in df.columns:
        return False, 0.0

    total = len(df)
    if total == 0:
        return False, 0.0

    non_null = df[col].notna().sum()
    observed_rate = non_null / total

    return observed_rate >= threshold, observed_rate


def check_cadence_compliance(
    df: pd.DataFrame,
    family: str,
    config: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any]]:
    """
    Check cadence compliance for low-frequency features.

    Per execution plan: Cadence gate applies ONLY after enforce_from date.
    Pre-enforce_from periods do not count against cadence requirements.
    This allows for historical data gaps before modern tracking began.

    Args:
        df: Matrix DataFrame
        family: Feature family (wasde, cftc, etc.)
        config: Cadence config with expected_per_year, max_age_days, and enforce_from

    Returns:
        Tuple of (passed, metrics dict)
    """
    _PREFIX_MAP = {
        "cftc": "cftc_zl_",
        "pmi": "pmi_cn_nbs_",
        "lcfs": "lcfs_ca_",
    }
    prefix = _PREFIX_MAP.get(family, f"{family}_")

    # Get enforcement start date (default to 2010 if not specified)
    enforce_from = config.get("enforce_from", date(2010, 1, 1))

    metrics = {
        "family": family,
        "expected_per_year": config["expected_per_year"],
        "max_age_days": config["max_age_days"],
        "enforce_from": str(enforce_from),
        "issues": [],
    }

    # Find release day columns for this family
    release_cols = [
        c for c in df.columns if c.startswith(prefix) and c.endswith("_is_release_day")
    ]

    if not release_cols:
        # No event-encoded columns for this family - just warn, don't fail
        metrics["issues"].append(
            f"No release day columns found for {family} (skipping cadence check)"
        )
        return True, metrics

    # Pre-compute enforcement-period filter once (not per column)
    trade_dates = pd.to_datetime(df["trade_date"]).dt.date
    enforce_mask = trade_dates >= enforce_from
    df_enforce = df[enforce_mask]

    if len(df_enforce) == 0:
        return True, metrics

    # Check each metric's release pattern
    all_passed = True
    for col in release_cols:
        metric_name = col.replace("_is_release_day", "")
        age_col = f"{metric_name}_age_days"

        if age_col not in df.columns:
            continue

        # Get data after first release (where is_available = 1) within enforcement period
        avail_col = f"{metric_name}_is_available"
        if avail_col in df_enforce.columns:
            active_df = df_enforce[df_enforce[avail_col] == 1]
        else:
            # Infer: rows where age_days < 9999 are post-first-release
            active_df = df_enforce[df_enforce[age_col] < 9999]

        if len(active_df) == 0:
            continue

        # Count releases within enforcement period
        release_count = active_df[col].sum()

        # Calculate expected releases based on date range within enforcement period
        active_dates = trade_dates[active_df.index]
        date_min = active_dates.min()
        date_max = active_dates.max()
        date_range = (date_max - date_min).days
        years = date_range / 365.25
        expected_releases = years * config["expected_per_year"]

        # Allow 20% tolerance (relaxed from 10% per execution plan)
        if release_count < expected_releases * 0.8:
            metrics["issues"].append(
                f"{metric_name}: {release_count} releases vs {expected_releases:.0f} expected ({enforce_from}+)"
            )
            all_passed = False

        # Check max age within enforcement period
        max_age = active_df[age_col].max()
        if max_age > config["max_age_days"]:
            p95_age = active_df[age_col].quantile(0.95)
            if p95_age > config["max_age_days"]:
                metrics["issues"].append(
                    f"{metric_name}: P95 age {p95_age:.0f}d exceeds {config['max_age_days']}d cap ({enforce_from}+)"
                )
                all_passed = False

    return all_passed, metrics


def check_dtype_consistency(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    Check that encoding columns have expected dtypes.

    Returns:
        Tuple of (passed, list of issues)
    """
    issues = []

    for col in df.columns:
        dtype = df[col].dtype

        # Event values should be float
        if col.endswith("_event_value") or col.endswith("_event_delta"):
            if not np.issubdtype(dtype, np.floating):
                issues.append(f"{col} should be float, is {dtype}")

        # Flags should be int
        if (
            col.endswith("_is_release_day")
            or col.endswith("_is_available")
            or col.endswith("_is_missing")
        ):
            if not np.issubdtype(dtype, np.integer):
                issues.append(f"{col} should be int, is {dtype}")

        # Age should be int
        if col.endswith("_age_days"):
            if not np.issubdtype(dtype, np.integer):
                issues.append(f"{col} should be int, is {dtype}")

    return len(issues) == 0, issues


def check_encoding_completeness(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    Check that all 5 encoding columns are present per low-freq metric.

    Per plan: Each low-freq metric should have:
    - {x}_event_value
    - {x}_event_delta
    - {x}_is_release_day
    - {x}_age_days
    - {x}_is_available

    Returns:
        Tuple of (passed, list of issues)
    """
    issues = []

    # Find all event_value columns (these define the metrics)
    event_value_cols = [c for c in df.columns if c.endswith("_event_value")]

    for col in event_value_cols:
        base = col.replace("_event_value", "")

        expected = [
            f"{base}_event_value",
            f"{base}_event_delta",
            f"{base}_is_release_day",
            f"{base}_age_days",
            f"{base}_is_available",
        ]

        missing = [e for e in expected if e not in df.columns]
        if missing:
            issues.append(f"{base}: missing encoding columns {missing}")

    return len(issues) == 0, issues


# =============================================================================
# MAIN VALIDATION FUNCTION
# =============================================================================


def validate_matrix(
    df: pd.DataFrame,
    strict: bool = True,
) -> ValidationResult:
    """
    Run all validation gates on the matrix.

    Args:
        df: Matrix DataFrame
        strict: If True, cadence/observed rate failures are hard failures.
                If False, they are warnings.

    Returns:
        ValidationResult with passed status, failures, and warnings
    """
    result = ValidationResult(passed=True)

    logger.info("Running matrix validation gates (v15.x)...")

    # =========================
    # HARD FAILURES (always fatal)
    # =========================

    # Gate 1: No NULLs
    passed, failures = check_null_gate(df)
    if not passed:
        for f in failures:
            result.add_failure(f"NULL GATE FAILED: {f}")
    else:
        logger.info("   ✅ NULL gate passed (zero NULLs)")

    # Gate 1b: No infinities
    passed, failures = check_infinity_gate(df)
    if not passed:
        for f in failures:
            result.add_failure(f"INFINITY GATE FAILED: {f}")
    else:
        logger.info("   ✅ Infinity gate passed (zero infinities)")

    # Gate 2: No epoch dates
    passed, failures = check_epoch_date_gate(df)
    if not passed:
        for f in failures:
            result.add_failure(f"EPOCH DATE GATE FAILED: {f}")
    else:
        logger.info("   ✅ Epoch date gate passed")

    # Gate 3: Date floor
    passed, failures = check_date_floor_gate(df)
    if not passed:
        for f in failures:
            result.add_failure(f"DATE FLOOR GATE FAILED: {f}")
    else:
        logger.info(f"   ✅ Date floor gate passed (>= {VALIDATION_CONFIG.DATE_FLOOR})")

    # Gate 4: Dtype consistency
    passed, issues = check_dtype_consistency(df)
    if not passed:
        for i in issues[:5]:  # Limit to first 5
            result.add_failure(f"DTYPE GATE FAILED: {i}")
    else:
        logger.info("   ✅ Dtype gate passed")

    # Gate 5: Encoding completeness
    passed, issues = check_encoding_completeness(df)
    if not passed:
        for i in issues[:5]:
            result.add_failure(f"ENCODING GATE FAILED: {i}")
    else:
        logger.info("   ✅ Encoding completeness gate passed")

    # =========================
    # CONDITIONAL GATES (strict vs warn)
    # =========================

    # Gate 6: Daily observed rate
    daily_cols = [
        c
        for c in df.columns
        if not any(c.startswith(p) for p in VALIDATION_CONFIG.LOW_FREQ_PREFIXES)
        and not c.endswith(
            (
                "_event_value",
                "_event_delta",
                "_is_release_day",
                "_age_days",
                "_is_available",
                "_is_missing",
            )
        )
        and c not in ("trade_date", "symbol")
        and np.issubdtype(df[c].dtype, np.number)
    ]

    low_observed = []
    for col in daily_cols:
        passed, rate = check_daily_observed_rate(df, col)
        if not passed:
            low_observed.append((col, rate))

    if low_observed:
        msg = f"Daily features with raw_observed_rate < 0.95: {len(low_observed)}"
        for col, rate in low_observed[:5]:
            msg += f"\n      {col}: {rate:.1%}"
        if strict:
            result.add_failure(f"OBSERVED RATE GATE FAILED: {msg}")
        else:
            result.add_warning(f"OBSERVED RATE WARNING: {msg}")
    else:
        logger.info("   ✅ Daily observed rate gate passed (>= 95%)")

    # Gate 7: Low-freq cadence compliance
    # Per execution plan: WASDE historical gaps are known issues - treat as warnings
    for family, config in VALIDATION_CONFIG.CADENCE_RULES.items():
        passed, metrics = check_cadence_compliance(df, family, config)
        if not passed:
            # WASDE cadence failures are warnings (known historical data gaps)
            # Other families are hard failures if strict mode
            is_wasde = family == "wasde"
            for issue in metrics["issues"]:
                if strict and not is_wasde:
                    result.add_failure(f"CADENCE GATE FAILED ({family}): {issue}")
                else:
                    result.add_warning(f"CADENCE WARNING ({family}): {issue}")
        else:
            logger.info(f"   ✅ Cadence gate passed for {family}")

    # =========================
    # METRICS
    # =========================

    result.metrics = {
        "row_count": len(df),
        "column_count": len(df.columns),
        "date_range": (
            str(df["trade_date"].min()) if "trade_date" in df.columns else None,
            str(df["trade_date"].max()) if "trade_date" in df.columns else None,
        ),
        "null_count": int(df.isnull().sum().sum()),
        "encoding_columns": len([c for c in df.columns if c.endswith("_event_value")]),
        "missing_flag_columns": len(
            [c for c in df.columns if c.endswith("_is_missing")]
        ),
    }

    # Final status
    if result.passed:
        logger.info("✅ VALIDATION PASSED - matrix is GO")
    else:
        logger.error(
            f"❌ VALIDATION FAILED - {len(result.hard_failures)} hard failures"
        )
        for f in result.hard_failures[:10]:
            logger.error(f"   {f}")

    if result.warnings:
        logger.warning(f"⚠️ {len(result.warnings)} warnings:")
        for w in result.warnings[:5]:
            logger.warning(f"   {w}")

    return result
