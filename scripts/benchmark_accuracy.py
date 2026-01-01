#!/usr/bin/env python3
"""
!!! DEPRECATED - DO NOT USE !!!
================================
This script uses DuckDB which is ARCHIVE ONLY.

USE INSTEAD:
    # Benchmarking should read from Prisma Postgres
    # This script needs to be rewritten to use Prisma

This script is kept for historical reference only.
It will raise an error if you try to run it.

Original description:
Benchmark forecast accuracy (rolling backtest) - Reads ZL prices and runs backtests
"""

import sys
print("=" * 70)
print("ERROR: This script is DEPRECATED!")
print("=" * 70)
print("")
print("DuckDB is ARCHIVE ONLY. Benchmarking should use Prisma Postgres.")
print("")
print("This script needs to be rewritten to use Prisma.")
print("See CLAUDE.md for the data architecture policy.")
print("=" * 70)
sys.exit(1)

# --- ORIGINAL CODE BELOW (disabled) ---

"""Benchmark forecast accuracy (rolling backtest).

Goal
----
Give you an AutoGluon-like "leaderboard" for accuracy, without adding heavy deps.

- Reads ZL prices from DuckDB (FUSION_DB_PATH, default: data/fusion.db)
- Runs rolling-origin backtests on a business-day calendar
- Evaluates point accuracy (MAE, MASE)

Models
------
- StatsForecast: AutoARIMA, AutoETS, AutoTheta, CES, MSTL, SeasonalNaive
- Optional: Chronos-Bolt (if you enable it and weights are available)
- Optional: NeuralForecast (if you enable it)

Notes
-----
- This script is read-only with respect to DuckDB (no schema/table creation).
- We regularize to a business-day index and forward-fill non-trading business days.
  This matches the earlier choice in the AutoGluon pipeline (freq='B').

Usage
-----
    .venv/bin/python scripts/benchmark_accuracy.py --horizons 5 21 63 126
    .venv/bin/python scripts/benchmark_accuracy.py --horizons 21 --n-windows 20

Optional Chronos:
    .venv/bin/python scripts/benchmark_accuracy.py --horizons 21 --enable-chronos

Optional NeuralForecast:
    .venv/bin/python scripts/benchmark_accuracy.py --horizons 21 --enable-neuralforecast
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import warnings


@dataclass
class WindowResult:
    model: str
    horizon: int
    cutoff: pd.Timestamp
    mae: float
    mase: float


def _get_db_path() -> Path:
    return Path(os.environ.get("FUSION_DB_PATH", "data/fusion.db")).resolve()


def load_zl_series() -> pd.Series:
    db_path = _get_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"DuckDB not found at {db_path}")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(
            """
            SELECT as_of_date::DATE as ds, CAST(zl_close AS DOUBLE) as y
            FROM training.specialist_signals_v3
            WHERE zl_close IS NOT NULL
            ORDER BY as_of_date
            """
        ).fetchdf()
    finally:
        con.close()

    df["ds"] = pd.to_datetime(df["ds"])
    df = df.dropna(subset=["ds", "y"]).sort_values("ds")

    # Regularize to business-day index and forward-fill.
    full_idx = pd.bdate_range(df["ds"].min(), df["ds"].max())
    s = df.set_index("ds")["y"].reindex(full_idx).ffill()
    s = s.replace([np.inf, -np.inf], np.nan).astype("float64")
    s.index.name = "ds"
    return s


def mase(y_true: np.ndarray, y_pred: np.ndarray, y_insample: np.ndarray) -> float:
    """MASE using seasonal period m=5 (business-week)."""
    m = 5
    if len(y_insample) <= m:
        return float("nan")
    naive_errors = np.abs(y_insample[m:] - y_insample[:-m])
    denom = float(np.mean(naive_errors)) if len(naive_errors) else float("nan")
    if denom == 0 or np.isnan(denom):
        return float("nan")
    return float(np.mean(np.abs(y_true - y_pred)) / denom)


def _describe_array(x: np.ndarray) -> dict[str, float]:
    x = np.asarray(x, dtype="float64")
    finite = np.isfinite(x)
    xf = x[finite]
    if xf.size == 0:
        return {
            "count": float(x.size),
            "finite": 0.0,
            "min": float("nan"),
            "max": float("nan"),
            "mean": float("nan"),
            "std": float("nan"),
        }
    return {
        "count": float(x.size),
        "finite": float(finite.sum()),
        "min": float(np.min(xf)),
        "max": float(np.max(xf)),
        "mean": float(np.mean(xf)),
        "std": float(np.std(xf)),
    }


def _clip_series_quantiles(y: pd.Series, q_lo: float, q_hi: float) -> pd.Series:
    if not (0.0 <= q_lo < q_hi <= 1.0):
        raise ValueError("clip quantiles must satisfy 0 <= q_lo < q_hi <= 1")
    lo = float(y.quantile(q_lo))
    hi = float(y.quantile(q_hi))
    return y.clip(lower=lo, upper=hi)


def _zscore_scale(y: pd.Series) -> tuple[pd.Series, float, float]:
    mean = float(y.mean())
    std = float(y.std(ddof=0))
    if not np.isfinite(std) or std == 0.0:
        std = 1.0
    return (y - mean) / std, mean, std


def _statsforecast_forecast(
    y_train: pd.Series,
    horizon: int,
    *,
    scale_zscore: bool,
    clip_quantiles: tuple[float, float] | None,
    enable_autoarima: bool,
    autoarima_approximation: bool,
) -> dict[str, np.ndarray]:
    from statsforecast import StatsForecast
    from statsforecast import models as sf_models

    y_model = y_train.astype("float64").copy()
    if clip_quantiles is not None:
        y_model = _clip_series_quantiles(y_model, clip_quantiles[0], clip_quantiles[1])

    mean = 0.0
    std = 1.0
    if scale_zscore:
        y_model, mean, std = _zscore_scale(y_model)

    sf_df = pd.DataFrame({"unique_id": "ZL", "ds": y_model.index, "y": y_model.values})

    # statsforecast model availability can vary across versions.
    # Build the model list defensively to keep this benchmark runnable.
    models = []

    def add_model(attr: str, **kwargs):
        cls = getattr(sf_models, attr, None)
        if cls is None:
            return
        models.append(cls(**kwargs))

    if enable_autoarima:
        add_model(
            "AutoARIMA",
            season_length=5,
            approximation=bool(autoarima_approximation),
        )
    add_model("AutoETS", season_length=5)
    add_model("AutoTheta", season_length=5)

    # Some versions expose CES as AutoCES or not at all.
    add_model("CES", season_length=5)
    add_model("AutoCES", season_length=5)

    # MSTL may not be present in older versions.
    add_model("MSTL", season_length=5)

    add_model("SeasonalNaive", season_length=5)

    if not models:
        raise RuntimeError("No StatsForecast models available in this environment.")

    # StatsForecast can emit numerical warnings on some windows (ARIMA in particular).
    # We prefer to keep the benchmark running and let metrics decide.
    with warnings.catch_warnings():
        if _SUPPRESS_WARNINGS:
            warnings.simplefilter("ignore", category=RuntimeWarning)
            warnings.simplefilter("ignore", category=UserWarning)
        old_err = np.seterr(all="ignore") if _SUPPRESS_WARNINGS else None
        try:
            sf = StatsForecast(models=models, freq="B", n_jobs=1)
            sf.fit(sf_df)
            fcst = sf.predict(h=horizon)
        finally:
            if old_err is not None:
                np.seterr(**old_err)

    out: dict[str, np.ndarray] = {}
    for col in fcst.columns:
        if col in ("unique_id", "ds"):
            continue
        y_pred = fcst[col].to_numpy(dtype="float64")
        if scale_zscore:
            y_pred = y_pred * std + mean
        out[str(col)] = y_pred
    return out


def _chronos_bolt_forecast(
    y_train: pd.Series,
    horizon: int,
    *,
    size: str = "small",
    scale_zscore: bool,
    clip_quantiles: tuple[float, float] | None,
) -> np.ndarray:
    import torch
    from chronos import ChronosBoltPipeline

    device = "mps" if torch.backends.mps.is_available() else "cpu"

    pipeline = ChronosBoltPipeline.from_pretrained(
        f"amazon/chronos-bolt-{size}",
        device_map=device,
        torch_dtype=torch.float32,
    )

    y_model = y_train.astype("float64").copy()
    if clip_quantiles is not None:
        y_model = _clip_series_quantiles(y_model, clip_quantiles[0], clip_quantiles[1])

    mean = 0.0
    std = 1.0
    if scale_zscore:
        y_model, mean, std = _zscore_scale(y_model)

    context = torch.tensor(y_model.values.astype(np.float32), dtype=torch.float32)
    forecast = pipeline.predict(
        context=context, prediction_length=horizon, num_samples=64
    )

    samples = forecast.detach().cpu().numpy()  # shape: [num_samples, horizon]
    y_pred = np.median(samples, axis=0).astype("float64")
    if scale_zscore:
        y_pred = y_pred * std + mean
    return y_pred


def _neuralforecast_forecast(
    y_train: pd.Series,
    horizon: int,
    *,
    scale_zscore: bool,
    clip_quantiles: tuple[float, float] | None,
) -> dict[str, np.ndarray]:
    from neuralforecast import NeuralForecast
    from neuralforecast.models import NBEATS, NHITS, NBEATSx

    y_model = y_train.astype("float64").copy()
    if clip_quantiles is not None:
        y_model = _clip_series_quantiles(y_model, clip_quantiles[0], clip_quantiles[1])

    mean = 0.0
    std = 1.0
    if scale_zscore:
        y_model, mean, std = _zscore_scale(y_model)

    nf_df = pd.DataFrame({"unique_id": "ZL", "ds": y_model.index, "y": y_model.values})

    models = [
        NBEATS(input_size=2 * horizon, h=horizon, max_epochs=50),
        NHITS(input_size=2 * horizon, h=horizon, max_epochs=50),
    ]

    nf = NeuralForecast(models=models, freq="B")
    nf.fit(df=nf_df)
    fcst = nf.predict()

    out: dict[str, np.ndarray] = {}
    for model_name in fcst.columns:
        if model_name in ("unique_id", "ds"):
            continue
        y_pred = fcst[model_name].to_numpy(dtype="float64")
        if scale_zscore:
            y_pred = y_pred * std + mean
        out[str(model_name)] = y_pred
    return out


def _autogluon_forecast(
    y_train: pd.Series,
    horizon: int,
    time_limit: int,
    presets: str,
) -> np.ndarray:
    from autogluon.timeseries import TimeSeriesDataFrame, TimeSeriesPredictor

    df = y_train.to_frame(name="y").reset_index()
    df["item_id"] = "ZL"
    ts_df = TimeSeriesDataFrame.from_data_frame(
        df,
        id_column="item_id",
        timestamp_column="ds",
    )

    predictor = TimeSeriesPredictor(
        prediction_length=horizon,
        eval_metric="MAE",
    )

    # Suppress verbose output from AutoGluon
    import logging

    ag_logger = logging.getLogger("autogluon")
    original_level = ag_logger.level
    ag_logger.setLevel(logging.ERROR)

    try:
        predictor.fit(
            ts_df,
            presets=presets,
            time_limit=time_limit,
        )
        predictions = predictor.predict(ts_df)
        y_pred = predictions["mean"].to_numpy()
    finally:
        ag_logger.setLevel(original_level)

    return y_pred


def rolling_backtest(
    series: pd.Series,
    horizons: list[int],
    n_windows: int,
    min_train: int,
    enable_chronos: bool,
    enable_neuralforecast: bool,
    enable_autogluon: bool,
    *,
    scale_zscore: bool,
    clip_quantiles: tuple[float, float] | None,
    diagnostics: bool,
    enable_autoarima: bool,
    autoarima_approximation: bool,
) -> pd.DataFrame:
    results: list[WindowResult] = []

    max_h = max(horizons)
    if len(series) < min_train + max_h + n_windows:
        raise ValueError(
            f"Not enough data for requested backtest. Have {len(series)} business days; "
            f"need at least ~{min_train + max_h + n_windows}."
        )

    # Choose cutoffs evenly spaced near the end.
    end = len(series) - max_h
    cutoffs = np.linspace(min_train, end - 1, num=n_windows, dtype=int)

    if diagnostics:
        desc = _describe_array(series.to_numpy(dtype="float64"))
        print(
            "Series diagnostics:"
            f" count={int(desc['count'])}"
            f" finite={int(desc['finite'])}"
            f" min={desc['min']:.6g}"
            f" max={desc['max']:.6g}"
            f" mean={desc['mean']:.6g}"
            f" std={desc['std']:.6g}"
        )
        if clip_quantiles is not None:
            q_lo, q_hi = clip_quantiles
            lo = float(series.quantile(q_lo))
            hi = float(series.quantile(q_hi))
            print(f"Clipping enabled: q{q_lo:.4g}={lo:.6g}, q{q_hi:.4g}={hi:.6g}")
        if scale_zscore:
            print(
                "Z-score scaling enabled (per-window; predictions inverted to original scale)."
            )

    for cutoff_idx in cutoffs:
        cutoff_date = series.index[cutoff_idx]
        y_train = series.iloc[: cutoff_idx + 1]

        # StatsForecast forecasts (one fit per cutoff; reuse for all horizons)
        sf_point_by_model: dict[int, dict[str, np.ndarray]] = {}
        for h in horizons:
            try:
                sf_point_by_model[h] = _statsforecast_forecast(
                    y_train,
                    horizon=h,
                    scale_zscore=scale_zscore,
                    clip_quantiles=clip_quantiles,
                    enable_autoarima=enable_autoarima,
                    autoarima_approximation=autoarima_approximation,
                )
            except Exception as e:
                # Fail-soft: record an error marker for this cutoff/horizon.
                sf_point_by_model[h] = {
                    f"ERROR({type(e).__name__})": np.full(h, np.nan)
                }

        # NeuralForecast forecasts
        nf_point_by_model: dict[int, dict[str, np.ndarray]] = {}
        if enable_neuralforecast:
            for h in horizons:
                try:
                    nf_point_by_model[h] = _neuralforecast_forecast(
                        y_train,
                        horizon=h,
                        scale_zscore=scale_zscore,
                        clip_quantiles=clip_quantiles,
                    )
                except Exception as e:
                    nf_point_by_model[h] = {
                        f"ERROR({type(e).__name__})": np.full(h, np.nan)
                    }

        # AutoGluon forecasts
        ag_point_by_model: dict[int, dict[str, np.ndarray]] = {}
        if enable_autogluon:
            for h in horizons:
                if h != 21:  # Only run for the specified prediction length
                    continue
                try:
                    ag_point_by_model[h] = _autogluon_forecast(
                        y_train,
                        horizon=h,
                        time_limit=300,
                        presets="medium_quality",
                    )
                except Exception as e:
                    ag_point_by_model[h] = {
                        f"ERROR({type(e).__name__})": np.full(h, np.nan)
                    }

        for h in horizons:
            y_true = series.iloc[cutoff_idx + 1 : cutoff_idx + 1 + h].to_numpy(
                dtype=float
            )

            for model_name, y_pred in sf_point_by_model[h].items():
                if len(y_pred) != len(y_true):
                    continue
                results.append(
                    WindowResult(
                        model=f"statsforecast::{model_name}",
                        horizon=h,
                        cutoff=cutoff_date,
                        mae=float(np.mean(np.abs(y_true - y_pred))),
                        mase=mase(y_true, y_pred, y_train.to_numpy(dtype=float)),
                    )
                )

            if enable_neuralforecast:
                for model_name, y_pred in nf_point_by_model[h].items():
                    if len(y_pred) != len(y_true):
                        continue
                    results.append(
                        WindowResult(
                            model=f"neuralforecast::{model_name}",
                            horizon=h,
                            cutoff=cutoff_date,
                            mae=float(np.mean(np.abs(y_true - y_pred))),
                            mase=mase(y_true, y_pred, y_train.to_numpy(dtype=float)),
                        )
                    )

            if enable_autogluon:
                for h in horizons:
                    if h != 21:  # Only run for the specified prediction length
                        continue
                    try:
                        y_pred_ag = _autogluon_forecast(
                            y_train,
                            horizon=h,
                            time_limit=300,
                            presets="medium_quality",
                        )
                        results.append(
                            WindowResult(
                                model="autogluon::medium_quality",
                                horizon=h,
                                cutoff=cutoff_date,
                                mae=float(np.mean(np.abs(y_true - y_pred_ag))),
                                mase=mase(
                                    y_true, y_pred_ag, y_train.to_numpy(dtype=float)
                                ),
                            )
                        )
                    except Exception as e:
                        results.append(
                            WindowResult(
                                model=f"autogluon::ERROR({type(e).__name__})",
                                horizon=h,
                                cutoff=cutoff_date,
                                mae=float("nan"),
                                mase=float("nan"),
                            )
                        )

            if enable_chronos:
                try:
                    y_pred_c = _chronos_bolt_forecast(
                        y_train,
                        horizon=h,
                        size="small",
                        scale_zscore=scale_zscore,
                        clip_quantiles=clip_quantiles,
                    )
                    results.append(
                        WindowResult(
                            model="chronos_bolt_small::median",
                            horizon=h,
                            cutoff=cutoff_date,
                            mae=float(np.mean(np.abs(y_true - y_pred_c))),
                            mase=mase(y_true, y_pred_c, y_train.to_numpy(dtype=float)),
                        )
                    )
                except Exception as e:
                    # Fail-soft: keep the benchmark usable without Chronos.
                    results.append(
                        WindowResult(
                            model=f"chronos_bolt_small::ERROR({type(e).__name__})",
                            horizon=h,
                            cutoff=cutoff_date,
                            mae=float("nan"),
                            mase=float("nan"),
                        )
                    )

    df = pd.DataFrame([r.__dict__ for r in results])
    return df


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    ok = df[~df["model"].str.contains("ERROR", na=False)].copy()
    agg = (
        ok.groupby(["horizon", "model"], as_index=False)
        .agg(
            mae_mean=("mae", "mean"),
            mase_mean=("mase", "mean"),
            windows=("mae", "count"),
        )
        .sort_values(["horizon", "mase_mean", "mae_mean"], ascending=[True, True, True])
    )
    return agg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizons", nargs="+", type=int, default=[5, 21, 63, 126])
    ap.add_argument("--n-windows", type=int, default=12)
    ap.add_argument("--min-train", type=int, default=750)
    ap.add_argument("--enable-chronos", action="store_true")
    ap.add_argument(
        "--enable-neuralforecast",
        action="store_true",
        help="Enable NeuralForecast models (NBEATS, NHITS).",
    )
    ap.add_argument(
        "--enable-autogluon",
        action="store_true",
        help="Enable AutoGluon models.",
    )
    ap.add_argument(
        "--disable-autoarima",
        action="store_true",
        help="Skip StatsForecast AutoARIMA (it can emit numerical warnings on some windows).",
    )
    ap.add_argument(
        "--autoarima-approximation",
        action="store_true",
        help="Use AutoARIMA approximation=True (can be more numerically stable in some cases).",
    )
    ap.add_argument(
        "--scale-zscore",
        action="store_true",
        help="Standardize y per window before fitting (helps avoid numerical overflows); predictions are unscaled back.",
    )
    ap.add_argument(
        "--clip-quantiles",
        nargs=2,
        type=float,
        metavar=("Q_LO", "Q_HI"),
        help="Clip y per window to these quantiles before fitting (e.g. --clip-quantiles 0.001 0.999).",
    )
    ap.add_argument(
        "--diagnostics",
        action="store_true",
        help="Print basic series diagnostics (min/max/std, clipping bounds, scaling enabled).",
    )
    ap.add_argument(
        "--no-suppress-warnings",
        action="store_true",
        help="Do not suppress numerical RuntimeWarnings from underlying libraries.",
    )
    args = ap.parse_args()

    global _SUPPRESS_WARNINGS
    _SUPPRESS_WARNINGS = not args.no_suppress_warnings

    series = load_zl_series()

    print(f"DB: {_get_db_path()}")
    print(
        f"Series business days: {len(series):,} | {series.index.min().date()} → {series.index.max().date()}"
    )

    df = rolling_backtest(
        series=series,
        horizons=args.horizons,
        n_windows=args.n_windows,
        min_train=args.min_train,
        enable_chronos=args.enable_chronos,
        enable_neuralforecast=bool(args.enable_neuralforecast),
        enable_autogluon=bool(args.enable_autogluon),
        scale_zscore=bool(args.scale_zscore),
        clip_quantiles=tuple(args.clip_quantiles) if args.clip_quantiles else None,
        diagnostics=bool(args.diagnostics),
        enable_autoarima=not bool(args.disable_autoarima),
        autoarima_approximation=bool(args.autoarima_approximation),
    )

    summary = summarize(df)

    pd.set_option("display.width", 140)
    pd.set_option("display.max_rows", 200)

    print("\n=== Accuracy leaderboard (lower is better) ===")
    print(summary.to_string(index=False))

    # Best model per horizon
    best = (
        summary.sort_values(["horizon", "mase_mean", "mae_mean"])
        .groupby("horizon")
        .head(1)
    )
    print("\n=== Best per horizon ===")
    print(
        best[["horizon", "model", "mase_mean", "mae_mean", "windows"]].to_string(
            index=False
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
