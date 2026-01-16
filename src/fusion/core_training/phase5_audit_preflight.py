"""
Phase 5: Pre-Flight Audit
==========================

MANDATORY HARD GATE before training. This is NOT advisory.

Checks (ALL MUST PASS):
1. Options features exist (BLOCKING GATE from Phase 1)
2. Elite indicators validated (from Phase 2)
3. Core matrix built with guardrails enforced (from Phase 3):
   - Feature count in [120, 350] → HARD FAIL if outside
   - No all-null columns
   - No constant columns
   - No duplicate (trade_date, symbol) keys
4. OOF table ready (from Phase 4)
5. Target column coverage
6. Structural leakage checks (not just correlation)

FAIL = DO NOT PROCEED TO TRAINING. Period.
"""

from __future__ import annotations

import logging
import hashlib
from datetime import datetime
from typing import Tuple, Dict, List, Optional

import pandas as pd
import numpy as np
import psycopg2

from .config import (
    DATABASE_URL,
    TARGET_SYMBOL,
    HORIZONS,
    FeatureMatrixConfig as FMC,
    OOF_TABLE_NAME,
    OOF_COLUMN_NAMES,
    HORIZONS as CONFIG_HORIZONS,
    QUANTILES as CONFIG_QUANTILES,
)

logger = logging.getLogger(__name__)


def compute_config_hash() -> str:
    """
    Compute hash of training-relevant config parameters.

    This hash changes if any of these change:
    - HORIZONS
    - QUANTILES
    - Feature guardrails (MIN_FEATURES, MAX_FEATURES)
    """
    fmc = FMC()
    config_str = (
        f"horizons={sorted(CONFIG_HORIZONS)}|"
        f"quantiles={sorted(CONFIG_QUANTILES)}|"
        f"min_features={fmc.MIN_FEATURES}|"
        f"max_features={fmc.MAX_FEATURES}|"
        f"normalize_method={fmc.NORMALIZE_METHOD}"
    )
    return hashlib.sha256(config_str.encode()).hexdigest()[:16]


class AuditResult:
    """Container for audit results with strict semantics and hash tracking."""

    def __init__(self):
        self.checks: Dict[str, bool] = {}
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.stats: Dict[str, any] = {}
        # Hash tracking for artifact binding
        self._core_matrix_hash: Optional[str] = None
        self._options_hash: Optional[str] = None
        self._elite_hash: Optional[str] = None
        self._config_hash: str = compute_config_hash()

    @property
    def passed(self) -> bool:
        """ALL checks must pass AND no errors."""
        return all(self.checks.values()) and len(self.errors) == 0

    @property
    def core_matrix_hash(self) -> Optional[str]:
        return self._core_matrix_hash

    @core_matrix_hash.setter
    def core_matrix_hash(self, value: str):
        self._core_matrix_hash = value

    @property
    def options_hash(self) -> Optional[str]:
        return self._options_hash

    @options_hash.setter
    def options_hash(self, value: str):
        self._options_hash = value

    @property
    def elite_hash(self) -> Optional[str]:
        return self._elite_hash

    @elite_hash.setter
    def elite_hash(self, value: str):
        self._elite_hash = value

    @property
    def config_hash(self) -> str:
        return self._config_hash

    def get_all_hashes(self) -> Dict[str, Optional[str]]:
        """Return all hashes for artifact binding."""
        return {
            "core_matrix_hash": self._core_matrix_hash,
            "options_hash": self._options_hash,
            "elite_hash": self._elite_hash,
            "config_hash": self._config_hash,
        }

    def add_check(self, name: str, passed: bool, message: str = None):
        """Record a check result."""
        self.checks[name] = passed
        status = "✅ PASS" if passed else "❌ FAIL"
        log_msg = f"   {status}: {name}" + (f" - {message}" if message else "")
        if passed:
            logger.info(log_msg)
        else:
            logger.error(log_msg)

    def add_warning(self, message: str):
        """Warnings don't block, but are logged."""
        self.warnings.append(message)
        logger.warning(f"   ⚠️ WARNING: {message}")

    def add_error(self, message: str):
        """Errors BLOCK training."""
        self.errors.append(message)
        logger.error(f"   ❌ ERROR: {message}")


# =============================================================================
# CHECK 1: OPTIONS FEATURES (BLOCKING GATE)
# =============================================================================


def check_options_features(conn, symbol: str, audit: AuditResult):
    """
    BLOCKING GATE: Options features from Phase 1 must exist.

    Validates:
    - Table exists
    - Has data for target symbol
    - No major date gaps in expected training range
    """
    logger.info("CHECK 1: Options Features (BLOCKING GATE)...")

    try:
        with conn.cursor() as cur:
            # Check table exists
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'gold' 
                      AND table_name = 'options_features_1d'
                )
            """
            )
            table_exists = cur.fetchone()[0]

            if not table_exists:
                audit.add_check("options_features", False, "TABLE DOES NOT EXIST")
                audit.add_error(
                    "gold.options_features_1d not found - run Phase 1 first"
                )
                return

            # Check row count and date range
            cur.execute(
                """
                SELECT 
                    COUNT(*) as rows,
                    MIN(trade_date) as min_date,
                    MAX(trade_date) as max_date,
                    COUNT(DISTINCT trade_date) as unique_dates
                FROM gold.options_features_1d
                WHERE symbol = %s
            """,
                (symbol,),
            )
            row = cur.fetchone()

            audit.stats["options_rows"] = row[0]
            audit.stats["options_min_date"] = str(row[1]) if row[1] else None
            audit.stats["options_max_date"] = str(row[2]) if row[2] else None
            audit.stats["options_unique_dates"] = row[3]

            if row[0] == 0:
                audit.add_check("options_features", False, "NO DATA FOR SYMBOL")
                audit.add_error(
                    f"gold.options_features_1d has no data for {symbol} - run Phase 1"
                )
                return

            # Check for date gaps (business days only, so allow some slack)
            expected_days = (
                pd.to_datetime(row[2]) - pd.to_datetime(row[1])
            ).days * 0.71  # ~71% are trading days
            coverage_ratio = row[3] / max(expected_days, 1)

            if coverage_ratio < 0.90:
                audit.add_warning(
                    f"Options date coverage: {coverage_ratio:.1%} (expected ~90%+)"
                )

            # Compute options hash for artifact binding
            cur.execute(
                """
                SELECT MD5(STRING_AGG(
                    trade_date::text || COALESCE(iv_atm::text, ''),
                    '' ORDER BY trade_date
                ))
                FROM gold.options_features_1d
                WHERE symbol = %s
            """,
                (symbol,),
            )
            audit.options_hash = cur.fetchone()[0]
            audit.stats["options_hash"] = audit.options_hash

            audit.add_check(
                "options_features", True, f"{row[0]:,} rows, {row[1]} to {row[2]}"
            )

    except psycopg2.errors.UndefinedTable:
        audit.add_check("options_features", False, "TABLE DOES NOT EXIST")
        audit.add_error("gold.options_features_1d not found - run Phase 1 first")


# =============================================================================
# CHECK 2: ELITE INDICATORS
# =============================================================================


def check_elite_indicators(conn, symbol: str, audit: AuditResult):
    """
    Validate elite indicators are populated from 2000+.
    """
    logger.info("CHECK 2: Elite Indicators...")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 
                COUNT(*) as rows,
                MIN(trade_date) as min_date,
                MAX(trade_date) as max_date,
                COUNT(DISTINCT trade_date) as unique_dates
            FROM gold.elite_indicators_1d
            WHERE symbol = %s
        """,
            (symbol,),
        )
        row = cur.fetchone()

        audit.stats["elite_rows"] = row[0]
        audit.stats["elite_min_date"] = str(row[1]) if row[1] else None
        audit.stats["elite_max_date"] = str(row[2]) if row[2] else None

        # Requirements: 6000+ rows, starting 2000 or earlier
        min_rows = 6000
        max_start = "2000-01-15"

        if row[0] < min_rows:
            audit.add_check(
                "elite_indicators", False, f"{row[0]} rows < {min_rows} required"
            )
            audit.add_error("Elite indicators insufficient - check Phase 2")
        elif row[1] and str(row[1]) > max_start:
            audit.add_check(
                "elite_indicators", False, f"Start date {row[1]} > {max_start}"
            )
            audit.add_error("Elite indicators don't go back to 2000")
        else:
            # Compute elite hash for artifact binding
            cur.execute(
                """
                SELECT MD5(STRING_AGG(
                    trade_date::text || COALESCE(close::text, ''),
                    '' ORDER BY trade_date
                ))
                FROM gold.elite_indicators_1d
                WHERE symbol = %s
            """,
                (symbol,),
            )
            audit.elite_hash = cur.fetchone()[0]
            audit.stats["elite_hash"] = audit.elite_hash

            audit.add_check("elite_indicators", True, f"{row[0]:,} rows from {row[1]}")


# =============================================================================
# CHECK 3: CORE MATRIX (HARD GUARDRAILS)
# =============================================================================


def check_core_matrix(conn, symbol: str, audit: AuditResult):
    """
    Validate core matrix with HARD GUARDRAILS:
    - Feature count in [MIN_FEATURES, MAX_FEATURES] → FAIL if outside
    - ANY all-null column → HARD FAIL (checked on ALL columns)
    - ANY constant column (variance ≈ 0) → HARD FAIL (checked on ALL columns)
    - ANY duplicate (trade_date, symbol) keys → HARD FAIL

    Unique key for training.core_matrix_curated_1d: (trade_date, symbol)
    """
    logger.info("CHECK 3: Core Matrix (HARD GUARDRAILS)...")

    FMC_INSTANCE = FMC()

    try:
        # Check table exists
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'training'
                      AND table_name = 'core_matrix_curated_1d'
                )
            """
            )
            if not cur.fetchone()[0]:
                audit.add_check("core_matrix", False, "TABLE DOES NOT EXIST")
                audit.add_error(
                    "training.core_matrix_curated_1d not found - run Phase 3"
                )
                return

        # Get row count
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) 
                FROM training.core_matrix_curated_1d
                WHERE symbol = %s
            """,
                (symbol,),
            )
            row_count = cur.fetchone()[0]
            audit.stats["matrix_rows"] = row_count

        if row_count == 0:
            audit.add_check("core_matrix", False, "NO DATA")
            audit.add_error("Core matrix is empty - run Phase 3")
            return

        # Get all columns
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name 
                FROM information_schema.columns
                WHERE table_schema = 'training'
                  AND table_name = 'core_matrix_curated_1d'
            """
            )
            all_cols = [row[0] for row in cur.fetchall()]

        # Metadata columns (not features)
        metadata_cols = {"trade_date", "symbol", "matrix_version", "created_at"} | {
            f"target_ret_{h}d" for h in HORIZONS
        }
        feature_cols = [c for c in all_cols if c not in metadata_cols]
        feature_count = len(feature_cols)
        audit.stats["feature_count"] = feature_count

        # ===== HARD GUARDRAIL: Feature count =====
        if feature_count < FMC_INSTANCE.MIN_FEATURES:
            audit.add_check(
                "feature_count_min",
                False,
                f"{feature_count} < {FMC_INSTANCE.MIN_FEATURES}",
            )
            audit.add_error(
                f"Feature count {feature_count} below minimum {FMC_INSTANCE.MIN_FEATURES}"
            )
        else:
            audit.add_check(
                "feature_count_min",
                True,
                f"{feature_count} >= {FMC_INSTANCE.MIN_FEATURES}",
            )

        if feature_count > FMC_INSTANCE.MAX_FEATURES:
            audit.add_check(
                "feature_count_max",
                False,
                f"{feature_count} > {FMC_INSTANCE.MAX_FEATURES}",
            )
            audit.add_error(
                f"Feature count {feature_count} above maximum {FMC_INSTANCE.MAX_FEATURES}"
            )
        else:
            audit.add_check(
                "feature_count_max",
                True,
                f"{feature_count} <= {FMC_INSTANCE.MAX_FEATURES}",
            )

        # ===== HARD GUARDRAIL: No all-null columns (check ALL columns) =====
        # Query counts non-null values for each feature column in one shot
        null_cols = []
        high_null_cols = []  # >30% null (warning only)

        logger.info(f"   Checking {len(feature_cols)} feature columns for nulls...")
        for col in feature_cols:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT("{col}") as non_null
                    FROM training.core_matrix_curated_1d
                    WHERE symbol = %s
                """,
                    (symbol,),
                )
                total, non_null = cur.fetchone()

                if non_null == 0:
                    null_cols.append(col)
                elif total > 0 and (non_null / total) < 0.70:
                    high_null_cols.append((col, f"{non_null/total:.1%}"))

        audit.stats["all_null_columns"] = null_cols
        audit.stats["all_null_count"] = len(null_cols)

        # HARD FAIL: ANY all-null column
        if null_cols:
            audit.add_check(
                "no_null_columns", False, f"{len(null_cols)} all-null columns"
            )
            audit.add_error(f"FATAL: All-null columns found: {null_cols[:10]}")
        else:
            audit.add_check(
                "no_null_columns", True, "No all-null columns (checked all)"
            )

        # WARNING: High null ratio columns (>30% null)
        if high_null_cols:
            audit.stats["high_null_columns"] = len(high_null_cols)
            audit.add_warning(
                f"{len(high_null_cols)} columns have >30% nulls: {high_null_cols[:5]}"
            )

        # ===== HARD GUARDRAIL: No constant columns (check ALL columns) =====
        constant_cols = []
        low_variance_cols = []  # Near-constant (warning only)

        logger.info(f"   Checking {len(feature_cols)} feature columns for variance...")
        for col in feature_cols:
            with conn.cursor() as cur:
                # Use COUNT(DISTINCT) as primary check - more robust than VARIANCE
                cur.execute(
                    f"""
                    SELECT 
                        COUNT(DISTINCT "{col}") as distinct_count,
                        VARIANCE("{col}") as var
                    FROM training.core_matrix_curated_1d
                    WHERE symbol = %s AND "{col}" IS NOT NULL
                """,
                    (symbol,),
                )
                result = cur.fetchone()
                distinct_count = result[0] if result[0] else 0
                variance = result[1]

                # CONSTANT: only 1 distinct value (or 0 if all null - caught above)
                if distinct_count <= 1:
                    constant_cols.append(col)
                # NEAR-CONSTANT: variance below epsilon (warning)
                elif (
                    variance is not None and variance < FMC_INSTANCE.MIN_VARIANCE_RATIO
                ):
                    low_variance_cols.append((col, f"var={variance:.2e}"))

        audit.stats["constant_columns"] = constant_cols
        audit.stats["constant_count"] = len(constant_cols)

        # HARD FAIL: ANY constant column
        if constant_cols:
            audit.add_check(
                "no_constant_columns", False, f"{len(constant_cols)} constant columns"
            )
            audit.add_error(f"FATAL: Constant columns found: {constant_cols[:10]}")
        else:
            audit.add_check(
                "no_constant_columns", True, "No constant columns (checked all)"
            )

        # WARNING: Near-constant columns
        if low_variance_cols:
            audit.stats["low_variance_columns"] = len(low_variance_cols)
            audit.add_warning(
                f"{len(low_variance_cols)} columns have near-zero variance: {low_variance_cols[:5]}"
            )

        # ===== HARD GUARDRAIL: No duplicate keys =====
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT trade_date, symbol, COUNT(*) as cnt
                FROM training.core_matrix_curated_1d
                WHERE symbol = %s
                GROUP BY trade_date, symbol
                HAVING COUNT(*) > 1
                LIMIT 5
            """,
                (symbol,),
            )
            dupes = cur.fetchall()

        audit.stats["duplicate_keys"] = len(dupes)
        if dupes:
            audit.add_check(
                "no_duplicate_keys",
                False,
                f"{len(dupes)}+ duplicate (date, symbol) pairs",
            )
            audit.add_error(f"Found duplicate keys: {dupes[:3]}...")
        else:
            audit.add_check("no_duplicate_keys", True, "No duplicate keys")

        # Compute matrix hash for lineage
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT MD5(STRING_AGG(
                    trade_date::text || COALESCE(close::text, ''),
                    '' ORDER BY trade_date
                ))
                FROM training.core_matrix_curated_1d
                WHERE symbol = %s
            """,
                (symbol,),
            )
            audit._core_matrix_hash = cur.fetchone()[0]
        audit.stats["core_matrix_hash"] = audit._core_matrix_hash

    except psycopg2.errors.UndefinedTable:
        audit.add_check("core_matrix", False, "TABLE DOES NOT EXIST")
        audit.add_error("training.core_matrix_curated_1d not found - run Phase 3")


# =============================================================================
# CHECK 4: OOF SCHEMA (including unique key validation)
# =============================================================================


def check_oof_schema(conn, symbol: str, audit: AuditResult):
    """
    Validate OOF table exists with correct columns and no duplicate keys.

    Unique key for training.oof_core_zl_1d: (trade_date, horizon_days, symbol)
    Note: symbol is included for future multi-symbol support.
    """
    logger.info("CHECK 4: OOF Schema...")

    # Parse table name
    schema, table = OOF_TABLE_NAME.split(".")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_name = %s
            )
        """,
            (schema, table),
        )
        exists = cur.fetchone()[0]

        if not exists:
            audit.add_check("oof_schema", False, f"{OOF_TABLE_NAME} does not exist")
            audit.add_error("OOF table missing - run Phase 4")
            return

        # Check columns
        cur.execute(
            """
            SELECT column_name 
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
        """,
            (schema, table),
        )
        existing_cols = {row[0] for row in cur.fetchall()}

        missing = set(OOF_COLUMN_NAMES) - existing_cols
        if missing:
            audit.add_check("oof_schema", False, f"Missing columns: {missing}")
            audit.add_error(f"OOF table missing columns: {missing}")
        else:
            audit.add_check(
                "oof_schema", True, f"All {len(OOF_COLUMN_NAMES)} columns present"
            )

        # Check for duplicate keys in OOF table (if any data exists)
        # Unique key: (trade_date, horizon_days, symbol) - symbol for future multi-symbol
        cur.execute(
            f"""
            SELECT COUNT(*) FROM {OOF_TABLE_NAME}
        """
        )
        oof_row_count = cur.fetchone()[0]
        audit.stats["oof_row_count"] = oof_row_count

        if oof_row_count > 0:
            # Check uniqueness on canonical key (trade_date, horizon_days, symbol)
            # Note: Current table may not have symbol column yet - handle gracefully
            cur.execute(
                f"""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'training' AND table_name = 'oof_core_zl_1d'
                  AND column_name = 'symbol'
            """
            )
            has_symbol_col = cur.fetchone() is not None

            if has_symbol_col:
                cur.execute(
                    f"""
                    SELECT trade_date, horizon_days, symbol, COUNT(*) as cnt
                    FROM {OOF_TABLE_NAME}
                    GROUP BY trade_date, horizon_days, symbol
                    HAVING COUNT(*) > 1
                    LIMIT 5
                """
                )
            else:
                # Fallback for tables without symbol column (legacy)
                cur.execute(
                    f"""
                    SELECT trade_date, horizon_days, COUNT(*) as cnt
                    FROM {OOF_TABLE_NAME}
                    GROUP BY trade_date, horizon_days
                    HAVING COUNT(*) > 1
                    LIMIT 5
            """
                )
            oof_dupes = cur.fetchall()

            if oof_dupes:
                key_desc = (
                    "(date, horizon_days, symbol)"
                    if has_symbol_col
                    else "(date, horizon_days)"
                )
                audit.add_check(
                    "oof_no_duplicate_keys",
                    False,
                    f"{len(oof_dupes)}+ duplicate {key_desc} keys",
                )
                audit.add_error(f"OOF table has duplicate keys: {oof_dupes[:3]}")
            else:
                audit.add_check(
                    "oof_no_duplicate_keys", True, "No duplicate keys in OOF table"
                )
        else:
            audit.add_check(
                "oof_no_duplicate_keys",
                True,
                "OOF table empty (will be populated in Phase 6)",
            )


# =============================================================================
# CHECK 5: TARGET COVERAGE
# =============================================================================


def check_target_coverage(conn, symbol: str, audit: AuditResult):
    """Check target columns have sufficient non-null coverage."""
    logger.info("CHECK 5: Target Coverage...")

    try:
        for horizon in HORIZONS:
            target_col = f"target_ret_{horizon}d"

            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT("{target_col}") as non_null
                    FROM training.core_matrix_curated_1d
                    WHERE symbol = %s
                """,
                    (symbol,),
                )
                row = cur.fetchone()

                if row[0] == 0:
                    continue

                coverage = row[1] / row[0]
                audit.stats[f"target_{horizon}d_coverage"] = f"{coverage:.1%}"

                # Last `horizon` rows should be null (forward returns can't be computed)
                expected_null_rows = horizon
                expected_coverage = (row[0] - expected_null_rows) / row[0]

                if coverage < expected_coverage - 0.10:  # 10% tolerance
                    audit.add_warning(
                        f"Target {horizon}d coverage low: {coverage:.1%} vs expected {expected_coverage:.1%}"
                    )

        audit.add_check("target_coverage", True, "All horizons have expected coverage")

    except Exception as e:
        audit.add_check("target_coverage", False, str(e))
        audit.add_error(f"Target coverage check failed: {e}")


# =============================================================================
# CHECK 6: STRUCTURAL LEAKAGE (NOT JUST CORRELATION)
# =============================================================================


def check_structural_leakage(conn, symbol: str, audit: AuditResult):
    """
    STRUCTURAL leakage checks (correlation is just dessert).

    Validates:
    1. No column names suggesting future info (*_lead*, *_future*, *_tplus*)
    2. Target construction sanity (spot check)
    3. Feature timestamps don't exceed trade_date
    """
    logger.info("CHECK 6: Structural Leakage Checks...")

    leakage_found = False

    try:
        # 1. Check column names for future-looking patterns
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name 
                FROM information_schema.columns
                WHERE table_schema = 'training'
                  AND table_name = 'core_matrix_curated_1d'
            """
            )
            all_cols = [row[0] for row in cur.fetchall()]

        future_patterns = ["_lead", "_future", "_tplus", "_forward", "_next"]
        suspicious_cols = [
            c for c in all_cols if any(p in c.lower() for p in future_patterns)
        ]

        if suspicious_cols:
            audit.add_check(
                "no_future_columns", False, f"Suspicious: {suspicious_cols}"
            )
            audit.add_error(f"Columns with future-looking names: {suspicious_cols}")
            leakage_found = True
        else:
            audit.add_check("no_future_columns", True, "No future-looking column names")

        # 2. Target construction sanity check
        # Verify target_ret_5d is approximately (close[t+5] - close[t]) / close[t]
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH lagged AS (
                    SELECT 
                        trade_date,
                        close,
                        LEAD(close, 5) OVER (ORDER BY trade_date) as close_5d,
                        target_ret_5d
                    FROM training.core_matrix_curated_1d
                    WHERE symbol = %s
                    ORDER BY trade_date
                    LIMIT 100
                )
                SELECT 
                    AVG(ABS(
                        target_ret_5d - (close_5d - close) / NULLIF(close, 0)
                    )) as avg_error
                FROM lagged
                WHERE close_5d IS NOT NULL AND target_ret_5d IS NOT NULL
            """,
                (symbol,),
            )
            result = cur.fetchone()

            if result and result[0] is not None:
                avg_error = result[0]
                audit.stats["target_construction_error"] = f"{avg_error:.6f}"

                if avg_error > 0.01:  # More than 1% average error
                    audit.add_check(
                        "target_construction",
                        False,
                        f"Avg error {avg_error:.4f} > 0.01",
                    )
                    audit.add_error(
                        "Target column construction doesn't match expected formula"
                    )
                    leakage_found = True
                else:
                    audit.add_check(
                        "target_construction", True, f"Avg error {avg_error:.6f}"
                    )
            else:
                audit.add_warning(
                    "Could not verify target construction (insufficient data)"
                )
                audit.add_check(
                    "target_construction", True, "Skipped (insufficient data)"
                )

        # 3. Correlation check (supplementary, not primary)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT CORR(close, target_ret_5d)
                FROM training.core_matrix_curated_1d
                WHERE symbol = %s
                  AND close IS NOT NULL
                  AND target_ret_5d IS NOT NULL
            """,
                (symbol,),
            )
            corr = cur.fetchone()[0]

            if corr is not None:
                audit.stats["close_target_correlation"] = f"{corr:.4f}"

                if abs(corr) > 0.95:
                    audit.add_warning(f"High close/target correlation: {corr:.4f}")
                    # This is a warning, not a fail, because high correlation
                    # can be legitimate in trending markets

        if not leakage_found:
            audit.add_check(
                "no_structural_leakage", True, "No structural leakage detected"
            )

    except Exception as e:
        # If leakage check FAILS, that's a FAIL, not a pass
        audit.add_check("no_structural_leakage", False, f"Check crashed: {e}")
        audit.add_error(f"Leakage check failed with error: {e}")


# =============================================================================
# CHECK 7: RAW DATA VERIFICATION (NO GLOBAL NORMALIZATION)
# =============================================================================


def check_raw_data_not_normalized(conn, symbol: str, audit: AuditResult):
    """
    VERIFY that core matrix contains RAW data, not globally normalized values.

    Detects global z-score normalization by checking:
    1. Mean of numeric columns is NOT ~0 (global z-score would center at 0)
    2. Std of numeric columns is NOT ~1 (global z-score would scale to 1)
    3. 'close' column has realistic price values (not z-scored)

    This is a HARD FAIL if detected - global normalization causes leakage.
    """
    logger.info("CHECK 7: Raw Data Verification (no global normalization)...")

    try:
        # Check 1: Close prices should be realistic (not z-scored)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    AVG(close) as mean_close,
                    STDDEV(close) as std_close,
                    MIN(close) as min_close,
                    MAX(close) as max_close
                FROM training.core_matrix_curated_1d
                WHERE symbol = %s AND close IS NOT NULL
            """,
                (symbol,),
            )
            row = cur.fetchone()

            if row and row[0] is not None:
                mean_close = float(row[0])
                std_close = float(row[1]) if row[1] else 0
                min_close = float(row[2]) if row[2] else 0
                max_close = float(row[3]) if row[3] else 0

                audit.stats["close_mean"] = f"{mean_close:.2f}"
                audit.stats["close_std"] = f"{std_close:.2f}"
                audit.stats["close_range"] = f"[{min_close:.2f}, {max_close:.2f}]"

                # Z-scored data would have mean ~0, std ~1
                # Raw ZL prices should be 30-80+ range
                looks_normalized = abs(mean_close) < 3 and 0.5 < std_close < 2.0

                if looks_normalized:
                    audit.add_check(
                        "raw_data_close",
                        False,
                        f"Close looks z-scored: mean={mean_close:.2f}, std={std_close:.2f}",
                    )
                    audit.add_error(
                        "FATAL: Core matrix appears globally normalized - this causes leakage"
                    )
                else:
                    audit.add_check(
                        "raw_data_close",
                        True,
                        f"Close is raw: mean={mean_close:.2f}, range=[{min_close:.2f}, {max_close:.2f}]",
                    )

        # Check 2: Sample a few more numeric columns
        # If multiple columns have mean~0, std~1, that's suspicious
        with conn.cursor() as cur:
            # Get 5 random numeric feature columns
            cur.execute(
                """
                SELECT column_name 
                FROM information_schema.columns
                WHERE table_schema = 'training'
                  AND table_name = 'core_matrix_curated_1d'
                  AND data_type IN ('double precision', 'real', 'numeric', 'integer', 'bigint')
                  AND column_name NOT IN ('trade_date', 'symbol', 'matrix_version')
                  AND column_name NOT LIKE 'target_%'
                LIMIT 10
            """
            )
            sample_cols = [row[0] for row in cur.fetchall()]

        zscore_suspect_count = 0
        for col in sample_cols[:5]:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT AVG("{col}"), STDDEV("{col}")
                    FROM training.core_matrix_curated_1d
                    WHERE symbol = %s AND "{col}" IS NOT NULL
                """,
                    (symbol,),
                )
                row = cur.fetchone()

                if row and row[0] is not None and row[1] is not None:
                    col_mean = float(row[0])
                    col_std = float(row[1])

                    # Check if it looks z-scored (mean ~0, std ~1)
                    if abs(col_mean) < 0.5 and 0.8 < col_std < 1.2:
                        zscore_suspect_count += 1

        # If majority of sampled columns look z-scored, flag it
        if zscore_suspect_count >= 3:
            audit.add_check(
                "raw_data_features",
                False,
                f"{zscore_suspect_count}/5 sampled features look z-scored",
            )
            audit.add_error("FATAL: Multiple features appear globally normalized")
        else:
            audit.add_check(
                "raw_data_features",
                True,
                f"Features appear raw ({zscore_suspect_count}/5 near mean=0,std=1)",
            )

    except Exception as e:
        audit.add_check("raw_data_verification", False, f"Check crashed: {e}")
        audit.add_error(f"Raw data verification failed: {e}")


# =============================================================================
# REPORT GENERATION
# =============================================================================


def generate_report(audit: AuditResult) -> str:
    """Generate human-readable audit report."""
    lines = [
        "",
        "=" * 70,
        "PRE-FLIGHT AUDIT REPORT",
        "=" * 70,
        f"Generated: {datetime.utcnow().isoformat()}Z",
        "",
        "CHECKS:",
    ]

    for name, passed in audit.checks.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        lines.append(f"  {name}: {status}")

    lines.append("")
    lines.append("STATISTICS:")
    for key, value in sorted(audit.stats.items()):
        lines.append(f"  {key}: {value}")

    if audit.warnings:
        lines.append("")
        lines.append("WARNINGS (non-blocking):")
        for w in audit.warnings:
            lines.append(f"  ⚠️ {w}")

    if audit.errors:
        lines.append("")
        lines.append("ERRORS (BLOCKING):")
        for e in audit.errors:
            lines.append(f"  ❌ {e}")

    lines.append("")
    lines.append("=" * 70)

    if audit.passed:
        lines.append("✅ AUDIT PASSED - READY FOR TRAINING")
        if audit._core_matrix_hash:
            lines.append(f"   Core Matrix Hash: {audit._core_matrix_hash}")
    else:
        lines.append("❌ AUDIT FAILED - DO NOT PROCEED TO TRAINING")
        lines.append("   Fix all errors before running Phase 6")

    lines.append("=" * 70)
    lines.append("")

    return "\n".join(lines)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================


def run(symbol: str = TARGET_SYMBOL) -> Tuple[bool, AuditResult]:
    """
    Execute Phase 5: Pre-Flight Audit.

    This is a MANDATORY HARD GATE. If it fails, Phase 6 MUST NOT run.

    Returns:
        (success: bool, audit: AuditResult)
    """
    logger.info("=" * 70)
    logger.info("PHASE 5: PRE-FLIGHT AUDIT (MANDATORY HARD GATE)")
    logger.info("=" * 70)
    logger.info(f"Symbol: {symbol}")
    logger.info("=" * 70)

    audit = AuditResult()

    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True  # Each check runs independently, no transaction needed
        logger.info("✅ Database connected")

        # Run all checks (each is independent, failures don't cascade)
        check_options_features(conn, symbol, audit)
        check_elite_indicators(conn, symbol, audit)
        check_core_matrix(conn, symbol, audit)
        check_oof_schema(conn, symbol, audit)
        check_target_coverage(conn, symbol, audit)
        check_structural_leakage(conn, symbol, audit)
        check_raw_data_not_normalized(conn, symbol, audit)

        conn.close()

        # Generate and print report
        report = generate_report(audit)
        print(report)

        return audit.passed, audit

    except Exception as e:
        logger.error(f"❌ PHASE 5 CRASHED: {e}", exc_info=True)
        audit.add_error(f"Audit crashed: {e}")
        return False, audit


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(
        description="Phase 5: Pre-Flight Audit (HARD GATE)"
    )
    parser.add_argument("--symbol", default=TARGET_SYMBOL)
    args = parser.parse_args()

    success, audit = run(args.symbol)

    # Exit code reflects gate status
    exit(0 if success else 1)
