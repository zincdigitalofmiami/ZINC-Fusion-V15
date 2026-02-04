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
# SIGNAL TYPE CLASSIFICATION (PATCHED 2026-01-31)
# =============================================================================

# Signal types determine which health metrics are appropriate
SIGNAL_TYPES = {
    # Continuous signals: use max_run metric (max identical consecutive values)
    "crush": "continuous",
    "china": "continuous",
    "substitutes": "continuous",
    "palm": "continuous",
    "fed": "continuous",
    "tariff": "continuous",  # Though rules-based, outputs continuous risk scores
    "biofuel": "continuous",
    "trump_effect": "continuous",
    # Warmup-aware signals: exclude early history from max_run calculation
    "energy": "warmup_aware",  # VAR needs 252 days warmup
    "fx": "warmup_aware",  # ARDL needs 500 days warmup
    # Volatility now outputs continuous signal values (GARCH-based)
    "volatility": "continuous",
}

# Warmup periods (days of history needed before signals are reliable)
WARMUP_PERIODS = {
    "energy": 252,  # VAR model needs 1 year
    "fx": 500,  # ARDL model needs ~2 years
}

# For regime classifiers: expected regime levels
REGIME_LEVELS = {
    "volatility": [0, 1, 2, 3],  # Retained for backward-compatibility if re-enabled
}


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
    Check staleness for a bucket using 95th percentile (not max).

    P0-1 FIX: Use PERCENTILE_CONT(0.95) to exclude abstain signals (999).
    Abstain signals correctly report 999 staleness but shouldn't fail validation.

    Returns:
        95th percentile staleness days (999 if no data)
    """
    # Column is max_input_age_days (not staleness_days)
    # Use p95 to be robust to abstain signals (999)
    query = """
    SELECT
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY max_input_age_days) as p95_staleness,
        MAX(max_input_age_days) as max_staleness,
        COUNT(*) FILTER (WHERE max_input_age_days = 999) as abstain_count,
        COUNT(*) as total_count
    FROM training.specialist_signals_1d
    WHERE bucket = %s
      AND as_of_date >= CURRENT_DATE - INTERVAL '30 days'
      AND max_input_age_days IS NOT NULL
    """

    df = pd.read_sql(query, conn, params=[bucket])
    if len(df) == 0 or pd.isna(df.iloc[0]["p95_staleness"]):
        return 999

    return int(df.iloc[0]["p95_staleness"])


def check_ic(conn, bucket: str, horizon: int = 21) -> float:
    """
    Check Information Coefficient (IC) for a bucket.

    Returns:
        IC value (Spearman correlation with forward returns)

    P0-1 FIX: Exclude last 130 days (forward return horizon + buffer)
    to avoid NaN targets corrupting the IC calculation.
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
      AND s.as_of_date < CURRENT_DATE - INTERVAL '130 days'
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


# =============================================================================
# SIGNAL-TYPE-AWARE HEALTH METRICS (PATCHED 2026-01-31)
# =============================================================================


def check_max_run(conn, bucket: str, exclude_warmup: bool = False) -> Dict:
    """
    Check maximum run of identical consecutive signal values.

    For continuous signals: max_run > 7 is suspicious (stuck signal)
    For warmup_aware signals: exclude warmup period from calculation
    For discrete_regime signals: DO NOT USE THIS METRIC (use check_regime_health instead)

    Returns:
        Dict with max_run, run_distribution, warmup_excluded_days
    """
    signal_type = SIGNAL_TYPES.get(bucket, "continuous")

    # For regime classifiers, this metric is inappropriate
    if signal_type == "discrete_regime":
        return {
            "max_run": None,
            "metric_applicable": False,
            "reason": "regime_classifier_use_transition_rate_instead",
        }

    query = """
    SELECT
        as_of_date,
        signal_1
    FROM training.specialist_signals_1d
    WHERE bucket = %s
      AND signal_1 IS NOT NULL
    ORDER BY as_of_date
    """

    df = pd.read_sql(query, conn, params=[bucket])
    if len(df) < 50:
        return {"max_run": 0, "metric_applicable": True, "reason": "insufficient_data"}

    # For warmup-aware signals, exclude warmup period
    warmup_excluded = 0
    if signal_type == "warmup_aware" and exclude_warmup:
        warmup_days = WARMUP_PERIODS.get(bucket, 0)
        if warmup_days > 0 and len(df) > warmup_days:
            warmup_excluded = warmup_days
            df = df.iloc[warmup_days:]

    # Calculate runs of identical values
    signals = df["signal_1"].values
    runs = []
    current_run = 1

    for i in range(1, len(signals)):
        if signals[i] == signals[i - 1]:
            current_run += 1
        else:
            runs.append(current_run)
            current_run = 1
    runs.append(current_run)

    max_run = max(runs) if runs else 0

    # Compute run distribution
    run_counts = {}
    for r in runs:
        run_counts[r] = run_counts.get(r, 0) + 1

    return {
        "max_run": max_run,
        "metric_applicable": True,
        "warmup_excluded_days": warmup_excluded,
        "run_distribution": dict(sorted(run_counts.items())[:10]),  # Top 10 run lengths
        "total_runs": len(runs),
        "pct_runs_gt_7": sum(1 for r in runs if r > 7) / len(runs) * 100 if runs else 0,
    }


def check_regime_health(conn, bucket: str) -> Dict:
    """
    Check health metrics for discrete regime classifiers.

    For regime classifiers (like VOLATILITY), appropriate metrics are:
    - transition_rate: Fraction of days with state change (target: 0.05-0.15)
    - state_entropy: Distribution across regimes (higher = more balanced)
    - state_distribution: Count of days in each regime state

    Returns:
        Dict with regime-specific health metrics
    """
    signal_type = SIGNAL_TYPES.get(bucket, "continuous")

    # For continuous signals, this metric is inappropriate
    if signal_type != "discrete_regime":
        return {
            "metric_applicable": False,
            "reason": "not_a_regime_classifier",
        }

    expected_levels = REGIME_LEVELS.get(bucket, [])

    query = """
    SELECT
        as_of_date,
        signal_1
    FROM training.specialist_signals_1d
    WHERE bucket = %s
      AND signal_1 IS NOT NULL
    ORDER BY as_of_date
    """

    df = pd.read_sql(query, conn, params=[bucket])
    if len(df) < 50:
        return {
            "metric_applicable": True,
            "transition_rate": None,
            "reason": "insufficient_data",
        }

    signals = df["signal_1"].values

    # Transition rate: how often does the state change?
    transitions = sum(1 for i in range(1, len(signals)) if signals[i] != signals[i - 1])
    transition_rate = transitions / (len(signals) - 1) if len(signals) > 1 else 0

    # State distribution
    state_counts = {}
    for s in signals:
        state_counts[int(s)] = state_counts.get(int(s), 0) + 1

    # State entropy (higher = more balanced distribution)
    total = len(signals)
    entropy = 0
    for count in state_counts.values():
        if count > 0:
            p = count / total
            entropy -= p * np.log2(p)

    # Check for missing expected states
    observed_states = set(int(s) for s in signals)
    missing_states = set(expected_levels) - observed_states if expected_levels else set()

    # Validate transitions are reasonable (not too low or too high)
    # Target: 5-15% transition rate (not constant, not noise)
    transition_ok = 0.03 <= transition_rate <= 0.20

    return {
        "metric_applicable": True,
        "transition_rate": transition_rate,
        "transition_rate_ok": transition_ok,
        "state_entropy": entropy,
        "state_distribution": state_counts,
        "unique_states": len(observed_states),
        "expected_states": expected_levels,
        "missing_states": list(missing_states) if missing_states else None,
        "total_days": len(signals),
    }


def validate_all_specialists(conn, strict: bool = False) -> Dict[str, Dict[str, any]]:
    """
    Run validation suite on all 11 specialists.

    PATCHED 2026-01-31: Added signal-type-aware health metrics
    - Continuous signals: max_run check (max identical consecutive values ≤7)
    - Warmup-aware signals: max_run check excluding warmup period
    - Discrete regime signals: transition_rate check instead of max_run

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

        # Signal-type-aware health metrics
        signal_type = SIGNAL_TYPES.get(bucket, "continuous")

        results[bucket] = {
            "signal_type": signal_type,
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

        # Add signal-type-specific health metrics
        if signal_type == "discrete_regime":
            # For regime classifiers: use transition_rate
            regime_health = check_regime_health(conn, bucket)
            results[bucket]["regime_health"] = regime_health
            results[bucket]["health_ok"] = regime_health.get("transition_rate_ok", False)
            results[bucket]["health_metric"] = f"transition_rate={regime_health.get('transition_rate', 0):.3f}"
        else:
            # For continuous/warmup-aware signals: use max_run
            exclude_warmup = signal_type == "warmup_aware"
            run_health = check_max_run(conn, bucket, exclude_warmup=exclude_warmup)
            results[bucket]["run_health"] = run_health
            max_run = run_health.get("max_run", 0)
            # max_run ≤ 7 is healthy for continuous signals
            results[bucket]["health_ok"] = max_run is not None and max_run <= 7
            warmup_note = f" (excl {run_health.get('warmup_excluded_days', 0)}d warmup)" if exclude_warmup else ""
            results[bucket]["health_metric"] = f"max_run={max_run}{warmup_note}"

        # Overall readiness (now includes health check)
        results[bucket]["ready"] = (
            results[bucket]["coverage_ok"]
            and results[bucket]["staleness_ok"]
            and results[bucket]["ic_positive"]
            and results[bucket]["no_leakage"]
            and results[bucket]["health_ok"]
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
        print("\n" + "=" * 90)
        print("SPECIALIST READINESS VALIDATION REPORT")
        print("(PATCHED 2026-01-31: Signal-type-aware health metrics)")
        print("=" * 90)

        ready_count = sum(1 for r in results.values() if r["ready"])
        print(f"\nOverall Status: {ready_count}/11 specialists ready for Core")

        # Signal type legend
        print("\nSignal Types:")
        print("  continuous    = max_run ≤ 7 days")
        print("  warmup_aware  = max_run ≤ 7 days (excluding warmup period)")
        print("  discrete_regime = transition_rate 3-20%")

        print("\n" + "-" * 90)
        print(
            f"{'Bucket':<15} {'Type':<15} {'Coverage':<10} {'Staleness':<10} "
            f"{'IC_21d':<8} {'Health':<25} {'Ready'}"
        )
        print("-" * 90)

        for bucket, status in sorted(results.items()):
            icon = "✅" if status["ready"] else "❌"
            coverage_str = f"{status['coverage_pct']:.1f}%"
            staleness_str = f"{status['max_staleness']}d"
            ic_str = f"{status['ic_21d']:.4f}"
            health_str = status.get("health_metric", "N/A")
            health_icon = "✓" if status.get("health_ok", False) else "✗"
            type_str = status.get("signal_type", "unknown")

            print(
                f"{bucket:<15} {type_str:<15} {coverage_str:<10} {staleness_str:<10} "
                f"{ic_str:<8} {health_icon} {health_str:<22} {icon}"
            )

        print("-" * 90)

        # Detailed issues
        failed = {b: s for b, s in results.items() if not s["ready"]}
        if failed:
            print("\n⚠️  FAILED VALIDATIONS:")
            for bucket, status in failed.items():
                print(f"\n{bucket} ({status.get('signal_type', 'unknown')}):")
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
                if not status.get("health_ok", True):
                    print(f"  ❌ Health: {status.get('health_metric', 'N/A')}")

        # Regime classifier details
        regime_specialists = {b: s for b, s in results.items() if s.get("signal_type") == "discrete_regime"}
        if regime_specialists:
            print("\n" + "-" * 90)
            print("REGIME CLASSIFIER DETAILS:")
            for bucket, status in regime_specialists.items():
                rh = status.get("regime_health", {})
                if rh.get("metric_applicable"):
                    print(f"\n{bucket}:")
                    print(f"  Transition rate: {rh.get('transition_rate', 0):.3f} (target: 0.03-0.20)")
                    print(f"  State entropy: {rh.get('state_entropy', 0):.3f}")
                    print(f"  State distribution: {rh.get('state_distribution', {})}")
                    if rh.get("missing_states"):
                        print(f"  ⚠️  Missing states: {rh.get('missing_states')}")

        # Warmup-aware details
        warmup_specialists = {b: s for b, s in results.items() if s.get("signal_type") == "warmup_aware"}
        if warmup_specialists:
            print("\n" + "-" * 90)
            print("WARMUP-AWARE SPECIALIST DETAILS:")
            for bucket, status in warmup_specialists.items():
                rh = status.get("run_health", {})
                warmup_days = WARMUP_PERIODS.get(bucket, 0)
                print(f"\n{bucket}:")
                print(f"  Warmup period: {warmup_days} days (excluded from max_run)")
                print(f"  Max run (post-warmup): {rh.get('max_run', 'N/A')}")
                if rh.get("pct_runs_gt_7", 0) > 0:
                    print(f"  % runs > 7 days: {rh.get('pct_runs_gt_7', 0):.1f}%")

        print("\n" + "=" * 90)

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
