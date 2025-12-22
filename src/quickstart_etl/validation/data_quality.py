"""
Data Quality Validation Gatekeeper for ZINC-FUSION-V15

This module provides comprehensive validation checks for incoming data:
- Duplicate detection
- Schema validation
- Type casting verification
- Null/missing value analysis
- Date range validation
- Primary key integrity

Usage:
    from quickstart_etl.validation.data_quality import DataQualityGatekeeper

    gatekeeper = DataQualityGatekeeper()
    report = gatekeeper.validate_parquet('/path/to/file.parquet',
                                          primary_key=['symbol', 'as_of_date'])

    if not report.passed:
        raise DataQualityError(report.summary())
"""

import pandas as pd
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a single validation check."""

    check_name: str
    passed: bool
    message: str
    severity: str = "ERROR"  # ERROR, WARNING, INFO
    details: dict = field(default_factory=dict)


@dataclass
class ValidationReport:
    """Aggregate validation report for a dataset."""

    source: str
    timestamp: datetime = field(default_factory=datetime.now)
    results: list[ValidationResult] = field(default_factory=list)
    row_count: int = 0
    column_count: int = 0

    @property
    def passed(self) -> bool:
        """Returns True if no ERROR-level checks failed."""
        return all(r.passed for r in self.results if r.severity == "ERROR")

    @property
    def warnings(self) -> list[ValidationResult]:
        """Returns all WARNING-level results."""
        return [r for r in self.results if r.severity == "WARNING" and not r.passed]

    @property
    def errors(self) -> list[ValidationResult]:
        """Returns all ERROR-level results that failed."""
        return [r for r in self.results if r.severity == "ERROR" and not r.passed]

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"═══ Data Quality Report: {self.source} ═══",
            f"Timestamp: {self.timestamp.isoformat()}",
            f"Rows: {self.row_count:,} | Columns: {self.column_count}",
            f"Status: {'✅ PASSED' if self.passed else '❌ FAILED'}",
            "",
        ]

        if self.errors:
            lines.append("ERRORS:")
            for r in self.errors:
                lines.append(f"  ❌ {r.check_name}: {r.message}")

        if self.warnings:
            lines.append("WARNINGS:")
            for r in self.warnings:
                lines.append(f"  ⚠️  {r.check_name}: {r.message}")

        passed = [r for r in self.results if r.passed]
        if passed:
            lines.append(f"PASSED: {len(passed)} checks")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Export as dictionary for logging/storage."""
        return {
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "passed": self.passed,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "results": [
                {
                    "check": r.check_name,
                    "passed": r.passed,
                    "severity": r.severity,
                    "message": r.message,
                    "details": r.details,
                }
                for r in self.results
            ],
        }


class DataQualityError(Exception):
    """Raised when data quality validation fails."""

    def __init__(self, report: ValidationReport):
        self.report = report
        super().__init__(report.summary())


class DataQualityGatekeeper:
    """
    Ultra-badass data quality gatekeeper for production-grade ZINC-FUSION-V15

    This class validates incoming data for:
    - Schema integrity and consistency
    - Primary key uniqueness and validity
    - Date range continuity and coverage
    - Null value analysis with configurable thresholds
    - Type casting and format validation
    - Duplicate detection and removal recommendations

    Built for institutional-grade commodity forecasting with zero tolerance
    for data quality issues that could impact trading decisions.
    """

    def __init__(self, strict_mode: bool = True):
        """
        Initialize gatekeeper.

        Args:
            strict_mode: If True, raise exception on validation failure.
                        If False, return report without raising.
        """
        self.strict_mode = strict_mode

    def validate_parquet(
        self,
        file_path: str | Path,
        primary_key: list[str] | None = None,
        required_columns: list[str] | None = None,
        date_column: str | None = None,
        min_date: str | None = None,
        max_date: str | None = None,
        max_null_pct: float = 0.5,
        numeric_columns: list[str] | None = None,
    ) -> ValidationReport:
        """
        Validate a parquet file.

        Args:
            file_path: Path to parquet file
            primary_key: Columns that should be unique together
            required_columns: Columns that must exist
            date_column: Column containing dates for range validation
            min_date: Minimum expected date (YYYY-MM-DD)
            max_date: Maximum expected date (YYYY-MM-DD)
            max_null_pct: Maximum allowed null percentage (0-1)
            numeric_columns: Columns that should be numeric

        Returns:
            ValidationReport with all check results
        """
        file_path = Path(file_path)
        report = ValidationReport(source=str(file_path))

        # Check file exists
        if not file_path.exists():
            report.results.append(
                ValidationResult(
                    check_name="file_exists",
                    passed=False,
                    message=f"File not found: {file_path}",
                    severity="ERROR",
                )
            )
            return self._finalize(report)

        # Load data
        try:
            df = pd.read_parquet(file_path)
        except Exception as e:
            report.results.append(
                ValidationResult(
                    check_name="file_readable",
                    passed=False,
                    message=f"Failed to read parquet: {e}",
                    severity="ERROR",
                )
            )
            return self._finalize(report)

        report.row_count = len(df)
        report.column_count = len(df.columns)

        # Run all checks
        report.results.extend(self._check_not_empty(df))

        if required_columns:
            report.results.extend(self._check_required_columns(df, required_columns))

        if primary_key:
            report.results.extend(self._check_duplicates(df, primary_key))

        if date_column and date_column in df.columns:
            report.results.extend(
                self._check_date_range(df, date_column, min_date, max_date)
            )

        report.results.extend(self._check_null_percentages(df, max_null_pct))

        if numeric_columns:
            report.results.extend(self._check_numeric_types(df, numeric_columns))

        return self._finalize(report)

    def validate_dataframe(
        self,
        df: pd.DataFrame,
        source_name: str,
        primary_key: list[str] | None = None,
        required_columns: list[str] | None = None,
        date_column: str | None = None,
        min_date: str | None = None,
        max_date: str | None = None,
        max_null_pct: float = 0.5,
        numeric_columns: list[str] | None = None,
    ) -> ValidationReport:
        """
        Validate a pandas DataFrame.

        Same parameters as validate_parquet but for in-memory data.
        """
        report = ValidationReport(source=source_name)
        report.row_count = len(df)
        report.column_count = len(df.columns)

        report.results.extend(self._check_not_empty(df))

        if required_columns:
            report.results.extend(self._check_required_columns(df, required_columns))

        if primary_key:
            report.results.extend(self._check_duplicates(df, primary_key))

        if date_column and date_column in df.columns:
            report.results.extend(
                self._check_date_range(df, date_column, min_date, max_date)
            )

        report.results.extend(self._check_null_percentages(df, max_null_pct))

        if numeric_columns:
            report.results.extend(self._check_numeric_types(df, numeric_columns))

        return self._finalize(report)

    def _check_not_empty(self, df: pd.DataFrame) -> list[ValidationResult]:
        """Check that dataframe is not empty."""
        return [
            ValidationResult(
                check_name="not_empty",
                passed=len(df) > 0,
                message=f"DataFrame has {len(df):,} rows"
                if len(df) > 0
                else "DataFrame is empty!",
                severity="ERROR",
                details={"row_count": len(df)},
            )
        ]

    def _check_required_columns(
        self, df: pd.DataFrame, required: list[str]
    ) -> list[ValidationResult]:
        """Check that required columns exist."""
        missing = [c for c in required if c not in df.columns]
        return [
            ValidationResult(
                check_name="required_columns",
                passed=len(missing) == 0,
                message=f"Missing columns: {missing}"
                if missing
                else "All required columns present",
                severity="ERROR",
                details={"missing": missing, "required": required},
            )
        ]

    def _check_duplicates(
        self, df: pd.DataFrame, key_columns: list[str]
    ) -> list[ValidationResult]:
        """Check for duplicate rows on primary key."""
        results = []

        # Check key columns exist
        missing_keys = [c for c in key_columns if c not in df.columns]
        if missing_keys:
            results.append(
                ValidationResult(
                    check_name="duplicate_check",
                    passed=False,
                    message=f"Key columns not found: {missing_keys}",
                    severity="ERROR",
                )
            )
            return results

        # Count duplicates
        dupe_mask = df.duplicated(subset=key_columns, keep=False)
        dupe_count = dupe_mask.sum()

        results.append(
            ValidationResult(
                check_name="no_duplicates",
                passed=dupe_count == 0,
                message=f"Found {dupe_count:,} duplicate rows on {key_columns}"
                if dupe_count > 0
                else f"No duplicates on {key_columns}",
                severity="ERROR",
                details={
                    "duplicate_count": int(dupe_count),
                    "key_columns": key_columns,
                    "sample_duplicates": df[dupe_mask].head(5).to_dict("records")
                    if dupe_count > 0
                    else [],
                },
            )
        )

        return results

    def _check_date_range(
        self,
        df: pd.DataFrame,
        date_col: str,
        min_date: str | None,
        max_date: str | None,
    ) -> list[ValidationResult]:
        """Check date column is within expected range."""
        results = []

        try:
            dates = pd.to_datetime(df[date_col])
            actual_min = dates.min()
            actual_max = dates.max()

            results.append(
                ValidationResult(
                    check_name="date_range",
                    passed=True,
                    message=f"Date range: {actual_min.date()} to {actual_max.date()}",
                    severity="INFO",
                    details={
                        "min_date": str(actual_min.date()),
                        "max_date": str(actual_max.date()),
                    },
                )
            )

            if min_date:
                expected_min = pd.to_datetime(min_date)
                if actual_min < expected_min:
                    results.append(
                        ValidationResult(
                            check_name="date_min_check",
                            passed=False,
                            message=f"Data starts before expected: {actual_min.date()} < {expected_min.date()}",
                            severity="WARNING",
                        )
                    )

            if max_date:
                expected_max = pd.to_datetime(max_date)
                if actual_max > expected_max:
                    results.append(
                        ValidationResult(
                            check_name="date_max_check",
                            passed=False,
                            message=f"Data extends beyond expected: {actual_max.date()} > {expected_max.date()}",
                            severity="WARNING",
                        )
                    )

        except Exception as e:
            results.append(
                ValidationResult(
                    check_name="date_parse",
                    passed=False,
                    message=f"Failed to parse dates in {date_col}: {e}",
                    severity="ERROR",
                )
            )

        return results

    def _check_null_percentages(
        self, df: pd.DataFrame, max_pct: float
    ) -> list[ValidationResult]:
        """Check null percentages per column."""
        results = []

        null_pcts = df.isnull().mean()
        high_null_cols = null_pcts[null_pcts > max_pct]

        if len(high_null_cols) > 0:
            for col, pct in high_null_cols.items():
                results.append(
                    ValidationResult(
                        check_name=f"null_check_{col}",
                        passed=False,
                        message=f"Column '{col}' has {pct:.1%} nulls (max: {max_pct:.1%})",
                        severity="WARNING",
                        details={"column": col, "null_pct": float(pct)},
                    )
                )

        # All-null columns are errors
        all_null = null_pcts[null_pcts == 1.0]
        for col in all_null.index:
            results.append(
                ValidationResult(
                    check_name=f"all_null_{col}",
                    passed=False,
                    message=f"Column '{col}' is 100% null",
                    severity="WARNING",  # Warning, not error - might be optional column
                    details={"column": col},
                )
            )

        if len(high_null_cols) == 0:
            results.append(
                ValidationResult(
                    check_name="null_check",
                    passed=True,
                    message=f"All columns below {max_pct:.0%} null threshold",
                    severity="INFO",
                )
            )

        return results

    def _check_numeric_types(
        self, df: pd.DataFrame, columns: list[str]
    ) -> list[ValidationResult]:
        """Check that specified columns can be cast to numeric."""
        results = []

        for col in columns:
            if col not in df.columns:
                continue

            # Try to convert to numeric
            original_type = df[col].dtype
            converted = pd.to_numeric(df[col], errors="coerce")
            failed_count = converted.isnull().sum() - df[col].isnull().sum()

            if failed_count > 0:
                results.append(
                    ValidationResult(
                        check_name=f"numeric_type_{col}",
                        passed=False,
                        message=f"Column '{col}' has {failed_count:,} non-numeric values (dtype: {original_type})",
                        severity="ERROR",
                        details={
                            "column": col,
                            "original_dtype": str(original_type),
                            "failed_count": int(failed_count),
                        },
                    )
                )
            else:
                results.append(
                    ValidationResult(
                        check_name=f"numeric_type_{col}",
                        passed=True,
                        message=f"Column '{col}' is numeric-compatible",
                        severity="INFO",
                    )
                )

        return results

    def _finalize(self, report: ValidationReport) -> ValidationReport:
        """Finalize report and optionally raise exception."""
        if self.strict_mode and not report.passed:
            raise DataQualityError(report)

        # Log summary
        logger.info(report.summary())

        return report


# ============================================================
# Pre-configured validators for ZINC-FUSION data sources
# ============================================================


def validate_databento_futures_1d(file_path: str | Path) -> ValidationReport:
    """Validate Databento daily futures OHLCV data."""
    gatekeeper = DataQualityGatekeeper(strict_mode=False)
    return gatekeeper.validate_parquet(
        file_path,
        primary_key=["symbol", "as_of_date"],
        required_columns=[
            "symbol",
            "as_of_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
        date_column="as_of_date",
        numeric_columns=["open", "high", "low", "close", "volume"],
    )


def validate_fred_economic(file_path: str | Path) -> ValidationReport:
    """Validate FRED economic indicator data."""
    gatekeeper = DataQualityGatekeeper(strict_mode=False)
    return gatekeeper.validate_parquet(
        file_path,
        primary_key=["series_id", "date"],
        required_columns=["series_id", "date", "value"],
        date_column="date",
        numeric_columns=["value"],
    )


def validate_cftc_cot(file_path: str | Path) -> ValidationReport:
    """Validate CFTC Commitment of Traders data."""
    gatekeeper = DataQualityGatekeeper(strict_mode=False)
    return gatekeeper.validate_parquet(
        file_path,
        primary_key=["symbol", "report_date"],
        required_columns=[
            "symbol",
            "report_date",
            "open_interest",
            "managed_money_net",
        ],
        date_column="report_date",
    )


def validate_ml_matrix(file_path: str | Path) -> ValidationReport:
    """Validate daily ML training matrix."""
    gatekeeper = DataQualityGatekeeper(strict_mode=False)
    return gatekeeper.validate_parquet(
        file_path,
        primary_key=["as_of_date"],
        required_columns=["as_of_date", "close"],
        date_column="as_of_date",
        max_null_pct=0.3,  # Training data should be fairly complete
    )


# Additional alias for Dagster asset imports
DataQualityValidator = DataQualityGatekeeper


# ============================================================
# CLI Entry Point
# ============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python data_quality.py <parquet_file> [primary_key_cols...]")
        sys.exit(1)

    file_path = sys.argv[1]
    pk_cols = sys.argv[2:] if len(sys.argv) > 2 else None

    gatekeeper = DataQualityGatekeeper(strict_mode=False)
    report = gatekeeper.validate_parquet(file_path, primary_key=pk_cols)

    print(report.summary())
    sys.exit(0 if report.passed else 1)
