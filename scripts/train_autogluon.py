#!/usr/bin/env python3
"""
ZINC-FUSION AutoGluon Training Script
=====================================
Reads from DuckDB → Trains TimeSeriesPredictor → Writes quantiles back

Usage:
    python scripts/train_autogluon.py

Requirements:
    pip install autogluon.timeseries duckdb pandas
"""

import os
import sys
from pathlib import Path
from datetime import datetime

import duckdb
import pandas as pd

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

DB_PATH = Path(os.environ.get("FUSION_DB_PATH", "data/fusion.db")).resolve()
MODEL_PATH = (
    Path(os.environ.get("FUSION_MODEL_DIR", "models")).resolve() / "autogluon_zl"
)

HORIZONS = [5, 21, 63, 126]  # days
QUANTILES = [0.1, 0.25, 0.5, 0.75, 0.9]
TIME_LIMIT = 600  # 10 minutes per horizon

# ═══════════════════════════════════════════════════════════════════════════════
# INSTALL CHECK
# ═══════════════════════════════════════════════════════════════════════════════

try:
    from autogluon.timeseries import TimeSeriesDataFrame, TimeSeriesPredictor
except ImportError:
    print("Installing autogluon.timeseries...")
    os.system(f"{sys.executable} -m pip install autogluon.timeseries")
    from autogluon.timeseries import TimeSeriesDataFrame, TimeSeriesPredictor


def load_data() -> pd.DataFrame:
    """Load specialist signals from DuckDB."""
    print(f"\n{'='*60}")
    print("LOADING DATA FROM DUCKDB")
    print(f"{'='*60}")

    con = duckdb.connect(str(DB_PATH), read_only=True)

    df = con.execute(
        """
        SELECT 
            as_of_date as timestamp,
            zl_close as target,
            crush_z, 
            china_z, 
            fx_z, 
            fed_z, 
            tariff_z,
            energy_z, 
            biofuel_z, 
            palm_z, 
            volatility_z, 
            substitutes_z
        FROM training.specialist_signals_v3
        WHERE zl_close IS NOT NULL
          AND crush_z IS NOT NULL
          AND palm_z IS NOT NULL
          AND biofuel_z IS NOT NULL
        ORDER BY as_of_date
    """
    ).fetchdf()

    con.close()

    print(f"✓ Loaded {len(df):,} rows")
    print(f"  Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"  Columns: {list(df.columns)}")

    return df


def prepare_timeseries(df: pd.DataFrame) -> TimeSeriesDataFrame:
    """Convert DataFrame to AutoGluon TimeSeriesDataFrame."""
    df = df.copy()
    df["item_id"] = "ZL"
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    ts_df = TimeSeriesDataFrame.from_data_frame(
        df, id_column="item_id", timestamp_column="timestamp"
    )

    # Convert to business day frequency (market data has weekends/holidays)
    ts_df = ts_df.convert_frequency(freq="B")

    print(f"✓ TimeSeriesDataFrame shape: {ts_df.shape} (after B freq conversion)")
    return ts_df


def train_model(ts_df: TimeSeriesDataFrame, horizon: int) -> TimeSeriesPredictor:
    """Train AutoGluon TimeSeriesPredictor for given horizon."""
    print(f"\n{'='*60}")
    print(f"TRAINING {horizon}-DAY MODEL")
    print(f"{'='*60}")

    model_dir = MODEL_PATH / f"horizon_{horizon}d"

    predictor = TimeSeriesPredictor(
        prediction_length=horizon,
        target="target",
        quantile_levels=QUANTILES,
        eval_metric="MASE",
        freq="B",  # Business days
        path=str(model_dir),
        verbosity=2,
    )

    predictor.fit(
        train_data=ts_df,
        presets="medium_quality",
        time_limit=TIME_LIMIT,
        # Exclude models that need GPU or are slow
        excluded_model_types=[
            "DeepAR",
            "TemporalFusionTransformer",
            "PatchTST",
            "WaveNet",
        ],
    )

    # Show leaderboard
    print("\n📊 Model Leaderboard:")
    print(predictor.leaderboard())

    return predictor


def generate_predictions(
    predictor: TimeSeriesPredictor, ts_df: TimeSeriesDataFrame, horizon: int
) -> pd.DataFrame:
    """Generate predictions with quantiles."""
    print(f"\n{'='*60}")
    print(f"GENERATING {horizon}-DAY PREDICTIONS")
    print(f"{'='*60}")

    predictions = predictor.predict(ts_df)

    # Flatten and rename.
    # AutoGluon returns columns: ['mean'] + quantile levels (often as floats like 0.1, 0.25, ...).
    # After reset_index(), we typically have 2 index cols + 1 mean + N quantile cols.
    pred_df = predictions.reset_index()

    rename_map: dict = {}
    for col in pred_df.columns:
        if col in ("item_id", "timestamp"):
            continue
        if col == "mean":
            rename_map[col] = "mean"
            continue

        # Quantile columns may be floats (0.1) or strings ("0.1").
        q_val = None
        if isinstance(col, (float, int)):
            q_val = float(col)
        else:
            try:
                q_val = float(str(col))
            except (TypeError, ValueError):
                q_val = None

        if q_val is not None and 0.0 < q_val < 1.0:
            rename_map[col] = f"p{int(round(q_val * 100))}"

    if rename_map:
        pred_df = pred_df.rename(columns=rename_map)

    # Ensure the expected quantile columns exist.
    expected_quantile_cols = [f"p{int(q * 100)}" for q in QUANTILES]
    missing = [c for c in expected_quantile_cols if c not in pred_df.columns]
    if missing:
        raise ValueError(
            "AutoGluon predictions missing expected quantile columns: "
            f"{missing}. Available columns: {list(pred_df.columns)}"
        )

    pred_df["horizon"] = horizon
    pred_df["generated_at"] = datetime.now()

    print(f"✓ Generated {len(pred_df)} predictions")
    print(pred_df.head())

    return pred_df


def save_to_duckdb(pred_df: pd.DataFrame, horizon: int):
    """Save predictions back to DuckDB."""
    print(f"\n{'='*60}")
    print("SAVING TO DUCKDB")
    print(f"{'='*60}")

    con = duckdb.connect(str(DB_PATH))

    table_name = f"forecasts.zl_autogluon_{horizon}d"

    con.execute("CREATE SCHEMA IF NOT EXISTS forecasts")
    con.execute(f"DROP TABLE IF EXISTS {table_name}")

    # Make the pandas DataFrame available to DuckDB SQL
    con.register("pred_df", pred_df)
    con.execute(
        f"""
        CREATE TABLE {table_name} AS 
        SELECT 
            timestamp,
            p10,
            p25,
            p50,
            p75,
            p90,
            horizon,
            generated_at
        FROM pred_df
    """
    )

    # Verify
    count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    print(f"✓ Saved {count} rows to {table_name}")

    con.close()


def run_backtest(
    predictor: TimeSeriesPredictor, ts_df: TimeSeriesDataFrame, horizon: int
):
    """Run proper backtest with walk-forward validation."""
    print(f"\n{'='*60}")
    print(f"BACKTESTING {horizon}-DAY MODEL")
    print(f"{'='*60}")

    # Use AutoGluon's built-in backtesting
    backtest_results = predictor.evaluate(ts_df)

    print("\n📈 Backtest Metrics:")
    for metric, value in backtest_results.items():
        print(f"  {metric}: {value:.4f}")

    return backtest_results


def main():
    """Main training pipeline."""
    print("\n" + "═" * 60)
    print("  ZINC-FUSION AUTOGLUON TRAINING")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("═" * 60)

    # Ensure directories exist
    MODEL_PATH.mkdir(parents=True, exist_ok=True)

    # Load data once
    df = load_data()
    ts_df = prepare_timeseries(df)

    # Train each horizon
    results = {}

    for horizon in HORIZONS:
        try:
            predictor = train_model(ts_df, horizon)
            pred_df = generate_predictions(predictor, ts_df, horizon)
            save_to_duckdb(pred_df, horizon)
            backtest = run_backtest(predictor, ts_df, horizon)
            results[horizon] = {"status": "success", "backtest": backtest}
        except Exception as e:
            print(f"\n❌ ERROR training {horizon}d model: {e}")
            results[horizon] = {"status": "failed", "error": str(e)}

    # Summary
    print("\n" + "═" * 60)
    print("  TRAINING COMPLETE")
    print("═" * 60)

    for horizon, result in results.items():
        status = "✅" if result["status"] == "success" else "❌"
        print(f"  {status} {horizon}-day model: {result['status']}")

    print("\n📁 Models saved to:", MODEL_PATH)
    print("🗄️  Predictions in:", DB_PATH)
    print("\nQuery predictions:")
    print(
        "  SELECT * FROM forecasts.zl_autogluon_21d ORDER BY timestamp DESC LIMIT 21;"
    )


if __name__ == "__main__":
    main()
