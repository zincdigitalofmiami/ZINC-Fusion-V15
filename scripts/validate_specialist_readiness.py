#!/usr/bin/env python3
"""
Task 4.7: Validate All Specialists Are Ready for Core Ensemble Training

Runs comprehensive validation suite on all 11 specialists:
1. Coverage: ≥90% daily rows per bucket (last 180 days)
2. Staleness: Max staleness within limits
3. IC: Positive IC at 21d horizon
4. Leakage: No correlation with past returns

Usage:
    python scripts/validate_specialist_readiness.py
    python scripts/validate_specialist_readiness.py --strict  # Exit non-zero on failure
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from datetime import date, timedelta
from typing import Dict, List
import pandas as pd
import numpy as np
import psycopg2
from scipy import stats

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from fusion.specialists import SPECIALIST_BUCKETS


# =============================================================================
# STALENESS LIMITS BY SOURCE
# =============================================================================

STALENESS_LIMITS = {
    "crush": {
        "wasde": 35,  # Monthly + buffer
        "cftc": 10,  # Weekly + buffer
    },
    "china": {
        "fred": 5,  # Daily + buffer
    },
    "fx": {
        "fred": 5,  # Daily + buffer
    },
    "fed": {
        "fred": 5,  # Daily + buffer
    },
    "energy": {
        "futures": 5,  # Daily + buffer
    },
    "volatility": {
        "fred": 5,  # Daily + buffer
    },
    "substitutes": {
        "fred": 35,  # Monthly commodities
        "futures": 5,  # Daily futures
    },
    "palm": {
        "futures": 5,  # Daily + buffer
        "fred": 5,  # Daily FX
    },
    "biofuel": {
        "rin": 14,  # Weekly + buffer
        "lcfs": 14,  # Weekly + buffer
    },
    "tariff": {
        "fred": 5,  # Daily + buffer
    },
    "trump_effect": {
        "fred": 5,  # Daily + buffer
        "etf": 5,  # Daily + buffer
    },
}


def get_staleness_limit(bucket: str) -> int:
    """Get maximum allowed staleness for a bucket."""
    limits = STALENESS_LIMITS.get(bucket, {})
    return max(limits.values()) if limits else 30  # Default 30 days


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================


def check_coverage(conn, bucket: str, lookback_days: int = 180) -> float:
    """
    Check signal coverage for a bucket.

    Returns:
        Coverage percentage (0-1)
    """
    query = f"""
    SELECT 
        COUNT(*) as n_signals,
        (SELECT COUNT(DISTINCT event_date)
         FROM mkt.futures_1d
         WHERE symbol = 'ZL'
           AND event_date >= CURRENT_DATE - INTERVAL '{lookback_days} days') as n_expected
    FROM training.specialist_signals_1d
    WHERE bucket = %s
      AND as_of_date >= CURRENT_DATE - INTERVAL '{lookback_days} days'
    """

    df = pd.read_sql(query, conn, params=[bucket])
    if len(df) == 0 or df.iloc[0]["n_expected"] == 0:
        return 0.0

    n_signals = df.iloc[0]["n_signals"]
    n_expected = df.iloc[0]["n_expected"]
    return n_signals / n_expected if n_expected > 0 else 0.0


def check_max_staleness(conn, bucket: str) -> int:
    """
    Check maximum staleness for a bucket.

    Returns:
        Maximum staleness days (999 if no data)
    """
    query = """
    SELECT MAX(staleness_days) as max_staleness
    FROM training.specialist_signals_1d
    WHERE bucket = %s
      AND as_of_date >= CURRENT_DATE - INTERVAL '30 days'
    """

    df = pd.read_sql(query, conn, params=[bucket])
    if len(df) == 0 or pd.isna(df.iloc[0]["max_staleness"]):
        return 999

    return int(df.iloc[0]["max_staleness"])


def check_ic(conn, bucket: str, horizon: int = 21) -> float:
    """
    Check Information Coefficient (IC) for a bucket.

    Returns:
        IC value (Spearman correlation with forward returns)
    """
    query = f"""
    SELECT 
        s.signal_1,
        m.target_ret_{horizon}d as target
    FROM training.specialist_signals_1d s
    JOIN training.matrix_1d m 
        ON s.as_of_date = m.trade_date 
        AND m.symbol = 'ZL'
    WHERE s.bucket = %s
      AND s.as_of_date >= CURRENT_DATE - INTERVAL '365 days'
      AND s.signal_1 IS NOT NULL
      AND m.target_ret_{horizon}d IS NOT NULL
    ORDER BY s.as_of_date
    """

    df = pd.read_sql(query, conn, params=[bucket])
    if len(df) < 100:
        return 0.0

    ic, _ = stats.spearmanr(df["signal_1"], df["target"])
    return ic if not np.isnan(ic) else 0.0


def check_leakage(conn, bucket: str) -> float:
    """
    Check leakage (correlation with past returns).

    Returns:
        Correlation with past returns (should be < 0.1)
    """
    query = """
    SELECT 
        s.signal_1,
        m.close,
        LAG(m.close) OVER (ORDER BY s.as_of_date) as prev_close
    FROM training.specialist_signals_1d s
    JOIN training.matrix_1d m 
        ON s.as_of_date = m.trade_date 
        AND m.symbol = 'ZL'
    WHERE s.bucket = %s
      AND s.as_of_date >= CURRENT_DATE - INTERVAL '365 days'
      AND s.signal_1 IS NOT NULL
    ORDER BY s.as_of_date
    """

    df = pd.read_sql(query, conn, params=[bucket])
    if len(df) < 100:
        return 0.0

    # Calculate past return
    df["past_return"] = (df["close"] - df["prev_close"]) / df["prev_close"]

    valid = df.dropna(subset=["signal_1", "past_return"])
    if len(valid) < 100:
        return 0.0

    corr, _ = stats.pearsonr(valid["signal_1"], valid["past_return"])
    return abs(corr) if not np.isnan(corr) else 0.0


def validate_all_specialists(conn, strict: bool = False) -> Dict[str, Dict[str, any]]:
    """
    Run validation suite on all 11 specialists.

    Returns:
        Dict mapping bucket to validation results
    """
    results = {}

    for bucket in SPECIALIST_BUCKETS:
        logger.info(f"Validating {bucket}...")

        coverage = check_coverage(conn, bucket)
        max_staleness = check_max_staleness(conn, bucket)
        staleness_limit = get_staleness_limit(bucket)
        ic_21d = check_ic(conn, bucket, horizon=21)
        leakage = check_leakage(conn, bucket)

        results[bucket] = {
            "coverage_ok": coverage >= 0.90,
            "coverage_pct": coverage * 100,
            "staleness_ok": max_staleness <= staleness_limit,
            "max_staleness": max_staleness,
            "staleness_limit": staleness_limit,
            "ic_positive": ic_21d > 0,
            "ic_21d": ic_21d,
            "no_leakage": leakage < 0.1,
            "leakage": leakage,
        }

        # Overall readiness
        results[bucket]["ready"] = (
            results[bucket]["coverage_ok"]
            and results[bucket]["staleness_ok"]
            and results[bucket]["ic_positive"]
            and results[bucket]["no_leakage"]
        )

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Validate all specialists are ready for Core ensemble training"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any specialist fails validation",
    )
    args = parser.parse_args()

    # Connect to database
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")

    conn = psycopg2.connect(database_url)

    try:
        results = validate_all_specialists(conn, strict=args.strict)

        # Print report
        print("\n" + "=" * 80)
        print("SPECIALIST READINESS VALIDATION REPORT")
        print("=" * 80)

        ready_count = sum(1 for r in results.values() if r["ready"])
        print(f"\nOverall Status: {ready_count}/11 specialists ready for Core")

        print("\n" + "-" * 80)
        print(
            f"{'Bucket':<20} {'Coverage':<12} {'Staleness':<12} {'IC_21d':<10} {'Leakage':<10} {'Ready'}"
        )
        print("-" * 80)

        for bucket, status in sorted(results.items()):
            icon = "✅" if status["ready"] else "❌"
            coverage_str = f"{status['coverage_pct']:.1f}%"
            staleness_str = f"{status['max_staleness']}d/{status['staleness_limit']}d"
            ic_str = f"{status['ic_21d']:.4f}"
            leakage_str = f"{status['leakage']:.4f}"

            print(
                f"{bucket:<20} {coverage_str:<12} {staleness_str:<12} "
                f"{ic_str:<10} {leakage_str:<10} {icon}"
            )

        print("-" * 80)

        # Detailed issues
        failed = {b: s for b, s in results.items() if not s["ready"]}
        if failed:
            print("\n⚠️  FAILED VALIDATIONS:")
            for bucket, status in failed.items():
                print(f"\n{bucket}:")
                if not status["coverage_ok"]:
                    print(f"  ❌ Coverage: {status['coverage_pct']:.1f}% < 90%")
                if not status["staleness_ok"]:
                    print(
                        f"  ❌ Staleness: {status['max_staleness']}d > {status['staleness_limit']}d limit"
                    )
                if not status["ic_positive"]:
                    print(f"  ❌ IC_21d: {status['ic_21d']:.4f} <= 0")
                if not status["no_leakage"]:
                    print(f"  ❌ Leakage: {status['leakage']:.4f} >= 0.1")

        print("\n" + "=" * 80)

        if ready_count == 11:
            print("✅ ALL SPECIALISTS READY FOR CORE ENSEMBLE")
            return 0
        else:
            print(f"❌ {11 - ready_count} SPECIALISTS NOT READY")
            return 1 if args.strict else 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
