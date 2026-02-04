#!/usr/bin/env python3
"""
Data Gate: Pre-flight validation for specialist signal generation.

This script validates data freshness according to Forward Fill Policy
(Docs/FORWARD_FILL_POLICY.md) before allowing specialist signals to run.

Usage:
    python scripts/data_gate_specialists.py
    python scripts/data_gate_specialists.py --strict
    python scripts/data_gate_specialists.py --bucket crush
    python scripts/data_gate_specialists.py --report-only

Exit codes:
    0: All data gates pass
    1: Some data gates fail (in strict mode)
    2: Critical data gates fail (always)
"""

import os
import sys
import argparse
import logging
from datetime import datetime, date, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fusion.db.connection import get_read_engine


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# TTL THRESHOLDS (From Forward Fill Policy)
# =============================================================================

@dataclass
class DataSourceCheck:
    """Configuration for a data source freshness check."""
    source: str
    table: str
    date_column: str
    ttl_days: int
    is_critical: bool
    description: str


# Data sources to check per specialist (TTL thresholds LOCKED)
SPECIALIST_DATA_GATES: Dict[str, List[DataSourceCheck]] = {
    "crush": [
        DataSourceCheck("futures", "mkt.futures_1d", "trade_date", 3, True, "ZL/ZS/ZM futures"),
        DataSourceCheck("cftc", "pos.cftc_1w", "report_date", 10, True, "CFTC COT positioning"),
    ],
    "china": [
        DataSourceCheck("futures", "mkt.futures_1d", "trade_date", 3, True, "Copper futures (HG)"),
        DataSourceCheck("fx", "mkt.fx_1d", "event_date", 3, True, "CNY/USD rate"),
    ],
    "fx": [
        DataSourceCheck("fx", "mkt.fx_1d", "event_date", 3, True, "FX rates"),
        DataSourceCheck("rates", "econ.rates_1d", "event_date", 3, True, "DGS2/DGS10"),
    ],
    "fed": [
        DataSourceCheck("rates", "econ.rates_1d", "event_date", 3, True, "Fed Funds, Treasury rates"),
    ],
    "volatility": [
        DataSourceCheck("vol", "econ.vol_indices_1d", "event_date", 3, True, "VIX, OVX"),
    ],
    "energy": [
        DataSourceCheck("futures", "mkt.futures_1d", "trade_date", 3, True, "CL/HO/RB futures"),
    ],
    "palm": [
        DataSourceCheck("futures", "mkt.futures_1d", "trade_date", 3, True, "FCPO futures"),
    ],
    "tariff": [
        DataSourceCheck("epu", "econ.rates_1d", "event_date", 45, False, "EPU indices"),
    ],
    "biofuel": [
        DataSourceCheck("rin", "supply.epa_rin_1d", "event_date", 10, True, "RIN prices"),
        DataSourceCheck("lcfs", "supply.lcfs_1d", "event_date", 10, True, "LCFS credits"),
    ],
    "substitutes": [
        DataSourceCheck("futures", "mkt.futures_1d", "trade_date", 3, True, "Substitute oil futures"),
    ],
    "trump_effect": [
        DataSourceCheck("epu", "econ.rates_1d", "event_date", 10, False, "EPU indices"),
        DataSourceCheck("vol", "econ.vol_indices_1d", "event_date", 3, True, "VIX"),
    ],
}


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def get_latest_date(engine, table: str, date_column: str) -> Optional[date]:
    """Get the latest date in a table."""
    try:
        query = f"SELECT MAX({date_column}) as max_date FROM {table}"
        result = pd.read_sql(query, engine)
        if result.empty or result["max_date"].isna().all():
            return None
        max_date = result["max_date"].iloc[0]
        if isinstance(max_date, pd.Timestamp):
            return max_date.date()
        return max_date
    except Exception as e:
        logger.warning(f"Error querying {table}: {e}")
        return None


def check_data_source(
    engine,
    check: DataSourceCheck,
    as_of_date: date,
) -> Tuple[bool, int, str]:
    """
    Check if a data source is fresh enough.

    Returns:
        Tuple of (passed, staleness_days, message)
    """
    latest = get_latest_date(engine, check.table, check.date_column)

    if latest is None:
        return False, 999, f"{check.source}: NO DATA in {check.table}"

    staleness = (as_of_date - latest).days

    if staleness <= check.ttl_days:
        return True, staleness, f"{check.source}: OK ({staleness}d old, TTL={check.ttl_days}d)"
    else:
        status = "CRITICAL" if check.is_critical else "WARNING"
        return False, staleness, f"{check.source}: {status} - stale ({staleness}d > TTL={check.ttl_days}d)"


def validate_specialist(
    engine,
    bucket: str,
    as_of_date: date,
) -> Tuple[bool, List[str]]:
    """
    Validate all data sources for a specialist.

    Returns:
        Tuple of (all_passed, messages)
    """
    checks = SPECIALIST_DATA_GATES.get(bucket, [])
    if not checks:
        return True, [f"{bucket}: No data gates configured"]

    messages = []
    all_passed = True
    has_critical_failure = False

    for check in checks:
        passed, staleness, msg = check_data_source(engine, check, as_of_date)
        messages.append(f"  {msg}")
        if not passed:
            all_passed = False
            if check.is_critical:
                has_critical_failure = True

    return all_passed, messages, has_critical_failure


def run_data_gate(
    buckets: Optional[List[str]] = None,
    strict: bool = False,
    as_of_date: Optional[date] = None,
) -> Tuple[bool, Dict[str, bool]]:
    """
    Run data gate validation for specified specialists.

    Args:
        buckets: List of buckets to check (default: all)
        strict: If True, fail on any staleness; if False, only fail on critical
        as_of_date: Date for staleness calculation (default: today)

    Returns:
        Tuple of (all_passed, results_by_bucket)
    """
    if buckets is None:
        buckets = list(SPECIALIST_DATA_GATES.keys())

    if as_of_date is None:
        as_of_date = date.today()

    engine = get_read_engine()
    all_passed = True
    results = {}

    logger.info(f"Running data gate validation for {len(buckets)} specialists (as_of={as_of_date})")
    logger.info("=" * 60)

    for bucket in buckets:
        passed, messages, has_critical = validate_specialist(engine, bucket, as_of_date)
        results[bucket] = passed

        status = "PASS" if passed else ("CRITICAL FAIL" if has_critical else "WARN")
        logger.info(f"\n[{bucket.upper()}] {status}")
        for msg in messages:
            logger.info(msg)

        if not passed:
            if strict or has_critical:
                all_passed = False

    logger.info("\n" + "=" * 60)
    passed_count = sum(1 for v in results.values() if v)
    logger.info(f"SUMMARY: {passed_count}/{len(results)} specialists passed data gate")

    return all_passed, results


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Pre-flight data freshness validation for specialist signals"
    )
    parser.add_argument(
        "--bucket",
        type=str,
        help="Specific bucket to validate (default: all)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on any staleness (not just critical)",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Report only, don't set exit code",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        help="Date for staleness check (YYYY-MM-DD, default: today)",
    )

    args = parser.parse_args()

    buckets = [args.bucket] if args.bucket else None
    as_of_date = None
    if args.as_of:
        as_of_date = datetime.strptime(args.as_of, "%Y-%m-%d").date()

    all_passed, results = run_data_gate(
        buckets=buckets,
        strict=args.strict,
        as_of_date=as_of_date,
    )

    if args.report_only:
        sys.exit(0)

    # Exit code based on results
    if all_passed:
        logger.info("\nDATA GATE: PASSED - All specialists have fresh data")
        sys.exit(0)
    else:
        logger.error("\nDATA GATE: FAILED - Some specialists have stale data")
        sys.exit(1)


if __name__ == "__main__":
    main()
