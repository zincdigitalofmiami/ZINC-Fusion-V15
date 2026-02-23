#!/usr/bin/env python3
"""
Phase 1A OOF Evaluation Script
===============================
Self-contained evaluation of Core model OOF predictions.
Queries the database directly and prints all metrics.

Usage:
    python scripts/evaluate_oof.py                          # Latest run
    python scripts/evaluate_oof.py --run-hash 8af745...     # Specific run
    python scripts/evaluate_oof.py --list-runs              # Show available runs

Metrics computed:
    1. Per-horizon MAE
    2. MAPE accuracy (1 - MAE / AvgPrice)
    3. Cutoff-to-target directional accuracy
    4. Core vs Naive (cutoff close) comparison
    5. Predicted move size vs actual move size
    6. Per-window breakdown
    7. Ensemble weights from saved models
    8. Phase 0 baseline comparison
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd
import psycopg2


# Phase 0 baseline (hardcoded from reports/phase0_baseline_2026-02-20.md)
PHASE0_BASELINE = {
    5: {"mae": 0.8727, "weights": "PerStepTabular 84%, AutoARIMA 14%, Naive 2%"},
    21: {
        "mae": 1.3665,
        "weights": "RecursiveTabular 42%, AutoARIMA 33%, PerStepTabular 25%",
    },
    63: {
        "mae": 2.6533,
        "weights": "PerStepTabular 54%, RecursiveTabular 31%, NPTS 15%",
    },
    126: {
        "mae": 3.3102,
        "weights": "PerStepTabular 39%, NPTS 31%, RecursiveTabular 17%, ADIDA 11%, Croston 2%",
    },
}


def get_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set. Run: source .envrc", file=sys.stderr)
        sys.exit(1)
    return psycopg2.connect(url)


def list_runs(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT run_hash, run_id, matrix_version,
               MIN(trained_at) as first_trained,
               MAX(trained_at) as last_trained,
               COUNT(*) as n_predictions,
               array_agg(DISTINCT horizon_days ORDER BY horizon_days) as horizons
        FROM training.oof_core_1d
        GROUP BY run_hash, run_id, matrix_version
        ORDER BY MAX(trained_at) DESC
    """)
    print("\n  Available OOF runs:")
    print(
        f"  {'run_hash':>20s}  {'run_id':>40s}  {'matrix':>18s}  {'trained':>22s}  {'N':>5s}  horizons"
    )
    print("  " + "-" * 140)
    for row in cur.fetchall():
        print(
            f"  {row[0][:20]:>20s}  {row[1]:>40s}  {row[2][:18]:>18s}  {str(row[4]):>22s}  {row[5]:>5d}  {row[6]}"
        )


def get_latest_run_hash(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT run_hash FROM training.oof_core_1d
        ORDER BY trained_at DESC LIMIT 1
    """)
    row = cur.fetchone()
    if not row:
        print("ERROR: No OOF predictions found.", file=sys.stderr)
        sys.exit(1)
    return row[0]


def load_oof_data(conn, run_hash):
    """Load OOF predictions joined with matrix close prices."""
    query = """
        SELECT o.horizon_days, o.trade_date, o.cutoff_date, o.window_id,
               o.predicted_price, o.target_value,
               m.close AS cutoff_close
        FROM training.oof_core_1d o
        LEFT JOIN training.matrix_1d m
            ON m.trade_date = o.cutoff_date AND m.symbol = 'ZL'
        WHERE o.run_hash = %s
        ORDER BY o.horizon_days, o.window_id, o.trade_date
    """
    df = pd.read_sql(query, conn, params=(run_hash,))
    return df


def print_section(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def evaluate(df, run_hash):
    """Compute and print all metrics."""

    print_section(f"OOF Evaluation  |  run_hash = {run_hash}")
    print(f"  Total predictions: {len(df)}")
    print(f"  Horizons: {sorted(df['horizon_days'].unique())}")
    print(f"  Date range: {df['trade_date'].min()} to {df['trade_date'].max()}")

    # ── 1. Per-Horizon MAE & MAPE Accuracy ──
    print_section("1. MAE & MAPE Accuracy  (1 - MAE / AvgTarget)")

    header = f"  {'Horizon':>8s}  {'N':>5s}  {'MAE':>8s}  {'AvgTarget':>10s}  {'Accuracy':>10s}  {'P0 MAE':>8s}  {'P0 Delta':>10s}"
    print(header)
    print("  " + "-" * len(header))

    for h in sorted(df["horizon_days"].unique()):
        hdf = df[df["horizon_days"] == h]
        mae = (hdf["predicted_price"] - hdf["target_value"]).abs().mean()
        avg_target = hdf["target_value"].mean()
        accuracy = (1 - mae / avg_target) * 100

        p0 = PHASE0_BASELINE.get(h, {})
        p0_mae = p0.get("mae", np.nan)
        delta = mae - p0_mae if not np.isnan(p0_mae) else np.nan
        delta_str = f"{delta:+.4f}" if not np.isnan(delta) else "N/A"

        print(
            f"  {h:>5d}d  {len(hdf):>5d}  {mae:>8.4f}  {avg_target:>10.2f}  {accuracy:>9.1f}%  {p0_mae:>8.4f}  {delta_str:>10s}"
        )

    # ── 2. Cutoff-to-Target Directional Accuracy ──
    print_section("2. Cutoff-to-Target Directional Accuracy")
    print("  Q: Did the model predict the correct direction from the cutoff close?")
    print()

    header = f"  {'Horizon':>8s}  {'Correct':>8s}  {'N':>5s}  {'Accuracy':>10s}  {'PredUp%':>8s}  {'ActualUp%':>10s}  {'NullClose':>10s}"
    print(header)
    print("  " + "-" * len(header))

    for h in sorted(df["horizon_days"].unique()):
        hdf = df[df["horizon_days"] == h].copy()
        null_close = hdf["cutoff_close"].isna().sum()
        valid = hdf.dropna(subset=["cutoff_close"])
        n = len(valid)

        if n == 0:
            print(
                f"  {h:>5d}d  {'N/A':>8s}  {0:>5d}  {'N/A':>10s}  {'N/A':>8s}  {'N/A':>10s}  {null_close:>10d}"
            )
            continue

        pred_dir = valid["predicted_price"] - valid["cutoff_close"]
        actual_dir = valid["target_value"] - valid["cutoff_close"]
        correct = ((pred_dir > 0) & (actual_dir > 0)) | (
            (pred_dir < 0) & (actual_dir < 0)
        )
        correct_n = correct.sum()
        acc = 100.0 * correct_n / n

        pred_up_pct = 100.0 * (pred_dir > 0).sum() / n
        actual_up_pct = 100.0 * (actual_dir > 0).sum() / n

        print(
            f"  {h:>5d}d  {correct_n:>8d}  {n:>5d}  {acc:>9.1f}%  {pred_up_pct:>7.1f}%  {actual_up_pct:>9.1f}%  {null_close:>10d}"
        )

    # ── 3. Core vs Naive ──
    print_section("3. Core vs Naive (Naive = cutoff close price)")

    header = f"  {'Horizon':>8s}  {'CoreMAE':>8s}  {'NaiveMAE':>9s}  {'Improvement':>12s}  {'PredMove':>9s}  {'ActualMove':>11s}  {'MoveRatio':>10s}"
    print(header)
    print("  " + "-" * len(header))

    for h in sorted(df["horizon_days"].unique()):
        valid = df[(df["horizon_days"] == h)].dropna(subset=["cutoff_close"])
        if len(valid) == 0:
            continue

        core_mae = (valid["predicted_price"] - valid["target_value"]).abs().mean()
        naive_mae = (valid["cutoff_close"] - valid["target_value"]).abs().mean()
        improvement = (1 - core_mae / naive_mae) * 100
        pred_move = (valid["predicted_price"] - valid["cutoff_close"]).abs().mean()
        actual_move = (valid["target_value"] - valid["cutoff_close"]).abs().mean()
        ratio = pred_move / actual_move if actual_move > 0 else 0

        print(
            f"  {h:>5d}d  {core_mae:>8.2f}  {naive_mae:>9.2f}  {improvement:>11.1f}%  {pred_move:>9.2f}  {actual_move:>11.2f}  {ratio:>9.2f}x"
        )

    # ── 4. Per-Window Breakdown ──
    print_section("4. Per-Window Breakdown")

    header = f"  {'Horizon':>8s}  {'Window':>7s}  {'Cutoff':>12s}  {'N':>4s}  {'MAE':>8s}  {'AvgPred':>9s}  {'AvgTarget':>10s}  {'PredBias':>9s}"
    print(header)
    print("  " + "-" * len(header))

    for h in sorted(df["horizon_days"].unique()):
        hdf = df[df["horizon_days"] == h]
        for w in sorted(hdf["window_id"].unique()):
            wdf = hdf[hdf["window_id"] == w]
            mae = (wdf["predicted_price"] - wdf["target_value"]).abs().mean()
            avg_pred = wdf["predicted_price"].mean()
            avg_target = wdf["target_value"].mean()
            bias = avg_pred - avg_target

            print(
                f"  {h:>5d}d  w{w:<6d}  {str(wdf['cutoff_date'].iloc[0]):>12s}  {len(wdf):>4d}  {mae:>8.2f}  {avg_pred:>9.2f}  {avg_target:>10.2f}  {bias:>+9.2f}"
            )

    # ── 5. Phase 0 Comparison ──
    print_section("5. Phase 0 Baseline Comparison")

    header = f"  {'Horizon':>8s}  {'Phase0 MAE':>11s}  {'Phase1A MAE':>12s}  {'Delta':>8s}  {'Change':>8s}  {'Phase0 Weights'}"
    print(header)
    print("  " + "-" * 100)

    for h in sorted(df["horizon_days"].unique()):
        hdf = df[df["horizon_days"] == h]
        mae = (hdf["predicted_price"] - hdf["target_value"]).abs().mean()
        p0 = PHASE0_BASELINE.get(h, {})
        p0_mae = p0.get("mae", np.nan)
        delta = mae - p0_mae
        direction = (
            "WORSE" if delta > 0.005 else ("BETTER" if delta < -0.005 else "FLAT")
        )
        weights = p0.get("weights", "N/A")

        print(
            f"  {h:>5d}d  {p0_mae:>11.4f}  {mae:>12.4f}  {delta:>+8.4f}  {direction:>8s}  {weights}"
        )

    # ── 6. Ensemble Weights from Saved Models ──
    print_section("6. Current Ensemble Weights (from saved models)")

    try:
        from autogluon.timeseries import TimeSeriesPredictor

        for h in sorted(df["horizon_days"].unique()):
            model_path = f"models/core_v2/{h}d"
            try:
                p = TimeSeriesPredictor.load(model_path)
                info = p.info()
                we = info.get("model_info", {}).get("WeightedEnsemble", {})
                weights = we.get("model_weights", {})
                best_score = -1 * p.leaderboard().iloc[0]["score_val"]

                if weights:
                    weight_str = ", ".join(
                        f"{k} {v:.0%}"
                        for k, v in sorted(weights.items(), key=lambda x: -x[1])
                    )
                else:
                    weight_str = "(empty)"

                print(f"  {h:>5d}d: {weight_str}  |  Ensemble MAE: {best_score:.4f}")
            except Exception as e:
                print(f"  {h:>5d}d: ERROR loading model: {e}")
    except ImportError:
        print("  AutoGluon not available. Skipping ensemble weight extraction.")


def main():
    parser = argparse.ArgumentParser(description="Evaluate Core model OOF predictions")
    parser.add_argument(
        "--run-hash", type=str, default=None, help="Specific run_hash to evaluate"
    )
    parser.add_argument(
        "--list-runs", action="store_true", help="List available OOF runs"
    )
    args = parser.parse_args()

    conn = get_connection()

    if args.list_runs:
        list_runs(conn)
        conn.close()
        return

    run_hash = args.run_hash or get_latest_run_hash(conn)
    df = load_oof_data(conn, run_hash)
    conn.close()

    if len(df) == 0:
        print(f"ERROR: No predictions found for run_hash={run_hash}", file=sys.stderr)
        sys.exit(1)

    evaluate(df, run_hash)

    print(f"\n{'=' * 70}")
    print(f"  END OF REPORT")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
