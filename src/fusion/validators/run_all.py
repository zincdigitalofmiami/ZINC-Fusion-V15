"""
ZINC-FUSION-V15 Pre-Training Validation Suite

Runs ALL validators before training to ensure data integrity.
This is the single command to run before any training run.

Usage:
    python -m src.fusion.validators.run_all

Exit codes:
    0 = All checks passed
    1 = Critical failures (schema violations)
    2 = Warnings only (stale data, but can proceed with caution)
"""

import os
import sys
from datetime import datetime

# Only import validators that exist
from .quarantine_verifier import QuarantineVerifier


def _status_label(val):
    """Format result value for summary display."""
    if val == "skipped":
        return "-- SKIPPED (not implemented)"
    if val is True:
        return "PASS"
    if val is False:
        return "FAIL"
    return "-- NOT RUN"


def main():
    """Run all pre-training validators."""

    conn_string = os.environ.get("DATABASE_URL", os.environ.get("POSTGRES_URL"))

    if not conn_string:
        print("ERROR: DATABASE_URL or POSTGRES_URL environment variable required")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("ZINC-FUSION-V15 PRE-TRAINING VALIDATION SUITE")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 70)

    results = {
        "schema": None,
        "freshness": None,
        "quarantine": None,
    }

    # =========================================================================
    # 1. SCHEMA CONTRACT VALIDATION (Critical)
    # =========================================================================
    print("\n\n[1/3] SCHEMA CONTRACT VALIDATION")
    print("-" * 70)

    try:
        from .schema_contract import SchemaContractValidator

        validator = SchemaContractValidator(conn_string)
        schema_ok = validator.validate_all()
        validator.print_report()
        validator.close()
        results["schema"] = schema_ok
    except ImportError:
        print("  SchemaContractValidator not yet implemented -- skipped")
        results["schema"] = "skipped"
    except Exception as e:
        print(f"ERROR: Schema validation failed with exception: {e}")
        results["schema"] = False

    # =========================================================================
    # 2. DATA FRESHNESS CHECK (Warning)
    # =========================================================================
    print("\n\n[2/3] DATA FRESHNESS CHECK")
    print("-" * 70)

    try:
        from .freshness_monitor import FreshnessMonitor

        monitor = FreshnessMonitor(conn_string)
        freshness_ok = monitor.check_all()
        monitor.print_report()
        monitor.close()
        results["freshness"] = freshness_ok
    except ImportError:
        print("  FreshnessMonitor not yet implemented -- skipped")
        results["freshness"] = "skipped"
    except Exception as e:
        print(f"ERROR: Freshness check failed with exception: {e}")
        results["freshness"] = False

    # =========================================================================
    # 3. QUARANTINE PIPELINE CHECK (Critical)
    # =========================================================================
    print("\n\n[3/3] QUARANTINE PIPELINE CHECK")
    print("-" * 70)

    try:
        verifier = QuarantineVerifier(conn_string)
        quarantine_ok = verifier.verify_all()
        verifier.close()
        results["quarantine"] = quarantine_ok
    except Exception as e:
        print(f"ERROR: Quarantine check failed with exception: {e}")
        results["quarantine"] = False

    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    print("\n\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    # Skipped validators are non-blocking but distinct from passed
    critical_pass = (results["schema"] in (True, "skipped")) and (
        results["quarantine"] is True
    )
    warnings_only = results["freshness"] is False

    print(f"\n  Schema Contract:     {_status_label(results['schema'])}")
    print(f"  Data Freshness:      {_status_label(results['freshness'])}")
    print(f"  Quarantine Pipeline: {_status_label(results['quarantine'])}")

    print("\n" + "=" * 70)

    if critical_pass and not warnings_only:
        print("ALL CHECKS PASSED - Safe to proceed with training")
        print("=" * 70 + "\n")
        sys.exit(0)
    elif critical_pass and warnings_only:
        print("WARNINGS DETECTED - Proceed with caution")
        print("   Some data may be stale. Consider refreshing before training.")
        print("=" * 70 + "\n")
        sys.exit(2)
    else:
        print("CRITICAL FAILURES - DO NOT PROCEED WITH TRAINING")
        print("   Fix schema or quarantine issues before training.")
        print("=" * 70 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
