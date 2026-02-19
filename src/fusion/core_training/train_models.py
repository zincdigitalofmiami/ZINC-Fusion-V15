"""
Phase 6: Sequential Core Training
==================================

Trains Core models for all 4 horizons using AutoGluon TimeSeriesPredictor.

Model: AutoGluon explicit model zoo (CPU-only, Chronos2 + deep + tabular + statistical).

Key Rules:
- All features as OBSERVED covariates (not known)
- num_val_windows=4 expanding windows
- OOF predictions via predictor.backtest_predictions() + backtest_targets()
- Sequential training: 5 → 21 → 63 → 126

Output:
- Models saved to models/core_v2/{horizon}d/
- OOF predictions written to training.oof_core_1d
"""

from __future__ import annotations

import os
import uuid

# =============================================================================
# CPU-ONLY SAFEGUARDS (set before any ML imports)
# =============================================================================
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
os.environ["AUTOGLUON_DISABLE_RAY"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # Block CUDA detection
os.environ["USE_MPS"] = "0"  # Disable MPS (HuggingFace)
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = (
    "1"  # Enable fallback to CPU (spec-compliant)
)
os.environ["PYTORCH_MPS_ENABLED"] = "0"  # Disable MPS backend explicitly

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from fusion.db.connection import get_write_connection
from psycopg2.extras import execute_values

from fusion.validation.all_data_policy import (
    check_source_freshness,
    enforce_all_data_policy,
)

from .config import (
    HORIZONS,
    MODEL_ZOO_FROZEN,
    OOF_COLUMN_NAMES,
    QUANTILES,
    TARGET_SYMBOL,
    TRAINING_CONFIG,
)

logger = logging.getLogger(__name__)

# AutoGluon imports (deferred to avoid import overhead)
TimeSeriesPredictor = None
TimeSeriesDataFrame = None


def import_autogluon():
    """Lazy import AutoGluon to avoid startup overhead."""
    global TimeSeriesPredictor, TimeSeriesDataFrame

    if TimeSeriesPredictor is None:
        logger.info("Importing AutoGluon (CPU-only mode)...")

        # Force torch to CPU before AutoGluon imports it
        import torch

        torch.set_default_device("cpu")
        if hasattr(torch.backends, "mps"):
            torch.backends.mps.is_available = lambda: False
        logger.info("   torch device: cpu (MPS disabled)")

        from autogluon.timeseries import TimeSeriesDataFrame as TSDF
        from autogluon.timeseries import TimeSeriesPredictor as TSP

        TimeSeriesPredictor = TSP
        TimeSeriesDataFrame = TSDF

        logger.info("✅ AutoGluon imported (CPU-only)")


def load_training_data(conn, symbol: str) -> pd.DataFrame:
    """
    Load core matrix for training.

    IMPORTANT: Data is loaded RAW (not normalized).
    AutoGluon handles normalization per-window internally.
    """
    logger.info("Loading training data (RAW features)...")

    query = """
        SELECT *
        FROM training.matrix_1d
        WHERE symbol = %s
        ORDER BY trade_date
    """
    df = pd.read_sql(query, conn, params=(symbol,))
    logger.info(f"   Loaded {len(df):,} rows, {len(df.columns)} columns")
    logger.info("   ⚠️ Features are RAW - AutoGluon handles normalization per-window")
    return df


def prepare_ts_dataframe(df: pd.DataFrame, horizon: int) -> TimeSeriesDataFrame:
    """
    Convert pandas DataFrame to TimeSeriesDataFrame for AutoGluon.

    All features are treated as OBSERVED covariates.
    """
    import_autogluon()

    # Target column
    target_col = f"target_ret_{horizon}d"

    # Drop rows where target is null (can't train on them)
    df_clean = df.dropna(subset=[target_col]).copy()
    # Also drop rows with non-finite targets (inf/-inf from zero prices)
    finite_mask = np.isfinite(df_clean[target_col])
    if not finite_mask.all():
        n_dropped = (~finite_mask).sum()
        logger.warning(f"   Dropped {n_dropped} rows with non-finite {target_col}")
        df_clean = df_clean[finite_mask].copy()

    # Drop known-problematic column before feature selection.
    if "hurst_exponent" in df_clean.columns:
        df_clean = df_clean.drop(columns=["hurst_exponent"])
        logger.warning("   Dropped column 'hurst_exponent' from core training matrix")

    # Identify feature columns (everything except metadata and other targets)
    exclude_cols = {"trade_date", "symbol", "matrix_version", "created_at"} | {
        f"target_ret_{h}d" for h in HORIZONS if h != horizon
    }

    feature_cols = [
        c for c in df_clean.columns if c not in exclude_cols and c != target_col
    ]

    # Rename for AutoGluon
    df_clean = df_clean.rename(columns={"trade_date": "timestamp"})

    # Add item_id (single time series)
    df_clean["item_id"] = TARGET_SYMBOL

    # Select columns in correct order
    ts_cols = ["item_id", "timestamp", target_col] + feature_cols
    df_ts = df_clean[ts_cols]

    # Convert to TimeSeriesDataFrame
    tsdf = TimeSeriesDataFrame.from_data_frame(
        df_ts, id_column="item_id", timestamp_column="timestamp"
    )

    logger.info(
        f"   Prepared TimeSeriesDataFrame: {len(tsdf)} rows, {len(feature_cols)} features"
    )
    return tsdf


def get_model_config(horizon: int) -> dict:
    """Get model configuration for horizon.

    CPU-only: explicit full model list, no presets, no time limits.
    Model zoo is defined in config.MODEL_ZOO_FROZEN (frozenset, 17 models).
    Only models in that frozen set are trained. No exceptions.

    AutoGluon trains all listed models and selects a WeightedEnsemble as best.
    """

    # Build hyperparameters from frozen set — no freehand additions possible
    hyperparameters = {model: {} for model in sorted(MODEL_ZOO_FROZEN)}

    logger.info(f"   Model zoo: {len(hyperparameters)} models from MODEL_ZOO_FROZEN")

    return {
        "hyperparameters": hyperparameters,
        "window_start": None,  # Use all available data
    }


def validate_trained_models(predictor, horizon: int) -> None:
    """Assert that ONLY frozen zoo models were trained.

    Raises RuntimeError if any unexpected model appears or any expected
    model is missing (excluding WeightedEnsemble variants which AutoGluon
    adds automatically).
    """
    trained = set(predictor.model_names())

    # AutoGluon adds WeightedEnsemble_* automatically — that's expected
    ensemble_models = {m for m in trained if m.startswith("WeightedEnsemble")}
    base_models = trained - ensemble_models

    # Check for rogue models (trained but not in frozen set)
    rogue = base_models - MODEL_ZOO_FROZEN
    if rogue:
        raise RuntimeError(
            f"ROGUE MODELS in {horizon}d training: {sorted(rogue)}. "
            f"Only MODEL_ZOO_FROZEN models are allowed. "
            f"Remove unauthorized models or update config.MODEL_ZOO_FROZEN."
        )

    # Check for missing models (in frozen set but didn't train)
    missing = MODEL_ZOO_FROZEN - base_models
    if missing:
        logger.warning(
            f"   {horizon}d: {len(missing)} models did not train: {sorted(missing)}"
        )

    logger.info(
        f"   {horizon}d model validation: {len(base_models)} base + "
        f"{len(ensemble_models)} ensemble OK"
    )


def filter_to_window(df: pd.DataFrame, window_start: str | None) -> pd.DataFrame:
    """Filter data to training window starting from window_start date."""
    if window_start is None:
        return df

    min_date = pd.to_datetime(window_start).date()
    filtered = df[df["trade_date"] >= min_date].copy()
    logger.info(
        f"   Filtered to window starting {window_start}: {len(filtered):,} rows"
    )
    return filtered


def train_horizon(
    df: pd.DataFrame, horizon: int, model_dir: Path, run_id: str
) -> tuple[TimeSeriesPredictor | None, pd.DataFrame | None]:
    """
    Train model for single horizon.

    Returns:
        (predictor, oof_predictions)
    """
    import_autogluon()

    logger.info(f"Training horizon {horizon}d...")

    config = get_model_config(horizon)
    target_col = f"target_ret_{horizon}d"

    # Filter to window
    df_window = filter_to_window(df, config["window_start"])

    # Prepare data
    tsdf = prepare_ts_dataframe(df_window, horizon)

    # Model path
    model_path = model_dir / f"{horizon}d"
    model_path.mkdir(parents=True, exist_ok=True)

    logger.info("   Presets: NONE (explicit model list)")
    logger.info("   Time limit: NONE")
    logger.info(f"   Validation windows: {TRAINING_CONFIG.num_val_windows}")
    logger.info(f"   Model path: {model_path}")

    # Get known covariates (NONE - all are observed)
    # Get static features (NONE for single time series)

    try:
        # Create predictor
        predictor = TimeSeriesPredictor(
            path=str(model_path),
            target=target_col,
            prediction_length=horizon,
            quantile_levels=QUANTILES,
            eval_metric=TRAINING_CONFIG.eval_metric,  # Use WQL from config
            known_covariates_names=[],  # EMPTY - all features are observed
            freq="B",  # Business day frequency (trading days have gaps)
        )

        # Fit model (explicit hyperparameters only; no presets, no time limit)
        predictor.fit(
            train_data=tsdf,
            hyperparameters=config[
                "hyperparameters"
            ],  # This now controls model selection
            num_val_windows=TRAINING_CONFIG.num_val_windows,
            # Let AutoGluon handle observed covariates automatically
        )

        # Validate: only frozen zoo models trained, no rogues
        validate_trained_models(predictor, horizon)

        logger.info(f"✅ Model trained for horizon {horizon}d")

        # Extract OOF predictions
        logger.info("   Extracting OOF predictions...")
        oof_df = extract_oof_predictions(predictor, horizon, run_id, df_window)

        return predictor, oof_df

    except Exception as e:
        logger.error(f"❌ Training failed for horizon {horizon}d: {e}", exc_info=True)
        return None, None


def _build_target_lookup(source_df: pd.DataFrame | None, horizon: int) -> dict:
    """Build {date → realized_return} lookup from training matrix.

    Returns empty dict if source_df is None or target column missing.
    """
    target_col = f"target_ret_{horizon}d"
    if source_df is None or target_col not in source_df.columns:
        return {}

    valid = source_df[["trade_date", target_col]].dropna()
    dates = pd.to_datetime(valid["trade_date"]).dt.date
    return dict(zip(dates, valid[target_col].astype(float)))


def extract_oof_predictions(
    predictor: TimeSeriesPredictor,
    horizon: int,
    run_id: str,
    source_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Extract out-of-fold predictions using AutoGluon 1.5 backtest API.

    Uses predictor.backtest_predictions() and predictor.backtest_targets()
    to get cached validation-window predictions from training.

    Args:
        predictor: Trained TimeSeriesPredictor
        horizon: Forecast horizon in days
        run_id: Training run identifier
        source_df: Original training data (unused — targets come from backtest_targets)

    Returns DataFrame with columns matching OOF schema.
    """
    try:
        num_windows = TRAINING_CONFIG.num_val_windows

        # Get cached predictions from training (data=None uses saved results)
        pred_windows = predictor.backtest_predictions(
            data=None, num_val_windows=num_windows
        )
        target_windows = predictor.backtest_targets(
            data=None, num_val_windows=num_windows
        )

        if not pred_windows:
            logger.warning("   No backtest predictions returned")
            return pd.DataFrame()

        logger.info(f"   Got {len(pred_windows)} validation windows")

        # Deterministic UUID from string run_id (stable across retries)
        run_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, run_id))

        target_col = f"target_ret_{horizon}d"
        oof_rows = []

        for window_id, (preds_df, targets_df) in enumerate(
            zip(pred_windows, target_windows), start=1
        ):
            # preds_df is a TimeSeriesDataFrame with quantile columns (e.g. "0.3", "0.5", "0.7")
            # targets_df has the actual target values; last `horizon` rows are the forecast period

            # Build target lookup from targets_df
            target_lookup = {}
            if targets_df is not None and target_col in targets_df.columns:
                # targets_df index is (item_id, timestamp) — get last `horizon` rows
                tail = targets_df.tail(horizon)
                for ts_idx, row in tail.iterrows():
                    # ts_idx is (item_id, timestamp)
                    ts = ts_idx[1] if isinstance(ts_idx, tuple) else ts_idx
                    target_lookup[pd.Timestamp(ts).date()] = float(row[target_col])

            # Cutoff = first prediction timestamp minus 1 business day
            if len(preds_df) > 0:
                first_ts = preds_df.index.get_level_values(-1).min()
                cutoff_date = (
                    pd.Timestamp(first_ts) - pd.tseries.offsets.BDay(1)
                ).date()
            else:
                cutoff_date = datetime.utcnow().date()

            # Extract quantile predictions
            for ts_idx, row in preds_df.iterrows():
                ts = ts_idx[1] if isinstance(ts_idx, tuple) else ts_idx
                trade_date = pd.Timestamp(ts)
                td_key = trade_date.date()

                oof_row = {
                    "trade_date": trade_date,
                    "symbol": TARGET_SYMBOL,
                    "horizon_days": horizon,
                    "p30": float(row.get("0.3", row.get("mean", 0))),
                    "p50": float(row.get("0.5", row.get("mean", 0))),
                    "p70": float(row.get("0.7", row.get("mean", 0))),
                    "target_value": target_lookup.get(td_key),
                    "window_id": window_id,
                    "cutoff_date": cutoff_date,
                    "trained_at": datetime.utcnow(),
                    "run_id": run_uuid,
                }
                oof_rows.append(oof_row)

        df_oof = pd.DataFrame(oof_rows)
        logger.info(
            f"   Extracted {len(df_oof):,} OOF predictions across {len(pred_windows)} windows"
        )
        return df_oof

    except Exception as e:
        raise RuntimeError(f"OOF extraction failed for {horizon}d: {e}") from e


def enforce_monotonic_quantiles(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure p30 <= p50 <= p70."""
    if len(df) == 0:
        return df

    violations = (df["p30"] > df["p50"]) | (df["p50"] > df["p70"])
    n_violations = violations.sum()

    if n_violations > 0:
        logger.warning(f"   Fixing {n_violations} quantile ordering violations")

        # Vectorized sort across quantile columns
        q_vals = df.loc[violations, ["p30", "p50", "p70"]].values
        q_vals.sort(axis=1)
        df.loc[violations, ["p30", "p50", "p70"]] = q_vals

    return df


def write_oof_predictions(conn, df_oof: pd.DataFrame, versions: dict):
    """Write OOF predictions to training.oof_core_1d."""
    if len(df_oof) == 0:
        logger.warning("   No OOF predictions to write")
        return 0

    logger.info(f"Writing {len(df_oof):,} OOF predictions...")

    # Add version columns
    df_oof["run_hash"] = versions.get("run_hash")
    df_oof["matrix_version"] = versions.get("matrix_version")

    # Enforce monotonic quantiles
    df_oof = enforce_monotonic_quantiles(df_oof)

    # Ensure all required columns exist
    for col in OOF_COLUMN_NAMES:
        if col not in df_oof.columns:
            df_oof[col] = None

    # Select only OOF columns
    df_oof = df_oof[list(OOF_COLUMN_NAMES)]

    # Insert
    cols = list(df_oof.columns)
    insert_sql = f"""
        INSERT INTO training.oof_core_1d ({",".join(cols)})
        VALUES %s
        ON CONFLICT (trade_date, symbol, horizon_days, window_id)
        DO UPDATE SET
            p30 = EXCLUDED.p30,
            p50 = EXCLUDED.p50,
            p70 = EXCLUDED.p70,
            target_value = EXCLUDED.target_value,
            cutoff_date = EXCLUDED.cutoff_date,
            run_hash = EXCLUDED.run_hash,
            matrix_version = EXCLUDED.matrix_version,
            trained_at = EXCLUDED.trained_at,
            run_id = EXCLUDED.run_id
    """

    # Convert NaN → None so Postgres stores NULL (not NaN which poisons aggregates)
    df_oof = df_oof.where(df_oof.notna(), None)
    values = [
        tuple(None if pd.isna(v) else v for v in row)
        for row in df_oof.itertuples(index=False, name=None)
    ]

    with conn.cursor() as cur:
        execute_values(cur, insert_sql, values, page_size=1000)

    conn.commit()
    logger.info(f"   Wrote {len(df_oof):,} OOF predictions")
    return len(df_oof)


def run(
    symbol: str = TARGET_SYMBOL, horizons: list[int] = None, versions: dict = None
) -> tuple[bool, dict[int, bool]]:
    """
    Execute Phase 6: Sequential Core Training.

    Args:
        symbol: Target symbol
        horizons: List of horizons to train (default: all)
        versions: Dict with matrix_version, options_version, elite_version

    Returns:
        (success: bool, results: Dict[horizon, success])
    """
    if horizons is None:
        horizons = HORIZONS
    if versions is None:
        versions = {}

    logger.info("=" * 60)
    logger.info("PHASE 6: SEQUENTIAL CORE TRAINING")
    logger.info("=" * 60)
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Horizons: {horizons}")
    logger.info(f"Quantiles: {QUANTILES}")
    logger.info("=" * 60)

    # Generate run ID
    run_id = f"core_v2_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    logger.info(f"Run ID: {run_id}")

    # Model directory
    from .config import MODELS_DIR

    model_dir = MODELS_DIR
    model_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    all_oof = []

    try:
        conn = get_write_connection()
        logger.info("✅ Database connected")

        # Enforce ALL DATA policy before training (per CORE_TRAINING_SPEC_LOCKED.md)
        logger.info("")
        logger.info("Validating ALL DATA policy...")
        for horizon in horizons:
            enforce_all_data_policy(conn, horizon=horizon, strict=True)
        logger.info("✅ ALL DATA policy passed for all horizons")

        # Enforce data source freshness (P0-1 fix: check recency, not just row counts)
        logger.info("")
        logger.info("Validating data source freshness...")
        check_source_freshness(conn, strict=True)
        logger.info("✅ Data freshness gate passed")

        # Enforce specialist data freshness (all 11 buckets, including biofuel RIN/LCFS)
        # Uses existing data_gate_specialists.py --strict via subprocess to reuse
        # SPECIALIST_DATA_GATES TTL definitions without cross-directory imports.
        logger.info("")
        logger.info("Validating specialist data freshness (all 11 buckets)...")
        project_root = str(Path(__file__).resolve().parents[3])
        gate_result = subprocess.run(
            [sys.executable, "scripts/data_gate_specialists.py", "--strict"],
            capture_output=True,
            text=True,
            cwd=project_root,
        )
        if gate_result.returncode != 0:
            logger.error(gate_result.stdout)
            logger.error(gate_result.stderr)
            raise ValueError(
                "SPECIALIST DATA GATE FAILED. "
                "All 11 specialist data sources are HARD-REQUIRED. "
                "Run: python scripts/data_gate_specialists.py --strict "
                "for full report."
            )
        logger.info("✅ Specialist data gate passed (all 11 buckets)")

        # Load data once
        df = load_training_data(conn, symbol)

        # Train each horizon sequentially
        for horizon in horizons:
            logger.info("")
            logger.info("-" * 40)
            logger.info(f"TRAINING HORIZON: {horizon}d")
            logger.info("-" * 40)

            predictor, oof_df = train_horizon(df, horizon, model_dir, run_id)

            if predictor is not None and oof_df is not None and len(oof_df) > 0:
                results[horizon] = True
                if "horizon_days" not in oof_df.columns:
                    oof_df["horizon_days"] = horizon
                all_oof.append(oof_df)
            else:
                results[horizon] = False
                if predictor is not None:
                    logger.error(
                        f"❌ {horizon}d: Model trained but OOF extraction "
                        f"returned empty — marking as FAILED"
                    )

        # Combine and write all OOF predictions
        if all_oof:
            df_all_oof = pd.concat(all_oof, ignore_index=True)
            write_oof_predictions(conn, df_all_oof, versions)

        conn.close()

        # Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("TRAINING SUMMARY")
        logger.info("=" * 60)

        for horizon, success in results.items():
            status = "✅" if success else "❌"
            logger.info(f"   {horizon}d: {status}")

        all_success = all(results.values())

        if all_success:
            logger.info("=" * 60)
            logger.info("✅ PHASE 6 COMPLETE - All models trained")
            logger.info(f"   Run ID: {run_id}")
            logger.info(f"   Models saved to: {model_dir}")
            logger.info("=" * 60)
        else:
            logger.error("=" * 60)
            logger.error("⚠️ PHASE 6 PARTIAL - Some models failed")
            logger.error("=" * 60)

        return all_success, results

    except Exception as e:
        logger.error(f"❌ PHASE 6 FAILED: {e}", exc_info=True)
        return False, results


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="Phase 6: Sequential Core Training")
    parser.add_argument("--symbol", default=TARGET_SYMBOL)
    parser.add_argument(
        "--horizons",
        type=int,
        nargs="+",
        default=HORIZONS,
        help="Horizons to train (default: 5 21 63 126)",
    )
    args = parser.parse_args()

    success, results = run(args.symbol, args.horizons)
    exit(0 if success else 1)
