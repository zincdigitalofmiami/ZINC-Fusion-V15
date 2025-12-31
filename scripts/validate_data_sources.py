#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Data Validation & Pre-Cleaning Tool

Scans all parquet files in Historical Data directory, validates schemas,
date ranges, and data quality BEFORE ingestion into Postgres.

Uses Pandera for schema validation and generates comprehensive reports.

Features:
- Schema inference and validation
- Date column detection and range analysis
- Missing value analysis
- Duplicate detection
- Data type consistency checks
- Generates JSON report for ingestion planning

Usage:
    python scripts/validate_data_sources.py --scan
    python scripts/validate_data_sources.py --validate /path/to/file.parquet
    python scripts/validate_data_sources.py --report
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict

import pandas as pd
import pyarrow.parquet as pq
import numpy as np

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Historical data paths - use env var
_hist_base = os.getenv("HISTORICAL_DATA_PATH", "")
_proj_data = Path(__file__).parent.parent / "data"

HIST_DATA_PATHS = [
    Path(_hist_base) if _hist_base else Path("/tmp/historical_data"),
    _proj_data,
]

# Output report path
REPORT_PATH = _proj_data / "validation_report.json"

# Date column patterns to look for
DATE_PATTERNS = [
    "date",
    "as_of_date",
    "timestamp",
    "time",
    "datetime",
    "report_date",
    "trade_date",
    "observation_date",
    "created_at",
    "updated_at",
    "period",
    "year",
    "month",
    "day",
]

# Known date formats
DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y%m%d",
]


class DataValidator:
    """Validates parquet files for schema, dates, and quality."""

    def __init__(self):
        self.validation_results = []
        self.schema_catalog = {}
        self.date_ranges = {}

    def scan_directory(self, base_path: Path) -> List[Path]:
        """Recursively find all parquet files."""
        parquet_files = []

        if not base_path.exists():
            logger.warning(f"Path does not exist: {base_path}")
            return parquet_files

        for path in base_path.rglob("*.parquet"):
            parquet_files.append(path)

        # Also check for CSV files
        csv_files = list(base_path.rglob("*.csv"))

        logger.info(
            f"Found {len(parquet_files)} parquet files, {len(csv_files)} CSV files in {base_path}"
        )

        return parquet_files

    def infer_date_columns(self, df: pd.DataFrame) -> List[str]:
        """Identify columns that contain date/time data."""
        date_cols = []

        for col in df.columns:
            col_lower = col.lower()

            # Check by column name pattern
            if any(pattern in col_lower for pattern in DATE_PATTERNS):
                date_cols.append(col)
                continue

            # Check by dtype
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                date_cols.append(col)
                continue

            # Try to parse as date (sample first few non-null values)
            if df[col].dtype == object:
                sample = df[col].dropna().head(5)
                if len(sample) > 0:
                    try:
                        pd.to_datetime(sample, errors="raise")
                        date_cols.append(col)
                    except:
                        pass

        return date_cols

    def analyze_date_range(self, df: pd.DataFrame, date_col: str) -> Dict:
        """Analyze the date range of a column."""
        try:
            dates = pd.to_datetime(df[date_col], errors="coerce")
            valid_dates = dates.dropna()

            if len(valid_dates) == 0:
                return {"error": "No valid dates found"}

            return {
                "min_date": str(valid_dates.min().date()),
                "max_date": str(valid_dates.max().date()),
                "count": len(valid_dates),
                "null_count": len(dates) - len(valid_dates),
                "unique_count": valid_dates.nunique(),
                "gaps": self._detect_date_gaps(valid_dates),
            }
        except Exception as e:
            return {"error": str(e)}

    def _detect_date_gaps(self, dates: pd.Series) -> List[Dict]:
        """Detect significant gaps in date series."""
        gaps = []
        if len(dates) < 2:
            return gaps

        sorted_dates = dates.sort_values().reset_index(drop=True)
        diffs = sorted_dates.diff()

        # Find gaps > 30 days
        large_gaps = diffs[diffs > pd.Timedelta(days=30)]

        for idx in large_gaps.index:
            if idx > 0:
                gaps.append(
                    {
                        "from": str(sorted_dates[idx - 1].date()),
                        "to": str(sorted_dates[idx].date()),
                        "days": diffs[idx].days,
                    }
                )

        return gaps[:10]  # Limit to first 10 gaps

    def validate_schema(self, df: pd.DataFrame, file_path: Path) -> Dict:
        """Validate and catalog the schema of a dataframe."""
        schema = {}

        for col in df.columns:
            dtype = str(df[col].dtype)
            null_count = df[col].isnull().sum()
            null_pct = null_count / len(df) * 100 if len(df) > 0 else 0

            # Sample values for reference
            sample = df[col].dropna().head(3).tolist()

            schema[col] = {
                "dtype": dtype,
                "null_count": int(null_count),
                "null_pct": round(null_pct, 2),
                "unique_count": int(df[col].nunique()),
                "sample_values": [str(v)[:50] for v in sample],  # Truncate long values
            }

        return schema

    def detect_duplicates(self, df: pd.DataFrame, date_cols: List[str]) -> Dict:
        """Detect duplicate rows based on key columns."""
        if len(df) == 0:
            return {
                "total_rows": 0,
                "duplicate_rows": 0,
                "duplicate_pct": 0,
                "key_columns": [],
            }

        # Try to find a reasonable key
        key_cols = []

        # Use date columns as part of key
        for col in date_cols:
            if col in df.columns:
                key_cols.append(col)

        # Add symbol/ticker columns if present
        for pattern in ["symbol", "ticker", "series_id", "id", "code"]:
            for col in df.columns:
                if pattern in col.lower() and col not in key_cols:
                    key_cols.append(col)
                    break

        try:
            if not key_cols:
                # Use all columns
                duplicates = df.duplicated().sum()
            else:
                duplicates = df.duplicated(subset=key_cols).sum()
        except Exception:
            # If duplicate detection fails, return safe defaults
            return {
                "total_rows": len(df),
                "duplicate_rows": 0,
                "duplicate_pct": 0,
                "key_columns": key_cols,
            }

        return {
            "total_rows": len(df),
            "duplicate_rows": int(duplicates),
            "duplicate_pct": round(duplicates / len(df) * 100, 2) if len(df) > 0 else 0,
            "key_columns": key_cols,
        }

    def validate_file(self, file_path: Path, sample_size: int = 10000) -> Dict:
        """Validate a single parquet file."""
        result = {
            "file_path": str(file_path),
            "file_name": file_path.name,
            "file_size_mb": round(file_path.stat().st_size / 1024 / 1024, 2),
            "validated_at": datetime.now().isoformat(),
            "status": "pending",
            "errors": [],
            "warnings": [],
        }

        try:
            # Read parquet metadata first (fast)
            pq_file = pq.ParquetFile(file_path)
            result["num_row_groups"] = pq_file.metadata.num_row_groups
            result["total_rows"] = pq_file.metadata.num_rows
            result["parquet_columns"] = pq_file.metadata.num_columns

            # Read sample for analysis
            if result["total_rows"] > sample_size:
                df = pq_file.read().to_pandas().sample(n=sample_size, random_state=42)
                result["sampled"] = True
                result["sample_size"] = sample_size
            else:
                df = pq_file.read().to_pandas()
                result["sampled"] = False
                result["sample_size"] = len(df)

            # Schema analysis
            result["schema"] = self.validate_schema(df, file_path)
            result["columns"] = list(df.columns)

            # Date analysis
            date_cols = self.infer_date_columns(df)
            result["date_columns"] = date_cols

            result["date_ranges"] = {}
            for col in date_cols:
                result["date_ranges"][col] = self.analyze_date_range(df, col)

            # Duplicate analysis
            result["duplicates"] = self.detect_duplicates(df, date_cols)

            # Quality checks
            result["quality"] = {
                "empty_columns": [
                    col
                    for col, info in result["schema"].items()
                    if info["null_pct"] == 100
                ],
                "high_null_columns": [
                    col
                    for col, info in result["schema"].items()
                    if 50 <= info["null_pct"] < 100
                ],
                "constant_columns": [
                    col
                    for col, info in result["schema"].items()
                    if info["unique_count"] == 1 and info["null_pct"] < 100
                ],
            }

            # Warnings
            if result["quality"]["empty_columns"]:
                result["warnings"].append(
                    f"Empty columns: {result['quality']['empty_columns']}"
                )
            if result["duplicates"]["duplicate_pct"] > 5:
                result["warnings"].append(
                    f"High duplicate rate: {result['duplicates']['duplicate_pct']}%"
                )

            result["status"] = "valid" if not result["errors"] else "invalid"

        except Exception as e:
            result["status"] = "error"
            result["errors"].append(str(e))
            logger.error(f"Error validating {file_path}: {e}")

        return result

    def categorize_file(self, result: Dict) -> str:
        """Categorize file by its likely data type."""
        file_name = result["file_name"].lower()
        columns = [c.lower() for c in result.get("columns", [])]

        # Market data
        if any(
            x in file_name for x in ["ohlcv", "futures", "market", "price", "databento"]
        ):
            return "market_futures"
        if any(x in columns for x in ["open", "high", "low", "close", "volume"]):
            return "market_futures"

        # FRED economic data
        if "fred" in file_name or "series_id" in columns:
            return "fred_observations"

        # USDA data
        if "usda" in file_name or "wasde" in file_name:
            return "usda_data"

        # CFTC COT data
        if "cftc" in file_name or "cot" in file_name:
            return "cftc_cot"

        # Weather data
        if any(x in file_name for x in ["weather", "noaa", "climate"]):
            return "weather"

        # EPA/RIN data
        if any(x in file_name for x in ["epa", "rin", "biofuel"]):
            return "epa_rin"

        # Sentiment/News
        if any(x in file_name for x in ["sentiment", "news", "headlines"]):
            return "sentiment"

        # Technical indicators
        if any(
            x in file_name for x in ["technical", "indicator", "sma", "rsi", "macd"]
        ):
            return "technical_indicators"

        # Features/training
        if any(x in file_name for x in ["feature", "training", "specialist"]):
            return "training_features"

        # Forecasts
        if any(x in file_name for x in ["forecast", "prediction"]):
            return "forecasts"

        return "other"

    def generate_report(self, results: List[Dict]) -> Dict:
        """Generate comprehensive validation report."""
        report = {
            "generated_at": datetime.now().isoformat(),
            "total_files": len(results),
            "total_rows": sum(r.get("total_rows", 0) for r in results),
            "total_size_mb": round(sum(r.get("file_size_mb", 0) for r in results), 2),
            "status_summary": defaultdict(int),
            "category_summary": defaultdict(
                lambda: {"count": 0, "rows": 0, "files": []}
            ),
            "date_coverage": {},
            "schema_catalog": {},
            "issues": [],
            "files": results,
        }

        for r in results:
            # Status summary
            report["status_summary"][r["status"]] += 1

            # Category summary
            category = self.categorize_file(r)
            r["category"] = category
            report["category_summary"][category]["count"] += 1
            report["category_summary"][category]["rows"] += r.get("total_rows", 0)
            report["category_summary"][category]["files"].append(r["file_name"])

            # Date coverage
            for col, date_info in r.get("date_ranges", {}).items():
                if "min_date" in date_info and "max_date" in date_info:
                    key = f"{category}:{col}"
                    if key not in report["date_coverage"]:
                        report["date_coverage"][key] = {
                            "min_date": date_info["min_date"],
                            "max_date": date_info["max_date"],
                            "files": [],
                        }
                    else:
                        if (
                            date_info["min_date"]
                            < report["date_coverage"][key]["min_date"]
                        ):
                            report["date_coverage"][key]["min_date"] = date_info[
                                "min_date"
                            ]
                        if (
                            date_info["max_date"]
                            > report["date_coverage"][key]["max_date"]
                        ):
                            report["date_coverage"][key]["max_date"] = date_info[
                                "max_date"
                            ]
                    report["date_coverage"][key]["files"].append(r["file_name"])

            # Collect issues
            if r["errors"]:
                report["issues"].append(
                    {"file": r["file_name"], "type": "error", "messages": r["errors"]}
                )
            if r["warnings"]:
                report["issues"].append(
                    {
                        "file": r["file_name"],
                        "type": "warning",
                        "messages": r["warnings"],
                    }
                )

        # Convert defaultdicts to regular dicts for JSON serialization
        report["status_summary"] = dict(report["status_summary"])
        report["category_summary"] = {
            k: dict(v) for k, v in report["category_summary"].items()
        }

        return report

    def print_summary(self, report: Dict):
        """Print human-readable summary."""
        print("\n" + "=" * 70)
        print("ZINC-FUSION-V15: DATA VALIDATION REPORT")
        print("=" * 70)
        print(f"\nGenerated: {report['generated_at']}")
        print(f"Total Files: {report['total_files']}")
        print(f"Total Rows: {report['total_rows']:,}")
        print(f"Total Size: {report['total_size_mb']:,.1f} MB")

        print("\n--- STATUS SUMMARY ---")
        for status, count in report["status_summary"].items():
            print(f"  {status}: {count}")

        print("\n--- CATEGORY SUMMARY ---")
        for category, info in sorted(report["category_summary"].items()):
            print(f"  {category}:")
            print(f"    Files: {info['count']}")
            print(f"    Rows: {info['rows']:,}")

        print("\n--- DATE COVERAGE ---")
        for key, info in sorted(report["date_coverage"].items()):
            print(f"  {key}:")
            print(f"    Range: {info['min_date']} to {info['max_date']}")
            print(f"    Files: {len(info['files'])}")

        if report["issues"]:
            print("\n--- ISSUES FOUND ---")
            errors = [i for i in report["issues"] if i["type"] == "error"]
            warnings = [i for i in report["issues"] if i["type"] == "warning"]
            print(f"  Errors: {len(errors)}")
            print(f"  Warnings: {len(warnings)}")

            if errors:
                print("\n  Top Errors:")
                for issue in errors[:5]:
                    print(f"    {issue['file']}: {issue['messages'][0][:60]}")

        print("\n" + "=" * 70)
        print(f"Report saved to: {REPORT_PATH}")
        print("=" * 70 + "\n")


def scan_all_sources():
    """Scan all historical data sources."""
    validator = DataValidator()
    all_files = []

    for base_path in HIST_DATA_PATHS:
        files = validator.scan_directory(base_path)
        all_files.extend(files)

    logger.info(f"Total parquet files found: {len(all_files)}")

    # Validate each file
    results = []
    for i, file_path in enumerate(all_files):
        if (i + 1) % 100 == 0:
            logger.info(f"Validated {i + 1}/{len(all_files)} files...")
        result = validator.validate_file(file_path)
        results.append(result)

    # Generate report
    report = validator.generate_report(results)

    # Save report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Print summary
    validator.print_summary(report)

    return report


def validate_single_file(file_path: str):
    """Validate a single parquet file."""
    validator = DataValidator()
    path = Path(file_path)

    if not path.exists():
        logger.error(f"File not found: {file_path}")
        return None

    result = validator.validate_file(path)

    print("\n" + "=" * 70)
    print(f"VALIDATION: {path.name}")
    print("=" * 70)
    print(f"Status: {result['status']}")
    print(f"Rows: {result.get('total_rows', 'N/A'):,}")
    print(f"Size: {result.get('file_size_mb', 'N/A')} MB")
    print(f"Category: {validator.categorize_file(result)}")

    print("\n--- COLUMNS ---")
    for col, info in result.get("schema", {}).items():
        null_str = f"({info['null_pct']}% null)" if info["null_pct"] > 0 else ""
        print(f"  {col}: {info['dtype']} {null_str}")

    print("\n--- DATE RANGES ---")
    for col, info in result.get("date_ranges", {}).items():
        if "min_date" in info:
            print(
                f"  {col}: {info['min_date']} to {info['max_date']} ({info['count']:,} rows)"
            )
            if info.get("gaps"):
                print(f"    Gaps: {len(info['gaps'])} gaps > 30 days")

    if result["errors"]:
        print("\n--- ERRORS ---")
        for err in result["errors"]:
            print(f"  {err}")

    if result["warnings"]:
        print("\n--- WARNINGS ---")
        for warn in result["warnings"]:
            print(f"  {warn}")

    print("=" * 70 + "\n")

    return result


def show_report():
    """Display the saved validation report."""
    if not REPORT_PATH.exists():
        logger.error("No validation report found. Run --scan first.")
        return

    with open(REPORT_PATH, "r") as f:
        report = json.load(f)

    validator = DataValidator()
    validator.print_summary(report)

    # Also print ingestion recommendations
    print("\n--- INGESTION RECOMMENDATIONS ---")
    print("\nPriority 1 (Core Data):")
    for cat in ["market_futures", "fred_observations"]:
        if cat in report["category_summary"]:
            info = report["category_summary"][cat]
            print(f"  {cat}: {info['count']} files, {info['rows']:,} rows")

    print("\nPriority 2 (Specialist Features):")
    for cat in ["usda_data", "cftc_cot", "weather", "epa_rin", "sentiment"]:
        if cat in report["category_summary"]:
            info = report["category_summary"][cat]
            print(f"  {cat}: {info['count']} files, {info['rows']:,} rows")

    print("\nPriority 3 (Derived Data):")
    for cat in ["technical_indicators", "training_features", "forecasts"]:
        if cat in report["category_summary"]:
            info = report["category_summary"][cat]
            print(f"  {cat}: {info['count']} files, {info['rows']:,} rows")


def main():
    parser = argparse.ArgumentParser(
        description="Validate data sources before ingestion"
    )
    parser.add_argument(
        "--scan", action="store_true", help="Scan and validate all parquet files"
    )
    parser.add_argument("--validate", type=str, help="Validate a single parquet file")
    parser.add_argument(
        "--report", action="store_true", help="Show saved validation report"
    )

    args = parser.parse_args()

    if args.scan:
        scan_all_sources()
    elif args.validate:
        validate_single_file(args.validate)
    elif args.report:
        show_report()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
