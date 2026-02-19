#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Signal-Quality & Robustness Diagnostic
=======================================================
Implements testing layers #2 (Diagnostics) and #3 (Leakage/Robustness).
Acts as a quality gate before ablation testing.

Metrics:
1. Coverage: % of valid trading days with signal.
2. Rank IC: Spearman correlation with forward returns (1d, 5d, 21d).
3. Leakage: Check if Signal(t) correlates better with Ret(t-1) than Ret(t+1).
4. Stability: Autocorrelation of the signal itself (smoothness).
5. Regime Stress: Performance delta in High Vol vs Low Vol regimes.

Usage:
    python scripts/diagnostic_signal_report.py
    python scripts/diagnostic_signal_report.py --bucket crush
    python scripts/diagnostic_signal_report.py --min-ic 0.02
"""

import os
import sys
import logging
import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import psycopg2
from scipy import stats

# Add src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

# Constants
TARGET_SYMBOL = "ZL"
HORIZONS = [1, 5, 21]  # Days to forecast
REGIME_WINDOW = 21
VOL_PERCENTILE = 0.75

# Big 11 Specialists
SPECIALISTS = [
    "crush",
    "china",
    "fx",
    "fed",
    "tariff",
    "energy",
    "biofuel",
    "palm",
    "volatility",
    "substitutes",
    "trump_effect",
]


def get_data_connection():
    """Get database connection."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")
    return psycopg2.connect(database_url)


def fetch_market_data(conn) -> pd.DataFrame:
    """
    Fetch ZL price data with forward returns for IC calculation.

    Returns DataFrame with:
    - close, volume
    - target_price_{1,5,21}d (forward returns)
    - vol_21d (rolling volatility)
    - regime (High Vol / Low Vol)
    """
    logger.info("Fetching market data...")

    query = """
    SELECT
        event_date as trade_date,
        close,
        volume
    FROM mkt.futures_1d
    WHERE symbol = 'ZL'
      AND event_date >= '2010-01-01'
      AND close IS NOT NULL
    ORDER BY event_date ASC
    """
    df = pd.read_sql(query, conn, parse_dates=["trade_date"])
    df = df.set_index("trade_date")

    # Calculate Forward Price Levels for Targets
    for h in HORIZONS:
        df[f"target_price_{h}d"] = df["close"].shift(-h)

    # Volatility Regime
    df["vol_21d"] = df["close"].pct_change().rolling(REGIME_WINDOW).std()
    vol_threshold = df["vol_21d"].quantile(VOL_PERCENTILE)
    df["regime"] = np.where(df["vol_21d"] > vol_threshold, "High Vol", "Low Vol")

    logger.info(
        f"Loaded {len(df)} days of ZL data ({df.index.min().date()} to {df.index.max().date()})"
    )
    return df


def fetch_specialist_signals(conn) -> pd.DataFrame:
    """
    Fetch all specialist signals from training.specialist_signals_1d.

    Returns DataFrame with trade_date index and columns for each specialist's signals.
    """
    logger.info("Fetching specialist signals...")

    query = """
    SELECT
        as_of_date as trade_date,
        bucket,
        signal_1,
        signal_2,
        confidence
    FROM training.specialist_signals_1d
    ORDER BY as_of_date, bucket
    """

    try:
        df = pd.read_sql(query, conn, parse_dates=["trade_date"])
    except Exception as e:
        logger.warning(f"Could not load specialist signals: {e}")
        return pd.DataFrame()

    if df.empty:
        logger.warning("No specialist signals found in training.specialist_signals_1d")
        return pd.DataFrame()

    # Pivot to wide format
    signals_wide = df.pivot(
        index="trade_date",
        columns="bucket",
        values=["signal_1", "signal_2", "confidence"],
    )

    # Flatten column names
    signals_wide.columns = [f"{bucket}_{sig}" for sig, bucket in signals_wide.columns]

    logger.info(
        f"Loaded signals for {len(df['bucket'].unique())} specialists, {len(signals_wide)} dates"
    )
    return signals_wide


def compute_diagnostics(
    market_df: pd.DataFrame, signals_df: pd.DataFrame, bucket_filter: str = None
) -> pd.DataFrame:
    """
    Compute diagnostic metrics for all signals.

    Returns DataFrame with:
    - Bucket, Feature
    - Coverage (% non-null)
    - IC_1d, IC_5d, IC_21d (Spearman correlation with forward returns)
    - IC_HighVol, IC_LowVol (regime-conditional IC)
    - Stability (autocorrelation)
    - Leakage_Corr, Leakage_Suspicion
    """
    # Merge signals with market data
    merged = signals_df.join(market_df, how="inner")

    if len(merged) < 252:
        logger.warning(f"Insufficient overlapping data: {len(merged)} rows")
        return pd.DataFrame()

    report = []

    # Get signal columns (signal_1 and signal_2 for each bucket)
    signal_cols = [
        c
        for c in signals_df.columns
        if c.endswith("_signal_1") or c.endswith("_signal_2")
    ]

    for col in signal_cols:
        # Extract bucket name
        parts = col.rsplit("_", 2)
        if len(parts) >= 3:
            bucket = parts[0]
            sig_type = parts[-1]  # "1" or "2"
        else:
            continue

        # Filter by bucket if specified
        if bucket_filter and bucket != bucket_filter:
            continue

        s = merged[col].replace([np.inf, -np.inf], np.nan)

        # 1. Coverage
        coverage = s.notnull().mean()

        if coverage < 0.1:
            continue

        # Get valid subset
        required_cols = [col, "target_price_5d", "target_price_21d", "regime"]
        valid_df = merged.dropna(subset=required_cols)

        if len(valid_df) < 252:
            continue

        # 2. IC (Rank Correlation) with forward returns
        ic_results = {}
        for h in HORIZONS:
            target_col = f"target_price_{h}d"
            if target_col in valid_df.columns:
                ic, p_val = stats.spearmanr(
                    valid_df[col].dropna(),
                    valid_df.loc[valid_df[col].notna(), target_col],
                )
                ic_results[f"IC_{h}d"] = ic if not np.isnan(ic) else 0.0

        # 3. Leakage Test
        # Does Signal(t) correlate with Ret(t-1) (past return)?
        lagged_target = valid_df["close"].pct_change().shift(1)
        leakage_corr = valid_df[col].corr(lagged_target)

        # Suspicious if leakage correlation > forward IC
        is_leaky = (
            abs(leakage_corr) > (abs(ic_results.get("IC_21d", 0)) * 1.5)
            and abs(leakage_corr) > 0.1
        )

        # 4. Stability (Autocorrelation)
        stability = valid_df[col].autocorr(1)

        # 5. Regime Performance
        hv_df = valid_df[valid_df["regime"] == "High Vol"]
        lv_df = valid_df[valid_df["regime"] == "Low Vol"]

        ic_hv = 0.0
        ic_lv = 0.0

        if len(hv_df) >= 100:
            ic_hv, _ = stats.spearmanr(hv_df[col], hv_df["target_price_21d"])
            ic_hv = ic_hv if not np.isnan(ic_hv) else 0.0

        if len(lv_df) >= 100:
            ic_lv, _ = stats.spearmanr(lv_df[col], lv_df["target_price_21d"])
            ic_lv = ic_lv if not np.isnan(ic_lv) else 0.0

        report.append(
            {
                "Bucket": bucket,
                "Feature": f"signal_{sig_type}",
                "Coverage": coverage,
                "IC_1d": ic_results.get("IC_1d", 0.0),
                "IC_5d": ic_results.get("IC_5d", 0.0),
                "IC_21d": ic_results.get("IC_21d", 0.0),
                "IC_HighVol": ic_hv,
                "IC_LowVol": ic_lv,
                "Stability": stability if not np.isnan(stability) else 0.0,
                "Leakage_Corr": leakage_corr if not np.isnan(leakage_corr) else 0.0,
                "Leakage_Suspicion": is_leaky,
                "N_Valid": len(valid_df),
            }
        )

    return pd.DataFrame(report)


def generate_report(results: pd.DataFrame, min_ic: float = 0.0) -> None:
    """Print formatted diagnostic report."""

    if results.empty:
        print("\nNo signals to analyze.")
        return

    # Sort by absolute IC_21d
    results = results.sort_values(by="IC_21d", key=abs, ascending=False)

    print("\n" + "=" * 90)
    print("SIGNAL DIAGNOSTICS REPORT")
    print("=" * 90)

    # Summary stats
    print(f"\nTotal signals analyzed: {len(results)}")
    print(f"Signals with |IC_21d| > 0.02: {(results['IC_21d'].abs() > 0.02).sum()}")
    print(f"Signals with leakage suspicion: {results['Leakage_Suspicion'].sum()}")

    # Filter by min IC if specified
    if min_ic > 0:
        filtered = results[results["IC_21d"].abs() >= min_ic]
        print(f"\nFiltered to |IC_21d| >= {min_ic}: {len(filtered)} signals")
    else:
        filtered = results

    # Display table
    print("\n" + "-" * 90)
    print(
        f"{'Bucket':<15} {'Feature':<10} {'IC_21d':>8} {'IC_HV':>8} {'IC_LV':>8} {'Stab':>6} {'Leak':>6} {'Leaky?'}"
    )
    print("-" * 90)

    for _, row in filtered.iterrows():
        leaky_flag = "YES" if row["Leakage_Suspicion"] else ""
        print(
            f"{row['Bucket']:<15} {row['Feature']:<10} "
            f"{row['IC_21d']:>8.4f} {row['IC_HighVol']:>8.4f} {row['IC_LowVol']:>8.4f} "
            f"{row['Stability']:>6.3f} {row['Leakage_Corr']:>6.3f} {leaky_flag}"
        )

    print("-" * 90)

    # Recommendations
    print("\n=== RECOMMENDATIONS ===")

    # Top performers
    top = results.nlargest(5, "IC_21d")
    print("\nTop 5 by IC_21d (positive):")
    for _, row in top.iterrows():
        print(f"  + {row['Bucket']}/{row['Feature']}: IC={row['IC_21d']:.4f}")

    # Bottom performers (negative IC can still be useful - inverse signal)
    bottom = results.nsmallest(5, "IC_21d")
    print("\nTop 5 by IC_21d (negative - potential inverse signals):")
    for _, row in bottom.iterrows():
        print(f"  - {row['Bucket']}/{row['Feature']}: IC={row['IC_21d']:.4f}")

    # Leaky signals
    leaky = results[results["Leakage_Suspicion"]]
    if len(leaky) > 0:
        print(f"\nWARNING: {len(leaky)} signals have leakage suspicion:")
        for _, row in leaky.iterrows():
            print(
                f"  ! {row['Bucket']}/{row['Feature']}: leakage_corr={row['Leakage_Corr']:.4f}"
            )

    # Regime specialists
    print("\nRegime-specific performers:")
    hv_specialists = results[
        results["IC_HighVol"].abs() > results["IC_LowVol"].abs() * 1.5
    ]
    if len(hv_specialists) > 0:
        print("  High Vol specialists:")
        for _, row in hv_specialists.head(3).iterrows():
            print(
                f"    {row['Bucket']}/{row['Feature']}: IC_HV={row['IC_HighVol']:.4f}, IC_LV={row['IC_LowVol']:.4f}"
            )


def main():
    parser = argparse.ArgumentParser(description="Signal Quality Diagnostics")
    parser.add_argument(
        "--bucket", type=str, default=None, help="Filter to specific bucket"
    )
    parser.add_argument(
        "--min-ic", type=float, default=0.0, help="Minimum |IC_21d| to display"
    )
    parser.add_argument("--output", type=str, default=None, help="Output CSV path")
    args = parser.parse_args()

    conn = get_data_connection()

    try:
        # Fetch data
        market_df = fetch_market_data(conn)
        signals_df = fetch_specialist_signals(conn)

        if signals_df.empty:
            logger.error(
                "No specialist signals found. Run generate_specialist_signals.py first."
            )
            return 1

        # Compute diagnostics
        results = compute_diagnostics(market_df, signals_df, bucket_filter=args.bucket)

        # Generate report
        generate_report(results, min_ic=args.min_ic)

        # Save if requested
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            results.to_csv(output_path, index=False)
            print(f"\nResults saved to {output_path}")
        else:
            # Default save location
            output_path = (
                PROJECT_ROOT / "docs" / "audit" / "signal_diagnostics_report.csv"
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            results.to_csv(output_path, index=False)
            print(f"\nResults saved to {output_path}")

        return 0

    except Exception as e:
        logger.error(f"Diagnostics failed: {e}", exc_info=True)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
