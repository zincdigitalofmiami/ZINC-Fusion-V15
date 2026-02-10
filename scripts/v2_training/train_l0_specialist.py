#!/usr/bin/env python3
"""
SoT v2: L0 Specialist Model Training (AutoGluon Tabular)

Trains all 11 specialist models for all 4 horizons (44 models total) using
AutoGluon TabularPredictor with quantile regression + bagging/stacking.
Outputs OOF predictions to training.oof_{specialist}_1d with horizon_days discriminator.

Specialists (Big 11):
- crush, china, fx, fed, tariff, energy, biofuel, palm, volatility, substitutes, trump_effect

Model IDs: zinc-fusion-v2-specialist-{bucket}-h{H}d

Usage:
    python scripts/v2_training/train_l0_specialist.py --bucket crush --horizon 5
    python scripts/v2_training/train_l0_specialist.py --bucket all --horizon all
    python scripts/v2_training/train_l0_specialist.py --bucket all --horizon 21 --dry-run

@author Claude (ZINC-FUSION-V15)
@version 1.0.0
@date 2026-01-20
"""

import os

os.environ["TF_USE_LEGACY_KERAS"] = "1"
os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
os.environ["AUTOGLUON_DISABLE_RAY"] = "1"

import sys
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv(PROJECT_ROOT / ".env")

# =============================================================================
# CONSTANTS (SoT v2 Locked)
# =============================================================================

HORIZONS = [5, 21, 63, 126]
QUANTILES = [0.30, 0.50, 0.70]
NUM_VAL_WINDOWS = 4

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

TACTICAL_START = "2020-01-01"
STRATEGIC_START = "2000-01-01"


def get_model_id(bucket: str, horizon: int) -> str:
    return f"zinc-fusion-v2-specialist-{bucket}-h{horizon}d"


def get_run_label() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# =============================================================================
# DATABASE CONNECTION
# =============================================================================


def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found")
    return psycopg2.connect(database_url)


# =============================================================================
# DATA LOADING
# =============================================================================


def load_specialist_data(conn, bucket: str, horizon: int) -> pd.DataFrame:
    """Load ALL available features from training.matrix_1d for this horizon."""

    start_date = TACTICAL_START if horizon in [5, 21] else STRATEGIC_START
    target_col = f"target_ret_{horizon}d"

    logger.info(f"Loading {bucket} specialist data for {horizon}d from {start_date}...")

    query = f"""
        SELECT *
        FROM training.matrix_1d
        WHERE symbol = 'ZL'
          AND trade_date >= %s
          AND {target_col} IS NOT NULL
        ORDER BY trade_date
    """

    df = pd.read_sql(query, conn, params=(start_date,))
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("trade_date")

    # Consistent label
    df["target"] = df[target_col]

    # Drop non-feature columns
    drop_cols = {"symbol", "matrix_version", "created_at"} | {
        f"target_ret_{h}d" for h in HORIZONS
    }
    drop_cols = [c for c in df.columns if c in drop_cols]
    df = df.drop(columns=drop_cols, errors="ignore")

    # Convert Decimal to float
    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            except Exception:
                pass

    # Forward-fill NaN
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].ffill().bfill()

    logger.info(f"  Loaded {len(df):,} rows, {len(df.columns) - 1} features")

    return df


# =============================================================================
# CROSS-VALIDATION WINDOWS
# =============================================================================


def create_expanding_windows(df: pd.DataFrame, horizon: int) -> List[Dict]:
    total_days = len(df)
    min_train_size = int(total_days * 0.6)
    val_space = horizon * NUM_VAL_WINDOWS

    windows = []
    for w in range(NUM_VAL_WINDOWS):
        train_end_idx = min_train_size + (
            w * (total_days - min_train_size - val_space) // NUM_VAL_WINDOWS
        )
        val_start_idx = train_end_idx
        val_end_idx = min(val_start_idx + horizon, total_days)

        cutoff_date = df.index[train_end_idx - 1]

        windows.append(
            {
                "window_id": w + 1,
                "train_end_idx": train_end_idx,
                "val_start_idx": val_start_idx,
                "val_end_idx": val_end_idx,
                "cutoff_date": cutoff_date,
            }
        )

    return windows


# =============================================================================
# MODEL TRAINING (AutoGluon TabularPredictor)
# =============================================================================


def train_quantile_predictor(
    train_df: pd.DataFrame,
    label: str,
    model_path: Path,
    time_limit: int,
    num_bag_folds: int,
    num_stack_levels: int,
) -> "TabularPredictor":  # noqa: F821
    from autogluon.tabular import TabularPredictor

    predictor = TabularPredictor(
        label=label,
        problem_type="quantile",
        quantile_levels=QUANTILES,
        path=str(model_path),
        eval_metric="pinball_loss",
    )

    predictor.fit(
        train_data=train_df,
        presets="best_quality",
        time_limit=time_limit,
        num_bag_folds=num_bag_folds,
        num_stack_levels=num_stack_levels,
        auto_stack=True,
        keep_only_best=False,
    )

    return predictor


# =============================================================================
# OOF PREDICTION GENERATION
# =============================================================================


def train_and_predict_oof(
    df: pd.DataFrame,
    bucket: str,
    horizon: int,
    run_hash: str,
    run_label: str,
    time_limit: int,
    num_bag_folds: int,
    num_stack_levels: int,
    dry_run: bool = False,
) -> pd.DataFrame:
    windows = create_expanding_windows(df, horizon)
    feature_cols = [c for c in df.columns if c not in ["target"]]

    oof_results = []

    for window in windows:
        w_id = window["window_id"]
        cutoff = window["cutoff_date"]
        train_idx = window["train_end_idx"]
        val_start = window["val_start_idx"]
        val_end = window["val_end_idx"]

        logger.info(f"  Window {w_id}/{NUM_VAL_WINDOWS} (cutoff: {cutoff.date()})")

        train_df = df.iloc[:train_idx]
        val_df = df.iloc[val_start:val_end]

        train_data = train_df[feature_cols + ["target"]]
        val_features = val_df[feature_cols]

        logger.info(f"    Train: {len(train_data):,}, Val: {len(val_features):,}")

        if dry_run:
            logger.info(
                f"    DRY RUN: Skipping window {w_id} training (no fake predictions generated)"
            )
            continue

        else:
            model_path = (
                Path("models")
                / "specialists"
                / bucket
                / f"horizon_{horizon}d"
                / f"run_{run_label}"
                / f"window_{w_id}"
            )
            model_path.mkdir(parents=True, exist_ok=True)

            predictor = train_quantile_predictor(
                train_df=train_data,
                label="target",
                model_path=model_path,
                time_limit=time_limit,
                num_bag_folds=num_bag_folds,
                num_stack_levels=num_stack_levels,
            )

            # AutoGluon 1.5: quantile predictor returns DataFrame with quantile columns
            preds = predictor.predict(val_features)
            if isinstance(preds, pd.Series):
                preds_df = pd.DataFrame({"0.5": preds}, index=val_features.index)
            else:
                preds_df = preds.copy()
                preds_df.columns = [str(c) for c in preds_df.columns]

        for i, (date, row) in enumerate(val_df.iterrows()):
            oof_results.append(
                {
                    "trade_date": date,
                    "symbol": "ZL",
                    "horizon_days": horizon,
                    "window_id": w_id,
                    "cutoff_date": cutoff,
                    "p30": float(preds_df.iloc[i].get("0.3", np.nan)),
                    "p50": float(preds_df.iloc[i].get("0.5", np.nan)),
                    "p70": float(preds_df.iloc[i].get("0.7", np.nan)),
                    "target_value": float(row["target"])
                    if pd.notna(row["target"])
                    else None,
                    "trained_at": datetime.now(timezone.utc),
                    "run_hash": run_hash,
                }
            )

    oof_df = pd.DataFrame(oof_results)
    logger.info(f"  Generated {len(oof_df)} OOF predictions")

    return oof_df


# =============================================================================
# DATABASE WRITE
# =============================================================================


def write_oof_to_db(
    conn, oof_df: pd.DataFrame, bucket: str, dry_run: bool = False
) -> int:
    table_name = f"training.oof_{bucket}_1d"

    if dry_run:
        logger.info(f"  [DRY RUN] Would write {len(oof_df)} rows to {table_name}")
        return 0

    records = []
    for _, row in oof_df.iterrows():
        records.append(
            (
                row["trade_date"],
                row["symbol"],
                row["horizon_days"],
                row["window_id"],
                row["cutoff_date"],
                row["p30"],
                row["p50"],
                row["p70"],
                row["target_value"],
                row["trained_at"],
                row["run_hash"],
                None,
            )
        )

    insert_sql = f"""
        INSERT INTO {table_name} (
            trade_date, symbol, horizon_days, window_id, cutoff_date,
            p30, p50, p70, target_value, trained_at, run_hash, matrix_version
        ) VALUES %s
        ON CONFLICT (trade_date, symbol, horizon_days, window_id)
        DO UPDATE SET
            p30 = EXCLUDED.p30,
            p50 = EXCLUDED.p50,
            p70 = EXCLUDED.p70,
            target_value = EXCLUDED.target_value,
            trained_at = EXCLUDED.trained_at,
            run_hash = EXCLUDED.run_hash
    """

    with conn.cursor() as cur:
        execute_values(cur, insert_sql, records)
    conn.commit()

    logger.info(f"  Wrote {len(records)} OOF predictions to {table_name}")
    return len(records)


# =============================================================================
# MAIN TRAINING
# =============================================================================


def train_specialist_model(
    bucket: str,
    horizon: int,
    run_hash: str,
    run_label: str,
    time_limit: int,
    num_bag_folds: int,
    num_stack_levels: int,
    dry_run: bool = False,
) -> Dict:
    model_id = get_model_id(bucket, horizon)
    logger.info(f"\n{'=' * 60}")
    logger.info(f"TRAINING: {model_id}")
    logger.info(f"{'=' * 60}")

    conn = get_connection()

    try:
        df = load_specialist_data(conn, bucket, horizon)

        if len(df) < 200:
            logger.error(f"Insufficient data: {len(df)} rows")
            return {
                "bucket": bucket,
                "horizon": horizon,
                "status": "failed",
                "reason": "insufficient_data",
            }

        oof_df = train_and_predict_oof(
            df=df,
            bucket=bucket,
            horizon=horizon,
            run_hash=run_hash,
            run_label=run_label,
            time_limit=time_limit,
            num_bag_folds=num_bag_folds,
            num_stack_levels=num_stack_levels,
            dry_run=dry_run,
        )

        if len(oof_df) > 0 and oof_df["target_value"].notna().any():
            mae = np.abs(oof_df["p50"] - oof_df["target_value"]).mean()
            coverage = (
                (oof_df["target_value"] >= oof_df["p30"])
                & (oof_df["target_value"] <= oof_df["p70"])
            ).mean()
            logger.info(f"  OOF MAE (p50): {mae:.6f}")
            logger.info(f"  OOF 40% Coverage: {coverage:.2%}")

        rows_written = write_oof_to_db(conn, oof_df, bucket, dry_run)

        return {
            "bucket": bucket,
            "horizon": horizon,
            "model_id": model_id,
            "status": "success",
            "rows_written": rows_written,
            "oof_count": len(oof_df),
        }

    except Exception as e:
        logger.error(f"Training failed for {model_id}: {e}")
        return {
            "bucket": bucket,
            "horizon": horizon,
            "status": "failed",
            "reason": str(e),
        }

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="SoT v2: L0 Specialist Model Training")
    parser.add_argument(
        "--bucket", type=str, required=True, help="Specialist bucket or 'all'"
    )
    parser.add_argument(
        "--horizon", type=str, required=True, help="Horizon (5, 21, 63, 126, or 'all')"
    )
    parser.add_argument(
        "--time-limit",
        type=int,
        default=5400,
        help="Time limit (seconds) per window fit",
    )
    parser.add_argument(
        "--num-bag-folds", type=int, default=10, help="AutoGluon bagging folds"
    )
    parser.add_argument(
        "--num-stack-levels", type=int, default=2, help="AutoGluon stack levels"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate without training"
    )
    args = parser.parse_args()

    # Parse buckets
    if args.bucket.lower() == "all":
        buckets = SPECIALISTS
    else:
        buckets = [args.bucket]
        if buckets[0] not in SPECIALISTS:
            logger.error(f"Invalid bucket: {buckets[0]}. Must be one of {SPECIALISTS}")
            return 1

    # Parse horizons
    if args.horizon.lower() == "all":
        horizons = HORIZONS
    else:
        horizons = [int(args.horizon)]
        if horizons[0] not in HORIZONS:
            logger.error(f"Invalid horizon: {horizons[0]}")
            return 1

    run_label = get_run_label()
    run_hash = f"specialist_{run_label}"

    logger.info("=" * 60)
    logger.info("SoT v2: L0 SPECIALIST MODEL TRAINING")
    logger.info("=" * 60)
    logger.info(f"Buckets: {buckets}")
    logger.info(f"Horizons: {horizons}")
    logger.info(f"Total models: {len(buckets) * len(horizons)}")
    logger.info(f"Run label: {run_label}")
    logger.info(f"Run hash: {run_hash}")
    logger.info("=" * 60)

    results = []
    for bucket in buckets:
        for horizon in horizons:
            result = train_specialist_model(
                bucket=bucket,
                horizon=horizon,
                run_hash=run_hash,
                run_label=run_label,
                time_limit=args.time_limit,
                num_bag_folds=args.num_bag_folds,
                num_stack_levels=args.num_stack_levels,
                dry_run=args.dry_run,
            )
            results.append(result)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TRAINING SUMMARY")
    logger.info("=" * 60)

    success_count = sum(1 for r in results if r["status"] == "success")
    total_oof = sum(r.get("oof_count", 0) for r in results)

    for r in results:
        status = "OK" if r["status"] == "success" else "FAIL"
        model_name = r.get("model_id", f"{r['bucket']}-h{r['horizon']}d")
        logger.info(f"  [{status}] {model_name}: {r['status']}")

    logger.info(
        f"\nTotal: {success_count}/{len(results)} successful, {total_oof} OOF predictions"
    )

    return 0 if success_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
