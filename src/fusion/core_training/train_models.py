"""
Phase 6: Sequential Core Training
==================================

Trains Core models for all 4 horizons using AutoGluon TimeSeriesPredictor.

Model: AutoGluon explicit model zoo (CPU-only, Chronos2 + deep + tabular + statistical).

Key Rules:
- All features as OBSERVED covariates (not known)
- num_val_windows=4 expanding windows
- OOF predictions via predictor.backtest()
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
from datetime import datetime
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from fusion.validation.all_data_policy import enforce_all_data_policy

from .config import (
    DATABASE_URL,
    HORIZONS,
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

    Per CORE_TRAINING_SPEC_LOCKED.md, this must include ALL Model Zoo entries:
    - Baselines (5): Naive, SeasonalNaive, Average, SeasonalAverage, Zero
    - Statistical (9): ETS, AutoETS, AutoARIMA, AutoCES, Theta, DynamicOptimizedTheta, NPTS, ADIDA, Croston, IMAPA
    - Deep/ML (5): DeepAR, TemporalFusionTransformer, DLinear, PatchTST, SimpleFeedForward
    - Neural (2): TiDE, WaveNet
    - Tabular TS (3): DirectTabular, PerStepTabular, RecursiveTabular
    - Pretrained (3): Chronos2, Chronos, Toto (disabled on macOS ARM due to HuggingFace mutex)

    AutoGluon trains all models and typically selects a WeightedEnsemble as best.
    """

    hyperparameters = {
        # === BASELINES (5) ===
        "Naive": {},
        "SeasonalNaive": {},
        "Average": {},
        "SeasonalAverage": {},
        "Zero": {},
        # === STATISTICAL (10) ===
        "ETS": {},
        "AutoETS": {},
        "AutoARIMA": {},
        "AutoCES": {},  # Added per spec
        "Theta": {},
        "DynamicOptimizedTheta": {},
        "NPTS": {},
        "ADIDA": {},
        "Croston": {},
        "IMAPA": {},
        # === DEEP / ML (5) ===
        "DeepAR": {},
        "TemporalFusionTransformer": {},
        "DLinear": {},
        "PatchTST": {},
        "SimpleFeedForward": {},
        # === NEURAL (2) ===
        "TiDE": {},
        "WaveNet": {},
        # === TABULAR TS (3) ===
        "DirectTabular": {},
        "PerStepTabular": {},
        "RecursiveTabular": {},
        # === PRETRAINED (disabled on macOS ARM - HuggingFace mutex lock issues) ===
        # Uncomment on Linux/server environments where these run reliably:
        # "Chronos2": {},
        # "Chronos": {},
        # "Toto": {},
    }

    return {
        "hyperparameters": hyperparameters,
        "window_start": None,  # Use all available data
    }


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

    # Identify covariate columns
    exclude = {"item_id", "timestamp", target_col}
    [c for c in tsdf.columns if c not in exclude]

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

    lookup = {}
    for _, src_row in source_df.iterrows():
        td = src_row.get("trade_date")
        if td is not None and pd.notna(src_row.get(target_col)):
            lookup[pd.Timestamp(td).date()] = float(src_row[target_col])
    return lookup


def extract_oof_predictions(
    predictor: TimeSeriesPredictor,
    horizon: int,
    run_id: str,
    source_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Extract out-of-fold predictions using backtest.

    Args:
        predictor: Trained TimeSeriesPredictor
        horizon: Forecast horizon in days
        run_id: Training run identifier
        source_df: Original training data with target_ret_{horizon}d for
                   populating target_value (realized return at horizon)

    Returns DataFrame with columns matching OOF schema.
    """
    try:
        # Get backtest predictions (OOF)
        backtest = predictor.backtest(
            num_val_windows=TRAINING_CONFIG.num_val_windows, return_predictions=True
        )

        # backtest returns a dict with 'predictions' and 'info'
        if isinstance(backtest, dict):
            preds = backtest.get("predictions", pd.DataFrame())
            info = backtest.get("info", {})
        else:
            preds = backtest
            info = {}

        if len(preds) == 0:
            logger.warning("   No backtest predictions returned")
            return pd.DataFrame()

        # Build lookup once (not per-window)
        target_lookup = _build_target_lookup(source_df, horizon)

        # Deterministic UUID from string run_id (stable across retries)
        run_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, run_id))

        # Convert to OOF format
        oof_rows = []

        for window_id in range(1, TRAINING_CONFIG.num_val_windows + 1):
            # Filter predictions for this window
            window_preds = (
                preds[preds.get("window_id", window_id) == window_id]
                if "window_id" in preds.columns
                else preds
            )

            for idx, row in window_preds.iterrows():
                trade_date = idx if isinstance(idx, datetime) else row.get("timestamp")
                td_key = (
                    pd.Timestamp(trade_date).date() if trade_date is not None else None
                )
                realized = target_lookup.get(td_key) if td_key else None

                oof_row = {
                    "trade_date": trade_date,
                    "symbol": TARGET_SYMBOL,
                    "horizon_days": horizon,
                    "p30": row.get("0.3", row.get("mean", 0)),
                    "p50": row.get("0.5", row.get("mean", 0)),
                    "p70": row.get("0.7", row.get("mean", 0)),
                    "target_value": realized,
                    "window_id": window_id,
                    "cutoff_date": info.get(
                        f"cutoff_{window_id}", datetime.utcnow().date()
                    ),
                    "trained_at": datetime.utcnow(),
                    "run_id": run_uuid,
                }
                oof_rows.append(oof_row)

        df_oof = pd.DataFrame(oof_rows)
        logger.info(f"   Extracted {len(df_oof):,} OOF predictions")
        return df_oof

    except Exception as e:
        logger.warning(f"   Could not extract OOF predictions: {e}")
        return pd.DataFrame()


def enforce_monotonic_quantiles(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure p30 <= p50 <= p70."""
    if len(df) == 0:
        return df

    violations = (df["p30"] > df["p50"]) | (df["p50"] > df["p70"])
    n_violations = violations.sum()

    if n_violations > 0:
        logger.warning(f"   Fixing {n_violations} quantile ordering violations")

        # Sort quantiles for each row
        for idx in df[violations].index:
            vals = sorted([df.loc[idx, "p30"], df.loc[idx, "p50"], df.loc[idx, "p70"]])
            df.loc[idx, "p30"] = vals[0]
            df.loc[idx, "p50"] = vals[1]
            df.loc[idx, "p70"] = vals[2]

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
    model_dir = Path("models/core_v2")
    model_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    all_oof = []

    try:
        conn = psycopg2.connect(DATABASE_URL)
        logger.info("✅ Database connected")

        # Enforce ALL DATA policy before training (per CORE_TRAINING_SPEC_LOCKED.md)
        logger.info("")
        logger.info("Validating ALL DATA policy...")
        for horizon in horizons:
            enforce_all_data_policy(conn, horizon=horizon, strict=True)
        logger.info("✅ ALL DATA policy passed for all horizons")

        # Load data once
        df = load_training_data(conn, symbol)

        # Train each horizon sequentially
        for horizon in horizons:
            logger.info("")
            logger.info("-" * 40)
            logger.info(f"TRAINING HORIZON: {horizon}d")
            logger.info("-" * 40)

            predictor, oof_df = train_horizon(df, horizon, model_dir, run_id)

            if predictor is not None:
                results[horizon] = True
                if len(oof_df) > 0:
                    if "horizon_days" not in oof_df.columns:
                        oof_df["horizon_days"] = horizon
                    all_oof.append(oof_df)
            else:
                results[horizon] = False

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
