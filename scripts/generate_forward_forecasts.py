"""
Generate Forward Forecasts via Model Inference
===============================================

Replaces OOF-based production forecasts with true forward inference.

For each horizon (5d, 21d, 63d, 126d):
  1. Load trained TimeSeriesPredictor from models/core_v2/{horizon}d/
  2. Build TimeSeriesDataFrame from latest matrix (training.matrix_1d)
  3. Generate known covariates (seasonal features) for the forecast horizon
  4. Call predictor.predict() to get point forecast
  5. Calibrate quantile ranges from historical OOF residuals
  6. Upsert into forecasts.production_1d with as_of_date = today

Usage:
    python scripts/generate_forward_forecasts.py
    python scripts/generate_forward_forecasts.py --horizon 63
    python scripts/generate_forward_forecasts.py --dry-run
"""

import logging
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fusion.db.connection import DatabaseConnections

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

HORIZONS = [5, 21, 63, 126]
SYMBOL = "ZL"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models" / "core_v2"

# Seasonal features — must match config.SEASONAL_FEATURES exactly
SEASONAL_FEATURES = [
    "month_sin",
    "month_cos",
    "week_of_year_sin",
    "week_of_year_cos",
    "is_planting_season",
    "is_harvest_season",
    "is_crush_season",
    "is_south_america_harvest",
]


def import_autogluon():
    """Lazy import to avoid startup overhead."""
    global TimeSeriesPredictor, TimeSeriesDataFrame
    from autogluon.timeseries import TimeSeriesDataFrame, TimeSeriesPredictor


def load_matrix(engine) -> pd.DataFrame:
    """Load full matrix from training.matrix_1d."""
    query = """
        SELECT *
        FROM training.matrix_1d
        WHERE symbol = %s
        ORDER BY trade_date
    """
    df = pd.read_sql(query, engine, params=(SYMBOL,))
    logger.info(f"Loaded matrix: {len(df):,} rows, {len(df.columns)} columns")
    return df


def get_latest_zl_close(engine) -> tuple:
    """Get most recent ZL close price."""
    query = """
        SELECT close, event_date
        FROM mkt.futures_1d
        WHERE symbol = 'ZL' AND close IS NOT NULL
        ORDER BY event_date DESC
        LIMIT 1
    """
    df = pd.read_sql(query, engine)
    if len(df) == 0:
        return None, None
    return float(df.iloc[0]["close"]), df.iloc[0]["event_date"]


def compute_seasonal_features(dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Compute deterministic seasonal features for future dates.

    These are known covariates — computable without market data.
    Must match the encoding in build_matrix.py exactly.
    """
    month = dates.month
    week = dates.isocalendar().week.astype(int)

    df = pd.DataFrame(index=dates)
    df["month_sin"] = np.sin(2 * math.pi * month / 12)
    df["month_cos"] = np.cos(2 * math.pi * month / 12)
    df["week_of_year_sin"] = np.sin(2 * math.pi * week / 52)
    df["week_of_year_cos"] = np.cos(2 * math.pi * week / 52)

    # Crop seasons (US Midwest soybean calendar)
    df["is_planting_season"] = month.isin([4, 5, 6]).astype(float)
    df["is_harvest_season"] = month.isin([9, 10, 11]).astype(float)
    df["is_crush_season"] = month.isin([10, 11, 12, 1, 2, 3]).astype(float)
    df["is_south_america_harvest"] = month.isin([2, 3, 4, 5]).astype(float)

    return df


def prepare_inference_data(df: pd.DataFrame, horizon: int):
    """Build TimeSeriesDataFrame for inference.

    Unlike training, we keep ALL rows (including where target is NaN) because
    the predictor needs the full history up to the present. The target column
    must exist but can have NaN at the tail.
    """
    target_col = f"target_price_{horizon}d"

    df_inf = df.copy()

    # Drop known-problematic column
    if "hurst_exponent" in df_inf.columns:
        df_inf = df_inf.drop(columns=["hurst_exponent"])

    # Exclude metadata and other horizons' targets
    exclude_cols = {"trade_date", "symbol", "matrix_version", "created_at"} | {
        f"target_price_{h}d" for h in HORIZONS if h != horizon
    }

    feature_cols = [
        c for c in df_inf.columns if c not in exclude_cols and c != target_col
    ]

    # Ensure target column exists (may be all NaN at tail — that's fine)
    if target_col not in df_inf.columns:
        df_inf[target_col] = np.nan

    df_inf = df_inf.rename(columns={"trade_date": "timestamp"})
    df_inf["item_id"] = SYMBOL

    ts_cols = ["item_id", "timestamp", target_col, *feature_cols]
    df_ts = df_inf[ts_cols]

    tsdf = TimeSeriesDataFrame.from_data_frame(
        df_ts, id_column="item_id", timestamp_column="timestamp"
    )

    return tsdf


def compute_residual_offsets(engine, horizon: int) -> dict[str, float]:
    """Compute calibration offsets from historical OOF residuals.

    Reuses the same approach as generate_production_forecasts.py:
    residuals = target_value - predicted_price → quantiles.
    """
    query = """
        SELECT target_value, predicted_price
        FROM training.oof_core_1d
        WHERE horizon_days = %s
          AND symbol = %s
          AND target_value IS NOT NULL
          AND predicted_price IS NOT NULL
        ORDER BY trade_date DESC
        LIMIT 5000
    """
    df = pd.read_sql(query, engine, params=(horizon, SYMBOL))

    if len(df) < 30:
        logger.warning(
            f"  {horizon}d: insufficient OOF residuals ({len(df)}) for calibration"
        )
        return {"p10_off": 0.0, "p30_off": 0.0, "p70_off": 0.0, "p90_off": 0.0}

    residuals = (df["target_value"] - df["predicted_price"]).astype(float)
    return {
        "p10_off": float(residuals.quantile(0.10)),
        "p30_off": float(residuals.quantile(0.30)),
        "p70_off": float(residuals.quantile(0.70)),
        "p90_off": float(residuals.quantile(0.90)),
    }


def upsert_production_forecast(conn, horizon: int, row: dict) -> bool:
    """Upsert a single forecast row into forecasts.production_1d."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO forecasts.production_1d (
                horizon,
                as_of_date, forecast_date,
                p30, p50, p70,
                p10_cal, p90_cal,
                price_p30, price_p50, price_p70,
                price_p10_cal, price_p90_cal,
                current_price, model_version, run_id, created_at
            ) VALUES (
                %(horizon)s,
                %(as_of_date)s, %(forecast_date)s,
                %(p30)s, %(p50)s, %(p70)s,
                %(p10_cal)s, %(p90_cal)s,
                %(price_p30)s, %(price_p50)s, %(price_p70)s,
                %(price_p10_cal)s, %(price_p90_cal)s,
                %(current_price)s, %(model_version)s, %(run_id)s, NOW()
            )
            ON CONFLICT (horizon, as_of_date) DO UPDATE SET
                forecast_date = EXCLUDED.forecast_date,
                p30 = EXCLUDED.p30,
                p50 = EXCLUDED.p50,
                p70 = EXCLUDED.p70,
                p10_cal = EXCLUDED.p10_cal,
                p90_cal = EXCLUDED.p90_cal,
                price_p30 = EXCLUDED.price_p30,
                price_p50 = EXCLUDED.price_p50,
                price_p70 = EXCLUDED.price_p70,
                price_p10_cal = EXCLUDED.price_p10_cal,
                price_p90_cal = EXCLUDED.price_p90_cal,
                current_price = EXCLUDED.current_price,
                model_version = EXCLUDED.model_version,
                run_id = EXCLUDED.run_id,
                created_at = NOW()
            """,
            row,
        )
    return True


def run_forward_inference(
    horizons: list[int] | None = None,
    dry_run: bool = False,
) -> bool:
    """Generate forward forecasts for all horizons.

    Loads trained models, runs predict() on latest matrix data,
    calibrates quantiles from OOF residuals, and writes to production_1d.
    All horizons share the same as_of_date (today) for a coherent forecast set.
    """
    import_autogluon()

    if horizons is None:
        horizons = HORIZONS

    logger.info("=" * 60)
    logger.info("FORWARD INFERENCE — Production Forecast Generation")
    logger.info("=" * 60)

    as_of_date = date.today()
    logger.info(f"As-of date: {as_of_date}")

    with DatabaseConnections() as (engine, conn):
        # Step 1: Get current ZL price
        current_price, price_date = get_latest_zl_close(engine)
        if current_price is None:
            logger.error("No ZL close price found — cannot generate forecasts")
            return False
        logger.info(f"Current ZL close: {current_price:.4f} (as of {price_date})")

        # Step 2: Load matrix once (shared across horizons)
        df_matrix = load_matrix(engine)
        if len(df_matrix) < 100:
            logger.error(f"Matrix too small ({len(df_matrix)} rows) for inference")
            return False

        total_written = 0

        for horizon in horizons:
            logger.info(f"\n{'─' * 40}")
            logger.info(f"Horizon: {horizon}d")
            logger.info(f"{'─' * 40}")

            # Step 3: Load trained predictor
            model_path = MODELS_DIR / f"{horizon}d"
            if not model_path.exists():
                logger.error(f"  Model not found at {model_path}")
                return False

            try:
                predictor = TimeSeriesPredictor.load(
                    str(model_path), require_version_match=False
                )
            except Exception as e:
                logger.error(f"  Failed to load predictor: {e}")
                return False

            logger.info(
                f"  Loaded predictor: best={predictor.model_best}, "
                f"prediction_length={predictor.prediction_length}"
            )

            # Step 4: Build inference data
            tsdf = prepare_inference_data(df_matrix, horizon)

            # Reconcile columns: add any columns the model expects but the
            # matrix no longer provides (e.g. legacy pandas_ta indicators
            # removed after training). AutoGluon tree models handle NaN
            # natively via NaN-aware splits.
            required = set(predictor._learner.feature_generator.required_column_names)
            present = set(tsdf.columns)
            missing_cols = required - present
            if missing_cols:
                logger.warning(
                    f"  Adding {len(missing_cols)} missing columns as NaN: "
                    f"{sorted(missing_cols)[:6]}{'...' if len(missing_cols) > 6 else ''}"
                )
                nan_df = pd.DataFrame(
                    np.nan,
                    index=tsdf.index,
                    columns=sorted(missing_cols),
                )
                tsdf = pd.concat([tsdf, nan_df], axis=1)

            logger.info(f"  Inference data: {len(tsdf)} rows")

            # Step 5: Build known covariates for forecast horizon
            future_df = predictor.make_future_data_frame(tsdf)
            future_dates = pd.DatetimeIndex(future_df["timestamp"])
            seasonal_df = compute_seasonal_features(future_dates)

            known_covariates = future_df.copy()
            for col in SEASONAL_FEATURES:
                known_covariates[col] = seasonal_df[col].values

            known_cov_tsdf = TimeSeriesDataFrame.from_data_frame(
                known_covariates, id_column="item_id", timestamp_column="timestamp"
            )

            # Step 6: Run prediction
            try:
                predictions = predictor.predict(
                    data=tsdf,
                    known_covariates=known_cov_tsdf,
                )
            except Exception as e:
                logger.error(f"  Prediction failed: {e}", exc_info=True)
                return False

            # Extract point forecast (mean of the prediction horizon)
            # The predictor returns prediction_length rows; we want the terminal value
            # which represents the predicted price at t + horizon
            if "mean" in predictions.columns:
                predicted_price = float(predictions["mean"].iloc[-1])
            else:
                # Fallback: use 0.5 quantile
                q50_col = [c for c in predictions.columns if "0.5" in str(c)]
                if q50_col:
                    predicted_price = float(predictions[q50_col[0]].iloc[-1])
                else:
                    logger.error(
                        f"  No mean or 0.5 quantile in predictions: {predictions.columns.tolist()}"
                    )
                    return False

            logger.info(f"  Predicted price ({horizon}d): {predicted_price:.4f}")

            # Step 7: Calibrate quantiles from OOF residuals
            offsets = compute_residual_offsets(engine, horizon)
            p50 = predicted_price
            p30 = predicted_price + offsets["p30_off"]
            p70 = predicted_price + offsets["p70_off"]
            p10_cal = predicted_price + offsets["p10_off"]
            p90_cal = predicted_price + offsets["p90_off"]

            forecast_date = pd.Timestamp(as_of_date) + pd.tseries.offsets.BDay(horizon)

            logger.info(
                f"  Forecast: P10={p10_cal:.2f} P30={p30:.2f} "
                f"P50={p50:.2f} P70={p70:.2f} P90={p90_cal:.2f}"
            )
            logger.info(f"  Forecast date: {forecast_date.date()}")

            if dry_run:
                logger.info("  [DRY RUN] Would write to production_1d")
                continue

            # Step 8: Write to production_1d
            row = {
                "horizon": horizon,
                "as_of_date": as_of_date,
                "forecast_date": forecast_date.date(),
                "p30": p30,
                "p50": p50,
                "p70": p70,
                "p10_cal": p10_cal,
                "p90_cal": p90_cal,
                "price_p30": p30,
                "price_p50": p50,
                "price_p70": p70,
                "price_p10_cal": p10_cal,
                "price_p90_cal": p90_cal,
                "current_price": current_price,
                "model_version": f"forward_v1_{horizon}d_{predictor.model_best}",
                "run_id": None,
            }

            upsert_production_forecast(conn, horizon, row)
            conn.commit()
            total_written += 1
            logger.info("  Written to production_1d")

    logger.info(f"\n{'=' * 60}")
    if dry_run:
        logger.info(
            f"FORWARD INFERENCE DRY RUN COMPLETE — {len(horizons)} horizons previewed"
        )
    else:
        logger.info(
            f"FORWARD INFERENCE COMPLETE — {total_written}/{len(horizons)} horizons"
        )
    logger.info(f"{'=' * 60}")

    if dry_run:
        return True
    return total_written == len(horizons)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate forward forecasts via model inference"
    )
    parser.add_argument(
        "--horizon",
        type=str,
        default="all",
        help="Horizon (5, 21, 63, 126) or 'all'",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")

    args = parser.parse_args()

    if args.horizon.lower() == "all":
        horizons = HORIZONS
    else:
        h = int(args.horizon)
        if h not in HORIZONS:
            logger.error(f"Invalid horizon: {h}. Must be one of {HORIZONS}")
            sys.exit(1)
        horizons = [h]

    success = run_forward_inference(horizons=horizons, dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
